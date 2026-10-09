"""스타트업 명단 줄의 카톡방 **후보 찾기 · 확정** — 좌측 [스타트업] → [방 매칭].

운영의 스타트업 명단 줄에는 방 이름이 든 곳이 하나도 없어서, 스타트업 안내
카톡(0.11.7)이 고를 수 있는 곳이 0곳이었다. 회사명으로 카톡을 뒤져 후보를
모으고, 사람이 골라 확정한다.

## 여기서 못박는 것

1. **찾는 줄** — 내 스타트업 줄 중 방이 확인 안 된 곳만. 남의 줄 · 감춘 줄 ·
   투자사 줄 · 이미 확인된 줄 · 딜소개 불가 · 검토중단은 id 로 찔러도 안 들어간다.
2. **발송기를 안 고쳤다** — 이미 있는 방 확인 잡(`verify_room`)에 `topic` 만
   달았다. 줄은 **회사명으로** 내주고 `target: company` 를 붙인다(발송기가 맨 위
   방 열기에서 투자사 방을 버린다). `firm` 은 안 보낸다.
3. **후보로만 담는다** — 하나뿐이고 `확인됨` 이어도 방 이름에 안 넣는다.
   투자사 방은 담지 않는다.
4. **확정** — 방 이름 = 그 제목, `확인됨`, 카톡 연결 여부 `O`(`room_joined`).
   그 순간 안내 카톡에서 고를 수 있고, 투자사로는 세지 않는다.
5. **직접 적기** — `확인 안 됨`. [방 연결 확인] 을 거쳐야 보낸다.
6. **투자사 담당자의 방 확인은 그대로다** — 하나면 그 제목을 넣는다.

이름·회사명은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json

import pytest

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

# 전부 지어낸 값이다.
MINE = "스타트업 · 강민준"
THEIRS = "스타트업 · 윤서아"
INVESTORS = "투자사 · 강민준"

ROOM_A = "홍길동 대표님가나다랩스 , 강민준 팀장"
ROOM_B = "가나다랩스 투자유치 공유방"
INVESTOR_ROOM = "가나다랩스 김투자 이사님 다라마인베스트먼트 Asset deal 공유"


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
    from app.models import SheetOwner

    db.add_all([
        SheetOwner(label=MINE, user_id=1, layout="startup", is_hidden=1),
        SheetOwner(label=THEIRS, user_id=2, layout="startup", is_hidden=1),
        SheetOwner(label=INVESTORS, user_id=1, layout="investor", is_hidden=0),
    ])
    rows = {
        # 방 이름이 없다 — 찾는다. 법인 표기는 검색어에서 뗀다.
        "noroom": _row(db, name="홍길동", firm="(주)가나다랩스"),
        # 적어 둔 이름은 있는데 확인 전 — 찾는다(후보만 담고 적어 둔 이름은 그대로).
        "typed": _row(db, name="김철수", firm="라마바랩스",
                      kakao_room_name="김철수 대표님 라마바", room_verified="unverified"),
        # 확인했는데 카톡에서 못 찾았다 — 찾는다.
        "notfound": _row(db, name="이영희", firm="사아자랩스",
                         kakao_room_name="이영희 대표 사아자", room_verified="not_found"),
        # 이미 확인된 방 — 안 찾는다.
        "ok": _row(db, name="박민수", firm="차카타랩스",
                   kakao_room_name="박민수 대표님차카타랩스 , 강민준 팀장",
                   room_verified="verified", kakao_joined="O"),
        # 회사명이 빈 줄 — 무엇으로 찾을지가 없다.
        "nofirm": _row(db, name="최수진", firm=""),
        # 딜소개 불가 · 검토중단 — 안내 카톡이 언제나 빼는 줄이라 안 찾는다.
        "blocked": _row(db, name="정하늘", firm="파하랩스",
                        notes={"contract": "딜소개 불가"}),
        "paused": _row(db, name="서가명", firm="가가랩스", status="paused"),
        # 줄 단위로 감춘 줄.
        "hidden": _row(db, name="한가명", firm="나나랩스", is_hidden=1),
        # 내 **투자사** 줄.
        "investor": _row(db, name="김투자", title="이사님", firm="다라마벤처스",
                         sheet=INVESTORS, kakao_room_name="김투자 이사님 다라마벤처스",
                         room_verified="unverified", connect_stage="connected"),
        # 남의 스타트업 줄 — 같은 기업.
        "twin": _row(db, user_id=2, sheet=THEIRS, name="홍길동", firm="(주)가나다랩스"),
    }
    db.commit()
    return rows


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def _search(client, ids=None):
    body = {} if ids is None else {"contact_ids": ids}
    return client.post("/api/startup-rooms/search", json=body)


def _jobs(db):
    from sqlalchemy import select

    from app.models import SendJob

    db.expire_all()
    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


def _agent_kinds() -> str:
    """**지금 발송기**가 폴링 때 밝히는 종류 그대로."""
    import agent.main as agent_main

    return ",".join(agent_main.SUPPORTED_KINDS)


def _poll(client, token=DEMO_TOKEN):
    res = client.get("/api/agent/poll", params={"kinds": _agent_kinds()},
                     headers=auth(token))
    assert res.status_code == 200, res.text
    return res.json()


def _report(client, item_id, *, candidates=None, verdict="ambiguous",
            found_room=None, token=DEMO_TOKEN):
    """발송기가 결과를 올리는 그 길(`agent/main.py: process_verify_job`)."""
    res = client.post(f"/api/agent/items/{item_id}/result", headers=auth(token),
                      json={"status": "sent" if verdict == "verified" else "failed",
                            "verify_result": verdict, "found_room": found_room,
                            "candidates": candidates})
    assert res.status_code == 200, res.text
    return res


def _item(db, job, contact_id):
    return next(i for i in job.items if i.contact_id == contact_id)


def _found(db, client, row, rooms, verdict="ambiguous", found_room=None):
    """찾기 → 그 줄의 결과를 발송기처럼 올린다."""
    assert _search(client).status_code == 200
    job = _jobs(db)[-1]
    item = _item(db, job, row.id)
    _report(client, item.id, candidates=rooms, verdict=verdict, found_room=found_room)
    db.expire_all()
    return item


def _confirm(client, row, room):
    return client.post(f"/api/startup-rooms/{row.id}/confirm", json={"room": room})


# ── 1. 찾는 줄 ──────────────────────────────────────────────────────────────

def test_찾기는_내_스타트업_줄_중_확인_안_된_곳만_싣는다(db, seeded, client):
    from app.models import ROOM_SEARCH_TOPIC

    res = _search(_login(client))
    assert res.status_code == 200, res.text

    jobs = _jobs(db)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "verify_room", "새 잡 종류를 만들면 낡은 발송기가 집어가지 않는다"
    assert job.topic == ROOM_SEARCH_TOPIC
    assert job.status == "queued"
    assert job.user_id == 1
    assert res.json()["href"] == f"/jobs/{job.id}"

    assert {i.contact_id for i in job.items} == {
        seeded["noroom"].id, seeded["typed"].id, seeded["notfound"].id}
    for item in job.items:
        assert item.message == "", "확인 잡에 보낼 문구가 실렸다"
        assert item.room_name == "", "모르는 방 이름을 지어 넣었다"
        assert item.ir_company_id is None


def test_고른_줄만_찾되_남의_줄_투자사_줄은_id로도_안_들어간다(db, seeded, client):
    ids = [seeded[k].id for k in ("noroom", "twin", "investor", "hidden", "ok",
                                  "blocked", "paused", "nofirm")]
    res = _search(_login(client), ids)
    assert res.status_code == 200, res.text
    assert res.json()["skipped"] == 7

    job = _jobs(db)[0]
    assert [i.contact_id for i in job.items] == [seeded["noroom"].id]


def test_찾을_곳이_없으면_잡을_세우지_않는다(db, seeded, client):
    res = _search(_login(client), [seeded["ok"].id, seeded["investor"].id])
    assert res.status_code == 400
    assert "찾을 곳이 없습니다" in res.json()["detail"]
    assert not _jobs(db)


def test_남의_계정으로는_내_줄을_찾지_않는다(db, seeded, client):
    """남(윤서아)이 내 줄 번호를 보내도 그 사람의 줄만 고른다."""
    me = _login(client, phone="01000000002")
    res = _search(me, [seeded["noroom"].id, seeded["twin"].id])
    assert res.status_code == 200, res.text
    job = _jobs(db)[0]
    assert job.user_id == 2
    assert [i.contact_id for i in job.items] == [seeded["twin"].id]


# ── 2. 발송기에 무엇이 가나 — 발송기는 안 고쳤다 ─────────────────────────────

def test_폴링이_회사명과_기업_표시를_내준다(db, seeded, client):
    """`query` 는 회사명(법인 표기 · 꼬리표를 뗀 것), `target` 은 `company`.

    `firm` 은 **안 보낸다** — 보내면 발송기가 결과가 둘 이상일 때 그것으로
    줄이고, 하나가 되면 나머지 후보를 버린 채 보고한다.
    """
    me = _login(client)
    _search(me)
    got = _poll(me)
    assert got["kind"] == "verify_room"
    by_id = {i["id"]: i for i in got["items"]}
    item = by_id[_item(db, _jobs(db)[0], seeded["noroom"].id).id]

    assert item["query"] == "가나다랩스"
    assert item["name"] == "가나다랩스"
    assert item["target"] == "company"
    assert "firm" not in item
    assert item["room_name"] == "" and item["message"] == ""
    # 성함으로 찾지 않는다 — 그 이름이 든 다른 방이 걸린다.
    assert all("홍길동" not in i["query"] for i in got["items"])


def test_투자사_담당자_방_확인은_이름과_직함으로_그대로_나간다(db, seeded, client):
    me = _login(client)
    res = me.post("/api/contacts/verify-rooms",
                  json={"contact_ids": [seeded["investor"].id]})
    assert res.status_code == 200, res.text
    job = _jobs(db)[0]
    assert job.topic is None

    item = _poll(me)["items"][0]
    assert item["query"] == "김투자 이사님"
    assert item["name"] == "김투자"
    assert item["firm"] == "다라마벤처스"
    assert "target" not in item


def test_발송기가_명단_줄을_기업_규칙으로_찾는다(db, seeded, client):
    """서버가 내준 그대로를 **실제 발송기 함수**에 넣는다.

    발송기는 줄이 어느 표의 것인지 모른다 — `query` 와 `target` 만 본다. 그래서
    판을 올리지 않고도 회사명으로 찾고(`company=True` — 맨 위 방 열기에서 투자사
    방을 버린다), 후보를 줄이지 않은 채 전부 올린다.
    """
    import agent.main as agent_main
    from tests.test_win_discover_rooms import NO_WAIT, FakeAgentClient

    class Recording:
        name = "fake"

        def __init__(self):
            self.calls = []

        def discover_rooms(self, query, marker="", company=False):
            self.calls.append((query, company))
            return [ROOM_A, ROOM_B] if query == "가나다랩스" else []

        def verify_room(self, room_name):
            return "not_found"

    me = _login(client)
    _search(me, [seeded["noroom"].id])
    job = _poll(me)
    sender, agent = Recording(), FakeAgentClient()
    agent_main.process_verify_job(agent, sender, job, dict(NO_WAIT))

    assert sender.calls == [("가나다랩스", True)]
    assert agent.items[0]["candidates"] == [ROOM_A, ROOM_B]
    assert agent.items[0]["verify_result"] == "ambiguous"


def test_발송기_판을_올리지_않았다():
    """새 잡 종류가 없다 — 지금 발송기가 이미 밝히는 종류로 선다."""
    import agent.main as agent_main
    from app.routers import agent_api, startup_outreach as router

    assert router.VERIFY_KIND is agent_api.VERIFY_KIND
    assert agent_api.VERIFY_KIND in agent_main.SUPPORTED_KINDS


# ── 3. 후보로만 담는다 ───────────────────────────────────────────────────────

def test_찾은_제목은_후보로만_담기고_투자사_방은_빠진다(db, seeded, client):
    from app.services import room_match

    me = _login(client)
    item = _found(db, me, seeded["noroom"], [INVESTOR_ROOM, ROOM_A, ROOM_B])
    row = seeded["noroom"]

    found = room_match.candidates(row)
    assert found["rooms"] == [ROOM_A, ROOM_B]
    assert found["dropped"] == 1
    assert found["query"] == "가나다랩스"
    assert row.kakao_room_name is None
    assert row.room_verified == "unverified"
    assert row.kakao_joined is None
    assert item.status == "failed"
    assert "후보 2개" in item.error and "방 매칭" in item.error
    assert "고유하게" not in item.error


def test_하나뿐이고_확인됨이어도_방_이름에_넣지_않는다(db, seeded, client):
    """**이 기능의 알맹이.** 회사명이 든 방이 꼭 그 대표와의 방인 것은 아니다 —
    서버가 혼자 넣으면 엉뚱한 방으로 안내 카톡이 간다."""
    from app.services import room_match

    me = _login(client)
    item = _found(db, me, seeded["noroom"], [ROOM_A], verdict="verified",
                  found_room=ROOM_A)
    row = seeded["noroom"]
    assert row.kakao_room_name is None
    assert row.room_verified == "unverified"
    assert row.kakao_joined is None
    assert room_match.candidates(row)["rooms"] == [ROOM_A]
    assert item.status == "sent"


def test_적어_둔_이름이_있는_줄도_후보만_담는다(db, seeded, client):
    from app.services import room_match

    me = _login(client)
    _found(db, me, seeded["typed"], ["김철수 대표님 라마바랩스"], verdict="verified",
           found_room="김철수 대표님 라마바랩스")
    row = seeded["typed"]
    assert row.kakao_room_name == "김철수 대표님 라마바"
    assert row.room_verified == "unverified"
    assert room_match.candidates(row)["rooms"] == ["김철수 대표님 라마바랩스"]


def test_후보의_가운데_공백은_그대로_담는다(db, seeded, client):
    """후보는 눌러서 그대로 방 이름이 되는 글자다 — 두 칸을 한 칸으로 줄이면
    확정한 순간 발송기가 못 찾는 이름이 된다."""
    from app.services import room_match

    me = _login(client)
    _found(db, me, seeded["noroom"], ["  홍길동  대표님 가나다랩스 "])
    assert room_match.candidates(seeded["noroom"])["rooms"] == ["홍길동  대표님 가나다랩스"]


def test_투자사_담당자_확인은_하나면_그대로_넣는다(db, seeded, client):
    """투자사 줄은 **적어 둔 이름을 대조**하는 길이라 결과 하나를 넣는다 —
    지금까지와 같다. 후보 칸도 안 쓴다."""
    me = _login(client)
    me.post("/api/contacts/verify-rooms", json={"contact_ids": [seeded["investor"].id]})
    item = _jobs(db)[0].items[0]
    found = "김투자 이사님 다라마벤처스 Deal 공유"
    _report(me, item.id, verdict="verified", found_room=found, candidates=[found])
    db.expire_all()

    row = seeded["investor"]
    assert row.kakao_room_name == found
    assert row.room_verified == "verified"
    assert row.kakao_joined == "O"
    assert row.room_candidates is None


# ── 4. 확정 ──────────────────────────────────────────────────────────────────

def test_확정하면_확인됨_참여_O_이고_안내_카톡에서_고를_수_있다(db, seeded, client):
    from app.models import STARTUP_MSG_KIND, User
    from app.services import sheet_owner, startup_outreach

    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A, ROOM_B])
    res = _confirm(me, seeded["noroom"], ROOM_A)
    assert res.status_code == 200, res.text
    assert res.json()["room_ready"] is True
    db.expire_all()

    row = seeded["noroom"]
    assert row.kakao_room_name == ROOM_A
    assert row.room_verified == "verified"
    assert row.kakao_joined == "O"

    # 안내 카톡이 곧바로 고를 수 있다 — 화면도, 목록을 만드는 자리도.
    user = db.get(User, 1)
    view = startup_outreach.rows(db, user, startup_outreach.TOPICS[0], 30)
    assert row.id in {r["id"] for r in view["ready_rows"]}
    page = me.get("/startup/msg").text
    assert f'class="msg-pick" value="{row.id}"' in page
    sent = me.post("/api/startup-msg/send", json={
        "topic": "startup_msg_progress", "contact_ids": [row.id], "title": "검사 회차"})
    assert sent.status_code == 200, sent.text
    job = _jobs(db)[-1]
    assert job.kind == STARTUP_MSG_KIND and job.status == "draft"
    assert [i.room_name for i in job.items] == [ROOM_A]

    # 확정해도 **투자사가 되지 않는다** — 딜소개 대상 · 투자사 수에 안 들어간다.
    assert row not in sheet_owner.investors(db, [row])
    assert row.id not in {c.id for c in sheet_owner.recipients(db, user)}


def test_후보에_없는_글자는_확정하지_않는다(db, seeded, client):
    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A])
    res = _confirm(me, seeded["noroom"], "아무렇게나 적은 방")
    assert res.status_code == 400
    assert "후보가 아닙니다" in res.json()["detail"]
    db.expire_all()
    assert seeded["noroom"].kakao_room_name is None
    assert seeded["noroom"].room_verified == "unverified"


def test_담겨_있는_투자사_방은_화면에도_안_서고_확정도_안_된다(db, seeded, client):
    """거르기가 생기기 전 · 투자사 명단이 늘기 전에 담긴 것도 같은 함수로 거른다."""
    from app.deps import now_iso
    from app.services import room_match

    room_match.save_candidates(seeded["noroom"], [INVESTOR_ROOM, ROOM_A], at=now_iso(),
                               query="가나다랩스")
    db.commit()
    me = _login(client)
    page = me.get("/startup/rooms").text
    assert ROOM_A in page
    assert INVESTOR_ROOM not in page
    assert "투자사 방 1개는 후보에서 뺐습니다" in page

    res = _confirm(me, seeded["noroom"], INVESTOR_ROOM)
    assert res.status_code == 400
    db.expire_all()
    assert seeded["noroom"].kakao_room_name is None


def test_같은_제목의_방이_여럿이면_확정하지_않는다(db, seeded, client):
    """그 글자로는 어느 방인지 가를 수 없다 — 방 확인의 `같은 이름이 여럿`."""
    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A, ROOM_A, ROOM_B])
    page = me.get("/startup/rooms").text
    assert "같은 제목의 방이 여럿" in page

    res = _confirm(me, seeded["noroom"], ROOM_A)
    assert res.status_code == 400
    assert "여럿" in res.json()["detail"]
    assert _confirm(me, seeded["noroom"], ROOM_B).status_code == 200


def test_남의_줄_감춘_줄_제외_줄은_확정할_수_없다(db, seeded, client):
    from app.deps import now_iso
    from app.services import room_match

    for key in ("twin", "hidden", "blocked", "investor"):
        room_match.save_candidates(seeded[key], [ROOM_A], at=now_iso(), query="x")
    db.commit()
    me = _login(client)
    for key in ("twin", "hidden", "blocked", "investor"):
        assert _confirm(me, seeded[key], ROOM_A).status_code == 404, key
    db.expire_all()
    assert seeded["twin"].kakao_room_name is None


def test_방_나감으로_적힌_줄은_확정해도_확인됨이_아니다(db, seeded, client):
    """`room_joined` 의 규칙 그대로 — 사람이 나갔다고 적어 둔 줄이다."""
    seeded["noroom"].connect_stage = "left_room"
    db.commit()
    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A])
    res = _confirm(me, seeded["noroom"], ROOM_A)
    assert res.status_code == 200
    assert res.json()["room_ready"] is False
    db.expire_all()
    assert seeded["noroom"].kakao_room_name == ROOM_A
    assert seeded["noroom"].room_verified == "unverified"


def test_다른_후보로_바꿔_확정해도_확인됨이다(db, seeded, client):
    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A, ROOM_B])
    assert _confirm(me, seeded["noroom"], ROOM_A).status_code == 200
    assert _confirm(me, seeded["noroom"], ROOM_B).status_code == 200
    db.expire_all()
    assert seeded["noroom"].kakao_room_name == ROOM_B
    assert seeded["noroom"].room_verified == "verified"


# ── 5. 직접 적기 ─────────────────────────────────────────────────────────────

def test_직접_적은_이름은_확인_안_됨이고_연결_확인을_거쳐야_한다(db, seeded, client):
    from app.models import User
    from app.services import startup_outreach

    me = _login(client)
    res = me.patch(f"/api/contacts/{seeded['noroom'].id}",
                   json={"kakao_room_name": "홍길동 대표님 가나다랩스"})
    assert res.status_code == 200, res.text
    db.expire_all()
    row = seeded["noroom"]
    assert row.kakao_room_name == "홍길동 대표님 가나다랩스"
    assert row.room_verified == "unverified"
    assert not startup_outreach.room_ready(row)

    view = startup_outreach.rows(db, db.get(User, 1), startup_outreach.TOPICS[0], 30)
    assert row.id in view["verify_ids"]
    page = me.get("/startup/rooms").text
    assert "적어 둔 이름" in page


def test_확정한_방을_직접_고치면_확인이_풀린다(db, seeded, client):
    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A])
    _confirm(me, seeded["noroom"], ROOM_A)
    me.patch(f"/api/contacts/{seeded['noroom'].id}",
             json={"kakao_room_name": ROOM_A + " 2"})
    db.expire_all()
    assert seeded["noroom"].room_verified == "unverified"


# ── 6. 화면 ──────────────────────────────────────────────────────────────────

def test_방_매칭_화면이_내_줄과_상태를_세운다(db, seeded, client):
    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A, ROOM_B])
    item = _item(db, _jobs(db)[-1], seeded["notfound"].id)
    _report(me, item.id, candidates=None, verdict="not_found")

    res = me.get("/startup/rooms")
    assert res.status_code == 200
    page = res.text
    # 내 줄(제외 줄 빼고)만 선다.
    for key in ("noroom", "typed", "notfound", "ok"):
        assert seeded[key].firm in page, key
    for firm in ("파하랩스", "가가랩스", "나나랩스", "다라마벤처스"):
        assert firm not in page, firm
    # 상태 넷.
    assert "확정됨" in page and "후보 2개" in page
    assert "후보 없음" in page and "아직 안 찾아봄" in page
    # 후보마다 [이 방으로 확정].
    assert f'data-room="{ROOM_A}"' in page and "이 방으로 확정" in page
    # 찾을 곳 수는 잡을 세우는 함수와 같은 수다(확인 안 된 내 줄 셋).
    assert "방 후보 찾기 (3곳)" in page
    assert "딜소개 불가 · 검토중단 <b>2곳</b>" in page
    assert 'class="room-input room-direct"' in page


def test_남의_화면에는_내_줄이_없다(db, seeded, client):
    page = _login(client, phone="01000000002").get("/startup/rooms").text
    assert "라마바랩스" not in page
    assert "방 후보 찾기 (1곳)" in page


def test_스타트업_화면에_단추가_서고_투자사_화면에는_없다(db, seeded, client):
    from urllib.parse import quote

    me = _login(client)
    page = me.get(f"/startup?sheet={quote(MINE)}").text
    assert 'id="room-search-btn"' in page
    assert 'href="/startup/rooms"' in page
    assert 'id="room-search-one-btn"' in page

    contacts = me.get("/contacts").text
    assert 'id="room-search-btn"' not in contacts
    assert 'id="room-search-one-btn"' not in contacts


def test_안내_카톡의_방_확인_전_칸에서_찾기로_이어진다(db, seeded, client):
    page = _login(client).get("/startup/msg").text
    assert 'id="msg-room-search-btn"' in page
    assert 'data-count="3"' in page
    assert 'href="/startup/rooms"' in page


def test_진행_화면이_후보_찾기라고_말하고_매칭으로_이어진다(db, seeded, client):
    me = _login(client)
    _search(me)
    job = _jobs(db)[0]
    page = me.get(f"/jobs/{job.id}").text
    assert "카톡방 후보 찾기" in page
    assert 'href="/startup/rooms"' in page
    assert "내 투자사로" not in page

    names = {i["contact_name"] for i in me.get(f"/api/jobs/{job.id}").json()["items"]}
    assert "(주)가나다랩스 · 홍길동" in names


def test_투자사_방_확인_진행_화면은_그대로다(db, seeded, client):
    me = _login(client)
    me.post("/api/contacts/verify-rooms", json={"contact_ids": [seeded["investor"].id]})
    page = me.get(f"/jobs/{_jobs(db)[0].id}").text
    assert "카톡방 후보 찾기" not in page
    assert "내 투자사로" in page


# ── 7. 스타트업 명단의 방은 투자사 방이 아니다 ──────────────────────────────

def test_확정한_스타트업_방이_투자사_방으로_읽히지_않는다(db, seeded, client):
    """스타트업 명단도 같은 표(`vc_contacts`)에 산다. 그 줄의 방 이름 · 회사명을
    투자사 쪽으로 세면, 확정해 둔 대표 방이 월간 발송 쪽 맞추기에서도, 이 명단
    쪽 맞추기에서도 **투자사 방으로 걸러진다**."""
    from app.models import IrCompany
    from app.services import room_match

    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A])
    _confirm(me, seeded["noroom"], ROOM_A)
    db.expire_all()

    known = room_match.investor_rooms(db)
    assert room_match.investor_reason(ROOM_A, "가나다랩스", known) == ""
    assert room_match.key("차카타랩스") not in known.firms
    # 투자사 줄은 그대로 센다(감춘 투자사 줄도 — 방은 여전히 투자사 방이다).
    assert room_match.key("다라마벤처스") in known.firms

    company = IrCompany(name="가나다랩스", contract_status="paid")
    db.add(company)
    db.commit()
    kept, dropped = room_match.drop_investor_rooms([ROOM_A], company.name, known)
    assert kept == [ROOM_A] and dropped == []


# ── 8. 브라우저 쪽 ──────────────────────────────────────────────────────────

def test_찾기_확정_직접_적기는_node_로_잰다():
    """`tests/js/startup_room_pick_test.js` — 확정은 누른 줄 · 누른 글자 그대로,
    찾기는 줄 번호 없이(서버가 고른다), 직접 적기는 수정창과 같은 길."""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 검사 생략 "
                    "(호스트에서 `node tests/js/startup_room_pick_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "startup_room_pick_test.js"
    done = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


def test_가짜_화면이_실제_화면과_같은_이름을_쓴다(db, seeded, client):
    from pathlib import Path

    me = _login(client)
    _found(db, me, seeded["noroom"], [ROOM_A])
    page = me.get("/startup/rooms").text
    js = (Path(__file__).resolve().parent / "js" / "startup_room_pick_test.js"
          ).read_text(encoding="utf-8")
    for token in ("room-pick-table", "room-confirm", "data-room", "room-direct",
                  "room-direct-save", "room-search-btn", "data-count",
                  "room-verify-btn", "data-ids", "room-pick-error"):
        assert token in page, f"템플릿에서 {token} 가 사라졌다"
        assert token in js, f"가짜 화면이 {token} 를 안 쓴다"
    assert "startup_room_pick.js" in page
