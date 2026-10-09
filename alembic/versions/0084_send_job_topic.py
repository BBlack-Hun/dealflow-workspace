"""스타트업 안내 카톡 — 회차에 **무슨 문구였는지** 칸 하나

`send_jobs.topic` — 스타트업 안내 카톡(`startup_msg`) 회차가 어느 문구로
나갔는가(`startup_msg_progress` · `startup_msg_quote` · `startup_msg_free`).
"이 기업이 이 문구를 언제 받았나"(마지막 발송일 · N일 안에 받은 곳 빼기)가
이 값을 읽는다(`services/startup_outreach.py`). 나머지 잡 종류에서는 비어 있다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 칸을
이미 갖고 시작한다. 있는지 보고 넣는다(0082 · 0083 과 같은 방식).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084_send_job_topic"
down_revision = "0083_startup_monthly_auto"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    have = _columns("send_jobs")
    if not have:
        return
    if "topic" not in have:
        op.add_column("send_jobs", sa.Column("topic", sa.String(), nullable=True))


def downgrade() -> None:
    if "topic" in _columns("send_jobs"):
        with op.batch_alter_table("send_jobs") as batch:
            batch.drop_column("topic")
