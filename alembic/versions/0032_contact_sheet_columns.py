"""투자사 명단 시트에만 있던 두 칸

`딜소싱 참여 투자사` 와 `TIPS 운영사 …` 는 시트에 있는데 앱에 칸이 없어서
화면에도 못 나오고 임포트에서도 버려졌다. 시트와 나란히 놓고 대조하면
그 자리만 비어 있다.

Revision ID: 0032_contact_sheet_columns
Revises: 0031_company_received_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_contact_sheet_columns"
down_revision = "0031_company_received_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("vc_contacts") as b:
        # 시트 표기가 자유 문장이다("전화완료 / 부재중" 등) — 원문을 보존한다.
        b.add_column(sa.Column("sourcing_note", sa.Text(), nullable=True))
        b.add_column(sa.Column("tips_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("vc_contacts") as b:
        b.drop_column("tips_note")
        b.drop_column("sourcing_note")
