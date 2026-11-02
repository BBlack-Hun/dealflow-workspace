"""i139 메모 칸에 새로 다는 줄 앞에 오늘 날짜 — **어느 칸이 메모인가**는 템플릿이 정한다.

날짜를 붙이는 일은 화면의 편집기가 한다(`static/js/memo_date.js` · tests/js/memo_date_test.js).
여기서는 표시(`data-memo-date`)가 메모 칸에만 서는지를 본다 — 선호 칸 · 소개 문구 · 조사 칸에
서면 날짜가 밖으로 나가는 글이나 짧은 값에 섞인다. 추가 메모 칸은 tests/test_custom_columns.py.

값은 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD


SHEET = "샘플 스타트업 명단"


@pytest.fixture()
def logged(client, db, users):
    from app.models import IrCompany, Meeting, SheetOwner, SourcingContact, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id, layout=cc.STARTUP, is_hidden=1))
    who = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역", firm="가나벤처스",
                    memo="처음 메모", round_size="10~30억", tips_note="O")
    db.add_all([who,
                IrCompany(name="샘플애그", one_liner="B2B 농산물", note="TIPS 가능"),
                SourcingContact(bucket="시리즈 A 이상", position=0, name="김철수",
                                firm="다라인베스트", round_size="30억", memo="재연락"),
                VcContact(user_id=users["u1"].id, source_sheet=SHEET, name="대표",
                          firm="샘플스타트업", memo="통화함")])
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=who.id, company_name="샘플애그",
                   kind="first", scheduled_at="2026-08-10", status="done",
                   outcome="review", note="후속 검토"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _tags(html, field):
    found = re.findall(r'<div class="cell[^"]*" data-field="%s"[^>]*>' % field, html)
    assert found, f"{field} 칸이 안 그려졌다"
    return found


@pytest.mark.parametrize("url, memo, others", [
    ("/contacts", ["memo"], ["round_size", "owned_funds", "tips_note", "sourcing_note"]),
    ("/companies", ["note"], ["one_liner", "business_desc"]),
    ("/sourcing", ["memo"], ["round_size"]),
    ("/ir", ["note"], []),
    ("/startup?sheet=" + quote(SHEET), ["memo"], []),
])
def test_메모_칸에만_날짜_표시가_선다(logged, url, memo, others):
    html = logged.get(url).text
    for field in memo:
        assert all("data-memo-date" in t for t in _tags(html, field)), (url, field)
    for field in others:
        assert not any("data-memo-date" in t for t in _tags(html, field)), (url, field)


def test_화면마다_날짜를_붙이는_부품이_실린다(logged):
    assert "/static/js/memo_date.js" in logged.get("/contacts").text
