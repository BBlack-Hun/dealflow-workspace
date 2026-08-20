"""명단(시트)별 담당 팀원

담당은 사람이 아니라 **명단 단위**로 정해진다. 그렇게 두지 않으면 시트를 올린
사람에게 팀 전체가 붙는다 — 실제로 한 사람의 대시보드에 333명이 '내 담당'으로
잡혔다(본인 담당은 126명).

Revision ID: 0012_sheet_owners
Revises: 0011_assignee_and_firm_type
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_sheet_owners"
down_revision = "0011_assignee_and_firm_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "sheet_owners" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "sheet_owners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assignee_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
    )
