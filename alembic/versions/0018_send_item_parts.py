"""발송 한 건을 여러 통으로 나눠 보낸다

IR 자료 전달은 링크를 먼저 한 통씩 던지고 마지막에 설명을 붙여야 한다.
카톡에서 링크는 각자 미리보기 카드로 떠야 하고, 설명이 그 아래 와야 읽힌다.

`send_items` 는 여전히 **사람당 한 줄**이다 — 진행 화면이 세는 것은
'몇 통 보냈나' 가 아니라 '몇 명에게 보냈나' 이기 때문이다.

Revision ID: 0018_send_item_parts
Revises: 0017_ir_delivery_links
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_send_item_parts"
down_revision = "0017_ir_delivery_links"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # **빈 DB 는 이 칸을 이미 가진 채로 여기 도착한다.** 0001 이
    # `Base.metadata.create_all()` 로 *지금 모델 전체*를 만들기 때문이다(모델과
    # 마이그레이션이 갈라지지 않게 하려고 일부러 그렇게 두었다 — 0001 의 설명
    # 참고). 그래서 새 DB 와 운영 DB 는 여기 올 때 모양이 다르고, **두 경로
    # 모두 head 까지 올라가야 한다.** 있으면 건너뛴다.
    #
    # 0002 가 정한 방식인데 0017 부터 잊혔고, 그 결과 빈 볼륨으로 컨테이너를
    # 처음 띄우면 바로 이 줄에서 `duplicate column name: parts_json` 으로
    # 부팅이 죽었다.
    if not _has_column("send_items", "parts_json"):
        op.add_column("send_items", sa.Column("parts_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("send_items", "parts_json"):
        op.drop_column("send_items", "parts_json")
