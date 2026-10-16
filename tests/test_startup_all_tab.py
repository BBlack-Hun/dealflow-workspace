"""#22 — 스타트업 메뉴의 `전체` 탭: 전체 개수 + 모든 명단에서 찾기.

사용자 요청: "스타트업 메뉴에 전체 개수 표시, 전체에서 기업 검색(지금은 탭별
검색만)."

정한 것(투자사 관리 현황의 `전체` 와 같은 결):

  1. 범위는 **탭을 세운 그 판정**이다 — 팀원은 자기 명단 전부, 관리자는 팀 전체.
  2. 숫자는 이 화면 명단의 **보이는 줄 수**다(감춘 줄 빼고, 두 명단에 같이 있는
     줄은 한 번). 투자사를 세지 않는다 — 그러면 늘 0이다.
  3. 달마다 늘어나는 칸은 명단마다 달라 **고정 칸만** 세우고, 어느 명단의 줄인지
     `명단` 칸을 하나 더 세운다(고쳐지는 칸이 아니다).
  4. 검색은 그려진 줄만 거른다 — 명단 탭에서는 [전체 명단에서 찾기] 가 그 검색어를
     들고 `전체` 로 간다(`?q=`).
  5. 투자사 관리 현황의 `전체` 는 **한 글자도 안 바뀐다.**

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

LIST_A = "샘플 스타트업 가"
LIST_B = "샘플 스타트업 나"
LIST_C = "샘플 스타트업 다"     # 다른 팀원 명단
VC_LIST = "샘플 투자사 명단"
ADMIN_PHONE = "01000000009"
JS_TEST = Path(__file__).resolve().parent / "js" / "contacts_search_all_test.js"


@pytest.fixture()
def world(db, users):
    from app.models import ContactColumn, SheetOwner, User, VcContact
    from app.services import auth as auth_svc
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    admin = User(name="관리샘플", phone=ADMIN_PHONE, role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    for label, owner in ((LIST_A, u1), (LIST_B, u1), (LIST_C, u2)):
        db.add(SheetOwner(label=label, user_id=owner.id, layout=cc.STARTUP,
                          is_hidden=1))
        # 달 칸은 **명단마다** 다르다 — 이름까지 다르게 둔다.
        db.add(ContactColumn(sheet=label, label=f"{label} 리마인드", position=0))
    db.add(SheetOwner(label=VC_LIST, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0))
    db.flush()

    def add(owner, sheet, firm, hidden=0):
        db.add(VcContact(user_id=owner.id, source_sheet=sheet, name="대표",
                         firm=firm, is_hidden=hidden,
                         notes=cc.dump_notes({"contract": "미계약"})))

    add(u1, LIST_A, "샘플가기업")
    add(u1, LIST_A, "샘플가기업둘")
    add(u1, LIST_B, "샘플나기업")
    add(u1, LIST_B, "샘플나감춘기업", hidden=1)
    add(u2, LIST_C, "샘플다기업")
    add(u1, VC_LIST, "샘플투자사")
    db.commit()
    return {"admin": admin}


def _login(phone):
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    r = c.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
               follow_redirects=False)
    assert r.status_code == 303
    return c


def _tabs(html):
    return re.search(r'<nav class="sheet-tabs">.*?</nav>', html, re.S).group(0)


def _firms(html):
    return set(re.findall(r'data-field="firm"[^>]*>([^<]*)<', html))


def _thead(html):
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    cells = re.findall(r"<th\b[^>]*>(.*?)</th>", m.group(1), re.S)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells]


# ── 1. 범위와 숫자 ─────────────────────────────────────────────────────────────

def test_a_member_sees_all_of_their_own_lists(world):
    html = _login("01000000001").get("/startup?sheet=all").text
    tabs = _tabs(html)
    # `전체` 가 눌려 있고, 숫자는 내 두 명단의 보이는 줄(감춘 줄 빼고 3).
    assert re.search(r'class="sheet-tab active" href="/startup\?sheet=all"[^>]*>\s*전체 <span>3</span>',
                     tabs), tabs
    assert _firms(html) == {"샘플가기업", "샘플가기업둘", "샘플나기업"}, _firms(html)
    # 남의 명단 · 투자사 명단 · 감춘 줄은 안 선다.
    assert "샘플다기업" not in html and "샘플투자사" not in html
    assert "샘플나감춘기업" not in _firms(html)


def test_an_admin_sees_the_whole_team(world):
    html = _login(ADMIN_PHONE).get("/startup?sheet=all").text
    assert re.search(r'href="/startup\?sheet=all"[^>]*>\s*전체 <span>4</span>', _tabs(html))
    assert _firms(html) == {"샘플가기업", "샘플가기업둘", "샘플나기업", "샘플다기업"}
    assert "팀 전체" in html


def test_the_all_tab_stands_on_every_tab_with_the_same_count(world):
    """명단 탭을 보고 있어도 `전체` 가 서고 숫자가 같다 — 눌렀을 때 나올 수다."""
    html = _login("01000000001").get(f"/startup?sheet={quote(LIST_A)}").text
    tabs = _tabs(html)
    assert re.search(r'<a class="sheet-tab " href="/startup\?sheet=all"[^>]*>\s*전체 <span>3</span>',
                     tabs), tabs


def test_opening_the_menu_still_opens_my_list(world):
    """기본은 그대로 **내 명단**이다 — `전체` 는 일부러 누르는 자리다."""
    html = _login("01000000001").get("/startup").text
    assert re.search(r'class="sheet-tab active[^"]*"\s+href="/startup\?sheet=' + re.escape(quote(LIST_A)),
                     html) or re.search(
        r'class="sheet-tab active[^"]*"\s+href="/startup\?sheet=' + re.escape(quote(LIST_B)), html)
    assert "list-view-line" not in html


# ── 2. 칸 ──────────────────────────────────────────────────────────────────────

def test_only_fixed_columns_plus_the_list_column(world):
    html = _login(ADMIN_PHONE).get("/startup?sheet=all").text
    head = _thead(html)
    # 명단마다 다른 달 칸은 안 선다.
    assert not any("리마인드" in h for h in head), head
    # 고정 칸은 그대로 — 기업명 바로 뒤에 `명단`.
    assert head[1] == "기업명" and head[2].startswith("명단"), head
    assert "계약여부" in " ".join(head)
    # 한 줄이 어느 명단인지 — 고쳐지는 칸이 아니다(`data-field` 없음).
    assert re.search(r'<td class="ellipsis muted" title="' + LIST_C + '">' + LIST_C + "</td>", html)
    # 왜 달 칸이 없는지 적는다.
    assert "고정 칸만" in html


def test_the_list_column_can_be_filtered_and_rows_carry_it(world):
    """머리글 필터 선언과 행이 싣는 값이 **같은 목록**에서 나온다."""
    html = _login(ADMIN_PHONE).get("/startup?sheet=all").text
    assert 'data-filters="list_label:명단"' in html
    rows = re.findall(r'data-f-list_label="([^"]*)"', html)
    assert sorted(rows) == sorted([LIST_A, LIST_A, LIST_B, LIST_C]), rows


def test_a_list_tab_keeps_its_month_columns(world):
    """명단 탭은 그대로다 — 그 명단의 달 칸이 서고 `명단` 칸은 없다."""
    html = _login("01000000001").get(f"/startup?sheet={quote(LIST_A)}").text
    head = _thead(html)
    assert any(f"{LIST_A} 리마인드" in h for h in head), head
    assert not any(h.startswith("명단") for h in head), head
    assert "data-f-list_label" not in html


# ── 3. 검색 ────────────────────────────────────────────────────────────────────

def test_a_list_tab_offers_searching_all_lists(world):
    html = _login("01000000001").get(f"/startup?sheet={quote(LIST_A)}").text
    link = re.search(r'<a class="linkbtn" id="search-all"[^>]*>', html)
    assert link, "명단 탭에 [전체 명단에서 찾기] 가 없다"
    assert 'data-base="/startup?sheet=all"' in link.group(0)
    assert " hidden" in link.group(0), "아무것도 안 쳤는데 링크가 떠 있다"


def test_the_all_tab_takes_the_search_word_along(world):
    html = _login("01000000001").get(f"/startup?sheet=all&q={quote('샘플나')}").text
    assert re.search(r'id="vc-search"[^>]*value="샘플나"', html)
    # 이미 전부라 다시 가는 길은 없다.
    assert 'id="search-all"' not in html


def test_the_export_button_is_not_offered_on_the_all_tab(world):
    """명단을 안 실은 내려받기는 투자사 표다 — 기업 명단을 보며 받으면 엉뚱한 파일."""
    c = _login("01000000001")
    assert "엑셀 내려받기" not in c.get("/startup?sheet=all").text
    assert "엑셀 내려받기" in c.get(f"/startup?sheet={quote(LIST_A)}").text


def test_hidden_rows_links_stay_on_the_all_tab(world):
    """감춘 줄 [함께 보기] 를 눌러도 보던 `전체` 에 머문다(빈 `sheet` 면 내 명단으로 튄다)."""
    c = _login("01000000001")
    html = c.get("/startup?sheet=all").text
    assert "감춘 줄 <b>1개</b>" in html
    assert 'href="/startup?sheet=all&hidden=1"' in html
    shown = c.get("/startup?sheet=all&hidden=1").text
    assert "샘플나감춘기업" in _firms(shown)


# ── 4. 투자사 관리 현황은 그대로 ────────────────────────────────────────────────

def test_the_investor_all_tab_is_unchanged(world):
    html = _login("01000000001").get("/contacts?sheet=all").text
    tabs = _tabs(html)
    assert re.search(r'class="sheet-tab active" href="/contacts\?sheet=all">\s*전체 <span>1</span>', tabs), tabs
    assert "list-view-line" not in html and "data-f-list_label" not in html
    assert "엑셀 내려받기" in html
    assert "샘플가기업" not in html


def test_a_screen_without_lists_has_no_all_tab(db, users):
    """명단이 하나도 없으면 모을 것이 없다 — 빈 `전체 0` 을 세우지 않는다."""
    html = _login("01000000002").get("/startup?sheet=all").text
    assert 'href="/startup?sheet=all"' not in _tabs(html)


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_the_search_all_link_follows_what_is_typed():
    r = subprocess.run([shutil.which("node"), str(JS_TEST)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
