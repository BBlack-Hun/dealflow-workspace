"""Series A 이상 딜 소싱 줄 → `계약여부` · `계약서 수신 여부` 칸 둘

10/28 요청: "Series A 이상 딜 소싱 탭의 이메일 오른쪽으로 계약여부랑 계약서 수신여부
컬럼 추가". IR 기업 현황의 같은 두 칸(`ir_companies.contract_status` ·
`contract_received`)과 같은 값을 적고, IR 기업에 이어진 줄은 따라 고친다
(`services/company_sync.FIELDS`). 이 판은 칸만 세운다 — 이미 이어진 줄의 빈칸은
`scripts/company_sync_fill.py` 가 채운다.

빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 두 칸을 뗀다(그 값만 사라지고 줄은 그대로다).

Revision ID: 0125_series_a_contract
Revises: 0124_firm_research_cols
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0125_series_a_contract"
down_revision = "0124_firm_research_cols"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"
COLUMNS = ("contract_status", "contract_received")


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if not have:
        return
    for name in COLUMNS:
        if name not in have:
            op.add_column(TABLE, sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    gone = [c for c in COLUMNS if c in _columns()]
    if gone:
        with op.batch_alter_table(TABLE) as batch:
            for name in gone:
                batch.drop_column(name)
