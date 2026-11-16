"""명단 탭·머리말의 **글자** — 그림 대신 꼬리표, 기업은 `곳`, 이름 속 숫자와 지금 수.

UX 정리에서 나온 셋을 지킨다.

1. 스타트업 탭의 수가 이름과 안 맞아 보였다 — `A (40) + B (34)` 옆에 `40`.
   계산이 틀린 것이 아니다: 이름은 저장된 글자이고, 옆의 수는 **지금 표에 뜨는
   줄(감춘 줄 빼고)** 이다. 그래서 단위(`곳`)를 붙이고, 감춘 줄이 있으면 그 수를
   옆에 적어 두 수가 어디서 갈리는지 보이게 한다.
2. 탭의 꼬리표는 그림(◇ · 🚫 · ✉)이 아니라 글자(`담당 없음` · `제외` · `딜소개`)다.
   `제외`(투자사로 세지 않는 명단)와 흐린 탭은 **투자사 화면에서만** — 스타트업
   명단은 전부 그 값이라 탭마다 붙으면 막힌 명단처럼 읽힌다.
3. 머리말의 수 단위는 화면이 정한다 — 기업은 `곳`, 사람은 `명`.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

STARTUP_LIST = "샘플 스타트업 다 (3) + 라 (2)"   # 이름 속 수는 지금 줄 수가 아니다
DEAL_LIST = "샘플 투자사 마"
OFF_LIST = "샘플 투자사 바"
POOL_LIST = "샘플 투자사 풀"
ADMIN_PHONE = "01000000009"


@pytest.fixture()
def world(db, users):
    from app.models import SheetOwner, User, VcContact
    from app.services import auth as auth_svc
    from app.services import contact_columns as cc

    u1 = users["u1"]
    db.add(User(name="관리샘플", phone=ADMIN_PHONE, role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.add(SheetOwner(label=STARTUP_LIST, user_id=u1.id, layout=cc.STARTUP,
                      is_hidden=1))
    db.add(SheetOwner(label=DEAL_LIST, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0))
    db.add(SheetOwner(label=OFF_LIST, user_id=u1.id, layout=cc.INVESTOR, is_hidden=1))
    db.add(SheetOwner(label=POOL_LIST, user_id=None, layout=cc.INVESTOR, is_hidden=0))
    db.flush()

    def add(sheet, name, hidden=0):
        db.add(VcContact(user_id=u1.id, source_sheet=sheet, name=name,
                         firm=f"{name}상사", is_hidden=hidden))

    # 스타트업 명단: 보이는 줄 2 · 감춘 줄 1 — 이름 속 (3)·(2) 와는 상관없다.
    add(STARTUP_LIST, "기업하나")
    add(STARTUP_LIST, "기업둘")
    add(STARTUP_LIST, "기업셋", hidden=1)
    add(DEAL_LIST, "투자하나")
    add(OFF_LIST, "투자둘")
    add(POOL_LIST, "투자셋")
    db.commit()


def _login(phone):
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    r = c.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
               follow_redirects=False)
    assert r.status_code == 303
    return c


def _tab(html: str, label: str) -> str:
    """그 명단 탭(`<a>…</a>`) 하나."""
    nav = re.search(r'<nav class="sheet-tabs">(.*?)</nav>', html, re.S).group(1)
    m = re.search(r'(<a class="sheet-tab[^"]*"\s+href="/\w+\?sheet='
                  + re.escape(quote(label)) + r'".*?</a>)', nav, re.S)
    assert m, f"{label} 탭이 없다: {nav}"
    return m.group(1)


def test_startup_tab_names_its_unit_and_the_hidden_rows(world):
    """이름 속 수와 옆의 수가 갈리는 까닭(감춘 줄)이 탭에 보인다."""
    html = _login("01000000001").get(f"/startup?sheet={quote(STARTUP_LIST)}").text
    tab = _tab(html, STARTUP_LIST)
    # 이름은 저장된 글자 그대로, 수는 지금 표에 뜨는 줄 + 감춘 줄.
    assert (f'{STARTUP_LIST} <span data-testid="tab-counts">2곳 · 감춘 줄 1개</span>'
            in tab), tab
    # 머리말 수도 기업 단위다(`기업 2 / 2명` 이 아니라).
    assert re.search(r'기업 <b data-unit="곳" data-filter-count>2 / 2곳</b>', html), html


def test_startup_tab_counts_hidden_rows_when_they_are_shown(world):
    """[감춘 줄도 보기] 로 연 탭은 표에 감춘 줄도 뜬다 — 수에 들고, 따로 안 적는다."""
    html = _login("01000000001").get(
        f"/startup?sheet={quote(STARTUP_LIST)}&hidden=1").text
    tab = _tab(html, STARTUP_LIST)
    assert '<span data-testid="tab-counts">3곳</span>' in tab, tab
    line = re.search(r'<p class="hint hidden-rows-line">(.*?)</p>', html, re.S).group(1)
    assert "다시 감추기" in line and "감춘 줄도 보기" not in line, line   # 이미 함께 보고 있다


def test_startup_tabs_do_not_wear_the_excluded_tag(world):
    """스타트업 명단은 전부 투자사로 안 세는 명단이다 — 꼬리표·흐림을 안 단다."""
    html = _login("01000000001").get(f"/startup?sheet={quote(STARTUP_LIST)}").text
    tab = _tab(html, STARTUP_LIST)
    assert "muted-tab" not in tab, tab
    assert ">제외</span>" not in tab, tab
    assert "투자사로 세지 않는 명단" in tab, "말풍선의 뜻까지 지웠다"


def test_investor_tabs_wear_word_tags(world):
    """꼬리표는 글자다 — `딜소개` · `제외` · `담당 없음`. 그림 하나로 뜻을 대신하지 않는다."""
    html = _login(ADMIN_PHONE).get(f"/contacts?sheet={quote(DEAL_LIST)}").text
    deal, off, pool = (_tab(html, x) for x in (DEAL_LIST, OFF_LIST, POOL_LIST))
    assert ">딜소개</span>" in deal, deal
    assert ">제외</span>" in off and "muted-tab" in off, off
    assert ">담당 없음</span>" in pool, pool
    for tab in (deal, off, pool):
        for picture in ("◇", "🚫", "✉"):
            assert picture not in tab, tab
    # 투자사 화면은 사람 단위, 탭 수는 `카톡방 확인` 까지.
    assert re.search(r'담당자 <b data-unit="명" data-filter-count>\d+ / \d+명</b>', html)
    assert re.search(r'<span data-testid="tab-counts">1명 / 카톡방 확인 0</span>', deal), deal
