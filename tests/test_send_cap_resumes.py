"""상한(job_cap)에 걸린 나머지가 **버려지지 않는가**.

## 왜 이 파일이 있나

97명짜리 딜소개 회차에서 60명에게만 나갔는데 회차는 '완료' 로 끝났다. 나머지
37명은 `pending` 인 채로 남았고, 화면이 끝났다고 하니 안 나간 것을 사람이
알아챌 방법이 없었다.

두 가지가 겹쳤다.

1. 서버가 97건을 통째로 내주는데 발송 프로그램은 앞 60건만 처리했다(계정 보호
   상한). 잘라낸 37건은 **그냥 버려졌다**.
2. 그러고도 잡 **전체**를 `done` 으로 보고했고, 서버는 대기 건이 남았는지 보지
   않고 그대로 받아 적었다.

**상태값만 보는 테스트로는 이 버그를 못 잡는다.** 그때도 잡은 `done` 으로 잘
바뀌고 있었다. 그래서 여기서는 가짜 카톡이 **몇 번 불렸는지**를 센다.

## 무엇을 지키나

- 97건은 여러 회분에 나뉘더라도 **결국 97건 다** 나간다. 그리고 **같은 사람에게
  두 번 가지 않는다**.
- 대기 건이 남았는데 완료로 보고하면 서버가 받아 주지 않는다 — 각자 PC 의 발송
  프로그램은 한동안 구버전이 섞여 도니까, 서버에서 막아야 **갱신하지 않은
  사람에게도** 이 버그가 사라진다.
- 그렇다고 무한히 되돌리지는 않는다. 진행이 없으면 멈춘다.
"""
from __future__ import annotations

import importlib
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def agent_main():
    return importlib.import_module("agent.main")


def fast(cap: int) -> dict:
    """사람 흉내 간격은 테스트에서 0 으로 — 상한 말고는 실제 설정 그대로."""
    return {"delay_min_sec": 0, "delay_max_sec": 0, "part_gap_sec": 0,
            "verify_delay_min_sec": 0, "verify_delay_max_sec": 0,
            "cancel_check_retries": 3, "cancel_check_backoff_sec": 0,
            "job_cap": cap}


class FakeResult:
    def __init__(self, ok=True, error=None):
        self.ok = ok
        self.error = error
        self.screenshot_b64 = None


class CountingSender:
    """보낸 방을 순서대로 적어 두는 가짜 카톡. **여기 적힌 수가 실제 발송 수다.**"""

    name = "test"

    def __init__(self):
        self.sent = []

    def send_text(self, room, _text):
        self.sent.append(room)
        return FakeResult()


class RecordingClient:
    """서버 대신 보고만 받아 적는 가짜. 항상 '계속 보내도 된다' 로 답한다."""

    def __init__(self):
        self.items = []
        self.reported = []

    def job_state(self, _job_id):
        return {"ok": True, "status": "running", "canceled": False, "canceled_items": []}

    def report_item(self, item_id, status, **_kw):
        self.items.append((item_id, status))

    def report_job(self, _job_id, status):
        self.reported.append(status)

    def report_diagnostics(self, _payload):
        pass


class OldAgent:
    """0.3.0 흉내 — 팀원들 PC 에서 지금도 도는 버전.

    - 폴링할 때 상한을 알리지 않는다 (`cap` 을 모른다)
    - 받은 명단에서 **앞 60건만** 처리하고 나머지는 버린다
    - 그러고도 잡 **전체**를 `done` 으로 보고한다

    지금 에이전트 코드를 부르지 않고 HTTP 로만 움직이는 것이 핵심이다. 고친
    코드를 재사용하면 "**에이전트를 고치지 않아도** 해결되는가" 라는 질문에
    답을 못 한다.
    """

    def __init__(self, http, token, cap=60):
        self.http = http
        self.headers = auth(token)
        self.cap = cap
        self.sent = []          # 실제로 손댄 방 이름 (= 나간 건수)

    def poll(self):
        r = self.http.get("/api/agent/poll", params={"kinds": "deal_intro"},
                          headers=self.headers)
        return None if r.status_code == 204 else r.json()

    def work(self, job, upto=None):
        """받은 명단을 처리한다. `upto` 로 '아무것도 못 한 회분' 도 만들 수 있다."""
        limit = self.cap if upto is None else upto
        for item in job["items"][:limit]:
            self.sent.append(item["room_name"])
            self.http.post(f"/api/agent/items/{item['id']}/result",
                           json={"status": "sent"}, headers=self.headers)
        return self.report_job(job["job_id"], "done")

    def report_job(self, job_id, status):
        return self.http.post(f"/api/agent/jobs/{job_id}/status",
                              json={"status": status}, headers=self.headers).json()


def agent_for(http, token, cap=None):
    """진짜 `AgentClient` — 통신만 TestClient 로 바꾼다."""
    from agent.main import AgentClient

    cfg = {"server_url": "", "token": token}
    if cap is not None:
        cfg["job_cap"] = cap
    ac = AgentClient(cfg)
    http.headers.update({"Authorization": f"Bearer {token}"})
    ac.session = http
    return ac


def login(http):
    http.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return http


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


def statuses(db, job_id):
    from app.models import SendItem, SendJob

    db.expire_all()   # 서버는 다른 세션으로 커밋했다 — 캐시를 버리고 다시 읽는다
    job = db.get(SendJob, job_id)
    items = db.query(SendItem).filter_by(job_id=job_id).order_by(SendItem.id).all()
    return job.status, [i.status for i in items]


def run_until_idle(ac, sender, agent_main, cfg, max_cycles=8):
    """실제 루프와 같은 순서로 돈다 — 폴링 → 처리 → 다시 폴링.

    `max_cycles` 는 **무한 반복을 테스트가 붙잡기 위한 것**이다. 진행이 없는데도
    서버가 계속 큐로 되돌리면 여기서 걸린다(운영에서는 폴링 간격만큼 영원히 돈다).
    """
    cycles = 0
    while True:
        job = ac.poll()
        if job is None:
            return cycles
        cycles += 1
        assert cycles <= max_cycles, f"잡이 {max_cycles}회분을 넘겨 계속 돌아온다 (무한 반복)"
        agent_main.process_job(ac, sender, job, cfg)


@pytest.fixture()
def ticking_clock(monkeypatch):
    """부를 때마다 1초씩 가는 시계.

    잡을 다시 물었는지(`started_at`)와 건을 손댔는지(`updated_at`)를 견줘 진행
    여부를 판정하는데, 저장하는 시각이 **초 단위**라 테스트가 한 초 안에 여러
    회분을 돌면 판정이 흐려진다. 실제로는 회분 사이에 폴링 간격(기본 3초)이
    있으므로, 시간이 흐르는 상황을 그대로 만들어 준다.

    `app/clock.py: now` 하나만 바꾸면 서버·모델이 함께 따라온다 — 시각을 적는
    자리가 거기 하나뿐이라서 그렇다.
    """
    from app import clock

    state = {"t": clock.now()}

    def fake_now():
        state["t"] += timedelta(seconds=1)
        return state["t"]

    monkeypatch.setattr(clock, "now", fake_now)
    return state


# --- 핵심: 97명이 **실제로** 97명에게 나가는가 ---------------------------------

def test_a_97_person_batch_actually_reaches_all_97(client, db, users, agent_main):
    """상한이 60이라 한 번에 다 못 보낸다 — 그래도 결국 97건이 나가야 한다.

    상태값이 아니라 **가짜 카톡이 몇 번 불렸는지**를 센다. 버그가 있던 때에도
    잡은 `done` 으로 잘 바뀌고 있었다.
    """
    job_id = make_job(db, users["u1"], count=97)
    ac = agent_for(client, DEMO_TOKEN, cap=60)
    sender = CountingSender()

    cycles = run_until_idle(ac, sender, agent_main, fast(60))

    assert len(sender.sent) == 97, (
        f"97명 중 {len(sender.sent)}명에게만 나갔다 — 나머지가 버려졌다")
    assert len(set(sender.sent)) == 97, "같은 사람에게 두 번 나갔다"
    assert cycles == 2, f"60건씩이면 두 회분이어야 한다 (실제 {cycles}회분)"

    job_status, item_statuses = statuses(db, job_id)
    assert job_status == "done"
    assert item_statuses == ["sent"] * 97


def test_the_job_is_not_done_while_people_are_still_waiting(client, db, users, agent_main):
    """첫 회분이 끝난 시점에 회차가 '완료' 로 보이면 안 된다.

    화면이 끝났다고 하면 안 나간 37명을 아무도 찾아보지 않는다.
    """
    job_id = make_job(db, users["u1"], count=97)
    ac = agent_for(client, DEMO_TOKEN, cap=60)
    sender = CountingSender()

    agent_main.process_job(ac, sender, ac.poll(), fast(60))   # 첫 회분만

    body = login(client).get(f"/api/jobs/{job_id}").json()

    assert body["status"] == "queued", f"대기 37명을 두고 {body['status']} 로 끝났다"
    assert body["counts"] == {"pending": 37, "sending": 0, "sent": 60,
                              "failed": 0, "canceled": 0}
    assert body["finished_at"] is None, "안 끝난 회차에 끝난 시각이 적혔다"


# --- 구버전(0.3.0) 에이전트에서도 해결되는가 -----------------------------------

def test_an_old_agent_that_lies_about_done_is_not_believed(client, db, users):
    """대기 건이 남았는데 완료로 보고하면 서버가 거부한다.

    팀원들 PC 에는 아직 0.3.0 이 돈다. 서버가 막아야 **에이전트를 갱신하지
    않아도** 사람이 빠지지 않는다.
    """
    job_id = make_job(db, users["u1"], count=97)
    old = OldAgent(client, DEMO_TOKEN, cap=60)

    job = old.poll()
    assert len(job["items"]) == 97, "상한을 모르는 구버전에게는 지금처럼 전부 준다"

    answer = old.work(job)      # 앞 60건만 처리하고 done 으로 보고

    assert answer["status"] == "queued", (
        f"대기 건이 남았는데 {answer['status']} 로 받아 줬다")
    assert answer["pending"] == 37


def test_an_old_agent_finishes_all_97_over_two_rounds(client, db, users):
    """구버전이라도 남은 37명이 **다음 폴링에서 이어 나간다.**"""
    job_id = make_job(db, users["u1"], count=97)
    old = OldAgent(client, DEMO_TOKEN, cap=60)

    rounds = 0
    while True:
        job = old.poll()
        if job is None:
            break
        rounds += 1
        assert rounds <= 5, "잡이 계속 돌아온다 (무한 반복)"
        old.work(job)

    assert len(old.sent) == 97, f"97명 중 {len(old.sent)}명에게만 나갔다"
    assert len(set(old.sent)) == 97, "같은 사람에게 두 번 나갔다"
    assert rounds == 2

    job_status, item_statuses = statuses(db, job_id)
    assert job_status == "done"
    assert item_statuses == ["sent"] * 97


def test_the_second_round_hands_out_only_what_is_left(client, db, users):
    """이어 보낼 때 이미 받은 60명이 다시 나오면 두 번 나간다."""
    job_id = make_job(db, users["u1"], count=97)
    old = OldAgent(client, DEMO_TOKEN, cap=60)

    first = old.poll()
    old.work(first)
    second = old.poll()

    assert len(second["items"]) == 37
    assert not ({i["id"] for i in second["items"]} & {i["id"] for i in first["items"][:60]})


# --- 무한 반복을 막는가 --------------------------------------------------------

def test_a_round_that_did_nothing_stops_the_job(client, db, users):
    """아무것도 못 보내는 상태에서 계속 되돌리면 영원히 돈다 — 멈춰야 한다."""
    job_id = make_job(db, users["u1"], count=5)
    old = OldAgent(client, DEMO_TOKEN)

    job = old.poll()
    assert len(job["items"]) == 5
    answer = old.work(job, upto=0)      # 한 건도 손대지 않고 done 으로 보고

    assert answer["status"] == "paused", (
        f"진행이 없는데 {answer['status']} 로 되돌렸다 (무한 반복)")
    assert old.poll() is None, "멈춘 잡을 다시 집어갔다 (무한 반복)"


def test_it_stops_after_a_round_that_could_not_move(client, db, users, ticking_clock):
    """첫 회분은 나갔는데 그 다음 회분이 한 건도 못 보내는 경우.

    '한 번이라도 나간 적 있으면 되돌린다' 로 판정하면 여기서 영원히 돈다.
    **이번 회분이** 일을 했는지를 봐야 한다.
    """
    job_id = make_job(db, users["u1"], count=97)
    old = OldAgent(client, DEMO_TOKEN, cap=60)

    assert old.work(old.poll())["status"] == "queued"        # 60건 나감 → 이어서
    stuck = old.work(old.poll(), upto=0)                     # 37건을 그냥 흘림

    assert stuck["status"] == "paused", (
        f"진행이 없는 회분 뒤에도 {stuck['status']} 로 되돌렸다 (무한 반복)")
    assert old.poll() is None, "멈춘 잡을 다시 집어갔다 (무한 반복)"

    # 멈춘 회차에도 나간 60명은 그대로 남는다 — 다시 보내면 두 번 간다.
    assert statuses(db, job_id)[1].count("sent") == 60


def test_a_canceled_job_stays_canceled(client, db, users):
    """[중단]을 누른 회차를 되돌리면 멈춘 발송이 다시 나간다."""
    job_id = make_job(db, users["u1"], count=97)
    old = OldAgent(client, DEMO_TOKEN, cap=60)
    job = old.poll()

    login(client)
    client.post(f"/api/jobs/{job_id}/cancel")
    old.report_job(job_id, "done")

    assert statuses(db, job_id)[0] == "canceled"
    assert old.poll() is None


# --- 상한값이 한 곳에만 있는가 -------------------------------------------------

def test_the_server_hands_out_only_as_many_as_the_agent_asked_for(client, db, users):
    """서버가 상한만큼만 내주면 에이전트가 버릴 것이 애초에 없다."""
    make_job(db, users["u1"], count=97)

    r = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                   headers=auth(DEMO_TOKEN))

    assert len(r.json()["items"]) == 60


def test_the_cap_number_lives_only_in_the_agent(client, db, users):
    """서버가 자기 상한을 따로 들고 있으면 두 숫자가 또 어긋난다.

    서버는 **에이전트가 말한 만큼만** 자른다. 말하지 않으면 자르지 않는다
    (구버전이 그렇다 — 남은 건은 `_settle` 이 다시 큐로 돌린다).
    """
    make_job(db, users["u1"], count=97)

    r = client.get("/api/agent/poll", params={"kinds": "deal_intro"},
                   headers=auth(DEMO_TOKEN))

    assert len(r.json()["items"]) == 97


def test_the_agent_takes_the_cap_from_its_own_config(agent_main):
    """발송 속도 관련 숫자는 config 에서 온다 (ROADMAP 공통 원칙 2)."""
    assert agent_main.job_cap({}) == agent_main.DEFAULT_CONFIG["job_cap"]
    assert agent_main.job_cap({"job_cap": 12}) == 12


def test_the_agent_tells_the_server_its_cap(client, db, users):
    """알리지 않으면 서버가 지킬 수가 없다 — 실제 요청에 실려 나가는지 본다."""
    make_job(db, users["u1"], count=97)
    ac = agent_for(client, DEMO_TOKEN, cap=12)

    assert len(ac.poll()["items"]) == 12


# --- 에이전트도 거짓으로 끝났다고 하지 않는가 ----------------------------------

def test_the_agent_does_not_claim_done_when_the_cap_cut_the_list(agent_main):
    """낡은 서버는 상한을 모르고 통째로 내준다. 그때도 완료라고 하면 안 된다.

    서버가 막아 주더라도, 에이전트가 거짓으로 보고하는 상태를 남겨 두지 않는다.
    """
    fake = RecordingClient()
    sender = CountingSender()
    job = {"job_id": 7, "kind": "deal_intro",
           "items": [{"id": n, "room_name": f"방{n}", "message": "문구"}
                     for n in range(1, 98)]}

    agent_main.process_job(fake, sender, job, fast(60))

    assert len(sender.sent) == 60, "상한을 넘겨 보냈다 (계정 보호)"
    assert fake.reported == ["queued"], (
        f"{fake.reported} — 손도 안 댄 37건을 두고 끝났다고 보고했다")


def test_the_agent_still_says_done_when_nothing_is_left(agent_main):
    """상한에 안 걸리는 보통 회차까지 안 끝난 것으로 만들면 더 나쁘다."""
    fake = RecordingClient()
    sender = CountingSender()
    job = {"job_id": 8, "kind": "deal_intro",
           "items": [{"id": n, "room_name": f"방{n}", "message": "문구"}
                     for n in range(1, 5)]}

    agent_main.process_job(fake, sender, job, fast(60))

    assert len(sender.sent) == 4
    assert fake.reported == ["done"]


# --- 끝난 회차의 성공/실패 표시 ------------------------------------------------

def test_a_failure_in_an_earlier_round_is_not_forgotten(client, db, users):
    """여러 회분에 나뉘면 마지막 회분만 성공해도 에이전트는 done 이라고 한다.

    그러면 앞 회분의 실패가 화면에서 사라져 [실패 재시도] 가 안 뜬다. 끝난
    회차의 성공·실패는 **건들을 보고** 정해야 한다.
    """
    job_id = make_job(db, users["u1"], count=97)
    old = OldAgent(client, DEMO_TOKEN, cap=60)

    job = old.poll()
    first = job["items"][0]
    client.post(f"/api/agent/items/{first['id']}/result",
                json={"status": "failed", "error": "방을 찾지 못했습니다"},
                headers=auth(DEMO_TOKEN))
    for item in job["items"][1:60]:
        client.post(f"/api/agent/items/{item['id']}/result",
                    json={"status": "sent"}, headers=auth(DEMO_TOKEN))
    old.report_job(job_id, "done")

    old.work(old.poll())        # 남은 37건은 전부 성공 → 에이전트는 done 이라고 한다

    assert statuses(db, job_id)[0] == "done_with_errors"


# --- 이미 그렇게 끝난 회차를 구제하는 길 ([이어 보내기]) -----------------------
#
# 위 수정은 **앞으로** 이런 회차가 생기지 않게 한다. 하지만 이미 `done` 으로 끝나
# 버린 회차(운영 13회차: 97건 중 sent 60 · pending 37)는 저절로 살아나지 않는다.
# [실패 재시도]는 `failed` 만, [취소분 재발송]은 `canceled` 만 고르므로 대기 건은
# 어느 쪽에도 안 걸린다 — 사람이 손쓸 방법이 하나도 없었다.

def finished_job_with_leftovers(db, user, sent=60, pending=37, channel="kakao"):
    """운영 13회차와 같은 모양 — 완료로 끝났는데 대기가 남아 있는 회차."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=user.id, kind="deal_intro", status="done",
                  total=sent + pending, sent=sent, failed=0,
                  finished_at="2026-08-19T10:00:00+09:00")
    db.add(job)
    db.flush()
    for n in range(1, sent + pending + 1):
        done = n <= sent
        db.add(SendItem(job_id=job.id, channel=channel,
                        room_name=(f"받는사람{n}@example.com" if channel == "email"
                                   else f"테스트방 {n}"),
                        subject="딜 소개" if channel == "email" else None,
                        message=f"문구 {n}", status="sent" if done else "pending",
                        sent_at="2026-08-19T10:00:00+09:00" if done else None))
    db.commit()
    return job.id


def test_the_leftovers_of_a_finished_job_can_still_go_out(client, db, users, agent_main):
    """13회차 구제 — 대기 37명에게만 나가고, 이미 받은 60명에게는 안 나간다.

    여기서도 상태값이 아니라 **가짜 카톡이 몇 번 불렸는지**를 센다.
    """
    job_id = finished_job_with_leftovers(db, users["u1"])

    answer = login(client).post(f"/api/jobs/{job_id}/resume").json()
    assert answer == {"status": "queued", "requeued": 37}

    ac = agent_for(client, DEMO_TOKEN, cap=60)
    sender = CountingSender()
    run_until_idle(ac, sender, agent_main, fast(60))

    assert len(sender.sent) == 37, f"대기 37명이 아니라 {len(sender.sent)}명에게 나갔다"
    assert set(sender.sent) == {f"테스트방 {n}" for n in range(61, 98)}, (
        "이미 받은 사람에게 다시 나갔다")

    job_status, item_statuses = statuses(db, job_id)
    assert job_status == "done"
    assert item_statuses == ["sent"] * 97


def test_resuming_never_touches_someone_who_already_got_it(client, db, users):
    """이 파일에서 가장 위험한 부분 — 발송은 되돌릴 수 없다."""
    from app.models import SendItem

    job_id = finished_job_with_leftovers(db, users["u1"], sent=3, pending=2)

    login(client).post(f"/api/jobs/{job_id}/resume")

    db.expire_all()
    rows = db.query(SendItem).filter_by(job_id=job_id).order_by(SendItem.id).all()
    assert [i.status for i in rows] == ["sent", "sent", "sent", "pending", "pending"]
    assert all(i.sent_at for i in rows[:3]), "이미 나간 건의 발송 시각이 지워졌다"


def test_resuming_a_job_with_nothing_waiting_is_refused(client, db, users):
    """아무 일도 안 일어났는데 성공으로 보이면 안 된다."""
    job_id = finished_job_with_leftovers(db, users["u1"], sent=3, pending=0)

    r = login(client).post(f"/api/jobs/{job_id}/resume")

    assert r.status_code == 400
    assert "대기" in r.json()["detail"]


def test_the_screen_can_show_how_many_will_go_before_the_click(client, db, users):
    """발송은 되돌릴 수 없다 — 누르기 **전에** 몇 명인지 보여야 한다."""
    job_id = finished_job_with_leftovers(db, users["u1"])

    body = login(client).get(f"/api/jobs/{job_id}").json()

    assert body["counts"]["pending"] == 37   # 버튼 문구에 그대로 쓸 수 있다


def test_a_resumed_job_is_actually_picked_up_by_the_agent(client, db, users):
    """되살려 놓고 집어가지 않으면 대기인 채로 그대로다."""
    job_id = finished_job_with_leftovers(db, users["u1"])
    login(client).post(f"/api/jobs/{job_id}/resume")

    r = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                   headers=auth(DEMO_TOKEN))

    assert r.status_code == 200
    assert r.json()["job_id"] == job_id
    assert len(r.json()["items"]) == 37


def test_resuming_mail_items_wakes_the_server_not_the_agent(client, db, users, monkeypatch):
    """메일은 서버가 보낸다 — 되살리기만 하고 아무도 안 보내면 영원히 대기다."""
    woken = []
    monkeypatch.setattr("app.routers.jobs.mail_sender.send_job",
                        lambda job_id, *a, **kw: woken.append(job_id))
    job_id = finished_job_with_leftovers(db, users["u1"], sent=1, pending=2,
                                         channel="email")

    login(client).post(f"/api/jobs/{job_id}/resume")

    assert woken == [job_id], "메일 건을 되살려 놓고 서버가 보내지 않았다"
    # 메일 건은 발송 프로그램이 집어가면 방을 찾다가 실패한다.
    r = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                   headers=auth(DEMO_TOKEN))
    assert r.json()["items"] == []


def test_resuming_a_mixed_job_moves_both_channels(client, db, users, monkeypatch):
    """카톡과 메일이 한 회차에 섞여 있으면 **둘 다** 제 길로 가야 한다."""
    from app.models import SendItem, SendJob

    woken = []
    monkeypatch.setattr("app.routers.jobs.mail_sender.send_job",
                        lambda job_id, *a, **kw: woken.append(job_id))

    job = SendJob(user_id=users["u1"].id, kind="deal_intro", status="done",
                  total=3, sent=1, failed=0, finished_at="2026-08-19T10:00:00+09:00")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, channel="kakao", room_name="테스트방 1",
                    message="문구", status="sent", sent_at="2026-08-19T10:00:00+09:00"))
    db.add(SendItem(job_id=job.id, channel="kakao", room_name="테스트방 2",
                    message="문구", status="pending"))
    db.add(SendItem(job_id=job.id, channel="email", room_name="받는사람@example.com",
                    subject="딜 소개", message="문구", status="pending"))
    db.commit()

    answer = login(client).post(f"/api/jobs/{job.id}/resume").json()

    assert answer["requeued"] == 2
    assert woken == [job.id]
    r = client.get("/api/agent/poll", params={"kinds": "deal_intro", "cap": 60},
                   headers=auth(DEMO_TOKEN))
    assert [i["room_name"] for i in r.json()["items"]] == ["테스트방 2"]


def test_resuming_someone_elses_job_is_refused(client, db, users):
    """조회는 관리자에게도 열려 있지만 **조작**은 주인만 한다."""
    job_id = finished_job_with_leftovers(db, users["u2"])

    r = login(client).post(f"/api/jobs/{job_id}/resume")

    assert r.status_code == 404
