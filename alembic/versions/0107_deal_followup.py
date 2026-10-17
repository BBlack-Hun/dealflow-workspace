"""리마인드 뒤 `답 없음 · 전화 필요` 표시와 메모 — 표 하나

`deal_followups` — 투자사 담당자 한 명에 한 줄. 리마인드 카톡을 보낸 뒤 답이
없으면 팀원·담당자가 `답 없음 · 전화 필요` 를 켜고 메모를 남긴다(10/17 회의
#37 · `models.DealFollowup`). 켜고 끈 사람·때, 메모를 적은 사람·때를 줄에 바로
적는다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만든다. 있는지 보고
만든다. 유일 색인은 표를 만드는 `if` **밖에서** 따로 본다(0100 과 같다).

## 판 번호

다른 브랜치가 `0106` 을 만들고 있다. 이 판은 지금의 머리(`0105`)에 붙여 두고,
두 브랜치를 합칠 때 `down_revision` 을 `0106` 쪽으로 바꾼다(PR 본문에 적었다).

## 되돌리기

표가 사라진다. 표시와 메모도 함께 사라지고, 오늘 할 일의 `전화 필요` 줄이
없어진다 — 다른 표는 이 표를 가리키지 않는다.

Revision ID: 0107_deal_followup
Revises: 0105_retire_old_auto_engines
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0107_deal_followup"
down_revision = "0105_retire_old_auto_engines"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    if "deal_followups" not in _tables():
        op.create_table(
            "deal_followups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("contact_id", sa.Integer(),
                      sa.ForeignKey("vc_contacts.id"), nullable=False),
            sa.Column("call_needed", sa.Integer(), nullable=False,
                      server_default="0"),
            sa.Column("call_by", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.Column("call_at", sa.String(), nullable=True),
            sa.Column("memo", sa.Text(), nullable=True),
            sa.Column("memo_by", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=True),
            sa.Column("memo_at", sa.String(), nullable=True),
        )
    if "uq_deal_followups_contact" not in _indexes("deal_followups"):
        op.create_index("uq_deal_followups_contact", "deal_followups",
                        ["contact_id"], unique=True)


def downgrade() -> None:
    if "uq_deal_followups_contact" in _indexes("deal_followups"):
        op.drop_index("uq_deal_followups_contact", table_name="deal_followups")
    if "deal_followups" in _tables():
        op.drop_table("deal_followups")
