"""관리자 메뉴 `컬럼 관리` + 표에서 추가 칸 값 적기(개선 과제 #6 · #7 · #8 · #12 · #46).

칸을 붙이고 · 이름을 바꾸고 · 옮기고 · 자리를 고르고 · 숨기는 것은 **전부 관리자만**이다
(`deps.admin_only`, 10/16 사용자 결정). 지우는 길은 없다 — 숨긴다.

값을 적는 길(`PUT /api/custom-values/…`)은 팀원 것이다. **고칠 수 있는 줄은 그
표의 판정 그대로다**(`_row`) — 판정을 여기 새로 적으면 표에서는 못 고치는 줄의
칸을 이 길로 고칠 수 있게 된다. 투자컨설턴트 계정은 미들웨어가 이 주소를
열어 두고(`deps.CONSULTANT_PATHS`), 여기서 자기 화면(투자컨설턴트) 줄만 받는다.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..clock import stamp_text
from ..db import get_db
from ..deps import admin_only, can_open, doer, get_current_user, templates
from ..models import CustomColumn, User
from ..services import custom_columns as svc
from ..ui import base_ctx

router = APIRouter(tags=["custom_columns"])

#: 좌측 메뉴의 열쇠(`ui.MENU`).
MENU_KEY = "columns"


def _back(target: str, msg: str = "") -> RedirectResponse:
    query = {"target": target}
    if msg:
        query["msg"] = msg
    return RedirectResponse("/columns?" + urlencode(query), status_code=303)


def _column(db: Session, column_id: int) -> CustomColumn:
    col = db.get(CustomColumn, column_id)
    if col is None:
        raise HTTPException(status_code=404, detail="칸을 찾을 수 없습니다")
    return col


@router.get("/columns", response_class=HTMLResponse, include_in_schema=False)
def columns_page(request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user),
                 target: str = "", msg: str = ""):
    admin_only(user)
    target = target if target in svc.TARGETS else next(iter(svc.TARGETS))
    ctx = base_ctx(request, db, user, active=MENU_KEY)
    cols = svc.columns(db, target, include_hidden=True)
    ctx.update({
        "targets": svc.TARGETS,
        "target": target,
        "cols": cols,
        # 고른 자리 — 이름이 바뀐 머리글이면 새 이름(`svc.anchor_of` · #63).
        "afters": {c.id: svc.anchor_of(c) for c in cols},
        "anchors": svc.anchors(target),
        "kinds": svc.KINDS,
        "name_max": svc.NAME_MAX,
        "msg": msg,
    })
    return templates.TemplateResponse("columns.html", ctx)


@router.post("/columns", include_in_schema=False)
def add_column(target: str = Form(...), name: str = Form(""), kind: str = Form("memo"),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    admin_only(user)
    try:
        col = svc.add(db, target, name, kind, user.id)
    except svc.ColumnError as exc:
        return _back(target, str(exc))
    db.commit()
    return _back(target, f"'{col.name}' 칸을 붙였습니다")


@router.post("/columns/{column_id}/rename", include_in_schema=False)
def rename_column(column_id: int, name: str = Form(""),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    admin_only(user)
    col = _column(db, column_id)
    try:
        svc.rename(db, col, name)
    except svc.ColumnError as exc:
        db.rollback()
        return _back(col.target, str(exc))
    db.commit()
    return _back(col.target, f"이름을 '{col.name}' 로 바꿨습니다")


@router.post("/columns/{column_id}/move", include_in_schema=False)
def move_column(column_id: int, step: int = Form(...),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    admin_only(user)
    col = _column(db, column_id)
    svc.move(db, col, step)
    db.commit()
    return _back(col.target)


@router.post("/columns/{column_id}/place", include_in_schema=False)
def place_column(column_id: int, after: str = Form(""),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """어느 기존 칸 뒤에 둘지(0110). 비면 맨 끝."""
    admin_only(user)
    col = _column(db, column_id)
    try:
        svc.place(col, after)
    except svc.ColumnError as exc:
        db.rollback()
        return _back(col.target, str(exc))
    db.commit()
    return _back(col.target, f"'{col.name}' 칸을 "
                 + (f"'{col.after_key}' 뒤에 둡니다" if col.after_key else "맨 끝에 둡니다"))


@router.post("/columns/{column_id}/hidden", include_in_schema=False)
def hide_column(column_id: int, hidden: int = Form(...),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    admin_only(user)
    col = _column(db, column_id)
    svc.set_hidden(col, bool(hidden))
    db.commit()
    return _back(col.target, f"'{col.name}' 칸을 " + ("숨겼습니다 — 적힌 값은 그대로 남습니다"
                                                    if hidden else "다시 보이게 했습니다"))


# ── 표에서 값 적기 ────────────────────────────────────────────────────────

def _row(db: Session, user: User, row_table: str, row_id: int):
    """고칠 수 있는 줄 하나 — **그 표의 PATCH 가 쓰는 판정을 그대로** 부른다."""
    from ..models import IrCompany, SeriesACompany, SourcingContact

    if row_table in ("ir_companies", "series_a_companies", "sourcing_contacts"):
        # 팀 공용 표 — 로그인한 누구나 고친다(각 표의 PATCH 와 같다).
        model = {"ir_companies": IrCompany, "series_a_companies": SeriesACompany,
                 "sourcing_contacts": SourcingContact}[row_table]
        row = db.get(model, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="줄을 찾을 수 없습니다")
        return row
    if row_table == "revenue_forecasts":
        from .forecast import _owned
        return _owned(db, user, row_id)
    if row_table == "consulting_companies":
        from ..models import ConsultingCompany
        from .consulting import owned, require_access
        require_access(user)
        return owned(db, ConsultingCompany, row_id, user, "기업")
    if row_table == "vc_contacts":
        from .contacts import _owned
        return _owned(db, row_id, user)
    raise HTTPException(status_code=404, detail="모르는 표입니다")


class ValueIn(BaseModel):
    column_id: int
    value: Optional[str] = ""


@router.put("/api/custom-values/{row_table}/{row_id}")
def put_value(row_table: str, row_id: int, body: ValueIn,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = svc.ROW_TARGET.get(row_table)
    if target is None:
        raise HTTPException(status_code=404, detail="모르는 표입니다")
    # 투자컨설턴트 계정은 이 주소까지는 온다(자기 화면 칸을 적어야 하므로) —
    # 그 밖의 화면 줄은 여기서 끊는다. 판정은 미들웨어와 같은 함수다.
    if not can_open(user, svc.TARGETS[target]["href"]):
        raise HTTPException(status_code=403, detail="이 화면의 칸을 고칠 수 없습니다")
    row = _row(db, user, row_table, row_id)
    col = db.get(CustomColumn, body.column_id)
    if col is None:
        raise HTTPException(status_code=404, detail="칸을 찾을 수 없습니다")
    try:
        value = svc.write(db, row, col, body.value, doer(user).id)
    except svc.ColumnError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    # `수정한 날짜` 칸이 있는 표는 이 값으로 그 자리에서 바뀐다(`companies.js` ·
    # `contacts.js` 의 `updated_at`) — 칸 값을 고친 것도 그 줄을 고친 것이다.
    return {"value": value, "updated_at": stamp_text(row.updated_at)}
