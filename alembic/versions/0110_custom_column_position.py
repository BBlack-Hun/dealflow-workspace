"""추가 칸의 자리 — `custom_columns.after_key`

관리자가 `컬럼 관리` 에서 칸마다 **어느 기존 칸 뒤에 둘지** 고른다. 값은 그 기존
칸의 머리글 이름이다(`services/custom_columns.anchors`). 비어 있으면 지금처럼
표 오른쪽 끝에 선다 — 그래서 이미 붙은 칸은 이 판을 지나도 자리가 그대로다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 칸이 있는지 보고
붙인다(0106 과 같다).

## 되돌리기

칸을 뗀다. 잃는 것은 고른 자리뿐이고, 칸과 적힌 값은 그대로 남아 맨 끝에 선다.

Revision ID: 0110_custom_column_position
Revises: 0109_custom_columns
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0110_custom_column_position"
down_revision = "0109_custom_columns"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if "custom_columns" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("custom_columns")}


def upgrade() -> None:
    have = _columns()
    if have and "after_key" not in have:
        op.add_column("custom_columns",
                      sa.Column("after_key", sa.String(), nullable=True))


def downgrade() -> None:
    if "after_key" in _columns():
        with op.batch_alter_table("custom_columns") as batch:
            batch.drop_column("after_key")
