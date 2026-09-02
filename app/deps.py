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


# --- 관리자 전용 ------------------------------------------------------------
#
# **판정은 여기 하나뿐이다.** 라우터마다 `role != "admin"` 을 적어 두면, 화면
# 요청인지 스크립트가 부른 것인지 가르는 규칙도 그만큼 늘어난다 — 팀 현황이
# 그래서 주소창에 날것의 JSON(`{"detail": "관리자만 …"}`)을 뿌렸다.
# 라우터는 `admin_only(user)` 만 부르고, 무엇을 돌려줄지는 `admin_block_response`
# 한 곳에서 정한다. 관리자 화면이 하나 더 생겨도 그 처리가 저절로 따라온다.
ADMIN_ONLY = "관리자만 사용할 수 있습니다"


class NotAdmin(HTTPException):
    """관리자 전용. 핸들러(app/main.py)가 화면과 조작을 갈라 답한다."""

    def __init__(self) -> None:
        super().__init__(status_code=403, detail=ADMIN_ONLY)


def admin_only(user: User) -> None:
    """관리자가 아니면 끊는다."""
    if user.role != "admin":
        raise NotAdmin()


def require_admin(user: User = Depends(get_current_user)) -> User:
    """`Depends` 로 거는 같은 판정 — 검사는 위 함수를 그대로 쓴다.

    두 곳이 각자 `role != "admin"` 과 각자의 사유 문구를 들고 있으면 하나는
    반드시 낡는다(`valid_role` 이 같은 이유로 판정을 한 곳에 모아 두었다).
    """
    admin_only(user)
    return user


def may_manage_team_contacts(user: User) -> bool:
    """팀 전체의 담당자를 **보고 또 고칠** 수 있는가.

    **판정은 여기 하나뿐이다.** 보는 쪽(`contact_rows` 의 `team_wide`)과 고치는
    쪽(`routers/contacts.py` 의 `_owned`)이 각자 `role == "admin"` 을 들고
    있어서 갈렸다 — 관리자 화면에는 팀 전체가 뜨는데 그 줄을 눌러 고치면
    `담당자를 찾을 수 없습니다`(404) 가 났다. **보이는데 못 고치는** 상태다.
    이 저장소가 반복해서 당한 부류다(투자사 수가 화면마다 갈린 일, 좌측 메뉴
    목록과 라우터 목록이 갈려 컨설턴트에게 다 열려 있던 일, 컨설턴트 줄에
    `막힘` 이라 떠 있는데 실제로는 열려 있던 일). 두 쪽이 이 함수 하나를 읽으면
    다음에 역할이 하나 늘어도 같이 움직인다.

    관리자에게 여는 것이 맞다 — 이 앱에서 관리자는 이미 팀 전체를 보고, 권한을
    바꾸고, 계정을 정지하고, 비밀번호를 초기화하며, 명단의 담당까지 통째로
    옮긴다(`routers/contacts.py` 의 `assign_sheet`). 그보다 훨씬 작은 담당자 한
    줄을 못 고치는 쪽이 오히려 어긋난다.

    팀원·투자컨설턴트는 그대로 **자기 것만**이다. 남의 담당자에 손대면 안 된다
    (딜소개 발송 대상 고르기가 관리자에게도 본인 담당분만인 것과는 다른 이야기다
    — 그쪽은 남의 방으로 문구가 실제로 나가는 일이라 열지 않는다).
    """
    return user.role == "admin"


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


# --- 로그인한 뒤 처음 보는 화면 ---------------------------------------------
#
# **어디로 보낼지는 여기 한 곳에서만 정한다.** 로그인 직후와 비밀번호를 바꾼
# 뒤가 각자 주소를 들고 있으면 하나는 반드시 낡는다 — 그리고 낡은 쪽은 조용히
# **막힌 화면**으로 보낸다. 컨설턴트에게 `/` 는 위 허용 목록 밖이라, 그리로
# 보내면 미들웨어가 되튕겨 내는 것을 한 번 보고서야 자기 화면에 닿는다.
# 역할이 하나 늘면 고칠 곳은 여기뿐이다.
#
# 좌측 메뉴(`ui.MENU`)의 첫 줄을 그대로 쓰지 않는 이유.
#   - 메뉴 순서는 **보기 좋으라고** 손댄다(ui.py 의 `명단 셋을 붙여 둔다`,
#     `순서는 쓰는 빈도다`). 그 손질이 도착지까지 같이 옮기면, 사이드바를
#     정리한 사람이 의도한 적 없는 변화가 조용히 따라붙는다.
#   - 메뉴에는 `ready: False`(준비 중) 자리가 있다. 도착지는 **열리는** 화면
#     이어야 하는데, 메뉴에 있다는 것은 그 보증이 못 된다.
# 대신 **메뉴와 어긋나지 않는지는 검사가 본다**(tests/test_landing.py) —
# 도착지는 그 사람 메뉴에 실제로 있고, 실제로 열려야 한다.
HOME_BY_ROLE = {
    # 컨설턴트는 대시보드에 못 들어간다 — 자기 화면이 곧 첫 화면이다.
    # 막혔을 때 되돌려 보내는 곳과 **같은 값**을 쓴다(바로 위 `CONSULTANT_HOME`).
    "consultant": CONSULTANT_HOME,
}

# 따로 정하지 않은 역할(관리자·팀원)이 가는 곳. `/` 는 대시보드다
# (`routers/pages.py` 의 `메인 = 대시보드`).
DEFAULT_HOME = "/"


def home_for(user: User) -> str:
    """이 사람이 로그인해서 처음 보는 화면.

    로그인 직후와 비밀번호를 바꾼 뒤가 **같이 읽는다**(`routers/auth.py`).
    모르는 역할은 대시보드로 둔다 — 역할 값이 어긋났을 때 아무 데도 못 가고
    멈추는 것보다, 권한 판정이 다시 걸러 주는 화면으로 보내는 편이 낫다.
    """
    return HOME_BY_ROLE.get(user.role, DEFAULT_HOME)


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


def may_view_consulting(user: User) -> bool:
    """투자컨설턴트 현황 화면을 볼 수 있는가.

    **판정은 여기 하나뿐이다.** 라우터는 역할까지 보고(`admin`·`consultant` 는
    통과) 팀 현황 표는 `can_view_consulting` 칸만 봐서, 컨설턴트 줄에 `막힘`
    이라고 떠 있는데 실제로는 열려 있었다 — 화면이 거짓말을 한 것이다.
    같은 부류의 사고를 이 저장소는 이미 여러 번 겪었다(메뉴 목록과 라우터
    목록이 갈려 컨설턴트에게 다 열려 있던 일, 투자사 수가 화면마다 달랐던 일).
    화면은 판정하지 않고 이 함수를 읽는다.

    - 관리자는 팀 전체를 본다.
    - 투자컨설턴트에게는 이 화면이 전부다 — 따로 켜 줄 필요가 없다.
    - 팀원은 관리자가 켜 준 계정만(`can_view_consulting`).
    """
    return consulting_by_role(user) or bool(user.can_view_consulting)


def may_view_all_consulting(user: User) -> bool:
    """투자컨설턴트 현황에서 **팀 전체**를 볼 수 있는가.

    이 화면은 원래 컨설턴트 **한 사람의 개인 표**다(줄마다 담당이 붙어 있다).
    그 개인 표들을 모아 팀이 보는 자리이기도 해서, 보는 사람이 둘로 갈린다.

    - 컨설턴트  자기 줄만. 남의 담당 기업이 보이면 안 되고, 각자 올린 시트가
                서로를 덮는다(월별 리마인드 열이 사람마다 다르다).
    - 그 외     관리자와, 관리자가 켜 준 팀원(`can_view_consulting`). 두 사람의
                표를 나란히 놓고 봐야 하는 자리라 **전체**를 본다.

    **판정을 여기 두는 이유.** 이 저장소는 같은 판단이 두 곳에 적혀 갈리는
    사고를 반복해 겪었다(메뉴 목록과 라우터 목록, 팀 현황의 `투자현황` 칸,
    투자사 수). 그래서 위 `may_view_consulting` 을 **다시 적지 않고 그대로
    태운다** — 볼 수 있는 사람이 늘거나 줄면 여기도 같이 움직인다.

    **보는 범위이지 고치는 범위가 아니다.** 팀원은 전체를 보되 남의 줄은
    고치지 못한다(`routers/consulting.py` 의 `may_edit_row`).
    """
    return may_view_consulting(user) and user.role != "consultant"


def consulting_by_role(user: User) -> bool:
    """`can_view_consulting` 칸과 상관없이 **역할만으로** 열려 있는가.

    켜고 끄는 단추를 보일지 정하는 자리다. 역할로 이미 열린 계정에서 그 단추는
    눌러도 아무 일이 없다 — 관리자는 껐다고 생각하는데 계속 보이는, 화면이
    거짓말을 하는 상태가 된다.

    역할 목록을 여기 한 번만 적는다. 화면·라우터가 각자 `("admin",
    "consultant")` 를 적어 두면 역할이 하나 늘 때 한쪽만 고쳐진다.
    """
    return user.role in ("admin", "consultant")


def sends_deals(user: User) -> bool:
    """이 계정이 딜소개를 보내는가.

    투자컨설턴트는 담당 투자사도 발송도 **원래 없다.** 팀 현황이 그것을 `0` 과
    `미연결` 로 그리면 아직 설정이 덜 된 사람처럼 읽힌다 — 특히 `미연결` 은 이
    앱에서 **고쳐야 할 것**을 뜻하는 표시라(대시보드 경고에도 같은 말을 쓴다)
    고칠 것이 없는데 경고가 뜨면 진짜 경고까지 무시하게 된다.

    무엇을 비울지 화면마다 정하지 않는다 — 여기서 한 번 판정하고 팀 현황 표와
    경고 목록이 그것을 읽는다.
    """
    return user.role != "consultant"


def consultant_block_response(request: Request) -> Response:
    """막을 때 무엇을 돌려줄지.

    브라우저 주소창에 403 만 뜨면 쓰는 사람은 고장인 줄 안다 — 화면 요청은
    자기 화면으로 보낸다. 반면 화면 속 스크립트에 리다이렉트를 주면 저장이
    성공한 것처럼 보이므로, 그쪽에는 403 을 그대로 준다.
    """
    if _wants_json(request):
        return JSONResponse({"detail": CONSULTANT_BLOCKED}, status_code=403)
    return RedirectResponse(CONSULTANT_HOME, status_code=303)


def admin_block_response(request: Request) -> Response:
    """관리자 전용에 권한 없이 닿았을 때 무엇을 돌려줄지.

    **위 컨설턴트 차단과 같은 판단이다** — 화면 요청은 화면으로 답하고,
    스크립트가 부르는 것에만 403 을 준다. 주소창에 날것의 JSON 이 뜨면 쓰는
    사람에게는 그냥 고장으로 보인다.

    다른 점은 **조작(폼 전송)** 이다. 컨설턴트는 애초에 그 화면에 볼일이 없어
    자기 화면으로 되돌려 보내는 것이 맞지만, 관리자 조작은 되돌려 보내면
    저장된 것처럼 보인다 — 권한 없이 누른 [계정 만들기]는 403 으로 실패를
    알려야 한다. 그래서 화면으로 답하는 것은 **주소창이 여는 GET** 뿐이다.
    """
    if request.method != "GET" or _wants_json(request):
        return JSONResponse({"detail": ADMIN_ONLY}, status_code=403)
    return _admin_only_page(request)


def _wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    # 주소창이 만들 수 있는 것은 GET · POST 뿐이다. PATCH·DELETE·PUT 은
    # 화면 스크립트(fetch)에서만 오므로 사람이 볼 응답이 아니다.
    if request.method in ("PATCH", "PUT", "DELETE"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def _admin_only_page(request: Request) -> Response:
    """앱 껍데기(사이드바)를 갖춘 빈 화면 + 대시보드로 가는 안내창.

    미들웨어·예외 핸들러는 라우팅 밖이라 `Depends` 를 쓸 수 없다 — 세션을
    직접 연다(`is_consultant` 와 같은 방식).

    **안내창은 서버가 그린 그대로 뜬다.** 스크립트 하나가 어긋난 날 상세
    패널이 통째로 안 열린 적이 있어서, 나가는 길을 알려 주는 창이 스크립트에
    기대면 같은 일이 난다(팀 현황의 수정칸을 주소로 여는 것과 같은 이유).
    """
    from .services import auth as auth_svc
    from .ui import base_ctx, screen_label  # ui 가 이 모듈을 부르므로 함수 안에서

    db = SessionLocal()
    try:
        user = auth_svc.user_for_token(db, request.cookies.get(auth_svc.SESSION_COOKIE))
        if user is None:
            # 판정과 응답 사이에 세션이 끊긴 경우 — 권한 안내보다 로그인이 먼저다.
            return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
        # 무엇을 열려 했는지 이름을 대 준다. 좌측 메뉴와 같은 목록에서 가져오므로
        # 관리자 화면이 늘어도 이 화면이 따로 낡지 않는다.
        label = screen_label(request.url.path)
        ctx = base_ctx(request, db, user, active="")
        ctx["page_title"] = label or "관리자 전용"
        ctx["blocked_label"] = label
        return templates.TemplateResponse("admin_only.html", ctx)
    finally:
        db.close()


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
