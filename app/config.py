"""Application configuration.

All values are read from environment variables with sensible local defaults.
Kakao automation numbers (delays / caps) live in the agent's config.yaml — NOT here —
per ROADMAP "스프린트 공통 원칙 2" (no hardcoded send-rate constants).
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root: .../dealflow
BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite file (WAL mode enabled in db.py). Override with DATABASE_URL for Postgres later.
DATA_DIR = Path(os.environ.get("DEALFLOW_DATA_DIR", BASE_DIR / "data"))
DEFAULT_DB_PATH = DATA_DIR / "dealflow.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

# Sprint 1: single hardcoded user session (auth is Sprint 4).
CURRENT_USER_ID = int(os.environ.get("DEALFLOW_CURRENT_USER_ID", "1"))

# 데모 데이터(가상 담당자·기업·사용자)를 넣을지. 기본은 끈다 — 실데이터가 들어간 뒤
# 컨테이너를 다시 띄웠다가 화면에 샘플 기업이 섞여 보인 적이 있다.
SEED_DEMO = os.getenv("DEALFLOW_SEED_DEMO", "0") == "1"

# ── 어디서 도는가 ─────────────────────────────────────────────────────────────
# 로컬(기본)이면 편하게 쓰라고 기본값을 준다. 인터넷에 올릴 때는 그 기본값이
# 그대로 구멍이 된다 — **저장소가 공개**라 기본 토큰·비밀번호를 누구나 안다.
# `DEALFLOW_ENV=production` 이면 기본값을 쓰는 것을 막는다(아래 assert_ready).
ENV = os.environ.get("DEALFLOW_ENV", "local").strip().lower()
IS_PRODUCTION = ENV == "production"

# Demo agent token seeded into agent_devices and shared with the mock agent container.
DEFAULT_AGENT_TOKEN = "agt_demo_token_sprint1"
DEMO_AGENT_TOKEN = os.environ.get("DEALFLOW_AGENT_TOKEN", DEFAULT_AGENT_TOKEN)

# An agent is considered "connected" if it polled/heartbeat within this many seconds.
AGENT_ONLINE_WINDOW_SEC = int(os.environ.get("DEALFLOW_AGENT_ONLINE_WINDOW_SEC", "30"))

# Message length warning threshold (FEATURE_SPEC §5: 카톡 장문 붙여넣기 안정성).
MESSAGE_WARN_CHARS = 3000

# 신규 계정의 초기 비밀번호. 전원 동일하게 발급하고, 첫 로그인 시 변경을 강제한다
# (must_change_password=1). 운영에서는 반드시 .env 로 바꿔서 쓸 것.
DEFAULT_INITIAL_PASSWORD = "dealflow123"
INITIAL_PASSWORD = os.environ.get("DEALFLOW_INITIAL_PASSWORD", DEFAULT_INITIAL_PASSWORD)


def production_problems() -> list:
    """인터넷에 올리기 전에 반드시 바꿔야 하는 것들.

    주석으로 "운영에서는 바꿔 쓸 것" 이라고 적어 두었지만, 적어 둔 것은
    지켜지지 않는다. 여기서 **뜨지 않게** 막는다.

    - 초기 비밀번호: 계정을 새로 만들면 이 값으로 발급된다. 저장소가 공개라
      **이미 아무나 아는 값**이고, 첫 로그인 전까지 그 계정으로 들어올 수 있다.
    - 데모 데이터: 실데이터 위에 가상 기업·담당자가 섞인다.
    - 에이전트 토큰: 평소에는 계정별 난수라 이 기본값이 쓰이지 않는다. 다만
      데모 시드가 켜지면 이 값으로 기기가 등록되고, 그러면 발송 대기열을
      가져갈 수 있는 열쇠가 된다. 둘이 겹치는 사고를 막는 이중 잠금이다.
    """
    problems = []
    if DEMO_AGENT_TOKEN == DEFAULT_AGENT_TOKEN:
        problems.append(
            "DEALFLOW_AGENT_TOKEN 이 저장소 기본값입니다 — 데모 시드가 켜지면 "
            "이 공개된 값으로 기기가 등록됩니다. "
            "`openssl rand -hex 24` 로 만들어 .env 에 넣으세요")
    if INITIAL_PASSWORD == DEFAULT_INITIAL_PASSWORD:
        problems.append(
            "DEALFLOW_INITIAL_PASSWORD 가 저장소 기본값입니다 — "
            "새 계정이 공개된 비밀번호로 발급됩니다")
    if SEED_DEMO:
        problems.append(
            "DEALFLOW_SEED_DEMO=1 입니다 — 실데이터에 가상 기업·담당자가 섞입니다")
    return problems


def assert_ready() -> None:
    """운영이면 문제가 있는 채로 뜨지 않는다.

    조용히 뜨고 나면 아무도 확인하지 않는다. 시작을 막고 무엇을 고쳐야 하는지
    그 자리에서 알려 주는 편이 낫다.
    """
    if not IS_PRODUCTION:
        return
    problems = production_problems()
    if problems:
        raise RuntimeError(
            "운영 설정이 덜 됐습니다 (DEALFLOW_ENV=production):\n  - "
            + "\n  - ".join(problems))

# ── 테스트 모드 ───────────────────────────────────────────────────────────────
# 값이 있으면 **모든 발송이 이 카톡방 하나로만** 나간다(실제 담당자 방으로 가지 않음).
# 실투자사 150명에게 실수로 발송되는 사고를 막기 위한 안전장치.
# 예: DEALFLOW_TEST_ROOM="본인 이름"  (카카오톡 '나와의 채팅' 방 제목)
# 비워두면 평소대로 각 담당자의 방으로 발송된다.
TEST_ROOM = os.environ.get("DEALFLOW_TEST_ROOM", "").strip()

# ── 일일 백업 ─────────────────────────────────────────────────────────────────
# 무엇을 왜 이렇게 두었는지는 `app/services/backup.py` 머리말에 있다. 짧게:
# 호스트 크론에 걸어 두었더니 **서버를 다시 세울 때 같이 사라졌고**, 사라진 것을
# 아무도 몰랐다. 그래서 이미지 안에서 돈다.
#
# 끌 수 있게 두는 것은 **검사 때문**이다. 검사는 앱을 수십 번 만들었다 버리는데
# 그때마다 백업 실이 뜨고 임시 폴더에 파일을 쓰면 검사가 느려지고 서로를 밟는다
# (tests/conftest.py 가 0 으로 둔다). 운영에서 끄라고 둔 손잡이가 아니다.
BACKUP_ENABLED = os.getenv("DEALFLOW_DAILY_BACKUP", "1") == "1"

# 며칠 치를 남기나. 사용자가 "1주일이면 충분하다" 고 했다.
# DB 한 개가 3MB 안팎이고 서버 여유가 29G 라 늘려도 부담은 없다.
BACKUP_KEEP_DAILY_DAYS = int(os.getenv("DEALFLOW_BACKUP_KEEP_DAYS", "7"))

# ── 이 서비스의 주소 ──────────────────────────────────────────────────────────
# Caddy 가 인증서를 받는 그 이름이다(`deploy/.env` 의 `DEALFLOW_DOMAIN`,
# `deploy/Caddyfile` 이 같은 값을 읽는다). 문자로 보내는 링크가 이 주소를 쓴다 —
# 주소를 코드에 박으면 도메인을 옮기는 날 **문자에 적힌 주소만** 옛것으로 남고,
# 그 문자를 받은 사람은 링크가 죽었다는 것을 눌러 봐야 안다.
#
# 함수인 이유는 메일 설정과 같다: 부를 때마다 환경변수를 다시 읽는다. 모듈
# 상수로 굳혀 두면 검사에서 값을 바꿔 끼울 수 없고, 무엇보다 "지금 켜져 있나"
# 를 화면이 물어볼 때 굳은 값을 돌려준다.
def domain() -> str:
    """`dealflow.example.org` 처럼 **호스트 이름만**. 없으면 빈 문자열."""
    return os.environ.get("DEALFLOW_DOMAIN", "").strip().strip("/")


def base_url() -> str:
    """`https://dealflow.example.org`. 주소가 없으면 빈 문자열.

    **https 로 고정한다.** 이 앱은 Caddy 뒤에서만 열리고 Caddy 는 http 를
    https 로 올린다(`deploy/Caddyfile`). 스킴까지 설정으로 받으면 실수로 http 가
    들어갔을 때 그 링크가 문자로 나간다.
    """
    host = domain()
    if not host:
        return ""
    # 이미 스킴이 붙어 들어온 값도 받아 준다 — `.env` 에 주소를 통째로 적는
    # 사람이 있고, 그때 `https://https://…` 가 되면 링크가 조용히 죽는다.
    if host.startswith("http://") or host.startswith("https://"):
        return "https://" + host.split("://", 1)[1]
    return f"https://{host}"


STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
