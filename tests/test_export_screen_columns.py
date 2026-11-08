"""IR 기업 현황 엑셀 두 벌에 화면 칸이 다 선다(#192 · 11/08 팀원 요청).

「관리자 에서 만 > 엑셀 내려받기 , 지금 화면 내려 받기 > 컬럼 이 보여지게」

두 단추는 이미 관리자(+ 켜 준 계정)에게만 선다(11/01 · 0132). 빠져 있던 것은 **칸**이다.

  · 전체(`엑셀 내려받기`) — 머리글이 옛 이름·차례를 지켜서 대표자명 · 연락처 · 메모처럼
    나중에 화면에 선 칸이 없었다. 옛 칸은 그대로 두고 화면 칸을 **끝에** 붙인다.
  · 지금 화면 — `컨설팅 상태` · `컨설팅 미팅일` 이 화면에는 서는데 파일에는 없었다.
"""
from __future__ import annotations

import io

import pytest

from tests.test_company_tab_order import _head_names


def _sheet(resp):
    from openpyxl import load_workbook

    assert resp.status_code == 200, resp.text
    ws = load_workbook(io.BytesIO(resp.content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    return rows[0], rows[1:]


@pytest.fixture()
def company(db, users, u1_admin):
    from app.models import ConsultingCompany, IrCompany
    from app.services import consulting_sheets as cs

    c = IrCompany(name="샘플화면랩", contact_name="샘플대표", note="샘플 메모",
                  guarantee="샘플 보증", top_deal_kind="핵심")
    db.add(c)
    db.flush()
    db.add(ConsultingCompany(user_id=users["u1"].id, sheet=cs.by_kind(db)[cs.STARTUP].label,
                             company_name=c.name, management="관리 중 : 미팅 완",
                             meeting_at="2026-11-03", ir_company_id=c.id))
    users["u1"].can_view_consulting = 1
    db.commit()
    return c


def test_전체_내려받기는_옛_칸_뒤에_화면_칸을_모두_붙인다(logged_in, company):
    from app.routers.data_io import COMPANY_HEADERS
    from app.services import company_view, revenue_years

    screen = [n for n in _head_names(logged_in.get("/companies").text) if n]
    assert "컨설팅 상태" in screen
    head, rows = _sheet(logged_in.get("/api/export/companies.xlsx"))
    # 받아 쓰던 수식이 머리글 자리로 칸을 찾는다 — 옛 칸은 한 칸도 안 밀린다.
    assert head[:len(COMPANY_HEADERS)] == COMPANY_HEADERS
    # 화면 칸은 이름 그대로 있거나, 같은 값을 싣는 옛 칸이 있다(`IN_FULL`).
    same = set(company_view.IN_FULL) | {
        label for f, label in revenue_years.columns() if f in company_view.AMOUNTS_IN_FULL}
    assert [n for n in screen if n not in head and n not in same] == []
    assert set(company_view.IN_FULL.values()) - {None} <= set(COMPANY_HEADERS)
    assert set(company_view.AMOUNTS_IN_FULL.values()) <= set(COMPANY_HEADERS)
    by = dict(zip(head, rows[0]))
    assert (by["대표자명"], by["메모"], by["정책자금"], by["핵심/TOP Deal"]) == (
        "샘플대표", "샘플 메모", "샘플 보증", "핵심")
    assert (by["컨설팅 상태"], by["컨설팅 미팅일"]) == ("관리 중", "2026-11-03")


def test_지금_화면_내려받기에_컨설팅_칸이_화면_자리에_선다(logged_in, company):
    head, rows = _sheet(logged_in.get("/api/export/companies-view.xlsx"))
    at = head.index("핵심/TOP Deal") + 1
    assert head[at:at + 2] == ["컨설팅 상태", "컨설팅 미팅일"]
    assert rows[0][at:at + 2] == ["관리 중", "2026-11-03"]


def test_컨설팅_칸은_그_화면을_볼_수_있는_계정에게만(logged_in, db, users, company):
    users["u1"].can_view_consulting = 0
    db.commit()
    assert "컨설팅 상태" not in logged_in.get("/companies").text
    for url in ("/api/export/companies.xlsx", "/api/export/companies-view.xlsx"):
        head, _rows = _sheet(logged_in.get(url))
        assert "컨설팅 상태" not in head and "대표자명" in head, url
