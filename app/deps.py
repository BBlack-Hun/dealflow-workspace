"""Shared dependencies: current user, agent auth, templates, helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import assets, clock, config
from .db import SessionLocal, get_db
from .models import AgentDevice, User

def _eok(value) -> str:
    """저장값(백만원) → 억 표기. `1830` → `18.3`."""
    from .services.message_composer import format_eok

    return format_eok(value) or ""


templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
# 정적 파일 주소에 지문을 붙인다 — 고쳐도 브라우저가 옛 것을 쓰는 일을 막는다.
# 전역으로 두어야 base.html 을 포함한 모든 화면에서 쓸 수 있다(컨텍스트에
# 넣으면 화면 하나에서 빠뜨리는 순간 그 화면만 캐시에 물린다).
templates.env.globals["asset"] = assets.asset
# 금액은 어느 화면에서든 억으로 보여 준다 — 저장은 백만원이라 그대로 두면
# `1,000` 이 10억으로 읽히지 않는다.
templates.env.globals["eok"] = _eok


# 저장용 시각은 `app/clock.py` 하나에서만 만든다 — 왜 지역시간인지는 그쪽에.
# 여기 두는 것은 라우터들이 예전부터 `deps.now_iso` 로 불러 왔기 때문이다.
now_iso = clock.now_iso


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


# --- 투자컨설턴트가 닿을 수 있는 곳 -----------------------------------------
#
# **허용 목록이다.** 막을 곳을 적는 방식이었다면 라우터가 하나 늘 때마다 여기
# 적는 것을 잊고, 잊은 것은 열린 채로 나간다 — 실제로 그랬다. 좌측 메뉴만
# 걸러 두고 라우터를 안 막아서, 주소를 직접 치면 딜·투자사·엑셀 내보내기까지
# 전부 열려 있었다. 이제 새 화면의 기본값은 **막힘**이다.
#
# 여기 적힌 것 말고는 화면이든 API 든 전부 끊긴다. 판정은 `app/main.py` 의
# 미들웨어 한 곳에서만 한다 — 라우터마다 흩뿌리면 다시 빠진다.
CONSULTANT_PATHS = (
    # 자기 화면과 그 화면이 부르는 것들(인라인 수정 PATCH · 월 열 추가/삭제 ·
    # 시트 올리기 · 엑셀 내려받기). 화면만 열어 두면 고칠 수가 없다.
    "/consulting",
    "/api/consulting",
    "/api/export/consulting.xlsx",
    # 참고 자료 패널. 투자사 관리 현황과 주소를 같이 쓴다 — 그래서 어느 화면의
    # 자료인지는 라우터가 따로 본다(routers/contacts.py 의 `_editable_ref`).
    "/ref-sheets",
    "/api/ref-sheets",
    # 로그인·로그아웃·비밀번호 변경. 막으면 들어올 수도, 나갈 수도 없다.
    "/login",
    "/logout",
    "/account/password",
    # 사이드바 배지(base.html)가 5초마다 부른다. 끊으면 자기 화면을 보는
    # 내내 403 이 쌓인다. 돌려주는 것은 **본인 기기**의 연결 상태뿐이다.
    "/api/agent-status",
    # 살아 있는지 확인하는 주소 · 정적 파일 · 파비콘.
    "/health",
    "/static",
    "/favicon.ico",
)


# 막혔을 때 돌아가는 화면과, 스크립트에 돌려줄 사유.
CONSULTANT_HOME = "/consulting"
CONSULTANT_BLOCKED = "투자컨설턴트는 투자컨설턴트 현황만 볼 수 있습니다"


def consultant_may_open(path: str) -> bool:
    """이 경로가 투자컨설턴트 허용 목록에 있는가.

    접두사는 **경로 조각 단위**로 견준다. 단순 `startswith` 로 두면 나중에
    `/consulting-report` 같은 이름을 붙였을 때 조용히 같이 열린다.
    """
    return any(path == item or path.startswith(item + "/")
               for item in CONSULTANT_PATHS)


def is_consultant(request: Request) -> bool:
    """이 요청을 보낸 사람이 투자컨설턴트인가.

    미들웨어는 라우팅 전에 돌아서 `Depends` 를 쓸 수 없다 — 세션을 직접 연다.
    허용 목록에 없는 경로일 때만 부르므로, 자기 화면을 쓰는 동안에는 이
    조회가 일어나지 않는다.
    """
    from .services import auth as auth_svc

    db = SessionLocal()
    try:
        user = auth_svc.user_for_token(db, request.cookies.get(auth_svc.SESSION_COOKIE))
        return user is not None and user.role == "consultant"
    finally:
        db.close()


def can_open(user: User, path: str) -> bool:
    """이 사람이 이 경로를 열어도 되는가 — 컨설턴트 여부만 본다.

    화면 접근은 미들웨어가 막지만, **여러 화면이 같이 쓰는 주소**는 그것만으로는
    부족하다(참고 자료 `/ref-sheets/…`). 번호만 바꿔 남의 화면 자료를 건드리는
    길을 라우터가 이 함수로 막는다 — 역할 판정은 여기 한 곳에 둔다.
    """
    return user.role != "consultant" or consultant_may_open(path)


def consultant_block_response(request: Request) -> Response:
    """막을 때 무엇을 돌려줄지.

    브라우저 주소창에 403 만 뜨면 쓰는 사람은 고장인 줄 안다 — 화면 요청은
    자기 화면으로 보낸다. 반면 화면 속 스크립트에 리다이렉트를 주면 저장이
    성공한 것처럼 보이므로, 그쪽에는 403 을 그대로 준다.
    """
    if _wants_json(request):
        return JSONResponse({"detail": CONSULTANT_BLOCKED}, status_code=403)
    return RedirectResponse(CONSULTANT_HOME, status_code=303)


def _wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    # 주소창이 만들 수 있는 것은 GET · POST 뿐이다. PATCH·DELETE·PUT 은
    # 화면 스크립트(fetch)에서만 오므로 사람이 볼 응답이 아니다.
    if request.method in ("PATCH", "PUT", "DELETE"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


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
            # 경과시간은 **순간**끼리 뺀다 — 저장값에 오프셋이 붙어 있으므로
            # 그 값이 UTC 표기든 한국시간 표기든 결과는 같다(옛 값과 섞여도).
            delta = (clock.now() - ts).total_seconds()
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
