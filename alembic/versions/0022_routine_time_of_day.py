"""반복 업무에 오전/오후를 붙인다

시트에는 "화요일 오전" 처럼 요일 옆에 시간대까지 적혀 있었는데 앱에는
요일만 있었다.

Revision ID: 0022_routine_time_of_day
Revises: 0021_top_deal_kind
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_routine_time_of_day"
down_revision = "0021_top_deal_kind"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있으면 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    if not _has_column("weekly_routines", "time_of_day"):
        op.add_column("weekly_routines",
                      sa.Column("time_of_day", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("weekly_routines", "time_of_day"):
        op.drop_column("weekly_routines", "time_of_day")
