"""시트 담당자 원문 + 투자사 유형

**담당자 원문(assignee_name)**
명단 시트의 '담당자' 는 우리 팀원 이름이다. 그 이름의 계정이 아직 없으면
임포트한 사람에게 폴백으로 붙는데, 지금까지 그 사실이 어디에도 남지 않았다.
그래서 한 사람의 대시보드에 팀 전체 투자사가 '내 담당'으로 잡혔다.
이름을 그대로 보관해 두면 계정을 만든 뒤 제자리로 보낼 수 있다.

**투자사 유형(firm_type)**
엔젤·AC 는 초기를, PE·자산운용은 중후기를 본다. 유형을 모르고 목록을 보내면
초기 딜이 PE 에게 간다. 이름에서 추론하고 사람이 고친다.

Revision ID: 0011_assignee_and_firm_type
Revises: 0010_connect_stage
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_assignee_and_firm_type"
down_revision = "0010_connect_stage"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    have = _columns("vc_contacts")
    if "assignee_name" not in have:
        op.add_column("vc_contacts", sa.Column("assignee_name", sa.String(), nullable=True))
    if "firm_type" not in have:
        op.add_column("vc_contacts", sa.Column("firm_type", sa.String(), nullable=True))


def downgrade() -> None:
    have = _columns("vc_contacts")
    if "firm_type" in have:
        op.drop_column("vc_contacts", "firm_type")
    if "assignee_name" in have:
        op.drop_column("vc_contacts", "assignee_name")
