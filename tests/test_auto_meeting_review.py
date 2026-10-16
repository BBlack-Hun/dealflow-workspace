"""A7 미팅 후 검토결과 문의 — **팀원 전원의 미팅에, 이틀 뒤 14:00, 한 번.**

1. 미팅을 완료로 적은 지 2일 뒤(주말이면 다음 평일) 14:00 에 그 투자사 방으로
   미팅 후기 문구가 **보내는 계정 것으로** 예약된다 — 보내는 계정이 아닌
   팀원의 미팅도 포함(예전 결과 문의 목록이 빠뜨리던 것).
2. 문구는 발송 화면의 미팅 후기 탭과 글자 하나까지 같다.
3. 결과가 적힌 · 다음 미팅이 잡힌 · 취소된 · 멈춘 담당자 · 방 없는 미팅은 뺀다.
4. 방 제목은 보내는 계정 카톡 기준(확인된 제목이 있으면 그것).
5. 아침에 세운 뒤 결과를 적으면 풀리는 순간 빠진다.
6. 실제 모드로 켜져 있으면 예전 결과 문의 대기 목록은 서지 않는다.
7. 며칠 뒤 · 몇 시는 팀 현황에서 고친다(보내는 시간 밖은 안 받는다).
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

TEST_ROOM = "자동화 시험방"
# 2026-10-12 월 · 10-14 수 · 10-16 금 · 10-17 토 · 10-19 월
WED_9AM = datetime(2026, 10, 14, 9, 0)


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def team(db, users):
    from app.models import AutoSendSetting, Meeting, VcContact

    users["u2"].role = "admin"   # 보내는 계정
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))

    def contact(owner, name, firm, **kw):
        row = VcContact(user_id=owner.id, name=name, firm=firm, title="심사역",
                        kakao_room_name=kw.pop("room", f"{name} {firm} Deal 공유"),
                        connect_stage="connected", source_sheet="내 명단", **kw)
        db.add(row)
        db.flush()
        return row

    def meeting(owner, who, done="2026-10-12", **kw):
        row = Meeting(user_id=owner.id, contact_id=who.id,
                      scheduled_at=kw.pop("scheduled_at", done),
                      status=kw.pop("status", "done"), done_at=done,
                      outcome=kw.pop("outcome", "reviewing"), **kw)
        db.add(row)
        db.flush()
        return row

    people = {
        "u1": contact(users["u1"], "홍길동", "가나다벤처스"),
        "u2": contact(users["u2"], "김철수", "라마바벤처스"),
        "decided": contact(users["u1"], "이결정", "사아자벤처스"),
        "asked": contact(users["u1"], "박물음", "차카타벤처스"),
        "next": contact(users["u1"], "최다음", "파하벤처스"),
        "paused": contact(users["u1"], "정멈춤", "가가벤처스", status="paused"),
        "noroom": contact(users["u1"], "강빈방", "나나벤처스", room=""),
        "old": contact(users["u1"], "조오래", "다다벤처스"),
    }
    meetings = {
        "u1": meeting(users["u1"], people["u1"]),
        "u2": meeting(users["u2"], people["u2"]),
        "decided": meeting(users["u1"], people["decided"], outcome="investing"),
        "asked": meeting(users["u1"], people["asked"], followup_done=1),
        "next": meeting(users["u1"], people["next"]),
        "next_later": meeting(users["u1"], people["next"], status="scheduled",
                              scheduled_at="2026-10-20", done=None),
        "paused": meeting(users["u1"], people["paused"]),
        "noroom": meeting(users["u1"], people["noroom"]),
        "old": meeting(users["u1"], people["old"], done="2026-09-01"),
    }
    db.commit()
    return {"people": people, "meetings": meetings, "sender": users["u2"]}


def _turn_on(db, *, test=False, **params):
    from app.services import automation, automation_runner as runner

    if params:
        runner.save_params(db, automation.MEETING_REVIEW, params)
    return automation.save(db, automation.MEETING_REVIEW, enabled=True,
                           user_id=None, test_mode=test, test_room=TEST_ROOM)


def _run(db, now=WED_9AM):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.MEETING_REVIEW, _aware(now))


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


def test_two_days_later_at_two_pm_for_everyones_meetings(db, users, team):
    from app.services import scheduled_send

    _turn_on(db)
    result = _run(db)
    assert result["status"] == "ready", result
    items = _items(db)
    people = team["people"]
    assert {i.contact_id for i in items} == {people["u1"].id, people["u2"].id}
    job = items[0].job
    assert job.user_id == users["u2"].id and job.kind == "deal_intro"
    assert scheduled_send.label(scheduled_send.scheduled_at(job)) == "10/14(수) 14:00"
    assert all(i.stage == 3 for i in items)


def test_message_is_the_review_tab_text(db, users, team):
    from app.routers import deals

    _turn_on(db)
    _run(db)
    item = next(i for i in _items(db) if i.contact_id == team["people"]["u1"].id)
    assert item.message == deals.review_message(db, users["u2"], team["people"]["u1"])
    assert item.room_name == "홍길동 가나다벤처스 Deal 공유"


def test_skipped_ones_are_named(db, users, team):
    _turn_on(db)
    result = _run(db)
    joined = " / ".join(result["skipped"])
    assert "결과가 이미 적혀 있습니다" in joined
    assert "결과 문의를 이미 했습니다" in joined
    assert "그 뒤 미팅이 또 잡혀 있습니다" in joined
    assert "검토중단" in joined
    assert "방 이름 없음" in joined
    assert "조오래" not in joined     # 너무 오래된 미팅은 아예 안 줍는다


def test_not_before_the_day_and_not_on_weekends(db, users, team):
    _turn_on(db)
    assert _run(db, datetime(2026, 10, 13, 9, 0))["status"] == "empty"   # 하루 뒤
    assert _run(db, datetime(2026, 10, 17, 9, 0))["status"] == "not_today"


def test_uses_the_sender_room_title(db, users, team):
    from app.models import SenderRoom

    who = team["people"]["u1"]
    db.add(SenderRoom(sender_user_id=users["u2"].id, contact_id=who.id,
                      room_name="곽 카톡의 제목", verified=1))
    db.commit()
    _turn_on(db)
    _run(db)
    item = next(i for i in _items(db) if i.contact_id == who.id)
    assert item.room_name == "곽 카톡의 제목"


def test_test_mode_goes_to_the_test_room(db, users, team):
    _turn_on(db, test=True)
    _run(db)
    items = _items(db)
    assert {i.room_name for i in items} == {TEST_ROOM}
    assert any("원래 받을 방: 홍길동 가나다벤처스 Deal 공유" in i.message for i in items)
    assert all(i.contact_id is None for i in items)


def test_result_written_before_two_pm_drops_it(db, users, team):
    from app.services import scheduled_send

    _turn_on(db)
    _run(db)
    team["meetings"]["u1"].outcome = "hold"
    db.commit()
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    items = {i.contact_id: i for i in _items(db)}
    assert items[team["people"]["u1"].id].status == "canceled"
    assert "결과가 이미 적혀" in items[team["people"]["u1"].id].error
    assert items[team["people"]["u2"].id].status == "pending"
    assert items[team["people"]["u2"].id].job.status == "queued"


def test_once_per_meeting(db, users, team):
    _turn_on(db)
    _run(db)
    for item in _items(db):
        item.status, item.sent_at = "sent", "2026-10-14T14:00:30+09:00"
    db.commit()
    assert _run(db, datetime(2026, 10, 15, 9, 0))["status"] == "empty"
    assert len(_items(db)) == 2


def test_old_review_list_stands_down_when_real_mode_is_on(db, users, team):
    from app.services import auto_send

    auto_send.save(db, auto_send.KIND_REVIEW, enabled=True,
                   user_id=users["u2"].id, from_hour=10, until_hour=17,
                   max_per_day=10)
    _turn_on(db, test=False)
    result = auto_send.run_once(db, kind=auto_send.KIND_REVIEW,
                                now=datetime(2026, 10, 14, 11, 0))
    assert result["skipped"] == "자동화(미팅 후 검토결과 문의)가 맡고 있음"


def test_days_and_time_are_settings(db, users, team):
    from app.services import automation, automation_runner as runner, scheduled_send

    with pytest.raises(ValueError):
        runner.save_params(db, automation.MEETING_REVIEW, {"time": "20:00"})
    db.rollback()
    _turn_on(db, days="1", time="15:30")
    # 월요일에 끝낸 미팅이 하루 뒤(화)에 15:30.
    result = _run(db, datetime(2026, 10, 13, 9, 0))
    assert result["status"] == "ready"
    job = _items(db)[0].job
    assert scheduled_send.label(scheduled_send.scheduled_at(job)) == "10/13(화) 15:30"


def test_panel_shows_the_fields(client, db, users, team):
    from tests.conftest import DEMO_PASSWORD

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    page = client.get("/team")
    assert 'name="p_days"' in page.text and 'name="p_time"' in page.text
    client.post("/team/automations/meeting_review", data={
        "enabled": "", "test_mode": "on", "test_mode_shown": "1",
        "test_room": TEST_ROOM, "p_days": "3", "p_time": "13:00"},
        follow_redirects=False)
    from app.services import automation, automation_runner as runner

    db.expire_all()
    assert runner.values(automation.load(db, "meeting_review"), "meeting_review") == {
        "days": 3, "time": "13:00", "manual_days": 7,
        "item_gap_min": 20, "item_gap_max": 60}
