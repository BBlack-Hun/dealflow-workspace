"""Server-rendered HTML pages (Jinja2 SSR)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import DEV_USER_COOKIE, get_current_user, templates
from ..models import IrCompany, SendJob, User, VcContact
from ..ui import MENU, base_ctx as _base_ctx
from .contacts import contact_rows

router = APIRouter(tags=["pages"])

__all__ = ["router", "MENU"]


@router.get("/", include_in_schema=False)
def index():
    return RedirectResponse(url="/deals")


@router.get("/dev/switch-user", include_in_schema=False)
def switch_user(user_id: int, next: str = "/deals", db: Session = Depends(get_db)):
    """개발용 사용자 전환 — 쿠키에 user_id 를 심고 원래 화면으로 돌아간다.

    ★ 인증이 아니다(정식 로그인은 다음 스프린트: 휴대폰번호 + 비밀번호).
    내부 테스트에서 '지금 누구로 보고 있는지'를 바꾸기 위한 스위치일 뿐이다.
    """
    user = db.get(User, user_id)
    target = next if next.startswith("/") else "/deals"  # 외부 주소로 튕기지 않게
    response = RedirectResponse(url=target, status_code=303)
    if user is not None:
        response.set_cookie(DEV_USER_COOKIE, str(user.id), max_age=60 * 60 * 24 * 30,
                            httponly=True, samesite="lax")
    return response


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
    """Sprint 1 stub for not-yet-built menu screens."""
    item = next((m for m in MENU if m["href"] == f"/{placeholder}"), None)
    if item is None:
        # Let unknown paths 404 naturally via a minimal response.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
    ctx = _base_ctx(request, db, user, item["key"])
    ctx.update({"title": item["label"], "sprint": item["sprint"]})
    return templates.TemplateResponse("placeholder.html", ctx)
