"""ID/PW 인증 테스트 — 로그인 ID 는 휴대폰번호(숫자만)."""
import pytest

from app.services import auth as auth_svc


# --- 휴대폰번호 정규화 -------------------------------------------------------

def test_normalize_phone_strips_non_digits():
    """하이픈을 넣어 입력해도 로그인돼야 한다(저장·비교 규칙이 같아야 함)."""
    assert auth_svc.normalize_phone("010-0000-0001") == "01000000001"
    assert auth_svc.normalize_phone("010 1234 5678") == "01012345678"
    assert auth_svc.normalize_phone("01000000001") == "01000000001"
    assert auth_svc.normalize_phone(None) == ""


# --- 비밀번호 해시 -----------------------------------------------------------

def test_hash_is_not_plaintext_and_salted():
    h1 = auth_svc.hash_password("secret123")
    h2 = auth_svc.hash_password("secret123")
    assert "secret123" not in h1
    assert h1 != h2, "salt 가 달라 같은 비밀번호도 해시가 달라야 한다"


def test_verify_password():
    h = auth_svc.hash_password("secret123")
    assert auth_svc.verify_password("secret123", h) is True
    assert auth_svc.verify_password("wrong", h) is False
    assert auth_svc.verify_password("secret123", None) is False
    assert auth_svc.verify_password("secret123", "쓰레기값") is False


def test_password_policy():
    assert auth_svc.password_problem("short") is not None
    assert auth_svc.password_problem("12345678") is not None   # 숫자만
    assert auth_svc.password_problem("dealflow123") is None


# --- 로그인 플로우 (HTTP) ----------------------------------------------------

def test_protected_page_redirects_to_login(client):
    r = client.get("/deals", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_api_returns_401_not_redirect(client):
    """API 는 리다이렉트가 아니라 401 이어야 한다(에이전트/스크립트가 파싱 가능하게)."""
    r = client.get("/api/agent-status", follow_redirects=False)
    assert r.status_code == 401


def test_login_success_sets_session_cookie(client, demo_user_password):
    r = client.post("/login", data={
        "phone": "01000000001", "password": demo_user_password, "next": "/deals",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert auth_svc.SESSION_COOKIE in r.cookies


def test_login_accepts_hyphenated_phone(client, demo_user_password):
    r = client.post("/login", data={
        "phone": "010-0000-0001", "password": demo_user_password, "next": "/deals",
    }, follow_redirects=False)
    assert auth_svc.SESSION_COOKIE in r.cookies


def test_login_failure_does_not_set_cookie(client):
    r = client.post("/login", data={
        "phone": "01000000001", "password": "틀린비밀번호", "next": "/deals",
    }, follow_redirects=False)
    assert auth_svc.SESSION_COOKIE not in r.cookies
    assert "error" in r.headers["location"]


def test_unknown_and_wrong_password_are_indistinguishable(client):
    """계정 존재 여부가 새어나가지 않아야 한다."""
    a = client.post("/login", data={"phone": "01099999999", "password": "x"},
                    follow_redirects=False)
    b = client.post("/login", data={"phone": "01000000001", "password": "x"},
                    follow_redirects=False)
    assert a.headers["location"] == b.headers["location"]


def test_logout_clears_session(client, demo_user_password):
    client.post("/login", data={"phone": "01000000001", "password": demo_user_password})
    assert client.get("/deals", follow_redirects=False).status_code == 200
    client.get("/logout", follow_redirects=False)
    assert client.get("/deals", follow_redirects=False).status_code == 303


def test_session_cookie_is_httponly(client, demo_user_password):
    """세션 토큰이 스크립트로 읽히면 안 된다."""
    r = client.post("/login", data={
        "phone": "01000000001", "password": demo_user_password,
    }, follow_redirects=False)
    assert "httponly" in r.headers.get("set-cookie", "").lower()


def test_forged_cookie_is_rejected(client):
    """쿠키를 위조해도 통과하면 안 된다(예전 개발용 전환과의 결정적 차이)."""
    client.cookies.set(auth_svc.SESSION_COOKIE, "forged-token-value")
    assert client.get("/deals", follow_redirects=False).status_code == 303
