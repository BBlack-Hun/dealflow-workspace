"""회차 준비 점검 · 규칙 밖 회차일.

발송 당일에 "왜 안 나가지?"를 찾는 것은 늦다. 막히는 자리는 정해져 있다 —
발송 프로그램이 안 켜져 있거나, 방 제목이 실제와 다르거나, 보낼 기업이 안
골라져 있다. 그것들을 '막힘' 으로 잡는다.

**시험방은 더는 '막힘' 이 아니다.** 예전에는 실발송인데 시험방이 켜져 있으면
막았다 — 그때는 시험방이 켜진 순간 발송이 전부 그 방으로 모였기 때문이다.
이제 일반 발송은 시험방을 읽지 않으므로(`tests/test_test_room_scope.py`)
막을 사고가 없다. 막을 것이 없는데 막으면 사람은 빨강을 안 믿게 되고,
**진짜 빨강도 같이 지나친다.** 리허설 쪽만 그대로 막는다 — 시험방 제목이
없으면 리허설 담당자를 만들 수가 없다.
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


def test_rehearsal_without_a_test_room_is_blocked(db, ready_state, monkeypatch):
    """리허설인데 시험방이 없으면 리허설 담당자를 만들 수가 없다.

    리허설이 안전한 까닭은 **그 담당자의 방 이름이 시험방**이기 때문이다
    (`scripts/rehearsal.py`). 방 제목이 없으면 그 담당자가 안 만들어진다.
    """
    from app import config
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "")
    result = readiness.report(db, ready_state, rehearsal=True)
    titles = [c["title"] for c in result["blocked"]]
    assert "시험방" in titles


def test_live_send_with_a_test_room_is_not_blocked(db, ready_state, monkeypatch):
    """★ 시험방이 켜져 있어도 실발송을 막지 않는다.

    예전에는 여기가 `BLOCK` 이었고 그럴 만했다 — 시험방이 켜져 있으면 발송이
    전부 그 방으로 모였으니 끄지 않고 보내면 투자사가 아무것도 못 받았다.
    이제 일반 발송은 시험방을 읽지 않는다. 막을 사고가 없는데 계속 막으면
    사람은 이 화면의 빨강을 "또 그 소리" 로 읽고 **다음 빨강도 같이 지나친다.**
    """
    from app import config
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "나와의 채팅")
    result = readiness.report(db, ready_state, rehearsal=False)

    assert not result["blocked"], [c["title"] for c in result["blocked"]]
    assert result["ready"] is True
    # 막지는 않되 **켜져 있다는 사실은 적는다** — 모른 채 누르면 안 된다.
    room_check = next(c for c in result["checks"] if c["title"] == "시험방")
    assert "나와의 채팅" in room_check["detail"]
    assert "/setup" in room_check["detail"]


def test_a_test_room_no_longer_means_rehearsal(db, ready_state, monkeypatch):
    """★ `rehearsal` 을 안 주면 **실발송 기준**이다.

    예전 기본값은 `bool(config.TEST_ROOM)` 이었다 — 시험방이 켜져 있으면 그날
    나가는 것이 전부 시험방행이었으니 "지금은 리허설" 이 사실이었다. 지금
    그대로 두면 **진짜 회차 날 아침에 "리허설 점검" 이라고 적힌 화면**을 보게
    되고, 거기 적힌 "실제 담당자에게는 가지 않습니다" 는 거짓말이다.
    """
    from app import config
    from app.services import readiness

    monkeypatch.setattr(config, "TEST_ROOM", "나와의 채팅")
    assert readiness.report(db, ready_state)["rehearsal"] is False


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


def test_the_detail_page_draws_both_modes(logged, ready_state, monkeypatch):
    """점검 화면이 두 기준을 **둘 다 그려야** 한다 — 그리고 서로 오갈 수 있어야.

    예전에는 시험방이 켜져 있으면 리허설 점검이 저절로 떴다. 그 추측을 없앴으니
    (`readiness.report`) 리허설 점검으로 가는 길을 화면에 두지 않으면, 주소를
    아는 사람만 볼 수 있는 화면이 된다.
    """
    from app import config

    monkeypatch.setattr(config, "TEST_ROOM", "나와의 채팅")

    live = logged.get("/readiness/detail")
    assert live.status_code == 200
    assert "실발송 점검" in live.text
    assert "시험방이 켜져 있어도 그렇습니다" in live.text
    assert "/readiness/detail?mode=rehearsal" in live.text

    rehearsal = logged.get("/readiness/detail?mode=rehearsal")
    assert rehearsal.status_code == 200
    assert "리허설 점검" in rehearsal.text
    assert "/readiness/detail?mode=live" in rehearsal.text


def test_the_detail_page_no_longer_tells_people_to_flip_the_test_room(
        logged, ready_state, monkeypatch):
    """★ "테스트 모드를 켜고 딜 제안 관리에서 한 건" 은 이제 **실발송 지시**다.

    그 문장이 맞던 때는 시험방을 켜면 발송이 전부 그리로 갔기 때문이다.
    남겨 두면 화면이 회차 전날 실제 투자사에게 보내라고 시키는 것이 된다.
    """
    from app import config

    monkeypatch.setattr(config, "TEST_ROOM", "")
    html = logged.get("/readiness/detail").text

    assert "테스트 모드를 켜고" not in html
    assert "모든 발송이 그 방 하나로만" not in html
    # 대신 발송기 확인은 `/setup` 의 시험 단추로 보낸다.
    assert "시험 단추" in html


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
