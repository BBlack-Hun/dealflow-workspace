"""#29 — 투자사 관리 현황 `전체` 의 숫자: 팀원에게는 `내 명단 N명 · 팀 전체 M명`.

운영 숫자: 관리자가 보는 팀 전체(`sheet_owner.managed(team_wide=True)`)가 766,
팀원 한 사람의 명단이 248. 팀원 화면의 `전체` 에는 248 이 떠 있었고, 사용자는
거기서 766("전체 인원")을 기대했다.

사용자가 정했다(2026-10-16):

  1. 팀원은 둘 다 본다 — `내 명단 N명 · 팀 전체 M명`.
  2. 관리자는 지금처럼 팀 전체 수 하나다.
  3. 표의 줄은 바뀌지 않는다(팀원의 `전체` 는 여전히 자기 명단).
  4. M 은 관리자가 보는 그 판정(`managed`)을 그대로 지난다.

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

MY_LIST = "샘플 투자사 가"
OTHER_LIST = "샘플 투자사 나"
OFF_LIST = "샘플 투자사 아님"        # 투자사로 세지 않는 명단
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
    db.add(SheetOwner(label=MY_LIST, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0))
    db.add(SheetOwner(label=OTHER_LIST, user_id=u2.id, layout=cc.INVESTOR, is_hidden=0))
    db.add(SheetOwner(label=OFF_LIST, user_id=u2.id, layout=cc.INVESTOR, is_hidden=1))
    db.add(SheetOwner(label=STARTUP_LIST, user_id=u1.id, layout=cc.STARTUP,
                      is_hidden=1))
    db.flush()

    def add(owner, sheet, name, firm, hidden=0):
        db.add(VcContact(user_id=owner.id, source_sheet=sheet, name=name,
                         firm=firm, is_hidden=hidden))

    # 내 명단 2명
    add(u1, MY_LIST, "홍길동", "가나벤처스")
    add(u1, MY_LIST, "김서연", "마바벤처스")
    # 남의 명단 3명 + 감춘 줄 1(안 센다)
    add(u2, OTHER_LIST, "박준호", "사아파트너스")
    add(u2, OTHER_LIST, "이도윤", "자차벤처스")
    add(u2, OTHER_LIST, "최하린", "카타인베스트")
    add(u2, OTHER_LIST, "정감춤", "파하벤처스", hidden=1)
    # 투자사로 세지 않는 명단(안 센다)
    add(u2, OFF_LIST, "한아님", "샘플상사")
    # 스타트업 명단(투자사가 아니다 — 안 센다)
    add(u1, STARTUP_LIST, "대표", "샘플가기업")
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


def _all_tab(html: str) -> str:
    found = re.search(r'<a class="sheet-tab[^"]*" href="/contacts\?sheet=all".*?</a>',
                      html, re.S)
    assert found, "투자사 관리 현황에 `전체` 탭이 없다"
    return found.group(0)


def test_a_member_sees_both_counts(world):
    tab = _all_tab(_login("01000000001").get("/contacts").text)
    assert "내 명단 2명 · 팀 전체 5명" in tab, tab
    assert "표에는 내 명단이 보입니다" in tab, "무엇이 표에 뜨는지 풍선말이 없다"


def test_the_team_total_is_the_admins_number(db, world):
    """팀원이 보는 M 과 관리자가 보는 수가 **한 명도** 안 갈린다 — 같은 판정이다."""
    from app.services import sheet_owner

    admin_tab = _all_tab(_login(ADMIN_PHONE).get("/contacts?sheet=all").text)
    said = re.search(r"전체 <span>(\d+)</span>", admin_tab)
    assert said, admin_tab
    assert int(said.group(1)) == 5
    assert sheet_owner.team_total(db) == 5
    assert sheet_owner.team_total(db) == len(
        sheet_owner.managed(db, world["admin"], team_wide=True))


def test_the_admin_keeps_one_number(world):
    tab = _all_tab(_login(ADMIN_PHONE).get("/contacts").text)
    assert "팀 전체" not in tab and "내 명단" not in tab, tab
    assert re.search(r"전체 <span>5</span>", tab), tab


def test_the_members_table_does_not_change(world):
    """숫자만 더 적는다 — 팀원의 `전체` 표에는 여전히 자기 명단만 뜬다."""
    html = _login("01000000001").get("/contacts?sheet=all").text
    assert "홍길동" in html and "김서연" in html
    for other in ("박준호", "이도윤", "최하린"):
        assert other not in html, f"남의 명단 줄({other})이 팀원 표에 섞였다"


def test_the_count_ignores_what_the_admin_does_not_count(db, world):
    """감춘 줄 · 투자사로 세지 않는 명단 · 스타트업 명단은 M 에도 안 든다
    (`investors` 를 그대로 지난다)."""
    from app.services import sheet_owner

    assert sheet_owner.team_total(db) == 5
    tab = _all_tab(_login("01000000002").get("/contacts").text)
    assert "내 명단 3명 · 팀 전체 5명" in tab, tab


def test_a_member_still_gets_only_their_rows(db, world, users):
    """`team_total` 은 **수만** 준다. 팀원이 `team_wide` 를 달라고 해도 줄은
    여전히 자기 것이다 — 권한 판정은 `managed` 한 곳에 그대로 있다."""
    from app.services import sheet_owner

    rows = sheet_owner.managed(db, users["u1"], team_wide=True)
    assert {c.name for c in rows} == {"홍길동", "김서연"}
    assert isinstance(sheet_owner.team_total(db), int)


def test_the_startup_all_tab_is_unchanged(world):
    """스타트업 화면의 `전체` 는 이 화면 명단의 줄 수 하나 그대로다(#22)."""
    html = _login("01000000001").get("/startup?sheet=all").text
    found = re.search(r'href="/startup\?sheet=all"[^>]*>\s*전체 <span>(\d+)</span>', html)
    assert found and found.group(1) == "1", html[:2000]
    assert "팀 전체" not in found.group(0)
