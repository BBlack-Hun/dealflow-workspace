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

from .version import VERSION

log = logging.getLogger("agent")

# 이 에이전트가 처리할 수 있는 잡 종류. 서버 poll 에 그대로 알린다.
# deal_intro/ir_delivery = 문구 전송, verify_room = 방 이름 대조(전송 없음).
SEND_KINDS = ("deal_intro", "ir_delivery")
VERIFY_KIND = "verify_room"
SUPPORTED_KINDS = SEND_KINDS + (VERIFY_KIND,)

DEFAULT_CONFIG = {
    "server_url": "http://127.0.0.1:8000",
    "token": "agt_demo_token_sprint1",
    "sender": "auto",          # auto | mock | kakao_windows
    "poll_interval_sec": 5,
    "heartbeat_interval_sec": 20,
    # 버전은 config 가 아니라 코드에서 온다 — config 는 사용자가 고칠 수
    # 있고, 그러면 서버가 낡은 프로그램을 못 짚는다.
    "agent_version": VERSION,
    "delay_min_sec": 3,        # human-like inter-send delay (TECH_SPEC §5.5)
    "delay_max_sec": 7,
    "job_cap": 60,             # 1잡 상한 (계정 보호)
    "part_gap_sec": 1.2,       # 한 건이 여러 통일 때 통 사이 간격
                               # (연달아 쏟으면 카톡이 순서를 뒤집는다)
    # 방 연결 확인은 메시지를 보내지 않아 검색만 반복한다. 그래도 사람 속도를 흉내낸다
    # (연속 검색도 자동화로 읽힐 수 있음). 발송 지연과 별개 값으로 둔다.
    "room_marker": "",   # 딜소개 방을 가려내는 표식(예: "우리브이씨 Asset")
    "verify_delay_min_sec": 1,
    "verify_delay_max_sec": 2,
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
    cfg["room_marker"] = os.environ.get("DEALFLOW_ROOM_MARKER", cfg.get("room_marker", ""))
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
        self.version = VERSION
        self.hostname = socket.gethostname()
        # 어떤 발송기인지 서버에 알린다 — 배지에서 mock/실발송을 구분하기 위함.
        self.sender_name = "unknown"

    def heartbeat(self):
        return self.session.post(f"{self.base}/api/agent/heartbeat",
                                 json={"hostname": self.hostname, "agent_version": self.version,
                                       "sender": self.sender_name},
                                 timeout=10)

    def poll(self):
        # 처리할 수 있는 잡 종류를 함께 알린다. 서버는 모르는 종류를 주지 않는다
        # (구버전 에이전트가 확인 잡을 발송으로 오해하는 사고를 구조적으로 막는다).
        r = self.session.get(f"{self.base}/api/agent/poll",
                             params={"kinds": ",".join(SUPPORTED_KINDS)}, timeout=15)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def report_item(self, item_id: int, status: str, error=None, screenshot_b64=None,
                    verify_result=None, found_room=None, candidates=None):
        return self.session.post(
            f"{self.base}/api/agent/items/{item_id}/result",
            json={"status": status, "error": error, "screenshot_b64": screenshot_b64,
                  "verify_result": verify_result,
                  "found_room": found_room, "candidates": candidates},
            timeout=15,
        )

    def report_diagnostics(self, payload: dict):
        """진단 스냅샷을 서버로 올린다(실패해도 발송에는 영향 없음)."""
        payload = {**payload, "agent_hostname": self.hostname}
        try:
            return self.session.post(f"{self.base}/api/agent/diagnostics",
                                     json=payload, timeout=15)
        except Exception as exc:  # noqa: BLE001
            log.warning("진단 업로드 실패: %s", exc)
            return None

    def report_job(self, job_id: int, status: str):
        return self.session.post(f"{self.base}/api/agent/jobs/{job_id}/status",
                                 json={"status": status}, timeout=15)


def send_item(sender, item: dict, cfg: dict):
    """한 건을 보낸다. **여러 통으로 나뉘어 있으면 순서대로.**

    IR 자료 전달이 그렇다 — 링크를 한 통씩 먼저 던지고 마지막에 설명을 붙인다.
    카톡에서 링크는 각자 미리보기 카드로 떠야 하고, 그게 먼저 와야 한다.

    `parts` 가 없으면 `message` 한 통 (지금까지의 동작).

    한 통이라도 실패하면 그 건 전체를 실패로 본다. 링크만 가고 설명이 안 가면
    받는 쪽은 뭘 받은 건지 모르고, 설명만 가고 링크가 안 가면 자료가 없다.
    서버가 다시 큐에 넣을 때 **처음부터** 다시 보내야 순서가 맞는다.
    """
    parts = item.get("parts") or [item["message"]]
    gap = float(cfg.get("part_gap_sec", 1.2))

    result = None
    for n, text in enumerate(parts, start=1):
        result = sender.send_text(item["room_name"], text)
        if not result.ok:
            if len(parts) > 1:
                result.error = f"{n}/{len(parts)}번째 통에서 실패 — {result.error}"
            return result
        if n < len(parts):
            # 연달아 쏟으면 카톡이 순서를 뒤집거나 묶어 버린다.
            time.sleep(gap)
    return result


def process_job(client: AgentClient, sender, job: dict, cfg: dict):
    """잡 종류로 갈린다 — 발송 잡만 문구를 전송한다.

    모르는 종류는 **보내지 않고** 실패로 보고한다. 서버가 나중에 새 잡 종류를
    추가했을 때 구형 에이전트가 그걸 발송으로 오해하는 쪽이 훨씬 위험하다.
    """
    kind = job.get("kind") or "deal_intro"
    if kind == VERIFY_KIND:
        return process_verify_job(client, sender, job, cfg)
    if kind not in SEND_KINDS:
        log.error("모르는 잡 종류 %r — 전송하지 않고 실패 처리합니다", kind)
        for item in job.get("items", []):
            client.report_item(item["id"], "failed",
                               error=f"unsupported job kind: {kind} (에이전트 업데이트 필요)")
        client.report_job(job["job_id"], "done_with_errors")
        return

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
        result = send_item(sender, item, cfg)
        if result.ok:
            client.report_item(item["id"], "sent")
            log.info("  [%d/%d] SENT room=%r", i, len(items), item["room_name"])
        else:
            any_fail = True
            client.report_item(item["id"], "failed", error=result.error,
                               screenshot_b64=result.screenshot_b64)
            log.warning("  [%d/%d] FAILED room=%r: %s", i, len(items), item["room_name"], result.error)
            # 실패 원인을 서버에서 볼 수 있게 창 상태를 함께 올린다.
            client.report_diagnostics(
                collect_diagnostics(sender, "send_failed",
                                    target_room=item["room_name"], error=result.error))
        # human-like inter-send delay
        if i < len(items):
            time.sleep(random.uniform(float(cfg["delay_min_sec"]), float(cfg["delay_max_sec"])))

    client.report_job(job_id, "done_with_errors" if any_fail else "done")
    log.info("job %s complete (errors=%s)", job_id, any_fail)


def process_verify_job(client: AgentClient, sender, job: dict, cfg: dict):
    """방 이름 대조 잡 (ROADMAP 2.5) — 검색만 하고 **전송은 하지 않는다**.

    방 제목이 실제와 다르면 발송이 통째로 skip 되므로, 실운영 전에 담당자 전원을
    한 번에 대조해야 한다. 여기서는 sender.send_text 를 절대 호출하지 않는다.
    """
    job_id = job["job_id"]
    items = job.get("items", [])
    log.info("processing verify job %s (%d rooms)", job_id, len(items))

    any_fail = False
    for i, item in enumerate(items, start=1):
        room = item["room_name"]
        query = (item.get("query") or "").strip() or room
        marker = str(cfg.get("room_marker", "") or "")
        try:
            # 방 이름은 생성으로 맞출 수 없다 → 이름+직함으로 **검색해 실제 제목을 찾는다**.
            found = []
            if hasattr(sender, "discover_rooms"):
                found = sender.discover_rooms(query, marker=marker)
                # 직함이 시트와 다를 수 있다(예: 시트 '제너럴파트너님' ↔ 방 '심사역님').
                # 이름만으로 한 번 더 찾아본다.
                name_only = (item.get("name") or "").strip()
                if not found and name_only and name_only != query:
                    found = sender.discover_rooms(name_only, marker=marker)
                # 동명이인이면 회사명으로 가린다(방 제목에 회사가 들어가는 경우).
                firm = (item.get("firm") or "").strip()
                if len(found) > 1 and firm:
                    key = firm.replace("(주)", "").replace("㈜", "").strip()
                    narrowed = [f for f in found if key and key[:6] in f]
                    if len(narrowed) == 1:
                        found = narrowed
            if found:
                verdict = "verified" if len(found) == 1 else "ambiguous"
            else:
                verdict = sender.verify_room(room)
        except Exception as exc:  # noqa: BLE001 - 한 건 실패로 전체를 멈추지 않는다
            log.exception("verify 실패 room=%r", room)
            verdict = "not_found"
            client.report_item(item["id"], "failed", error=f"verify error: {exc}",
                               verify_result=verdict)
            any_fail = True
        else:
            ok = verdict == "verified"
            any_fail = any_fail or not ok
            client.report_item(item["id"], "sent" if ok else "failed",
                               verify_result=verdict,
                               found_room=found[0] if len(found) == 1 else None,
                               candidates=found or None)
            log.info("  [%d/%d] %s query=%r found=%r", i, len(items), verdict, query, found)
        if i < len(items):
            time.sleep(random.uniform(float(cfg.get("verify_delay_min_sec", 1)),
                                      float(cfg.get("verify_delay_max_sec", 2))))

    client.report_job(job_id, "done_with_errors" if any_fail else "done")
    log.info("verify job %s complete (mismatch=%s)", job_id, any_fail)


def collect_diagnostics(sender, kind: str, target_room=None, error=None) -> dict:
    """현재 창 상태 + 최근 로그를 모아 서버로 보낼 형태로 만든다.

    Windows PC 는 원격 접속이 안 되므로, 에이전트가 스스로 상태를 보고해야
    서버 쪽에서 room_mismatch / focus_failed 원인을 판단할 수 있다.
    """
    payload = {"kind": kind, "platform": platform.system(),
               "sender": getattr(sender, "name", "unknown")}
    if target_room:
        payload["target_room"] = target_room
    if error:
        payload["error"] = error

    try:
        from agent.diagnose import list_titles
        payload["window_titles"] = list_titles()
    except Exception as exc:  # noqa: BLE001
        payload["window_titles"] = [f"(수집 실패: {exc})"]

    try:
        fg = getattr(sender, "_foreground_title", None)
        if callable(fg):
            payload["foreground_window"] = fg()
    except Exception:  # noqa: BLE001
        pass

    try:
        log_path = Path(__file__).resolve().parent.parent / "agent_logs" / "agent.log"
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            payload["log_tail"] = "\n".join(lines[-40:])
    except Exception:  # noqa: BLE001
        pass
    return payload


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
    # 기동 시 1회 환경 스냅샷 업로드 — 서버에서 카톡 창 상태를 확인할 수 있게.
    client.report_diagnostics(collect_diagnostics(sender, "startup"))

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
