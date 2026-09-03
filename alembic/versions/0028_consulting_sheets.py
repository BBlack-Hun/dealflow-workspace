"""투자컨설턴트 현황을 시트별로 나눈다

원본이 `중요 스타트업` · `경영본부 전달 기업` 으로 나뉘어 있고 관리하는
사람이 다르다. 한 표에 쏟으면 자기 명단을 못 찾는다.

월 컬럼도 시트마다 다르다(`중요 스타트업` 은 6·7·8월, `경영본부 전달 기업` 은
6·7월). 섞으면 없는 달의 빈 칸이 생긴다.

이미 들어 있는 자료는 전부 `중요 스타트업` 이다 — 그 시트만 가져왔었다.

Revision ID: 0028_consulting_sheets
Revises: 0027_sourcing_contacts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_consulting_sheets"
down_revision = "0027_sourcing_contacts"
branch_labels = None
depends_on = None

DEFAULT = "중요 스타트업"


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있으면 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    for table in ("consulting_companies", "consulting_columns"):
        if not _has_column(table, "sheet"):
            op.add_column(table, sa.Column("sheet", sa.String(), nullable=False,
                                           server_default=DEFAULT))


def downgrade() -> None:
    for table in ("consulting_companies", "consulting_columns"):
        if _has_column(table, "sheet"):
            op.drop_column(table, "sheet")
