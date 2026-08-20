"""규칙 밖 회차일 (일회성 추가 · 건너뛰기)

"다음 딜 제안은 8월 26일" 처럼 규칙(매월 첫째·셋째 수요일)에서 벗어난 날짜가
정해져 내려온다. 규칙 자체를 고치면 그 달 이후가 전부 따라 바뀌므로,
한 번짜리 날짜는 따로 담는다.

Revision ID: 0013_extra_send_dates
Revises: 0012_sheet_owners
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_extra_send_dates"
down_revision = "0012_sheet_owners"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    have = _columns("schedule_rules")
    for name in ("extra_dates", "skip_dates"):
        if name not in have:
            op.add_column("schedule_rules", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    have = _columns("schedule_rules")
    for name in ("extra_dates", "skip_dates"):
        if name in have:
            op.drop_column("schedule_rules", name)
