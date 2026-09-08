"""IR 기업 현황에 `미팅제공일자` 칸

## 왜 칸이 하나 더 필요한가

`계약여부` 에 **무료 IR 미팅** 두 상태가 생겼다 —
`무료IR 미팅제공예정` · `무료 IR 미팅제공완료함`(`routers/companies.py` 의
`CONTRACT_LABELS`). 상태만으로는 "그래서 그게 언제냐" 를 적을 자리가 없다.
`예정` 이 몇 달째 예정인지, `완료함` 이 지난주인지 작년인지 구별할 수 없으면
그 두 상태는 표에서 세어 봐야 아무것도 알려 주지 않는다.

자리는 **`계약여부` 바로 앞**이다(사용자 요청). 날짜를 먼저 보고 상태를 읽는
차례라, 떨어뜨려 두면 두 칸을 번갈아 짚어야 한다.

## 왜 날짜형이 아니라 글자인가

사람이 **손으로 적는 칸**이다(사용자 요청 — 달력 고르개가 아니다). 이 표의
같은 결인 칸들이 이미 그렇다: `contract_month`(홍보메일삭제)에 실제로 들어
있는 값은 `삭제 완료` · `8/13 삭제` 이고, `received_at`(수신일)도 String
이다. 날짜형으로 못 박으면 `9월 중` · `미정` 처럼 실제로 쓰는 말을 적을 데가
없어지고, 그 말은 메모 칸으로 새어 이 칸은 빈 채로 남는다.

## 왜 기본값을 안 주는가

새 칸이라 **어느 줄에도 사실이 없다.** `nullable=True` 에 `server_default` 를
두지 않는다 — 이미 있는 줄은 전부 NULL 로 남아 화면에서 빈 칸으로 보인다.
옆의 `contract_received`(0047)·`meet_mode`(0060)가 같은 이유로 같은 모양이다.

## downgrade

칸만 지운다. SQLite 는 예전 판에서 `ALTER TABLE … DROP COLUMN` 을 못 하므로
다른 마이그레이션과 같이 `batch_alter_table`(표를 다시 만들어 옮긴다)로 간다.
내리면 적어 둔 날짜는 함께 사라진다 — 되돌릴 값이 이 칸 말고는 없다.
(`계약여부` 의 새 두 상태는 값이 글자라 스키마를 건드리지 않는다. 내려도
`ir_companies.contract_status` 에 그대로 남고, 다시 올리면 그대로 읽힌다.)

Revision ID: 0065_ir_meeting_offered_at
Revises: 0064_contact_column_hidden
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0065_ir_meeting_offered_at"
down_revision = "0064_contact_column_hidden"
branch_labels = None
depends_on = None

TABLE = "ir_companies"
COLUMN = "meeting_offered_at"


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 이미 있으면 건너뛴다 — 빈 DB 는 0001 이 모델 그대로 만들어 준 채로 온다
    # (tests/test_migrations.py 가 그 길을 지킨다).
    if not _has_column(TABLE, COLUMN):
        with op.batch_alter_table(TABLE) as b:
            # 기본값 없음 = 이미 있는 줄은 전부 NULL(아직 안 정함).
            b.add_column(sa.Column(COLUMN, sa.String(), nullable=True))


def downgrade() -> None:
    if _has_column(TABLE, COLUMN):
        with op.batch_alter_table(TABLE) as b:
            b.drop_column(COLUMN)
