"""투자사 관리 현황 → 명단 탭 차례 — `sheet_owners.position`

#181: 관리자가 `전체` 에서 보는 명단 차례를 정해 달라고 했다. 지금 차례는 연결
완료 → 인원 → 이름이라 사람이 고를 수 없다. 이름으로 차례를 적지 않으려고
(탭 이름은 11/04 처럼 바뀐다) 명단에 수 하나를 붙인다 — 작은 수가 앞이고, 비면
지금까지처럼 그 뒤에 선다.

지난 줄은 채워 넣지 않는다 — 빈칸으로 시작해 차례가 지금과 같다.
빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(차례만 예전으로 돌아간다).

Revision ID: 0134_sheet_tab_position
Revises: 0133_consulting_contract_ym
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0134_sheet_tab_position"
down_revision = "0133_consulting_contract_ym"
branch_labels = None
depends_on = None

TABLE = "sheet_owners"
COLUMN = "position"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if have and COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
