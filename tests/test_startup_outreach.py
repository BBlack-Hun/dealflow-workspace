"""스타트업 안내 카톡 — **각자 맡은 스타트업에, 확인된 방으로, 고른 문구 하나.**

사용자 요청: "스타트업 카톡 매칭이랑 계약을 위해 보내야 할 카톡들이 있는데
이것도 딜소개처럼 보낼 수 있으면 좋을거 같아" — 그리고 "월간 발송 말고, 각자가
관리하고 있는 스타트업이 있는데 거기서 나갈 예정이야".

## 여기서 못박는 것

1. **누구에게** — 내 [스타트업] 명단 줄 중 카톡에서 **확인된 방**이 있는 곳만.
   `딜소개 불가`·`검토중단`·감춘 줄·남의 줄·투자사 줄은 고를 수도, 주소로
   찔러 넣을 수도 없다.
2. **무엇을** — 채움말(`{대표명}`·`{회사명}`·`{보내는사람}`)이 채워진 글.
   성함이 비면 그 자리를 빼고 `안녕하세요 대표님.` 으로 읽힌다(빈칸 두 개 없이).
3. **같은 문구를 N일 안에 또 보내지 않는다** — 기본 30일. 다른 팀원 명단의
   같은 기업이 받은 것도 센다. 0일이면 다시 고를 수 있다.
4. **잡 종류는 `startup_msg`** — 월간 발송(`startup_ir`)과 갈린다. 그래서
   매월 자동 예약이 이 회차를 그 달 월간 발송으로 잘못 보지 않는다.
5. **발송기는 그 종류를 밝혀야 받는다** — 낡은 발송기(0.11.6)에는 안 내려간다.
6. **각자 보낸다** — 월간 발송의 `한 계정만` 설정과 상관이 없다.
7. **세우기만 한다** — `draft` 로 서고, 예약은 09~19시만 받는다.

## 진짜로는 한 통도 안 나간다

이 검사는 발송 목록까지만 만든다. 이름·회사명은 **전부 지어낸 값**이다 —
저장소가 공개다.
"""
from __future__ import annotations

import json

import pytest

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

# 전부 지어낸 값이다.
MINE = "스타트업 · 강민준"
THEIRS = "스타트업 · 윤서아"
INVESTORS = "투자사 · 강민준"

#: 0.11.6 발송기가 폴링 때 밝히던 종류 — `startup_msg` 가 없다.
OLD_AGENT_KINDS = "deal_intro,ir_delivery,sourcing_intro,verify_room,test_send,startup_ir"

AT = "2099-03-12T14:00"


def _row(db, **kw):
    from app.models import VcContact

    notes = kw.pop("notes", None)
    row = VcContact(user_id=kw.pop("user_id", 1), source_sheet=kw.pop("sheet", MINE),
                    notes=json.dumps(notes, ensure_ascii=False) if notes else None,
                    status=kw.pop("status", "active"), **kw)
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def seeded(db, users):
    """내 스타트업 명단 줄 여럿 — 갈래마다 하나씩."""
    from app.models import SheetOwner

    db.add_all([
        SheetOwner(label=MINE, user_id=1, layout="startup", is_hidden=1),
        SheetOwner(label=THEIRS, user_id=2, layout="startup", is_hidden=1),
        SheetOwner(label=INVESTORS, user_id=1, layout="investor", is_hidden=0),
    ])
    rows = {
        # 보낼 수 있다.
        "ok": _row(db, name="홍길동", firm="가나다랩스",
                   kakao_room_name="홍길동 대표님가나다랩스 , 강민준 팀장",
                   room_verified="verified", notes={"contract": "미계약"}),
        # 성함이 빈 줄 — 그래도 보낼 수 있다(`안녕하세요 대표님.`).
        "noname": _row(db, name="", firm="라마바랩스",
                       kakao_room_name="라마바랩스 대표님 , 강민준 팀장",
                       room_verified="verified", notes={"contract": "계약검토중"}),
        # 방 이름은 있는데 카톡에서 확인 전.
        "unverified": _row(db, name="김철수", firm="사아자랩스",
                           kakao_room_name="김철수 대표님사아자랩스",
                           room_verified="unverified"),
        # 방 이름이 없다.
        "noroom": _row(db, name="이영희", firm="차카타랩스"),
        # 딜소개 불가 — 확인된 방이 있어도 언제나 빠진다.
        "blocked": _row(db, name="박민수", firm="파하랩스",
                        kakao_room_name="박민수 대표님파하랩스",
                        room_verified="verified", notes={"contract": "딜소개 불가"}),
        # 검토중단.
        "paused": _row(db, name="최수진", firm="가가랩스",
                       kakao_room_name="최수진 대표님가가랩스",
                       room_verified="verified", status="paused"),
        # 줄 단위로 감춘 줄.
        "hidden": _row(db, name="정하늘", firm="나나랩스",
                       kakao_room_name="정하늘 대표님나나랩스",
                       room_verified="verified", is_hidden=1),
        # 내 **투자사** 줄 — 스타트업 화면의 줄이 아니다.
        "investor": _row(db, name="김투자", firm="가나벤처스", sheet=INVESTORS,
                         kakao_room_name="김투자 심사역님 가나벤처스",
                         room_verified="verified", connect_stage="connected"),
        # 남의 스타트업 줄 — 같은 기업(다른 팀원 몫의 같은 줄).
        "twin": _row(db, user_id=2, sheet=THEIRS, name="홍길동", firm="가나다랩스",
                     kakao_room_name="홍길동 대표님가나다랩스 , 윤서아 팀장",
                     room_verified="verified"),
    }
    db.commit()
    return rows


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def _topic(key="startup_msg_progress"):
    from app.services import startup_outreach

    return startup_outreach.topic_of(key)


def _send(client, ids, topic="startup_msg_progress", **kw):
    payload = {"topic": topic, "contact_ids": ids, "title": "검사 회차"}
    payload.update(kw)
    return client.post("/api/startup-msg/send", json=payload)


def _jobs(db, kind=None):
    from sqlalchemy import select

    from app.models import SendJob

    stmt = select(SendJob).order_by(SendJob.id)
    if kind:
        stmt = stmt.where(SendJob.kind == kind)
    db.expire_all()
    return db.execute(stmt).scalars().all()


# ── 1. 누구에게 ──────────────────────────────────────────────────────────────

def test_확인된_방이_있는_내_스타트업_줄만_고를_수_있다(db, seeded):
    from app.models import User
    from app.services import startup_outreach

    view = startup_outreach.rows(db, db.get(User, 1), _topic(), 30)
    ids = lambda key: {r["id"] for r in view[f"{key}_rows"]}  # noqa: E731

    assert ids("ready") == {seeded["ok"].id, seeded["noname"].id}
    # 방이 없거나 확인 전 — 접힌 칸에 **남는다**(조용히 빠지지 않는다).
    assert ids("no_room") == {seeded["unverified"].id, seeded["noroom"].id}
    # 딜소개 불가 · 검토중단 — 언제나 빠지되 까닭과 함께 선다.
    assert ids("excluded") == {seeded["blocked"].id, seeded["paused"].id}
    # 감춘 줄 · 투자사 줄 · 남의 줄은 **어디에도** 없다.
    every = {r["id"] for r in view["rows"]}
    for key in ("hidden", "investor", "twin"):
        assert seeded[key].id not in every, key
    # [방 연결 확인] 은 방 이름이 있는 줄만 건다(없는 줄은 찾을 글자가 없다).
    assert view["verify_ids"] == [seeded["unverified"].id]


def test_딜소개_불가는_띄어쓰기가_달라도_빠진다(db, seeded):
    from app.services import startup_outreach

    seeded["ok"].notes = json.dumps({"contract": "딜소개불가"}, ensure_ascii=False)
    assert startup_outreach.refusal(seeded["ok"]) == "딜소개 불가"


@pytest.mark.parametrize("key", ["unverified", "noroom", "blocked", "paused"])
def test_못_고르는_줄은_주소로_찔러도_목록이_안_선다(db, seeded, client, key):
    res = _send(_login(client), [seeded["ok"].id, seeded[key].id])

    assert res.status_code == 400, res.text
    assert seeded[key].firm in res.json()["detail"]
    assert _jobs(db) == []


@pytest.mark.parametrize("key", ["hidden", "investor", "twin"])
def test_내_스타트업_줄이_아니면_없는_줄이다(db, seeded, client, key):
    res = _send(_login(client), [seeded[key].id])

    assert res.status_code == 404
    assert _jobs(db) == []


# ── 2. 무엇을 ────────────────────────────────────────────────────────────────

def test_기본_문구는_사용자가_준_글_그대로다():
    """`000` 자리만 채움말로 바뀌었다. 띄어쓰기 두 칸까지 원문이다."""
    from app.services import startup_outreach

    a, b, c = (startup_outreach.topic_of(k).default for k in
               ("startup_msg_progress", "startup_msg_quote", "startup_msg_free"))
    assert a.startswith("안녕하세요 {대표명} 대표님.\n")
    assert a.endswith("최근 투자사에서 신규 기업 검토 요청이 있어서\n"
                      "대표님 회사 투자유치진행 상황이 어떠신지\n"
                      "문의 연락드렸습니다.")
    assert b == ("안녕하세요, 대표님.\n견적서를 카톡으로 공유 드렸습니다.\n\n"
                 "조건이나 진행 방식 관련하여 조율이 필요하신 부분은 언제든 말씀해 주세요.")
    assert c.startswith("안녕하세요 대표님.\n")
    assert " ASSET  {보내는사람} 팀장입니다.\n\n" in c
    assert c.endswith("무료투자유치 조건 조율이 필요하시면 편하게 톡 주시면 검토 후 "
                      "안내드리겠습니다.")
    assert "000" not in a + b + c


def test_채움말이_채워진다(db, seeded):
    from app.models import User
    from app.services import startup_outreach

    me = db.get(User, 1)
    text = startup_outreach.render(_topic().default, seeded["ok"], me)
    assert text.startswith("안녕하세요 홍길동 대표님.\n")

    free = startup_outreach.render(_topic("startup_msg_free").default, seeded["ok"], me)
    assert f" ASSET  {me.name} 팀장입니다." in free
    assert startup_outreach.render("{회사명} 건으로 연락드립니다", seeded["ok"], me) \
        == "가나다랩스 건으로 연락드립니다"


def test_성함이_비면_대표님으로_읽히고_빈칸이_겹치지_않는다(db, seeded):
    from app.models import User
    from app.services import startup_outreach

    text = startup_outreach.render(_topic().default, seeded["noname"], db.get(User, 1))
    first = text.splitlines()[0]
    assert first == "안녕하세요 대표님."
    assert "{" not in text


def test_성함에_대표가_붙어_있어도_한_번만_나온다(db, seeded):
    from app.models import User
    from app.services import startup_outreach

    seeded["ok"].name = "홍길동 대표"
    text = startup_outreach.render(_topic().default, seeded["ok"], db.get(User, 1))
    assert text.splitlines()[0] == "안녕하세요 홍길동 대표님."


def test_이름_없는_계정은_전화번호를_보내지_않는다(db, seeded):
    from app.models import User
    from app.services import startup_outreach

    me = db.get(User, 1)
    me.name = me.phone       # 계정을 만들 때 이름을 비우면 이렇게 든다
    text = startup_outreach.render(_topic("startup_msg_free").default, seeded["ok"], me)
    assert me.phone not in text
    assert "{보내는사람}" not in text


def test_미리보기와_나가는_글이_같다(db, seeded, client):
    _login(client)
    body = "안녕하세요 {대표명} 대표님.\n{회사명} 건으로 연락드립니다."
    shown = client.post("/api/startup-msg/preview", json={
        "topic": "startup_msg_quote", "body": body,
        "contact_ids": [seeded["ok"].id, seeded["noname"].id]}).json()
    assert not shown["sample"]
    assert [p["message"] for p in shown["previews"]] == [
        "안녕하세요 홍길동 대표님.\n가나다랩스 건으로 연락드립니다.",
        "안녕하세요 대표님.\n라마바랩스 건으로 연락드립니다.",
    ]

    res = _send(client, [seeded["ok"].id, seeded["noname"].id],
                topic="startup_msg_quote", body=body)
    assert res.status_code == 200, res.text
    job = _jobs(db)[0]
    assert [i.message for i in job.items] == [p["message"] for p in shown["previews"]]


def test_아무것도_안_고르면_지어낸_줄로_미리_본다(db, seeded, client):
    shown = _login(client).post("/api/startup-msg/preview", json={
        "topic": "startup_msg_progress", "contact_ids": []}).json()
    assert shown["sample"]
    assert shown["previews"][0]["firm"] == "○○기업"


def test_고른_문구틀이_기본으로_뜬다(db, seeded, client):
    """문구 관리에서 고친 **내 문구**가 이 화면의 기본이다 — 딜 제안 문구와 같은 규칙."""
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=1, kind="startup_msg_quote", name="내 문구",
                           body="안녕하세요 {대표명} 대표님. 견적서 확인 부탁드립니다.",
                           is_active=1))
    db.commit()
    page = _login(client).get("/startup/msg?topic=startup_msg_quote").text
    assert "견적서 확인 부탁드립니다." in page

    res = _send(client, [seeded["ok"].id], topic="startup_msg_quote")
    assert res.status_code == 200, res.text
    assert _jobs(db)[0].items[0].message == "안녕하세요 홍길동 대표님. 견적서 확인 부탁드립니다."


def test_모르는_문구는_짐작하지_않는다(db, seeded, client):
    res = _send(_login(client), [seeded["ok"].id], topic="startup_ir")
    assert res.status_code == 400
    assert _jobs(db) == []


# ── 3. 같은 문구를 또 보내지 않는다 ─────────────────────────────────────────

def _mark_sent(db, job):
    from app import clock

    for item in job.items:
        item.status = "sent"
        item.sent_at = clock.now_iso()
    job.status = "done"
    db.commit()


def test_같은_문구를_30일_안에_받은_곳은_빠지고_0일이면_다시_고른다(db, seeded, client):
    from app.models import User
    from app.services import startup_outreach

    assert _send(_login(client), [seeded["ok"].id]).status_code == 200
    me = db.get(User, 1)

    # 아직 안 나간 회차에 들어 있어도 빠진다 — 둘 다 나가면 두 번 받는다.
    pending = startup_outreach.rows(db, me, _topic(), 30)
    waiting = next(r for r in pending["recent_rows"] if r["id"] == seeded["ok"].id)
    assert f"#{_jobs(db)[0].id}" in waiting["reason"]     # 그 회차로 가는 길

    _mark_sent(db, _jobs(db)[0])
    view = startup_outreach.rows(db, me, _topic(), 30)
    row = next(r for r in view["rows"] if r["id"] == seeded["ok"].id)
    assert row["group"] == "recent"
    assert row["last_date"]
    assert "이 문구를 받음" in row["reason"]
    # 주소로 찔러도 막힌다(화면과 같은 판정).
    again = _send(client, [seeded["ok"].id])
    assert again.status_code == 400
    assert "이 문구를 받음" in again.json()["detail"]

    # 다른 문구는 상관없다.
    other = startup_outreach.rows(db, me, _topic("startup_msg_quote"), 30)
    assert seeded["ok"].id in {r["id"] for r in other["ready_rows"]}
    # 0일이면 빼지 않는다 — 마지막 발송일은 그대로 보인다.
    zero = startup_outreach.rows(db, me, _topic(), 0)
    ready = next(r for r in zero["ready_rows"] if r["id"] == seeded["ok"].id)
    assert ready["last_date"]
    assert _send(client, [seeded["ok"].id], days=0).status_code == 200


def test_다른_팀원_명단의_같은_기업이_받은_것도_센다(db, seeded, client):
    from app.models import User
    from app.services import startup_outreach

    # 윤서아(2번)가 자기 명단의 같은 기업에 보냈다.
    assert _send(_login(client, "01000000002"), [seeded["twin"].id]).status_code == 200
    _mark_sent(db, _jobs(db)[0])

    view = startup_outreach.rows(db, db.get(User, 1), _topic(), 30)
    row = next(r for r in view["rows"] if r["id"] == seeded["ok"].id)
    assert row["group"] == "recent"
    assert row["last_by"] == "윤서아"


def test_취소한_회차는_받은_것으로_안_친다(db, seeded, client):
    from app.models import User
    from app.services import startup_outreach

    _send(_login(client), [seeded["ok"].id])
    job = _jobs(db)[0]
    assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 200
    view = startup_outreach.rows(db, db.get(User, 1), _topic(), 30)
    assert seeded["ok"].id in {r["id"] for r in view["ready_rows"]}


# ── 4. 잡 종류 · 월간 자동 예약 ──────────────────────────────────────────────

def test_대기_목록은_startup_msg_로_서고_문구가_남는다(db, seeded, client):
    from app.models import STARTUP_MSG_KIND

    res = _send(_login(client), [seeded["ok"].id])
    assert res.status_code == 200, res.text
    assert res.json()["href"] == f"/jobs/{res.json()['job_id']}"

    job = _jobs(db)[0]
    assert job.kind == STARTUP_MSG_KIND == "startup_msg"
    assert job.status == "draft"           # 세우기만 한다
    assert job.topic == "startup_msg_progress"
    assert job.user_id == 1
    item = job.items[0]
    assert item.contact_id == seeded["ok"].id
    assert item.ir_company_id is None
    assert item.room_name == seeded["ok"].kakao_room_name
    assert item.message.startswith("안녕하세요 홍길동 대표님.")
    # 진행 화면에 **기업명**이 선다(성함이 빈 줄이 흔하다).
    assert item.recipient_name == "가나다랩스 · 홍길동"
    status = client.get(f"/api/jobs/{job.id}").json()
    assert status["items"][0]["contact_name"] == "가나다랩스 · 홍길동"
    # 진행 화면의 `새 발송` 은 이 화면으로 돌아온다(딜 제안 관리가 아니다).
    assert 'href="/startup/msg?topic=startup_msg_progress"' in client.get(f"/jobs/{job.id}").text


def test_월간_자동_예약은_안내_카톡_회차를_그_달_월간_발송으로_안_본다(db, seeded, client):
    from app.services import ir_monthly, startup_monthly

    assert _send(_login(client), [seeded["ok"].id]).status_code == 200
    assert startup_monthly.month_job(db, ir_monthly.this_month()) is None


def test_안내_카톡은_딜소개_실적에_안_섞인다():
    from app.models import SEND_KINDS, STARTUP_MSG_KIND

    assert STARTUP_MSG_KIND not in SEND_KINDS


# ── 5. 발송기는 그 종류를 밝혀야 받는다 ─────────────────────────────────────

def test_낡은_발송기에는_안_내려가고_새_발송기는_집어간다(db, seeded, client):
    from agent.main import STARTUP_MSG_KIND, SUPPORTED_KINDS
    from app.models import STARTUP_MSG_KIND as SERVER_KIND

    assert STARTUP_MSG_KIND == SERVER_KIND
    assert STARTUP_MSG_KIND in SUPPORTED_KINDS

    _send(_login(client), [seeded["ok"].id])
    job = _jobs(db)[0]
    # draft 인 동안은 새 발송기도 못 가져간다.
    new_kinds = {"kinds": ",".join(SUPPORTED_KINDS), "files": 0}
    assert client.get("/api/agent/poll", params=new_kinds,
                      headers=auth(DEMO_TOKEN)).status_code == 204

    assert client.post(f"/api/jobs/{job.id}/start").status_code == 200
    # 0.11.6 은 이 종류를 모른다 — 서버가 안 내준다(잡은 큐에 그대로 선다).
    assert client.get("/api/agent/poll", params={"kinds": OLD_AGENT_KINDS},
                      headers=auth(DEMO_TOKEN)).status_code == 204
    assert _jobs(db)[0].status == "queued"
    # 남의 발송기도 못 가져간다 — 그 사람 PC 의 카톡에서 나간다.
    assert client.get("/api/agent/poll", params=new_kinds,
                      headers=auth(OTHER_TOKEN)).status_code == 204

    got = client.get("/api/agent/poll", params=new_kinds, headers=auth(DEMO_TOKEN))
    assert got.status_code == 200
    assert got.json()["kind"] == "startup_msg"
    assert got.json()["items"][0]["room_name"] == seeded["ok"].kakao_room_name
    assert "files" not in got.json()["items"][0]


def test_발송기는_안내_카톡을_발송_잡처럼_보낸다():
    """모르는 종류로 보고 실패 처리하면 안 된다 — 방 하나에 문구 한 통이다."""
    from agent import main
    from agent.sender.base import SendResult

    sent = []

    class Sender:
        name = "mock"

        def send_text(self, room, text):
            sent.append((room, text))
            return SendResult(ok=True)

    class Client:
        def __init__(self):
            self.items, self.jobs = [], []

        def job_state(self, job_id):
            return {"canceled": False, "canceled_items": []}

        def report_item(self, item_id, status, **kw):
            self.items.append((item_id, status))

        def report_job(self, job_id, status):
            self.jobs.append(status)

        def report_diagnostics(self, payload):
            pass

    cfg = dict(main.DEFAULT_CONFIG, delay_min_sec=0, delay_max_sec=0,
               part_gap_sec=0, cancel_check_backoff_sec=0)
    client = Client()
    main.process_job(client, Sender(), {
        "job_id": 1, "kind": "startup_msg",
        "items": [{"id": 7, "room_name": "가나다랩스 대표님", "message": "안녕하세요 대표님."}],
    }, cfg)
    assert client.items == [(7, "sent")]
    assert client.jobs == ["done"]
    assert sent == [("가나다랩스 대표님", "안녕하세요 대표님.")]


# ── 6. 각자 보낸다 ───────────────────────────────────────────────────────────

def test_월간_발송의_한_계정_설정과_상관없이_각자_보낸다(db, seeded, client):
    """월간 발송은 정해진 한 계정만 보낸다(`startup_send.may_send`). 안내 카톡은
    딜소개처럼 각자다 — 그 설정이 다른 사람으로 켜져 있어도 내 줄에는 보낸다."""
    from app.models import User
    from app.services import startup_send

    startup_send.save(db, enabled=True, user_id=2)
    assert not startup_send.may_send(db, db.get(User, 1))

    _login(client)
    assert client.get("/startup/msg").status_code == 200
    assert _send(client, [seeded["ok"].id]).status_code == 200


def test_관리자도_남의_줄에는_못_보낸다(db, seeded, client):
    from app.models import User

    db.get(User, 1).role = "admin"
    db.commit()
    assert _send(_login(client), [seeded["twin"].id]).status_code == 404


# ── 7. 예약 ─────────────────────────────────────────────────────────────────

def test_보낼_시각을_고르면_예약이_걸리고_곳으로_센다(db, seeded, client):
    res = _send(_login(client), [seeded["ok"].id, seeded["noname"].id], scheduled_at=AT)
    assert res.status_code == 200, res.text
    job = _jobs(db)[0]
    assert job.status == "draft"
    assert job.scheduled_at.startswith("2099-03-12T14:00")

    status = client.get(f"/api/jobs/{job.id}").json()
    assert status["scheduled"]["unit"] == "곳"
    assert "2곳에" in status["scheduled"]["sentence"]


def test_업무시간_밖_예약은_거절하고_회차도_안_선다(db, seeded, client):
    res = _send(_login(client), [seeded["ok"].id], scheduled_at="2099-03-12T22:00")
    assert res.status_code == 400
    assert _jobs(db) == []


# ── 8. 화면 ─────────────────────────────────────────────────────────────────

def test_화면이_고를_수_있는_줄과_까닭을_세운다(db, seeded, client):
    page = _login(client).get("/startup/msg").text

    assert 'class="msg-pick" value="%d"' % seeded["ok"].id in page
    assert 'class="msg-pick" value="%d"' % seeded["noname"].id in page
    for key in ("unverified", "blocked", "paused"):
        assert 'class="msg-pick" value="%d"' % seeded[key].id not in page, key
    # 방 확인 전 · 제외 줄도 **화면에 선다**(조용히 빠지지 않는다).
    for key in ("unverified", "noroom", "blocked", "paused"):
        assert seeded[key].firm in page, key
    for key in ("hidden", "investor"):
        assert seeded[key].firm not in page, key
    assert "msg-verify-btn" in page
    assert "startup_msg.js" in page
    # 문구 셋이 다 고를 거리로 선다.
    for key in ("startup_msg_progress", "startup_msg_quote", "startup_msg_free"):
        assert f"topic={key}" in page


def test_스타트업_화면에서_안내_카톡과_방_연결_확인으로_간다(db, seeded, client):
    page = _login(client).get(f"/startup?sheet={MINE}").text
    assert 'href="/startup/msg"' in page
    assert 'id="verify-btn"' in page
    assert 'id="verify-one-btn"' in page
    # 수정창에서 방 이름을 적을 수 있다(그동안 이 배치엔 자리가 없었다).
    assert 'id="f-kakao_room_name"' in page


# ── 9. 방 연결 확인 — 스타트업 줄도 받되 투자사가 되지는 않는다 ────────────

def test_스타트업_줄도_방_연결_확인을_건다(db, seeded, client):
    res = _login(client).post("/api/contacts/verify-rooms",
                              json={"contact_ids": [seeded["unverified"].id]})
    assert res.status_code == 200, res.text
    job = _jobs(db, "verify_room")[0]
    assert [i.contact_id for i in job.items] == [seeded["unverified"].id]
    assert job.items[0].message == ""          # 아무것도 안 보낸다


def test_감춘_스타트업_줄은_방_연결_확인도_안_건다(db, seeded, client):
    res = _login(client).post("/api/contacts/verify-rooms",
                              json={"contact_ids": [seeded["hidden"].id]})
    assert res.status_code == 400
    assert _jobs(db, "verify_room") == []


def test_방이_확인돼도_스타트업_줄은_딜소개_대상이_아니다(db, seeded):
    from app.models import User
    from app.services import sheet_owner

    me = db.get(User, 1)
    seeded["ok"].connect_stage = "connected"
    db.commit()
    names = {c.id for c in sheet_owner.recipients(db, me)}
    assert seeded["ok"].id not in names
    assert seeded["investor"].id in names
    assert seeded["ok"].id not in {c.id for c in sheet_owner.my_contacts(db, me)}


# ── 10. 문구 관리 ────────────────────────────────────────────────────────────

def test_문구_관리에_셋이_서고_새_서버에_기본_문구가_심긴다(db, users, client):
    from sqlalchemy import select

    from app.models import MessageTemplate
    from app.services import startup_outreach
    from scripts.bootstrap import bootstrap

    page = _login(client).get("/templates").text
    for t in startup_outreach.TOPICS:
        assert f"스타트업 안내 — {t.label}" in page

    bootstrap(db)
    db.commit()
    for t in startup_outreach.TOPICS:
        row = db.execute(select(MessageTemplate).where(
            MessageTemplate.kind == t.key, MessageTemplate.user_id.is_(None))).scalar_one()
        assert row.body == t.default


# ── 11. 브라우저 쪽 ──────────────────────────────────────────────────────────

def test_고르기와_보내기는_node_로_잰다():
    """`tests/js/startup_msg_test.js` — 단추의 `N곳`, 감춘 줄의 체크 풀기,
    보내는 값, 미리보기를 글자 그대로 적는가. `node` 가 없으면 건너뛴다."""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 검사 생략 "
                    "(호스트에서 `node tests/js/startup_msg_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "startup_msg_test.js"
    done = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


def test_가짜_화면이_실제_화면과_같은_이름을_쓴다(db, seeded, client):
    """`node` 검사는 손으로 지은 화면에서 돈다 — 실제 템플릿에서 이름이 바뀌면
    그쪽은 조용히 통과한다. 그 틈을 여기서 막는다."""
    from pathlib import Path

    page = _login(client).get("/startup/msg").text
    js = (Path(__file__).resolve().parent / "js" / "startup_msg_test.js"
          ).read_text(encoding="utf-8")
    for token in ("msg-table", "msg-row", "msg-pick", "msg-body", "data-topic",
                  "msg-send-btn", "data-days", "msg-all", "msg-contract",
                  "data-contract", "msg-search", "data-search", "msg-title",
                  "msg-when", "msg-preview-btn", "msg-preview-list",
                  "msg-preview-note", "msg-error"):
        assert token in page, f"템플릿에서 {token} 가 사라졌다"
        assert token in js, f"가짜 화면이 {token} 를 안 쓴다"


# ── 12. 활동 이력 ────────────────────────────────────────────────────────────

def test_보낸_안내_카톡이_그_줄의_활동_이력에_문구_이름으로_남는다(db, seeded, client):
    _send(_login(client), [seeded["ok"].id], topic="startup_msg_free")
    _mark_sent(db, _jobs(db)[0])

    timeline = client.get(f"/api/contacts/{seeded['ok'].id}").json()["timeline"]
    row = next(t for t in timeline if t["kind"] == "startup_msg")
    assert row["content"] == "안내 카톡 · 무료 투자유치 제안"
    assert row["date"]
