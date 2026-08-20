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
    {"key": "home", "label": "대시보드", "href": "/", "ready": True},
    {"key": "deal", "label": "딜소개 보내기", "href": "/deals", "ready": True},
    {"key": "vc", "label": "내 투자사", "href": "/contacts", "ready": True},
    {"key": "su", "label": "딜 기업 DB", "href": "/companies", "ready": True},
    {"key": "templates", "label": "문구 관리", "href": "/templates", "ready": True},
    {"key": "check", "label": "오늘 할 일", "href": "/todo", "ready": False},
    {"key": "req", "label": "IR·미팅 관리", "href": "/ir", "ready": False},
    {"key": "admin", "label": "팀 현황", "href": "/team", "ready": True, "admin_only": True},
    {"key": "setup", "label": "발송 프로그램 설치", "href": "/setup", "ready": True},
]


def visible_menu(user: User) -> list:
    """관리자 전용 메뉴는 관리자에게만 보인다."""
    return [m for m in MENU if not m.get("admin_only") or user.role == "admin"]


def base_ctx(request: Request, db: Session, user: User, active: str) -> dict:
    return {
        "request": request,
        "menu": visible_menu(user),
        "active": active,
        "user": user,
        "agent": agent_status(db, user.id),
        "test_room": config.TEST_ROOM,
        "current_path": request.url.path,
    }
