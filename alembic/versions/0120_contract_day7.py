"""계약 Day7 우편 발송(#9) — IR 기업 `계약 완료로 바뀐 날` · 팀원 `받을 카톡방` 칸

- `ir_companies.contract_done_at` — 계약여부가 계약 완료(무료/유료)로 바뀐 날(`YYYY-MM-DD`).
  flush 한 자리가 적는다(`services/automations/contract_day7.before_flush`).
  **채워 넣지 않는다** — 지금 계약 완료인 기업은 비어 있어 자동화에 안 걸린다(기존
  계약 기업에는 보내지 않는다 · 사용자 결정).
- `users.kakao_room_name` — 그 팀원에게 알릴 카톡방 제목(자동 발송 계정 카톡 기준).
  팀 현황 › 자동화 판에서 넣는다.

둘 다 NULL 이고 기본값이 없다. 빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 —
칸이 있는지 보고 붙인다(0119 와 같다). 되돌리기: 칸을 뗀다.

Revision ID: 0120_contract_day7
Revises: 0119_ir_success_fee
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0120_contract_day7"
down_revision = "0119_ir_success_fee"
branch_labels = None
depends_on = None

COLUMNS = (("ir_companies", "contract_done_at"), ("users", "kakao_room_name"))


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    for table, column in COLUMNS:
        have = _columns(table)
        if have and column not in have:
            op.add_column(table, sa.Column(column, sa.String(), nullable=True))


def downgrade() -> None:
    for table, column in COLUMNS:
        if column in _columns(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
