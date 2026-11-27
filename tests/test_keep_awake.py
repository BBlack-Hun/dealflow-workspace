"""보낼 일이 있는 동안 화면을 깨워 둔다 (0.11.18).

서버: 폴 응답 머리글 `X-Pending-Work` — 대기 · 진행 중 회차가 있으면 1. 보내는 시간
밖이라 안 내주는 회차, 맡긴 계정의 회차도 센다. 발송기: 그 값(또는 잡을 받음)대로
`caffeinate` / `SetThreadExecutionState` 를 켜고 끈다 — 여기선 가짜로 바꿔 끼운다.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from .conftest import DEMO_TOKEN, OTHER_TOKEN, auth

KINDS = "deal_intro,ir_delivery,verify_room"


def _job(db, user_id=1, kind="deal_intro", status="queued", channel="kakao"):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind=kind, status=status, total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, room_name="홍길동 심사역님 가나다벤처스",
                    message="안녕하세요", status="pending", channel=channel))
    db.commit()
    return job


def _flag(client, token=DEMO_TOKEN):
    res = client.get("/api/agent/poll", params={"kinds": KINDS, "cap": 60}, headers=auth(token))
    return res.status_code, res.headers.get("X-Pending-Work")


def test_no_work_says_zero(client, db, users):
    assert _flag(client) == (204, "0")


def test_handed_out_job_says_one(client, db, users):
    _job(db)
    assert _flag(client) == (200, "1")


@pytest.mark.send_window
def test_night_queue_keeps_awake_without_handing_out(client, db, users, monkeypatch):
    """저녁 9시 — 내주지는 않지만 아침 9시 전에 잠기지 않게 1."""
    from app import clock

    _job(db)
    monkeypatch.setattr(clock, "now", lambda: datetime(2099, 3, 12, 21, 0).astimezone())
    assert _flag(client) == (204, "1")


def test_delegated_account_counts_for_the_delegate(client, db, users):
    from app.models import User

    db.get(User, 2).send_via_user_id = 1
    db.commit()
    _job(db, user_id=2, status="running")
    assert _flag(client, DEMO_TOKEN)[1] == "1"
    # 맡긴 쪽 발송기는 아무것도 안 받으니 깨울 까닭도 없다.
    assert _flag(client, OTHER_TOKEN)[1] == "0"


def test_mail_only_and_finished_and_draft_do_not_count(client, db, users):
    _job(db, channel="email")
    _job(db, status="done")
    _job(db, status="draft")
    assert _flag(client) == (204, "0")


# ── 발송기 ────────────────────────────────────────────────────────────────────

class _Proc:
    def __init__(self):
        self.alive = True

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.alive = False


def test_mac_holds_one_caffeinate_and_lets_go(monkeypatch):
    from agent import keep_awake

    started = []

    def popen(cmd, **_):
        started.append(cmd)
        return _Proc()

    monkeypatch.setattr(keep_awake.subprocess, "Popen", popen)
    k = keep_awake.KeepAwake(platform="darwin")
    k.set(True)
    k.set(True)                      # 이미 붙들고 있으면 또 띄우지 않는다
    assert len(started) == 1 and started[0][:4] == ["caffeinate", "-d", "-i", "-w"]
    proc = k._proc
    k.set(False)
    assert proc.alive is False and k.on is False
    k.set(True)
    k._proc.alive = False            # 누가 죽였으면 다음 폴에 다시 띄운다
    k.set(True)
    assert len(started) == 3


def test_windows_sets_and_clears_execution_state(monkeypatch):
    import ctypes

    from agent import keep_awake

    calls = []

    class _K32:
        def SetThreadExecutionState(self, flags):
            calls.append(flags)
            return 1

    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": _K32()})(), raising=False)
    k = keep_awake.KeepAwake(platform="win32")
    k.set(True)
    k.set(False)
    assert calls == [keep_awake.ES_CONTINUOUS | keep_awake.ES_DISPLAY_REQUIRED
                     | keep_awake.ES_SYSTEM_REQUIRED, keep_awake.ES_CONTINUOUS]


def test_failure_is_quiet_and_other_platforms_do_nothing(monkeypatch):
    from agent import keep_awake

    def boom(*_a, **_k):
        raise FileNotFoundError("caffeinate")

    monkeypatch.setattr(keep_awake.subprocess, "Popen", boom)
    k = keep_awake.KeepAwake(platform="darwin")
    k.set(True)                      # 터지지 않는다
    assert k.on is False
    other = keep_awake.KeepAwake(platform="linux")
    other.set(True)
    assert other.on is False


def test_client_poll_drives_keep_awake():
    from agent.main import AgentClient

    class _Resp:
        def __init__(self, code, flag=None):
            self.status_code = code
            self.headers = {"X-Pending-Work": flag} if flag else {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"job_id": 1, "kind": "deal_intro", "items": []}

    seen = []
    client = AgentClient({"server_url": "http://x", "token": "t"})
    client.keep_awake = type("K", (), {"set": lambda self, v: seen.append(v)})()
    for resp in (_Resp(204, "1"), _Resp(200), _Resp(204, "0"), _Resp(204)):
        client.session.get = lambda *a, _r=resp, **k: _r
        client.poll()
    assert seen == [True, True, False, False]
