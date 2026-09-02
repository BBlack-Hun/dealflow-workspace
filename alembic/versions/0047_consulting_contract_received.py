"""`월간 계약 업무현황표` — `계약서 수신여부` 칸(`O`/`X`)

## 왜 칸을 새로 만드나

계약을 맺은 것과 **계약서를 받은 것**은 다른 사실이다. 지금까지는 그 둘이
`계약여부`(`무료`/`유료`) 한 칸에 섞여 있어서, 계약은 했는데 서류가 아직
안 온 곳을 표에서 가려낼 방법이 없었다.

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

새 칸은 전부 NULL 로 시작한다. 화면에서는 빈칸이고, 그 빈칸이 곧
`아직 안 정함` 이다.

전부 `X` 로 채우고 싶어지는 자리인데, 그러면 앱이 "이 계약들은 계약서를
안 받았다"고 **단정**하는 것이 된다. 아무도 확인한 적 없는 사실이고, 나중에
사람이 채워 넣을 때 이미 `X` 가 적혀 있으면 **누가 확인한 X 인지 아무도
모른다** — 비어 있어야 "아직 안 봤다"가 눈에 보인다. 이 저장소가 값을 지어
넣지 않는 것과 같은 이유다(0040 이 `계약일` 이 적힌 줄을 안 건드린 것,
`split_contract_line` 이 적힌 그대로 옮기는 것).

빈칸인 줄을 찾는 길은 있다 — 머리글 `계약서 수신여부 ▾` 에 `(비어 있음)` 이
선다(`static/js/filters.js`).

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면 건너뛴다(0040 · 0037 과 같은 방식). 스탬프가 어긋난 DB 로
컨테이너가 뜨면 `duplicate column name` 으로 죽고 다시 뜨는 크래시 루프가 된다.

## 되돌리면

칸을 지운다. 적어 둔 `O`/`X` 도 같이 사라지는데, 되돌릴 곳이 없는 값이라
(다른 칸에서 옮겨 온 것이 아니라 이 칸에서 처음 생긴 값이다) 남겨 둘 자리가
없다 — 0040 의 `source_line` 처럼 원본이 따로 있는 경우와 다르다.

Revision ID: 0047_consulting_contract_received
Revises: 0046_promo_mail_ref
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_consulting_contract_received"
down_revision = "0046_promo_mail_ref"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"
COLUMN = "contract_received"


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if _has_column(TABLE, COLUMN):
        return
    with op.batch_alter_table(TABLE) as b:
        b.add_column(sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    if not _has_column(TABLE, COLUMN):
        return
    with op.batch_alter_table(TABLE) as b:
        b.drop_column(COLUMN)
