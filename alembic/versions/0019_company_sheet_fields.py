"""IR 기업현황·스타트업DB 시트의 빠진 칸들

시트를 그대로 옮겨 담기 위해 모자란 칸을 채운다.

- 연도별 매출(22~25): 한 해만 남기면 성장 추세가 사라진다.
  "작년 대비" 가 딜소개에서 자주 쓰인다.

  **글자로 담는다.** 원본 시트에 `8.2억` · `1,224백만원` · `150억 ~ 200억` 이
  한 칸에 섞여 있다. 숫자로 바꾸려면 단위를 판별해야 하는데, 잘못 읽으면
  100배가 틀어진 채 딜소개 문구에 실려 나간다. 적은 그대로 두고 그대로
  보여주는 편이 안전하다 — 사람이 적은 것이 곧 사실이다.
  (`revenue_recent` 같은 기존 숫자 칸은 그대로다. '소개 가능' 판정과
   억 단위 표시가 그 값을 쓴다.)
- 설립년도 · 기보/신보/중진공: 투자사가 자주 묻는다
- 담당자: 이 기업을 맡은 팀원

Revision ID: 0019_company_sheet_fields
Revises: 0018_send_item_parts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_company_sheet_fields"
down_revision = "0018_send_item_parts"
branch_labels = None
depends_on = None

NEW = [
    ("revenue_2022", sa.String()),
    ("revenue_2023", sa.String()),
    ("revenue_2024", sa.String()),
    ("revenue_2025", sa.String()),
    ("founded_year", sa.String()),
    ("guarantee", sa.String()),
    ("assignee_name", sa.String()),
]


def _columns(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있는 칸은 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    have = _columns("ir_companies")
    for name, kind in NEW:
        if name not in have:
            op.add_column("ir_companies", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    have = _columns("ir_companies")
    for name, _kind in reversed(NEW):
        if name in have:
            op.drop_column("ir_companies", name)
