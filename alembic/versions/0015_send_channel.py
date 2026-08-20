"""발송 채널 (카톡 · 메일)

메일은 카톡과 **나가는 길이 다르다**. 카톡은 각자 PC 의 발송 프로그램이 창을 눌러
보내지만 메일은 서버가 SMTP 로 바로 보낸다. 이 값이 없으면 메일 건을 카톡 프로그램이
집어가 방을 찾다가 실패한다.

Revision ID: 0015_send_channel
Revises: 0014_ir_requests_meetings
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_send_channel"
down_revision = "0014_ir_requests_meetings"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    have = _columns("send_items")
    if "channel" not in have:
        op.add_column("send_items", sa.Column("channel", sa.String(), nullable=False,
                                              server_default="kakao"))
        # 에이전트 폴링이 매번 타는 조건이라 인덱스를 함께 둔다.
        op.create_index("ix_send_items_channel", "send_items", ["job_id", "channel"])
    if "subject" not in have:
        op.add_column("send_items", sa.Column("subject", sa.String(), nullable=True))


def downgrade() -> None:
    have = _columns("send_items")
    if "subject" in have:
        op.drop_column("send_items", "subject")
    if "channel" in have:
        op.drop_index("ix_send_items_channel", table_name="send_items")
        op.drop_column("send_items", "channel")
