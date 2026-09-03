"""주간 업무 체크리스트 + 반복 업무

시트에 '항목 · 세부업무 · 일시 · 상태' 로 손으로 적던 표다. 목록 아래에는
"* 이메일 발송 — 매주 화요일, 목요일" 같은 규칙이 글로 적혀 있었고, 사람이 그걸
읽고 매주 옮겨 적다 보니 빠지는 주가 생겼다. 규칙을 담아 두고 요일이 오면
그 주 목록에 저절로 생기게 한다.

Revision ID: 0016_weekly_tasks
Revises: 0015_send_channel
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_weekly_tasks"
down_revision = "0015_send_channel"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    have = _tables()
    if "weekly_routines" not in have:
        op.create_table(
            "weekly_routines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("weekdays", sa.String(), nullable=False, server_default=""),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    if "weekly_tasks" not in have:
        op.create_table(
            "weekly_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("week_start", sa.String(), nullable=False),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("due_date", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="todo"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("routine_id", sa.Integer(),
                      sa.ForeignKey("weekly_routines.id"), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )

    # **인덱스는 표를 만드는 것과 따로 본다.** 빈 DB 는 0001 의
    # `create_all()` 이 표를 이미 만들어 둔 채로 오는데, 모델에는 이 인덱스가
    # 선언돼 있지 않다. 표 만들기 안에 넣어 두면 그 길에서 통째로 건너뛰어,
    # **새 서버만 인덱스 없이** 도는 DB 가 된다(0005 가 쓰는 방식).
    #
    # 화면이 매번 타는 조건: 내 것 중 이번 주
    if not _has_index("weekly_tasks", "ix_weekly_tasks_user_week"):
        op.create_index("ix_weekly_tasks_user_week", "weekly_tasks",
                        ["user_id", "week_start"])


def downgrade() -> None:
    have = _tables()
    if "weekly_tasks" in have:
        op.drop_table("weekly_tasks")
    if "weekly_routines" in have:
        op.drop_table("weekly_routines")
