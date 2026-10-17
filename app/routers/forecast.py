"""업무 보고 › `매출예상리스트` 탭(개선 과제 #46) — 화면 · 고치기 · 엑셀.

자동 칸을 읽는 규칙은 `services/forecast.py` 한 곳이다.

권한
    보기          기본은 내 줄. 관리자는 팀 전체 · 팀원 한 명(`/report` 와 같은 방식)
    고치기 · 지우기  줄 담당자와 관리자만 — 그 밖은 **404**(줄이 있는지도 안 알린다)
    투자컨설턴트   미들웨어가 막는다(`deps.CONSULTANT_PATHS` 에 없다)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import IrCompany, RevenueForecast, User
from ..services import forecast as svc
from ..ui import base_ctx
from .data_io import _xlsx

router = APIRouter(tags=["forecast"])


def _scope(db: Session, user: User, scope: str, member: int):
    """`(누구 것, 팀 전체인가)` — `/report` 와 같은 판정. 누구 것이 None 이면 팀 전체."""
    if user.role == "admin" and member:
        picked = db.get(User, member)
        if picked is not None:
            return picked, False
    if user.role == "admin" and scope == "team":
        return None, True
    return user, False


def _owned(db: Session, user: User, row_id: int) -> RevenueForecast:
    row = db.get(RevenueForecast, row_id)
    if row is None or (row.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="줄을 찾을 수 없습니다")
    return row


@router.get("/report/forecast", response_class=HTMLResponse, include_in_schema=False)
def forecast_page(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user),
                  scope: str = "", member: int = 0):
    who, team_wide = _scope(db, user, scope, member)
    ctx = base_ctx(request, db, user, active="report")
    rows = svc.views(db, svc.rows_for(db, who))
    ctx.update({
        "rows": rows,
        "company_options": svc.company_options(db),
        "firm_options": svc.firm_options(db, {r["owner"] for r in rows}),
        "columns": svc.COLUMNS,
        "report_tab": "forecast",
        "viewing": who,
        "team_wide": team_wide,
        "scope": scope,
        "members": ([{"id": u.id, "name": u.name} for u in
                     db.execute(select(User).order_by(User.id)).scalars()]
                    if user.role == "admin" else []),
    })
    return templates.TemplateResponse("forecast.html", ctx)


@router.get("/api/export/forecast.xlsx")
def export_forecast(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user),
                    scope: str = "", member: int = 0):
    """화면과 같은 범위 · 같은 칸 차례. 자동 칸은 화면에 보이는 글자 그대로."""
    who, _team = _scope(db, user, scope, member)
    rows = [[v["cells"][f]["text"] for f, _l, _s in svc.COLUMNS]
            for v in svc.views(db, svc.rows_for(db, who))]
    return _xlsx("매출예상리스트.xlsx", "매출예상리스트",
                 [label for _f, label, _s in svc.COLUMNS], rows)


class ForecastIn(BaseModel):
    """칸 이름은 모델 칸 이름 그대로다 — 표의 `data-field` 가 이 이름으로 보낸다."""

    firm: Optional[str] = None
    company_name: Optional[str] = None
    vc_name: Optional[str] = None
    vc_phone: Optional[str] = None
    ceo_name: Optional[str] = None
    ceo_phone: Optional[str] = None
    pre_value: Optional[str] = None
    raise_target: Optional[str] = None
    post_value: Optional[str] = None
    ceo_share: Optional[str] = None
    meeting_plan: Optional[str] = None
    meeting1_done: Optional[str] = None
    meeting2_done: Optional[str] = None
    result_note: Optional[str] = None


def _result(db: Session, row: RevenueForecast) -> dict:
    """저장 뒤 화면이 칸을 다시 그릴 값 — 자동 칸은 서버만 안다."""
    return svc.views(db, [row])[0]


@router.post("/api/forecast")
def create_row(body: ForecastIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """[줄 추가] — 기업명을 받아 내 줄로 세운다. 나머지는 표에서 고친다."""
    if not (body.company_name or "").strip():
        raise HTTPException(status_code=400, detail="기업명을 입력하세요")
    row = RevenueForecast(user_id=user.id)
    svc.assign(db, row, body.model_dump(exclude_unset=True))
    db.add(row)
    db.commit()
    return _result(db, row)


@router.patch("/api/forecast/{row_id}")
def update_row(row_id: int, body: ForecastIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    row = _owned(db, user, row_id)
    svc.assign(db, row, body.model_dump(exclude_unset=True))
    db.commit()
    return _result(db, row)


class CompanyIn(BaseModel):
    company_id: int


@router.post("/api/forecast/{row_id}/company")
def pick_company(row_id: int, body: CompanyIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """같은 이름의 IR 기업이 여럿일 때 [이걸로] — 사람이 고른 것을 잇는다."""
    row = _owned(db, user, row_id)
    if db.get(IrCompany, body.company_id) is None:
        raise HTTPException(status_code=400, detail="IR 기업을 찾을 수 없습니다")
    row.ir_company_id = body.company_id
    db.commit()
    return _result(db, row)


@router.delete("/api/forecast/{row_id}")
def delete_row(row_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    row = _owned(db, user, row_id)
    db.delete(row)
    db.commit()
    return {"deleted": row_id}
