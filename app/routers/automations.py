"""2단계 자동화 — 팀원이 손대는 자리(관리자 판은 팀 현황에 있다).

지금은 하나다: **미팅 요청 나갈 곳**(`/automations/meeting-request`). 미팅 요청
자동화(A2)는 답이 온 곳에 더 묻지 않는데, 카톡으로 온 답을 앱은 모른다. 나가기
전날 오늘 할 일에 그 수가 서고(`automations/meeting_request.notes`), 여기서
답이 온 곳에 **[답 옴]** 을 누른다.

**자기 담당자만** 누른다 — 관리자는 팀 전체(`deps.may_manage_team_contacts`,
담당자 줄을 고치는 문과 같다).
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import clock
from ..db import get_db
from ..deps import get_current_user, may_manage_team_contacts, templates
from ..models import User
from ..services import automation, cadence
from ..ui import base_ctx

router = APIRouter(tags=["automations"])

HREF = "/automations/meeting-request"


def _rows(db: Session, user: User, day, test: bool, row) -> list:
    from ..services.automations import meeting_request as a2

    asks, _ = a2.due_on(db, row, day, test)
    if not may_manage_team_contacts(user):
        asks = [a for a in asks if a.contact.user_id == user.id]
    owners = {u.id: u.name for u in db.query(User).all()}
    return [{"contact_id": a.contact.id, "name": a.contact.name,
             "firm": a.contact.firm or "", "owner": owners.get(a.contact.user_id, ""),
             "anchor": a.anchor, "round": a.round,
             "due": f"{a.due.month}/{a.due.day}"} for a in asks]


@router.get(HREF, response_class=HTMLResponse, include_in_schema=False)
def meeting_request_page(request: Request, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user), msg: str = ""):
    """오늘 · 다음 평일에 미팅 요청이 나갈 곳 — 답이 온 곳은 [답 옴]."""
    row = automation.load(db, automation.MEETING_REQUEST)
    test = automation.is_test(row)
    today = clock.today()
    nxt = cadence.next_business_day(today + timedelta(days=1))
    ctx = base_ctx(request, db, user, active="todo")
    ctx.update({
        "on": automation.is_on(row), "test": test, "msg": msg,
        "today_rows": _rows(db, user, today, test, row),
        "next_rows": _rows(db, user, nxt, test, row),
        "next_label": f"{nxt.month}/{nxt.day}",
    })
    return templates.TemplateResponse(request, "auto_meeting_request.html", ctx)


def _contact_or_404(db: Session, contact_id: int, user: User):
    from .contacts import _owned

    return _owned(db, contact_id, user)


@router.post(HREF + "/{contact_id}/replied", include_in_schema=False)
def mark_replied(contact_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """[답 옴] — 이 담당자에게 미팅 요청 자동화를 멈춘다."""
    from ..services.automations import meeting_request as a2

    contact = _contact_or_404(db, contact_id, user)
    a2.mark_replied(db, contact)
    db.commit()
    note = f"{contact.name} 님 — 답 옴으로 적었습니다. 미팅 요청이 더 나가지 않습니다"
    return RedirectResponse(f"{HREF}?msg={quote(note)}", status_code=303)


@router.post(HREF + "/{contact_id}/replied/undo", include_in_schema=False)
def undo_replied(contact_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """잘못 누른 [답 옴] 을 거둔다."""
    from ..services.automations import meeting_request as a2

    contact = _contact_or_404(db, contact_id, user)
    a2.undo_replied(db, contact)
    db.commit()
    note = f"{contact.name} 님 — 답 옴 표시를 거뒀습니다"
    return RedirectResponse(f"{HREF}?msg={quote(note)}", status_code=303)
