"""문구 템플릿 관리 — 만들고 고쳐서 회차마다 골라 쓴다.

딜소개 문구는 매번 같지 않다(첫 연락/재연락, 리마인드, 미팅 요청, 연말 인사 …).
그래서 같은 종류(kind)라도 템플릿을 여러 개 두고 발송 화면에서 고르게 한다.

팀 기본 템플릿(user_id=NULL)은 모두에게 보이고, 본인이 만든 것은 본인에게만 보인다.
남의 것을 고치거나 지울 수 없다(팀 기본은 관리자만).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates as jinja
from ..models import MessageTemplate, User
from ..ui import base_ctx

router = APIRouter(tags=["templates"])

# 화면에 보여줄 종류와 설명. 문구가 어디에 쓰이는지 알아야 제대로 쓴다.
KINDS = [
    ("opening_first", "인사말 — 첫 연락", "처음 딜소개를 보내는 담당자에게"),
    ("opening_re", "인사말 — 재연락", "이미 보낸 적 있는 담당자에게"),
    ("closing_day1", "안내문 — 딜소개", "기업 목록 위에 오는 안내 문구"),
    ("closing_remind", "안내문 — 리마인드", "발송 후 6~7일 뒤 후속"),
    ("closing_meeting", "안내문 — 미팅 요청", "발송 후 11~14일 뒤 후속"),
    ("ask_preference", "문구만 — 선호 분야 묻기", "반응이 없는 담당자에게 기업 목록 없이 이 문구만"),
    ("ir_delivery", "IR 자료 전달", "자료를 먼저 보낸 뒤 뒤따라 보내는 문구"),
]
KIND_LABELS = {k: label for k, label, _ in KINDS}

# 문구에 쓸 수 있는 치환 변수 (화면 안내용)
VARIABLES = [
    ("{기업목록}", "1번 기업 샘플애그 (IR 자료 전달에서만)"),
    ("{담당자명}", "김영주"),
    ("{직함}", "심사역님 (없으면 자동으로 '님')"),
    ("{투자사}", "가나벤처스"),
    ("{개수}", "선택한 기업 수"),
]


def _visible(db: Session, user: User) -> List[MessageTemplate]:
    """내가 쓸 수 있는 템플릿 = 팀 기본 + 내 것."""
    return db.execute(
        select(MessageTemplate)
        .where(or_(MessageTemplate.user_id.is_(None),
                   MessageTemplate.user_id == user.id))
        .order_by(MessageTemplate.kind, MessageTemplate.id)
    ).scalars().all()


def _editable(t: MessageTemplate, user: User) -> bool:
    """팀 기본(user_id=NULL)은 관리자만, 개인 것은 주인만 고칠 수 있다."""
    if t.user_id is None:
        return user.role == "admin"
    return t.user_id == user.id


@router.get("/templates", response_class=HTMLResponse, include_in_schema=False)
def templates_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), msg: str = ""):
    rows = _visible(db, user)
    grouped = []
    for kind, label, desc in KINDS:
        # 키 이름을 'items' 로 두면 Jinja 에서 dict.items 메서드가 잡힌다(실제로 500 발생).
        of_kind = [t for t in rows if t.kind == kind]
        grouped.append({"kind": kind, "label": label, "desc": desc,
                        "rows": [{"t": t, "editable": _editable(t, user)} for t in of_kind]})
    ctx = base_ctx(request, db, user, active="templates")
    ctx.update({"grouped": grouped, "kinds": KINDS, "variables": VARIABLES, "msg": msg})
    return jinja.TemplateResponse("templates.html", ctx)


@router.post("/templates/new", include_in_schema=False)
def create_template(
    kind: str = Form(...),
    name: str = Form(""),
    body: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if kind not in KIND_LABELS:
        raise HTTPException(status_code=400, detail="알 수 없는 문구 종류입니다")
    if not body.strip():
        return RedirectResponse("/templates?msg=내용을+입력하세요", status_code=303)
    db.add(MessageTemplate(user_id=user.id, kind=kind,
                           name=(name.strip() or None), body=body.strip(), is_active=1))
    db.commit()
    return RedirectResponse("/templates?msg=문구를+추가했습니다", status_code=303)


@router.post("/templates/{template_id}/edit", include_in_schema=False)
def edit_template(
    template_id: int,
    name: str = Form(""),
    body: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(MessageTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문구를 찾을 수 없습니다")
    if not _editable(t, user):
        raise HTTPException(status_code=403, detail="이 문구를 수정할 권한이 없습니다")
    t.name = name.strip() or None
    t.body = body.strip()
    db.commit()
    return RedirectResponse("/templates?msg=문구를+수정했습니다", status_code=303)


@router.post("/templates/{template_id}/delete", include_in_schema=False)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(MessageTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문구를 찾을 수 없습니다")
    if not _editable(t, user):
        raise HTTPException(status_code=403, detail="이 문구를 삭제할 권한이 없습니다")
    db.delete(t)
    db.commit()
    return RedirectResponse("/templates?msg=문구를+삭제했습니다", status_code=303)


@router.get("/api/templates")
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """발송 화면의 문구 선택기용."""
    rows = _visible(db, user)
    return {
        "templates": [
            {"id": t.id, "kind": t.kind,
             "name": t.name or ("팀 기본" if t.user_id is None else "내 문구"),
             "body": t.body, "mine": t.user_id == user.id}
            for t in rows
        ],
        "kinds": [{"kind": k, "label": label} for k, label, _ in KINDS],
    }
