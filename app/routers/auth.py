"""로그인 / 로그아웃 / 비밀번호 변경 (휴대폰번호 + 비밀번호)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import (VIEW_AS_COOKIE, admin_only, can_open, get_current_user,
                    home_for, may_view_as, templates)
from ..ui import PASSWORD_CHANGED, base_ctx
from ..models import User
from ..services import account_rename
from ..services import auth as auth_svc

router = APIRouter(tags=["auth"])
log = logging.getLogger(__name__)


def _safe_next(value: str) -> str:
    """오픈 리다이렉트 방지 — **내부 경로만** 남기고 나머지는 버린다.

    비어 있는 것을 여기서 `/` 로 메우지 않는다. 그 `/` 는 로그인 화면의 숨은
    칸에 박혀 다시 돌아오므로, 아무 데도 가려 하지 않은 사람이 '대시보드에
    가려던 사람'이 된다 — 컨설턴트에게 `/` 는 막힌 곳이라 되튕겨 나온다.
    갈 곳을 정하는 것은 사람을 알고 난 뒤 `deps.home_for` 하나다.
    """
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return ""


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, next: str = "/", error: str = ""):
    return templates.TemplateResponse(
        request, "login.html",
        {"request": request, "next": _safe_next(next), "error": error},
    )


@router.post("/login", include_in_schema=False)
def login(
    request: Request,
    phone: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    target = _safe_next(next)
    # 앞의 프록시(Caddy)가 적은 진짜 주소다 — uvicorn 이 프록시 머리글을 믿게 띄운다.
    ip = request.client.host if request.client else ""
    # 잠겨 있으면 비밀번호를 견주지도 않는다(`auth_svc.login_locked` 머리말).
    if auth_svc.login_locked(phone, ip):
        return RedirectResponse(
            url=f"/login?next={target}&error=locked", status_code=303
        )
    user = auth_svc.authenticate(db, phone, password)
    if user is None:
        locked = auth_svc.note_login_failure(phone, ip)
        # 번호는 가려서 남긴다 — 번호 가리기는 `auth_svc.redact` 한 곳이다.
        log.warning("로그인 실패: 번호 %s · IP %s%s",
                    auth_svc.redact(auth_svc.normalize_phone(phone)), ip,
                    " — 15분 잠금" if locked else "")
        # 없는 번호인지 틀린 비밀번호인지 구분해 알리지 않는다(계정 존재 여부 노출 방지).
        return RedirectResponse(
            url=f"/login?next={target}&error=1", status_code=303
        )
    auth_svc.note_login_success(phone)

    token = auth_svc.create_session(db, user, request.headers.get("user-agent", ""))
    # 관리자가 만들어준 임시 비밀번호면 먼저 바꾸게 한다.
    if user.must_change_password:
        target = "/account/password"
    elif not target or not can_open(user, target):
        # 가려던 곳이 없거나 그 사람에게 막힌 곳이면 **첫 화면**으로 보낸다.
        # 비밀번호를 바꾼 뒤와 같은 함수를 읽는다 — 두 길이 서로 다른 곳으로
        # 가면, 처음 들어온 사람은 로그인할 때와 바꾼 뒤가 다른 화면이라
        # 어디가 제자리인지 알 수 없다.
        target = home_for(user)
    resp = RedirectResponse(url=target, status_code=303)
    auth_svc.set_session_cookie(resp, token)
    # 같은 브라우저에서 앞사람이 켜 둔 `팀원 화면으로 보기` 를 물려받지 않게.
    resp.delete_cookie(VIEW_AS_COOKIE)
    return resp


# 상태를 바꾸는 길이라 **POST 만 받는다.** 화면의 로그아웃은 작은 폼이다
# (`base.html` · `consulting_blocked.html`).
@router.post("/logout", include_in_schema=False)
def logout(request: Request, db: Session = Depends(get_db)):
    auth_svc.destroy_session(db, request.cookies.get(auth_svc.SESSION_COOKIE))
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(auth_svc.SESSION_COOKIE)
    resp.delete_cookie(VIEW_AS_COOKIE)
    return resp


# ── 팀원 화면으로 보기 (#3) ──────────────────────────────────────────────────
# `/account` 아래라 이 두 길은 보는 중에도 관리자 본인으로 열린다
# (`deps.VIEW_AS_OWN_PATHS`). 누구를 고를 수 있는지는 `deps.may_view_as` 하나.

@router.post("/account/view-as", include_in_schema=False)
def view_as_on(member_id: int = Form(0), next: str = Form(""),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    admin_only(user)
    if not may_view_as(user, db.get(User, member_id)):
        raise HTTPException(status_code=404, detail="볼 수 있는 팀원이 아닙니다")
    resp = RedirectResponse(_safe_next(next) or "/", status_code=303)
    # 수명을 주지 않는다 — 브라우저를 닫으면 내 화면으로 돌아온다.
    resp.set_cookie(VIEW_AS_COOKIE, str(member_id), httponly=True, samesite="lax")
    return resp


@router.post("/account/view-as/off", include_in_schema=False)
def view_as_off(next: str = Form(""), user: User = Depends(get_current_user)):
    resp = RedirectResponse(_safe_next(next) or "/", status_code=303)
    resp.delete_cookie(VIEW_AS_COOKIE)
    return resp


@router.get("/account/password", response_class=HTMLResponse, include_in_schema=False)
def password_page(request: Request, error: str = "",
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    # base.html 이 요구하는 공통 컨텍스트(menu/agent 등)를 그대로 재사용한다.
    #
    # 성공 알림(`?ok=1`)을 받던 자리는 없앴다 — 바꾸고 나면 여기 머무르지 않고
    # 첫 화면으로 나가므로, 남겨 두면 아무도 닿지 않는 두 번째 알림이 된다.
    ctx = base_ctx(request, db, user, active="")
    ctx.update({"error": error,
                "must_change": bool(user.must_change_password)})
    return templates.TemplateResponse(request, "password.html", ctx)


@router.post("/account/password", include_in_schema=False)
def change_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
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
    # 바꾸고 나면 **쓸 수 있는 첫 화면**으로 내보낸다. 여기 머무르면 초기
    # 비밀번호로 처음 들어온 사람은 바꾼 뒤에도 같은 화면을 보고, 어디로 가야
    # 하는지 스스로 찾아야 한다. 어디가 첫 화면인지는 `deps.home_for` 하나가
    # 정한다(로그인 직후와 같은 자리) — 여기 `/` 를 적으면 컨설턴트는 막힌
    # 화면으로 간다. 바뀌었다는 알림은 표시를 달아 도착지까지 데려간다.
    resp = RedirectResponse(f"{home_for(user)}?{PASSWORD_CHANGED}=1", status_code=303)
    auth_svc.set_session_cookie(resp, token)
    return resp


# ── 이름 바꾸기 ─────────────────────────────────────────────────────────────
# 같은 사람의 표시 이름을 바꾸고 그 이름이 든 탭 · 담당자 칸을 같이 옮긴다
# (`services/account_rename`). **본인은 누구나, 남의 것은 관리자만** — 팀 현황의 줄마다
# 이 화면으로 오는 링크가 있고(`?member=`), 팀 현황을 못 여는 팀원은 사이드바에서 온다.
# 한 화면이 미리보기(GET `?to=`)와 바꾸기(POST)를 같이 한다 — 미리 본 계획의 지문
# (`expect`)이 맞아야 바뀐다.
#
# `/account` 아래라 팀원 화면으로 보는 중에도 관리자 본인으로 열린다
# (`deps.VIEW_AS_OWN_PATHS`). 그래도 **보는 중에는 바꾸지 않는다** — 화면 위 띠는 팀원
# 이름을 말하는데 바뀌는 것은 관리자 이름이라 헷갈리고, 대리 보기는 보기 · 수정까지가 원칙이다.
VIEW_AS_RENAME_BLOCKED = ("팀원 화면으로 보는 중에는 이름을 바꿀 수 없습니다 — "
                          "[내 화면으로] 돌아간 뒤 바꿔 주세요")


def _rename_target(db: Session, user: User, member_id: int) -> User:
    """이름을 바꿀 계정 — 본인이 아니면 관리자만."""
    if not member_id or member_id == user.id:
        return user
    admin_only(user)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    return member


@router.get("/account/name", response_class=HTMLResponse, include_in_schema=False)
def name_page(request: Request, member: int = 0, to: str = "", msg: str = "",
              db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    target = _rename_target(db, user, member)
    ctx = base_ctx(request, db, user, active="")
    ctx.update({"member": target, "to": to, "msg": msg, "plan": None, "refused": "",
                "max_name": account_rename.MAX_NAME,
                "viewing": getattr(request.state, "view_as", None) is not None,
                "view_as_blocked": VIEW_AS_RENAME_BLOCKED})
    if to.strip():
        try:
            ctx["plan"] = account_rename.plan(db, target, to)
        except account_rename.RenameRefused as exc:
            ctx["refused"] = str(exc)
    return templates.TemplateResponse(request, "account_name.html", ctx)


@router.post("/account/name", include_in_schema=False)
def rename_account(request: Request, member: int = Form(0), name: str = Form(""),
                   expect: str = Form(""), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    from urllib.parse import quote

    target = _rename_target(db, user, member)
    back = f"/account/name?member={target.id}&to={quote(name)}&msg="
    if getattr(request.state, "view_as", None) is not None:
        return RedirectResponse(back + quote(VIEW_AS_RENAME_BLOCKED), status_code=303)
    try:
        done = account_rename.apply(db, target, name, actor_user_id=user.id,
                                    expect=expect, path=request.url.path, method="POST")
    except account_rename.RenameRefused as exc:
        db.rollback()
        return RedirectResponse(back + quote(str(exc)), status_code=303)
    db.commit()
    text = (f"이름을 {done.before} → {done.after} 로 바꿨습니다 "
            f"(탭 {len(done.tabs)}개 · 담당자 칸 {done.total}줄)")
    if target.id != user.id:
        return RedirectResponse(f"/team?msg={quote(text)}", status_code=303)
    return RedirectResponse(f"/account/name?msg={quote(text)}", status_code=303)
