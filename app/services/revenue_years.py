"""연도별 매출 칸 — 화면에 **어느 해**를 세우나, 해가 바뀌면 **무엇을 옮겨 적나** (#75).

## 칸은 미리 파 두었다

`ir_companies.revenue_2022` ~ `revenue_2030`(0019 · 0121). 해마다 판을 만들지 않으려고
다섯 해치를 한 번에 팠다 — Series A 탭이 24~27년을 미리 판 것과 같은 방식이다(0112).

**2032년 1월 전에 `revenue_2031` 판 하나만 더한다.** 그해에 처음으로 지난해 칸
(`revenue_2031`)이 필요해진다. 판과 함께 한 줄씩 적을 곳이 셋이다 — 모델 ·
`routers/companies.CompanyIn` · `static/js/companies.js` 의 `FIELDS`. 빠뜨리면
tests/test_revenue_years.py 가 잡는다. 칸이 모자라도 화면은 안 죽는다 — 없는 해는
건너뛴다(`shown`).

## 화면에 서는 해 — 올해 기준 **지난 세 해** + `최근 매출액(올해)`

2026년이면 23·24·25년과 `최근 매출액(26년)`. 올해 매출은 해가 안 끝나서 연도 칸이
아니라 `revenue_recent` 가 그 자리다(옛 결정 — 딜소개 문구 · 소개 가능 판정 · 엑셀 ·
LLM 이 읽는 칸이라 그대로 둔다).

스타트업DB 탭 · IR 기업 현황 탭 · [수정] 창 · `지금 화면 내려받기` · 한줄 소개 조합이
**이 파일 하나**를 읽는다. 오래된 해는 **표에서 빠질 뿐** 값은 그대로다 — 창에도 안
서므로 [저장]이 그 칸을 보내지 않고, 시트 가져오기는 모든 해를 채운다
(`scripts/import_company_sheets.py`).

## 해가 바뀌면 — `최근 매출액` 을 지난해 칸으로 **옮겨 적는다** (`roll_over`)

2027년 첫 화면에서, `revenue_2026` 이 빈 기업은 `revenue_recent` 를 그 칸에 적는다.

  · `revenue_recent` 는 **안 지운다** — 새 값이 들어올 때까지 '가장 최근 값' 이다.
  · 지난해 칸에 이미 적힌 값은 **안 덮는다.**
  · **단위를 붙여 옮긴다**(`18.3` → `18.3억`). `revenue_recent` 는 단위가 억으로 정해진
    칸이라 숫자만 적혀 있는데, 연도 칸은 **적힌 그대로** 읽는 글자라(`8.2억` ·
    `1,224백만원`) 그대로 옮기면 한줄 소개가 `매출 26년 18.3` 이 된다. 붙이는 규칙은
    문구가 쓰는 그것이다(`amount.phrase`). 못 읽는 글자(`~` · `확인필요`)는 그대로 옮긴다.

**언제 — 화면(`/companies`)을 열 때.** 달마다 칸을 세우는 방식 그대로다
(`monthly_columns`). 예약 실(백업 · 자동화)도 있지만 거기에는 사람이 없어 **수정
로그에 안 남는다** — 공용 표 수백 줄을 한 번에 고치는 일이라 남아야 한다. 그래서
화면을 연 사람 이름으로 남긴다(`edit_log.begin` — 딜 소싱 `mark_invited` 와 같다).
아무도 안 연 동안 옮겨지지 않은 것은 탈이 없다 — 여는 순간 옮겨진다.

**해마다 한 번이다**(`MonthlyColumnRun` 에 `revenue_year` · 그 해). 사람이 일부러 비운
지난해 칸을 다음 화면이 다시 채우지 않고, 동시에 연 두 화면 중 하나만 돈다.

**2026년에는 안 돈다.** `revenue_recent` 가 처음부터 26년 자리였다 — 그 값을 25년
칸에 옮기면 틀린 해에 적힌다(`FIRST_RECENT_YEAR`).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import IrCompany, MonthlyColumnRun
from . import amount, edit_log
from .monthly_columns import _claim

#: 표에 세우는 지난 해 수.
SHOWN = 3
#: `revenue_recent` 가 처음 가리킨 해 — 옮겨 적기는 그다음 해(2027)부터다.
FIRST_RECENT_YEAR = 2026
#: `MonthlyColumnRun.target` — 그해 옮겨 적었다는 표시.
TARGET = "revenue_year"

#: 모델에 파 둔 연도별 매출 칸 — 오래된 해부터(`revenue_2022` …).
FIELDS = sorted(c.key for c in IrCompany.__table__.columns
                if re.fullmatch(r"revenue_\d{4}", c.key))


def this_year() -> int:
    """올해. 검사는 이것 하나를 못 박는다(tests/conftest.py)."""
    return clock.today().year


def shown(year: Optional[int] = None) -> List[Tuple[str, str]]:
    """화면에 세우는 지난 세 해 — `[("revenue_2023", "23"), …]`, 오래된 해부터.

    뒷값은 머리글·한줄 소개에 적는 연도 글자다(`23년 매출` · `매출 23년 2억`).
    칸을 안 판 해는 건너뛴다 — 판을 늦게 더해도 화면은 안 죽는다.
    """
    year = year or this_year()
    return [(f"revenue_{y}", f"{y % 100:02d}") for y in range(year - SHOWN, year)
            if f"revenue_{y}" in FIELDS]


def recent_label(year: Optional[int] = None) -> str:
    """`revenue_recent` 의 이름 — `최근 매출액(26년)`. 표 · 창 · 엑셀이 같은 글자다."""
    return f"최근 매출액({(year or this_year()) % 100:02d}년)"


def columns(year: Optional[int] = None) -> List[Tuple[str, str]]:
    """IR 기업 현황 탭이 `소분류` 바로 뒤에 세우는 칸 `[(칸, 머리글)]` — 표와 엑셀의 차례."""
    year = year or this_year()
    return ([(f, f"{yy}년 매출") for f, yy in shown(year)]
            + [("revenue_recent", recent_label(year)), ("funding_total", "누적투자금액"),
               ("raise_target", "투자유치희망금액"), ("pre_value", "Pre Value")])


def roll_over(db: Session, actor_id: int, year: Optional[int] = None) -> int:
    """새해 첫 화면에서 한 번 — 지난해 칸이 빈 기업에 `최근 매출액` 을 옮겨 적는다.

    옮긴 기업 수를 돌려준다. 이미 돈 해 · 2026년 · 칸을 안 판 해면 0.
    """
    year = year or this_year()
    field = f"revenue_{year - 1}"
    if year - 1 < FIRST_RECENT_YEAR or field not in FIELDS:
        return 0
    scope, mark = IrCompany.__tablename__, str(year)
    # 화면마다 부르는 길이라 이미 돈 해는 넣어 보지 않고 물러난다 — 맡는 것은 `_claim` 의 유일 색인.
    if db.scalar(select(MonthlyColumnRun.id).where(
            MonthlyColumnRun.target == TARGET, MonthlyColumnRun.scope == scope,
            MonthlyColumnRun.month == mark)) is not None:
        return 0
    if not _claim(db, TARGET, scope, mark, [field]):
        return 0
    rows = [c for c in db.execute(select(IrCompany)).scalars()
            if not (getattr(c, field) or "").strip() and (c.revenue_recent or "").strip()]
    from . import company_sync   # 그 모듈이 이 파일을 부른다

    token = edit_log.begin(actor_id, "GET", "/companies")
    try:
        for c in rows:
            recent = c.revenue_recent.strip()
            setattr(c, field, amount.phrase(recent) or recent)
        # 저절로 하는 옮겨 적기다 — 이어진 Series A 줄은 빈칸만 채운다(사람이 적은 값을 안 덮는다).
        with company_sync.fill_only(db):
            db.flush()
    finally:
        edit_log.end(token)
    db.commit()
    return len(rows)
