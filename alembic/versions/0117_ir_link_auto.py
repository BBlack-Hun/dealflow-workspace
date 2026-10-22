"""IR 기업 연결 — `자동 연결` 표시 칸(`ir_link_auto`)

스타트업 명단 줄 · 투자컨설턴트 줄이 **이름으로 저절로**(또는 [후보 하나 일괄 연결]로)
IR 기업에 이어졌는지를 적는다(10/22 결정 2 — 새 줄도 이름이 정확히 하나 맞으면
저절로 잇고, 화면에 `자동 연결` 을 보여 [연결 풀기]를 고를 수 있게 한다).
사람이 한 줄씩 [이 기업으로 연결]한 것은 0 이다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 칸이 있는지 보고
붙인다(0116 과 같다).

## 되돌리기

칸을 뗀다. 연결(`ir_company_id`)은 그대로 남고, `자동 연결` 표시만 사라진다.

Revision ID: 0117_ir_link_auto
Revises: 0116_ir_company_sync_columns
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0117_ir_link_auto"
down_revision = "0116_ir_company_sync_columns"
branch_labels = None
depends_on = None

TABLES = ("vc_contacts", "consulting_companies")


def _has(table: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return (table in inspector.get_table_names()
            and "ir_link_auto" in {c["name"] for c in inspector.get_columns(table)})


def upgrade() -> None:
    names = set(sa.inspect(op.get_bind()).get_table_names())
    for table in TABLES:
        if table in names and not _has(table):
            op.add_column(table, sa.Column("ir_link_auto", sa.Integer(), nullable=False,
                                           server_default="0"))


def downgrade() -> None:
    for table in TABLES:
        if _has(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column("ir_link_auto")
