"""반복 업무에 **주차** — 격주로 도는 일을 담을 자리

## 왜 칸이 필요한가

반복 업무는 요일만 정할 수 있었다("매주 화요일"). 그런데 팀 업무 중에는
**격주로 도는 것**이 있고, 그것을 담을 자리가 없어 매주 생기는 줄을 사람이
격주로 지우고 있었다.

값은 `"1,3"` — 그 달의 1주차·3주차. **사용자가 확정한 격주의 뜻이 이것이다.**
회차일이 "매월 첫째·셋째 수요일" 인 것과 같은 결이다.

## 왜 새 모양을 만들지 않았나

`schedule_rules.nth_weeks`(0009)가 이미 같은 것을 담고 있다 — 회차일 규칙의
`weekday=2, nth_weeks="1,3"`. 같은 뜻에 다른 모양을 하나 더 만들면 읽는 규칙도
두 벌이 되고, 한쪽만 고쳐지는 날이 온다. **칸 이름도 형식도 그대로 가져온다.**

주차를 세는 규칙도 하나뿐이다 — `sheet_import.week_of_month`(**1~7일이 1주차**).
예전에 같은 날이 화면마다 3주차·4주차로 갈린 적이 있어서, 두 번째 규칙은 만들지
않는다.

## 비워 둘 수 있어야 한다 — 빈칸이 곧 `매주`

**NOT NULL 로 두지 않고 기본값도 주지 않는다.** 지금 있는 규칙은 전부 매주
도는 것이고, 여기에 `"1,3"` 같은 값을 채워 넣으면 **아무도 고르지 않은 규칙이
그날부터 격주가 된다** — 매주 나가던 홍보 메일이 말없이 두 주에 한 번이 된다.
`meetings.meet_mode`(0060) · `contract_received`(0048) 가 같은 이유로 NULL 을
남겨 두었다.

빈칸이 곧 "매주" 다. 옮길 데이터가 없다 — 지금 규칙 수백 개가 그대로 매주다.

## 되돌리기

**칸을 지운다.** 되돌리면 `fill_week` 도 함께 돌아가 주차를 아예 보지 않는다 —
값을 되짚어 둘 자리가 없고, 되돌린 뒤에는 격주 규칙이 매주로 돈다.

`app/models.py` 와 화면이 **같은 커밋에서 함께** 옮겨간다
(`tests/test_migrations.py::test_the_fresh_schema_matches_the_models` 가 이주
결과와 모델을 칸 단위로 대조한다).

Revision ID: 0063_weekly_routine_nth_weeks
Revises: 0062_weekly_routine_runs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0063_weekly_routine_nth_weeks"
down_revision = "0062_weekly_routine_runs"
branch_labels = None
depends_on = None

TABLE = "weekly_routines"
COLUMN = "nth_weeks"


def _has_column() -> bool:
    """빈 DB 길에서는 `0001` 이 모델 전체를 이미 만들어 둔다.

    그 자리에 또 붙이면 `duplicate column name` 으로 **부팅이 죽는다**
    (`tests/test_migrations.py` 가 지키는 규칙이다).
    """
    insp = sa.inspect(op.get_bind())
    if TABLE not in insp.get_table_names():
        return False
    return COLUMN in {c["name"] for c in insp.get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        # 기본값을 주지 않는다 — 지금 규칙은 **빈 채로** 남아 매주 돈다
        # (위 `## 비워 둘 수 있어야 한다`).
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    """칸을 지운다 — 위 `## 되돌리기` 참고."""
    if _has_column():
        op.drop_column(TABLE, COLUMN)
