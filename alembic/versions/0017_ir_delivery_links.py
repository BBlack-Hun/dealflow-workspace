"""IR 자료 전달 문구에 링크 자리를 넣는다

이미 쓰고 있는 문구에는 `{자료링크}` 가 없어서 "IR deck 먼저 전달드리겠습니다"
까지만 나가고 **정작 자료는 안 갔다**. 받은 쪽은 다시 물어봐야 한다.

이미 손으로 고쳐 둔 문구는 건드리지 않는다 — 기본값 그대로인 것만 고친다.
(작성자가 일부러 링크를 뺐을 수도 있으므로, 그때는 발송 단계에서 자동으로
붙는다: `message_composer.compose_message` 참고)

Revision ID: 0017_ir_delivery_links
Revises: 0016_weekly_tasks
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_ir_delivery_links"
down_revision = "0016_weekly_tasks"
branch_labels = None
depends_on = None

OLD = "{담당자명} {직함} 안녕하세요.\n{기업목록} IR deck 먼저 전달드리겠습니다."
NEW = OLD + "\n\n{자료링크}"


def upgrade() -> None:
    templates = sa.table("message_templates",
                         sa.column("id", sa.Integer),
                         sa.column("kind", sa.String),
                         sa.column("body", sa.Text))
    op.execute(
        templates.update()
        .where(sa.and_(templates.c.kind == "ir_delivery",
                       templates.c.body == OLD))
        .values(body=NEW)
    )


def downgrade() -> None:
    templates = sa.table("message_templates",
                         sa.column("kind", sa.String),
                         sa.column("body", sa.Text))
    op.execute(
        templates.update()
        .where(sa.and_(templates.c.kind == "ir_delivery",
                       templates.c.body == NEW))
        .values(body=OLD)
    )
