"""핵심 / TOP 을 갈라 둔다

시트의 `핵심/TOP Deal` 칸에는 `핵심`(13) · `TOP`(11) · 둘 다(2) 가 들어 있다.
켜짐/꺼짐 하나로는 어느 쪽인지 구분할 수 없다.

`is_top_deal` 은 그대로 둔다 — 발송 화면의 '추천 딜' 이 그 값을 쓴다.
둘 중 하나라도 적히면 켜진다.

Revision ID: 0021_top_deal_kind
Revises: 0020_business_desc
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_top_deal_kind"
down_revision = "0020_business_desc"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있으면 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    # 뒷채움도 **칸을 이번에 만들었을 때만** 돈다. 다시 돌린 DB 에서 이 UPDATE 가
    # 또 돌면, 사람이 화면에서 `TOP` 으로 고쳐 둔 것을 `핵심` 으로 되돌린다.
    if not _has_column("ir_companies", "top_deal_kind"):
        op.add_column("ir_companies",
                      sa.Column("top_deal_kind", sa.String(), nullable=True))
        # 이미 켜져 있던 것은 '핵심' 으로 본다 — 시트에서 더 많은 쪽이다.
        op.execute("UPDATE ir_companies SET top_deal_kind = '핵심' WHERE is_top_deal = 1")


def downgrade() -> None:
    if _has_column("ir_companies", "top_deal_kind"):
        op.drop_column("ir_companies", "top_deal_kind")
