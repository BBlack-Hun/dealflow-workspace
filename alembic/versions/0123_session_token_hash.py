"""로그인 세션 열쇠를 해시로만 둔다

`sessions.token` 에 쿠키의 토큰을 그대로 두던 것을 **그 sha256 값**으로 바꾼다
(`services/auth._token_key`). 칸 이름·모양은 그대로다 — 들어 있는 값만 바뀐다.

있던 줄도 같은 값으로 바꿔 둔다. 브라우저의 쿠키는 그대로이고 앱은 쿠키 토큰을
해시해서 찾으므로, **이주한 날 아무도 로그아웃되지 않는다.**

이미 해시인 값(64자리 16진수)은 건드리지 않는다 — 옛 토큰(`token_urlsafe(32)`,
43자)과 모양이 달라 섞이지 않는다. 백업에서 되돌린 DB 가 이 판을 다시 지나도
두 번 해시되지 않는다.

되돌리기: 해시에서 토큰을 되살릴 수 없으므로 **세션을 모두 지운다**(다시 로그인).

Revision ID: 0123_session_token_hash
Revises: 0122_series_a_ir_link
"""
from __future__ import annotations

import hashlib
import re

import sqlalchemy as sa
from alembic import op

revision = "0123_session_token_hash"
down_revision = "0122_series_a_ir_link"
branch_labels = None
depends_on = None

_HASHED = re.compile(r"[0-9a-f]{64}")


def _has_sessions() -> bool:
    return "sessions" in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_sessions():
        return
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, token FROM sessions")).fetchall()
    for row_id, token in rows:
        if not token or _HASHED.fullmatch(token):
            continue
        bind.execute(sa.text("UPDATE sessions SET token = :t WHERE id = :i"),
                     {"t": hashlib.sha256(token.encode("utf-8")).hexdigest(), "i": row_id})


def downgrade() -> None:
    if _has_sessions():
        op.execute("DELETE FROM sessions")
