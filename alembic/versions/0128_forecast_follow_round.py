"""매출예상리스트 → `후속라운드 시작 년월` 칸(`YYYY-MM`) — 관리자 추가 칸을 칸으로 올린다

10/30 개선 과제 #94: 이 값으로 담당 팀원에게 세 번 알린다(`automations/follow_round`).
관리자 추가 칸(`custom_columns`, 자유 글자)은 이름을 바꾸면 끊기고 꼴도 안 맞춰 받는다 —
그래서 `예상 시기` 처럼 `YYYY-MM` 으로 맞춰 받는 칸으로 올린다(`forecast.MONTH_FIELDS`).

## 옮기기

같은 이름의 추가 칸(`forecast` 화면 · `후속라운드 시작 년월`) 값 중 `YYYY-MM` 으로 읽히는
것을 새 칸으로 옮긴다(새 칸이 빈 줄만). **추가 칸은 지우지 않고 숨긴다** — 값이 남아
되돌릴 수 있다. 못 읽은 값이 하나라도 있으면 숨기지 않는다(그 값이 화면에서 사라지지 않게).

## 되돌리기

추가 칸을 다시 보이게 하고 새 칸을 뗀다. 올린 뒤 새 칸에 적은 값은 추가 칸으로 안 돌아간다.

Revision ID: 0128_forecast_follow_round
Revises: 0127_series_a_follow_round
"""
from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0128_forecast_follow_round"
down_revision = "0127_series_a_follow_round"
branch_labels = None
depends_on = None

TABLE = "revenue_forecasts"
COLUMN = "follow_round_month"
CUSTOM_NAME = "후속라운드 시작 년월"
_MONTH_RE = re.compile(r"^(\d{4})\s*[-./]\s*(\d{1,2})$")      # `forecast.month` 와 같은 꼴


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns() -> set:
    if TABLE not in _tables():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _month(text: str):
    hit = _MONTH_RE.match((text or "").strip())
    if not hit or not 1 <= int(hit.group(2)) <= 12:
        return None
    return f"{hit.group(1)}-{int(hit.group(2)):02d}"


def _custom_id(bind):
    if "custom_columns" not in _tables():
        return None
    return bind.execute(sa.text(
        "SELECT id FROM custom_columns WHERE target = 'forecast' AND name = :name"),
        {"name": CUSTOM_NAME}).scalar()


def upgrade() -> None:
    have = _columns()
    if not have:
        return
    if COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(), nullable=True))
    bind = op.get_bind()
    column_id = _custom_id(bind)
    if column_id is None or "custom_column_values" not in _tables():
        return
    unread = 0
    for row_id, value in bind.execute(sa.text(
            "SELECT row_id, value FROM custom_column_values "
            "WHERE column_id = :cid AND row_table = :tbl"),
            {"cid": column_id, "tbl": TABLE}).all():
        found = _month(value)
        if found is None:
            unread += (value or "").strip() != ""
            continue
        bind.execute(sa.text(
            f"UPDATE {TABLE} SET {COLUMN} = :v WHERE id = :id "
            f"AND ({COLUMN} IS NULL OR {COLUMN} = '')"), {"v": found, "id": row_id})
    if not unread:
        bind.execute(sa.text("UPDATE custom_columns SET is_hidden = 1 WHERE id = :cid"),
                     {"cid": column_id})


def downgrade() -> None:
    bind = op.get_bind()
    column_id = _custom_id(bind)
    if column_id is not None:
        bind.execute(sa.text("UPDATE custom_columns SET is_hidden = 0 WHERE id = :cid"),
                     {"cid": column_id})
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
