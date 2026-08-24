"""딜 진행 관리 — 보낸 뒤에 챙길 일의 건수를 한 군데서 센다.

후속 문구(리마인드)와 IR·미팅은 원래 다른 메뉴였다. 둘 다 딜소개를 보낸 뒤에
생기는 일인데 화면이 갈라져 있어서 매일 두 군데를 열어 봐야 했다. 메뉴를 하나로
합치면서, 탭에 붙일 건수도 한 군데서 세게 한다.

두 화면이 각자 세면 반드시 어긋난다 — 실제로 대시보드와 투자사 관리 현황 가 6명 어긋난
적이 있다. 그래서 여기서도 새로 세지 않고 **이미 있는 서비스가 낸 값**을 옮겨 담는다.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from ..models import User
from . import cadence, pipeline


def counts(db: Session, user: User, today: Optional[date] = None) -> dict:
    """탭에 띄울 건수. 급한 것(warn)과 그냥 잡혀 있는 것을 나눠 준다."""
    today = today or date.today()

    rows = cadence.sequence_rows(db, user.id, today)
    active = [r for r in rows if r["status"] == "active" and r["due"]]
    due = [r for r in active if r["due"] <= today.isoformat()]

    items = pipeline.today_items(db, user, today)
    meetings = pipeline.meeting_rows(db, user)

    return {
        "due": len(due),
        "upcoming": len(active) - len(due),
        "ir_open": len(items["open_requests"]),
        "ir_overdue": len(items["overdue_requests"]),
        # 오늘 약속 — 미팅 탭에서 손이 가는 것
        "meeting_todo": len(items["today_meetings"]),
        "meeting_open": sum(1 for m in meetings if m["status"] == "scheduled"),
        # 미팅 후기 — 끝났는데 아직 결과를 안 물어본 곳. 놓치면 계약을 잊는다.
        "review_due": len(items["due_followups"]),
        "review_open": sum(1 for m in meetings
                           if m["status"] != "scheduled" and not m.get("followup_done")),
    }
