"""`업무 프로세스` 자료를 투자사 관리 현황으로 되돌린다

## 무엇을 되돌리는가

0043 이 스타트업 쪽 참고 자료 **둘**을 새 화면으로 옮겼다. 그중 하나만
되돌린다.

  · `40개사 스타트업 매월 1회 리마인드 카톡 가이드` — 새 화면에 그대로 둔다.
    스타트업 대표에게 매월 보내는 말 그 자체다.
  · `업무 프로세스` — **투자사 관리 현황으로 되돌린다.** 스타트업 시트의 표
    아래에 붙어 있던 글이라 함께 옮겼는데, 실제로 적힌 것은 팀이 딜을 돌리는
    순서였다. 옮겨 놓고 보니 그 화면에서 찾을 자료가 아니었다.

## 명단(사람 데이터)은 여기서 옮기지 않는다

같은 배포에서 `스타트업` 명단들이 새 화면으로 간다. **그런데 손댈 데이터가
없다.** 어느 명단이 어느 화면에 서는지는 그 명단에 이미 붙어 있는 배치
값(`sheet_owners.layout`)이 정하고, 그 배치가 어느 화면인지는 코드가 정한다
(`app/services/contact_columns.py` 의 `Layout.page`).

값을 하나 더 두지 않은 이유가 그것이다 — 새 칸을 만들었다면 여기서 306행을
훑어 채워야 했고, 다음에 명단이 들어올 때 그 칸을 빠뜨리면 명단이 화면에서
사라진다. 배치만 맞추면 화면이 따라오는 편이 빠뜨릴 자리가 없다.

## 두 번 돌려도 되는가

`page = 'startup'` 인 줄만 고른다. 두 번째 실행에서는 그 이름이 이미
`contacts` 라 걸리는 줄이 0이다. 스키마를 건드리지 않으므로 크래시 루프가 날
자리도 없다.

이름으로 찾는 것도 0043 과 같은 이유다 — `RefSheet` 에 이 자료를 가리킬 다른
표시가 없고(번호는 DB 마다 다르다), 사람이 화면에서 이름을 이미 바꿨다면 걸리지
않고 그냥 지나간다. **조용히 실패하는 쪽이 맞다**: 못 찾았다고 엉뚱한 자료를
옮기면 스타트업 안내문이 투자사 화면으로 사라진다. 남는 것은 그 화면에 그대로
있으므로 눌러서 옮길 수 있다.

Revision ID: 0044_process_ref_back
Revises: 0043_startup_ref_page
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_process_ref_back"
down_revision = "0043_startup_ref_page"
branch_labels = None
depends_on = None

CONTACTS = "contacts"
STARTUP = "startup"

# 원본 시트의 탭 이름 그대로. 0043 이 옮긴 둘 중 **이것만** 되돌린다.
TITLES = ("업무 프로세스",)


def _move(frm: str, to: str) -> None:
    table = sa.table("ref_sheets",
                     sa.column("page", sa.String),
                     sa.column("title", sa.String))
    op.execute(
        table.update()
        .where(sa.and_(table.c.page == frm, table.c.title.in_(TITLES)))
        .values(page=to)
    )


def upgrade() -> None:
    _move(STARTUP, CONTACTS)


def downgrade() -> None:
    _move(CONTACTS, STARTUP)
