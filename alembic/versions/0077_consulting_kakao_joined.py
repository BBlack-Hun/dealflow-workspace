"""`관리 스타트업` 탭 — `카톡 연결 여부` 칸을 세운다

## 무엇을

`consulting_companies` 에 `kakao_joined` 를 더한다 (`O`/`X`, 빈칸 = 아직 안 정함).
화면 이름은 `카톡 연결 여부` 이고 자리는 `계약서 수신완료여부` 바로 뒤,
`딜 소개문구` 앞이다(`routers/consulting.py` 의 `STARTUP_COLUMNS`).

## 왜 이미 있는 칸을 안 쓰나 — **이을 열쇠가 없다**

`계약서 수신완료여부` 는 계약 탭의 칸을 그대로 썼다(0068 의 설명). 이번에는
그렇게 못 한다. 카톡 연결을 적는 자리가 이 앱에 이미 둘 있는데, **둘 다 다른
표**다.

  · `vc_contacts.kakao_joined` — 줄마다 하나. 대시보드의 `카톡방 연결 상태` 가
    읽고, 발송 가능 여부까지 이 값이 정한다.
  · `vc_contacts.notes` 안의 월별 `N월 카톡 연결` — 달마다 하나. `스타트업`
    명단이 세운다.

`consulting_companies` 와 `vc_contacts` 사이에는 외래키가 없고(둘 다 `users`
만 가리킨다) 기업명으로 맞춰도 겹치지 않는다 — 어느 쪽도 이름에 유일성이 없고
`vc_contacts` 는 사람 줄이라 한 기업에 여러 줄이 실린다. 이어 주는 것이 없는
채로 값을 끌어오면 같은 이름의 **다른 기업 줄**에서 값이 넘어온다.

그래서 세 번째 자리를 만든다. **같은 기업이 스타트업 화면과 컨설턴트 화면에서
서로 다른 답을 보일 수 있다** — 사용자가 알고 정한 것이고, 어디에 무엇이 있고
왜 안 이었는지는 `models.ConsultingCompany.kakao_joined` 주석에 한 곳으로 적혀
있다(시험: `tests/test_consulting_kakao_joined.py`).

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

NULL 로 시작한다. 화면에서는 빈칸이고 그 빈칸이 곧 `아직 안 정함` 이다(머리글
필터가 `(비어 있음)` 으로 세워 준다). `X` 로 채우면 앱이 "확인했는데 연결이
안 됐다" 고 **단정**하는 것이 되는데, 그건 아무도 확인한 적 없는 사실이다.
`vc_contacts.kakao_joined` 에서 읽어다 채우는 길도 없다 — 위에 적은 대로 두
표를 잇는 열쇠가 없다(0047 · 0048 · 0049 · 0065 · 0068 이 같은 이유로
backfill 을 안 했다).

## 되돌리면

칸을 지운다. **여기에 적은 값은 안 돌아온다** — 이 칸에서 처음 생긴 값이라
옮겨 둘 자리가 없다(0049 · 0065 · 0068 과 같다). 되돌린 뒤 다시 올리면 빈 칸이
선다. 이 저장소는 운영에 올리기 전에 `downgrade` → `upgrade` 를 실제로 돌려
표가 같은지 확인한다(`tests/test_migrations.py` 의 5번이 같은 것을 본다).

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면 건너뛴다 — 0048 · 0049 · 0065 · 0068 과 같은 방식이다.
스탬프가 어긋난 DB 로 컨테이너가 뜨면 `duplicate column name` 으로 죽고 다시
뜨는 크래시 루프가 된다.

Revision ID: 0077_consulting_kakao_joined
Revises: 0076_manual_send_log
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0077_consulting_kakao_joined"
down_revision = "0076_manual_send_log"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"

# 세우는 칸. `O`/`X` 한 글자라 `String` 이다 — 옆의 `contract_received`(0048) ·
# `contract_done`(0068) 과 같은 모양이고, 이름이 같은
# `vc_contacts.kakao_joined` 와도 같은 모양이다.
ADDED = [("kakao_joined", sa.String())]


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _add(columns) -> None:
    # 한 번에 하나씩 본다. 절반만 올라간 DB 에서도 나머지가 붙어야 한다 —
    # 묶어서 검사하면 그 DB 는 영영 안 채워진다(0068 과 같은 방식).
    for name, kind in columns:
        if _has_column(TABLE, name):
            continue
        with op.batch_alter_table(TABLE) as b:
            b.add_column(sa.Column(name, kind, nullable=True))


def _drop(columns) -> None:
    for name, _kind in columns:
        if not _has_column(TABLE, name):
            continue
        with op.batch_alter_table(TABLE) as b:
            b.drop_column(name)


def upgrade() -> None:
    _add(ADDED)


def downgrade() -> None:
    _drop(ADDED)
