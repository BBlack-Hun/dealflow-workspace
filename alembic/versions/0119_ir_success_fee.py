"""IR 기업 현황 새 칸 — 성공보수율(결정 10 · 기업 동기화 2단계)

투자컨설턴트 `월간 계약 업무현황표` 탭 · 스타트업 명단 수정창에만 있던 `성공보수율` 을
IR 기업 현황(기준 표)에도 세운다. 이어진 줄끼리는 따라 고친다(`services/company_sync.py`).
계약금은 옮기지 않는다 — 계약 탭에만 둔다(결정 10).

NULL 이고 기본값이 없다 — 빈칸이 곧 `아직 안 정함` 이다. 값 옮기기는 이주가 아니라
`scripts/company_sync_fill.py`(빈칸만 채움)가 한다.

빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다(0116 과 같다).
되돌리기: 칸을 뗀다. 컨설턴트 · 스타트업 줄의 같은 칸은 그대로다.

Revision ID: 0119_ir_success_fee
Revises: 0118_series_a_ir_file
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0119_ir_success_fee"
down_revision = "0118_series_a_ir_file"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if "ir_companies" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("ir_companies")}


def upgrade() -> None:
    have = _columns()
    if have and "success_fee" not in have:
        op.add_column("ir_companies", sa.Column("success_fee", sa.String(), nullable=True))


def downgrade() -> None:
    if "success_fee" in _columns():
        with op.batch_alter_table("ir_companies") as batch:
            batch.drop_column("success_fee")
