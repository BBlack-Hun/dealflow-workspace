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


# 개발용 사용자 전환 쿠키. ★ 인증이 아니다.
DEV_USER_COOKIE = "dealflow_dev_user"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """현재 사용자 — **개발용 임시 전환**(쿠키), 없으면 기본 사용자로 폴백.

    ★ 이것은 인증이 아니다. 쿠키만 바꾸면 누구나 다른 사용자가 되므로 내부 테스트
    전용이다. 정식 로그인(휴대폰번호 + 비밀번호)은 다음 스프린트에 붙는다.

    지금 이게 필요한 이유: Mac·Windows 두 기기로 동시에 테스트할 때 모두가 같은
    사용자로 잡히면 어느 기기가 잡을 가져갈지 예측할 수 없다. 기기마다 다른 사용자를
    고르면 ``SendJob.user_id == AgentDevice.user_id`` 격리로 자연히 갈린다.

    정식 로그인 도입 시 **이 함수 한 곳만** 세션 조회로 바꾸면 된다(쿠키 → 세션).
    """
    user = None
    raw = request.cookies.get(DEV_USER_COOKIE)
    if raw and raw.isdigit():
        user = db.get(User, int(raw))
        if user is not None and not user.is_active:
            user = None
    if user is None:
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
