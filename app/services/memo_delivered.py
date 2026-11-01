"""IR 요청 칸 메모의 `전달` → 업무 보고 `IR 자료 전달함` 수.

## 왜 만드나

투자사 딜공유 명단의 월별 `N월 IR 요청` 칸에 사람이 `8/5 샘플가 전달` 처럼 적는다.
그 글은 `VcContact.notes` 의 글일 뿐이라 업무 보고(`ir_requests` 만 센다)에 안
잡혔다 — 팀 피드백: "자료는 전달했으나 그 뒤 피드백이 없거나 미팅 없이 드랍된 건이
체크되지 않는다". 셀 수 없으면 그 뒤를 챙길 수도 없다.

## 쓰지 않는다 — 보고가 열릴 때 읽는다

`memo_intro`(딜소개 메모)처럼 활동 이력 줄로 옮기지 않는다. 표도 이주도 없고,
메모를 고치면 다음에 열 때 그대로 따라온다. 칸을 고르는 법(이름에 `N월`, 숨긴 칸
제외)과 칸 값 읽기(`contact_columns.load_notes`)는 `memo_intro` 와 같다.

## 읽는 규칙 — `ir-sent-contract` 스킬의 시트 이력 규칙과 같다

- 회차 가르기: `company_names.rounds`(시트 가져오기 · `memo_intro` 와 같은 함수).
- 옛 꼴 `8/5 샘플가 전달, 샘플나 전달`: 단계 기호(`→` `->`)·`/`·쉼표로 잘라
  **`전달` 이 붙은 조각의 기업만** 센다. 기업은 그 조각에서 `전달` 앞 글이다.
- 새 꼴 `[전달] 샘플가, 샘플나`: 태그 뒤부터 다음 단계 기호·태그까지가 전달한 기업이다.
  `[전달]` 뒤가 비면 바로 앞 조각의 기업(`[요청] 샘플가 → [전달]`). `[요청]` 만 있는
  조각은 안 센다.
- `미전달` · `전달 예정` 처럼 안 보냈다는 말은 안 센다.
- 기업을 못 읽은 회차는 **회차 하나를 1건**으로 센다(`unnamed` 로 따로 밝힌다).
- shortcut: 번호로 지목한 `2번 전달` 은 번호 기업을 고르지 않고 못 읽은 회차로 센다
  (2026-11 운영 0건). 쓰이기 시작하면 앞 조각의 번호 목록에서 고른다.

## 달 · 사람 · 겹침

- 달: 글 앞 날짜의 달, 없으면 칸의 달. 운영(2026-11)에서 둘이 다른 줄은 11/200줄로
  모두 칸 다음 달 — 요청받은 달 칸에 다음 달 전달일을 적은 것이다.
- 사람: 칸이 든 명단의 주인(`SheetOwner.user_id`).
- 겹침: 같은 달 · 같은 사람(투자사+이름 — `ir_no_meeting._person`) · 같은 기업(비교키가
  같거나 한쪽이 다른 쪽을 품음)인 앱 전달 기록이 있으면 명단 쪽을 뺀다. 앱 기록의 달은
  요청한 달과 전달한 달 둘 다 본다.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactColumn, IrRequest, SheetOwner, VcContact
from . import company_names as cn
from . import contact_columns, monthly_columns, sheet_owner
from .ir_monthly import _key
from .ir_no_meeting import _person

_TAG = re.compile(r"\[\s*(전달|요청)\s*\]")
#: 단계 기호와, 태그 **앞**(태그가 새 조각을 연다).
_STEP = re.compile(r"→|->|(?=\[\s*(?:전달|요청)\s*\])")
_LIST = re.compile(r"[/,;、]")
_NOT_SENT = re.compile(r"미\s*전달|전달\s*(?:예정|전(?!화)|[xX]|안\s*[함했됨]|못|불가)")
#: 기업 이름 자리에 붙는 말 — `샘플가 IR 전달` · `샘플가IR자료전달`.
_FILLER = re.compile(r"(?<![A-Za-z])IR(?![A-Za-z])|자료", re.I)
_NUMBER_ONLY = re.compile(r"\d+\s*번")


def _names(text: str) -> List[str]:
    text = _FILLER.sub(" ", _TAG.sub(" ", text))
    # 한 글자 조각은 버린다 — 날짜 바로 뒤 `(주)` 는 `rounds` 가 여는 괄호를 떼어 `주` 가 남는다.
    return [n for n in cn.split(text).names
            if len(n) > 1 and not _NUMBER_ONLY.fullmatch(n)]


def parse(text: str) -> List[Tuple[Optional[Tuple[int, int]], List[str]]]:
    """칸 글 → `전달` 이 든 회차마다 `((월, 일) 또는 None, 기업들)`. 못 읽으면 기업이 빈 목록."""
    out = []
    for chunk in cn.rounds(text):
        body = _NOT_SENT.sub(" ", chunk.content)
        if "전달" not in body:
            continue
        names: List[str] = []
        prev: List[str] = []
        for step in _STEP.split(body):
            step = step.strip()
            tag = _TAG.match(step)
            if tag:
                got = _names(step[tag.end():])
                if tag.group(1) == "전달":
                    names += got or prev
            else:
                got = _names(step)
                for seg in _LIST.split(step):
                    for before in seg.split("전달")[:-1]:
                        names += _names(before)
            prev = got or prev
        out.append(((chunk.month, chunk.day) if chunk.dated else None,
                    list(dict.fromkeys(names))))
    return out


def target_columns(columns) -> list:
    """읽을 칸 — 이름에 `N월` 과 `IR요청` 이 든 칸(숨긴 칸 · `IR 요청기업 미팅 안내전화` 제외)."""
    out = []
    for c in columns:
        label = (c.label or "").replace(" ", "")
        if (not c.is_hidden and monthly_columns.month_of(c.label) is not None
                and "IR요청" in label and "IR요청기업" not in label):
            out.append(c)
    return out


def _column_month(col: ContactColumn, today: date) -> Tuple[int, int]:
    """칸의 (해, 달). 칸에 해가 없으면 오늘에서 거꾸로 가장 가까운 그 달."""
    if col.month and col.month[:4].isdigit():
        return int(col.month[:4]), int(col.month[5:7])
    mon = monthly_columns.month_of(col.label)
    return (today.year if mon <= today.month else today.year - 1), mon


def _day_month(day: Tuple[int, int], col: Tuple[int, int]) -> str:
    """글 앞 날짜의 `YYYY-MM` — 해는 칸의 달에 가장 가까운 해(12월 칸의 `1/5` 는 다음 해)."""
    year = min((col[0] - 1, col[0], col[0] + 1),
               key=lambda y: abs((y * 12 + day[0]) - (col[0] * 12 + col[1])))
    return f"{year:04d}-{day[0]:02d}"


def _same_company(a: str, b: str) -> bool:
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 2 and (a in b or b in a)))


def entries(db: Session, today: date) -> List[dict]:
    """명단 칸에서 읽은 전달 **전부** — `{owner, contact_id, person, month, company}`.

    `company` 가 빈 글자면 기업을 못 읽은 회차다. 같은 사람 · 달 · 기업은 한 번만 싣는다
    (두 칸이나 두 명단에 같은 일을 적었다).
    """
    owners = {r.label: r.user_id for r in db.execute(select(SheetOwner)).scalars()}
    cols = target_columns(db.execute(select(ContactColumn)).scalars().all())
    by_sheet: Dict[str, list] = {}
    for col in cols:
        by_sheet.setdefault(col.sheet, []).append(col)
    if not by_sheet:
        return []
    out, seen = [], set()
    for person in db.execute(select(VcContact).where(VcContact.is_hidden == 0,
                                                     VcContact.notes.isnot(None))).scalars():
        sheets = [s for s in sheet_owner.labels_of(person.source_sheet) if s in by_sheet]
        if not sheets:
            continue
        notes = contact_columns.load_notes(person.notes)
        who = _person(person)
        for sheet in sheets:
            for col in by_sheet[sheet]:
                text = notes.get(contact_columns.note_key(col.id), "")
                if "전달" not in text:
                    continue
                col_month = _column_month(col, today)
                for line, (day, names) in enumerate(parse(text)):
                    month = (_day_month(day, col_month) if day
                             else f"{col_month[0]:04d}-{col_month[1]:02d}")
                    for name in names or [""]:
                        key = (who, month, _key(name) or f"#{col.id}:{line}")
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append({"owner": owners.get(sheet), "contact_id": person.id,
                                    "person": who, "month": month, "company": name})
    return out


def app_delivered(db: Session) -> Dict[tuple, List[str]]:
    """앱의 전달 기록 — `{(사람, 달): [기업 비교키…]}`. 달은 요청한 달과 전달한 달 둘 다."""
    out: Dict[tuple, List[str]] = {}
    for req, contact in db.execute(
            select(IrRequest, VcContact).join(VcContact, VcContact.id == IrRequest.contact_id)
            .where(IrRequest.status == "delivered")).all():
        who = _person(contact)
        for when in {(req.requested_at or "")[:7], (req.delivered_at or "")[:7]} - {""}:
            out.setdefault((who, when), []).append(_key(req.company_name))
    return out


def month_count(db: Session, year: int, month: int, user_id: Optional[int],
                today: date, rows: Optional[List[dict]] = None,
                app: Optional[Dict[tuple, List[str]]] = None) -> dict:
    """그 달 명단 기록 전달 수 — 앱 기록과 겹치는 것은 뺀다. `{count, unnamed, overlap}`.

    `user_id` 를 주면 그 사람 **명단**의 것만(명단 주인으로 센다). 연간 보고는 `rows` ·
    `app` 을 한 번 읽어 열두 달에 넘긴다.
    """
    rows = entries(db, today) if rows is None else rows
    app = app_delivered(db) if app is None else app
    want = f"{year:04d}-{month:02d}"
    count = unnamed = overlap = 0
    for row in rows:
        if row["month"] != want or (user_id is not None and row["owner"] != user_id):
            continue
        if not row["company"]:
            unnamed += 1
        elif any(_same_company(_key(row["company"]), k)
                 for k in app.get((row["person"], want), [])):
            overlap += 1
            continue
        count += 1
    return {"count": count, "unnamed": unnamed, "overlap": overlap}
