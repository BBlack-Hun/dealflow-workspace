"""테스트 서버 전용 스위치 — 보내는 시간(09:00~19:00) 끄기 (`services/send_window.py`).

사용자가 정했다: "운영서버는 발송제한이 있어야하지만 테스트서버는 없어도 됨".
여기서 못박는 것은 여섯이다.

1. **기본은 제한을 지킨다.** 변수가 없거나 `1` 이 아니면 09~19시 그대로다.
2. 켜면 폭을 읽는 자리가 **전부 함께** 00:00~24:00 이 된다 — 반만 꺼지면 고를
   수는 있는데 안 나가는(또는 그 반대) 시각이 생긴다.
3. 끄는 것은 **시간 폭 하나**다. 하루 상한은 밤에도 그대로 막는다.
4. **운영에서는 켜지지 않는다.** 값이 있어도 끈 것으로 보지 않고, 아예 뜨지 않는다.
5. 운영 compose · 배포 파일 · `.env` 예시에 이 변수가 없고, 검사(pytest)로 새지 않는다.
6. 켜면 관리자 화면 머리에 띠가 서고 시작 로그에 경고가 남는다.

시각은 전부 못박는다. 관문을 보는 검사는 `@pytest.mark.send_window` 를 단다
(`conftest._send_window_open` 이 그 밖의 검사에서는 관문을 늘 열어 둔다).
"""
from __future__ import annotations

import importlib
import logging
import os
from datetime import datetime
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

ENV = "DEALFLOW_TEST_SERVER_NO_SEND_WINDOW"
BANNER = "테스트 서버 — 발송 시간 제한 꺼짐"
ROOT = Path(__file__).resolve().parent.parent

#: 2099-03-12 는 목요일이다. 실제 오늘이 언제든 이 날이 '지금' 일 수 없다.
DAY = (2099, 3, 12)
NEXT_DAY = (2099, 3, 13)


def _at(hour, minute=0, day=DAY):
    """그날 그 시각 — **이 프로세스의 시간대**로(CI 는 UTC 다)."""
    return datetime(*day, hour, minute).astimezone()


@pytest.fixture()
def switch_on(monkeypatch):
    monkeypatch.setenv(ENV, "1")


@pytest.fixture()
def reload_config():
    """설정을 다시 읽은 검사 뒤에 원래대로 돌려놓는다.

    `monkeypatch` 보다 **먼저** 받아야 한다 — 그래야 환경변수가 돌아온 뒤에
    다시 읽는다(`test_production_guard._restore` 와 같은 까닭).
    """
    yield
    from app import config

    importlib.reload(config)


def _job(db, *, kind="deal_intro", status="draft", n=1, user_id=1, **over):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind=kind, status=status, total=n, **over)
    db.add(job)
    db.flush()
    for i in range(n):
        db.add(SendItem(job_id=job.id, room_name=f"시험방{i}", message="안녕하세요",
                        status="pending"))
    db.commit()
    return job


def _sent_today(db, user_id, count, when):
    """그날 이미 카톡으로 나간 문구 — 다른 회차에서."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user_id, kind="deal_intro", status="done", total=count)
    db.add(job)
    db.flush()
    for i in range(count):
        db.add(SendItem(job_id=job.id, room_name=f"이미{i}", message="-",
                        status="sent", channel="kakao",
                        sent_at=when.isoformat(timespec="seconds")))
    db.commit()


# ── 1. 기본은 제한을 지킨다 ──────────────────────────────────────────────────

def test_pytest_runs_with_the_window_kept():
    """테스트 서버 컨테이너 안에서 돌려도 검사는 운영과 같은 폭이다(conftest 가 지운다)."""
    from app.services import send_window

    assert os.environ.get(ENV) is None
    assert not send_window.off()
    assert send_window.hours() == (9, 19)


@pytest.mark.send_window
def test_default_keeps_the_window_everywhere(monkeypatch):
    """변수가 없으면 — 운영의 모양 그대로. 폭을 읽는 자리를 하나씩 본다."""
    monkeypatch.delenv(ENV, raising=False)
    from app import config
    from app.services import (auto_send, automation, scheduled_send, send_guard,
                              send_window, startup_monthly)

    assert not config.send_window_off()
    assert send_window.hours() == (9, 19)
    assert send_window.label() == send_guard.window_label() == "09:00~19:00"
    # 내주는 자리
    assert not send_guard.window_open(_at(8, 59))
    assert send_guard.window_open(_at(9, 0))
    assert send_guard.window_open(_at(18, 59))
    assert not send_guard.window_open(_at(19, 0))
    assert not send_guard.window_open(_at(21, 0))
    # 예약 — 고르는 자리와 푸는 자리
    with pytest.raises(ValueError, match="09:00~19:00"):
        scheduled_send.check(_at(21, 30), _at(10, 0))
    assert scheduled_send.deadline(_at(18, 40)) == _at(19, 0)
    # 팀 시간대
    assert automation.guard_window() == (9 * 60, 19 * 60)
    with pytest.raises(ValueError):
        automation.clean_team({"window_start": "00:00", "window_end": "24:00"})
    # 자동화 · 스타트업 월간 발송 시각 칸
    with pytest.raises(ValueError, match="09:00~19:00"):
        startup_monthly.parse_time("21:00")
    # 미팅 후기 자동 준비 창
    assert auto_send.clamp_hours(0, 24) == (9, 19)
    # 아침에 세우는 시각
    assert send_window.prepare_hour(8) == 8


@pytest.mark.send_window
@pytest.mark.parametrize("value", ["", "0", "true", "yes", "on", "2"])
def test_only_1_turns_it_off(monkeypatch, value):
    """잘못 적은 값으로 꺼지지 않는다 — 꺼지는 쪽이 위험한 쪽이다."""
    from app.services import send_guard, send_window

    monkeypatch.setenv(ENV, value)
    assert send_window.hours() == (9, 19)
    assert not send_guard.window_open(_at(21, 0))


@pytest.mark.send_window
def test_default_night_poll_still_holds_the_job(client, db, monkeypatch):
    """기본이면 밤 9시에 발송기가 물어도 문구 잡은 큐에 그대로 선다."""
    from app import clock

    monkeypatch.delenv(ENV, raising=False)
    job = _job(db, status="queued", n=2)
    monkeypatch.setattr(clock, "now", lambda: _at(21, 0))
    got = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                     headers=auth(DEMO_TOKEN))
    assert got.status_code == 204
    db.expire_all()
    assert db.get(type(job), job.id).status == "queued"


# ── 2. 켜면 전부 함께 ────────────────────────────────────────────────────────

@pytest.mark.send_window
def test_switch_opens_every_place_together(switch_on):
    from app.services import (auto_send, automation, scheduled_send, send_guard,
                              send_window, startup_monthly)

    assert send_window.off()
    assert send_window.hours() == (0, 24)
    assert send_window.label() == send_guard.window_label() == "00:00~24:00"
    # 내주는 자리 — 하루 내내
    for hour in (0, 3, 8, 19, 21, 23):
        assert send_guard.window_open(_at(hour, 30)), hour
    # 예약 — 밤 시각을 고를 수 있고, 푸는 창이 자정을 넘어 이어진다
    at = scheduled_send.check(_at(23, 30), _at(21, 0))
    assert scheduled_send.deadline(at) == _at(0, 30, day=NEXT_DAY)
    assert scheduled_send.deadline(_at(21, 0)) == _at(22, 0)
    # 팀 시간대 — 00:00~24:00 을 받는다
    assert automation.guard_window() == (0, 24 * 60)
    cleaned = automation.clean_team({"window_start": "00:00", "window_end": "24:00"})
    assert (cleaned["window_start"], cleaned["window_end"]) == ("00:00", "24:00")
    # 자동화 · 스타트업 월간 발송 시각 칸
    assert startup_monthly.parse_time("23:30") == "23:30"
    assert startup_monthly.parse_time("00:10") == "00:10"
    # 미팅 후기 자동 준비 창
    assert auto_send.clamp_hours(0, 24) == (0, 24)
    # 아침에 세우는 시각 — 0시부터(00:30 회차를 08시에 세우면 이미 지난 뒤다)
    assert send_window.prepare_hour(8) == 0


def test_scheduled_night_job_is_released_not_expired(monkeypatch):
    """밤 예약이 '시각을 놓쳤다' 로 떨어지지 않고 풀린다 — 기본이면 떨어진다."""
    from app.models import SendJob
    from app.services import scheduled_send

    job = SendJob(user_id=1, kind="deal_intro", status="draft",
                  scheduled_at=_at(18, 40).isoformat(timespec="seconds"))
    monkeypatch.delenv(ENV, raising=False)
    assert scheduled_send.state(job, _at(19, 10)) == scheduled_send.STATE_EXPIRED
    monkeypatch.setenv(ENV, "1")
    assert scheduled_send.state(job, _at(19, 10)) == scheduled_send.STATE_DUE


@pytest.mark.send_window
def test_switch_hands_out_the_job_at_night(switch_on, client, db, monkeypatch):
    """켜면 밤 9시에도 문구 잡을 내준다 — 그 밖의 판정(종류 · 주인)은 그대로다."""
    from app import clock

    job = _job(db, status="queued", n=2)
    monkeypatch.setattr(clock, "now", lambda: _at(21, 0))
    got = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                     headers=auth(DEMO_TOKEN))
    assert got.status_code == 200
    assert got.json()["job_id"] == job.id


# ── 3. 끄는 것은 시간 폭 하나다 ──────────────────────────────────────────────

@pytest.mark.send_window
def test_daily_cap_still_holds_at_night(switch_on, db, users):
    """새벽 2시에 시간은 열려 있어도, 오늘 상한을 다 쓰면 더 내주지 않는다."""
    from app.services import send_guard

    users["u1"].daily_send_cap = 2
    db.commit()
    night = _at(2, 0)
    gate = send_guard.gate(db, users["u1"], night)
    assert (gate.blocked, gate.left) == ((), 2)

    _sent_today(db, users["u1"].id, 2, _at(1, 30))
    gate = send_guard.gate(db, users["u1"], night)
    assert (gate.blocked, gate.left) == (send_guard.GATED_KINDS, 0)


@pytest.mark.send_window
def test_daily_cap_holds_the_poll_at_night(switch_on, client, db, users, monkeypatch):
    """발송기 쪽에서 봐도 같다 — 상한 1, 이미 1통 → 밤에 물어도 안 내준다."""
    from app import clock

    users["u1"].daily_send_cap = 1
    db.commit()
    _sent_today(db, users["u1"].id, 1, _at(20, 0))
    _job(db, status="queued", n=2)
    monkeypatch.setattr(clock, "now", lambda: _at(21, 0))
    got = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                     headers=auth(DEMO_TOKEN))
    assert got.status_code == 204


# ── 4. 운영에서는 켜지지 않는다 ──────────────────────────────────────────────

@pytest.mark.send_window
def test_production_never_turns_it_off(monkeypatch):
    from app import config
    from app.services import send_guard, send_window

    monkeypatch.setenv(ENV, "1")
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    assert not config.send_window_off()
    assert send_window.hours() == (9, 19)
    assert not send_guard.window_open(_at(21, 0))


def test_production_refuses_to_start_with_the_switch(reload_config, monkeypatch):
    """운영 .env 에 실수로 들어가면 **뜨지 않는다** — 조용히 밤에 나가는 것보다 낫다."""
    for key in ("DEALFLOW_ENV", "DEALFLOW_AGENT_TOKEN", "DEALFLOW_INITIAL_PASSWORD",
                "DEALFLOW_SEED_DEMO"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DEALFLOW_ENV", "production")
    monkeypatch.setenv("DEALFLOW_AGENT_TOKEN", "agt_real_secret")
    monkeypatch.setenv("DEALFLOW_INITIAL_PASSWORD", "바꾼비밀번호")
    from app import config

    cfg = importlib.reload(config)
    cfg.assert_ready()                       # 스위치가 없으면 뜬다

    monkeypatch.setenv(ENV, "1")
    with pytest.raises(RuntimeError) as err:
        cfg.assert_ready()
    assert ENV in str(err.value)


# ── 5. 운영 파일에 없다 · 검사로 새지 않는다 ─────────────────────────────────

def test_prod_compose_does_not_carry_the_switch():
    text = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert ENV not in text


def test_no_deploy_file_or_env_template_carries_the_switch():
    """배포 폴더 · 배포 실 · `.env` 예시 · 기본 compose 어디에도 없다."""
    paths = [ROOT / "docker-compose.yml", ROOT / ".env.example", ROOT / "Dockerfile"]
    paths += [p for p in (ROOT / "deploy").rglob("*") if p.is_file()]
    paths += [p for p in (ROOT / ".github").rglob("*") if p.is_file()]
    for path in paths:
        if path.exists():
            assert ENV not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_no_override_file_that_compose_reads_by_itself():
    """`docker-compose.override.yml` 은 compose 가 저절로 읽는다 — 검사 실행에 샌다."""
    assert not (ROOT / "docker-compose.override.yml").exists()
    assert not (ROOT / "docker-compose.override.yaml").exists()


def test_testserver_compose_sets_only_the_switch_for_web():
    import yaml

    path = ROOT / "docker-compose.testserver.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(data) == ["services"]
    assert list(data["services"]) == ["web"]
    assert data["services"]["web"] == {"environment": {ENV: "1"}}
    # 띄우는 법이 머리말에 적혀 있다.
    assert ("docker compose -f docker-compose.yml -f docker-compose.testserver.yml "
            "up -d --no-build web") in path.read_text(encoding="utf-8")


# ── 6. 보이게 ────────────────────────────────────────────────────────────────

def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def test_admin_sees_the_banner_only_when_switched(client, db, users, monkeypatch):
    users["u1"].role = "admin"
    db.commit()
    _login(client)

    monkeypatch.delenv(ENV, raising=False)
    page = client.get("/team").text
    assert 'data-testid="send-window-off-banner"' not in page
    assert BANNER not in page

    monkeypatch.setenv(ENV, "1")
    page = client.get("/team").text
    assert 'data-testid="send-window-off-banner"' in page
    assert BANNER in page


def test_member_does_not_see_the_banner(client, users, monkeypatch):
    monkeypatch.setenv(ENV, "1")
    _login(client)
    page = client.get("/").text
    assert 'data-testid="send-window-off-banner"' not in page


def test_team_time_inputs_unchanged_by_default_and_open_when_switched(
        client, db, users, monkeypatch):
    """팀 공통 시간대 칸 — 기본은 지금과 같은 글자(09:00~19:00 · 10분 단위),
    켜면 `24:00` 을 못 담는 시간 칸에 `23:59` 까지 고를 수 있다."""
    users["u1"].role = "admin"
    db.commit()
    _login(client)

    monkeypatch.delenv(ENV, raising=False)
    page = client.get("/team").text
    assert 'name="window_end" value="19:00" step="600"' in page
    assert 'min="09:00" max="19:00"' in page

    monkeypatch.setenv(ENV, "1")
    page = client.get("/team").text
    assert 'min="00:00" max="23:59"' in page
    assert 'name="window_end" value="19:00" step="60"' in page


def test_team_window_accepts_all_day_from_the_form_only_when_switched(
        client, db, users, monkeypatch):
    from app.services import automation

    users["u1"].role = "admin"
    db.commit()
    _login(client)
    form = {"window_start": "00:00", "window_end": "23:59"}

    monkeypatch.delenv(ENV, raising=False)
    client.post("/team/automation-team", data=form, follow_redirects=False)
    db.expire_all()
    assert automation.team(db).window_label == "09:00~19:00"

    monkeypatch.setenv(ENV, "1")
    client.post("/team/automation-team", data=form, follow_redirects=False)
    db.expire_all()
    assert automation.team(db).window_label == "00:00~23:59"


def test_startup_warns_only_when_switched(monkeypatch, caplog):
    from app.services import send_window

    monkeypatch.delenv(ENV, raising=False)
    with caplog.at_level(logging.WARNING, logger="app.services.send_window"):
        send_window.announce()
    assert BANNER not in caplog.text

    monkeypatch.setenv(ENV, "1")
    with caplog.at_level(logging.WARNING, logger="app.services.send_window"):
        send_window.announce()
    assert BANNER in caplog.text
    assert ENV in caplog.text


def test_create_app_announces_the_switch(monkeypatch, caplog):
    from app.main import create_app

    monkeypatch.setenv(ENV, "1")
    with caplog.at_level(logging.WARNING, logger="app.services.send_window"):
        create_app()
    assert BANNER in caplog.text
