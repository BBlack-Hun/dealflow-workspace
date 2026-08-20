"""IR 요청 · 미팅

딜소개를 보내면 "이 기업 자료 주세요" 하는 답이 온다. 받은 것을 놓치면 그 회차에서
가장 뜨거운 반응을 흘려보내는 셈이다. 미팅은 끝나고 **열흘 뒤 결과를 물어야** 하는데
그걸 사람이 기억하고 있었다.

Revision ID: 0014_ir_requests_meetings
Revises: 0013_extra_send_dates
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_ir_requests_meetings"
down_revision = "0013_extra_send_dates"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "ir_requests" not in have:
        op.create_table(
            "ir_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("contact_id", sa.Integer(), sa.ForeignKey("vc_contacts.id"), nullable=False),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("ir_companies.id"), nullable=True),
            sa.Column("company_name", sa.String(), nullable=False),
            sa.Column("requested_at", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="open"),
            sa.Column("delivered_at", sa.String(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
        # 화면이 매번 타는 경로: 내 것 중 열린 요청
        op.create_index("ix_ir_requests_user_status", "ir_requests", ["user_id", "status"])
        op.create_index("ix_ir_requests_contact", "ir_requests", ["contact_id"])

    if "meetings" not in have:
        op.create_table(
            "meetings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("contact_id", sa.Integer(), sa.ForeignKey("vc_contacts.id"), nullable=False),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("ir_companies.id"), nullable=True),
            sa.Column("company_name", sa.String(), nullable=True),
            sa.Column("scheduled_at", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False, server_default="first"),
            sa.Column("status", sa.String(), nullable=False, server_default="scheduled"),
            sa.Column("done_at", sa.String(), nullable=True),
            sa.Column("outcome", sa.String(), nullable=True),
            sa.Column("followup_due", sa.String(), nullable=True),
            sa.Column("followup_done", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
        op.create_index("ix_meetings_user_status", "meetings", ["user_id", "status"])
        op.create_index("ix_meetings_due", "meetings", ["followup_due"])


def downgrade() -> None:
    have = _tables()
    if "meetings" in have:
        op.drop_table("meetings")
    if "ir_requests" in have:
        op.drop_table("ir_requests")
