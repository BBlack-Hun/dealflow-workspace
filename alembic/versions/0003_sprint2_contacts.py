"""Sprint 2: contact_activities + vc_contacts.invited_status

시트 A의 월별 3열 세트(1차 딜소개 / IR 자료 요청 / 미팅 요청)는 달이 갈수록
컬럼이 오른쪽으로 늘어난다(SHEET_FINDINGS §2). 이를 컬럼이 아니라 **행**으로
정규화해야 월이 늘어도 스키마가 그대로다 — contact_activities 가 그 그릇이다.

invited_status(초대완료여부)는 시트 A에만 있고 모델에 없던 필드다
(SHEET_FINDINGS §4 TODO). 카톡방 초대가 끝났는지가 발송 가능 여부의 선행 조건이라
담당자 행에 그대로 둔다.

Revision ID: 0003_sprint2_contacts
Revises: 0002_agent_sender
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_sprint2_contacts"
down_revision = "0002_agent_sender"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vc_contacts", sa.Column("invited_status", sa.String(), nullable=True))

    op.create_table(
        "contact_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("vc_contacts.id"), nullable=False),
        sa.Column("month", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("happened_at", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="import"),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
    )
    # 상세 패널 타임라인은 담당자 1명분을 최신순으로 읽는다.
    op.create_index("ix_contact_activities_contact", "contact_activities",
                    ["contact_id", "month"])


def downgrade() -> None:
    op.drop_index("ix_contact_activities_contact", table_name="contact_activities")
    op.drop_table("contact_activities")
    op.drop_column("vc_contacts", "invited_status")
