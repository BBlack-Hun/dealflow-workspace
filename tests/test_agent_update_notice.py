"""옛 발송기 알림 — 본인 발송기가 최신보다 낡았으면 **화면마다** 창이 뜬다.

지키는 것:

1. **판은 숫자로 견준다.** `0.10.0` 은 `0.9.0` 보다 새것이다. 못 읽는 판은 낡았다고
   하지 않는다 — 모르는 판으로 모든 화면을 가리면 받아도 안 사라진다.
2. **화면마다 뜬다.** 밑틀을 쓰는 화면을 훑는다(손으로 목록을 적지 않는다). 닫는
   것은 그 화면에서만 — 기억하는 장치가 없다.
3. **안 뜨는 자리.** 로그인 화면 · 내려받기 화면 · 최신 판 · 빈 판 · 오래 안 쓴 PC ·
   남의 기기 · 팀원 화면으로 보는 중의 그 팀원 기기.
4. **새 판을 보고하면 바로 사라진다.** 발송기가 실제로 두드리는 길(박동)로 본다.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import clock, version
from app.services import agent_update

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

MARK = 'data-testid="agent-update"'


def _set_device(db, user_id: int, ver, days_ago: float = 0):
    from app.models import AgentDevice

    dev = db.query(AgentDevice).filter_by(user_id=user_id).one()
    dev.agent_version = ver
    dev.last_poll_at = (clock.now() - timedelta(days=days_ago)).isoformat()
    db.commit()
    return dev


def _login(client, phone: str = "01000000001"):
    r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                    follow_redirects=False)
    assert r.status_code == 303
    return client


# ── 1. 판 견주기 ─────────────────────────────────────────────────────────────

def test_versions_compare_as_numbers_not_text():
    assert agent_update.is_older("0.9.0", "0.10.0")
    assert not agent_update.is_older("0.10.0", "0.9.0")
    assert agent_update.is_older("0.5.0", "0.11.13")
    assert agent_update.is_older("0.11.9", "0.11.13")
    assert not agent_update.is_older("0.11.13", "0.11.13")
    assert not agent_update.is_older("1.0.0", "0.11.13")
    # 자리 수가 달라도 빈 자리는 0 이다
    assert not agent_update.is_older("0.11", "0.11.0")
    assert agent_update.is_older("0.11", "0.11.1")


@pytest.mark.parametrize("bad", [None, "", "  ", "이상한값", "v0.5.0", "0.5.0-beta", "0..5"])
def test_an_unreadable_version_is_not_called_old(bad):
    assert not agent_update.is_older(bad, "0.11.13")


# ── 2. 화면마다 뜬다 ─────────────────────────────────────────────────────────

def test_an_old_agent_brings_up_the_notice(client, db, users):
    _set_device(db, users["u1"].id, "0.5.0")
    html = _login(client).get("/").text

    assert MARK in html
    assert "발송기 업데이트가 필요합니다" in html
    assert "<b>0.5.0</b>" in html                      # 지금 판
    assert f"<b>{version.VERSION}</b>" in html         # 새 판 — 내려받기가 싣는 그 값
    assert 'href="/setup">새 발송기 내려받기' in html  # 기존 내려받기 화면
    # 닫기는 브라우저가 한다 — 스크립트도 기억하는 장치도 없다
    assert '<form method="dialog"' in html and "나중에" in html


def test_it_shows_on_every_screen_but_the_download_screen(client, db, users):
    """**화면 이름을 손으로 적지 않는다** — 등록된 화면을 훑는다(`test_notices` 와 같은 얼개)."""
    from app.main import create_app

    _set_device(db, users["u1"].id, "0.5.0")
    _login(client)
    checked = 0
    for route in create_app().routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or ()
        if "GET" not in methods or "{" in path:
            continue
        if path.startswith(("/api/", "/static")) or path in ("/logout", "/health", "/login"):
            continue
        resp = client.get(path, follow_redirects=False)
        if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
            continue
        if 'class="sidebar"' not in resp.text:      # 밑틀을 쓰는 화면만
            continue
        if path.startswith("/setup"):
            assert MARK not in resp.text, "내려받기 화면에서는 띄우지 않는다"
            continue
        assert MARK in resp.text, f"{path} 에 알림 창이 안 떴습니다"
        checked += 1
    assert checked >= 8, f"훑은 화면이 너무 적습니다({checked}개) — 검사가 헛돕니다"


def test_closing_is_for_this_screen_only(client, db, users):
    """닫아도 서버는 모른다 — 같은 화면을 다시 열어도, 다른 화면을 열어도 또 뜬다."""
    _set_device(db, users["u1"].id, "0.5.0")
    _login(client)
    for path in ("/", "/contacts", "/deals", "/"):
        assert MARK in client.get(path).text, path


def test_not_on_the_login_or_download_screens(client, db, users):
    _set_device(db, users["u1"].id, "0.5.0")
    assert MARK not in client.get("/login").text       # 로그인 전
    _login(client)
    assert MARK not in client.get("/setup").text       # 내려받기 화면 자체


def test_not_while_the_password_must_be_changed(client, db, users):
    """어디를 눌러도 비밀번호 화면으로 돌아오는 동안에는 [내려받기]가 갈 곳이 없다."""
    _set_device(db, users["u1"].id, "0.5.0")
    users["u1"].must_change_password = 1
    db.commit()
    _login(client)
    assert MARK not in client.get("/account/password").text


# ── 3. 안 뜨는 기기 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("ver", [version.VERSION, "", None, "이상한값"])
def test_latest_or_unknown_versions_stay_quiet(client, db, users, ver):
    _set_device(db, users["u1"].id, ver)
    assert MARK not in _login(client).get("/").text


def test_a_pc_left_unused_for_a_month_stays_quiet(client, db, users):
    _set_device(db, users["u1"].id, "0.5.0", days_ago=agent_update.STALE_DAYS + 1)
    assert MARK not in _login(client).get("/").text
    _set_device(db, users["u1"].id, "0.5.0", days_ago=agent_update.STALE_DAYS - 1)
    assert MARK in client.get("/").text


def test_a_device_that_never_reported_stays_quiet(client, db, users):
    """conftest 의 기기는 보고한 적이 없다 — 판도 시각도 비어 있다."""
    assert MARK not in _login(client).get("/").text


def test_someone_elses_old_agent_is_not_my_business(client, db, users):
    _set_device(db, users["u2"].id, "0.5.0")
    _set_device(db, users["u1"].id, version.VERSION)
    assert MARK not in _login(client).get("/").text


def test_view_as_looks_at_the_admins_own_pc(client, db, users):
    """팀원 화면으로 보는 중이어도 **로그인한 본인** 기기다 — 대리 보기는 보기·수정만."""
    users["u2"].role = "admin"
    db.commit()
    _set_device(db, users["u1"].id, "0.5.0")         # 보는 대상(팀원)은 옛 판
    _set_device(db, users["u2"].id, version.VERSION)  # 관리자 본인은 최신
    _login(client, "01000000002")
    client.post("/account/view-as", data={"member_id": users["u1"].id, "next": "/"})
    html = client.get("/contacts").text
    assert 'data-testid="view-as-banner"' in html     # 정말 보는 중이다
    assert MARK not in html

    _set_device(db, users["u2"].id, "0.5.0")          # 관리자 본인이 옛 판이면 뜬다
    assert MARK in client.get("/contacts").text


# ── 4. 새 판을 보고하면 바로 사라진다 ────────────────────────────────────────

def test_reporting_the_new_version_clears_it_at_once(client, db, users):
    _set_device(db, users["u1"].id, "0.5.0")
    _login(client)
    assert MARK in client.get("/").text

    r = client.post("/api/agent/heartbeat", json={"agent_version": version.VERSION},
                    headers=auth(DEMO_TOKEN))
    assert r.status_code == 200
    assert MARK not in client.get("/").text


# ── 5. 여러 기기 · 팀 현황 ───────────────────────────────────────────────────

def test_several_old_pcs_are_listed_by_name():
    """지금은 계정마다 기기 한 줄이지만(`agent_devices.user_id` 유일) 창은 여럿도 그린다."""
    from app.deps import templates

    html = templates.env.get_template("_agent_update.html").render(agent_update={
        "latest": "0.11.13",
        "devices": [{"name": "PC-가", "version": "0.5.0"},
                    {"name": "PC-나", "version": "0.10.2"}]})
    assert "PC-가 · <b>0.5.0</b>" in html and "PC-나 · <b>0.10.2</b>" in html
    assert "지금 <b>" not in html                      # 하나일 때의 괄호는 안 붙는다


def test_team_screen_tags_old_versions(client, db, users):
    """팀 현황: 최신보다 낡았지만 `MIN_AGENT_VERSION` 위인 판에 `옛 버전` 딱지."""
    users["u2"].role = "admin"
    db.commit()
    _set_device(db, users["u1"].id, version.MIN_AGENT_VERSION)
    _set_device(db, users["u2"].id, version.VERSION)
    html = _login(client, "01000000002").get("/team").text
    assert html.count(">옛 버전</span>") == 1
