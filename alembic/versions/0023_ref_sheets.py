"""참고 시트 — 원본 스프레드시트의 '자료' 탭들

투자사 명단 말고도 시트에는 스크립트·가이드·성격 정리 탭이 여럿 있었다.
매번 구글 시트를 따로 열어 보던 자료라 화면 안으로 들여온다.

지울 수 있게 둔다 — 다 옮겨 놓고 쓰면서 추리는 것이 순서다.

Revision ID: 0023_ref_sheets
Revises: 0022_routine_time_of_day
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_ref_sheets"
down_revision = "0022_routine_time_of_day"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ref_sheets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="text"),
        sa.Column("content_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ref_sheets")
