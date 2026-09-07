"""반복 업무를 그 주에 한 번 만들었다는 표시 — 지운 줄이 되살아나지 않게

## 무슨 고장인가

주간 업무 줄에는 모두 [삭제] 가 붙어 있고, 그 경로도 멀쩡히 있다
(`POST /todo/tasks/{id}/delete`). 그런데 **반복 업무에서 생긴 줄은 지워지지
않았다** — 지우고 `/todo` 로 돌아오면 그 자리에 그대로 다시 서 있다.

화면을 열 때 도는 `fill_week`(`services/weekly.py`)가 "이 규칙 줄이 이번 주에
있나" 를 **지금 남아 있는 `weekly_tasks.routine_id`** 로만 봤기 때문이다.
지우면 그 자취까지 함께 사라져 없는 것이 되고, 리다이렉트로 돌아온 그 화면이
곧바로 "없으니 만들자" 를 다시 돌린다. 지운 사람 눈에는 **지워지지 않는 줄**이다.

## 왜 표인가 — 줄을 세어서는 막을 수 없다

`monthly_column_runs`(0041) 가 같은 문제를 같은 방식으로 풀었다. 칸을 세면
지운 다음 요청에서 다시 만들어지므로, 칸이 아니라 **만들었다는 사실**을 남긴다.
여기도 같다 — 지워도 이 표시는 남으므로 되살아나지 않는다.

한 가지를 더 얻는다. `(user_id, week_start, routine_id)` 에 유일 색인이 걸려
있어 **화면 두 개를 같은 순간에 열어도 한쪽만 줄을 넣는 데 성공한다.** 세어
보고 넣는 방식은 두 요청이 같은 순간에 세면 둘 다 통과한다 — 지금까지는 같은
반복 업무가 한 주에 두 줄로 앉을 수 있었다.

## 왜 `weekly_tasks` 에 '지웠음' 칸을 붙이지 않았나

지운 줄을 숨긴 채 남겨 두는 길도 있었다. 그러면 이 표를 읽는 모든 자리
(`task_rows` · `carry_over_candidates` · `carry_over` · 다음 `position`)가 전부
"지운 것은 빼고" 를 따로 기억해야 하고, **한 곳만 잊으면 지운 줄이 거기서 다시
보인다.** 사람이 직접 만든 줄까지 안 지워지는 것도 이상하다 — 지우기는
지우기여야 한다.

## 옮길 데이터 — 이미 만들어 둔 줄을 그대로 적는다

지금 있는 `weekly_tasks` 중 `routine_id` 가 있는 줄은 모두 **`fill_week` 가
만든 것**이다. 그 (사람·주·규칙)을 그대로 이 표에 옮겨 적는다.

**옮기지 않으면 배포 직후 한 번은 여전히 되살아난다.** 새 표가 비어 있으니
`fill_week` 가 "이 주에는 만든 적 없다" 로 읽고, 사람이 지운 그 줄을 한 번 더
만든다(그때 표시가 남아 두 번째 삭제부터 붙든다). 고쳤다는데 첫 번에 안 되는
자리는 안 고친 것과 같다.

지난 주 것까지 다 옮긴다. 지난 주는 `fill_week` 가 어차피 채우지 않지만
(`if start < week_start(today): return 0`), 이 표가 적는 것은 "만들었다" 는
사실이고 그것은 지난 주에도 참이다. 날짜로 잘라 두면 그 기준이 이주를 돌린
날에 매이고, 다시 돌릴 때마다 다른 결과가 나온다.

## 두 번 돌려도 죽지 않는가

표와 색인 둘 다 있으면 건너뛴다(0041 이 쓰는 방식과 같다). 빈 DB 길에서는
`0001` 이 모델 전체를 이미 만들어 두므로 표는 건너뛰고 색인만 선다
(`tests/test_migrations.py` 가 지키는 규칙이다). 옮겨 적는 문장도 **이미 있는
짝은 빼고** 넣으므로 몇 번을 돌려도 같은 자리에 머문다.

## 되돌리기

**표를 지운다.** 되돌리면 `fill_week` 도 함께 돌아가 다시 줄만 보고 판단한다 —
이 표를 아예 읽지 않으므로 값을 되짚어 둘 자리가 없다. 되돌린 뒤에는 지운 줄이
다시 되살아나는 옛 동작으로 돌아간다.

Revision ID: 0062_weekly_routine_runs
Revises: 0061_sms_notices
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0062_weekly_routine_runs"
down_revision = "0061_sms_notices"
branch_labels = None
depends_on = None

TABLE = "weekly_routine_runs"
INDEX = "uq_weekly_routine_runs_user_week_routine"


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
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=False),
            # 그 주 월요일 (YYYY-MM-DD) — `weekly_tasks.week_start` 와 같은 값.
            sa.Column("week_start", sa.String(), nullable=False),
            sa.Column("routine_id", sa.Integer(),
                      sa.ForeignKey("weekly_routines.id"), nullable=False),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    if not _has_index(TABLE, INDEX):
        op.create_index(INDEX, TABLE, ["user_id", "week_start", "routine_id"],
                        unique=True)

    # 이미 만들어 둔 줄을 그대로 옮겨 적는다(위 `## 옮길 데이터`).
    #
    # **`GROUP BY` 로 짝마다 한 줄만** 넣는다. 같은 (사람·주·규칙) 줄이 둘인
    # DB 가 있을 수 있어서다 — [이번 주로 가져오기] 가 지난 주 반복 항목을
    # 이번 주로 끌어와 두 벌로 앉히던 자리가 있었다. 그대로 넣으면 새 유일
    # 색인에 걸려 **이주가 죽고 컨테이너가 크래시 루프에 빠진다.**
    # `NOT EXISTS` 는 이미 있는 짝을 빼므로 몇 번을 돌려도 같은 자리다.
    op.execute(sa.text(f"""
        INSERT INTO {TABLE} (user_id, week_start, routine_id, created_at, updated_at)
        SELECT t.user_id, t.week_start, t.routine_id,
               MIN(t.created_at), MIN(t.created_at)
          FROM weekly_tasks AS t
         WHERE t.routine_id IS NOT NULL
           AND NOT EXISTS (
                 SELECT 1 FROM {TABLE} AS r
                  WHERE r.user_id = t.user_id
                    AND r.week_start = t.week_start
                    AND r.routine_id = t.routine_id)
         GROUP BY t.user_id, t.week_start, t.routine_id
    """))


def downgrade() -> None:
    """표를 지운다 — 위 `## 되돌리기` 참고."""
    if _has_table(TABLE):
        if _has_index(TABLE, INDEX):
            op.drop_index(INDEX, table_name=TABLE)
        op.drop_table(TABLE)
