"""사람이 확정한 잇기 — `sourcing_contacts.vc_link_confirmed`

딜 소싱 › 시리즈 A 갈래 줄과 투자사 관리 현황 줄의 잇기(`vc_contact_id`, 0093)를
**사람이 [이 분으로 확정]으로 정했는지**(1) · 앱이 저절로 이었는지(0) 적는 칸이다
(#28). 시트를 다시 가져오면(`scripts/import_sourcing.py`) 갈래를 통째로 갈아 끼워
잇기가 사라지는데, 저절로 이은 줄은 같은 규칙(이름 + 번호)으로 다시 이어지지만
사람이 확정한 줄은 그 규칙에 안 맞아 다시 후보로 떴다. 이 표시로 그 줄만 기억해
되살린다(사용자 결정 2026-10-17).

처음에는 전부 0 이다 — 지금까지의 잇기는 이주(0093)와 저절로 잇기가 한 것이다.

## 이 판의 번호

`0103_template_apply_backups`(#306) 바로 뒤다. 그 PR 이 먼저 들어가야 한다.

## 빈 DB 에서는 만들지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다 — 있는지 보고 더한다
(0101 과 같은 방식).

## 되돌리기

칸째 지운다 — 잃는 것은 '사람이 확정했다' 는 표시뿐이다(잇기는 그대로 남는다).

Revision ID: 0104_sourcing_vc_link_confirmed
Revises: 0103_template_apply_backups
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0104_sourcing_vc_link_confirmed"
down_revision = "0103_template_apply_backups"
branch_labels = None
depends_on = None

TABLE = "sourcing_contacts"
COLUMN = "vc_link_confirmed"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=False,
                                       server_default="0"))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
