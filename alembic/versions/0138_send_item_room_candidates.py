"""투자사 [방 연결 확인]이 찾은 방 제목 — `send_items.room_candidates`

요청(11/13): "방 찾기를 했을 때 찾아진 방이 있잖아? 그 방 이름이 사유에 나오게 되는데,
자동으로 연결 안 해 줄 거면 그걸 클릭해서 카톡방에 입력 후 해당 투자사만 재검사".
찾은 제목은 사유 글에만 잘려 적혀 있었다(`vc_room_search._shown` — 셋까지 · 60자).
그 글을 쪼개 읽지 않고, 발송기가 올린 제목을 건에 JSON 으로 담는다(`save_rooms`).

비워 둔다 — 이 칸 전에 끝난 건은 후보를 모른다(진행 화면에 단추가 안 선다. 사유 글은
그대로 보인다). 빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고
붙인다. 되돌리기: 칸을 뗀다(단추가 사라질 뿐 건 · 줄은 그대로다).

Revision ID: 0138_send_item_room_candidates
Revises: 0137_ir_delivered_time
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0138_send_item_room_candidates"
down_revision = "0137_ir_delivered_time"
branch_labels = None
depends_on = None

TABLE = "send_items"
COLUMN = "room_candidates"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if have and COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
