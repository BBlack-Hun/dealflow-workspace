"""스타트업 월간 발송 매월 자동 예약 — 설정 줄에 칸 둘

`auto_send_settings` 의 `startup_ir` 줄이 이미 "누가 보내는가" 를 담는다
(`services/startup_send.py`). 같은 줄에 **매월 자동으로 세울지**와 **몇 시에
나갈지**를 붙인다 — 표를 새로 세우면 설정이 두 군데로 갈린다.

- `monthly_auto` — 0/1. 기본 꺼짐(이미 있는 줄도 꺼짐으로 채운다).
- `monthly_time` — `HH:MM`. 기본 `17:00`.

달마다 한 번만 세웠다는 표시는 이미 있는 `auto_send_runs` 의
`(kind, ref_id)` 유일 색인을 그대로 쓴다(`ref_id` = `YYYYMM`).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 두 칸을
이미 갖고 시작한다. 있는지 보고 넣는다(0082 와 같은 방식).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0083_startup_monthly_auto"
down_revision = "0082_startup_room_match"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    have = _columns("auto_send_settings")
    if not have:
        return
    if "monthly_auto" not in have:
        op.add_column("auto_send_settings",
                      sa.Column("monthly_auto", sa.Integer(), nullable=False,
                                server_default="0"))
    if "monthly_time" not in have:
        op.add_column("auto_send_settings",
                      sa.Column("monthly_time", sa.String(), nullable=False,
                                server_default="17:00"))


def downgrade() -> None:
    have = _columns("auto_send_settings")
    for name in ("monthly_time", "monthly_auto"):
        if name in have:
            with op.batch_alter_table("auto_send_settings") as batch:
                batch.drop_column(name)
