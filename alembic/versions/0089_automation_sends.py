"""2단계 자동화 — 대상마다 '보냈다' 표시, 표 하나

`automation_sends` — 자동화가 이 대상에게 보냈다는 줄. 열쇠는
`(automation, ref, test)` 이고 영구히 남는다(`models.AutomationSend`).
`auto_send_runs` 가 **회차**를 두 번 세우지 않게 한다면, 이 표는 그 안의
**대상**을 두 번 보내지 않게 한다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다. 유일 색인은 표를 만드는 `if` **밖에서** 따로 본다(0078 과 같다).

## 되돌리기

표가 사라진다 — 그러면 같은 대상에게 다시 보낼 수 있게 된다. 되돌리기 전에
자동화를 전부 끄는 것이 순서다.

Revision ID: 0089_automation_sends
Revises: 0088_automations
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0089_automation_sends"
down_revision = "0088_automations"
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
    if "automation_sends" not in _tables():
        op.create_table(
            "automation_sends",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("automation", sa.String(), nullable=False),
            sa.Column("ref", sa.String(), nullable=False),
            sa.Column("test", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("run_id", sa.Integer(),
                      sa.ForeignKey("auto_send_runs.id"), nullable=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("send_jobs.id"),
                      nullable=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("send_items.id"),
                      nullable=True),
            sa.Column("room", sa.String(), nullable=True),
            sa.Column("contact_id", sa.Integer(), nullable=True),
            sa.Column("sourcing_contact_id", sa.Integer(), nullable=True),
            sa.Column("company_id", sa.Integer(), nullable=True),
        )
    if "uq_automation_sends_ref" not in _indexes("automation_sends"):
        op.create_index("uq_automation_sends_ref", "automation_sends",
                        ["automation", "ref", "test"], unique=True)


def downgrade() -> None:
    if "uq_automation_sends_ref" in _indexes("automation_sends"):
        op.drop_index("uq_automation_sends_ref", table_name="automation_sends")
    if "automation_sends" in _tables():
        op.drop_table("automation_sends")
