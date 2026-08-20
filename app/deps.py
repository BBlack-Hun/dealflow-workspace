"""Shared dependencies: current user, agent auth, templates, helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import AgentDevice, User

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NotAuthenticated(HTTPException):
    """로그인 필요. 미들웨어/핸들러가 로그인 화면으로 보낸다."""

    def __init__(self) -> None:
        super().__init__(status_code=401, detail="로그인이 필요합니다")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """현재 로그인 사용자 (휴대폰번호 + 비밀번호 세션).

    쿠키에는 **세션 토큰만** 담기고 소유자는 서버가 DB 에서 판단한다.
    (이전의 개발용 전환은 쿠키에 user_id 를 그대로 담아 누구나 바꿀 수 있었다.)
    """
    from .services import auth as auth_svc

    user = auth_svc.user_for_token(db, request.cookies.get(auth_svc.SESSION_COOKIE))
    if user is None:
        raise NotAuthenticated()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다")
    return user


def get_agent_device(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> AgentDevice:
    """Authenticate the sending agent via `Authorization: Bearer <agent_token>`."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[7:].strip()
    device = db.execute(
        select(AgentDevice).where(AgentDevice.token == token)
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    return device


def agent_status(db: Session, user_id: Optional[int] = None) -> dict:
    """Connection badge state for a user's agent device.

    사용자를 전환하면 배지도 그 사용자의 기기를 가리켜야 한다 — 그렇지 않으면
    Mac 화면에서 Windows 에이전트가 '내 에이전트'처럼 보인다(실제로 겪은 혼선).
    """
    device = db.execute(
        select(AgentDevice).where(
            AgentDevice.user_id == (user_id if user_id is not None else config.CURRENT_USER_ID)
        )
    ).scalar_one_or_none()
    online = False
    last_poll = None
    if device and device.last_poll_at:
        last_poll = device.last_poll_at
        try:
            ts = datetime.fromisoformat(device.last_poll_at)
            delta = (datetime.now(timezone.utc) - ts).total_seconds()
            online = delta <= config.AGENT_ONLINE_WINDOW_SEC
        except ValueError:
            online = False
    # 어떤 발송기가 붙었는지까지 보여준다.
    # mock 이 붙은 채로 실제 발송을 누르면 그 잡을 가로채 '보낸 것처럼' 처리되므로,
    # 단순히 "연결됨"만 띄우면 실발송이 안 되는 이유를 알 수 없다.
    sender = getattr(device, "sender", None) if device else None
    host = (device.hostname or "").strip() if device else ""
    is_mock = sender == "mock"

    if not online:
        label = "발송 프로그램 연결 안 됨"
    elif is_mock:
        label = f"연습 모드 — 실제로 보내지 않음{f' · {host}' if host else ''}"
    else:
        label = f"발송 프로그램 연결됨{f' · {host}' if host else ''}"

    return {
        "online": online,
        "last_poll_at": last_poll,
        "sender": sender,
        "hostname": host,
        "is_mock": is_mock,
        "label": label,
    }
