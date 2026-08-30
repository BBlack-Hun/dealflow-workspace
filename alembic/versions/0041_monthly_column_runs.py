"""월별 칸을 그 달에 한 번만 만들었다는 표시

달마다 늘어나는 칸(`8월 마지막주 리마인드 톡 or TEL` · `7월 리마인드 문자`)을
월 초에 저절로 세운다. 그러려면 두 가지를 막아야 하는데, **칸을 세어서는 둘 다
막을 수 없다.**

  1. 같은 달 칸이 두 번 생기는 것 — 화면 두 개를 동시에 열면 양쪽이 "없네" 를
     보고 각각 만든다. 그 달 기록이 두 칸으로 갈린다.
  2. 사람이 **일부러 지운 칸이 되살아나는 것** — 칸만 보면 다음 요청에서
     "없으니 만들자" 가 그대로 다시 돈다.

그래서 칸이 아니라 **만들었다는 사실**을 남긴다. `(target, scope, month)` 에
유일 색인을 걸어, 동시에 들어온 요청 중 하나만 줄을 넣는 데 성공하게 한다.

왜 기존 칸 표에 유일 색인을 걸지 않았나
---------------------------------------
`consulting_columns` · `contact_columns` 에 `(주인, 시트, 이름)` 유일 색인을
거는 길도 있었다. 그런데 **운영 DB 에 이미 같은 이름이 둘 있으면 색인을 만드는
순간 마이그레이션이 죽고, 컨테이너가 크래시 루프에 빠진다.** 여기서 확인할 수
없는 상태에 기대는 장치는 두지 않는다. 새 표는 비어 있으니 그럴 일이 없다.

두 번 돌려도 죽지 않는가
------------------------
표와 색인 둘 다 있으면 건너뛴다(0037 이 쓰는 방식과 같다).

Revision ID: 0041_monthly_column_runs
Revises: 0040_contract_sheet_columns
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_monthly_column_runs"
down_revision = "0040_contract_sheet_columns"
branch_labels = None
depends_on = None

TABLE = "monthly_column_runs"
INDEX = "uq_monthly_column_runs_target_scope_month"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _inspector().get_indexes(table)}


def upgrade() -> None:
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            # consulting | contact
            sa.Column("target", sa.String(), nullable=False),
            # 칸이 갈리는 단위. 투자컨설턴트는 사람마다·탭마다(`"3:스타트업"`),
            # 투자사 관리 현황은 명단마다(명단 이름 그대로).
            sa.Column("scope", sa.String(), nullable=False),
            sa.Column("month", sa.String(), nullable=False),      # "2026-08"
            # 무엇을 만들었는지. 되짚어 볼 때 칸이 이미 지워졌을 수 있다.
            sa.Column("labels", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    if not _has_index(TABLE, INDEX):
        op.create_index(INDEX, TABLE, ["target", "scope", "month"], unique=True)


def downgrade() -> None:
    if _has_table(TABLE):
        if _has_index(TABLE, INDEX):
            op.drop_index(INDEX, table_name=TABLE)
        op.drop_table(TABLE)
