"""손으로 보낸 것을 적을 자리 — 활동 이력에 **묶음 표시**와 **되돌림 표시**

## 왜

카톡을 프로그램으로 보내지 않고 **손으로 보내는** 사람이 있다. 그 사람이 한
일은 지금 아무 데도 안 남아서, 진행 단계도 리마인드도 보고도 그 사람만 비어
있다. 적을 자리는 이미 있다(`contact_activities` — 앱이 안 보낸 일을 적는
자리다: `ir_delivery` · `meeting_ask`). 모자란 것은 두 가지뿐이다.

1. **어느 판으로 들어왔나** — 한 번에 80명을 적는 길이 생긴다. 잘못 적었을 때
   묶음째 되돌리려면 그 80줄이 같은 표시를 달고 있어야 한다. 줄마다 지우게
   하면 80번을 눌러야 하고, 몇 줄을 빠뜨렸는지 알 길이 없다.
2. **되돌렸나** — 지우지 않는다. 이 표는 보고·진행 단계·이력이 함께 읽는
   자리라, 지우면 무엇이 있었는지 물을 데가 없다(`VcContact.is_hidden` 과
   같은 뜻이다: 잘못 올라간 날 되돌릴 수 있어야 한다).

사람이 적었다는 표시는 **칸을 더하지 않는다** — 이미 있는 `source` 에
`manual` 이라는 값을 하나 더 쓴다(지금 값은 `import` · `system`). 글자 칸이라
옛 줄은 한 줄도 안 옮긴다.

## 값을 채우지 않는다

`INSERT` 도 `UPDATE` 도 없다. 지금 서 있는 줄은 전부 가져오기·발송이 만든
것이고, 묶음으로 들어온 적도 되돌려진 적도 없다 — 둘 다 `NULL` 이 맞는 값이다.
`undone_at` 이 비어 있는 것이 **보이는 줄**이라, 옛 줄은 그대로 다 보인다.

## 되돌리기

칸 둘을 지운다(색인도 함께). 값을 한 글자도 안 옮겼으므로 되돌린 DB 는 이
이전 전과 같은 자료다.

Revision ID: 0076_manual_send_log
Revises: 0075_column_month_kind
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0076_manual_send_log"
down_revision = "0075_column_month_kind"
branch_labels = None
depends_on = None

TABLE = "contact_activities"
INDEX = "ix_contact_activities_batch_key"


def _columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _indexes() -> set:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(TABLE)}


def upgrade() -> None:
    # **두 번 돌려도 죽지 않아야 한다.** `0001_initial` 이 `create_all()` 로 지금
    # 모델 전체를 만들기 때문에, 빈 DB 는 이 칸들을 이미 갖고 시작한다 — 그대로
    # 붙이면 `duplicate column name` 으로 부팅에서 죽는다
    # (`tests/test_migrations.py` 가 지키는 그것이다).
    have = _columns()
    # **`server_default` 를 주지 않는다.** 둘 다 `NULL` 이 뜻 있는 값이다 —
    # 묶음 없이 들어온 줄이고, 되돌려지지 않은 줄이다. 빈 글자로 채우면
    # "묶음 이름이 빈 글자인 묶음" 이 하나 생겨 80줄이 거기 섞인다.
    if "batch_key" not in have:
        op.add_column(TABLE, sa.Column("batch_key", sa.String(), nullable=True))
    if "undone_at" not in have:
        op.add_column(TABLE, sa.Column("undone_at", sa.String(), nullable=True))
    # 묶음 하나를 되돌릴 때마다 이 칸으로 80줄을 찾는다.
    if INDEX not in _indexes():
        op.create_index(INDEX, TABLE, ["batch_key"])


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    if INDEX in _indexes():
        op.drop_index(INDEX, table_name=TABLE)
    have = _columns()
    if "undone_at" in have:
        op.drop_column(TABLE, "undone_at")
    if "batch_key" in have:
        op.drop_column(TABLE, "batch_key")
