"""IR 자료를 전달한 **시각** — `ir_requests.delivered_time`

요청(11/12): "업무보고 > 상태 컬럼에 IR 전달 완료 우측에 년월일시 자동으로 들어가게".
날짜(`delivered_at`)는 전부터 적혀 있었고 시각은 어디에도 없었다. 전달하는 순간
(`pipeline.deliver`) 이 칸에 `HH:MM` 을 적는다 — 미팅의 `scheduled_time` 과 같은 꼴.

비워 둔다 — 지금 줄은 몇 시에 전달했는지 모른다. 업무 보고는 그 줄에 날짜만 붙인다.
빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(업무 보고가 다시 날짜만 보인다 — 줄은 그대로다).

Revision ID: 0137_ir_delivered_time
Revises: 0136_no_reaction_cleared
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0137_ir_delivered_time"
down_revision = "0136_no_reaction_cleared"
branch_labels = None
depends_on = None

TABLE = "ir_requests"
COLUMN = "delivered_time"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if have and COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
