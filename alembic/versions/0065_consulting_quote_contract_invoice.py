"""`관리 스타트업` 탭 — `견적서 첨부여부` · `계약관리` · `계산서 수신여부`

## 왜 칸을 새로 만드나

투자컨설턴트가 기업 하나를 붙들고 가는 흐름에 **견적서 → 계약 → 계산서** 라는
세 마디가 있는데, 표에는 그 자리가 없었다. 지금까지는 바로 옆 `기업 관리` 에
`관리 중 : 미팅 완. -> 견적서 보내기 완료.` 처럼 한 문장으로 적혀 있었다.

그 칸은 **지금 어떻게 되고 있는가**를 적고 그 값으로 칩과 KPI 를 세는 자리라
(`services/consulting_status.py`) 세 마디를 거기 계속 담으면 두 가지를 잃는다.

  · 견적서를 아직 안 보낸 곳만 골라낼 수가 없다. 한 문단 안에 섞여 있어서
    필터로도 검색으로도 "안 한 곳" 이 안 나온다(있는 것은 찾아지지만
    **없는 것**은 안 찾아진다).
  · 문장이 길어질수록 `관리`·`드랍` 같은 낱말이 우연히 들어가 그 줄이 엉뚱한
    갈래에 걸린다. 0049 가 `딜 소개문구` 를 따로 뺀 것과 같은 이유다.

## 왜 두 칸은 `String` 이고 한 칸만 `Text` 인가

`견적서 첨부여부` · `계산서 수신여부` 는 `O` / `X` 두 글자다 — 옆 탭의
`계약서 수신여부`(0048)와 같은 뜻·같은 모양이라 자료형도 같게 둔다.

`계약관리` 만 `Text` 다. **보기를 정해 두지 않은 자유 글**이라서다. 옆 두 칸은
이름이 `~여부` 로 끝나는데 이 칸만 `~관리` 이고, 이 표에서 `~관리` 로 끝나는
칸은 이미 하나 있다(`management` = `기업 관리`) — 그것도 문단이 들어오는
자유 문장이다. 시트를 쓰는 사람이 붙인 이름이 값의 모양을 말하고 있다.

보기를 세우지 않은 것은 **잘못 세우면 사람이 적을 자리가 없어지기** 때문이다.
자유 글로 두면 값이 몇 가지로 모이는 것이 나중에 보일 때 보기를 세우면 되고,
그때는 이미 적힌 값이 근거가 된다. 반대 방향은 되돌릴 자리가 없다.

## 이미 들어 있는 줄은 어떻게 되나 — **손대지 않는다**

세 칸 다 NULL 로 시작한다. 화면에서는 빈칸이고, 그 빈칸이 곧 `아직 안 정함`
이라는 뜻이다(머리글 필터가 `(비어 있음)` 으로 세워 준다).

전부 `X` 로 채우고 싶어지는 자리인데, 그러면 앱이 "안 보냈다"고 **단정**하는
것이 된다 — 아무도 확인한 적 없는 사실이다. `기업 관리` 에 섞여 적힌 문장을
읽어다 나눠 담는 것도 마찬가지다. 그 경계는 아무도 정한 적이 없고, 잘못 나눈
뒤에는 원래 한 줄이 어땠는지 남지 않는다(0047 · 0048 · 0049 가 같은 이유로
backfill 을 안 했다).

## 두 번 돌려도 죽지 않는가

칸이 이미 있으면 건너뛴다(0049 · 0048 · 0040 과 같은 방식). 스탬프가 어긋난
DB 로 컨테이너가 뜨면 `duplicate column name` 으로 죽고 다시 뜨는 크래시
루프가 된다.

## 되돌리면

칸을 지운다. 적어 둔 값도 같이 사라지는데, 다른 칸에서 옮겨 온 것이 아니라
이 칸에서 처음 생긴 값이라 남겨 둘 자리가 없다(0049 와 같다).

Revision ID: 0065_consulting_quote_contract_invoice
Revises: 0064_contact_column_hidden
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0065_consulting_quote_contract_invoice"
down_revision = "0064_contact_column_hidden"
branch_labels = None
depends_on = None

TABLE = "consulting_companies"
# (칸 이름, 자료형). `계약관리` 만 자유 글이라 `Text` 다 — 위 설명 참고.
COLUMNS = [
    ("quote_attached", sa.String()),
    ("contract_management", sa.Text()),
    ("invoice_received", sa.String()),
]


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 한 번에 하나씩 본다. 셋 중 하나만 이미 있는 DB(앞서 절반만 올라간 것)
    # 에서도 나머지가 붙어야 한다 — 묶어서 검사하면 그 DB 는 영영 안 채워진다.
    for name, kind in COLUMNS:
        if _has_column(TABLE, name):
            continue
        with op.batch_alter_table(TABLE) as b:
            b.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _kind in reversed(COLUMNS):
        if not _has_column(TABLE, name):
            continue
        with op.batch_alter_table(TABLE) as b:
            b.drop_column(name)
