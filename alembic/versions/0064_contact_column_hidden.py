"""명단의 칸을 **지우지 않고 숨긴다**

담당자마다 쓰던 스타트업 명단이 시트에서 그대로 딸려 온 옛 칸을 하나둘 달고
있다. 팀이 쓰는 한 가지 모양(`N월 리마인드 문자` · `N월 리마인드 TEL` ·
`N월 카톡 연결`)으로 맞추면서 그 칸들은 더 쓰지 않는데, **지우면 적혀 있던
내용이 함께 사라진다** — `routers/contacts.py` 의 `delete_column` 이 그 값을
줄마다의 `notes` 에서 같이 지운다. 지난 기록은 남겨 두고 표에서만 빼야 한다.

`SheetOwner.is_hidden` 과 **같은 방식**이다(같은 이름·같은 뜻·같은 기본값).
지우는 것이 아니라 세지 않는 것이고, 켜고 끄는 단추가 화면에 남아 있어
되돌리면 값이 그대로 다시 보인다.

`0` 으로 채운다 — 지금 서 있는 칸은 전부 보이던 칸이다. `nullable=False` 로
두지 않고 기본값 `0` 을 주는 것은 `SheetOwner.is_hidden` · `VcContact.is_hidden`
과 맞춘 것이다(같은 뜻의 칸이 표마다 다른 모양이면 읽는 쪽이 매번 확인해야 한다).

Revision ID: 0064_contact_column_hidden
Revises: 0063_weekly_routine_nth_weeks
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064_contact_column_hidden"
down_revision = "0063_weekly_routine_nth_weeks"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # **두 번 돌려도 죽지 않아야 한다.** `0001_initial` 이 `create_all()` 로 지금
    # 모델 전체를 만들기 때문에, 빈 DB 는 이 칸을 이미 갖고 시작한다 — 그대로
    # 붙이면 `duplicate column name` 으로 **부팅에서 죽는다**
    # (`tests/test_migrations.py` 가 지키는 그것이다).
    # 이미 서 있는 칸은 전부 보이던 칸이다 — `server_default="0"` 이 그 줄들을
    # 그대로 채운다(0007 과 같은 방식). `NULL` 이 섞이면 읽는 쪽마다
    # "비어 있으면 안 숨긴 것" 을 또 적어야 한다.
    if not _has_column("contact_columns", "is_hidden"):
        op.add_column("contact_columns",
                      sa.Column("is_hidden", sa.Integer(),
                                nullable=False, server_default="0"))


def downgrade() -> None:
    # **되돌리기가 비어 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서
    # 멎는다**(0012 가 그랬다 — `tests/test_migrations.py` 참고).
    # 숨겨 둔 표시는 사라지고 칸은 다시 전부 보인다. 값은 `notes` 에 있으므로
    # 그대로 남는다.
    if _has_column("contact_columns", "is_hidden"):
        op.drop_column("contact_columns", "is_hidden")
