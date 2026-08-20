"""Server-rendered HTML pages (Jinja2 SSR)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import IrCompany, SendJob, User, VcContact
from ..ui import MENU, base_ctx as _base_ctx
from .companies import blocked_reason as companyblocked_reason
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
    contacts = db.execute(
        select(VcContact)
        .where(VcContact.user_id == user.id, VcContact.channel_kakao == 1)
        .order_by(VcContact.id)
    ).scalars().all()
    ctx = _base_ctx(request, db, user, "deal")
    ctx.update({
        "companies": companies,
        "contacts": contacts,
        "blocked_reasons": {c.id: companyblocked_reason(c)
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
    ctx = _base_ctx(request, db, user, "vc")
    ctx.update({"rows": contact_rows(db, user)})
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
