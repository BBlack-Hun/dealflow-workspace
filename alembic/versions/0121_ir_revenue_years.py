"""IR 기업 현황 연도별 매출 칸 — 26~30년을 미리 판다(#75)

화면은 오늘 기준 **지난 세 해**와 `최근 매출액(올해)` 를 세운다(`services/revenue_years.py`).
해가 바뀔 때마다 판을 만들지 않으려고 다섯 해치를 한 번에 판다 — Series A 탭이
24~27년을 미리 판 것과 같은 방식이다(0112). 2032년 1월 전에 `revenue_2031` 판
하나만 더하면 된다(그해에 지난해 칸이 필요해진다 — `revenue_years` 머리말).

NULL 이고 기본값이 없다 — 빈칸이 곧 `아직 안 적음` 이다. 값은 이주가 채우지 않는다:
해가 바뀐 뒤 첫 화면이 `최근 매출액` 을 지난해 칸으로 옮겨 적는다(빈 칸만 · 해마다 한 번).

빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다(0119 와 같다).
되돌리기: 칸을 뗀다(그 칸에 옮겨 적힌 값도 함께 사라진다 — `최근 매출액` 은 그대로다).

Revision ID: 0121_ir_revenue_years
Revises: 0120_contract_day7
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0121_ir_revenue_years"
down_revision = "0120_contract_day7"
branch_labels = None
depends_on = None

NEW = [f"revenue_{year}" for year in range(2026, 2031)]


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if "ir_companies" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("ir_companies")}


def upgrade() -> None:
    have = _columns()
    for name in NEW:
        if have and name not in have:
            op.add_column("ir_companies", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    have = _columns()
    gone = [name for name in NEW if name in have]
    if gone:
        with op.batch_alter_table("ir_companies") as batch:
            for name in gone:
                batch.drop_column(name)
