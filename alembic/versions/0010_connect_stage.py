"""투자사 연결 단계 + 부서

지금까지 시스템에는 **카톡방까지 연결이 끝난** 담당자만 있었다. 실제 운영에서는
그 앞에 '전화 → 카톡 초대 → 연결'이라는 긴 과정이 있고, 그건 시트에만 있었다.
연결 단계를 넣어 그 과정을 시스템 안으로 들인다.

기존 담당자는 카톡방 이름이 있으면 연결 완료로 본다 — 지금까지 발송해 온
사람들이므로 연결이 끝난 것이 맞다.

Revision ID: 0010_connect_stage
Revises: 0009_sequences
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_connect_stage"
down_revision = "0009_sequences"
branch_labels = None
depends_on = None


def _columns(table: str) -> set:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    have = _columns("vc_contacts")
    if "department" not in have:
        op.add_column("vc_contacts", sa.Column("department", sa.String(), nullable=True))
    if "connect_stage" not in have:
        op.add_column("vc_contacts",
                      sa.Column("connect_stage", sa.String(), nullable=False,
                                server_default="not_started"))
        # 이미 카톡방이 붙어 있는 담당자는 연결이 끝난 사람이다.
        op.execute(
            "UPDATE vc_contacts SET connect_stage = 'connected' "
            "WHERE kakao_room_name IS NOT NULL AND TRIM(kakao_room_name) <> ''"
        )

    # **인덱스는 칸을 붙이는 것과 따로 본다.** 빈 DB 는 0001 의 `create_all()` 이
    # 칸까지 이미 만들어 둔 채로 오는데, 모델에는 이 인덱스가 선언돼 있지 않다.
    # 칸 만들기 안에 넣어 두면 그 길에서 통째로 건너뛰어, **새 서버만 인덱스
    # 없이** 도는 DB 가 된다(0005 가 쓰는 방식).
    if not _has_index("vc_contacts", "ix_vc_contacts_connect_stage"):
        op.create_index("ix_vc_contacts_connect_stage", "vc_contacts",
                        ["user_id", "connect_stage"])


def downgrade() -> None:
    have = _columns("vc_contacts")
    if _has_index("vc_contacts", "ix_vc_contacts_connect_stage"):
        op.drop_index("ix_vc_contacts_connect_stage", table_name="vc_contacts")
    if "connect_stage" in have:
        op.drop_column("vc_contacts", "connect_stage")
    if "department" in have:
        op.drop_column("vc_contacts", "department")
