"""#31 스타트업 월간 발송은 **A5 하나**다 — 옛 30일 자동을 걷었다.

사용자 결정(2026-10-17, "추천대로"):

1. 옛 30일 자동(`services/startup_monthly` 의 실 · `monthly_auto`)은 걷는다. 표와
   이력(`auto_send_settings` · `auto_send_runs`)은 남긴다.
2. 매월은 A5 하나 — 10/17 의 순환은 **월말** `26 11:00 / 30 13:00 / 28 14:00`(30일이
   없으면 말일 — #73 부터 기본은 `3주 목 / 4주 수`, 월말 줄도 그대로 받는다).
   그날이 토·일이면 **앞 평일**(다음 달로 넘어가지 않는다).
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


MONTH_END = ["26 11:00", "30 13:00", "28 14:00"]


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

def test_month_end_rotation_still_works():
    from app.services.automations import startup_monthly as a5

    values = {"slots": MONTH_END, "variants": 3}
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


def test_panel_summary_says_odd_and_even_months():
    from app.services import automation

    summary = automation.BY_KEY[automation.STARTUP_MONTHLY].summary
    assert "홀수 달 3주차 목요일" in summary and "짝수 달 4주차 수요일" in summary
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


def test_changing_the_menu_sender_moves_a5_and_stops_its_jobs(db, users, client, seeded,
                                                             monkeypatch):
    from app import clock
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
    # 나갈 시각이 지난 뒤에 바꾼다 — 그 전이면 새 계정으로 다시 선다(아래 리뷰 5).
    monkeypatch.setattr(clock, "now", lambda: datetime(
        day.year, day.month, day.day, 18, 0).astimezone())

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


def test_turning_the_menu_off_turns_a5_off_too(db, users, client):
    """메뉴를 끄면 A5 는 보낼 계정이 없다 — 켜짐으로 남아 '다음: 날짜' 를 약속하지
    않게 A5 도 끈다(서 있던 회차는 거둔다)."""
    from app.services import automation
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=True)
    admin = _admin_client(client, db, users)
    answer = admin.post("/team/startup-send", data={"enabled": "", "user_id": 1},
                        follow_redirects=False)
    db.expire_all()
    assert automation.load(db, automation.STARTUP_MONTHLY).enabled == 0
    assert "A5" in unquote(answer.headers["location"])
    assert a5.header(db)["on"] is False


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
    assert head["next_label"].startswith("11/19")      # 홀수 달 3주차 목요일


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


# ── 화면 점검에서 나온 것(테스트 서버 10/17) ────────────────────────────────

def _css() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / "app/static/css/app.css").read_text()


def test_the_rotation_preview_is_not_cut_off(db, users, client):
    """A5 순환 미리보기('순환: 10/28 … → 11/19 … → 12/23 …')가 좁은 칸에서 `…` 로
    잘렸다 — 자동화 표의 칸 아래 줄은 접히고, 다 적은 글은 풍선말로도 단다."""
    from app.services import automation_runner as runner

    page = _admin_client(client, db, users).get("/team").text
    describe = runner.status_of(db, "startup_monthly")["describe"]
    row = page.split('data-automation="startup_monthly"', 1)[1].split("</tr>", 1)[0]
    assert f'title="{describe}"' in row
    assert 'class="grid-table compact automation-table"' in page
    rule = _css().split(".automation-table td .cell-sub", 1)[1].split("}", 1)[0]
    assert "white-space: normal" in rule


def test_the_send_guard_card_does_not_stretch_beside_the_automation_panel(db, users, client):
    page = _admin_client(client, db, users).get("/team").text
    head = page.split('data-testid="send-guard-panel"', 1)[0].rsplit("<section", 1)[1]
    assert "align-top" in head
    rule = _css().split(".dash-grid .panel.align-top", 1)[1].split("}", 1)[0]
    assert "align-self: start" in rule


def test_a5_cannot_be_switched_on_in_the_form_while_the_menu_is_off(db, users, client):
    page = _admin_client(client, db, users).get("/team").text
    row = page.split('data-automation="startup_monthly"', 1)[1].split("</tr>", 1)[0]
    switch = row.split('<select name="enabled"', 1)[1].split(">", 1)[0]
    assert "disabled" in switch
    assert "메뉴가 꺼져 있어 켤 수 없습니다" in row
    # 메뉴를 켜면 고를 수 있다.
    _turn_on(db, user_id=1)
    page = client.get("/team").text
    row = page.split('data-automation="startup_monthly"', 1)[1].split("</tr>", 1)[0]
    assert "disabled" not in row.split('<select name="enabled"', 1)[1].split(">", 1)[0]


def test_the_team_sender_default_names_the_menu_account(db, users, client):
    _turn_on(db, user_id=2)
    page = _admin_client(client, db, users).get("/team").text
    form = page.split('data-testid="automation-team-form"', 1)[1].split("</select>", 1)[0]
    assert f"스타트업 월간 발송 메뉴의 계정 따름 ({users['u2'].name})" in form


# ── PR #315 리뷰 ─────────────────────────────────────────────────────────────
#
# 날짜를 박는다 — 2026-10 의 A5 날짜는 기본 순환으로 10/28(수, 짝수 달 4주차) 11:00,
# 11월은 11/19(목, 홀수 달 3주차). 검사 날은 10/28·10/29 를 피한다 — 그날 돌면
# `today._at` 이 진짜 시계를 쓴다.


def _at(*args):
    return datetime(*args).astimezone()


def _lines(db, user, day, needle):
    from app.services import today

    return [i for i in today.build(db, user, day)["items"] if needle in i["title"]]


def _startup_job(db, *, created="2026-10-02T10:00:00+09:00", status="done",
                 item_status="sent"):
    """사람이 세운 스타트업 회차 하나(이 달치) — 나간 곳이 한 곳 있다."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=1, kind="startup_ir", status=status, total=1,
                  created_at=created)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, channel="kakao", room_name="샘플에이 대표님",
                    message="월간", status=item_status))
    db.commit()
    return job


def test_header_shows_todays_own_booking_instead_of_skipping(db, seeded, client,
                                                             monkeypatch):
    """A5 가 오늘 아침 세운 **제 회차**(아직 안 나감)를 '이 달 회차가 이미 있음' 으로
    읽어 '건너뜁니다 — 다음: 다음 달' 이라 적었다 — '오늘 HH:MM 나갑니다(예약)'."""
    from app import clock
    from app.services import automation, automation_runner as runner
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=False)
    today = date.today()
    day, hhmm = a5.slot_for(_defaults(), today.year, today.month)
    made = runner.run_once(db, automation.STARTUP_MONTHLY,
                           _at(day.year, day.month, day.day, 9, 0))
    assert made["status"] == "ready", made
    later = _at(day.year, day.month, day.day, 9, 30)
    head = a5.header(db, later)
    assert head["skip"] is None
    assert head["booked"] == {"label": f"오늘 {hhmm}", "job_id": made["job_ids"][0],
                              "count": 1}
    monkeypatch.setattr(clock, "now", lambda: later)
    page = _login(client).get("/deals/startup-ir").text
    line = page.split('data-testid="startup-a5-next"', 1)[1].split("</p>", 1)[0]
    assert f"오늘 {hhmm} 나갑니다 (예약)" in line
    assert "건너뜁니다" not in line


def test_header_still_skips_a_month_someone_else_sent(db, seeded):
    """사람이 먼저 세운 회차는 그대로 '건너뜁니다'(위와 갈리는 쪽)."""
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=False)
    _startup_job(db)
    head = a5.header(db, _at(2026, 10, 17, 9, 0))
    assert head["booked"] is None and head["skip"]["month"] == "2026-10"


def test_header_survives_a_counting_failure(db, users, client, monkeypatch):
    """곳 수를 세다 실패해도 팀 현황 · 발송 화면이 500 이 되지 않는다 — 0 곳으로 적는다."""
    from app.services import startup_send
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=True)

    def boom(*_a, **_k):
        raise RuntimeError("세다 실패")

    monkeypatch.setattr(startup_send, "sendable_ids", boom)
    head = a5.header(db, _at(2026, 10, 17, 9, 0))
    assert head["next_label"] and head["next_count"] == 0
    assert _admin_client(client, db, users).get("/team").status_code == 200


def _missed_month(db):
    """10월 A5 가 실제 모드로 켜져 있고, 그날 보낼 곳이 0곳이라 못 섰다."""
    from app.services import automation, automation_runner as runner

    _turn_on(db, user_id=1)
    _a5(db, test=False)
    assert runner.run_once(db, automation.STARTUP_MONTHLY,
                           _at(2026, 10, 28, 9, 0))["status"] == "empty"


def test_a_missed_month_warns_every_day_until_the_month_ends(db, users):
    """A5 가 못 선 달 — 그날만이 아니라 **그 달이 끝나거나 나갈 때까지** 오늘 할 일에
    (관리자 · 보내는 계정). 옛 30일 자동이 한 달 내내 띄우던 경고 자리."""
    _missed_month(db)
    needle = "10월분이 아직 안 나갔습니다"
    for day in (date(2026, 10, 30), date(2026, 10, 31)):
        [line] = _lines(db, users["u1"], day, needle)
        assert line["level"] == "urgent"
        assert "10/28" in line["detail"] and "0곳" in line["detail"]
        assert "손으로" in line["detail"]
    assert _lines(db, users["u1"], date(2026, 10, 27), needle) == []   # 날짜 전
    assert _lines(db, users["u2"], date(2026, 10, 30), needle) == []   # 남의 일
    users["u2"].role = "admin"
    db.commit()
    assert len(_lines(db, users["u2"], date(2026, 10, 30), needle)) == 1


def test_the_missed_month_warning_goes_once_something_is_sent(db, users):
    _missed_month(db)
    _startup_job(db, created="2026-10-28T15:00:00+09:00")
    assert _lines(db, users["u1"], date(2026, 10, 30), "아직 안 나갔습니다") == []


def test_a_list_that_never_went_out_does_not_count_as_sent(db, users):
    """사람이 세우고 안 누른 목록 · 다 실패한 회차는 '나간 회차' 가 아니다."""
    _missed_month(db)
    _startup_job(db, created="2026-10-28T15:00:00+09:00", status="draft",
                 item_status="pending")
    assert len(_lines(db, users["u1"], date(2026, 10, 30), "아직 안 나갔습니다")) == 1


def test_the_missed_month_shows_in_the_startup_header(db, users, client, monkeypatch):
    from app import clock
    from app.services.automations import startup_monthly as a5

    _missed_month(db)
    when = _at(2026, 10, 30, 9, 0)
    assert a5.header(db, when)["missed"]["month"] == "2026-10"
    monkeypatch.setattr(clock, "now", lambda: when)
    page = _login(client).get("/deals/startup-ir").text
    line = page.split('data-testid="startup-a5-missed"', 1)[1].split("</p>", 1)[0]
    assert "10월분이 아직 안 나갔습니다" in line


# 리뷰 11 — A5 가 꺼져 있으면(또는 시험 모드면) 이 달 발송이 안 나간다고 알린다.
OFF_NEEDLE = "스타트업 월간 발송(A5)이"


def test_a5_off_reminds_ten_days_before_the_slot(db, users):
    _turn_on(db, user_id=1)                          # 메뉴 켜짐 · A5 줄 없음 = 꺼짐
    [line] = _lines(db, users["u1"], date(2026, 10, 18), OFF_NEEDLE)
    assert line["title"] == ("스타트업 월간 발송(A5)이 꺼져 있어 이번 달 발송이 안 "
                             "나갑니다 — 팀 현황 › 자동화에서 켜세요")
    assert "10/28" in line["detail"] and line["href"] == "/team#automations"
    assert _lines(db, users["u1"], date(2026, 10, 17), OFF_NEEDLE) == []   # 11일 전
    assert _lines(db, users["u2"], date(2026, 10, 18), OFF_NEEDLE) == []   # 남의 일
    users["u2"].role = "admin"
    db.commit()
    assert len(_lines(db, users["u2"], date(2026, 10, 18), OFF_NEEDLE)) == 1


def test_a5_off_reminds_after_the_slot_passed_without_a_job(db, users):
    _turn_on(db, user_id=1)
    [line] = _lines(db, users["u1"], date(2026, 10, 30), OFF_NEEDLE)
    assert line["level"] == "urgent" and "손으로" in line["detail"]


def test_no_off_reminder_when_the_month_already_has_a_job(db, users):
    """운영 모양 — 10월은 이미 회차가 있다. 11월 날짜(11/19)는 10일보다 멀다."""
    _turn_on(db, user_id=1)
    _startup_job(db)
    assert _lines(db, users["u1"], date(2026, 10, 17), OFF_NEEDLE) == []
    assert len(_lines(db, users["u1"], date(2026, 11, 20), OFF_NEEDLE)) == 1


def test_no_off_reminder_without_the_menu(db, users):
    users["u1"].role = "admin"
    db.commit()
    assert _lines(db, users["u1"], date(2026, 10, 17), OFF_NEEDLE) == []


def test_test_mode_a5_reminds_too(db, users):
    _turn_on(db, user_id=1)
    _a5(db, test=True)
    [line] = _lines(db, users["u1"], date(2026, 10, 18), OFF_NEEDLE)
    assert "시험 모드" in line["title"]


def test_a_real_a5_gets_no_off_reminder(db, users):
    _turn_on(db, user_id=1)
    _a5(db, test=False)
    assert _lines(db, users["u1"], date(2026, 10, 17), OFF_NEEDLE) == []


# 리뷰 5 — 보내는 날 메뉴 계정을 바꾸면 거둔 A5 회차를 새 계정으로 다시 세운다.

def _a5_booked_today(db):
    """이번 달 A5 날 09:00 — 1번 계정 것으로 예약이 선다(아직 안 풀림)."""
    from app.services import automation, automation_runner as runner
    from app.services.automations import startup_monthly as a5

    _turn_on(db, user_id=1)
    _a5(db, test=False)
    today = date.today()
    day, hhmm = a5.slot_for(_defaults(), today.year, today.month)
    made = runner.run_once(db, automation.STARTUP_MONTHLY,
                           _at(day.year, day.month, day.day, 9, 0))
    assert made["status"] == "ready", made
    hour, minute = (int(x) for x in hhmm.split(":"))
    return {"day": day, "at": _at(day.year, day.month, day.day, hour, minute),
            "period": day.year * 100 + day.month}


def _switch_menu(client, db, users, monkeypatch, when):
    from app import clock

    monkeypatch.setattr(clock, "now", lambda: when)
    answer = _admin_client(client, db, users).post(
        "/team/startup-send", data={"enabled": "on", "user_id": users["u2"].id},
        follow_redirects=False)
    assert answer.status_code == 303
    db.expire_all()
    return unquote(answer.headers["location"])


def test_changing_the_sender_before_the_slot_rebuilds_for_the_new_sender(
        db, users, client, seeded, monkeypatch):
    """보내는 날 아침 메뉴 계정을 바꾸면 옛 계정 PC 로 선 회차는 거두는데, 그 달 자리
    (`auto_send_runs`)가 `ready` 로 남아 다시 안 서고 그 달이 조용히 빠졌다 —
    풀리기 전 예약이었으면 자리를 풀어 새 계정으로 다시 세운다."""
    from datetime import timedelta

    from app.services import automation, automation_runner as runner

    slot = _a5_booked_today(db)
    note = _switch_menu(client, db, users, monkeypatch, slot["at"] - timedelta(minutes=90))
    old, new = _jobs(db)
    assert old.status == "canceled" and old.user_id == 1
    assert new.user_id == users["u2"].id and new.status == "draft"
    assert [i.status for i in new.items] == ["pending"]
    assert [i.status for i in old.items] == ["canceled"]
    assert "다시 세웠습니다" in note, note
    run = runner.run_row(db, automation.STARTUP_MONTHLY, False, slot["period"])
    assert run.status == "ready" and run.job_id == new.id and run.user_id == users["u2"].id
    # 옛 건은 '다시 실림' 표시 — 사람이 옛 회차를 되살려도 같은 곳에 또 가지 않는다.
    assert runner.screen(db, old, old.items) == {
        old.items[0].id: f"{runner.EXCLUDED} — {runner.RETAKEN}"}


def test_after_the_slot_time_it_says_send_by_hand(db, users, client, seeded, monkeypatch):
    from datetime import timedelta

    slot = _a5_booked_today(db)
    note = _switch_menu(client, db, users, monkeypatch, slot["at"] + timedelta(minutes=30))
    [job] = _jobs(db)
    assert job.status == "canceled"
    assert "손으로 보내세요" in note, note


def test_a_released_job_is_never_rebuilt(db, users, client, seeded, monkeypatch):
    """이미 풀려 발송기 손에 갔을 수 있는 회차는 다시 세우지 않는다(두 번 가는 길)."""
    from datetime import timedelta

    from app import clock

    slot = _a5_booked_today(db)
    [job] = _jobs(db)
    job.status, job.released_at = "queued", clock.now_iso()
    db.commit()
    note = _switch_menu(client, db, users, monkeypatch, slot["at"] - timedelta(minutes=90))
    assert [j.status for j in _jobs(db)] == ["canceled"]
    assert "손으로 보내세요" in note, note
