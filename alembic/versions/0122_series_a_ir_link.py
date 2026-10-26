"""Series A 이상 딜 소싱 줄 → IR 기업 연결 칸 둘(기업 동기화 3단계)

- `series_a_companies.ir_company_id` — 이 딜이 IR 기업 현황의 어느 기업인가.
- `series_a_companies.ir_link_auto` — 이름으로 저절로(또는 일괄 연결로) 이었는가.

투자컨설턴트 · 스타트업 명단의 같은 두 칸(0097 · 0117)과 같다. 이 판은 칸만 세운다 —
값은 채우지 않는다. 있던 줄은 관리자가 `/ir-link` 의 Series A 탭 [후보가 하나인 줄
일괄 연결] 로 잇는다(새 줄은 저장할 때 이름이 정확히 하나 맞으면 저절로).

외래키는 0097 과 같은 까닭으로 SQLite 에서 `ADD COLUMN … REFERENCES` 한 줄로 붙인다.
빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(이어 둔 것만 사라지고 줄은 그대로다).

Revision ID: 0122_series_a_ir_link
Revises: 0121_ir_revenue_years
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0122_series_a_ir_link"
down_revision = "0121_ir_revenue_years"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if not have:
        return
    if "ir_company_id" not in have:
        if op.get_bind().dialect.name == "sqlite":
            op.execute(f"ALTER TABLE {TABLE} ADD COLUMN ir_company_id INTEGER "
                       f"REFERENCES ir_companies (id)")
        else:
            op.add_column(TABLE, sa.Column("ir_company_id", sa.Integer(),
                                           sa.ForeignKey("ir_companies.id"), nullable=True))
    if "ir_link_auto" not in have:
        op.add_column(TABLE, sa.Column("ir_link_auto", sa.Integer(), nullable=False,
                                       server_default="0"))


def downgrade() -> None:
    gone = [c for c in ("ir_company_id", "ir_link_auto") if c in _columns()]
    if gone:
        with op.batch_alter_table(TABLE) as batch:
            for name in gone:
                batch.drop_column(name)
