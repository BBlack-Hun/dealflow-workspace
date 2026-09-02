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


def test_readiness_moved_into_the_weekly_page(logged, ready_state):
    """회차 준비 점검은 주간 업무 화면으로 합쳤다 — 아침에 두 군데를 열지 않게.

    여러 곳에서 /readiness 를 부르고 있어 길만 돌려 둔다.
    """
    moved = logged.get("/readiness", follow_redirects=False)
    assert moved.status_code == 307
    assert moved.headers["location"].startswith("/todo")

    page = logged.get("/todo")
    assert page.status_code == 200
    assert "회차 준비 점검" in page.text


def test_멈춰_둔_사람은_회차_준비_점검에서도_발송_대상이_아니다(db, users, ready_state,
                                                monkeypatch):
    """**발송 대상 수를 말하는 자리가 여럿이다.**

    딜 제안 관리에서 빠진 사람이 회차 직전 점검에서는 대상으로 잡히면, 보내기
    직전에 두 화면이 다른 수를 말한다 — 쓰는 사람은 어느 쪽을 믿을지 알 수
    없다. 판정은 `sheet_owner.can_send_to` 한 곳을 지난다.
    """
    from app import config
    from app.models import VcContact
    from app.services import readiness, sheet_owner

    monkeypatch.setattr(config, "TEST_ROOM", "")

    def 발송_대상():
        checks = readiness.report(db, ready_state, rehearsal=False)["checks"]
        return next(c for c in checks if c["title"] == "발송 대상")

    # 방까지 다 있는 사람 하나를 더 둔다 — 멈춘 뒤에 수가 실제로 줄어야 한다.
    db.add(VcContact(user_id=users["u1"].id, name="멈출이", firm="다라인베스트",
                     source_sheet="내 명단", channel_kakao=1,
                     kakao_room_name="멈출이 방", room_verified="verified",
                     connect_stage="connected"))
    db.commit()
    assert 발송_대상()["detail"].startswith("2명"), 발송_대상()

    row = db.query(VcContact).filter_by(name="멈출이").one()
    row.status = sheet_owner.STATUS_PAUSED
    db.commit()

    said = 발송_대상()["detail"]
    assert said.startswith("1명"), f"멈춰 뒀는데 점검이 여전히 대상으로 센다: {said}"
    # 명단에서 사라진 것은 아니다 — 감추기가 아니라 멈추기다.
    assert "명단 2명 중" in said, said
    assert 발송_대상()["detail"].startswith(
        f"{len(sheet_owner.recipients(db, ready_state))}명"), (
        "회차 준비 점검이 딜 제안 관리와 다른 수를 말한다")
