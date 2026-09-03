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


# 시트 표기가 자유 문장이다("전화완료 / 부재중" 등) — 원문을 보존한다.
NEW = ("sourcing_note", "tips_note")


def _columns(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있는 칸은 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    have = _columns("vc_contacts")
    missing = [name for name in NEW if name not in have]
    if missing:
        with op.batch_alter_table("vc_contacts") as b:
            for name in missing:
                b.add_column(sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    have = _columns("vc_contacts")
    present = [name for name in reversed(NEW) if name in have]
    if present:
        with op.batch_alter_table("vc_contacts") as b:
            for name in present:
                b.drop_column(name)
