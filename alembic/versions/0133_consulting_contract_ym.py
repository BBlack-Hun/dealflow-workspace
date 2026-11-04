"""투자컨설턴트 → `계약년월` 칸(`YYYY-MM`) — `consulting_companies.contract_ym`

11/04 개선 과제 #154: "투자컨설턴트 > 계약년월, 계약여부, 계약서수신여부, 성공보수률
등록일 컬럼 오른쪽에 쪼르륵 넣어 주세요". 넷 중 셋(계약여부 · 계약서 수신 여부 ·
성공보수율)은 이미 칸이 있고, 계약년월만 이 표에 담을 자리가 없었다 — 계약 탭의
`계약월` 은 `meeting_at`(메타 탭에서는 `컨설팅 미팅일`)을 빌려 쓰는 다른 칸이다.
IR 기업 현황의 같은 이름 칸(0129 · `ir_companies.contract_ym`)과 같은 이름 · 같은 꼴이다.

지난 줄은 채워 넣지 않는다 — 빈칸으로 시작한다(이어진 줄은 따라 고치기가 채운다).
빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(그 값만 사라지고 줄은 그대로다).

Revision ID: 0133_consulting_contract_ym
Revises: 0132_export_companies_access
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0133_consulting_contract_ym"
down_revision = "0132_export_companies_access"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"
COLUMN = "contract_ym"


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
