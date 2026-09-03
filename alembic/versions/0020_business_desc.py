"""사업 설명을 카테고리와 갈라 둔다

스타트업DB 시트의 `사업분야` 칸에는 카테고리가 아니라 **사업 설명**이 들어
있다(283건 중 230건이 40자를 넘는 문장). 카테고리는 IR 기업현황 탭의
`사업분야 대분류/소분류` 가 따로 들고 있다.

둘을 같은 칸에 넣으면 카테고리 필터가 문장으로 채워져 못 쓰게 된다.

한줄 소개의 첫 토막이 이 값이다:
    {사업 설명} | 매출 N억 | 누적투자금액 N억 | … | {특이사항}

Revision ID: 0020_business_desc
Revises: 0019_company_sheet_fields
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_business_desc"
down_revision = "0019_company_sheet_fields"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있으면 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    if not _has_column("ir_companies", "business_desc"):
        op.add_column("ir_companies", sa.Column("business_desc", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("ir_companies", "business_desc"):
        op.drop_column("ir_companies", "business_desc")
