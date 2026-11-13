"""투자사 관리 현황 탭마다 `총원 / 확인` (11/13 사용자 요청).

  "투자사 관리 현황에 각 탭별로 총원/확인된 카톡방 연결 수가 같이 나왔으면"

- 총원: 그 탭을 눌렀을 때 **표에 뜨는 줄 수**. 감춘 줄은 빠지고, [함께 보기]
  (`?hidden=1`)로 연 탭은 표에 뜨므로 같이 센다. 탭 이름에 박힌 `119명` 은
  가져올 때 붙은 글자라 이 수와 다르다.
- 확인: 그중 방 확인이 `확인됨` 으로 끝난 줄(`dashboard.room_confirmed`).
  미확인 · 방 없음 · 어느 방인지 모름 · 방 미등록 · 메일 채널은 안 센다.
- `전체` 탭도 같은 판정 — 투자사로 세는 사람(`sheet_owner.investors`) 기준,
  두 명단에 같이 있는 사람은 한 번만.
- 스타트업 화면은 방 확인의 뜻이 달라 지금처럼 수 하나다.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

LIST_A = "샘플 투자사 가 119명"     # 이름에 박힌 수(119)는 실제 줄 수가 아니다
LIST_B = "샘플 투자사 나"
OFF_LIST = "샘플 투자사 아님"        # 투자사로 세지 않는 명단 — 탭은 선다
STARTUP_LIST = "샘플 스타트업 가"
ADMIN_PHONE = "01000000009"


@pytest.fixture()
def world(db, users):
    from app.models import SheetOwner, User, VcContact
    from app.services import auth as auth_svc
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    admin = User(name="관리샘플", phone=ADMIN_PHONE, role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.add(SheetOwner(label=LIST_A, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0))
    db.add(SheetOwner(label=LIST_B, user_id=u2.id, layout=cc.INVESTOR, is_hidden=0))
    db.add(SheetOwner(label=OFF_LIST, user_id=u2.id, layout=cc.INVESTOR, is_hidden=1))
    db.add(SheetOwner(label=STARTUP_LIST, user_id=u1.id, layout=cc.STARTUP,
                      is_hidden=1))
    db.flush()

    def add(owner, sheet, name, *, room="샘플방", state="verified", kakao=1,
            email=0, hidden=0):
        db.add(VcContact(user_id=owner.id, source_sheet=sheet, name=name,
                         firm=f"{name}벤처스", channel_kakao=kakao,
                         channel_email=email, kakao_room_name=room,
                         room_verified=state, is_hidden=hidden))

    # 가 명단: 표에 6줄(감춘 줄 1 빼고), 확인됨 2(둘 다 명단에 있는 사람 포함)
    add(u1, LIST_A, "확인가")                                  # 확인됨
    add(u1, LIST_A, "미확인가", state="unverified")            # 미확인
    add(u1, LIST_A, "못찾가", state="not_found")               # 방 없음
    add(u1, LIST_A, "미등록가", room="")                       # 방 미등록(값은 verified)
    add(u1, LIST_A, "메일가", kakao=0, email=1)                # 메일 채널(값은 verified)
    add(u1, LIST_A, "감춤가", hidden=1)                        # 감춘 줄 — 확인됨
    add(u1, f"{LIST_A},{LIST_B}", "겹침")                     # 두 명단 — 확인됨
    # 나 명단: 겹침 + 2줄
    add(u2, LIST_B, "모름나", state="ambiguous")               # 어느 방인지 모름
    add(u2, LIST_B, "확인나")                                  # 확인됨
    # 투자사로 세지 않는 명단 — 제 탭에서는 보이고, `전체` 에는 안 든다
    add(u2, OFF_LIST, "아님다")                                # 확인됨
    # 스타트업 명단
    add(u1, STARTUP_LIST, "대표")
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


def _tab_counts(html: str) -> dict:
    """탭 이름 → (총원, 확인). 탭 안의 `N명 / 확인 K` 를 읽는다."""
    nav = re.search(r'<nav class="sheet-tabs">(.*?)</nav>', html, re.S).group(1)
    out = {}
    for href, body in re.findall(
            r'<a class="sheet-tab[^"]*"\s+href="/contacts\?sheet=([^"]+)"[^>]*>(.*?)</a>',
            nav, re.S):
        m = re.search(r'data-testid="(?:tab|all-tab)-counts">(?:내 명단 )?(\d+)명 / 확인 (\d+)',
                      body)
        assert m, f"탭에 `총원 / 확인` 이 없다: {body}"
        out[href] = (int(m.group(1)), int(m.group(2)))
    return out


def _table(html: str):
    """표에 뜬 줄 수와 그중 방 `확인됨` 인 줄 수."""
    rows = re.findall(r'<tr class="data-row[^"]*" data-id="\d+".*?>', html, re.S)
    ok = re.findall(r'<tr class="data-row[^"]*" data-id="\d+"[^>]*?data-f-room="확인됨"',
                    html, re.S)
    return len(rows), len(ok)


def _key(label):
    from urllib.parse import quote

    return quote(label)


def test_each_tab_shows_total_and_confirmed(world):
    tabs = _tab_counts(_login(ADMIN_PHONE).get("/contacts?sheet=all").text)
    assert tabs[_key(LIST_A)] == (6, 2), tabs   # 감춘 줄 빠짐 · 미확인/방 없음/미등록/메일 빠짐
    assert tabs[_key(LIST_B)] == (3, 2), tabs   # 겹침 · 확인나 / 모름나 빠짐
    assert tabs[_key(OFF_LIST)] == (1, 1), tabs  # 투자사로 안 세도 제 탭에는 뜬다
    # `전체` — 투자사로 세는 사람 한 번씩: 가 6 + 나 2(겹침은 한 번), 아님 명단 빠짐
    assert tabs["all"] == (8, 3), tabs


@pytest.mark.parametrize("label", [LIST_A, LIST_B, OFF_LIST])
def test_the_tab_number_is_the_table(world, label):
    """탭에 적힌 수 = 그 탭을 눌렀을 때 표에 뜨는 줄 · 그중 `확인됨` 줄."""
    html = _login(ADMIN_PHONE).get(f"/contacts?sheet={_key(label)}").text
    assert _tab_counts(html)[_key(label)] == _table(html)


def test_the_all_tab_number_is_the_table(world):
    html = _login(ADMIN_PHONE).get("/contacts?sheet=all").text
    assert _tab_counts(html)["all"] == _table(html) == (8, 3)


def test_showing_hidden_rows_counts_them_on_that_tab_only(world):
    """[함께 보기] 로 연 탭은 표에 감춘 줄이 뜨므로 수에도 든다. 다른 탭 링크는
    `hidden` 을 안 실어 누르면 감춘 줄이 빠진 표라, 그 탭 수는 그대로다."""
    html = _login(ADMIN_PHONE).get(f"/contacts?sheet={_key(LIST_A)}&hidden=1").text
    tabs = _tab_counts(html)
    assert tabs[_key(LIST_A)] == (7, 3) == _table(html)
    assert tabs[_key(LIST_B)] == (3, 2)


def test_a_member_sees_confirmed_for_their_own_list(world):
    """팀원의 `전체` 는 내 명단이 표다 — `/ 확인` 도 내 명단 몫이다."""
    html = _login("01000000001").get("/contacts?sheet=all").text
    tab = re.search(r'data-testid="all-tab-counts">([^<]*)<', html).group(1)
    assert tab == "내 명단 6명 / 확인 2 · 팀 전체 8명", tab
    assert _table(html) == (6, 2)


def test_the_startup_tabs_keep_one_number(world):
    """스타트업 화면의 `카톡방 확인` 은 대표와의 방이라 뜻이 다르다 — 수 하나 그대로."""
    html = _login("01000000001").get(f"/startup?sheet={_key(STARTUP_LIST)}").text
    nav = re.search(r'<nav class="sheet-tabs">(.*?)</nav>', html, re.S).group(1)
    assert "확인 " not in nav, nav
    assert "샘플 스타트업 가 <span>1</span>" in nav, nav


def test_counting_does_not_ask_the_db_per_tab(db, users):
    """탭이 늘어도 세는 데 드는 질의 수는 같다 — 한 번 읽어 묶어 센다."""
    from sqlalchemy import event

    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc
    from app.services import sheet_owner

    def queries(n_tabs):
        db.query(VcContact).delete()
        db.query(SheetOwner).delete()
        for i in range(n_tabs):
            label = f"샘플 명단 {n_tabs}-{i}"
            db.add(SheetOwner(label=label, user_id=users["u1"].id, layout=cc.INVESTOR))
            for j in range(3):
                db.add(VcContact(user_id=users["u1"].id, source_sheet=label,
                                 name=f"샘플{i}-{j}", channel_kakao=1,
                                 kakao_room_name="샘플방", room_verified="verified"))
        db.commit()
        contacts = sheet_owner.managed(db, users["u1"], include_hidden=True)
        seen = []

        def count(*_a, **_k):
            seen.append(1)

        event.listen(db.bind, "before_cursor_execute", count)
        try:
            tabs = sheet_owner.sheet_rows(db, contacts)
        finally:
            event.remove(db.bind, "before_cursor_execute", count)
        assert len(tabs) == n_tabs and all(t["confirmed"] == 3 for t in tabs)
        return len(seen)

    assert queries(2) == queries(12)
