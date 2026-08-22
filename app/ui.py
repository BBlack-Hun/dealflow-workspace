"""화면 공통 컨텍스트 — 사이드바 메뉴 · 에이전트 배지 · 개발용 사용자 전환.

페이지 라우터가 여럿(pages / setup)이라 공통 컨텍스트를 한 곳에 둔다. 여기가
갈라지면 화면마다 사이드바 상태가 달라진다(실제로 /setup 만 사용자 전환이 안 되는
식의 버그가 나기 쉽다).
"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .deps import agent_status
from .models import User

# 좌측 메뉴. 쓰는 순서대로 둔다.
#
# 화면에는 개발 용어를 쓰지 않는다. 예전에 'S2' 같은 스프린트 배지와
# '에이전트' 같은 말이 그대로 보였는데, 쓰는 사람에게는 아무 뜻이 없다.
# 아직 없는 화면은 `ready: False` 로 두고 '준비 중'으로만 표시한다.
#
# `admin_only` 인 메뉴는 관리자에게만 보인다(들어가도 403 이지만, 보이지 않는 편이 낫다).
MENU = [
    {"key": "check", "label": "주간 업무", "href": "/todo", "ready": True},
    {"key": "home", "label": "대시보드 요약", "href": "/", "ready": True},
    {"key": "deal", "label": "딜 제안 관리", "href": "/deals", "ready": True},
    {"key": "su", "label": "스타트업 관리", "href": "/companies", "ready": True},
    {"key": "vc", "label": "투자사 DB", "href": "/contacts", "ready": True},
    {"key": "followup", "label": "후속 관리", "href": "/followups", "ready": True},
    {"key": "templates", "label": "딜 제안 문구", "href": "/templates", "ready": True},
    {"key": "req", "label": "IR·미팅 관리", "href": "/ir", "ready": True},
    
    {"key": "consult", "label": "투자컨설턴트 현황", "href": "/consulting", "ready": True,
     "needs": "can_view_consulting"},
    {"key": "report", "label": "업무 보고", "href": "/report", "ready": True},
    {"key": "admin", "label": "팀 현황", "href": "/team", "ready": True, "admin_only": True},
]


def can_see(user: User, item: dict) -> bool:
    """이 사람에게 이 메뉴를 보여도 되는가.

    관리자는 전부 본다. `needs` 가 붙은 메뉴는 그 계정 속성이 켜진 사람만 본다
    (볼 사람 이름을 코드에 박으면 담당이 바뀔 때마다 배포해야 한다).
    """
    if user.role == "admin":
        return True
    if item.get("admin_only"):
        return False
    need = item.get("needs")
    return not need or bool(getattr(user, need, 0))


def visible_menu(user: User) -> list:
    return [m for m in MENU if can_see(user, m)]


def menu_label(active: str) -> str:
    """지금 보고 있는 화면의 이름. 좌측 메뉴와 화면 제목이 어긋나지 않게 한 곳에서 가져온다."""
    item = next((m for m in MENU if m["key"] == active), None)
    return item["label"] if item else "CONTACTVC ASSET"


def base_ctx(request: Request, db: Session, user: User, active: str) -> dict:
    return {
        "page_title": menu_label(active),
        "request": request,
        "menu": visible_menu(user),
        "active": active,
        "user": user,
        "agent": agent_status(db, user.id),
        "test_room": config.TEST_ROOM,
        "current_path": request.url.path,
    }
