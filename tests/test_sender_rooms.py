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
