"""IR·미팅 관리 — 딜소개 뒤에 오는 일을 놓치지 않게.

받은 요청을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보낸다. 그래서
**열린 것**(아직 안 보낸 요청 · 오늘 미팅 · 결과를 물을 때가 된 건)이 먼저 온다.

요청이 들어왔다는 것은 답이 왔다는 뜻이므로 **후속(리마인드)을 멈춘다** —
IR 요청이 왔는데 "지난번 공유드린 기업들 검토 중…"이 또 나가면
상대는 이쪽이 자기 답을 못 봤다고 생각한다.
"""
from __future__ import annotations

import json
from datetime import date
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, now_iso, templates
from ..models import ContactActivity, IrRequest, Meeting, User, VcContact
from ..services import cadence, flow, pipeline, sheet_owner
from . import followups
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
            user: User = Depends(get_current_user), msg: str = "",
            contact: int = 0):
    today = date.today()
    requests = pipeline.request_rows(db, user)
    meetings = pipeline.meeting_rows(db, user)
    items = pipeline.today_items(db, user, today)

    ctx = base_ctx(request, db, user, active="flow")
    # 리마인드 구역도 이 한 페이지 안에 있다 — 딴 페이지로 갈리면
    # "자료 보냈나 → 답 없으면 리마인드 → 미팅 잡기" 흐름이 끊긴다.
    ctx.update(followups.remind_context(db, user, today))
    ctx.update({
        # 후속 화면에서 이름을 눌러 넘어왔다 — 폼을 열고 그 사람을 골라 둔다.
        # 화면을 옮겨 담당자를 다시 고르는 사이에 "누구였더라" 가 된다.
        "preselect_contact": contact or 0,
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
    """자료 요청을 받았다고 적는다. **번호로 적어도 된다** — "2, 4" 처럼."""
    contact = _owned_contact(db, contact_id, user)
    when = (requested_at or "").strip() or date.today().isoformat()

    rows, unknown = pipeline.resolve_request_names(db, contact.id, company_name)
    if not rows and not unknown:
        return RedirectResponse("/ir?msg=기업명이나 번호를 입력하세요", status_code=303)
    if not rows:
        return RedirectResponse(
            f"/ir?msg={quote('지난 회차에 없는 번호입니다: ' + ', '.join(unknown) + '번')}",
            status_code=303)

    for row in rows:
        db.add(IrRequest(user_id=user.id, contact_id=contact.id,
                         company_id=row["company_id"],
                         company_name=row["name"], requested_at=when,
                         note=note.strip() or None))

    # 요청이 왔다는 것은 답이 왔다는 뜻이다 — 리마인드를 더 보내면 안 된다.
    cadence.stop_on_reaction(db, contact.id, "IR 자료를 요청했습니다")
    db.commit()

    msg = f"{len(rows)}건 기록했습니다"
    if unknown:
        # 조용히 버리면 요청 하나가 통째로 사라진 줄 모른다.
        msg += f" (지난 회차에 없는 번호는 건너뜀: {', '.join(unknown)}번)"
    return RedirectResponse(f"/ir?msg={quote(msg)}", status_code=303)


# 자료 파일은 **사람이 PC 카톡에서 직접 첨부한다.** 구글 드라이브 링크를 문구에
# 실어 보내던 방식은 폐기했다(0053) — 그래서 이 단추가 하는 일이 달라졌다.
#
# 예전에는 발송 화면으로 넘어가는 링크 하나였다. 링크만으로는 **손으로 한 일이
# 아무 데도 안 남는다** — 자료를 앱이 보내지 않으니, 누가 언제 어느 기업 자료를
# 보내려고 나섰는지는 여기서 적어 두지 않으면 기록이 없다.
#
# ## 무엇을 적고 무엇을 적지 않나
#
# `ContactActivity` 한 줄만 남긴다. **요청을 '전달함' 으로 닫지 않는다** —
# 아직 아무것도 나가지 않았고, 여기서 닫으면 사람이 첨부를 잊어도 요청이
# '보낼 자료' 목록에서 사라진다. 닫는 것은 지금처럼 발송이 성공한 뒤
# `pipeline.close_requests_for` 가 맡는다(또는 사람이 [전달함] 을 누른다).
# 같은 이유로 진행 단계(`deal_stage`)도 올리지 않는다 — 그 사다리의
# `IR 자료 전달` 칸은 실제로 전달된 건을 세는 자리다.
ATTACH_ON_PC = "IR 자료 전달 시작 — PC 에서 직접 첨부"


@router.post("/ir/deliver-guide", include_in_schema=False)
def deliver_guide(contact_id: int = Form(...), company_ids: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """[자료 보내기] — 활동 이력에 남기고, 안내창과 함께 발송 화면으로 보낸다."""
    contact = _owned_contact(db, contact_id, user)
    ids = [int(v) for v in company_ids.split(",") if v.strip().isdigit()]
    # 이 담당자가 **열어 둔 요청** 중 지금 보내려는 기업의 이름. 화면이 넘겨준
    # 번호를 그대로 믿지 않고 요청에서 되짚는다 — 남의 기업 번호가 주소에
    # 섞여 들어와도 이력에는 이 담당자가 실제로 요청한 것만 남아야 한다.
    names = [row.company_name for row in db.execute(
        select(IrRequest).where(IrRequest.contact_id == contact.id,
                                IrRequest.status == "open",
                                IrRequest.company_id.in_(ids))
    ).scalars().all() if row.company_name]

    today = date.today().isoformat()
    payload = json.dumps(names, ensure_ascii=False)
    # 두 번 눌렀다고 같은 줄이 두 번 쌓이면 이력이 아니라 소음이다.
    already = db.execute(
        select(ContactActivity).where(
            ContactActivity.contact_id == contact.id,
            ContactActivity.kind == "ir_delivery",
            ContactActivity.happened_at == today,
            ContactActivity.company_names == payload)
    ).scalars().first()
    if already is None:
        db.add(ContactActivity(
            contact_id=contact.id, kind="ir_delivery", source="system",
            content=ATTACH_ON_PC, happened_at=today, month=today[:7],
            company_names=payload, company_count=len(names) or None))
        db.commit()

    # 넘어갈 곳은 예전과 같다 — 담당자와 기업이 이미 골라진 발송 화면.
    # `attach=1` 이 거기서 안내창을 띄운다.
    query = (f"mode=ir&contacts={contact.id}"
             f"&companies={','.join(str(i) for i in ids)}&attach=1")
    return RedirectResponse(f"/deals?{query}", status_code=303)


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
    # 시각은 **선택**이다. 날짜만 아는 단계가 실제로 있고("다음 주 화요일쯤"),
    # 필수로 만들면 그 단계를 기록할 수 없다. 못 읽은 값은 `clean_time` 이
    # 버린다 — 자정 미팅을 지어내는 것보다 빈칸이 정확하다.
    scheduled_time: str = Form(""),
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
                   scheduled_time=pipeline.clean_time(scheduled_time),
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
                  note: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """결과를 물어본 것을 기록한다.

    무엇을 들었는지 함께 적는다 — 결과 한 칸(진행/보류/거절)만으로는 **왜**
    그런지가 남지 않고, 다음 회차에 이 투자사를 어떻게 대할지는 거기서 나온다.
    """
    meeting = _owned_meeting(db, meeting_id, user)
    meeting.followup_done = 1
    meeting.followup_at = now_iso()[:10]
    if outcome in pipeline.OUTCOMES:
        meeting.outcome = outcome
    text = (note or "").strip()
    if text:
        # 다시 물어본 경우 앞의 것을 지우지 않는다 — 두 번의 통화가 다른
        # 이야기라, 덮으면 앞의 맥락이 사라진다.
        before = (meeting.followup_note or "").strip()
        stamp = meeting.followup_at
        meeting.followup_note = (f"{before}\n[{stamp}] {text}".strip()
                                 if before else f"[{stamp}] {text}")
    db.commit()
    return RedirectResponse("/ir?msg=결과 문의를 기록했습니다#reviews", status_code=303)


class MeetingNoteIn(BaseModel):
    note: Optional[str] = None
    followup_note: Optional[str] = None


@router.patch("/api/meetings/{meeting_id}", include_in_schema=False)
def edit_meeting_note(meeting_id: int, body: MeetingNoteIn,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """미팅 후기·결과 문의 메모를 표에서 바로 고친다."""
    meeting = _owned_meeting(db, meeting_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(meeting, field, (value or "").strip() or None)
    db.commit()
    return {"ok": True}


@router.post("/ir/meetings/{meeting_id}/cancel", include_in_schema=False)
def cancel_meeting(meeting_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    meeting = _owned_meeting(db, meeting_id, user)
    meeting.status = "canceled"
    meeting.followup_due = None
    db.commit()
    return RedirectResponse("/ir?msg=미팅을 취소했습니다", status_code=303)
