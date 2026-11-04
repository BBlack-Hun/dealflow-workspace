"""Series A 이상 딜 소싱 줄 → `메모`(#142) · `IR 투자컨설팅 미팅일시`(#143) 칸

#142: "Series A 이상 딜소싱 기업명 컬럼 오른쪽에 메모 컬럼 삽입, 수정담당자명, 수정일 컬럼".
`수정한 날짜` 는 있던 `updated_at`, `수정한 팀원` 은 수정 로그에서 읽어 칸이 따로 없다 —
새 칸은 `memo` 하나다. #143: "후속라운드 시작 컬럼 오른쪽에 IR 투자컨설팅 미팅일시간".
사람이 적는 칸이고 `YYYY-MM-DD HH:MM` 으로 맞춘다(`routers/series_a.meeting_text`).

빈 DB 는 `0001_initial` 이 `create_all()` 로 만든다 — 칸이 있는지 보고 붙인다.
되돌리기: 칸을 뗀다(그 값만 사라지고 줄은 그대로다).

Revision ID: 0131_series_a_memo_meeting
Revises: 0130_channel_sms
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0131_series_a_memo_meeting"
down_revision = "0130_channel_sms"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"
COLUMNS = {"memo": sa.Text, "consulting_meeting_at": sa.String}


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    have = _columns()
    for name, kind in COLUMNS.items():
        if have and name not in have:
            op.add_column(TABLE, sa.Column(name, kind(), nullable=True))


def downgrade() -> None:
    gone = [name for name in COLUMNS if name in _columns()]
    if gone:
        with op.batch_alter_table(TABLE) as batch:
            for name in gone:
                batch.drop_column(name)
