"""메일도 보내는 시간(09~19시)과 하루 상한을 지킨다 (`services/mail_sender.py`).

카톡은 발송기에게 내주는 자리(`agent_api.poll`)에서 막지만, 메일은 서버가 SMTP 로
바로 보내 그 자리를 지나지 않는다. 여기서 못박는 것.

1. 시간 밖이면 **실패로 닫지 않고 대기로 둔다** — 까닭을 그 건에 적는다.
2. 보내는 시간이 열리면 예약 실이 **이어 보낸다**(`resume_waiting`) — 이미 나간
   사람에게 다시 가지 않는다.
3. 하루 상한은 같은 숫자를 **메일끼리** 센다.
4. 테스트 서버의 시간 관문 스위치는 메일에도 똑같이 먹는다.
5. 기다림 표시가 없는 옛 대기 건 · 닫힌 회차는 저절로 나가지 않는다.

시각은 전부 못박는다(`@pytest.mark.send_window` — 진짜 관문을 쓴다).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from .conftest import DEMO_TOKEN, auth

pytestmark = pytest.mark.send_window

#: 2099-03-12 는 목요일이다. 실제 오늘이 언제든 이 날이 '지금' 일 수 없다.
DAY = (2099, 3, 12)
NEXT_DAY = (2099, 3, 13)


def _at(hour, minute=0, day=DAY):
    return datetime(*day, hour, minute).astimezone()


@pytest.fixture()
def mail_on(monkeypatch):
    monkeypatch.setenv("DEALFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PORT", "465")
    monkeypatch.setenv("DEALFLOW_SMTP_USER", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_FROM", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PASSWORD", "secret")
    monkeypatch.delenv("DEALFLOW_TEST_SERVER_NO_SEND_WINDOW", raising=False)


@pytest.fixture()
def clock_at(monkeypatch):
    """`now["t"]` 를 바꾸면 그 순간부터 '지금' 이 바뀐다."""
    from app import clock

    now = {"t": _at(10, 0)}
    monkeypatch.setattr(clock, "now", lambda: now["t"])
    return now


@pytest.fixture()
def outbox(monkeypatch):
    """가짜 SMTP — 실제로 몇 번 누구에게 나갔는지 센다."""
    sent = []
    monkeypatch.setattr("app.services.mailer.send_mail",
                        lambda to, subject, body, settings=None: sent.append(to))
    return sent


@pytest.fixture()
def inline(monkeypatch):
    """이어 보내기 실을 그 자리에서 돌린다."""
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "_dispatch", lambda func, *args: func(*args))
    monkeypatch.setattr(mail_sender, "GAP_SEC", 0)


def _mail_job(db, n=3, user_id=1, status="queued"):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind="deal_intro", status=status, total=n)
    db.add(job)
    db.flush()
    for i in range(n):
        db.add(SendItem(job_id=job.id, channel="email", room_name=f"vc{i}@example.com",
                        subject="딜 소개", message="안녕하세요", status="pending"))
    db.commit()
    return job.id


def _items(db, job_id):
    from app.models import SendItem

    db.expire_all()
    return db.query(SendItem).filter_by(job_id=job_id).order_by(SendItem.id).all()


def _job(db, job_id):
    from app.models import SendJob

    db.expire_all()
    return db.get(SendJob, job_id)


# ── 1. 시간 밖이면 대기 ──────────────────────────────────────────────────────

def test_night_mail_waits_instead_of_going_out(db, users, mail_on, clock_at, outbox):
    from app.services import mail_sender

    clock_at["t"] = _at(22, 0)
    job_id = _mail_job(db)

    result = mail_sender._run(db, job_id, gap_sec=0)

    assert outbox == [], "밤 10시에 메일이 나갔다"
    assert result["held"] == 3
    rows = _items(db, job_id)
    assert [i.status for i in rows] == ["pending"] * 3, "실패로 닫으면 사람이 다시 만들어야 한다"
    assert {i.error for i in rows} == {mail_sender.HELD_WINDOW}
    assert _job(db, job_id).status == "queued"


def test_window_closing_mid_run_stops_there(db, users, mail_on, clock_at, monkeypatch):
    """18:59 에 시작한 회차가 19시를 넘기면 그 자리에서 멈춘다."""
    from app.services import mail_sender

    sent = []

    def send_and_tick(to, subject, body, settings=None):
        sent.append(to)
        clock_at["t"] = _at(19, 0)

    monkeypatch.setattr("app.services.mailer.send_mail", send_and_tick)
    clock_at["t"] = _at(18, 59)
    job_id = _mail_job(db)

    mail_sender._run(db, job_id, gap_sec=0)

    assert sent == ["vc0@example.com"]
    assert [i.status for i in _items(db, job_id)] == ["sent", "pending", "pending"]


# ── 2. 다음 창에서 이어 보낸다 — 두 번 나가지 않는다 ─────────────────────────

def test_waiting_mail_resumes_next_window_once(db, users, mail_on, clock_at, outbox, inline,
                                               monkeypatch):
    from app.services import mail_sender

    def send_and_tick(to, subject, body, settings=None):
        outbox.append(to)
        clock_at["t"] = _at(19, 0)

    monkeypatch.setattr("app.services.mailer.send_mail", send_and_tick)
    clock_at["t"] = _at(18, 59)
    job_id = _mail_job(db)
    mail_sender._run(db, job_id, gap_sec=0)              # 한 통 나가고 19시
    assert outbox == ["vc0@example.com"]

    # 밤에는 깨어나도 아무것도 안 띄운다.
    clock_at["t"] = _at(23, 0)
    assert mail_sender.resume_waiting(db, clock_at["t"]) == []

    # 다음 날 09시 — 남은 두 사람에게만.
    monkeypatch.setattr("app.services.mailer.send_mail",
                        lambda to, subject, body, settings=None: outbox.append(to))
    clock_at["t"] = _at(9, 0, day=NEXT_DAY)
    assert mail_sender.resume_waiting(db, clock_at["t"]) == [job_id]
    # 한 번 더 깨어나도 보낼 것이 없다.
    assert mail_sender.resume_waiting(db, clock_at["t"]) == []

    assert outbox == ["vc0@example.com", "vc1@example.com", "vc2@example.com"]
    assert len(outbox) == len(set(outbox)), "같은 사람에게 두 번 나갔다"
    rows = _items(db, job_id)
    assert [i.status for i in rows] == ["sent"] * 3
    assert all(i.error is None for i in rows)
    assert _job(db, job_id).status == "done"


def test_two_runs_of_the_same_job_send_each_mail_once(db, users, mail_on, clock_at,
                                                      monkeypatch):
    """[이어 보내기] 와 이어 보내기 실이 겹쳐도 한 건은 한 번만 나간다(`_claim`)."""
    from app.services import mail_sender

    sent = []
    job_id = _mail_job(db)

    def send(to, subject, body, settings=None):
        sent.append(to)
        if len(sent) == 1:
            # 첫 통을 보내는 사이 다른 실이 같은 회차를 돈다.
            mail_sender.send_job(job_id, gap_sec=0)

    monkeypatch.setattr("app.services.mailer.send_mail", send)
    mail_sender._run(db, job_id, gap_sec=0)

    assert sorted(sent) == ["vc0@example.com", "vc1@example.com", "vc2@example.com"]
    assert [i.status for i in _items(db, job_id)] == ["sent"] * 3


def test_agent_does_not_close_a_waiting_mail_job(client, db, users, mail_on, clock_at, outbox):
    """창이 열리는 순간 발송기가 먼저 물어도 메일 회차는 내주지 않는다 — 빈 회분
    보고로 `done` 이 되면 기다리던 메일이 영영 안 나간다."""
    from app.services import mail_sender

    clock_at["t"] = _at(22, 0)
    job_id = _mail_job(db)
    mail_sender._run(db, job_id, gap_sec=0)

    clock_at["t"] = _at(9, 0, day=NEXT_DAY)
    got = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                     headers=auth(DEMO_TOKEN))
    assert got.status_code == 204
    assert _job(db, job_id).status == "queued"


def test_only_marked_waiting_jobs_resume(db, users, mail_on, clock_at, outbox, inline):
    """까닭 없이 대기로 남은 옛 건 · [중단] 한 회차는 저절로 나가지 않는다."""
    from app.models import SendItem
    from app.services import mail_sender

    old = _mail_job(db, n=1)                         # 서버가 내려가 남은 옛 건
    stopped = _mail_job(db, n=1, status="canceled")  # 사람이 멈춘 회차
    db.query(SendItem).filter_by(job_id=stopped).update({"error": mail_sender.HELD_WINDOW})
    db.commit()

    assert mail_sender.resume_waiting(db, _at(10, 0)) == []
    assert outbox == []


# ── 3. 하루 상한은 메일끼리 ──────────────────────────────────────────────────

def test_daily_cap_counts_mail_on_its_own(db, users, mail_on, clock_at, outbox, inline):
    from app.models import SendItem, SendJob
    from app.services import mail_sender, send_guard

    users["u1"].daily_send_cap = 2
    # 오늘 카톡으로 이미 다섯 통 — 메일 한도와는 따로 센다.
    kakao = SendJob(user_id=1, kind="deal_intro", status="done", total=5)
    db.add(kakao)
    db.flush()
    for i in range(5):
        db.add(SendItem(job_id=kakao.id, room_name=f"방{i}", message="-", status="sent",
                        sent_at=_at(9, 30).isoformat(timespec="seconds")))
    db.commit()

    job_id = _mail_job(db)
    mail_sender._run(db, job_id, gap_sec=0)

    assert outbox == ["vc0@example.com", "vc1@example.com"]
    rows = _items(db, job_id)
    assert [i.status for i in rows] == ["sent", "sent", "pending"]
    assert rows[2].error == mail_sender.HELD_CAP
    assert send_guard.sent_today(db, 1, _at(10, 0).date(), mail=True) == 2
    assert send_guard.sent_today(db, 1, _at(10, 0).date()) == 5

    # 같은 날에는 깨어나도 안 띄운다 — 다음 날 이어 간다.
    assert mail_sender.resume_waiting(db, _at(15, 0)) == []
    clock_at["t"] = _at(9, 0, day=NEXT_DAY)
    assert mail_sender.resume_waiting(db, clock_at["t"]) == [job_id]
    assert outbox == ["vc0@example.com", "vc1@example.com", "vc2@example.com"]


def test_progress_screen_says_why_the_mail_waits(db, users, mail_on, clock_at, outbox):
    from app.services import mail_sender, send_guard

    clock_at["t"] = _at(22, 0)
    job_id = _mail_job(db)
    mail_sender._run(db, job_id, gap_sec=0)

    guard = send_guard.describe(db, _job(db, job_id), clock_at["t"])
    assert guard["held"] is True
    assert "보내는 시간" in guard["sentence"]


# ── 4. 테스트 서버 스위치는 메일에도 ────────────────────────────────────────

def test_test_server_switch_lets_night_mail_go(db, users, mail_on, clock_at, outbox,
                                               monkeypatch):
    from app.services import mail_sender

    monkeypatch.setenv("DEALFLOW_TEST_SERVER_NO_SEND_WINDOW", "1")
    clock_at["t"] = _at(22, 0)
    job_id = _mail_job(db, n=2)

    mail_sender._run(db, job_id, gap_sec=0)

    assert outbox == ["vc0@example.com", "vc1@example.com"]
    assert _job(db, job_id).status == "done"
