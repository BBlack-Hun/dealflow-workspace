"""투자사 줄 연락 채널에 `문자` — `vc_contacts.channel_sms`

요청: "팀원 중에 문자로도 딜 소개를 하는 경우가 있음. 연락 채널에 카톡, 메일이 있는데,
문자도 추가!" 앱의 문자 발송은 11/01 에 걷었다 — 이 칸은 **팀원이 휴대폰으로 직접 문자를
보내는 투자사**라는 표시일 뿐이다. 카톡·메일이 다 꺼지고 이것만 켜진 줄은 자동 발송에서
빠지고 카톡방 상태가 `문자(직접 발송)` 으로 선다(`dashboard._room_state`).

`0` 으로 채운다 — 지금 줄은 전부 문자 표시가 없던 줄이라 동작이 그대로다. 빈 DB 는
`0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(그 표시만 사라지고 줄은 그대로다).

Revision ID: 0130_channel_sms
Revises: 0129_contract_ym
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0130_channel_sms"
down_revision = "0129_contract_ym"
branch_labels = None
depends_on = None

TABLE = "vc_contacts"
COLUMN = "channel_sms"


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
