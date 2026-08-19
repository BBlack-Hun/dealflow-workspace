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


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 0001 이 Base.metadata.create_all() 로 **현재 모델 전체**를 만든다. 그래서 새 DB에서는
    # 이 컬럼이 이미 생긴 채로 여기 도착한다(기존 DB에서는 없다). 두 경로 모두 head 까지
    # 올라가야 하므로 존재 여부를 보고 건너뛴다.
    if not _has_column("agent_devices", "sender"):
        op.add_column("agent_devices", sa.Column("sender", sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column("agent_devices", "sender"):
        op.drop_column("agent_devices", "sender")
