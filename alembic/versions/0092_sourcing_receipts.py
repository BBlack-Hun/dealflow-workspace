"""딜 소싱 — 달마다 '딜 받음' 표시 · 카톡방 후보

- 표 `sourcing_receipts` — (사람, 달) 마다 '이 달 딜을 받았다' 한 줄. 소싱
  리마인드가 아직 안 준 사람에게만 나가게 한다(`models.SourcingReceipt`).
- 칸 `sourcing_contacts.room_candidates` — [방 후보 찾기] 가 카톡에서 찾아 온
  방 제목들(JSON). 사람이 골라 확정해야 방 이름이 된다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다(0078 · 0085 와 같은 방식). 유일 색인은 표를 만드는 `if` **밖에서**
따로 본다.

## 되돌리기

표와 칸이 사라진다 — 잃는 것은 '딜 받음' 표시와 후보 목록뿐이다. 확정한 방
이름은 `kakao_room_name` 에 남는다.

Revision ID: 0092_sourcing_receipts
Revises: 0091_sender_rooms
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0092_sourcing_receipts"
down_revision = "0091_sender_rooms"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    if "sourcing_receipts" not in _tables():
        op.create_table(
            "sourcing_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("sourcing_contact_id", sa.Integer(),
                      sa.ForeignKey("sourcing_contacts.id"), nullable=False),
            sa.Column("month", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False,
                      server_default="manual"),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
        )
    if "uq_sourcing_receipts_month" not in _indexes("sourcing_receipts"):
        op.create_index("uq_sourcing_receipts_month", "sourcing_receipts",
                        ["sourcing_contact_id", "month"], unique=True)
    have = _columns("sourcing_contacts")
    if have and "room_candidates" not in have:
        op.add_column("sourcing_contacts",
                      sa.Column("room_candidates", sa.Text(), nullable=True))


def downgrade() -> None:
    if "room_candidates" in _columns("sourcing_contacts"):
        with op.batch_alter_table("sourcing_contacts") as batch:
            batch.drop_column("room_candidates")
    if "uq_sourcing_receipts_month" in _indexes("sourcing_receipts"):
        op.drop_index("uq_sourcing_receipts_month", table_name="sourcing_receipts")
    if "sourcing_receipts" in _tables():
        op.drop_table("sourcing_receipts")
