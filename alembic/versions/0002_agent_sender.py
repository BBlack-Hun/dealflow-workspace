"""agent_devices.sender 추가

어떤 발송기(mock / kakao_windows / kakao_mac / telegram)가 연결됐는지 기록한다.
mock 이 붙은 채로 실제 발송을 시도하면 잡을 가로채 '보낸 것처럼' 끝나므로,
연결 배지에서 이를 구분해 보여주기 위함이다.

Revision ID: 0002_agent_sender
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_agent_sender"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_devices", sa.Column("sender", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_devices", "sender")
