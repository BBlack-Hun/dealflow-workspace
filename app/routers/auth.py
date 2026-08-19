"""로그인 / 로그아웃 / 비밀번호 변경 (휴대폰번호 + 비밀번호)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..ui import base_ctx
from ..models import User
from ..services import auth as auth_svc

router = APIRouter(tags=["auth"])


def _safe_next(value: str) -> str:
    """오픈 리다이렉트 방지 — 내부 경로만 허용한다."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/deals"


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, next: str = "/deals", error: str = ""):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next": _safe_next(next), "error": error},
    )


@router.post("/login", include_in_schema=False)
def login(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    next: str = Form("/deals"),
    db: Session = Depends(get_db),
):
    target = _safe_next(next)
    user = auth_svc.authenticate(db, phone, password)
    if user is None:
        # 없는 번호인지 틀린 비밀번호인지 구분해 알리지 않는다(계정 존재 여부 노출 방지).
        return RedirectResponse(
            url=f"/login?next={target}&error=1", status_code=303
        )

    token = auth_svc.create_session(db, user, request.headers.get("user-agent", ""))
    # 관리자가 만들어준 임시 비밀번호면 먼저 바꾸게 한다.
    if user.must_change_password:
        target = "/account/password"
    resp = RedirectResponse(url=target, status_code=303)
    resp.set_cookie(
        auth_svc.SESSION_COOKIE, token,
        max_age=60 * 60 * 24 * auth_svc.SESSION_DAYS,
        httponly=True, samesite="lax",
    )
    return resp


@router.get("/logout", include_in_schema=False)
@router.post("/logout", include_in_schema=False)
def logout(request: Request, db: Session = Depends(get_db)):
    auth_svc.destroy_session(db, request.cookies.get(auth_svc.SESSION_COOKIE))
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(auth_svc.SESSION_COOKIE)
    return resp


@router.get("/account/password", response_class=HTMLResponse, include_in_schema=False)
def password_page(request: Request, error: str = "", ok: str = "",
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    # base.html 이 요구하는 공통 컨텍스트(menu/agent 등)를 그대로 재사용한다.
    ctx = base_ctx(request, db, user, active="")
    ctx.update({"error": error, "ok": ok,
                "must_change": bool(user.must_change_password)})
    return templates.TemplateResponse("password.html", ctx)


@router.post("/account/password", include_in_schema=False)
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not auth_svc.verify_password(current_password, user.password_hash):
        return RedirectResponse("/account/password?error=현재+비밀번호가+맞지+않습니다",
                                status_code=303)
    if new_password != confirm_password:
        return RedirectResponse("/account/password?error=새+비밀번호가+서로+다릅니다",
                                status_code=303)
    problem = auth_svc.password_problem(new_password)
    if problem:
        return RedirectResponse(f"/account/password?error={problem}", status_code=303)

    user.password_hash = auth_svc.hash_password(new_password)
    user.must_change_password = 0
    db.commit()

    # 비밀번호가 바뀌면 다른 기기의 세션은 모두 끊고, 이 기기만 새로 로그인시킨다.
    auth_svc.destroy_all_sessions(db, user.id)
    token = auth_svc.create_session(db, user, request.headers.get("user-agent", ""))
    resp = RedirectResponse("/account/password?ok=1", status_code=303)
    resp.set_cookie(
        auth_svc.SESSION_COOKIE, token,
        max_age=60 * 60 * 24 * auth_svc.SESSION_DAYS,
        httponly=True, samesite="lax",
    )
    return resp
