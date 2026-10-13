"""2단계 자동화의 스위치 — 표 하나

`automations` — 자동화마다 한 줄: 켜짐/꺼짐 · 보내는 계정 · 시험 모드 ·
시험방 · 자동화마다 다른 값(JSON). 무엇을 왜 이렇게 담는지는 `models.Automation`.

## 번호가 0088 인 까닭

같은 때에 열린 다른 PR 이 `0087_activity_sequence_trace` 를 쓴다. 이 판은
`0086_send_guard` 위에 선다 — 둘 중 나중에 들어가는 쪽이 `down_revision` 을
앞의 것으로 고쳐 머리를 하나로 맞춘다(`tests/test_migrations.py` 가 머리가
둘이면 멈춘다).

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

Revision ID: 0088_automations
Revises: 0086_send_guard
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0088_automations"
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
