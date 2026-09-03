"""비밀번호를 바꾼 뒤 · 로그인한 뒤 **어디에 내려놓는가**.

이 검사가 생긴 이유. 비밀번호를 바꾸면 비밀번호 화면에 그대로 머물렀다
(`/account/password?ok=1`). 초기 비밀번호로 처음 들어온 사람은 바꾸고 나서도
같은 화면을 보고, 어디로 가야 하는지 스스로 찾아야 했다.

여기서 못 박는 것.

1. **역할마다 도착지가 있다** — 관리자·팀원은 대시보드, 투자컨설턴트는 자기
   화면. 기대값은 아래 `LANDING` 에 **손으로** 적는다. `deps.HOME_BY_ROLE` 를
   읽어 오면 그쪽이 틀려도 검사가 같이 틀려서 아무것도 못 잡는다.
2. **도착지가 실제로 열린다.** 컨설턴트를 대시보드로 보내면 허용 목록 밖이라
   미들웨어가 되튕겨 낸다 — 200 이 아닌 것이 오는 순간 빨개진다. 화면과 권한
   판정이 갈려 있는 것은 이 저장소가 반복해서 당한 부류다(좌측 메뉴 목록과
   라우터 목록이 갈려 컨설턴트에게 다 열려 있던 일).
3. **로그인 직후와 어긋나지 않는다.** 바꾼 뒤와 그냥 로그인했을 때가 서로
   다른 곳으로 가면, 처음 들어온 사람은 어디가 제자리인지 알 수 없다.
4. **좌측 메뉴와도 어긋나지 않는다.** 메뉴에 없는 화면에 떨어뜨리면 거기서
   돌아올 길이 눈에 보이지 않는다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

# 바꿔 넣을 비밀번호. 초기값(`DEMO_PASSWORD`)과 달라야 '바뀌었다'와 '원래
# 그 값이었다'가 구분된다.
NEW_PASSWORD = "LandedHere-7q3"

# 역할과 그 역할이 내려앉을 곳.
LANDING = {
    "admin": "/",
    "user": "/",
    # 컨설턴트는 대시보드에 못 들어간다(`deps.CONSULTANT_PATHS`).
    "consultant": "/consulting",
}

ROLES = sorted(LANDING)

PHONE = {"admin": "01000000071",
         "user": "01000000072",
         "consultant": "01000000073"}


@pytest.fixture()
def people(db, users):
    """역할 셋. 전부 **초기 비밀번호를 쓰는 상태**로 둔다.

    관리자가 계정을 만들거나 비밀번호를 초기화한 직후가 이 모습이고, 사용자가
    말한 "초기 비밀번호로 로그인 했을때" 가 바로 여기다.
    """
    from app import deps
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    # 투자현황은 계정마다 켜고 끈다 — **만들 때의 기본값**을 앱과 같은 함수에서
    # 가져온다. 여기에 숫자를 손으로 적어 두면 기본값이 바뀔 때 이 검사만 낡아,
    # 새로 만든 컨설턴트가 첫 화면부터 막히는 것을 못 잡는다.
    rows = {
        role: User(id=70 + i, name=f"도착지{i}", phone=PHONE[role], role=role,
                   can_view_consulting=1 if deps.consulting_default_for(role) else 0,
                   password_hash=pw, must_change_password=1)
        for i, role in enumerate(ROLES, start=1)
    }
    db.add_all(rows.values())
    db.commit()
    return rows


@pytest.fixture()
def app(db, users, people):
    """앱 하나. 역할마다 클라이언트를 따로 만든다 — 한 클라이언트로 로그인을
    갈아타면 쿠키가 덮여서 어느 사람으로 부른 것인지 알 수 없다."""
    from app.main import create_app

    return create_app()


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def _sign_in(app, role: str, password: str = DEMO_PASSWORD, **data):
    """로그인하고 (클라이언트, 도착지) 를 돌려준다."""
    client = _client(app)
    r = client.post("/login",
                    data={"phone": PHONE[role], "password": password, **data},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "error=1" not in r.headers["location"], "로그인이 안 됐다"
    return client, r.headers["location"]


def _change(client):
    return client.post("/account/password", data={
        "current_password": DEMO_PASSWORD,
        "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    }, follow_redirects=False)


def _settled(db, user):
    """초기 비밀번호 관문을 이미 지난 상태로 둔다."""
    user.must_change_password = 0
    db.commit()


def _path(location: str) -> str:
    """`/consulting?pw=1` → `/consulting`."""
    return location.split("?")[0]


# --- 바꾸고 나면 어디로 가는가 ----------------------------------------------

@pytest.mark.parametrize("role", ROLES)
def test_the_change_lands_on_that_roles_first_screen(app, role):
    """비밀번호 화면에 머무르지 않고 그 사람이 쓸 수 있는 첫 화면으로 간다."""
    client, first = _sign_in(app, role)
    # 초기 비밀번호로 들어오면 먼저 비밀번호 화면이다.
    assert first == "/account/password"

    r = _change(client)
    assert r.status_code == 303
    assert _path(r.headers["location"]) == LANDING[role]
    assert _path(r.headers["location"]) != "/account/password"


@pytest.mark.parametrize("role", ROLES)
def test_the_landing_actually_opens(app, role):
    """**간 곳이 열려야 한다.** 403·404 도, 되튕기는 303 도 도착이 아니다.

    컨설턴트를 `/` 로 보내면 미들웨어가 `/consulting` 으로 되튕겨 내므로
    여기서 303 이 잡힌다 — 화면은 '보냈다'고 하는데 못 여는 상태다.
    """
    client, _ = _sign_in(app, role)
    landing = _change(client).headers["location"]

    page = client.get(landing, follow_redirects=False)
    assert page.status_code == 200, (
        f"{role} 를 {landing} 로 보냈는데 {page.status_code} 가 돌아온다"
    )


def test_the_consultant_is_never_sent_to_the_dashboard(app):
    """컨설턴트에게 대시보드는 허용 목록 밖이다 — 보내면 막힌 화면을 본다."""
    from app import deps

    client, _ = _sign_in(app, "consultant")
    landing = _path(_change(client).headers["location"])

    assert landing not in ("/", "/dashboard"), "컨설턴트를 대시보드로 보냈다"
    assert deps.consultant_may_open(landing), f"{landing} 는 컨설턴트에게 막혀 있다"


# --- 로그인 직후와 어긋나지 않는가 ------------------------------------------

@pytest.mark.parametrize("role", ROLES)
def test_the_login_and_the_change_agree(app, role):
    """두 길이 다른 곳으로 가면 처음 들어온 사람은 제자리를 못 찾는다."""
    client, _ = _sign_in(app, role)
    after_change = _path(_change(client).headers["location"])

    # 이제 초기 비밀번호가 아니다 — 그냥 로그인하면 어디로 가는가.
    _, after_login = _sign_in(app, role, password=NEW_PASSWORD)
    assert _path(after_login) == after_change


def test_a_wanted_page_still_wins(app, db, people):
    """가려던 곳이 있으면 그것이 첫 화면보다 우선이다.

    로그인 화면을 거치게 만든 것이 대개 '열려다 막힌 주소'(`?next=`)다.
    그것까지 첫 화면으로 덮으면 매번 손으로 다시 찾아 들어가야 한다.
    """
    _settled(db, people["user"])
    _, target = _sign_in(app, "user", password=DEMO_PASSWORD, next="/deals")
    assert target == "/deals"


def test_a_blocked_next_falls_back_to_the_first_screen(app, db, people):
    """가려던 곳이 그 사람에게 막혔으면 첫 화면으로 돌린다.

    컨설턴트가 남의 화면 주소를 안고 로그인 화면에 오면(만료된 링크 등)
    그대로 보내 봐야 막힌 화면을 한 번 보고서야 자기 화면에 닿는다.
    """
    _settled(db, people["consultant"])
    _, target = _sign_in(app, "consultant", password=DEMO_PASSWORD, next="/deals")
    assert target == LANDING["consultant"]


# --- 좌측 메뉴와 어긋나지 않는가 --------------------------------------------

@pytest.mark.parametrize("role", ROLES)
def test_the_landing_is_on_that_persons_menu(people, role):
    """메뉴에 없는 화면에 떨어뜨리면 거기서 돌아올 길이 눈에 안 보인다.

    도착지를 메뉴 첫 줄에서 **가져오지는** 않는다(이유는 `deps.HOME_BY_ROLE`) —
    메뉴 순서는 보기 좋으라고 손대는 것이라 도착지까지 따라 움직이면 안 된다.
    둘이 어긋나지 않는지만 여기서 본다.
    """
    from app.ui import visible_menu

    seen = {m["href"]: m for m in visible_menu(people[role])}
    assert LANDING[role] in seen, f"{role} 의 메뉴에 {LANDING[role]} 가 없다"
    assert seen[LANDING[role]]["ready"], "'준비 중' 화면에 내려놓으면 안 된다"


# --- 바뀌었다는 말이 따라가는가 --------------------------------------------

@pytest.mark.parametrize("role", ROLES)
def test_the_confirmation_follows_to_the_landing(app, role):
    """알림을 비밀번호 화면에 두고 오면, 다른 기기가 왜 로그아웃됐는지 모른다."""
    client, _ = _sign_in(app, role)
    page = client.get(_change(client).headers["location"])

    assert "비밀번호가 변경되었습니다" in page.text
    assert "다른 기기" in page.text


@pytest.mark.parametrize("role", ROLES)
def test_the_confirmation_does_not_linger(app, role):
    """그 다음에 그 화면을 다시 열면 남아 있으면 안 된다."""
    client, _ = _sign_in(app, role)
    _change(client)

    again = client.get(LANDING[role])
    assert again.status_code == 200
    assert "비밀번호가 변경되었습니다" not in again.text
