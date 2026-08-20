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

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 테스트 계정 공용 비밀번호
DEMO_PASSWORD = "dealflow123"

DEMO_TOKEN = "agt_test_token_user1"
OTHER_TOKEN = "agt_test_token_user2"


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
