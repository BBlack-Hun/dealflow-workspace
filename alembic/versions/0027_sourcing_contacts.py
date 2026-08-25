"""딜 소싱 참여 심사역

투자사 관리 현황(딜소개를 **보내는** 명단)과는 성격이 다르다. 여기는
"우리 딜을 같이 볼 사람" 이라 시리즈 A 이상·개인 참여·M&A·후속투자처럼
**찾는 것**으로 나뉜다.

Revision ID: 0027_sourcing_contacts
Revises: 0026_fix_misfiled_template
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_sourcing_contacts"
down_revision = "0026_fix_misfiled_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sourcing_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bucket", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("firm", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("assignee_name", sa.String(), nullable=True),
        sa.Column("requested_at", sa.String(), nullable=True),
        sa.Column("share_method", sa.String(), nullable=True),
        sa.Column("sectors", sa.String(), nullable=True),
        sa.Column("round_size", sa.String(), nullable=True),
        sa.Column("tips", sa.String(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("kakao_reply", sa.Text(), nullable=True),
        sa.Column("call_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
    )
    op.create_index("ix_sourcing_bucket", "sourcing_contacts", ["bucket"])


def downgrade() -> None:
    op.drop_index("ix_sourcing_bucket", table_name="sourcing_contacts")
    op.drop_table("sourcing_contacts")
