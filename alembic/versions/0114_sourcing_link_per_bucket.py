"""딜 소싱 ↔ 투자사 관리 현황 — 한 투자사 줄에 **갈래마다** 한 소싱 줄

투자사 관리 현황의 `딜 소싱` 칸이 갈래 셋(Series A · M&A · 구주·후속)을 고른다
(`services/sourcing_sync.BRANCHES` — 사용자 결정 2026-10-21). 같은 분이 Series A 와
M&A 에 다 있으면 두 소싱 줄이 같은 투자사 줄을 가리킨다. 그래서 유일 색인을
`(vc_contact_id)` 에서 `(vc_contact_id, bucket)` 으로 바꾼다.

**데이터는 건드리지 않는다.** 색인만 바꾼다 — 넓히는 쪽이라 지금 있는 줄은 모두
새 색인을 지킨다. M&A · 구주·후속 줄을 잇는 일은 이주가 하지 않고 딜 소싱 화면의
[저절로 잇기] · [이 분으로 확정]이 한다(사용자 결정 — 몰래 잇지 않는다).

SQLite 의 색인은 표와 따로 선 것이라(`0093` 이 `create_index` 로 세웠다) 표를 다시
짓는 batch 작업 없이 색인만 지우고 새로 세운다.

## 있는지 보고 한다

`0001_initial` 이 `create_all()` 로 **지금 모델**(새 색인)을 만든다. 그 뒤 `0093` 은
옛 이름의 색인이 없으니 옛 색인을 또 세운다 — 새로 깐 DB 에는 둘 다 있다. 그래서
옛 색인은 있으면 지우고, 새 색인은 없을 때만 세운다.

## 내리기 — 겹친 줄이 있으면 **거절한다**

옛 색인(투자사 줄 하나에 소싱 줄 하나)을 다시 세우려면 같은 투자사 줄을 가리키는
소싱 줄이 둘 이상인 곳이 없어야 한다. 있으면 색인을 세우다 터지거나, 이주가 줄을
골라 잇기를 지워야 한다 — 어느 갈래의 잇기를 버릴지는 사람이 정할 일이라 이주가
고르지 않는다. 그래서 **아무것도 바꾸지 않고 멈춘다**(그 투자사 줄 번호를 적는다).
딜 소싱 화면에서 남길 갈래만 두고 [연결 풀기]로 푼 뒤 다시 내린다.

Revision ID: 0114_sourcing_link_per_bucket
Revises: 0113_send_via_agent
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0114_sourcing_link_per_bucket"
down_revision = "0113_send_via_agent"
branch_labels = None
depends_on = None

TABLE = "sourcing_contacts"
OLD = "uq_sourcing_contacts_vc_contact"
NEW = "uq_sourcing_contacts_vc_contact_bucket"


def _indexes() -> set:
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(TABLE)}


def upgrade() -> None:
    have = _indexes()
    if OLD in have:
        op.drop_index(OLD, table_name=TABLE)
    if NEW not in have:
        op.create_index(NEW, TABLE, ["vc_contact_id", "bucket"], unique=True)


def downgrade() -> None:
    twins = op.get_bind().execute(sa.text(
        f"SELECT vc_contact_id FROM {TABLE} WHERE vc_contact_id IS NOT NULL "
        "GROUP BY vc_contact_id HAVING COUNT(*) > 1 ORDER BY vc_contact_id")).scalars().all()
    if twins:
        raise RuntimeError(
            "0114 를 내릴 수 없습니다 — 투자사 줄 하나에 딜 소싱 줄이 둘 이상 이어져 있습니다"
            f"(투자사 줄 번호 {', '.join(map(str, twins))}). 딜 소싱 화면에서 남길 갈래만 "
            "두고 [연결 풀기]로 푼 뒤 다시 내리세요. 아무것도 바꾸지 않았습니다.")
    have = _indexes()
    if NEW in have:
        op.drop_index(NEW, table_name=TABLE)
    if OLD not in have:
        op.create_index(OLD, TABLE, ["vc_contact_id"], unique=True)
