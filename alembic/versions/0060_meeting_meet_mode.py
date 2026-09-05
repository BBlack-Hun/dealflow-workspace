"""미팅이 **대면인가 화상인가** — 캘린더 제목에 그 자리가 있는데 칸이 없었다

## 왜 칸이 필요한가

팀이 손으로 적어 오던 캘린더 제목은 이렇게 생겼다::

    [적은 사람/기업 담당자/대면] 가나컴퍼니 IR 미팅 / 투자사 …

세 번째 자리가 **만나는 방식**이다. 그 자리를 채우려면 미팅마다 대면인지
화상인지를 알아야 하는데, `meetings` 에는 그 칸이 없었다 — 날짜·시각·구분
(1차/2차)·결과는 있는데 **어디서 만나는지는 적을 자리가 없었다.**

값은 둘이다: `in_person`(대면) · `video`(화상). 같은 표의 `kind`·`status`·
`outcome` 과 같은 방식이다 — DB 에는 코드, 화면에는 우리말
(`services/pipeline.py: MEETING_MODES`).

## 비워 둘 수 있어야 한다

**NOT NULL 로 두지 않는다.** 이 칸이 생기기 전에 잡힌 미팅이 이미 수백 건이고,
둘 중 하나를 기본값으로 채우면 **아무도 고르지 않은 미팅이 `대면` 으로 적힌다.**
그 미팅은 캘린더 제목에 `대면` 을 달고 나가고, 사람은 그 말을 믿고 나갈 준비를
한다. 옆의 `contract_received`(0048) 가 같은 이유로 NULL 을 남겨 두었다.

빈칸이 곧 `안 정함` 이다. 캘린더 제목에서는 그 자리가 **슬래시째** 빠진다 —
`[적은 사람/기업 담당자]`. 값이 없다는 것과 지어낸 값은 다르다.

## 옮길 데이터가 없다

새 칸이고, 지금 있는 미팅 어느 것도 이 값을 다른 칸에 담고 있지 않다.
채워 넣을 근거가 아무 데도 없으므로 **전부 빈 채로 시작한다.** 사람이 미팅
화면에서 하나씩 고르면 그때부터 제목에 선다.

## 되돌리기

**칸을 지운다.** 되돌리면 코드도 함께 돌아가 제목이 두 자리로 서고, 그 코드는
이 칸을 아예 읽지 않는다 — 값을 되짚어 둘 자리가 없다.

`app/models.py` 와 화면·경로가 **같은 커밋에서 함께** 옮겨간다
(`tests/test_migrations.py::test_the_fresh_schema_matches_the_models` 가
이주 결과와 모델을 칸 단위로 대조한다).

Revision ID: 0060_meeting_meet_mode
Revises: 0059_ir_auto_attach_access
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0060_meeting_meet_mode"
down_revision = "0059_ir_auto_attach_access"
branch_labels = None
depends_on = None

TABLE = "meetings"
COLUMN = "meet_mode"


def _has_column() -> bool:
    """빈 DB 길에서는 `0001` 이 모델 전체를 이미 만들어 둔다.

    그 자리에 또 붙이면 `duplicate column name` 으로 **부팅이 죽는다**
    (`tests/test_migrations.py` 가 지키는 규칙이다).
    """
    insp = sa.inspect(op.get_bind())
    if TABLE not in insp.get_table_names():
        return False
    return COLUMN in {c["name"] for c in insp.get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        # nullable 이라 기본값을 주지 않는다 — 지금 있는 미팅은 **빈 채로**
        # 남는다(위 `## 비워 둘 수 있어야 한다`).
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    """칸을 지운다 — 위 `## 되돌리기` 참고."""
    if _has_column():
        op.drop_column(TABLE, COLUMN)
