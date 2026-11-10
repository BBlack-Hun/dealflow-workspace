"""보내는 계정 카톡 기준 방 제목 — 딜 소싱 명단 줄도 담는다

`sender_rooms` 는 (보내는 계정, 투자사 담당자) 마다 그 계정 카톡에서의 방 제목을
담았다. 딜 소싱 방 이름도 그 방을 찾아 확정한 팀원 카톡의 제목이라, 자동화를
보내는 계정 카톡에서는 다를 수 있다 — 같은 표에 **딜 소싱 줄을 가리키는 칸**을
하나 더 두고, 둘 중 **하나만** 채운다(`send_items` 가 0029 에서 한 것과 같다).
`contact_id` 가 비게 되는 것은 이 때문이다.

## 빈 DB 에서는 칸을 건드리지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델을 만든다 — 칸이 이미 있고 이미
비어도 되면 표를 다시 만들지 않는다. 유일 색인은 그 `if` **밖에서** 따로 본다.

## 되돌리기

딜 소싱 줄을 가리키는 줄을 지우고 칸을 뗀다. 자동화는 딜 소싱 명단에 적힌 방
이름으로 돌아간다 — 그 칸은 이 표가 건드린 적이 없다.

Revision ID: 0135_sender_room_sourcing
Revises: 0134_sheet_tab_position
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0135_sender_room_sourcing"
down_revision = "0134_sheet_tab_position"
branch_labels = None
depends_on = None

TABLE = "sender_rooms"
COLUMN = "sourcing_contact_id"
PAIR = "uq_sender_rooms_pair"
INDEX = "uq_sender_rooms_sourcing"


def _columns() -> dict:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return {}
    return {c["name"]: c for c in inspector.get_columns(TABLE)}


def _indexes() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(TABLE)}


def upgrade() -> None:
    have = _columns()
    if not have:
        return
    add_ref = COLUMN not in have
    open_null = have.get("contact_id", {}).get("nullable") is False
    if add_ref or open_null:
        # 표를 통째로 다시 만드는 일이라 **할 일이 있을 때만** 연다(0029 와 같다).
        with op.batch_alter_table(TABLE) as batch:
            if add_ref:
                # 이름 없는 외래 키는 표를 다시 만드는 길에서 받지 않는다(SQLite) —
                # `send_items.sourcing_contact_id`(0029)처럼 칸만 붙인다.
                batch.add_column(sa.Column(COLUMN, sa.Integer(), nullable=True))
            if open_null:
                batch.alter_column("contact_id", existing_type=sa.Integer(),
                                   nullable=True)
    # 다시 만든 표에서 이름 붙은 색인이 빠졌으면 되살린다.
    if PAIR not in _indexes():
        op.create_index(PAIR, TABLE, ["sender_user_id", "contact_id"], unique=True)
    if INDEX not in _indexes():
        op.create_index(INDEX, TABLE, ["sender_user_id", COLUMN], unique=True)


def downgrade() -> None:
    if INDEX in _indexes():
        op.drop_index(INDEX, table_name=TABLE)
    have = _columns()
    if not have:
        return
    # 딜 소싱 줄은 담당자가 없다 — 남겨 두면 NOT NULL 을 다시 걸 수 없다.
    op.execute(f"DELETE FROM {TABLE} WHERE contact_id IS NULL")
    drop_ref = COLUMN in have
    close_null = have.get("contact_id", {}).get("nullable") is True
    if drop_ref or close_null:
        with op.batch_alter_table(TABLE) as batch:
            if close_null:
                batch.alter_column("contact_id", existing_type=sa.Integer(),
                                   nullable=False)
            if drop_ref:
                batch.drop_column(COLUMN)
    if PAIR not in _indexes():
        op.create_index(PAIR, TABLE, ["sender_user_id", "contact_id"], unique=True)
