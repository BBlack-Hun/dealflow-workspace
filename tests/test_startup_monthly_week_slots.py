"""#73 스타트업 월간 발송(A5) — **홀수 달 3주차 목요일 · 짝수 달 4주차 수요일 11:00**.

사용자 결정(2026-10-28, "추천대로"):

1. 순환 줄이 `3주 목 11:00`(주차 요일 시각) 모양을 받는다 — 1~7일이 1주차라 곧
   N번째 그 요일. 두 줄이면 홀수 달 = 첫 줄, 짝수 달 = 둘째 줄. 기본값이 이 두 줄이다.
2. 달 중간에 나가므로 글의 `{달} 말 기준` 은 `{날짜} 기준`(보내는 날)이다 — 운영에
   저장된 문구의 그 구절은 0126 이주가 바꾼다.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from .test_migrations import _alembic


def _values(*slots):
    from app.services.automations import startup_monthly as a5

    return {"slots": list(slots) or a5.DEFAULT_SLOTS, "variants": 3}


def test_default_is_odd_third_thursday_even_fourth_wednesday():
    from app.services.automations import startup_monthly as a5

    values = _values()
    assert a5.DEFAULT_SLOTS == ["3주 목 11:00", "4주 수 11:00"]
    assert a5.slot_for(values, 2026, 11) == (date(2026, 11, 19), "11:00")   # 목
    assert a5.slot_for(values, 2026, 12) == (date(2026, 12, 23), "11:00")   # 수
    assert a5.slot_for(values, 2027, 1) == (date(2027, 1, 21), "11:00")     # 목
    assert a5.slot_for(values, 2027, 2) == (date(2027, 2, 24), "11:00")     # 수
    for month in range(1, 13):
        day, _ = a5.slot_for(values, 2027, month)
        assert day.weekday() == (3 if month % 2 else 2) and 15 <= day.day <= 28


def test_week_slot_spellings_and_refusals():
    from app.services.automations import startup_monthly as a5

    assert a5.parse_slots(["3주차 목요일 11:00", "4주 수 10:30", "26 11:00"]) == [
        ((3, 3), "11:00"), ((4, 2), "10:30"), (26, "11:00")]
    for bad in ("6주 목 11:00", "3주 X 11:00", "3주 목 20:00", "3주 11:00"):
        with pytest.raises(ValueError):
            a5.parse_slots([bad])


def test_a_missing_fifth_week_falls_back_to_the_last_one():
    from app.services.automations import startup_monthly as a5

    # 2027-02 수요일은 3·10·17·24 — 다섯째가 없으면 마지막 수요일.
    assert a5.slot_for(_values("5주 수 11:00"), 2027, 2) == (date(2027, 2, 24), "11:00")


def test_the_panel_saves_the_new_shape(db, users):
    from app.services import automation, automation_runner as runner

    runner.save_params(db, automation.STARTUP_MONTHLY,
                       {"slots": "3주 목 11:00\n4주 수 11:00", "variants": "3"})
    row = automation.load(db, automation.STARTUP_MONTHLY)
    assert runner.values(row, automation.STARTUP_MONTHLY)["slots"] == [
        "3주 목 11:00", "4주 수 11:00"]


def test_the_wording_says_the_send_day(monkeypatch):
    from app import clock
    from app.services import ir_kakao

    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 19, 9, 0).astimezone())
    assert ir_kakao.send_day_label("2026-11") == "11월 19일"
    assert ir_kakao.send_day_label("2026-10") == "10월 31일"     # 지난 달 글은 그 달 말일
    head = ir_kakao.header("2026-11", ["샘플에너지"])
    assert "샘플에너지의 11월 19일 기준 IR 진행 현황" in head
    assert "말 기준" not in head
    for n in (2, 3):
        assert ir_kakao.DAY_TOKEN in ir_kakao.VARIANT_HEADS[n]


# ── 0126 이주 — 운영에 저장된 `{달} 말 기준` 을 `{날짜} 기준` 으로 ──────────────

BEFORE = "0125_series_a_contract"
NOW = "2026-10-28T09:00:00+09:00"


def _template(db, kind, body):
    con = sqlite3.connect(db)
    try:
        con.execute("INSERT INTO message_templates (user_id, kind, name, body, is_active, "
                    "created_at, updated_at) VALUES (NULL, ?, NULL, ?, 1, ?, ?)",
                    (kind, body, NOW, NOW))
        con.commit()
    finally:
        con.close()


def _bodies(db) -> dict:
    con = sqlite3.connect(db)
    try:
        return dict(con.execute("SELECT kind, body FROM message_templates"))
    finally:
        con.close()


def test_the_migration_swaps_only_that_phrase(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", BEFORE).returncode == 0
    _template(db, "startup_sms", "안녕하세요.\n\n{기업들}의 {달} 말 기준 IR 진행 현황입니다.")
    _template(db, "startup_sms_v3", "{기업들}의 {달} 말 기준 현황입니다.")
    _template(db, "startup_sms_tail", "{달} 말 기준 그대로")             # 맺음말은 안 건드린다
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    bodies = _bodies(db)
    assert bodies["startup_sms"] == "안녕하세요.\n\n{기업들}의 {날짜} 기준 IR 진행 현황입니다."
    assert bodies["startup_sms_v3"] == "{기업들}의 {날짜} 기준 현황입니다."
    assert bodies["startup_sms_tail"] == "{달} 말 기준 그대로"
    down = _alembic(db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
    assert _bodies(db)["startup_sms"].endswith("{달} 말 기준 IR 진행 현황입니다.")
