"""Series A 딜 공유 기록 — `series_a_shares` 표

딜 제안 관리 › 딜 소싱 제안의 [보낼 문구 › Series A 딜 공유]로 **어느 심사역
(`sourcing_contacts`)에게 어느 기업(`series_a_companies`)을 보냈나**를 발송
건(`send_items`)마다 한 줄씩 남긴다(`models.SeriesAShare`). 받았는지는 그 발송
건의 상태가 정한다 — 대기 · 보내는 중 · 보냄만 센다(`services/series_a_share.py`).

## 이 판의 번호

`0094_series_a_companies` 바로 뒤다. 열려 있는 PR 의 판 이름(0088 ~ 0092)과
겹치지 않게 0095 를 쓴다. 그 PR 들이 뒤에 들어오면 `down_revision` 을 이어
머리가 하나가 되게 맞춘다.

## 빈 DB 에서는 만들지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다 — 있는지 보고
만든다(0087 · 0094 와 같은 방식). 색인은 표를 만드는 `if` **밖에서** 따로 본다
(`tests/test_migrations.py` 3번).

## 되돌리기

표째 지운다 — 잃는 것은 Series A 딜 공유 기록뿐이다(나간 문구 자체는 발송 건
`send_items.message` 에 그대로 남는다). 대신 `이미 받은 분` 수가 0 으로 돌아가
같은 기업을 다시 고를 수 있게 된다.

Revision ID: 0095_series_a_shares
Revises: 0094_series_a_companies
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0095_series_a_shares"
down_revision = "0094_series_a_companies"
branch_labels = None
depends_on = None

TABLE = "series_a_shares"
INDEXES = (
    ("ix_series_a_shares_company", ["series_a_company_id"], False),
    ("ix_series_a_shares_contact", ["sourcing_contact_id"], False),
    ("uq_series_a_shares_item_company", ["send_item_id", "series_a_company_id"], True),
)


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(TABLE)}


def upgrade() -> None:
    if TABLE not in _tables():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("series_a_company_id", sa.Integer(),
                      sa.ForeignKey("series_a_companies.id"), nullable=False),
            sa.Column("sourcing_contact_id", sa.Integer(),
                      sa.ForeignKey("sourcing_contacts.id"), nullable=False),
            sa.Column("send_item_id", sa.Integer(),
                      sa.ForeignKey("send_items.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False,
                      server_default="1"),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    have = _indexes()
    for name, cols, unique in INDEXES:
        if name not in have:
            op.create_index(name, TABLE, cols, unique=unique)


def downgrade() -> None:
    if TABLE in _tables():
        op.drop_table(TABLE)
