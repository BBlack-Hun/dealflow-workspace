"""확정한 공유 심사역 — `series_a_companies.shared_by_contact_id`

IR 기업 현황 › `Series A 이상 기업` 탭의 `공유 심사역`(사람이 시트에 적은 자유
글자)을 딜 소싱 명단의 **그 분 줄**로 확정해 두는 칸이다. Series A 딜 공유는
"이 딜을 넘겨 준 분께는 이 딜을 빼고 보낸다" 를 이름 · 회사 짐작으로 정하는데
(`services/series_a_share.is_own`), 짐작이 틀리는 줄은 탭의 칸에서 사람이 [이 분으로
확정]을 누른다. 값이 있으면 짐작하지 않고 이 번호만 본다. 처음에는 전부 비어 있다
(채워 넣지 않는다 — 지금까지와 똑같이 짐작한다).

## 이 판의 번호

`0095_series_a_shares` 바로 뒤다. 열려 있는 PR 들이 0096 ~ 0100
(`0096_activity_sequence_trace` · `0097_ir_company_link` · `0098_automations` ·
`0099_automation_sends` · `0100_sender_rooms`)을 쓰고 있어 겹치지 않게 0101 을 쓴다.
그 PR 들이 먼저 들어오면 이 판의 `down_revision` 을 그 머리로 옮겨 머리가 하나가
되게 맞춘다(이 판이 먼저 들어가면 그쪽 0096 의 `down_revision` 을 이 판으로).

## 빈 DB 에서는 만들지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다 — 있는지 보고 더한다
(0093 과 같은 방식). 외래키는 운영 SQLite 에 붙이지 않는다(ALTER 로는 못 붙인다 —
`sourcing_contacts.vc_contact_id` 와 같은 사정). 소싱 줄을 지울 때 이 칸을 비우는
것은 앱이 한다(`models._forget_series_a_sharers`).

## 되돌리기

칸째 지운다 — 잃는 것은 확정해 둔 공유 심사역뿐이다(다시 이름 · 회사로 짐작한다).

Revision ID: 0101_series_a_shared_by
Revises: 0095_series_a_shares
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0101_series_a_shared_by"
down_revision = "0095_series_a_shares"
branch_labels = None
depends_on = None

TABLE = "series_a_companies"
COLUMN = "shared_by_contact_id"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
