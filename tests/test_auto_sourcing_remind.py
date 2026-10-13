"""A1 소싱 리마인드 — **이 달 딜을 안 준 심사역에게 2·3주차 수요일 11:00.**

1. 정한 갈래의 사람 중 이 달 `딜 받음` 이 아닌 사람에게, 2주차·3주차 수요일
   11:00 에 리마인드 문구가 보내는 계정 것으로 예약된다.
2. 문구는 딜 소싱 제안과 같은 틀(인사말 + 안내문)에 리마인드 글.
3. `딜 받음` 인 사람 · 방이 없는 사람은 빠진다. 아침 뒤에 눌러도 풀릴 때 빠진다.
4. 딜 소싱 화면의 `딜 받음` 단추 · 메일로 적는 길(`record_from_mail`).
5. [방 후보 찾기] — 보내는 계정 PC 로 방 확인 잡, 찾은 제목은 후보로만,
   [이 방으로 확정] 해야 방 이름이 된다.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD, OTHER_TOKEN, auth

TEST_ROOM = "자동화 시험방"
GROUP = "시리즈 A 이상 딜 소싱 참여 심사역"
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
        "other": person("박다른", bucket="M&A 찾는 투자사", room="박다른 방"),
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
    from app.services import scheduled_send

    _turn_on(db)
    assert _run(db, datetime(2026, 10, 7, 9, 0))["status"] == "not_today"
    assert _run(db, datetime(2026, 10, 13, 9, 0))["status"] == "not_today"
    result = _run(db, WEEK2)
    assert result["status"] == "ready"
    items = _items(db)
    assert {i.sourcing_contact_id for i in items} == {people["a"].id, people["b"].id}
    job = items[0].job
    assert job.kind == "sourcing_intro" and job.user_id == users["u2"].id
    assert scheduled_send.label(scheduled_send.scheduled_at(job)) == "10/14(수) 11:00"
    assert any("방 이름 없음" in s for s in result["skipped"])

    assert _run(db, WEEK3)["status"] == "ready"      # 한 달에 두 번
    assert len(_items(db)) == 4


def test_message_is_the_sourcing_frame_with_the_reminder(db, users, people):
    from app.services.automations import sourcing_remind

    _turn_on(db)
    _run(db, WEEK2)
    items = {i.sourcing_contact_id: i for i in _items(db)}
    text = items[people["a"].id].message
    assert text.startswith("안녕하세요, 홍길동 심사역")
    assert "Deal Sourcing 네트워크 관련하여 이번 달 딜 공유 요청드립니다." in text
    # 직함이 빈 줄은 갈래로 호칭을 채운다(딜 소싱 제안과 같은 규칙).
    assert items[people["b"].id].message.startswith("안녕하세요, 김철수 심사역")
    assert sourcing_remind.DEFAULT_BODY in text


def test_received_this_month_is_left_out(db, users, people):
    from app.services import sourcing_receipts

    sourcing_receipts.mark(db, people["a"].id, "2026-10")
    db.commit()
    _turn_on(db)
    result = _run(db, WEEK2)
    assert [i.sourcing_contact_id for i in _items(db)] == [people["b"].id]
    assert any("이번 달 딜 받음" in s for s in result["skipped"])


def test_received_after_setup_drops_it_at_release(db, users, people):
    from app.services import scheduled_send, sourcing_receipts

    _turn_on(db)
    _run(db, WEEK2)
    sourcing_receipts.mark(db, people["b"].id, "2026-10")
    db.commit()
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 11, 0, 20)))
    status = {i.sourcing_contact_id: i.status for i in _items(db)}
    assert status == {people["a"].id: "pending", people["b"].id: "canceled"}


def test_groups_are_a_setting(db, users, people):
    from app.services import automation, automation_runner as runner

    runner.save_params(db, automation.SOURCING_REMIND,
                       {"groups": "M&A 찾는 투자사", "weeks": "2", "weekday": "수",
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


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def test_received_button_on_the_sourcing_page(client, db, users, people):
    from app.services import sourcing_receipts

    _login(client, "01000000001")
    page = client.get(f"/sourcing?tab={GROUP}")
    assert "10월 딜 받음" in page.text or "월 딜 받음" in page.text
    month = sourcing_receipts.month_of()
    client.post(f"/sourcing/{people['a'].id}/received",
                data={"month": "2026-10", "on": "1", "tab": GROUP},
                follow_redirects=False)
    assert sourcing_receipts.is_received(db, people["a"].id, "2026-10")
    client.post(f"/sourcing/{people['a'].id}/received",
                data={"month": "2026-10", "on": "0", "tab": GROUP},
                follow_redirects=False)
    db.expire_all()
    assert not sourcing_receipts.is_received(db, people["a"].id, "2026-10")
    assert month[:4].isdigit()


def test_mail_hook_marks_by_address(db, users, people):
    from datetime import date

    from app.services import sourcing_receipts

    people["a"].email = "Hong@Example.com"
    db.commit()
    assert sourcing_receipts.record_from_mail(db, "hong@example.com",
                                              when=date(2026, 10, 9)) == [people["a"].id]
    db.commit()
    assert sourcing_receipts.is_received(db, people["a"].id, "2026-10")


def test_room_search_queues_on_the_sender_and_keeps_candidates(client, db, users, people):
    from app.models import SendJob, SourcingContact

    _login(client, "01000000002")
    answer = client.post("/sourcing/rooms/search", data={"tab": GROUP},
                         follow_redirects=False)
    assert answer.status_code == 303
    job = db.execute(select(SendJob)).scalars().one()
    assert (job.kind, job.topic, job.user_id) == ("verify_room", "sourcing_room",
                                                  users["u2"].id)
    assert [i.sourcing_contact_id for i in job.items] == [people["noroom"].id]

    got = client.get("/api/agent/poll", params={"kinds": "verify_room"},
                     headers=auth(OTHER_TOKEN)).json()
    item = got["items"][0]
    assert item["query"] == "이빈방" and "target" not in item
    client.post(f"/api/agent/items/{item['id']}/result",
                json={"status": "sent", "verify_result": "verified",
                      "found_room": "이빈방 심사역 가나다", "candidates": ["이빈방 심사역 가나다"]},
                headers=auth(OTHER_TOKEN))
    db.expire_all()
    row = db.get(SourcingContact, people["noroom"].id)
    assert row.kakao_room_name is None       # 후보일 뿐 — 방 이름이 아니다
    page = client.get(f"/sourcing?tab={GROUP}")
    assert "이 방으로 확정" in page.text
    client.post(f"/sourcing/{row.id}/room-confirm",
                data={"room": "이빈방 심사역 가나다", "tab": GROUP},
                follow_redirects=False)
    db.expire_all()
    row = db.get(SourcingContact, people["noroom"].id)
    assert (row.kakao_room_name, row.room_verified) == ("이빈방 심사역 가나다", "verified")


def test_room_search_is_admin_only(client, db, users, people):
    from app.models import SendJob

    _login(client, "01000000001")
    client.post("/sourcing/rooms/search", data={"tab": GROUP}, follow_redirects=False)
    assert db.execute(select(SendJob)).scalars().all() == []


def test_confirm_refuses_a_made_up_title(client, db, users, people):
    from app.models import SourcingContact

    _login(client, "01000000001")
    client.post(f"/sourcing/{people['noroom'].id}/room-confirm",
                data={"room": "지어낸 방", "tab": GROUP}, follow_redirects=False)
    db.expire_all()
    assert db.get(SourcingContact, people["noroom"].id).kakao_room_name is None


def test_deleting_a_row_takes_its_receipts(client, db, users, people):
    from app.models import SourcingReceipt
    from app.services import sourcing_receipts

    sourcing_receipts.mark(db, people["other"].id, "2026-10")
    db.commit()
    _login(client, "01000000001")
    assert client.delete(f"/api/sourcing/{people['other'].id}").status_code == 200
    assert db.execute(select(SourcingReceipt)).scalars().all() == []
