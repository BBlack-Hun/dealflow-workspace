"""달마다 늘어나는 칸을 **월 초에 저절로** 세운다.

두 표가 같은 모양을 쓴다.

    ConsultingColumn   투자컨설턴트      `8월 마지막주 리마인드 톡 or TEL`
    ContactColumn      투자사 관리 현황   `7월 리마인드 문자 (7/28)` · `7월 리마인드 TEL`

지금까지는 사람이 [칸 추가] 를 눌러야 했다. 누르는 것을 잊으면 그 달 통화 기록이
**지난달 칸에 섞여 들어간다** — 나중에 어느 달 것인지 가릴 방법이 없다.

## 언제 도는가 — 요청이 들어올 때

이 앱에는 예약 실행 장치가 없다(크론도, 워커도, 스케줄러도). 새로 들이면 배포와
감시 대상이 하나 더 늘고, 그것이 죽어 있는 것은 아무도 모른다. 대신 이 저장소가
이미 쓰는 방식을 따른다 — **화면을 열 때 그 달 것이 없으면 만든다.**
주간 업무가 그렇게 돈다(`services/weekly.py` 의 `fill_week`).

값이 늦게 생기는 것이 문제가 되지 않는 일이라 가능하다. 아무도 그 표를 열지
않은 달의 칸은 없어도 되고, 여는 순간 생긴다.

## 이름을 어떻게 짓는가 — 직전 칸을 본떠서

칸 이름이 명단마다 다르다(`8월 마지막주 리마인드 톡 or TEL` 과 `7월 리마인드
문자`). 코드가 형식을 정해 버리면 시트와 글자가 달라져 나란히 놓고 대조할 수가
없다. 그래서 **그 표의 가장 최근 칸에서 달 숫자만 바꾼다.** 이름을 짓는 것은
코드가 아니라 그 표를 쓰던 사람이다.

본이 없으면(칸이 하나도 없으면) 만들지 않는다 — 어떻게 부르는 표인지 알 수 없다.

괄호 안 날짜(`(7/28)`)는 떼고 옮긴다. 그것은 실제로 그날 보냈다는 기록이라,
다음 달로 그대로 옮겨 적으면 **일어나지 않은 날짜를 앱이 지어내는** 것이 된다.

괄호를 안 친 날짜(`8월 딜소개 8/5 8/12 8/19`)도 같은 기록이다. 다만 **그 칸의
달과 숫자가 같을 때만** 뗀다 — 아무 `M/D` 나 떼면 `8월 성공보수 1/2 조건` 의
`1/2` 를 날짜로 오인해 시트에 있던 글자를 지운다. 달이 맞을 때만 "그 달에 보낸
날" 이라는 원래 뜻과 정확히 겹친다. 괄호를 쳤으면 날짜인 것이 이미 분명하니
그쪽은 지금처럼 달과 무관하게 뗀다.

같은 달 칸이 여럿인 표(`7월 리마인드 문자` · `7월 리마인드 TEL` · `7월 카톡
연결`)는 그 세 칸을 **다 같이** 만든다. 하나만 만들면 나머지 두 기록이 갈 곳이 없다.

## 어느 칸을 본으로 삼는가 — 오늘에서 거꾸로 세어 가장 가까운 달

**위치로는 못 정한다.** 지금까지는 맨 앞(왼쪽) 칸이 그 표의 최근 달이라고 봤는데,
운영에 두 방향이 다 있었다(2026-09-01 실측 · 그날 이 둘만 9월 칸이 안 섰다).

    스타트업(40)     7월 → 7월 → 8월 → 8월           오름차순
    전체 딜소개현황   7월 → 6월 → 5월 → 4월 → … → 8월   내림차순 + 뒤에 합쳐진 탭

게다가 두 명단 다 맨 앞이 `투자유치 진행 여부` · `1차 딜소개` 처럼 **달과 무관한
고정 칸**이었다. 맨 앞 칸만 보고 "달이 안 적혀 있으니 본뜰 수 없다" 로 물러나,
뒤에 멀쩡한 월별 칸이 여덟·열두 개 있어도 안 봤다.

`max(달)` 도 아니다. 칸 이름에 **연도가 없어서** 해가 바뀌면 12월에 얼어붙는다 —
1월·2월·3월이 모두 지난해 12월을 본뜬다.

그래서 **오늘 달에서 거꾸로 세어 가장 먼저 만나는 달**을 최근으로 본다
(`(오늘 - 그 달) % 12`). 연도가 이름에 없어도 **오늘**이라는 기준은 있고, 그
기준은 12월 다음이 1월인 것을 그대로 안다. 달을 못 읽는 칸은 본을 고르는 데
끼지 않는다 — 그 표의 고정 칸이지 어느 달인지를 가리키는 표시가 아니다.

달을 적은 칸이 **하나도** 없는 표(담당자별 스타트업 명단이 그렇다)에는 여전히
만들지 않는다. 거기까지 만들기 시작하면 달을 안 쓰는 표에 달 칸이 생긴다.

## 두 번 만들지 않는 것 · 지운 칸을 되살리지 않는 것

둘 다 칸을 세어서는 막을 수 없다.

  · 화면 두 개를 동시에 열면 양쪽이 "없네" 라고 보고 각각 만든다.
  · 사람이 지운 칸은 다음 요청에서 "없으니 만들자" 로 그대로 되살아난다.

그래서 칸이 아니라 **만들었다는 사실**(`MonthlyColumnRun`)을 남기고 그것을 본다.
`(target, scope, month)` 에 유일 색인이 걸려 있어, 동시에 들어온 요청 중 하나만
줄을 넣는 데 성공한다. 나머지는 IntegrityError 로 조용히 물러난다 — 세어 보고
넣는(check-then-insert) 방식은 두 요청이 같은 순간에 세면 둘 다 통과한다.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..models import ConsultingColumn, ContactColumn, MonthlyColumnRun

# `MonthlyColumnRun.target` 값. 표를 늘리려면 여기 한 줄과 아래 감싸는 함수 하나다.
CONSULTING = "consulting"
CONTACT = "contact"

# `8월` · `12 월` — 칸 이름 안의 달.
_MONTH = re.compile(r"(\d{1,2})\s*월")
# `(7/28)` — 그 달에 **실제로 보낸 날**. 다음 달로 옮겨 적을 수 없는 값이다.
_DATE_PAREN = re.compile(r"\s*\(\s*\d{1,2}\s*/\s*\d{1,2}\s*\)")
# 괄호 없는 `8/5` — 날짜일 **수도** 있는 토막. 뗄지는 달을 보고 정한다(`relabel`).
# 앞뒤가 글자나 숫자에 **붙어 있으면** 날짜가 아니라 다른 말의 일부다
# (`3/4분기` · `2026/8/19`). 통째로 남긴다 — 반쪽만 떼면 `4월분기` 처럼 남은
# 조각이 옆 글자에 들러붙어, 시트에 없던 말이 된다.
_DATE_BARE = re.compile(r"\s*(?<![\w/])(\d{1,2})\s*/\s*\d{1,2}(?![\w/])")


def month_of(label: str) -> Optional[int]:
    """칸 이름이 가리키는 달. 없거나 1~12 밖이면 None."""
    m = _MONTH.search(label or "")
    if not m:
        return None
    value = int(m.group(1))
    return value if 1 <= value <= 12 else None


def relabel(label: str, month: int) -> str:
    """`7월 리마인드 문자 (7/28)` + 8 → `8월 리마인드 문자`.

    달 숫자만 바꾼다. 이름을 새로 짓지 않는 이유는 위 모듈 설명 참고 —
    시트와 글자가 달라지면 나란히 놓고 대조할 수가 없다.

    이름에 달이 두 번 적혀 있으면 둘 다 바꾼다. 한쪽만 바꾸면 `8월 … 7월 …`
    처럼 **어느 달인지 이름 안에서 갈리는** 칸이 된다.

    보낸 날은 떼고 옮긴다 — `8월 딜소개 8/5 8/12 8/19` + 9 → `9월 딜소개`.
    """
    out = _DATE_PAREN.sub("", label or "")
    # 괄호 없는 토막은 **그 칸의 달과 숫자가 같을 때만** 날짜로 본다. 달을 못
    # 읽는 이름은 대조할 것이 없으니 손대지 않는다 — 지우는 쪽이 더 나쁘다.
    was = month_of(out)
    if was is not None:
        out = _DATE_BARE.sub(
            lambda m: "" if int(m.group(1)) == was else m.group(0), out)
    out = _MONTH.sub(f"{month}월", out)
    # 안쪽 공백은 손대지 않는다 — 시트 이름에 두 칸짜리 공백이 그대로 들어
    # 있는 칸이 있고(`리마인드 카톡  or  TEL`), 고르면 시트와 글자가 달라진다.
    return out.strip()


def latest_month(months: Sequence[Optional[int]],
                 month: int) -> Optional[int]:
    """이 표에서 **가장 최근** 달. 달을 읽을 수 있는 칸이 없으면 None.

    `month` 에서 **거꾸로 세어 가장 먼저 만나는 달**이다. 왜 이 기준인지는 위
    모듈 설명 참고 — 위치는 운영에 오름차순·내림차순이 다 있어 못 쓰고,
    `max(달)` 은 이름에 연도가 없어 해가 바뀌면 12월에 얼어붙는다.

    거꾸로 세는 것이라 12월 다음이 1월인 것을 그대로 안다: 1월에 12월 칸은 한
    달 전(`(1 - 12) % 12 == 1`)이고, 2월에 12월 칸은 두 달 전이다.

    앞질러 만들어 둔 다음 달 칸(9월에 서 있는 `10월`)은 열한 달 전으로 세어져
    본이 되지 않는다. **아직 오지 않은 달**을 본뜨는 것보다 그쪽이 맞다.

    거리가 같은 두 달은 없다 — 서로 다른 달 숫자는 나머지도 서로 다르다.
    """
    seen = [m for m in months if m is not None]
    if not seen:
        return None
    return min(seen, key=lambda m: (month - m) % 12)


def plan(labels: Sequence[str], month: int) -> List[str]:
    """이 표에 이번 달 칸을 세운다면 어떤 이름이 되는가. 셀 것이 없으면 빈 목록.

    `labels` 는 화면에 서는 순서(`position`)다. **그 순서는 어느 칸이 최근인지
    말해 주지 않는다** — 본뜰 달은 `latest_month` 가 달을 보고 정한다.
    """
    months = [month_of(x) for x in labels]
    if not labels or month in months:
        # 이미 있으면 그만이다. 해가 바뀌어 같은 달 숫자가 다시 와도 만들지
        # 않는다 — 칸 이름에 연도가 없어서, 만들면 `8월` 두 칸이 나란히 서고
        # 어느 해 것인지 이름으로 가릴 수가 없다. 그때는 사람이 정리할 일이다.
        return []
    head = latest_month(months, month)
    if head is None:
        # 달을 적은 칸이 하나도 없다 — 달을 안 쓰는 표다. 여기에 달 칸을
        # 만들면 그 표를 쓰던 사람이 지워야 한다.
        return []
    # 같은 달 칸이 여럿인 표가 있다(문자 · TEL · 카톡 연결). 다 같이 만든다.
    # 세우는 차례는 **화면에 서 있던 순서 그대로**다 — 본이 된 칸들이 나란히
    # 서 있던 차례가 그 표를 쓰는 사람이 일하는 차례다.
    return [relabel(x, month) for x, m in zip(labels, months) if m == head]


def _claim(db: Session, target: str, scope: str, month: str,
           labels: List[str]) -> bool:
    """이 달 몫을 내가 맡는다. 이미 누가 맡았으면 False.

    유일 색인이 판정한다 — 세어 보고 넣으면 동시에 들어온 두 요청이 둘 다
    "없네" 를 보고 둘 다 넣는다. 저장점(SAVEPOINT) 안에서 넣는 것은, 실패했을
    때 **부르는 쪽이 하던 일까지 되돌리지 않기** 위해서다.
    """
    try:
        with db.begin_nested():
            db.add(MonthlyColumnRun(
                target=target, scope=scope, month=month,
                labels=json.dumps(labels, ensure_ascii=False)))
    except IntegrityError:
        return False
    return True


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _ensure(db: Session, target: str, scope: str, columns: Sequence,
            today: Optional[date] = None) -> List[str]:
    """(공통) 이번 달 칸을 세우고 만든 이름을 돌려준다.

    `columns` 는 그 표의 칸을 **화면 순서 그대로**(`position`) 준다. 그 순서가
    달 순서라는 보장은 없다 — 본뜰 달은 `plan` 이 달을 보고 고른다.

    새 칸은 맨 앞에 선다 — 지금 챙겨야 할 달이 먼저 보여야 하고, 사람이 [칸
    추가] 로 넣을 때와 같은 자리여야 한다.
    """
    day = today or clock.today()
    labels = plan([c.label for c in columns], day.month)
    if not labels:
        return []
    if not _claim(db, target, scope, _month_key(day), labels):
        return []       # 다른 요청이 먼저 맡았다 · 또는 사람이 지운 달이다
    for col in columns:
        col.position += len(labels)
    return labels


def ensure_consulting(db: Session, user_id: Optional[int], sheet: str,
                      today: Optional[date] = None) -> List[str]:
    """투자컨설턴트의 이번 달 칸. 칸이 **사람마다·탭마다**라 둘을 같이 본다.

    주인 없는 줄(`user_id` 가 비어 있는 것)은 배정 전이라 건드리지 않는다 —
    누구의 표가 될지 모르는 칸을 미리 만들면 배정한 사람이 지워야 한다.
    """
    if not user_id or not sheet:
        return []
    columns = db.execute(
        select(ConsultingColumn)
        .where(ConsultingColumn.user_id == user_id,
               ConsultingColumn.sheet == sheet)
        .order_by(ConsultingColumn.position, ConsultingColumn.id)
    ).scalars().all()
    labels = _ensure(db, CONSULTING, f"{user_id}:{sheet}", columns, today)
    for pos, label in enumerate(labels):
        db.add(ConsultingColumn(user_id=user_id, sheet=sheet,
                                label=label, position=pos))
    if labels:
        db.commit()
    return labels


def ensure_contact(db: Session, sheet: str,
                   today: Optional[date] = None) -> List[str]:
    """투자사 관리 현황 명단의 이번 달 칸. 칸이 **명단마다**다.

    여기서 칸을 정하는 것은 올린 사람이 아니라 원본 시트이고, 명단은 담당이
    바뀌어도 같은 명단이다(`services/contact_columns.py` 참고).
    """
    if not sheet:
        return []
    columns = db.execute(
        select(ContactColumn)
        .where(ContactColumn.sheet == sheet)
        .order_by(ContactColumn.position, ContactColumn.id)
    ).scalars().all()
    labels = _ensure(db, CONTACT, sheet, columns, today)
    for pos, label in enumerate(labels):
        db.add(ContactColumn(sheet=sheet, label=label, position=pos))
    if labels:
        db.commit()
    return labels
