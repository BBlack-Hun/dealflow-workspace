"""`관리 스타트업` 탭 — `딜 소개문구` 칸(메모처럼 쓰는 긴 글)

## 왜 칸을 새로 만드나

투자사에 이 기업을 어떻게 소개할지 적어 두는 자리가 표에 없었다. 지금까지는
바로 옆 `기업 관리` 칸에 같이 적혀 있었는데, 그 칸은 **지금 어떻게 되고
있는가**(관리중 / 드랍 이유 / 백업팀 전환)를 적는 자리라 성격이 다르다.
섞어 두면 두 가지가 한 문단에 엉키고, 무엇보다 `기업 관리` 는 그 값으로
칩과 KPI 를 세는 칸이라(`services/consulting_status.py`) 소개 문구가 길게
붙는 순간 `관리` 라는 낱말이 문구 안에 우연히 들어 있다는 이유로 엉뚱한
갈래에 걸린다.

## 왜 `Text` 인가

메모처럼 쓰는 칸이다. 한 줄짜리 값이 아니라 문단이 들어오고 줄바꿈도 그대로
남아야 한다 — 같은 성격인 `management` · `notes` · `source_line` 이 이미
`Text` 다. `String` 으로 두면 SQLite 에서는 지금 당장 차이가 없지만, 이
저장소가 나중에 다른 DB 로 옮길 때 길이 제한에 걸리는 자리가 된다.

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

새 칸은 전부 NULL 로 시작한다. 화면에서는 빈칸이다.

`기업 관리` 에 적힌 문장을 옮겨 오거나 나눠 담고 싶어지는 자리인데, 그러면
앱이 **어디까지가 소개 문구인지 지어내는 것**이 된다. 두 가지가 한 칸에
섞여 있다는 것까지는 사실이지만 그 경계는 아무도 정한 적이 없고, 잘못 나눈
뒤에는 원래 한 줄이 어땠는지 남지 않는다. 사람이 읽고 옮기는 것이 맞다.
이 저장소가 값을 지어 넣지 않는 것과 같은 이유다(0048 이 backfill 을 안 한
것, `split_contract_line` 이 적힌 그대로 옮기는 것).

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면 건너뛴다(0048 · 0040 · 0037 과 같은 방식). 스탬프가 어긋난
DB 로 컨테이너가 뜨면 `duplicate column name` 으로 죽고 다시 뜨는 크래시
루프가 된다.

## 되돌리면

칸을 지운다. 적어 둔 문구도 같이 사라지는데, 되돌릴 곳이 없는 값이라
(다른 칸에서 옮겨 온 것이 아니라 이 칸에서 처음 생긴 값이다) 남겨 둘 자리가
없다 — 0040 의 `source_line` 처럼 원본이 따로 있는 경우와 다르다.

Revision ID: 0049_consulting_deal_pitch
Revises: 0048_consulting_contract_received
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049_consulting_deal_pitch"
down_revision = "0048_consulting_contract_received"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"
COLUMN = "deal_pitch"


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if _has_column(TABLE, COLUMN):
        return
    with op.batch_alter_table(TABLE) as b:
        b.add_column(sa.Column(COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    if not _has_column(TABLE, COLUMN):
        return
    with op.batch_alter_table(TABLE) as b:
        b.drop_column(COLUMN)
