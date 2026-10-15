"""`Series A 이상 기업` 가져오기 열쇠 — `series_a_companies.import_key`

시트 가져오기(`services/series_a_import.py`)가 한 줄을 `(기업명, 수신 일자)` 로만
알아봐서 두 가지가 어긋났다.

  · 같은 날 **다른 투자사에게서** 받은 같은 기업 딜이 한 줄로 뭉쳐, 둘째부터
    버려졌다.
  · 앱에서 기업명 · 수신 일자를 고치면 열쇠가 바뀌어, 다시 가져올 때 같은 딜이
    **새 줄로 또** 섰다.

그래서 **가져온 그때의 시트 줄**(기업명 · 수신 일자 · 공유 심사역 · 회사를 다듬은
값)을 칸에 적어 두고 그것으로 맞춘다. 앱에서 고쳐도 다시 셈하지 않는다.

## 이미 있는 줄은 채우지 않는다

이 판에서 지금 값으로 열쇠를 셈해 채우면, 가져온 뒤 앱에서 고친 줄은 **고친 값**
이 열쇠가 되어 다음 가져오기에서 시트 줄과 안 맞고 새 줄이 선다 — 막으려던 바로
그 일이다. 비워 두면 다음 가져오기가 예전 열쇠 `(기업명, 수신 일자)` 로 한 번 맞춰
그 시트 줄의 열쇠를 적는다(그 열쇠로 맞는 줄이 하나일 때만 — 서비스 머리말).

## 이 판의 번호 — 머지 차례에 따라 다시 이어야 한다

지금 `main` 의 머리는 `0095_series_a_shares` 다. 열려 있는 PR 이 0096 ~ 0100 을,
같은 때 고치는 Series A 딜 공유 PR 이 0101 을 쓸 수 있어 겹치지 않게 0102 를
쓴다. **먼저 들어간 판이 있으면 `down_revision` 을 그 판으로 바꿔** 머리가
하나가 되게 맞춘다(`alembic heads` 가 하나여야 한다).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 칸을
이미 갖고 시작한다. 있는지 보고 넣는다(0084 와 같은 방식).

## 되돌리기

칸째 지운다 — 잃는 것은 열쇠뿐이다(줄과 값은 그대로). 다시 올리면 빈 칸으로
돌아오고, 다음 가져오기가 예전 열쇠로 다시 맞춘다.

Revision ID: 0102_series_a_import_key
Revises: 0095_series_a_shares
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0102_series_a_import_key"
down_revision = "0095_series_a_shares"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"
COLUMN = "import_key"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    if have and COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
