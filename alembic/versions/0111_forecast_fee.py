"""매출예상리스트 2판 — 수수료 칸 넷(개선 과제 #46)

`revenue_forecasts` 에 칸 넷을 붙인다. 이 표의 매출은 **우리 수수료(성공보수)**다.

    fee_rate        성공보수율(%)     비면 자동 — 이어 둔 기업의 성공보수율
    expected_fee    예상 수수료(억)   비면 자동 — 희망 투자유치금액 × 성공보수율 ÷ 100
    expected_month  예상 시기         `YYYY-MM`
    likelihood      가능성            상 · 중 · 하

자동 칸은 앞 판과 같이 **사람이 적은 값만** 담는다(`services/forecast.py`).

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 칸이 있는지 보고
붙인다(0110 과 같다).

## 되돌리기

칸 넷을 뗀다. 사람이 적은 보수율 · 수수료 · 시기 · 가능성이 함께 사라진다 —
다른 표는 이 칸을 가리키지 않는다.

Revision ID: 0111_forecast_fee
Revises: 0110_custom_column_position
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0111_forecast_fee"
down_revision = "0110_custom_column_position"
branch_labels = None
depends_on = None

COLUMNS = ("fee_rate", "expected_fee", "expected_month", "likelihood")


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if "revenue_forecasts" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("revenue_forecasts")}


def upgrade() -> None:
    have = _columns()
    for name in COLUMNS:
        if have and name not in have:
            op.add_column("revenue_forecasts",
                          sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    gone = [name for name in COLUMNS if name in _columns()]
    if gone:
        with op.batch_alter_table("revenue_forecasts") as batch:
            for name in gone:
                batch.drop_column(name)
