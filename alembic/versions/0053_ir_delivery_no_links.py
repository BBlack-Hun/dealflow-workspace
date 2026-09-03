"""IR 자료 전달 문구에서 `{자료링크}` 를 뺀다 — 구글 드라이브 링크 방식 폐기

## 무엇을 그만두나

자료 전달은 지금까지 **구글 드라이브 링크를 문구에 실어** 보냈다. 기업 하나당
한 통씩 링크를 먼저 던지고, 설명을 마지막에 붙였다.

    1번 (주)샘플애그
    https://drive.google.com/file/d/…        ← 이 통들이 없어진다

    홍길동 팀장님 안녕하세요.
    1번 기업 (주)샘플애그 IR deck 먼저 전달드리겠습니다.

이 방식을 그만두기로 했다. 자료는 이제 사람이 **PC 카톡에서 파일로 직접
첨부**한다 — 링크를 받은 쪽이 드라이브 권한에 막히거나, 링크만 보고 넘기는
일이 있었다.

## 왜 칸이 아니라 문구만 고치나

`ir_companies.ir_drive_url` 은 **그대로 둔다.** 344곳에 값이 들어 있고, 첨부할
파일을 내려받으려면 화면에서 그 링크를 열어야 한다. 폐기한 것은 *보내는 방식*
이지 *자료가 어디 있는지* 가 아니다.

## 손으로 고쳐 둔 문구는 건드리지 않는다

0025 와 같은 규칙이다 — 기본값 그대로인 줄만 고친다. 사람이 고쳐 둔 문구에
`{자료링크}` 가 남아 있어도 **빈칸으로 지워져** 나간다(`render_template` 이
치환 목록에 그대로 들고 있는 이유가 이것이다). 토큰이 글자 그대로 투자사
카톡방에 나가는 일은 없다.

Revision ID: 0053_ir_delivery_no_links
Revises: 0052_one_liner_bulk_undo
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0053_ir_delivery_no_links"
down_revision = "0052_one_liner_bulk_undo"
branch_labels = None
depends_on = None

WITH_LINKS = "{기업목록} IR deck 먼저 전달드리겠습니다.\n\n{자료링크}"
NO_LINKS = "{기업목록} IR deck 먼저 전달드리겠습니다."


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
    _swap(WITH_LINKS, NO_LINKS)


def downgrade() -> None:
    _swap(NO_LINKS, WITH_LINKS)
