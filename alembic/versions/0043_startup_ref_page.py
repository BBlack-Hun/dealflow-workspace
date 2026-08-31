"""스타트업 쪽 참고 자료를 `스타트업 리마인드` 화면으로 옮긴다

## 무엇을 옮기는가

투자사 관리 현황의 참고 탭에 성격이 다른 자료 둘이 섞여 있었다. 나머지 자료는
**심사역에게 딜을 보내는** 이야기인데(전화응대 스크립트 · 딜소개 스크립트 ·
투자사 성격정리 · 카톡방 연결 순서 · IR 배분) 이 둘만 **스타트업 대표에게
보내는** 매월 리마인드 안내다. 말 거는 상대가 다르면 집어야 할 문구도 다른데,
탭 이름만 보고는 갈리지 않아 열어 읽어 봐야 알 수 있었다.

옮기는 것은 **자료뿐이다.** `스타트업(16)` 명단(사람 데이터)은 투자사 관리
현황의 탭으로 그대로 둔다 — 명단을 옮기는 것은 명단 소유·월별 칸·발송 대상
판정이 함께 따라오는 일이라 확인 없이 건드릴 자리가 아니다.

## 왜 스크립트가 아니라 마이그레이션인가

0039 와 같은 이유다.

  · **배포와 같은 순간에 돌아야 한다.** 새 메뉴가 뜬 뒤 사람이 스크립트를
    부르기까지의 사이가, 새 화면은 비어 있고 옛 화면에는 그대로 남아 있는
    시간이다. 컨테이너는 기동할 때 이미 마이그레이션을 돌린다.
  · **한 번만 돌아야 한다.** 스크립트는 운영에 적용됐는지 확인할 방법이
    또 돌려 보는 것뿐이다.
  · **되돌릴 수 있어야 한다.** `downgrade` 가 투자사 관리 현황으로 돌려놓는다.

## 왜 이름으로 찾는가 — 그리고 두 번 돌려도 되는가

`RefSheet` 에는 이 자료를 가리킬 다른 표시가 없다(번호는 DB 마다 다르다).
그래서 원본 시트의 탭 이름 그대로 찾는다 — 사람이 화면에서 이름을 이미
바꿨다면 걸리지 않고 그냥 지나간다. **조용히 실패하는 쪽이 맞다**: 못 찾았다고
엉뚱한 자료를 옮기면 투자사 쪽 스크립트가 스타트업 화면으로 사라진다.
남는 것은 옛 화면에 그대로 있으므로 화면에서 눌러 옮길 수 있다.

두 번째 실행에서는 `page = 'contacts'` 인 줄이 없어 걸리는 줄이 0이다.
스키마를 건드리지 않으므로 크래시 루프가 날 자리도 없다.

Revision ID: 0043_startup_ref_page
Revises: 0042_sheet_deal_list
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_startup_ref_page"
down_revision = "0042_sheet_deal_list"
branch_labels = None
depends_on = None

CONTACTS = "contacts"
STARTUP = "startup"

# 원본 시트의 탭 이름 그대로. 화면에서 이름을 바꾼 자료는 걸리지 않는다(위 참고).
TITLES = (
    "40개사 스타트업 매월 1회 리마인드 카톡 가이드",
    # 스타트업 시트의 표 아래에 붙어 있던 운영 안내문이다
    # (`scripts/import_startup_sheet.py` 가 명단과 갈라 여기 넣었다).
    "업무 프로세스",
)


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
    _move(CONTACTS, STARTUP)


def downgrade() -> None:
    _move(STARTUP, CONTACTS)
