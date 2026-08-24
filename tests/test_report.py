"""주간·월간 업무 보고.

원본 시트는 미팅을 하고 나서 **사람이 다시 옮겨 적고** 있었다.

    6월 미팅 총 4개사
      6월 첫주   미팅 완료 2개사   결과 문의전화 완료
      6월 둘째주 미팅 완료 0개사

옮겨 적는 사이에 빠지는 건이 생긴다. 이제 기록에서 뽑는다.
시트에 "결과확인전화가 없으면 계약을 잊어버리는 경우가 발생할 수 있습니다" 라고
적혀 있었다 — **결과 문의를 했는지**가 이 보고의 핵심이다.
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _meeting(db, users, when, *, status="done", outcome="reviewing",
             followup_due=None, followup_done=0, user_key="u1", who="홍길동"):
    """`who` 로 담당자를 나눈다.

    한 담당자에게 미팅이 두 건이면 **뒤엣것이 앞엣것을 대신한다** — 2차 미팅을
    잡았으면 1차에 결과를 물을 이유가 없다. 그 규칙과 무관한 것을 재려면
    담당자를 나눠야 한다.
    """
    from app.models import Meeting, VcContact

    contact = db.query(VcContact).filter_by(name=who).first()
    if contact is None:
        contact = VcContact(user_id=users["u1"].id, name=who, firm="가나벤처스")
        db.add(contact)
        db.flush()
    row = Meeting(user_id=users[user_key].id, contact_id=contact.id,
                  scheduled_at=when.isoformat(), kind="first", status=status,
                  done_at=when.isoformat() if status == "done" else None,
                  outcome=outcome if status == "done" else None,
                  followup_due=(followup_due or when).isoformat(),
                  followup_done=followup_done)
    db.add(row)
    db.commit()
    return row


# --- 주차 계산 --------------------------------------------------------------

@pytest.mark.parametrize("day, week", [
    (date(2026, 6, 1), 1),
    (date(2026, 6, 10), 2),
    (date(2026, 6, 16), 3),
    (date(2026, 6, 25), 4),
    (date(2026, 6, 30), 5),
])
def test_week_of_month(day, week):
    from app.services.report import week_of_month

    assert week_of_month(day) == week


# --- 보고 -------------------------------------------------------------------

def test_monthly_groups_by_week(db, users):
    """시트와 같은 모양 — 월 합계 + 주차별."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10))
    _meeting(db, users, date(2026, 6, 16))
    _meeting(db, users, date(2026, 6, 25))
    _meeting(db, users, date(2026, 7, 1))     # 다른 달은 안 섞인다

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 20))
    assert data["total"] == 3
    assert [w["week"] for w in data["weeks"]] == [2, 3, 4]
    assert all(w["done"] == 1 for w in data["weeks"])


def test_late_followup_is_counted(db, users):
    """열흘이 지났는데 결과를 안 물어본 건 — 이 보고가 잡아내야 할 것."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="안물어본사람",
             followup_due=date(2026, 6, 20), followup_done=0)
    _meeting(db, users, date(2026, 6, 16), who="물어본사람",
             followup_due=date(2026, 6, 26), followup_done=1)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["followup_done"] == 1
    assert data["followup_late"] == 1


def test_future_followup_is_not_late(db, users):
    from app.services import report

    _meeting(db, users, date(2026, 6, 25), followup_due=date(2026, 7, 5))
    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["followup_late"] == 0


def test_outcomes_are_counted(db, users):
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), outcome="investing")
    _meeting(db, users, date(2026, 6, 11), outcome="investing")
    _meeting(db, users, date(2026, 6, 12), outcome="pass")

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert dict(data["outcomes"]) == {"투자 검토": 2, "거절": 1}


def test_ir_requests_are_counted_too(db, users):
    """미팅만으로는 그 달의 반응이 안 보인다."""
    from app.models import IrRequest, VcContact
    from app.services import report

    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add_all([
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_name="샘플애그", requested_at="2026-06-05",
                  status="delivered"),
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_name="샘플메디", requested_at="2026-06-20"),
    ])
    db.commit()

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["ir_requested"] == 2
    assert data["ir_delivered"] == 1
    assert data["ir_open"] == 1


def test_my_report_excludes_teammates(db, users):
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), user_key="u1")
    _meeting(db, users, date(2026, 6, 11), user_key="u2")

    mine = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    team = report.monthly(db, 2026, 6, None, today=date(2026, 7, 1))
    assert mine["total"] == 1
    assert team["total"] == 2


def test_page_opens(logged):
    r = logged.get("/report")
    assert r.status_code == 200
    assert "미팅 총" in r.text


def test_team_scope_is_admin_only(logged, db, users):
    """남의 미팅이 보이는 화면이다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 11), user_key="u2")
    body = logged.get("/report?month=2026-06&scope=team").text
    # 관리자가 아니면 scope=team 을 줘도 본인 것만 보인다
    assert "미팅 총 0개사" in body


# --- 결과를 물어볼 필요가 없는 경우 --------------------------------------------

def test_a_rejected_meeting_needs_no_followup(db, users):
    """거절당한 곳에 "그 뒤 어떻게 되셨나요" 를 묻는 것은 실례다 —
    이미 답을 받았으므로 물어볼 것이 남아 있지 않다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="거절함", outcome="pass",
             followup_due=date(2026, 6, 20), followup_done=0)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    assert data["followup_open"] == 0
    assert data["followup_late"] == 0


def test_a_held_meeting_still_needs_one(db, users):
    """보류는 다시 살아날 수 있어 물어볼 값어치가 있다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="보류함", outcome="hold",
             followup_due=date(2026, 6, 20), followup_done=0)

    assert report.monthly(db, 2026, 6, users["u1"],
                          today=date(2026, 7, 1))["followup_open"] == 1


def test_booking_the_next_meeting_closes_the_previous_one(db, users):
    """2차 미팅을 잡았다는 것은 이미 이어졌다는 뜻이다 — 1차에 결과를
    물을 이유가 없다."""
    from app.services import report

    _meeting(db, users, date(2026, 6, 10), who="이어진사람",
             followup_due=date(2026, 6, 20), followup_done=0)
    _meeting(db, users, date(2026, 6, 24), who="이어진사람",
             followup_due=date(2026, 7, 4), followup_done=0)

    data = report.monthly(db, 2026, 6, users["u1"], today=date(2026, 7, 1))
    # 뒤엣것 하나만 남는다
    assert data["followup_open"] == 1


def test_completing_a_rejected_meeting_schedules_nothing(db, users):
    """거절로 끝났으면 물어볼 날 자체를 잡지 않는다."""
    from app.models import Meeting, VcContact
    from app.services import pipeline

    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.commit()
    meeting = Meeting(user_id=users["u1"].id, contact_id=contact.id,
                      kind="first", status="planned",
                      scheduled_at=date(2026, 6, 10).isoformat())
    db.add(meeting)
    db.commit()

    pipeline.complete_meeting(db, meeting, outcome="pass", when=date(2026, 6, 10))
    db.commit()
    assert meeting.followup_due is None

    pipeline.complete_meeting(db, meeting, outcome="reviewing", when=date(2026, 6, 10))
    db.commit()
    assert meeting.followup_due is not None
