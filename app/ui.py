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

# 좌측 메뉴 (FEATURE_SPEC §0.2 권장안, 사용 빈도순).
# `badge` 는 아직 구현되지 않은 화면에만 붙는다(어느 스프린트에 오는지 표시).
MENU = [
    {"key": "check", "label": "오늘 할 일", "href": "/todo", "sprint": 4, "badge": "S4"},
    {"key": "deal", "label": "딜소개 보내기", "href": "/deals", "sprint": 1, "badge": None},
    {"key": "req", "label": "IR·미팅 관리", "href": "/ir", "sprint": 2, "badge": "S2"},
    {"key": "vc", "label": "내 투자사", "href": "/contacts", "sprint": 2, "badge": None},
    {"key": "su", "label": "딜 기업 DB", "href": "/companies", "sprint": 2, "badge": "S2"},
    {"key": "templates", "label": "문구 관리", "href": "/templates"},
    {"key": "admin", "label": "팀 현황", "href": "/team", "sprint": 4, "badge": "S4"},
    {"key": "setup", "label": "에이전트 설치", "href": "/setup", "sprint": 1, "badge": None},
]


def base_ctx(request: Request, db: Session, user: User, active: str) -> dict:
    return {
        "request": request,
        "menu": MENU,
        "active": active,
        "user": user,
        "agent": agent_status(db, user.id),
        "test_room": config.TEST_ROOM,
        "current_path": request.url.path,
    }
