"""미팅 후기 · 결과 문의 메모

미팅이 끝나고 무슨 얘기가 오갔는지, 열흘 뒤 결과를 물었을 때 뭐라고 했는지를
적을 칸이 없었다. 결과는 `outcome` 한 칸(진행/보류/거절)뿐이라 **왜 그런지**가
남지 않는다 — 다음 회차에 이 투자사를 어떻게 대할지는 거기서 나온다.

둘을 나눠 둔다. 미팅 자리에서 들은 것과 열흘 뒤 전화로 들은 것은 다른
시점의 이야기라, 한 칸에 섞으면 언제 들은 말인지 알 수 없다.

Revision ID: 0034_meeting_notes
Revises: 0033_ref_sheet_page
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_meeting_notes"
down_revision = "0033_ref_sheet_page"
branch_labels = None
depends_on = None


#: 새로 붙일 칸. `followup_at` 은 언제 물었는지 — `followup_done` 만으로는
#: 오늘 물은 건지 지난달에 물은 건지 알 수 없다.
NEW_COLUMNS = (
    ("note", sa.Text()),
    ("followup_note", sa.Text()),
    ("followup_at", sa.String()),
)


def upgrade() -> None:
    # **이미 있는 칸은 건너뛴다.** 마이그레이션이 도중에 끊기면(컨테이너가
    # 다시 뜨는 등) 앞쪽 칸만 들어간 채로 남는데, 그대로 다시 돌리면
    # `duplicate column name` 으로 영영 못 지나간다 — 실제로 그렇게 멎었다.
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("meetings")}
    with op.batch_alter_table("meetings") as b:
        for name, kind in NEW_COLUMNS:
            if name not in have:
                b.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("meetings")}
    with op.batch_alter_table("meetings") as b:
        for name, _kind in reversed(NEW_COLUMNS):
            if name in have:
                b.drop_column(name)
