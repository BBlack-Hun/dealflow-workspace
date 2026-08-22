"""발송 한 건을 여러 통으로 나눠 보낸다

IR 자료 전달은 링크를 먼저 한 통씩 던지고 마지막에 설명을 붙여야 한다.
카톡에서 링크는 각자 미리보기 카드로 떠야 하고, 설명이 그 아래 와야 읽힌다.

`send_items` 는 여전히 **사람당 한 줄**이다 — 진행 화면이 세는 것은
'몇 통 보냈나' 가 아니라 '몇 명에게 보냈나' 이기 때문이다.

Revision ID: 0018_send_item_parts
Revises: 0017_ir_delivery_links
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_send_item_parts"
down_revision = "0017_ir_delivery_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("send_items", sa.Column("parts_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("send_items", "parts_json")
