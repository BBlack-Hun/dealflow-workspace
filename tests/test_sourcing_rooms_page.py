"""딜 소싱 **카톡방 찾기 전용 화면**(`/sourcing/rooms`)과 방 찾기 [중단].

    ① 줄마다 상태(확인 완료 · 골라야 함 · 못 찾음 · 확인 못 함 · 아직 안 찾아봄)와 머리 셈
    ② 그 화면의 찾기 · 확정은 딜 소싱 화면과 같은 길을 지나 그 화면으로 돌아온다
    ③ 아직 도는 회차가 진행 셈 · [중단] 과 함께 서고, 실린 줄은 `찾는 중` 이다
    ④ [중단] — 남은 건은 **찾기 전 그대로**다(후보 · 확정을 안 지운다). 늦게 온 결과도
       버린다. 발송기에는 멈추라고 답한다. 남의 회차는 못 멈춘다
    ⑤ 보내는 계정은 그 계정 카톡 기준 제목으로 선다 · 팀 현황 판에도 도는 회차가 선다

이름 · 회사 · 방 제목은 모두 지어낸 값이다.
"""
from __future__ import annotations

import re

from app.models import SendItem, SendJob, SourcingContact
from app.services import room_match, room_unchecked, sourcing_rooms
from tests.conftest import DEMO_TOKEN, OTHER_TOKEN, auth
from tests.test_sender_rooms import (GROUP, _login, _member_report,  # noqa: F401
                                     _member_search, sourcing, team)

ROOMS_TAB = "all:rooms"


def _states(db, user):
    db.expire_all()
    return {r["name"]: r["state"] for r in sourcing_rooms.board(db, user)["rows"]}


def test_the_page_shows_every_state_and_counts(client, db, users):
    job, item, rows = _member_search(client, db, ["가확정", "나후보", "다없음", "라못봄", "마대기"])
    one, two, none, blind, _ = rows
    db.add_all([SourcingContact(bucket=GROUP, name="바적음", kakao_room_name="바적음 방"),
                SourcingContact(bucket=GROUP, name="사불참", participation="불참여")])
    db.commit()
    _member_report(client, item[one.id], status="sent", verify_result="verified",
                   found_room="가확정 딜소싱", candidates=["가확정 딜소싱"])
    _member_report(client, item[two.id], verify_result="ambiguous",
                   candidates=["나후보 방 하나", "나후보 방 둘"])
    _member_report(client, item[none.id])
    _member_report(client, item[blind.id], verify_reason="unreadable")

    assert _states(db, users["u1"]) == {
        "가확정": "confirmed", "나후보": "picks", "다없음": "not_found",
        "라못봄": "unchecked", "마대기": "never", "바적음": "typed"}
    page = client.get("/sourcing/rooms")
    assert page.status_code == 200
    summary = re.sub(r"<[^>]+>|\s+", "", page.text.split('sourcing-room-summary">')[1]
                     .split("</p>")[0])
    assert summary == ("대상6명·확인완료1·골라야함1·못찾음1·확인못함1·아직안찾아봄1"
                       "·카톡방이름직접적음1")
    assert room_unchecked.MESSAGES["unreadable"] in page.text
    assert "사불참" not in page.text
    # 아직 도는 회차 — 진행 셈 · [중단] · 남은 줄은 `찾는 중`.
    assert f'data-job="{job.id}"' in page.text and "js-room-job-stop" in page.text
    assert page.text.count('data-testid="sourcing-room-busy"') == 1
    # 딜 소싱 화면에서 오는 길.
    assert 'href="/sourcing/rooms"' in client.get("/sourcing").text


def test_search_and_confirm_from_the_page_come_back_to_it(client, db, users):
    db.add(SourcingContact(bucket=GROUP, name="가대상", title="심사역"))
    db.commit()
    row = db.execute(SourcingContact.__table__.select()).first()
    _login(client, "01000000001")
    board = sourcing_rooms.board(db, users["u1"])
    assert (board["never_ids"], board["retry_ids"]) == (str(row.id), "")

    answer = client.post("/sourcing/rooms/search", data={"tab": ROOMS_TAB, "ids": str(row.id)},
                         follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"].startswith("/sourcing/rooms?msg=")
    job = db.query(SendJob).one()
    assert job.user_id == users["u1"].id          # 누른 계정 PC 의 카톡에서 찾는다
    # 찾는 중인 줄은 다시 싣지 않는다.
    assert sourcing_rooms.board(db, users["u1"])["never_ids"] == ""

    _member_report(client, job.items[0].id, verify_result="ambiguous",
                   candidates=["가대상 방 하나", "가대상 방 둘"])
    answer = client.post(f"/sourcing/{row.id}/room-confirm",
                         data={"tab": ROOMS_TAB, "room": "가대상 방 둘"},
                         follow_redirects=False)
    assert answer.headers["location"].startswith("/sourcing/rooms?msg=")
    db.expire_all()
    assert db.get(SourcingContact, row.id).kakao_room_name == "가대상 방 둘"


def test_stop_leaves_the_rest_as_it_was(client, db, users):
    job, item, rows = _member_search(client, db, ["가끝남", "나후보둠", "다처음"])
    done, kept, fresh = rows
    room_match.save_candidates(kept, ["나후보둠 방 하나", "나후보둠 방 둘"],
                               at="2026-11-18T10:00:00", query="나후보둠 심사역")
    db.commit()
    _member_report(client, item[done.id])                      # 한 건은 이미 돌았다

    assert client.post(f"/api/jobs/{job.id}/cancel").json()["status"] == "canceled"
    # 발송기가 건 사이에 묻는 자리 — 멈추라고 답한다(`agent/main.py: check_before_send`).
    state = client.get(f"/api/agent/jobs/{job.id}/state", headers=auth(DEMO_TOKEN)).json()
    assert state["canceled"] is True
    # 중단 뒤 늦게 온 결과 — 받지 않는다.
    _member_report(client, item[fresh.id], status="sent", verify_result="verified",
                   found_room="다처음 딜소싱", candidates=["다처음 딜소싱"])
    _member_report(client, item[kept.id])

    assert _states(db, users["u1"]) == {
        "가끝남": "not_found", "나후보둠": "picks", "다처음": "never"}
    assert [p["room"] for p in sourcing_rooms.picks(db.get(SourcingContact, kept.id))["rooms"]
            ] == ["나후보둠 방 하나", "나후보둠 방 둘"]
    assert db.get(SourcingContact, fresh.id).kakao_room_name is None
    assert {db.get(SendItem, i).status for i in (item[kept.id], item[fresh.id])} == {"canceled"}
    page = client.get("/sourcing/rooms").text
    assert "js-room-job" not in page                           # 도는 회차가 없다
    assert sourcing_rooms.board(db, users["u1"])["never_ids"] == str(fresh.id)


def test_nobody_stops_someone_elses_search(client, db, users):
    job, _, _ = _member_search(client, db, ["가남의것"])
    _login(client, "01000000002")
    assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 404
    db.expire_all()
    assert db.get(SendJob, job.id).status == "queued"
    # 남의 회차는 내 화면에 서지 않는다.
    assert "js-room-job" not in client.get("/sourcing/rooms").text


def test_the_sender_account_sees_its_own_titles(client, db, users, team, sourcing):
    from app.services import sender_rooms

    _login(client, "01000000002")
    answer = client.post("/sourcing/rooms/search",
                         data={"tab": ROOMS_TAB, "ids": str(sourcing["noroom"].id)},
                         headers={"Accept": "application/json"})
    job = db.get(SendJob, answer.json()["job_id"])
    board = sourcing_rooms.board(db, users["u2"])
    assert board["sender"] and [j["id"] for j in board["jobs"]] == [job.id]
    r = client.post(f"/api/agent/items/{job.items[0].id}/result", headers=auth(OTHER_TOKEN),
                    json={"status": "failed", "verify_result": "not_found",
                          "verify_reason": "locked"})
    assert r.status_code == 200
    # 팀 현황 판에도 도는 회차가 선다 — 그 계정으로 열었으니 [중단] 도.
    team_page = client.get("/team/sender-rooms").text
    assert f'data-job="{job.id}"' in team_page and "js-room-job-stop" in team_page

    assert _states(db, users["u2"]) == {"홍소싱": "never", "이빈방": "unchecked"}
    page = client.get("/sourcing/rooms").text
    assert room_unchecked.MESSAGES["locked"] in page
    assert sender_rooms.row_of(db, users["u2"].id, sourcing["noroom"].id,
                               sourcing=True).verified == 0
