"""IR·미팅 관리 — 딜소개 뒤에 오는 일을 놓치지 않게.

받은 요청을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보낸다. 그래서
**열린 것**(아직 안 보낸 요청 · 오늘 미팅 · 결과를 물을 때가 된 건)이 먼저 온다.

요청이 들어왔다는 것은 답이 왔다는 뜻이므로 **후속(리마인드)을 멈춘다** —
IR 요청이 왔는데 "지난번 공유드린 기업들 검토 중…"이 또 나가면
상대는 이쪽이 자기 답을 못 봤다고 생각한다.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import IrRequest, Meeting, User, VcContact
from ..services import cadence, flow, pipeline, sheet_owner
from ..ui import base_ctx

router = APIRouter(tags=["ir"])


def _owned_contact(db: Session, contact_id: int, user: User) -> VcContact:
    contact = db.get(VcContact, contact_id)
    if contact is None or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")
    return contact


def _owned_request(db: Session, request_id: int, user: User) -> IrRequest:
    row = db.get(IrRequest, request_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다")
    return row


def _owned_meeting(db: Session, meeting_id: int, user: User) -> Meeting:
    row = db.get(Meeting, meeting_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="미팅을 찾을 수 없습니다")
    return row


@router.get("/ir", response_class=HTMLResponse, include_in_schema=False)
def ir_page(request: Request, db: Session = Depends(get_db),
            user: User = Depends(get_current_user), msg: str = ""):
    today = date.today()
    requests = pipeline.request_rows(db, user)
    meetings = pipeline.meeting_rows(db, user)
    items = pipeline.today_items(db, user, today)

    ctx = base_ctx(request, db, user, active="flow")
    ctx.update({
        "flow_tab": "ir",
        "flow_counts": flow.counts(db, user, today),
        "requests": requests,
        "meetings": meetings,
        "open_requests": [r for r in requests if r["status"] == "open"],
        # 한 담당자가 여러 기업을 요청하는 일이 잦다 — 한 번에 보내야 자연스럽다.
        "request_groups": pipeline.group_by_contact(
            [r for r in requests if r["status"] == "open"]),
        "done_requests": [r for r in requests if r["status"] != "open"],
        "scheduled": [m for m in meetings if m["status"] == "scheduled"],
        "finished": [m for m in meetings if m["status"] != "scheduled"],
        "items": items,
        "counts": {
            "open": len(items["open_requests"]),
            "overdue": len(items["overdue_requests"]),
            "today": len(items["today_meetings"]),
            "followup": len(items["due_followups"]),
        },
        # 담당자 고르기 — 내 명단만
        "contacts": sorted(sheet_owner.my_contacts(db, user),
                           key=lambda c: (c.firm or "", c.name)),
        "outcomes": pipeline.OUTCOMES,
        "kinds": pipeline.MEETING_KINDS,
        "followup_days": pipeline.MEETING_FOLLOWUP_DAYS,
        "today": today.isoformat(),
        "msg": msg,
    })
    return templates.TemplateResponse("ir.html", ctx)


@router.get("/api/ir/last-batch/{contact_id}")
def last_batch(contact_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """그 담당자에게 마지막으로 보낸 회차의 **번호와 기업**.

    투자사는 "4번, 6번 주세요" 라고 답한다. 번호를 눌러 기록할 수 있어야
    지난 카톡을 뒤지지 않는다.
    """
    _owned_contact(db, contact_id, user)
    return pipeline.last_batch_items(db, contact_id)


# --- IR 요청 ----------------------------------------------------------------

@router.post("/ir/requests", include_in_schema=False)
def create_request(
    contact_id: int = Form(...),
    company_name: str = Form(...),
    requested_at: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """자료 요청을 받았다고 적는다. 여러 기업이면 줄바꿈으로 한 번에."""
    contact = _owned_contact(db, contact_id, user)
    when = (requested_at or "").strip() or date.today().isoformat()

    names = [n.strip() for n in company_name.replace(",", "\n").splitlines()
             if n.strip()]
    if not names:
        return RedirectResponse("/ir?msg=기업명을 입력하세요", status_code=303)

    for name in names:
        company = pipeline.match_company(db, name)
        db.add(IrRequest(user_id=user.id, contact_id=contact.id,
                         company_id=company.id if company else None,
                         company_name=name, requested_at=when,
                         note=note.strip() or None))

    # 요청이 왔다는 것은 답이 왔다는 뜻이다 — 리마인드를 더 보내면 안 된다.
    cadence.stop_on_reaction(db, contact.id, "IR 자료를 요청했습니다")
    db.commit()
    return RedirectResponse(f"/ir?msg={len(names)}건 기록했습니다", status_code=303)


@router.post("/ir/requests/{request_id}/deliver", include_in_schema=False)
def deliver_request(request_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    pipeline.deliver(db, _owned_request(db, request_id, user))
    db.commit()
    return RedirectResponse("/ir?msg=전달 완료로 표시했습니다", status_code=303)


@router.post("/ir/requests/{request_id}/drop", include_in_schema=False)
def drop_request(request_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    row = _owned_request(db, request_id, user)
    row.status = "dropped"
    db.commit()
    return RedirectResponse("/ir?msg=보내지 않기로 표시했습니다", status_code=303)


@router.post("/ir/requests/{request_id}/delete", include_in_schema=False)
def delete_request(request_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    db.delete(_owned_request(db, request_id, user))
    db.commit()
    return RedirectResponse("/ir?msg=요청을 지웠습니다", status_code=303)


# --- 미팅 ------------------------------------------------------------------

@router.post("/ir/meetings", include_in_schema=False)
def create_meeting(
    contact_id: int = Form(...),
    scheduled_at: str = Form(...),
    kind: str = Form("first"),
    company_name: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contact = _owned_contact(db, contact_id, user)
    try:
        when = date.fromisoformat(scheduled_at.strip())
    except ValueError:
        return RedirectResponse("/ir?msg=미팅 날짜를 확인해 주세요", status_code=303)

    company = pipeline.match_company(db, company_name) if company_name.strip() else None
    db.add(Meeting(user_id=user.id, contact_id=contact.id,
                   company_id=company.id if company else None,
                   company_name=company_name.strip() or None,
                   scheduled_at=when.isoformat(),
                   kind=kind if kind in pipeline.MEETING_KINDS else "first",
                   note=note.strip() or None))
    # 미팅이 잡혔으면 답이 온 것이다.
    cadence.stop_on_reaction(db, contact.id, "미팅이 잡혔습니다")
    db.commit()
    return RedirectResponse("/ir?msg=미팅을 등록했습니다", status_code=303)


@router.post("/ir/meetings/{meeting_id}/done", include_in_schema=False)
def finish_meeting(meeting_id: int, outcome: str = Form(""),
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """완료 처리하면 **열흘 뒤 결과를 물을 날**이 자동으로 잡힌다."""
    meeting = pipeline.complete_meeting(db, _owned_meeting(db, meeting_id, user),
                                        outcome=outcome)
    db.commit()
    return RedirectResponse(
        f"/ir?msg=미팅 완료 · {meeting.followup_due} 에 결과를 물어보세요",
        status_code=303)


@router.post("/ir/meetings/{meeting_id}/followup", include_in_schema=False)
def mark_followup(meeting_id: int, outcome: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    meeting = _owned_meeting(db, meeting_id, user)
    meeting.followup_done = 1
    if outcome in pipeline.OUTCOMES:
        meeting.outcome = outcome
    db.commit()
    return RedirectResponse("/ir?msg=결과 문의를 마쳤습니다", status_code=303)


@router.post("/ir/meetings/{meeting_id}/cancel", include_in_schema=False)
def cancel_meeting(meeting_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    meeting = _owned_meeting(db, meeting_id, user)
    meeting.status = "canceled"
    meeting.followup_due = None
    db.commit()
    return RedirectResponse("/ir?msg=미팅을 취소했습니다", status_code=303)
