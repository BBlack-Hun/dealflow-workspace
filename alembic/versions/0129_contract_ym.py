"""IR 기업 현황 · Series A 이상 딜 소싱 → `계약년월` 칸(`YYYY-MM`)

11/01 개선 과제 #122: "IR 기업현황 > 미팅제공일자 > 오른쪽에 계약년월 컬럼 넣기 ,
Series A 이상 딜 소싱 -> 계약여부 왼쪽에 계약년월 컬럼넣기". 사람이 적는 칸이고, 계약여부가
계약 완료로 바뀌는 순간 비어 있으면 그 달이 들어간다(`contract_day7.before_flush`).
지난 계약은 채워 넣지 않는다 — 빈칸으로 시작한다.

빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(그 값만 사라지고 줄은 그대로다).

Revision ID: 0129_contract_ym
Revises: 0128_forecast_follow_round
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0129_contract_ym"
down_revision = "0128_forecast_follow_round"
branch_labels = None
depends_on = None

TABLES = ("ir_companies", "series_a_companies")
COLUMN = "contract_ym"


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    for table in TABLES:
        have = _columns(table)
        if have and COLUMN not in have:
            op.add_column(table, sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        if COLUMN in _columns(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(COLUMN)
