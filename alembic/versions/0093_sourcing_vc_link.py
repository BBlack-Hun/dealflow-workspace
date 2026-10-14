"""딜 소싱 ↔ 투자사 관리 현황 잇기 — `sourcing_contacts` 에 두 칸 + 처음 한 번 잇기

- `vc_contact_id` — 이 소싱 줄이 투자사 관리 현황의 어느 줄과 같은 사람인가.
  투자사 관리 현황의 `Series A 딜 소싱` 칸(O/X/빈칸)이 이것을 보고 선다
  (`services/sourcing_sync.py`). 한 투자사 줄에 많아야 한 줄(유일 색인).
- `participation` — `참여`(기본) | `불참여`. 불참여인 분은 딜 소싱 제안에서 빠진다.

## 처음 한 번 잇기 — 확실한 것만

`시리즈 A 이상 딜 소싱 참여 심사역` 갈래 줄만 본다. **휴대폰 숫자가 같고, 그
번호가 양쪽에 딱 한 줄씩**일 때만 잇는다 — 투자사 쪽은 투자사로 세는 명단의
감추지 않은 줄만(`sheet_owner.investors`), 번호는 10자리 이상
(`sourcing_link.MIN_DIGITS`). 앱이 딜 소싱에서 사람을 넣을 때 저절로 잇는 규칙
(`sourcing_sync.auto_link`)과 **같은 규칙**이다. 나머지(번호 없음 · 겹침 · 맞는
줄 없음)는 잇지 않는다 — 사람이 투자사 관리 현황에서 O 를 넣으면 그때 이어진다.

운영 DB 에서 미리 세어 본 수(2026-10-14, 읽기 전용): 그 갈래 21줄 중 **18줄을
잇고**, 3줄은 그대로 둔다(번호 없음 2 · 같은 분이 두 팀원 명단에 한 줄씩 있어
어느 쪽인지 모름 1).

**적힌 값은 덮지 않는다.** 앱이 이을 때(`sourcing_sync.link`)와 같이 소싱 줄의
**빈 칸만** 투자사 줄 값으로 채운다(운영: 메일 1칸). 이은 18줄 중 14줄은 직함 ·
회사 · 메일 표기가 서로 다른데(직함 7 · 회사 9 · 메일 2), 둘 다 사람이 적은 값이라
어느 쪽이 맞는지 이주가 모른다 — 딜 소싱 화면이 그 줄에 `다른 칸` 을 표시하고,
어느 쪽에서든 한 번 고치면 그때부터 두 줄이 같이 움직인다.

## 이 판의 번호 — 다른 PR 과 겹치지 않게

`0087_sourcing_mail` 바로 뒤다. 열려 있는 PR 의 판 이름(0087_activity_sequence_trace
· 0088_ir_company_link · 0089_automations · 0090_automation_sends ·
0091_sender_rooms · 0092_sourcing_receipts)과 겹치지 않게 0093 을 쓴다. 그 PR 들이
뒤에 들어오면 `down_revision` 을 이 판으로 옮겨야 머리가 하나가 된다.

## 빈 DB 에서는 칸을 만들지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다 — 있는지 보고
더한다(0087 과 같은 방식). 외래키는 운영 SQLite 에 붙이지 않는다(ALTER 로는
못 붙인다 — `send_items.sourcing_contact_id` 와 같은 사정). 투자사 줄을 지울 때
이 칸을 먼저 비우는 것은 앱이 한다(`sourcing_sync.detach`).

## 되돌리기

두 칸과 색인이 사라진다 — 잃는 것은 잇기와 `불참여` 표시다.

Revision ID: 0093_sourcing_vc_link
Revises: 0087_sourcing_mail
"""
from __future__ import annotations

import re
from collections import Counter

import sqlalchemy as sa
from alembic import op

revision = "0093_sourcing_vc_link"
down_revision = "0087_sourcing_mail"
branch_labels = None
depends_on = None

#: 이 판을 만든 때의 글자 그대로 — 앱의 `sourcing_sync.SYNC_BUCKET`.
SYNC_BUCKET = "시리즈 A 이상 딜 소싱 참여 심사역"
#: `sourcing_link.MIN_DIGITS`.
MIN_DIGITS = 10
#: `sheet_owner.MANUAL_SHEET` — 명단 칸이 빈 줄이 속하는 명단.
MANUAL_SHEET = "직접 추가"
INDEX = "uq_sourcing_contacts_vc_contact"
#: `sourcing_sync.SHARED_FIELDS` — 두 표에 다 있는 칸.
SHARED_FIELDS = ("name", "title", "firm", "phone", "email")


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


def _digits(value) -> str:
    return re.sub(r"\D", "", value or "")


def _labels(value) -> list:
    labels = [x.strip() for x in (value or "").split(",") if x.strip()]
    return labels or [MANUAL_SHEET]


def pairs(bind) -> dict:
    """{소싱 줄 번호: 투자사 줄 번호} — 확실한 것만(머리말). 검사도 이것을 부른다."""
    hidden = {label for label, flag in bind.execute(sa.text(
        "SELECT label, is_hidden FROM sheet_owners")) if flag}
    investors = {}
    for cid, phone, sheets, row_hidden in bind.execute(sa.text(
            "SELECT id, phone, source_sheet, is_hidden FROM vc_contacts")):
        key = _digits(phone)
        if len(key) < MIN_DIGITS or row_hidden:
            continue
        if not any(label not in hidden for label in _labels(sheets)):
            continue
        investors.setdefault(key, []).append(cid)

    rows = bind.execute(sa.text(
        "SELECT id, phone FROM sourcing_contacts "
        "WHERE bucket = :bucket AND vc_contact_id IS NULL"),
        {"bucket": SYNC_BUCKET}).all()
    taken = {cid for (cid,) in bind.execute(sa.text(
        "SELECT vc_contact_id FROM sourcing_contacts "
        "WHERE vc_contact_id IS NOT NULL"))}
    seen = Counter(_digits(phone) for _id, phone in rows)
    out = {}
    for sid, phone in rows:
        key = _digits(phone)
        if len(key) < MIN_DIGITS or seen[key] != 1:
            continue
        match = investors.get(key, [])
        if len(match) == 1 and match[0] not in taken:
            out[sid] = match[0]
    return out


def upgrade() -> None:
    have = _columns("sourcing_contacts")
    if "vc_contact_id" not in have:
        op.add_column("sourcing_contacts",
                      sa.Column("vc_contact_id", sa.Integer(), nullable=True))
    if "participation" not in have:
        op.add_column("sourcing_contacts",
                      sa.Column("participation", sa.String(), nullable=False,
                                server_default="참여"))
    if INDEX not in _indexes("sourcing_contacts"):
        op.create_index(INDEX, "sourcing_contacts", ["vc_contact_id"], unique=True)

    bind = op.get_bind()
    for sid, cid in pairs(bind).items():
        bind.execute(sa.text(
            "UPDATE sourcing_contacts SET vc_contact_id = :cid WHERE id = :sid"),
            {"cid": cid, "sid": sid})
        # 소싱 줄의 **빈 칸만** 채운다(`sourcing_sync.link` 와 같다).
        for field in SHARED_FIELDS:
            bind.execute(sa.text(
                f"UPDATE sourcing_contacts SET {field} = "
                f"(SELECT TRIM(v.{field}) FROM vc_contacts v WHERE v.id = :cid) "
                f"WHERE id = :sid AND TRIM(COALESCE({field}, '')) = '' "
                f"AND (SELECT TRIM(COALESCE(v.{field}, '')) FROM vc_contacts v "
                f"WHERE v.id = :cid) != ''"),
                {"cid": cid, "sid": sid})


def downgrade() -> None:
    if INDEX in _indexes("sourcing_contacts"):
        op.drop_index(INDEX, table_name="sourcing_contacts")
    have = _columns("sourcing_contacts")
    with op.batch_alter_table("sourcing_contacts") as batch:
        if "participation" in have:
            batch.drop_column("participation")
        if "vc_contact_id" in have:
            batch.drop_column("vc_contact_id")
