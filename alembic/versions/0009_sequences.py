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
        # 화면이 매번 타는 경로: 내 것 중 예약된 것, 그리고 담당자별 진행 중 시퀀스
        op.create_index("ix_send_sequences_user_status", "send_sequences",
                        ["user_id", "status"])
        op.create_index("ix_send_sequences_contact", "send_sequences", ["contact_id"])
        op.create_index("ix_send_sequences_due", "send_sequences", ["next_due_date"])


def downgrade() -> None:
    have = _tables()
    if "send_sequences" in have:
        op.drop_table("send_sequences")
    if "schedule_rules" in have:
        op.drop_table("schedule_rules")
