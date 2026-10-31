"""#84 IR 기업 현황 탭에 **대표자명 · 연락처 · 이메일 · 기업 한줄 소개** 네 칸.

10/28 사용자 '추천대로': 스타트업DB 탭과 같은 표(`ir_companies`)라 값은 이미 있다 —
화면 칸만 스타트업DB 차례 그대로 세운다. 지금 화면 내려받기 · 관리자 추가 칸의 기준점도
같은 차례다. #105 · #106 부터 `수신일` 과 이 넷 사이에 `수정한 날짜` · `수정한 팀원` 이 선다.
이름 · 번호는 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import io

import pytest

from tests.conftest import DEMO_PASSWORD
from tests.test_company_tab_order import _head_names

FOUR = ["대표자명", "연락처", "이메일", "기업 한줄 소개"]
AFTER_RECEIVED = ["수신일", "수정한 날짜", "수정한 팀원", *FOUR]


@pytest.fixture()
def logged(client, users, db):
    from app.models import IrCompany

    db.add(IrCompany(name="샘플가온헬스", received_at="2026-09-01", contact_name="김샘플",
                     contact_phone="010-0000-1234", contact_email="ceo@example.com",
                     business_desc="샘플 헬스케어 플랫폼"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def test_the_ir_tab_shows_the_four_after_received_date(logged):
    html = logged.get("/companies").text
    names = _head_names(html)
    at = names.index("수신일")
    assert names[at:at + 7] == AFTER_RECEIVED, names
    body = html.split("<tbody>", 1)[1]
    for field, value in (("contact_name", "김샘플"), ("contact_phone", "010-0000-1234"),
                         ("contact_email", "ceo@example.com"),
                         ("business_desc", "샘플 헬스케어 플랫폼")):
        assert f'data-field="{field}"' in body and value in body, field


def test_the_view_export_and_anchors_follow(logged):
    import openpyxl

    from app.services import custom_columns

    resp = logged.get("/api/export/companies-view.xlsx")
    assert resp.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    head, row = [[c.value for c in r] for r in ws.iter_rows(max_row=2)]
    assert head[2:9] == AFTER_RECEIVED
    assert row[5:9] == ["김샘플", "010-0000-1234", "ceo@example.com", "샘플 헬스케어 플랫폼"]
    ir_tab = custom_columns.anchor_groups("companies")["IR 기업 현황"]
    assert list(ir_tab[1:8]) == AFTER_RECEIVED
