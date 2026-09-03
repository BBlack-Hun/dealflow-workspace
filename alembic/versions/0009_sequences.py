"""후속 캐던스 — 발송 주기 규칙 + 담당자별 후속 흐름

주기("매월 첫째·셋째 수요일", "6~7일 뒤 리마인드")를 코드에 박아 두면 바뀔 때마다
배포해야 한다. 실제로 '매주'에서 '월 2회'로 한 번 바뀌었다. DB 로 옮긴다.

Revision ID: 0009_sequences
Revises: 0008_consulting_tables
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_sequences"
down_revision = "0008_consulting_tables"
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
    if "schedule_rules" not in have:
        op.create_table(
            "schedule_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(), nullable=False, unique=True),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("weekday", sa.Integer(), nullable=True),
            sa.Column("nth_weeks", sa.String(), nullable=True),
            sa.Column("offset_min_days", sa.Integer(), nullable=True),
            sa.Column("offset_max_days", sa.Integer(), nullable=True),
            sa.Column("skip_weekend", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("effective_from", sa.String(), nullable=True),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    if "send_sequences" not in have:
        op.create_table(
            "send_sequences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("contact_id", sa.Integer(), sa.ForeignKey("vc_contacts.id"), nullable=False),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("deal_batches.id"), nullable=True),
            sa.Column("stage", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("day1_sent_at", sa.String(), nullable=True),
            sa.Column("last_sent_at", sa.String(), nullable=True),
            sa.Column("next_stage", sa.Integer(), nullable=True),
            sa.Column("next_due_date", sa.String(), nullable=True),
            sa.Column("stopped_reason", sa.String(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )

    # **인덱스는 표를 만드는 것과 따로 본다.** 빈 DB 는 0001 의
    # `create_all()` 이 표를 이미 만들어 둔 채로 오는데, 모델에는 이 인덱스가
    # 선언돼 있지 않다. 표 만들기 안에 넣어 두면 그 길에서 통째로 건너뛰어,
    # **새 서버만 인덱스 없이** 도는 DB 가 된다(0005 가 쓰는 방식).
    #
    # 화면이 매번 타는 경로: 내 것 중 예약된 것, 그리고 담당자별 진행 중 시퀀스
    for name, cols in (("ix_send_sequences_user_status", ["user_id", "status"]),
                       ("ix_send_sequences_contact", ["contact_id"]),
                       ("ix_send_sequences_due", ["next_due_date"])):
        if not _has_index("send_sequences", name):
            op.create_index(name, "send_sequences", cols)


def downgrade() -> None:
    have = _tables()
    if "send_sequences" in have:
        op.drop_table("send_sequences")
    if "schedule_rules" in have:
        op.drop_table("schedule_rules")
