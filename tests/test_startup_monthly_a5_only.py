"""#31 스타트업 월간 발송은 **A5 하나**다 — 옛 30일 자동을 걷었다.

사용자 결정(2026-10-17, "추천대로"):

1. 옛 30일 자동(`services/startup_monthly` 의 실 · `monthly_auto`)은 걷는다. 표와
   이력(`auto_send_settings` · `auto_send_runs`)은 남긴다.
2. 매월은 A5 하나 — 기본 순환은 **월말** `26 11:00 / 30 13:00 / 28 14:00`(30일이
   없으면 말일). 그날이 토·일이면 **앞 평일**(다음 달로 넘어가지 않는다).
   같은 달 두 번은 없다(`month_job` — 사람이 세운 것 · 옛 자동이 세운 것도 센다).
3. A5 의 보내는 계정은 **스타트업 월간 발송 메뉴의 계정**과 같다 — 다른 계정은
   받지 않고, 판에 그 계정을 보여 준다. 메뉴 판은 `메뉴·보내는 계정` 만 남는다.
4. `/deals/startup-ir` 머리에 A5 의 다음 날짜, 꺼져 있으면 `A5 꺼짐`.

이름·회사명은 전부 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import threading
from datetime import date, datetime
from urllib.parse import unquote

import pytest

from tests.conftest import DEMO_PASSWORD
from tests.test_startup_monthly_send import (  # noqa: F401 - 픽스처를 함께 쓴다
    _jobs, _login, _turn_on, seeded)

TEST_ROOM = "자동화 시험방"


def _defaults():
    from app.services.automations import startup_monthly as a5

    return {"slots": a5.DEFAULT_SLOTS, "variants": 3}


def _a5(db, *, enabled=True, test=True, user_id=None):
    from app.services import automation

    return automation.save(db, automation.STARTUP_MONTHLY, enabled=enabled,
                           user_id=user_id, test_mode=test, test_room=TEST_ROOM)


def _admin_client(client, db, users):
    users["u1"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


# ── 1. 옛 30일 자동은 없다 ──────────────────────────────────────────────────

def test_the_old_thirtieth_engine_is_gone(db, users, client):
    """`monthly_auto` 가 켜진 줄이 남아 있어도 실이 뜨지 않는다 — A5 [중단] 뒤에
    30일에 다시 보내거나, A5 가 실패한 달에 다른 글을 조용히 보내던 길이 없다."""
    from app.models import AutoSendSetting
    from app.services import startup_monthly

    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=1,
                           monthly_auto=1, monthly_time="17:00"))
    db.commit()
    assert not hasattr(startup_monthly, "run_once")
    assert not hasattr(startup_monthly, "start_scheduler")
    assert "startup-monthly" not in {t.name for t in threading.enumerate()}


# ── 2. 월말 순환 · 주말이면 앞 평일 ─────────────────────────────────────────

def test_default_rotation_is_month_end():
    from app.services.automations import startup_monthly as a5

    values = _defaults()
    assert a5.DEFAULT_SLOTS == ["26 11:00", "30 13:00", "28 14:00"]
    assert a5.slot_for(values, 2026, 10) == (date(2026, 10, 26), "11:00")
    assert a5.slot_for(values, 2026, 11) == (date(2026, 11, 30), "13:00")
    assert a5.slot_for(values, 2026, 12) == (date(2026, 12, 28), "14:00")
    assert a5.slot_for(values, 2027, 1) == (date(2027, 1, 26), "11:00")
    # 2월엔 30일이 없어 말일(28일 · 일요일) → 앞 평일 금요일.
    assert a5.slot_for(values, 2027, 2) == (date(2027, 2, 26), "13:00")
    assert [a5.variant_for(values, date(2026, m, 1)) for m in (10, 11, 12)] == [1, 2, 3]


def test_a_weekend_slot_moves_to_the_previous_weekday():
    from app.services.automations import startup_monthly as a5

    one = {"slots": ["26 11:00"], "variants": 1}
    assert date(2026, 9, 26).weekday() == 5                  # 토
    assert a5.slot_for(one, 2026, 9) == (date(2026, 9, 25), "11:00")
    assert date(2027, 9, 26).weekday() == 6                  # 일
    assert a5.slot_for(one, 2027, 9) == (date(2027, 9, 24), "11:00")
    # 앞 평일이 지난달이면(1일이 주말) 그 달 첫 평일 — 다른 달로 넘어가지 않는다.
    first = {"slots": ["1 10:00"], "variants": 1}
    assert date(2026, 8, 1).weekday() == 5
    assert a5.slot_for(first, 2026, 8) == (date(2026, 8, 3), "10:00")


def test_the_plan_fires_on_the_moved_day_only(db, users):
    from app.models import Automation
    from app.services import automation
    from app.services.automations import startup_monthly as a5

    row = Automation(key=automation.STARTUP_MONTHLY, enabled=1, test_mode=1,
                     params='{"slots": ["26 11:00"], "variants": 1}')
    assert a5.plan(db, row, date(2026, 9, 26)) is None       # 토 — 안 선다
    plan = a5.plan(db, row, date(2026, 9, 25))
    assert plan is not None and plan.at.strftime("%m/%d %H:%M") == "09/25 11:00"


def test_panel_summary_says_month_end():
    from app.services import automation

    summary = automation.BY_KEY[automation.STARTUP_MONTHLY].summary
    assert "26일 11:00" in summary and "30일" in summary and "28일 14:00" in summary
    assert "앞 평일" in summary


# ── 3. 보내는 계정 = 스타트업 월간 발송 메뉴의 계정 ─────────────────────────

def test_a5_takes_the_menu_sender_and_refuses_another(db, users):
    from app.services import automation

    _turn_on(db, user_id=1)
    with pytest.raises(ValueError, match="메뉴"):
        _a5(db, user_id=users["u2"].id)
    db.rollback()
    row = _a5(db, user_id=None)
    assert row.user_id == 1
    assert automation.sender(db, row).id == 1


def test_a5_cannot_be_turned_on_while_the_menu_is_off(db, users):
    with pytest.raises(ValueError, match="메뉴"):
        _a5(db)
    db.rollback()
    row = _a5(db, enabled=False)          # 꺼 둔 채 값만 저장하는 것은 된다
    assert row.enabled == 0


def test_changing_the_menu_sender_moves_a5_and_stops_its_jobs(db, users, client, seeded):
    from app.models import SendJob
    from app.services import automation, automation_runner as runner
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=False)
    # 이번 달 순환 날 아침에 회차가 선다(1번 계정 PC).
    today = date.today()
    day, _ = a5.slot_for(_defaults(), today.year, today.month)
    made = runner.run_once(db, automation.STARTUP_MONTHLY,
                           datetime(day.year, day.month, day.day, 9, 0).astimezone())
    assert made["status"] == "ready", made

    admin = _admin_client(client, db, users)
    answer = admin.post("/team/startup-send",
                        data={"enabled": "on", "user_id": users["u2"].id},
                        follow_redirects=False)
    assert answer.status_code == 303
    db.expire_all()
    assert automation.load(db, automation.STARTUP_MONTHLY).user_id == users["u2"].id
    [job] = db.query(SendJob).all()
    assert job.status == "canceled"          # 옛 계정 PC 로 서 있던 회차는 거둔다
    assert "거뒀습니다" in unquote(answer.headers["location"])


def test_the_team_panel_shows_the_fixed_sender(db, users, client):
    _turn_on(db, user_id=2)
    page = _admin_client(client, db, users).get("/team").text
    row = page.split('data-automation="startup_monthly"', 1)[1].split("</tr>", 1)[0]
    assert 'data-testid="automation-fixed-sender"' in row
    assert users["u2"].name in row
    assert '<select name="user_id">' not in row


# ── 메뉴·보내는 계정 판 ─────────────────────────────────────────────────────

def test_the_menu_panel_has_no_monthly_switch(db, users, client):
    page = _admin_client(client, db, users).get("/team").text
    assert "메뉴·보내는 계정" in page
    assert 'name="monthly"' not in page
    assert 'name="monthly_time"' not in page
    assert 'action="/team/startup-send"' in page


def test_saving_the_menu_ignores_old_monthly_fields(db, users, client):
    from app.services import startup_send

    admin = _admin_client(client, db, users)
    admin.post("/team/startup-send", data={
        "enabled": "on", "user_id": 1, "monthly": "on", "monthly_time": "16:30"},
        follow_redirects=False)
    db.expire_all()
    row = startup_send.setting(db)
    assert startup_send.is_on(row) and row.user_id == 1
    assert row.monthly_auto == 0 and row.monthly_time == "17:00"


# ── 4. /deals/startup-ir 머리 ───────────────────────────────────────────────

def test_header_says_a5_is_off(db, seeded, client):
    _turn_on(db, user_id=1)
    page = _login(client).get("/deals/startup-ir").text
    head = page.split('data-testid="startup-a5-off"', 1)[1].split("</p>", 1)[0]
    assert "A5 꺼짐" in head


def test_header_shows_a5_next_date(db, seeded, client):
    from app import clock
    from app.services import automation, automation_runner as runner, scheduled_send

    _turn_on(db, user_id=1)
    _a5(db, test=True)
    plan = runner.next_plan(db, automation.load(db, automation.STARTUP_MONTHLY),
                            clock.now())
    page = _login(client).get("/deals/startup-ir").text
    head = page.split('data-testid="startup-a5-next"', 1)[1].split("</p>", 1)[0]
    assert scheduled_send.label(plan.at) in head
    assert "시험 모드" in head


def test_header_skips_a_month_that_is_already_sent(db, seeded):
    """이 달 회차가 이미 있으면(사람이 먼저 세운 것도) 그 달은 건너뛰고 다음 달 날짜."""
    from app.models import SendJob
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=False)
    now = datetime(2026, 10, 17, 9, 0).astimezone()
    db.add(SendJob(user_id=1, kind="startup_ir", status="done", total=1,
                   created_at="2026-10-02T10:00:00+09:00"))
    db.commit()
    head = a5.header(db, now)
    assert head["on"] and head["skip"]["month"] == "2026-10"
    assert head["next_label"].startswith("11/30")


def test_an_empty_a5_day_shows_in_today(db, users):
    """옛 '자동 발송을 세우지 못했습니다' 대신 A5 의 오늘 할 일 줄이 선다."""
    from app.services import automation, automation_runner as runner, today
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=False)
    now = date.today()
    day, _ = a5.slot_for(_defaults(), now.year, now.month)
    when = datetime(day.year, day.month, day.day, 9, 0).astimezone()
    assert runner.run_once(db, automation.STARTUP_MONTHLY, when)["status"] == "empty"
    items = today.build(db, users["u1"], day)
    titles = [i["title"] for i in items["items"]]
    assert any("스타트업 월간 발송" in t and "안 나갑니다" in t for t in titles), titles
    assert not any("세우지 못했습니다" in t for t in titles)
