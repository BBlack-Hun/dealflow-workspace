"""투자컨설턴트는 자기 화면 하나만 쓴다 — 나머지는 주소를 직접 쳐도 막힌다.

**경로를 손으로 적지 않는다.** 좌측 메뉴만 걸러 두고 라우터를 막지 않아서
`/deals` · `/contacts` · `/api/export/contacts.xlsx` 가 전부 열려 있었던 것이
이 테스트가 생긴 이유다. 막을 곳을 적어 두는 방식이었다면 라우터가 하나 늘
때마다 여기 적는 것을 또 잊었을 것이다.

그래서 여기서는 **앱에 등록된 라우트를 통째로 훑는다**(`app.routes`).
새 화면이 생기면 자동으로 이 검사에 걸리고, 열어 두려면 `deps.CONSULTANT_PATHS`
와 아래 `EXPECTED_OPEN` 을 **둘 다** 고쳐야 한다 — 실수로 열리지 않는다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

# 투자컨설턴트에게 열어 두는 것 전부. (메서드, 라우트 경로)
#
# 이쪽은 손으로 적는 것이 맞다 — 열어 두는 쪽은 하나하나 이유를 대야 하고,
# 목록이 늘어나면 그 사실 자체가 눈에 띄어야 한다.
EXPECTED_OPEN = {
    # 자기 화면과 그 화면이 부르는 것들. 화면만 열면 칸을 고칠 수가 없다.
    ("GET", "/consulting"),
    # 탭 이름 바꾸기. 자기 화면의 탭이라 고칠 수 있어야 한다 — 바뀌는 것은
    # 화면 글자뿐이고, 표 모양은 바뀌지 않는 열쇠가 정한다.
    ("POST", "/consulting/sheets/rename"),
    ("POST", "/consulting/columns"),
    ("POST", "/consulting/columns/{column_id}/rename"),
    ("POST", "/consulting/columns/{column_id}/delete"),
    ("POST", "/consulting/import"),
    ("GET", "/api/consulting/{company_id}"),
    ("POST", "/api/consulting"),
    ("PATCH", "/api/consulting/{company_id}"),
    ("DELETE", "/api/consulting/{company_id}"),
    ("GET", "/api/export/consulting.xlsx"),
    # 참고 자료 패널(스크립트·가이드). 투자사 관리 현황과 주소를 같이 쓰므로
    # 어느 화면 자료인지는 라우터가 따로 본다.
    ("PATCH", "/api/ref-sheets/{sheet_id}/cell"),
    ("POST", "/ref-sheets/{sheet_id}/body"),
    ("POST", "/ref-sheets/{sheet_id}/rename"),
    ("POST", "/ref-sheets/{sheet_id}/delete"),
    # 막으면 들어올 수도 나갈 수도 없다.
    ("GET", "/login"),
    ("POST", "/login"),
    ("GET", "/logout"),
    ("POST", "/logout"),
    ("GET", "/account/password"),
    ("POST", "/account/password"),
    # 사이드바 배지가 5초마다 부른다(본인 기기 상태만 돌려준다).
    ("GET", "/api/agent-status"),
    ("GET", "/health"),
}

_PARAM = re.compile(r"\{[^}]+\}")


def _routes(app):
    """앱에 등록된 (메서드, 경로) 전부.

    `/openapi.json` · `/docs` 처럼 FastAPI 가 스스로 붙이는 것까지 함께 나온다 —
    그것도 컨설턴트에게 보여줄 이유가 없으므로 검사 대상이다.
    메서드가 없는 것(`/static` 마운트)은 훑을 대상이 아니다.
    """
    out = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or ()
        path = getattr(route, "path", "")
        if not path:
            continue
        for method in methods:
            if method not in ("HEAD", "OPTIONS"):
                out.add((method, path))
    return sorted(out)


def _url(path: str) -> str:
    """`/api/consulting/{company_id}` → `/api/consulting/1`."""
    return _PARAM.sub("1", path)


def _blocked(resp) -> bool:
    """막힌 응답인가.

    화면 요청은 자기 화면으로 돌려보내고, API 요청만 403 이다 — 주소창에
    403 만 뜨면 쓰는 사람은 고장인 줄 안다.
    """
    if resp.status_code == 303 and resp.headers.get("location") == "/consulting":
        return True
    return resp.status_code == 403 and "투자컨설턴트" in resp.text


@pytest.fixture()
def people(db, users):
    """컨설턴트 · 관리자 계정. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=91, name="컨설턴트시험", phone="01000000091",
             role="consultant", password_hash=pw),
        User(id=92, name="관리자시험", phone="01000000092",
             role="admin", password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"consultant": rows[0], "admin": rows[1]}


@pytest.fixture()
def portal(db, users, people):
    """앱 하나 + 역할별로 따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여서 어느 사람으로 부른
    것인지 알 수 없게 된다.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {
        "app": app,
        "consultant": sign_in("01000000091"),
        "admin": sign_in("01000000092"),
        "user": sign_in("01000000001"),
    }


# --- 막혔는가 ---------------------------------------------------------------

def test_every_route_outside_the_allow_list_is_blocked(portal):
    """허용 목록에 없는 것은 화면이든 API 든 전부 끊긴다.

    라우트를 통째로 훑으므로, 앞으로 라우터가 추가되면 여기서 잡힌다.
    """
    from app import deps

    app, client = portal["app"], portal["consultant"]
    leaked = []
    for method, path in _routes(app):
        if deps.consultant_may_open(path):
            continue
        resp = client.request(method, _url(path), follow_redirects=False)
        if not _blocked(resp):
            leaked.append(f"{method} {path} → {resp.status_code}")
    assert not leaked, "컨설턴트에게 열려 있다:\n" + "\n".join(leaked)


def test_the_allow_list_did_not_quietly_widen(portal):
    """열어 둔 경로가 목록과 정확히 같은가.

    위 검사는 '허용 목록에 있으면 건너뛴다' 이므로, 목록 자체가 넓어지면
    아무 것도 못 잡는다. 무엇이 열려 있는지는 여기서 못 박는다.
    """
    from app import deps

    opened = {(method, path) for method, path in _routes(portal["app"])
              if deps.consultant_may_open(path)}
    assert opened == EXPECTED_OPEN


def test_pages_come_back_to_the_consulting_screen(portal):
    """주소창에 403 만 뜨면 쓰는 사람은 고장인 줄 안다."""
    client = portal["consultant"]
    for path in ("/", "/deals", "/contacts", "/todo", "/team", "/setup"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 303, path
        assert resp.headers["location"] == "/consulting", path


def test_scripts_get_403_not_a_redirect(portal):
    """화면 속 fetch 에 리다이렉트를 주면 저장이 성공한 것처럼 보인다."""
    client = portal["consultant"]
    assert client.get("/api/export/contacts.xlsx").status_code == 403
    assert client.patch("/api/contacts/1", json={"name": "x"}).status_code == 403
    assert client.get("/api/companies").status_code == 403


def test_the_menu_shows_only_the_consulting_screen(portal):
    """메뉴와 라우터가 같은 목록을 본다 — 하나만 걸러 두면 다시 어긋난다."""
    body = portal["consultant"].get("/consulting").text
    assert 'href="/consulting"' in body
    for href in ('href="/deals"', 'href="/contacts"', 'href="/todo"',
                 'href="/companies"', 'href="/report"'):
        assert href not in body, href


# --- 쓸 수 있는가 -----------------------------------------------------------

def test_the_consulting_screen_still_works_end_to_end(portal):
    """막는 것만 맞고 자기 화면이 안 되면 계정이 무용지물이다."""
    client = portal["consultant"]
    assert client.get("/consulting").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.get("/api/agent-status").status_code == 200

    created = client.post("/api/consulting", json={"company_name": "가상기업"})
    assert created.status_code == 200
    company_id = created.json()["id"]

    # 칸을 눌러 바로 고치는 길(인라인 수정)이 살아 있어야 한다.
    assert client.patch(f"/api/consulting/{company_id}",
                        json={"region": "서울"}).status_code == 200
    assert client.get(f"/api/consulting/{company_id}").json()["region"] == "서울"

    # 달마다 늘어나는 열도 본인이 추가한다.
    added = client.post("/consulting/columns", data={"label": "9월 리마인드"},
                        follow_redirects=False)
    assert added.status_code == 303
    assert added.headers["location"].startswith("/consulting?")

    assert client.get("/api/export/consulting.xlsx").status_code == 200
    assert client.delete(f"/api/consulting/{company_id}").status_code == 200


def test_the_reference_panel_stays_on_its_own_screen(portal, db):
    """참고 자료 주소는 두 화면이 같이 쓴다 — 번호만 바꿔 남의 것을 못 건드린다."""
    import json

    from app.models import RefSheet

    mine = RefSheet(page="consulting", title="진행 스크립트", kind="text",
                    is_active=1, content_json=json.dumps({"body": "1) 인사"}))
    theirs = RefSheet(page="contacts", title="연결 순서", kind="text",
                      is_active=1, content_json=json.dumps({"body": "전화 → 초대"}))
    db.add_all([mine, theirs])
    db.commit()

    client = portal["consultant"]
    ok = client.post(f"/ref-sheets/{mine.id}/rename", data={"title": "IR 스크립트"},
                     follow_redirects=False)
    assert ok.status_code == 303
    db.refresh(mine)
    assert mine.title == "IR 스크립트"

    assert client.post(f"/ref-sheets/{theirs.id}/rename",
                       data={"title": "가로채기"}).status_code == 403
    assert client.post(f"/ref-sheets/{theirs.id}/delete").status_code == 403
    db.refresh(theirs)
    assert theirs.title == "연결 순서"
    assert theirs.is_active == 1


# --- 남의 접근이 좁아지지 않았는가 ------------------------------------------

@pytest.mark.parametrize("who", ["user", "admin"])
def test_reading_screens_did_not_narrow(portal, who):
    """일반 팀원·관리자는 무엇을 열든 컨설턴트 차단에 걸리지 않는다."""
    app, client = portal["app"], portal[who]
    hit = []
    for method, path in _routes(app):
        if method != "GET":
            continue
        resp = client.get(_url(path), follow_redirects=False)
        if _blocked(resp):
            hit.append(f"GET {path} → {resp.status_code}")
    assert not hit, f"{who} 의 접근이 좁아졌다:\n" + "\n".join(hit)


@pytest.mark.parametrize("who", ["user", "admin"])
def test_writing_did_not_narrow(portal, who):
    """쓰기(폼 전송·인라인 수정)도 마찬가지다.

    `/logout` 만 건너뛴다 — 세션이 끊기면 그 뒤 요청이 전부 로그인 화면으로
    가서 무엇을 검사한 것인지 알 수 없게 된다.
    """
    app, client = portal["app"], portal[who]
    hit = []
    for method, path in _routes(app):
        if method == "GET" or path == "/logout":
            continue
        resp = client.request(method, _url(path), follow_redirects=False)
        if _blocked(resp):
            hit.append(f"{method} {path} → {resp.status_code}")
    assert not hit, f"{who} 의 접근이 좁아졌다:\n" + "\n".join(hit)


def test_an_admin_still_reaches_the_team_screen(portal):
    assert portal["admin"].get("/team").status_code == 200
    assert portal["user"].get("/deals").status_code == 200
    assert portal["user"].get("/", follow_redirects=False).status_code == 200


# --- 권한이 저장되는가 -------------------------------------------------------
#
# 라우터를 다 막아도 계정이 컨설턴트로 저장되지 않으면 아무 소용이 없다.
# 실제로 팀 현황에서 [투자컨설턴트] 를 골라도 조용히 팀원으로 만들어졌다.

def _make_member(client, phone: str, role: str):
    return client.post("/team/members",
                       data={"name": "시험계정", "phone": phone, "role": role},
                       follow_redirects=False)


@pytest.mark.parametrize("picked,saved", [
    ("consultant", "consultant"),
    ("admin", "admin"),
    ("user", "user"),
    # 아는 값이 아니면 가장 좁은 권한으로 떨어뜨린다.
    ("superuser", "user"),
    ("", "user"),
])
def test_the_role_picked_on_the_form_is_the_role_saved(portal, db, picked, saved):
    from sqlalchemy import select

    from app.models import User

    phone = "01000000093"
    assert _make_member(portal["admin"], phone, picked).status_code == 303
    made = db.execute(select(User).where(User.phone == phone)).scalars().first()
    assert made is not None
    assert made.role == saved


def test_a_new_consultant_account_is_blocked_right_away(portal, db):
    """화면 폼으로 만든 계정도 그 화면 하나만 보여야 한다."""
    from fastapi.testclient import TestClient

    from app.services import auth as auth_svc

    phone = "01000000094"
    _make_member(portal["admin"], phone, "consultant")
    # 관리자가 만든 계정은 첫 로그인 때 비밀번호를 바꾸게 되어 있다 —
    # 여기서는 권한만 보므로 바로 쓸 수 있게 해 둔다.
    from sqlalchemy import select

    from app.models import User

    made = db.execute(select(User).where(User.phone == phone)).scalars().first()
    made.password_hash = auth_svc.hash_password(DEMO_PASSWORD)
    made.must_change_password = 0
    db.commit()

    client = TestClient(portal["app"])
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                follow_redirects=False)
    assert made.role == "consultant"
    assert _blocked(client.get("/deals", follow_redirects=False))
    assert client.get("/consulting").status_code == 200


def test_an_existing_account_can_be_switched_over(portal, db, users):
    """잘못 만들어진 계정을 고칠 길이 있어야 한다 — 없으면 지우고 다시 만들게 된다."""
    admin = portal["admin"]
    r = admin.post(f"/team/members/{users['u1'].id}/role",
                   data={"role": "consultant"}, follow_redirects=False)
    assert r.status_code == 303
    db.refresh(users["u1"])
    assert users["u1"].role == "consultant"

    # 바뀐 권한은 다음 요청부터 바로 먹는다 — 로그인 중이어도 마찬가지다.
    assert _blocked(portal["user"].get("/deals", follow_redirects=False))


def test_an_unknown_role_does_not_quietly_demote(portal, db, users):
    admin = portal["admin"]
    admin.post(f"/team/members/{users['u1'].id}/role",
               data={"role": "superuser"}, follow_redirects=False)
    db.refresh(users["u1"])
    assert users["u1"].role == "user"


def test_an_admin_cannot_lock_themselves_out(portal, db, people):
    """스스로 권한을 내리면 팀 현황에 다시 들어올 길이 없다."""
    admin = people["admin"]
    portal["admin"].post(f"/team/members/{admin.id}/role",
                         data={"role": "consultant"}, follow_redirects=False)
    db.refresh(admin)
    assert admin.role == "admin"


def test_only_an_admin_can_change_a_role(portal, db, users):
    r = portal["user"].post(f"/team/members/{users['u2'].id}/role",
                            data={"role": "admin"}, follow_redirects=False)
    assert r.status_code == 403
    db.refresh(users["u2"])
    assert users["u2"].role == "user"
