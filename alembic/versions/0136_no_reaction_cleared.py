"""`반응 없음` 에서 손으로 빼기 — `vc_contacts.no_reaction_cleared_at`

요청(11/11): "반응 없는 담당자 사용자가 체크해서 뺄 수 있게". 앱은 기록만 보고
`반응 없음` 을 정하는데(`services/no_reaction`), 전화 · 다른 길로 반응이 있었던 분은
기록이 없어 그대로 남는다. 딜 제안 관리에서 사람이 뺀 시각을 이 칸에 적는다.

비워 둔다 — 지금 줄은 전부 손으로 뺀 적이 없는 줄이라 판정이 그대로다. 빈 DB 는
`0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(손으로 뺀 분이 다시 `반응 없음` 으로 선다 — 줄은 그대로다).

Revision ID: 0136_no_reaction_cleared
Revises: 0135_sender_room_sourcing
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0136_no_reaction_cleared"
down_revision = "0135_sender_room_sourcing"
branch_labels = None
depends_on = None

TABLE = "vc_contacts"
COLUMN = "no_reaction_cleared_at"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if have and COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
