"""발송 안전장치 — 칸 둘

- `users.daily_send_cap` — 이 계정으로 하루에 몇 통까지 보내나. 발송기가 잡을
  집어갈 때 서버가 그날 나간 수를 세어 남은 만큼만 내준다
  (`services/send_guard.py`). 기본 200.
- `send_jobs.alerted_at` — 자동 회차가 실패로 끝났거나 예약 시각을 놓쳤을 때
  관리자에게 알린 시각. 같은 회차로 메일이 두 번 가지 않게 하는 자물쇠다.

## 이미 있는 계정은 200 이다

`server_default="200"` 이라 칸을 더하는 순간 모든 줄이 기본값을 갖는다. 지난
두 달 동안 한 계정이 하루에 보낸 것이 가장 많은 날 139통이었다 — 지금 쓰는
만큼은 막히지 않는다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 칸들을
이미 갖고 시작한다. 있는지 보고 넣는다(0082 · 0084 · 0085 와 같은 방식).

## 되돌리기

되돌려도 잃는 것은 **계정마다 고친 상한**과 알림 표시뿐이다. 보낸 기록은
`send_items` 에 그대로 있다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086_send_guard"
down_revision = "0085_contact_room_candidates"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    users = _columns("users")
    if users and "daily_send_cap" not in users:
        op.add_column("users", sa.Column("daily_send_cap", sa.Integer(),
                                         nullable=False, server_default="200"))
    jobs = _columns("send_jobs")
    if jobs and "alerted_at" not in jobs:
        op.add_column("send_jobs",
                      sa.Column("alerted_at", sa.String(), nullable=True))


def downgrade() -> None:
    if "alerted_at" in _columns("send_jobs"):
        with op.batch_alter_table("send_jobs") as batch:
            batch.drop_column("alerted_at")
    if "daily_send_cap" in _columns("users"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("daily_send_cap")
