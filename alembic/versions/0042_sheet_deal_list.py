"""딜 소개를 보내는 명단 표시

딜 제안 관리의 발송 대상이 **"내가 들고 있는 줄 중 카톡방 연결이 끝난 사람"**
이었다. 그래서 딜 소개 명단에 올린 적이 없는 **투자사 풀** 사람까지 목록에
떴다 — 실데이터에서 142명 중 17명이 그랬다(풀 세 곳에서 9·7·1명).

기준은 `전체 딜소개현황` 명단이다. 그런데 **명단 이름을 코드에 적으면 안
된다**: 지금 이름은 `전체 딜소개현황(125명)` 처럼 괄호 안 인원이 붙어 있고
그 수는 사람이 늘 때마다 바뀐다. `layout`·`is_hidden` 과 같은 방식으로
**명단에 붙은 값**으로 정한다.

`nullable` 이다. `NULL` 은 "아직 사람이 정하지 않았다" 이고, 그때는 **할당
여부를 따른다**(할당된 명단 = 내가 딜소개를 보내는 명단 —
`app/services/sheet_owner.py` 의 정의 그대로). 그래서 **뒤채움이 필요 없다**:
지금 데이터에서 할당된 명단은 `전체 딜소개현황` 하나뿐이라, 이 열이 비어
있는 것만으로 원하는 결과가 나온다. 0/1 로 채워 두면 나중에 명단이 늘 때
"채워 넣는 것을 잊은 명단" 만 조용히 발송에서 빠진다.

Revision ID: 0042_sheet_deal_list
Revises: 0041_monthly_column_runs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_sheet_deal_list"
down_revision = "0041_monthly_column_runs"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # **두 번 돌려도 죽지 않아야 한다.** 스탬프가 어긋난 DB 로 컨테이너가 뜨면
    # `duplicate column name` 으로 죽고, 다시 뜨고, 또 죽는 크래시 루프가 된다
    # — 실데이터가 든 DB 라 그 상태로는 손댈 수도 없다(0037·0038 과 같은 방식).
    if not _has_column("sheet_owners", "is_deal_list"):
        with op.batch_alter_table("sheet_owners") as b:
            b.add_column(sa.Column("is_deal_list", sa.Integer(), nullable=True))


def downgrade() -> None:
    if _has_column("sheet_owners", "is_deal_list"):
        with op.batch_alter_table("sheet_owners") as b:
            b.drop_column("is_deal_list")
