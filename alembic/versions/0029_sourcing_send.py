"""딜 소싱 제안을 실제로 보낼 수 있게 한다

소싱 명단은 투자사 관리 현황과 겹치지 않는다(39명 중 7명만 겹친다). 그래서
"기존 담당자를 찾아 붙인다"로는 32명에게 못 보낸다 — 소싱 명단도 자기
카톡방을 가져야 한다.

발송 건(`send_items`)은 지금까지 투자사 담당자만 가리켰다. 소싱 대상은 다른
표에 있으므로 가리키는 칸을 하나 더 두고, 둘 중 **하나만** 채운다.
`contact_id` 가 비게 되는 것은 이 때문이다.

Revision ID: 0029_sourcing_send
Revises: 0028_consulting_sheets
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_sourcing_send"
down_revision = "0028_consulting_sheets"
branch_labels = None
depends_on = None


SOURCING_COLUMNS = (
    ("kakao_room_name", lambda: sa.Column("kakao_room_name", sa.String(),
                                          nullable=True)),
    ("room_verified", lambda: sa.Column("room_verified", sa.String(),
                                        nullable=False,
                                        server_default="unverified")),
)


def _columns(table: str) -> dict:
    return {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있는 칸은 건너뛴다 — 빈 DB 는 0001 이 만들어 준 채로 온다(0018 참고).
    # `batch_alter_table` 은 표를 통째로 다시 만드는 일이라, **할 일이 없으면
    # 아예 열지 않는다** — 공연히 다시 만들다 인덱스를 잃을 자리를 만들지 않는다.
    have = _columns("sourcing_contacts")
    missing = [make() for name, make in SOURCING_COLUMNS if name not in have]
    if missing:
        with op.batch_alter_table("sourcing_contacts") as b:
            for column in missing:
                b.add_column(column)

    have = _columns("send_items")
    # 소싱 대상을 가리키는 칸. 기존 건은 전부 투자사 담당자라 NULL 로 남는다.
    add_ref = "sourcing_contact_id" not in have
    # 소싱 건은 투자사 담당자가 없다. 여기를 열어 주지 않으면 소싱 발송이
    # 아예 저장되지 않는다. 이미 열려 있으면(새 DB) 손대지 않는다.
    open_null = have.get("contact_id", {}).get("nullable") is False
    if add_ref or open_null:
        with op.batch_alter_table("send_items") as b:
            if add_ref:
                b.add_column(sa.Column("sourcing_contact_id", sa.Integer(),
                                       nullable=True))
            if open_null:
                b.alter_column("contact_id", existing_type=sa.Integer(),
                               nullable=True)


def downgrade() -> None:
    # 되돌리기 전에 소싱 건을 지운다 — 남겨 두면 contact_id 가 NULL 인 채로
    # NOT NULL 을 다시 걸게 되어 되돌리기 자체가 실패한다.
    op.execute("DELETE FROM send_items WHERE contact_id IS NULL")
    have = _columns("send_items")
    drop_ref = "sourcing_contact_id" in have
    close_null = have.get("contact_id", {}).get("nullable") is True
    if drop_ref or close_null:
        with op.batch_alter_table("send_items") as b:
            if close_null:
                b.alter_column("contact_id", existing_type=sa.Integer(),
                               nullable=False)
            if drop_ref:
                b.drop_column("sourcing_contact_id")

    have = _columns("sourcing_contacts")
    present = [name for name, _make in reversed(SOURCING_COLUMNS) if name in have]
    if present:
        with op.batch_alter_table("sourcing_contacts") as b:
            for name in present:
                b.drop_column(name)
