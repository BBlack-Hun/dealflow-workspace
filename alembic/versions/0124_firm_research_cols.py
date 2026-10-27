"""투자사 회사 단위 칸 둘 — `펀드 종류` · `소분류`(`investor_firms`)

`소유 펀드`(0106 · 화면 이름은 이제 `챗GPT 조사 소유펀드`)와 같은 회사 단위 값이다.
둘 다 쉼표로 여럿을 적는 글 칸이다. `소분류` 는 분야 기준 목록의 소분류만 받는다
(`services/investor_firms.clean_sub_sectors`) — 검사는 앱이 하고 칸은 글 그대로다.

빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 두 칸을 뗀다(그 값만 사라지고 회사 줄 · 소유 펀드는 그대로다).

Revision ID: 0124_firm_research_cols
Revises: 0123_session_token_hash
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0124_firm_research_cols"
down_revision = "0123_session_token_hash"
branch_labels = None
depends_on = None

TABLE = "investor_firms"
COLUMNS = ("fund_types", "sub_sectors")


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if not have:
        return
    for name in COLUMNS:
        if name not in have:
            op.add_column(TABLE, sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    gone = [c for c in COLUMNS if c in _columns()]
    if gone:
        with op.batch_alter_table(TABLE) as batch:
            for name in gone:
                batch.drop_column(name)
