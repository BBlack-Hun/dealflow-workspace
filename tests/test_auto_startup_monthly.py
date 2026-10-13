"""A5 스타트업 월간 발송 순환 — **날짜·시각과 문구를 달마다 돌린다, 한 달에 한 번.**

1. 기본 순환 15일 11:00 → 20일 13:00 → 16일 14:00 — 달의 번호로 고른다.
2. 문구도 최대 셋 중에서 달마다(1번 = 지금 문구, 2·3번 = 초안). 자료는 같다.
3. 그날 아침 스타트업 화면과 같은 글로 회차가 서고 그 시각 예약이 걸린다.
   회차명에 그 달이 적혀 '이 달 회차' 판정이 알아본다.
4. 이 달 회차가 이미 있으면 세우지 않는다.
5. 실제 모드로 켜지면 옛 30일 자동은 물러난다(시험 모드면 그대로).
6. 보내는 계정이 스타트업 월간 발송 계정이 아니면 세우지 않는다.

기업 자료는 **실제 이번 달**로 심는다(`test_startup_monthly_send.seeded`) — 그래서
이번 달 순환 날짜를 계산해 그날로 돌린다.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from tests.test_startup_monthly_send import (  # noqa: F401 - 픽스처를 함께 쓴다
    _jobs, _turn_on, seeded)

TEST_ROOM = "자동화 시험방"


def _aware(when):
    return when.astimezone()


def _values():
    from app.services.automations import startup_monthly as a5

    return {"slots": a5.DEFAULT_SLOTS, "variants": 3}


def _this_month_slot():
    from app.services.automations import startup_monthly as a5

    today = date.today()
    return a5.slot_for(_values(), today.year, today.month)


def _on(db, *, test=False, user_id=None):
    from app.services import automation

    return automation.save(db, automation.STARTUP_MONTHLY, enabled=True,
                           user_id=user_id, test_mode=test, test_room=TEST_ROOM)


def _run(db, hour=9):
    from app.services import automation, automation_runner as runner

    day, _ = _this_month_slot()
    return runner.run_once(db, automation.STARTUP_MONTHLY,
                           _aware(datetime(day.year, day.month, day.day, hour, 0)))


def test_rotation_of_days_times_and_wording():
    from app.services.automations import startup_monthly as a5

    values = _values()
    assert a5.slot_for(values, 2026, 10) == (date(2026, 10, 15), "11:00")
    assert a5.slot_for(values, 2026, 11) == (date(2026, 11, 20), "13:00")
    assert a5.slot_for(values, 2026, 12) == (date(2026, 12, 16), "14:00")
    assert a5.slot_for(values, 2027, 1) == (date(2027, 1, 15), "11:00")
    assert [a5.variant_for(values, date(2026, m, 1)) for m in (10, 11, 12)] == [1, 2, 3]
    assert a5.variant_for({"slots": a5.DEFAULT_SLOTS, "variants": 1},
                          date(2026, 11, 1)) == 1
    # 그 달에 없는 날이면 말일.
    assert a5.slot_for({"slots": ["31 10:00"], "variants": 1}, 2027, 2) == (
        date(2027, 2, 28), "10:00")


def test_bad_slot_lines_are_refused(db, users):
    from app.services import automation, automation_runner as runner

    for bad in ("15일 11:00", "15 20:00", "40 11:00"):
        with pytest.raises(ValueError):
            runner.save_params(db, automation.STARTUP_MONTHLY, {"slots": bad})
        db.rollback()


def test_it_sets_up_on_the_slot_day_with_the_month_in_the_title(db, seeded):
    from app.services import scheduled_send, startup_monthly

    _turn_on(db)            # 스타트업 월간 발송 계정 = 1번 = 기본 보내는 계정
    _on(db)
    result = _run(db)
    assert result["status"] == "ready", result
    [job] = _jobs(db)
    day, hhmm = _this_month_slot()
    assert job.kind == "startup_ir" and job.status == "draft" and job.user_id == 1
    assert scheduled_send.scheduled_at(job).strftime("%H:%M") == hhmm
    assert [i.ir_company_id for i in job.items] == [seeded["ok"].id]
    # '이 달 회차' 판정이 알아본다 — 30일 자동도 사람도 두 번 못 세운다.
    assert startup_monthly.month_job(db, seeded["month"]).id == job.id


def test_wording_follows_the_month(db, seeded):
    from app.models import User
    from app.services import ir_kakao
    from app.services.automations import startup_monthly as a5

    _turn_on(db)
    _on(db)
    _run(db)
    [job] = _jobs(db)
    day, _ = _this_month_slot()
    variant = a5.variant_for(_values(), day)
    want = ir_kakao.for_company(db, db.get(User, 1), seeded["ok"].id,
                                seeded["month"], variant=variant)
    assert job.items[0].message == want.text
    one = ir_kakao.for_company(db, db.get(User, 1), seeded["ok"].id, seeded["month"], 1)
    two = ir_kakao.for_company(db, db.get(User, 1), seeded["ok"].id, seeded["month"], 2)
    # 자료(목록)는 같고 인사·맺음만 다르다.
    assert one.lines == two.lines and one.summary == two.summary
    assert one.text != two.text


def test_an_existing_month_job_blocks_it(db, seeded):
    from app.models import SendJob

    _turn_on(db)
    db.add(SendJob(user_id=1, kind="startup_ir", status="done", total=1,
                   created_at=f"{seeded['month']}-02T10:00:00+09:00"))
    db.commit()
    _on(db)
    result = _run(db)
    assert result["status"] == "empty"


def test_the_old_thirtieth_steps_aside_only_in_real_mode(db, seeded):
    from app.services import startup_monthly, startup_send

    startup_send.save(db, enabled=True, user_id=1, monthly=True,
                      monthly_time="17:00")
    _on(db, test=True)
    assert startup_monthly.handed_over(db) is False
    _on(db, test=False)
    assert startup_monthly.handed_over(db) is True
    when = startup_monthly.run_day(2026, 10)
    assert startup_monthly.run_once(
        db, _aware(datetime(when.year, when.month, when.day, 9, 0)))["status"] == "handed_over"
    assert startup_monthly.status(db)["handed_over"] is True


def test_sender_must_be_the_startup_sender(db, seeded, users):
    _turn_on(db, user_id=1)
    _on(db, user_id=users["u2"].id)
    result = _run(db)
    assert result["status"] == "empty"
    assert _jobs(db) == []


def test_test_mode_goes_to_the_test_room(db, seeded):
    _turn_on(db)
    _on(db, test=True)
    _run(db)
    [job] = _jobs(db)
    assert job.kind == "test_send"
    assert job.items[0].room_name == TEST_ROOM
    assert job.items[0].message.startswith("[시험] 원래 받을 방: ")
    assert job.items[0].ir_company_id is None


def test_panel_line_shows_the_rotation(db, users):
    from app.services import automation_runner as runner

    state = runner.status_of(db, "startup_monthly")
    assert state["describe"].startswith("순환: ")
    assert "·문구" in state["describe"]
