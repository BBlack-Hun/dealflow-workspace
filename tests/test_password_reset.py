"""관리자가 팀원의 비밀번호를 초기화한다 — 팀 현황(`/team`).

이 테스트가 생긴 이유. 운영에서 관리자가 비밀번호를 잊어 로그인을 못 했는데
**화면에는 되돌릴 길이 하나도 없었다.** 서버에 들어가 DB 를 직접 고치는 수밖에
없었다. 팀이 늘고 입퇴사가 생기는 중이라 그 일은 반복된다.

여기서 못 박는 것.

1. **관리자만 한다.** 팀원도 투자컨설턴트도 남의 비밀번호를 건드릴 수 없다.
2. **초기화하면 그 값으로 실제로 로그인된다.** 되돌려 놓기만 하고 전달할 값이
   틀리면 기능이 없는 것과 같다.
3. **초기화된 계정은 첫 로그인 때 반드시 바꾼다**(`must_change_password=1`).
   관리자가 아는 값으로 계속 쓰면 "본인만 아는 비밀번호" 라는 전제가 깨진다.
4. **비밀번호가 주소에 실리지 않는다.** 질의문자열은 브라우저 기록과 서버
   접근 로그에 요청 줄 그대로 남는다. 주소는 '적어 달라'는 표시(`pw=1`)만
   나르고 값은 서버가 화면에 그린다.
5. **본인 것은 이 길로 못 바꾼다.** 관리자 자신은 계정 메뉴에서 현재 비밀번호를
   대고 바꾼다.
"""
from __future__ import annotations

import pytest

from app import config

from .conftest import DEMO_PASSWORD

# 이 테스트 안에서만 쓰는 팀 공통 초기값.
#
# 저장소 기본값(`config.DEFAULT_INITIAL_PASSWORD`)은 테스트 계정들이 이미 쓰는
# 값과 같다. 그대로 두면 '초기화가 됐다'와 '원래부터 그 값이었다'를 구분할 수
# 없어 통과해도 아무것도 증명하지 못한다.
RESET_TO = "TeamInitial-9x7"

# 팀원이 스스로 정해 쓰던 비밀번호(초기화 전 상태를 만들기 위한 값).
MEMBER_OWN = "MemberChosen-4k2"


@pytest.fixture()
def initial_password(monkeypatch):
    """팀 공통 초기값을 못 박는다 — `.env` 가 무엇이든 결과가 같아야 한다."""
    monkeypatch.setattr(config, "INITIAL_PASSWORD", RESET_TO)
    return RESET_TO


@pytest.fixture()
def people(db, users):
    """관리자 둘 · 투자컨설턴트 하나. conftest 의 두 계정은 둘 다 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=81, name="관리자하나", phone="01000000081", role="admin", password_hash=pw),
        User(id=82, name="관리자둘", phone="01000000082", role="admin", password_hash=pw),
        User(id=83, name="컨설턴트", phone="01000000083", role="consultant", password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "admin2": rows[1], "consultant": rows[2],
            "member": users["u1"]}


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
        "admin": sign_in("01000000081"),
        "admin2": sign_in("01000000082"),
        "consultant": sign_in("01000000083"),
        "member": sign_in("01000000001"),
    }


def _reset(client, member_id: int):
    return client.post(f"/team/members/{member_id}/reset-password",
                       follow_redirects=False)


def _can_log_in(app, phone: str, password: str):
    """새 클라이언트로 로그인해 본다 — 되면 도착지, 안 되면 None."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.post("/login", data={"phone": phone, "password": password},
                    follow_redirects=False)
    if r.status_code != 303 or "error=1" in r.headers.get("location", ""):
        return None
    return r.headers["location"]


def _set_own_password(db, member, password: str) -> None:
    """팀원이 첫 로그인 때 스스로 정한 상태를 만든다."""
    from app.services import auth as auth_svc

    member.password_hash = auth_svc.hash_password(password)
    member.must_change_password = 0
    db.commit()


# --- 관리자만 한다 ----------------------------------------------------------

def test_a_team_member_cannot_reset_anyones_password(portal, db, people):
    member, admin = people["member"], people["admin"]
    before = admin.password_hash

    assert _reset(portal["member"], admin.id).status_code == 403

    db.refresh(admin)
    assert admin.password_hash == before
    assert member.role == "user"


def test_a_consultant_cannot_reset_anyones_password(portal, db, people):
    """컨설턴트는 미들웨어가 자기 화면으로 돌려보낸다 — 403 이 아니라 303 이다."""
    member = people["member"]
    before = member.password_hash

    r = _reset(portal["consultant"], member.id)
    assert r.status_code == 303
    assert r.headers["location"] == "/consulting"

    db.refresh(member)
    assert member.password_hash == before


# --- 초기화가 실제로 통하는가 -----------------------------------------------

def test_the_member_can_log_in_with_the_initial_password(portal, db, people,
                                                         initial_password):
    """되돌려 놓기만 하고 그 값으로 못 들어가면 기능이 없는 것과 같다."""
    member = people["member"]
    _set_own_password(db, member, MEMBER_OWN)
    assert _can_log_in(portal["app"], member.phone, initial_password) is None

    assert _reset(portal["admin"], member.id).status_code == 303

    assert _can_log_in(portal["app"], member.phone, initial_password) is not None
    # 옛 비밀번호는 더 이상 통하지 않는다.
    assert _can_log_in(portal["app"], member.phone, MEMBER_OWN) is None


def test_a_reset_account_must_change_the_password_first(portal, db, people,
                                                        initial_password):
    """관리자가 아는 값으로 계속 쓰게 두면 초기화가 뒷문이 된다."""
    member = people["member"]
    _set_own_password(db, member, MEMBER_OWN)

    _reset(portal["admin"], member.id)

    db.refresh(member)
    assert member.must_change_password == 1
    # 첫 로그인은 비밀번호 변경 화면으로 간다.
    assert _can_log_in(portal["app"], member.phone,
                       initial_password) == "/account/password"


def test_the_open_sessions_are_cut(portal, db, people, initial_password):
    """변경 요구는 **로그인할 때만** 걸린다.

    열려 있던 세션을 남겨 두면 그 기기는 로그인 화면을 다시 거치지 않으므로
    비밀번호를 바꾸지 않은 채 계속 쓴다.
    """
    member = people["member"]
    assert portal["member"].get("/dashboard").status_code == 200

    _reset(portal["admin"], member.id)

    r = portal["member"].get("/dashboard", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


# --- 비밀번호가 어디에 남는가 -----------------------------------------------

def test_the_password_never_rides_in_the_url(portal, db, people, initial_password):
    """질의문자열은 브라우저 기록과 서버 접근 로그에 요청 줄 그대로 남는다."""
    member = people["member"]
    r = _reset(portal["admin"], member.id)

    location = r.headers["location"]
    assert initial_password not in location
    # 주소가 나르는 것은 '적어 달라'는 표시뿐이다.
    assert "pw=1" in location

    # 표시를 받은 화면은 값을 서버에서 읽어 그린다 — 알려 주기는 한다.
    page = portal["admin"].get(location)
    assert page.status_code == 200
    assert initial_password in page.text
    # 그 화면조차 캐시되지 않는다.
    assert "no-store" in page.headers.get("cache-control", "")


def test_a_name_with_an_ampersand_does_not_split_the_query(portal, db, people,
                                                           initial_password):
    """안내 뒤에 표시(`&pw=1`)가 붙는 자리다 — 이름이 질의문자열을 가르면 안 된다."""
    member = people["member"]
    member.name = "가&pw=0&나"
    db.commit()

    location = _reset(portal["admin"], member.id).headers["location"]
    assert location.endswith("&pw=1")
    assert "pw=0" not in location
    assert initial_password in portal["admin"].get(location).text


def test_the_team_page_does_not_show_it_unasked(portal, initial_password):
    """평소에는 띄우지 않는다 — 어깨너머로 보일 자리를 줄인다."""
    page = portal["admin"].get("/team")
    assert page.status_code == 200
    assert initial_password not in page.text


# --- 본인 · 없는 계정 -------------------------------------------------------

def test_an_admin_cannot_reset_their_own_password(portal, db, people, initial_password):
    """관리자 자신은 계정 메뉴에서 현재 비밀번호를 대고 바꾼다.

    여기서 허용하면 잠깐 자리를 비운 관리자 화면 앞에 앉은 사람이 현재
    비밀번호를 모르고도 갈아 끼울 수 있다.
    """
    admin = people["admin"]
    before = admin.password_hash

    r = _reset(portal["admin"], admin.id)
    assert r.status_code == 303
    assert initial_password not in r.headers["location"]

    db.refresh(admin)
    assert admin.password_hash == before
    assert admin.must_change_password == 0


def test_resetting_an_account_that_is_not_there_is_404(portal):
    assert _reset(portal["admin"], 999_999).status_code == 404


# --- 관리자가 여럿일 때 -----------------------------------------------------

def test_admins_can_unlock_each_other(portal, db, people, initial_password):
    """관리자를 여럿 두는 이유가 곧 '한 사람이 잠겨도 팀이 멈추지 않게' 다.

    서로를 막으면 관리자가 잠겼을 때 다시 ssh 로 돌아간다 — 이 기능이
    없애려던 바로 그 상황이다.
    """
    locked = people["admin2"]
    _set_own_password(db, locked, MEMBER_OWN)

    assert _reset(portal["admin"], locked.id).status_code == 303

    db.refresh(locked)
    assert locked.must_change_password == 1
    assert _can_log_in(portal["app"], locked.phone,
                       initial_password) == "/account/password"


# --- 화면에 길이 있는가 -----------------------------------------------------

def test_the_button_is_on_the_team_screen(portal, people):
    """라우터만 있고 단추가 없으면 관리자는 여전히 서버에 들어가야 한다."""
    body = portal["admin"].get("/team").text
    assert f'action="/team/members/{people["member"].id}/reset-password"' in body
    # 본인 줄에는 없다.
    assert f'action="/team/members/{people["admin"].id}/reset-password"' not in body
