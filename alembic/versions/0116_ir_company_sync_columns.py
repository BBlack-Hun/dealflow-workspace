"""IR 기업 현황 새 칸 셋 — 지역 · 견적서 첨부 여부 · 카톡 연결 여부

투자컨설턴트 메타 탭에만 있던 **기업 사실** 셋을 IR 기업 현황(기준 표)에도 세운다
(10/22 요청 "IR 기업현황에 누락된 내용 추가" · 설계 5장).

    region          지역              컨설턴트 `region`
    quote_attached  견적서 첨부 여부  메타 `contract_management` · 스타트업 `notes.quote_attached`
    kakao_joined    카톡 연결 여부    메타 `kakao_joined` · 스타트업 `kakao_joined`

전부 NULL 이고 기본값이 없다 — 빈칸이 곧 `아직 안 정함` 이다. 값 옮기기는 이주가
아니라 연결할 때 빈칸만 채우는 쪽(`services/company_sync.py`)이 한다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 칸이 있는지 보고
붙인다(0111 과 같다).

## 되돌리기

칸 셋을 뗀다. IR 쪽에 적힌 값만 사라지고, 컨설턴트 · 스타트업 줄의 같은 칸은
그대로다.

Revision ID: 0116_ir_company_sync_columns
Revises: 0115_sourcing_tabs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0116_ir_company_sync_columns"
down_revision = "0115_sourcing_tabs"
branch_labels = None
depends_on = None

COLUMNS = ("region", "quote_attached", "kakao_joined")


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if "ir_companies" not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns("ir_companies")}


def upgrade() -> None:
    have = _columns()
    for name in COLUMNS:
        if have and name not in have:
            op.add_column("ir_companies",
                          sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    gone = [name for name in COLUMNS if name in _columns()]
    if gone:
        with op.batch_alter_table("ir_companies") as batch:
            for name in gone:
                batch.drop_column(name)
