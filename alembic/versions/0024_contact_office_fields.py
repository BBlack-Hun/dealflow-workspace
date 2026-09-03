"""시트에 있는데 앱에 칸이 없던 값들

근무처 팩스(162건) · 명함 등록일(257건)이 시트에 있는데 앱에 담을 곳이
없어 임포트할 때마다 통째로 버려졌다.

"명함 받은 날" 은 언제부터 아는 사이인지를 말해 준다 — 오래 알던 분께
처음 연락하는 문구를 보내면 어색하다.

Revision ID: 0024_contact_office_fields
Revises: 0023_ref_sheets
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_contact_office_fields"
down_revision = "0023_ref_sheets"
branch_labels = None
depends_on = None

NEW = [("office_fax", sa.String()), ("card_registered_at", sa.String())]


def _columns(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있는 칸은 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    have = _columns("vc_contacts")
    for name, kind in NEW:
        if name not in have:
            op.add_column("vc_contacts", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    have = _columns("vc_contacts")
    for name, _kind in reversed(NEW):
        if name in have:
            op.drop_column("vc_contacts", name)
