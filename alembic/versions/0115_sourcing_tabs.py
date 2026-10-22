"""딜 소싱 [+ 탭 추가] — 사람이 없어도 서는 탭 이름 `sourcing_tabs`

갈래(탭)는 `sourcing_contacts.bucket` 글자를 모아 세운다. 사람이 없는 새 탭은
설 자리가 없어서, 만든 탭의 이름만 이 표에 남긴다(`models.SourcingTab`).
있던 갈래는 옮기지 않는다 — 그 탭들은 지금처럼 줄에서 선다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고 만든다.

## 되돌리기

표가 사라진다. 사람을 넣은 탭은 줄에서 그대로 서고, 아직 비어 있던 탭만 안 보인다.

Revision ID: 0115_sourcing_tabs
Revises: 0114_sourcing_link_per_bucket
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0115_sourcing_tabs"
down_revision = "0114_sourcing_link_per_bucket"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "sourcing_tabs" not in _tables():
        op.create_table(
            "sourcing_tabs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.UniqueConstraint("name", name="uq_sourcing_tabs_name"),
        )


def downgrade() -> None:
    if "sourcing_tabs" in _tables():
        op.drop_table("sourcing_tabs")
