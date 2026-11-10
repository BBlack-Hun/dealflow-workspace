"""#196 딜 소싱 참여 제안 — **3주차 화요일 10:00, `제안 대기중` 분께 참여 안내(처음) 한 번.**

손으로 보내는 참여 안내와 같은 글 · 같은 잡 모양이라(그쪽 시험이 따로 있다) 여기서는
자동화만 본다.

1. 3주차(15~21일) 화요일 10:00 에 보내는 계정 것으로 예약 — `sourcing_intro` + 빈 문구.
2. `제안 대기중` + 방 있는 분만. `물어보는 중` 은 까닭을 남기고 뺀다(이미 제안함).
3. 한 분께 한 번 — 나가면 `물어보는 중`, 칸을 다시 돌려도 자동으로는 다시 안 간다.
   손으로 보낸 참여 안내가 있어도 뺀다.
4. 보내는 계정으로 로그인하면 전날 · 당일 · 끝난 뒤 알림 창(단계마다 한 번).
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

GROUP = "시리즈 A 이상 딜 소싱 참여 심사역"
OFFER = "딜 소싱 참여 제안 대기중"
ASKING = "참여 의사를 물어보는 중"
TEST_ROOM = "자동화 시험방"
# 10월 화요일: 6 · 13 · 20(3주차) · 27 / 11월: 17 / 12월: 15
TUE3 = datetime(2026, 10, 20, 9, 0)


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def people(db, users):
    from app.models import AutoSendSetting, SourcingContact

    users["u2"].role = "admin"          # 보내는 계정(스타트업 월간 계정 = 기본)
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))

    def person(name, participation=OFFER, room=None):
        row = SourcingContact(bucket=GROUP, name=name, firm="가나다벤처스", title="심사역",
                              kakao_room_name=room, participation=participation)
        db.add(row)
        db.flush()
        return row

    rows = {"a": person("홍길동", room="홍길동 방"),
            "noroom": person("이빈방"),
            "asking": person("박묻는", ASKING, room="박묻는 방"),
            "joined": person("최참여", "참여", room="최참여 방")}
    db.commit()
    return rows


def _turn_on(db, test=False):
    from app.services import automation

    automation.save(db, automation.SOURCING_INVITE, enabled=True, user_id=None,
                    test_mode=test, test_room=TEST_ROOM)


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.SOURCING_INVITE, _aware(now))


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


def test_third_tuesday_ten_to_offer_pending_only(db, users, people):
    from app.services import scheduled_send, sourcing_msg

    _turn_on(db)
    for day in (13, 21, 27):
        assert _run(db, datetime(2026, 10, day, 9, 0))["status"] == "not_today", day
    result = _run(db, TUE3)
    assert result["status"] == "ready"
    [item] = _items(db)
    assert item.sourcing_contact_id == people["a"].id and item.room_name == "홍길동 방"
    job = item.job
    # 손으로 보낸 참여 안내와 같은 모양 — 그래야 나간 뒤 `물어보는 중` 으로 바뀐다.
    assert (job.kind, job.topic, job.user_id) == ("sourcing_intro", None, users["u2"].id)
    assert scheduled_send.label(scheduled_send.scheduled_at(job)) == "10/20(화) 10:00"
    assert sourcing_msg.body_for(db, users["u2"], GROUP) in item.message
    assert any("방 이름 없음" in s for s in result["skipped"])
    assert any(s.startswith("박묻는(") and "이미 제안함" in s for s in result["skipped"])
    assert not any(s.startswith("최참여(") for s in result["skipped"])


def test_once_per_person_even_if_reset(db, users, people):
    from app.models import SourcingContact
    from app.services import sourcing_sync

    _turn_on(db)
    _run(db, TUE3)
    [item] = _items(db)
    item.status = "sent"
    sourcing_sync.mark_invited(db, item)
    db.commit()
    assert db.get(SourcingContact, people["a"].id).participation == ASKING
    # 다음 달 — 이미 제안함.
    result = _run(db, datetime(2026, 11, 17, 9, 0))
    assert len(_items(db)) == 1
    assert any(s.startswith("홍길동(") and "이미 제안함" in s for s in result["skipped"])
    # 누가 칸을 다시 `제안 대기중` 으로 돌려도 자동으로는 다시 안 간다.
    db.get(SourcingContact, people["a"].id).participation = OFFER
    db.commit()
    _run(db, datetime(2026, 12, 15, 9, 0))
    assert len(_items(db)) == 1


def test_a_manual_invite_already_sent_is_left_out(db, users, people):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=users["u1"].id, kind="sourcing_intro", status="done", total=1)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, sourcing_contact_id=people["a"].id, room_name="홍길동 방",
                    message="참여 안내", status="sent", sent_at="2026-09-30T10:00:00+09:00"))
    db.commit()
    _turn_on(db)
    result = _run(db, TUE3)
    assert result["status"] == "empty"
    assert any(s.startswith("홍길동(") and "중복 방지" in s for s in result["skipped"])


def test_test_mode_goes_to_the_test_room(db, users, people):
    _turn_on(db, test=True)
    _run(db, TUE3)
    [item] = _items(db)
    assert item.room_name == TEST_ROOM and item.sourcing_contact_id is None
    assert item.job.kind == "test_send"          # `물어보는 중` 으로 안 바뀐다


def test_alert_for_the_sender_eve_day_and_after(db, users, people):
    from app.services import automation_runner as runner

    def alert(now, who="u2", seen=None):
        return runner.alert_for(db, users[who], seen, _aware(now))

    assert alert(datetime(2026, 10, 19, 12, 0)) is None     # 꺼져 있으면 없다
    _turn_on(db)
    eve = alert(datetime(2026, 10, 19, 12, 0))
    assert "내일 10:00 딜 소싱 참여 제안" in eve["title"]
    assert alert(datetime(2026, 10, 19, 12, 0), who="u1") is None   # 보내는 계정만
    assert alert(datetime(2026, 10, 19, 12, 0), seen=f"x|{eve['key']}") is None
    assert "오늘 10:00" in alert(datetime(2026, 10, 20, 7, 0))["title"]
    _run(db, TUE3)
    ready = alert(datetime(2026, 10, 20, 9, 30))
    assert "1건 예정" in ready["title"] and ready["href"].startswith("/jobs/")
    [item] = _items(db)
    item.status, item.job.status = "failed", "done_with_errors"
    db.commit()
    done = alert(datetime(2026, 10, 20, 11, 0))
    assert "보냄 0건 · 실패 1건" in done["title"] and done["level"] == "urgent"
    assert len({eve["key"], ready["key"], done["key"]}) == 3


def test_alert_shows_on_pages_for_the_sender_only(client, db, users, people):
    """밑틀이 창을 그린다 — 보내는 계정 화면에만, [확인] 한 단계는 다시 안 그린다."""
    from datetime import timedelta

    from app import clock
    from app.services import automation, automation_runner as runner
    from app.services.automations.sourcing_invite import week_of_month

    from .conftest import DEMO_PASSWORD

    tomorrow = clock.now().date() + timedelta(days=1)       # 내일이 보내는 날이 되게
    runner.save_params(db, automation.SOURCING_INVITE,
                       {"weeks": str(week_of_month(tomorrow)),
                        "weekday": runner.WEEKDAYS[tomorrow.weekday()], "time": "10:00"})
    _turn_on(db)

    def page(phone):
        client.cookies.clear()
        client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
        return client.get("/todo").text

    html = page("01000000002")
    assert 'data-testid="auto-alert"' in html and "내일 10:00 딜 소싱 참여 제안" in html
    assert '<form method="dialog"' in html
    assert 'data-testid="auto-alert"' not in page("01000000001")
    key = runner.alert_for(db, users["u2"])["key"]
    client.cookies.clear()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    client.cookies.set(runner.ALERT_COOKIE, key)
    assert 'data-testid="auto-alert"' not in client.get("/todo").text


def test_uses_the_sender_kakao_title_when_confirmed(db, users, people):
    """보내는 계정 카톡에서 확인된 딜 소싱 방 제목이 있으면 그 제목으로(`sender_rooms`) —
    명단의 방 이름은 그 방을 찾은 팀원 카톡의 제목이라 다를 수 있다."""
    from app.models import SenderRoom, SourcingContact

    db.add(SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=people["a"].id,
                      room_name="보내는 계정 카톡의 홍길동 방", verified=1))
    db.commit()
    _turn_on(db)
    assert _run(db, TUE3)["status"] == "ready"
    [item] = _items(db)
    assert item.room_name == "보내는 계정 카톡의 홍길동 방"
    assert db.get(SourcingContact, people["a"].id).kakao_room_name == "홍길동 방"
