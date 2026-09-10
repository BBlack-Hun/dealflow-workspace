"""수정 로그 — 남의 것 · 공용 자료를 고친 일이 남는 표(`edit_logs`)

## 왜 표가 하나인가

`남의 것을 고쳤을 때` 와 `공용 화면을 고쳤을 때` 를 **한 표에 묶는다.** 보는
사람이 알고 싶은 것은 "내가 안 한 변경이 무엇인가" 하나이고, 그것을 두 화면에
갈라 놓으면 두 곳을 다 열어야 알 수 있다. 둘을 가르는 것은 `scope` 칸이다
(`others` · `shared`).

## `TimestampMixin` 을 쓰지 않는다

이 표의 줄은 고쳐지지 않는다 — `updated_at` 이 뜻을 갖지 않는다. 언제인지는
`at` 하나면 된다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 표를
이미 갖고 시작한다. 여기서 또 만들면 `table already exists` 로 부팅이 죽는다
(`tests/test_migrations.py` 가 지키는 그것이다). 색인도 표를 만드는 `if`
**밖에서** 따로 본다 — 안에 넣으면 빈 DB 길에서 통째로 건너뛴다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0072_edit_log"
down_revision = "0071_send_job_scheduled_at"
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
    if "edit_logs" not in _tables():
        op.create_table(
            "edit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("at", sa.String(), nullable=True),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
            # 공용 자료는 주인이 없다 — 비어 있다.
            sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.Column("scope", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("table_name", sa.String(), nullable=False),
            sa.Column("row_id", sa.Integer(), nullable=False),
            sa.Column("screen", sa.String(), nullable=True,
                      server_default=""),
            sa.Column("row_label", sa.String(), nullable=True,
                      server_default=""),
            sa.Column("method", sa.String(), nullable=True, server_default=""),
            sa.Column("path", sa.String(), nullable=True, server_default=""),
            sa.Column("changes_json", sa.Text(), nullable=True,
                      server_default="[]"),
        )

    # 화면은 늘 최신순으로 읽는다.
    if "ix_edit_logs_at" not in _indexes("edit_logs"):
        op.create_index("ix_edit_logs_at", "edit_logs", ["at"])
    # `이 줄이 그동안 어떻게 바뀌었나`.
    if "ix_edit_logs_row" not in _indexes("edit_logs"):
        op.create_index("ix_edit_logs_row", "edit_logs",
                        ["table_name", "row_id"])


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    indexes = _indexes("edit_logs")
    if "ix_edit_logs_row" in indexes:
        op.drop_index("ix_edit_logs_row", table_name="edit_logs")
    if "ix_edit_logs_at" in indexes:
        op.drop_index("ix_edit_logs_at", table_name="edit_logs")
    if "edit_logs" in _tables():
        op.drop_table("edit_logs")
