"""딜 소싱 ↔ 투자사 관리 현황 — **한쪽에서 고치면 다른 쪽도 그대로다.**

투자사 관리 현황의 `Series A 딜 소싱` 칸(O/X/빈칸)은 저장된 값이 아니라
딜 소싱 `시리즈 A 이상 딜 소싱 참여 심사역` 갈래의 **이어진 줄**에서 읽는다
(`services/sourcing_sync.py`). 여기서 못 박는 것.

  ① O — 이어진 줄이 없으면 그 갈래에서 같은 분을 찾아 잇고(번호 → 이름+회사),
     그래도 없으면 새 줄을 만든다. 다른 갈래의 줄은 건드리지 않는다.
  ② X — `불참여` 로 둘 뿐 지우지 않는다. 빈칸은 바꾸지 않음(이어진 분은 막는다).
  ③ 칸은 이어진 줄에서 그린다 — 다른 갈래는 안 본다. 머리글 필터가 선다.
  ④ 두 화면이 같은 칸을 본다 — 딜 소싱에서 참여를 바꾸면 투자사 쪽이 X/O.
  ⑤ 딜 소싱에서 넣거나 번호를 고치면 투자사 쪽 같은 분과 저절로 잇는다(번호가
     딱 한 줄일 때만).
  ⑥ 이어진 두 줄의 이름 · 직함 · 회사 · 휴대폰 · 메일은 어느 쪽에서 고쳐도 같이.
  ⑦ 불참여인 분께는 딜 소싱 제안(처음 안내 · 월간 리마인드)이 안 나간다.
  ⑧ 권한 — 그 투자사 줄을 고칠 수 있는 사람만(담당 · 관리자). 수정 로그가 남는다.
  ⑨ 투자사 줄을 지워도 소싱 줄은 남고 연결만 끊긴다. 시리즈 A 갈래는 이름을 못 바꾼다.

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

SYNC = "시리즈 A 이상 딜 소싱 참여 심사역"
MNA = "M&A 찾는 투자사"
SHEET = "강민준 투자사"


@pytest.fixture()
def admin(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=61, name="관리자시험", phone="01070000001", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def board(client, db, users):
    """u1 의 투자사 명단 하나 + 시리즈 A · M&A 갈래. u1 으로 로그인해 둔다."""
    from app.models import SheetOwner

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id, layout="investor"))
    db.commit()
    login(client, "01000000001")
    return client


def login(client, phone):
    client.post("/logout")
    r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    assert r.status_code in (200, 303), r.text


def vc(db, users, name="홍길동", phone="010-1234-5678", firm="가나다벤처스",
       title="심사역", email="hong@example.com", who="u1", sheet=SHEET, **kw):
    from app.models import VcContact

    row = VcContact(user_id=users[who].id, name=name, firm=firm, title=title,
                    phone=phone, email=email, source_sheet=sheet,
                    kakao_room_name=f"{name} 방", room_verified="verified",
                    connect_stage="connected", channel_kakao=1, **kw)
    db.add(row)
    db.commit()
    return row


def sc(db, name="홍길동", phone="010-1234-5678", bucket=SYNC, firm="가나다벤처스",
       **kw):
    from app.models import SourcingContact

    row = SourcingContact(bucket=bucket, position=kw.pop("position", 1), name=name,
                          phone=phone, firm=firm, **kw)
    db.add(row)
    db.commit()
    return row


def mark(client, contact_id, value):
    return client.patch(f"/api/contacts/{contact_id}", json={"sourcing_join": value})


def sync_rows(db):
    from app.models import SourcingContact

    db.expire_all()
    return db.query(SourcingContact).filter_by(bucket=SYNC).order_by(SourcingContact.id).all()


def column(client, contact_id):
    rows = client.get("/api/contacts").json()["contacts"]
    return next(r for r in rows if r["id"] == contact_id)["sourcing_join"]


# ── ① O ─────────────────────────────────────────────────────────────────────

def test_O_makes_a_new_row_when_nobody_matches(board, db, users):
    contact = vc(db, users)

    r = mark(board, contact.id, "O")
    assert r.status_code == 200, r.text
    assert r.json()["sourcing_join"] == "O"
    assert "새로 넣었습니다" in r.json()["sourcing_msg"]

    [row] = sync_rows(db)
    assert row.vc_contact_id == contact.id
    assert row.participation == "참여"
    assert (row.name, row.title, row.firm, row.phone, row.email) == (
        "홍길동", "심사역", "가나다벤처스", "010-1234-5678", "hong@example.com")
    # 담당은 그 투자사 줄을 맡은 팀원, 방은 **비워 둔다**(이어진 투자사 줄의 방을 쓴다)
    assert row.assignee_name == users["u1"].name
    assert not row.kakao_room_name
    assert row.room_verified == "unverified"
    assert column(board, contact.id) == "O"


def test_the_new_row_borrows_the_investor_room(board, db, users):
    """방 이름을 베끼지 않는다 — 비어 있으면 이어진 투자사 줄의 방으로 나간다."""
    from app.services import sourcing_link

    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    linked = sourcing_link.linked_rooms(db, [row])
    assert sourcing_link.room_for(row, linked) == "홍길동 방"


def test_O_links_the_row_with_the_same_phone(board, db, users):
    """번호 표기가 달라도(하이픈) 숫자가 같으면 같은 분이다. 적힌 값은 덮지 않는다."""
    contact = vc(db, users, phone="01012345678", email="hong@example.com")
    existing = sc(db, phone="010-1234-5678", firm="가나다벤처스(주)", email=None,
                  participation="불참여")

    r = mark(board, contact.id, "O")
    assert r.status_code == 200, r.text
    assert "이었습니다" in r.json()["sourcing_msg"]
    [row] = sync_rows(db)
    assert row.id == existing.id
    assert row.vc_contact_id == contact.id
    assert row.participation == "참여"
    assert row.firm == "가나다벤처스(주)"            # 다르게 적힌 값은 그대로
    assert row.email == "hong@example.com"           # 빈 칸만 채운다


def test_O_links_by_name_and_firm_when_there_is_no_phone(board, db, users):
    contact = vc(db, users)
    existing = sc(db, phone=None, firm="가나다 벤처스")   # 띄어쓰기만 다르다

    assert mark(board, contact.id, "O").status_code == 200
    [row] = sync_rows(db)
    assert row.id == existing.id and row.vc_contact_id == contact.id


def test_a_name_match_with_another_phone_is_someone_else(board, db, users):
    contact = vc(db, users, phone="010-1234-5678")
    sc(db, phone="010-9999-0000")                      # 같은 이름 · 회사, 다른 번호

    assert mark(board, contact.id, "O").status_code == 200
    rows = sync_rows(db)
    assert len(rows) == 2
    assert [r.vc_contact_id for r in rows] == [None, contact.id]


def test_another_bucket_is_left_alone(board, db, users):
    """M&A 갈래에만 있는 분 — 그 줄은 옮기지도 잇지도 않고 시리즈 A 에 새 줄."""
    from app.models import SourcingContact

    contact = vc(db, users)
    other = sc(db, bucket=MNA, title="이사")

    r = mark(board, contact.id, "O")
    assert r.status_code == 200, r.text
    assert MNA in r.json()["sourcing_msg"]
    db.expire_all()
    other = db.get(SourcingContact, other.id)
    assert (other.bucket, other.vc_contact_id, other.title) == (MNA, None, "이사")
    [row] = sync_rows(db)
    assert row.vc_contact_id == contact.id


def test_two_candidates_are_refused_not_guessed(board, db, users):
    contact = vc(db, users)
    sc(db, position=1)
    sc(db, position=2)

    r = mark(board, contact.id, "O")
    assert r.status_code == 400
    assert "어느 줄인지" in r.json()["detail"]
    assert all(row.vc_contact_id is None for row in sync_rows(db))


def test_the_same_person_on_two_lists_is_linked_once(board, db, users):
    """두 팀원 명단에 한 줄씩 있는 같은 분 — 두 번째 O 가 새 줄을 또 만들면
    그 분께 딜 소싱 제안이 두 번 나간다."""
    from app.models import SheetOwner

    db.add(SheetOwner(label="윤서아 투자사", user_id=users["u2"].id, layout="investor"))
    db.commit()
    mine = vc(db, users)
    theirs = vc(db, users, who="u2", sheet="윤서아 투자사")
    assert mark(board, mine.id, "O").status_code == 200

    login(board, "01000000002")
    r = mark(board, theirs.id, "O")
    assert r.status_code == 400
    assert "이미" in r.json()["detail"]
    assert len(sync_rows(db)) == 1


def test_a_startup_list_row_cannot_join(board, db, users):
    from app.models import SheetOwner

    db.add(SheetOwner(label="스타트업 명단", user_id=users["u1"].id,
                      layout="startup", is_hidden=1))
    db.commit()
    contact = vc(db, users, sheet="스타트업 명단")
    r = mark(board, contact.id, "O")
    assert r.status_code == 400
    assert sync_rows(db) == []


# ── ② X · 빈칸 ──────────────────────────────────────────────────────────────

def test_X_marks_not_taking_part_and_keeps_the_row(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")

    r = mark(board, contact.id, "x")                   # 소문자도 같은 뜻
    assert r.status_code == 200, r.text
    assert r.json()["sourcing_join"] == "X"
    [row] = sync_rows(db)
    assert row.participation == "불참여"
    assert row.vc_contact_id == contact.id
    assert column(board, contact.id) == "X"

    assert mark(board, contact.id, "O").status_code == 200
    [row] = sync_rows(db)
    assert row.participation == "참여"


def test_X_without_a_row_is_refused(board, db, users):
    contact = vc(db, users)
    r = mark(board, contact.id, "X")
    assert r.status_code == 400
    assert sync_rows(db) == []


def test_X_links_an_existing_row_as_not_taking_part(board, db, users):
    contact = vc(db, users)
    sc(db)
    assert mark(board, contact.id, "X").status_code == 200
    [row] = sync_rows(db)
    assert (row.vc_contact_id, row.participation) == (contact.id, "불참여")


def test_blank_changes_nothing_but_cannot_unlink(board, db, users):
    contact = vc(db, users)
    assert mark(board, contact.id, "").status_code == 200
    assert sync_rows(db) == []

    mark(board, contact.id, "O")
    r = mark(board, contact.id, "")
    assert r.status_code == 400
    assert "X" in r.json()["detail"]
    [row] = sync_rows(db)
    assert row.vc_contact_id == contact.id


def test_an_unknown_word_is_refused(board, db, users):
    contact = vc(db, users)
    assert mark(board, contact.id, "참여함").status_code == 400


def test_the_edit_panel_saves_the_same_way(board, db, users):
    """수정창은 모든 칸을 한 번에 보낸다 — 이름을 고치면서 O 를 넣어도 새 이름으로."""
    contact = vc(db, users)
    r = board.patch(f"/api/contacts/{contact.id}",
                    json={"name": "홍길동", "title": "파트너", "sourcing_join": "O"})
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert row.title == "파트너"
    got = board.get(f"/api/contacts/{contact.id}").json()["contact"]
    assert got["sourcing_join"] == "O"


def test_adding_a_contact_with_O_puts_them_in_sourcing(board, db, users):
    r = board.post("/api/contacts", json={"name": "김철수", "firm": "라마바투자",
                                          "phone": "010-2222-3333", "sheet": SHEET,
                                          "sourcing_join": "O"})
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert (row.name, row.vc_contact_id) == ("김철수", r.json()["id"])


# ── ③ 칸 · 필터 ─────────────────────────────────────────────────────────────

def test_the_column_reads_only_the_series_a_bucket(board, db, users):
    contact = vc(db, users)
    sc(db, bucket=MNA)          # 같은 번호가 다른 갈래에 — 칸은 빈칸이다
    assert column(board, contact.id) == ""


def test_the_table_has_the_column_and_its_filter(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")

    body = board.get(f"/contacts?sheet={SHEET}").text
    assert 'data-filters="sourcing:Series A 딜 소싱"' in body
    assert 'data-f-sourcing="O"' in body
    assert 'data-field="sourcing_join"' in body
    assert 'id="f-sourcing_join"' in body


# ── ④ 두 화면이 같은 칸 ─────────────────────────────────────────────────────

def test_changing_participation_on_sourcing_moves_the_investor_column(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)

    r = board.patch(f"/api/sourcing/{row.id}", json={"participation": "불참여"})
    assert r.status_code == 200, r.text
    assert r.json()["participation"] == "불참여"
    assert column(board, contact.id) == "X"

    r = board.patch(f"/api/sourcing/{row.id}", json={"participation": "O"})
    assert r.json()["participation"] == "참여"
    assert column(board, contact.id) == "O"


def test_the_sourcing_page_shows_participation_and_the_link(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")
    mark(board, contact.id, "X")

    body = board.get(f"/sourcing?tab={SYNC}").text
    assert 'data-filters="participation:참여"' in body
    assert 'data-f-participation="불참여"' in body
    assert f"투자사 관리 현황: {SHEET} 명단" in body


def test_a_bad_participation_word_is_refused(board, db, users):
    row = sc(db)
    r = board.patch(f"/api/sourcing/{row.id}", json={"participation": "글쎄"})
    assert r.status_code == 400


# ── ⑤ 딜 소싱 쪽에서 넣으면 저절로 잇는다 ───────────────────────────────────

def test_adding_on_sourcing_links_by_phone(board, db, users):
    contact = vc(db, users, phone="010-5555-6666")
    r = board.post(f"/api/sourcing?bucket={SYNC}",
                   json={"name": "홍길동", "phone": "01055556666"})
    assert r.status_code == 200, r.text
    assert SHEET in r.json()["linked_msg"]
    [row] = sync_rows(db)
    assert row.vc_contact_id == contact.id
    assert column(board, contact.id) == "O"


def test_adding_to_another_bucket_links_nothing(board, db, users):
    contact = vc(db, users)
    r = board.post(f"/api/sourcing?bucket={MNA}",
                   json={"name": "홍길동", "phone": "010-1234-5678"})
    assert "linked_msg" not in r.json()
    assert column(board, contact.id) == ""


def test_an_ambiguous_phone_links_nobody(board, db, users):
    vc(db, users, name="홍길동", firm="가나다벤처스")
    vc(db, users, name="김서연", firm="라마바투자")      # 같은 번호가 둘
    board.post(f"/api/sourcing?bucket={SYNC}",
               json={"name": "홍길동", "phone": "010-1234-5678"})
    [row] = sync_rows(db)
    assert row.vc_contact_id is None


def test_fixing_the_phone_on_sourcing_links_it(board, db, users):
    contact = vc(db, users, phone="010-7777-8888")
    row = sc(db, phone="010-0000-0000")
    r = board.patch(f"/api/sourcing/{row.id}", json={"phone": "010-7777-8888"})
    assert r.status_code == 200, r.text
    assert r.json().get("linked_msg")
    assert column(board, contact.id) == "O"


# ── ⑥ 같은 칸은 어느 쪽에서 고쳐도 같이 ─────────────────────────────────────

def test_editing_the_investor_row_updates_the_sourcing_row(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")

    r = board.patch(f"/api/contacts/{contact.id}",
                    json={"title": "이사", "firm": "가나다파트너스",
                          "phone": "010-4444-5555", "email": "new@example.com"})
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert (row.title, row.firm, row.phone, row.email) == (
        "이사", "가나다파트너스", "010-4444-5555", "new@example.com")


def test_editing_the_sourcing_row_updates_the_investor_row(board, db, users):
    from app.models import VcContact

    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)

    r = board.patch(f"/api/sourcing/{row.id}",
                    json={"name": "홍길순", "email": "hong2@example.com", "memo": "메모"})
    assert r.status_code == 200, r.text
    db.expire_all()
    back = db.get(VcContact, contact.id)
    assert (back.name, back.email) == ("홍길순", "hong2@example.com")
    assert back.memo is None           # 같은 칸이 아닌 것은 넘어가지 않는다


def test_an_unlinked_row_drags_nothing_along(board, db, users):
    from app.models import VcContact

    contact = vc(db, users)
    row = sc(db, bucket=MNA)
    board.patch(f"/api/sourcing/{row.id}", json={"title": "대표"})
    db.expire_all()
    assert db.get(VcContact, contact.id).title == "심사역"


def test_the_sourcing_page_flags_fields_that_differed_when_linked(board, db, users):
    contact = vc(db, users)
    sc(db, firm="가나다벤처스(주)")
    mark(board, contact.id, "O")
    body = board.get(f"/sourcing?tab={SYNC}").text
    assert "다른 칸: 회사" in body


# ── ⑦ 불참여는 보내지 않는다 ────────────────────────────────────────────────

def test_not_taking_part_is_not_offered_and_not_sent(board, db, users):
    from app.models import SourcingContact

    contact = vc(db, users)
    mark(board, contact.id, "O")
    mark(board, contact.id, "X")
    [row] = sync_rows(db)
    stays = sc(db, name="김철수", phone="010-2222-3333", kakao_room_name="김철수 방")

    deals = board.get("/deals").text
    sourcing_list = deals[deals.index('id="sourcing-list"'):]
    assert f'value="{row.id}" data-name="홍길동"' not in sourcing_list
    assert f'value="{stays.id}"' in sourcing_list

    for topic in ("sourcing_intro", "sourcing_remind"):
        r = board.post("/api/deals/send", json={"contact_ids": [row.id],
                                                "mode": "sourcing", "topic": topic})
        assert r.status_code == 400, r.text
        assert "불참여" in r.json()["detail"]

    preview = board.post("/api/deals/preview",
                         json={"contact_ids": [row.id], "mode": "sourcing"}).json()
    assert "딜 소싱 불참여" in preview["previews"][0]["warnings"]

    state = board.get("/api/sourcing/state").json()
    out = {r["id"]: r["out"] for r in state["rows"]}
    assert out[row.id] is True and out[stays.id] is False
    assert db.get(SourcingContact, row.id) is not None


def test_the_mail_check_does_not_ask_for_addresses_of_people_who_left(db, users):
    """`메일 주소 없는 분 N명` 은 채워 넣을 할 일이다 — 빠진 분은 세지 않는다."""
    from app.services import sourcing_receipts

    sc(db, name="가심사", phone=None, email=None)
    sc(db, name="나심사", phone=None, email=None, participation="불참여")
    assert sourcing_receipts.without_address(db) == 1


# ── ⑧ 권한 · 로그 ───────────────────────────────────────────────────────────

def test_someone_elses_investor_row_is_not_theirs_to_mark(board, db, users):
    contact = vc(db, users)
    login(board, "01000000002")
    assert mark(board, contact.id, "O").status_code == 404
    assert sync_rows(db) == []


def test_a_linked_row_is_guarded_on_the_sourcing_side(board, db, users, admin):
    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)

    login(board, "01000000002")
    # 같은 칸 · 참여 · 삭제는 막는다 — 남의 투자사 줄로 넘어간다
    for body in ({"participation": "불참여"}, {"phone": "010-0000-1111"},
                 {"name": "다른이름"}):
        r = board.patch(f"/api/sourcing/{row.id}", json=body)
        assert r.status_code == 403, (body, r.text)
    assert board.delete(f"/api/sourcing/{row.id}").status_code == 403
    # 같은 값을 다시 보내는 것 · 같은 칸이 아닌 것은 지금까지처럼 누구나
    assert board.patch(f"/api/sourcing/{row.id}",
                       json={"memo": "통화함", "name": "홍길동"}).status_code == 200

    # 관리자는 팀 전체의 투자사 줄을 고친다 — 이어진 줄도 같다
    login(board, "01070000001")
    assert board.patch(f"/api/sourcing/{row.id}",
                       json={"participation": "불참여"}).status_code == 200
    assert mark(board, contact.id, "O").status_code == 200
    [row] = sync_rows(db)
    assert row.participation == "참여"


def test_link_create_and_participation_are_logged(board, db, users):
    import json

    from app.models import EditLog

    contact = vc(db, users)
    mark(board, contact.id, "O")
    mark(board, contact.id, "X")
    logs = db.query(EditLog).filter_by(table_name="sourcing_contacts").order_by(EditLog.id).all()
    assert [log.action for log in logs] == ["create", "update"]
    changes = json.loads(logs[1].changes_json)
    assert {"field": "participation", "before": "참여", "after": "불참여"} in changes
    created = {c["field"]: c.get("after") for c in json.loads(logs[0].changes_json)}
    assert str(created.get("vc_contact_id")) == str(contact.id)


# ── ⑨ 지우기 · 이름 바꾸기 ──────────────────────────────────────────────────

def test_deleting_the_investor_row_keeps_the_sourcing_row(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")
    r = board.delete(f"/api/contacts/{contact.id}")
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert row.vc_contact_id is None
    assert row.name == "홍길동"


def test_the_series_a_bucket_cannot_be_renamed(board, db, users):
    sc(db)
    r = board.post("/sourcing/buckets/rename", data={"old": SYNC, "new": "시리즈 A"},
                   follow_redirects=False)
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]
    assert len(sync_rows(db)) == 1


# ── 같은 칸을 고치는 세션 한 자리 ───────────────────────────────────────────

def test_a_sheet_import_style_write_also_flows(db, users):
    """화면 PATCH 가 아니어도(시트 가져오기 · 스크립트) flush 를 지나면 따라온다."""
    from app.models import SourcingContact, VcContact

    contact = vc(db, users)
    row = sc(db, vc_contact_id=contact.id)
    contact.title = "본부장"
    db.commit()
    db.expire_all()
    assert db.get(SourcingContact, row.id).title == "본부장"
    assert db.get(VcContact, contact.id).title == "본부장"


# ── 화면 — 칸은 서버가 읽은 값으로 다시 그린다 ──────────────────────────────

JOIN_JS = Path(__file__).resolve().parent / "js" / "contacts_sourcing_join_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_the_cell_is_redrawn_from_the_server_value():
    """`o` 를 적어도 칸 · 필터 값은 서버가 읽은 `O` 다(`contacts.js`).

    로컬에서는 `node tests/js/contacts_sourcing_join_test.js` 로도 돈다.
    """
    result = subprocess.run([shutil.which("node"), str(JOIN_JS)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
