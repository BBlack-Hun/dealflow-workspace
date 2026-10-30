"""Series A 이상 딜 소싱 줄 → `후속라운드 시작` 칸(`YYYY-MM`)

10/30 개선 과제 #98: "Series A 이상 딜소싱 > 수신일 오른쪽에 후속라운드시작 컬럼 추가".
사람이 적는 칸이다 — 적을 때 `YYYY-MM` 으로 맞춘다(`routers/series_a._assign`).

빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(그 값만 사라지고 줄은 그대로다).

Revision ID: 0127_series_a_follow_round
Revises: 0126_startup_send_day_wording
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0127_series_a_follow_round"
down_revision = "0126_startup_send_day_wording"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"
COLUMN = "follow_round_month"


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
