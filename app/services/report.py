"""주간·월간 업무 보고 — 시트에 손으로 적던 것을 기록에서 뽑는다.

원본 시트는 이런 모양이었다.

    6월 미팅 총 4개사
      6월 첫주   미팅 완료 2개사   결과 문의전화 완료
      6월 둘째주 미팅 완료 0개사
      6월 셋째주 6/16 (주)○○ / ○○PE   6/26 결과 문의 : …

미팅을 하고 나서 사람이 다시 시트에 옮겨 적고 있었다. 이제 미팅을 기록하면
같은 표가 저절로 나온다 — 옮겨 적는 사이에 빠지는 건이 없어진다.

**결과 문의(미팅 후 열흘)를 했는지**를 함께 센다. 원본 시트에도
"결과확인전화가 없으면 계약을 잊어버리는 경우가 발생할 수 있습니다" 라고
적혀 있었다. 그게 이 보고의 목적이다.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IrRequest, Meeting, User, VcContact
from .pipeline import MEETING_KINDS, OUTCOMES

WEEK_NAMES = ["첫주", "둘째주", "셋째주", "넷째주", "다섯째주", "여섯째주"]


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def week_of_month(day: date) -> int:
    """그 달의 몇 번째 주인가 (1부터). 1일이 낀 주가 첫주다."""
    first_weekday = date(day.year, day.month, 1).weekday()
    return (day.day + first_weekday - 1) // 7 + 1


def month_range(year: int, month: int) -> tuple:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def monthly(db: Session, year: int, month: int,
            user: Optional[User] = None, today: Optional[date] = None) -> dict:
    """한 달치 보고. `user` 를 주면 그 사람 것만, 없으면 팀 전체."""
    today = today or date.today()
    start, end = month_range(year, month)

    stmt = select(Meeting).where(Meeting.scheduled_at >= start.isoformat(),
                                 Meeting.scheduled_at <= end.isoformat())
    if user is not None:
        stmt = stmt.where(Meeting.user_id == user.id)
    meetings = db.execute(stmt.order_by(Meeting.scheduled_at)).scalars().all()

    contacts = {
        c.id: c for c in db.execute(
            select(VcContact).where(
                VcContact.id.in_([m.contact_id for m in meetings] or [0]))
        ).scalars().all()
    }
    owners = {u.id: u.name for u in db.execute(select(User)).scalars().all()}

    weeks: Dict[int, List[dict]] = {}
    for meeting in meetings:
        when = _as_date(meeting.scheduled_at)
        if when is None:
            continue
        contact = contacts.get(meeting.contact_id)
        due = _as_date(meeting.followup_due)
        weeks.setdefault(week_of_month(when), []).append({
            "date": meeting.scheduled_at,
            "name": contact.name if contact else "-",
            "firm": (contact.firm or "") if contact else "",
            "company": meeting.company_name or "",
            "kind": MEETING_KINDS.get(meeting.kind, meeting.kind),
            "status": meeting.status,
            "outcome": OUTCOMES.get(meeting.outcome or "", ""),
            "owner": owners.get(meeting.user_id, ""),
            "followup_due": meeting.followup_due or "",
            "followup_done": bool(meeting.followup_done),
            # 열흘이 지났는데 아직 안 물어봤다 — 이 보고가 잡아내야 할 것.
            "followup_late": bool(
                meeting.status == "done" and not meeting.followup_done
                and due is not None and due <= today),
        })

    done = [m for m in meetings if m.status == "done"]
    rows = [
        {"week": w, "label": f"{month}월 {WEEK_NAMES[w - 1] if w <= len(WEEK_NAMES) else f'{w}주'}",
         "items": sorted(items, key=lambda x: x["date"]),
         "done": sum(1 for x in items if x["status"] == "done")}
        for w, items in sorted(weeks.items())
    ]

    # IR 요청도 같은 달로 함께 센다 — 미팅만으로는 그 달의 반응이 안 보인다.
    ir_stmt = select(IrRequest).where(IrRequest.requested_at >= start.isoformat(),
                                      IrRequest.requested_at <= end.isoformat())
    if user is not None:
        ir_stmt = ir_stmt.where(IrRequest.user_id == user.id)
    requests = db.execute(ir_stmt).scalars().all()

    outcome_counts = {}
    for meeting in done:
        label = OUTCOMES.get(meeting.outcome or "", "결과 미정")
        outcome_counts[label] = outcome_counts.get(label, 0) + 1

    return {
        "year": year,
        "month": month,
        "weeks": rows,
        "total": len(meetings),
        "done": len(done),
        "canceled": sum(1 for m in meetings if m.status == "canceled"),
        "followup_done": sum(1 for m in done if m.followup_done),
        "followup_late": sum(
            1 for w in rows for x in w["items"] if x["followup_late"]),
        "outcomes": sorted(outcome_counts.items(), key=lambda t: -t[1]),
        "ir_requested": len(requests),
        "ir_delivered": sum(1 for r in requests if r.status == "delivered"),
        "ir_open": sum(1 for r in requests if r.status == "open"),
    }


def recent_months(today: Optional[date] = None, count: int = 6) -> List[tuple]:
    """최근 달들 (연, 월). 화면의 달 고르기에 쓴다."""
    today = today or date.today()
    out = []
    year, month = today.year, today.month
    for _ in range(count):
        out.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out
