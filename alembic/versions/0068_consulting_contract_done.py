"""`관리 스타트업` 탭 — `계약완료여부` 를 세우고 `견적서`·`계산서` 두 칸을 뺀다

## 무엇을

`consulting_companies` 에

  · `contract_done` 을 **더한다** (`계약완료여부` — `무료계약완료`/`유료계약완료`)
  · `quote_attached`(`견적서 첨부여부`) · `invoice_received`(`계산서 수신여부`)
    를 **지운다**

사용자가 이 탭에 세워 달라고 부른 칸이 바뀌었다. 흐름의 세 마디가
`견적서 → 계약 → 계산서` 가 아니라 `계약관리 → 계약완료여부 →
계약서 수신완료여부` 였다.

## `계약서 수신완료여부` 는 왜 여기 없나 — **이미 있는 칸을 쓴다**

`contract_received`(0048)가 `계약서 수신여부` 라는 이름으로 계약 탭에 서 있다.
묻는 사실이 같다 — 계약서가 왔는가, 하나뿐인 물음이다. 뜻이 같은데 칸을 둘로
두면 같은 기업의 같은 사실이 두 군데에 갈려 어느 쪽이 맞는지 알 수 없게 된다.

탭마다 이름이 다른 것은 이 표가 이미 하는 일이다 — 같은 `region` 이 한 탭에서는
`지역`, 다른 탭에서는 `월` 로 서고 `meeting_at` 도 그렇다. 이름은 탭이 정하고
(`routers/consulting.py` 의 `SHEET_LAYOUTS`) 담기는 칸은 하나다.

## 지우는 두 칸 — 값이 **한 줄도 없다**

어제(0065) 만들어 아직 아무도 안 썼다. 운영 DB 에서 두 칸 다 값이 든 줄이
0개인 것을 확인하고 지운다. 값이 있었다면 지우지 않았을 것이다 — 이 저장소는
이력을 함부로 지우지 않는다(`CONTRACT_TAIL` 이 계약 탭에서 대표자·연락처를
**화면에서만** 뺀 것이 그 예다).

칸까지 지우는 쪽을 고른 까닭은 남겨 두는 쪽이 더 비싸서다. `tests/test_migrations.py`
가 **모델과 스키마를 칸 단위로 대조**한다 — 모델에서만 빼고 DB 에 남기면 그
검사가 빨개지고, 그렇다고 모델에 남겨 두면 어느 화면도 안 세우는 칸이 모델에
영영 남는다. 되돌리는 길은 아래 `downgrade` 가 연다.

## 되돌리면

`contract_done` 을 지우고 두 칸을 도로 세운다. **값은 안 돌아온다** — 지울 때
비어 있었으므로 돌아올 값이 없다. `contract_done` 에 적은 값은 이 칸에서 처음
생긴 값이라 남겨 둘 자리가 없다(0049 · 0065 와 같다).

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

`contract_done` 은 NULL 로 시작한다. 화면에서는 빈칸이고, 그 빈칸이 곧
`아직 안 정함` 이라는 뜻이다(머리글 필터가 `(비어 있음)` 으로 세워 준다).
아직 안 정한 기업이 실제로 있다.

둘 중 하나로 채우고 싶어지는 자리인데, 그러면 앱이 "무료로 계약했다" 고
**단정**하는 것이 된다 — 아무도 확인한 적 없는 사실이다. 옆 `기업 관리` 나
`계약관리` 에 적힌 문장을 읽어다 나눠 담는 것도 마찬가지다. 그 경계는 아무도
정한 적이 없고, 잘못 나눈 뒤에는 원래 한 줄이 어땠는지 남지 않는다
(0047 · 0048 · 0049 · 0065 가 같은 이유로 backfill 을 안 했다).

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면(없으면) 건너뛴다 — 0049 · 0048 · 0065 와 같은 방식이다.
스탬프가 어긋난 DB 로 컨테이너가 뜨면 `duplicate column name` 으로 죽고 다시
뜨는 크래시 루프가 된다.

Revision ID: 0068_consulting_contract_done
Revises: 0067_consulting_columns_per_sheet
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0068_consulting_contract_done"
down_revision = "0067_consulting_columns_per_sheet"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"

# 세우는 칸. `무료계약완료`/`유료계약완료` 라는 짧은 글자라 `String` 이다 —
# 옆의 `contract_received`(0048) · `quote_attached`(0065) 와 같은 모양이다.
ADDED = [("contract_done", sa.String())]

# 빼는 칸. 되돌릴 때 **같은 자료형으로** 다시 세워야 하므로 0065 가 적어 둔
# 것을 그대로 들고 있는다.
DROPPED = [("quote_attached", sa.String()), ("invoice_received", sa.String())]


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _add(columns) -> None:
    # 한 번에 하나씩 본다. 절반만 올라간 DB 에서도 나머지가 붙어야 한다 —
    # 묶어서 검사하면 그 DB 는 영영 안 채워진다.
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
    _drop(DROPPED)


def downgrade() -> None:
    _add(DROPPED)
    _drop(ADDED)
