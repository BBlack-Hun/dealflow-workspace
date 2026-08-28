"""관리자 전용 화면에 권한 없이 닿았을 때 — 화면 요청은 화면으로 답한다.

팀원이 `/team` 주소를 열면 브라우저에 날것의 JSON 이 떴다.

    {"detail": "관리자만 사용할 수 있습니다"}

쓰는 사람에게는 그냥 고장이다. 좌측 메뉴에 `팀 현황` 이 애초에 안 보이는
계정이라, 여기 닿는 길은 **주소를 직접 쳤거나 옛 링크를 누른 경우**뿐이다 —
그때 필요한 것은 '없는 화면' 이라는 말이 아니라 '권한이 없다' 와 **나갈 길**이다.

**화면만 바뀌고 권한이 느슨해지면 안 된다.** 관리자 조작(POST)은 그대로 403 이고,
관리자는 지금처럼 진짜 화면을 본다.

라우트를 훑는 두 검사는 `tests/test_consultant_access.py` 의 방식을 그대로 쓴다 —
손으로 적은 목록은 화면이 하나 늘 때마다 낡는다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD
# 훑는 도구는 컨설턴트 차단 검사와 **같은 것**을 쓴다. 여기 복사해 두면
# 한쪽만 고쳐진다(라우트를 세는 규칙이 갈리면 검사가 조용히 좁아진다).
from .test_consultant_access import _routes, _url


@pytest.fixture()
def people(db, users):
    """관리자 · 컨설턴트. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=81, name="관리자시험", phone="01000000081", role="admin", password_hash=pw),
        User(id=82, name="컨설턴트시험", phone="01000000082", role="consultant",
             password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


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
        "member": sign_in("01000000001"),      # 일반 팀원
        "admin": sign_in("01000000081"),
        "consultant": sign_in("01000000082"),
    }


def _content(html: str) -> str:
    """본문(`<main class="content">…</main>`)만 잘라 본다.

    사이드바는 어느 화면에서나 배지 스크립트를 한 줄 싣는다 — 안내창이
    스크립트 없이 뜨는지 보려면 본문만 봐야 한다.
    """
    start = html.index('<main class="content">')
    return html[start:html.index("</main>", start)]


# --- 화면 요청은 화면으로 -----------------------------------------------------

def test_a_member_gets_a_screen_not_json(portal):
    resp = portal["member"].get("/team")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert not resp.text.lstrip().startswith("{")
    assert '"detail"' not in resp.text


def test_the_notice_says_it_is_about_permission_not_a_missing_screen(portal):
    """'없는 화면' 으로 읽히면 다음에 무엇을 할지 알 수 없다."""
    body = portal["member"].get("/team").text
    assert "관리자만 볼 수 있습니다" in body
    assert "권한" in body
    # 좌측 메뉴에 없는 화면이라, 여기 온 사람은 주소를 직접 쳤거나 옛 링크를 눌렀다.
    assert "주소를 직접" in body


def test_the_notice_leads_to_the_dashboard(portal):
    """막는 것만 하고 나갈 길을 안 주면 뒤로가기 말고는 방법이 없다."""
    block = _content(portal["member"].get("/team").text)
    assert 'href="/"' in block
    assert "대시보드로 가기" in block


def test_the_notice_works_without_javascript(portal):
    """스크립트 예외 하나로 상세 패널이 통째로 안 열린 적이 있다.

    나가는 길을 알려 주는 창이 스크립트에 기대면 그날 나갈 방법이 사라진다 —
    안내창은 서버가 그린 그대로, 평범한 링크 하나로 되어야 한다.
    """
    block = _content(portal["member"].get("/team").text)
    assert "<script" not in block
    assert "onclick" not in block
    # 숨겨 두고 스크립트로 펴는 방식도 같은 곳에서 깨진다.
    # (`aria-hidden` 은 읽어 주는 프로그램용 표시라 해당 없다 — 속성 `hidden` 만 본다.)
    assert not re.search(r"\shidden[\s=>]", block)
    assert "<dialog" not in block          # showModal() 을 불러야 창이 된다


def test_the_app_shell_is_still_there(portal):
    """빈 화면이라도 앱 안이어야 한다 — 껍데기가 없으면 로그아웃된 줄 안다."""
    body = portal["member"].get("/team").text
    assert 'class="sidebar"' in body
    assert 'href="/deals"' in body         # 좌측 메뉴가 그대로 있다


def test_the_blocked_screen_names_itself(portal):
    """무엇을 열려 했는지 이름을 댄다 — 이름은 좌측 메뉴에서 가져온다."""
    body = portal["member"].get("/team").text
    assert "팀 현황 화면은 관리자만 볼 수 있습니다" in body


def test_no_team_data_leaks_into_the_notice(portal):
    """볼 수 없는 화면이라 뒤에 그릴 내용이 없다 — 흐리게라도 깔지 않는다."""
    body = portal["member"].get("/team").text
    assert "팀원별 현황" not in body
    assert "관리자시험" not in body        # 남의 계정 정보


# --- 조작과 스크립트는 그대로 403 --------------------------------------------

def test_admin_actions_still_return_403(portal, db, users):
    """화면만 바뀌고 권한이 느슨해지면 안 된다.

    조작을 손으로 나열하지 않는다 — 관리자 조작이 하나 늘어도 여기서 같이 걸린다.
    """
    app, client = portal["app"], portal["member"]
    # 폼 검사는 라우터보다 먼저 돈다 — 빈 몸통으로 부르면 권한이 아니라 422 로
    # 걸려서, 무엇이 막았는지 알 수 없다. 아무 조작에나 맞는 값을 채워 보낸다.
    filled = {"name": "시험계정", "phone": "01000000099", "role": "admin",
              "to": "nobody@example.com"}
    leaked = []
    for method, path in _routes(app):
        if method == "GET" or not path.startswith("/team"):
            continue
        resp = client.request(method, _url(path), data=filled, follow_redirects=False)
        if resp.status_code != 403:
            leaked.append(f"{method} {path} → {resp.status_code}")
    assert not leaked, "팀원이 관리자 조작을 할 수 있다:\n" + "\n".join(leaked)

    # 상태 코드만 맞고 실제로는 바뀌었을 수 있다. 위 훑기가 `{member_id}` 를
    # 1 번으로 채워 이 계정을 겨눴으므로, 그 계정이 그대로인지 본다.
    db.refresh(users["u1"])
    assert users["u1"].role == "user"
    assert users["u1"].is_active == 1


def test_a_script_still_gets_403(portal):
    """화면 속 fetch 에 HTML 을 주면 저장이 성공한 것처럼 보인다."""
    resp = portal["member"].get("/team", headers={"accept": "application/json"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "관리자만 사용할 수 있습니다"


# --- 관리자는 지금처럼 ---------------------------------------------------------

def test_the_admin_still_sees_the_real_screen(portal):
    body = portal["admin"].get("/team").text
    assert "팀원별 현황" in body
    # 안내창은 뜨지 않는다. 화면 문구로 견주지 않는 것은 팀 현황 머리말에도
    # `관리자만 볼 수 있습니다` 라는 말이 이미 있기 때문이다.
    assert "guard-modal" not in body


def test_the_admin_can_still_act(portal, db, users):
    r = portal["admin"].post(f"/team/members/{users['u2'].id}/role",
                             data={"role": "admin"}, follow_redirects=False)
    assert r.status_code == 303
    db.refresh(users["u2"])
    assert users["u2"].role == "admin"


# --- 새 관리자 화면이 생겨도 --------------------------------------------------

def test_no_admin_screen_answers_with_json(portal):
    """관리자 전용 **화면**은 어느 것도 날것의 JSON 을 뱉지 않는다.

    화면을 손으로 나열하지 않는다(`app.routes` 를 훑는다) — 관리자 화면이
    하나 늘면 판정 한 곳(`deps.admin_block_response`)이 자동으로 걸어 주고,
    그렇지 않은 것은 여기서 잡힌다.

    `/api/…` 는 대상이 아니다. 그쪽은 스크립트가 부르는 자리라 403 JSON 이 맞다.
    `/logout` 만 건너뛴다 — 세션이 끊기면 그 뒤 요청이 전부 로그인 화면으로
    가서 무엇을 검사한 것인지 알 수 없게 된다.
    """
    from app import deps

    app, client = portal["app"], portal["member"]
    raw = []
    for method, path in _routes(app):
        if method != "GET" or path.startswith("/api/") or path == "/logout":
            continue
        resp = client.get(_url(path), follow_redirects=False)
        if deps.ADMIN_ONLY in resp.text:
            kind = resp.headers.get("content-type", "")
            if not kind.startswith("text/html"):
                raw.append(f"GET {path} → {resp.status_code} {kind}")
    assert not raw, "화면 요청에 JSON 이 그대로 나갔다:\n" + "\n".join(raw)


def test_a_consultant_is_still_sent_to_their_own_screen(portal):
    """컨설턴트 차단이 먼저다 — 두 처리가 부딪히면 컨설턴트가 남의 화면 이름을 본다."""
    resp = portal["consultant"].get("/team", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/consulting"
