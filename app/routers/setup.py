"""발송 에이전트 배포 — 웹에서 바로 내려받게 한다.

7명이 각자 PC에 에이전트를 깔아야 하므로(TECH_SPEC §3: 카톡방은 각자 계정에 있음),
USB로 파일을 옮기는 대신 **웹 접속 → 다운로드 → 실행** 흐름을 제공한다.

zip 은 요청 시점에 메모리에서 조립하며, `agent/config.yaml` 의
server_url / token 을 **접속한 주소와 그 사용자의 토큰으로 자동 채워** 넣는다.
사용자가 설정 파일을 손댈 필요가 없게 하려는 것이다.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import AgentDevice, User
from ..ui import base_ctx

router = APIRouter(tags=["setup"])

ROOT = Path(__file__).resolve().parent.parent.parent

# zip 에 담을 에이전트 소스 (경로, zip 내부 경로)
AGENT_FILES = [
    ("agent/__init__.py", "agent/__init__.py"),
    ("agent/main.py", "agent/main.py"),
    ("agent/version.py", "agent/version.py"),
    ("agent/diagnose.py", "agent/diagnose.py"),
    ("agent/selectors.yaml", "agent/selectors.yaml"),
    ("agent/sender/__init__.py", "agent/sender/__init__.py"),
    ("agent/sender/base.py", "agent/sender/base.py"),
    ("agent/sender/mock.py", "agent/sender/mock.py"),
    ("agent/sender/kakao_windows.py", "agent/sender/kakao_windows.py"),
    ("agent/sender/kakao_mac.py", "agent/sender/kakao_mac.py"),
    ("agent/sender/telegram.py", "agent/sender/telegram.py"),
]

# OS 별로 다른 파일. mac zip 에 windows 용 requirements 가 들어가던 버그를 막는다.
OS_FILES = {
    "windows": [
        ("requirements-agent-windows.txt", "requirements.txt"),
        ("packaging/windows/setup.bat", "setup.bat"),
        ("packaging/windows/run_agent.bat", "run_agent.bat"),
        ("packaging/windows/README-KR.txt", "README-KR.txt"),
    ],
    "mac": [
        ("requirements-agent-mac.txt", "requirements.txt"),
        ("packaging/mac/setup.sh", "setup.sh"),
        # Finder 에서 더블클릭으로 끝나게 한다 — 쓰는 사람이 터미널 명령을 알 이유가 없다.
        ("packaging/mac/1. 설치하기.command", "1. 설치하기.command"),
        ("packaging/mac/2. 발송 프로그램 켜기.command", "2. 발송 프로그램 켜기.command"),
    ],
}

CONFIG_TEMPLATE = """# dealflow 발송 에이전트 설정 (웹에서 자동 생성됨)
#
# server_url 과 token 은 다운로드 시점에 자동으로 채워졌습니다.
# 서버 주소가 바뀌면 server_url 만 수정하세요.

server_url: "{server_url}"
token: "{token}"
sender: "{sender}"

poll_interval_sec: 3
heartbeat_interval_sec: 20
agent_version: "0.1.0"

# 사람 유사 발송 패턴 (계정 보호). 줄이지 마세요.
delay_min_sec: 3
delay_max_sec: 7
job_cap: 60

# 방 연결 확인(검색만 하고 전송하지 않음)
verify_delay_min_sec: 1
verify_delay_max_sec: 2

selectors_file: "agent/selectors.yaml"

# 카톡 창 조작 대기시간(초). 창이 늦게 뜨면 늘리세요.
kakao_windows:
  search_hotkey: ["ctrl", "f"]
  after_search_hotkey: 0.5
  after_query_paste: 1.0
  after_open_room: 1.2
  before_message_paste: 0.2
  after_message_paste: 0.6
  after_send: 0.5
  chat_wait: 3.0

kakao_mac:
  search_hotkey: "f"
  after_activate: 1.0
  after_search_hotkey: 0.8
  after_query_paste: 1.2
  after_open_room: 1.5
  after_paste: 0.6
  after_send: 0.8
  close_after_send: true

mock:
  delay_min_sec: 0.5
  delay_max_sec: 1.5
  fail_rate: 0.0
"""


def _build_info(os_kind: str) -> str:
    """zip 에 동봉하는 빌드 정보.

    서버 이미지가 낡으면 옛 코드가 담긴 zip 이 배포되는데(실기 발생),
    받은 쪽에서는 그걸 알 방법이 없다. 코드 지문을 남겨 대조 가능하게 한다.
    """
    import hashlib

    parts = [f"os: {os_kind}"]
    for src, _dest in AGENT_FILES:
        f = ROOT / src
        if f.exists():
            digest = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
            parts.append(f"{src}  {digest}")
    return "dealflow agent build\n" + "\n".join(parts) + "\n"


def _server_url(request: Request) -> str:
    """사용자가 실제로 접속한 주소. 에이전트가 그대로 되돌아오면 된다."""
    return str(request.base_url).rstrip("/")


def _device(db: Session, user: User) -> AgentDevice:
    """이 사용자의 기기 줄. 없으면 만든다 (사람마다 한 줄)."""
    _ensure_token(db, user)
    return db.execute(
        select(AgentDevice).where(AgentDevice.user_id == user.id)
    ).scalars().first()


def _ensure_token(db: Session, user: User) -> str:
    """이 사용자의 에이전트 토큰. 없으면 만든다."""
    dev = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == user.id)
    ).scalars().first()
    if dev:
        return dev.token
    import secrets

    dev = AgentDevice(user_id=user.id, token=f"agt_{secrets.token_hex(16)}",
                      hostname="", agent_version="")
    db.add(dev)
    db.commit()
    return dev.token


@router.get("/setup", response_class=HTMLResponse)
def setup_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """에이전트 설치 안내 + 다운로드 링크. 토큰은 **지금 선택된 사용자**의 것이다."""
    ctx = base_ctx(request, db, user, "setup")
    ctx.update({"server_url": _server_url(request), "token": _ensure_token(db, user),
                "ir_root": _device(db, user).ir_root or "",
                "saved": request.query_params.get("saved") == "ir_root"})
    return templates.TemplateResponse("setup.html", ctx)


@router.post("/setup/ir-root")
def save_ir_root(
    ir_root: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """IR 자료 폴더 자리를 저장한다 — **본인 것만.**

    ## 왜 본인만인가

    이 값은 "그 PC 의 어느 폴더" 다. 그 PC 앞에 앉은 사람만 그 경로가 맞는지 안다.
    관리자라도 대신 넣게 하면 안 된다 — 틀린 경로를 넣어 두면 발송기는 그 자리를
    뒤지다 실패하고, 정작 본인은 자기가 넣지도 않은 값 때문에 막힌 줄을 모른다.
    그래서 로그인한 사람의 기기 줄에만 쓴다(대상 사용자를 **받지 않는다**).

    ## 여기서 경로를 검사하지 않는 이유

    서버는 다른 기기다. 사용자 PC 에 그 폴더가 있는지 서버는 볼 수 없다.
    있는지·폴더인지는 **발송기가** 켜질 때와 보내기 전에 확인하고 분명히
    실패한다(`agent/sender/base.py: ir_root`). 여기서는 앞뒤 공백만 턴다.
    """
    device = _device(db, user)
    device.ir_root = (ir_root or "").strip() or None
    db.commit()
    return RedirectResponse("/setup?saved=ir_root", status_code=303)


@router.get("/download/agent")
def download_agent(
    request: Request,
    os_kind: str = "windows",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """에이전트 zip 을 즉석에서 조립해 내려준다 (설정 자동 주입)."""
    sender = "kakao_mac" if os_kind == "mac" else "kakao_windows"
    # 토큰은 **지금 선택된 사용자**의 것이다 → 기기마다 다른 사용자를 골라 받아야
    # 발송 잡이 어느 기기로 갈지 예측 가능해진다(사용자 1명 = 에이전트 1대).
    config_yaml = CONFIG_TEMPLATE.format(
        server_url=_server_url(request),
        token=_ensure_token(db, user),
        sender=sender,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, dest in AGENT_FILES + OS_FILES.get(os_kind, OS_FILES["windows"]):
            path = ROOT / src
            if not path.exists():
                continue  # 배포 구성에 따라 없을 수 있음(예: mac 전용 파일)
            data = path.read_bytes()
            if dest.endswith(".bat"):
                # Windows cmd 호환을 위해 CRLF 보장
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            info = zipfile.ZipInfo(dest)
            info.compress_type = zipfile.ZIP_DEFLATED
            # 실행 권한이 없으면 Finder 에서 더블클릭해도 열리지 않고 편집기로 뜬다.
            executable = dest.endswith((".command", ".sh"))
            info.external_attr = (0o755 if executable else 0o644) << 16
            zf.writestr(info, data)
        zf.writestr("agent/config.yaml", config_yaml)
        zf.writestr("agent_logs/.keep", "")
        zf.writestr("BUILD_INFO.txt", _build_info(os_kind))

    buf.seek(0)
    name = f"dealflow-agent-{os_kind}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
