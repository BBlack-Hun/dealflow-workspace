"""무엇이 팀 공용이고 무엇이 내 것인가.

    IR 기업현황(딜 기업 DB) = **팀 전체가 함께 관리**한다.
      한 기업을 여러 사람이 서로 다른 투자사에게 소개하므로, 사람마다 따로
      두면 같은 기업이 여러 벌 생기고 내용이 갈라진다.

    나머지(투자사 관리 현황 · 후속 · IR/미팅 · 주간 업무 · 업무 보고) = **내 것**.
      남의 담당 투자사에 실수로 보내면 안 된다.

이 경계는 화면을 하나 더 만들 때마다 흐려진다. 테스트로 못 박아 둔다.
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


# --- 팀 공용: IR 기업현황 --------------------------------------------------

def test_company_added_by_one_user_is_visible_to_everyone(client, db, users):
    """한 사람이 등록한 기업을 팀 전체가 본다."""
    _login(client, "01000000001")
    r = client.post("/api/companies", json={"name": "샘플애그", "sector_major": "애그테크"})
    assert r.status_code == 200

    _login(client, "01000000002")
    assert "샘플애그" in client.get("/companies").text


def test_anyone_on_the_team_can_edit_a_company(client, db, users):
    """같은 기업을 여러 사람이 서로 다른 투자사에게 소개한다 — 함께 고친다."""
    from app.models import IrCompany

    _login(client, "01000000001")
    cid = client.post("/api/companies", json={"name": "샘플애그"}).json()["id"]

    _login(client, "01000000002")
    r = client.patch(f"/api/companies/{cid}",
                     json={"name": "샘플애그", "one_liner": "다른 사람이 채운 소개"})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(IrCompany, cid).one_liner == "다른 사람이 채운 소개"


def test_company_list_is_the_same_for_everyone(db, users):
    from app.models import IrCompany
    from app.routers.companies import company_rows

    db.add_all([IrCompany(name="샘플애그"), IrCompany(name="샘플메디")])
    db.commit()
    # 사용자를 인자로 받지 않는다 = 누구에게나 같은 목록
    assert len(company_rows(db)) == 2


# --- 내 것: 투자사 관리 현황 · 후속 · IR/미팅 · 주간 업무 ---------------------------

def test_contacts_are_personal(client, db, users):
    from app.models import SheetOwner, VcContact

    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        VcContact(user_id=users["u1"].id, name="내담당", firm="가나벤처스",
                  source_sheet="내 명단", connect_stage="connected"),
    ])
    db.commit()

    _login(client, "01000000002")      # 관리자 아님
    assert "내담당" not in client.get("/contacts?sheet=all").text


def test_followups_are_personal(client, db, users):
    from app.models import SendSequence, VcContact

    contact = VcContact(user_id=users["u1"].id, name="내담당", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add(SendSequence(user_id=users["u1"].id, contact_id=contact.id,
                        stage=1, status="active", next_stage=2,
                        next_due_date=date.today().isoformat()))
    db.commit()

    _login(client, "01000000002")
    assert "내담당" not in client.get("/followups").text


def test_ir_requests_are_personal(client, db, users):
    from app.models import IrRequest, VcContact

    contact = VcContact(user_id=users["u1"].id, name="내담당", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add(IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                     company_name="남의요청기업", requested_at=date.today().isoformat()))
    db.commit()

    _login(client, "01000000002")
    body = client.get("/ir").text
    assert "남의요청기업" not in body
    assert "내담당" not in body


def test_weekly_tasks_are_personal(client, db, users):
    from app.models import WeeklyTask
    from app.services import weekly

    db.add(WeeklyTask(user_id=users["u1"].id,
                      week_start=weekly.week_start().isoformat(),
                      title="내 업무입니다"))
    db.commit()

    _login(client, "01000000002")
    assert "내 업무입니다" not in client.get("/todo").text


def test_sending_to_someone_elses_contact_is_blocked(client, db, users):
    """남의 담당 투자사에 실수로 보내면 안 된다."""
    from app.models import IrCompany, VcContact

    company = IrCompany(name="샘플애그", sector_major="애그테크", revenue_recent=10)
    other = VcContact(user_id=users["u1"].id, name="남담당", firm="가나벤처스",
                      kakao_room_name="남담당 방", connect_stage="connected")
    db.add_all([company, other])
    db.commit()

    _login(client, "01000000002")
    r = client.post("/api/deals/send", json={
        "company_ids": [company.id], "contact_ids": [other.id]})
    assert r.status_code == 404
