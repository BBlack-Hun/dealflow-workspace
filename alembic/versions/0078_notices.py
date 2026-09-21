"""공지 — 팀에게 알리는 글(`notices`)과 **봤다는 표시**(`notice_reads`)

## 왜 표가 둘인가

공지 한 장을 사람 수만큼이 읽는다. 읽은 사람을 `notices` 안에 담을 자리가
없어서 옆 표가 하나 선다. `(notice_id, user_id)` 에 유일 색인을 걸어 두 번
눌러도 줄이 하나다 — `sms_notices` 가 `(kind, day, user_id)` 로 그날 자리를
하나만 잡는 것과 같은 방식이고, 열쇠만 다르다.

## 왜 `edit_logs` 를 쓰지 않았나

`edit_logs` 에는 이미 **누가 무엇을 고쳤는지**가 줄줄이 남는다. 그것을 그대로
띄우지 않는 이유가 셋이다(`app/services/notices.py` 머리말에 한 곳으로 적어
두었다): 시트 한 번 올리면 수백 줄이라 띄우면 더 안 본다 · 거기 실린 것은
사람 이름과 기업 이름이라 전원에게 띄우면 공지가 아니라 남의 근무 기록이
된다 · `connect_stage: 연결 전 → 연결됨` 은 기계의 말이고 팀이 읽어야 하는
것은 `미팅 종류 칸이 생겼습니다` 다.

## 이미 들어 있는 줄은 어떻게 되나 — **없다**

새로 세우는 표라 옮겨 올 값이 없다. 빈 채로 시작하고, 공지가 하나도 없으면
밑틀은 아무 것도 그리지 않는다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 표를
이미 갖고 시작한다. 여기서 또 만들면 `table already exists` 로 부팅이 죽는다
(`tests/test_migrations.py` 가 지키는 그것이다). 유일 색인도 표를 만드는 `if`
**밖에서** 따로 본다 — 안에 넣으면 빈 DB 길에서 통째로 건너뛴다(0072 와 같다).

## 되돌리면

두 표가 사라진다. **올린 공지와 누가 봤는지는 안 돌아온다** — 이 표에서 처음
생긴 값이라 옮겨 둘 자리가 없다. 되돌린 뒤 다시 올리면 빈 표가 서고, 그때는
전에 확인한 공지가 (다시 올린다면) 한 번 더 뜬다.

Revision ID: 0078_notices
Revises: 0077_consulting_kakao_joined
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0078_notices"
down_revision = "0077_consulting_kakao_joined"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    tables = _tables()
    if "notices" not in tables:
        op.create_table(
            "notices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
            sa.Column("title", sa.String(), nullable=False),
            # 제목 한 줄이면 되는 공지가 많다 — 본문은 비어 있어도 된다.
            sa.Column("body", sa.Text(), nullable=True, server_default=""),
            # 내리면 0. 줄은 지우지 않는다(`services/notices.turn_off`).
            sa.Column("is_active", sa.Integer(), nullable=True,
                      server_default="1"),
            sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
        )
    if "notice_reads" not in tables:
        op.create_table(
            "notice_reads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("notice_id", sa.Integer(), sa.ForeignKey("notices.id"),
                      nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                      nullable=False),
            sa.Column("at", sa.String(), nullable=True),
        )

    # 두 번 눌러도 줄이 하나. 막히는 것에 기대지는 않지만(서비스가 먼저
    # 본다) 뒤로가기 · 두 창을 같이 열어 둔 경우까지 여기서 잡힌다.
    if "uq_notice_reads_notice_user" not in _indexes("notice_reads"):
        op.create_index("uq_notice_reads_notice_user", "notice_reads",
                        ["notice_id", "user_id"], unique=True)


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    if "uq_notice_reads_notice_user" in _indexes("notice_reads"):
        op.drop_index("uq_notice_reads_notice_user", table_name="notice_reads")
    tables = _tables()
    if "notice_reads" in tables:
        op.drop_table("notice_reads")
    if "notices" in tables:
        op.drop_table("notices")
