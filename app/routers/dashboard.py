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
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import get_current_user, templates
from ..models import AgentDevice, User, WeeklyRoutine, WeeklyTask
from ..services import auth as auth_svc
from ..services import dashboard as dash
from ..services import readiness, report, today, weekly
from ..ui import base_ctx

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), top: int = 10):
    # '내 투자사 선호'를 몇 명까지 볼지 — 10~20 사이에서 사용자가 고른다.
    top_n = min(max(top, 5), 20)
    ctx = base_ctx(request, db, user, active="home")
    ctx.update(dash.user_dashboard(db, user, top_n=top_n))
    ctx["top_n"] = top_n
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/todo", response_class=HTMLResponse, include_in_schema=False)
def todo_page(request: Request, db: Session = Depends(get_db),
              user: User = Depends(get_current_user), week: str = ""):
    """주간 업무 — 손으로 적는 체크리스트 + 시스템이 아는 일 + 회차 준비 점검.

    셋을 한 화면에 둔다. 예전엔 '오늘 할 일'과 '회차 준비 점검'이 따로 있었는데,
    아침에 두 군데를 열어야 했다.
    """
    from datetime import date as _date

    today_ = _date.today()
    start = weekly.week_start(_as_week(week) or today_)

    weekly.ensure_routines(db, user)
    weekly.fill_week(db, user, start)

    rows = weekly.task_rows(db, user, start, today_)
    ctx = base_ctx(request, db, user, active="check")
    ctx.update(today.build(db, user))          # 시스템이 아는 일 (읽기 전용)
    ctx.update(readiness.report(db, user))     # 회차 준비 점검 (합침)
    ctx.update({
        "tasks": rows,
        "summary": weekly.summary(rows),
        "week_start": start,
        "week_label": weekly.week_label(start),
        "prev_week": (start - timedelta(days=7)).isoformat(),
        "next_week": (start + timedelta(days=7)).isoformat(),
        "this_week": weekly.week_start(today_).isoformat(),
        "is_this_week": start == weekly.week_start(today_),
        "carry": weekly.carry_over_candidates(db, user, start),
        "statuses": weekly.STATUS_LABELS,
        "weekday_names": weekly.WEEKDAYS,
        "routines": db.execute(
            select(WeeklyRoutine).where(WeeklyRoutine.user_id == user.id)
            .order_by(WeeklyRoutine.id)).scalars().all(),
        "weekday_label": weekly.weekday_label,
        "today_iso": today_.isoformat(),
    })
    return templates.TemplateResponse("todo.html", ctx)


def _as_week(value: str):
    from datetime import date as _date

    try:
        return _date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# --- 주간 업무 고치기 --------------------------------------------------------

def _owned_task(db: Session, task_id: int, user: User) -> WeeklyTask:
    row = db.get(WeeklyTask, task_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="업무를 찾을 수 없습니다")
    return row


@router.post("/todo/tasks", include_in_schema=False)
def add_task(category: str = Form(""), title: str = Form(...),
             due_date: str = Form(""), week: str = Form(""),
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    from datetime import date as _date

    start = weekly.week_start(_as_week(week) or _date.today())
    if not title.strip():
        return RedirectResponse(f"/todo?week={start}", status_code=303)
    last = db.execute(
        select(WeeklyTask.position).where(WeeklyTask.user_id == user.id,
                                          WeeklyTask.week_start == start.isoformat())
        .order_by(WeeklyTask.position.desc()).limit(1)
    ).scalar() or 0
    db.add(WeeklyTask(user_id=user.id, week_start=start.isoformat(),
                      category=category.strip() or None, title=title.strip(),
                      due_date=(due_date.strip() or None), position=last + 1))
    db.commit()
    return RedirectResponse(f"/todo?week={start}", status_code=303)


class TaskPatch(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None


@router.patch("/api/todo/tasks/{task_id}")
def patch_task(task_id: int, body: TaskPatch, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """칸을 눌러 바로 고친다. 손으로 적던 표라 고치는 일이 잦다."""
    task = _owned_task(db, task_id, user)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in weekly.STATUS_LABELS:
        raise HTTPException(status_code=400, detail="알 수 없는 상태입니다")
    if "title" in data and not (data["title"] or "").strip():
        raise HTTPException(status_code=400, detail="내용을 비울 수 없습니다")
    for field, value in data.items():
        setattr(task, field, (value or "").strip() or None
                if isinstance(value, str) and field != "status" else value)
    db.commit()
    return {"id": task.id, "status": task.status}


@router.post("/todo/tasks/{task_id}/delete", include_in_schema=False)
def delete_task(task_id: int, week: str = Form(""),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    db.delete(_owned_task(db, task_id, user))
    db.commit()
    return RedirectResponse(f"/todo?week={week}" if week else "/todo", status_code=303)


@router.post("/todo/carry-over", include_in_schema=False)
def carry_over(week: str = Form(""), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """지난 주 미완료를 이번 주로. 그냥 두면 지난 주 화면에 묻혀 잊힌다."""
    from datetime import date as _date

    start = weekly.week_start(_as_week(week) or _date.today())
    moved = weekly.carry_over(db, user, start)
    return RedirectResponse(f"/todo?week={start}&moved={moved}", status_code=303)


@router.post("/todo/routines", include_in_schema=False)
def add_routine(category: str = Form(""), title: str = Form(...),
                weekdays: str = Form(""), time_of_day: str = Form(""),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    if title.strip():
        db.add(WeeklyRoutine(user_id=user.id, category=category.strip() or "기타",
                             title=title.strip(),
                             weekdays=",".join(str(d) for d in
                                               weekly.parse_weekdays(weekdays)),
                             time_of_day=time_of_day if time_of_day in ("am", "pm") else None))
        db.commit()
    return RedirectResponse("/todo", status_code=303)


class RoutineIn(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    time_of_day: Optional[str] = None


@router.patch("/api/todo/routines/{routine_id}")
def update_routine(routine_id: int, body: RoutineIn,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """표에서 눌러 바로 고친다 — 항목·세부업무·오전/오후."""
    row = db.get(WeeklyRoutine, routine_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="반복 업무를 찾을 수 없습니다")
    if body.category is not None:
        row.category = body.category.strip() or "기타"
    if body.title is not None and body.title.strip():
        row.title = body.title.strip()
    if body.time_of_day is not None:
        row.time_of_day = body.time_of_day if body.time_of_day in ("am", "pm") else None
    db.commit()
    return {"ok": True}


@router.post("/todo/routines/{routine_id}/delete", include_in_schema=False)
def delete_routine(routine_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    row = db.get(WeeklyRoutine, routine_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="반복 업무를 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return RedirectResponse("/todo", status_code=303)


@router.get("/readiness", include_in_schema=False)
def readiness_redirect(mode: str = ""):
    """회차 준비 점검은 주간 업무 화면으로 합쳤다.

    여러 곳에서 이 주소를 부르고 있어서 길만 돌려 둔다.
    """
    return RedirectResponse("/todo#readiness", status_code=307)


@router.get("/readiness/detail", response_class=HTMLResponse, include_in_schema=False)
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


@router.get("/report", response_class=HTMLResponse, include_in_schema=False)
def report_page(request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user),
                month: str = "", scope: str = "", member: int = 0):
    """주간·월간 업무 보고. 시트에 손으로 옮겨 적던 표를 기록에서 뽑는다."""
    from datetime import date as _date

    today = _date.today()
    year, mon = today.year, today.month
    if month:
        try:
            year, mon = (int(x) for x in month.split("-")[:2])
        except (ValueError, TypeError):
            pass
    # 관리자는 팀 전체를 볼 수 있다. 기본은 본인 것.
    team_wide = user.role == "admin" and scope == "team"
    # 관리자는 팀원 한 사람 것만 따로 볼 수도 있어야 한다 — 전체만 보면
    # 누가 얼마나 했는지는 보이지만 그 사람과 이야기할 자료가 안 나온다.
    target = user
    if user.role == "admin" and member:
        picked = db.get(User, member)
        if picked is not None:
            target, team_wide = picked, False
    ctx = base_ctx(request, db, user, active="report")
    ctx.update(report.monthly(db, year, mon, None if team_wide else target, today))
    ctx.update({
        "viewing": None if team_wide else target,
        "members": ([{"id": u.id, "name": u.name} for u in
                     db.execute(select(User).order_by(User.id)).scalars().all()]
                    if user.role == "admin" else []),
    })
    ctx.update({
        "months": [(y, m, f"{y}-{m:02d}") for y, m in report.recent_months(today)],
        "selected": f"{year}-{mon:02d}",
        "team_wide": team_wide,
        "can_team": user.role == "admin",
        "scope": scope,
    })
    return templates.TemplateResponse("report.html", ctx)


@router.post("/team/mail-test", include_in_schema=False)
def test_mail(to: str = Form(""), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """설정이 맞는지 한 통 보내 본다.

    비밀번호가 틀렸는지 포트를 잘못 잡았는지는 실제로 보내 봐야 안다.
    회차 당일에 알게 되면 늦다.
    """
    _admin_only(user)
    from urllib.parse import quote

    from ..services import mailer

    target = (to or "").strip() or mailer.load_settings().from_address
    result = mailer.send_test(target)
    return RedirectResponse(f"/team?msg={quote(result['detail'])}", status_code=303)


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
