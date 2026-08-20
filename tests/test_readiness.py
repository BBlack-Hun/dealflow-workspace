"""회차 준비 점검 · 규칙 밖 회차일.

발송 당일에 "왜 안 나가지?"를 찾는 것은 늦다. 막히는 자리는 정해져 있고,
그중 가장 위험한 두 가지는 서로 정반대다.

- **리허설인데 테스트 모드가 꺼져 있다** → 실제 투자사에게 연습 문구가 나간다
- **실발송인데 테스트 모드가 켜져 있다** → 아무에게도 안 나가고 나갔다고 착각한다

둘 다 '막힘'으로 잡는다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def ready_state(db, users):
    """보낼 수 있는 상태를 만든다."""
    from app.models import AgentDevice, IrCompany, MessageTemplate, SheetOwner, VcContact

    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스",
                  source_sheet="내 명단", channel_kakao=1,
                  kakao_room_name="홍길동 방", room_verified="verified",
                  connect_stage="connected"),
        IrCompany(name="샘플애그", one_liner="B2B 농산물", revenue_recent=12),
        MessageTemplate(user_id=None, kind="opening_first", body="안녕하세요", is_active=1),
        MessageTemplate(user_id=None, kind="closing_day1", body="공유드립니다", is_active=1),
    ])
    device = db.execute(
        __import__("sqlalchemy").select(AgentDevice).where(
            AgentDevice.user_id == users["u1"].id)
    ).scalars().first()
    device.last_poll_at = datetime.now(timezone.utc).isoformat()
    device.sender = "kakao_mac"
    db.commit()
    return users["u1"]


# --- 규칙 밖 회차일 ---------------------------------------------------------

def test_one_off_date_is_included(db):
    """'다음 회차는 8/26' 처럼 규칙 밖 날짜가 내려온다."""
    from app.models import ScheduleRule
    from app.services import cadence

    db.add(ScheduleRule(key="deal_cycle", label="딜소개 회차",
                        kind="monthly_weekday", weekday=2, nth_weeks="1,3",
                        skip_weekend=1, extra_dates="2026-08-26"))
    db.commit()
    days = cadence.upcoming_send_dates(db, date(2026, 8, 20), count=2)
    assert days[0] == date(2026, 8, 26)      # 규칙(9/2)보다 앞선다


def test_skip_date_is_removed(db):
    from app.models import ScheduleRule
    from app.services import cadence

    db.add(ScheduleRule(key="deal_cycle", label="딜소개 회차",
                        kind="monthly_weekday", weekday=2, nth_weeks="1,3",
                        skip_weekend=1, skip_dates="2026-09-02"))
    db.commit()
    days = cadence.upcoming_send_dates(db, date(2026, 8, 20), count=1)
    assert days[0] == date(2026, 9, 16)


def test_bad_dates_are_ignored(db):
    """형식이 틀린 값 때문에 회차일 계산이 죽으면 안 된다."""
    from app.models import ScheduleRule
    from app.services import cadence

    db.add(ScheduleRule(key="deal_cycle", label="딜소개 회차",
                        kind="monthly_weekday", weekday=2, nth_weeks="1,3",
                        skip_weekend=1, extra_dates="8/26, 내일, 2026-08-26"))
    db.commit()
    days = cadence.upcoming_send_dates(db, date(2026, 8, 20), count=1)
    assert days[0] == date(2026, 8, 26)


# --- 준비 점검 --------------------------------------------------------------

def test_everything_ready(db, ready_state, monkeypatch):
    from app import config
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "")
    result = readiness.report(db, ready_state, rehearsal=False)
    assert result["ready"] is True
    assert not result["blocked"]


def test_rehearsal_without_test_room_is_blocked(db, ready_state, monkeypatch):
    """리허설인데 테스트 모드가 꺼져 있으면 실제 투자사에게 나간다."""
    from app import config
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "")
    result = readiness.report(db, ready_state, rehearsal=True)
    titles = [c["title"] for c in result["blocked"]]
    assert "테스트 모드" in titles


def test_live_send_with_test_room_is_blocked(db, ready_state, monkeypatch):
    """실발송인데 테스트 모드가 켜져 있으면 아무에게도 안 나간다."""
    from app import config
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "나와의 채팅")
    result = readiness.report(db, ready_state, rehearsal=False)
    titles = [c["title"] for c in result["blocked"]]
    assert "테스트 모드" in titles


def test_stale_agent_is_blocked(db, ready_state, monkeypatch):
    from sqlalchemy import select

    from app import config
    from app.models import AgentDevice
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "")
    device = db.execute(select(AgentDevice).where(
        AgentDevice.user_id == ready_state.id)).scalars().first()
    device.last_poll_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db.commit()

    result = readiness.report(db, ready_state, rehearsal=False)
    assert any(c["title"] == "발송 프로그램" for c in result["blocked"])


def test_mock_sender_is_blocked(db, ready_state, monkeypatch):
    """연습 모드로 붙어 있으면 보낸 것처럼 처리되고 실제로는 안 나간다."""
    from sqlalchemy import select

    from app import config
    from app.models import AgentDevice
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "")
    device = db.execute(select(AgentDevice).where(
        AgentDevice.user_id == ready_state.id)).scalars().first()
    device.sender = "mock"
    db.commit()

    result = readiness.report(db, ready_state, rehearsal=False)
    assert any(c["title"] == "발송 프로그램" for c in result["blocked"])


def test_no_sendable_target_is_blocked(db, users, monkeypatch):
    from app import config
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "")
    result = readiness.report(db, users["u1"], rehearsal=False)
    assert any(c["title"] == "발송 대상" for c in result["blocked"])


def test_page_opens(logged, ready_state):
    r = logged.get("/readiness")
    assert r.status_code == 200
    assert "다음 딜 제안" in r.text
