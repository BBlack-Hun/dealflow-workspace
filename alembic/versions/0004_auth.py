"""ID/PW 인증 — users.password_hash + sessions

로그인 ID 는 기존 users.phone(unique)을 그대로 쓴다. 새 식별자를 만들지 않는다.

Revision ID: 0004_auth
Revises: 0003_sprint2_contacts
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_auth"
down_revision = "0003_sprint2_contacts"
branch_labels = None
depends_on = None

USER_COLUMNS = (
    ("password_hash", sa.String()),
    ("must_change_password", sa.Integer()),
    ("last_login_at", sa.String()),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _inspector().get_columns(table)}


def upgrade() -> None:
    for name, type_ in USER_COLUMNS:
        if not _has_column("users", name):
            op.add_column("users", sa.Column(name, type_, nullable=True))

    if not _has_table("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("token", sa.String(), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("expires_at", sa.String(), nullable=False),
            sa.Column("user_agent", sa.String(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
        op.create_index("ix_sessions_token", "sessions", ["token"], unique=True)


def downgrade() -> None:
    if _has_table("sessions"):
        op.drop_index("ix_sessions_token", table_name="sessions")
        op.drop_table("sessions")
    for name, _type in USER_COLUMNS:
        if _has_column("users", name):
            op.drop_column("users", name)
