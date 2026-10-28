"""IR 기업 현황 — 금액 모아 보기 필터(#88 · #90)와 `수정한 팀원`(#89).

  1. 투자유치희망금액은 5 · 10 · 20 · 30 · 40 · 50억 이상, 연도 매출은 10 · 20 · 30 · 50 · 100억
     이상으로 **겹쳐** 든다. 구간 값은 아래로, 못 읽는 글은 빈 칸과 따로 모인다.
  2. 표의 머리글이 그 필터를 세우고 줄이 그 값을 싣는다. 칸을 고치면 응답이 새 값을 준다.
  3. `수정한 팀원` 은 수정 로그의 마지막 수정자 — 그 뒤에 앱이 혼자 고쳤으면 `자동`.

값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플모아테크", raise_target="30억", revenue_recent="12",
                    revenue_2025="1,224백만원", revenue_2024="확인안됨")
    db.add(row)
    db.commit()
    return row


def test_금액_구간은_겹쳐_들고_못_읽는_글은_따로_모인다(company):
    from app.routers.companies import amount_bands

    bands = amount_bands(company)
    assert bands["raise_target"] == "5억 이상|10억 이상|20억 이상|30억 이상"
    assert bands["revenue_recent"] == "10억 이상"
    assert bands["revenue_2025"] == "10억 이상"        # 1,224백만원 = 12.24억
    assert bands["revenue_2024"] == "금액 못 읽음"
    assert bands["revenue_2023"] == ""                 # 빈 칸 — 필터의 `(비어 있음)`

    company.raise_target, company.revenue_recent = "5-10억", "3"
    bands = amount_bands(company)
    assert bands["raise_target"] == "5억 이상"           # 구간은 아래로 센다
    assert bands["revenue_recent"] == "10억 미만"


def test_머리글이_금액_필터를_세우고_줄이_그_값을_싣는다(logged_in, company):
    html = logged_in.get("/companies").text
    assert 'data-filters="raise_target:투자유치희망금액"' in html
    assert 'data-filters="revenue_2025:25년 매출"' in html
    assert 'data-filters="revenue_recent:26년 매출"' in html
    assert 'data-f-raise_target="5억 이상|10억 이상|20억 이상|30억 이상"' in html
    assert 'data-f-revenue_2025="10억 이상"' in html


def test_고치면_응답이_새_필터_값과_고친_팀원을_준다(logged_in, company, users):
    r = logged_in.patch(f"/api/companies/{company.id}", json={"raise_target": "50억"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bands"]["raise_target"].endswith("50억 이상")
    assert data["updated_by"] == users["u1"].name
    assert f">{users['u1'].name}</td>" in logged_in.get("/companies").text


def test_앱이_혼자_고친_것이_마지막이면_자동이다(logged_in, company, db):
    from sqlalchemy import text as sql

    from app.models import IrCompany
    from app.routers.companies import AUTO_EDITOR, last_editors

    assert logged_in.patch(f"/api/companies/{company.id}",
                           json={"raise_target": "40억"}).status_code == 200
    # 사람 없이 줄만 늦게 고쳐진 꼴 — 수정 로그는 그대로, `updated_at` 만 한참 뒤.
    db.execute(sql("UPDATE ir_companies SET updated_at = '2099-01-01T00:00:00+09:00' "
                   "WHERE id = :i"), {"i": company.id})
    db.commit()
    db.expire_all()
    assert last_editors(db, [db.get(IrCompany, company.id)]) == {company.id: AUTO_EDITOR}


def test_로그가_없는_줄은_빈칸이다(db, company):
    from app.routers.companies import last_editors

    assert last_editors(db, [company]) == {}
