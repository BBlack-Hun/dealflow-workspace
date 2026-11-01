"""IR 미팅 달력 — 딜 진행 관리에 잡힌 미팅을 달·해 단위로 본다(#5).

업무 보고는 같은 미팅을 월간은 목록으로, 연간은 달마다 수로만 보여 준다.
**언제 어느 기업이 어느 투자사를 만났는지·만날지**를 날짜 위에 놓고 보려면
달력이 있어야 했다(10/16 결정).

## 무엇을 싣나

`meetings` 표 하나다. 이 표의 줄은 전부 투자사 담당자(`contact_id`)와
기업(`company_name`) 사이의 IR 미팅이다 — `kind` 는 1차·2차·기타 **차수**일 뿐
다른 종류의 미팅이 아니라 거르지 않는다. 시트에서 들여온 미팅 기록
(`contact_activities` 의 `meeting_*`)은 날짜·기업이 따로 없어 달력에 못 올린다.

날짜는 `scheduled_at`(잡은 날 = 만난 날)이다. **취소한 미팅은 뺀다** — 없던
일이다. 예정·완료는 `status` 그대로 가른다.

업무 보고 › `IR 미팅진행 리스트`(#120)도 같은 줄을 한 줄씩 읽는다(`listing`). 그 화면
아래 `지난 기록` 은 앱 미팅이 생기기 전 명단 월별 `미팅` 칸에 적던 글이다(`memo_rows`).
"""
from __future__ import annotations

from calendar import Calendar
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactColumn, IrCompany, Meeting, SheetOwner, User, VcContact
from . import amount, contact_columns, monthly_columns, pipeline, sheet_owner
from .memo_delivered import _column_month

# 일요일부터 — 벽에 거는 달력 모양이다.
_WEEKS = Calendar(firstweekday=6)


def _rows(db: Session, user_id: Optional[int], start: str, end: str) -> List[Meeting]:
    """`start` ≤ 날짜 < `end` 인 미팅. `user_id` 가 없으면 팀 전체."""
    q = (select(Meeting)
         .where(Meeting.status != "canceled",
                Meeting.scheduled_at >= start, Meeting.scheduled_at < end)
         .order_by(Meeting.scheduled_at, Meeting.scheduled_time, Meeting.id))
    if user_id is not None:
        q = q.where(Meeting.user_id == user_id)
    return list(db.execute(q).scalars().all())


def _month_rows(db: Session, user_id: Optional[int], year: int, mon: int) -> List[Meeting]:
    end = date(year + mon // 12, mon % 12 + 1, 1)
    return _rows(db, user_id, date(year, mon, 1).isoformat(), end.isoformat())


def month(db: Session, user_id: Optional[int], year: int, mon: int,
          today: date) -> dict:
    """한 달 달력 — 주마다 한 줄, 날마다 그날 미팅들."""
    rows = _month_rows(db, user_id, year, mon)
    contacts = pipeline._contact_map(db, [r.contact_id for r in rows])
    # 팀 전체를 볼 때만 **누구 미팅인지** 적는다 — 제 것만 볼 때는 다 제 이름이다.
    owners = (dict(db.execute(select(User.id, User.name)).all())
              if user_id is None else {})

    by_day: Dict[str, List[dict]] = {}
    for r in rows:
        c = contacts.get(r.contact_id)
        by_day.setdefault(r.scheduled_at, []).append({
            "id": r.id,
            "user_id": r.user_id,
            "company": r.company_name or "",
            # 투자사 이름이 비어 있으면 담당자 이름으로 — 칩이 `↔ ` 로 끝나면
            # 누구와의 미팅인지 알 수 없다.
            "firm": ((c.firm or c.name) if c else "-"),
            "who": f"{c.name} {c.title or ''}".strip() if c else "",
            "time": r.scheduled_time or "",
            "kind": pipeline.MEETING_KINDS.get(r.kind, r.kind),
            "done": r.status == "done",
            "outcome": pipeline.OUTCOMES.get(r.outcome or "", ""),
            "owner": owners.get(r.user_id, ""),
        })

    done = sum(1 for r in rows if r.status == "done")
    return {
        "weeks": [[{"date": d, "in_month": d.month == mon, "today": d == today,
                    "meetings": by_day.get(d.isoformat(), [])}
                   for d in week]
                  for week in _WEEKS.monthdatescalendar(year, mon)],
        "done": done,
        "planned": len(rows) - done,
    }


def year(db: Session, user_id: Optional[int], year: int) -> List[dict]:
    """한 해 — 달마다 완료·예정 수."""
    months = [{"month": m, "done": 0, "planned": 0} for m in range(1, 13)]
    for r in _rows(db, user_id, f"{year:04d}-01-01", f"{year + 1:04d}-01-01"):
        # 날짜는 미팅 등록 폼이 `date.fromisoformat` 으로 거른 ISO 값뿐이다.
        months[int(r.scheduled_at[5:7]) - 1]["done" if r.status == "done" else "planned"] += 1
    return months


def listing(db: Session, user_id: Optional[int], year: int, mon: int) -> List[dict]:
    """한 달 미팅 **한 줄 = 한 건** — 예정은 다가오는 차례로 위에, 완료는 최근 차례로 아래에.

    투자유치희망금액은 미팅에 이어 둔 IR 기업(`company_id` — [미팅 잡기] 가 이름으로
    잇는다)의 `raise_target` 이다. 안 이었으면 빈칸 — 이름으로 짐작하지 않는다.
    """
    rows = _month_rows(db, user_id, year, mon)
    rows = [r for r in rows if r.status != "done"] + [r for r in rows if r.status == "done"][::-1]
    contacts = pipeline._contact_map(db, [r.contact_id for r in rows])
    owners = dict(db.execute(select(User.id, User.name)).all())
    targets = dict(db.execute(select(IrCompany.id, IrCompany.raise_target).where(
        IrCompany.id.in_({r.company_id for r in rows if r.company_id} or {0}))).all())
    out = []
    for r in rows:
        c = contacts.get(r.contact_id)
        out.append({
            "date": r.scheduled_at,
            "time": r.scheduled_time or "",
            "owner": owners.get(r.user_id, ""),
            "who": f"{c.name} {c.title or ''}".strip() if c else "-",
            "firm": (c.firm or "") if c else "",
            "company": r.company_name or "",
            "raise_target": amount.phrase(targets.get(r.company_id)) or "",
            "kind": pipeline.MEETING_KINDS.get(r.kind, r.kind),
            "mode": pipeline.MEETING_MODES.get(r.meet_mode or "", ""),
            "done": r.status == "done",
            "status": pipeline.MEETING_STATUS.get(r.status, r.status),
            "outcome": pipeline.OUTCOMES.get(r.outcome or "", ""),
        })
    return out


def memo_rows(db: Session, user_id: Optional[int], year: int, mon: int,
              today: date) -> List[dict]:
    """명단 월별 `미팅` 칸(이름에 `N월` 과 `미팅`, 숨긴 칸 제외)에 적힌 글 — **원문 그대로.**

    읽기만 한다. 글에서 기업·날짜를 뽑지 않는다 — 적는 꼴이 제각각이라 뽑으면 틀린 줄이
    생긴다. 칸의 달 · 값 읽기 · 사람(명단 주인 `SheetOwner.user_id`)은 명단 `전달` 읽기
    (`memo_delivered.entries`, #444)와 같다. `user_id` 를 주면 그 사람 명단만.
    """
    owners = {r.label: r.user_id for r in db.execute(select(SheetOwner)).scalars()}
    by_sheet: Dict[str, List[ContactColumn]] = {}
    for col in db.execute(select(ContactColumn)).scalars():
        if (not col.is_hidden and "미팅" in (col.label or "")
                and monthly_columns.month_of(col.label) is not None
                and _column_month(col, today) == (year, mon)
                and (user_id is None or owners.get(col.sheet) == user_id)):
            by_sheet.setdefault(col.sheet, []).append(col)
    if not by_sheet:
        return []
    names = dict(db.execute(select(User.id, User.name)).all())
    out = []
    for person in db.execute(select(VcContact).where(VcContact.is_hidden == 0,
                                                     VcContact.notes.isnot(None))).scalars():
        notes = contact_columns.load_notes(person.notes)
        for sheet in sheet_owner.labels_of(person.source_sheet):
            for col in by_sheet.get(sheet, []):
                text = notes.get(contact_columns.note_key(col.id), "").strip()
                if text:
                    row = {"owner": names.get(owners.get(sheet), ""), "sheet": sheet,
                           "column": col.label, "firm": person.firm or "",
                           "name": person.name or "", "text": text}
                    out.append(((sheet, col.position, row["firm"], row["name"]), row))
    # 명단 → 칸(명단 화면의 왼→오 차례) → 투자사 → 이름.
    return [row for _key, row in sorted(out, key=lambda x: x[0])]
