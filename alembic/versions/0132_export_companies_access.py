"""IR 기업현황 엑셀 내려받기를 계정마다 연다 — `users.can_export_companies`

11/01 에 내려받기 두 길(`/api/export/companies.xlsx` · `companies-view.xlsx`)을
**관리자만**으로 좁혔다. 그 원칙은 그대로 두고, 관리자가 팀 현황에서 켜 준 계정만
예외로 연다(`deps.may_export_companies`). 옆칸 `can_auto_attach_ir`(0059) 와 같은
자리, 같은 모양이다.

`0` 으로 채운다 — 지금 일반 팀원은 전부 막혀 있던 사람들이라 동작이 그대로다.
관리자는 이 칸과 무관하게 늘 받는다. 빈 DB 는 `0001_initial` 이 `create_all()` 로
만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(켜 준 팀원만 다시 막힌다).

Revision ID: 0132_export_companies_access
Revises: 0131_series_a_memo_meeting
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0132_export_companies_access"
down_revision = "0131_series_a_memo_meeting"
branch_labels = None
depends_on = None

TABLE = "users"
COLUMN = "can_export_companies"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if have and COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=False,
                                       server_default="0"))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
