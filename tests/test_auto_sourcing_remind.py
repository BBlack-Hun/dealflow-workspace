"""A1 소싱 리마인드 — **이 달 딜을 안 준 심사역에게 2·3주차 수요일 11:00.**

손으로 보내는 월간 리마인드(main #283)를 자동으로 돌린 것이라, 표 · 문구 ·
방 후보 찾기는 main 의 것을 그대로 쓴다(`sourcing_receipts` · `sourcing_msg`
· `sourcing_rooms` — 그쪽 시험이 따로 있다). 여기서는 자동화만 본다.

1. 정한 갈래의 사람 중 이 달 `딜 받음` 이 아닌 사람에게, 2주차·3주차 수요일
   11:00 에 리마인드가 보내는 계정 것으로 예약된다(`topic=sourcing_remind`).
2. 글은 손으로 보내는 월간 리마인드와 같다(인사말 + 리마인드 문구, `{월}`).
3. `딜 받음` · `불참여` · 방 없음은 빠진다. 아침 뒤에 그리 되어도 풀릴 때 빠진다.
4. 방 — 시리즈 A 갈래는 투자사 방을 이어받지 않는다(main #284). 다른 갈래는
   이어받되 보내는 계정 카톡 기준 제목으로(#274).
5. 켜 두면 리마인드 30분 전에 메일 확인이 한 번 더 돈다(main #281 의 고리).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select

TEST_ROOM = "자동화 시험방"
GROUP = "시리즈 A 이상 딜 소싱 참여 심사역"
OTHER = "M&A 찾는 투자사"
# 2026-10-01 은 목요일 — 수요일: 10/7(1주차) · 10/14(2주차) · 10/21(3주차)
WEEK2 = datetime(2026, 10, 14, 9, 0)
WEEK3 = datetime(2026, 10, 21, 9, 0)


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def people(db, users):
    from app.models import AutoSendSetting, SourcingContact

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))

    def person(name, bucket=GROUP, room=None, **kw):
        row = SourcingContact(bucket=bucket, name=name, firm="가나다벤처스",
                              kakao_room_name=room, **kw)
        db.add(row)
        db.flush()
        return row

    rows = {
        "a": person("홍길동", room="홍길동 심사역 방", title="심사역"),
        "b": person("김철수", room="김철수 방", title=""),
        "noroom": person("이빈방"),
        "other": person("박다른", bucket=OTHER, room="박다른 방"),
    }
    db.commit()
    return rows


def _turn_on(db, test=False):
    from app.services import automation

    return automation.save(db, automation.SOURCING_REMIND, enabled=True,
                           user_id=None, test_mode=test, test_room=TEST_ROOM)


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.SOURCING_REMIND, _aware(now))


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


def test_second_and_third_wednesday_at_eleven(db, users, people):
    from app.services import scheduled_send, sourcing_msg

    _turn_on(db)
    assert _run(db, datetime(2026, 10, 7, 9, 0))["status"] == "not_today"
    assert _run(db, datetime(2026, 10, 13, 9, 0))["status"] == "not_today"
    result = _run(db, WEEK2)
    assert result["status"] == "ready"
    items = _items(db)
    assert {i.sourcing_contact_id for i in items} == {people["a"].id, people["b"].id}
    job = items[0].job
    assert job.kind == "sourcing_intro" and job.user_id == users["u2"].id
    # 손으로 보낸 월간 리마인드와 같은 이름으로 남는다.
    assert job.topic == sourcing_msg.REMIND_KIND
    assert scheduled_send.label(scheduled_send.scheduled_at(job)) == "10/14(수) 11:00"
    assert any("방 이름 없음" in s for s in result["skipped"])

    assert _run(db, WEEK3)["status"] == "ready"      # 한 달에 두 번
    assert len(_items(db)) == 4


def test_message_is_the_manual_monthly_remind(db, users, people):
    from app.services import sourcing_msg

    _turn_on(db)
    _run(db, WEEK2)
    items = {i.sourcing_contact_id: i for i in _items(db)}
    text = items[people["a"].id].message
    assert text.startswith("안녕하세요, 홍길동 심사역")
    # 손으로 보낼 때 고르는 그 문구 — `{월}` 은 보내는 날의 달.
    body = sourcing_msg.remind_body_for(db, users["u2"], GROUP, date(2026, 10, 14))
    assert body in text
    assert sourcing_msg.MONTH_TOKEN not in text
    # 직함이 빈 줄은 갈래로 호칭을 채운다(딜 소싱 제안과 같은 규칙).
    assert items[people["b"].id].message.startswith("안녕하세요, 김철수 심사역")


def test_received_this_month_is_left_out(db, users, people):
    from app.services import sourcing_receipts

    sourcing_receipts.mark(db, people["a"].id, "2026-10")
    db.commit()
    _turn_on(db)
    result = _run(db, WEEK2)
    assert [i.sourcing_contact_id for i in _items(db)] == [people["b"].id]
    assert any("이번 달 딜 받음" in s for s in result["skipped"])


def test_left_out_participation_is_skipped(db, users, people):
    from app.services import sourcing_sync

    people["a"].participation = sourcing_sync.LEFT
    db.commit()
    _turn_on(db)
    result = _run(db, WEEK2)
    assert [i.sourcing_contact_id for i in _items(db)] == [people["b"].id]
    assert any(sourcing_sync.LEFT in s for s in result["skipped"])


def test_received_or_left_after_setup_drops_it_at_release(db, users, people):
    from app.models import SourcingContact
    from app.services import scheduled_send, sourcing_receipts, sourcing_sync

    _turn_on(db)
    _run(db, WEEK2)
    # 아침에 선 뒤 — 메일 확인이 b 를 `딜 받음` 으로, 사람이 a 를 `불참여` 로.
    sourcing_receipts.mark(db, people["b"].id, "2026-10",
                           source=sourcing_receipts.SOURCE_MAIL)
    db.get(SourcingContact, people["a"].id).participation = sourcing_sync.LEFT
    db.commit()
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 11, 0, 20)))
    status = {i.sourcing_contact_id: i.status for i in _items(db)}
    assert status == {people["a"].id: "canceled", people["b"].id: "canceled"}


def test_groups_are_a_setting(db, users, people):
    from app.services import automation, automation_runner as runner

    runner.save_params(db, automation.SOURCING_REMIND,
                       {"groups": OTHER, "weeks": "2", "weekday": "수",
                        "time": "10:30"})
    _turn_on(db)
    _run(db, WEEK2)
    assert [i.sourcing_contact_id for i in _items(db)] == [people["other"].id]
    assert _run(db, WEEK3)["status"] == "not_today"
    with pytest.raises(ValueError):
        runner.save_params(db, automation.SOURCING_REMIND, {"weekday": "수요일"})


def test_test_mode_goes_to_the_test_room(db, users, people):
    _turn_on(db, test=True)
    _run(db, WEEK2)
    items = _items(db)
    assert {i.room_name for i in items} == {TEST_ROOM}
    assert all(i.sourcing_contact_id is None for i in items)
    assert items[0].job.topic is None          # 시험 회차는 기록에 안 섞인다


def test_rooms_follow_the_sourcing_link_rule(db, users, people):
    """시리즈 A 갈래는 투자사 방을 이어받지 않는다(main #284 — 남의 딜소개 방).
    다른 갈래는 번호로 이어받되, 보내는 계정 카톡 기준 제목으로(#274)."""
    from app.models import SenderRoom, SourcingContact, VcContact
    from app.services import automation, automation_runner as runner

    phone_a, phone_b = "010-1234-0001", "010-1234-0002"
    vc_a = VcContact(user_id=users["u1"].id, name="최연결", firm="라마바벤처스",
                     title="심사역", phone=phone_a, kakao_room_name="최연결 딜소개 방",
                     connect_stage="connected", source_sheet="내 명단")
    vc_b = VcContact(user_id=users["u1"].id, name="정이어", firm="라마바벤처스",
                     title="심사역", phone=phone_b, kakao_room_name="정이어 딜소개 방",
                     connect_stage="connected", source_sheet="내 명단")
    db.add_all([vc_a, vc_b])
    db.flush()
    db.add(SenderRoom(sender_user_id=users["u2"].id, contact_id=vc_b.id,
                      room_name="정이어 (보내는 계정 제목)", verified=1))
    series_a = SourcingContact(bucket=GROUP, name="최연결", firm="라마바벤처스",
                               title="심사역", phone=phone_a)
    other = SourcingContact(bucket=OTHER, name="정이어", firm="라마바벤처스",
                            title="심사역", phone=phone_b)
    db.add_all([series_a, other])
    db.commit()

    runner.save_params(db, automation.SOURCING_REMIND,
                       {"groups": f"{GROUP}\n{OTHER}", "weeks": "2,3",
                        "weekday": "수", "time": "11:00"})
    _turn_on(db)
    result = _run(db, WEEK2)
    rooms = {i.sourcing_contact_id: i.room_name for i in _items(db)}
    assert series_a.id not in rooms
    assert any(s.startswith("최연결(") and "방 이름 없음" in s
               for s in result["skipped"])
    assert rooms[other.id] == "정이어 (보내는 계정 제목)"


def test_mail_check_runs_again_before_the_remind(db, users, people):
    """켜 두면 리마인드가 나가는 날 그 30분 전에 메일 확인 회차가 하나 더 선다."""
    from app.services import automation, sourcing_mail
    from app.services.automations import sourcing_remind  # noqa: F401 — 고리를 단다

    assert sourcing_remind.remind_at in sourcing_mail.REMIND_SOURCES
    wed = date(2026, 10, 14)

    def pre(day):
        return [s for s in sourcing_mail.slots_on(db, day)
                if s.key == sourcing_mail.SLOT_PRE]

    assert pre(wed) == []                       # 꺼져 있으면 없다
    _turn_on(db)
    [slot] = pre(wed)
    assert slot.at.strftime("%H:%M") == "10:30"
    assert slot.until.strftime("%H:%M") == "11:00"
    assert pre(date(2026, 10, 7)) == []         # 1주차 — 리마인드가 없는 날

    automation.save(db, automation.SOURCING_REMIND, enabled=False, user_id=None,
                    test_mode=False, test_room=TEST_ROOM)
    assert pre(wed) == []
