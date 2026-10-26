"""테스트 공통 설정.

앱은 import 시점에 ``config.DATABASE_URL`` 로 엔진을 만든다. 그래서 **어떤 app 모듈보다
먼저** 임시 DB 경로를 환경변수에 심어야 한다. conftest 는 테스트 모듈보다 먼저 import 되므로
여기 최상단이 그 자리다(운영 DB를 건드리지 않기 위한 안전장치이기도 하다).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dealflow-test-"))
os.environ["DEALFLOW_DATA_DIR"] = str(_TMP)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["DEALFLOW_TEST_ROOM"] = ""  # 테스트 모드 OFF (발송 대상 치환이 끼어들지 않게)
# 방 이름 접미사는 조직마다 다르고 .env 로 실제 값을 준다. 테스트가 그 값을 읽으면
# 실행 환경에 따라 결과가 달라지고, 공개 저장소에 실제 상호가 기대값으로 박힌다.
os.environ["DEALFLOW_ROOM_SUFFIX"] = "Deal 공유 우리브이씨 Asset"
os.environ["DEALFLOW_SEED_DEMO"] = "0"
# 일일 백업 실을 끈다. 검사는 앱을 수십 번 만들었다 버리는데, 그때마다 실이 뜨고
# 임시 폴더에 .db 를 쓰면 서로를 밟는다(백업 자체는 따로 검사한다).
os.environ["DEALFLOW_DAILY_BACKUP"] = "0"
# 메일 설정도 꺼 둔다. 켜져 있는 환경에서 돌리면 '메일 채널이 꺼져 있다'는
# 검사가 그 환경 때문에 실패한다(방 이름 접미사에서 이미 겪었다).
for _name in ("HOST", "PORT", "USER", "PASSWORD", "FROM", "TLS", "SSL"):
    os.environ[f"DEALFLOW_SMTP_{_name}"] = ""
# 문자 발송 설정도 비운다. 이유가 둘이다.
#   1. 켜져 있는 환경에서 돌리면 '안 켜면 아무 일도 없다' 는 검사가 그 환경
#      때문에 실패한다(메일 설정에서 이미 겪었다).
#   2. **실수로라도 진짜 문자가 나가면 안 된다.** 설정이 비면 알림 실이 뜨지
#      않고, 발송 코드는 그 앞에서 멈춘다. 검사는 가짜 발송기만 쓴다.
for _name in ("API_KEY", "API_SECRET", "FROM"):
    os.environ[f"DEALFLOW_SMS_{_name}"] = ""
# 딜 소싱 메일 확인(POP3)도 비운다 — 켜진 환경에서 돌리면 진짜 편지함에 붙고,
# '설정이 없으면 꺼짐' 검사가 그 환경 때문에 실패한다. 비밀값도 비운다 — 잠그는
# 검사는 그 검사가 스스로 넣는다.
for _name in ("HOST", "PORT", "USER", "PASSWORD"):
    os.environ[f"DEALFLOW_POP3_{_name}"] = ""
os.environ["DEALFLOW_SECRET_KEY"] = ""
os.environ["DEALFLOW_DOMAIN"] = ""
# 테스트 서버의 '보내는 시간 제한 끄기' 스위치를 지운다. 테스트 서버 컨테이너
# 안에서 검사를 돌려도 **운영과 같은 09~19시**로 돈다(`app/services/send_window.py`).
# 스위치를 보는 검사는 그 검사가 스스로 켠다.
os.environ.pop("DEALFLOW_TEST_SERVER_NO_SEND_WINDOW", None)

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 테스트 계정 공용 비밀번호
DEMO_PASSWORD = "dealflow123"

DEMO_TOKEN = "agt_test_token_user1"
OTHER_TOKEN = "agt_test_token_user2"


@pytest.fixture(autouse=True)
def _send_window_open(request):
    """**발송 시간 관문(09~19시)을 검사 중에는 열어 둔다.**

    `poll` 은 지금 시각이 09~19시 밖이면 문구 잡을 내주지 않는다
    (`services/send_guard.py`). 실제 시계로 재면 **밤에만 깨지는 검사**가
    수백 개 생긴다 — 발송기 폴링을 쓰는 검사가 그만큼 많다. 그래서 관문 하나만
    늘 열어 두고, 관문 자체를 보는 검사는 `@pytest.mark.send_window` 를 달아
    진짜 판정을 쓴다(시각은 그 검사가 `now=` 로 못박는다).
    """
    if request.node.get_closest_marker("send_window"):
        yield
        return
    from app.services import send_guard

    # `monkeypatch` 를 **쓰지 않는다.** 모든 검사에 붙는 고정물이 `monkeypatch`
    # 를 잡으면 그 고정물이 검사 파일의 고정물보다 **먼저 서고 나중에 걷힌다** —
    # 그러면 파일 쪽 정리(예: `test_production_guard._restore` 의 설정 다시
    # 읽기)가 환경변수가 아직 안 돌아온 채로 돌아, 다음 검사들이 운영 설정으로
    # 뜬다. 손으로 바꾸고 손으로 되돌린다.
    real = send_guard.window_open
    send_guard.window_open = lambda now=None: True
    try:
        yield
    finally:
        send_guard.window_open = real


@pytest.fixture(autouse=True)
def _revenue_year_2026():
    """**연도별 매출 칸이 서는 해를 2026 으로 못 박는다**(#75 · `services/revenue_years.py`).

    표 · 수정창 · 한줄 소개가 올해 기준 지난 세 해를 세운다. 실제 시계로 두면
    `23년 매출` · `매출 23년 2억` 을 재는 검사들이 **2027년 1월 1일에 한꺼번에**
    깨진다. 해를 바꿔 보는 검사는 스스로 민다(tests/test_revenue_years.py 의 `at`).
    위와 같은 까닭으로 `monkeypatch` 를 쓰지 않고 손으로 바꾸고 되돌린다.
    """
    from app.services import revenue_years

    real = revenue_years.this_year
    revenue_years.this_year = lambda: 2026
    try:
        yield
    finally:
        revenue_years.this_year = real


@pytest.fixture()
def db():
    """매 테스트마다 빈 스키마. (SQLite 파일 하나라 drop/create 가 가장 단순하고 빠르다)"""
    import app.models  # noqa: F401  (Base.metadata 에 모델 등록)
    from app.db import Base, SessionLocal, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def users(db):
    """사용자 2명 + 각자의 에이전트 기기(토큰). 사용자 간 격리 검증용."""
    from app.models import AgentDevice, User

    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    u1 = User(id=1, name="강민준", phone="01000000001", role="user", password_hash=pw)
    u2 = User(id=2, name="윤서아", phone="01000000002", role="user", password_hash=pw)
    db.add_all([u1, u2])
    db.flush()
    db.add_all([
        AgentDevice(user_id=u1.id, token=DEMO_TOKEN, hostname="mac-test"),
        AgentDevice(user_id=u2.id, token=OTHER_TOKEN, hostname="win-test"),
    ])
    db.commit()
    return {"u1": u1, "u2": u2}


@pytest.fixture()
def client(db, users):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def demo_user_password():
    return DEMO_PASSWORD


@pytest.fixture()
def logged_in(client, users):
    """u1 으로 로그인된 클라이언트. 화면/사용자 API 테스트의 기본 상태."""
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
