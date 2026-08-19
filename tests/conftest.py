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

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

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

    u1 = User(id=1, name="강민준", phone="01000000001", role="user")
    u2 = User(id=2, name="윤서아", phone="01000000002", role="user")
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


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
