"""투자컨설턴트 현황의 **탭이 정해지는 한 곳**.

탭 셋은 `SHEETS = ["스타트업", …]` 처럼 코드에 박힌 목록이었다. 그래서

  · **이름을 고치려면 배포를 해야 했다.** 실제로 한 번 고쳤는데(`중요 스타트업`
    → `스타트업`) 이름만 바꾸니 이미 들어간 줄이 옛 이름의 유령 탭으로 갈라져,
    자료를 옮기는 마이그레이션을 따로 써야 했다(0039).
  · **표 모양의 짝을 이름으로 맞추고 있었다.** `월간 계약 업무현황표` 만 칸이
    다른데(`routers/consulting.py` 의 `CONTRACT_COLUMNS`) 그 짝이 이름이라,
    이름을 고칠 수 있게 하는 순간 **탭 이름 한 글자에 계약 표가 일반 표로
    돌아간다.** 화면은 멀쩡하고 `계약월`·`성공보수율` 칸만 조용히 사라진다.

그래서 이름을 값으로 빼되(`ConsultingSheet.label`) **바뀌지 않는 열쇠**를 따로
둔다(`ConsultingSheet.kind`). 표 모양·기본 탭·계약 탭 판정은 전부 열쇠로 하고,
이름은 화면 글자로만 쓴다. `SheetOwner.layout`·`is_hidden`·`is_deal_list` 로
옮긴 것과 같은 방식이다 — 이 저장소가 반복해 당한 유형이라 값으로 둔다.

## 탭은 팀 공용이다

셋은 팀이 함께 쓰는 업무 단계라(스타트업 → 경영본부 전달 → 계약), 새 컨설턴트도
**같은 탭 셋**을 그대로 받아야 한다. 사람마다 이름을 따로 두면 관리자가 팀
전체를 볼 때 같은 탭이 여러 이름으로 갈라져 보인다.

## 이름을 바꾸면 줄이 따라간다

`ConsultingCompany.sheet` 와 `ConsultingColumn.sheet` 는 **이름을 그대로** 담고
있다. 이름만 바꾸고 그 줄들을 안 옮기면 그 사람들이 어느 탭에도 안 뜬다 —
0039 가 고쳐야 했던 바로 그 사고다. `rename()` 이 한 번에 같이 옮긴다.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ConsultingColumn, ConsultingCompany, ConsultingSheet

# ── 바뀌지 않는 열쇠 ────────────────────────────────────────────────────────
#
# **화면에 보이지 않는다.** 사람이 보는 것은 `label` 뿐이고, 코드가 짝을 맞출
# 때만 이 값을 읽는다. 그래서 이름을 아무리 고쳐도 표 모양이 안 흔들린다.
STARTUP = "startup"
HANDOVER = "handover"
CONTRACT = "contract"

# 처음 세우는 탭 셋 — (열쇠, 처음 이름). **이름은 초깃값일 뿐**이고, 한 번
# 세운 뒤에는 화면에서 고친 값이 이긴다(`ensure` 가 덮지 않는다).
#
# 이름을 여기 적어 두는 것은 하드코딩이 아니다. 아무것도 없는 DB 에 무엇을
# 세울지는 어딘가 적혀 있어야 하고, 그 뒤로는 이 값을 아무도 안 읽는다.
DEFAULTS: List[tuple] = [
    (STARTUP, "스타트업"),
    (HANDOVER, "경영본부 전달 기업"),
    (CONTRACT, "월간 계약 업무현황표"),
]

# 첫 화면에서 여는 탭. 탭이 지워질 수 있는 자리가 아니라 늘 있다.
DEFAULT_KIND = STARTUP


def ensure(db: Session) -> List[ConsultingSheet]:
    """탭 셋이 있는지 보고, 없으면 세운다. **이미 있으면 손대지 않는다.**

    화면을 열 때마다 부른다 — 예약 실행 장치가 없는 앱이라 "새 컨설턴트가
    처음 들어온 순간" 을 알아챌 자리가 요청뿐이다(월별 칸이 같은 방식이다,
    `services/monthly_columns.py`).

    **이름을 덮지 않는 것이 중요하다.** 덮으면 화면에서 고친 이름이 다음
    요청에 원래대로 돌아가고, 고친 사람은 저장이 안 된 줄 안다.
    """
    rows = {r.kind: r for r in db.execute(select(ConsultingSheet)).scalars()}
    made = False
    for pos, (kind, label) in enumerate(DEFAULTS):
        if kind in rows:
            continue
        db.add(ConsultingSheet(kind=kind, label=label, position=pos))
        made = True
    if made:
        # **바로 커밋한다.** 탭을 세우는 것은 요청이 하려던 일과 상관없는
        # 독립된 사실이고, 열어 둔 채로 두면 SQLite 에서 쓰기 잠금을 물고 있어
        # 같은 순간의 다른 요청이 `database is locked` 로 떨어진다.
        # 월별 칸이 같은 이유로 같은 자리에서 커밋한다
        # (`services/monthly_columns.py` 의 `_ensure`).
        db.commit()
    return all_sheets(db)


def all_sheets(db: Session) -> List[ConsultingSheet]:
    """탭 순서 그대로."""
    return list(db.execute(
        select(ConsultingSheet).order_by(ConsultingSheet.position,
                                         ConsultingSheet.id)
    ).scalars().all())


def labels(db: Session) -> List[str]:
    """지금 탭 이름들. 줄이 어느 탭에 붙는지 견주는 데 쓴다."""
    return [s.label for s in ensure(db)]


def default_label(db: Session) -> str:
    """아무 탭도 안 고른 채 들어왔을 때 열 탭의 이름."""
    rows = {s.kind: s.label for s in ensure(db)}
    # 열쇠가 있는 탭이 없으면 첫 탭이라도 연다 — 빈 화면보다 낫다.
    return rows.get(DEFAULT_KIND) or (labels(db) or [""])[0]


def kind_of(db: Session, label: str) -> str:
    """이 이름의 탭이 **어떤 탭인가**. 모르는 이름이면 빈 값.

    사람이 시트를 올려 만든 탭은 여기 없다 — 그 탭들은 지금까지의 표를 쓴다.
    """
    for sheet in ensure(db):
        if sheet.label == label:
            return sheet.kind
    return ""


def by_kind(db: Session) -> Dict[str, ConsultingSheet]:
    return {s.kind: s for s in ensure(db)}


def rename(db: Session, kind: str, label: str) -> Optional[ConsultingSheet]:
    """탭 이름을 바꾸고 **그 탭의 줄들을 같이 옮긴다.**

    `ConsultingCompany.sheet` 와 `ConsultingColumn.sheet` 가 이름을 그대로 담고
    있어서, 이름만 바꾸면 그 줄들이 **어느 탭에도 안 뜬다** — 옛 이름의 유령
    탭으로 갈라진다. 0039 마이그레이션이 고쳐야 했던 사고가 정확히 그것이다.

    빈 이름은 받지 않는다. 이름 없는 탭은 누를 자리가 없어진다.
    이미 다른 탭이 쓰는 이름도 받지 않는다 — 두 탭이 같은 이름이면 줄이 어느
    쪽 것인지 알 수 없고, 옮기는 순간 두 탭의 줄이 섞인다.
    """
    after = (label or "").strip()[:80]
    rows = by_kind(db)
    sheet = rows.get(kind)
    if sheet is None or not after or after == sheet.label:
        return sheet
    if any(s.label == after for s in rows.values() if s.kind != kind):
        return None

    before = sheet.label
    for company in db.execute(
        select(ConsultingCompany).where(ConsultingCompany.sheet == before)
    ).scalars():
        company.sheet = after
    for column in db.execute(
        select(ConsultingColumn).where(ConsultingColumn.sheet == before)
    ).scalars():
        column.sheet = after
    sheet.label = after
    db.flush()
    return sheet
