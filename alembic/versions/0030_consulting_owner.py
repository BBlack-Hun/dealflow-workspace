"""투자컨설턴트 현황을 사람별로 나눈다

지금까지는 이 화면을 볼 수 있는 사람이면 **같은 표 하나**를 보았다. 컨설턴트가
여럿이면 남의 담당 기업까지 보이고, 무엇보다 각자 올린 시트가 서로를 덮는다
(월별 리마인드 열이 사람마다 다르다).

담당자를 붙이고, 관리자만 전부 본다.

기존 줄은 지금 이 화면을 쓰는 계정에게 붙인다. NULL 로 두면 아무에게도 안
보여서, 올려 둔 50개사가 사라진 것처럼 된다.

Revision ID: 0030_consulting_owner
Revises: 0029_sourcing_send
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_consulting_owner"
down_revision = "0029_sourcing_send"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("consulting_companies", "consulting_columns"):
        with op.batch_alter_table(table) as b:
            b.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    # 이미 있는 줄의 주인을 정한다. 이 화면을 쓰는 계정이 하나뿐이면 그 사람,
    # 여럿이거나 없으면 손대지 않는다(관리자가 화면에서 배정한다).
    conn = op.get_bind()
    owners = [r[0] for r in conn.execute(sa.text(
        "SELECT id FROM users WHERE can_view_consulting = 1 AND role != 'admin'"
    ))]
    if len(owners) == 1:
        for table in ("consulting_companies", "consulting_columns"):
            conn.execute(sa.text(f"UPDATE {table} SET user_id = :uid"),
                         {"uid": owners[0]})


def downgrade() -> None:
    for table in ("consulting_companies", "consulting_columns"):
        with op.batch_alter_table(table) as b:
            b.drop_column("user_id")
