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


def upgrade() -> None:
    op.add_column("weekly_routines", sa.Column("time_of_day", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("weekly_routines", "time_of_day")
