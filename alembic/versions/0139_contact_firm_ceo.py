"""투자사 대표님 표시 — `vc_contacts.is_firm_ceo`

요청(11/27): "딜소개 드리는 분들중에서 투자사 대표님은 그룹웨어에 별도로 기입 … 표시가
좀 눈에 띄어야 함". 직함 칸 글자로 가르면 `부대표` · 겸직 직함을 손으로 바로잡을 길이
없어, 사람이 고르는 O/X 칸으로 둔다. 1 이면 투자사 관리 현황 표의 이름 옆에 [대표]
배지가 선다. 발송 문구(인사말 `{직함}` 등)는 이 칸을 읽지 않는다.

0 으로 채운다 — 처음 값은 화면이나 앱 저장 길로 넣는다. 빈 DB 는 `0001_initial` 이
`create_all()` 로 만든다 — 칸이 있는지 보고 붙인다. 되돌리기: 칸을 뗀다(배지·칸이
사라질 뿐 줄은 그대로다).

Revision ID: 0139_contact_firm_ceo
Revises: 0138_send_item_room_candidates
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0139_contact_firm_ceo"
down_revision = "0138_send_item_room_candidates"
branch_labels = None
depends_on = None

TABLE = "vc_contacts"
COLUMN = "is_firm_ceo"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if have and COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=False,
                                       server_default="0"))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
