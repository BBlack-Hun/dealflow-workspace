"""표에 붙이는 추가 칸 — 표 둘(개선 과제 #6 · #7 · #8 · #12 · #46)

`custom_columns` — 관리자가 화면에 붙인 칸(이름 · 형식 메모/OX · 차례 · 숨김).
`custom_column_values` — 칸 하나 × 줄 하나의 값(`models.CustomColumnValue`).

**기존 표는 손대지 않는다.** 값은 줄의 표에 칸을 더하지 않고 따로 둔다 — 까닭은
`models.CustomColumnValue` 머리말에.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다(0108 과 같다).

## 되돌리기

두 표가 사라진다. 관리자가 붙인 칸과 팀원이 적은 값도 함께 사라진다 — 다른
표는 이 두 표를 가리키지 않는다.

Revision ID: 0109_custom_columns
Revises: 0108_revenue_forecasts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0109_custom_columns"
down_revision = "0108_revenue_forecasts"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "custom_columns" not in have:
        op.create_table(
            "custom_columns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("target", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("is_hidden", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.UniqueConstraint("target", "name",
                                name="uq_custom_columns_target_name"),
        )
    if "custom_column_values" not in have:
        op.create_table(
            "custom_column_values",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("column_id", sa.Integer(),
                      sa.ForeignKey("custom_columns.id"), nullable=False),
            sa.Column("row_table", sa.String(), nullable=False),
            sa.Column("row_id", sa.Integer(), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.UniqueConstraint("column_id", "row_table", "row_id",
                                name="uq_custom_column_values_cell"),
        )
        op.create_index("ix_custom_column_values_row", "custom_column_values",
                        ["row_table", "row_id"])


def downgrade() -> None:
    have = _tables()
    if "custom_column_values" in have:
        op.drop_index("ix_custom_column_values_row",
                      table_name="custom_column_values")
        op.drop_table("custom_column_values")
    if "custom_columns" in have:
        op.drop_table("custom_columns")
