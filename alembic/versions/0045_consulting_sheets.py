"""투자컨설턴트 현황의 탭을 **값으로** 옮긴다

## 무엇이 문제였나

탭 셋(`스타트업` · `경영본부 전달 기업` · `월간 계약 업무현황표`)이 코드에 박힌
목록이었다. 그래서 이름을 고치려면 배포를 해야 했고, 실제로 한 번 고쳤을 때
(`중요 스타트업` → `스타트업`) 이름만 바꾸니 이미 들어간 줄이 **옛 이름의 유령
탭으로 갈라져서** 자료를 옮기는 마이그레이션을 따로 써야 했다(0039).

그리고 `월간 계약 업무현황표` 만 표 모양이 다른데(`CONTRACT_COLUMNS`) 그 짝을
**이름으로** 맞추고 있었다 — 이름을 고칠 수 있게 하는 순간 탭 이름 한 글자에
계약 표가 일반 표로 돌아간다.

## 무엇을 만드나

`consulting_sheets` 표. 칸 둘이 핵심이다.

    kind   **바뀌지 않는 열쇠.** 표 모양·기본 탭 판정이 이것으로 간다.
    label  화면에 보이는 이름. 사람이 고친다.

## 이름을 **지금 쓰고 있는 값**에서 가져온다

기본 이름을 그냥 넣으면 안 된다. 누군가 이미 시트를 올려 `스타트업` 이 아닌
이름으로 줄을 쌓아 두었다면, 새 탭 이름과 그 줄의 이름이 어긋나 **그 줄들이
어느 탭에도 안 뜬다.** 그래서 `consulting_companies` · `consulting_columns` 에
실제로 적혀 있는 이름을 먼저 보고, 기본 이름이 거기 있으면 그대로 쓴다.

여기서 줄을 옮기지는 않는다 — 옮길 것이 없다. 이름을 **줄 쪽에 맞추는** 것이지
줄을 이름 쪽으로 끌고 오는 것이 아니다.

## 두 번 돌려도 되는가

표를 만들 때 `checkfirst` 로 이미 있으면 넘어가고, 씨앗은 **없는 열쇠만** 넣는다.
두 번째 실행에서는 세 열쇠가 다 있어 넣는 줄이 0이고, 그때 이미 고쳐 둔 이름을
덮지 않는다 — 덮으면 화면에서 바꾼 이름이 배포마다 원래대로 돌아간다.

Revision ID: 0045_consulting_sheets
Revises: 0044_process_ref_back
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_consulting_sheets"
down_revision = "0044_process_ref_back"
branch_labels = None
depends_on = None

TABLE = "consulting_sheets"

# (열쇠, 처음 이름). `app/services/consulting_sheets.py` 의 `DEFAULTS` 와 같아야
# 한다 — 갈리면 마이그레이션이 세운 탭과 앱이 찾는 탭이 어긋난다.
DEFAULTS = [
    ("startup", "스타트업"),
    ("handover", "경영본부 전달 기업"),
    ("contract", "월간 계약 업무현황표"),
]


def upgrade() -> None:
    bind = op.get_bind()
    sa.Table(
        TABLE, sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String, unique=True),
        sa.Column("label", sa.String),
        sa.Column("position", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.String),
        sa.Column("updated_at", sa.String),
    ).create(bind, checkfirst=True)

    # **없는 열쇠만 넣는다.** 이미 있는 줄의 이름을 덮으면, 화면에서 고쳐 둔
    # 이름이 배포할 때마다 원래대로 돌아간다.
    have = {row[0] for row in bind.execute(sa.text(f"SELECT kind FROM {TABLE}"))}
    for pos, (kind, label) in enumerate(DEFAULTS):
        if kind in have:
            continue
        bind.execute(
            sa.text(f"INSERT INTO {TABLE} (kind, label, position) "
                    "VALUES (:k, :l, :p)"),
            {"k": kind, "l": label, "p": pos})

    # 줄이 **다른 이름**으로 쌓여 있으면(누가 그 이름으로 시트를 올린 경우)
    # 여기서 짝지어 주지 않는다. 짐작으로 맞추면 남의 탭을 뭉칠 수 있다.
    # 그 줄들은 화면에 그 이름 그대로 탭이 되고(`sheet_tabs` 가 줄의 이름도
    # 탭으로 세운다), 사람이 [이름 저장] 으로 맞추면 그때 줄까지 따라온다.


def downgrade() -> None:
    op.drop_table(TABLE)
