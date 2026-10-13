"""보내는 계정 카톡 기준 방 제목 — 표 하나

`sender_rooms` — (보내는 계정, 담당자) 마다 그 계정 카톡에서의 방 제목과 후보.
카톡 단톡방 제목은 사람마다 따로 바꿀 수 있어서, 담당 팀원이 적어 둔 제목과
자동화를 보내는 계정 카톡의 제목이 다를 수 있다(`models.SenderRoom`).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다. 유일 색인은 표를 만드는 `if` **밖에서** 따로 본다(0078 과 같다).

## 되돌리기

표가 사라진다. 자동화는 담당 팀원이 적어 둔 제목으로 돌아간다 — 그 칸은 이
표가 건드린 적이 없다.

Revision ID: 0090_sender_rooms
Revises: 0089_automation_sends
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0090_sender_rooms"
down_revision = "0089_automation_sends"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    if "sender_rooms" not in _tables():
        op.create_table(
            "sender_rooms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
            sa.Column("contact_id", sa.Integer(),
                      sa.ForeignKey("vc_contacts.id"), nullable=False),
            sa.Column("room_name", sa.String(), nullable=True),
            sa.Column("verified", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("candidates", sa.Text(), nullable=True),
            sa.Column("checked_at", sa.String(), nullable=True),
        )
    if "uq_sender_rooms_pair" not in _indexes("sender_rooms"):
        op.create_index("uq_sender_rooms_pair", "sender_rooms",
                        ["sender_user_id", "contact_id"], unique=True)


def downgrade() -> None:
    if "uq_sender_rooms_pair" in _indexes("sender_rooms"):
        op.drop_index("uq_sender_rooms_pair", table_name="sender_rooms")
    if "sender_rooms" in _tables():
        op.drop_table("sender_rooms")
