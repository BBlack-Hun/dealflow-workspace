"""쌓여 있던 UTC 시각을 같은 순간의 한국시간 표기로 옮긴다

저장은 UTC(`...+00:00`), 화면은 한국시간이라 **날짜가 하루 어긋났다.** 한국시간
자정~오전 9시에 적힌 값은 UTC 날짜가 어제여서, 그 시간대에 보낸 발송의 후속이
하루 당겨져 잡혔다. 적는 쪽은 `app/clock.py` 에서 고쳤고, 여기서는 **이미 쌓인
값**을 맞춘다.

왜 남겨 두면 안 되는가
----------------------
읽는 쪽이 앞 10자를 잘라 날짜로 쓰고(`sent_at[:10]`), SQL 에서도 날짜 문자열과
`>=` 로 비교한다(`dashboard.py` 주간 발송 집계, `readiness.py` 최근 발송 확인).
UTC 로 남은 줄은 그 비교에서 **하루 앞**으로 읽혀, 새 값과 나란히 놓으면 같은
표 안에서 기준이 둘이 된다. 실제로 이 DB 에서 성공 발송 122건 중 5건,
`send_sequences` 는 2건 전부가 한국 날짜와 다른 날짜로 읽히고 있었다.

정렬은 왜 괜찮았는가 (그래도 옮기는 이유)
-----------------------------------------
섞였을 때를 실제로 재 봤다. 같은 길이·같은 배치의 ISO 문자열이라 `>=` 는 벽시계
표기끼리 견주는데, 새 값은 옛 값보다 9시간 **뒤로** 적히므로 나중에 쓴 줄이 항상
뒤에 온다 — 이력 순서가 뒤집히지는 않는다. 하지만 **날짜 문자열로 거르는** 자리는
그대로 어긋난 채 남는다. 순서가 안전하다고 필터까지 안전한 것은 아니다.

무엇을 건드리지 않는가
----------------------
날짜만 들어 있는 칸(`happened_at` · `scheduled_at` · `requested_at` ·
`next_due_date` · `followup_due`)은 시각이 아니라 사람이 적은 날짜다. 아래
조건이 `T` 와 `+00:00` 을 모두 요구하므로 이런 값은 걸리지 않는다.

되돌릴 수 있는가
----------------
가리키는 **순간**은 건드리지 않고 표기만 바꾸므로 downgrade 로 되돌아간다.
단 하나, 마이크로초까지 적혀 있던 값(`sessions.expires_at` ·
`users.last_login_at` — 예전 `auth.py` 가 그렇게 적었다)은 초 단위로 잘린다.
30일짜리 세션의 만료 시각에서 1초 미만은 뜻이 없다. 그래도 옮기기 전 스냅샷을
`scripts/db_snapshot.py` 로 따로 떠 두었다.

Revision ID: 0036_local_time_storage
Revises: 0035_template_choice
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_local_time_storage"
down_revision = "0035_template_choice"
branch_labels = None
depends_on = None

# 한국은 1988년 이후 서머타임이 없다 — 오프셋이 늘 +09:00 이라 계산이 하나로 끝난다.
# 이 값을 프로세스 시간대에서 읽지 않는 것은, 마이그레이션이 어디서 돌든(예: TZ 를
# 안 준 일회성 컨테이너) **한국 팀이 한국에서 적은 값**이라는 사실이 변하지 않기
# 때문이다. 환경에 따라 결과가 달라지면 되돌릴 수도 없다.
SHIFT = "+9 hours"
OFFSET = "+09:00"

# `____-__-__T%+00:00` — 날짜 뒤에 `T` 가 오고 `+00:00` 으로 끝나는 값만.
# 날짜만 든 칸(`2026-08-13`)과 이미 옮긴 칸(`+09:00`)은 걸리지 않는다.
UTC_LIKE = "____-__-__T%+00:00"
LOCAL_LIKE = "____-__-__T%" + OFFSET


def _iso(col: str, shift: str, offset: str) -> str:
    """`strftime` 으로 벽시계 표기를 다시 쓴다.

    **주의.** SQLite 는 오프셋이 붙은 값을 읽는 순간 이미 UTC 로 바꿔 놓는다.
    그래서 `shift` 는 "UTC 에서 얼마를 더할까" 이지 "지금 표기에서 얼마를
    옮길까" 가 아니다 — `+09:00` 값을 UTC 로 되돌릴 때 `-9 hours` 를 주면
    아홉 시간이 두 번 빠진다(되돌리기 검사에서 실제로 그렇게 어긋났다).

    `datetime()` 이 아니라 `strftime` 을 쓰는 것은 구분자 때문이다 — `datetime()`
    은 `2026-08-27 00:21:24` 처럼 사이를 **공백**으로 돌려줘서, 앞 10자를 자르는
    쪽은 몰라도 `fromisoformat` 과 문자열 비교가 다른 모양을 보게 된다.
    """
    return f"strftime('%Y-%m-%dT%H:%M:%S', {col}, '{shift}') || '{offset}'"


def _shift_all(conn, like: str, shift: str, offset: str) -> None:
    """모든 표·모든 칸을 훑어 조건에 맞는 값만 옮긴다.

    칸 이름을 손으로 나열하지 않는 것은, 표가 24개에 시각 칸이 50개 가까이 되고
    `created_at`/`updated_at` 은 앞으로 생길 표에도 계속 붙기 때문이다. 하나라도
    빠뜨리면 그 칸만 조용히 어긋난 채 남는다 — 그게 이 버그가 살아남은 방식이다.
    """
    insp = sa.inspect(conn)
    moved = 0
    for table in sorted(insp.get_table_names()):
        if table == "alembic_version":
            continue
        for column in insp.get_columns(table):
            name = column["name"]
            # 값이 있는 칸만 건드린다. 숫자 칸은 LIKE 가 걸리지 않아 0 이 나온다.
            n = conn.execute(
                sa.text(f'SELECT COUNT(*) FROM "{table}" WHERE "{name}" LIKE :p'),
                {"p": like},
            ).scalar_one()
            if not n:
                continue
            expr = _iso(f'"{name}"', shift, offset)
            conn.execute(sa.text(
                f'UPDATE "{table}" SET "{name}" = {expr} '
                f'WHERE "{name}" LIKE :p AND {expr} IS NOT NULL'
            ), {"p": like})
            moved += n
            print(f"[0036] {table}.{name}: {n}행")
    print(f"[0036] 시각 {moved}행을 옮겼습니다 ({like} → {offset})")


# 같은 줄의 `created_at` 에서 회차 날짜를 뽑는 두 가지 방법.
# UTC 표기 그대로 자른 날짜 / 한국시간으로 옮겨 자른 날짜.
_AS_UTC_DATE = "substr(created_at, 1, 10)"
_AS_LOCAL_DATE = f"substr({_iso('created_at', SHIFT, '')}, 1, 10)"


def _rewrite_batch_dates(conn, was: str, now: str) -> None:
    """회차 날짜(`deal_batches.sent_date`)를 `was` 에서 나온 값일 때만 `now` 로 바꾼다.

    이 칸은 발송을 만들 때 `now_iso()[:10]` 으로 박히던 **날짜 문자열**이라
    오프셋이 없다 — 위의 시각 조건에 걸리지 않는데 UTC 날짜가 그대로 굳어 있다.
    이 DB 에서는 7개 회차 중 4개가 하루 앞선 날짜였다.

    고쳐도 되는 이유는 이 칸을 사람이 건드리는 화면이 없기 때문이다(`deals.py`
    한 곳에서만 쓴다). 그래도 안전하게 **같은 줄의 생성 시각에서 나온 값일
    때만** 손댄다 — 다르면 손으로 넣은 값이므로 그대로 둔다.
    """
    where = f"WHERE created_at IS NOT NULL AND sent_date = {was} AND {now} <> {was}"
    n = conn.execute(
        sa.text(f"SELECT COUNT(*) FROM deal_batches {where}")).scalar_one()
    if not n:
        return
    conn.execute(sa.text(f"UPDATE deal_batches SET sent_date = {now} {where}"))
    print(f"[0036] deal_batches.sent_date: {n}행")


def upgrade() -> None:
    conn = op.get_bind()
    # 회차 날짜를 먼저 고친다 — 판단 근거가 아직 UTC 표기인 `created_at` 이라,
    # 순서를 바꾸면 "생성 시각에서 나온 값인가" 를 알아볼 수 없다.
    _rewrite_batch_dates(conn, was=_AS_UTC_DATE, now=_AS_LOCAL_DATE)
    _shift_all(conn, UTC_LIKE, SHIFT, OFFSET)


def downgrade() -> None:
    conn = op.get_bind()
    # `+0 hours` 인 것이 맞다 — SQLite 가 `+09:00` 을 읽으면서 이미 UTC 로
    # 바꿔 놓으므로, 여기서는 그 UTC 를 그대로 적기만 하면 된다.
    # 시각을 먼저 되돌린 뒤에야 `created_at` 이 다시 회차 날짜의 판단 근거가 된다.
    _shift_all(conn, LOCAL_LIKE, "+0 hours", "+00:00")
    _rewrite_batch_dates(conn, was=_AS_LOCAL_DATE, now=_AS_UTC_DATE)
