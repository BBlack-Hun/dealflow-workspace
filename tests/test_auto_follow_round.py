"""#94 · #98 후속라운드 시작 알림 — 한 달 전 1일 · 전달 15일 · 당월 1일, 카톡 · 문자.

1. 세 날짜 — 주말이면 다음 평일.
2. 받는 팀원(기본: 그 줄 담당 + 자동 발송 계정 주인)의 카톡방으로 한 번씩, 같은 날 또 돌아도 그대로.
3. 실제 모드 문자는 서버가 받는 사람마다 한 번씩 — 날이 달라도 다시 안 보낸다.
4. Series A 이상 딜 소싱 줄은 `담당자` 칸의 지금 담당자에게.
5. 못 정한 받는 팀원 · 빈 카톡방 · 문자 설정 없음은 건너뛰고 까닭이 선다.
6. 시험 모드에서는 문자도 시험방 카톡으로. 풀기 직전에 값이 바뀌었으면 뺀다.
7. 매출예상리스트 칸(0128) — `YYYY-MM` 으로 맞춰 받고, 관리자 추가 칸 값을 옮긴다.

값(기업명 · 방 이름)은 지어낸 것이다.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest
from sqlalchemy import select

from .test_migrations import _alembic

TEST_ROOM = "자동화 시험방"
U1_ROOM, U2_ROOM = "후속 알림 테스트방", "나와의 채팅 테스트"
MONTH = "2027-05"                  # 알림 4/1(목) · 4/15(목) · 5/3(월 — 5/1 이 토요일)


def _at(y, m, d, hh=9, mm=0):
    return datetime(y, m, d, hh, mm).astimezone()


@pytest.fixture()
def row(db, users):
    from app.models import RevenueForecast

    users["u1"].kakao_room_name = U1_ROOM
    users["u2"].kakao_room_name = U2_ROOM
    found = RevenueForecast(user_id=users["u1"].id, company_name="샘플후속",
                            follow_round_month=MONTH)
    db.add(found)
    db.commit()
    return found


@pytest.fixture()
def texts(monkeypatch):
    """문자 업체 대신 — 보낸 (번호, 글)을 모은다."""
    from app.services import sms

    sent = []
    monkeypatch.setattr(sms, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "load_settings", lambda: None)
    monkeypatch.setattr(sms, "send", lambda to, text, settings=None: sent.append((to, text)) or "m1")
    return sent


def _turn_on(db, users, test=False, **params):
    from app.services import automation, automation_runner as runner

    row_ = automation.save(db, automation.FOLLOW_ROUND, enabled=True,
                           user_id=users["u2"].id, test_mode=test, test_room=TEST_ROOM)
    if params:
        automation.set_params(row_, runner.clean_params(automation.FOLLOW_ROUND, params))
        db.commit()
    return row_


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.FOLLOW_ROUND, now)


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


def test_세_날짜는_한_달_전_1일_전달_15일_당월_1일_주말이면_다음_평일():
    from app.services.automations import follow_round as fr

    assert fr.alert_days(MONTH) == [date(2027, 4, 1), date(2027, 4, 15), date(2027, 5, 3)]
    assert fr.alert_days("2027-01") == [date(2026, 12, 1), date(2026, 12, 15), date(2027, 1, 1)]


def test_담당과_계정_주인_카톡방으로_한_번씩(db, users, row):
    from app.services.automations import follow_round as fr

    _turn_on(db, users)
    assert _run(db, _at(2027, 3, 31))["status"] == "empty"            # 아직
    assert _run(db, _at(2027, 4, 1))["status"] == "ready"
    assert _run(db, _at(2027, 4, 1, 9, 30))["status"] == "done"       # 같은 날 또 — 그대로
    items = _items(db)
    assert sorted(i.room_name for i in items) == sorted([U1_ROOM, U2_ROOM])
    assert {i.message for i in items} == {"샘플후속 5월 라운드 시작입니다 (1/3)"}
    job = items[0].job
    assert job.user_id == users["u2"].id and job.topic == fr.TOPIC
    assert all(i.contact_id is None for i in items)


def test_문자는_받는_사람마다_회차마다_한_번(db, users, row, texts):
    from app.models import SmsNotice
    from app.services.automations import follow_round as fr

    _turn_on(db, users)
    assert fr.send_sms(db, _at(2027, 4, 1, 9, 30))["status"] == "not_now"    # 판의 시각 전
    assert fr.send_sms(db, _at(2027, 4, 1, 10, 30))["sent"] == 2
    assert fr.send_sms(db, _at(2027, 4, 2, 10, 30))["sent"] == 0             # 다음 날도
    assert fr.send_sms(db, _at(2027, 4, 15, 10, 30))["sent"] == 2
    assert sorted(texts) == [
        ("01000000001", "샘플후속 5월 라운드 시작입니다 (1/3)"),
        ("01000000001", "샘플후속 5월 라운드 시작입니다 (2/3)"),
        ("01000000002", "샘플후속 5월 라운드 시작입니다 (1/3)"),
        ("01000000002", "샘플후속 5월 라운드 시작입니다 (2/3)")]
    kinds = db.execute(select(SmsNotice.kind, SmsNotice.user_id)).all()
    assert (f"follow_round:fc:{row.id}:{MONTH}:1", users["u1"].id) in kinds


def test_Series_A_줄은_담당자_칸의_지금_담당자에게(db, users):
    from app.models import SeriesACompany

    users["u1"].kakao_room_name = U1_ROOM
    db.add(SeriesACompany(name="샘플시리즈", assignee_name="윤서아 > 10/1 강민준",
                          follow_round_month=MONTH))
    db.commit()
    _turn_on(db, users, recipients="담당 팀원")
    assert _run(db, _at(2027, 5, 3))["status"] == "ready"
    items = _items(db)
    assert [(i.room_name, i.message) for i in items] == [
        (U1_ROOM, "샘플시리즈 5월 라운드 시작입니다 (3/3)")]


def test_못_정한_받는_팀원과_빈_카톡방은_건너뛰고_까닭이_선다(db, users, row, monkeypatch):
    from app import clock
    from app.services import automation_runner as runner

    users["u1"].kakao_room_name = None
    db.commit()
    _turn_on(db, users, recipients="없는사람\n강민준")
    result = _run(db, _at(2027, 4, 1))
    assert result["status"] == "empty" and _items(db) == []
    joined = " / ".join(result["skipped"])
    assert "받는 팀원 '없는사람' 을 계정에서 못 찾았습니다" in joined
    assert "강민준 님의 카톡방 이름이 비어 있어 카톡은 건너뜁니다" in joined
    monkeypatch.setattr(clock, "now", lambda: _at(2027, 4, 1, 9, 5))
    state = runner.status_of(db, "follow_round")
    assert "문자 설정" in state["describe"] and "없는사람" in state["describe"]


def test_시험_모드에서는_문자도_시험방_카톡으로(db, users, row, texts):
    from app.services.automations import follow_round as fr

    _turn_on(db, users, test=True, recipients="담당 팀원")
    assert _run(db, _at(2027, 4, 1))["status"] == "ready"
    items = _items(db)
    assert {i.room_name for i in items} == {TEST_ROOM}
    assert any(i.message.startswith("[시험] 원래 받을 방: 문자 → 강민준") for i in items)
    assert fr.send_sms(db, _at(2027, 4, 1, 10, 30))["status"] == "off" and texts == []


def test_풀기_직전에_값이_바뀌었으면_뺀다(db, users, row):
    from app.services import automation_runner as runner

    _turn_on(db, users, recipients="담당 팀원")
    _run(db, _at(2027, 4, 1))
    row.follow_round_month = "2027-06"
    db.commit()
    job = _items(db)[0].job
    assert runner.prune(db, job, _at(2027, 4, 1, 10, 0)) == 0
    assert "후속라운드 시작이 바뀌었습니다" in _items(db)[0].error


# ── 매출예상리스트 칸(0128) ────────────────────────────────────────────────────

def test_매출예상리스트_칸은_YYYY_MM_으로_맞춘다():
    from app.services import forecast

    assert forecast.clean("follow_round_month", "2027.5") == "2027-05"
    with pytest.raises(forecast.InputError, match="후속라운드 시작은 YYYY-MM"):
        forecast.clean("follow_round_month", "내년 봄")
    assert "follow_round_month" in forecast.FIELDS


NOW = "'2026-10-30T00:00:00', '2026-10-30T00:00:00'"


def test_0128_은_추가_칸_값을_옮기고_숨긴다(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", "0127_series_a_follow_round").returncode == 0
    con = sqlite3.connect(db)
    try:
        # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
        con.execute("ALTER TABLE revenue_forecasts DROP COLUMN follow_round_month")
        con.execute("INSERT INTO revenue_forecasts (id, user_id, company_name, created_at, "
                    f"updated_at) VALUES (1, 1, '샘플옮김', {NOW})")   # 외래키는 꺼져 있다
        con.execute("INSERT INTO custom_columns (id, target, name, kind, position, is_hidden, "
                    f"created_at, updated_at) VALUES (2, 'forecast', '후속라운드 시작 년월', "
                    f"'memo', 2, 0, {NOW})")
        con.execute("INSERT INTO custom_column_values (column_id, row_table, row_id, value, "
                    f"created_at, updated_at) VALUES (2, 'revenue_forecasts', 1, '2027.5', {NOW})")
        con.commit()
    finally:
        con.close()

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT follow_round_month FROM revenue_forecasts").fetchone() == ("2027-05",)
        assert con.execute("SELECT is_hidden FROM custom_columns WHERE id = 2").fetchone() == (1,)
    finally:
        con.close()

    down = _alembic(db, "downgrade", "0127_series_a_follow_round")
    assert down.returncode == 0, down.stdout + down.stderr
    con = sqlite3.connect(db)
    try:
        cols = {r[1] for r in con.execute('PRAGMA table_info("revenue_forecasts")')}
        assert "follow_round_month" not in cols
        assert con.execute("SELECT is_hidden FROM custom_columns WHERE id = 2").fetchone() == (0,)
    finally:
        con.close()
