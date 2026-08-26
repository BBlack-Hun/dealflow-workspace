"""발송 프로그램(에이전트)이 실제로 도는가.

여기까지는 테스트가 없었다 — 서버만 봤다. 그래서 함수 하나가 통째로 빠진 채
배포됐고, 사용자 PC 에서 `NameError: name 'send_item' is not defined` 로
터졌다. 문법 검사(ast.parse)는 통과한다 — 이름이 없는 건 실행해야 안다.

에이전트는 사용자 PC 에서 돌아 로그를 바로 볼 수 없으므로, 서버보다 오히려
더 확실히 잡아 둬야 한다.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def agent_main():
    return importlib.import_module("agent.main")


class FakeResult:
    def __init__(self, ok=True, error=None):
        self.ok = ok
        self.error = error
        self.screenshot_b64 = None


class FakeSender:
    """보낸 것을 순서대로 적어 두는 가짜 카톡."""

    def __init__(self, fail_on=None):
        self.sent = []
        self.fail_on = fail_on          # 몇 번째 통에서 실패할지 (1부터)

    def send_text(self, room, text):
        self.sent.append((room, text))
        if self.fail_on == len(self.sent):
            return FakeResult(ok=False, error="방을 찾지 못했습니다")
        return FakeResult(ok=True)


NO_GAP = {"part_gap_sec": 0}


def test_every_function_the_loop_calls_exists(agent_main):
    """호출부만 고치고 정의를 안 넣은 채 배포된 적이 있다."""
    for name in ("send_item", "process_job", "process_verify_job",
                 "build_sender", "load_config", "main"):
        assert callable(getattr(agent_main, name, None)), f"{name} 가 없다"


def test_one_message_still_goes_as_one(agent_main):
    sender = FakeSender()
    result = agent_main.send_item(
        sender, {"room_name": "홍길동 심사역님", "message": "안녕하세요"}, NO_GAP)

    assert result.ok
    assert sender.sent == [("홍길동 심사역님", "안녕하세요")]


def test_parts_go_in_order(agent_main):
    """링크가 먼저 한 통씩, 설명이 마지막."""
    sender = FakeSender()
    result = agent_main.send_item(sender, {
        "room_name": "홍길동 심사역님",
        "message": "합친 전문",
        "parts": ["1번 샘플애그\nhttps://…", "2번 샘플메디\nhttps://…",
                  "홍길동 심사역님 안녕하세요."],
    }, NO_GAP)

    assert result.ok
    assert [t for _room, t in sender.sent] == [
        "1번 샘플애그\nhttps://…", "2번 샘플메디\nhttps://…",
        "홍길동 심사역님 안녕하세요."]
    assert "합친 전문" not in [t for _r, t in sender.sent]


def test_a_failed_bubble_stops_the_rest(agent_main):
    """설명만 가고 링크가 안 가면 자료가 없다 — 처음부터 다시 보내야 한다."""
    sender = FakeSender(fail_on=2)
    result = agent_main.send_item(sender, {
        "room_name": "홍길동 심사역님", "message": "…",
        "parts": ["1통", "2통", "3통"]}, NO_GAP)

    assert not result.ok
    assert "2/3번째" in result.error, result.error
    assert len(sender.sent) == 2, "실패한 뒤에도 계속 보냈다"


def test_empty_parts_falls_back_to_the_message(agent_main):
    sender = FakeSender()
    agent_main.send_item(
        sender, {"room_name": "방", "message": "본문", "parts": []}, NO_GAP)
    assert [t for _r, t in sender.sent] == ["본문"]


def test_the_gap_between_bubbles_is_configurable(agent_main):
    """연달아 쏟으면 카톡이 순서를 뒤집거나 묶어 버린다."""
    assert agent_main.DEFAULT_CONFIG["part_gap_sec"] > 0

# --- 서버와 에이전트가 같은 잡 종류를 보는가 ----------------------------------
#
# 딜 소싱 제안을 서버에만 넣고 에이전트의 목록을 안 고쳐서, 잡이 큐에 그대로
# 멈춰 있었다. 에이전트는 폴링할 때 자기 목록을 `?kinds=` 로 보내고, 서버는
# 그 안에 든 것만 준다 — 한쪽만 고치면 조용히 안 나간다.

def test_agent_and_server_agree_on_send_kinds():
    from agent.main import SEND_KINDS as AGENT_KINDS
    from app.models import SEND_KINDS as SERVER_KINDS

    assert tuple(AGENT_KINDS) == tuple(SERVER_KINDS), (
        "서버가 만드는 잡을 에이전트가 집어가지 못합니다 — "
        f"서버 {SERVER_KINDS} · 에이전트 {AGENT_KINDS}"
    )


def test_the_agent_asks_for_every_kind_it_can_do():
    """폴링할 때 보내는 목록이 실제 처리 목록보다 좁으면 그만큼 못 받는다."""
    from agent.main import SEND_KINDS, SUPPORTED_KINDS, VERIFY_KIND

    assert set(SEND_KINDS) <= set(SUPPORTED_KINDS)
    assert VERIFY_KIND in SUPPORTED_KINDS


def test_a_sourcing_job_is_handed_to_the_agent(client, db, users):
    """큐에 넣어 두고 못 집어가면 발송이 조용히 멈춘다."""
    from agent.main import SUPPORTED_KINDS
    from app.models import AgentDevice, SendItem, SendJob

    # 사용자당 기기는 하나다 — 있으면 그 토큰을 쓴다.
    dev = db.query(AgentDevice).filter_by(user_id=users["u1"].id).first()
    if dev is None:
        dev = AgentDevice(user_id=users["u1"].id, token="agt_test_sourcing",
                          hostname="t", agent_version="0.3.0")
        db.add(dev)
    job = SendJob(user_id=users["u1"].id, kind="sourcing_intro", status="queued",
                  total=1, sent=0, failed=0)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, sourcing_contact_id=None, room_name="테스트방",
                    message="문구", status="pending"))
    db.commit()

    r = client.get("/api/agent/poll",
                   params={"kinds": ",".join(SUPPORTED_KINDS)},
                   headers={"Authorization": f"Bearer {dev.token}"})
    assert r.status_code == 200, "소싱 잡을 집어가지 못했습니다"
    assert r.json()["kind"] == "sourcing_intro"

