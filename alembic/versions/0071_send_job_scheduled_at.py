"""예약 발송 — 회차가 **언제 나갈지**(`scheduled_at`)와 **풀린 시각**(`released_at`)

## 왜 두 칸인가

**언제 보낼지**와 **이미 풀렸는지**는 다른 것이다.

- `send_jobs.scheduled_at` — 사람이 정한 시각. 이 값이 있으면 회차는 `draft`
  로 서서 기다린다. **`queued` 로 미리 만들어 두고 나중에 거르지 않는다** —
  발송기는 `queued` 만 집어가므로(`routers/agent_api.py: poll`) 그 사이 폴링에
  그대로 새어 나간다.
- `send_jobs.released_at` — 그 예약을 푼 시각. **두 번 풀리지 않게 하는
  자물쇠**다. 푸는 쪽이 이 칸이 빈 줄만 원자적으로 집는다
  (`services/scheduled_send.py: _claim`).

한 칸으로 줄이려면 상태(`draft`→`queued`)로 집어야 하는데, 그러면 상태를 먼저
올려 커밋한 순간 발송기가 집어갈 수 있다. 뒤이어 대기 건을 세우는 쪽이 상태를
한 번 더 만지면 이미 `running` 인 회차를 `queued` 로 되돌려 **같은 사람에게 두
번** 나간다. 되돌릴 수 없는 일이라 칸 하나를 더 두는 편이 싸다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다 — 새 DB 는 두 칸을
이미 갖고 시작한다. 그대로 `add_column` 하면 `duplicate column` 으로 **부팅이
죽는다**(`tests/test_migrations.py` 가 지키는 그것이다). 그래서 있는지 보고 넣는다.

## 되돌리기를 비워 두지 않는다

비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서 멎는다(0012 가 그랬다).
SQLite 는 `drop_column` 에 표를 다시 만들어야 해서 `batch_alter_table` 로 한다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0071_send_job_scheduled_at"
down_revision = "0070_startup_send_room"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    have = _columns("send_jobs")
    if "scheduled_at" not in have:
        op.add_column("send_jobs",
                      sa.Column("scheduled_at", sa.String(), nullable=True))
    if "released_at" not in have:
        op.add_column("send_jobs",
                      sa.Column("released_at", sa.String(), nullable=True))


def downgrade() -> None:
    have = _columns("send_jobs")
    with op.batch_alter_table("send_jobs") as batch:
        if "released_at" in have:
            batch.drop_column("released_at")
        if "scheduled_at" in have:
            batch.drop_column("scheduled_at")
