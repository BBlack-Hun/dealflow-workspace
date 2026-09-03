"""[전체 자동조합] 을 되돌릴 자리 — `one_liner_backups`

## 무엇이 문제였나

`한줄 소개` 자동 조합은 지금까지 **한 곳씩** 눌러야 했다. 스타트업DB 를 채워도
사람이 쓴 소개는 일부러 안 덮기 때문에(`one_liner.origin` 의 AUTO/MANUAL),
쓰는 사람 눈에는 "동기화가 안 된다" 로 보인다. 그래서 화면에 [전체 자동조합] 을
두는데, 이것은 **빈 칸을 채우는 일이 아니라 이미 적힌 문장을 갈아엎는 일**이다 —
운영과 같은 사본 344곳에서 181곳이 사람이 쓴 값을 덮는 쪽이다.

그리고 덮는 쪽이 늘 나은 것도 아니다. 원본의 오타(`2,5억`)를 그대로 들고
오거나, 사람이 손으로 덧붙여 둔 매출이 빠지는 예가 실제로 있다. 그래서
**되돌릴 수 있어야** 누를 수 있는 기능이 된다.

## 왜 `desc_backup` 을 쓰지 않나

0051 이 만든 `ir_companies.desc_backup` 은 **합치기 직전 딱 한 번의 스냅숏**이다.
"원래 사업분야에는 뭐라고 적혀 있었지" 를 나중에 물을 때 돌아볼 곳이 그 칸
하나뿐이라, 일괄 적용이 그 위에 덮어쓰면 **그때의 백업이 영영 사라진다.**
성격도 다르다 — 그쪽은 한 번 쓰고 안 바뀌는 이력이고, 이쪽은 누를 때마다
쌓였다 없어지는 되돌리기 버퍼다. 같은 칸에 둘을 담으면 어느 쪽을 지우는
것인지 구분할 수가 없다.

## 왜 칸이 아니라 표인가

`ir_companies` 에 `one_liner_prev` 같은 칸 하나를 파면 **"이번 한 번에 바뀐
줄이 어디까지인가" 를 답할 수 없다.** [되돌리기] 는 방금 누른 그 묶음만
되돌려야 하는데, 칸으로는 두 번째 적용이 첫 번째의 흔적을 덮어써서 어느 줄이
어느 묶음이었는지 남지 않는다. 그러면 되돌리기가 다른 때 바꾼 줄까지 같이
끌고 온다. 그래서 **묶음(batch)** 을 들고 다니는 표로 둔다.

칸을 안 파는 이유가 하나 더 있다 — [수정] 창은 화면에 있는 칸을 **전부**
보내고, 그 짝이 맞는지 검사가 지킨다(`test_the_panel_sends_every_field_it_shows`).
서버만 쓰는 칸을 `ir_companies` 에 더하면 그 검사와 부딪힌다.

## 표의 모양

    batch       일괄 적용 한 번 = 한 묶음. `max(batch)+1` 로 매긴다.
    company_id  어느 기업인가
    previous    바꾸기 전 값. **NULL 이면 그때 비어 있었다**는 뜻이다
                (`''` 와 구분한다 — 0051 이 같은 이유로 NULL 을 쓴다).
    applied     우리가 써 넣은 값. 되돌릴 때 **그 뒤에 사람이 또 고쳤는가**를
                이 값과 맞춰 본다. 다르면 그 줄은 건드리지 않는다 —
                0051 의 downgrade 가 쓰는 것과 같은 방식이다.
    user_id     누가 눌렀나

되돌리기가 끝난 묶음은 지운다. 남겨 두면 [되돌리기] 를 다시 눌렀을 때 같은
묶음을 또 되돌리려 든다.

## 되돌아가나

`downgrade` 는 표를 통째로 지운다. 되돌리기 버퍼라 잃을 이력이 없다 —
`한줄 소개` 자체는 `ir_companies` 에 그대로 있다.

Revision ID: 0052_one_liner_bulk_undo
Revises: 0051_one_liner_single_source
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052_one_liner_bulk_undo"
down_revision = "0051_one_liner_single_source"
branch_labels = None
depends_on = None

TABLE = "one_liner_backups"


def _has_table(name: str) -> bool:
    # 빈 DB 는 0001 의 `create_all()` 이 지금 모델 전체를 만들어 주므로 이미 있다.
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(),
                  sa.ForeignKey("ir_companies.id"), nullable=False),
        # NULL = 그때 비어 있었다. `''` 로 적으면 '비어 있었다' 와
        # '빈 글자가 들어 있었다' 가 같아진다.
        sa.Column("previous", sa.Text(), nullable=True),
        sa.Column("applied", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=True),
    )
    # 되돌리기는 늘 **가장 최근 묶음**을 찾는다. 묶음 수가 늘어도 그 한 번이
    # 표를 통째로 훑지 않도록 한다.
    op.create_index(f"ix_{TABLE}_batch", TABLE, ["batch"])


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index(f"ix_{TABLE}_batch", table_name=TABLE)
    op.drop_table(TABLE)
