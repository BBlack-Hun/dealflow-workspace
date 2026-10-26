"""IR·미팅 관리 — 딜소개 뒤에 오는 일을 놓치지 않게.

받은 요청을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보낸다. 그래서
**열린 것**(아직 안 보낸 요청 · 오늘 미팅 · 결과를 물을 때가 된 건)이 먼저 온다.

요청이 들어왔다는 것은 답이 왔다는 뜻이므로 **리마인드를 멈춘다** —
IR 요청이 왔는데 "지난번 공유드린 기업들 검토 중…"이 또 나가면
상대는 이쪽이 자기 답을 못 봤다고 생각한다.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import quote, urlencode
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import doer, get_current_user, now_iso, templates
from ..models import IrCompany, IrRequest, Meeting, User, VcContact
from ..services import (call_flags, cadence, flow, ir_attach, ir_no_meeting,
                        meeting_calendar, pipeline, sheet_owner)
from . import followups
from .data_io import _xlsx
from .companies import BLOCKED_CONTRACT, contract_key
from ..ui import base_ctx

router = APIRouter(tags=["ir"])


def _company_names(db: Session) -> list:
    """「요청받은 기업」 칸의 **후보 이름들** — 한 번에 실어 보낸다.

    ## 왜 서버가 한 번에 주나

    타이핑할 때마다 서버에 물으면 이름 한 줄을 적는 동안 질의가 열 번 넘게
    나간다. 후보 목록은 344곳짜리 표 하나이고 화면을 여는 사이에 바뀌지도
    않아서, **화면을 그릴 때 한 번** 읽어 싣는 편이 맞다. 도메인 후보를 싣는
    자리와 같은 방식이다(`services/email_domains.py` → `#opts-email-domain`).

    이름 두 칸만 읽는다 — 줄 전체를 들고 오면 344줄짜리 객체가 그려지지도
    않을 화면에 실린다.

    ## 무엇을 빼나 — **딜소개 불가**

    발송 화면(`routers/pages.py` 의 `deals_page`)이 목록에서 빼는 그 기업이다.
    "보내면 안 되는 곳" 이라 목록에 있는 것만으로 실수로 고를 수 있다는 것이
    거기 적힌 이유이고, 여기도 **고르는 자리**라 같은 이유가 그대로 선다.
    값이 예전 말(`딜소개 불가`)로 적혀 있어도 걸러지도록 `contract_key` 를
    지난다(`services/llm_brief.py` 가 같은 것을 부른다).

    **거르는 것이지 막는 것이 아니다.** 후보에 없는 이름을 손으로 적으면
    지금처럼 그대로 기록된다 — 서버는 이 목록을 모른다
    (`pipeline.resolve_request_names`).
    """
    rows = db.execute(select(IrCompany.name, IrCompany.contract_status)).all()
    names = {
        (name or "").strip()
        for name, contract in rows
        if (name or "").strip() and contract_key(contract) != BLOCKED_CONTRACT
    }
    return sorted(names)


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
    requests = pipeline.request_rows(db, user, today)
    meetings = pipeline.meeting_rows(db, user)
    items = pipeline.today_items(db, user, today)

    # ── 전달한 자료 — **지난 것을 위로** ────────────────────────────────────
    #
    # 이 판은 오래 쓸수록 줄이 쌓여서 최근 20줄만 그린다. 그런데 이 기능이
    # 보여 주려는 것이 바로 **오래된 채로 말이 안 붙은 건**이라, 그것이 20줄
    # 밖으로 밀려 안 보이면 기능의 뜻이 없다. 그래서 둘을 같이 한다.
    #
    #   ① 지난 줄을 맨 위로 올린다(그 안의 차례는 그대로 — 안정 정렬).
    #   ② 지난 줄이 20보다 많으면 **그만큼 늘린다.** 재촉할 것은 한 줄도
    #      안 자른다.
    #
    # 전부 그리지 않는 이유: 전달 기록은 계속 쌓이기만 하는 표라 몇백 줄이
    # 되면 화면이 느려지고, 무엇보다 끝난 옛 줄이 눈을 가린다. 잘라도 되는
    # 것은 **이미 말이 붙은 줄**뿐이다.
    done = [r for r in requests if r["status"] != "open"]
    done.sort(key=lambda r: 0 if r["meeting_ask_overdue"] else 1)

    # **담당자 단위로 센다.** 한 투자사가 기업 3곳 자료를 받아도 미팅 요청
    # 카톡은 한 통이라, 줄마다 세면 한 번 보낼 일이 세 건으로 보인다.
    delivered = [r for r in done if r["status"] == "delivered"]
    ask_missing = {r["contact_id"] for r in delivered if not r["meeting_asked"]}
    ask_overdue = {r["contact_id"] for r in delivered if r["meeting_ask_overdue"]}

    ctx = base_ctx(request, db, user, active="flow")
    # 담당자 고르기에 세울 사람들 — **맡은 사람 전부**(`my_contacts`)다.
    # 발송 대상(`recipients`)이 아니라는 것이 이 화면의 뜻이다: 여기는 보내는
    # 곳이 아니라 **이미 일어난 일을 적는** 곳이라, 방을 나간 분이 메일로
    # 요청한 일도 적을 수 있어야 한다. 대신 왜 이 사람이 목록에 있는지를
    # 줄마다 적는다(아래 `pick_notes`).
    picks = sorted(sheet_owner.my_contacts(db, user),
                   key=lambda c: (c.firm or "", c.name))
    # 리마인드 구역도 이 한 페이지 안에 있다 — 딴 페이지로 갈리면
    # "자료 보냈나 → 답 없으면 리마인드 → 미팅 잡기" 흐름이 끊긴다.
    ctx.update(followups.remind_context(db, user, today))
    ctx.update({
        # 리마인드 구역에서 이름을 눌러 넘어왔다 — 폼을 열고 그 사람을 골라 둔다.
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
        "done_requests": done,
        # 지난 줄은 한 줄도 안 자른다 — 위 주석 참고.
        "done_limit": max(20, sum(1 for r in done if r["meeting_ask_overdue"])),
        "meeting_ask_missing": len(ask_missing),
        "meeting_ask_overdue": len(ask_overdue),
        # 화면 안내문이 "7일" 이라고 말할 때 쓰는 값. 코드와 화면이 다른
        # 숫자를 말하면 안 된다(`followup_days` 와 같은 방식).
        "meeting_ask_days": pipeline.IR_MEETING_ASK_DAYS,
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
        "contacts": picks,
        # 그 줄에 함께 적을 **상태**(`[방 나감]` · `[검토중단]` …). 판정도
        # 한글 이름도 서버 한 곳에서 나온다 — 화면이 `connect_stage` 값을
        # 직접 보고 말을 지어내면, 임포트가 말을 바꾸는 날 이 화면만 낡는다.
        "pick_notes": sheet_owner.pick_notes(db, picks),
        # 「요청받은 기업」 칸의 후보. **질의는 이 한 번뿐**이다 — 위 함수 참고.
        "company_names": _company_names(db),
        # 같은 칸에 함께 뜨는 **Series A 이상 딜 소싱** 기업 — 화면이 `Series A`
        # 딱지를 붙인다. IR 기업 현황에 같은 기업이 있으면 IR 쪽 하나로만 선다.
        "series_a_names": sorted(pipeline.series_a_names(db).values()),
        "outcomes": pipeline.OUTCOMES,
        "kinds": pipeline.MEETING_KINDS,
        "meet_modes": pipeline.MEETING_MODES,
        "followup_days": pipeline.MEETING_FOLLOWUP_DAYS,
        # ── 화면 말 (10/17 회의 #35~#44) — 짓는 자리는 `pipeline.LABEL_*` 한 곳.
        "labels": {
            "delivered": pipeline.LABEL_DELIVERED,
            "asked": pipeline.LABEL_ASKED,
            "not_asked": pipeline.LABEL_NOT_ASKED,
            "book": pipeline.LABEL_BOOK_MEETING,
            "mark_asked": pipeline.LABEL_MARK_ASKED,
            "requested": pipeline.LABEL_REQUESTED,
        },
        # ── 답 없음 · 전화 요청 (#37) ─────────────────────────────────────
        # 사람 → 표시·메모. 켜졌거나 메모가 있는 사람만 든다. 줄마다 붙일지는
        # 템플릿의 `call_flag` 매크로가 **그 줄에서 리마인드가 나갔는가**로 가른다.
        "call_flags": call_flags.views(db),
        "call_flag_label": call_flags.LABEL,
        # 이 사람이 걸어야 할 전화 — `전화 요청` 구역 맨 위 묶음. 오늘 할 일과
        # 같은 한 벌이다(`call_flags.needed_for`).
        "call_needed_rows": call_flags.needed_for(db, user),
        "today": today.isoformat(),
        "msg": msg,
    })
    return templates.TemplateResponse(request, "ir.html", ctx)


def _month_of(ym: str, today: date) -> tuple:
    """`2026-10` → (2026, 10). 못 읽으면 이번 달 — 주소를 손으로 고쳐도 500 이 안 난다."""
    try:
        year, mon = (int(x) for x in ym.split("-"))
    except ValueError:
        return today.year, today.month
    return (year, mon) if 2000 <= year <= 2100 and 1 <= mon <= 12 else (today.year, today.month)


def _who(request: Request, user: User, member: int) -> tuple:
    """`(누구 것 — None 이면 팀 전체, 고른 팀원, 주소에 이어 붙일 꼬리)`.

    팀원은 **제 것만**(`member` 를 붙여 와도). 관리자는 팀 전체가 기본이고 한 사람을
    고를 수 있다 — 업무 보고의 `?member=` 와 같은 모양이다. 팀원 화면으로 보는
    중이면 기본은 그 팀원이다(#3) — `팀 전체` 칩은 `member=0` 을 실어 와서 그대로
    전체가 열린다(투자컨설턴트 고르개와 같은 길).
    """
    if user.role != "admin":
        return user.id, 0, ""
    viewing = doer(user) is not user
    if viewing and "member" not in request.query_params:
        member = user.id
    # 앞뒤 이동·거르기가 고른 팀원을 놓치지 않게 주소에 이어 붙인다. 보는 중에
    # 고른 `팀 전체`(0)도 이어 붙인다 — 빠지면 다음 화면에서 그 팀원으로 돌아간다.
    return member or None, member, f"&member={member}" if member or viewing else ""


def _members(db: Session, user: User) -> list:
    """관리자 고르개에 세울 사람들 — 관리자가 아니면 빈 목록(고르개가 안 선다)."""
    if user.role != "admin":
        return []
    return [{"id": u.id, "name": u.name} for u in
            db.execute(select(User).where(User.is_active == 1)
                       .order_by(User.id)).scalars().all()]


@router.get("/ir/calendar", response_class=HTMLResponse, include_in_schema=False)
def meeting_calendar_page(request: Request, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user),
                          view: str = "month", ym: str = "", y: str = "",
                          member: int = 0):
    """IR 미팅 달력 — 월간(`?view=month&ym=2026-10`) · 연간(`?view=year&y=2026`) (#5).

    팀원은 **제 미팅만** 본다. 관리자는 팀 전체가 기본이고 팀원 한 사람을
    고를 수 있다 — 업무 보고의 `?member=` 와 같은 모양이다. 관리자가 아닌
    계정이 `member` 를 붙여 와도 제 것만 나온다(업무 보고와 같다).
    """
    today = date.today()
    who, member, member_q = _who(request, user, member)
    ctx = base_ctx(request, db, user, active="flow")
    ctx.update({
        "ir_tab": "calendar",
        "view": "year" if view == "year" else "month",
        "member": member,
        "member_q": member_q,
        "members": _members(db, user),
        "this_ym": f"{today.year}-{today.month:02d}",
        "this_year": today.year,
    })
    if ctx["view"] == "year":
        year = _month_of(f"{y}-01", today)[0]   # 해만 고른다 — 읽는 규칙은 월간과 하나
        # `월간` 으로 돌아갈 달 — 올해면 이번 달, 아니면 1월.
        ctx.update({"year": year, "month": today.month if year == today.year else 1,
                    "months": meeting_calendar.year(db, who, year)})
    else:
        year, mon = _month_of(ym, today)
        prev = (year - 1, 12) if mon == 1 else (year, mon - 1)
        nxt = (year + 1, 1) if mon == 12 else (year, mon + 1)
        ctx.update({"year": year, "month": mon,
                    "prev_ym": f"{prev[0]}-{prev[1]:02d}",
                    "next_ym": f"{nxt[0]}-{nxt[1]:02d}",
                    **meeting_calendar.month(db, who, year, mon, today)})
    return templates.TemplateResponse(request, "meeting_calendar.html", ctx)


# 경과일 거르기 칩 — 그 밖의 값은 `전체` 로 읽는다(주소를 손으로 고쳐도 500 이 안 난다).
NO_MEETING_DAYS = ("7", "30", "90")


def _no_meeting(request: Request, db: Session, user: User, view: str, days: str,
                sent: str, src: str, drop: str, member: int) -> dict:
    """`IR 요청 후 미팅 없음` 화면과 엑셀이 **같이 읽는** 줄 — 거르기까지 한 번에."""
    who, member, member_q = _who(request, user, member)
    view = "scheduled" if view == "scheduled" else "none"
    days = days if days in NO_MEETING_DAYS else ""
    sent = sent if sent in ("yes", "no") else ""
    src = src if src in ("app", "sheet") else ""
    drop = "show" if drop == "show" else ""     # `보내지 않음` 은 기본으로 뺀다 — 칩으로 본다
    found, skipped = ir_no_meeting.rows(db, who, date.today())
    rows = [r for r in found
            if (not days or (r["days"] or 0) >= int(days))
            and (not sent or (r["state"] == "delivered") == (sent == "yes"))
            and (not src or (r["src"] == "sheet") == (src == "sheet"))
            and (drop or r["state"] != "dropped")]
    planned = [r for r in rows if r["scheduled"]]
    params = {"view": view, "days": days, "sent": sent, "src": src, "drop": drop}

    def href(path: str = "/ir/no-meeting", **change) -> str:
        """지금 거르기에 `change` 만 바꾼 주소 — 고른 팀원도 이어 붙인다."""
        return f"{path}?{urlencode({k: v for k, v in {**params, **change}.items() if v})}{member_q}"

    return {
        **params, "who": who, "member": member, "href": href, "skipped": skipped,
        "here": f"/ir/no-meeting?{urlencode({k: v for k, v in params.items() if v})}",
        "rows": planned if view == "scheduled" else [r for r in rows if not r["scheduled"]],
        "n_none": len(rows) - len(planned), "n_planned": len(planned),
    }


@router.get("/ir/no-meeting", response_class=HTMLResponse, include_in_schema=False)
def no_meeting_page(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user), view: str = "",
                    days: str = "", sent: str = "", src: str = "", drop: str = "",
                    member: int = 0):
    """IR 요청 후 미팅 없음 — 정의는 `services/ir_no_meeting.py` 첫머리."""
    ctx = base_ctx(request, db, user, active="flow")
    ctx.update(_no_meeting(request, db, user, view, days, sent, src, drop, member))
    ctx.update({"ir_tab": "no_meeting", "members": _members(db, user),
                "day_steps": NO_MEETING_DAYS, "sources": ir_no_meeting.SOURCES})
    return templates.TemplateResponse(request, "ir_no_meeting.html", ctx)


@router.get("/api/export/ir-no-meeting.xlsx")
def export_no_meeting(request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user), view: str = "",
                      days: str = "", sent: str = "", src: str = "", drop: str = "",
                      member: int = 0):
    """화면과 같은 범위 · 같은 거르기. 요청일은 첫·최근 두 칸으로 가른다."""
    got = _no_meeting(request, db, user, view, days, sent, src, drop, member)
    planned = got["view"] == "scheduled"
    heads = ["기업명", "투자사", "심사역", "첫 요청일", "최근 요청일", "요청 상태", "전달일",
             "경과일", "담당", "요청 건수", "출처", "비고"] + (["미팅 예정일"] if planned else [])
    rows = [[r["company"], r["firm"], f"{r['contact_name']} {r['contact_title']}".strip(),
             r["first_at"], r["last_at"], r["status_label"], r["delivered_at"], r["days"],
             r["owners"], r["count"], ir_no_meeting.SOURCES[r["src"]], r["note"]]
            + ([r["scheduled_on"]] if planned else [])
            for r in got["rows"]]
    title = "IR 요청 후 미팅 예정" if planned else "IR 요청 후 미팅 없음"
    return _xlsx(f"{title}_{date.today().isoformat()}.xlsx", title, heads, rows)


@router.get("/api/ir/last-batch/{contact_id}")
def last_batch(contact_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """그 담당자에게 마지막으로 보낸 회차의 **번호와 기업**.

    투자사는 "기업4, 기업6 주세요" 라고 답한다. 번호를 눌러 기록할 수 있어야
    지난 카톡을 뒤지지 않는다.
    """
    _owned_contact(db, contact_id, user)
    return pipeline.last_batch_items(db, contact_id)


# --- IR 요청 ----------------------------------------------------------------

@router.post("/ir/requests", include_in_schema=False)
def create_request(
    contact_id: int = Form(...),
    company_name: str = Form(""),
    requested_at: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """자료 요청을 받았다고 적는다. **번호로 적어도 된다** — "[기업2], 4" 처럼.

    받는 모양은 `deal_numbers.parse_label` 이 정한다(`2` · `기업2` · `[기업2]`).
    """
    contact = _owned_contact(db, contact_id, user)
    when = (requested_at or "").strip() or date.today().isoformat()

    rows, unknown = pipeline.resolve_request_names(db, contact.id, company_name)
    if not rows and not unknown:
        return RedirectResponse("/ir?msg=기업명이나 번호를 입력하세요", status_code=303)
    if not rows:
        return RedirectResponse(
            f"/ir?msg={quote('지난 회차에 없는 번호입니다: ' + ', '.join(unknown))}",
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
        msg += f" (지난 회차에 없는 번호는 건너뜀: {', '.join(unknown)})"
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
                  series_a_ids: str = Form(""),
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
    opened = db.execute(
        select(IrRequest).where(IrRequest.contact_id == contact.id,
                                IrRequest.status == "open")
    ).scalars().all()
    ids = [row.company_id for row in opened if row.company_id in asked]
    # Series A 이상 딜 소싱 기업(0118) — 이 담당자가 **이름으로 열어 둔 요청**의 그
    # 기업 줄만 넘긴다(`pipeline.series_a_rows` 가 고른 그 줄 — 화면도 같은 줄을 싣는다).
    picked = {int(v) for v in series_a_ids.split(",") if v.strip().isdigit()}
    wanted = {pipeline._key(row.company_name) for row in opened if not row.company_id}
    sa_ids = [row.id for key, row in pipeline.series_a_rows(db).items()
              if key in wanted and row.id in picked]

    # 넘어갈 곳은 예전과 같다 — 담당자와 기업이 이미 골라진 발송 화면.
    # `attach=1` 이 거기서 안내창을 띄운다(자동 첨부를 켜지 않은 계정만).
    query = (f"mode=ir&contacts={contact.id}"
             f"&companies={','.join(str(i) for i in ids)}&attach=1")
    if sa_ids:
        query += f"&series_a={','.join(str(i) for i in sa_ids)}"
    return RedirectResponse(f"/deals?{query}", status_code=303)


@router.post("/ir/requests/{request_id}/deliver", include_in_schema=False)
def deliver_request(request_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    pipeline.deliver(db, _owned_request(db, request_id, user))
    db.commit()
    return RedirectResponse(
        f"/ir?msg={quote(pipeline.LABEL_DELIVERED + '로 표시했습니다')}",
        status_code=303)


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


@router.post("/ir/contacts/{contact_id}/meeting-asked", include_in_schema=False)
def mark_meeting_asked(contact_id: int, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """미팅 요청을 **카톡으로 직접 보냈다**고 표시한다.

    앱을 안 거치고 사람이 바로 보내는 일이 흔하다. 그것을 적을 자리가 없으면
    「안 보냄」이 영영 떠 있고, 거짓으로 뜨는 숫자는 곧 아무도 안 본다.

    **줄이 아니라 담당자에게 적는다** — 나가는 카톡이 담당자당 한 통이라
    (`deals.MODES_WITH_COMPANIES` 에 미팅이 없다) 자료 줄에 적으면 같은 사람의
    다른 줄이 여전히 「안 보냄」으로 남는다. 판정도 담당자 단위다
    (`pipeline.meeting_ask_state`).
    """
    contact = _owned_contact(db, contact_id, user)
    pipeline.record_meeting_ask(db, contact.id)
    db.commit()
    # 단추 이름이 `IR 자료 검토 요청 보냄` 이 됐다(10/17 회의 #42). 누르면 그
    # 담당자 줄들이 `회의실 미팅 톡 요청 보냄 완료` 로 바뀐다 — 둘 다 말해 준다.
    msg = (f"{pipeline.LABEL_MARK_ASKED}으로 표시했습니다 — "
           f"{pipeline.LABEL_ASKED}")
    return RedirectResponse(f"/ir?msg={quote(msg)}", status_code=303)


# --- 답 없음 · 전화 요청 (10/17 회의 #37) ------------------------------------
#
# 리마인드 카톡을 보낸 뒤 답이 없으면 팀원·담당자가 켜고, 메모를 남긴다. 판정과
# 저장은 `services/call_flags.py` 한 곳이고, 여기서는 권한과 돌아갈 자리만 본다.

#: 누르고 **돌아갈 구역.** 폼이 실어 온 글자를 그대로 주소에 붙이지 않는다 —
#: 아는 구역 이름만 받고, 모르면 `전화 요청` 구역으로 간다.
CALL_FLAG_BACK = ("remind", "calls", "delivered", "meetings", "reviews")


def _flag_contact(db: Session, contact_id: int, user: User) -> VcContact:
    """표시·메모를 고칠 사람. 고칠 수 없는 계정에는 **없는 사람**으로 답한다."""
    contact = db.get(VcContact, contact_id)
    if contact is None or not call_flags.may_edit(db, user, contact):
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")
    return contact


def _flag_back(back: str, msg: str) -> RedirectResponse:
    anchor = back if back in CALL_FLAG_BACK else "calls"
    return RedirectResponse(f"/ir?msg={quote(msg)}#{anchor}", status_code=303)


@router.post("/ir/contacts/{contact_id}/call-needed", include_in_schema=False)
def set_call_needed(contact_id: int, on: int = Form(1), back: str = Form(""),
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """`답 없음 · 전화 요청` 을 켜고 끈다. 누가 언제 했는지 줄에 남는다.

    **켜는 것은 리마인드가 나간 사람에게만** — 화면도 그런 줄에만 단추를 세운다.
    끄는 것은 언제나 된다(남은 표시를 치울 길은 늘 있어야 한다).
    """
    contact = _flag_contact(db, contact_id, user)
    if on and not call_flags.reminded(db, contact.id):
        raise HTTPException(status_code=400,
                            detail="리마인드 카톡이 나간 뒤에 표시할 수 있습니다")
    call_flags.set_call(db, contact.id, bool(on), user)
    db.commit()
    return _flag_back(back, "전화 요청으로 표시했습니다" if on
                      else "전화 요청을 취소했습니다")


@router.post("/ir/contacts/{contact_id}/call-memo", include_in_schema=False)
def set_call_memo(contact_id: int, memo: str = Form(""), back: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """메모를 적는다(비우면 지운다). 누가 언제 적었는지 줄에 남는다.

    새로 적는 것은 켜는 것과 같은 조건이다 — 리마인드가 나갔거나, 이미 표시·
    메모가 있는 사람. 지우는 것은 언제나 된다.
    """
    contact = _flag_contact(db, contact_id, user)
    if ((memo or "").strip() and not call_flags.views(db, [contact.id])
            and not call_flags.reminded(db, contact.id)):
        raise HTTPException(status_code=400,
                            detail="리마인드 카톡이 나간 뒤에 메모할 수 있습니다")
    call_flags.set_memo(db, contact.id, memo, user)
    db.commit()
    return _flag_back(back, "메모를 저장했습니다" if (memo or "").strip()
                      else "메모를 지웠습니다")


# --- 미팅 ------------------------------------------------------------------

@router.post("/ir/meetings", include_in_schema=False)
def create_meeting(
    contact_id: int = Form(...),
    scheduled_at: str = Form(""),
    # 시각은 **선택**이다. 날짜만 아는 단계가 실제로 있고("다음 주 화요일쯤"),
    # 필수로 만들면 그 단계를 기록할 수 없다. 못 읽은 값은 `clean_time` 이
    # 버린다 — 자정 미팅을 지어내는 것보다 빈칸이 정확하다.
    scheduled_time: str = Form(""),
    kind: str = Form("first"),
    # 대면인가 화상인가. **비워 둘 수 있다** — 아직 안 정한 단계가 실제로 있고,
    # 둘 중 하나를 고르게 하면 안 정한 미팅이 `대면` 으로 적혀 나간다.
    meet_mode: str = Form(""),
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
                   # 모르는 값은 **빈 채로** 둔다 — 아무거나 골라 넣으면
                   # 그 말이 캘린더 제목에 실려 나간다.
                   meet_mode=meet_mode if meet_mode in pipeline.MEETING_MODES else None,
                   note=note.strip() or None))
    # 미팅이 잡혔으면 답이 온 것이다.
    cadence.stop_on_reaction(db, contact.id, "미팅이 잡혔습니다")
    db.commit()
    return RedirectResponse("/ir?msg=미팅을 등록했습니다", status_code=303)


@router.post("/ir/meetings/{meeting_id}/mode", include_in_schema=False)
def set_meeting_mode(meeting_id: int, meet_mode: str = Form(""),
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """잡아 둔 미팅이 **대면인지 화상인지** 고른다.

    등록할 때만 고르게 두면 이 칸이 생기기 전에 잡힌 미팅 수백 건은 영영
    빈 채로 남는다 — 그 미팅들의 캘린더 제목에서 그 자리가 계속 빠진다.
    지우는 것도 되어야 한다(`안 정함`): 잘못 골랐을 때 되돌릴 길이 없으면
    사람은 미팅을 지우고 새로 만든다.

    표에서 고르는 순간 저장된다(`team.html` 의 권한 칸과 같은 방식) — 줄마다
    [저장] 을 세우면 손댈 것이 모인 칸이 그만큼 좁아진다.
    """
    meeting = _owned_meeting(db, meeting_id, user)
    meeting.meet_mode = meet_mode if meet_mode in pipeline.MEETING_MODES else None
    db.commit()
    return RedirectResponse("/ir#meetings", status_code=303)


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
                  note: str = Form(""), back: str = Form(""),
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
    if back == "forecast":
        # 매출예상리스트의 재접촉 시기(#68)에서 적었으면 그 화면으로 돌아간다.
        return RedirectResponse("/report/forecast#recontact", status_code=303)
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
