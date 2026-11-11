"""IR 기업 현황 › IR 기업현황 탭의 **안내 카톡** · **카톡방 찾기·확인** (11/11).

사용자: *"스타트업에 있는 안내 카톡 기능을 IR 기업 현황 메뉴의 IR 기업현황 탭에도
동일하게 있어야 함. 방 매칭도."*

## 여기서 못박는 것

1. **같은 길** — 목록은 `create_send_list`(`MODE_STARTUP_MSG_IR`)가 세운다. 잡 종류도
   스타트업 안내 카톡과 같고(`startup_msg`), 글도 같은 함수가 채운다.
2. **보내는 계정 PC** — 회차는 스타트업 월간 발송의 그 계정 것이고(그 계정 발송기만
   집어간다), 묶음은 누른 사람 것이라 누른 사람이 [발송 시작] 을 누른다. 남은 못 건드린다.
3. **막는 규칙** — 딜소개 불가 · 폐업 · 이어 둔 스타트업 줄 검토중단 · 확인 안 된 방은
   미리보기에서 빠지고, 목록 만들기는 통째로 거절한다(주소로 찔러도).
4. **이 문구를 언제 받았나** — 이 기업 + 이어 둔 스타트업 줄(거꾸로도) 센다.
5. **카톡방 찾기·확인** — 한 잡에 대조 · 찾기가 섞이고, 보내는 계정 것이며, 결과는
   **기업 줄의 방 칸에만** 적힌다.
6. **맞추기 화면** — 고른 기업으로 열 수 있고, 메뉴가 켜져 있으면 누구나 보고 저장한다.

이름 · 회사명 · 방 제목은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

ROOM_OK = "홍길동 대표 가나다랩스 , 강민준 팀장"
ROOM_OK2 = "김철수 대표 라마바랩스"
ROOM_TYPED = "이영희 대표 사아자"
ROOM_LINKED = "이영희 대표님 사아자랩스 , 강민준 팀장"     # 팀원 카톡 쪽 제목


@pytest.fixture()
def seeded(db, users):
    """u2(윤서아)가 스타트업 월간 발송 계정 — 그 PC 에서 나간다. u1(강민준)이 누른다."""
    from app.models import IrCompany, SheetOwner, User, VcContact
    from app.services import auth as auth_svc, startup_send

    db.add(User(id=3, name="박지훈", phone="01000000003", role="user",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    startup_send.save(db, enabled=True, user_id=2)
    rows = {
        "ok": IrCompany(name="가나다랩스", contact_name="홍길동 대표", contract_status="paid",
                        kakao_room_name=ROOM_OK, room_verified="verified"),
        # 계약을 안 했어도 보낸다 — 안내 카톡은 계약과 상관없다.
        "ok2": IrCompany(name="라마바랩스", contact_name="김철수", contract_status="none",
                         kakao_room_name=ROOM_OK2, room_verified="verified"),
        "typed": IrCompany(name="사아자랩스", contact_name="이영희",
                           kakao_room_name=ROOM_TYPED, room_verified="unverified"),
        "noroom": IrCompany(name="(주)차카타랩스", contact_name="최수진"),
        "notfound": IrCompany(name="다다랩스", kakao_room_name="옛 방 이름",
                              room_verified="not_found"),
        "blocked": IrCompany(name="파하랩스", contract_status="blocked",
                             kakao_room_name="파하랩스 방", room_verified="verified"),
        "closed": IrCompany(name="가가랩스 [26년 3월 폐업함]", contract_status="paid",
                            kakao_room_name="가가랩스 방", room_verified="verified"),
        "paused": IrCompany(name="나나랩스", kakao_room_name="나나랩스 방",
                            room_verified="verified"),
    }
    db.add_all(rows.values())
    db.add(SheetOwner(label="스타트업 · 강민준", user_id=1, layout="startup", is_hidden=1))
    db.flush()
    # 이어 둔 스타트업 명단 줄 — 하나는 검토중단, 하나는 그 팀원 카톡 기준 방 이름이 있다.
    rows["paused_link"] = VcContact(user_id=1, source_sheet="스타트업 · 강민준",
                                    name="정하늘", firm="나나랩스", status="paused",
                                    ir_company_id=rows["paused"].id)
    rows["typed_link"] = VcContact(user_id=1, source_sheet="스타트업 · 강민준",
                                   name="이영희", firm="사아자랩스", status="active",
                                   kakao_room_name=ROOM_LINKED, room_verified="unverified",
                                   ir_company_id=rows["typed"].id)
    db.add_all([rows["paused_link"], rows["typed_link"]])
    db.commit()
    return rows


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def _preview(client, ids, topic="startup_msg_free", days=30, body=""):
    return client.post("/api/ir-msg/preview", json={
        "topic": topic, "body": body, "company_ids": ids, "days": days})


def _send(client, ids, topic="startup_msg_free", days=30):
    return client.post("/api/ir-msg/send", json={
        "topic": topic, "company_ids": ids, "days": days, "title": "검사 회차"})


def _jobs(db, kind=None):
    from sqlalchemy import select

    from app.models import SendJob

    db.expire_all()
    q = select(SendJob).order_by(SendJob.id)
    if kind:
        q = q.where(SendJob.kind == kind)
    return db.execute(q).scalars().all()


def _ids(seeded, *keys):
    return [seeded[k].id for k in keys]


# ── 1. 미리보기 — 고른 곳마다 나갈 글 또는 빠지는 까닭 ─────────────────────────

def test_미리보기가_보낼_곳과_빠지는_까닭을_가른다(db, seeded, client):
    me = _login(client)
    res = _preview(me, _ids(seeded, "ok", "typed", "noroom", "blocked", "closed", "paused"))
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["sender"] == "윤서아"
    assert d["ready_ids"] == [seeded["ok"].id]
    reasons = {s["company_id"]: s["reason"] for s in d["skipped"]}
    assert reasons[seeded["blocked"].id] == "딜소개 불가"
    assert reasons[seeded["closed"].id] == "폐업"
    assert "검토중단" in reasons[seeded["paused"].id]
    assert reasons[seeded["typed"].id] == "확인 안 됨"
    assert reasons[seeded["noroom"].id] == "카톡방 이름 없음"

    [p] = d["previews"]
    assert p["room"] == ROOM_OK
    # 채우는 함수는 스타트업 화면과 같다 — `대표` 꼬리는 떼고, 보내는 사람은 **누른 사람**.
    assert p["message"].startswith("안녕하세요 대표님.")
    assert "ASSET  강민준 팀장입니다" in p["message"]
    assert "윤서아" not in p["message"]


def test_대표명과_회사명_채움말은_기업_줄에서_온다(db, seeded, client):
    me = _login(client)
    d = _preview(me, _ids(seeded, "ok"), topic="startup_msg_progress",
                 body="{대표명} 대표님 · {회사명}").json()
    assert d["previews"][0]["message"] == "홍길동 대표님 · 가나다랩스"


def test_아무것도_안_고르면_지어낸_줄로_글만_보여_준다(db, seeded, client):
    d = _preview(_login(client), []).json()
    assert d["sample"] is True and d["ready_ids"] == []
    assert d["previews"][0]["firm"] == "○○기업"
    assert not _jobs(db)


# ── 2. 목록 — 같은 길 · 보내는 계정 PC ────────────────────────────────────────

def test_대기_목록은_보내는_계정_회차로_서고_묶음은_누른_사람_것이다(db, seeded, client):
    from app.models import STARTUP_MSG_KIND, DealBatch

    me = _login(client)
    res = _send(me, _ids(seeded, "ok", "ok2"))
    assert res.status_code == 200, res.text
    assert res.json()["sender"] == "윤서아"
    [job] = _jobs(db)
    assert job.kind == STARTUP_MSG_KIND and job.status == "draft"
    assert job.topic == "startup_msg_free"
    assert job.user_id == 2, "누른 사람 PC 로 섰다 — 그 카톡에는 이 방 제목이 없을 수 있다"
    assert db.get(DealBatch, job.batch_id).user_id == 1
    assert res.json()["href"] == f"/jobs/{job.id}"
    items = sorted(job.items, key=lambda i: i.ir_company_id)
    assert [i.ir_company_id for i in items] == sorted(_ids(seeded, "ok", "ok2"))
    assert all(i.contact_id is None for i in items)
    assert {i.room_name for i in items} == {ROOM_OK, ROOM_OK2}
    assert all("강민준 팀장" in i.message for i in items)


@pytest.mark.parametrize("key, why", [("blocked", "딜소개 불가"), ("closed", "폐업"),
                                      ("paused", "검토중단"), ("typed", "확인 안 됨"),
                                      ("noroom", "카톡방 이름 없음")])
def test_섞인_곳이_있으면_통째로_거절한다(db, seeded, client, key, why):
    res = _send(_login(client), _ids(seeded, "ok", key))
    assert res.status_code == 400
    assert why in res.json()["detail"]
    assert not _jobs(db)


def test_주소로_찔러도_같은_길이_막는다(db, seeded, client):
    """`create_send_list` 자체가 막는다 — 화면 라우터를 건너뛰어도 같은 판정이다."""
    me = _login(client)
    for key in ("blocked", "closed", "paused", "typed"):
        res = me.post("/api/deals/send", json={
            "mode": "startup_msg_ir", "topic": "startup_msg_quote",
            "contact_ids": [seeded[key].id]})
        assert res.status_code == 400, key
    assert not _jobs(db)
    # 딜 제안 화면의 미리보기는 이 글을 짓지 않는다(짓는 자리는 그 화면 하나).
    res = me.post("/api/deals/preview", json={"mode": "startup_msg_ir", "contact_ids": []})
    assert res.status_code == 400


def test_보내는_계정이_없으면_세우지_않는다(db, seeded, client):
    from app.services import startup_send

    startup_send.save(db, enabled=False, user_id=2)
    me = _login(client)
    res = _send(me, _ids(seeded, "ok"))
    assert res.status_code == 400 and "보내는 계정" in res.json()["detail"]
    res = me.post("/api/ir-rooms/check", json={"company_ids": _ids(seeded, "noroom")})
    assert res.status_code == 400
    assert not _jobs(db)
    page = me.get("/companies").text
    assert 'data-testid="irm-no-sender"' in page
    assert 'class="irm-pick"' not in page, "보낼 수 없는데 고르는 칸이 섰다"


def test_누른_사람이_시작하고_보내는_계정_발송기만_집어간다(db, seeded, client):
    me = _login(client)
    job_id = _send(me, _ids(seeded, "ok")).json()["job_id"]

    page = me.get(f"/jobs/{job_id}").text
    assert "조회만 가능합니다" not in page
    assert "윤서아 계정 PC 의 카톡에서 나갑니다" in page
    assert 'href="/companies"' in page

    assert me.post(f"/api/jobs/{job_id}/start").status_code == 200, "세운 사람이 못 누른다"
    mine = me.get("/api/agent/poll", params={"kinds": "startup_msg"},
                  headers=auth(DEMO_TOKEN))
    assert mine.status_code == 204, "누른 사람 PC 발송기가 집어갔다"
    theirs = me.get("/api/agent/poll", params={"kinds": "startup_msg"},
                    headers=auth(OTHER_TOKEN)).json()
    assert theirs["job_id"] == job_id
    assert [i["room_name"] for i in theirs["items"]] == [ROOM_OK]


def test_남이_세운_회차는_못_건드린다(db, seeded, client):
    job_id = _send(_login(client), _ids(seeded, "ok")).json()["job_id"]
    other = _login(client, phone="01000000003")
    assert other.post(f"/api/jobs/{job_id}/start").status_code == 404
    assert other.post(f"/api/jobs/{job_id}/cancel").status_code == 404
    assert other.get(f"/api/jobs/{job_id}").status_code == 404


# ── 3. 이 문구를 언제 받았나 ─────────────────────────────────────────────────

def _mark_sent(db, job_id):
    from app.clock import now_iso
    from app.models import SendJob

    job = db.get(SendJob, job_id)
    for item in job.items:
        item.status, item.sent_at = "sent", now_iso()
    job.status = "done"
    db.commit()


def test_최근_받은_곳은_빠지고_0일이면_다시_보낸다(db, seeded, client):
    me = _login(client)
    _mark_sent(db, _send(me, _ids(seeded, "ok")).json()["job_id"])

    d = _preview(me, _ids(seeded, "ok")).json()
    assert d["ready_ids"] == []
    assert "이 문구를 받음" in d["skipped"][0]["reason"]
    assert d["skipped"][0]["last_date"]
    assert _send(me, _ids(seeded, "ok")).status_code == 400
    # 다른 문구는 상관없다 · 0 이면 빼지 않는다.
    assert _preview(me, _ids(seeded, "ok"), topic="startup_msg_quote").json()["ready_ids"]
    assert _preview(me, _ids(seeded, "ok"), days=0).json()["ready_ids"] == _ids(seeded, "ok")


def test_이어_둔_스타트업_줄이_받은_것도_세고_거꾸로도_센다(db, seeded, client):
    from app.clock import now_iso
    from app.models import STARTUP_MSG_KIND, SendItem, SendJob, User
    from app.services import startup_outreach

    seeded["typed"].room_verified = "verified"
    db.commit()
    # 스타트업 화면에서 그 줄에 같은 문구가 나갔다.
    job = SendJob(user_id=1, kind=STARTUP_MSG_KIND, topic="startup_msg_free", status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=seeded["typed_link"].id, room_name=ROOM_LINKED,
                    message="x", status="sent", sent_at=now_iso()))
    db.commit()
    d = _preview(_login(client), _ids(seeded, "typed")).json()
    assert d["ready_ids"] == []
    assert "강민준 님 명단에서" in d["skipped"][0]["reason"]

    # 거꾸로 — IR 기업현황 탭에서 나간 것을 스타트업 화면이 센다.
    db.delete(db.get(SendItem, job.items[0].id))
    db.commit()
    me = _login(client)
    _mark_sent(db, _send(me, _ids(seeded, "typed")).json()["job_id"])
    topic = startup_outreach.topic_of("startup_msg_free")
    info = startup_outreach.last_sent(db, [seeded["typed_link"]], topic)[seeded["typed_link"].id]
    assert startup_outreach.recent_reason(info, 30).startswith("IR 기업현황 탭에서 ")
    view = startup_outreach.rows(db, db.get(User, 1), topic, 30)
    row = next(r for r in view["rows"] if r["id"] == seeded["typed_link"].id)
    assert row["last_from"] == "IR 기업현황 탭"


# ── 4. 카톡방 찾기·확인 — 기업 줄 ─────────────────────────────────────────────

def test_찾기_확인은_보내는_계정_잡_하나에_대조와_찾기를_섞는다(db, seeded, client):
    me = _login(client)
    res = me.post("/api/ir-rooms/check", json={"company_ids": _ids(
        seeded, "ok", "typed", "noroom", "notfound", "blocked", "closed")})
    assert res.status_code == 200, res.text
    d = res.json()
    [job] = _jobs(db)
    assert (job.kind, job.status, job.user_id) == ("verify_room", "queued", 2)
    assert (d["exact"], d["search"], d["skipped"]) == (1, 2, 3)
    # 진행 화면을 못 보는 사람은 맞추기 화면으로 — 고른 기업으로 연다.
    assert d["href"] == ""
    assert d["rooms_href"].startswith("/deals/startup-ir/rooms?ids=")
    rooms = {i.ir_company_id: i.room_name for i in job.items}
    assert rooms == {seeded["typed"].id: ROOM_TYPED, seeded["noroom"].id: "",
                     seeded["notfound"].id: ""}
    assert all(i.message == "" and i.contact_id is None for i in job.items)

    got = me.get("/api/agent/poll", params={"kinds": "verify_room"},
                 headers=auth(OTHER_TOKEN)).json()
    by_id = {i["id"]: i for i in got["items"]}
    exact = by_id[next(i.id for i in job.items if i.ir_company_id == seeded["typed"].id)]
    assert exact["query"] == ROOM_TYPED and exact["exact"] is True and "target" not in exact
    search = by_id[next(i.id for i in job.items if i.ir_company_id == seeded["noroom"].id)]
    assert search["query"] == "차카타랩스" and search["target"] == "company"


def test_결과는_기업_줄의_방_칸에만_적힌다(db, seeded, client):
    """대조가 맞으면 확인됨(+ 카톡 연결 여부 O) · 찾은 제목은 후보로만. 이어 둔 스타트업
    명단 줄의 방 이름 · 확인 표시는 그 팀원 카톡 기준이라 그대로다."""
    from app.services import room_match

    me = _login(client)
    me.post("/api/ir-rooms/check", json={"company_ids": _ids(seeded, "typed", "noroom")})
    [job] = _jobs(db)
    item_of = {i.ir_company_id: i.id for i in job.items}

    def report(company, **body):
        res = me.post(f"/api/agent/items/{item_of[seeded[company].id]}/result",
                      headers=auth(OTHER_TOKEN), json=body)
        assert res.status_code == 200, res.text

    report("typed", status="sent", verify_result="verified", found_room=ROOM_TYPED,
           candidates=[ROOM_TYPED])
    report("noroom", status="failed", verify_result="ambiguous",
           candidates=["최수진 대표 차카타랩스", "차카타랩스 투자유치방"])
    db.expire_all()

    typed, noroom, link = seeded["typed"], seeded["noroom"], seeded["typed_link"]
    assert (typed.kakao_room_name, typed.room_verified, typed.kakao_joined) == (
        ROOM_TYPED, "verified", "O")
    assert room_match.candidates(typed)["rooms"] == []
    assert noroom.kakao_room_name is None and noroom.room_verified == "unverified"
    assert room_match.candidates(noroom)["rooms"] == ["최수진 대표 차카타랩스", "차카타랩스 투자유치방"]
    assert (link.kakao_room_name, link.room_verified) == (ROOM_LINKED, "unverified")
    assert link.room_candidates is None


def test_다른_제목이_걸리면_대조는_못_찾음이고_이름은_그대로다(db, seeded, client):
    me = _login(client)
    me.post("/api/ir-rooms/check", json={"company_ids": _ids(seeded, "typed")})
    [job] = _jobs(db)
    me.post(f"/api/agent/items/{job.items[0].id}/result", headers=auth(OTHER_TOKEN),
            json={"status": "sent", "verify_result": "verified",
                  "found_room": ROOM_TYPED + "랩스", "candidates": [ROOM_TYPED + "랩스"]})
    db.expire_all()
    assert seeded["typed"].kakao_room_name == ROOM_TYPED
    assert seeded["typed"].room_verified == "not_found"


def test_찾을_곳이_없으면_잡을_안_세운다(db, seeded, client):
    res = _login(client).post("/api/ir-rooms/check",
                              json={"company_ids": _ids(seeded, "ok", "blocked", "closed")})
    assert res.status_code == 400 and "찾을 곳이 없습니다" in res.json()["detail"]
    assert not _jobs(db)


def test_관리자는_진행_화면으로_간다(db, seeded, client):
    from app.models import User

    db.get(User, 1).role = "admin"
    db.commit()
    res = _login(client).post("/api/ir-rooms/check", json={"company_ids": _ids(seeded, "noroom")})
    job = _jobs(db)[0]
    assert res.json()["href"] == f"/jobs/{job.id}"
    page = client.get(f"/jobs/{job.id}").text
    assert "카톡방 찾기·확인" in page
    assert f'/deals/startup-ir/rooms?ids={seeded["noroom"].id}' in page


# ── 5. 맞추기 화면 — 고른 기업으로 · 메뉴가 켜져 있으면 누구나 ────────────────

def test_맞추기_화면을_고른_기업으로_열고_저장한다(db, seeded, client):
    from app.clock import now_iso
    from app.services import room_match

    room_match.save_candidates(seeded["noroom"], ["최수진 대표 차카타랩스"], at=now_iso(),
                               query="차카타랩스")
    db.commit()
    me = _login(client)            # 보내는 계정이 아니다
    ids = f'{seeded["noroom"].id},{seeded["ok2"].id}'
    page = me.get(f"/deals/startup-ir/rooms?ids={ids}")
    assert page.status_code == 200
    body = page.text
    assert "(주)차카타랩스" in body and "라마바랩스" in body
    assert "가나다랩스" not in body, "고르지 않은 기업이 섰다"
    assert 'data-room="최수진 대표 차카타랩스"' in body
    assert "윤서아 계정 PC" in body
    # 그 계정만의 것은 안 선다(월간 발송 표 · 옛 [카톡에서 방 찾기]).
    assert 'action="/deals/startup-ir/rooms/search"' not in body
    assert 'href="/deals/startup-ir">' not in body

    res = me.post("/deals/startup-ir/rooms", follow_redirects=False, data={
        "ids": ids, "company_ids": [seeded["noroom"].id, seeded["ok"].id],
        "rooms": ["최수진 대표 차카타랩스", "아무 방"]})
    assert res.status_code == 303
    assert f"ids={ids}" in res.headers["location"]
    db.expire_all()
    assert seeded["noroom"].kakao_room_name == "최수진 대표 차카타랩스"
    # 카톡 후보 그대로 골랐다 — 확인됨(`room_match.verify_picked`).
    assert seeded["noroom"].room_verified == "verified"
    assert seeded["ok"].kakao_room_name == ROOM_OK, "화면에 없던 기업이 저장됐다"


def test_맞추기_기본_화면은_그대로_계약_기업이다(db, seeded, client):
    body = _login(client).get("/deals/startup-ir/rooms").text
    assert "가나다랩스" in body
    assert "라마바랩스" not in body, "기본 화면에 계약 안 한 기업이 섰다"


# ── 6. 화면 ─────────────────────────────────────────────────────────────────

def test_IR_기업현황_탭에_고르는_칸과_안내_카톡_칸이_선다(db, seeded, client):
    page = _login(client).get("/companies").text
    assert 'id="irm-panel"' in page and 'data-sender="윤서아"' in page
    assert "윤서아 계정 PC</b>의 카톡에서 나갑니다" in page
    assert page.count('class="irm-pick"') == len([k for k in seeded if not k.endswith("_link")])
    assert 'id="irm-pick-all"' in page
    assert 'style="--stick-a:32px; --stick-b:68px"' in page
    for key in ("startup_msg_progress", "startup_msg_quote", "startup_msg_free"):
        assert f'data-topic="{key}"' in page
    assert 'id="irm-room-check-btn"' in page and 'id="irm-rooms-link"' in page
    assert "ir_msg.js" in page


def test_가짜_화면이_실제_화면과_같은_이름을_쓴다(db, seeded, client):
    from pathlib import Path

    page = _login(client).get("/companies").text
    js = (Path(__file__).resolve().parent / "js" / "ir_msg_test.js").read_text(encoding="utf-8")
    for token in ("irm-panel", "irm-fold", "irm-count", "irm-pick-all", "irm-pick",
                  "irm-body", "irm-days", "irm-title", "irm-when", "irm-preview-btn",
                  "irm-send-btn", "irm-room-check-btn", "irm-rooms-link", "irm-error",
                  "irm-preview-list", "irm-skipped-list", "irm-topic", "data-sender",
                  "data-rooms-href", "data-body", "data-title", "co-table"):
        assert token in page, f"템플릿에서 {token} 가 사라졌다"
        assert token in js, f"가짜 화면이 {token} 를 안 쓴다"


def test_브라우저_쪽은_node_로_잰다():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — `node tests/js/ir_msg_test.js`")
    js = Path(__file__).resolve().parent / "js" / "ir_msg_test.js"
    done = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


def test_발송기_판을_올리지_않았다():
    """새 잡 종류가 없다 — 지금 발송기가 이미 밝히는 종류다."""
    import agent.main as agent_main
    from app.models import STARTUP_MSG_KIND

    assert STARTUP_MSG_KIND in agent_main.SUPPORTED_KINDS
    assert "verify_room" in agent_main.SUPPORTED_KINDS
