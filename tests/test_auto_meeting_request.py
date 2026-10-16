"""A2 미팅 요청 2회 — **IR 자료 전달 7일 · 10일 뒤, 답이 오면 멈춘다.**

1. 자료 전달 7일 뒤(주말이면 다음 평일) 14:00 에 미팅 요청이 보내는 계정 것으로
   예약된다 — 발송 화면의 미팅 요청 탭과 같은 글.
2. 첫 번째가 실제로 나갔고 답이 없으면 10일 뒤 조금 다른 글로 한 번 더.
   첫 번째가 끝내 안 나갔으면(시각을 놓침 · 실패) 두 번째 대신 **첫 번째를
   늦게 한 번** — 그 분이 아무것도 못 받는 일이 없게. 옛 건은 거둔다.
3. 미팅 기록 · 새 IR 요청 · [답 옴] 이 있으면 멈춘다. 풀리기 직전에도 다시 본다.
4. 사람이 이미 미팅 요청을 보냈으면 첫 번째는 안 나간다.
5. 나가기 전날 오늘 할 일에 `내일 미팅 요청 나갈 곳 N` — 담당 팀원에게.
6. [답 옴] 은 자기 담당자에게 누른다.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

TEST_ROOM = "자동화 시험방"
DELIVERED = "2026-10-05"            # 월 → +7 = 10/12(월) · +10 = 10/15(목)
FIRST_DAY = datetime(2026, 10, 12, 9, 0)
SECOND_DAY = datetime(2026, 10, 15, 9, 0)


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def team(db, users):
    from app.models import AutoSendSetting, IrRequest, VcContact

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))

    def contact(name, firm):
        row = VcContact(user_id=users["u1"].id, name=name, firm=firm, title="심사역",
                        kakao_room_name=f"{name} {firm} Deal 공유",
                        connect_stage="connected", source_sheet="내 명단")
        db.add(row)
        db.flush()
        db.add(IrRequest(user_id=users["u1"].id, contact_id=row.id,
                         company_name="가나기업", requested_at="2026-10-01",
                         status="delivered", delivered_at=DELIVERED))
        return row

    people = {"a": contact("홍길동", "가나다벤처스"),
              "b": contact("김철수", "라마바벤처스")}
    db.commit()
    return people


def _turn_on(db, test=False):
    from app.services import automation

    return automation.save(db, automation.MEETING_REQUEST, enabled=True,
                           user_id=None, test_mode=test, test_room=TEST_ROOM)


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.MEETING_REQUEST, _aware(now))


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


def _deliver(db, items):
    """발송기가 보냈다고 알린 것처럼."""
    for item in items:
        item.status = "sent"
        item.sent_at = "2026-10-12T14:00:30+09:00"
    db.commit()


def test_first_ask_on_day_seven_with_the_meeting_tab_text(db, users, team):
    from app.routers import deals
    from app.services import scheduled_send

    _turn_on(db)
    assert _run(db, datetime(2026, 10, 9, 9, 0))["status"] == "empty"   # 아직
    result = _run(db, FIRST_DAY)
    assert result["status"] == "ready"
    items = _items(db)
    assert {i.contact_id for i in items} == {team["a"].id, team["b"].id}
    job = items[0].job
    assert job.user_id == users["u2"].id and job.kind == "deal_intro"
    assert scheduled_send.label(scheduled_send.scheduled_at(job)) == "10/12(월) 14:00"
    a = next(i for i in items if i.contact_id == team["a"].id)
    assert a.message == deals.meeting_ask_message(db, users["u2"], team["a"])
    assert a.stage == 3


def test_second_ask_only_after_the_first_went_out(db, users, team):
    from app.routers import deals

    _turn_on(db)
    _run(db, FIRST_DAY)
    first = _items(db)
    # 첫 번째는 한 사람(a)에게만 실제로 나갔다.
    _deliver(db, [i for i in first if i.contact_id == team["a"].id])

    result = _run(db, SECOND_DAY)
    assert result["status"] == "ready"
    second = [i for i in _items(db) if i.id not in {x.id for x in first}]
    by_contact = {i.contact_id: i for i in second}
    assert set(by_contact) == {team["a"].id, team["b"].id}
    again = deals.meeting_ask_message(db, users["u2"], team["a"], again=True)
    assert by_contact[team["a"].id].message == again
    assert again != first[0].message
    # b 는 첫 번째가 시각을 놓쳐 안 나갔다 — 두 번째 대신 **첫 번째를 늦게**.
    assert by_contact[team["b"].id].message == deals.meeting_ask_message(
        db, users["u2"], team["b"])
    old_b = next(i for i in _items(db) if i.id in {x.id for x in first}
                 and i.contact_id == team["b"].id)
    assert old_b.status == "canceled" and "다시 실림" in old_b.error


def test_reply_mark_meeting_or_new_request_stops_it(db, users, team):
    from app.models import IrRequest, Meeting
    from app.services.automations import meeting_request as a2

    a2.mark_replied(db, team["a"], when=date(2026, 10, 8))
    db.add(Meeting(user_id=users["u1"].id, contact_id=team["b"].id,
                   scheduled_at="2026-10-20", status="scheduled"))
    db.commit()
    _turn_on(db)
    result = _run(db, FIRST_DAY)
    assert result["status"] == "empty"
    joined = " / ".join(result["skipped"])
    assert "답 옴 표시가 있습니다" in joined and "미팅이 기록됐습니다" in joined

    a2.undo_replied(db, team["a"])
    db.add(IrRequest(user_id=users["u1"].id, contact_id=team["a"].id,
                     company_name="다른기업", requested_at="2026-10-07",
                     status="open"))
    db.commit()
    asks, skipped = a2.due_on(db, None, date(2026, 10, 12), False)
    assert asks == []
    assert any("IR 요청이 새로 들어왔습니다" in s for s in skipped)


def test_reply_after_setup_drops_it_at_release(db, users, team):
    from app.services import scheduled_send
    from app.services.automations import meeting_request as a2

    _turn_on(db)
    _run(db, FIRST_DAY)
    a2.mark_replied(db, team["a"], when=date(2026, 10, 12))
    db.commit()
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 12, 14, 0, 20)))
    status = {i.contact_id: i.status for i in _items(db)}
    assert status == {team["a"].id: "canceled", team["b"].id: "pending"}


def test_already_asked_by_hand_skips_the_first(db, users, team):
    from app.services import pipeline

    pipeline.record_meeting_ask(db, team["a"].id, when=date(2026, 10, 7))
    db.commit()
    _turn_on(db)
    result = _run(db, FIRST_DAY)
    assert [i.contact_id for i in _items(db)] == [team["b"].id]
    assert any("미팅 요청을 이미 보냈습니다" in s for s in result["skipped"])


def test_day_before_note_goes_to_the_owner(db, users, team):
    from app.services import automation_runner as runner

    _turn_on(db)
    friday = _aware(datetime(2026, 10, 9, 10, 0))      # 다음 평일 = 월 10/12
    lines = runner.today_items(db, users["u1"], friday)
    note = next(line for line in lines if "미팅 요청 나갈 곳" in line["title"])
    assert note["title"] == "10/12 미팅 요청 나갈 곳 2"
    assert note["href"] == "/automations/meeting-request"
    sunday = _aware(datetime(2026, 10, 11, 10, 0))
    assert runner.today_items(db, users["u1"], sunday)[0]["title"] == "내일 미팅 요청 나갈 곳 2"


def test_reply_button_for_the_owner(client, db, users, team):
    from app.models import ContactActivity

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    page = client.get("/automations/meeting-request")
    assert page.status_code == 200
    answer = client.post(f"/automations/meeting-request/{team['a'].id}/replied",
                         follow_redirects=False)
    assert answer.status_code == 303
    rows = db.execute(select(ContactActivity).where(
        ContactActivity.kind == "reply")).scalars().all()
    assert [r.contact_id for r in rows] == [team["a"].id]


def test_reply_button_refuses_someone_elses_contact(client, db, users, team):
    from app.models import ContactActivity, VcContact

    other = VcContact(user_id=users["u2"].id, name="남의분", firm="가나다벤처스",
                      kakao_room_name="남의 방", connect_stage="connected",
                      source_sheet="남 명단")
    db.add(other)
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    answer = client.post(f"/automations/meeting-request/{other.id}/replied",
                         follow_redirects=False)
    assert answer.status_code == 404
    assert db.execute(select(ContactActivity)).scalars().all() == []


def test_second_must_come_after_first(db, users, team):
    from app.services import automation, automation_runner as runner

    with pytest.raises(ValueError, match="뒤여야"):
        runner.save_params(db, automation.MEETING_REQUEST,
                           {"first_days": "7", "second_days": "5"})


def test_test_mode_goes_to_the_test_room(db, users, team):
    _turn_on(db, test=True)
    _run(db, FIRST_DAY)
    items = _items(db)
    assert {i.room_name for i in items} == {TEST_ROOM}
    assert all(i.contact_id is None for i in items)
