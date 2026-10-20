"""한 발송기로 두 계정 보내기 — `users.send_via_user_id`

한 PC 의 한 카톡에 두 계정의 발송기가 붙어 있으면 서로 부딪친다. 비어 있으면
지금처럼 본인 발송기, 값이 있으면 그 계정의 발송기가 이 계정의 잡을 집어간다
(`routers/agent_api.poll`). 관리자가 팀 현황에서 정한다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 칸이 있는지 보고
붙인다(0111 과 같다).

## 되돌리기

칸을 뗀다. 맡겨 둔 계정은 다시 본인 발송기로 보낸다 — 그 PC 에서 그 계정의
발송기를 다시 켜야 나간다.

Revision ID: 0113_send_via_agent
Revises: 0112_series_a_fields
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0113_send_via_agent"
down_revision = "0112_series_a_fields"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if "users" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("users")}


def upgrade() -> None:
    have = _columns()
    if have and "send_via_user_id" not in have:
        op.add_column("users", sa.Column("send_via_user_id", sa.Integer(),
                                         nullable=True))


def downgrade() -> None:
    if "send_via_user_id" in _columns():
        with op.batch_alter_table("users") as batch:
            batch.drop_column("send_via_user_id")
