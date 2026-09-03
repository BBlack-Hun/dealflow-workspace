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


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


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

    # **인덱스는 표를 만드는 것과 따로 본다.** 빈 DB 는 0001 의
    # `create_all()` 이 표를 이미 만들어 둔 채로 오는데, 모델에는 이 인덱스가
    # 선언돼 있지 않다. 표 만들기 안에 넣어 두면 그 길에서 통째로 건너뛰어,
    # **새 서버만 인덱스 없이** 도는 DB 가 된다(0005 가 쓰는 방식).
    #
    # 화면이 매번 타는 경로: 내 것 중 열린 요청 / 다가오는 미팅
    for table, name, cols in (
        ("ir_requests", "ix_ir_requests_user_status", ["user_id", "status"]),
        ("ir_requests", "ix_ir_requests_contact", ["contact_id"]),
        ("meetings", "ix_meetings_user_status", ["user_id", "status"]),
        ("meetings", "ix_meetings_due", ["followup_due"]),
    ):
        if not _has_index(table, name):
            op.create_index(name, table, cols)


def downgrade() -> None:
    have = _tables()
    if "meetings" in have:
        op.drop_table("meetings")
    if "ir_requests" in have:
        op.drop_table("ir_requests")
