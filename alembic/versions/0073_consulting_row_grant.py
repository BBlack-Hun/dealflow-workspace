"""이 사람의 줄을 고쳐도 되는 팀원(`consulting_row_grants`)

## 왜 칸이 아니라 표인가

옆의 `users.can_view_consulting` 은 화면 하나를 열고 닫는 참거짓이라 칸으로
충분했다. 이번 것은 주는 단위가 **누구의 줄인가**이고 한 사람의 줄에 팀원
여럿을 붙일 수 있어야 한다 — 계정 칸에 담으려면 번호를 글자로 이어 붙이는
수밖에 없는데(`"3,7"`), 그러면 계정이 지워질 때 남는 번호를 아무도 못 치우고
조회로 거를 수도 없다. 자세한 것은 `models.ConsultingRowGrant` 에 적었다.

## 값을 하나도 안 넣는다

지금 누구에게 줄지는 **자료로 정하는 일**이지 마이그레이션이 단정할 일이
아니다. 아무에게도 안 준 상태에서 시작하면 지금까지와 똑같이 움직이고
(관리자 전부 · 나머지 자기 줄만), 관리자가 팀 현황에서 하나씩 준다.
0047·0048·0049·0065 가 같은 이유로 backfill 을 안 했다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 표를
이미 갖고 시작한다. 여기서 또 만들면 `table already exists` 로 부팅이 죽는다
(`tests/test_migrations.py` 가 지키는 그것이다). 색인도 표를 만드는 `if`
**밖에서** 따로 본다 — 안에 넣으면 빈 DB 길에서 통째로 건너뛴다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0073_consulting_row_grant"
down_revision = "0072_edit_log"
branch_labels = None
depends_on = None

TABLE = "consulting_row_grants"


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    if TABLE not in _tables():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            # 줄의 주인. `consulting_companies.user_id` 와 같은 것을 가리킨다.
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
            # 그 줄을 고쳐도 되는 팀원.
            sa.Column("editor_user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            # 같은 짝이 두 줄이면, 뺄 때 하나만 지워져 **화면에는 빠졌는데
            # 서버는 아직 허락하는** 상태가 된다.
            sa.UniqueConstraint("user_id", "editor_user_id",
                                name="uq_consulting_grant"),
        )

    # 판정이 묻는 것은 늘 `이 사람이 누구의 줄을 고칠 수 있나` 하나다
    # (`routers/consulting.py` 의 `grant_owner_ids`).
    if "ix_consulting_grants_editor" not in _indexes(TABLE):
        op.create_index("ix_consulting_grants_editor", TABLE, ["editor_user_id"])


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    if "ix_consulting_grants_editor" in _indexes(TABLE):
        op.drop_index("ix_consulting_grants_editor", table_name=TABLE)
    if TABLE in _tables():
        op.drop_table(TABLE)
