"""참고 자료가 어느 화면에 붙는가

참고 탭은 지금까지 투자사 관리 현황에만 붙었다. 투자컨설턴트 현황에도
스크립트·가이드가 있는데(미팅 진행 프로세스 · 견적서 발송 톡 …) 붙일 자리가
없었다.

기존 자료는 전부 투자사 관리 현황 것이다.

Revision ID: 0033_ref_sheet_page
Revises: 0032_contact_sheet_columns
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_ref_sheet_page"
down_revision = "0032_contact_sheet_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ref_sheets") as b:
        b.add_column(sa.Column("page", sa.String(), nullable=False,
                               server_default="contacts"))


def downgrade() -> None:
    with op.batch_alter_table("ref_sheets") as b:
        b.drop_column("page")
