"""Series A 이상 딜 소싱 탭 — 직접 적는 칸 열(개선 과제 #24)

`series_a_companies` 에 칸 열을 붙인다. 시트에 없는 칸이라 **탭에서 사람이 적는다**
(사용자 결정 — IR 기업 현황에서 옮겨 오지 않는다). 처음에는 전부 비어 있다.

    ceo_name · ceo_phone · ceo_email          대표자명 · 핸드폰 · 이메일
    revenue_2024 ~ revenue_2027               24 ~ 27년 매출(억, 적은 그대로)
    funding_total · raise_target · pre_value  누적투자금액 · 투자유치희망금액 · 프리밸류

`딜소개 문구`(`deal_pitch`)는 이미 있는 칸이라 붙이지 않는다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 칸이 있는지 보고
붙인다(0111 과 같다).

## 되돌리기

칸 열을 뗀다. 사람이 적은 대표자 · 매출 · 금액이 함께 사라진다 — 다른 표는 이
칸을 가리키지 않는다.

Revision ID: 0112_series_a_fields
Revises: 0111_forecast_fee
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0112_series_a_fields"
down_revision = "0111_forecast_fee"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"
COLUMNS = ("ceo_name", "ceo_phone", "ceo_email",
           "revenue_2024", "revenue_2025", "revenue_2026", "revenue_2027",
           "funding_total", "raise_target", "pre_value")


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    for name in COLUMNS:
        if have and name not in have:
            op.add_column(TABLE, sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    gone = [name for name in COLUMNS if name in _columns()]
    if gone:
        with op.batch_alter_table(TABLE) as batch:
            for name in gone:
                batch.drop_column(name)
