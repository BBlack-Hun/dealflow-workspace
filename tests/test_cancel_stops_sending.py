"""[중단]을 누르면 카톡이 **실제로** 멈추는가.

## 왜 이 파일이 있나

[중단]은 서버 DB 만 바꿨다 — 잡을 canceled 로, 대기 건을 canceled 로. 그런데
발송 프로그램은 폴링할 때 명단을 통째로 받아 메모리에 들고 끝까지 돌았고,
중간에 서버에 다시 묻지 않았다. 그래서 [중단]을 눌러도 카톡은 계속 나갔다.
서버가 결과 보고만 거부해 **기록에 안 남았을 뿐 받는 쪽은 그대로 받았다.**
사람은 [중단]을 '발송이 멈춘다' 로 읽는다.

**상태값만 보는 테스트로는 이 버그를 못 잡는다.** 그때도 잡은 canceled 로 잘
바뀌고 있었다. 그래서 여기서는 가짜 발송기가 **몇 번 불렸는지**를 센다.

## 어떻게 재현하나

가짜 서버를 세우지 않는다. 진짜 `AgentClient` 의 통신만 FastAPI TestClient 로
바꿔서, 발송 프로그램 코드와 서버 코드가 **실제로 맞물려** 돌게 한다. 취소도
DB 를 직접 고치지 않고 화면의 버튼과 같은 경로(`POST /api/jobs/{id}/cancel`)를
부른다 — 어느 한쪽만 고쳐도 여기서 걸린다.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
import requests

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# 사람 흉내 간격은 테스트에서 0 으로. 재시도 간격도 0 이라야 몇 초를 안 버린다.
FAST = {
    "delay_min_sec": 0, "delay_max_sec": 0, "part_gap_sec": 0, "job_cap": 60,
    "verify_delay_min_sec": 0, "verify_delay_max_sec": 0,
    "cancel_check_retries": 3, "cancel_check_backoff_sec": 0,
}


@pytest.fixture()
def agent_main():
    return importlib.import_module("agent.main")


class FakeResult:
    def __init__(self, ok=True, error=None):
        self.ok = ok
        self.error = error
        self.screenshot_b64 = None


class CountingSender:
    """보낸 방을 순서대로 적어 두는 가짜 카톡."""

    name = "test"

    def __init__(self):
        self.sent = []

    def send_text(self, room, _text):
        self.sent.append(room)
        return FakeResult()


class StopWhileSending(CountingSender):
    """N번째 건을 보내는 **순간** 사용자가 [중단]을 누른 상황을 만든다.

    화면의 버튼과 같은 경로를 부른다 — DB 를 직접 고치면 실제 버튼이 하는
    일과 어긋나도 모른다.
    """

    def __init__(self, http, job_id, stop_at):
        super().__init__()
        self.http = http
        self.job_id = job_id
        self.stop_at = stop_at

    def send_text(self, room, text):
        result = super().send_text(room, text)
        if len(self.sent) == self.stop_at:
            self.http.post(f"/api/jobs/{self.job_id}/cancel")
        return result


class StopWhileVerifying:
    """방 이름 대조 잡용. 전송은 안 하지만 오래 돌아서 멈추고 싶을 수 있다."""

    name = "test"

    def __init__(self, http, job_id, stop_at):
        self.http = http
        self.job_id = job_id
        self.stop_at = stop_at
        self.looked = []

    def verify_room(self, room):
        self.looked.append(room)
        if len(self.looked) == self.stop_at:
            self.http.post(f"/api/jobs/{self.job_id}/cancel")
        return "verified"


class DeafClient:
    """서버에 못 묻는 상태(네트워크 끊김·서버 재배포)."""

    def __init__(self):
        self.asked = 0
        self.reported = []
        self.items = []

    def job_state(self, _job_id):
        self.asked += 1
        raise requests.RequestException("서버에 닿지 않습니다")

    def report_item(self, item_id, status, **_kw):
        self.items.append((item_id, status))

    def report_job(self, _job_id, status):
        self.reported.append(status)

    def report_diagnostics(self, _payload):
        pass


class NosyClient(DeafClient):
    """몇 번 물어봤는지 세는 클라이언트. 항상 '계속 보내도 된다' 로 답한다."""

    def job_state(self, _job_id):
        self.asked += 1
        return {"ok": True, "status": "running", "canceled": False, "canceled_items": []}


def agent_for(http, token):
    """진짜 `AgentClient` — 통신만 TestClient 로 바꾼다."""
    from agent.main import AgentClient

    ac = AgentClient({"server_url": "", "token": token})
    http.headers.update({"Authorization": f"Bearer {token}"})
    ac.session = http
    return ac


def make_job(db, user, kind="deal_intro", count=5):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user.id, kind=kind, status="queued",
                  total=count, sent=0, failed=0)
    db.add(job)
    db.flush()
    for n in range(1, count + 1):
        db.add(SendItem(job_id=job.id, room_name=f"테스트방 {n}",
                        message=f"문구 {n}", status="pending"))
    db.commit()
    return job.id


def login(http):
    http.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})


def statuses(db, job_id):
    from app.models import SendItem, SendJob

    db.expire_all()   # 서버는 다른 세션으로 커밋했다 — 캐시를 버리고 다시 읽는다
    job = db.get(SendJob, job_id)
    items = db.query(SendItem).filter_by(job_id=job_id).order_by(SendItem.id).all()
    return job.status, [i.status for i in items]


# --- 핵심: 취소 뒤에 **몇 건이 실제로 나갔는가** ------------------------------

def test_hitting_stop_mid_job_stops_the_kakao(client, db, users, agent_main):
    """5건짜리 회차에서 2번째를 보내는 중에 [중단] — 3·4·5번은 나가면 안 된다."""
    job_id = make_job(db, users["u1"], count=5)
    login(client)
    ac = agent_for(client, DEMO_TOKEN)

    job = ac.poll()
    assert job and job["job_id"] == job_id

    sender = StopWhileSending(client, job_id, stop_at=2)
    agent_main.process_job(ac, sender, job, FAST)

    assert len(sender.sent) == 2, (
        f"[중단] 뒤에도 카톡이 나갔다 — 실제 전송 {len(sender.sent)}건: {sender.sent}")
    assert sender.sent == ["테스트방 1", "테스트방 2"]

    job_status, item_statuses = statuses(db, job_id)
    assert job_status == "canceled"
    # 3~5번은 아예 보내지 않았고 서버에서도 취소로 남는다.
    assert item_statuses[2:] == ["canceled", "canceled", "canceled"]


def test_stopping_before_the_first_one_sends_nothing(client, db, users, agent_main):
    """폴링과 첫 발송 사이에도 [중단]을 누를 수 있다 — 첫 건 앞에서도 확인한다."""
    job_id = make_job(db, users["u1"], count=3)
    login(client)
    ac = agent_for(client, DEMO_TOKEN)

    job = ac.poll()
    client.post(f"/api/jobs/{job_id}/cancel")   # 잡을 물자마자 중단

    sender = CountingSender()
    agent_main.process_job(ac, sender, job, FAST)

    assert sender.sent == [], f"한 건도 나가면 안 된다: {sender.sent}"


def test_a_job_nobody_stopped_still_sends_everything(client, db, users, agent_main):
    """확인을 넣었다고 멀쩡한 회차가 덜 나가면 더 나쁘다."""
    job_id = make_job(db, users["u1"], count=4)
    login(client)
    ac = agent_for(client, DEMO_TOKEN)

    job = ac.poll()
    sender = CountingSender()
    agent_main.process_job(ac, sender, job, FAST)

    assert len(sender.sent) == 4
    job_status, item_statuses = statuses(db, job_id)
    assert job_status == "done"
    assert item_statuses == ["sent"] * 4


def test_it_asks_before_every_single_one(agent_main):
    """한 번 묻고 나머지를 몰아 보내면 지금 고치는 문제가 그대로다."""
    nosy = NosyClient()
    sender = CountingSender()
    job = {"job_id": 7, "kind": "deal_intro",
           "items": [{"id": n, "room_name": f"방{n}", "message": "문구"}
                     for n in (1, 2, 3)]}

    agent_main.process_job(nosy, sender, job, FAST)

    assert len(sender.sent) == 3
    assert nosy.asked == 3, f"3건을 보내며 {nosy.asked}번만 물어봤다"


# --- 서버에 못 물어보는 경우 ---------------------------------------------------

def test_it_does_not_send_when_it_cannot_ask(agent_main):
    """서버에 못 묻는 채로 계속 보내면 [중단]이 또 안 듣는다 — 보내지 않는다."""
    deaf = DeafClient()
    sender = CountingSender()
    job = {"job_id": 9, "kind": "deal_intro",
           "items": [{"id": n, "room_name": f"방{n}", "message": "문구"}
                     for n in (1, 2, 3)]}

    agent_main.process_job(deaf, sender, job, FAST)

    assert sender.sent == [], f"서버에 못 물어보는데 보냈다: {sender.sent}"
    assert deaf.reported == ["paused"], "멈춘 사실을 서버에 알리지 않았다"


def test_it_retries_a_few_times_before_giving_up(agent_main):
    """서버 재배포 같은 몇 초짜리 끊김에 회차가 통째로 죽으면 못 쓴다."""
    deaf = DeafClient()
    gate = agent_main.check_before_send(deaf, 1, FAST)

    assert not gate.go
    assert gate.reason == "unreachable"
    assert deaf.asked == FAST["cancel_check_retries"], (
        f"한 번만 물어보고 포기했다 (asked={deaf.asked})")


def test_the_retry_count_is_configurable(agent_main):
    """발송 속도 관련 숫자는 config 에서 온다 (ROADMAP 공통 원칙 2)."""
    assert agent_main.DEFAULT_CONFIG["cancel_check_retries"] >= 2
    assert agent_main.DEFAULT_CONFIG["cancel_check_backoff_sec"] > 0


# --- 건 하나만 취소된 경우 -----------------------------------------------------

def test_one_canceled_item_is_skipped_but_the_rest_go(client, db, users, agent_main):
    """잡은 살아 있고 특정 건만 취소된 경우. 그 건만 건너뛰고 나머지는 보낸다."""
    from app.models import SendItem

    job_id = make_job(db, users["u1"], count=4)
    ac = agent_for(client, DEMO_TOKEN)
    job = ac.poll()

    # 폴링 뒤에 3번 건만 취소된 상황(건 단위 취소 화면이 생겨도 여기서 걸린다).
    third = db.query(SendItem).filter_by(job_id=job_id).order_by(SendItem.id).all()[2]
    third.status = "canceled"
    db.commit()

    sender = CountingSender()
    agent_main.process_job(ac, sender, job, FAST)

    assert sender.sent == ["테스트방 1", "테스트방 2", "테스트방 4"], sender.sent


# --- 방 이름 대조 잡 -----------------------------------------------------------

def test_stopping_a_verify_job_stops_the_searching(client, db, users, agent_main):
    """전송은 없지만 오래 돌아서 멈추고 싶을 수 있다."""
    job_id = make_job(db, users["u1"], kind="verify_room", count=5)
    login(client)
    ac = agent_for(client, DEMO_TOKEN)

    job = ac.poll()
    assert job["kind"] == "verify_room"

    sender = StopWhileVerifying(client, job_id, stop_at=2)
    agent_main.process_verify_job(ac, sender, job, FAST)

    assert len(sender.looked) == 2, (
        f"[중단] 뒤에도 계속 찾았다 — {len(sender.looked)}건: {sender.looked}")
    assert statuses(db, job_id)[0] == "canceled"


# --- 서버 경로의 규약 ----------------------------------------------------------

def test_the_state_endpoint_says_stop_after_cancel(client, db, users):
    job_id = make_job(db, users["u1"], count=3)
    login(client)
    ac = agent_for(client, DEMO_TOKEN)
    ac.poll()

    assert ac.job_state(job_id)["canceled"] is False

    client.post(f"/api/jobs/{job_id}/cancel")
    state = ac.job_state(job_id)

    assert state["canceled"] is True
    assert state["status"] == "canceled"
    assert len(state["canceled_items"]) == 3


def test_a_finished_job_is_not_sent_again(client, db, users):
    """이미 끝난 것으로 표시된 잡을 계속 보내면 같은 사람에게 두 번 나간다."""
    from app.models import SendJob

    job_id = make_job(db, users["u1"], count=2)
    ac = agent_for(client, DEMO_TOKEN)
    db.get(SendJob, job_id).status = "done"
    db.commit()

    assert ac.job_state(job_id)["canceled"] is True


def test_it_says_stop_about_someone_elses_job(client, db, users):
    """모르는 잡은 '멈춰라' 로 답한다 — 모르면 안 보내는 쪽이 안전하다."""
    job_id = make_job(db, users["u1"], count=1)
    other = agent_for(client, OTHER_TOKEN)

    state = other.job_state(job_id)
    assert state["ok"] is False
    assert state["canceled"] is True

    missing = other.job_state(999999)
    assert missing["canceled"] is True


def test_asking_needs_the_agent_token(client, db, users):
    """`/api/agent/*` 는 전부 에이전트 토큰이 있어야 한다."""
    job_id = make_job(db, users["u1"], count=1)
    client.headers.pop("Authorization", None)

    r = client.get(f"/api/agent/jobs/{job_id}/state")
    assert r.status_code in (401, 403), r.status_code


def test_asking_keeps_the_connection_badge_fresh(client, db, users):
    """확인도 에이전트가 살아 있다는 신호다 — poll 처럼 last_poll_at 을 갱신한다."""
    from app.models import AgentDevice

    job_id = make_job(db, users["u1"], count=1)
    device = db.query(AgentDevice).filter_by(user_id=users["u1"].id).first()
    device.last_poll_at = None
    db.commit()

    agent_for(client, DEMO_TOKEN).job_state(job_id)

    db.expire_all()
    assert db.query(AgentDevice).filter_by(user_id=users["u1"].id).first().last_poll_at
