"""딜 소싱 — 메일로 온 딜을 저절로 `딜 받음` (POP3 머리글만)

- 칸 `sourcing_receipts.mail_at` · `mail_subject` · `mail_message_id` — 메일로
  선 표시가 어느 메일로 섰는지(날짜 · 잘린 제목 · Message-ID). 본문은 없다.
- 표 `sourcing_mail_seen` — 이미 본 메일(Message-ID × 사람). 사람이 거둔
  표시를 같은 메일이 다시 세우지 않게(`models.SourcingMailSeen`).
- 표 `sourcing_mail_checks` — 편지함을 훑은 회마다 한 줄. 정해진 회차는
  `run_key` 유일 색인으로 하루 한 번(`models.SourcingMailCheck`).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다(0092 와 같은 방식). 유일 색인은 표를 만드는 `if` **밖에서** 따로 본다.

## 되돌리기

두 표와 세 칸이 사라진다 — 잃는 것은 메일 확인 이력과 '어느 메일로 섰나'
뿐이다. `딜 받음` 표시 자체(`sourcing_receipts` 의 줄)는 남는다.

Revision ID: 0093_sourcing_mail
Revises: 0092_sourcing_receipts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0093_sourcing_mail"
down_revision = "0092_sourcing_receipts"
branch_labels = None
depends_on = None

RECEIPT_COLUMNS = ("mail_at", "mail_subject", "mail_message_id")


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    have = _columns("sourcing_receipts")
    for name in RECEIPT_COLUMNS:
        if have and name not in have:
            op.add_column("sourcing_receipts",
                          sa.Column(name, sa.String(), nullable=True))

    if "sourcing_mail_seen" not in _tables():
        op.create_table(
            "sourcing_mail_seen",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("message_id", sa.String(), nullable=False),
            sa.Column("sourcing_contact_id", sa.Integer(),
                      sa.ForeignKey("sourcing_contacts.id"), nullable=False),
            sa.Column("month", sa.String(), nullable=False),
            sa.Column("mail_at", sa.String(), nullable=True),
        )
    if "uq_sourcing_mail_seen_message" not in _indexes("sourcing_mail_seen"):
        op.create_index("uq_sourcing_mail_seen_message", "sourcing_mail_seen",
                        ["message_id", "sourcing_contact_id"], unique=True)

    if "sourcing_mail_checks" not in _tables():
        op.create_table(
            "sourcing_mail_checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("run_key", sa.String(), nullable=True),
            sa.Column("slot", sa.String(), nullable=False),
            sa.Column("day", sa.String(), nullable=False),
            sa.Column("month", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False,
                      server_default="running"),
            sa.Column("started_at", sa.String(), nullable=True),
            sa.Column("finished_at", sa.String(), nullable=True),
            sa.Column("scanned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("matched", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("marked", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
        )
    if "uq_sourcing_mail_checks_run_key" not in _indexes("sourcing_mail_checks"):
        op.create_index("uq_sourcing_mail_checks_run_key", "sourcing_mail_checks",
                        ["run_key"], unique=True)


def downgrade() -> None:
    if "uq_sourcing_mail_checks_run_key" in _indexes("sourcing_mail_checks"):
        op.drop_index("uq_sourcing_mail_checks_run_key",
                      table_name="sourcing_mail_checks")
    if "sourcing_mail_checks" in _tables():
        op.drop_table("sourcing_mail_checks")
    if "uq_sourcing_mail_seen_message" in _indexes("sourcing_mail_seen"):
        op.drop_index("uq_sourcing_mail_seen_message",
                      table_name="sourcing_mail_seen")
    if "sourcing_mail_seen" in _tables():
        op.drop_table("sourcing_mail_seen")
    have = _columns("sourcing_receipts")
    gone = [name for name in RECEIPT_COLUMNS if name in have]
    if gone:
        with op.batch_alter_table("sourcing_receipts") as batch:
            for name in gone:
                batch.drop_column(name)
