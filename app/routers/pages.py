"""Server-rendered HTML pages (Jinja2 SSR)."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import IrCompany, SendJob, User, VcContact
from ..services import mailer, sheet_import
from ..ui import MENU, base_ctx as _base_ctx
from .companies import blocked_reason as company_blocked_reason
from .contacts import contact_rows

router = APIRouter(tags=["pages"])

__all__ = ["router", "MENU"]


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """메인 = 대시보드. 좌측 위 'dealflow' 를 누르면 여기로 온다."""
    from ..services import dashboard as dash

    ctx = _base_ctx(request, db, user, "home")
    ctx.update(dash.user_dashboard(db, user))
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/deals", response_class=HTMLResponse)
def deals_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    companies = db.execute(select(IrCompany).order_by(IrCompany.id)).scalars().all()
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
    ctx = _base_ctx(request, db, user, "deal")
    ctx.update({
        "companies": companies,
        "contacts": contacts,
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
):
    """내 투자사 (FEATURE_SPEC §3). 표는 SSR, 필터는 브라우저에서 즉시 반응."""
    # 관리자는 팀 전체를 본다 — 누가 어떤 투자사를 맡고 있는지 알아야 한다.
    # 발송 대상 고르기는 여전히 본인 담당분만이다(/deals 참고).
    team_wide = user.role == "admin"
    rows = contact_rows(db, user, team_wide=team_wide)
    stages = Counter(r["connect_stage"] for r in rows)
    ctx = _base_ctx(request, db, user, "vc")
    ctx.update({
        "rows": rows,
        "team_wide": team_wide,
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
    mine = job is not None and job.user_id == user.id
    # 방 연결 확인 잡도 같은 진행 화면을 쓰되, 문구는 '발송'이 아니어야 한다
    # (확인 잡은 아무것도 보내지 않는다 — 사용자가 오해하면 안 되는 지점).
    verify = mine and job.kind == "verify_room"
    ctx = _base_ctx(request, db, user, "vc" if verify else "deal")
    ctx.update({"job_id": job_id, "job_exists": mine, "verify": verify})
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
