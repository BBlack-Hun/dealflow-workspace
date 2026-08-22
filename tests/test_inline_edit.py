"""표에서 눌러 바로 고치기 — 한 칸만 보내도 저장되는가.

투자컨설턴트 현황에서만 쓰던 조작을 투자사 DB · 스타트업 관리로 넓혔다.
칸 하나를 고칠 때 **다른 값까지 같이 보내야 한다면** 쓸 수 없는 기능이다.
실제로 처음엔 `name` 이 필수라 매출 한 칸을 고치는 데 422 가 났다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged_in(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플애그", sector_major="애그테크",
                    one_liner="B2B 농산물 선도거래", revenue_recent=1200)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def contact(db, users):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                    firm="가나벤처스", memo="처음 메모")
    db.add(row)
    db.commit()
    return row


# --- 스타트업 관리 -----------------------------------------------------------

def test_one_field_is_enough(logged_in, db, company):
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"revenue_recent": 3400})
    assert r.status_code == 200, r.text
    db.refresh(company)
    assert company.revenue_recent == 3400
    assert company.name == "샘플애그", "이름을 안 보냈다고 지워지면 안 된다"


def test_zero_is_not_empty(logged_in, db, company):
    """'매출 0' 과 '아직 안 적음'은 다르다."""
    logged_in.patch(f"/api/companies/{company.id}", json={"revenue_recent": 0})
    db.refresh(company)
    assert company.revenue_recent == 0

    logged_in.patch(f"/api/companies/{company.id}", json={"revenue_recent": None})
    db.refresh(company)
    assert company.revenue_recent is None


def test_response_says_whether_it_became_introducible(logged_in, db, company):
    """한 칸을 채우면 '소개 가능'이 바뀔 수 있다. 새로고침해야 보이면 안 된다."""
    body = logged_in.patch(f"/api/companies/{company.id}",
                           json={"one_liner": "고침"}).json()
    assert body["introducible"] is False
    assert "없음" in body["blocked_reason"], "무엇이 모자란지 말해 줘야 채울 수 있다"

    for field, value in [("funding_total", 20), ("raise_target", 700),
                         ("pre_value", 3000), ("competitiveness", "특허 6건"),
                         ("ir_drive_url", "https://drive.google.com/file/d/x/view"),
                         ("summary_status", "done")]:
        body = logged_in.patch(f"/api/companies/{company.id}",
                               json={field: value}).json()
    assert body["introducible"] is True, body["blocked_reason"]


def test_creating_still_needs_a_name(logged_in):
    assert logged_in.post("/api/companies", json={"sector_major": "AI"}).status_code == 400


# --- 투자사 DB ---------------------------------------------------------------

def test_memo_only(logged_in, db, contact):
    r = logged_in.patch(f"/api/contacts/{contact.id}", json={"memo": "고친 메모"})
    assert r.status_code == 200, r.text
    db.refresh(contact)
    assert contact.memo == "고친 메모"
    assert contact.name == "홍길동"


def test_changing_the_room_name_clears_the_check(logged_in, db, contact):
    """방 이름이 바뀌면 이전 확인 결과는 더 이상 근거가 아니다."""
    contact.kakao_room_name = "예전 방"
    contact.room_verified = "verified"
    db.commit()

    logged_in.patch(f"/api/contacts/{contact.id}",
                    json={"kakao_room_name": "새 방 이름"})
    db.refresh(contact)
    assert contact.kakao_room_name == "새 방 이름"
    assert contact.room_verified == "unverified"


def test_cannot_touch_someone_elses(client, db, users, contact):
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert client.patch(f"/api/contacts/{contact.id}",
                        json={"memo": "남의 것"}).status_code == 404


# --- 화면에 붙어 있는가 ------------------------------------------------------

def test_tables_are_wired(logged_in, company, contact):
    companies = logged_in.get("/companies").text
    assert 'data-inline-url="/api/companies"' in companies
    assert 'data-field="revenue_recent" data-type="number"' in companies
    assert "inline_edit.js" in companies

    contacts = logged_in.get("/contacts").text
    assert 'data-inline-url="/api/contacts"' in contacts
    assert 'data-field="memo"' in contacts
    assert "inline_edit.js" in contacts
