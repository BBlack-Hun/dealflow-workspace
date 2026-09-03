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


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    have = _columns("send_items")
    if "channel" not in have:
        op.add_column("send_items", sa.Column("channel", sa.String(), nullable=False,
                                              server_default="kakao"))
    if "subject" not in have:
        op.add_column("send_items", sa.Column("subject", sa.String(), nullable=True))

    # **인덱스는 칸을 붙이는 것과 따로 본다.** 빈 DB 는 0001 의 `create_all()` 이
    # 칸까지 이미 만들어 둔 채로 오는데, 모델에는 이 인덱스가 선언돼 있지 않다.
    # 칸 만들기 안에 넣어 두면 그 길에서 통째로 건너뛰어, **새 서버만 인덱스
    # 없이** 도는 DB 가 된다(0005 가 쓰는 방식).
    #
    # 에이전트 폴링이 매번 타는 조건이라 인덱스를 둔다.
    if not _has_index("send_items", "ix_send_items_channel"):
        op.create_index("ix_send_items_channel", "send_items", ["job_id", "channel"])


def downgrade() -> None:
    have = _columns("send_items")
    if "subject" in have:
        op.drop_column("send_items", "subject")
    if _has_index("send_items", "ix_send_items_channel"):
        op.drop_index("ix_send_items_channel", table_name="send_items")
    if "channel" in have:
        op.drop_column("send_items", "channel")
