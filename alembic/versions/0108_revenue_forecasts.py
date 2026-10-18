"""업무 보고 › `매출예상리스트` — 표 하나

`revenue_forecasts` — 기업 하나 × 투자사 하나에 한 줄(개선 과제 #46 ·
`models.RevenueForecast`). 자동 칸 아홉은 사람이 적은 값만 담고, 비면 화면이
원본에서 그때그때 읽는다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다(0107 과 같다).

## 되돌리기

표가 사라진다. 사람이 적은 줄과 값도 함께 사라진다 — 다른 표는 이 표를
가리키지 않는다.

Revision ID: 0108_revenue_forecasts
Revises: 0107_deal_followup
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0108_revenue_forecasts"
down_revision = "0107_deal_followup"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "revenue_forecasts" in _tables():
        return
    op.create_table(
        "revenue_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("firm", sa.String(), nullable=True),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("ir_company_id", sa.Integer(),
                  sa.ForeignKey("ir_companies.id"), nullable=True),
        *[sa.Column(name, sa.String(), nullable=True) for name in (
            "vc_name", "vc_phone", "ceo_name", "ceo_phone", "pre_value",
            "raise_target", "meeting_plan", "meeting1_done", "meeting2_done",
            "post_value", "ceo_share")],
        sa.Column("result_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    if "revenue_forecasts" in _tables():
        op.drop_table("revenue_forecasts")
