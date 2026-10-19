"""관리자 메뉴 `분야 기준 목록` — 목록 고치기(#2) · IR 기업 현황 정리.

**전부 관리자만이다**(`deps.admin_only`). 목록의 이름 하나를 바꾸면 팀 전체의
IR 기업 현황 값과 투자사 선호분야 값이 같이 바뀌고, 정리는 수백 줄을 한 판에
고친다 — 팀원 화면에 단추를 둘 일이 아니다. 팀원은 투자사 줄에서 **목록에서
골라 적기만** 한다(`contacts.html` 의 선호 투자분야 칸).

값을 바꾸는 길은 모두 두 걸음이다.

    미리보기    몇 줄이 무엇에서 무엇으로 바뀌는지 — **아무것도 쓰지 않는다**
    반영        서버가 계획을 **다시 세워** 고른 것만 적고, 한 번에 커밋한다

화면이 보낸 값을 그대로 적지 않는 이유는 `ir_sector_cleanup` 머리말에 있다.

**투자사 선호분야 재분류(#30)는 뺐다**(10/19). 10/18 에 한 번 반영했고, 다시
돌리면 원치 않는 데이터 이동이 생긴 적이 있다 — 탭도 길(`/api/taxonomy/
pref-sectors`)도 없앤다. `?tab=pref` 로 와도 기준 목록이 뜬다.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import admin_only, get_current_user, templates
from ..models import User
from ..services import ir_sector_cleanup
from ..services import taxonomy as tx
from ..ui import base_ctx

router = APIRouter(tags=["taxonomy"])

#: 좌측 메뉴의 열쇠(`ui.MENU`).
MENU_KEY = "taxonomy"


def _fail(exc: Exception):
    raise HTTPException(status_code=400, detail=str(exc))


@router.get("/taxonomy", response_class=HTMLResponse, include_in_schema=False)
def taxonomy_page(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user), tab: str = ""):
    """목록 · IR 정리를 한 화면의 탭으로."""
    admin_only(user)
    ctx = base_ctx(request, db, user, active=MENU_KEY)
    ctx.update({
        "tab": "ir" if tab == "ir" else "list",
        "tree": tx.tree(db, include_hidden=True),
        "cleanup_only": tx.CLEANUP_ONLY_MAJORS,
    })
    return templates.TemplateResponse("taxonomy.html", ctx)


# ── 목록 ────────────────────────────────────────────────────────────────────

class TermIn(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    target_id: Optional[int] = None
    step: Optional[int] = None
    hidden: Optional[bool] = None


@router.get("/api/taxonomy")
def get_tree(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """목록 — 관리자는 숨긴 줄까지, 팀원은 고를 거리만."""
    if user.role == "admin":
        return {"tree": tx.tree(db, include_hidden=True)}
    return {"tree": tx.picker_tree(db)}


@router.post("/api/taxonomy/terms")
def add_term(body: TermIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    admin_only(user)
    tx.ensure_seed(db)
    try:
        row = tx.add(db, body.name or "", body.parent_id)
    except tx.TaxonomyError as exc:
        _fail(exc)
    db.commit()
    return {"id": row.id, "tree": tx.tree(db, include_hidden=True)}


def _plan(db: Session, term_id: int, op: str, body: TermIn):
    if op == "rename":
        return tx.plan_rename(db, term_id, body.name or "")[2]
    if op == "merge":
        if not body.target_id:
            raise tx.TaxonomyError("합칠 곳을 고르세요")
        return tx.plan_merge(db, term_id, body.target_id)[2]
    if op == "move":
        if not body.parent_id:
            raise tx.TaxonomyError("옮길 대분류를 고르세요")
        return tx.plan_move(db, term_id, body.parent_id)[2]
    raise tx.TaxonomyError(f"모르는 고침입니다: {op}")


@router.post("/api/taxonomy/terms/{term_id}/preview/{op}")
def preview_term(term_id: int, op: str, body: TermIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """이름 바꾸기 · 합치기 · 옮기기를 하면 **몇 줄이** 바뀌는가. 쓰지 않는다."""
    admin_only(user)
    try:
        edits = _plan(db, term_id, op, body)
    except tx.TaxonomyError as exc:
        _fail(exc)
    samples = [{"field": e.field, "old": e.old, "new": e.new,
                "name": getattr(e.obj, "name", "") or ""} for e in edits[:20]]
    return {**tx.impact(edits), "samples": samples}


@router.post("/api/taxonomy/terms/{term_id}/{op}")
def change_term(term_id: int, op: str, body: TermIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """목록 한 줄을 고친다. 값까지 바꾸는 고침은 **한 트랜잭션**이다."""
    admin_only(user)
    result: dict = {}
    try:
        if op == "rename":
            result = tx.rename(db, term_id, body.name or "")
        elif op == "merge":
            if not body.target_id:
                raise tx.TaxonomyError("합칠 곳을 고르세요")
            result = tx.merge(db, term_id, body.target_id)
        elif op == "move":
            if not body.parent_id:
                raise tx.TaxonomyError("옮길 대분류를 고르세요")
            result = tx.move(db, term_id, body.parent_id)
        elif op == "hide":
            tx.set_hidden(db, term_id, bool(body.hidden))
        elif op == "order":
            tx.reorder(db, term_id, body.step or 0)
        else:
            raise tx.TaxonomyError(f"모르는 고침입니다: {op}")
    except tx.TaxonomyError as exc:
        db.rollback()
        _fail(exc)
    db.commit()
    return {**result, "tree": tx.tree(db, include_hidden=True)}


# ── IR 기업 현황 정리 ───────────────────────────────────────────────────────

class CleanupItem(BaseModel):
    id: int
    major: Optional[str] = None


class CleanupIn(BaseModel):
    items: List[CleanupItem] = []


@router.get("/api/taxonomy/ir-cleanup")
def ir_cleanup_preview(db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    admin_only(user)
    return ir_sector_cleanup.preview(db)


@router.post("/api/taxonomy/ir-cleanup")
def ir_cleanup_apply(body: CleanupIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    admin_only(user)
    try:
        result = ir_sector_cleanup.apply(db, [i.model_dump() for i in body.items])
    except tx.TaxonomyError as exc:
        db.rollback()
        _fail(exc)
    return {**result, **ir_sector_cleanup.preview(db)}

