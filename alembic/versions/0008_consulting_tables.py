"""투자컨설턴트 현황표

원본 구글시트를 그대로 옮긴다. 월별 리마인드 열은 달마다 하나씩 늘어나므로
테이블 컬럼이 아니라 `consulting_columns` 행으로 두고, 내용은 기업 행의 JSON 에 담는다
(그러지 않으면 매달 마이그레이션을 해야 한다).

Revision ID: 0008_consulting_tables
Revises: 0007_consulting_access
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_consulting_tables"
down_revision = "0007_consulting_access"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    have = _tables()
    if "consulting_columns" not in have:
        op.create_table(
            "consulting_columns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    if "consulting_companies" not in have:
        op.create_table(
            "consulting_companies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("position", sa.Integer(), nullable=True),
            sa.Column("region", sa.String(), nullable=True),
            sa.Column("meeting_at", sa.String(), nullable=True),
            sa.Column("company_name", sa.Text(), nullable=True),
            sa.Column("management", sa.Text(), nullable=True),
            sa.Column("ceo_name", sa.String(), nullable=True),
            sa.Column("phone", sa.String(), nullable=True),
            sa.Column("email", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )

    # **인덱스는 표를 만드는 것과 따로 본다.** 빈 DB 는 0001 의
    # `create_all()` 이 표를 이미 만들어 둔 채로 오는데, 모델에는 이 인덱스가
    # 선언돼 있지 않다. 표 만들기 안에 넣어 두면 그 길에서 통째로 건너뛰어,
    # **새 서버만 인덱스 없이** 도는 DB 가 된다(0005 가 쓰는 방식).
    if not _has_index("consulting_companies", "ix_consulting_companies_position"):
        op.create_index("ix_consulting_companies_position",
                        "consulting_companies", ["position"])


def downgrade() -> None:
    have = _tables()
    if "consulting_companies" in have:
        op.drop_table("consulting_companies")
    if "consulting_columns" in have:
        op.drop_table("consulting_columns")
