"""IR 기업현황 엑셀 내려받기 — 관리자 + **관리자가 켜 준 계정**만 (0132).

11/01 에 두 길(`/api/export/companies.xlsx` · `companies-view.xlsx`)을 관리자만으로
좁혔다. 그 원칙은 두고 팀 현황에서 켠 일반 팀원만 예외로 연다
(`users.can_export_companies` → `deps.may_export_companies`). 지키는 것:

1. 칸이 꺼진 팀원은 두 길 모두 지금처럼 403 이고, 단추도 안 보인다
2. 켠 팀원은 둘 다 받고 단추도 보인다 — 화면과 라우터가 같은 판정을 읽는다
3. 관리자는 그대로 받는다
4. 켜고 끄는 것은 관리자만, 바꾸면 수정 기록에 남는다
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD

ROUTES = ("/api/export/companies.xlsx", "/api/export/companies-view.xlsx")
BUTTON = 'href="/api/export/companies.xlsx"'


def _allow(db, user, on=True):
    user.can_export_companies = 1 if on else 0
    db.commit()


@pytest.fixture()
def admin(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    boss = User(name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(boss)
    db.commit()
    return boss


@pytest.fixture()
def as_admin(db, admin):
    """관리자 세션 — `logged_in`(u1) 과 따로 연다(한 창에 다시 로그인하면 덮인다)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        c.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
        yield c


def test_a_member_without_the_switch_is_refused_as_before(logged_in):
    for path in ROUTES:
        assert logged_in.get(path).status_code == 403, path
    assert BUTTON not in logged_in.get("/companies").text


def test_a_member_with_the_switch_gets_both_files_and_the_buttons(logged_in, db, users):
    _allow(db, users["u1"])
    for path in ROUTES:
        assert logged_in.get(path).status_code == 200, path
    page = logged_in.get("/companies").text
    assert BUTTON in page and 'id="co-export-view"' in page


def test_an_admin_still_gets_both(logged_in, u1_admin):
    for path in ROUTES:
        assert logged_in.get(path).status_code == 200, path
    assert BUTTON in logged_in.get("/companies").text


def test_the_button_follows_the_same_judgment_as_the_route(logged_in, db, users):
    """★ 단추가 보이는데 403 이거나, 안 보이는데 주소로 받히는 상태가 없다."""
    for on in (True, False, True):
        _allow(db, users["u1"], on=on)
        shown = BUTTON in logged_in.get("/companies").text
        ok = logged_in.get(ROUTES[0]).status_code == 200
        assert shown is on and ok is on


def test_only_an_admin_can_switch_it(logged_in, db, users):
    r = logged_in.post(f"/team/members/{users['u1'].id}/export-companies",
                       follow_redirects=False)
    assert r.status_code == 403
    db.expire_all()
    assert users["u1"].can_export_companies == 0


def test_switching_it_is_on_the_team_screen_and_written_down(as_admin, db, users):
    from app.models import EditLog

    page = as_admin.get("/team").text
    assert f"/team/members/{users['u1'].id}/export-companies" in page
    assert "엑셀 내려받기" in page

    r = as_admin.post(f"/team/members/{users['u1'].id}/export-companies",
                      follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert users["u1"].can_export_companies == 1

    logs = [x for x in db.query(EditLog).all() if x.table_name == "users"]
    assert logs, "수정 기록에 안 남았다"
    changes = {c["field"]: c for c in json.loads(logs[-1].changes_json)}
    assert "can_export_companies" in changes
    assert logs[-1].target_user_id == users["u1"].id


def test_an_admin_row_has_no_button(as_admin, admin):
    """관리자는 칸과 무관하게 늘 받는다 — 눌러도 안 바뀌는 단추를 두지 않는다."""
    assert f"/team/members/{admin.id}/export-companies" not in as_admin.get("/team").text


def test_switching_a_missing_account_is_not_a_crash(as_admin):
    assert as_admin.post("/team/members/99999/export-companies").status_code == 404
