"""IR 자료 전달 문구에서 인사말을 뺀다

인사말은 이제 **모든 방식에서 기본으로 붙는다**(선호 분야 묻기만 예외).
그런데 이 문구가 자체적으로 `{담당자명} {직함} 안녕하세요.` 로 시작해서
인사가 두 번 나갔다.

    안녕하세요, 홍길동 팀장님
    컨텍브이씨 ASSET입니다.

    홍길동 팀장님 안녕하세요.       ← 두 번째
    1번 기업 … IR deck 전달드리겠습니다.

인사는 인사말이 맡고, 이 문구는 **본문만** 담는다.
손으로 고쳐 둔 문구는 건드리지 않는다 — 기본값 그대로인 것만 고친다.

Revision ID: 0025_ir_template_no_greeting
Revises: 0024_contact_office_fields
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_ir_template_no_greeting"
down_revision = "0024_contact_office_fields"
branch_labels = None
depends_on = None

OLD = ("{담당자명} {직함} 안녕하세요.\n"
       "{기업목록} IR deck 먼저 전달드리겠습니다.\n\n{자료링크}")
NEW = "{기업목록} IR deck 먼저 전달드리겠습니다.\n\n{자료링크}"


def _swap(before: str, after: str) -> None:
    templates = sa.table("message_templates",
                         sa.column("kind", sa.String),
                         sa.column("body", sa.Text))
    op.execute(
        templates.update()
        .where(sa.and_(templates.c.kind == "ir_delivery",
                       templates.c.body == before))
        .values(body=after)
    )


def upgrade() -> None:
    _swap(OLD, NEW)


def downgrade() -> None:
    _swap(NEW, OLD)
