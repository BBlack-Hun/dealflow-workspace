"""분야 기준 목록(#2) · 투자사 선호분야 재분류(#30) · 소유 펀드(#1) 의 자리

사용자 결정(2026-10-17): 분야 기준 단어는 **IR 기업 현황의 대분류·소분류**로
통일한다. 그 목록을 앱이 들고 있어야 IR 기업 현황과 투자사 `선호 투자분야` 가 같은
말을 쓰게 할 수 있다.

## 표 둘

    sector_terms     분야 기준 목록. 대분류(parent_id 빈 줄) → 소분류 2단계.
                     지우지 않고 숨긴다(is_hidden). 합친 줄은 어디로 합쳤는지
                     (merged_into_id)를 남긴다 — 옛 이름을 만나면 그 화살표를
                     따라 기준 이름으로 바꾼다.
    investor_firms   투자사 **회사 단위** 값(지금은 `소유 펀드` 하나). 열쇠는
                     정규화한 회사명(firm_key, unique) — 사람 줄(`vc_contacts`)이
                     자기 `firm` 글자에서 같은 규칙으로 열쇠를 지어 찾는다.

## 칸 셋 — **원래 값 백업**

    ir_companies.sector_major_raw · sector_minor_raw
    vc_contacts.sectors_raw

정리 · 재분류가 값을 바꾸기 **전에 한 번만** 적는다. NULL 이면 아직 손댄 적이
없다는 뜻이고, 다시 돌려도 덮지 않는다(두 번째 판의 '원래 값' 은 이미 첫 판이
고친 값이다).

## 목록의 처음 값은 여기서 넣지 않는다

처음 값(사용자가 정한 표)은 `app/services/taxonomy.SEED` 한 곳에 있고, 목록이
비어 있으면 앱이 처음 읽을 때 넣는다(`taxonomy.ensure_seed`). 이주에 글자를 한 벌
더 적으면 둘 중 하나가 낡는다. 이 판은 **자리만** 만든다.

## 번호

`0105_retire_old_auto_engines` 바로 뒤다. 다른 갈래가 0105 위에 0107 을 짓고 있어
이 번호를 지킨다(머리가 하나여야 한다 — `tests/test_migrations.py`).

## 빈 DB

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어 새 DB 는 표와 칸을 이미
갖고 시작한다. 그래서 있는지 보고 만든다. 인덱스는 표를 만드는 `if` **밖에서**
따로 본다(0005 · 0100 과 같은 방식 — 안에 두면 빈 DB 길에서 통째로 빠진다).

## 되돌리기

표 둘을 지우고 칸 셋을 뗀다. 잃는 것은 기준 목록 · 소유 펀드 값 · 원래 값
백업이다 — 정리 · 재분류가 이미 바꾼 값은 제 칸에 그대로 남는다.

Revision ID: 0106_taxonomy_owned_funds
Revises: 0105_retire_old_auto_engines
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0106_taxonomy_owned_funds"
down_revision = "0105_retire_old_auto_engines"
branch_labels = None
depends_on = None

#: (표, 칸, 타입) — 원래 값 백업 칸.
RAW_COLUMNS = (
    ("ir_companies", "sector_major_raw", sa.String()),
    ("ir_companies", "sector_minor_raw", sa.String()),
    ("vc_contacts", "sectors_raw", sa.Text()),
)


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    if "sector_terms" not in _tables():
        op.create_table(
            "sector_terms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("parent_id", sa.Integer(),
                      sa.ForeignKey("sector_terms.id"), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("is_hidden", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("merged_into_id", sa.Integer(),
                      sa.ForeignKey("sector_terms.id"), nullable=True),
        )
    if "ix_sector_terms_parent" not in _indexes("sector_terms"):
        op.create_index("ix_sector_terms_parent", "sector_terms", ["parent_id"])

    if "investor_firms" not in _tables():
        op.create_table(
            "investor_firms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("firm_key", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("owned_funds", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
        )
    if "uq_investor_firms_firm_key" not in _indexes("investor_firms"):
        op.create_index("uq_investor_firms_firm_key", "investor_firms",
                        ["firm_key"], unique=True)

    for table, column, kind in RAW_COLUMNS:
        if table in _tables() and column not in _columns(table):
            op.add_column(table, sa.Column(column, kind, nullable=True))


def downgrade() -> None:
    for table, column, _kind in RAW_COLUMNS:
        if column in _columns(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
    if "uq_investor_firms_firm_key" in _indexes("investor_firms"):
        op.drop_index("uq_investor_firms_firm_key", table_name="investor_firms")
    if "investor_firms" in _tables():
        op.drop_table("investor_firms")
    if "ix_sector_terms_parent" in _indexes("sector_terms"):
        op.drop_index("ix_sector_terms_parent", table_name="sector_terms")
    if "sector_terms" in _tables():
        op.drop_table("sector_terms")
