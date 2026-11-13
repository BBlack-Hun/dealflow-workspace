"""[방 연결 확인] — 적어 둔 카톡방 이름 → 이름+직급 → 이름 (11/12).

사용자: "카톡방 이름으로만 방매칭을 하고 있는 거 같아서… 카톡방 이름(제일 우선) >>>
이름 직급 >>> 이름 이런 식으로 체크를 해야 할 거 같음". 운영에서는 방 이름이 하나도
없는 명단(46줄 중 0줄)이 [방 연결 확인]을 눌러도 잡이 서지 않았다.

여기 이름 · 회사 · 방 제목은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest

from app.models import SendItem, SendJob, SheetOwner, User, VcContact
from app.services import sheet_import, sheet_owner, vc_room_search

from .conftest import DEMO_TOKEN, auth


def _row(db, name, firm, room=None, title="심사역", user_id=1, **kw):
    row = VcContact(user_id=user_id, name=name, title=title, firm=firm,
                    channel_kakao=kw.pop("channel_kakao", 1), kakao_room_name=room,
                    room_verified="unverified",
                    connect_stage=kw.pop("connect_stage", "not_started"),
                    status="active", **kw)
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


def _report(client, item_id, verdict="not_found", candidates=None, error=None):
    body = {"status": "sent" if verdict == "verified" else "failed",
            "verify_result": verdict}
    if candidates is not None:
        body["candidates"] = candidates
    if error is not None:
        body["error"] = error
    r = client.post(f"/api/agent/items/{item_id}/result", json=body,
                    headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, r.text


def _end_round(client, job_id):
    r = client.post(f"/api/agent/jobs/{job_id}/status", json={"status": "done"},
                    headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, r.text
    return r.json()["status"]


def _fresh(db, model, row_id):
    db.expire_all()
    return db.get(model, row_id)


def _search_one(client, db, row, candidates, verdict="ambiguous"):
    """방 이름이 빈 줄 하나를 찾고 결과를 보고한다 — (줄, 건)."""
    _queue(client, [row.id])
    [item] = _claim(client)
    _report(client, item["id"], verdict, candidates=candidates)
    return _fresh(db, VcContact, row.id), _fresh(db, SendItem, item["id"])


# ── 방 이름이 빈 줄도 싣는다 — 이름+직급, 못 찾으면 이름, 여럿이면 회사 ──────────

def test_rows_without_a_room_name_are_searched_by_name_and_title(logged_in, db, users):
    """방 이름이 하나도 없는 명단 — 예전에는 400(`확인할 카톡방 이름이 …`)으로 끝났다."""
    a = _row(db, "홍길동", "가나다벤처스")
    b = _row(db, "김서연", "라마바파트너스", title="")
    body = _queue(logged_in)
    assert (body["total"], body["search"]) == (2, 2)

    items = {i["id"]: i for i in _claim(logged_in)}
    job = db.get(SendJob, body["job_id"])
    by_row = {i.contact_id: items[i.id] for i in job.items}
    # 발송기가 이미 아는 칸뿐이다 — `query` 로 못 찾으면 `name` 으로, 여럿이면 `firm`.
    assert by_row[a.id]["query"] == "홍길동 심사역"
    assert (by_row[a.id]["name"], by_row[a.id]["firm"]) == ("홍길동", "가나다벤처스")
    assert by_row[b.id]["query"] == by_row[b.id]["name"] == "김서연"
    for i in items.values():
        assert i["room_name"] == "" and not i.get("exact")


def test_rows_with_a_room_name_still_check_that_name_first(logged_in, db, users):
    room = "홍길동 심사역님 가나다벤처스 딜방"
    _row(db, "홍길동", "가나다벤처스", room)
    _row(db, "김서연", "라마바파트너스")
    body = _queue(logged_in)
    assert (body["total"], body["search"]) == (2, 1)
    first, second = _claim(logged_in)
    # 대조할 건이 먼저 — 그 건은 적어 둔 이름 그대로, 이름 · 회사는 안 싣는다.
    assert (first["room_name"], first["query"], first["exact"]) == (room, room, True)
    assert "name" not in first and "firm" not in first
    assert second["room_name"] == "" and second["query"] == "김서연 심사역"


def test_rows_that_are_not_kakao_investors_are_not_searched(logged_in, db, users):
    """메일로만 · 문자로만 받는 줄 · 방을 나간 줄 · 이름이 빈 줄 · 스타트업 명단 줄은
    이름으로 찾지 않는다 — 찾을 줄이 없으면 예전처럼 400."""
    _row(db, "홍길동", "가나다벤처스", channel_kakao=0, channel_email=1)
    _row(db, "최하늘", "하늘인베스트", channel_kakao=0, channel_sms=1)
    _row(db, "김서연", "라마바파트너스", connect_stage="left_room")
    _row(db, "", "사아벤처스")
    r = logged_in.post("/api/contacts/verify-rooms", json={})
    assert r.status_code == 400
    assert "메일 · 문자로만 받지 않는" in r.json()["detail"]

    db.add(SheetOwner(label="스타트업 명단", user_id=1, layout="startup", is_hidden=1))
    db.commit()
    _row(db, "박준호", "자차랩스", source_sheet="스타트업 명단")
    r = logged_in.post("/api/contacts/verify-rooms", json={})
    assert r.status_code == 400
    assert db.query(SendJob).count() == 0


def test_rows_with_no_channel_set_yet_are_searched(logged_in, db, users):
    """시트 가져오기는 `초대 완료` 줄에만 카톡을 켠다 — 채널 칸이 하나도 안 켜진 줄은
    받는 길을 아직 안 정한 줄이라 찾는다(운영: 팀원 계정 46줄 중 31줄)."""
    row = _row(db, "홍길동", "가나다벤처스", channel_kakao=0)
    body = _queue(logged_in)
    assert (body["total"], body["search"]) == (1, 1)
    [item] = _claim(logged_in)
    assert item["query"] == "홍길동 심사역"
    assert db.get(SendItem, item["id"]).contact_id == row.id


# ── 찾은 방을 어떻게 받나 — 방 이름이 빈 줄 ─────────────────────────────────

def test_one_room_with_name_and_title_fills_the_room_name(logged_in, db, users):
    row = _row(db, "홍길동", "가나다벤처스")
    title = "홍길동 심사역님 딜 공유방"
    got, item = _search_one(logged_in, db, row, [title], verdict="verified")
    assert (got.kakao_room_name, got.room_verified) == (title, "verified")
    # 확인됨이면 `카톡방 참여여부` 도 O 로 맞는다(`room_joined` 규칙 1).
    assert got.kakao_joined == "O"
    assert (item.status, item.room_name, item.error) == ("sent", title, None)


def test_one_room_with_the_firm_name_fills_the_room_name(logged_in, db, users):
    row = _row(db, "홍길동", "가나다벤처스")
    title = "가나다벤처스 홍길동 이사님 Deal 공유"   # 직급이 시트와 달라도 회사가 있다
    got, _item = _search_one(logged_in, db, row, [title], verdict="verified")
    assert (got.kakao_room_name, got.room_verified) == (title, "verified")


def test_a_room_that_only_has_the_name_is_not_filled(logged_in, db, users):
    """이름으로만 찾은 방 — 같은 성함의 다른 분 방일 수 있다. 사유에 제목만 적는다."""
    row = _row(db, "홍길동", "가나다벤처스")
    other = "홍길동 대표님 (판교 모임)"
    got, item = _search_one(logged_in, db, row, [other], verdict="verified")
    assert not got.kakao_room_name and got.room_verified == "unverified"
    assert item.status == "failed" and other in item.error


def test_a_shorter_name_inside_a_longer_name_is_not_filled(logged_in, db, users):
    """`홍길` 로 찾으면 `홍길동` 방이 걸린다 — 이름+직급(`홍길심사역`)이 안 맞는다."""
    row = _row(db, "홍길", "가나다벤처스")
    got, item = _search_one(logged_in, db, row, ["홍길동 심사역님 딜방"], verdict="verified")
    assert not got.kakao_room_name and item.status == "failed"


def test_several_rooms_are_not_filled(logged_in, db, users):
    row = _row(db, "홍길동", "가나다벤처스")
    rooms = ["홍길동 심사역님 딜 공유방", "홍길동 심사역님 펀드 LP 방"]
    got, item = _search_one(logged_in, db, row, rooms)
    assert not got.kakao_room_name
    assert item.status == "failed" and "여럿" in item.error
    assert all(r in item.error for r in rooms)


def test_two_rooms_with_the_same_title_are_not_filled(logged_in, db, users):
    row = _row(db, "홍길동", "가나다벤처스")
    title = "홍길동 심사역님 딜 공유방"
    got, item = _search_one(logged_in, db, row, [title, title])
    assert not got.kakao_room_name
    assert "같은 제목" in item.error


def test_a_namesake_elsewhere_in_the_team_needs_the_firm_in_the_title(logged_in, db, users):
    """팀 명단(다른 팀원 줄 포함)에 같은 성함의 **다른 회사** 분이 있으면 회사명이 든
    제목만 넣는다 — 이름+직급까지 같아도 그분 방일 수 있다."""
    _row(db, "홍길동", "다라인베스트", user_id=2)
    row = _row(db, "홍길동", "가나다벤처스")
    got, item = _search_one(logged_in, db, row, ["홍길동 심사역님 딜 공유방"],
                            verdict="verified")
    assert not got.kakao_room_name and item.status == "failed"
    assert "같은 성함" in item.error

    title = "홍길동 심사역님 가나다벤처스 딜 공유방"
    got, item = _search_one(logged_in, db, row, [title], verdict="verified")
    assert (got.kakao_room_name, got.room_verified) == (title, "verified")


def test_the_same_person_in_another_list_is_not_a_namesake(logged_in, db, users):
    """같은 분이 두 명단에 겹친 것(같은 회사)은 동명이인이 아니다."""
    _row(db, "홍길동", "가나다 벤처스", user_id=2)
    row = _row(db, "홍길동", "가나다벤처스")
    title = "홍길동 심사역님 딜 공유방"
    got, _item = _search_one(logged_in, db, row, [title], verdict="verified")
    assert got.kakao_room_name == title


def test_an_agent_error_leaves_the_row_alone(logged_in, db, users):
    row = _row(db, "홍길동", "가나다벤처스")
    _queue(logged_in, [row.id])
    [item] = _claim(logged_in)
    _report(logged_in, item["id"], "not_found",
            error="verify error: 카카오톡 메인 창을 앞으로 가져오지 못했습니다.")
    got = _fresh(db, VcContact, row.id)
    assert (got.kakao_room_name, got.room_verified) == (None, "unverified")
    sent = _fresh(db, SendItem, item["id"])
    assert sent.status == "failed" and "카카오톡 메인 창" in sent.error


# ── 확정하면 보낼 수 있는 줄로 — 연결 완료 · 카톡 켬(`vc_room_search._connect`) ─────
#
# 방 이름만 넣고 확인됨을 달면 단계가 `미착수` 그대로라 딜 소개 대상에 안 뜬다.

TITLE = "홍길동 심사역님 가나다벤처스 딜 공유방"


@pytest.mark.parametrize("stage", ["not_started", "in_progress"])
def test_a_confirmed_room_makes_the_row_sendable(logged_in, db, users, stage):
    row = _row(db, "홍길동", "가나다벤처스", connect_stage=stage)
    assert not sheet_owner.can_send_to(row)
    got, _item = _search_one(logged_in, db, row, [TITLE], verdict="verified")
    assert (got.kakao_room_name, got.room_verified) == (TITLE, "verified")
    assert sheet_import.CONNECT_LABELS[got.connect_stage] == "연결 완료"
    assert sheet_owner.can_send_to(got)


def test_a_confirmed_row_with_no_channel_set_turns_kakao_on(logged_in, db, users):
    """방을 찾았다 = 카톡으로 받는다 — 채널을 아직 안 정한 줄은 카톡을 켠다."""
    row = _row(db, "홍길동", "가나다벤처스", channel_kakao=0)
    got, _item = _search_one(logged_in, db, row, [TITLE], verdict="verified")
    assert (got.channel_kakao, got.connect_stage, got.room_verified) == (
        1, "connected", "verified")
    assert sheet_owner.can_send_to(got)


def test_a_row_marked_left_while_searching_keeps_its_stage(logged_in, db, users):
    """찾는 사이 `방 나감` 으로 고친 줄 — 방을 찾아도 확인됨 · 연결 완료를 달지 않는다
    (`room_joined.set_verdict` 와 같은 판정)."""
    row = _row(db, "홍길동", "가나다벤처스", channel_kakao=0)
    _queue(logged_in, [row.id])
    [item] = _claim(logged_in)
    _fresh(db, VcContact, row.id).connect_stage = "left_room"
    db.commit()
    _report(logged_in, item["id"], "verified", candidates=[TITLE])
    got = _fresh(db, VcContact, row.id)
    assert got.connect_stage == "left_room" and got.room_verified != "verified"
    assert got.channel_kakao == 0
    assert not sheet_owner.can_send_to(got)


@pytest.mark.parametrize("rooms", [
    ["홍길동 심사역님 딜 공유방", "홍길동 심사역님 펀드 LP 방"],   # 여럿
    ["홍길동 대표님 (판교 모임)"],                                  # 이름만 든 제목
    [],                                                             # 못 찾음
])
def test_an_unconfirmed_row_keeps_its_stage_and_channels(logged_in, db, users, rooms):
    row = _row(db, "홍길동", "가나다벤처스", channel_kakao=0)
    got, item = _search_one(logged_in, db, row, rooms,
                            verdict="ambiguous" if rooms else "not_found")
    assert item.status == "failed"
    assert (got.kakao_room_name, got.connect_stage, got.channel_kakao) == (
        None, "not_started", 0)
    assert not sheet_owner.can_send_to(got)


# ── 적어 둔 이름으로 못 찾았다 → 같은 건이 이름으로 한 번 더 ──────────────────────

def _written_then_missed(client, db, room="홍길동 심사역님 딜방 (옛 제목)"):
    row = _row(db, "홍길동", "가나다벤처스", room)
    job_id = _queue(client, [row.id])["job_id"]
    [item] = _claim(client)
    _report(client, item["id"], "not_found")
    return row, job_id, item["id"]


def test_a_missed_written_name_goes_back_for_a_name_search(logged_in, db, users):
    row, job_id, item_id = _written_then_missed(logged_in, db)
    sent = _fresh(db, SendItem, item_id)
    assert (sent.status, sent.room_name) == ("pending", "")
    # 진행 화면은 대기 건에도 사유 칸을 그린다 — 다시 찾는 중이라고 적는다.
    assert sent.error.startswith(vc_room_search.SEARCHING)
    assert _fresh(db, VcContact, row.id).room_verified == "not_found"
    # 회분의 건이 전부 되돌아가도 `paused` 로 멈추지 않는다 — 다음 폴링에 이어 찾는다.
    assert _end_round(logged_in, job_id) == "queued"
    [again] = _claim(logged_in)
    assert again["id"] == item_id
    assert (again["query"], again["name"], again["firm"]) == ("홍길동 심사역", "홍길동",
                                                              "가나다벤처스")
    assert not again.get("exact")


def test_the_written_name_found_by_name_search_is_verified(logged_in, db, users):
    """적어 둔 이름 대조에서 놓쳤는데(결과가 늦게 읽힘 등) 이름으로 찾으니 그 방이 있다 —
    바꿀 것 없이 그대로 확인됨이다(같은 제목이 하나면 다른 제목이 함께 와도)."""
    room = "홍길동 심사역님 딜방 (옛 제목)"
    row, job_id, item_id = _written_then_missed(logged_in, db, room)
    _end_round(logged_in, job_id)
    [again] = _claim(logged_in)
    _report(logged_in, again["id"], "ambiguous", candidates=[room, "홍길동 심사역님 펀드방"])
    got = _fresh(db, VcContact, row.id)
    assert (got.kakao_room_name, got.room_verified) == (room, "verified")
    # 이름 찾기로 확인됐으니 보낼 수 있는 줄로(`_connect`) — 미착수였다.
    assert got.connect_stage == "connected" and sheet_owner.can_send_to(got)
    sent = _fresh(db, SendItem, item_id)
    assert (sent.status, sent.room_name, sent.error) == ("sent", room, None)
    assert _end_round(logged_in, job_id) == "done"


# ── 적어 둔 이름이 카톡에 없다 → 이름으로 찾은 방이 이 분 방으로 분명하면 바꾼다(11/13) ──
#
# 사용자(11/13): "규칙에 따라서 방 이름을 찾게 되는데 찾아진 방이 있으면 그 방이름으로
# 카톡방이름 대체해줘". 11/12 에는 덮어쓰지 않고 사유에 「찾은 방: …」만 남겼다. 막이는
# 방 이름이 빈 줄을 채울 때와 같다(`vc_room_search._pick`).

OLD = "홍길동 심사역님 딜방 (옛 제목)"


def _search_after_miss(client, db, row, candidates, before_result=None):
    """적어 둔 이름으로 못 찾은 줄 하나 → 같은 건을 이름으로 찾은 결과 `candidates` 보고.

    `before_result(db)` 는 이름으로 찾는 건을 집어간 **뒤**, 결과가 오기 **전**에 돈다
    (찾는 사이 사람이 줄을 고친 경우). (줄, 건, 회차 끝 상태)를 돌려준다.
    """
    job_id = _queue(client, [row.id])["job_id"]
    [item] = _claim(client)
    _report(client, item["id"], "not_found")
    _end_round(client, job_id)
    [again] = _claim(client)
    assert again["id"] == item["id"] and again["room_name"] == ""
    if before_result is not None:
        before_result(db)
    _report(client, again["id"], "verified" if len(candidates) == 1 else "ambiguous",
            candidates=candidates)
    end = _end_round(client, job_id)
    return _fresh(db, VcContact, row.id), _fresh(db, SendItem, item["id"]), end


def _room_logs(db, row_id):
    import json

    from app.models import EditLog

    db.expire_all()
    logs = db.query(EditLog).filter(EditLog.table_name == "vc_contacts",
                                    EditLog.row_id == row_id).all()
    return [(log, c) for log in logs for c in json.loads(log.changes_json)
            if c["field"] == "kakao_room_name"]


def test_a_written_name_missing_in_kakao_is_replaced_by_the_one_found_room(
        logged_in, db, users):
    """이름+직급이 든 방 하나 — 그 제목으로 바꾸고 확인됨 · 연결 완료(미착수였다)."""
    row = _row(db, "홍길동", "가나다벤처스", OLD)
    found = "홍길동 심사역님 딜 공유방"
    got, sent, end = _search_after_miss(logged_in, db, row, [found])
    assert (got.kakao_room_name, got.room_verified, got.kakao_joined) == (
        found, "verified", "O")
    assert got.connect_stage == "connected" and sheet_owner.can_send_to(got)
    # 진행 화면: 카톡방 칸은 새 제목, 상태는 확인됨, 사유 칸에 바꾼 것 — 실패로 안 센다.
    assert (sent.status, sent.room_name) == ("sent", found)
    assert sent.error == f"방 이름을 찾은 제목으로 바꿈 (전: {OLD})"
    assert end == "done"
    # 자기 줄이라도 수정 로그에 전→후가 남는다 — 찾기를 건 계정 이름으로.
    [(log, change)] = _room_logs(db, row.id)
    assert (change["before"], change["after"]) == (OLD, found)
    assert (log.actor_user_id, log.target_user_id, log.scope) == (1, 1, "mine")


def test_the_firm_in_the_title_is_enough_to_replace(logged_in, db, users):
    """직급이 시트와 달라도 회사명이 들었으면 바꾼다 — 빈 줄을 채울 때와 같다."""
    row = _row(db, "홍길동", "가나다벤처스", OLD)
    found = "가나다벤처스 홍길동 이사님 Deal 공유"
    got, sent, _end = _search_after_miss(logged_in, db, row, [found])
    assert (got.kakao_room_name, got.room_verified) == (found, "verified")
    assert sent.status == "sent"


@pytest.mark.parametrize("rooms,why", [
    (["홍길동 대표님 (판교 모임)"], "이름만 든 제목"),
    (["홍길동 심사역님 딜 공유방", "홍길동 심사역님 펀드 LP 방"], "여럿"),
    (["홍길동 심사역님 딜 공유방", "홍길동 심사역님 딜 공유방"], "같은 제목의 방이 여럿"),
])
def test_an_unclear_room_does_not_replace_the_written_name(logged_in, db, users,
                                                           rooms, why):
    row = _row(db, "홍길동", "가나다벤처스", OLD)
    got, sent, end = _search_after_miss(logged_in, db, row, rooms)
    assert (got.kakao_room_name, got.room_verified, got.connect_stage) == (
        OLD, "not_found", "not_started")
    assert (sent.status, sent.room_name) == ("failed", OLD)
    assert "찾은 방:" in sent.error and why in sent.error
    assert all(r in sent.error for r in rooms)
    assert end == "done_with_errors" and not _room_logs(db, row.id)


def test_a_namesake_needs_the_firm_in_the_title_to_replace(logged_in, db, users):
    """팀 명단에 같은 성함의 다른 회사 분 — 이름+직급이 맞아도 회사명이 없으면 안 바꾼다."""
    _row(db, "홍길동", "다라인베스트", user_id=2)
    row = _row(db, "홍길동", "가나다벤처스", OLD)
    got, sent, _end = _search_after_miss(logged_in, db, row, ["홍길동 심사역님 딜 공유방"])
    assert (got.kakao_room_name, got.room_verified) == (OLD, "not_found")
    assert sent.status == "failed" and "같은 성함" in sent.error

    title = "홍길동 심사역님 가나다벤처스 딜 공유방"
    got, sent, _end = _search_after_miss(logged_in, db, row, [title])
    assert (got.kakao_room_name, got.room_verified) == (title, "verified")


def test_a_row_marked_left_while_searching_keeps_its_written_name(logged_in, db, users):
    """찾는 사이 `방 나감` 으로 고친 줄 — 찾은 방이 분명해도 방 이름 · 단계를 그대로 둔다."""
    row = _row(db, "홍길동", "가나다벤처스", OLD)

    def leave(db):
        _fresh(db, VcContact, row.id).connect_stage = "left_room"
        db.commit()

    got, sent, _end = _search_after_miss(logged_in, db, row, ["홍길동 심사역님 딜 공유방"],
                                         before_result=leave)
    assert (got.kakao_room_name, got.connect_stage) == (OLD, "left_room")
    assert got.room_verified != "verified" and not sheet_owner.can_send_to(got)
    assert sent.status == "failed" and "방 나감" in sent.error


def test_a_name_edited_while_searching_is_not_overwritten(logged_in, db, users):
    """찾는 사이 사람이 방 이름을 고쳤다 — 그 이름은 아직 대조도 안 했다. 옛 이름으로
    찾은 결과로 덮지 않는다(`fall_back` 이 떠 둔 이름과 다르다)."""
    row = _row(db, "홍길동", "가나다벤처스", OLD)
    typed = "홍길동 심사역님 새 딜방"

    def edit(db):
        _fresh(db, VcContact, row.id).kakao_room_name = typed
        db.commit()

    got, sent, _end = _search_after_miss(logged_in, db, row, ["홍길동 심사역님 딜 공유방"],
                                         before_result=edit)
    assert got.kakao_room_name == typed and got.room_verified != "verified"
    assert (sent.status, sent.room_name) == ("failed", typed)
    assert "방 이름이 바뀌어" in sent.error


def test_a_missed_startup_row_is_not_searched_by_a_person_name(logged_in, db, users):
    """스타트업 명단 줄은 회사명으로 찾는 길이 따로다 — 성함으로 다시 찾지 않는다."""
    db.add(SheetOwner(label="스타트업 명단", user_id=1, layout="startup", is_hidden=1))
    db.commit()
    row = _row(db, "박준호", "자차랩스", "자차랩스 박준호 대표님", title="대표",
               source_sheet="스타트업 명단")
    _queue(logged_in, [row.id])
    [item] = _claim(logged_in)
    _report(logged_in, item["id"], "not_found")
    sent = _fresh(db, SendItem, item["id"])
    assert (sent.status, sent.room_name) == ("failed", "자차랩스 박준호 대표님")


# ── 팀원 화면으로 보는 관리자 — 그 팀원 잡, 맡긴 발송기(관리자 PC)가 찾는다 ─────────

def test_admin_viewing_a_member_whose_agent_is_the_admins(u1_admin, logged_in, db, users):
    """팀 현황 `○○ 발송기로` 로 팀원 잡을 관리자 발송기에 맡겨 둔 경우(`send_via_user_id`).
    팀원 명단에 방 이름이 하나도 없어도 잡이 서고, 관리자 발송기가 집어가 찾은 방이
    그 팀원 줄에 확인됨으로 선다."""
    member = db.get(User, users["u2"].id)
    member.send_via_user_id = users["u1"].id
    db.commit()
    row = _row(db, "홍길동", "가나다벤처스", user_id=member.id)

    r = logged_in.post("/account/view-as", data={"member_id": member.id, "next": "/"},
                       follow_redirects=False)
    assert r.status_code == 303
    body = _queue(logged_in, [row.id])
    assert db.get(SendJob, body["job_id"]).user_id == member.id

    [item] = _claim(logged_in)          # 관리자(u1) 발송기 토큰으로 집어간다
    title = "홍길동 심사역님 가나다벤처스 딜 공유방"
    _report(logged_in, item["id"], "verified", candidates=[title])
    got = _fresh(db, VcContact, row.id)
    assert (got.kakao_room_name, got.room_verified) == (title, "verified")


# ── 발송기는 그대로다 — 지금 판(0.11.14)의 방 확인 고리가 서버가 준 칸만으로 찾는다 ──

class _Relay:
    """발송기의 서버 호출을 시험 클라이언트로 그대로 넘긴다(`agent/main.AgentClient` 모양)."""

    def __init__(self, client):
        self.client = client

    def job_state(self, job_id):
        return self.client.get(f"/api/agent/jobs/{job_id}/state",
                               headers=auth(DEMO_TOKEN)).json()

    def report_item(self, item_id, status, error=None, screenshot_b64=None,
                    verify_result=None, found_room=None, candidates=None):
        body = {"status": status, "error": error, "verify_result": verify_result,
                "found_room": found_room, "candidates": candidates}
        r = self.client.post(f"/api/agent/items/{item_id}/result",
                             json={k: v for k, v in body.items() if v is not None},
                             headers=auth(DEMO_TOKEN))
        assert r.status_code == 200, r.text

    def report_job(self, job_id, status):
        r = self.client.post(f"/api/agent/jobs/{job_id}/status", json={"status": status},
                             headers=auth(DEMO_TOKEN))
        assert r.status_code == 200, r.text


class _Kakao:
    """카톡 검색 흉내 — 검색어(공백 무시)가 든 방 제목. `verify_room` 은 글자까지."""

    def __init__(self, rooms):
        self.rooms = rooms

    def discover_rooms(self, query, marker="", **_):
        q = "".join(query.split())
        return [t for t in self.rooms if q and q in "".join(t.split())]

    def verify_room(self, room_name):
        hits = [t for t in self.rooms if t == room_name]
        return "verified" if len(hits) == 1 else "ambiguous" if hits else "not_found"


def _run_agent(client, sender):
    import agent.main as agent_main

    r = client.get("/api/agent/poll?kinds=verify_room", headers=auth(DEMO_TOKEN))
    if r.status_code == 204:
        return False
    agent_main.process_verify_job(_Relay(client), sender, r.json(),
                                  {"verify_delay_min_sec": 0, "verify_delay_max_sec": 0,
                                   "room_marker": ""})
    return True


def test_the_current_agent_walks_room_name_then_name_and_title_then_name(
        logged_in, db, users):
    ok = _row(db, "김서연", "라마바파트너스", "김서연 심사역님 라마바파트너스 딜방")
    old = _row(db, "박준호", "자차벤처스", "박준호 이사님 딜방 (옛 제목)", title="이사")
    blank = _row(db, "홍길동", "가나다벤처스")          # 시트 직급은 심사역, 방은 이사님
    kakao = _Kakao(["김서연 심사역님 라마바파트너스 딜방",
                    "박준호 이사님 자차벤처스 Deal 공유",
                    "가나다벤처스 홍길동 이사님 Deal 공유",
                    "투자 네트워크 (박준호 외 12명)"])
    job_id = _queue(logged_in)["job_id"]

    rounds = 0
    while _run_agent(logged_in, kakao):
        rounds += 1
    assert rounds == 2                   # 적어 둔 이름 → (못 찾은 건만) 이름으로

    db.expire_all()
    job = db.get(SendJob, job_id)
    assert job.status == "done" and job.total == 3
    # 1) 적어 둔 이름 그대로 있다 → 확인됨.
    assert db.get(VcContact, ok.id).room_verified == "verified"
    # 2) 적어 둔 이름이 카톡에 없다 → 이름+직급으로 찾은 방 하나(이름+직급 · 회사명이
    #    든 제목)로 방 이름을 바꾸고 확인됨(11/13 — 11/12 에는 사유에만 적었다).
    got = db.get(VcContact, old.id)
    assert (got.kakao_room_name, got.room_verified) == ("박준호 이사님 자차벤처스 Deal 공유",
                                                        "verified")
    [item] = [i for i in job.items if i.contact_id == old.id]
    assert item.status == "sent" and "박준호 이사님 딜방 (옛 제목)" in item.error
    # 3) 방 이름이 없다 → 이름+직급(홍길동 심사역)은 없고 이름으로 하나 → 회사명이 든
    #    제목이라 이 분 방으로 넣는다.
    got = db.get(VcContact, blank.id)
    assert (got.kakao_room_name, got.room_verified) == ("가나다벤처스 홍길동 이사님 Deal 공유",
                                                        "verified")
