"""세션 열쇠를 해시로 바꾸는 판(0123) — **이주해도 아무도 로그아웃되지 않는가.**

운영과 같은 모양을 세운다: `0122` 까지 올린 DB 에 옛 방식(토큰 그대로)의 세션 줄.
올린 뒤 그 줄은 쿠키 토큰의 sha256 이 되어, 앱이 같은 쿠키로 찾는 값과 같아야 한다.
"""
from __future__ import annotations

import secrets
import sqlite3

import pytest

from app.services import auth as auth_svc

from .test_migrations import _alembic

BEFORE = "0122_series_a_ir_link"


def _tokens(db) -> list:
    con = sqlite3.connect(db)
    try:
        return [r[0] for r in con.execute("SELECT token FROM sessions ORDER BY id")]
    finally:
        con.close()


@pytest.fixture()
def old_db(tmp_path):
    db = tmp_path / "old.db"
    done = _alembic(db, "upgrade", BEFORE)
    assert done.returncode == 0, done.stdout + done.stderr
    return db


def _add_session(db, token):
    """세션 줄만 넣는다(이 연결은 외래키를 안 본다 — 판이 보는 것은 열쇠 칸뿐이다)."""
    con = sqlite3.connect(db)
    try:
        con.execute("INSERT INTO sessions (token, user_id, expires_at, created_at, updated_at) "
                    "VALUES (?, 1, '2026-11-09T00:00:00+09:00', "
                    "'2026-10-26T00:00:00+09:00', '2026-10-26T00:00:00+09:00')", (token,))
        con.commit()
    finally:
        con.close()


def test_옛_세션이_같은_쿠키로_그대로_찾힌다(old_db):
    old = [secrets.token_urlsafe(32) for _ in range(3)]
    for token in old:
        _add_session(old_db, token)

    up = _alembic(old_db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert _tokens(old_db) == [auth_svc._token_key(t) for t in old]


def test_이미_해시인_값은_두_번_해시하지_않는다(old_db):
    hashed = auth_svc._token_key(secrets.token_urlsafe(32))
    _add_session(old_db, hashed)
    up = _alembic(old_db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert _tokens(old_db) == [hashed]


def test_되돌리면_세션을_비운다(old_db):
    _add_session(old_db, secrets.token_urlsafe(32))
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    down = _alembic(old_db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
    assert _tokens(old_db) == []
