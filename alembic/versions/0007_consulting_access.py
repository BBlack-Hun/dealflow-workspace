"""투자현황 화면 접근 권한 컬럼

이 화면은 팀 전체가 아니라 정해진 사람만 본다. 볼 사람 이름을 코드에 박으면
담당이 바뀔 때마다 배포해야 하므로 계정 속성으로 둔다(관리자는 항상 볼 수 있다).

Revision ID: 0007_consulting_access
Revises: 0006_template_name
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_consulting_access"
down_revision = "0006_template_name"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("users", "can_view_consulting"):
        op.add_column("users", sa.Column("can_view_consulting", sa.Integer(),
                                         nullable=False, server_default="0"))


def downgrade() -> None:
    if _has_column("users", "can_view_consulting"):
        op.drop_column("users", "can_view_consulting")
