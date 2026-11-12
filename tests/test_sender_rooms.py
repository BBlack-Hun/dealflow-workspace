"""보내는 계정 카톡 기준 방 제목 — **확인만 하고, 담당 팀원의 줄은 안 건드린다.**

1. 확인 대상은 팀원 전원의 보낼 수 있는 투자사 담당자다(보내는 계정 본인 것 ·
   검토중단 · 연결 전 · 감춘 줄 · 방 이름 없음 · 메일 전용은 빠진다).
2. [전체 방 확인] 은 방 확인 잡 하나를 **보내는 계정 것으로** 세운다 — 그 계정
   기기만 집어가고, 검색어는 담당 팀원의 방 제목 → 이름 → 회사.
3. 담당 팀원의 제목과 똑같은 방이 **정확히 하나**면 저절로 확인됨, 다르거나
   여럿이면 후보만 담는다. 담당 팀원의 방 이름 · 확인 표시는 그대로다.
4. 자동화가 고르는 방: 확인된 제목 → 없으면 담당 팀원의 제목.
5. 확정은 후보에 있는 글자만, 관리자만.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

OWN = "홍길동 심사역 가나다벤처스 Deal 공유"


@pytest.fixture()
def team(db, users):
    """u2 가 보내는 계정(관리자), u1 이 담당 팀원."""
    from app.models import AutoSendSetting, VcContact

    users["u2"].role = "admin"
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))

    def contact(owner, name, room, **kw):
        row = VcContact(user_id=owner.id, name=name, firm="가나다벤처스",
                        title="심사역", kakao_room_name=room,
                        connect_stage=kw.pop("connect_stage", "connected"),
                        source_sheet="내 명단", **kw)
        db.add(row)
        return row

    rows = {
        "ok": contact(users["u1"], "홍길동", OWN),
        "paused": contact(users["u1"], "김멈춤", "멈춤방", status="paused"),
        "not_connected": contact(users["u1"], "이연결", "연결방",
                                 connect_stage="in_progress"),
        "hidden": contact(users["u1"], "박감춤", "감춤방", is_hidden=1),
        "no_room": contact(users["u1"], "최빈방", None),
        "email_only": contact(users["u1"], "정메일", "메일방", channel_email=1,
                              channel_kakao=0),
        "sender_own": contact(users["u2"], "강본인", "본인방"),
    }
    db.commit()
    return rows


def _sender(db, users):
    return users["u2"]


def test_targets_are_everyone_elses_sendable_contacts(db, users, team):
    from app.services import sender_rooms

    got = [c.id for c in sender_rooms.targets(db, users["u2"])]
    assert got == [team["ok"].id]


def test_check_job_belongs_to_the_sender_and_searches_by_owner_title(
        client, db, users, team):
    from app.models import SENDER_ROOM_TOPIC
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    assert (job.kind, job.topic, job.user_id) == ("verify_room", SENDER_ROOM_TOPIC,
                                                  users["u2"].id)
    assert [(i.contact_id, i.room_name, i.message) for i in job.items] == [
        (team["ok"].id, OWN, "")]

    kinds = {"kinds": "deal_intro,verify_room"}
    assert client.get("/api/agent/poll", params=kinds,
                      headers=auth(DEMO_TOKEN)).status_code == 204
    got = client.get("/api/agent/poll", params=kinds, headers=auth(OTHER_TOKEN))
    item = got.json()["items"][0]
    assert (item["query"], item["name"], item["firm"]) == (OWN, "홍길동", "가나다벤처스")


def _report(client, item_id, **body):
    payload = {"status": "sent", "verify_result": "verified"}
    payload.update(body)
    return client.post(f"/api/agent/items/{item_id}/result", json=payload,
                       headers=auth(OTHER_TOKEN))


def _row(db, users, team):
    from app.services import sender_rooms

    db.expire_all()
    return sender_rooms.row_of(db, users["u2"].id, team["ok"].id)


def test_one_exact_match_is_applied_without_touching_the_owner_row(
        client, db, users, team):
    from app.models import VcContact
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    _report(client, item_id, found_room=OWN, candidates=[OWN])
    row = _row(db, users, team)
    assert (row.verified, row.room_name) == (1, OWN)
    owner_row = db.get(VcContact, team["ok"].id)
    assert owner_row.kakao_room_name == OWN
    assert owner_row.room_verified == "unverified"   # 주인의 확인 표시는 그대로


def test_a_renamed_room_is_only_a_candidate(client, db, users, team):
    from app.models import SendItem, VcContact
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    item_id = job.items[0].id
    _report(client, item_id, found_room="가나다 홍길동님 방",
            candidates=["가나다 홍길동님 방"])
    row = _row(db, users, team)
    assert row.verified == 0 and row.room_name is None
    assert sender_rooms.candidates(row) == ["가나다 홍길동님 방"]
    item = db.get(SendItem, item_id)
    assert item.status == "failed" and "후보 1개" in item.error
    # 담당 팀원의 방 이름은 **바뀌지 않는다**(투자사 쪽 확인이면 바뀌었을 것이다).
    assert db.get(VcContact, team["ok"].id).kakao_room_name == OWN


def test_exact_among_several_is_applied(client, db, users, team):
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    _report(client, job.items[0].id, verify_result="ambiguous", status="failed",
            candidates=["다른 방", OWN])
    row = _row(db, users, team)
    assert (row.verified, row.room_name) == (1, OWN)


def test_two_rooms_with_the_same_title_stay_candidates(client, db, users, team):
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    _report(client, job.items[0].id, verify_result="ambiguous", status="failed",
            candidates=[OWN, OWN])
    row = _row(db, users, team)
    assert row.verified == 0
    assert sender_rooms.state_of(row) == sender_rooms.PICKS


def test_plain_verify_without_search_counts_as_the_owner_title(
        client, db, users, team):
    """검색 기능이 없는 발송기는 주인의 제목으로 방을 열어 보고 `verified` 만 준다."""
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    _report(client, job.items[0].id)
    row = _row(db, users, team)
    assert (row.verified, row.room_name) == (1, OWN)


def test_room_for_prefers_the_confirmed_sender_title(db, users, team):
    from app.models import SenderRoom
    from app.services import sender_rooms

    contact = team["ok"]
    assert sender_rooms.room_for(db, users["u2"].id, contact) == OWN
    db.add(SenderRoom(sender_user_id=users["u2"].id, contact_id=contact.id,
                      room_name="곽 카톡의 제목", verified=1,
                      candidates='["곽 카톡의 제목"]', checked_at="2026-10-13"))
    db.commit()
    assert sender_rooms.room_for(db, users["u2"].id, contact) == "곽 카톡의 제목"
    assert sender_rooms.rooms_for(db, users["u2"].id, [contact]) == {
        contact.id: "곽 카톡의 제목"}
    # 다른 보내는 계정에게는 영향이 없다.
    assert sender_rooms.room_for(db, users["u1"].id, contact) == OWN
    # 보내는 계정 본인의 담당자는 그 제목이 곧 기준이다.
    own = team["sender_own"]
    assert sender_rooms.room_for(db, users["u2"].id, own) == "본인방"


def test_confirm_only_takes_a_candidate(db, users, team):
    from app.models import SenderRoom
    from app.services import sender_rooms

    db.add(SenderRoom(sender_user_id=users["u2"].id, contact_id=team["ok"].id,
                      candidates='["후보 방"]', checked_at="2026-10-13"))
    db.commit()
    with pytest.raises(sender_rooms.NotPickable):
        sender_rooms.confirm(db, users["u2"].id, team["ok"].id, "지어낸 방")
    row = sender_rooms.confirm(db, users["u2"].id, team["ok"].id, "후보 방")
    assert (row.verified, row.room_name) == (1, "후보 방")
    sender_rooms.clear(db, users["u2"].id, team["ok"].id)
    assert sender_rooms.room_for(db, users["u2"].id, team["ok"]) == OWN


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def test_page_and_check_button_for_admin(client, db, users, team):
    from app.models import SendJob

    _login(client, "01000000002")
    page = client.get("/team/sender-rooms")
    assert page.status_code == 200
    assert "PC로 전체 방 확인 (1명)" in page.text
    answer = client.post("/team/sender-rooms/check",
                         data={"sender_id": users["u2"].id}, follow_redirects=False)
    assert answer.status_code == 303
    jobs = db.execute(select(SendJob)).scalars().all()
    assert [(j.kind, j.user_id) for j in jobs] == [("verify_room", users["u2"].id)]


def test_confirm_from_the_page(client, db, users, team):
    from app.models import SenderRoom
    from app.services import sender_rooms

    db.add(SenderRoom(sender_user_id=users["u2"].id, contact_id=team["ok"].id,
                      candidates='["후보 방"]', checked_at="2026-10-13"))
    db.commit()
    _login(client, "01000000002")
    client.post(f"/team/sender-rooms/{team['ok'].id}/confirm",
                data={"sender_id": users["u2"].id, "room": "후보 방"},
                follow_redirects=False)
    db.expire_all()
    assert sender_rooms.room_for(db, users["u2"].id, team["ok"]) == "후보 방"


def test_non_admin_cannot_check(client, db, users, team):
    from app.models import SendJob

    _login(client, "01000000001")
    client.post("/team/sender-rooms/check", data={"sender_id": users["u2"].id},
                follow_redirects=False)
    assert db.execute(select(SendJob)).scalars().all() == []


# ── 딜 소싱 명단도 보내는 계정 기준 제목을 따로 둔다(0135) ─────────────────────
#
# 딜 소싱 방 이름은 [방 후보 찾기]를 누른 팀원 카톡의 제목이다. 보내는 계정(자동화)이
# 찾은 제목은 `sender_rooms` 에만 담기고, 명단의 방 이름 · 후보 · 확인 표시는 그대로다.
# 그 계정이 딜 소싱 분께 보낼 때는 확인된 제목이 먼저, 없으면 명단의 방 이름.

GROUP = "시리즈 A 이상 딜 소싱 참여 심사역"
SRC_OWN = "홍소싱 심사역 방"


@pytest.fixture()
def sourcing(db, users, team):
    from app.models import SourcingContact

    def person(name, room=None, participation="참여"):
        row = SourcingContact(bucket=GROUP, name=name, firm="가나다벤처스", title="심사역",
                              kakao_room_name=room, participation=participation)
        db.add(row)
        db.flush()
        return row

    rows = {"room": person("홍소싱", SRC_OWN),
            "noroom": person("이빈방"),
            "left": person("박불참", "불참방", "불참여")}
    db.commit()
    return rows


def _sourcing_item(job, person):
    return next(i for i in job.items if i.sourcing_contact_id == person.id)


def test_check_also_carries_sourcing_people_except_those_who_left(
        client, db, users, team, sourcing):
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    assert job.total == 3        # 투자사 1 + 딜 소싱 2(불참여 빼고)
    got = {i.sourcing_contact_id: i.room_name for i in job.items if i.sourcing_contact_id}
    assert got == {sourcing["room"].id: SRC_OWN,
                   sourcing["noroom"].id: "이빈방 심사역"}

    kinds = {"kinds": "deal_intro,verify_room"}
    items = client.get("/api/agent/poll", params=kinds,
                       headers=auth(OTHER_TOKEN)).json()["items"]
    by_room = {i["room_name"]: i for i in items}
    # 방 이름이 있으면 그 제목, 없으면 이름+직함 — 못 찾으면 이름. 회사는 안 보낸다.
    assert (by_room[SRC_OWN]["query"], by_room[SRC_OWN]["name"]) == (SRC_OWN, "홍소싱")
    assert by_room["이빈방 심사역"]["query"] == "이빈방 심사역"
    assert "firm" not in by_room[SRC_OWN]


def test_sourcing_result_goes_to_the_sender_table_only(client, db, users, team, sourcing):
    from app.models import SourcingContact
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    same = _sourcing_item(job, sourcing["room"]).id
    renamed = _sourcing_item(job, sourcing["noroom"]).id
    _report(client, same, found_room=SRC_OWN, candidates=[SRC_OWN])
    _report(client, renamed, verify_result="ambiguous", status="failed",
            candidates=["곽 카톡 이빈방", "다른 방"])
    db.expire_all()

    row = sender_rooms.row_of(db, users["u2"].id, sourcing["room"].id, sourcing=True)
    assert (row.verified, row.room_name, row.contact_id) == (1, SRC_OWN, None)
    picks = sender_rooms.row_of(db, users["u2"].id, sourcing["noroom"].id, sourcing=True)
    assert picks.verified == 0
    assert sender_rooms.candidates(picks) == ["곽 카톡 이빈방", "다른 방"]
    # 딜 소싱 명단의 줄은 **그대로**다 — 방 이름 · 후보 · 확인 표시 모두.
    for key in ("room", "noroom"):
        person = db.get(SourcingContact, sourcing[key].id)
        assert person.room_candidates is None
        assert person.room_verified == "unverified"
    assert db.get(SourcingContact, sourcing["noroom"].id).kakao_room_name is None


def test_sourcing_rooms_for_prefers_the_confirmed_sender_title(db, users, team, sourcing):
    from app.models import SenderRoom
    from app.services import sender_rooms

    person = sourcing["room"]
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person]) == {}
    db.add(SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=person.id,
                      candidates='["곽 카톡 홍소싱"]', checked_at="2026-11-10"))
    db.commit()
    sender_rooms.confirm(db, users["u2"].id, person.id, "곽 카톡 홍소싱", sourcing=True)
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person]) == {
        person.id: "곽 카톡 홍소싱"}
    # 다른 계정에는 영향이 없다 · 같은 번호의 투자사 줄과 섞이지 않는다.
    assert sender_rooms.sourcing_rooms_for(db, users["u1"].id, [person]) == {}
    assert sender_rooms.row_of(db, users["u2"].id, person.id) is None
    sender_rooms.clear(db, users["u2"].id, person.id, sourcing=True)
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person]) == {}


def test_page_lists_sourcing_people_and_confirms_by_kind(client, db, users, team, sourcing):
    from app.models import SenderRoom
    from app.services import sender_rooms

    person = sourcing["noroom"]
    db.add(SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=person.id,
                      candidates='["곽 카톡 이빈방"]', checked_at="2026-11-10"))
    db.commit()
    _login(client, "01000000002")
    page = client.get("/team/sender-rooms")
    assert "PC로 전체 방 확인 (3명)" in page.text
    assert f"딜 소싱 · {GROUP}" in page.text
    assert 'data-kind="sourcing"' in page.text
    client.post(f"/team/sender-rooms/{person.id}/confirm",
                data={"sender_id": users["u2"].id, "room": "곽 카톡 이빈방",
                      "kind": "sourcing"}, follow_redirects=False)
    db.expire_all()
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person]) == {
        person.id: "곽 카톡 이빈방"}


def test_sender_pressing_sourcing_search_keeps_the_list_untouched(
        client, db, users, team, sourcing):
    """보내는 계정이 딜 소싱 화면에서 [방 후보 찾기]를 눌러도 → 보내는 계정 기준 표로."""
    from app.models import SENDER_ROOM_TOPIC, SendJob, SourcingContact
    from app.services import sender_rooms

    _login(client, "01000000002")
    person = sourcing["noroom"]
    answer = client.post("/sourcing/rooms/search",
                         data={"tab": GROUP, "ids": str(person.id)},
                         headers={"Accept": "application/json"})
    assert answer.status_code == 200 and "보내는 계정 기준 방 제목" in answer.json()["note"]
    [job] = db.execute(select(SendJob)).scalars().all()
    assert (job.user_id, job.topic) == (users["u2"].id, SENDER_ROOM_TOPIC)
    item = job.items[0]
    _report(client, item.id, verify_result="ambiguous", status="failed",
            candidates=["곽 카톡 이빈방"])
    db.expire_all()
    assert db.get(SourcingContact, person.id).room_candidates is None
    # 하나뿐이라 보내는 계정 표에서는 그 방으로 확정된다(사용자 결정 2026-11-10).
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person]) == {
        person.id: "곽 카톡 이빈방"}


def test_member_pressing_sourcing_search_is_unchanged(client, db, users, team, sourcing):
    """보내는 계정이 아니면 예전 그대로 — 누른 사람 PC, 명단의 후보로."""
    from app.models import SOURCING_ROOM_TOPIC, SendJob

    _login(client, "01000000001")
    client.post("/sourcing/rooms/search",
                data={"tab": GROUP, "ids": str(sourcing["noroom"].id)})
    [job] = db.execute(select(SendJob)).scalars().all()
    assert (job.user_id, job.topic) == (users["u1"].id, SOURCING_ROOM_TOPIC)


def test_sender_sends_to_sourcing_with_its_own_title(db, users, team, sourcing):
    """자동화(참여 제안 · 소싱 리마인드)와 손으로 보내는 딜 소싱 제안 — 확인된 제목 먼저."""
    from app.models import SenderRoom
    from app.routers.deals import _room_of
    from app.services import sender_rooms
    from app.services.automations import sourcing_remind

    person = sourcing["room"]
    db.add(SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=person.id,
                      room_name="곽 카톡 홍소싱", verified=1))
    db.commit()
    mine = sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person])
    assert _room_of(person, {}, mine) == "곽 카톡 홍소싱"
    assert _room_of(person, {}) == SRC_OWN               # 다른 계정은 명단의 방 이름
    assert sourcing_remind._room(db, users["u2"], person, {}, mine) == "곽 카톡 홍소싱"
    assert sourcing_remind._room(db, users["u1"], person, {}) == SRC_OWN


def test_deleting_a_sourcing_row_takes_its_sender_titles(client, db, users, team, sourcing):
    from app.models import SenderRoom
    from app.services import sourcing_rooms

    person = sourcing["room"]
    db.add(SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=person.id,
                      room_name="곽 카톡 홍소싱", verified=1))
    db.commit()
    sourcing_rooms.forget(db, person.id)
    db.commit()
    assert db.execute(select(SenderRoom)).scalars().all() == []


# ── 딜 소싱 분은 찾은 방이 하나면 그 방으로 확정(사용자 결정 2026-11-10) ─────────
#
# "딜 소싱에서 방후보 찾기 할때 후보가 1개면 무조건 그걸로 매칭해줘" · "2개 이상일
# 경우부터 고르게 해야지". 사람이 [이 방으로 확정] 한 것과 같은 길(`confirm`)이고,
# 딜 소싱 명단의 줄은 그대로다. 투자사 담당자 줄은 예전 그대로(하나뿐이어도 후보만 —
# `test_a_renamed_room_is_only_a_candidate`).

def test_a_single_sourcing_candidate_is_confirmed_in_the_sender_table_only(
        client, db, users, team, sourcing):
    import json

    from app.models import EditLog, SendItem, SourcingContact
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    item_id = _sourcing_item(job, sourcing["noroom"]).id
    _report(client, item_id, verify_result="ambiguous", status="failed",
            candidates=["곽 카톡 이빈방"])
    db.expire_all()
    row = sender_rooms.row_of(db, users["u2"].id, sourcing["noroom"].id, sourcing=True)
    assert (row.verified, row.room_name) == (1, "곽 카톡 이빈방")
    assert db.get(SendItem, item_id).status == "sent"
    person = db.get(SourcingContact, sourcing["noroom"].id)
    assert (person.kakao_room_name, person.room_candidates, person.room_verified) == (
        None, None, "unverified")
    # 수정 로그 — 찾기를 건 계정(u2) 이름으로.
    [log] = db.query(EditLog).filter_by(table_name="sender_rooms", row_id=row.id).all()
    assert log.actor_user_id == users["u2"].id
    assert "room_name" in {c["field"] for c in json.loads(log.changes_json)}


def test_two_sourcing_candidates_or_one_title_twice_stay_candidates(
        client, db, users, team, sourcing):
    from app.services import sender_rooms

    job = sender_rooms.queue_check(db, users["u2"])
    _report(client, _sourcing_item(job, sourcing["noroom"]).id, verify_result="ambiguous",
            status="failed", candidates=["곽 카톡 이빈방", "다른 방"])
    _report(client, _sourcing_item(job, sourcing["room"]).id, verify_result="ambiguous",
            status="failed", candidates=["곽 카톡 홍소싱", "곽 카톡 홍소싱"])
    for key in ("noroom", "room"):
        db.expire_all()
        row = sender_rooms.row_of(db, users["u2"].id, sourcing[key].id, sourcing=True)
        assert (row.verified, row.room_name) == (0, None), key


def test_a_new_single_sourcing_room_replaces_a_title_no_longer_found(
        client, db, users, team, sourcing):
    from app.models import SenderRoom
    from app.services import sender_rooms

    person = sourcing["noroom"]
    db.add(SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=person.id,
                      room_name="예전 제목", verified=1, candidates='["예전 제목"]',
                      checked_at="2026-11-01"))
    db.commit()
    job = sender_rooms.queue_check(db, users["u2"])
    _report(client, _sourcing_item(job, person).id, verify_result="ambiguous",
            status="failed", candidates=["바뀐 제목"])
    db.expire_all()
    row = sender_rooms.row_of(db, users["u2"].id, person.id, sourcing=True)
    assert (row.verified, row.room_name) == (1, "바뀐 제목")


def test_board_shows_pick_buttons_for_sourcing_only_from_two(
        client, db, users, team, sourcing):
    """하나뿐인데 확정 안 된 딜 소싱 줄(확정을 거둠 · 예전에 담긴 후보)에는 고르는
    단추 · `골라 주세요` 가 없다. 투자사 담당자 줄은 하나여도 고른다."""
    from app.models import SenderRoom
    from app.services import sender_rooms

    db.add_all([
        SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=sourcing["noroom"].id,
                   candidates='["곽 카톡 이빈방"]', checked_at="2026-11-10"),
        SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=sourcing["room"].id,
                   candidates='["가 방", "나 방"]', checked_at="2026-11-10"),
        SenderRoom(sender_user_id=users["u2"].id, contact_id=team["ok"].id,
                   candidates='["후보 방"]', checked_at="2026-11-10"),
    ])
    db.commit()
    rows = {(r["kind"], r["contact_id"]): r
            for r in sender_rooms.board(db, users["u2"])["rows"]}
    single = rows[("sourcing", sourcing["noroom"].id)]
    assert not single["choose"] and "골라" not in single["state_label"]
    assert rows[("sourcing", sourcing["room"].id)]["choose"]
    assert rows[("vc", team["ok"].id)]["choose"]

    _login(client, "01000000002")
    page = client.get("/team/sender-rooms").text
    forms = re.findall(r'action="/team/sender-rooms/(\d+)/confirm"[^<]*'
                       r'<input[^>]*>\s*<input type="hidden" name="kind" value="(\w+)">',
                       page)
    assert ("sourcing", str(sourcing["noroom"].id)) not in {(k, c) for c, k in forms}
    assert {(k, c) for c, k in forms} >= {("sourcing", str(sourcing["room"].id)),
                                          ("vc", str(team["ok"].id))}


# ── 보내는 계정으로 연 딜 소싱 화면 — 그 계정 전용 제목이 카톡방 칸에 선다(11/11) ──
#
# 사용자: 보내는 계정으로 [방 후보 찾기]를 했는데 "결과가 화면에 안 보임". 찾은 제목은
# 그 계정 전용 표(`sender_rooms`)에만 담기는데 딜 소싱 화면은 명단의 방 이름만 그렸다.
# 이제 그 계정으로 열면 그 표의 상태(확정 · 후보 · 못 찾음)가 먼저 서고, 고르고 거두는
# 것도 그 표다 — 명단의 방 이름은 그대로다. 찾을 줄도 그 계정 제목 기준이다.

def _cell(page: str, row_id: int) -> str:
    """그 줄의 html — `<tr data-id="N"` 부터 `</tr>` 까지."""
    return re.search(rf'<tr data-id="{row_id}"[\s\S]*?</tr>', page).group(0)


@pytest.fixture()
def sender_view(db, users, sourcing):
    """u2(보내는 계정) 전용 제목 — 확정 · 후보 둘 · 못 찾음 · 아직 없음(명단 이름만)."""
    from app.models import SenderRoom, SourcingContact

    def person(name, room=None):
        row = SourcingContact(bucket=GROUP, name=name, firm="가나다벤처스", title="심사역",
                              kakao_room_name=room, participation="참여")
        db.add(row)
        db.flush()
        return row

    rows = dict(sourcing, missed=person("최못찾"), shared=person("정명단", "정명단 팀원 방"))
    db.add_all([
        SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=rows["room"].id,
                   room_name="보내는 계정 홍소싱 방", verified=1, candidates='["보내는 계정 홍소싱 방"]',
                   checked_at="2026-11-11T10:00:00"),
        SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=rows["noroom"].id,
                   candidates='["가 방", "나 방"]', checked_at="2026-11-11T10:00:00"),
        SenderRoom(sender_user_id=users["u2"].id, sourcing_contact_id=rows["missed"].id,
                   checked_at="2026-11-11T10:00:00"),
    ])
    db.commit()
    return rows


def test_sender_sees_its_own_titles_on_the_sourcing_page(client, db, users, sender_view):
    _login(client, "01000000002")
    page = client.get("/sourcing", params={"tab": GROUP}).text
    me = users["u2"].name

    done = _cell(page, sender_view["room"].id)
    assert 'data-testid="sourcing-sender-room"' in done and 'data-state="confirmed"' in done
    assert f"{me} 전용" in done and "💬 보내는 계정 홍소싱 방" in done
    assert f'action="/sourcing/{sender_view["room"].id}/room-clear"' in done
    assert ">톡방 연결 끊기</button>" in done and "확정 거두기" not in done
    assert "명단 이름:" in done and SRC_OWN in done       # 명단의 방 이름은 아래 참고로
    assert "data-no-room" not in done.split(">", 1)[0]     # 이 계정 제목이 있다 — 안 찾는다
    assert "room-confirm" not in done

    picks = _cell(page, sender_view["noroom"].id)
    assert 'data-state="picks"' in picks and "후보 2개 — 골라 주세요" in picks
    assert picks.count(f'action="/sourcing/{sender_view["noroom"].id}/room-confirm"') == 2
    assert 'value="가 방"' in picks and 'value="나 방"' in picks
    assert "data-no-room" in picks.split(">", 1)[0]

    missed = _cell(page, sender_view["missed"].id)
    assert 'data-state="not_found"' in missed and "이 계정 카톡에서 못 찾음" in missed
    assert "방 없음" in missed                  # 이 계정 제목도 명단 이름도 없다
    assert "방 없음" not in done

    # 이 계정 제목이 아직 없는 분 — 명단 이름은 참고로 · 그래도 찾을 수 있다.
    shared = _cell(page, sender_view["shared"].id)
    assert 'data-state="never"' in shared and "아직 안 찾아봄" in shared
    assert "명단 이름:" in shared and "정명단 팀원 방" in shared
    assert "이 계정 제목이 없으면 명단 이름으로 보냅니다" in shared
    assert "data-no-room" in shared.split(">", 1)[0]
    assert 'data-testid="sourcing-no-room"' not in shared   # 명단 쪽 `방 없음` 은 안 선다
    assert "방 없음" not in shared              # 명단 이름으로는 보낼 수 있다
    # 뺀 분을 말하는 글도 이 계정 기준이다.
    assert 'data-skip="이 계정 제목이 이미 확인된(또는 불참여인)"' in page


def test_member_view_of_the_sourcing_room_cell_is_unchanged(client, db, users, sender_view):
    """보내는 계정이 아니면 예전 그대로 — 명단의 방 이름 · `방 없음` · 명단의 후보."""
    _login(client, "01000000001")
    page = client.get("/sourcing", params={"tab": GROUP}).text
    assert "sourcing-sender-room" not in page and "전용</span>" not in page
    assert "/room-clear" not in page and "data-skip=" not in page
    assert "명단 이름:" not in page

    room = _cell(page, sender_view["room"].id)
    assert f'<div class="cell" data-field="kakao_room_name">{SRC_OWN}</div>' in room
    assert "data-no-room" not in room.split(">", 1)[0]
    noroom = _cell(page, sender_view["noroom"].id)
    assert "data-no-room" in noroom.split(">", 1)[0]
    assert 'data-testid="sourcing-no-room"' in noroom
    assert "가 방" not in noroom               # 보내는 계정의 후보는 안 보인다
    shared = _cell(page, sender_view["shared"].id)
    assert "data-no-room" not in shared.split(">", 1)[0]


def test_sender_pick_and_clear_on_the_sourcing_page_keep_the_list(
        client, db, users, sender_view):
    from app.models import SourcingContact
    from app.services import sender_rooms

    person = sender_view["noroom"]
    _login(client, "01000000002")
    json_ = {"Accept": "application/json"}
    bad = client.post(f"/sourcing/{person.id}/room-confirm",
                      data={"tab": GROUP, "room": "카톡에 없던 방"}, headers=json_)
    assert bad.status_code == 400
    answer = client.post(f"/sourcing/{person.id}/room-confirm",
                         data={"tab": GROUP, "room": "나 방"}, headers=json_)
    assert answer.status_code == 200
    body = answer.json()
    assert (body["ok"], body["sender"], body["room"]) == (True, True, "나 방")
    assert "전용" in body["note"]
    db.expire_all()
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person]) == {person.id: "나 방"}
    row = db.get(SourcingContact, person.id)
    assert (row.kakao_room_name, row.room_verified, row.room_candidates) == (
        None, "unverified", None)

    # 거두기도 그 계정 표만 — 명단의 방 이름은 그대로.
    shared = sender_view["room"]
    gone = client.post(f"/sourcing/{shared.id}/room-clear", data={"tab": GROUP},
                       follow_redirects=False)
    assert gone.status_code == 303
    assert "톡방 연결을 끊었습니다" in unquote(gone.headers["location"])
    db.expire_all()
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [shared]) == {}
    assert db.get(SourcingContact, shared.id).kakao_room_name == SRC_OWN


def test_member_cannot_clear_and_confirms_the_list_as_before(client, db, users, sender_view):
    from app.models import SourcingContact
    from app.services import sender_rooms

    _login(client, "01000000001")
    person = sender_view["room"]
    answer = client.post(f"/sourcing/{person.id}/room-clear", data={"tab": GROUP},
                         headers={"Accept": "application/json"})
    assert answer.status_code == 400
    db.expire_all()
    assert sender_rooms.sourcing_rooms_for(db, users["u2"].id, [person]) == {
        person.id: "보내는 계정 홍소싱 방"}
    # 보내는 계정의 후보를 팀원이 눌러도 명단에는 안 들어간다 — 명단의 후보가 아니다.
    assert client.post(f"/sourcing/{sender_view['noroom'].id}/room-confirm",
                       data={"tab": GROUP, "room": "가 방"},
                       headers={"Accept": "application/json"}).status_code == 400
    assert db.get(SourcingContact, sender_view["noroom"].id).kakao_room_name is None


def test_sender_search_takes_list_named_rows_without_its_own_title(
        client, db, users, sender_view):
    """명단의 방 이름이 있어도 이 계정 제목이 없으면 찾는다 · 확정된 분 · 불참여는 뺀다."""
    from app.models import SendJob
    from app.services import sourcing_rooms

    every = [sender_view[k].id for k in ("room", "noroom", "left", "missed", "shared")]
    got = {r.id for r in sourcing_rooms.targets(db, GROUP, every, users["u2"].id)}
    assert got == {sender_view[k].id for k in ("noroom", "missed", "shared")}
    # 보내는 계정이 아니면 예전 그대로 — 명단의 방 이름이 있는 분은 빠진다.
    assert {r.id for r in sourcing_rooms.targets(db, GROUP, every)} == {
        sender_view[k].id for k in ("noroom", "missed")}

    _login(client, "01000000002")
    json_ = {"Accept": "application/json"}
    answer = client.post("/sourcing/rooms/search",
                         data={"tab": GROUP, "ids": ",".join(map(str, every))}, headers=json_)
    assert answer.status_code == 200
    assert sorted(answer.json()["ids"]) == sorted(got)
    [job] = db.execute(select(SendJob)).scalars().all()
    assert {i.sourcing_contact_id for i in job.items} == got
    shared = next(i for i in job.items if i.sourcing_contact_id == sender_view["shared"].id)
    assert shared.room_name == "정명단 팀원 방"   # 명단의 방 이름으로 먼저 찾는다

    # 이 계정 제목이 확정된 분만 고르면 찾을 줄이 없다.
    none = client.post("/sourcing/rooms/search",
                       data={"tab": GROUP, "ids": str(sender_view["room"].id)}, headers=json_)
    assert none.status_code == 400
    assert "다 확인돼 있습니다" in none.json()["detail"]
