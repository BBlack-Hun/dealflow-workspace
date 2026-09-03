"""스타트업DB 의 '수신일' 칸

홍보메일을 보내면 답장이 오고, 그 **받은 날짜**를 팀원이 손으로 적는다.
시트에서는 맨 앞 칸인데 앱에는 이 칸이 아예 없어서, 그 뒤가 통째로 한 칸씩
밀려 보였다(시트와 나란히 놓고 대조할 때마다 눈이 어긋난다).

날짜지만 문자열로 둔다 — 시트에 `2025-01-07` 도 있고 비어 있는 줄도 많다.

Revision ID: 0031_company_received_at
Revises: 0030_consulting_owner
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_company_received_at"
down_revision = "0030_consulting_owner"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있으면 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    if not _has_column("ir_companies", "received_at"):
        with op.batch_alter_table("ir_companies") as b:
            b.add_column(sa.Column("received_at", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("ir_companies", "received_at"):
        with op.batch_alter_table("ir_companies") as b:
            b.drop_column("received_at")
