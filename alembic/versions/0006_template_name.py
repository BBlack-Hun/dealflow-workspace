"""message_templates.name — 같은 종류 템플릿을 여러 개 두고 고르기 위한 이름

Revision ID: 0006_template_name
Revises: 0005_indexes
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_template_name"
down_revision = "0005_indexes"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("message_templates", "name"):
        op.add_column("message_templates", sa.Column("name", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("message_templates", "name"):
        op.drop_column("message_templates", "name")
