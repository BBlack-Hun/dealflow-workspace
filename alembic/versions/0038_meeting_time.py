"""미팅 시각 — 몇 시에 만나는지

미팅을 잡을 때 날짜만 받고 있었다. 하루에 두 건이 잡히면 어느 쪽이 먼저인지
화면으로는 알 수 없고, 그날 아침에 시간을 다시 찾아봐야 했다.

**날짜 칸에 붙이지 않고 칸을 따로 둔다.** `meetings.scheduled_at` 은 여러
곳에서 **날짜 문자열 그대로** 견주고 있다 —

    app/services/report.py   scheduled_at >= 월초  and  scheduled_at <= 월말
    app/services/pipeline.py scheduled_at == 오늘 / > 오늘

여기에 `T14:00` 이 붙으면 `'2026-08-31T14:00' <= '2026-08-31'` 이 거짓이 되어
**그 달 마지막 날의 미팅이 월간 집계에서 통째로 빠지고**, 오늘 미팅도 하나도
안 잡힌다. 칸을 나누면 그 비교들이 그대로 산다.

비워 둘 수 있다(`nullable`). 날짜만 아는 단계가 실제로 있고, 이미 들어 있는
미팅은 시각을 모른다 — **모르면 비어 있는 것이 정확하다.**

Revision ID: 0038_meeting_time
Revises: 0037_contact_list_layout
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_meeting_time"
down_revision = "0037_contact_list_layout"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # **두 번 돌려도 죽지 않아야 한다.** 스탬프가 어긋난 DB 로 컨테이너가 뜨면
    # `duplicate column name` 으로 죽고, 다시 뜨고, 또 죽는 크래시 루프가 된다
    # — 실데이터가 든 DB 라 그 상태로는 손댈 수도 없다(0034·0037 과 같은 방식).
    if not _has_column("meetings", "scheduled_time"):
        with op.batch_alter_table("meetings") as b:
            b.add_column(sa.Column("scheduled_time", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("meetings", "scheduled_time"):
        with op.batch_alter_table("meetings") as b:
            b.drop_column("scheduled_time")
