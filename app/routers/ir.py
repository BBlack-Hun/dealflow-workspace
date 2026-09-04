"""IR·미팅 관리 — 딜소개 뒤에 오는 일을 놓치지 않게.

받은 요청을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보낸다. 그래서
**열린 것**(아직 안 보낸 요청 · 오늘 미팅 · 결과를 물을 때가 된 건)이 먼저 온다.

요청이 들어왔다는 것은 답이 왔다는 뜻이므로 **후속(리마인드)을 멈춘다** —
IR 요청이 왔는데 "지난번 공유드린 기업들 검토 중…"이 또 나가면
상대는 이쪽이 자기 답을 못 봤다고 생각한다.
"""
from __future__ import annotations

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
from ..models import IrRequest, Meeting, User, VcContact
from ..services import cadence, flow, ir_attach, pipeline, sheet_owner
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
        # 자료를 **누가 붙이는가** — 발송 화면과 **같은 판단**을 읽는다
        # (`services/ir_attach.py`). 두 화면이 따로 판단하면 여기서는 손으로
        # 붙이라고 하는데 저기서는 발송기가 붙여 자료가 두 번 나간다.
        "ir_auto_attach": ir_attach.auto_attach_enabled(db, user),
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


# [자료 보내기] 는 **그 자리에서 끝난다** — 화면을 옮기지 않는다.
#
# 예전에는 이 자리가 하는 일이 둘이었다: 활동 이력에 한 줄을 남기고, 딜 제안
# 관리(`/deals`)로 화면을 통째로 옮긴다. 둘 다 없앴다.
#
# ## 화면을 안 옮긴다
#
# 넘어간 사람이 거기서 할 일은 이미 정해져 있었다 — **이 담당자에게, 이 기업들
# 자료를, 지금 보낸다.** 그 한 가지를 하려고 기업 고르기·담당자 고르기·예약
# 큐가 다 붙은 넓은 화면으로 옮기면, 돌아올 길을 스스로 찾아야 하고 옮긴
# 화면에서 체크가 하나 풀려도 어디가 달라졌는지 모른다.
#
# 지금은 IR 관리 화면 안에서 창이 열려 번호·파일명·나갈 문구를 보여 주고 거기서
# 보낸다(`static/js/ir_send.js`). **그 창이 값을 짓지 않는다** — 서버 미리보기
# (`POST /api/deals/preview`)를 그대로 받아 그리고, 발송도 딜 제안 관리가 쓰는
# 그 길(`POST /api/deals/send`)로 간다.
#
# ## 그래도 이 자리는 남는다 — **스크립트가 죽었을 때의 길**
#
# 화면의 [자료 보내기] 는 여전히 폼이고, 스크립트가 이 폼의 `submit` 을 가로채
# 창을 연다. 스크립트가 안 실리거나 예외가 나면 폼은 폼대로 여기로 와서 예전처럼
# 딜 제안 관리로 간다. 문구를 손보거나 담당자를 더하려면 그 화면이 필요해서,
# 창 안에도 그리로 가는 길을 남겨 두었다.
#
# ## 이력은 여기서 안 적는다 — **보낸 때 적는다**
#
# 누른 것만으로 적으면 창을 열어 문구만 확인하고 닫아도 '자료 보냄' 이 남는다.
# 그 자리에서 끝내는 흐름이 된 뒤로는 그렇게 닫는 것이 자연스러운 동작이라 더
# 어긋난다. 적는 자리는 발송 목록을 만드는 한 곳으로 옮겼다
# (`services/ir_attach.py: record_delivery` — 왜 거기인지 그 옆에 적어 두었다).


@router.post("/ir/deliver-guide", include_in_schema=False)
def deliver_guide(contact_id: int = Form(...), company_ids: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """[자료 보내기] 의 **스크립트 없는 길** — 담당자·기업이 골라진 발송 화면으로.

    스크립트가 살아 있으면 여기까지 오지 않는다(창이 그 자리에서 열린다).
    """
    # 남의 담당자로는 아무 데도 못 간다 — 주소에 남의 번호를 넣어도 여기서 막힌다.
    contact = _owned_contact(db, contact_id, user)
    # 화면이 넘겨준 번호를 그대로 믿지 않는다. 이 담당자가 **열어 둔 요청**의
    # 기업만 넘긴다 — 남의 기업 번호가 주소에 섞여 들어와도 발송 화면에는 이
    # 담당자가 실제로 요청한 것만 골라져 있어야 한다.
    asked = [int(v) for v in company_ids.split(",") if v.strip().isdigit()]
    ids = [row.company_id for row in db.execute(
        select(IrRequest).where(IrRequest.contact_id == contact.id,
                                IrRequest.status == "open",
                                IrRequest.company_id.in_(asked))
    ).scalars().all() if row.company_id]

    # 넘어갈 곳은 예전과 같다 — 담당자와 기업이 이미 골라진 발송 화면.
    # `attach=1` 이 거기서 안내창을 띄운다(자동 첨부를 켜지 않은 계정만).
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
