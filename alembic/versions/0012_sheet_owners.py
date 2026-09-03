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


def downgrade() -> None:
    # **이 판에는 원래 `downgrade` 가 아예 없었다.** 알렘빅은 되돌릴 길을
    # 짤 때 판마다 이 함수를 찾는데, 하나라도 없으면 `AttributeError` 로
    # **그 판을 지나가는 되돌리기 전체가 서지 않는다** — 0013 이후를 한 칸만
    # 내리려 해도 계획 단계에서 멎는다.
    if "sheet_owners" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("sheet_owners")
