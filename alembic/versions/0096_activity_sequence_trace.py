"""손으로 적은 줄이 **후속 시퀀스에 한 일** — 칸 하나

`contact_activities.sequence_trace` — 손으로 보낸 것을 적을 때
(`services/manual_send.record`) `cadence.advance` 가 리마인드 시퀀스를 새로
세우거나 덮어쓴다. 그 **전 모습과 뒤 모습**을 JSON 으로 적어 둔다.

## 왜

되돌리기(`manual_send.undo`)가 활동 줄만 숨기고 시퀀스는 그대로 두었다. 그래서
잘못 적은 딜 소개를 되돌려도 리마인드가 `오늘 할 일` 과 후속 관리에 남아, 받은
적 없는 사람에게 "지난번 공유드린…" 이 나갈 수 있었다.

되돌리려면 **그 줄이 세운 시퀀스인지**, 이미 서 있던 것을 덮어썼다면 **그 전에
어땠는지**를 알아야 한다. `advance` 는 딜소개일·단계·다음 예정일을 덮어써서
그 전 값이 어디에도 안 남는다 — 기존 칸으로는 가를 수 없어서 칸을 하나 둔다.

## 값을 채우지 않는다

`INSERT` 도 `UPDATE` 도 없다. 이미 서 있는 줄은 무엇을 했는지 적힌 적이 없으니
`NULL`(= 시퀀스를 안 건드린 줄)이 맞는 값이다. 그 줄들을 되돌리면 지금처럼 줄만
숨고 시퀀스는 그대로다 — 이 판 전과 같다.

## 빈 DB 에서는 아무 일도 하지 않는다

`0001_initial` 이 `create_all()` 로 지금 모델 전체를 만들어, 새 DB 는 이 칸을
이미 갖고 시작한다. 있는지 보고 넣는다(0084 · 0085 와 같은 방식).

## 번호

0087~0095 는 딜 소싱 메일·투자사 연결·Series A 표(`0095_series_a_shares`)가 먼저
썼다 — 그 판 위에 선다(처음에는 0087 이었다). 그 뒤 Series A 리뷰 수정
(`0101_series_a_shared_by` · `0102_series_a_import_key`)이 먼저 운영에 나가,
릴리스에서 이 판을 0102 뒤로 옮겨 머리를 하나로 맞춘다
(0102 → 0096 → 0097 → 0098 → 0099 → 0100).

Revision ID: 0096_activity_sequence_trace
Revises: 0102_series_a_import_key
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0096_activity_sequence_trace"
down_revision = "0102_series_a_import_key"
branch_labels = None
depends_on = None

TABLE = "contact_activities"
COLUMN = "sequence_trace"


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    have = _columns(TABLE)
    if not have:
        return
    if COLUMN not in have:
        op.add_column(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    # 되돌려도 잃는 것은 **되짚을 근거**뿐이다. 그 뒤에 되돌리는 줄은 이 판
    # 전처럼 줄만 숨고 시퀀스는 그대로 남는다.
    if COLUMN in _columns(TABLE):
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
