"""#31 자동화 전환 판(0105) — 옛 두 엔진의 설정을 **꺼진 2단계 자동화 줄**로 옮긴다.

`tests/test_migrations.py` 는 빈 DB 로 오르내린다 — 그 길에서는 설정 줄이 없어
옮기는 길이 밟히지 않는다. 운영과 같은 모양(옛 설정 두 줄 + 팀 공통 줄)을 세워
그 길을 밟는다.

사용자 결정(2026-10-17):

- 스타트업 월간 — 옛 `startup_ir` 설정으로 A5 줄을 세운다: **꺼짐 · 시험 모드 ·
  월말 순환 · 보내는 계정 = 옛 설정의 계정.** 옛 30일 자동(`monthly_auto`)은 0.
- 미팅 후기 — 팀 공통(`_team`)의 자동 발송 계정이 비어 있으면 옛 `meeting_review`
  설정의 계정을 넣는다. 차 있으면 그대로.
- 지우는 자료는 없다(설정 줄 · 이력 그대로).
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from .test_migrations import _alembic

BEFORE = "0104_sourcing_vc_link_confirmed"
NOW = "2026-10-17T09:00:00+09:00"
SLOTS = ["26 11:00", "30 13:00", "28 14:00"]


def _exec(db, sql, *args):
    con = sqlite3.connect(db)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def _setting(db, kind, user_id, monthly_auto=0):
    _exec(db, "INSERT INTO auto_send_settings (kind, enabled, user_id, from_hour, "
              "until_hour, max_per_day, monthly_auto, monthly_time, created_at, "
              "updated_at) VALUES (?, 1, ?, 10, 17, 10, ?, '17:00', ?, ?)",
          kind, user_id, monthly_auto, NOW, NOW)


def _automation(db, key, user_id=None, params=None, enabled=0):
    _exec(db, "INSERT INTO automations (key, enabled, user_id, test_mode, params, "
              "created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?, ?)",
          key, enabled, user_id, params, NOW, NOW)


def _rows(db) -> dict:
    con = sqlite3.connect(db)
    try:
        autos = {k: (en, uid, tm, json.loads(p) if p else None)
                 for k, en, uid, tm, p in con.execute(
                     "SELECT key, enabled, user_id, test_mode, params FROM automations")}
        settings = {k: (en, uid, ma, mt) for k, en, uid, ma, mt in con.execute(
            "SELECT kind, enabled, user_id, monthly_auto, monthly_time "
            "FROM auto_send_settings")}
    finally:
        con.close()
    return {"automations": autos, "settings": settings}


@pytest.fixture()
def old_db(tmp_path):
    db = tmp_path / "old.db"
    done = _alembic(db, "upgrade", BEFORE)
    assert done.returncode == 0, done.stdout + done.stderr
    return db


def _up(db):
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr


def test_production_shape_moves_into_switched_off_rows(old_db):
    """운영의 모양 — 옛 두 설정이 같은 계정(8), 팀 공통 줄은 계정 없이 있다."""
    _setting(old_db, "startup_ir", 8, monthly_auto=1)
    _setting(old_db, "meeting_review", 8)
    _automation(old_db, "_team")
    _up(old_db)

    got = _rows(old_db)
    enabled, uid, test_mode, params = got["automations"]["startup_monthly"]
    assert (enabled, uid, test_mode) == (0, 8, 1)          # 꺼짐 · 시험 모드 · 그 계정
    assert params["slots"] == SLOTS and params["variants"] == 3
    assert got["automations"]["_team"][1] == 8               # 비어 있던 팀 계정
    # 옛 30일 자동은 내리고, 메뉴 켜짐 · 계정은 그대로다. 지운 줄은 없다.
    assert got["settings"]["startup_ir"] == (1, 8, 0, "17:00")
    assert got["settings"]["meeting_review"][:2] == (1, 8)


def test_a_team_sender_already_chosen_is_kept(old_db):
    _setting(old_db, "meeting_review", 8)
    _automation(old_db, "_team", user_id=5)
    _up(old_db)
    got = _rows(old_db)
    assert got["automations"]["_team"][1] == 5
    # 스타트업 설정이 없으면 A5 줄을 지어내지 않는다(줄 없음 = 꺼짐 · 기본값).
    assert "startup_monthly" not in got["automations"]


def test_no_team_row_gets_one_when_meeting_review_had_a_sender(old_db):
    _setting(old_db, "meeting_review", 8)
    _up(old_db)
    enabled, uid, test_mode, _params = _rows(old_db)["automations"]["_team"]
    assert (enabled, uid, test_mode) == (0, 8, 1)


def test_an_existing_a5_row_is_aligned_not_switched(old_db):
    """이미 있는 A5 줄 — 옛 기본 순환(15/20/16)만 월말로 바꾸고, 고친 순환은 그대로.
    보내는 계정은 메뉴의 계정으로 맞춘다. 켜짐 · 시험 모드는 건드리지 않는다."""
    _setting(old_db, "startup_ir", 8)
    _automation(old_db, "startup_monthly", user_id=5, enabled=1, params=json.dumps(
        {"slots": ["15 11:00", "20 13:00", "16 14:00"], "variants": 2,
         "item_gap_min": 30, "item_gap_max": 90}))
    _up(old_db)
    enabled, uid, _tm, params = _rows(old_db)["automations"]["startup_monthly"]
    assert (enabled, uid) == (1, 8)
    assert params == {"slots": SLOTS, "variants": 2,
                      "item_gap_min": 30, "item_gap_max": 90}


def test_custom_slots_are_kept(old_db):
    _setting(old_db, "startup_ir", 8)
    _automation(old_db, "startup_monthly", user_id=8,
                params=json.dumps({"slots": ["27 10:00"], "variants": 1}))
    _up(old_db)
    assert _rows(old_db)["automations"]["startup_monthly"][3]["slots"] == ["27 10:00"]


def test_running_it_again_changes_nothing(old_db):
    _setting(old_db, "startup_ir", 8, monthly_auto=1)
    _setting(old_db, "meeting_review", 8)
    _up(old_db)
    before = _rows(old_db)
    _up(old_db)
    assert _rows(old_db) == before


def test_it_comes_down_and_goes_back_up(old_db):
    _setting(old_db, "startup_ir", 8, monthly_auto=1)
    _up(old_db)
    down = _alembic(old_db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
    # 내려도 지우지 않는다 — A5 줄은 꺼진 채 남고 옛 자동은 0 그대로(덜 보내는 쪽).
    got = _rows(old_db)
    assert got["automations"]["startup_monthly"][0] == 0
    assert got["settings"]["startup_ir"][2] == 0
    _up(old_db)


def test_the_app_reads_the_moved_row(db, users):
    """이주가 적은 모양을 앱이 그대로 읽는다 — 순환 · 계정."""
    from app.models import Automation
    from app.services import automation, automation_runner as runner

    db.add(Automation(key="startup_monthly", enabled=0, test_mode=1, user_id=1,
                      params=json.dumps({"slots": SLOTS, "variants": 3})))
    db.commit()
    row = automation.load(db, automation.STARTUP_MONTHLY)
    assert runner.values(row, automation.STARTUP_MONTHLY)["slots"] == SLOTS
    assert automation.sender_id(db, row) == 1
