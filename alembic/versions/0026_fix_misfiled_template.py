"""잘못된 종류로 저장된 문구를 옮긴다

`ask_preference`(선호 분야 묻기)는 **투자사에게** 어떤 기업을 보고 싶은지
되묻는 문구다. 그런데 거기에 **스타트업에게** 회사 정보를 적어 달라는
스크립트가 들어가 있었다.

개인 문구가 팀 기본보다 먼저 쓰이므로, 선호 분야를 물으려 하면 스타트업용
스크립트가 그대로 투자사에게 나갔다.

`startup_info`(기업 — 정보 기재 요청)라는 자리를 새로 만들어 옮긴다.
**지우지 않는다** — 실제로 쓰는 문구다.

Revision ID: 0026_fix_misfiled_template
Revises: 0025_ir_template_no_greeting
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_fix_misfiled_template"
down_revision = "0025_ir_template_no_greeting"
branch_labels = None
depends_on = None

# 옮길 문구를 알아보는 표식. 이름은 사람마다 다르게 붙이므로 본문에서
# 스타트업용 스크립트에만 나오는 낱말로 고른다.
MARK = "%기재회신%"


def upgrade() -> None:
    t = sa.table("message_templates",
                 sa.column("kind", sa.String), sa.column("body", sa.Text))
    op.execute(
        t.update()
        .where(sa.and_(t.c.kind == "ask_preference", t.c.body.like(MARK)))
        .values(kind="startup_info")
    )


def downgrade() -> None:
    t = sa.table("message_templates",
                 sa.column("kind", sa.String), sa.column("body", sa.Text))
    op.execute(
        t.update()
        .where(sa.and_(t.c.kind == "startup_info", t.c.body.like(MARK)))
        .values(kind="ask_preference")
    )
