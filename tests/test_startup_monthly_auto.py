"""스타트업 월간 발송 — **매월 30일(2월은 말일)에 저절로 예약이 선다.**

1. 날짜 — 30일, 2월은 말일, 그 시각이 지나면 다음 달.
2. 그날 아침 깨어나면 [대기 목록 만들기] 와 **같은 길**로 목록이 서고, 정한
   시각에 나가도록 예약이 걸린다(`draft` — 그 전에는 발송기가 못 가져간다).
3. 한 달에 한 번만 — 두 번 깨어나도 회차는 하나.
4. 그 달 회차가 이미 있으면 세우지 않는다.
5. 보낼 곳이 0곳이면 세우지 않고 오늘 할 일에 사유가 뜬다.
6. 설정은 팀 현황에서 저장되고, 화면에 다음 자동 발송이 적힌다.

이름·회사명은 전부 지어낸 값이다. 날은 `clock.now` 하나만 바꿔 고정한다 —
기업 자료는 실제 이번 달로 심기므로 **이번 달의 그날**로 고정한다.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from tests.conftest import DEMO_PASSWORD
from tests.test_startup_monthly_send import (  # noqa: F401 - 픽스처를 함께 쓴다
    _jobs, _login, _make_draft, _poll, _turn_on, seeded)


def _freeze(monkeypatch, when: datetime) -> datetime:
    from app import clock

    aware = when.astimezone()
    monkeypatch.setattr(clock, "now", lambda: aware)
    return aware


def _run_day_now(hour=9, minute=0) -> datetime:
    """**실제 이번 달**의 그날 그 시각."""
    from app.services import startup_monthly

    today = date.today()
    day = startup_monthly.run_day(today.year, today.month)
    return datetime(day.year, day.month, day.day, hour, minute)


def _monthly_on(db, user_id=1, at="17:00"):
    from app.services import startup_send

    return startup_send.save(db, enabled=True, user_id=user_id,
                             monthly=True, monthly_time=at)


def _row(at="17:00"):
    class Row:
        monthly_time = at
    return Row()


# ── 1. 날짜 ─────────────────────────────────────────────────────────────────

def test_나가는_날은_30일이고_2월은_말일이다():
    from app.services.startup_monthly import run_day

    assert run_day(2026, 10) == date(2026, 10, 30)
    assert run_day(2026, 12) == date(2026, 12, 30)
    assert run_day(2027, 2) == date(2027, 2, 28)
    assert run_day(2028, 2) == date(2028, 2, 29)   # 윤년


def test_다음_자동_발송_시각():
    from app.services.startup_monthly import label, next_run

    def at(*a):
        return datetime(*a).astimezone()

    assert next_run(_row(), at(2026, 10, 7, 10, 0)) == at(2026, 10, 30, 17, 0)
    assert label(next_run(_row(), at(2026, 10, 7, 10, 0))) == "10/30(금) 17:00"
    # 그날 시각 전이면 그날이다.
    assert next_run(_row(), at(2026, 10, 30, 16, 59)) == at(2026, 10, 30, 17, 0)
    # 시각이 지나면 다음 달.
    assert next_run(_row(), at(2026, 10, 30, 17, 0)) == at(2026, 11, 30, 17, 0)
    assert next_run(_row(), at(2026, 10, 31, 9, 0)) == at(2026, 11, 30, 17, 0)
    # 1월 30일이 지나면 2월 말일.
    assert next_run(_row(), at(2027, 1, 30, 18, 0)) == at(2027, 2, 28, 17, 0)
    # 12월 → 다음 해 1월.
    assert next_run(_row(), at(2026, 12, 31, 9, 0)) == at(2027, 1, 30, 17, 0)
    # 사람이 고른 시각.
    assert next_run(_row("09:30"), at(2026, 10, 7, 10, 0)) == at(2026, 10, 30, 9, 30)


def test_시각은_09시_19시_안에서만():
    from app.services.startup_monthly import parse_time

    assert parse_time("9:05") == "09:05"
    assert parse_time("18:50") == "18:50"
    for bad in ("08:59", "19:00", "23:00", "abc", "", "12:61"):
        with pytest.raises(ValueError):
            parse_time(bad)


# ── 2. 그날 목록이 선다 ─────────────────────────────────────────────────────

def test_그날_아침_목록이_서고_정한_시각에_예약이_걸린다(db, seeded, client, monkeypatch):
    from app.services import startup_monthly

    _monthly_on(db, at="17:30")
    now = _freeze(monkeypatch, _run_day_now(9))

    done = startup_monthly.run_once(db)
    assert done["status"] == "ready", done
    assert done["count"] == 1

    jobs = _jobs(db)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "startup_ir"
    assert job.status == "draft"          # 시각 전에는 발송기가 못 가져간다
    assert job.user_id == 1
    assert job.scheduled_at.startswith(f"{now:%Y-%m-%d}T17:30")
    assert [i.ir_company_id for i in job.items] == [seeded["ok"].id]
    assert _poll(client).status_code == 204

    # 오늘 할 일에 예약으로 선다(`standing_for`).
    from app.services import scheduled_send
    from app.models import User
    standing = scheduled_send.standing_for(db, db.get(User, 1), now)
    assert [s["job_id"] for s in standing] == [job.id]


def test_한_달에_한_번만_선다(db, seeded, monkeypatch):
    from app.services import startup_monthly

    _monthly_on(db)
    _freeze(monkeypatch, _run_day_now(9))
    assert startup_monthly.run_once(db)["status"] == "ready"
    _freeze(monkeypatch, _run_day_now(9, 5))
    assert startup_monthly.run_once(db)["status"] == "done"
    assert len(_jobs(db)) == 1


def test_그날이_아니거나_이르거나_늦으면_안_선다(db, seeded, monkeypatch):
    from app.services import startup_monthly

    _monthly_on(db)
    day = _run_day_now(9)
    _freeze(monkeypatch, day.replace(day=day.day - 1))
    assert startup_monthly.run_once(db)["status"] == "not_today"
    _freeze(monkeypatch, _run_day_now(7, 59))
    assert startup_monthly.run_once(db)["status"] == "too_early"
    _freeze(monkeypatch, _run_day_now(17, 0))
    assert startup_monthly.run_once(db)["status"] == "too_late"
    assert _jobs(db) == []


def test_꺼져_있으면_안_선다(db, seeded, monkeypatch):
    from app.services import startup_monthly

    _turn_on(db, user_id=1)              # 메뉴만 켜고 자동은 끔
    _freeze(monkeypatch, _run_day_now(9))
    assert startup_monthly.run_once(db)["status"] == "off"
    assert _jobs(db) == []


def test_그_달_회차가_이미_있으면_세우지_않는다(db, seeded, client, monkeypatch):
    from app.services import startup_monthly

    _monthly_on(db)
    made = _make_draft(_login(client), seeded)
    assert made.status_code == 303
    db.expire_all()
    assert len(_jobs(db)) == 1

    _freeze(monkeypatch, _run_day_now(9))
    done = startup_monthly.run_once(db)
    assert done["status"] == "exists"
    assert done["job_id"] == _jobs(db)[0].id
    assert len(_jobs(db)) == 1


def test_보낼_곳이_0곳이면_세우지_않고_알린다(db, users, monkeypatch):
    from app.services import startup_monthly, today

    _monthly_on(db)
    _freeze(monkeypatch, _run_day_now(9))
    assert startup_monthly.run_once(db)["status"] == "empty"
    assert _jobs(db) == []

    items = today.build(db, users["u1"], _run_day_now().date())
    titles = [i["title"] for i in items["items"]]
    assert any("자동 발송을 세우지 못했습니다" in t for t in titles), items


# ── 3. 설정과 화면 ──────────────────────────────────────────────────────────

def test_팀_현황에서_켜고_시각을_저장한다(db, users, client):
    from app.services import startup_monthly, startup_send

    users["u1"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    page = client.get("/team").text
    assert 'data-testid="startup-monthly-toggle"' in page
    assert 'name="monthly_time"' in page

    client.post("/team/startup-send", data={
        "enabled": "on", "user_id": 1, "monthly": "on", "monthly_time": "16:30"},
        follow_redirects=False)
    db.expire_all()
    row = startup_send.setting(db)
    assert row.monthly_auto == 1 and row.monthly_time == "16:30"
    state = startup_monthly.status(db)
    assert state["on"] and state["next_label"].endswith("16:30")
    assert "다음 자동 발송" in client.get("/team").text

    # 업무시간 밖은 저장되지 않는다.
    client.post("/team/startup-send", data={
        "enabled": "on", "user_id": 1, "monthly": "on", "monthly_time": "21:00"},
        follow_redirects=False)
    db.expire_all()
    assert startup_send.setting(db).monthly_time == "16:30"

    # 끄면 꺼진다.
    client.post("/team/startup-send", data={
        "enabled": "on", "user_id": 1, "monthly": "", "monthly_time": "16:30"},
        follow_redirects=False)
    db.expire_all()
    assert startup_monthly.status(db)["on"] is False


def test_발송_화면에_다음_자동_발송이_적힌다(db, seeded, client):
    _monthly_on(db)
    page = _login(client).get("/deals/startup-ir").text
    assert 'data-testid="startup-monthly-next"' in page
    assert "다음 자동 발송" in page
    assert "발송 프로그램이 켜져 있어야" in page


def test_꺼져_있으면_켜는_곳을_알려_준다(db, seeded, client):
    _turn_on(db, user_id=1)
    page = _login(client).get("/deals/startup-ir").text
    assert 'data-testid="startup-monthly-off"' in page
