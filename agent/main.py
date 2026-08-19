"""Sending agent main loop (ROADMAP task 1.7, TECH_SPEC §5.1).

Polls the web app's queue API over HTTP (never shares the DB), processes each
send_item through the selected Sender, and reports results. Runs MockSender on
macOS/Docker and KakaoDesktopSender on Windows.

Usage:
  python -m agent.main --config agent/config.yaml
Env overrides (used by docker-compose): DEALFLOW_SERVER_URL, DEALFLOW_AGENT_TOKEN,
DEALFLOW_SENDER, DEALFLOW_MOCK_FAIL_RATE, DEALFLOW_POLL_INTERVAL.

All send-rate numbers (delays, per-job cap) come from config.yaml — never hardcoded
(ROADMAP 공통 원칙 2).
"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import random
import socket
import sys
import time
from pathlib import Path

import requests
import yaml

log = logging.getLogger("agent")

DEFAULT_CONFIG = {
    "server_url": "http://127.0.0.1:8000",
    "token": "agt_demo_token_sprint1",
    "sender": "auto",          # auto | mock | kakao_windows
    "poll_interval_sec": 5,
    "heartbeat_interval_sec": 20,
    "agent_version": "0.1.0",
    "delay_min_sec": 3,        # human-like inter-send delay (TECH_SPEC §5.5)
    "delay_max_sec": 7,
    "job_cap": 60,             # 1잡 상한 (계정 보호)
    "mock": {"delay_min_sec": 0.5, "delay_max_sec": 1.5, "fail_rate": 0.15},
    "selectors_file": "agent/selectors.yaml",
}


def load_config(path: str) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    p = Path(path)
    if p.exists():
        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cfg.update({k: v for k, v in loaded.items() if v is not None})
    # env overrides
    cfg["server_url"] = os.environ.get("DEALFLOW_SERVER_URL", cfg["server_url"])
    cfg["token"] = os.environ.get("DEALFLOW_AGENT_TOKEN", cfg["token"])
    cfg["sender"] = os.environ.get("DEALFLOW_SENDER", cfg["sender"])
    if os.environ.get("DEALFLOW_POLL_INTERVAL"):
        cfg["poll_interval_sec"] = float(os.environ["DEALFLOW_POLL_INTERVAL"])
    if os.environ.get("DEALFLOW_MOCK_FAIL_RATE"):
        cfg.setdefault("mock", {})["fail_rate"] = float(os.environ["DEALFLOW_MOCK_FAIL_RATE"])
    return cfg


def build_sender(cfg: dict):
    choice = cfg.get("sender", "auto")
    if choice == "auto":
        choice = "kakao_windows" if platform.system() == "Windows" else "mock"

    if choice == "kakao_mac":
        # macOS 카카오톡 UI 자동화 — 반드시 호스트에서 실행(도커는 GUI 제어 불가).
        from agent.sender import kakao_mac
        log.info("using KakaoMacSender (macOS 카카오톡)")
        return kakao_mac.create(cfg.get("kakao_mac", {}))

    if choice == "telegram":
        # 테스트용 실제 수신 채널 — 운영자 본인에게만 전송(실제 투자사 발송 아님).
        from agent.sender.telegram import create_from_env
        log.info("using TelegramSender (테스트 수신 — 본인에게만 발송)")
        return create_from_env(cfg)

    if choice == "kakao_windows":
        from agent.sender import kakao_windows
        selectors = {}
        sel_path = Path(cfg.get("selectors_file", "agent/selectors.yaml"))
        if sel_path.exists():
            selectors = yaml.safe_load(sel_path.read_text(encoding="utf-8")) or {}
        screenshot_dir = str(Path(__file__).resolve().parent.parent / "agent_logs")
        log.info("using KakaoDesktopSender (Windows)")
        return kakao_windows.create(selectors, screenshot_dir)

    from agent.sender.mock import MockSender
    m = cfg.get("mock", {})
    log.info("using MockSender (fail_rate=%s)", m.get("fail_rate"))
    return MockSender(
        delay_min=float(m.get("delay_min_sec", 0.5)),
        delay_max=float(m.get("delay_max_sec", 1.5)),
        fail_rate=float(m.get("fail_rate", 0.0)),
    )


class AgentClient:
    def __init__(self, cfg: dict):
        self.base = cfg["server_url"].rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {cfg['token']}"})
        self.version = cfg.get("agent_version", "0.1.0")
        self.hostname = socket.gethostname()
        # 어떤 발송기인지 서버에 알린다 — 배지에서 mock/실발송을 구분하기 위함.
        self.sender_name = "unknown"

    def heartbeat(self):
        return self.session.post(f"{self.base}/api/agent/heartbeat",
                                 json={"hostname": self.hostname, "agent_version": self.version,
                                       "sender": self.sender_name},
                                 timeout=10)

    def poll(self):
        r = self.session.get(f"{self.base}/api/agent/poll", timeout=15)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def report_item(self, item_id: int, status: str, error=None, screenshot_b64=None):
        return self.session.post(
            f"{self.base}/api/agent/items/{item_id}/result",
            json={"status": status, "error": error, "screenshot_b64": screenshot_b64},
            timeout=15,
        )

    def report_job(self, job_id: int, status: str):
        return self.session.post(f"{self.base}/api/agent/jobs/{job_id}/status",
                                 json={"status": status}, timeout=15)


def process_job(client: AgentClient, sender, job: dict, cfg: dict):
    job_id = job["job_id"]
    items = job.get("items", [])
    cap = int(cfg.get("job_cap", 60))
    if len(items) > cap:
        log.warning("job %s has %d items > cap %d; processing first %d only",
                    job_id, len(items), cap, cap)
        items = items[:cap]

    log.info("processing job %s (%d items)", job_id, len(items))
    any_fail = False
    for i, item in enumerate(items, start=1):
        result = sender.send_text(item["room_name"], item["message"])
        if result.ok:
            client.report_item(item["id"], "sent")
            log.info("  [%d/%d] SENT room=%r", i, len(items), item["room_name"])
        else:
            any_fail = True
            client.report_item(item["id"], "failed", error=result.error,
                               screenshot_b64=result.screenshot_b64)
            log.warning("  [%d/%d] FAILED room=%r: %s", i, len(items), item["room_name"], result.error)
        # human-like inter-send delay
        if i < len(items):
            time.sleep(random.uniform(float(cfg["delay_min_sec"]), float(cfg["delay_max_sec"])))

    client.report_job(job_id, "done_with_errors" if any_fail else "done")
    log.info("job %s complete (errors=%s)", job_id, any_fail)



def _setup_logging() -> None:
    """콘솔 + 파일 로깅.

    카톡 자동화 실패는 화면을 못 보는 상태에서 원인을 찾아야 하므로
    (포커스를 뺏기면 안 되니 지켜보기 어렵다) 파일 로그가 사실상 유일한 단서다.
    agent_logs/agent.log 에 회전 저장한다.
    """
    from logging.handlers import RotatingFileHandler

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    log_dir = Path(__file__).resolve().parent.parent / "agent_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_dir / "agent.log", maxBytes=2_000_000,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
        root.info("로그 파일: %s", log_dir / "agent.log")
    except Exception as exc:  # noqa: BLE001
        root.warning("파일 로그를 열지 못했습니다: %s", exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description="dealflow sending agent")
    parser.add_argument("--config", default="agent/config.yaml")
    args = parser.parse_args(argv)

    _setup_logging()

    cfg = load_config(args.config)
    log.info("agent starting; server=%s sender=%s", cfg["server_url"], cfg["sender"])
    sender = build_sender(cfg)
    client = AgentClient(cfg)
    client.sender_name = getattr(sender, "name", "unknown")

    last_heartbeat = 0.0
    while True:
        try:
            now = time.time()
            if now - last_heartbeat >= float(cfg["heartbeat_interval_sec"]):
                client.heartbeat()
                last_heartbeat = now

            job = client.poll()
            if job:
                process_job(client, sender, job, cfg)
            else:
                time.sleep(float(cfg["poll_interval_sec"]))
        except requests.RequestException as exc:
            log.warning("server unreachable (%s); retrying...", exc)
            time.sleep(float(cfg["poll_interval_sec"]))
        except KeyboardInterrupt:
            log.info("agent stopped by user")
            break
        except Exception:  # noqa: BLE001
            log.exception("unexpected error; continuing")
            time.sleep(float(cfg["poll_interval_sec"]))


if __name__ == "__main__":
    sys.exit(main())
