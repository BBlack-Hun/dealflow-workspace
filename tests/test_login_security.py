"""로그인·세션 보강 — 비밀번호 변경 강제 · 시도 제한 · 세션 열쇠 해시 · 쿠키 · 로그아웃.

각 판정의 자리:
- 변경 강제: `deps.get_current_user` → `deps.must_change_response`
- 시도 제한: `services/auth.py` 의 로그인 시도 제한(메모리, 검사마다 conftest 가 비운다)
- 세션 열쇠: `services/auth._token_key`(이주는 `tests/test_session_token_hash_migration.py`)
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest
from sqlalchemy import select

from app import config
from app.models import Session as SessionRow
from app.services import auth as auth_svc

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

ROOT = Path(__file__).resolve().parent.parent


def _login(client, phone="01000000001", password=DEMO_PASSWORD):
    return client.post("/login", data={"phone": phone, "password": password},
                       follow_redirects=False)


# --- 1. 초기 비밀번호를 바꾸기 전에는 변경 화면만 ------------------------------

@pytest.fixture()
def must_change(db, users):
    users["u1"].must_change_password = 1
    db.commit()
    return users["u1"]


def test_화면은_변경_화면으로_보낸다(client, must_change):
    assert _login(client).headers["location"] == "/account/password"
    for path in ("/", "/deals", "/contacts", "/setup"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"] == "/account/password", path
    assert client.get("/account/password", follow_redirects=False).status_code == 200


def test_화면_밖_요청은_403(client, must_change):
    _login(client)
    assert client.get("/api/agent-status").status_code == 403
    assert client.post("/notices/seen", data={}, follow_redirects=False).status_code == 403
    assert client.patch("/api/companies/1", json={}).status_code == 403


def test_로그아웃과_정적_파일은_열려_있다(client, must_change):
    _login(client)
    assert client.get("/static/css/app.css").status_code == 200
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_바꾸고_나면_풀린다(client, db, must_change):
    _login(client)
    r = client.post("/account/password", data={
        "current_password": DEMO_PASSWORD, "new_password": "newpass-123",
        "confirm_password": "newpass-123"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/deals", follow_redirects=False).status_code == 200


def test_발송기_API_는_영향이_없다(client, must_change):
    """발송기는 토큰으로 온다 — 사람이 비밀번호를 안 바꿨다고 발송이 멎으면 안 된다."""
    r = client.get("/api/agent/poll", params={"kinds": "deal", "cap": 1},
                   headers=auth(DEMO_TOKEN))
    assert r.status_code in (200, 204), r.text


# --- 2·3. 로그인 시도 제한 · 없는 번호도 같은 일 ------------------------------

def test_다섯_번_틀리면_맞는_비밀번호도_15분_막힌다(client, users, monkeypatch):
    for _ in range(auth_svc.LOGIN_MAX_FAILS):
        assert _login(client, password="wrong-pass").headers["location"].endswith("error=1")

    # 잠긴 동안에는 비밀번호를 견주지도 않는다.
    calls = []
    real = auth_svc.verify_password
    monkeypatch.setattr(auth_svc, "verify_password",
                        lambda *a: calls.append(a) or real(*a))
    r = _login(client)
    assert "error=locked" in r.headers["location"]
    assert auth_svc.SESSION_COOKIE not in r.cookies
    assert calls == []
    assert "15분" in client.get("/login?error=locked").text


def test_IP_하나에서_여러_번호로_틀려도_막힌다(client, users):
    for n in range(auth_svc.LOGIN_MAX_FAILS):
        _login(client, phone=f"0109000000{n}", password="wrong-pass")
    assert "error=locked" in _login(client).headers["location"]


def test_잠금은_15분_뒤_풀리고_맞으면_번호_쪽은_지워진다():
    t0 = 1000.0
    for i in range(auth_svc.LOGIN_MAX_FAILS - 1):
        auth_svc.note_login_failure("01011112222", f"10.0.0.{i}", now=t0)
    auth_svc.note_login_success("01011112222")
    for i in range(auth_svc.LOGIN_MAX_FAILS - 1):
        auth_svc.note_login_failure("01011112222", f"10.0.1.{i}", now=t0)
    assert not auth_svc.login_locked("01011112222", "10.0.9.9", now=t0)

    locked = auth_svc.note_login_failure("01011112222", "10.0.2.1", now=t0)
    assert locked == ["phone:01011112222"]
    assert auth_svc.login_locked("01011112222", "10.0.9.9", now=t0 + 60)
    late = t0 + auth_svc.LOGIN_LOCK_SECONDS + 1
    assert not auth_svc.login_locked("01011112222", "10.0.9.9", now=late)


def test_실패는_번호를_가려_로그에_남긴다(client, users, caplog):
    with caplog.at_level(logging.WARNING, logger="app.routers.auth"):
        _login(client, password="wrong-pass")
        _login(client, phone="010-0000-0001", password="wrong-pass")
    text = caplog.text
    assert text.count("로그인 실패") == 2
    assert "01000000001" not in text and "0000-0001" not in text


def test_없는_번호도_해시는_견주기_한_번뿐(db, monkeypatch):
    made, checked = [], []
    real_verify = auth_svc.verify_password
    monkeypatch.setattr(auth_svc, "hash_password", lambda *a, **k: made.append(a))
    monkeypatch.setattr(auth_svc, "verify_password",
                        lambda *a: checked.append(a) or real_verify(*a))
    assert auth_svc.authenticate(db, "01077776666", "anything-1") is None
    assert made == [] and len(checked) == 1


# --- 5. 쿠키 -----------------------------------------------------------------

@pytest.mark.parametrize("production", [True, False])
def test_운영이면_세션_쿠키에_Secure(monkeypatch, production):
    from fastapi.responses import Response

    monkeypatch.setattr(config, "IS_PRODUCTION", production)
    resp = Response()
    auth_svc.set_session_cookie(resp, "tok")
    cookie = resp.headers["set-cookie"].lower()
    assert ("secure" in cookie) is production
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=" in cookie


def test_비밀번호를_바꾼_뒤_쿠키도_같은_함수가_굽는다(client, users):
    """로그인과 비밀번호 변경이 굽는 쿠키의 속성이 같다(값만 다르다)."""
    def attrs(r):
        cookie = next(c for c in r.headers.get_list("set-cookie")
                      if c.startswith(auth_svc.SESSION_COOKIE + "="))
        return sorted(part.strip().lower() for part in cookie.split(";")[1:]
                      if not part.strip().lower().startswith("expires="))

    login = _login(client)
    change = client.post("/account/password", data={
        "current_password": DEMO_PASSWORD, "new_password": "newpass-123",
        "confirm_password": "newpass-123"}, follow_redirects=False)
    assert attrs(change) == attrs(login)


# --- 6. 세션 열쇠는 해시로만 --------------------------------------------------

def test_DB_에는_토큰이_아니라_해시가_남는다(client, db, users):
    token = _login(client).cookies[auth_svc.SESSION_COOKIE]
    stored = db.execute(select(SessionRow.token)).scalars().all()
    assert token not in stored
    assert hashlib.sha256(token.encode()).hexdigest() in stored
    assert client.get("/deals", follow_redirects=False).status_code == 200

    client.post("/logout")
    db.expire_all()
    assert db.execute(select(SessionRow)).scalars().all() == []


def test_해시를_쿠키로_넣어도_안_들어온다(client, db, users):
    _login(client)
    stored = db.execute(select(SessionRow.token)).scalars().one()
    client.cookies.clear()
    client.cookies.set(auth_svc.SESSION_COOKIE, stored)
    assert client.get("/deals", follow_redirects=False).status_code == 303


# --- 7. 로그아웃은 POST 만 ----------------------------------------------------

def test_GET_로그아웃은_세션을_끊지_않는다(client, users):
    _login(client)
    client.get("/logout", follow_redirects=False)
    assert client.get("/deals", follow_redirects=False).status_code == 200


def test_화면의_로그아웃은_POST_폼이다(client, users):
    _login(client)
    html = client.get("/deals").text
    assert '<form method="post" action="/logout"' in html
    for path in (ROOT / "app" / "templates").rglob("*.html"):
        assert 'href="/logout"' not in path.read_text(encoding="utf-8"), path.name
