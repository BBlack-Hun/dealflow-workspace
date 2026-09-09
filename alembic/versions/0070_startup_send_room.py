"""스타트업 월간 발송 — 기업 카톡방 이름 한 칸, 발송 건이 가리킬 기업 한 칸

## 왜 두 칸인가

**보낼 곳**과 **보낸 기록**은 다른 것이다.

- `ir_companies.kakao_room_name` — 그 기업 대표와의 카톡방 제목. 지금까지 앱이
  스타트업에게 보내지 못한 까닭이 이 칸이 없어서였다(`routers/startup.py` 에
  "스타트업 카톡방이 자료에 없다" 고 적혀 있던 그것이다).
- `send_items.ir_company_id` — 이 발송 건이 **어느 기업 줄**로 갔나. 받는 쪽이
  투자사(`contact_id`)도 소싱 명단(`sourcing_contact_id`)도 아니라, 가리킬 칸이
  하나 더 필요했다. 셋 중 하나만 찬다.

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

revision = "0070_startup_send_room"
down_revision = "0069_auto_send"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if "kakao_room_name" not in _columns("ir_companies"):
        op.add_column("ir_companies",
                      sa.Column("kakao_room_name", sa.String(), nullable=True))

    if "ir_company_id" not in _columns("send_items"):
        # 외래키를 붙이지 않는다. SQLite 에서 `add_column` 에 FK 를 얹으려면
        # 표를 통째로 다시 만들어야 하는데, `send_items` 는 발송 이력이라
        # 다시 만드는 값이 크다. 모델 쪽 관계는 그대로 돌고
        # (`SendItem.ir_company` 는 이 칸으로 잇는다), 이 칸에 들어오는 값을
        # 정하는 자리는 하나뿐이다(`routers/deals.create_send_list`).
        op.add_column("send_items",
                      sa.Column("ir_company_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    if "ir_company_id" in _columns("send_items"):
        with op.batch_alter_table("send_items") as batch:
            batch.drop_column("ir_company_id")
    if "kakao_room_name" in _columns("ir_companies"):
        with op.batch_alter_table("ir_companies") as batch:
            batch.drop_column("kakao_room_name")
