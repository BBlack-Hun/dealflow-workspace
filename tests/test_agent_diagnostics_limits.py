"""발송기 진단 기록 — 크기 상한 · 날마다 돌리기 · 30일 보관 (`routers/agent_api.py`).

진단과 실패 화면은 서버 디스크(DB 와 같은 볼륨)에 쌓인다. 여기서 못박는 것.

1. 한 건이 상한을 넘으면 받지 않는다 — 기록 파일에 아무것도 안 붙는다.
2. 날이 바뀌면 어제 기록을 날짜 붙은 이름으로 돌리고, 30일 지난 것은 지운다.
3. 하루치가 상한에 닿으면 그날은 더 적지 않는다.
4. 실패 화면도 크기 상한이 있고, 30일 지난 것은 지운다.
"""
from __future__ import annotations

import base64
import os
from datetime import date, datetime

import pytest

from .conftest import DEMO_TOKEN, auth

TODAY = date(2099, 3, 12)


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    from app import clock, config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(clock, "now", lambda: datetime(2099, 3, 12, 10, 0).astimezone())
    return tmp_path


def _post(client, **body):
    return client.post("/api/agent/diagnostics", json={"kind": "manual", **body},
                       headers=auth(DEMO_TOKEN))


def _stamp(path, day):
    ts = datetime(day.year, day.month, day.day, 12, 0).timestamp()
    os.utime(path, (ts, ts))


def test_small_report_is_written(client, data_dir):
    assert _post(client, error="창을 못 찾음").json() == {"ok": True}
    assert "창을 못 찾음" in (data_dir / "agent_reports.log").read_text(encoding="utf-8")


def test_oversized_report_is_refused(client, data_dir):
    from app.routers import agent_api

    res = _post(client, log_tail="가" * agent_api.DIAG_MAX_BYTES)
    assert res.status_code == 413
    assert not (data_dir / "agent_reports.log").exists()


def test_rotates_by_day_and_keeps_30_days(client, data_dir):
    log = data_dir / "agent_reports.log"
    log.write_text('{"old": 1}\n', encoding="utf-8")
    _stamp(log, date(2099, 3, 11))                                   # 어제 기록
    keep = data_dir / "agent_reports.log.2099-02-20"                 # 20일 전
    gone = data_dir / "agent_reports.log.2099-02-01"                 # 39일 전
    odd = data_dir / "agent_reports.log.손으로-둔-것"                 # 날짜가 아니다
    for path in (keep, gone, odd):
        path.write_text("{}\n", encoding="utf-8")

    assert _post(client, error="오늘").json() == {"ok": True}

    assert (data_dir / "agent_reports.log.2099-03-11").read_text(encoding="utf-8") == '{"old": 1}\n'
    assert "오늘" in log.read_text(encoding="utf-8")
    assert '"old"' not in log.read_text(encoding="utf-8")
    assert keep.exists() and odd.exists()
    assert not gone.exists(), "30일 지난 진단 기록이 남았다"


def test_daily_cap_stops_writing(client, data_dir, monkeypatch):
    from app.routers import agent_api

    monkeypatch.setattr(agent_api, "DIAG_DAY_MAX_BYTES", 100)
    log = data_dir / "agent_reports.log"
    log.write_text("x" * 100, encoding="utf-8")
    _stamp(log, TODAY)

    assert _post(client, error="더").json()["ok"] is False
    assert log.read_text(encoding="utf-8") == "x" * 100


def test_screenshot_size_and_retention(tmp_path, monkeypatch):
    from app import clock
    from app.routers import agent_api

    monkeypatch.setattr(agent_api, "AGENT_LOG_DIR", tmp_path / "agent_logs")
    monkeypatch.setattr(agent_api.config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(clock, "now", lambda: datetime(2099, 3, 12, 10, 0).astimezone())
    shots = tmp_path / "agent_logs"
    shots.mkdir()
    old = shots / "7.png"
    old.write_bytes(b"png")
    _stamp(old, date(2099, 1, 1))
    other = shots / "agent.log"                       # 건 번호 이름이 아니면 안 지운다
    other.write_text("log", encoding="utf-8")
    _stamp(other, date(2099, 1, 1))

    small = base64.b64encode(b"png").decode()
    assert agent_api._save_screenshot(8, small) == "agent_logs/8.png"
    assert not old.exists(), "30일 지난 실패 화면이 남았다"
    assert other.exists()

    monkeypatch.setattr(agent_api, "SHOT_MAX_B64", 8)
    assert agent_api._save_screenshot(9, base64.b64encode(b"0123456789").decode()) is None
    assert not (shots / "9.png").exists()
