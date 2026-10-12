"""발송 안전장치 — **내주는 자리에서** 막는다 (`services/send_guard.py`).

## 왜 이 검사가 있나

자동화가 사람 확인 없이 돌기 시작하면, 사람이 눈으로 막아 주던 것을 서버가
막아야 한다. 지난 60일 동안 풀려서 `queued` 로 서 있던 회차가 **발송기가
켜지는 순간** 나갔다 — 20시대에 265통, 0~3시에 7통. 여기서 못박는 것은 넷이다.

1. **09~19시 밖에는 문구 잡을 내주지 않는다.** 잡은 큐에 그대로 서 있다가
   시간이 되면 나간다. 방 확인·시험 발송은 막지 않는다.
2. **계정마다 하루 상한.** 그날 나간 수를 서버가 세어 남은 만큼만 내주고, 다
   쓰면 더 내주지 않는다. 남은 사람은 버려지지 않고 큐에 선다.
3. **예약으로 풀렸는데 발송기가 못 집어간 채 시각을 넘긴 회차는 저절로 안
   나간다** — "예약 시각을 놓쳤습니다" 로 서고, 사람이 누르면 그때 나간다.
4. **자동 회차가 실패하거나 시각을 놓치면** 오늘 할 일(주인·관리자)에 서고
   관리자에게 메일이 한 통 간다.

## 시계에 기대지 않는다

시각은 전부 못박는다(`clock.now`). 관문 자체를 보는 검사만
`@pytest.mark.send_window` 를 단다 — 나머지 검사에서는 관문이 늘 열려 있다
(`conftest._send_window_open`).

## 진짜로는 한 통도 안 나간다

발송기는 HTTP 로만 흉내 낸다. 메일도 가짜로 바꿔 끼운다.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

#: 2099-03-12 는 목요일이다. 실제 오늘이 언제든 이 날이 '지금' 일 수 없다.
DAY = (2099, 3, 12)
AT_ISO = "2099-03-12T14:00:00+09:00"


def _at(hour, minute=0, day=DAY):
    return datetime(*day, hour, minute).astimezone()


ON_TIME = _at(14, 0)
#: 정한 시각으로부터 90분 — `EXPIRE_MINUTES`(60) 를 넘겼다.
LONG_AFTER = _at(15, 30)

KINDS = "deal_intro,ir_delivery,sourcing_intro,verify_room,test_send,startup_ir,startup_msg"


def _freeze(monkeypatch, when):
    from app import clock

    monkeypatch.setattr(clock, "now", lambda: when)


def _job(db, user_id=1, kind="deal_intro", n=3, status="queued", **over):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind=kind, status=status, total=n, **over)
    db.add(job)
    db.flush()
    for i in range(n):
        db.add(SendItem(job_id=job.id, room_name=f"홍길동{i} 심사역님 가나다벤처스",
                        message="안녕하세요", status="pending"))
    db.commit()
    return job


def _sent_items(db, user_id, count, when, kind="deal_intro", channel="kakao"):
    """그날 이미 나간 문구 — 다른 회차에서."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind=kind, status="done", total=count)
    db.add(job)
    db.flush()
    for i in range(count):
        db.add(SendItem(job_id=job.id, room_name=f"이미{i}", message="-",
                        status="sent", channel=channel,
                        sent_at=when.isoformat(timespec="seconds")))
    db.commit()
    return job


def _poll(client, token=DEMO_TOKEN, kinds=KINDS, cap=60):
    return client.get("/api/agent/poll", params={"kinds": kinds, "cap": cap},
                      headers=auth(token))


def _fresh(db, job_id):
    from app.models import SendJob

    db.expire_all()
    return db.get(SendJob, job_id)


def _report_all(client, data, status="sent", token=DEMO_TOKEN):
    """받은 건을 전부 보고하고 회분을 끝냈다고 알린다 — 발송기가 하는 그대로."""
    for item in data["items"]:
        client.post(f"/api/agent/items/{item['id']}/result",
                    json={"status": status, "error": None if status == "sent" else "방 없음"},
                    headers=auth(token))
    return client.post(f"/api/agent/jobs/{data['job_id']}/status",
                       json={"status": "done"}, headers=auth(token))


# ── 1. 보내는 시간 ────────────────────────────────────────────────────────────

@pytest.mark.send_window
def test_window_edges():
    """09:00 은 열리고 19:00 은 닫힌다 — 예약을 고를 수 있는 폭과 **같은 값**."""
    from app.services import scheduled_send, send_guard

    assert (send_guard.EARLIEST_HOUR, send_guard.LATEST_HOUR) == (
        scheduled_send.EARLIEST_HOUR, scheduled_send.LATEST_HOUR) == (9, 19)
    assert not send_guard.window_open(_at(8, 59))
    assert send_guard.window_open(_at(9, 0))
    assert send_guard.window_open(_at(18, 59))
    assert not send_guard.window_open(_at(19, 0))
    assert not send_guard.window_open(_at(2, 0))


@pytest.mark.send_window
@pytest.mark.parametrize("kind", ["deal_intro", "ir_delivery", "sourcing_intro",
                                  "startup_ir", "startup_msg"])
def test_no_message_goes_out_at_night(client, db, monkeypatch, kind):
    """저녁 9시에 발송기가 켜져도 **문구 잡은 안 나간다.** 큐에 그대로 선다."""
    job = _job(db, kind=kind)
    _freeze(monkeypatch, _at(21, 0))

    assert _poll(client).status_code == 204
    job = _fresh(db, job.id)
    assert job.status == "queued"
    assert job.started_at is None
    assert {i.status for i in job.items} == {"pending"}


@pytest.mark.send_window
def test_the_night_job_goes_out_next_morning(client, db, monkeypatch):
    """막힌 것이 아니라 **서 있는 것**이다 — 다음 날 09시에 그대로 나간다."""
    job = _job(db)
    _freeze(monkeypatch, _at(21, 0))
    assert _poll(client).status_code == 204

    _freeze(monkeypatch, _at(9, 0, day=(2099, 3, 13)))
    got = _poll(client)
    assert got.status_code == 200
    assert got.json()["job_id"] == job.id
    assert len(got.json()["items"]) == 3


@pytest.mark.send_window
def test_room_checks_and_test_sends_are_not_held(client, db, monkeypatch):
    """방 확인은 아무것도 안 보내고, 시험 발송은 우리 시험방으로만 간다 — 막지 않는다."""
    verify = _job(db, kind="verify_room")
    _freeze(monkeypatch, _at(23, 0))
    got = _poll(client)
    assert got.status_code == 200 and got.json()["job_id"] == verify.id

    test = _job(db, kind="test_send", n=1)
    got = _poll(client)
    assert got.status_code == 200 and got.json()["job_id"] == test.id


@pytest.mark.send_window
def test_night_hold_leaves_room_checks_queued_behind_it(client, db, monkeypatch):
    """문구 잡이 먼저 서 있어도 방 확인은 그 뒤에서 나간다 — 막힌 잡이 줄을 막지 않는다."""
    _job(db, kind="deal_intro")
    verify = _job(db, kind="verify_room")
    _freeze(monkeypatch, _at(20, 0))
    got = _poll(client)
    assert got.status_code == 200 and got.json()["job_id"] == verify.id


# ── 2. 계정마다 하루 상한 ─────────────────────────────────────────────────────

def test_only_what_is_left_today_is_handed_out(client, db, users, monkeypatch):
    """상한 5, 오늘 이미 3통 → 10명짜리 잡에서 **2명만** 내준다."""
    now = _at(10, 0)
    _freeze(monkeypatch, now)
    users["u1"].daily_send_cap = 5
    db.commit()
    _sent_items(db, 1, 3, _at(9, 30))
    job = _job(db, n=10)

    got = _poll(client)
    assert got.status_code == 200
    assert got.json()["job_id"] == job.id
    assert len(got.json()["items"]) == 2


def test_cap_reached_holds_the_rest_until_tomorrow(client, db, users, monkeypatch):
    """다 쓰면 **더 내주지 않는다.** 남은 사람은 버려지지 않고 큐에 서서 다음 날 이어 나간다."""
    _freeze(monkeypatch, _at(10, 0))
    users["u1"].daily_send_cap = 2
    db.commit()
    job = _job(db, n=5)

    first = _poll(client).json()
    assert len(first["items"]) == 2
    done = _report_all(client, first)
    # 대기 건이 남았고 이번 회분이 일을 했다 → 다시 큐로(`_settle`).
    assert done.json()["status"] == "queued"
    assert done.json()["pending"] == 3

    assert _poll(client).status_code == 204
    assert _fresh(db, job.id).status == "queued"

    _freeze(monkeypatch, _at(10, 0, day=(2099, 3, 13)))
    second = _poll(client).json()
    assert second["job_id"] == job.id
    assert len(second["items"]) == 2
    # 같은 사람에게 두 번 가지 않는다 — 앞 회분과 겹치는 건이 없다.
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


def test_cap_counts_what_actually_went_by_kakao_today(db, users):
    """세는 것은 **오늘 카톡으로 나간 문구**뿐 — 어제 것 · 메일 · 방 확인 · 실패는 안 센다."""
    from app.services import send_guard

    today = _at(10, 0)
    _sent_items(db, 1, 4, today)
    _sent_items(db, 1, 7, _at(18, 0, day=(2099, 3, 11)))           # 어제
    _sent_items(db, 1, 5, today, channel="email")                   # 메일은 서버가 보낸다
    _sent_items(db, 1, 6, today, kind="verify_room")                # 아무것도 안 보냈다
    _sent_items(db, 1, 2, today, kind="startup_msg")                # 스타트업 안내도 센다
    _sent_items(db, 2, 9, today)                                    # 남의 계정

    assert send_guard.sent_today(db, 1, today.date()) == 6
    assert send_guard.remaining_today(db, users["u1"], today.date()) == 200 - 6


def test_default_cap_and_clamp(db, users):
    from app.services import send_guard

    assert users["u1"].daily_send_cap == send_guard.DEFAULT_DAILY_CAP == 200
    assert send_guard.clamp_daily_cap("0") == 1
    assert send_guard.clamp_daily_cap(5000) == 1000
    assert send_guard.clamp_daily_cap("abc") == 200


def test_room_checks_go_out_even_when_the_cap_is_used_up(client, db, users, monkeypatch):
    _freeze(monkeypatch, _at(10, 0))
    users["u1"].daily_send_cap = 1
    db.commit()
    _sent_items(db, 1, 1, _at(9, 10))
    _job(db, n=2)
    verify = _job(db, kind="verify_room")

    got = _poll(client)
    assert got.status_code == 200 and got.json()["job_id"] == verify.id


def test_cap_is_per_account(client, db, users, monkeypatch):
    """한 계정이 다 썼다고 남의 계정이 막히지 않는다."""
    _freeze(monkeypatch, _at(10, 0))
    users["u1"].daily_send_cap = 1
    db.commit()
    _sent_items(db, 1, 1, _at(9, 10))
    _job(db, user_id=1)
    theirs = _job(db, user_id=2)

    assert _poll(client).status_code == 204
    got = _poll(client, token=OTHER_TOKEN)
    assert got.status_code == 200 and got.json()["job_id"] == theirs.id


def test_progress_screen_shows_what_is_left(client, db, users, monkeypatch):
    """진행 화면이 읽는 값 — 오늘 남은 한도와, 서 있는 까닭."""
    _freeze(monkeypatch, _at(10, 0))
    users["u1"].daily_send_cap = 3
    db.commit()
    _sent_items(db, 1, 3, _at(9, 10))
    job = _job(db, n=2)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    guard = client.get(f"/api/jobs/{job.id}").json()["guard"]
    assert guard["gated"] is True
    assert (guard["cap"], guard["sent_today"], guard["remaining"]) == (3, 3, 0)
    assert guard["held"] is True
    assert "오늘 발송 한도(3건)를 다 썼습니다" in guard["sentence"]

    page = client.get(f"/jobs/{job.id}").text
    assert 'id="guard-note"' in page


@pytest.mark.send_window
def test_progress_screen_says_it_waits_for_the_morning(client, db, monkeypatch):
    _freeze(monkeypatch, _at(21, 0))
    job = _job(db, n=2)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    guard = client.get(f"/api/jobs/{job.id}").json()["guard"]
    assert guard["held"] is True
    assert "보내는 시간(09:00~19:00)이 아닙니다" in guard["sentence"]
    assert "오늘 남은 발송 한도 200/200건" in guard["sentence"]


def _admin(db):
    from app.models import User
    from app.services import auth as auth_svc

    admin = User(id=9, name="관리자", phone="01000000009", role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.commit()
    return admin


def test_admin_sets_caps_on_the_team_page(client, db, users):
    """팀 현황의 `발송 안전장치` 판 — 계정마다 상한을 고친다. 폭은 서버가 자른다."""
    _admin(db)
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})

    page = client.get("/team").text
    assert 'data-testid="send-guard-panel"' in page
    assert 'name="cap_1"' in page and 'name="cap_2"' in page

    res = client.post("/team/send-caps", data={"cap_1": "150", "cap_2": "99999"},
                      follow_redirects=False)
    assert res.status_code == 303
    db.expire_all()
    from app.models import User
    assert db.get(User, 1).daily_send_cap == 150
    assert db.get(User, 2).daily_send_cap == 1000


def test_members_cannot_set_caps(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    res = client.post("/team/send-caps", data={"cap_1": "999"}, follow_redirects=False)
    assert res.status_code in (303, 403)
    db.expire_all()
    from app.models import User
    assert db.get(User, 1).daily_send_cap == 200


# ── 3. 예약 시각을 놓친 회차 ──────────────────────────────────────────────────

def _booked(db, **over):
    """예약 회차 — `draft` 로 서서 시각을 기다린다(`scheduled_send`)."""
    return _job(db, status="draft", scheduled_at=AT_ISO, **over)


def _release(db, job, now=ON_TIME):
    from app.services import scheduled_send

    assert scheduled_send.release(db, job, now) is True
    return _fresh(db, job.id)


def test_a_released_job_nobody_picked_up_does_not_go_out_late(client, db, monkeypatch):
    """14:00 에 풀렸는데 PC 가 꺼져 있었다. 15:30 에 켜져도 **나가지 않는다.**"""
    from app.services import scheduled_send

    job = _release(db, _booked(db))
    assert job.status == "queued"

    _freeze(monkeypatch, LONG_AFTER)
    assert _poll(client).status_code == 204

    job = _fresh(db, job.id)
    assert job.status == "draft"
    assert job.released_at is None
    assert {i.status for i in job.items} == {"pending"}
    assert scheduled_send.state(job, LONG_AFTER) == scheduled_send.STATE_EXPIRED
    said = scheduled_send.sentence(job, LONG_AFTER)
    assert "예약 시각을 놓쳤습니다" in said and "다시 예약하거나" in said


def test_the_schedule_thread_also_catches_it(db, users):
    """발송기가 아예 안 켜져도 예약 실이 되돌린다 — 화면·오늘 할 일이 그 상태를 말한다."""
    from app.services import scheduled_send

    job = _release(db, _booked(db))
    # 아직 포기할 때가 아니다.
    assert scheduled_send.expire_missed(db, _at(14, 59)) == []
    assert scheduled_send.expire_missed(db, _at(15, 0)) == [job.id]
    assert _fresh(db, job.id).status == "draft"
    # 두 번 되돌리지 않는다.
    assert scheduled_send.expire_missed(db, LONG_AFTER) == []


def test_missed_booking_stands_in_today_for_the_owner(db, users, monkeypatch):
    from app.services import scheduled_send, today

    job = _release(db, _booked(db))
    _freeze(monkeypatch, LONG_AFTER)   # 오늘 할 일은 '지금' 으로 예약을 잰다
    scheduled_send.expire_missed(db, LONG_AFTER)

    standing = scheduled_send.standing_for(db, users["u1"], LONG_AFTER)
    assert [s["job_id"] for s in standing] == [job.id]
    assert standing[0]["state"] == scheduled_send.STATE_EXPIRED
    assert standing[0]["level"] == "urgent"

    items = today.build(db, users["u1"], LONG_AFTER.date())["items"]
    assert any(i["title"] == "예약 시각을 놓쳤습니다"
               and i["href"] == f"/jobs/{job.id}" for i in items)


def test_a_person_can_still_send_it(client, db, monkeypatch):
    """놓친 회차도 **사람이 누르면** 그때 나간다 — 다시 놓친 것으로 되돌리지 않는다."""
    job = _release(db, _booked(db))
    _freeze(monkeypatch, LONG_AFTER)
    assert _poll(client).status_code == 204

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.post(f"/api/jobs/{job.id}/start").status_code == 200

    _freeze(monkeypatch, _at(17, 0))
    got = _poll(client)
    assert got.status_code == 200 and got.json()["job_id"] == job.id


def test_it_can_be_booked_again(client, db, monkeypatch):
    """놓친 회차는 **다시 예약할 수 있다** — 지나 버린 예약과 똑같은 상태다."""
    from app.services import scheduled_send

    job = _release(db, _booked(db))
    scheduled_send.expire_missed(db, LONG_AFTER)
    job = _fresh(db, job.id)
    assert scheduled_send.can_schedule(job)
    scheduled_send.set_at(db, job, "2099-03-13T10:00", now=LONG_AFTER)
    assert scheduled_send.state(_fresh(db, job.id), LONG_AFTER) == scheduled_send.STATE_WAITING


def test_a_job_the_agent_already_started_is_not_missed(client, db, monkeypatch):
    """발송기가 시각 안에 물어 간 회차는 **이어 나간다** — 상한에 걸려 남은 것이다."""
    from app.services import scheduled_send

    job = _release(db, _booked(db, n=4))
    _freeze(monkeypatch, _at(14, 1))
    first = _poll(client, cap=2).json()
    assert len(first["items"]) == 2
    _report_all(client, first)
    assert _fresh(db, job.id).status == "queued"

    assert scheduled_send.expire_missed(db, LONG_AFTER) == []
    _freeze(monkeypatch, LONG_AFTER)
    got = _poll(client, cap=2)
    assert got.status_code == 200 and got.json()["job_id"] == job.id


def test_pressing_start_early_is_not_a_schedule_release(db, users):
    """예약 시각 전에 사람이 [발송 시작] 을 눌렀다 — 그 회차는 예약으로 풀린 것이 아니다."""
    from app.models import SendJob
    from app.services import scheduled_send

    job = _booked(db)
    job.status = "queued"
    job.released_at = _at(11, 0).isoformat(timespec="seconds")
    db.commit()
    assert scheduled_send.released_on_schedule(job) is False
    assert scheduled_send.expire_missed(db, LONG_AFTER) == []
    assert db.get(SendJob, job.id).status == "queued"


# ── 4. 자동 회차 알림 ────────────────────────────────────────────────────────

@pytest.fixture()
def mail_box(monkeypatch):
    """메일 대역 — 설정은 켜진 것으로 보이게, 보낸 것은 적어 두기만."""
    from app.services import mailer, send_guard

    for key, value in {"DEALFLOW_SMTP_HOST": "smtp.example.com",
                       "DEALFLOW_SMTP_FROM": "team@example.com"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(send_guard.ALERT_EMAIL_ENV, raising=False)
    box = []
    monkeypatch.setattr(mailer, "send_mail",
                        lambda to, subject, body, settings=None: box.append((to, subject, body)))
    # 실을 띄우지 않고 그 자리에서 보낸다.
    monkeypatch.setattr(send_guard, "_dispatch", lambda func, *args: func(*args))
    return box


def _mark_auto(db, job, kind="meeting_review"):
    from app.models import AutoSendRun

    db.add(AutoSendRun(kind=kind, ref_id=job.id, user_id=job.user_id,
                       day="2099-03-12", status="ready", job_id=job.id))
    db.commit()


def test_an_auto_job_that_ends_with_failures_mails_the_admins(client, db, mail_box, monkeypatch):
    _freeze(monkeypatch, _at(10, 0))
    job = _job(db, n=2)
    _mark_auto(db, job)

    data = _poll(client).json()
    _report_all(client, data, status="failed")
    assert _fresh(db, job.id).status == "done_with_errors"

    assert len(mail_box) == 1
    to, subject, body = mail_box[0]
    assert to == "team@example.com"
    assert f"#{job.id}" in subject and "실패 2건" in subject
    assert f"/jobs/{job.id}" in body
    assert _fresh(db, job.id).alerted_at

    # 같은 회차로 두 번 보내지 않는다.
    client.post(f"/api/agent/jobs/{job.id}/status", json={"status": "done"},
                headers=auth(DEMO_TOKEN))
    assert len(mail_box) == 1


def test_a_hand_made_job_does_not_mail(client, db, mail_box, monkeypatch):
    """사람이 세운 회차는 그 사람이 진행 화면을 보고 있다 — 메일을 보내지 않는다."""
    _freeze(monkeypatch, _at(10, 0))
    job = _job(db, n=1)
    _report_all(client, _poll(client).json(), status="failed")
    assert _fresh(db, job.id).status == "done_with_errors"
    assert mail_box == []


def test_a_missed_auto_job_mails_and_shows_to_admins(db, users, mail_box, monkeypatch):
    from app.services import scheduled_send, send_guard, today

    monkeypatch.setenv(send_guard.ALERT_EMAIL_ENV, "a@example.com, b@example.com")
    job = _release(db, _booked(db))
    _freeze(monkeypatch, LONG_AFTER)
    _mark_auto(db, job, kind="startup_ir_monthly")
    assert scheduled_send.expire_missed(db, LONG_AFTER) == [job.id]

    assert [m[0] for m in mail_box] == ["a@example.com", "b@example.com"]
    assert "예약 시각을 놓쳤습니다" in mail_box[0][1]

    admin = _admin(db)
    items = today.build(db, admin, LONG_AFTER.date())["items"]
    mine = [i for i in items if i["href"] == f"/jobs/{job.id}"]
    assert len(mine) == 1 and mine[0]["title"] == "자동 회차가 예약 시각을 놓쳤습니다"
    assert mine[0]["level"] == "urgent"
    # 주인에게는 이미 예약 줄(`예약 시각을 놓쳤습니다`)이 선다 — 같은 일을
    # 알림 줄로 한 번 더 세우지 않는다.
    owner_items = today.build(db, users["u1"], LONG_AFTER.date())["items"]
    titles = [i["title"] for i in owner_items if i["href"] == f"/jobs/{job.id}"]
    assert "예약 시각을 놓쳤습니다" in titles
    assert "자동 회차가 예약 시각을 놓쳤습니다" not in titles
    # 다른 팀원에게는 안 보인다.
    other = today.build(db, users["u2"], LONG_AFTER.date())["items"]
    assert not [i for i in other if i["href"] == f"/jobs/{job.id}"]


def test_failed_auto_job_stands_in_today_for_owner_and_admins(db, users):
    from app.services import send_guard, today

    job = _job(db, n=2, status="done_with_errors",
               finished_at=_at(16, 0).isoformat(timespec="seconds"))
    for item in job.items:
        item.status = "failed"
    db.commit()
    _mark_auto(db, job)
    admin = _admin(db)

    for who in (users["u1"], admin):
        rows = send_guard.alerts_for(db, who, _at(17, 0).date(), _at(17, 0))
        assert [r["job_id"] for r in rows] == [job.id]
        assert rows[0]["reason"] == send_guard.REASON_FAILED
        items = today.build(db, who, _at(17, 0).date())["items"]
        assert any(i["title"] == "자동 회차에 실패가 있습니다" for i in items)
    assert send_guard.alerts_for(db, users["u2"], _at(17, 0).date(), _at(17, 0)) == []
    # 사흘이 지나면 내려간다.
    later = _at(10, 0, day=(2099, 3, 16))
    assert send_guard.alerts_for(db, admin, later.date(), later) == []


def test_requeue_reopens_the_alert(client, db, mail_box, monkeypatch):
    """[실패 재시도] 로 다시 살린 뒤의 결과는 새로 알릴 일이다."""
    _freeze(monkeypatch, _at(10, 0))
    job = _job(db, n=1)
    _mark_auto(db, job)
    _report_all(client, _poll(client).json(), status="failed")
    assert len(mail_box) == 1

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.post(f"/api/jobs/{job.id}/retry").status_code == 200
    assert _fresh(db, job.id).alerted_at is None
    _report_all(client, _poll(client).json(), status="failed")
    assert len(mail_box) == 2


def test_no_mail_settings_means_no_mail_and_no_crash(client, db, monkeypatch):
    """메일 설정이 없으면 조용히 건너뛴다 — 알림이 발송 보고를 막으면 안 된다."""
    from app.services import mailer, send_guard

    sent = []
    monkeypatch.setattr(mailer, "send_mail", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(send_guard, "_dispatch", lambda func, *args: func(*args))
    _freeze(monkeypatch, _at(10, 0))
    job = _job(db, n=1)
    _mark_auto(db, job)
    res = _report_all(client, _poll(client).json(), status="failed")
    assert res.status_code == 200
    assert sent == []
    assert _fresh(db, job.id).alerted_at  # 오늘 할 일은 상태를 읽으므로 그대로 선다
