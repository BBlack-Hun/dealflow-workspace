"""IR 기업 현황 메뉴의 `Series A 이상 기업` 탭 — `series_a_companies` 표

딜 소싱 네트워크로 **받은 딜 한 건이 한 줄**인 표다(`models.SeriesACompany`).
`ir_companies` 와 따로 두는 까닭은 모델 머리글에 있다.

표만 만든다. 값은 시트에서 가져온다(`scripts/import_series_a.py`) — 이 판이
시트를 읽지 않는 것은, 시트가 저장소 밖의 문서라 판을 돌리는 자리마다 있을 수
없어서다.

## 이 판의 번호 — 다른 PR 과 겹치지 않게

`0093_sourcing_vc_link` 바로 뒤다. 열려 있는 PR 의 판 이름(0088 ~ 0092)과
겹치지 않게 0094 를 쓴다. 그 PR 들이 뒤에 들어오면 `down_revision` 을 이어
머리가 하나가 되게 맞춘다.

## 빈 DB 에서는 만들지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다 — 있는지 보고
만든다(0087 · 0093 과 같은 방식).

## 되돌리기

표째 지운다 — 잃는 것은 이 탭의 줄 전부다(시트에서 다시 가져올 수 있다).

Revision ID: 0094_series_a_companies
Revises: 0093_sourcing_vc_link
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0094_series_a_companies"
down_revision = "0093_sourcing_vc_link"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"


def _has_table() -> bool:
    return TABLE in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("received_at", sa.String(), nullable=True),
        sa.Column("deal_type", sa.String(), nullable=True),
        sa.Column("assignee_name", sa.String(), nullable=True),
        sa.Column("shared_by", sa.String(), nullable=True),
        sa.Column("source_firm", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sector_major", sa.String(), nullable=True),
        sa.Column("sector_minor", sa.String(), nullable=True),
        sa.Column("series", sa.String(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("deal_pitch", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE)
