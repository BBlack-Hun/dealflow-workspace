"""버전이 실제로 일을 하는가.

각자 PC 로 zip 을 받아 돌리는 구조라, "지금 붙어 있는 게 어느 버전인가" 를
서버가 알아야 낡은 것을 짚어 줄 수 있다. 실제로 함수 하나가 빠진 채 배포돼
사용자 PC 에서 터졌는데, 받은 쪽에서는 낡은 것인지 고친 것인지 알 수 없었다.
"""
from __future__ import annotations

import pathlib
import re

from agent.version import VERSION as AGENT_VERSION
from app import version

from .conftest import DEMO_PASSWORD


def test_the_two_files_agree():
    """zip 에 `app/` 이 안 들어가서 파일이 둘이다 — 값이 갈리면 여기서 잡는다."""
    assert AGENT_VERSION == version.VERSION, (
        f"app/version.py({version.VERSION}) 와 "
        f"agent/version.py({AGENT_VERSION}) 가 다르다")


def test_it_looks_like_a_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.VERSION), version.VERSION


def test_older_agents_are_spotted():
    assert version.agent_is_old("0.1.0")
    assert version.agent_is_old("0.1.9")
    assert not version.agent_is_old(version.MIN_AGENT_VERSION)
    assert not version.agent_is_old("9.0.0")


def test_an_agent_that_says_nothing_counts_as_old():
    """모르는 것은 낡은 것으로 본다 — 그 편이 안전하다."""
    assert version.agent_is_old(None)
    assert version.agent_is_old("")
    assert version.agent_is_old("이상한값")


def test_the_agent_zip_carries_its_version():
    """버전 파일이 zip 에 안 들어가면 발송 프로그램이 뜨지도 않는다."""
    from app.routers.setup import AGENT_FILES

    assert ("agent/version.py", "agent/version.py") in AGENT_FILES


def test_the_version_is_not_taken_from_config():
    """config 는 사용자가 고칠 수 있다 — 그러면 낡은 프로그램을 못 짚는다."""
    main = pathlib.Path("agent/main.py").read_text(encoding="utf-8")
    assert 'cfg.get("agent_version"' not in main
    assert "self.version = VERSION" in main


def test_the_footer_says_which_version_is_running(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert f"v{version.VERSION}" in client.get("/").text


def test_team_status_flags_a_stale_agent(client, db, users):
    from app.models import AgentDevice

    users["u2"].role = "admin"
    device = db.query(AgentDevice).filter_by(user_id=users["u1"].id).first()
    device.last_poll_at = "2026-08-23T00:00:00+00:00"
    device.agent_version = "0.1.0"
    db.commit()

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    body = client.get("/team").text
    assert "갱신 필요" in body
    assert "발송 프로그램이 낡았습니다" in body


def test_a_current_agent_is_not_nagged(client, db, users):
    from app.models import AgentDevice

    users["u2"].role = "admin"
    device = db.query(AgentDevice).filter_by(user_id=users["u1"].id).first()
    device.last_poll_at = "2026-08-23T00:00:00+00:00"
    device.agent_version = version.MIN_AGENT_VERSION
    db.commit()

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    body = client.get("/team").text
    assert "발송 프로그램이 낡았습니다" not in body


def test_a_stale_agent_can_still_send(client, db, users):
    """회차 당일에 낡았다고 발송을 막으면, 보낼 수 있었던 것까지 못 보낸다.

    크게 알리되 **막지는 않는다.**
    """
    from app.models import AgentDevice

    device = db.query(AgentDevice).filter_by(user_id=users["u1"].id).first()
    device.agent_version = "0.1.0"
    db.commit()

    r = client.get("/api/agent/poll",
                   headers={"Authorization": f"Bearer {device.token}"})
    assert r.status_code in (200, 204), "낡았다고 폴링을 막으면 안 된다"
