"""Series A 이상 딜 소싱 기업도 IR 자료로 보낸다 — 칸 둘

    series_a_companies.ir_file_name   보낼 IR 자료 파일 이름(`ir_companies` 의 같은 칸과 같은 규칙)
    deal_batches.series_a_names       IR 자료 전달 회차에 실린 Series A 기업 이름(JSON 목록)

뒤엣것은 보낸 뒤 그 요청을 `IR 자료 전달 완료` 로 닫는 데 쓴다 — 회차의 기업 칸
(`deal_batch_companies`)은 `ir_companies` 만 가리켜 이 기업을 못 담는다.

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 칸이 있는지 보고
붙인다(0112 · 0117 과 같다).

## 되돌리기

칸 둘을 뗀다. 적어 둔 Series A 자료 파일 이름이 함께 사라진다 — 다른 표는 이 칸을
가리키지 않는다. 이미 닫힌 요청은 그대로다.

Revision ID: 0118_series_a_ir_file
Revises: 0117_ir_link_auto
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0118_series_a_ir_file"
down_revision = "0117_ir_link_auto"
branch_labels = None
depends_on = None

#: (표, 칸, 꼴)
COLUMNS = (("series_a_companies", "ir_file_name", sa.String()),
           ("deal_batches", "series_a_names", sa.Text()))


def _has(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return (table in inspector.get_table_names()
            and column in {c["name"] for c in inspector.get_columns(table)})


def upgrade() -> None:
    names = set(sa.inspect(op.get_bind()).get_table_names())
    for table, column, kind in COLUMNS:
        if table in names and not _has(table, column):
            op.add_column(table, sa.Column(column, kind, nullable=True))


def downgrade() -> None:
    for table, column, _kind in COLUMNS:
        if _has(table, column):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
