"""문자로 알렸다는 표시 — 하루·한 사람·한 종류에 한 줄

## 왜 표가 필요한가

미팅 결과를 물어볼 때가 되면 담당 팀원에게 문자로 알린다. 그 알림을 보내는
실은 30분마다 깨어나 "오늘 물어볼 미팅이 있나" 를 본다(`services/backup.py` 의
일일 백업과 같은 방식이다 — 정해진 시각에 걸면 그 시각에 컨테이너가 안 떠
있는 날을 조용히 건너뛴다).

그런데 백업은 **뜬 파일 자체가 증거**라 따로 적을 것이 없었다. 문자는 나가고
나면 아무것도 남지 않는다. 남기지 않으면 깰 때마다 다시 보내서 **하루에 스무
통이 간다** — 문자는 통마다 돈이 나가고, 받는 사람 폰이 30분마다 울린다.

그래서 보냈다는 **사실**을 남기고 `(kind, day, user_id)` 에 유일 색인을 건다.
`monthly_column_runs`(0041) 가 같은 이유로 있는 표다.

## 왜 미팅 표에 칸을 붙이지 않았나

한 통에 여러 건이 실린다(`홍길동님(가나벤처스) 외 2건`). 미팅마다 `문자 보냄`
을 켜면 한 통이 세 칸을 건드리고, 그 사이에 미팅이 하나 더 완료되면 **같은 날
두 번째 문자**가 나간다. 보낸 단위(사람·날)로 남겨야 보낸 횟수와 맞는다.

## 옮길 데이터가 없다

지금까지 문자를 보낸 적이 없다. 표는 비어서 시작한다.

## 되돌리기

**표를 지운다.** 되돌리면 문자를 보내는 코드도 함께 돌아가고, 그 코드는 이 표를
아예 읽지 않는다 — 값을 되짚어 둘 자리가 없다.

## 두 번 돌려도 죽지 않는가

표와 색인 둘 다 있으면 건너뛴다(0041 이 쓰는 방식과 같다). 빈 DB 길에서는
`0001` 이 모델 전체를 이미 만들어 두므로 이 판은 아무 일도 하지 않는다
(`tests/test_migrations.py` 가 지키는 규칙이다).

Revision ID: 0061_sms_notices
Revises: 0060_meeting_meet_mode
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0061_sms_notices"
down_revision = "0060_meeting_meet_mode"
branch_labels = None
depends_on = None

TABLE = "sms_notices"
INDEX = "uq_sms_notices_kind_day_user"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in _inspector().get_indexes(table)}


def upgrade() -> None:
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            # 무슨 알림인가. 지금은 meeting_followup 하나.
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("day", sa.String(), nullable=False),          # YYYY-MM-DD
            sa.Column("user_id", sa.Integer(),
                      sa.ForeignKey("users.id"), nullable=False),
            # 그 문자에 몇 건이 실렸는가.
            sa.Column("count", sa.Integer(), nullable=True),
            # sending | sent | failed
            sa.Column("status", sa.String(), nullable=False,
                      server_default="sending"),
            # 왜 못 보냈나. 화면에 그대로 보여 준다.
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.String(), nullable=True),
            sa.Column("created_at", sa.String(), nullable=True),
            sa.Column("updated_at", sa.String(), nullable=True),
        )
    if not _has_index(TABLE, INDEX):
        op.create_index(INDEX, TABLE, ["kind", "day", "user_id"], unique=True)


def downgrade() -> None:
    if _has_table(TABLE):
        if _has_index(TABLE, INDEX):
            op.drop_index(INDEX, table_name=TABLE)
        op.drop_table(TABLE)
