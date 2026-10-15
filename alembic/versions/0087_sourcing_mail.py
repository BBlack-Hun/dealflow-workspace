"""딜 소싱 — 이 달 `딜 받음` 표시 + 메일로 저절로 (POP3 머리글만)

- 표 `sourcing_receipts` — (사람, 달) 마다 '이 달 딜을 받았다' 한 줄
  (`models.SourcingReceipt`). 사람이 누르거나(manual) 메일 확인이 세운다(mail —
  날짜 · 잘린 제목 · Message-ID 를 함께).
- 표 `sourcing_mail_seen` — 이미 본 메일(Message-ID × 사람). 사람이 거둔
  표시를 같은 메일이 다시 세우지 않게.
- 표 `sourcing_mail_checks` — 편지함을 훑은 회마다 한 줄. 정해진 회차는
  `run_key` 유일 색인으로 하루 한 번.
- 표 `sourcing_mail_settings` — 팀 현황에서 넣는 편지함(비밀번호는 암호화).

## 이 판의 번호 — 다른 PR 과 겹치지 않게

`0086_send_guard` 바로 뒤다. 열려 있는 PR #268(`0087_activity_sequence_trace`)
· #273(`0088_ir_company_link`) · 2단계 자동화(#271~ `0089_automations` …)도
0086 을 부모로 삼거나 그 뒤를 잇는다 — **이 판이 먼저 들어가므로 그 PR 들은
`down_revision` 을 이 판(`0087_sourcing_mail`)으로 옮겨야 머리가 하나가 된다.**
판 이름(revision)은 그쪽과 다르다(`0087_sourcing_mail` ≠ `0087_activity_sequence_trace`).

#277(소싱 리마인드)의 `0092_sourcing_receipts` 는 같은 표를 같은 칸으로 만들려
했다. 그 판은 표 · 색인이 있는지 보고 만들므로, 이 판 뒤에 와도 표를 두 번
만들지 않는다(그 PR 은 제 모델 사본만 빼면 된다).

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다(0078 · 0085 와 같은 방식). 유일 색인은 표를 만드는 `if` **밖에서**
따로 본다. 이미 표가 있는 DB(위 #277 이 먼저 들어간 시험 서버 등)에는 메일 칸
셋만 더한다.

## 되돌리기

네 표가 사라진다 — 잃는 것은 `딜 받음` 표시 · 메일 확인 이력 · 넣어 둔 편지함
설정이다.

Revision ID: 0087_sourcing_mail
Revises: 0086_send_guard
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0087_sourcing_mail"
down_revision = "0086_send_guard"
branch_labels = None
depends_on = None

RECEIPT_MAIL_COLUMNS = ("mail_at", "mail_subject", "mail_message_id")


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


def _stamps() -> list:
    return [sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True)]


def upgrade() -> None:
    if "sourcing_receipts" not in _tables():
        op.create_table(
            "sourcing_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            *_stamps(),
            sa.Column("sourcing_contact_id", sa.Integer(),
                      sa.ForeignKey("sourcing_contacts.id"), nullable=False),
            sa.Column("month", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False,
                      server_default="manual"),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            *[sa.Column(name, sa.String(), nullable=True)
              for name in RECEIPT_MAIL_COLUMNS],
        )
    have = _columns("sourcing_receipts")
    for name in RECEIPT_MAIL_COLUMNS:
        if name not in have:
            op.add_column("sourcing_receipts",
                          sa.Column(name, sa.String(), nullable=True))
    if "uq_sourcing_receipts_month" not in _indexes("sourcing_receipts"):
        op.create_index("uq_sourcing_receipts_month", "sourcing_receipts",
                        ["sourcing_contact_id", "month"], unique=True)

    if "sourcing_mail_seen" not in _tables():
        op.create_table(
            "sourcing_mail_seen",
            sa.Column("id", sa.Integer(), primary_key=True),
            *_stamps(),
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
            *_stamps(),
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

    if "sourcing_mail_settings" not in _tables():
        op.create_table(
            "sourcing_mail_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            *_stamps(),
            sa.Column("host", sa.String(), nullable=True),
            sa.Column("port", sa.Integer(), nullable=False, server_default="995"),
            sa.Column("username", sa.String(), nullable=True),
            sa.Column("password_enc", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    if "sourcing_mail_settings" in _tables():
        op.drop_table("sourcing_mail_settings")
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
    if "uq_sourcing_receipts_month" in _indexes("sourcing_receipts"):
        op.drop_index("uq_sourcing_receipts_month", table_name="sourcing_receipts")
    if "sourcing_receipts" in _tables():
        op.drop_table("sourcing_receipts")
