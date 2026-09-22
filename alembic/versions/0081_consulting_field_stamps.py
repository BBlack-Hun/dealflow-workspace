"""투자컨설턴트 리스트 — **칸마다 `수정한 날짜`** 를 담을 자리

## 무엇을

`consulting_companies` 에 `field_stamps` 를 더한다 — `{"칸 이름": "시각"}` 을
담는 JSON 글자다(`{"deal_pitch": "2026-09-21T14:30:12+09:00", "note:12": …}`).

화면에서는 세 칸 밑에 잔글씨로 선다 — `딜 소개문구` · `카톡 연결 여부` ·
`당월 리마인드`(보이는 석 달치가 **각자 제 날짜**를 갖는다).

## 왜 `updated_at` 으로 안 되나

저것은 **줄 전체**가 마지막으로 바뀐 때다. 딜 소개문구만 고쳤는데 옆
`카톡 연결 여부` 밑에도 같은 날짜가 뜨면 화면이 거짓말을 한다.

## 왜 `edit_logs` 에서 못 끌어오나 — **두 가지가 다 막는다**

  · **자기 줄을 고친 것은 아예 안 남는다.** `services/edit_log.py` 의
    `_row_scope` 가 `owner_id == actor_id` 인 UPDATE 를 버린다(하루 수백 줄이
    쌓이면 아무도 안 보기 때문이다). 이 표는 줄마다 담당이 붙어 있고 그 담당이
    자기 줄을 고치는 화면이라 **거의 모든 편집이 안 남는다.**
  · **달을 구분할 수가 없다.** 월별 리마인드 석 달치가 `notes` **한 칸**에
    JSON 으로 들어 있어서 로그에는 `notes 바뀜` 한 줄만 남는다.

둘 다 고쳐 로그를 쓰게 만드는 길도 있었지만, 그러면 로그의 보안·용량 규칙을
바꾸는 일이 되고 344줄을 그릴 때마다 로그 표를 뒤져야 한다. 값이 줄에 붙어
있으면 **표를 그릴 때 조회가 한 번도 안 는다.**

## 왜 칸을 다섯 개 세우지 않나

리마인드가 석 달치라 날짜가 다섯 개 는다. 칸으로 세우면 이미 2,600px 넘는 표가
한 화면에서 영영 안 보인다. 그리고 달이 바뀔 때마다 칸이 하나씩 더 늘어야
한다 — 월별 리마인드를 칸이 아니라 JSON 으로 둔 이유와 같다(`models` 머리글).

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

NULL 로 시작한다. 화면에서는 날짜가 아예 안 뜬다.

**`updated_at` 을 읽어다 채우지 않는다.** 그것은 줄 전체의 시각이라, 옮겨
담으면 **한 번도 고친 적 없는 칸에** 날짜가 붙는다 — 앱이 아무도 확인한 적
없는 사실을 단정하는 것이다(0047 · 0048 · 0049 · 0065 · 0068 · 0077 · 0078 이
같은 이유로 backfill 을 안 했다). 그 칸을 다음에 고치는 순간 제 날짜가 붙는다.

## 되돌리면

칸을 지운다. 여기에 쌓인 날짜는 안 돌아온다 — 이 칸에서 처음 생긴 값이라
옮겨 둘 자리가 없다. **줄의 값은 하나도 안 잃는다** — 날짜만 사라진다.

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면 건너뛴다 — 0048 · 0049 · 0065 · 0068 · 0077 · 0078 · 0079 와
같은 방식이다.

Revision ID: 0081_consulting_field_stamps
Revises: 0080_consulting_management_detail
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0081_consulting_field_stamps"
down_revision = "0080_consulting_management_detail"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"

# JSON 글자라 `Text` 다 — 바로 위 `notes` 와 같은 모양이고 같은 이유다
# (열쇠가 몇 개까지 늘지 모른다).
ADDED = [("field_stamps", sa.Text())]


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _add(columns) -> None:
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
