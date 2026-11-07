"""숫자를 누르면 뜨는 상세 목록(`/reactions/list`) — 무엇을 싣는지는 `services/drilldown.py`."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import User
from ..services import drilldown
from ..ui import base_ctx

router = APIRouter()


@router.get("/reactions/list", response_class=HTMLResponse, include_in_schema=False)
def reaction_list_page(request: Request, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user), key: str = "",
                       month: str = "", year: str = "", scope: str = "", member: int = 0):
    try:
        got = drilldown.build(db, user, key, month, year, scope, member)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    # 대시보드 반응은 `대시보드 요약`, 미팅 카드 · 연간 반응은 `업무 보고` 메뉴에 불을 켠다.
    active = "home" if got["back"] == "/" else "report"
    ctx = base_ctx(request, db, user, active=active)
    ctx.update(got)
    ctx["page_title"] = got["title"]
    return templates.TemplateResponse(request, "reaction_list.html", ctx)
