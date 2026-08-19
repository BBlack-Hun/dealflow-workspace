"""Server-rendered HTML pages (Jinja2 SSR)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import agent_status, get_current_user, templates
from ..models import IrCompany, SendJob, User, VcContact

router = APIRouter(tags=["pages"])

# Sidebar menu (FEATURE_SPEC §0.2 권장안, usage-frequency order).
MENU = [
    {"key": "check", "label": "오늘 할 일", "href": "/todo", "sprint": 4},
    {"key": "deal", "label": "딜소개 보내기", "href": "/deals", "sprint": 1},
    {"key": "req", "label": "IR·미팅 관리", "href": "/ir", "sprint": 2},
    {"key": "vc", "label": "내 투자사", "href": "/contacts", "sprint": 2},
    {"key": "su", "label": "딜 기업 DB", "href": "/companies", "sprint": 2},
    {"key": "admin", "label": "팀 현황", "href": "/team", "sprint": 4},
    {"key": "setup", "label": "에이전트 설치", "href": "/setup", "sprint": 1},
]


def _base_ctx(request: Request, db: Session, user: User, active: str) -> dict:
    return {
        "request": request,
        "menu": MENU,
        "active": active,
        "user": user,
        "agent": agent_status(db),
        "test_room": config.TEST_ROOM,
    }


@router.get("/", include_in_schema=False)
def index():
    return RedirectResponse(url="/deals")


@router.get("/deals", response_class=HTMLResponse)
def deals_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    companies = db.execute(select(IrCompany).order_by(IrCompany.id)).scalars().all()
    introducible = [c for c in companies if c.introducible]
    contacts = db.execute(
        select(VcContact)
        .where(VcContact.user_id == user.id, VcContact.channel_kakao == 1)
        .order_by(VcContact.id)
    ).scalars().all()
    ctx = _base_ctx(request, db, user, "deal")
    ctx.update({"companies": introducible, "contacts": contacts})
    return templates.TemplateResponse("deals.html", ctx)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(SendJob, job_id)
    ctx = _base_ctx(request, db, user, "deal")
    ctx.update({"job_id": job_id, "job_exists": job is not None and job.user_id == user.id})
    return templates.TemplateResponse("progress.html", ctx)


@router.get("/{placeholder}", response_class=HTMLResponse)
def placeholder_page(
    placeholder: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sprint 1 stub for not-yet-built menu screens."""
    item = next((m for m in MENU if m["href"] == f"/{placeholder}"), None)
    if item is None:
        # Let unknown paths 404 naturally via a minimal response.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
    ctx = _base_ctx(request, db, user, item["key"])
    ctx.update({"title": item["label"], "sprint": item["sprint"]})
    return templates.TemplateResponse("placeholder.html", ctx)
