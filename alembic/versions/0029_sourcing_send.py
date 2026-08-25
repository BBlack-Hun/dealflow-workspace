"""딜 소싱 제안을 실제로 보낼 수 있게 한다

소싱 명단은 투자사 관리 현황과 겹치지 않는다(39명 중 7명만 겹친다). 그래서
"기존 담당자를 찾아 붙인다"로는 32명에게 못 보낸다 — 소싱 명단도 자기
카톡방을 가져야 한다.

발송 건(`send_items`)은 지금까지 투자사 담당자만 가리켰다. 소싱 대상은 다른
표에 있으므로 가리키는 칸을 하나 더 두고, 둘 중 **하나만** 채운다.
`contact_id` 가 비게 되는 것은 이 때문이다.

Revision ID: 0029_sourcing_send
Revises: 0028_consulting_sheets
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_sourcing_send"
down_revision = "0028_consulting_sheets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sourcing_contacts") as b:
        b.add_column(sa.Column("kakao_room_name", sa.String(), nullable=True))
        b.add_column(sa.Column("room_verified", sa.String(),
                               nullable=False, server_default="unverified"))

    # 소싱 대상을 가리키는 칸. 기존 건은 전부 투자사 담당자라 NULL 로 남는다.
    with op.batch_alter_table("send_items") as b:
        b.add_column(sa.Column("sourcing_contact_id", sa.Integer(), nullable=True))
        # 소싱 건은 투자사 담당자가 없다. 여기를 열어 주지 않으면 소싱 발송이
        # 아예 저장되지 않는다.
        b.alter_column("contact_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # 되돌리기 전에 소싱 건을 지운다 — 남겨 두면 contact_id 가 NULL 인 채로
    # NOT NULL 을 다시 걸게 되어 되돌리기 자체가 실패한다.
    op.execute("DELETE FROM send_items WHERE contact_id IS NULL")
    with op.batch_alter_table("send_items") as b:
        b.alter_column("contact_id", existing_type=sa.Integer(), nullable=False)
        b.drop_column("sourcing_contact_id")

    with op.batch_alter_table("sourcing_contacts") as b:
        b.drop_column("room_verified")
        b.drop_column("kakao_room_name")
