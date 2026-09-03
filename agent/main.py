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
from collections import namedtuple
from pathlib import Path
from typing import List

import requests
import yaml

from .version import VERSION

log = logging.getLogger("agent")

# 이 에이전트가 처리할 수 있는 잡 종류. 서버 poll 에 그대로 알린다.
# deal_intro/ir_delivery = 문구 전송, verify_room = 방 이름 대조(전송 없음).
# 서버가 만드는 발송 잡 종류. **여기 없으면 집어가지 않는다** —
# 딜 소싱 제안을 서버에만 넣고 이 줄을 안 고쳐서, 잡이 큐에 그대로 멈춰
# 있었다(에이전트는 폴링할 때 이 목록을 `?kinds=` 로 보낸다).
#
# 서버의 `app/models.py: SEND_KINDS` 와 같아야 한다.
SEND_KINDS = ("deal_intro", "ir_delivery", "sourcing_intro")
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
    # 1잡 상한 (계정 보호). **이 숫자가 사는 유일한 자리** — 서버는 폴링할 때
    # 받은 값을 지킬 뿐 자기 상한을 따로 들고 있지 않다(`job_cap()` 참고).
    "job_cap": 60,
    "part_gap_sec": 1.2,       # 한 건이 여러 통일 때 통 사이 간격
                               # (연달아 쏟으면 카톡이 순서를 뒤집는다)
    # 방 연결 확인은 메시지를 보내지 않아 검색만 반복한다. 그래도 사람 속도를 흉내낸다
    # (연속 검색도 자동화로 읽힐 수 있음). 발송 지연과 별개 값으로 둔다.
    "room_marker": "",   # 딜소개 방을 가려내는 표식(예: "우리브이씨 Asset")
    "verify_delay_min_sec": 1,
    "verify_delay_max_sec": 2,
    # 한 건을 보내기 **직전** 서버에 "아직 보내도 되는가" 를 묻는다.
    # 못 물어보면 보내지 않고 멈추는데, 서버 재배포 같은 몇 초짜리 끊김에
    # 회차가 통째로 죽으면 못 쓴다 — 그래서 몇 번 다시 묻고 나서 멈춘다.
    "cancel_check_retries": 3,
    "cancel_check_backoff_sec": 1.0,
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
        # IR 자료 폴더 자리는 여기서 넣지 않는다 — **서버가 내려준다**
        # (`apply_server_settings`). config 에 적어 두면 발송기를 새로 내려받을
        # 때 데모 값으로 되돌아간다.
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


def job_cap(cfg: dict) -> int:
    """한 번에 처리할 건수 상한 (계정 보호).

    **이 값이 사는 곳은 여기 하나뿐이다.** 서버는 자기 상한을 따로 들고 있지 않고
    폴링할 때 받은 값을 지킨다(`?cap=`). 두 곳에 숫자를 박아 두면 어긋나고,
    어긋난 만큼이 조용히 버려진다 — 서버가 97건을 내주고 에이전트가 60건에서
    자르는 바람에 37명에게 안 나간 채 회차가 완료로 끝난 적이 있다.
    """
    return int(cfg.get("job_cap") or DEFAULT_CONFIG["job_cap"])


class AgentClient:
    def __init__(self, cfg: dict):
        self.base = cfg["server_url"].rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {cfg['token']}"})
        self.version = VERSION
        self.hostname = socket.gethostname()
        # 어떤 발송기인지 서버에 알린다 — 배지에서 mock/실발송을 구분하기 위함.
        self.sender_name = "unknown"
        # 그 발송기가 자료 파일을 붙일 줄 아는가(`Sender.can_send_files`).
        # **기본은 아니오다** — `sender_name` 이 `unknown` 으로 시작하는 것과 같은
        # 이유다. 붙기 전에는 모르고, 모르는 것을 할 줄 안다고 밝히면 못 할 일을
        # 떠맡는다.
        self.sender_can_send_files = False
        self.job_cap = job_cap(cfg)

    def heartbeat(self):
        return self.session.post(f"{self.base}/api/agent/heartbeat",
                                 json={"hostname": self.hostname, "agent_version": self.version,
                                       "sender": self.sender_name},
                                 timeout=10)

    def poll(self):
        # 처리할 수 있는 잡 종류를 함께 알린다. 서버는 모르는 종류를 주지 않는다
        # (구버전 에이전트가 확인 잡을 발송으로 오해하는 사고를 구조적으로 막는다).
        #
        # 상한(`cap`)도 함께 알려 **서버가 그만큼만 내주게** 한다. 전에는 서버가
        # 97건을 통째로 내주고 우리가 앞 60건만 처리했는데, 나머지 37건이 그냥
        # 버려졌다. 서버가 60건만 주면 애초에 버릴 것이 없다.
        #
        # 자료 파일을 붙일 줄 아는지도 함께 밝힌다(`files=`). 밝히지 않으면 서버는
        # 파일이 실린 잡을 내주지 않는다 — 이 칸을 모르는 구버전 발송기가 파일을
        # 조용히 버리고 **문구만** 보내는 사고를 구조적으로 막는다
        # (`send_item` 이 파일을 먼저 보낸다).
        #
        # ★ **붙어 있는 발송기가 실제로 할 줄 알 때만 밝힌다.** 판 번호로 되는
        # 것이 아니다 — 같은 0.7.0 이라도 Windows 발송기는 파일 전송을 지원하지
        # 않는다(실기 확인 전이라 `file_send_unsupported` 로 거절한다). 무조건
        # 밝히면 그쪽은 **파일 잡을 받아 놓고 첫 파일에서 실패**하고, 사람은 왜
        # 계속 실패하는지 알 길이 없다. 아예 안 받는 편이 낫다 — 잡은 큐에 남아
        # 있다가 파일을 붙일 줄 아는 발송기가 붙는 날 그대로 나간다.
        r = self.session.get(f"{self.base}/api/agent/poll",
                             params={"kinds": ",".join(SUPPORTED_KINDS),
                                     "cap": self.job_cap,
                                     "files": 1 if self.sender_can_send_files else 0},
                             timeout=15)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def job_state(self, job_id: int):
        """이 잡을 계속 보내도 되는지 서버에 **묻는다**.

        `report_job` 은 우리가 알리는 것이고 이쪽은 묻는 것이다.
        발송 직전마다 부르므로 timeout 을 짧게 둔다 — 여기서 오래 매달리면
        건 사이 간격이 들쭉날쭉해져 사람 흉내가 깨진다.
        """
        r = self.session.get(f"{self.base}/api/agent/jobs/{job_id}/state", timeout=10)
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
    """한 건을 보낸다 — **자료 파일이 먼저, 문구가 마지막.**

    ## 차례

        files[0] files[1] …      자료 파일. 서버가 준 차례 그대로다
        parts[0] parts[1] …      문구. 없으면 `message` 한 통(지금까지의 동작)

    자료가 먼저 가야 문구의 "1번 기업 …, 2번 기업 … 전달드리겠습니다" 가 방금
    올라온 파일을 짚는 말이 된다. 문구가 먼저 가면 받는 쪽은 빈 약속을 먼저 읽고
    자료를 기다린다.

    파일명의 차례는 **투자사가 기억하는 번호의 차례**다(딜 소개에서 붙인 번호 —
    `app/services/deal_numbers.py`). 여기서 다시 정렬하지 않는다.

    ## ★ 파일이 하나라도 실패하면 문구를 보내지 않는다

    "자료 보내드렸습니다" 만 가고 자료가 없는 것이 **제일 나쁜 결과**다. 받는
    쪽은 자기가 놓친 줄 알고 찾아 헤매고, 보낸 쪽은 보냈다고 기록해 두어 아무도
    다시 보내지 않는다. 반대로 파일만 가고 문구가 안 간 것은 **눈에 띄고**
    (파일 뒤에 말이 없다) 서버가 그 건을 실패로 남겨 다시 보낼 수 있다.

    `send_file` 은 **보내기 전에** 이름을 전부 걸러 실제 경로로 조립하므로
    (`agent/sender/base.py: resolve_ir_file`), 이름이 하나라도 규칙에 어긋나면
    카톡을 건드리기도 전에 실패한다.

    ## 한 통이라도 실패하면 그 건 전체가 실패

    문구도 마찬가지다. 서버가 다시 큐에 넣을 때 **처음부터** 다시 보내야 차례가
    맞는다 — 그래서 다시 보내면 이미 나간 파일이 겹칠 수 있고, 그 사실은 실패
    문구에 적힌다(`send_file` 이 몇 개를 보낸 뒤 막혔는지 적는다).
    """
    gap = float(cfg.get("part_gap_sec", 1.2))

    # 자료 파일 — 이 칸을 모르는 서버(구버전)는 주지 않는다. 그러면 지금까지처럼
    # 문구만 나가고 자료는 사람이 PC 카톡에서 붙인다.
    files = [str(f) for f in (item.get("files") or []) if str(f).strip()]
    if files:
        result = sender.send_file(item["room_name"], files)
        if not result.ok:
            result.error = (f"자료 파일을 보내지 못해 **문구도 보내지 않았습니다** "
                            f"— {result.error}")
            return result
        # 파일이 다 올라간 뒤에 문구가 와야 한다. 연달아 쏟으면 카톡이 순서를
        # 뒤집거나 묶어 버린다(통 사이 간격과 같은 이유·같은 값).
        time.sleep(gap)

    parts = item.get("parts") or [item["message"]]

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


# 발송 직전 확인 결과. `go` 가 False 면 **이 건도 남은 건도 보내지 않는다**.
#   reason: "" 계속 | "canceled" 잡이 멈췄음 | "unreachable" 서버에 못 물어봄
#   detail: 로그에 남길 사유 (서버가 준 상태값이나 예외 문구)
#   canceled_items: 잡은 살아 있지만 이 건들만 취소됨 → 그것만 건너뛴다
Gate = namedtuple("Gate", "go reason detail canceled_items")


def check_before_send(client: AgentClient, job_id: int, cfg: dict) -> Gate:
    """한 건을 **보내기 전에** 서버에 물어본다 — 아직 보내도 되는가.

    ## 왜 필요했나

    화면의 [중단]은 서버 DB 만 바꿨다. 그런데 우리는 폴링할 때 items 를 통째로
    받아 메모리에 들고 끝까지 돌았고, 중간에 다시 묻지 않았다. 그래서 [중단]을
    눌러도 카톡은 계속 나갔다 — 서버가 결과 보고만 거부해 기록에 안 남았을 뿐,
    받는 쪽은 그대로 받았다. 사람은 [중단]을 '발송이 멈춘다' 로 읽는다.

    건 사이에 이미 delay_min_sec~delay_max_sec(기본 3~7초)을 쉬므로, 여기서
    한 번 더 묻는 비용은 무시할 만하다.

    ## 못 물어보면 보내지 않는다

    서버에 닿지 않는 상태에서 계속 보내면 지금 고치려는 문제가 그대로다
    ([중단]을 눌러도 안 멈춘다). 그렇다고 한 번 실패에 멈추면 서버 재배포나
    잠깐의 와이파이 끊김에도 회차가 통째로 죽어 쓸 수 없다.

    그래서 **몇 번 다시 묻고(기본 3회, 1초씩 쉬며) 그래도 안 되면 멈춘다.**
    3회·1초는 재배포로 서버가 잠깐 내려간 정도는 넘기고, 진짜 끊긴 경우에는
    몇 초 안에 판단이 끝나는 선이다. 헛되이 오래 매달리면 그 사이 사용자는
    [중단]을 누른 채 카톡이 계속 나가는지 아닌지 모르는 상태로 기다리게 된다.
    """
    tries = max(1, int(cfg.get("cancel_check_retries", 3)))
    backoff = float(cfg.get("cancel_check_backoff_sec", 1.0))

    last_error = None
    for attempt in range(1, tries + 1):
        try:
            state = client.job_state(job_id)
        except Exception as exc:  # noqa: BLE001 - 통신·JSON 어느 쪽이 터져도 판단은 같다
            last_error = exc
            log.warning("발송 전 확인 실패 (%d/%d) job=%s: %s", attempt, tries, job_id, exc)
            if attempt < tries:
                time.sleep(backoff)
            continue
        if state.get("canceled"):
            return Gate(False, "canceled", str(state.get("status") or "canceled"), set())
        return Gate(True, "", "", set(state.get("canceled_items") or []))

    return Gate(False, "unreachable", f"서버에 물어보지 못했습니다 ({last_error})", set())


def report_stopped(client: AgentClient, job_id: int, gate: Gate, remaining: int) -> None:
    """확인에 걸려 멈춘 잡을 서버에 알린다.

    - 취소 — 서버는 이미 canceled 다. 알려도 canceled 로 남는다
      (`app/routers/agent_api.py: job_status_update` 가 그렇게 지킨다).
    - 서버에 못 닿음 — 이 보고도 실패할 가능성이 높다. 그래도 잠깐 끊겼다
      붙은 경우에는 화면이 '멈춤' 으로 바뀌어 사람이 알아챌 수 있다.
      여기서 예외가 새면 다음 폴링까지 죽으므로 삼킨다.
    """
    log.warning("job %s 중단(%s) — 남은 %d건은 보내지 않습니다. %s",
                job_id, gate.reason, remaining, gate.detail)
    try:
        client.report_job(job_id, "canceled" if gate.reason == "canceled" else "paused")
    except Exception as exc:  # noqa: BLE001
        log.warning("중단 보고 실패 (job %s): %s", job_id, exc)


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
    # 상한을 넘는 만큼은 이번에 처리하지 않는다(계정 보호). 서버가 상한을 지켜
    # 내주면(폴링할 때 `cap` 으로 알린다) 여기서 잘릴 일이 없다 — 낡은 서버에
    # 붙었을 때를 위한 안전망으로 남긴다.
    cap = job_cap(cfg)
    left_over = max(0, len(items) - cap)
    if left_over:
        log.warning("job %s has %d items > cap %d; processing first %d only",
                    job_id, len(items), cap, cap)
        items = items[:cap]

    log.info("processing job %s (%d items)", job_id, len(items))
    any_fail = False
    attempted = False   # 첫 건 앞에는 쉬지 않는다
    for i, item in enumerate(items, start=1):
        # human-like inter-send delay. 확인을 이 **뒤에** 두는 것이 핵심이다 —
        # 쉬는 동안 사용자가 [중단]을 누를 수 있어서, 쉬기 전에 물어보면
        # 최대 delay_max_sec 만큼 낡은 답으로 보내게 된다.
        if attempted:
            time.sleep(random.uniform(float(cfg["delay_min_sec"]), float(cfg["delay_max_sec"])))

        gate = check_before_send(client, job_id, cfg)
        if not gate.go:
            report_stopped(client, job_id, gate, remaining=len(items) - i + 1)
            return
        if item["id"] in gate.canceled_items:
            # 잡은 살아 있는데 이 건만 취소된 경우. 남은 건은 그대로 보낸다.
            log.info("  [%d/%d] SKIP 취소된 건 room=%r", i, len(items), item["room_name"])
            continue

        result = send_item(sender, item, cfg)
        attempted = True
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

    if left_over:
        # 상한에 걸려 손도 안 댄 건이 남았다 → **끝났다고 하면 안 된다.**
        # 여기서 done 을 보내면 화면은 '완료' 가 되고, 안 나간 사람은 아무도
        # 모른다(97명 중 60명만 나간 회차가 그렇게 끝났다). 다시 큐로 돌려
        # 달라고 알린다 — 다음 폴링에서 남은 건만 이어 보낸다.
        log.warning("job %s: 상한(%d) 때문에 %d건이 남았습니다 — 완료로 보고하지 "
                    "않고 다음 폴링에서 이어 보냅니다", job_id, cap, left_over)
        client.report_job(job_id, "queued")
        return

    client.report_job(job_id, "done_with_errors" if any_fail else "done")
    log.info("job %s complete (errors=%s)", job_id, any_fail)


def process_verify_job(client: AgentClient, sender, job: dict, cfg: dict):
    """방 이름 대조 잡 (ROADMAP 2.5) — 검색만 하고 **전송은 하지 않는다**.

    방 제목이 실제와 다르면 발송이 통째로 skip 되므로, 실운영 전에 담당자 전원을
    한 번에 대조해야 한다. 여기서는 sender.send_text 를 절대 호출하지 않는다.

    전송이 없어도 [중단]은 들어야 한다 — 수백 명을 검색하느라 몇 분씩 돌고,
    그동안 카톡 창을 붙잡고 있어서 사용자가 다른 일을 못 한다.
    """
    job_id = job["job_id"]
    items = job.get("items", [])
    log.info("processing verify job %s (%d rooms)", job_id, len(items))

    any_fail = False
    checked = False   # 첫 건 앞에는 쉬지 않는다
    for i, item in enumerate(items, start=1):
        if checked:
            time.sleep(random.uniform(float(cfg.get("verify_delay_min_sec", 1)),
                                      float(cfg.get("verify_delay_max_sec", 2))))

        gate = check_before_send(client, job_id, cfg)
        if not gate.go:
            report_stopped(client, job_id, gate, remaining=len(items) - i + 1)
            return
        if item["id"] in gate.canceled_items:
            log.info("  [%d/%d] SKIP 취소된 건 room=%r", i, len(items), item["room_name"])
            continue
        checked = True

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


def apply_server_settings(sender, payload) -> bool:
    """서버가 박동 응답에 실어 준 설정을 발송기에 반영한다. 바뀌었으면 True.

    지금은 IR 자료 폴더 자리 하나다. 값은 사람이 웹에서 넣고, 여기로 따라온다 —
    화면에서 고치면 다음 박동에 반영되므로 발송기를 다시 켤 필요가 없다.
    """
    if not isinstance(payload, dict):
        return False
    if not getattr(sender, "can_send_files", False):
        return False          # 파일을 못 보내는 발송기는 알 필요가 없다
    value = str(payload.get("ir_root") or "")
    if getattr(sender, "ir_root_setting", None) == value:
        return False
    sender.ir_root_setting = value
    return True


def _json(response):
    """응답 본문을 조용히 읽는다. 못 읽어도 발송에는 지장이 없다."""
    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return None


def preflight(sender) -> List[str]:
    """켤 때 **미리** 짚어 주는 것들. 발송을 막지는 않는다.

    ## 왜 필요했나

    `quartz_available()` 은 진작 있었는데 **실행 코드 어디서도 부르지 않았다.**
    그래서 Quartz 가 빠진 PC 도 켤 때는 멀쩡해 보이고, 발송을 눌러 실패가 난
    뒤에야 알게 됐다. 그때는 이미 회차 당일이다. 있는 검사를 안 쓰고 있었을 뿐이라
    켜는 자리에서 한 번 물어보게 한다.

    IR 자료 폴더도 같이 알린다 — 자료를 어디에 넣어야 하는지 사람이 **눈으로**
    봐야 한다. 없으면 여기서 만든다.
    """
    notes: List[str] = []

    if getattr(sender, "name", "") == "kakao_mac":
        from agent.sender.kakao_mac import quartz_available
        if not quartz_available():
            notes.append(
                "⚠ Quartz(pyobjc)가 없어 **채팅방을 자동으로 열 수 없습니다.** "
                "보낼 채팅방 창을 카카오톡에서 미리 열어두면 발송됩니다. "
                "(자동 열기까지 쓰려면 packaging/mac/setup.sh 를 다시 돌리세요)")

    if getattr(sender, "can_send_files", False):
        # 보낼 때와 **같은 판단**을 쓴다 — 두 군데에 적으면 한쪽이 낡는다.
        from agent.sender.base import IrPathError, ir_root
        try:
            notes.append(f"IR 자료 폴더: "
                         f"{ir_root(getattr(sender, 'ir_root_setting', ''))} "
                         f"— 보낼 자료를 이 폴더에 넣으세요")
        except IrPathError as exc:
            notes.append(f"⚠ {exc}")

    return notes


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
    # 파일을 붙일 줄 아는지는 **발송기가 스스로 안다.** 폴링에서 그대로 밝힌다.
    client.sender_can_send_files = bool(getattr(sender, "can_send_files", False))

    # 설정(IR 자료 폴더 자리)을 **먼저** 받아 온다 — 사전 점검이 그 값을 본다.
    # 서버에 못 닿아도 켜지는 것 자체는 막지 않는다(다음 박동에 다시 받는다).
    try:
        apply_server_settings(sender, _json(client.heartbeat()))
        last_heartbeat = time.time()
    except Exception as exc:  # noqa: BLE001
        log.warning("서버 설정을 받지 못했습니다(계속 진행): %s", exc)
        last_heartbeat = 0.0

    # ★ 켜는 자리에서 미리 짚어 준다 (Quartz 유무 · IR 자료 폴더 자리).
    notes = preflight(sender)
    for note in notes:
        log.warning(note) if note.startswith("⚠") else log.info(note)

    # 기동 시 1회 환경 스냅샷 업로드 — 서버에서 카톡 창 상태를 확인할 수 있게.
    snapshot = collect_diagnostics(sender, "startup")
    snapshot["preflight"] = notes
    client.report_diagnostics(snapshot)

    while True:
        try:
            now = time.time()
            if now - last_heartbeat >= float(cfg["heartbeat_interval_sec"]):
                if apply_server_settings(sender, _json(client.heartbeat())):
                    log.info("IR 자료 폴더가 바뀌었습니다: %r",
                             getattr(sender, "ir_root_setting", ""))
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
