"""진행 단계 — 어디까지 갔는지가 맞게 매겨지는가.

"IR 있음 / 미팅 있음" 태그로는 *IR 자료까지 보냈는데 미팅으로 못 넘어간 곳*을
골라낼 수 없었다. 단계를 매기는 규칙이 어긋나면 그 명단이 통째로 틀어지므로
사다리의 각 칸을 하나씩 못 박는다.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import deal_stage

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def contact(db, users):
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    row = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                    firm="가나벤처스", source_sheet="내 명단", channel_kakao=1)
    db.add(row)
    db.commit()
    return row


def stage_of(db, contact) -> str:
    return deal_stage.of_many(db, [contact.id])[contact.id]


def test_nothing_yet(db, contact):
    assert stage_of(db, contact) == deal_stage.NONE


def test_imported_history_counts(db, contact):
    """시트에서 옮겨 온 기록만 있어도 단계가 매겨져야 한다.

    이걸 놓치면 옮겨 오기 전 담당자 300여 명이 전부 '접촉 전'으로 보인다.
    """
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro",
                           happened_at="2025-06-04", content="7개사"))
    db.commit()
    assert stage_of(db, contact) == deal_stage.INTRO

    db.add(ContactActivity(contact_id=contact.id, kind="ir_request",
                           happened_at="2025-06-10", content="샘플애그"))
    db.commit()
    assert stage_of(db, contact) == deal_stage.IR_ASKED


def test_request_then_delivery(db, contact):
    from app.models import IrRequest

    request = IrRequest(user_id=contact.user_id, contact_id=contact.id,
                        company_name="샘플애그", status="open",
                        requested_at=date.today().isoformat())
    db.add(request)
    db.commit()
    assert stage_of(db, contact) == deal_stage.IR_ASKED

    request.status = "delivered"
    db.commit()
    assert stage_of(db, contact) == deal_stage.IR_SENT


def test_meetings_climb(db, contact):
    from app.models import Meeting

    first = Meeting(user_id=contact.user_id, contact_id=contact.id,
                    kind="first", status="planned",
                    scheduled_at=date.today().isoformat())
    db.add(first)
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_1

    second = Meeting(user_id=contact.user_id, contact_id=contact.id,
                     kind="second", status="planned",
                     scheduled_at=date.today().isoformat())
    db.add(second)
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_2

    second.status = "done"
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_DONE


def test_it_never_goes_back_down(db, contact):
    """거절당해도 '미팅까지 갔던 곳'은 그대로다.

    단계는 *지금 상태*가 아니라 *어디까지 갔나*다. 거절을 단계로 덮어쓰면
    미팅까지 갔다가 거절된 명단 — 제일 아까운 명단 — 을 다시 못 찾는다.
    """
    from app.models import ContactActivity, Meeting

    db.add_all([
        Meeting(user_id=contact.user_id, contact_id=contact.id, kind="first",
                status="done", outcome="pass",
                scheduled_at=date.today().isoformat()),
        # 나중에 딜소개를 한 번 더 보냈다고 단계가 내려가면 안 된다
        ContactActivity(contact_id=contact.id, kind="deal_intro",
                        happened_at="2025-08-06", content="7개사"),
    ])
    contact.status = "declined"
    db.commit()
    assert stage_of(db, contact) == deal_stage.MEET_DONE


def test_one_query_per_kind_not_per_contact(db, users):
    """300명 표에서 행마다 묻지 않는지. 느려지면 표가 못 쓰게 된다."""
    from sqlalchemy import event

    from app.models import ContactActivity, VcContact

    ids = []
    for i in range(50):
        row = VcContact(user_id=users["u1"].id, name=f"담당{i}")
        db.add(row)
        db.flush()
        db.add(ContactActivity(contact_id=row.id, kind="deal_intro",
                               happened_at="2025-06-04", content="7개사"))
        ids.append(row.id)
    db.commit()

    seen = []

    def count(*_args, **_kwargs):
        seen.append(1)

    event.listen(db.bind, "before_cursor_execute", count)
    try:
        result = deal_stage.of_many(db, ids)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)

    assert len(result) == 50
    assert all(v == deal_stage.INTRO for v in result.values())
    assert len(seen) <= 5, f"담당자 50명에 질의 {len(seen)}번 — 행마다 묻고 있다"


def test_funnel_keeps_empty_steps():
    """0명인 칸을 지우면 어디서 끊겼는지가 안 보인다."""
    rows = deal_stage.funnel({1: deal_stage.INTRO, 2: deal_stage.INTRO,
                              3: deal_stage.MEET_DONE})
    assert [r["key"] for r in rows] == deal_stage.LADDER
    counts = {r["label"]: r["count"] for r in rows}
    assert counts["1차 딜소개"] == 2
    assert counts["IR 자료 전달"] == 0
    assert counts["미팅 완료"] == 1


def test_table_shows_the_stage_and_can_filter_on_it(client, db, contact):
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=contact.id, kind="ir_request",
                           happened_at="2025-06-10", content="샘플애그"))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/contacts").text

    assert 'data-f-dealstage="IR 자료 요청"' in body      # 행에 값이 붙는다
    assert "dealstage:진행 단계" in body                  # 컬럼 필터가 열린다
    assert "funnel-step" in body                          # 눌러서 거를 수 있다
