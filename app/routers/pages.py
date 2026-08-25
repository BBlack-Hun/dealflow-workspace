"""Server-rendered HTML pages (Jinja2 SSR)."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import IrCompany, RefSheet, SendJob, SourcingContact, User, VcContact
from ..services import (cadence, deal_history, deal_stage, mailer,
                        sheet_import, sheet_owner)
from ..ui import MENU, base_ctx as _base_ctx
from .companies import BLOCKED_CONTRACT
from .companies import blocked_reason as company_blocked_reason
from .contacts import contact_rows, sheet_tabs

router = APIRouter(tags=["pages"])

__all__ = ["router", "MENU"]


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db),
          user: User = Depends(get_current_user), top: int = 10):
    """메인 = 대시보드. 좌측 위 브랜드를 누르면 여기로 온다.

    투자컨설턴트는 대시보드를 볼 이유가 없다 — 자기 화면으로 보낸다.
    """
    from ..services import dashboard as dash

    if user.role == "consultant":
        return RedirectResponse("/consulting", status_code=303)

    # '내 투자사 선호'를 몇 명까지 볼지 — 10·20·30 중에서 고른다.
    top_n = min(max(top, 5), 30)
    ctx = _base_ctx(request, db, user, "home")
    ctx.update(dash.user_dashboard(db, user, top_n=top_n))
    ctx["top_n"] = top_n
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/deals", response_class=HTMLResponse)
def deals_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # **딜소개 불가로 표시한 기업은 아예 안 보여준다.**
    # 내용이 부족한 기업과는 다르다 — 그건 채우면 되지만, 이건 "보내면 안 되는
    # 곳" 이라 목록에 있는 것만으로 실수로 고를 수 있다.
    companies = db.execute(
        select(IrCompany)
        .where(func.coalesce(IrCompany.contract_status, "") != BLOCKED_CONTRACT)
        .order_by(IrCompany.id)
    ).scalars().all()
    # 소개 가능한 기업을 앞에 세우되, 내용이 부족한 기업도 **감추지 않는다**.
    # 감추면 "왜 내가 넣은 기업이 없지?" 가 되고 어디를 고쳐야 하는지도 알 수 없다.
    companies = sorted(companies, key=lambda c: (not c.introducible, c.name or ""))
    # 발송 대상은 **연결이 끝난 담당자**다. 연결 전 명단(전화·초대 진행 중)이
    # 여기 섞이면 보낼 방도 없는 사람에게 체크를 하게 된다.
    contacts = db.execute(
        select(VcContact)
        .where(VcContact.user_id == user.id,
               VcContact.connect_stage == "connected")
        .order_by(VcContact.id)
    ).scalars().all()
    # 딜소개를 보냈는데 IR 요청·미팅으로 이어지지 않은 담당자.
    # 이들에게는 목록을 또 밀어 넣기보다 무엇을 보고 싶은지 되묻는 편이 답이 온다.
    no_reaction_ids = {
        row["id"] for row in contact_rows(db, user)
        if row["last_deal"] and not (row["ir_total"] or row["meet_total"])
    }
    # 딜 소싱 제안의 대상. 투자사 명단과 다른 표이고 **팀 공용**이다 —
    # 우리 딜을 같이 볼 사람이라 담당을 나눌 것이 아니다.
    # 방 이름이 없으면 보낼 길이 없으므로 그것부터 보이게 정렬한다.
    sourcing_contacts = db.execute(
        select(SourcingContact).order_by(SourcingContact.position, SourcingContact.id)
    ).scalars().all()
    # 갈래는 곧 문구다. 이름을 검색창에 쳐서 찾게 하면 갈래가 몇 개인지도
    # 모른 채 골라야 하므로, 누를 수 있는 필터로 내놓는다. 순서는 명단과
    # 같게 — 좌측 [딜 소싱] 탭에서 보던 순서 그대로여야 헷갈리지 않는다.
    sourcing_buckets = []
    for c in sourcing_contacts:
        if not sourcing_buckets or sourcing_buckets[-1]["name"] != c.bucket:
            match = next((b for b in sourcing_buckets if b["name"] == c.bucket), None)
            if match is None:
                sourcing_buckets.append({"name": c.bucket, "count": 0})
                match = sourcing_buckets[-1]
        else:
            match = sourcing_buckets[-1]
        match["count"] += 1
    ctx = _base_ctx(request, db, user, "deal")
    # 매 회차 같은 기업을 또 보내면 받는 쪽에서는 지난번을 기억 못 한다고 읽는다.
    history = deal_history.annotate(companies, deal_history.last_sent_map(db))
    # 회차명은 **보내는 날에서 만든다.** 손으로 적으면 "8월회차" · "8월 셋째주" ·
    # "0826" 이 섞여 남아, 나중에 몇 주차에 뭘 보냈는지 찾을 때 이력이 갈라진다.
    next_send = cadence.upcoming_send_dates(db, date.today())[0]
    ctx.update({
        "companies": companies,
        "default_batch_title": cadence.batch_title(next_send),
        "history": history,
        "recent_count": sum(1 for h in history.values() if h["recent"]),
        "recent_days": deal_history.RECENT_DAYS,
        "contacts": contacts,
        "sourcing_contacts": sourcing_contacts,
        "sourcing_buckets": sourcing_buckets,
        "no_reaction_ids": no_reaction_ids,
        # 메일 채널은 설정이 있어야 고를 수 있다.
        # 고를 수 있는데 나가지 않는 것이 제일 나쁘다.
        "mail": mailer.status(),
        "blocked_reasons": {c.id: company_blocked_reason(c)
                            for c in companies if not c.introducible},
    })
    return templates.TemplateResponse("deals.html", ctx)


@router.get("/contacts", response_class=HTMLResponse)
def contacts_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    sheet: str = "",
    ref: str = "",
    contact: int = 0,
):
    """내 투자사 (FEATURE_SPEC §3). 표는 SSR, 필터는 브라우저에서 즉시 반응.

    명단(시트)별로 탭을 나눈다. 333명을 한 표에 쏟으면 시트를 쓰던 사람이
    자기 명단을 못 찾는다 — 시트가 나뉘어 있던 구분을 그대로 살린다.
    """
    # 관리자는 팀 전체를 본다 — 누가 어떤 투자사를 맡고 있는지 알아야 한다.
    # 발송 대상 고르기는 여전히 본인 담당분만이다(/deals 참고).
    team_wide = user.role == "admin"
    all_rows = contact_rows(db, user, team_wide=team_wide)
    # 담당은 명단(시트) 단위다 — "내 이름으로 된 탭만 내 담당 투자사".
    contacts = db.execute(
        select(VcContact) if team_wide
        else select(VcContact).where(VcContact.user_id == user.id)
    ).scalars().all()
    tabs = sheet_owner.sheet_rows(db, contacts)

    # 아무 것도 고르지 않았으면 **내가 담당인 명단**을 먼저 연다.
    # 전체(333명)를 먼저 보여주면 매번 자기 명단을 다시 골라야 한다.
    # `sheet=all` 은 일부러 전체를 본다는 뜻이다.
    if sheet == "all":
        selected = ""
    elif any(t["key"] == sheet for t in tabs):
        selected = sheet
    else:
        mine_first = next((t["key"] for t in tabs if t["owner_id"] == user.id), "")
        selected = mine_first
    rows = [r for r in all_rows if selected in r["sheets"]] if selected else all_rows

    # 참고 시트 — 스크립트·가이드처럼 매번 구글 시트를 열어 보던 자료.
    # 지울 수 있게 두었으므로 살아 있는 것만 가져온다.
    ref_sheets = db.execute(
        select(RefSheet).where(RefSheet.is_active == 1)
        .order_by(RefSheet.position, RefSheet.id)
    ).scalars().all()
    picked_ref = next((s for s in ref_sheets if str(s.id) == ref), None)

    stages = Counter(r["connect_stage"] for r in rows)
    # 깔때기는 **지금 탭에 보이는 사람들** 기준이다. 탭이 곧 명단이라,
    # 전체 기준으로 세면 내 명단을 보고 있는데 숫자만 남의 것이 섞인다.
    stage_funnel = deal_stage.funnel(
        {r["id"]: r["deal_stage"] for r in rows})
    ctx = _base_ctx(request, db, user, "vc")
    ctx.update({
        "rows": rows,
        "team_wide": team_wide,
        "tabs": tabs,
        "selected_sheet": selected,
        "members": ([{"id": u.id, "name": u.name} for u in
                     db.execute(select(User).order_by(User.id)).scalars().all()]
                    if team_wide else []),
        # 풀에서 고른 사람을 어느 명단으로 할당할지 — 내 명단만 고를 수 있다.
        "my_sheets": [t for t in tabs if t["owner_id"] == user.id],
        # 풀 탭에서는 골라서 내 명단으로 할당할 수 있다.
        "pool_view": any(t["key"] == selected and t["kind"] == "pool" for t in tabs),
        "total_count": len(all_rows),
        "funnel": stage_funnel,
        # 대시보드의 '내 투자사 선호'에서 눌러 오면 그 사람 상세를 바로 연다 —
        # 무엇을 좋아하는지(선호 분야·라운드) 보려고 누른 것이다.
        "open_contact": contact or 0,
        "ref_sheets": ref_sheets,
        "ref": picked_ref,
        "ref_content": json.loads(picked_ref.content_json) if picked_ref else None,
        "connect_counts": [
            {"key": key, "label": label, "count": stages.get(key, 0)}
            for key, label in sheet_import.CONNECT_LABELS.items()
        ],
    })
    return templates.TemplateResponse("contacts.html", ctx)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(SendJob, job_id)
    # 관리자는 팀 현황에서 넘어와 **누구에게 보냈는지** 조회한다 — 본인 것이
    # 아니어도 읽기는 되어야 한다. 재시도·취소 같은 조작은 API 쪽에서
    # 여전히 본인 것만 허용한다(jobs.py 의 _job_or_404).
    can_view = job is not None and (job.user_id == user.id or user.role == "admin")
    verify = can_view and job.kind == "verify_room"
    ctx = _base_ctx(request, db, user, "vc" if verify else "deal")
    ctx.update({"job_id": job_id, "job_exists": can_view, "verify": verify,
                "readonly": can_view and job.user_id != user.id})
    return templates.TemplateResponse("progress.html", ctx)


@router.get("/{placeholder}", response_class=HTMLResponse)
def placeholder_page(
    placeholder: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """아직 만들지 않은 메뉴의 안내 화면."""
    item = next((m for m in MENU if m["href"] == f"/{placeholder}"), None)
    if item is None:
        # Let unknown paths 404 naturally via a minimal response.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
    ctx = _base_ctx(request, db, user, item["key"])
    ctx.update({"title": item["label"]})
    return templates.TemplateResponse("placeholder.html", ctx)
