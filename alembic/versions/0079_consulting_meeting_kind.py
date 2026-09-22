"""투자컨설턴트 리스트 — `미팅종류` 칸을 세운다

## 무엇을

`consulting_companies` 에 `meeting_kind` 를 더한다
(`화상미팅` / `회의실 미팅`, 빈칸 = 아직 안 정함). 자리는 `미팅일` 바로
오른쪽이다(`routers/consulting.py` 의 `FIXED_COLUMNS`).

## 왜 칸을 새로 만드나 — **한 칸에 두 가지가 적혀 있었다**

원본 시트의 머리글이 **`미팅일(화상, 회의실)`** 이다. 시트가 처음부터 두
가지를 한 칸에 적으라고 했고, 실제 값이 `9/16 PM2 (화상미팅)` 처럼 날짜와
자리가 괄호로 붙어 있다. 섞여 있으면 **화상으로만 만난 기업**을 골라낼 수가
없다 — 적는 꼴이 줄마다 달라(`화상`·`화상미팅`·`(화상)`) 머리글 필터에 올릴
값이 모이지 않는다. 옆 `기업 관리` 에서 `견적서 첨부 여부` 셋을 갈라낸 것
(0065)과 같은 자리다.

`Meeting.meet_mode` 를 끌어다 쓰지 않는다. 저쪽은 IR 미팅 줄(`meetings`)에
붙고 값이 `in_person`/`video` 라는 **열쇠**이며 화면에 보일 때만 `대면`/`화상`
으로 옮겨진다. 이쪽은 **화면에 보이는 말이 곧 저장되는 값**이고
(`static/js/consulting.js` 가 칸 글자를 그대로 보낸다) 쓰는 말도 시트의
`화상, 회의실` 이다. 두 표를 잇는 열쇠도 없다 — 0077 이 같은 이야기를 한다.

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

NULL 로 시작한다. 화면에서는 빈칸이고 그 빈칸이 곧 `아직 안 정함` 이다(머리글
필터가 `(비어 있음)` 으로 세워 준다).

**`미팅일` 칸에서 괄호를 읽어다 채우지 않는다.** 그렇게 채우면 앱이 아무도
확인한 적 없는 사실을 단정하는 것이 된다 — 실제 값에 `(화상미팅)` 이라고 적힌
줄도 있지만 아무 것도 안 적힌 줄이 더 많고, 그 줄에 무엇을 넣어도 추측이다.
0047 · 0048 · 0049 · 0065 · 0068 · 0077 이 같은 이유로 backfill 을 안 했다.
**`미팅일` 의 글자도 안 지운다** — 이 저장소는 적힌 것을 고쳐 쓰지 않는다.
사람이 이 칸을 채우면서 옆 칸을 다듬는 것은 사람의 일이다.

## 되돌리면

칸을 지운다. **여기에 적은 값은 안 돌아온다** — 이 칸에서 처음 생긴 값이라
옮겨 둘 자리가 없다(0049 · 0065 · 0068 · 0077 과 같다). 되돌린 뒤 다시 올리면
빈 칸이 선다.

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면 건너뛴다 — 0048 · 0049 · 0065 · 0068 · 0077 과 같은
방식이다. 스탬프가 어긋난 DB 로 컨테이너가 뜨면 `duplicate column name` 으로
죽고 다시 뜨는 크래시 루프가 된다.

Revision ID: 0079_consulting_meeting_kind
Revises: 0078_notices
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0079_consulting_meeting_kind"
down_revision = "0078_notices"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"

# 세우는 칸. 보기가 둘로 정해진 짧은 글자라 `String` 이다 — 옆의
# `contract_received`(0048) · `contract_done`(0068) · `kakao_joined`(0077) 과
# 같은 모양이다.
ADDED = [("meeting_kind", sa.String())]


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _add(columns) -> None:
    # 한 번에 하나씩 본다. 절반만 올라간 DB 에서도 나머지가 붙어야 한다 —
    # 묶어서 검사하면 그 DB 는 영영 안 채워진다(0077 과 같은 방식).
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
