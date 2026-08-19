"""Shared dependencies: current user (Sprint 1 hardcoded), agent auth, templates, helpers."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import AgentDevice, User

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_current_user(db: Session = Depends(get_db)) -> User:
    """Sprint 1: single hardcoded user session. Real OTP auth arrives in Sprint 4."""
    user = db.get(User, config.CURRENT_USER_ID)
    if user is None:
        raise HTTPException(status_code=500, detail="Seed data missing — run seed_demo.py")
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


def agent_status(db: Session) -> dict:
    """Connection badge state for the current user's agent device."""
    device = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == config.CURRENT_USER_ID)
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
        label = "발송 에이전트 오프라인"
    elif is_mock:
        label = f"데모(mock) 에이전트 — 실제 발송 안 됨{f' · {host}' if host else ''}"
    else:
        label = f"발송 에이전트 연결됨{f' · {host}' if host else ''}"

    return {
        "online": online,
        "last_poll_at": last_poll,
        "sender": sender,
        "hostname": host,
        "is_mock": is_mock,
        "label": label,
    }
