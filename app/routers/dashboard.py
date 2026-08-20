"""대시보드 — 로그인하면 처음 보는 화면.

두 가지가 있고 보는 목적이 다르다.

- `/` · `/dashboard` : 내 화면. "다음 발송까지 내가 뭘 고쳐야 하나."
- `/team`            : 팀 현황(관리자 전용). "팀이 굴러가고 있나."

좌측 위 **dealflow** 를 누르면 `/` 로 온다. 관리자는 팀 현황이 기본 화면이
되는 편이 자연스럽지만, 관리자도 자기 담당분을 보내므로 `/` 는 그대로 두고
팀 현황은 메뉴로 간다.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import get_current_user, templates
from ..models import AgentDevice, User
from ..services import auth as auth_svc
from ..services import dashboard as dash
from ..services import readiness, today
from ..ui import base_ctx

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    ctx = base_ctx(request, db, user, active="home")
    ctx.update(dash.user_dashboard(db, user))
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/todo", response_class=HTMLResponse, include_in_schema=False)
def todo_page(request: Request, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """오늘 할 일. 흩어져 있던 것을 한 화면에 모은다."""
    ctx = base_ctx(request, db, user, active="check")
    ctx.update(today.build(db, user))
    return templates.TemplateResponse("todo.html", ctx)


@router.get("/readiness", response_class=HTMLResponse, include_in_schema=False)
def readiness_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), mode: str = ""):
    """회차 준비 점검. `?mode=live` 로 실발송 기준으로도 볼 수 있다."""
    rehearsal = None
    if mode == "live":
        rehearsal = False
    elif mode == "rehearsal":
        rehearsal = True
    ctx = base_ctx(request, db, user, active="ready")
    ctx.update(readiness.report(db, user, rehearsal=rehearsal))
    ctx["mode"] = mode
    return templates.TemplateResponse("readiness.html", ctx)


def _admin_only(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 사용할 수 있습니다")


@router.get("/team", response_class=HTMLResponse, include_in_schema=False)
def team_page(request: Request, db: Session = Depends(get_db),
              user: User = Depends(get_current_user), msg: str = ""):
    """팀 현황. 남의 담당분이 다 보이므로 관리자만 들어온다."""
    _admin_only(user)
    ctx = base_ctx(request, db, user, active="admin")
    ctx.update(dash.admin_dashboard(db))
    ctx["msg"] = msg
    return templates.TemplateResponse("team.html", ctx)


@router.post("/team/members", include_in_schema=False)
def create_member(
    name: str = Form(...),
    phone: str = Form(...),
    role: str = Form("user"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """팀원 계정 생성 — 관리자가 화면에서 끝낸다.

    발송 프로그램 연결키(토큰)를 함께 발급한다. **한 계정 = 한 PC** 가 원칙이라
    같은 키를 두 대에 넣으면 발송이 어느 쪽으로 갈지 알 수 없다.
    """
    _admin_only(user)
    normalized = auth_svc.normalize_phone(phone)
    if len(normalized) < 10:
        return RedirectResponse("/team?msg=휴대폰번호를+다시+확인해+주세요", status_code=303)
    if role not in ("user", "admin"):
        role = "user"
    if db.execute(select(User).where(User.phone == normalized)).scalars().first():
        return RedirectResponse("/team?msg=이미+등록된+번호입니다", status_code=303)

    member = User(name=name.strip() or normalized, phone=normalized, role=role,
                  password_hash=auth_svc.hash_password(config.INITIAL_PASSWORD),
                  must_change_password=1)
    db.add(member)
    db.flush()
    db.add(AgentDevice(user_id=member.id, token=f"agt_{secrets.token_hex(16)}",
                       hostname="", agent_version=""))
    db.commit()
    return RedirectResponse(
        f"/team?msg={member.name}+계정을+만들었습니다.+초기+비밀번호는+팀+공통값입니다",
        status_code=303)


@router.post("/team/members/{member_id}/consulting", include_in_schema=False)
def toggle_consulting(
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """투자현황 화면을 볼 수 있게 하거나 막는다(관리자는 항상 볼 수 있다)."""
    _admin_only(user)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    member.can_view_consulting = 0 if member.can_view_consulting else 1
    db.commit()
    state = "볼 수 있게" if member.can_view_consulting else "볼 수 없게"
    return RedirectResponse(f"/team?msg={member.name}+님을+투자현황을+{state}+했습니다",
                            status_code=303)


@router.post("/team/members/{member_id}/deactivate", include_in_schema=False)
def deactivate_member(
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """퇴사 처리 — 계정을 지우지 않고 정지한다.

    지워 버리면 그 사람이 담당하던 투자사와 발송 이력이 주인을 잃는다.
    로그인만 막고 기록은 남긴다. 열려 있던 세션도 함께 끊는다.
    """
    _admin_only(user)
    if member_id == user.id:
        return RedirectResponse("/team?msg=본인+계정은+정지할+수+없습니다", status_code=303)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    member.is_active = 0
    db.commit()
    auth_svc.destroy_all_sessions(db, member.id)
    return RedirectResponse(f"/team?msg={member.name}+계정을+정지했습니다", status_code=303)
