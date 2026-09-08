"""발송 에이전트 배포 — 웹에서 바로 내려받게 한다.

7명이 각자 PC에 에이전트를 깔아야 하므로(TECH_SPEC §3: 카톡방은 각자 계정에 있음),
USB로 파일을 옮기는 대신 **웹 접속 → 다운로드 → 실행** 흐름을 제공한다.

zip 은 요청 시점에 메모리에서 조립하며, `agent/config.yaml` 의
server_url / token 을 **접속한 주소와 그 사용자의 토큰으로 자동 채워** 넣는다.
사용자가 설정 파일을 손댈 필요가 없게 하려는 것이다.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import get_current_user, may_auto_attach, templates
from ..models import TEST_SEND_KIND, AgentDevice, IrCompany, SendItem, SendJob, User
from ..services import startup_msg
from ..ui import base_ctx

router = APIRouter(tags=["setup"])

#: 자동 첨부가 꺼진 계정이 자료 폴더를 넣으려 할 때. 한 곳에 적어 두고
#: 라우터와 검사가 같은 말을 읽는다.
AUTO_ATTACH_BLOCKED = "자료 자동 첨부를 쓸 수 없는 계정입니다"


# ══════════════════════════════════════════════════════════════════════════
#  시험용 자리 — 발송기가 실제로 도는지 여기서 눌러 본다
# ══════════════════════════════════════════════════════════════════════════
#
# ## 무엇이 없었나
#
# 파일 첨부가 되는지, 카톡방 이름이 맞는지 보려면 **사람이 DB 에 잡을 손으로
# 심어야 했다.** 발송기를 새 PC 에 깔 때마다 그 짓을 반복했고, 그 자리가 화면에
# 없으니 깔아 준 사람이 아니면 확인할 방법이 아예 없었다.
#
# ## 어디로 가나 — **시험방 하나뿐이다**
#
# 파일 시험이 만드는 잡의 방 이름은 `config.TEST_ROOM` 이다. **사람이 고르지
# 못한다.** 방 이름을 적는 칸은 방 이름 시험에만 있고, 그쪽은 아무것도 보내지
# 않는다(검색해서 열리는지만 본다).
#
# ## 왜 시험방이 없으면 자리 자체가 없나  ★ 이것이 이 기능의 안전선이다
#
# 운영에는 `DEALFLOW_TEST_ROOM` 이 없다. 그래서 이 자리는 **운영에서 저절로
# 닫힌다** — 끄는 것을 사람이 기억할 필요가 없다. 화면에서 감추기만 하면 주소로
# 그대로 부를 수 있으므로(이 저장소가 여러 번 겪은 사고다) 라우터도 같이 닫는다.
# 판정은 아래 함수 하나이고 화면·라우터가 그것을 함께 읽는다.
#
# ## 왜 "임시" 로 두지 않았나
#
# 사용자는 "임시로 만들어 달라" 고 했지만 남기는 쪽으로 정했다. 이 자리는
# **발송기를 깔 때마다** 쓰는 자리다(PC 가 바뀌면 파일 첨부도 방 검색도 다시
# 확인해야 한다). 임시로 두면 지우는 것을 누군가 기억해야 하는데, 이 저장소가
# 거듭 적어 둔 대로 적어 둔 것은 지켜지지 않는다. 대신 **시험방이 없으면 사라진다**
# 는 조건을 달아 두어, 지울 사람이 없어도 운영에서는 없는 자리가 된다.
# 남기는 만큼 화면에는 시험용이라는 것이 분명히 보여야 한다(`setup.html`).

#: 시험 잡이 실어 보내는 문구. **파일 뒤에 한 통** 나간다 —
#: 실제 자료 전달이 그 차례이므로(`agent/main.py: send_item`) 같은 모양으로
#: 시험해야 첨부가 되는지, 차례가 맞는지가 함께 드러난다.
TEST_FILE_MESSAGE = "[시험] 자료 첨부 시험입니다 — 실제 발송이 아닙니다."

#: 칸을 비운 채 눌렀을 때. 주소에 실려 화면이 다시 읽는다(`setup.html`).
#:
#: `no_template` 만 성격이 다르다 — 사람이 안 적은 것이 아니라 **문구틀이
#: 비어 있는 것**이라, 고칠 자리가 이 화면이 아니다. 그래서 어디로 가야
#: 하는지를 말에 담는다(화면이 그 자리로 가는 고리를 함께 그린다).
TEST_INPUT_MISSING = {
    "need_file": "시험할 파일 이름을 적어주세요",
    "need_room": "확인할 카톡방 이름을 적어주세요",
    "need_company": "어느 기업 것으로 만들지 골라주세요",
    "no_template": ("「기업 리마인드 — 문자」 문구가 비어 있습니다 — "
                    "딜 제안 문구에서 먼저 적어 주세요"),
}


def _test_companies(db: Session) -> list:
    """시험용 기업 고르개에 담을 명단 — **스타트업 명단 전부**, 이름 순.

    ## 왜 거르지 않나

    "월말 리마인드를 **누구에게** 보내는가" 는 이번에 정하지 않는다. 그건
    대상 고르기·중복 방지·이력 남기기가 따라붙는 별개의 일이라, 여기서
    슬쩍 정해 버리면 그 규칙이 시험 화면 안에 숨은 채 실전의 기준이 된다.
    이 자리는 **문구가 어떤 모양으로 나가는지** 보는 자리다.

    거르면 정작 봐야 할 것도 가려진다 — 담당자 성함이 빈 줄은 문구가
    `안녕하세요  대표님` 으로 나가는데, 그 줄을 목록에서 빼면 그것을 볼 수
    있는 자리가 없어진다.

    ## `딜소개 불가` 기업도 뺀 것이 아니다

    발송 화면은 그런 기업을 목록에서 아예 뺀다 — "목록에 있는 것만으로 실수로
    고를 수 있다"(`routers/companies.BLOCKED_CONTRACT`). 그 규칙이 막는 사고는
    **그 기업을 투자사에 소개해 버리는 것**이다. 여기서는 소개하지 않고, 골라도
    그 기업에게는 **아무것도 가지 않는다**(가는 곳은 시험방 하나뿐이다).
    막을 사고가 없는데 목록에서 빼면, 정작 그 기업에 보낼 문구가 어떻게
    생겼는지만 못 보게 된다.
    """
    return list(db.execute(select(IrCompany).order_by(IrCompany.name)).scalars().all())


def test_tools_on() -> bool:
    """시험용 자리를 내줄 것인가 — **시험방이 정해져 있을 때만.**

    판정은 여기 하나뿐이다. 화면(`setup.html` 의 시험용 칸)과 두 라우터가
    같은 함수를 읽는다 — 화면만 감추면 주소로 부를 수 있고, 라우터만 막으면
    눌러야 막힌 것을 아는 단추가 남는다. 둘 다 이 저장소가 겪은 사고다.

    값을 모듈 상수로 굳히지 않고 부를 때마다 읽는다. 굳히면 검사에서 값을
    바꿔 끼울 수 없다(메일 설정이 `config.domain()` 을 함수로 둔 것과 같은 이유).
    """
    return bool((config.TEST_ROOM or "").strip())


def _test_room() -> str:
    """시험방 제목. 없으면 **이 자리는 없는 것으로 답한다(404).**

    403 이 아닌 이유: 권한이 모자란 것이 아니라 이 서버에 그런 자리가 없는
    것이다. 운영에서 주소를 쳐 본 사람에게 "막혔다" 가 아니라 "없다" 가
    사실이고, 없는 것을 있다고 알리면 그 자리를 찾아 헤매게 된다.
    """
    room = (config.TEST_ROOM or "").strip()
    if not room:
        raise HTTPException(status_code=404, detail="Not Found")
    return room

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
    ("agent/sender/win_clipboard.py", "agent/sender/win_clipboard.py"),
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
    """에이전트 설치 안내 + 다운로드 링크. 토큰은 **지금 선택된 사용자**의 것이다.

    자료 폴더 칸은 **자동 첨부를 켜 준 계정에만** 그린다(`base_ctx` 가 실어 주는
    `may_auto_attach`). 꺼진 계정에 값이 남아 있어도 여기서는 내보내지 않는다 —
    화면에 그리지 않을 값을 컨텍스트에 태우면 언젠가 그 값을 쓰는 자리가
    생긴다.

    다만 **넣어 둔 값이 있었는지**(`ir_root_kept`)는 알려 준다. 화면이 그
    한 줄로 "왜 칸이 사라졌는지" 를 답한다 — 이유는 `setup.html` 에.
    """
    ctx = base_ctx(request, db, user, "setup")
    saved_root = _device(db, user).ir_root or ""
    allowed = ctx["may_auto_attach"]
    ctx.update({"server_url": _server_url(request), "token": _ensure_token(db, user),
                "ir_root": saved_root if allowed else "",
                "ir_root_kept": bool(saved_root.strip()) and not allowed,
                "saved": request.query_params.get("saved") == "ir_root",
                # 시험용 자리를 그릴 것인가. **라우터와 같은 함수**를 읽는다 —
                # 화면만 감추면 주소로 부를 수 있고, 라우터만 막으면 눌러야
                # 막힌 것을 아는 단추가 남는다.
                "test_tools": test_tools_on(),
                # 시험용 자리를 안 그릴 때는 명단도 싣지 않는다 — 화면에
                # 그리지 않을 값을 컨텍스트에 태우면 언젠가 그 값을 쓰는
                # 자리가 생긴다(바로 위 `ir_root` 와 같은 조심).
                "test_companies": _test_companies(db) if test_tools_on() else [],
                # 칸을 비운 채 눌렀을 때 되돌아오며 실려 오는 말.
                "test_msg": TEST_INPUT_MISSING.get(
                    request.query_params.get("test", ""), "")})
    return templates.TemplateResponse("setup.html", ctx)


@router.post("/setup/ir-root")
def save_ir_root(
    ir_root: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """IR 자료 폴더 자리를 저장한다 — **켜 준 계정의, 본인 것만.**

    ## 왜 켜 준 계정만인가

    이 값을 넣는 것이 곧 자동 첨부를 켜는 일이다(`services/ir_attach.py`).
    화면에서 칸만 감추면 **주소로 그대로 부를 수 있어** 누구든 스스로 켤 수
    있다 — 화면 목록과 라우터 목록이 갈려 막은 줄 알았던 것이 열려 있던 사고를
    이 저장소는 여러 번 겪었다. 판정은 화면과 **같은 함수**를 읽는다
    (`deps.may_auto_attach`).

    막을 때 **403 을 준다.** 되돌려 보낼 화면이 없어서가 아니라, 이 길로 오는
    것은 칸이 그려지지 않은 화면에서 온 요청뿐이기 때문이다 — 사람이 폼을
    눌러서 닿을 수 있는 자리가 아니다. 안내 문구로 답하면 그 문구를 볼 화면이
    없다.

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
    if not may_auto_attach(user):
        raise HTTPException(status_code=403, detail=AUTO_ATTACH_BLOCKED)
    device = _device(db, user)
    device.ir_root = (ir_root or "").strip() or None
    db.commit()
    return RedirectResponse("/setup?saved=ir_root", status_code=303)


def _queue_test_job(db: Session, user: User, kind: str, room: str,
                    message: str, files: list) -> int:
    """시험 잡 한 건을 큐에 넣고 회차 번호를 돌려준다.

    **로그인한 사람 것으로 만든다.** 발송 잡은 그 사람의 기기 토큰으로만 내려가고
    (`routers/agent_api.py: poll` 이 `SendJob.user_id == device.user_id` 로 고른다),
    시험은 **지금 이 PC 의 발송기**가 도는지 보는 일이다. 남의 계정으로 만들면
    잡이 남의 PC 로 내려가 엉뚱한 카톡을 건드린다.

    두 시험이 이 한 곳을 함께 쓴다 — 잡과 건을 세우는 절차를 두 벌로 두면
    한쪽만 고쳐진다(`_requeue` 가 같은 이유로 한 곳에 있다).
    """
    job = SendJob(user_id=user.id, kind=kind, status="queued", total=1,
                  sent=0, failed=0)
    db.add(job)
    db.flush()
    db.add(SendItem(
        job_id=job.id,
        # 담당자가 없다. 이 자리는 명단이 아니라 **적어 넣은 이름**을 시험한다
        # (칸은 이미 비어도 되게 돼 있다 — 딜 소싱 발송이 그렇다).
        contact_id=None,
        room_name=room,
        message=message,
        files_json=json.dumps(files, ensure_ascii=False) if files else None,
        status="pending",
    ))
    db.commit()
    return job.id


@router.post("/setup/test/attach")
def test_attach(
    file_name: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[시험] 파일 첨부 — **시험방으로** 파일 하나와 문구 한 통을 보낸다.

    ## 왜 파일명을 사람이 적나

    서버는 그 PC 의 자료 폴더에 무엇이 들어 있는지 **모른다.** 폴더 자리는 각
    PC 의 값이고(`agent_devices.ir_root`), 목록을 아는 것은 발송기뿐이다.
    그래서 고르는 칸이 아니라 적는 칸이다.

    ## 왜 문구도 함께 보내나

    실제 자료 전달이 **파일 먼저, 문구 나중**이기 때문이다
    (`agent/main.py: send_item`). 파일만 보내면 그 차례와 사이 간격이 시험에서
    빠지고, 정작 실전에서 처음 겪게 된다. 파일이 하나라도 실패하면 문구는
    나가지 않으므로(같은 함수) 시험에서도 "문구만 나가는" 결과는 없다.

    ## 무엇을 보게 되나  ★ 이 시험의 알맹이

    막히면 **그 까닭이 오류 문구로 화면에 그대로 뜬다**(`/jobs/{id}` 의
    `사유 / 시각` 칸 — `static/js/progress.js` 는 서버가 준 `error` 를 손대지
    않고 적는다). 발송기가 보내기 직전에 거는 관문이 그 문구를 만든다:

        시트에 없는 파일: …   자료 폴더에 그 이름이 없거나 카톡이 다른 것을 물었다
        방이 다릅니다: …      앞에 있는 창이 시험방이 아니다
        개수가 다릅니다: …    확인 시트에 뜬 파일 수가 보내려던 수와 다르다

    사람은 그 문구를 읽고 폴더나 파일 이름을 고친다. 그래서 결과를 요약하지
    않고 **있는 그대로** 보여 주는 화면으로 보낸다.

    ## 왜 기다리지 않고 화면으로 보내나

    발송기는 건마다 3~7초를 쉬고, 잡을 집어가는 것도 폴링 주기(기본 3초) 뒤다.
    응답을 붙잡고 기다리면 그동안 화면이 멈추고, 발송기가 안 켜져 있으면 영영
    안 끝난다. 이미 있는 진행 화면이 2초마다 스스로 갱신하므로 그리로 보낸다 —
    발송기가 아직 안 집어갔으면 `대기 중` 으로 정직하게 서 있는다.

    ## 왜 자동 첨부를 켜 준 계정만인가

    발송기는 자료 폴더를 알아야 파일 이름을 실제 경로로 조립하는데, 그 폴더는
    자동 첨부가 켜진 계정에만 내려간다(`routers/agent_api.py: heartbeat`).
    꺼진 계정에서 누르면 **무조건** 실패하고, 그 사람은 `/setup` 에 폴더 칸이
    없어 고칠 수도 없다 — 눌러 봐야 못 고치는 단추를 그려 두는 것은 이 저장소가
    반복해 고쳐 온 거짓말이다. 판정은 폴더 칸과 **같은 함수**를 읽는다.
    """
    room = _test_room()
    if not may_auto_attach(user):
        raise HTTPException(status_code=403, detail=AUTO_ATTACH_BLOCKED)
    name = (file_name or "").strip()
    if not name:
        return RedirectResponse("/setup?test=need_file", status_code=303)
    job_id = _queue_test_job(db, user, TEST_SEND_KIND, room,
                             TEST_FILE_MESSAGE, [name])
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/setup/test/startup-remind")
def test_startup_remind(
    company_id: int = Form(0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[시험] 월말 리마인드 문구 — **시험방으로** 그 문구를 한 통 보낸다.

    ## 왜 이 자리가 필요한가

    스타트업에 매월 보내는 문구는 이미 있다 — `startup_sms`. 그런데 **그 문구를
    보내는 코드가 없어서** 지금까지는 사람이 문구 화면에서 글을 복사해 손으로
    보냈다. 손으로 옮기면 `{담당자명}` 같은 자리를 눈으로 갈아 끼우게 되는데,
    이 저장소는 갈아 끼우는 것을 잊은 `{…}` 가 **글자 그대로** 카톡방에 나간
    적이 있다. 여기서 눌러 보면 실제로 어떤 글자가 나가는지 먼저 보게 된다.

    ## 문구를 여기서 짓지 않는다

    짓는 일은 `services/startup_msg.py` 에 있다. 명단 전체에 실제로 돌리는 길은
    아직 없지만(대상 고르기·중복 방지·이력이 따라붙는 별개의 일이다), 그 길을
    낼 때 문구를 **다시 짜지 않아도 되게** 밖에 빼 두었다. 문구틀의 어느 자리가
    채워지고 어디가 비는지도 그 파일 머리말에 있다.

    ## 왜 기업을 고르게 하나

    아무 값이나 채워 넣으면 그때 보이는 것은 **시험용으로 지어낸 문구**지 실제로
    나갈 문구가 아니다. 명단의 기업을 그대로 쓰면 담당자 성함이 빈 줄·이름에
    괄호가 섞인 줄처럼 **실제 자료가 만드는 모양**이 그대로 드러난다.

    ## 문구틀이 비어 있으면 — **잡을 만들지 않는다**

    코드에 적힌 뼈대를 대신 보내지 않는다. 그것을 보내면 사람은 그것이 팀이 정한
    문구인 줄 알고, 정작 문구틀은 빈 채로 남는다. 대신 어디에 적어야 하는지를
    말로 돌려준다(`TEST_INPUT_MISSING["no_template"]`).

    ## 왜 `may_auto_attach` 를 보지 않나

    이 시험은 **파일을 붙이지 않는다.** 파일 시험이 그 판정을 함께 읽는 것은
    발송기가 자료 폴더를 알아야 파일 이름을 실제 자리로 조립할 수 있기
    때문인데(`routers/agent_api.py: heartbeat`), 문구만 나가는 이 길에는 그
    이유가 없다. 없는 이유로 막으면 못 고치는 단추를 하나 더 그리는 것이다.

    ## 머리말을 붙이지 않는다

    딜소개는 시험 모드에서 `[테스트 발송 → …]` 를 앞에 붙인다
    (`routers/deals.py: _apply_test_room`). 거기서는 150명 몫이 한 방에 쏟아져
    누구에게 갈 문구였는지 알 수 없기 때문이다. 여기는 사람이 기업을 골라 한 통을
    보내는 자리이고, **문구틀이 만든 것과 글자 하나까지 같은지**를 보는 것이 이
    시험의 알맹이다 — 앞에 한 줄이라도 얹으면 그것을 볼 수 없다.
    """
    room = _test_room()
    company = db.get(IrCompany, company_id) if company_id else None
    if company is None:
        # 없는 번호를 밀어 넣은 경우도 같은 길이다 — 고를 수 있는 것은 명단에
        # 있는 기업뿐이고, 없는 것을 골랐다는 말은 화면에 적을 자리가 없다.
        return RedirectResponse("/setup?test=need_company", status_code=303)
    message = startup_msg.compose(db, user, company)
    if not message:
        return RedirectResponse("/setup?test=no_template", status_code=303)
    job_id = _queue_test_job(db, user, TEST_SEND_KIND, room, message, [])
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/setup/test/room")
def test_room_name(
    room_name: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[시험] 카톡방 이름 — **아무것도 보내지 않는다.** 방이 열리는지만 본다.

    ## 새로 만들지 않고 이미 있는 길을 빌린다

    방 이름 대조는 이미 있다 — 내 투자사의 [방 연결 확인] 이 만드는
    `verify_room` 잡이다(`routers/contacts.py: verify_rooms`). 발송기는 그 잡에서
    `send_text` 를 **부르지 않고** 검색만 한다(`agent/main.py:
    process_verify_job`), 진행 화면도 그 잡이면 어휘가 바뀐다
    (`문구는 전송하지 않습니다`). 각자 PC 에 이미 깔려 도는 발송기가 그대로
    처리한다는 것도 크다 — 새 종류를 만들면 발송기를 갱신할 때까지 큐에 멈춘다.

    다른 점은 **담당자가 없다**는 것 하나다. 명단의 방을 대조하는 것이 아니라
    사람이 적어 넣은 이름을 대조한다. 건에 담당자를 안 붙이면 나머지가 저절로
    맞는다 — 서버는 검색어(`query`·`name`·`firm`)를 담당자가 있을 때만 실어
    주므로, 없으면 발송기가 **적어 넣은 방 이름 그대로** 검색한다
    (`routers/agent_api.py: poll`). 결과를 배지에 적는 자리도 담당자가 없으면
    건너뛴다(같은 파일의 `_apply_verify_result`).

    ## 왜 이 자리가 필요한가

    스타트업 방 이름을 아직 아무도 채우지 않았다. 명단에 넣기 **전에** 이름을
    맞춰 보는 자리가 여기다 — 넣고 나서 틀린 것을 알면 명단부터 고쳐야 한다.

    ## 방 이름을 아무거나 적어도 되는 이유

    이 잡은 문구를 보내지 않는다. 건의 `message` 도 빈 문자열이라, 혹시 아주
    낡은 발송기가 이 잡을 발송으로 오해해도 보낼 내용이 없다
    (`verify_rooms` 가 같은 이유로 같은 값을 넣는다).
    """
    _test_room()   # 시험방이 없으면 이 자리 자체가 없다
    name = (room_name or "").strip()
    if not name:
        return RedirectResponse("/setup?test=need_room", status_code=303)
    job_id = _queue_test_job(db, user, "verify_room", name, "", [])
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


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
