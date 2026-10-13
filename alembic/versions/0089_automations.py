"""2단계 자동화의 스위치 — 표 하나

`automations` — 자동화마다 한 줄: 켜짐/꺼짐 · 보내는 계정 · 시험 모드 ·
시험방 · 자동화마다 다른 값(JSON). 무엇을 왜 이렇게 담는지는 `models.Automation`.

## 판 순서 — 머지 차례 #268 → #273 → 이 판

같은 때에 열린 두 판이 같은 부모(`0086_send_guard`)를 둔다 —
`0087_activity_sequence_trace`(#268) · `0088_ir_company_link`(#273). 그래서 이
판은 번호를 0089 로 두고, 이 브랜치에서는 `0086_send_guard` 위에 선다(혼자서
검사가 돌게). 머지는 **#268 → #273 → 이 판** 차례이고, 넣을 때 두 줄을 잇는다.

  · #273 의 `down_revision` → `0087_activity_sequence_trace` (#273 머리말에 적힌 대로)
  · 이 판의 `down_revision` → `0088_ir_company_link`

잇지 않으면 머리가 여럿이 되어 부팅에서 멎는다(`tests/test_migrations.py` 가 잡는다).

## 기본은 전부 꺼짐 · 시험 모드 켜짐

줄을 미리 넣지 않는다. 줄이 없는 것이 꺼짐이고, 화면에서 처음 저장할 때
줄이 선다 — 그때도 시험 모드는 켜진 채다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 표를
이미 갖고 시작한다. 있는지 보고 만든다(0078 과 같은 방식). 유일 색인은 표를
만드는 `if` **밖에서** 따로 본다.

## 되돌리기

표가 사라진다. 잃는 것은 자동화 설정뿐이다 — 나간 발송은 `send_jobs` ·
`send_items` 에 그대로 있다.

Revision ID: 0089_automations
Revises: 0086_send_guard
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0089_automations"
down_revision = "0086_send_guard"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    if "automations" not in _tables():
        op.create_table(
            "automations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("enabled", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.Column("test_mode", sa.Integer(), nullable=False,
                      server_default="1"),
            sa.Column("test_room", sa.String(), nullable=True),
            sa.Column("params", sa.Text(), nullable=True),
        )
    if "uq_automations_key" not in _indexes("automations"):
        op.create_index("uq_automations_key", "automations", ["key"],
                        unique=True)


def downgrade() -> None:
    if "uq_automations_key" in _indexes("automations"):
        op.drop_index("uq_automations_key", table_name="automations")
    if "automations" in _tables():
        op.drop_table("automations")
