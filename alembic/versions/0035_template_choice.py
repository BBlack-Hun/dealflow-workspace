"""사용자가 고른 팀 기본 문구

팀 기본 문구는 한 종류에 여러 개 둘 수 있는데(딜 소싱 제안은 갈래마다 하나씩
다섯 개다), 그중 무엇을 쓸지는 아무도 고르지 않았다. 코드가 `.first()` 로
집었고, 정렬 없는 조회의 순서는 DB 가 정하는 것이라 **같은 회차에서 사람마다
다른 문구가 나갈 수 있었다.**

고르는 일을 사람에게 돌려준다. 사용자는 문구 화면에서 한 번 고르고, 그 선택이
여기 남는다. 고치는 권한은 그대로 관리자에게 있다 — 고르는 것과 고치는 것은
다른 일이다.

Revision ID: 0035_template_choice
Revises: 0034_meeting_notes
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_template_choice"
down_revision = "0034_meeting_notes"
branch_labels = None
depends_on = None

TABLE = "template_choices"


def upgrade() -> None:
    # **이미 있으면 건너뛴다.** 마이그레이션이 도중에 끊기면(컨테이너가 다시
    # 뜨는 등) 표만 만들어진 채로 남는데, 그대로 다시 돌리면 `table already
    # exists` 로 영영 못 지나간다 — 이 저장소에서 실제로 그렇게 멎었다.
    insp = sa.inspect(op.get_bind())
    if TABLE in insp.get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        # 같은 종류 안에서 서로 겨루는 무리를 가르는 칸. 보통은 빈 문자열이고,
        # 딜 소싱만 갈래 이름이 들어간다. NULL 을 쓰면 NULL 끼리 서로 다른
        # 값으로 쳐서 아래 유일 제약이 걸리지 않는다.
        sa.Column("variant", sa.String(), nullable=False, server_default=""),
        # 고른 문구가 지워지면 선택도 함께 사라져야 한다 — 없는 문구를 가리킨
        # 채 남으면 "골라 뒀는데 다른 것이 나간다".
        sa.Column("template_id", sa.Integer(),
                  sa.ForeignKey("message_templates.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
        # 한 자리에 두 개를 고를 수는 없다.
        sa.UniqueConstraint("user_id", "kind", "variant", name="uq_template_choice_slot"),
    )
    op.create_index("ix_template_choices_user_id", TABLE, ["user_id"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if TABLE not in insp.get_table_names():
        return
    op.drop_index("ix_template_choices_user_id", table_name=TABLE)
    op.drop_table(TABLE)
