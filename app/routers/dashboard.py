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
from ..db import SessionLocal, get_db
from ..deps import (admin_only, consulting_default_for,
                    consulting_is_only_screen, get_current_user,
                    templates)
from ..models import AgentDevice, User, WeeklyRoutine, WeeklyTask
from ..services import auth as auth_svc
from ..services import dashboard as dash
from ..services import backup, readiness, report, today, weekly
from ..ui import base_ctx

router = APIRouter(tags=["dashboard"])

# 만들 수 있는 권한.
#   user       — 딜소개를 하는 사람
#   consultant — 투자컨설턴트 현황만 본다 (딜소개를 하지 않는다)
#   admin      — 팀 전체를 본다
ROLES = {"user", "consultant", "admin"}


def valid_role(raw: str) -> Optional[str]:
    """폼에서 온 권한 값 — 아는 값이면 그대로, 아니면 None.

    **판정은 여기 하나뿐이어야 한다.** 예전에는 계정 생성이 `ROLES` 를 보기
    전에 `("user", "admin")` 을 한 번 더 적어 두었다. 그래서 팀 현황에서
    [투자컨설턴트] 를 골라도 조용히 팀원 계정이 만들어졌고, 만들어 준 사람은
    "컨설턴트인데 메뉴가 다 보인다"는 말을 듣고서야 알았다. 목록이 둘이면
    하나는 반드시 낡는다.
    """
    role = (raw or "").strip()
    return role if role in ROLES else None


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), top: int = dash.TOP_DEFAULT):
    # '내 투자사 선호'를 몇 명까지 볼지.
    top_n = dash.clamp_top(top)
    ctx = base_ctx(request, db, user, active="home")
    ctx.update(dash.user_dashboard(db, user, top_n=top_n))
    ctx["top_n"] = top_n
    ctx["top_choices"] = dash.TOP_CHOICES
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/api/dashboard/top-requesters")
def top_requesters_api(db: Session = Depends(get_db),
                       user: User = Depends(get_current_user), top: int = dash.TOP_DEFAULT):
    """'내 투자사 선호' 목록만. 개수를 바꿀 때 대시보드 전체를 다시 그리면
    스크롤이 맨 위로 튀고, 이 목록 하나 보려고 나머지를 다 기다린다."""
    from ..services import sheet_owner
    from ..services.dashboard import top_requesters

    top_n = dash.clamp_top(top)
    # 담당은 명단(시트) 단위다 — 화면과 같은 범위여야 수가 맞는다.
    ids = [c.id for c in sheet_owner.my_contacts(db, user)]
    return {"rows": top_requesters(db, ids, limit=top_n)}


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


@router.get("/team", response_class=HTMLResponse, include_in_schema=False)
def team_page(request: Request, db: Session = Depends(get_db),
              user: User = Depends(get_current_user), msg: str = "", pw: str = "",
              edit: int = 0):
    """팀 현황. 남의 담당분이 다 보이므로 관리자만 들어온다.

    `pw=1` 은 **'초기 비밀번호를 이 화면에 적어 달라'는 표시**일 뿐이고 값이
    아니다. 값은 서버가 설정에서 읽어 그린다 — 비밀번호를 `msg` 에 실어
    보내면 브라우저 기록과 서버 접근 로그(요청 줄에 질의문자열이 그대로
    남는다)에 남는다. 늘 띄워 두지 않는 것은 어깨너머로 보일 자리를 줄이려는
    것이다(초기화 직후 한 번만 보이면 전달하기에 충분하다).

    `edit=<계정번호>` 는 그 줄 아래에 이름·로그인 ID 수정칸을 펴 달라는 표시다.
    **여는 것도 서버가 한다** — 자바스크립트로 감췄다 폈다 하면 스크립트가 한
    번 어긋나는 날 관리자에게 그 칸으로 가는 길이 아예 없어진다(상세 패널이
    통째로 안 열린 적이 있다). 이 화면은 SSR 이므로 주소로 여는 편이 같은
    결과를 훨씬 적은 수단으로 낸다. 닫기는 `/team` 으로 돌아오는 링크다.
    """
    admin_only(user)
    ctx = base_ctx(request, db, user, active="admin")
    ctx.update(dash.admin_dashboard(db))
    ctx["msg"] = msg
    ctx["initial_password"] = config.INITIAL_PASSWORD if pw == "1" else ""
    ctx["edit_id"] = edit
    # 백업이 조용히 멈춘 것을 아무도 모르는 상태가 이 기능이 생긴 이유다.
    # 관리자가 매일 여는 화면에 상태를 띄운다 — 되돌리기 화면까지 들어가야
    # 보인다면, 되돌릴 일이 생기고 나서야 백업이 없다는 것을 알게 된다.
    ctx["backup"] = backup.health()
    return templates.TemplateResponse("team.html", ctx)


# --- 데이터 되돌리기 (관리자 전용) --------------------------------------------
#
# 화면은 **서버가 그린 그대로** 움직인다. 고르는 것도 확인하는 것도 평범한
# 링크와 폼이다 — 팀 현황의 수정칸을 주소(`?edit=`)로 여는 것과 같은 이유로,
# 스크립트가 한 번 어긋나는 날 되돌릴 방법이 통째로 사라지면 안 된다.
# 되돌리기는 하필 **무언가 잘못됐을 때** 쓰는 기능이다.

@router.get("/team/restore", response_class=HTMLResponse, include_in_schema=False)
def restore_page(request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user),
                 pick: str = "", msg: str = ""):
    """되돌릴 수 있는 지점 목록. `?pick=<파일>` 이면 **무엇이 바뀌는지**까지.

    두 걸음으로 나눈 이유: 날짜만 보고 누르면 오늘 들어온 기업 열두 곳이
    사라지는 것을 누른 뒤에야 안다. 고른 지점과 지금의 차이를 표로 세어
    보여 주고 나서 확인을 받는다.

    셈은 고른 지점 하나에 대해서만 한다. 목록에 있는 파일이 여든 개가 넘어
    (배포마다 뜬 것이 쌓였다) 전부 세면 화면 여는 것만으로 느려진다 —
    목록에는 파일이 들고 있는 값싼 것(날짜·크기·알렘빅 판)만 띄운다.
    """
    admin_only(user)
    ctx = base_ctx(request, db, user, active="admin")
    picked = backup.find_point(pick) if pick else None
    ctx.update({
        "page_title": "데이터 되돌리기",
        "health": backup.health(),
        "points": backup.restore_points(),
        "picked": picked,
        "diff": backup.diff(picked) if picked else [],
        "risk": backup.login_risk(picked, user.phone) if picked else None,
        # 발송이 돌고 있으면 되돌리지 않는다. 화면에서 미리 막아 두고,
        # 누르는 쪽(아래 apply)에서 한 번 더 본다 — 화면을 열어 둔 채로
        # 발송이 시작될 수 있다.
        "sending": backup.sending_now(db),
        "keep_days": backup.KEEP_DAILY_DAYS,
        "msg": msg,
    })
    return templates.TemplateResponse("restore.html", ctx)


@router.post("/team/restore/apply", include_in_schema=False)
def restore_apply(name: str = Form(""), db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """고른 지점으로 되돌린다.

    **화면에서 막은 것을 여기서 다시 본다.** 확인 화면을 열어 둔 채로 발송이
    시작될 수 있고, 주소를 직접 두드리면 확인 화면을 건너뛴다. 막는 판정은
    화면과 같은 함수를 읽는다(`backup.sending_now`).
    """
    admin_only(user)
    from urllib.parse import quote

    def back(message: str, pick: str = "") -> RedirectResponse:
        where = f"/team/restore?msg={quote(message)}"
        return RedirectResponse(where + (f"&pick={quote(pick)}" if pick else ""),
                                status_code=303)

    # 폼으로 온 파일 이름을 그대로 열지 않는다 — 목록에 실제로 있는 것만 받는다.
    point = backup.find_point((name or "").strip())
    if point is None:
        return back("되돌릴 지점을 찾을 수 없습니다")

    running = backup.sending_now(db)
    if running:
        # 회차 중간에 DB 가 옛 것으로 바뀌면 어디까지 나갔는지 기록이 어긋나고,
        # 이미 카톡을 받은 투자사에게 **또 나간다.**
        return back(
            f"발송 회차 {running[0].id}번이 {running[0].status} 상태입니다 — "
            "끝나거나 멈춘 뒤에 되돌려 주세요", point.name)

    # 우리 연결부터 놓는다. 되돌리기는 DB 안쪽을 통째로 덮으므로, 이 요청이
    # 쥐고 있는 연결이 남아 있으면 그만큼 부딪힐 자리가 생긴다.
    db.close()
    try:
        result = backup.restore(point)
    except backup.BackupError as exc:
        return back(str(exc), point.name)
    except Exception as exc:  # noqa: BLE001 - 사유를 화면에 보여 준다
        return back(f"되돌리지 못했습니다: {exc}", point.name)

    note = f"{result['restored']} 지점으로 되돌렸습니다"
    if result.get("migrated_to"):
        note += f" (스키마를 {result['migrated_to']} 로 올렸습니다)"
    note += f". 되돌리기 직전 상태는 {result['safety']} 에 남겨 두었습니다"

    # **로그인 세션도 DB 안에 있다**(`sessions` 표). 되돌리면 지금 쓰는 세션이
    # 그 시점 것으로 바뀌어 대개 사라지고, 누른 사람은 결과 알림조차 못 본 채
    # 로그인 화면으로 튕긴다(실제로 그랬다) — 되돌렸는지 아닌지도 모르는 상태다.
    #
    # 되돌아가야 하는 것은 **데이터**이지 '지금 누가 쓰고 있는가' 가 아니므로,
    # 계정이 그 시점에도 있으면 세션을 다시 붙여 준다. 계정 자체가 없으면
    # 붙일 수 없고, 그때는 로그인 화면이 맞다(확인 화면에서 미리 경고한다).
    resp = back(note)
    fresh = SessionLocal()
    try:
        again = fresh.execute(
            select(User).where(User.phone == user.phone, User.role == "admin")
        ).scalars().first()
        if again is not None:
            auth_svc.set_session_cookie(
                resp, auth_svc.create_session(fresh, again))
    finally:
        fresh.close()
    return resp


@router.get("/report", response_class=HTMLResponse, include_in_schema=False)
def report_page(request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user),
                month: str = "", scope: str = "", member: int = 0,
                span: str = "month", year: str = ""):
    """주간·월간 업무 보고. 시트에 손으로 옮겨 적던 표를 기록에서 뽑는다."""
    from datetime import date as _date

    today = _date.today()
    year_, mon = today.year, today.month
    if month:
        try:
            year_, mon = (int(x) for x in month.split("-")[:2])
        except (ValueError, TypeError):
            pass
    # 연간 보기는 해만 고른다 — "올해 몇 건이나 했나" 를 보려고 열두 달을
    # 하나씩 눌러 보고 있었다.
    if year:
        try:
            year_ = int(year)
        except (ValueError, TypeError):
            pass
    yearly_view = span == "year"
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
    who = None if team_wide else target
    if yearly_view:
        ctx.update(report.yearly(db, year_, who, today))
    else:
        ctx.update(report.monthly(db, year_, mon, who, today))
    ctx.update({
        "viewing": None if team_wide else target,
        "members": ([{"id": u.id, "name": u.name} for u in
                     db.execute(select(User).order_by(User.id)).scalars().all()]
                    if user.role == "admin" else []),
    })
    ctx.update({
        # 달·해를 드롭다운으로 고른다. 단추로 늘어놓으면 두 해치가 스무 개가
        # 넘어 줄바꿈되고, 정작 찾는 달이 어디 있는지 안 보인다.
        "month_options": [(y, m, f"{y}-{m:02d}")
                          for y, m in report.recent_months(today, count=36)],
        "year_options": report.selectable_years(today),
        "selected": f"{year_}-{mon:02d}",
        "selected_year": year_,
        "yearly_view": yearly_view,
        "span": span,
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
    admin_only(user)
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
    admin_only(user)
    normalized = auth_svc.normalize_phone(phone)
    if len(normalized) < 10:
        return RedirectResponse("/team?msg=휴대폰번호를+다시+확인해+주세요", status_code=303)
    if db.execute(select(User).where(User.phone == normalized)).scalars().first():
        return RedirectResponse("/team?msg=이미+등록된+번호입니다", status_code=303)

    # 모르는 값이면 가장 좁은 권한으로 떨어뜨린다 — 오타 하나로 관리자가
    # 생기는 것보다 낫다(권한 판정이 전부 이 값으로 갈린다).
    role = valid_role(role) or "user"

    # 투자현황을 처음부터 켤지는 **역할이 기본값만 정한다**(그 뒤로는 팀 현황에서
    # 누구든 끄고 켠다). 투자컨설턴트를 꺼진 채로 만들면 그 계정에는 볼 화면이
    # 하나도 없어서, 만들어 준 사람이 무엇을 빠뜨렸는지 알기 어렵다.
    member = User(name=name.strip() or normalized, phone=normalized, role=role,
                  can_view_consulting=1 if consulting_default_for(role) else 0,
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


@router.post("/team/members/{member_id}/profile", include_in_schema=False)
def edit_member_profile(
    member_id: int,
    name: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이름·로그인 ID 고치기 — **계정을 사람에게서 사람에게로 넘긴다.**

    퇴사자가 생기면 계정을 지우거나 새로 만드는 대신 **입사자 이름과 휴대폰
    번호로 갈아 끼워 그대로 물려준다.** 담당 투자사(`VcContact.user_id`)와
    발송 이력(`SendJob.user_id`)이 계정에 붙어 있어서, 새로 만들면 그 이력이
    통째로 끊긴다 — 계정 정지(`/deactivate`)가 지우지 않고 남기는 것과 같은
    이유다. 오타로 만들어진 이름을 고치는 데도 같은 길을 쓴다.

    **본인 것은 못 바꾼다.** 형제 라우터들(권한·초기화·정지)이 본인을 막는
    이유와 같고, 여기는 한 가지가 더 있다: 번호를 바꾸면 아래에서 세션을
    끊으므로 관리자가 제 번호를 잘못 적으면 그 자리에서 로그아웃되고 **옛
    번호로도 새 번호로도 못 들어온다**(오타 난 번호는 본인이 받을 수 없는
    번호다). 되돌리려면 DB 를 직접 고쳐야 하는데, 그게 이 화면이 없애려던
    상황이다. 관리자를 여럿 두는 이유가 곧 이것이라 다른 관리자가 바꿔 준다.
    """
    admin_only(user)
    if member_id == user.id:
        return RedirectResponse("/team?msg=본인+계정은+다른+관리자가+바꿉니다",
                                status_code=303)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")

    # 로그인 ID 는 휴대폰번호다. 저장·비교 양쪽이 같은 규칙으로 정규화돼야
    # 하이픈 유무로 로그인이 실패하지 않는다(`normalize_phone` 주석 참고).
    # 계정 생성과 **같은 기준**으로 거른다 — 두 곳이 갈리면 하나는 곧 낡는다.
    normalized = auth_svc.normalize_phone(phone)
    if len(normalized) < 10:
        return RedirectResponse(
            f"/team?edit={member_id}&msg=휴대폰번호를+다시+확인해+주세요",
            status_code=303)
    # 이미 쓰는 번호면 막는다. 두 계정이 같은 번호를 가지면 그 번호로 온
    # 로그인이 **어느 계정으로 갈지 알 수 없다**(`authenticate` 는 먼저 찾은
    # 하나를 집는다). 자기 자신은 뺀다 — 이름만 고치려고 번호를 그대로 두고
    # 저장하는 것이 정상 동작이다.
    taken = db.execute(
        select(User).where(User.phone == normalized, User.id != member_id)
    ).scalars().first()
    if taken is not None:
        return RedirectResponse(
            f"/team?edit={member_id}&msg=이미+등록된+번호입니다",
            status_code=303)

    phone_changed = member.phone != normalized
    # 이름이 비면 번호를 이름으로 쓴다 — 계정 생성과 같은 규칙이다.
    # (입력칸이 required 라 보통은 안 오지만, 이름 없는 줄이 표에 서면 그
    #  줄이 누구인지 화면에서 알 길이 없다.)
    member.name = name.strip() or normalized
    member.phone = normalized

    note = "+이름을+바꿨습니다"
    if phone_changed:
        # **발송 프로그램 연결키(토큰)를 새로 발급한다.**
        #
        # 그대로 두면 퇴사자 PC 에 남은 키가 계속 유효하다. 그 PC 의 에이전트는
        # 새 담당자가 만든 발송 잡을 가로채 **퇴사자 카톡으로 실제 투자사에게**
        # 보낸다 — 이 저장소가 가장 크게 치는 사고다(오발송 막으려고
        # `DEALFLOW_TEST_ROOM` 까지 둔다). '한 계정 = 한 PC' 도 계정 생성이
        # 이미 못 박아 둔 원칙이다.
        #
        # 새 키를 받는 길이 화면에 있으므로 되돌릴 수 없는 처리가 아니다 —
        # 새 담당자가 로그인해 [발송 프로그램 설치]에서 다시 내려받으면
        # 설정 파일에 새 키가 자동으로 박힌다(routers/setup.py).
        #
        # 이름만 고칠 때는 건드리지 않는다. 오타를 고치는 일에 남의 발송
        # 프로그램을 끊을 이유가 없다.
        device = db.execute(
            select(AgentDevice).where(AgentDevice.user_id == member.id)
        ).scalars().first()
        if device is not None:
            device.token = f"agt_{secrets.token_hex(16)}"
            # 붙어 있던 PC 의 흔적도 지운다. 남겨 두면 팀 현황의 발송 프로그램
            # 칸이 이제 못 붙는 기기를 '연결됨 · 퇴사자PC' 로 계속 보여 준다.
            device.last_poll_at = None
            device.hostname = ""
            device.agent_version = ""
            device.sender = None
        note = ("+로그인+ID+를+바꿨습니다.+열린+세션을+끊고+발송+프로그램+"
                "연결키를+새로+발급했습니다+—+새+담당자가+[발송+프로그램+설치]"
                "에서+다시+받아야+발송됩니다")
    db.commit()
    if phone_changed:
        # **그 계정의 열린 세션을 끊는다.** 세션은 번호가 아니라 쿠키의 토큰으로
        # 사는 것이라, 남겨 두면 퇴사자 PC 가 로그인 화면을 다시 거치지 않고 새
        # 담당자의 화면을 계속 쓴다. 이름만 고칠 때는 끊지 않는다 — 오타를
        # 고치는 일에 그 사람을 로그아웃시킬 이유가 없다.
        # (`/reset-password`·`/deactivate` 가 같은 이유로, 같은 자리에서 끊는다.)
        auth_svc.destroy_all_sessions(db, member.id)
    # 이름을 감싸서 넣는다 — 이름에 `&` 가 섞이면 질의문자열이 그 자리에서
    # 갈려 안내가 잘린다(`/reset-password` 도 같은 이유로 감싼다).
    from urllib.parse import quote

    return RedirectResponse(f"/team?msg={quote(member.name)}+님의{note}",
                            status_code=303)


@router.post("/team/members/{member_id}/role", include_in_schema=False)
def change_member_role(
    member_id: int,
    role: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이미 만들어진 계정의 권한 바꾸기.

    계정을 만든 뒤에는 권한을 고칠 길이 없었다. 그래서 잘못 만들어진 계정
    (컨설턴트로 골랐는데 팀원으로 저장되던 버그)을 고치려면 계정을 정지하고
    새로 만드는 수밖에 없었는데, 그러면 담당 투자사와 발송 이력이 끊긴다.

    바뀐 권한은 다음 요청부터 바로 먹는다 — 권한은 요청마다 DB 에서 읽는다.
    """
    admin_only(user)
    # 본인 권한은 못 바꾼다. 관리자가 스스로를 내리면 팀 현황에 다시 들어올
    # 길이 없어져, 되돌리려면 DB 를 직접 고쳐야 한다.
    if member_id == user.id:
        return RedirectResponse("/team?msg=본인+권한은+바꿀+수+없습니다", status_code=303)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    # 권한을 바꾸러 온 요청이 모르는 값 때문에 조용히 팀원으로 떨어지면
    # 안 된다 — 계정 생성과 달리 여기서는 되돌려 보내고 알린다.
    picked = valid_role(role)
    if picked is None:
        return RedirectResponse("/team?msg=알+수+없는+권한입니다", status_code=303)
    member.role = picked
    db.commit()
    return RedirectResponse(f"/team?msg={member.name}+님의+권한을+바꿨습니다",
                            status_code=303)


@router.post("/team/members/{member_id}/consulting", include_in_schema=False)
def toggle_consulting(
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """투자현황 화면을 볼 수 있게 하거나 막는다 — **누구든 끄고 켠다.**

    예전에는 관리자·투자컨설턴트가 역할만으로 열려 있어 여기서 못 껐다. 그런데
    이 화면을 누구에게 열지는 그때그때 사람이 정하는 일이지 역할로 굳어 있을
    일이 아니다. 이제 칸 하나(`can_view_consulting`)가 전부이고, 역할이 하는
    일은 새 계정의 기본값뿐이다(`deps.consulting_default_for`).

    **본인은 못 끈다.** 관리자가 스스로를 잠그면 그 화면에 다시 들어갈 길이
    없어져, 되돌리려면 다른 관리자를 부르거나 DB 를 직접 고쳐야 한다. 바로 위
    권한 바꾸기가 같은 이유로 본인을 막고 있다 — 그 결을 따른다. 표에도 본인
    줄에는 단추 대신 상태만 적는다.

    **투자컨설턴트를 끄면 그 계정에는 볼 화면이 하나도 남지 않는다**
    (`deps.CONSULTANT_PATHS` 가 허용 목록이라 `/consulting` 이 전부다). 막는
    것 자체는 막지 않는다 — 관리자가 알고 끄는 일이 있다. 다만 **모르고 끄는
    것**을 막으려고, 팀 현황이 누르기 전에 확인 문구를 띄우고 여기서는 끈 뒤
    안내에 같은 사실을 적는다. 판정은 `deps.consulting_is_only_screen` 한 곳이라
    두 문구가 갈릴 자리가 없다.
    """
    admin_only(user)
    if member_id == user.id:
        return RedirectResponse("/team?msg=본인+투자현황은+끄고+켤+수+없습니다",
                                status_code=303)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    member.can_view_consulting = 0 if member.can_view_consulting else 1
    db.commit()
    state = "볼 수 있게" if member.can_view_consulting else "볼 수 없게"
    note = ""
    if not member.can_view_consulting and consulting_is_only_screen(member):
        note = "+—+이+계정에는+이제+볼+화면이+없습니다"
    return RedirectResponse(
        f"/team?msg={member.name}+님을+투자현황을+{state}+했습니다{note}",
        status_code=303)


@router.post("/team/members/{member_id}/reset-password", include_in_schema=False)
def reset_member_password(
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """비밀번호 초기화 — 잠긴 팀원을 화면에서 되살린다.

    비밀번호를 잊으면 화면에는 되돌릴 길이 하나도 없었다. 실제로 관리자가
    로그인을 못 해 서버에 들어가 DB 를 직접 고쳐야 했다. 팀이 늘고 입퇴사가
    생기는 중이라 그 일은 반복된다.

    **어떤 값으로 되돌리는가 — 팀 공통 초기값(`config.INITIAL_PASSWORD`).**
    계정을 만들 때 넣는 값과 같은 값이다. 계정마다 난수를 만드는 쪽이 값이
    겹치지 않아 좋아 보이지만, 난수는 만든 순간 **관리자에게 보여 줄 길**이
    필요하다. 이 화면의 안내는 `?msg=...` 로 나르므로 그 자리에 넣으면
    비밀번호가 브라우저 기록과 서버 접근 로그에 남는다. 공통값은 관리자가
    이미 아는 값이라 응답에 실어 나를 것이 없다. '초기 비밀번호' 라는 개념이
    계정 생성과 여기 둘로 갈리지도 않는다 — 값이 두 군데면 하나는 반드시
    낡는다(`valid_role` 이 같은 이유로 판정을 한 곳에 모아 두었다).

    여러 사람이 같은 값을 갖게 되는 약점은 **계정 생성이 이미 지고 있던 것과
    같은** 것이지 여기서 새로 생기지 않는다. 아래 `must_change_password=1`
    과 팀 현황의 '비밀번호 미변경' 표시로 그 창을 좁힌다. 공개된 저장소
    기본값 그대로 운영에 뜨는 것은 `config.assert_ready()` 가 이미 막는다.

    **관리자끼리는 서로 초기화할 수 있다.** 관리자를 여럿 두는 이유가 곧
    "한 사람이 잠겨도 팀이 멈추지 않게" 이기 때문이다. 서로를 막으면 관리자가
    잠겼을 때 다시 ssh 로 돌아가는데, 그게 이 기능이 없애려던 상황이다.
    권한 변경·계정 정지도 이미 다른 관리자에게 열려 있다(본인만 막는다).
    """
    admin_only(user)
    # 본인 것은 이 길로 못 바꾼다 — 관리자 자신은 `/account/password` 에서
    # 현재 비밀번호를 대고 바꾼다. 여기서 허용하면 잠깐 자리를 비운 관리자
    # 화면 앞에 앉은 사람이 현재 비밀번호를 모르고도 갈아 끼울 수 있다.
    if member_id == user.id:
        return RedirectResponse("/team?msg=본인+비밀번호는+계정+메뉴에서+바꿉니다",
                                status_code=303)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    member.password_hash = auth_svc.hash_password(config.INITIAL_PASSWORD)
    # 첫 로그인 때 반드시 새 비밀번호를 정하게 한다 — 관리자가 아는 값으로
    # 계속 쓰면 "본인만 아는 비밀번호" 라는 전제가 깨진다.
    member.must_change_password = 1
    db.commit()
    # 열려 있던 세션은 끊는다. 변경 요구는 **로그인할 때만** 걸리므로
    # (routers/auth.py) 세션을 남겨 두면 그 기기는 로그인 화면을 다시 거치지
    # 않고, 바꾸지 않은 채 계속 쓴다. 비밀번호 변경(`/account/password`)과
    # 퇴사 처리도 같은 이유로 세션을 끊는다.
    auth_svc.destroy_all_sessions(db, member.id)
    # 주소에는 비밀번호를 싣지 않는다 — `pw=1` 은 '초기 비밀번호를 적어
    # 달라'는 표시일 뿐이고, 값은 팀 현황이 설정에서 읽어 그린다.
    #
    # 이름은 감싸서 넣는다. 여기만 안내 뒤에 표시(`&pw=1`)가 하나 더 붙으므로,
    # 이름에 `&` 가 섞이면 질의문자열이 그 자리에서 갈려 표시가 떨어져 나가거나
    # 반대로 이름만으로 표시가 켜진다(`/team/mail-test` 도 같은 이유로 감싼다).
    from urllib.parse import quote

    return RedirectResponse(
        f"/team?msg={quote(member.name)}+님의+비밀번호를+초기화했습니다&pw=1",
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
    admin_only(user)
    if member_id == user.id:
        return RedirectResponse("/team?msg=본인+계정은+정지할+수+없습니다", status_code=303)
    member = db.get(User, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    member.is_active = 0
    db.commit()
    auth_svc.destroy_all_sessions(db, member.id)
    return RedirectResponse(f"/team?msg={member.name}+계정을+정지했습니다", status_code=303)
