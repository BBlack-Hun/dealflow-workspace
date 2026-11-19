"""방 확인을 **못 한** 건은 `못 찾음` 과 다른 말로 선다 — 서버 쪽 (0.11.16).

운영의 윈도우 PC 한 대에서 방 찾기 한 회차가 전부 `이 방을 찾지 못했습니다` 로 끝났다.
실제로는 그 PC 카톡의 검색 결과를 한 줄도 못 읽은 것이었는데, 화면에는 **방이 없다**와
같은 말로 섰다. 0.11.16 발송기는 그런 건에 까닭(`verify_reason`)을 함께 올린다
(`tests/test_win_verify_unreadable.py`). 여기서는 서버가 그것을 어떻게 받는지 못박는다.

    ① 까닭이 오면 사유 글 · 상태 말이 **확인 못 함**이다 — 무엇을 볼지(채팅 탭 · 잠금모드)
       까지 적는다
    ② **판정은 그대로다** — 무엇도 확인됨으로 올리지 않고, 확인 표시를 거두는 자리 ·
       이름으로 다시 찾기도 예전과 같다
    ③ 까닭 없이 온 결과(0.11.15 까지의 발송기 · 맥 발송기)는 **예전 문구 그대로**다
    ④ 찾은 제목이나 발송기 오류가 함께 오면 그쪽 말이 먼저다
    ⑤ 발송기 → 서버까지 한 줄로 이어 본다(가짜 카톡 → 진짜 방 확인 고리 → 서버 글)

이름 · 회사 · 방 제목은 모두 지어낸 값이다.
"""
from __future__ import annotations

import base64
import json
import types

import pytest

from app.models import (ROOM_SEARCH_TOPIC, SendItem, SendJob, SenderRoom,
                        SourcingContact, VcContact)
from app.services import room_unchecked, sender_rooms, vc_room_search
from tests.conftest import DEMO_TOKEN, OTHER_TOKEN, auth
from tests.test_sender_rooms import (GROUP, OWN, SRC_OWN,  # noqa: F401 - 픽스처를 함께 쓴다
                                     _end, _login, _member_report, _member_search,
                                     _sourcing_item, sourcing, team)
from tests.test_vc_room_search import _Kakao, _claim, _end_round, _fresh, _queue
from tests.test_vc_room_search import _row as _vc_row
from tests.test_vc_room_search import _run_agent as _run_old_agent

PREFIX = "확인 못 함 — "
OLD_SENDER_TEXT = "보내는 계정 카톡에서 이 방을 찾지 못했습니다"
OLD_SEARCH_TEXT = "카톡에서 이 분의 방을 찾지 못했습니다 (이름+직급 → 이름으로 찾음)"
TAIL = ("\n확인 못 함: 보내는 PC 카톡이 채팅 탭에 있는지, 잠금모드가 아닌지 보고 다시 "
        "확인해 주세요")


def _body(**kw):
    """발송기가 올린 건 결과 흉내(`agent_api.ItemResult` 모양)."""
    base = {"verify_result": "not_found", "verify_reason": None, "error": None,
            "found_room": None, "candidates": None}
    base.update(kw)
    return types.SimpleNamespace(**base)


def _report(client, item_id, token=DEMO_TOKEN, **body):
    payload = {"status": "failed", "verify_result": "not_found"}
    payload.update(body)
    r = client.post(f"/api/agent/items/{item_id}/result", json=payload,
                    headers=auth(token))
    assert r.status_code == 200, r.text


def _sender_report(client, item_id, **body):
    _report(client, item_id, OTHER_TOKEN, **body)


def _sender_row(db, users, team):
    db.expire_all()
    return sender_rooms.row_of(db, users["u2"].id, team["ok"].id)


# ══════════════════════════════════════════════════════════════════════════
#  까닭 → 말 (`room_unchecked.note`)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("reason, words", [
    ("unreadable", ["검색 결과를 읽지 못했습니다", "방이 없다는 뜻은 아닙니다",
                    "채팅 탭", "잠금모드", "방 이름"]),
    ("not_chat_tab", ["채팅 탭이 아닌 것으로 보입니다", "채팅 탭으로 바꾼 뒤"]),
    ("locked", ["잠금모드로 보입니다", "잠금을 풀고"]),
    ("no_focus", ["카톡 창을 앞으로 가져오지 못했습니다", "카톡 창을 열어 두고"]),
])
def test_each_reason_says_what_to_check(reason, words):
    text = room_unchecked.note(_body(verify_reason=reason))
    assert text.startswith(PREFIX) and room_unchecked.is_note(text)
    assert all(w in text for w in words)
    assert "다시 확인해 주세요" in text


def test_an_unknown_reason_is_still_unchecked():
    """나중 판의 발송기가 새 까닭 값을 보내도 `확인 못 함` 으로 선다."""
    assert (room_unchecked.note(_body(verify_reason="something_new"))
            == room_unchecked.MESSAGES["unreadable"])


@pytest.mark.parametrize("body", [
    _body(),                                                   # 까닭이 없다(예전 발송기)
    _body(verify_reason=""),
    _body(verify_reason="   "),
    _body(verify_reason=7),                                    # 글자가 아니다
    _body(verify_reason="unreadable", verify_result="verified"),
    _body(verify_reason="unreadable", verify_result="ambiguous"),
    _body(verify_reason="unreadable", verify_result=None),
    _body(verify_reason="unreadable", error="verify error: 창을 못 잡았습니다"),
    _body(verify_reason="unreadable", found_room="홍길동 심사역님 딜방"),
    _body(verify_reason="unreadable", candidates=["홍길동 심사역님 딜방"]),
])
def test_no_note_without_a_reason_or_when_something_else_came(body):
    assert room_unchecked.note(body) == ""


def test_only_the_note_itself_counts_as_a_note():
    assert not room_unchecked.is_note(None)
    assert not room_unchecked.is_note(OLD_SENDER_TEXT)
    # 이름으로 다시 찾는 동안의 말(앞에 다른 글이 붙는다)은 아직 결과가 아니다.
    assert not room_unchecked.is_note(
        vc_room_search.SEARCHING + room_unchecked.MESSAGES["unreadable"])


# ══════════════════════════════════════════════════════════════════════════
#  보내는 계정 방 제목 — 사고가 난 길(`sender_rooms.apply_result`)
# ══════════════════════════════════════════════════════════════════════════

def test_a_reason_makes_the_sender_row_unchecked_not_missing(client, db, users, team):
    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    _sender_report(client, item_id, verify_reason="unreadable")

    item = _fresh(db, SendItem, item_id)
    assert item.status == "failed"
    assert item.error == room_unchecked.MESSAGES["unreadable"]
    assert OLD_SENDER_TEXT not in item.error
    row = _sender_row(db, users, team)
    assert sender_rooms.state_of(row) == "unchecked"
    assert sender_rooms.unchecked_note(row) == item.error
    # 확인된 것은 아무것도 없다 — 고를 후보도 없다.
    assert (row.verified, row.room_name) == (0, None)
    assert sender_rooms.candidates(row) == []
    # 담당 팀원의 줄은 그대로다.
    owner = db.get(VcContact, team["ok"].id)
    assert (owner.kakao_room_name, owner.room_verified) == (OWN, "unverified")


def test_without_a_reason_it_is_the_old_not_found(client, db, users, team):
    """0.11.15 까지의 발송기 · 맥 발송기 — 문구도 상태도 예전 그대로다."""
    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    _sender_report(client, item_id)

    assert _fresh(db, SendItem, item_id).error == OLD_SENDER_TEXT
    row = _sender_row(db, users, team)
    assert sender_rooms.state_of(row) == "not_found"
    assert sender_rooms.unchecked_note(row) == ""
    assert row.candidates is None


@pytest.mark.parametrize("reason", ["not_chat_tab", "locked", "no_focus", "새_까닭"])
def test_every_reason_lands_as_unchecked(client, db, users, team, reason):
    job = sender_rooms.queue_check(db, users["u2"])
    _sender_report(client, job.items[0].id, verify_reason=reason)
    row = _sender_row(db, users, team)
    assert sender_rooms.state_of(row) == "unchecked"
    assert sender_rooms.unchecked_note(row) == room_unchecked.MESSAGES.get(
        reason, room_unchecked.MESSAGES["unreadable"])


def test_a_reason_never_confirms_anything(client, db, users, team):
    """★ 약한 근거로 확인됨이 되지 않는다 — 까닭이 실려 와도 판정은 판정대로다."""
    job = sender_rooms.queue_check(db, users["u2"])
    _sender_report(client, job.items[0].id, verify_reason="unreadable")
    assert _sender_row(db, users, team).verified == 0
    # 자동화가 고르는 방도 예전처럼 담당 팀원의 제목이다(이 계정 제목은 없다).
    assert sender_rooms.room_for(db, users["u2"].id, team["ok"]) == OWN


def test_an_unchecked_result_still_clears_a_confirmed_title_as_before(
        client, db, users, team):
    """확인 표시를 거두는 것은 예전과 같다 — 모르면 미확인 쪽이다. 달라지는 것은 말뿐."""
    first = sender_rooms.queue_check(db, users["u2"])
    _sender_report(client, first.items[0].id, status="sent", verify_result="verified",
                   found_room=OWN, candidates=[OWN])
    assert _sender_row(db, users, team).verified == 1
    client.post(f"/api/agent/jobs/{first.id}/status", json={"status": "done"},
                headers=auth(OTHER_TOKEN))

    db.expire_all()
    again = sender_rooms.queue_check(db, users["u2"])
    _sender_report(client, again.items[0].id, verify_reason="unreadable")
    row = _sender_row(db, users, team)
    assert (row.verified, row.room_name) == (0, None)
    assert sender_rooms.state_of(row) == "unchecked"


def test_a_found_title_wins_over_a_reason(client, db, users, team):
    """찾은 제목이 함께 오면 확인 못 함이 아니다 — 예전 길 그대로 후보로 담는다."""
    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    _sender_report(client, item_id, verify_reason="unreadable",
                   candidates=["가나다 홍길동님 방"])
    row = _sender_row(db, users, team)
    assert sender_rooms.state_of(row) == "picks"
    assert sender_rooms.candidates(row) == ["가나다 홍길동님 방"]
    assert "후보 1개" in _fresh(db, SendItem, item_id).error


def test_an_agent_error_wins_over_a_reason(client, db, users, team):
    job = sender_rooms.queue_check(db, users["u2"])
    _sender_report(client, job.items[0].id, verify_reason="unreadable",
                   error="verify error: 카카오톡 메인 창을 앞으로 가져오지 못했습니다.")
    assert sender_rooms.state_of(_sender_row(db, users, team)) == "not_found"


def test_the_next_real_result_replaces_the_mark(client, db, users, team):
    def check(**body):
        job = sender_rooms.queue_check(db, users["u2"])
        _sender_report(client, job.items[0].id, **body)
        client.post(f"/api/agent/jobs/{job.id}/status", json={"status": "done"},
                    headers=auth(OTHER_TOKEN))
        row = _sender_row(db, users, team)
        return sender_rooms.state_of(row), sender_rooms.unchecked_note(row)

    assert check(verify_reason="locked")[0] == "unchecked"
    assert check() == ("not_found", "")                       # 이번에는 읽혔고, 없었다
    assert check(verify_reason="unreadable")[0] == "unchecked"
    assert check(status="sent", verify_result="verified", found_room=OWN,
                 candidates=[OWN]) == ("confirmed", "")


def test_the_mark_is_not_a_room_name_anywhere(client, db, users, team):
    """후보 칸에 목록 대신 표시를 담는다 — 그 글이 방 제목으로 읽히는 곳이 없어야 한다."""
    from app.services import automation

    job = sender_rooms.queue_check(db, users["u2"])
    _sender_report(client, job.items[0].id, verify_reason="unreadable")
    row = _sender_row(db, users, team)
    assert json.loads(row.candidates) == {"unchecked": room_unchecked.MESSAGES["unreadable"]}
    names = automation.real_rooms(db)
    assert OWN in names
    assert not any("확인 못 함" in n or "unchecked" in n for n in names)
    # 표시는 후보가 아니다 — 확정할 수 없다.
    with pytest.raises(Exception):
        sender_rooms.confirm(db, users["u2"], team["ok"], "unchecked")


def test_the_board_shows_what_to_check(client, db, users, team):
    _login(client, "01000000002")
    before = client.get("/team/sender-rooms").text
    assert "확인 못 함" not in before and "sender-room-unchecked" not in before

    job = sender_rooms.queue_check(db, users["u2"])
    _sender_report(client, job.items[0].id, verify_reason="unreadable")
    db.expire_all()
    board = sender_rooms.board(db, users["u2"])
    assert board["counts"]["unchecked"] == 1 and board["counts"]["not_found"] == 0
    [line] = board["rows"]
    assert (line["state"], line["state_label"]) == ("unchecked", "확인 못 함")
    assert line["note"] == room_unchecked.MESSAGES["unreadable"]

    page = client.get("/team/sender-rooms").text
    assert "· 확인 못 함 <b>1</b>" in page
    assert 'data-testid="sender-room-unchecked"' in page
    assert "채팅 탭에 있는지, 잠금모드가 아닌지" in page
    assert "못 찾았습니다 —" not in page          # `못 찾음` 줄의 말은 서지 않는다


def test_the_progress_page_counts_unchecked_apart(client, db, users, team):
    """[전체 방 확인] 진행 화면 — 줄의 상태 말과 끝날 때 알림이 **확인 못 함**을 가른다."""
    other = VcContact(user_id=users["u1"].id, name="김영희", firm="다라마인베스트",
                      title="이사", kakao_room_name="김영희 이사님 다라마인베스트 딜방",
                      connect_stage="connected", source_sheet="내 명단")
    db.add(other)
    db.commit()
    job = sender_rooms.queue_check(db, users["u2"])
    item = {i.contact_id: i.id for i in job.items}
    _sender_report(client, item[team["ok"].id], verify_reason="unreadable")
    _sender_report(client, item[other.id])                     # 까닭 없이 못 찾음
    _end(client, job.id, OTHER_TOKEN)

    _login(client, "01000000002")
    got = client.get(f"/api/jobs/{job.id}").json()
    assert got["room_done"] == {
        "sentence": "방 연결 확인이 끝났습니다 — 확인됨 0 · 불일치 1 · 확인 못 함 1" + TAIL,
        "pick": False}
    result = {i["id"]: i["result"] for i in got["items"]}
    assert result[item[team["ok"].id]] == "확인 못 함"
    assert result[item[other.id]] is None                      # 예전 그대로(`불일치`)


# ── 딜 소싱 명단 ───────────────────────────────────────────────────────────

def test_a_sourcing_person_is_unchecked_in_the_sender_table_only(
        client, db, users, team, sourcing):
    job = sender_rooms.queue_check(db, users["u2"])
    item_id = _sourcing_item(job, sourcing["room"]).id
    _sender_report(client, item_id, verify_reason="unreadable")

    db.expire_all()
    view = sender_rooms.sourcing_view(db, users["u2"].id)[sourcing["room"].id]
    assert view["state"] == "unchecked" and view["note"].startswith(PREFIX)
    person = db.get(SourcingContact, sourcing["room"].id)
    assert person.kakao_room_name == SRC_OWN and not person.room_candidates

    _login(client, "01000000002")
    page = client.get("/sourcing", params={"tab": GROUP}).text
    assert "확인 못 함 — 보내는 PC 카톡 확인" in page
    assert 'data-state="unchecked"' in page
    assert "이 계정 카톡에서 못 찾음" not in page


def test_a_finished_sender_search_tells_why_nothing_was_checked(
        client, db, users, team, sourcing):
    people = [sourcing["room"], sourcing["noroom"]]
    _login(client, "01000000002")
    answer = client.post("/sourcing/rooms/search",
                         data={"tab": GROUP, "ids": ",".join(str(p.id) for p in people)},
                         headers={"Accept": "application/json"})
    job_id = answer.json()["job_id"]
    job = db.get(SendJob, job_id)
    for item in job.items:
        _sender_report(client, item.id, verify_reason="unreadable")
    _end(client, job_id, OTHER_TOKEN)

    got = client.get(f"/api/jobs/{job_id}").json()
    assert got["room_search"] == {
        "confirmed": 0, "picks": 0, "not_found": 0, "failed": 2, "canceled": 0,
        "reason": room_unchecked.MESSAGES["unreadable"],
        # 무엇을 볼지는 까닭 글에 이미 있다 — 카톡 안내를 겹쳐 적지 않는다.
        "hint": ""}
    assert got["room_done"] == {
        "sentence": "딜 소싱 방 찾기가 끝났습니다 — 확정 0 · 후보 고르기 0 · 못 찾음 0 · "
                    "확인 못 함 2" + TAIL,
        "pick": False}
    assert {i["result"] for i in got["items"]} == {"확인 못 함"}


def test_a_member_search_keeps_its_candidates_and_tells_why(client, db, users, team):
    """팀원이 건 딜 소싱 [방 후보 찾기] — 발송기 오류로 끝난 찾기와 같은 길이다:
    담아 둔 후보를 `후보 없음` 으로 덮지 않는다."""
    from app.services import room_match, sourcing_rooms

    job, item, rows = _member_search(client, db, ["가후보", "나없음"])
    kept, missing = rows
    room_match.save_candidates(kept, ["가후보 방 하나", "가후보 방 둘"],
                               at="2026-11-18T10:00:00", query="가후보 심사역")
    db.commit()
    _member_report(client, item[kept.id], verify_reason="unreadable")
    _member_report(client, item[missing.id])                   # 까닭 없이 못 찾음
    _end(client, job.id)

    db.expire_all()
    person = db.get(SourcingContact, kept.id)
    assert [p["room"] for p in sourcing_rooms.picks(person)["rooms"]] == [
        "가후보 방 하나", "가후보 방 둘"]
    assert sourcing_rooms.last_error(person) == room_unchecked.MESSAGES["unreadable"]
    got = client.get(f"/api/jobs/{job.id}").json()
    assert got["room_search"] == {
        "confirmed": 0, "picks": 0, "not_found": 1, "failed": 1, "canceled": 0,
        "reason": room_unchecked.MESSAGES["unreadable"], "hint": ""}
    assert got["room_done"]["sentence"] == (
        "딜 소싱 방 찾기가 끝났습니다 — 확정 0 · 후보 고르기 0 · 못 찾음 1 · 확인 못 함 1"
        + TAIL)


# ══════════════════════════════════════════════════════════════════════════
#  투자사 [방 연결 확인] — 적어 둔 이름 대조 → 이름으로 찾기
# ══════════════════════════════════════════════════════════════════════════

WRITTEN = "홍길동 심사역님 딜방 (옛 제목)"


def _exact_round(client, db, **body):
    row = _vc_row(db, "홍길동", "가나다벤처스", WRITTEN)
    job_id = _queue(client, [row.id])["job_id"]
    [item] = _claim(client)
    _report(client, item["id"], **body)
    return row, job_id, item["id"]


def test_an_unread_written_name_still_goes_on_to_the_name_search(logged_in, db, users):
    """★ 판정 · 다음 걸음은 예전 그대로다 — 결과 줄을 못 읽는 PC 는 이름으로 찾는 길에서
    방을 찾는다. 달라지는 것은 그동안 서는 말뿐이다."""
    row, job_id, item_id = _exact_round(logged_in, db, verify_reason="unreadable")
    item = _fresh(db, SendItem, item_id)
    assert (item.status, item.room_name) == ("pending", "")
    assert item.error == vc_room_search.SEARCHING + room_unchecked.MESSAGES["unreadable"]
    assert _fresh(db, VcContact, row.id).room_verified == "not_found"     # 예전과 같다
    assert _end_round(logged_in, job_id) == "queued"
    [again] = _claim(logged_in)
    assert (again["id"], again["query"], again["name"]) == (item_id, "홍길동 심사역", "홍길동")


def test_unread_both_times_ends_as_unchecked(logged_in, db, users):
    row, job_id, item_id = _exact_round(logged_in, db, verify_reason="unreadable")
    _end_round(logged_in, job_id)
    _claim(logged_in)
    _report(logged_in, item_id, verify_reason="unreadable")
    assert _end_round(logged_in, job_id) == "done_with_errors"

    item = _fresh(db, SendItem, item_id)
    assert (item.status, item.room_name) == ("failed", WRITTEN)
    assert item.error == room_unchecked.MESSAGES["unreadable"]
    got = _fresh(db, VcContact, row.id)
    assert got.kakao_room_name == WRITTEN                      # 방 이름은 그대로다
    assert got.room_verified == "not_found"

    done = logged_in.get(f"/api/jobs/{job_id}").json()
    assert done["room_done"] == {
        "sentence": "방 연결 확인이 끝났습니다 — 확인됨 0 · 불일치 0 · 확인 못 함 1" + TAIL,
        "pick": False}
    assert done["items"][0]["result"] == "확인 못 함"
    assert done["items"][0]["room_pick"] is None


def test_a_room_found_on_the_second_round_is_not_called_unchecked(logged_in, db, users):
    """앞 대조는 못 읽었지만 이름으로 찾으니 방이 걸렸다 — 그 건은 확인 못 함이 아니다."""
    row, job_id, item_id = _exact_round(logged_in, db, verify_reason="unreadable")
    _end_round(logged_in, job_id)
    _claim(logged_in)
    other = "홍길동 대표님 (판교 모임)"                         # 이 분 방인지 분명하지 않다
    _report(logged_in, item_id, verify_result="verified", status="sent",
            candidates=[other])

    item = _fresh(db, SendItem, item_id)
    assert item.status == "failed" and other in item.error
    assert not room_unchecked.is_note(item.error)
    assert item.error.startswith("카톡에서 적어 둔 방 이름과 같은 제목을 찾지 못했습니다")
    _end_round(logged_in, job_id)
    done = logged_in.get(f"/api/jobs/{job_id}").json()
    assert done["room_done"]["sentence"] == "방 연결 확인이 끝났습니다 — 확인됨 0 · 불일치 1"
    assert done["items"][0]["result"] is None


def test_a_room_that_fits_on_the_second_round_is_confirmed_as_before(logged_in, db, users):
    row, job_id, item_id = _exact_round(logged_in, db, verify_reason="unreadable")
    _end_round(logged_in, job_id)
    _claim(logged_in)
    title = "홍길동 심사역님 가나다벤처스 딜 공유방"
    _report(logged_in, item_id, verify_result="verified", status="sent",
            candidates=[title])
    got = _fresh(db, VcContact, row.id)
    assert (got.kakao_room_name, got.room_verified) == (title, "verified")
    assert _fresh(db, SendItem, item_id).status == "sent"


def test_read_but_missing_on_the_second_round_is_the_old_not_found(logged_in, db, users):
    """이름으로 찾을 때는 읽혔고 없었다 — 앞의 `확인 못 함` 을 앞에 붙이지 않는다."""
    row, job_id, item_id = _exact_round(logged_in, db, verify_reason="unreadable")
    _end_round(logged_in, job_id)
    _claim(logged_in)
    _report(logged_in, item_id)
    assert _fresh(db, SendItem, item_id).error == (
        "카톡에서 적어 둔 방 이름과 같은 제목을 찾지 못했습니다 · 이름+직급 → 이름으로도 "
        "찾지 못했습니다")


def test_the_old_agent_gets_the_old_words_on_the_written_name_path(logged_in, db, users):
    row, job_id, item_id = _exact_round(logged_in, db)
    item = _fresh(db, SendItem, item_id)
    assert item.error == (vc_room_search.SEARCHING
                          + "카톡에서 같은 이름의 방을 찾지 못했습니다 (방 제목을 확인하세요)")


def test_a_name_search_that_read_nothing_leaves_the_row_alone(logged_in, db, users):
    """방 이름이 빈 줄 — 발송기 오류로 끝난 찾기와 같은 길이다(줄은 그대로)."""
    row = _vc_row(db, "홍길동", "가나다벤처스")
    job_id = _queue(logged_in, [row.id])["job_id"]
    [item] = _claim(logged_in)
    _report(logged_in, item["id"], verify_reason="not_chat_tab")

    sent = _fresh(db, SendItem, item["id"])
    assert sent.status == "failed"
    assert sent.error == room_unchecked.MESSAGES["not_chat_tab"]
    got = _fresh(db, VcContact, row.id)
    assert (got.kakao_room_name, got.room_verified) == (None, "unverified")
    _end_round(logged_in, job_id)
    done = logged_in.get(f"/api/jobs/{job_id}").json()
    assert done["room_done"]["sentence"] == (
        "방 연결 확인이 끝났습니다 — 확인됨 0 · 불일치 0 · 확인 못 함 1" + TAIL)


def test_a_name_search_without_a_reason_is_the_old_not_found(logged_in, db, users):
    row = _vc_row(db, "홍길동", "가나다벤처스")
    _queue(logged_in, [row.id])
    [item] = _claim(logged_in)
    _report(logged_in, item["id"])
    assert _fresh(db, SendItem, item["id"]).error == OLD_SEARCH_TEXT


def test_a_reason_on_a_verified_result_changes_nothing(logged_in, db, users):
    """판정이 `verified` 면 까닭은 쓰지 않는다 — 확인됨은 예전과 같은 근거로만 선다."""
    title = "홍길동 심사역님 가나다벤처스 딜방"
    row = _vc_row(db, "홍길동", "가나다벤처스", title)
    _queue(logged_in, [row.id])
    [item] = _claim(logged_in)
    _report(logged_in, item["id"], status="sent", verify_result="verified",
            found_room=title, candidates=[title], verify_reason="unreadable")
    assert _fresh(db, VcContact, row.id).room_verified == "verified"
    sent = _fresh(db, SendItem, item["id"])
    assert (sent.status, sent.error) == ("sent", None)


def test_a_reason_alone_never_verifies(logged_in, db, users):
    """판정 없이 까닭만 온 결과 — 예전처럼 `못 찾음` 쪽이다(모르면 미확인)."""
    title = "홍길동 심사역님 가나다벤처스 딜방"
    row = _vc_row(db, "홍길동", "가나다벤처스", title)
    _queue(logged_in, [row.id])
    [item] = _claim(logged_in)
    r = logged_in.post(f"/api/agent/items/{item['id']}/result",
                       json={"status": "sent", "verify_reason": "unreadable"},
                       headers=auth(DEMO_TOKEN))
    assert r.status_code == 200, r.text
    assert _fresh(db, VcContact, row.id).room_verified == "not_found"
    assert _fresh(db, SendItem, item["id"]).status == "failed"


# ══════════════════════════════════════════════════════════════════════════
#  회사명으로 찾는 줄 — 스타트업 [카톡방 찾기·확인]
# ══════════════════════════════════════════════════════════════════════════

def _company_job(db):
    row = VcContact(user_id=1, source_sheet="스타트업 · 강민준", name="백대표",
                    firm="자자랩스")
    job = SendJob(user_id=1, kind="verify_room", topic=ROOM_SEARCH_TOPIC,
                  status="running", total=1)
    db.add_all([row, job])
    db.flush()
    item = SendItem(job_id=job.id, contact_id=row.id, room_name="", message="",
                    status="sending")
    db.add(item)
    db.commit()
    return job.id, item.id


@pytest.mark.parametrize("reason, sentence, result", [
    ("unreadable",
     "방 찾기가 끝났습니다 — 찾음 0 · 여럿 0 · 못 찾음 0 · 확인 못 함 1" + TAIL,
     "확인 못 함"),
    (None, "방 찾기가 끝났습니다 — 찾음 0 · 여럿 0 · 못 찾음 1", "못 찾음"),
])
def test_a_company_search_counts_unchecked_apart(logged_in, db, users, reason,
                                                 sentence, result):
    job_id, item_id = _company_job(db)
    _report(logged_in, item_id, **({"verify_reason": reason} if reason else {}))
    _end_round(logged_in, job_id)

    item = _fresh(db, SendItem, item_id)
    assert item.status == "failed"
    assert room_unchecked.is_note(item.error) is bool(reason)
    done = logged_in.get(f"/api/jobs/{job_id}").json()
    assert done["room_done"] == {"sentence": sentence, "pick": True}
    assert done["items"][0]["result"] == result


# ══════════════════════════════════════════════════════════════════════════
#  증거 화면 — 확인을 못 한 건에만 담는다
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def shots(tmp_path, monkeypatch):
    from app.routers import agent_api

    monkeypatch.setattr(agent_api, "AGENT_LOG_DIR", tmp_path / "agent_logs")
    monkeypatch.setattr(agent_api.config, "BASE_DIR", tmp_path)
    return tmp_path / "agent_logs"


PNG = base64.b64encode(b"png-bytes").decode()


def test_the_screen_of_an_unchecked_item_is_kept(client, db, users, team, shots):
    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    _sender_report(client, item_id, verify_reason="unreadable", screenshot_b64=PNG)
    assert (shots / f"{item_id}.png").read_bytes() == b"png-bytes"
    assert _fresh(db, SendItem, item_id).screenshot_path == f"agent_logs/{item_id}.png"


@pytest.mark.parametrize("body", [
    {},                                                        # 까닭이 없다
    {"verify_reason": "unreadable", "candidates": ["가나다 홍길동님 방"]},
    {"status": "sent", "verify_result": "verified", "verify_reason": "unreadable"},
])
def test_no_screen_is_kept_for_any_other_verify_result(client, db, users, team, shots,
                                                       body):
    """방 확인 건은 예전처럼 화면을 담지 않는다 — 확인을 못 한 건만 예외다."""
    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    _sender_report(client, item_id, screenshot_b64=PNG, **body)
    assert not shots.exists() or not list(shots.iterdir())
    assert _fresh(db, SendItem, item_id).screenshot_path is None


# ══════════════════════════════════════════════════════════════════════════
#  발송기 → 서버 — 한 줄로 이어 본다
# ══════════════════════════════════════════════════════════════════════════

class Relay:
    """발송기의 서버 호출을 시험 클라이언트로 그대로 넘긴다(`agent/main.AgentClient` 와
    같은 칸을 같은 규칙으로 싣는다 — 까닭은 있을 때만)."""

    def __init__(self, client, token):
        self.client = client
        self.headers = auth(token)
        self.diags = []

    def job_state(self, job_id):
        return self.client.get(f"/api/agent/jobs/{job_id}/state",
                               headers=self.headers).json()

    def report_item(self, item_id, status, error=None, screenshot_b64=None,
                    verify_result=None, found_room=None, candidates=None,
                    verify_reason=None):
        body = {"status": status, "error": error, "screenshot_b64": screenshot_b64,
                "verify_result": verify_result, "found_room": found_room,
                "candidates": candidates}
        if verify_reason:
            body["verify_reason"] = verify_reason
        r = self.client.post(f"/api/agent/items/{item_id}/result", json=body,
                             headers=self.headers)
        assert r.status_code == 200, r.text

    def report_diagnostics(self, payload):
        self.diags.append(payload)
        r = self.client.post("/api/agent/diagnostics", json=payload,
                             headers=self.headers)
        assert r.status_code == 200, r.text

    def report_job(self, job_id, status):
        r = self.client.post(f"/api/agent/jobs/{job_id}/status",
                             json={"status": status}, headers=self.headers)
        assert r.status_code == 200, r.text


def test_a_blind_windows_pc_ends_as_unchecked_on_the_server(
        client, db, users, team, shots, tmp_path, monkeypatch):
    """결과 줄을 못 읽고 맨 위 방도 안 열리는 PC — [전체 방 확인] 한 회차를 진짜 방 확인
    고리로 돌려, 서버에 무엇이 서는지 본다."""
    import agent.diagnose
    import agent.main as agent_main
    from app import config
    from tests.test_win_verify_unreadable import BlindWin

    monkeypatch.setattr(agent.diagnose, "list_titles", lambda: ["카카오톡"])
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(BlindWin, "_shot_window",
                        lambda self, win: PNG, raising=True)
    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    polled = client.get("/api/agent/poll", params={"kinds": "deal_intro,verify_room"},
                        headers=auth(OTHER_TOKEN)).json()
    relay = Relay(client, OTHER_TOKEN)
    agent_main.process_verify_job(relay, BlindWin(), polled,
                                  {"verify_delay_min_sec": 0, "verify_delay_max_sec": 0,
                                   "room_marker": ""})

    db.expire_all()
    job = db.get(SendJob, job.id)
    assert job.status == "done_with_errors"
    item = db.get(SendItem, item_id)
    assert item.status == "failed"
    assert item.error == room_unchecked.MESSAGES["unreadable"]
    row = sender_rooms.row_of(db, users["u2"].id, team["ok"].id)
    assert sender_rooms.state_of(row) == "unchecked" and row.verified == 0
    # 증거 — 화면 한 장과 진단 기록 한 줄이 서버에 남는다.
    assert (shots / f"{item_id}.png").read_bytes() == b"png-bytes"
    [diag] = relay.diags
    assert diag["kind"] == "verify_unreadable" and diag["target_room"] == OWN
    log = (tmp_path / "agent_reports.log").read_text(encoding="utf-8")
    assert '"kind": "verify_unreadable"' in log and "방 확인을 못 했습니다" in log


def test_the_old_agent_loop_still_ends_with_the_old_words(logged_in, db, users):
    """까닭을 모르는 발송기(0.11.15 까지 · 맥) — 서버 문구는 한 글자도 안 바뀐다."""
    row = _vc_row(db, "홍길동", "가나다벤처스")
    job_id = _queue(logged_in, [row.id])["job_id"]
    while _run_old_agent(logged_in, _Kakao([])):
        pass
    db.expire_all()
    job = db.get(SendJob, job_id)
    assert job.status == "done_with_errors"
    [item] = job.items
    assert item.error == OLD_SEARCH_TEXT
    done = logged_in.get(f"/api/jobs/{job_id}").json()
    assert done["room_done"] == {
        "sentence": "방 연결 확인이 끝났습니다 — 확인됨 0 · 불일치 1", "pick": False}


def test_no_sender_room_row_keeps_a_mark_from_another_shape(db, users, team):
    """후보 칸이 깨졌거나 다른 모양이어도 화면은 선다 — 표시가 아니면 예전 판정이다."""
    row = SenderRoom(sender_user_id=users["u2"].id, contact_id=team["ok"].id,
                     candidates="{not json", checked_at="2026-11-18T10:00:00")
    db.add(row)
    db.commit()
    assert sender_rooms.unchecked_note(row) == ""
    assert sender_rooms.state_of(row) == "not_found"
    row.candidates = json.dumps({"other": 1})
    assert sender_rooms.state_of(row) == "not_found"
    row.candidates = json.dumps({"unchecked": ""})
    assert sender_rooms.state_of(row) == "not_found"
