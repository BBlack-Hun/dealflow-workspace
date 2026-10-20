"""[중단]이 **한 건 안에서도** 들리는가 (발송기 0.11.12).

## 실제로 난 일

잡 150(IR 자료 전달, 1건) — 발송기가 건을 집은 지 4초쯤 뒤에 [중단]을 눌렀는데 30~40초
뒤에 자료 파일 셋과 문구가 그대로 나갔다. 0.11.11 까지는 건 **앞에서** 한 번만 물었고
(`check_before_send`), 파일을 올리고 문구를 보내는 동안에는 다시 묻지 않았다.

0.11.12 첫 판도 **한 통짜리 건**은 다시 묻지 않았다 — 시험 서버 실기에서 [중단] 0.4초
뒤 첫 Enter 가 빗나가고, 다시 찾아 약 7초 뒤 문구가 나갔다. 이제 발송기가 방을 연 뒤
넣기 직전마다 · 다시 찾기 전마다 묻는다(그쪽은 발송기별 시험이 본다).

## 이 파일이 지키는 것

    ① 파일 하나 · 문구 한 통 앞마다 다시 묻는다 — 첫 파일 앞 · 파일 사이 · 문구 앞 ·
       **한 통짜리 건의 그 한 통 앞**
    ② 아무것도 안 나갔으면 건 앞에서 멈춘 것과 같다(그 건은 보고하지 않고 잡만 멈춤)
    ③ 무엇이 나갔으면 '보냄' 으로 적고 무엇이 나갔는지 남긴다 — 안 그러면 [취소분
       재발송]이 같은 자료를 또 보낸다
    ④ 이 건만 취소됐으면 이 건만 멈추고 다음 건은 보낸다
    ⑤ 서버에 못 물으면 건 앞의 확인과 똑같이 몇 번 다시 묻고 멈춘다(잡은 '멈춤')
    ⑥ 묻는 수 — 건 앞 한 번 + 넣을 것(파일 · 문구 한 통)마다 한 번

서버는 흉내다(`FakeClient`) — 묻는 차례대로 답을 정해 둔다. 실제 서버와 맞물리는 것은
`test_cancel_stops_sending.py` 가 본다.
"""
from __future__ import annotations

import importlib

import pytest
import requests

from agent.sender.base import SendResult, stop_result

FAST = {"delay_min_sec": 0, "delay_max_sec": 0, "part_gap_sec": 0, "job_cap": 60,
        "cancel_check_retries": 3, "cancel_check_backoff_sec": 0}
ROOM = "가나다 시험방"
FILES = ["가.pdf", "나.pdf", "다.pdf"]


@pytest.fixture()
def agent_main(monkeypatch):
    mod = importlib.import_module("agent.main")
    # 진단 스냅샷은 창 목록을 긁는다 — 여기서는 무엇을 실었는지만 본다.
    monkeypatch.setattr(mod, "collect_diagnostics",
                        lambda sender, kind, target_room=None, error=None:
                        {"kind": kind, "target_room": target_room, "error": error})
    return mod


class FakeClient:
    """서버 대신. [중단] 확인에 **묻는 차례대로** 답하고, 보고를 적어 둔다.

    `stop_at=n` — n번째 물음부터 잡이 멈췄다고 답한다(1번째는 건 앞의 확인).
    `item_stop_at=n` — n번째 물음부터 1번 건만 취소됐다고 답한다.
    `down_at=n` — n번째 물음부터 서버에 닿지 않는다.
    """

    def __init__(self, stop_at=0, item_stop_at=0, down_at=0):
        self.stop_at, self.item_stop_at, self.down_at = stop_at, item_stop_at, down_at
        self.asked = 0
        self.items, self.jobs, self.diags = [], [], []

    def job_state(self, job_id):
        self.asked += 1
        if self.down_at and self.asked >= self.down_at:
            raise requests.ConnectionError("서버가 내려갔다")
        if self.stop_at and self.asked >= self.stop_at:
            return {"canceled": True, "status": "canceled"}
        hit = self.item_stop_at and self.asked >= self.item_stop_at
        return {"canceled": False, "canceled_items": [1] if hit else []}

    def report_item(self, item_id, status, error=None, **_):
        self.items.append((item_id, status, error))

    def report_job(self, job_id, status):
        self.jobs.append(status)

    def report_diagnostics(self, payload):
        self.diags.append(payload)


class Kakao:
    """보낸 것을 차례대로 적는 가짜 카톡. 파일 하나 · 문구 한 통을 넣기 직전마다
    `should_stop` 을 묻는다(진짜 발송기와 같은 약속 — `Sender.send_file` · `send_text`)."""

    name = "test"

    def __init__(self):
        self.sent = []

    def send_file(self, room, files, should_stop=None):
        for n, name in enumerate(files):
            if should_stop is not None and should_stop():
                return stop_result("파일 앞에서 멈췄습니다", n)
            self.sent.append(name)
        return SendResult(ok=True)

    def send_text(self, room, text, should_stop=None):
        if should_stop is not None and should_stop():
            return stop_result("문구를 넣기 전에 멈췄습니다")
        self.sent.append(text)
        return SendResult(ok=True)


def ir_job(*items):
    return {"job_id": 150, "kind": "ir_delivery", "items": list(items)}


def ir_item(item_id=1, files=FILES, parts=("자료 보내드렸습니다",)):
    return {"id": item_id, "room_name": ROOM, "files": list(files), "parts": list(parts)}


# ── ① ② 첫 파일 앞 — 아무것도 안 나갔다 ─────────────────────────────────

def test_첫_파일_앞에서_멈추면_아무것도_안_보내고_건도_보고하지_않는다(agent_main):
    client, kakao = FakeClient(stop_at=2), Kakao()        # 2 = 첫 파일 앞
    agent_main.process_job(client, kakao, ir_job(ir_item()), FAST)

    assert kakao.sent == []
    assert client.items == []                 # 건 앞에서 멈춘 것과 같다 — 서버는 이미 '취소'
    assert client.jobs == ["canceled"]
    assert client.diags == []


# ── ③ 파일 사이 · 문구 앞 — 나간 것이 있다 ──────────────────────────────

def test_파일_사이에서_멈추면_나간_파일까지만_보냄으로_적는다(agent_main):
    client, kakao = FakeClient(stop_at=4), Kakao()        # 4 = 세 번째 파일 앞
    agent_main.process_job(client, kakao, ir_job(ir_item()), FAST)

    assert kakao.sent == ["가.pdf", "나.pdf"]
    note = "중단: 파일 2/3 보냄, 문구 안 보냄"
    assert client.items == [(1, "sent", note)]
    assert client.jobs == ["canceled"]
    assert client.diags == [{"kind": "send_stopped", "target_room": ROOM, "error": note}]


def test_문구_앞에서_멈추면_파일만_보냄으로_적는다(agent_main):
    client, kakao = FakeClient(stop_at=5), Kakao()        # 5 = 파일 셋 뒤 문구 앞
    agent_main.process_job(client, kakao, ir_job(ir_item()), FAST)

    assert kakao.sent == FILES
    assert client.items == [(1, "sent", "중단: 파일 3/3 보냄, 문구 안 보냄")]
    assert client.jobs == ["canceled"]


def test_한_통짜리_건도_방을_연_뒤_넣기_전에_멈추면_아무것도_안_보낸다(agent_main):
    """시험 서버 실기(0.11.12 첫 판) — 건을 집은 0.4초 뒤 [중단], 그래도 문구가 나갔다."""
    client, kakao = FakeClient(stop_at=2), Kakao()        # 2 = 방을 연 뒤 그 한 통 앞
    agent_main.process_job(client, kakao, {"job_id": 7, "kind": "deal_intro", "items": [
        {"id": 1, "room_name": ROOM, "message": "안녕하세요"}]}, FAST)

    assert kakao.sent == []
    assert client.items == []                 # 서버에는 이미 '취소' — 그대로 둔다
    assert client.jobs == ["canceled"]


def test_여러_통_문구_사이에서_멈추면_나간_통까지_적는다(agent_main):
    client, kakao = FakeClient(stop_at=3), Kakao()        # 3 = 둘째 통 앞(파일 없음)
    item = ir_item(files=(), parts=("첫 통", "둘째 통"))
    agent_main.process_job(client, kakao, ir_job(item), FAST)

    assert kakao.sent == ["첫 통"]
    assert client.items == [(1, "sent", "중단: 문구 1/2통 보냄")]


def test_멈추지_않으면_파일_하나_문구_한_통_앞마다_묻고_다_보낸다(agent_main):
    client, kakao = FakeClient(), Kakao()
    agent_main.process_job(client, kakao, ir_job(ir_item()), FAST)

    assert kakao.sent == FILES + ["자료 보내드렸습니다"]
    assert client.asked == 1 + 3 + 1          # 건 앞 · 파일 셋 앞 · 문구 앞
    assert client.items == [(1, "sent", None)]
    assert client.jobs == ["done"]


# ── ④ 이 건만 취소 ──────────────────────────────────────────────────────

def test_이_건만_보내는_중에_취소되면_그_건만_멈추고_다음_건은_보낸다(agent_main):
    client, kakao = FakeClient(item_stop_at=3), Kakao()   # 3 = 1번 건 둘째 파일 앞
    second = {"id": 2, "room_name": "라마바 시험방", "message": "안녕하세요"}
    agent_main.process_job(client, kakao, ir_job(ir_item(), second), FAST)

    assert kakao.sent == ["가.pdf", "안녕하세요"]
    assert client.items == [(1, "sent", "중단: 파일 1/3 보냄, 문구 안 보냄"),
                            (2, "sent", None)]
    assert client.jobs == ["done"]


# ── ⑤ 서버에 못 물음 ────────────────────────────────────────────────────

def test_보내는_중에_서버에_못_물으면_몇_번_다시_묻고_멈춘다(agent_main):
    client, kakao = FakeClient(down_at=3), Kakao()        # 3 = 둘째 파일 앞부터
    agent_main.process_job(client, kakao, ir_job(ir_item()), FAST)

    assert kakao.sent == ["가.pdf"]
    assert client.asked == 2 + FAST["cancel_check_retries"]
    assert client.items == [(1, "sent", "중단: 파일 1/3 보냄, 문구 안 보냄")]
    assert client.jobs == ["paused"]


# ── ⑥ 묻는 수 ───────────────────────────────────────────────────────────

def test_한_통짜리_건은_건_앞과_넣기_직전에_묻는다(agent_main):
    client, kakao = FakeClient(), Kakao()
    items = [{"id": n, "room_name": ROOM, "message": f"{n}번째"} for n in (1, 2, 3)]
    agent_main.process_job(client, kakao, {"job_id": 7, "kind": "deal_intro",
                                           "items": items}, FAST)

    assert client.asked == 3 * 2
    assert [status for _id, status, _e in client.items] == ["sent"] * 3


# ── 첫 시도에 막혔다가 나간 건 — 실패가 아니라 경고 ──────────────────────

def test_첫_시도_경고는_보냄으로_적고_로그와_진단_기록에_남긴다(agent_main, caplog):
    class Retried(Kakao):
        def send_text(self, room, text, should_stop=None):
            super().send_text(room, text, should_stop)
            return SendResult(ok=True, warning="첫 시도에 Enter 로 방이 열리지 않음 — "
                                               "다시 찾아 열었습니다")

    client = FakeClient()
    with caplog.at_level("WARNING", logger="agent"):
        agent_main.process_job(client, Retried(), {"job_id": 7, "kind": "deal_intro", "items": [
            {"id": 1, "room_name": ROOM, "message": "안녕하세요"}]}, FAST)

    assert client.items == [(1, "sent", None)]
    assert client.jobs == ["done"]
    assert "경고: 첫 시도에 Enter 로 방이 열리지 않음" in caplog.text
    assert [d["kind"] for d in client.diags] == ["send_warning"]
