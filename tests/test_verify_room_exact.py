"""[방 연결 확인] — 적어 둔 방 이름을 **바꾸지 않고**, 글자까지 같을 때만 확인됨.

팀원이 알린 두 가지(11/05):

1. 카톡 설정에서 복사해 넣은 방 이름이, 확인을 돌리자 **실제로 있는 다른 방
   이름**으로 바뀌고 `확인됨` 이 됐다. 발송기는 검색어가 든 제목을 넉넉히 모으고
   (이름만으로 한 번 더 찾기 · 맨 위 방 열기) **하나만 걸리면** `verified` 로
   올렸고, 서버는 그 제목(`found_room`)으로 방 이름 칸을 덮었다.
2. 동명이인은 방 이름을 아무리 또렷하게 넣어도 회사명이 방 이름에 없으면 확인에
   싣지도 않았다. 전체 목록에서 돌리자 성함과 방 이름 짝이 뒤섞였다 — 건마다
   남의 방 제목이 `found_room` 으로 올라와 그대로 덮였다.

여기 이름 · 회사 · 방 제목은 모두 지어낸 값이다.
"""
from __future__ import annotations

import unicodedata

from sqlalchemy import select

from app.models import SendItem, SendJob, VcContact

from .conftest import DEMO_TOKEN, auth


def _row(db, name, firm, room, title="심사역"):
    row = VcContact(user_id=1, name=name, title=title, firm=firm,
                    channel_kakao=1, kakao_room_name=room,
                    room_verified="unverified", connect_stage="connected",
                    status="active")
    db.add(row)
    db.commit()
    return row


def _queue(client, ids=None):
    r = client.post("/api/contacts/verify-rooms",
                    json={"contact_ids": ids} if ids else {})
    assert r.status_code == 200, r.text
    return r.json()


def _claim(client):
    r = client.get("/api/agent/poll?kinds=verify_room", headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _report(client, item_id, verdict, found_room=None, candidates=None):
    body = {"status": "sent" if verdict == "verified" else "failed",
            "verify_result": verdict}
    if found_room is not None:
        body["found_room"] = found_room
    if candidates is not None:
        body["candidates"] = candidates
    r = client.post(f"/api/agent/items/{item_id}/result", json=body,
                    headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, r.text


def _fresh(db, row_id):
    db.expire_all()
    return db.get(VcContact, row_id)


# ── 버그 1 — 비슷한 다른 방 하나가 걸려도 방 이름을 안 바꾸고, 확인됨도 아니다 ──

def test_a_similar_room_found_first_does_not_rename_or_verify(logged_in, db, users):
    """검색 결과 맨 위에 **비슷한 다른 방**이 왔다(발송기는 하나만 걸려 verified)."""
    mine = "가나다 홍길동 심사역님 딜 공유방"
    other = "가나다 홍길동 심사역님 딜 공유방 2기"
    row = _row(db, "홍길동", "가나다벤처스", mine)
    _queue(logged_in)
    [item] = _claim(logged_in)

    _report(logged_in, item["id"], "verified", found_room=other, candidates=[other])

    got = _fresh(db, row.id)
    assert got.kakao_room_name == mine, "확인이 적어 둔 방 이름을 바꿨다"
    assert got.room_verified != "verified"
    sent = db.get(SendItem, item["id"])
    assert sent.room_name == mine
    assert sent.status == "failed"
    # 찾은 제목은 **참고로만** 남긴다 — 사람이 보고 고칠 수 있게.
    assert other in (sent.error or "")


def test_a_room_found_by_name_only_does_not_replace_the_typed_name(logged_in, db, users):
    """적어 둔 이름으로 못 찾고 **이름만으로** 다시 찾아 나온 남의 방(단체방)."""
    mine = "홍길동 심사역님 가나다벤처스 딜방"
    group = "라마바 투자 네트워크 (홍길동 외 12명)"
    row = _row(db, "홍길동", "가나다벤처스", mine)
    _queue(logged_in)
    [item] = _claim(logged_in)

    _report(logged_in, item["id"], "verified", found_room=group, candidates=[group])

    got = _fresh(db, row.id)
    assert (got.kakao_room_name, got.room_verified) == (mine, "not_found")


def test_the_exact_title_is_verified_and_the_name_is_kept(logged_in, db, users):
    """글자까지 같으면 확인됨 — 앞뒤 공백 · 자모 조합 형태(NFD)만 봐준다."""
    mine = "홍길동 심사역님 가나다벤처스 딜방"
    row = _row(db, "홍길동", "가나다벤처스", mine)
    _queue(logged_in)
    [item] = _claim(logged_in)

    shown = unicodedata.normalize("NFD", mine) + " "
    _report(logged_in, item["id"], "verified", found_room=shown, candidates=[shown])

    got = _fresh(db, row.id)
    assert (got.kakao_room_name, got.room_verified) == (mine, "verified")
    assert db.get(SendItem, item["id"]).status == "sent"


def test_one_exact_title_among_several_is_verified(logged_in, db, users):
    """발송기는 둘이 걸려 `ambiguous` 라 했지만, 글자까지 같은 것은 하나뿐이다."""
    mine = "홍길동 심사역님 가나다벤처스 딜방"
    other = "홍길동 대표님 다라인베스트 딜방"
    row = _row(db, "홍길동", "가나다벤처스", mine)
    _queue(logged_in)
    [item] = _claim(logged_in)

    _report(logged_in, item["id"], "ambiguous", candidates=[other, mine])

    got = _fresh(db, row.id)
    assert (got.kakao_room_name, got.room_verified) == (mine, "verified")


def test_the_same_exact_title_twice_stays_ambiguous(logged_in, db, users):
    mine = "홍길동 심사역님 가나다벤처스 딜방"
    row = _row(db, "홍길동", "가나다벤처스", mine)
    _queue(logged_in)
    [item] = _claim(logged_in)

    _report(logged_in, item["id"], "ambiguous", candidates=[mine, mine])

    assert _fresh(db, row.id).room_verified == "ambiguous"


def test_a_verdict_without_titles_is_the_exact_check_and_is_kept(logged_in, db, users):
    """후보 없이 온 판정은 발송기의 정확 대조(`sender.verify_room`) 결과다."""
    mine = "홍길동 심사역님 가나다벤처스 딜방"
    row = _row(db, "홍길동", "가나다벤처스", mine)
    _queue(logged_in)
    [item] = _claim(logged_in)

    _report(logged_in, item["id"], "verified")

    got = _fresh(db, row.id)
    assert (got.kakao_room_name, got.room_verified) == (mine, "verified")


def test_a_name_edited_while_the_job_waited_is_not_marked(logged_in, db, users):
    """잡을 세운 뒤 방 이름을 고쳤다 — 옛 이름의 확인 결과를 새 이름에 달지 않는다."""
    mine = "홍길동 심사역님 가나다벤처스 딜방"
    row = _row(db, "홍길동", "가나다벤처스", mine)
    _queue(logged_in)
    [item] = _claim(logged_in)
    row = _fresh(db, row.id)
    row.kakao_room_name = "홍길동 심사역님 새 딜방"
    db.commit()

    _report(logged_in, item["id"], "verified", found_room=mine, candidates=[mine])

    got = _fresh(db, row.id)
    assert (got.kakao_room_name, got.room_verified) == ("홍길동 심사역님 새 딜방",
                                                        "unverified")


def test_the_search_uses_the_typed_room_name_and_asks_for_an_exact_match(
        logged_in, db, users):
    """검색어는 **적어 둔 방 이름 그대로**다 — 표준 꼴(이름 · 직함 · 회사로 지은
    값)과 같아도 이름+직함으로 바꿔 찾지 않는다. `name` · `firm` 은 안 보낸다 —
    낡은 발송기도 성함으로 다시 찾거나(같은 성함이 든 남의 방) 회사로 좁히지
    (글자까지 같은 방을 버린다) 않는다. 순서(번호)가 아니라 이름을 싣는다."""
    from app.services.room_name import build_room_name

    std = build_room_name("홍길동", "심사역", "가나다벤처스")
    _row(db, "홍길동", "가나다벤처스", std)
    _queue(logged_in)
    [item] = _claim(logged_in)
    assert item["query"] == item["room_name"] == std
    assert "name" not in item and "firm" not in item
    assert item["exact"] is True


# ── 버그 2 — 동명이인 · 전체 목록 ──────────────────────────────────────────────

def _namesakes(db):
    """같은 성함 셋. 방 이름은 또렷하게 다르지만 **회사명은 안 들어 있다.**"""
    return [
        _row(db, "홍길동", "가나다벤처스", "홍길동 이사님 딜 공유방 (판교)", title="이사"),
        _row(db, "홍길동", "다라인베스트", "홍길동 심사역님 딜 공유방 (여의도)"),
        _row(db, "홍길동", "마바캐피탈", "홍길동 팀장님 딜 공유방 (강남)", title="팀장"),
    ]


def test_namesakes_with_distinct_room_names_are_each_checked(logged_in, db, users):
    rows = _namesakes(db)
    body = _queue(logged_in)
    assert body["total"] == 3 and body["conflicts"] == []

    items = _claim(logged_in)
    job = db.get(SendJob, body["job_id"])
    by_item = {i.id: i for i in job.items}
    # 건은 **줄 id** 로 묶여 있고, 실린 방 이름은 그 줄의 것이다.
    assert {(by_item[i["id"]].contact_id, i["room_name"]) for i in items} == {
        (r.id, r.kakao_room_name) for r in rows}

    # 결과를 거꾸로 보고해도 각자 제 줄에 붙는다.
    for i in reversed(items):
        _report(logged_in, i["id"], "verified", found_room=i["room_name"],
                candidates=[i["room_name"]])
    for r in rows:
        got = _fresh(db, r.id)
        assert (got.kakao_room_name, got.room_verified) == (r.kakao_room_name,
                                                            "verified")


def test_namesakes_with_the_same_room_name_are_still_held_back(logged_in, db, users):
    """방 이름까지 같으면 정말로 누가 누구인지 모른다 — 여전히 싣지 않는다."""
    a = _row(db, "홍길동", "가나다벤처스", "홍길동 심사역님 딜 공유방")
    b = _row(db, "홍길동", "다라인베스트", "홍길동 심사역님  딜 공유방 ")
    r = logged_in.post("/api/contacts/verify-rooms", json={"contact_ids": [a.id, b.id]})
    assert r.status_code == 400
    assert _fresh(db, a.id).room_verified == "ambiguous"
    assert _fresh(db, b.id).room_verified == "ambiguous"


def test_whole_list_with_shifted_results_never_swaps_room_names(logged_in, db, users):
    """전체 목록 잡 — 건마다 **바로 앞 건의 방 제목**이 올라온다(검색 결과가 한
    박자 늦게 읽힌 꼴). 예전에는 그 제목으로 덮어 짝이 통째로 밀렸다."""
    rows = _namesakes(db) + [
        _row(db, "김서연", "사아파트너스", "김서연 심사역님 딜방"),
        _row(db, "박준호", "자차벤처스", "박준호 이사님 딜방", title="이사"),
    ]
    body = _queue(logged_in)
    assert body["total"] == len(rows)
    items = _claim(logged_in)

    for prev, cur in zip(items[-1:] + items[:-1], items):
        _report(logged_in, cur["id"], "verified", found_room=prev["room_name"],
                candidates=[prev["room_name"]])

    for r in rows:
        got = _fresh(db, r.id)
        assert got.kakao_room_name == r.kakao_room_name, "남의 방 이름으로 바뀌었다"
        assert got.room_verified == "not_found"
    # 사유가 **다른 줄의 방 이름**이라고 짚는다 — 남의 방 제목을 그대로 싣지 않는다.
    for i in items:
        assert "다른 줄의 방 이름" in (db.get(SendItem, i["id"]).error or "")


def test_a_failure_in_the_middle_does_not_shift_the_rest(logged_in, db, users):
    """중간 한 건이 실패(발송기 예외)해도 나머지는 **제 건 번호**로만 붙는다.

    결과는 순서(몇 번째)가 아니라 건 번호(`item_id` → 그 건의 줄)로 잇는다. 그래서
    실패 뒤로 짝이 한 칸 밀리는 일은 서버에서 생기지 않는다 — 결과를 뒤섞어
    보고해도 같다."""
    rows = [
        _row(db, "홍길동", "가나다벤처스", "홍길동 이사님 딜 공유방 (판교)", title="이사"),
        _row(db, "홍길동", "다라인베스트", "홍길동 심사역님 딜 공유방 (여의도)"),
        _row(db, "김서연", "사아파트너스", "김서연 심사역님 딜방"),
        _row(db, "박준호", "자차벤처스", "박준호 이사님 딜방", title="이사"),
    ]
    _queue(logged_in)
    items = _claim(logged_in)
    assert len(items) == 4
    fail, *rest = items[1:2] + items[:1] + items[2:]
    r = logged_in.post(f"/api/agent/items/{fail['id']}/result",
                       json={"status": "failed", "verify_result": "not_found",
                             "error": "verify error: 시험"}, headers=auth(DEMO_TOKEN))
    assert r.status_code == 200
    for i in reversed(rest):
        _report(logged_in, i["id"], "verified", found_room=i["room_name"],
                candidates=[i["room_name"]])

    by_room = {r.kakao_room_name: r for r in rows}
    for i in items:
        got = _fresh(db, by_room[i["room_name"]].id)
        assert got.kakao_room_name == i["room_name"]
        want = "not_found" if i["id"] == fail["id"] else "verified"
        assert got.room_verified == want


def test_an_old_mac_agent_with_a_late_read_cannot_rename(logged_in, db, users):
    """0.5.0 Mac 발송기는 `exact` 를 모른다 — 검색어 첫 낱말이 든 **앞 건의 결과**를
    읽어 `verified` + 앞 건 방 이름을 보낸다. 서버가 막는다."""
    from app.models import AgentDevice

    device = db.query(AgentDevice).filter_by(user_id=1).first()
    device.sender, device.agent_version = "kakao_mac", "0.5.0"
    db.commit()
    first = _row(db, "홍길동", "가나다벤처스", "딜방 홍길동 심사역님")
    second = _row(db, "김서연", "다라인베스트", "딜방 김서연 심사역님")
    _queue(logged_in)
    a, b = _claim(logged_in)
    _report(logged_in, a["id"], "verified", found_room=a["room_name"],
            candidates=[a["room_name"]])
    _report(logged_in, b["id"], "verified", found_room=a["room_name"],
            candidates=[a["room_name"]])
    assert (_fresh(db, first.id).room_verified, _fresh(db, second.id).room_verified) == (
        "verified", "not_found")
    assert _fresh(db, second.id).kakao_room_name == "딜방 김서연 심사역님"
    # Mac 의 '제목 없는 verified' 는 글자까지 견준 판정이라 그대로 믿는다.
    _queue(logged_in, [second.id])
    [again] = _claim(logged_in)
    _report(logged_in, again["id"], "verified")
    assert _fresh(db, second.id).room_verified == "verified"


def test_an_old_windows_agent_bare_verified_is_not_trusted(logged_in, db, users):
    """0.11.0 보다 낡은 Windows 발송기의 `verify_room` 은 무조건 verified 였다."""
    from app.models import AgentDevice

    device = db.query(AgentDevice).filter_by(user_id=1).first()
    device.sender, device.agent_version = "kakao_windows", "0.10.0"
    db.commit()
    row = _row(db, "홍길동", "가나다벤처스", "홍길동 심사역님 딜방")
    _queue(logged_in)
    [item] = _claim(logged_in)
    _report(logged_in, item["id"], "verified")
    assert _fresh(db, row.id).room_verified == "not_found"
    assert "대조하지 못합니다" in (db.get(SendItem, item["id"]).error or "")


def test_the_setup_test_room_check_is_exact_too(logged_in, db, users):
    """담당자 없는 시험 확인(`/setup`)도 같은 규칙 — 비슷한 방은 확인됨이 아니다."""
    job = SendJob(user_id=1, kind="verify_room", status="running", total=1)
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, room_name="시험 딜방", message="", status="pending")
    db.add(item)
    db.commit()

    _report(logged_in, item.id, "verified", found_room="시험 딜방 (보관)",
            candidates=["시험 딜방 (보관)"])
    db.expire_all()
    got = db.get(SendItem, item.id)
    assert (got.status, got.room_name) == ("failed", "시험 딜방")


# ── 발송기 — 서버가 `exact` 를 붙인 건은 글자까지 같은 제목만 센다 (0.11.14) ──

class _Client:
    def __init__(self):
        self.items = []

    def job_state(self, job_id):
        return {"canceled": False, "canceled_items": []}

    def report_item(self, item_id, status, error=None, screenshot_b64=None,
                    verify_result=None, found_room=None, candidates=None):
        self.items.append({"status": status, "verify_result": verify_result,
                           "found_room": found_room, "candidates": candidates})

    def report_job(self, job_id, status):
        pass


class _Sender:
    """`discover_rooms` 는 넉넉히(검색어가 든 제목), `verify_room` 은 글자까지."""

    def __init__(self, found, exact_titles=()):
        self.found = found
        self.exact_titles = list(exact_titles)

    def discover_rooms(self, query, marker="", **_):
        return list(self.found.get(query, []))

    def verify_room(self, room_name):
        hits = [t for t in self.exact_titles if t == room_name]
        return "verified" if len(hits) == 1 else "ambiguous" if hits else "not_found"


def _agent_verify(sender, **extra):
    import agent.main as agent_main

    client = _Client()
    item = {"id": 1, "room_name": "홍길동 심사역님 딜방", "query": "홍길동 심사역님 딜방",
            "name": "홍길동", **extra}
    agent_main.process_verify_job(
        client, sender, {"job_id": 9, "items": [item]},
        {"verify_delay_min_sec": 0, "verify_delay_max_sec": 0, "room_marker": ""})
    return client.items[0]


def test_agent_does_not_verify_a_single_similar_title_when_exact_is_asked():
    other = "홍길동 심사역님 딜방 2기"
    got = _agent_verify(_Sender({"홍길동 심사역님 딜방": [other]}), exact=True)
    assert got["verify_result"] == "not_found" and got["status"] == "failed"
    assert got["found_room"] is None
    assert got["candidates"] == [other]          # 참고로는 올린다


def test_agent_verifies_the_one_exact_title_among_several():
    mine, other = "홍길동 심사역님 딜방", "홍길동 대표님 다른 딜방"
    got = _agent_verify(_Sender({mine: [other, mine]}), exact=True)
    assert (got["verify_result"], got["found_room"]) == ("verified", mine)


def test_agent_name_only_result_is_not_taken_when_exact_is_asked():
    group = "투자 네트워크 (홍길동 외 12명)"
    got = _agent_verify(_Sender({"홍길동": [group]}), exact=True)
    assert got["verify_result"] == "not_found"
    assert got["found_room"] is None


class _LaggySender:
    """카톡 검색 결과가 **한 박자 늦게** 바뀌는 것 — 늘 **앞 검색어**의 결과를 준다."""

    def __init__(self, boom_on=None):
        self.prev = None
        self.boom_on = boom_on

    def discover_rooms(self, query, marker="", **_):
        if query == self.boom_on:
            self.prev = query
            raise RuntimeError("카톡 창이 사라졌다")
        shown, self.prev = self.prev, query
        return [shown] if shown else []

    def verify_room(self, room_name):
        return "not_found"


def test_agent_never_reports_the_previous_items_room_even_with_a_failure_between():
    """한 칸 밀림 + 중간 실패 — 건마다 앞 건의 방 제목이 보여도 `verified` 로 올리지
    않고, 건 번호는 제 건 그대로다."""
    import agent.main as agent_main

    rooms = ["딜방 가나 홍길동님", "딜방 다라 김서연님", "딜방 마바 박준호님", "딜방 사아 이영희님"]
    client = _Client()
    job = {"job_id": 9, "items": [{"id": 10 + n, "room_name": r, "query": r, "exact": True}
                                  for n, r in enumerate(rooms)]}
    agent_main.process_verify_job(
        client, _LaggySender(boom_on=rooms[1]), job,
        {"verify_delay_min_sec": 0, "verify_delay_max_sec": 0, "room_marker": ""})

    assert [i["verify_result"] for i in client.items] == ["not_found"] * 4
    assert all(i["found_room"] is None for i in client.items)
    assert client.items[1]["status"] == "failed"


def test_agent_asks_the_sender_to_wait_for_this_query_only_when_exact():
    seen = []

    class Recording(_Sender):
        def discover_rooms(self, query, marker="", **kw):
            seen.append(kw)
            return []

    _agent_verify(Recording({}), exact=True)
    _agent_verify(Recording({}))
    assert seen[0] == {"exact": True}
    assert "exact" not in seen[-1]


def test_windows_waits_for_the_whole_room_name_when_exact():
    """Windows — 앞 건의 결과에도 첫 낱말(성함)이 들어 있으면, 첫 낱말만 보고
    넘어가 **앞 건의 목록**을 읽는다. `exact` 면 방 이름 전체가 보일 때까지 기다린다."""
    from tests.test_win_discover_rooms import FakeKakao, FakeWin

    mine = "홍길동 대표 가나다컴퍼니 , 김영희 매니저"
    before = "홍길동 대표 다라마컴퍼니 , 박철수 이사"   # 앞 건(같은 성함)의 방
    timings = {"room_search_wait": 5.0, "room_search_poll": 0}

    late = FakeWin(FakeKakao({mine: [mine]}, stale=[before], stale_reads=4),
                   timings=timings)
    assert late.discover_rooms(mine) == [before], "첫 낱말만 보면 앞 건을 읽는다(옛 동작)"

    late = FakeWin(FakeKakao({mine: [mine]}, stale=[before], stale_reads=4),
                   timings=timings)
    assert late.discover_rooms(mine, exact=True) == [mine]
    late = FakeWin(FakeKakao({mine: [mine]}, stale=[before], stale_reads=4),
                   timings=timings)
    assert late.verify_room(mine) == "verified"


def test_windows_freshness_rule():
    from agent.sender.kakao_windows import result_is_fresh

    before = ["홍길동 대표 다라마컴퍼니"]
    assert result_is_fresh(before, "홍길동 대표 가나다컴퍼니")          # 옛 규칙: 첫 낱말
    assert not result_is_fresh(before, "홍길동 대표 가나다컴퍼니", exact=True)
    assert result_is_fresh(["홍길동  대표 가나다컴퍼니 외 2"], "홍길동 대표 가나다컴퍼니",
                           exact=True)


def test_mac_waits_for_the_whole_room_name_when_exact(monkeypatch):
    from agent.sender import kakao_mac

    scripts = []

    def fake(script, timeout=20):
        scripts.append(script)
        return ""

    class Mac(kakao_mac.KakaoMacSender):
        def _activate(self):
            pass

        def _focus_window(self, title):
            return True

    monkeypatch.setattr(kakao_mac, "_osa", fake)
    mac = Mac({})
    mac.discover_rooms("홍길동 심사역님 딜방", exact=True)
    mac.discover_rooms("홍길동 심사역님 딜방")
    assert 'acc contains "홍길동 심사역님 딜방" then exit repeat' in scripts[0]
    assert 'acc contains "홍길동" then exit repeat' in scripts[1]


def test_agent_without_the_flag_behaves_as_before():
    """서버가 `exact` 를 안 붙인 건(보내는 계정 · 딜 소싱 · 기업 후보 찾기)은 그대로."""
    other = "홍길동 심사역님 딜방 2기"
    got = _agent_verify(_Sender({"홍길동 심사역님 딜방": [other]}))
    assert (got["verify_result"], got["found_room"]) == ("verified", other)
