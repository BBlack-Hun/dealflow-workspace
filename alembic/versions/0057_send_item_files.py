"""발송 한 건에 **붙여 보낼 자료 파일명**을 함께 굳혀 둔다

## 무엇이 비어 있었나

발송기는 파일을 붙여 보낼 줄 안다(0055·#110). 그런데 **어느 파일을 보낼지가
잡에 실리지 않았다** — 파일명은 발송 화면의 `[보낼 자료]` 목록(사람이 눌러
내려받는 자리)에만 있었다. 그래서 [자료 보내기] 를 눌러도 문구만 나갔다.

`send_items` 에 칸 하나를 더한다. 값은 발송 목록을 만들 때 적히고
(`app/routers/deals.py: create_send_list`), 발송기가 폴링 응답으로 받아 간다.

## 왜 `send_items` 인가 — 왜 그때 기업 표를 다시 읽지 않나

`message` 와 **같은 성질의 값**이기 때문이다. 발송 목록은 만든 순간의
스냅숏이다: 문구도, 방 이름도 그때 굳는다. 파일만 나중에 다시 읽으면, 목록을
만든 뒤 기업의 자료 칸을 고친 순간 **문구는 "1번 기업 …" 인데 다른 파일이
나간다.** 나가고 나면 되돌릴 수 없다.

`parts_json` 바로 옆자리다 — 같은 건을 어떻게 나눠 보내는지를 적는 자리.

## 왜 `send_jobs` 가 아닌가

한 잡의 모든 건이 같은 기업 묶음을 받는 것은 **지금의 화면이 그럴 뿐**이다.
받는 사람마다 다른 자료를 보내는 날(요청한 기업이 사람마다 다르다 — `ir.html`
의 [자료 보내기] 가 이미 사람별로 묶는다) 잡에 매달아 두면 그 자리가 없다.
`message` 가 건마다 다른 것과 같은 이유다.

## 되돌리기

칸을 지운다. 값은 발송 목록을 만들 때 다시 적히는 것이라 잃을 기록이 아니다 —
칸이 없으면 파일이 실리지 않을 뿐이고, 그러면 **문구만 나가고 자료는 사람이
PC 에서 손으로 첨부하는** 예전 동작으로 돌아간다. 내려간 상태로도 위험하지
않다(자료 없이 "보내드렸습니다" 만 나가지 않게, 화면의 첨부 안내창도 함께
되살아난다).

Revision ID: 0057_send_item_files
Revises: 0056_ir_file_name
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057_send_item_files"
down_revision = "0056_ir_file_name"
branch_labels = None
depends_on = None

TABLE = "send_items"
COLUMN = "files_json"


def _has_column() -> bool:
    """빈 DB 길에서는 `0001` 이 모델 전체를 이미 만들어 둔다.

    그 자리에 또 붙이면 `duplicate column name` 으로 **부팅이 죽는다**
    (`tests/test_migrations.py` 가 지키는 규칙이다).
    """
    cols = sa.inspect(op.get_bind()).get_columns(TABLE)
    return any(c["name"] == COLUMN for c in cols)


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
