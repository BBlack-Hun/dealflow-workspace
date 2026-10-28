"""딜 소싱 ↔ 투자사 관리 현황 — **한쪽에서 고치면 다른 쪽도 그대로다.**

투자사 관리 현황의 `Series A 딜 소싱` 칸(O/X/빈칸)은 저장된 값이 아니라
딜 소싱 `시리즈 A 이상 딜 소싱 참여 심사역` 갈래의 **이어진 줄**에서 읽는다
(`services/sourcing_sync.py`). 여기서 못 박는 것.

  ① O — 이어진 줄이 없으면 그 갈래에서 같은 분을 찾아 잇고(이름 + 번호가 둘 다
     같을 때만 — #28. 번호나 이름 · 회사만 같으면 잇지도 새로 만들지도 않고 딜 소싱
     화면의 후보로 넘긴다), 아무도 없으면 새 줄을 만든다. 다른 갈래의 줄은 건드리지 않는다.
  ② X — `불참여` 로 둘 뿐 지우지 않는다. 빈칸은 바꾸지 않음(이어진 분은 막는다).
     O 는 갈래에 넣는 것이지 동의가 아니다 — 새 줄 · `불참여` 였던 줄은
     `딜 소싱 참여 제안 대기중` 이 된다(자세한 규칙은 `tests/test_sourcing_asking.py`).
  ③ 칸은 이어진 줄에서 그린다 — 다른 갈래는 안 본다. 머리글 필터가 선다.
  ④ 두 화면이 같은 칸을 본다 — 딜 소싱에서 참여를 바꾸면 투자사 쪽이 X/O.
  ⑤ 딜 소싱에서 넣거나 이름 · 번호를 고치면 투자사 쪽 같은 분과 저절로 잇는다
     (번호가 딱 한 줄에 맞고 그 줄의 이름도 같을 때만 — #28. 나머지는 사람이
     확정한다 — `tests/test_sourcing_link_confirm.py`).
  ⑥ 이어진 두 줄의 이름 · 직함 · 회사 · 휴대폰 · 메일 · 투자분야(선호 투자분야) ·
     라운드 사이즈는 어느 쪽에서 고쳐도 같이. 메모는 따로(#17).
  ⑦ 불참여인 분께는 딜 소싱 제안(처음 안내 · 월간 리마인드)이 안 나간다.
  ⑧ 권한 — 투자사 칸은 그 투자사 줄 담당 · 관리자. 딜 소싱 쪽은 이어진 줄이어도
     누구나(딜 소싱은 투자사 담당과 따로 관리한다). 수정 로그가 남는다.
  ⑨ 투자사 줄을 지워도 소싱 줄은 남고 연결만 끊긴다. 시리즈 A 갈래는 이름을 못 바꾼다.
  ⑩ 카톡방 — 시리즈 A 갈래는 투자사 딜소개 방을 이어받지 않는다. 방이 없으면
     빼고 보내고, [방 후보 찾기]로 누른 사람 PC 카톡에서 찾아 확정한다.
     [방 후보 찾기]는 **표에서 고른 줄만** 찾는다 — 안 고르면 아무것도 안 찾는다.

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

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

    kw.setdefault("kakao_room_name", f"{name} 방")
    row = VcContact(user_id=users[who].id, name=name, firm=firm, title=title,
                    phone=phone, email=email, source_sheet=sheet,
                    room_verified="verified",
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
    # O 는 갈래에 넣는 것이지 동의가 아니다 — 새 줄은 `딜 소싱 참여 제안 대기중`
    assert row.participation == "딜 소싱 참여 제안 대기중"
    assert "제안 대기중" in r.json()["sourcing_msg"]
    assert (row.name, row.title, row.firm, row.phone, row.email) == (
        "홍길동", "심사역", "가나다벤처스", "010-1234-5678", "hong@example.com")
    # 담당은 그 투자사 줄을 맡은 팀원, 방은 **비워 둔다**(이어진 투자사 줄의 방을 쓴다)
    assert row.assignee_name == users["u1"].name
    assert not row.kakao_room_name
    assert row.room_verified == "unverified"
    assert column(board, contact.id) == "O"


def test_the_new_row_does_not_borrow_the_investor_room(board, db, users):
    """방 이름을 베끼지도 이어받지도 않는다 — 투자사 줄의 방은 그 담당 팀원의
    **딜소개 방**이고, 딜 소싱 방은 보내는 사람 카톡에 따로 있다."""
    from app.services import sourcing_link

    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    assert not row.kakao_room_name
    assert sourcing_link.linked_rooms(db, [row]) == {}
    assert sourcing_link.room_for(row, {}) == ""


def test_the_marker_becomes_the_sourcing_assignee(board, db, users, admin):
    """새 줄의 담당은 O 를 넣은 사람 — 투자사 줄 주인을 옮기지 않는다."""
    contact = vc(db, users)                       # u1 의 줄
    login(board, "01070000001")                   # 관리자가 O
    assert mark(board, contact.id, "O").status_code == 200
    [row] = sync_rows(db)
    assert row.assignee_name == "관리자시험"


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
    # `불참여` 였던 분께 O — 다시 묻는 것으로 본다(바로 `참여` 가 되지 않는다)
    assert row.participation == "딜 소싱 참여 제안 대기중"
    assert row.firm == "가나다벤처스(주)"            # 다르게 적힌 값은 그대로
    assert row.email == "hong@example.com"           # 빈 칸만 채운다


def _refused_as_candidate(board, db, contact, existing, value="O"):
    """O/X 가 그 줄과 **잇지도, 새 줄을 만들지도 않고** 막혔다 — 딜 소싱 화면의 그 줄에
    이 투자사 줄이 후보로 떠, 사람이 [이 분으로 확정]으로 잇는다(#28)."""
    from app.services import sourcing_sync

    r = mark(board, contact.id, value)
    assert r.status_code == 400, r.text
    assert "이 분으로 확정" in r.json()["detail"]
    [row] = sync_rows(db)
    assert (row.id, row.vc_contact_id) == (existing.id, None)
    assert column(board, contact.id) == ""
    picks = sourcing_sync.link_candidates(db, [row])[row.id]
    assert [c["id"] for c in picks] == [contact.id]


def test_O_does_not_link_by_name_and_firm_alone(board, db, users):
    """번호가 없어 이름 · 회사만 같다 — 저절로 잇는 규칙(이름 + 번호, #28)에 안 맞는다.
    예전에는 여기서 이었다."""
    contact = vc(db, users)
    existing = sc(db, phone=None, firm="가나다 벤처스")   # 띄어쓰기만 다르다
    _refused_as_candidate(board, db, contact, existing)


@pytest.mark.parametrize("value", ["O", "X"])
def test_O_does_not_link_a_phone_match_with_another_name(board, db, users, value):
    """번호만 같고 이름이 다르다 — 딜 소싱 줄의 이름(`홍길둥`)이나 번호를 잘못 적은 줄이다.
    예전에는 번호만으로 이어 남의 투자사 줄과 조용히 이어질 수 있었다(#28 의 규칙을
    투자사 쪽 O/X 가 비켜 갔다)."""
    contact = vc(db, users, name="홍길동", phone="010-1234-5678")
    existing = sc(db, name="홍길둥", phone="010-1234-5678")
    _refused_as_candidate(board, db, contact, existing, value)


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
    assert row.participation == "딜 소싱 참여 제안 대기중"   # 다시 묻는다
    assert column(board, contact.id) == "O"


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
    # 예전 `Series A 딜 소싱`(O/X) 칸은 갈래 셋을 고르는 `딜 소싱` 칸이 되었다(2026-10-21).
    assert 'data-filters="sourcing:딜 소싱"' in body
    assert 'data-f-sourcing="Series A"' in body
    assert 'data-field="sourcing_branches" data-type="branches"' in body
    assert 'data-value="Series A"' in body
    assert "Series A·제안 대기중</span>" in body
    assert 'id="f-sourcing_branches"' in body
    assert "Series A 딜 소싱" not in body


def test_the_column_sits_right_after_the_sheet_sourcing_column(board, db, users):
    """`딜 소싱` 은 시트 칸 `딜소싱 참여 투자사` **바로 뒤**다(요청).

    머리글은 손으로 적고 행 칸도 손으로 적는다 — 한쪽만 옮기면 머리글 밑에 남의
    값이 선다. 그래서 머리글 · 행 · 수정창 세 곳의 차례를 같이 본다.
    """
    import re

    contact = vc(db, users)
    mark(board, contact.id, "O")
    body = board.get(f"/contacts?sheet={SHEET}").text

    head = body[body.index("<thead>"):body.index("</thead>")]
    labels = [re.sub(r"<[^>]+>", "", x).strip()
              for x in re.findall(r"<th[\s>].*?</th>", head, re.S)]
    at = labels.index("딜소싱 참여 투자사")
    assert labels[at + 1] == "딜 소싱", labels
    assert labels.count("딜 소싱") == 1

    rows = body[body.index("<tbody>"):body.index("</tbody>")]
    first_row = rows[:rows.index("</tr>")]
    fields = re.findall(r'data-field="(\w+)"', first_row)
    assert fields[fields.index("sourcing_note") + 1] == "sourcing_branches", fields

    # 머리글 칸 수 == 행 칸 수 — 옮기다 하나가 빠지거나 겹치면 여기서 걸린다.
    assert (len(re.findall(r"<th[\s>]", head))
            == len(re.findall(r"<td[\s>]", first_row)))

    # 수정창도 같은 차례 — `딜소싱 참여 투자사` 바로 다음 입력칸
    panel = re.findall(r'id="f-(\w+)"', body)
    assert panel[panel.index("sourcing_note") + 1] == "sourcing_branches", panel


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
    """사람이 적는 문구는 받는다(`tests/test_sourcing_asking.py`) — 막는 것은 줄바꿈 ·
    탭 같은 제어문자와 너무 긴 글이다."""
    row = sc(db)
    for bad in ("글쎄\n다음 달", "글쎄\t보류", "가" * 41):
        r = board.patch(f"/api/sourcing/{row.id}", json={"participation": bad})
        assert r.status_code == 400, bad


# ── ⑤ 딜 소싱 쪽에서 넣으면 저절로 잇는다 ───────────────────────────────────

def test_adding_on_sourcing_links_by_name_and_phone(board, db, users):
    # #28 — 이름도 같아야 한다(여기서는 둘 다 `홍길동`). 번호만 맞는 경우는
    # `test_sourcing_link_confirm.py` 가 본다(잇지 않고 후보).
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
    # 이름까지 맞는 줄은 하나(`홍길동`)여도 번호가 두 줄에 맞으면 잇지 않는다(#28 —
    # 어느 줄인지는 사람이 확정한다).
    vc(db, users, name="홍길동", firm="가나다벤처스")
    vc(db, users, name="김서연", firm="라마바투자")      # 같은 번호가 둘
    board.post(f"/api/sourcing?bucket={SYNC}",
               json={"name": "홍길동", "phone": "010-1234-5678"})
    [row] = sync_rows(db)
    assert row.vc_contact_id is None


def test_fixing_the_phone_on_sourcing_links_it(board, db, users):
    contact = vc(db, users, phone="010-7777-8888")
    row = sc(db, phone="010-0000-0000")             # 이름은 둘 다 `홍길동` (#28)
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


def test_anyone_can_manage_a_linked_sourcing_row(board, db, users):
    """딜 소싱은 투자사 줄을 누가 맡았는지와 **따로** 관리한다 — 이어진 줄이어도
    딜 소싱 쪽은 지금까지처럼 누구나 고친다. 같은 칸은 남의 투자사 줄로도
    넘어가고, 그 일은 수정 로그에 `남의 것` 으로 남는다."""
    import json

    from app.models import EditLog, VcContact

    contact = vc(db, users)                       # u1 의 줄
    mark(board, contact.id, "O")
    [row] = sync_rows(db)

    login(board, "01000000002")                   # u2
    r = board.patch(f"/api/sourcing/{row.id}",
                    json={"participation": "불참여", "title": "파트너"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(VcContact, contact.id).title == "파트너"
    log = db.query(EditLog).filter_by(table_name="vc_contacts",
                                      row_id=contact.id).one()
    assert (log.scope, log.actor_user_id, log.target_user_id) == ("others", 2, 1)
    assert {"field": "title", "before": "심사역", "after": "파트너"} in json.loads(
        log.changes_json)

    # 투자사 칸은 여전히 그 줄 담당 · 관리자만 — u2 에게는 없는 줄이다
    assert mark(board, contact.id, "O").status_code == 404
    login(board, "01000000001")
    assert column(board, contact.id) == "X"

    login(board, "01000000002")
    assert board.delete(f"/api/sourcing/{row.id}").status_code == 200
    login(board, "01000000001")
    assert column(board, contact.id) == ""


def test_link_create_and_participation_are_logged(board, db, users):
    import json

    from app.models import EditLog

    contact = vc(db, users)
    mark(board, contact.id, "O")
    mark(board, contact.id, "X")
    logs = db.query(EditLog).filter_by(table_name="sourcing_contacts").order_by(EditLog.id).all()
    assert [log.action for log in logs] == ["create", "update"]
    changes = json.loads(logs[1].changes_json)
    assert {"field": "participation", "before": "딜 소싱 참여 제안 대기중",
            "after": "불참여"} in changes
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


# ── ⑩ 카톡방 — 이어받지 않는다 · 방 후보 찾기 ──────────────────────────────

def test_series_a_rows_never_send_into_the_investor_room(board, db, users):
    """번호가 맞는 투자사 줄에 방이 있어도 시리즈 A 갈래는 그 방으로 안 나간다 —
    빼고 이유를 말한다. 미리보기도 `방 없음` 이다."""
    from app.models import SendItem

    vc(db, users, phone="010-1234-5678")          # 방 '홍길동 방' 이 있다
    no_room = sc(db)                              # 시리즈 A · 방 없음
    has_room = sc(db, name="김철수", phone="010-2222-3333",
                  kakao_room_name="김철수 딜소싱방")

    preview = board.post("/api/deals/preview",
                         json={"contact_ids": [no_room.id], "mode": "sourcing"}).json()
    p = preview["previews"][0]
    assert p["room_name"] == ""
    assert "방 후보 찾기" in p["room_warning"]

    r = board.post("/api/deals/send", json={"contact_ids": [no_room.id, has_room.id],
                                            "mode": "sourcing", "topic": "sourcing_remind"})
    assert r.status_code == 200, r.text
    skipped = r.json()["skipped"]
    assert [s["contact_id"] for s in skipped] == [no_room.id]
    assert "카톡방 없음" in skipped[0]["reason"]
    items = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).all()
    assert [(i.sourcing_contact_id, i.room_name) for i in items] == [
        (has_room.id, "김철수 딜소싱방")]

    r = board.post("/api/deals/send", json={"contact_ids": [no_room.id],
                                            "mode": "sourcing", "topic": "sourcing_remind"})
    assert r.status_code == 400
    assert "카톡방" in r.json()["detail"]


def test_other_buckets_keep_borrowing_as_before(board, db, users):
    """다른 갈래는 예전 그대로 — 번호가 맞는 투자사 줄의 방을 이어받는다."""
    from app.services import sourcing_link

    vc(db, users, phone="010-1234-5678")
    other = sc(db, bucket=MNA)
    assert sourcing_link.linked_rooms(db, [other])[other.id]["room"] == "홍길동 방"


def _poll(client, token=DEMO_TOKEN):
    import agent.main as agent_main

    res = client.get("/api/agent/poll", params={"kinds": ",".join(agent_main.SUPPORTED_KINDS)},
                     headers=auth(token))
    assert res.status_code in (200, 204), res.text
    return res.json() if res.status_code == 200 else {}


def test_room_search_runs_on_the_pressers_pc_and_only_collects_candidates(board, db, users):
    from app.models import SOURCING_ROOM_TOPIC, SendJob, SourcingContact

    a = sc(db, name="홍길동", title="심사역")
    has_room = sc(db, name="김철수", phone="010-2222-3333", kakao_room_name="김철수 방")
    other = sc(db, name="박영희", phone="010-3333-4444", bucket=MNA)
    vc(db, users, name="박영희", phone="010-3333-4444")   # 다른 갈래는 이어받아 방 있음

    page = board.get(f"/sourcing?tab={SYNC}").text
    assert _no_room_rows(page) == [a.id]
    assert 'data-testid="sourcing-no-room"' in page

    login(board, "01000000002")                   # 누른 사람 = u2 → u2 PC
    # 셋을 골라도 방이 있는 줄 · 다른 갈래 줄은 빠진다
    r = board.post("/sourcing/rooms/search",
                   data={"tab": SYNC, "ids": f"{a.id},{has_room.id},{other.id}"},
                   follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    [job] = db.query(SendJob).all()
    assert (job.user_id, job.kind, job.topic, job.total) == (
        2, "verify_room", SOURCING_ROOM_TOPIC, 1)
    assert [i.sourcing_contact_id for i in job.items] == [a.id]
    assert all(i.message == "" for i in job.items)
    assert other.id not in [i.sourcing_contact_id for i in job.items]

    # u1 의 발송기는 이 잡을 못 집는다 — u2 의 것이다
    assert _poll(board, DEMO_TOKEN).get("job_id") != job.id
    got = _poll(board, OTHER_TOKEN)
    assert got["job_id"] == job.id
    [item] = got["items"]
    assert item["query"] == "홍길동 심사역"
    assert item["name"] == "홍길동"
    assert not item.get("firm")                     # 회사로 줄이면 딜소개 방만 남는다
    assert "target" not in item                     # 투자사 방을 버리면 안 된다

    res = board.post(f"/api/agent/items/{item['id']}/result", headers=auth(OTHER_TOKEN),
                     json={"status": "failed", "verify_result": "ambiguous",
                           "candidates": ["홍길동 심사역 딜소싱", "홍길동 이사님 딜소개"]})
    assert res.status_code == 200, res.text
    db.expire_all()
    row = db.get(SourcingContact, a.id)
    assert not row.kakao_room_name                  # 후보일 뿐 — 방 이름은 그대로
    assert "홍길동 심사역 딜소싱" in (row.room_candidates or "")

    page = board.get(f"/sourcing?tab={SYNC}").text
    assert "후보 2개" in page
    assert "홍길동 심사역 딜소싱 — 이 방으로 확정" in page

    r = board.post(f"/sourcing/{a.id}/room-confirm",
                   data={"room": "홍길동 심사역 딜소싱", "tab": SYNC},
                   follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    row = db.get(SourcingContact, a.id)
    assert (row.kakao_room_name, row.room_verified) == ("홍길동 심사역 딜소싱", "verified")
    assert _no_room_rows(board.get(f"/sourcing?tab={SYNC}").text) == []


def test_only_a_found_candidate_can_be_confirmed(board, db, users):
    from app.models import SourcingContact

    row = sc(db)
    r = board.post(f"/sourcing/{row.id}/room-confirm",
                   data={"room": "아무 방", "tab": SYNC}, follow_redirects=False)
    assert "msg=" in r.headers["location"]
    db.expire_all()
    assert not db.get(SourcingContact, row.id).kakao_room_name


def test_nothing_to_search_queues_nothing(board, db, users):
    from app.models import SendJob

    row = sc(db, kakao_room_name="홍길동 방")
    r = board.post("/sourcing/rooms/search", data={"tab": SYNC, "ids": str(row.id)},
                   follow_redirects=False)
    assert "msg=" in r.headers["location"]
    assert db.query(SendJob).count() == 0


# ── 새로고침 없이 — 화면 스크립트가 부르면 JSON(`sourcing_rooms.js`) ─────────────
#
# 사용자: "딜 소싱에서 방 후보 누를때 비동기로 해줘… 계속 새로고침이 되서… 연속해서
# 클릭을 못함". 같은 주소 · 같은 처리이고, `Accept: application/json` 이면 되돌아가는
# 대신 JSON 으로 답한다. 폼 그대로(머리글 없음)는 위 시험들처럼 303 그대로다.

AJAX = {"Accept": "application/json"}


def test_confirm_answers_json_to_the_page_script(board, db, users):
    from app.models import SourcingContact
    from app.services import room_match

    row = sc(db)
    room_match.save_candidates(row, ["홍길동 딜소싱", "홍길동 다른 방"],
                               at="2026-10-28T10:00:00+09:00")
    db.commit()

    r = board.post(f"/sourcing/{row.id}/room-confirm", headers=AJAX,
                   data={"room": "홍길동 딜소싱", "tab": SYNC}, follow_redirects=False)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["room"] == "홍길동 딜소싱"
    assert "방을 확정했습니다" in body["msg"]
    db.expire_all()
    got = db.get(SourcingContact, row.id)
    assert (got.kakao_room_name, got.room_verified) == ("홍길동 딜소싱", "verified")


def test_a_refused_confirm_answers_400_and_saves_nothing(board, db, users):
    from app.models import SourcingContact

    row = sc(db)
    r = board.post(f"/sourcing/{row.id}/room-confirm", headers=AJAX,
                   data={"room": "아무 방", "tab": SYNC}, follow_redirects=False)
    assert r.status_code == 400
    assert "후보가 아닙니다" in r.json()["detail"]
    assert "ok" not in r.json()
    db.expire_all()
    assert not db.get(SourcingContact, row.id).kakao_room_name

    r = board.post("/sourcing/999999/room-confirm", headers=AJAX,
                   data={"room": "아무 방"}, follow_redirects=False)
    assert r.status_code == 404


def test_search_answers_json_with_the_job_and_rows(board, db, users):
    from app.models import SendJob

    a = sc(db, name="홍길동")
    has_room = sc(db, name="김철수", phone="010-2222-3333", kakao_room_name="김철수 방",
                  position=2)

    r = board.post("/sourcing/rooms/search", headers=AJAX,
                   data={"tab": SYNC, "ids": ""}, follow_redirects=False)
    assert r.status_code == 400 and "먼저 고르세요" in r.json()["detail"]
    r = board.post("/sourcing/rooms/search", headers=AJAX,
                   data={"tab": SYNC, "ids": str(has_room.id)}, follow_redirects=False)
    assert r.status_code == 400 and "찾을 줄이 없습니다" in r.json()["detail"]
    assert db.query(SendJob).count() == 0

    r = board.post("/sourcing/rooms/search", headers=AJAX,
                   data={"tab": SYNC, "ids": f"{a.id},{has_room.id}"}, follow_redirects=False)
    assert r.status_code == 200, r.text
    body = r.json()
    [job] = db.query(SendJob).all()
    assert body["ok"] is True and body["job_id"] == job.id
    assert body["ids"] == [a.id], "방이 있는 줄까지 찾는다고 답했다"
    assert "1명의 방을 찾습니다" in body["msg"]


def test_json_answers_keep_the_same_gates(board, db, users):
    """권한 · 로그인 · 팀원 화면 막기는 예전 그대로 — 스크립트에 JSON 성공으로 새지 않는다."""
    from app.models import SendJob, User
    from app.services import auth as auth_svc

    row = sc(db)
    db.add(User(id=93, name="컨설턴트시험", phone="01000000093", role="consultant",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    board.post("/logout")
    r = board.post("/login", data={"phone": "01000000093", "password": DEMO_PASSWORD},
                   follow_redirects=False)
    assert r.status_code == 303, r.text
    for url, data in (("/sourcing/rooms/search", {"ids": str(row.id)}),
                      (f"/sourcing/{row.id}/room-confirm", {"room": "아무 방"})):
        r = board.post(url, headers=AJAX, data=data, follow_redirects=False)
        assert r.status_code == 403, (url, r.status_code)

    board.post("/logout")
    r = board.post("/sourcing/rooms/search", headers=AJAX, data={"ids": str(row.id)},
                   follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert db.query(SendJob).count() == 0


def _no_room_rows(page):
    """`방 없음` 표시(`data-no-room`)가 선 줄 번호 — 화면이 [방 후보 찾기]에 싣는 줄."""
    return [int(rid) for rid, attrs in re.findall(r'<tr data-id="(\d+)"([^>]*)>', page)
            if "data-no-room" in attrs]


def test_room_search_looks_only_for_the_picked_rows(board, db, users):
    """사용자: "딜 소싱의 방 후보 찾기도 선택한걸 기반으로 찾게 해줘".

    고른 줄(`ids`)만 찾는다. 아무도 안 골랐으면 **아무것도 안 세운다** — 예전처럼
    그 갈래의 방 없는 분 전부로 대신하지 않는다(화면이 단추를 잠가도 서버가 한 번 더).
    """
    from urllib.parse import unquote

    from app.models import SendJob

    a = sc(db, name="홍길동")
    b = sc(db, name="김철수", phone="010-2222-3333", position=2)

    for body in ({"tab": SYNC}, {"tab": SYNC, "ids": ""}, {"tab": "all", "ids": " , "}):
        r = board.post("/sourcing/rooms/search", data=body, follow_redirects=False)
        assert r.status_code == 303
        assert "찾을 분을 먼저 고르세요" in unquote(r.headers["location"]), body
    assert db.query(SendJob).count() == 0, "안 골랐는데 갈래 전부를 찾는다"

    r = board.post("/sourcing/rooms/search", data={"tab": SYNC, "ids": str(b.id)},
                   follow_redirects=False)
    assert "1명의 방을 찾습니다" in unquote(r.headers["location"])
    db.expire_all()
    [job] = db.query(SendJob).all()
    assert [i.sourcing_contact_id for i in job.items] == [b.id]
    assert a.id not in [i.sourcing_contact_id for i in job.items]

    # 전체 탭에서도 같다 — 고른 줄만
    r = board.post("/sourcing/rooms/search", data={"tab": "all", "ids": str(a.id)},
                   follow_redirects=False)
    db.expire_all()
    job = db.query(SendJob).order_by(SendJob.id.desc()).first()
    assert [i.sourcing_contact_id for i in job.items] == [a.id]


@pytest.mark.parametrize("tab", [SYNC, MNA, "all"])
def test_every_tab_has_pick_boxes_and_a_locked_room_search_button(board, db, users, tab):
    """[방 후보 찾기]는 모든 탭에 있다 — 고르는 칸도 모든 탭에 선다. 처음에는 아무도
    안 골랐으니 단추가 잠긴 채 `(선택 0명)` 이고 옆에 `찾을 분을 먼저 고르세요`.
    [Series A 딜 소개]는 예전처럼 시리즈 A 갈래에만."""
    from urllib.parse import quote

    a = sc(db, name="홍길동")
    m = sc(db, name="김철수", phone="010-2222-3333", bucket=MNA)
    page = board.get(f"/sourcing?tab={quote(tab)}").text

    form = re.search(r'<form [^>]*id="sourcing-room-search".*?</form>', page, re.S)
    assert form, "[방 후보 찾기] 자리가 없다"
    assert 'action="/sourcing/rooms/search"' in form.group(0)
    assert re.search(r'<input type="hidden" name="ids" value="">', form.group(0))
    btn = re.search(r'<button [^>]*id="sourcing-room-btn"[^>]*>([^<]*)</button>',
                    form.group(0))
    assert btn and btn.group(1).strip() == "방 후보 찾기 (선택 0명)", btn and btn.group(1)
    assert " disabled" in btn.group(0), "아무도 안 골랐는데 단추가 눌린다"
    assert re.search(r'id="sourcing-room-hint"[^>]*>찾을 분을 먼저 고르세요<', page)

    assert 'id="sourcing-check-all"' in page
    picks = re.findall(r'class="js-sourcing-pick" value="(\d+)"', page)
    shown = {SYNC: [a.id], MNA: [m.id], "all": [a.id, m.id]}[tab]
    assert sorted(int(x) for x in picks) == sorted(shown)
    assert sorted(_no_room_rows(page)) == sorted(shown)
    assert ('id="sourcing-share-btn"' in page) == (tab == SYNC)


ROOM_JS = Path(__file__).resolve().parent / "js" / "sourcing_room_search_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_the_room_search_button_follows_the_picks():
    """체크한 `방 없음` 분만 싣는다 · 안 골랐으면 잠긴다 · 확인창에 누구인지(`sourcing.html`).

    로컬에서는 `node tests/js/sourcing_room_search_test.js` 로도 돈다.
    """
    result = subprocess.run([shutil.which("node"), str(ROOM_JS)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_room_buttons_work_without_a_reload():
    """방 찾기 · 확정이 새로고침 없이 그 줄만 고친다(`sourcing_rooms.js`).

    로컬에서는 `node tests/js/sourcing_rooms_async_test.js` 로도 돈다.
    """
    result = subprocess.run([shutil.which("node"), str(ROOM_JS.parent / "sourcing_rooms_async_test.js")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_room_forms_are_marked_for_the_script(board, db, users):
    """가로챌 폼 셋(툴바 찾기 · 줄 찾기 · 확정)에 표시가 있고, 스크립트가 실린다.
    폼 자체(주소 · 보내는 칸)는 그대로다 — 스크립트가 없으면 예전처럼 보낸다."""
    from app.services import room_match

    row = sc(db)
    room_match.save_candidates(row, ["홍길동 딜소싱"], at="2026-10-28T10:00:00+09:00")
    db.commit()
    page = board.get(f"/sourcing?tab={SYNC}").text
    assert re.search(r'<form method="post" action="/sourcing/rooms/search" '
                     r'class="inline-form js-room-search" data-send\s+id="sourcing-room-search"', page)
    assert re.search(r'<form method="post" action="/sourcing/rooms/search" '
                     r'class="inline-form js-room-search" data-send>', page)
    assert f'action="/sourcing/{row.id}/room-confirm" class="inline-form js-room-confirm"' in page
    assert "/static/js/sourcing_rooms.js" in page


# ── PR #284 리뷰에서 짚인 것 ────────────────────────────────────────────────
#
# 리뷰 댓글마다 한 묶음. 이름 · 번호 · 방 제목은 전부 가상값이다(공개 저장소).

def _join(client, contact_id, **fields):
    """수정창 [저장] 이 보내는 모양 — 칸 **전부**를 보낸다(빈 칸은 `""`)."""
    body = {f: "" for f in ("name", "title", "firm", "phone", "email", "memo")}
    body.update(fields)
    return client.patch(f"/api/contacts/{contact_id}", json=body)


def test_saving_the_edit_panel_does_not_wipe_the_linked_sourcing_row(board, db, users):
    """투자사 쪽이 비어 있는(None) 칸을 수정창이 `""` 로 다시 적어도, 이어진 딜
    소싱 줄의 값은 그대로다 — None 과 `""` 는 같은 '빈칸' 이다."""
    contact = vc(db, users, title=None, email=None)
    sc(db, title="수석심사역", email="hong@example.com")
    mark(board, contact.id, "O")                  # 번호로 이어진다 — 소싱 값은 그대로

    r = _join(board, contact.id, name="홍길동", firm="가나다벤처스",
              phone="010-1234-5678", memo="통화함")
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert (row.title, row.email) == ("수석심사역", "hong@example.com")


def test_an_empty_value_never_flows_to_the_other_side(board, db, users):
    """한쪽에서 비워도 다른 쪽은 안 지운다 — 고친 값(빈칸 아닌 것)만 넘어간다."""
    from app.models import VcContact

    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)

    assert board.patch(f"/api/contacts/{contact.id}",
                       json={"email": "  ", "title": ""}).status_code == 200
    [row] = sync_rows(db)
    assert (row.title, row.email) == ("심사역", "hong@example.com")

    assert board.patch(f"/api/sourcing/{row.id}",
                       json={"firm": "", "phone": ""}).status_code == 200
    db.expire_all()
    back = db.get(VcContact, contact.id)
    assert (back.firm, back.phone) == ("가나다벤처스", "010-1234-5678")

    # 빈칸이 아닌 값은 예전처럼 넘어간다
    assert board.patch(f"/api/contacts/{contact.id}",
                       json={"title": "이사"}).status_code == 200
    [row] = sync_rows(db)
    assert row.title == "이사"


@pytest.fixture()
def mail_on(monkeypatch):
    monkeypatch.setenv("DEALFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PORT", "465")
    monkeypatch.setenv("DEALFLOW_SMTP_USER", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_FROM", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PASSWORD", "secret")


def test_an_email_send_does_not_need_a_kakao_room(board, db, users, mail_on, monkeypatch):
    """`방 없음` 으로 빼는 것은 **카톡**일 때만 — 메일은 주소로 나간다."""
    from app.models import SendItem
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    no_room = sc(db, email="hong@example.com")    # 시리즈 A · 방 없음 · 메일 있음
    r = board.post("/api/deals/send", json={"contact_ids": [no_room.id],
                                            "mode": "sourcing", "channel": "email",
                                            "topic": "sourcing_remind"})
    assert r.status_code == 200, r.text
    assert not r.json().get("skipped")
    [item] = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).all()
    assert (item.sourcing_contact_id, item.channel, item.room_name) == (
        no_room.id, "email", "hong@example.com")

    # 불참여는 채널과 상관없이 뺀다
    left = sc(db, name="김철수", phone="010-2222-3333", email="kim@example.com",
              participation="불참여")
    r = board.post("/api/deals/send", json={"contact_ids": [left.id],
                                            "mode": "sourcing", "channel": "email"})
    assert r.status_code == 400
    assert "불참여" in r.json()["detail"]


def _search(client, row_id, token=OTHER_TOKEN, login_phone="01000000002"):
    """[방 후보 찾기] 를 누르고 그 PC 의 발송기가 잡을 집어 간다 → 실린 건 하나."""
    login(client, login_phone)
    r = client.post("/sourcing/rooms/search", data={"tab": SYNC, "ids": str(row_id)},
                    follow_redirects=False)
    assert r.status_code == 303
    got = _poll(client, token)
    [item] = got["items"]
    return item


def _report(client, item, token=OTHER_TOKEN, **body):
    res = client.post(f"/api/agent/items/{item['id']}/result", headers=auth(token),
                      json={"status": "failed", **body})
    assert res.status_code == 200, res.text


def test_room_search_sends_no_firm_and_drops_the_deal_intro_room(board, db, users):
    """회사를 실어 보내면 발송기가 회사 이름이 든 방(= 투자사 딜소개 방) 하나로
    줄여 버린다. 회사는 안 보내고, **사람이 적은 문구**인 분의 딜소개 방 제목은 후보에서
    뺀다 — 이어진 투자사 줄의 방 · 번호가 같은 다른 팀원 명단 줄의 방 둘 다(`참여` ·
    참여 안내 받을 분은 둔다 — 아래 시험)."""
    from app.models import SourcingContact

    contact = vc(db, users, kakao_room_name="홍길동 심사역 가나다벤처스")
    vc(db, users, who="u2", sheet=SHEET, kakao_room_name="홍길동 이사님 딜소개")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    row.participation = "다음 달에 다시 여쭙기"
    db.commit()

    item = _search(board, row.id)
    assert item["query"] == "홍길동 심사역" and item["name"] == "홍길동"
    assert not item.get("firm"), "회사를 실으면 발송기가 딜소개 방 하나로 줄인다"

    _report(board, item, verify_result="ambiguous",
            candidates=["홍길동 심사역 가나다벤처스", "딜소싱 홍길동 심사역",
                        "홍길동 이사님 딜소개"])
    db.expire_all()
    from app.services import room_match

    found = room_match.candidates(db.get(SourcingContact, row.id))
    assert found["rooms"] == ["딜소싱 홍길동 심사역"]


def test_a_deal_intro_room_cannot_be_confirmed_as_the_sourcing_room(board, db, users):
    """예전에 담긴 후보에 딜소개 방이 남아 있어도 확정은 막는다."""
    from app.models import SourcingContact
    from app.services import room_match

    contact = vc(db, users, kakao_room_name="홍길동 심사역 가나다벤처스")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    row.participation = "다음 달에 다시 여쭙기"   # 참여 · 참여 안내 받을 분은 확정한다(아래 시험)
    room_match.save_candidates(row, ["홍길동 심사역 가나다벤처스", "딜소싱 홍길동"],
                               at="2026-10-14T10:00:00+09:00")
    db.commit()

    r = board.post(f"/sourcing/{row.id}/room-confirm",
                   data={"room": "홍길동 심사역 가나다벤처스", "tab": SYNC},
                   follow_redirects=False)
    assert "msg=" in r.headers["location"]
    db.expire_all()
    assert not db.get(SourcingContact, row.id).kakao_room_name


@pytest.mark.parametrize("value", ["딜 소싱 참여 제안 대기중", "참여 의사를 물어보는 중", "참여"])
def test_an_invitee_keeps_the_deal_intro_room_and_can_confirm_it(board, db, users, value):
    """참여 안내 받을 분(제안 대기중 · 물어보는 중)은 아직 딜 소싱 방이 없어 찾은 방이
    딜소개 방 하나뿐이다 — 운영에서 그 방을 빼 고를 단추가 없었다(2026-10-19).
    `참여` 인 분도 같다 — 팀은 대개 한 방에서 딜소개와 딜 소싱을 같이 한다(2026-10-22).
    후보로 담고 [이 방으로 확정] 이 서고, 누르면 그 줄의 방이 된다."""
    from app.models import SourcingContact

    contact = vc(db, users, kakao_room_name="홍길동 심사역 가나다벤처스")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    row.participation = value
    db.commit()

    _report(board, _search(board, row.id), verify_result="found",
            found_room="홍길동 심사역 가나다벤처스")
    page = board.get(f"/sourcing?tab={SYNC}").text
    assert "후보 1개" in page
    assert "홍길동 심사역 가나다벤처스 — 이 방으로 확정" in page

    r = board.post(f"/sourcing/{row.id}/room-confirm",
                   data={"room": "홍길동 심사역 가나다벤처스", "tab": SYNC},
                   follow_redirects=False)
    assert r.status_code == 303 and "방을 확정했습니다" in unquote(r.headers["location"])
    db.expire_all()
    got = db.get(SourcingContact, row.id)
    assert (got.kakao_room_name, got.room_verified) == ("홍길동 심사역 가나다벤처스", "verified")


def test_a_room_search_does_not_block_deleting_the_row(board, db, users):
    """방 찾기는 아무것도 보내지 않는다 — 그 건이 `보낸 이력` 으로 세여 줄을
    못 지우게 하면 안 된다. 지우면 그 줄을 가리키던 방 찾기 건도 치운다."""
    from app.models import SendItem, SendJob, SourcingContact

    rid = sc(db).id
    item = _search(board, rid)
    _report(board, item, verify_result="not_found")
    job_id = db.get(SendItem, item["id"]).job_id

    r = board.delete(f"/api/sourcing/{rid}")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(SourcingContact, rid) is None
    assert db.query(SendItem).filter_by(sourcing_contact_id=rid).count() == 0
    job = db.get(SendJob, job_id)
    assert (job.total, job.sent, job.failed) == (0, 0, 0)


def test_a_failed_search_keeps_the_candidates_found_before(board, db, users):
    """발송기 오류로 끝난 찾기는 담아 둔 후보를 지우지 않는다 — 오류만 남긴다.
    찾아봤는데 없던 것(오류 없음)은 예전처럼 `후보 없음` 이다."""
    from app.models import SendItem, SourcingContact
    from app.services import sourcing_rooms

    row = sc(db)
    _report(board, _search(board, row.id), verify_result="ambiguous",
            candidates=["딜소싱 홍길동", "홍길동 딜소싱방"])
    item = _search(board, row.id)
    _report(board, item, error="verify error: 카톡 창을 못 찾았습니다",
            verify_result="not_found")
    db.expire_all()
    pick = sourcing_rooms.picks(db.get(SourcingContact, row.id))
    assert [p["room"] for p in pick["rooms"]] == ["딜소싱 홍길동", "홍길동 딜소싱방"]
    assert pick["state"] == "picks"
    assert "카톡 창" in pick["error"]
    assert "카톡 창" in db.get(SendItem, item["id"]).error

    # 오류 없이 못 찾은 것은 찾아본 결과다 — 후보 없음
    _report(board, _search(board, row.id), verify_result="not_found")
    db.expire_all()
    pick = sourcing_rooms.picks(db.get(SourcingContact, row.id))
    assert (pick["state"], pick["rooms"], pick["error"]) == ("no_picks", [], "")


def test_the_phone_written_differently_is_not_a_different_field(board, db, users):
    from app.services import sourcing_sync

    contact = vc(db, users, phone="010-1234-5678")
    sc(db, phone="01012345678")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    assert row.vc_contact_id == contact.id
    assert "휴대폰" not in sourcing_sync.badges(db, [row])[row.id]["diff"]


def test_people_who_left_need_no_room(board, db, users):
    """불참여인 분은 받을 일이 없다 — `방 없음` 도, 방 찾기 대상도 아니다."""
    from app.services import sourcing_rooms

    stays = sc(db)
    left = sc(db, name="김철수", phone="010-2222-3333", participation="불참여")
    assert [r.id for r in sourcing_rooms.needs_room(db, [stays, left])] == [stays.id]
    assert [r.id for r in sourcing_rooms.targets(db, SYNC)] == [stays.id]
    assert sourcing_rooms.targets(db, SYNC, [left.id]) == []
    assert _no_room_rows(board.get(f"/sourcing?tab={SYNC}").text) == [stays.id]


def test_deleting_the_investor_row_logs_the_unlink(board, db, users):
    """투자사 줄을 지워 연결이 끊긴 것도 수정 로그에 남는다 — `vc_contact_id`."""
    import json

    from app.models import EditLog

    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    cid, rid = contact.id, row.id
    db.expunge_all()                              # 요청 세션에 소싱 줄이 안 올라와 있다

    assert board.delete(f"/api/contacts/{cid}").status_code == 200
    logs = db.query(EditLog).filter_by(table_name="sourcing_contacts",
                                       row_id=rid, action="update").all()
    changes = [c for log in logs for c in json.loads(log.changes_json)]
    assert {"field": "vc_contact_id", "before": cid, "after": None} in changes


SAVE_JS = Path(__file__).resolve().parent / "js" / "contacts_sourcing_join_save_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_the_edit_panel_sends_the_column_only_when_it_was_changed():
    """수정창이 열 때 읽은 O/X 를 저장할 때마다 다시 보내면, 그 사이 딜 소싱에서
    바뀐 참여를 되돌리거나 지운 줄을 되살린다 — 고쳤을 때만 보낸다.

    로컬에서는 `node tests/js/contacts_sourcing_join_save_test.js` 로도 돈다.
    """
    result = subprocess.run([shutil.which("node"), str(SAVE_JS)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


# ── ⑥ 더하기 — 투자분야 · 라운드 사이즈(#17) ─────────────────────────────────
#
# "두 메뉴의 컬럼이 같으면 어느 쪽에 넣어도 다른 쪽에 자동으로." 딜 소싱의
# `투자분야` 와 투자사 관리 현황의 `선호 투자분야` 는 같은 칸(`sectors`)이고,
# `라운드 사이즈` 도 같다. 범위는 지금 잇는 그대로 — 시리즈 A 갈래의 이어진 줄.
# **메모는 잇지 않는다**(담는 이야기가 다르다).

def test_investor_sectors_and_round_size_flow_to_sourcing(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")

    r = board.patch(f"/api/contacts/{contact.id}",
                    json={"sectors": "AI,헬스케어", "round_size": "10~50억",
                          "memo": "투자사 쪽 통화 메모"})
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert (row.sectors, row.round_size) == ("AI,헬스케어", "10~50억")
    assert row.memo is None, "메모는 따라가면 안 된다"


def test_sourcing_sectors_and_round_size_flow_to_the_investor(board, db, users):
    from app.models import VcContact

    contact = vc(db, users, memo="원래 메모")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)

    r = board.patch(f"/api/sourcing/{row.id}",
                    json={"sectors": "바이오, 딥테크", "round_size": "Series A 30억",
                          "memo": "딜 소싱 방 이야기"})
    assert r.status_code == 200, r.text
    db.expire_all()
    back = db.get(VcContact, contact.id)
    assert (back.sectors, back.round_size) == ("바이오, 딥테크", "Series A 30억")
    assert back.memo == "원래 메모", "딜 소싱 메모가 투자사 메모를 덮었다"


def test_a_new_row_made_by_O_carries_sectors_and_round_size(board, db, users):
    contact = vc(db, users, sectors="AI", round_size="5억 이하")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    assert (row.sectors, row.round_size) == ("AI", "5억 이하")


def test_linking_fills_only_empty_sectors_and_flags_a_difference(board, db, users):
    """이을 때는 **빈 칸만** 채운다 — 이미 다르게 적힌 값은 `다른 칸` 으로 알린다."""
    contact = vc(db, users, sectors="AI", round_size="10억")
    sc(db, sectors="핀테크")                     # 번호로 이어진다 · 라운드는 비어 있다
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    assert row.sectors == "핀테크" and row.round_size == "10억"
    body = board.get(f"/sourcing?tab={SYNC}").text
    assert "다른 칸: 선호 투자분야" in body


def test_comma_spacing_alone_is_not_a_different_field(board, db, users):
    """`AI,헬스케어` 와 `AI, 헬스케어` 는 투자사 관리 현황에서 같은 두 분야다."""
    import re

    contact = vc(db, users, sectors="AI,헬스케어")
    sc(db, sectors="AI, 헬스케어")
    mark(board, contact.id, "O")
    body = board.get(f"/sourcing?tab={SYNC}").text
    diff = re.search(r'data-testid="sourcing-vc-diff"[^>]*>([^<]*)<', body)
    assert diff is None or "투자분야" not in diff.group(1), diff and diff.group(1)


def test_an_empty_sectors_or_round_size_never_wipes_the_other_side(board, db, users):
    from app.models import VcContact

    contact = vc(db, users, sectors="AI", round_size="10억")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    assert board.patch(f"/api/sourcing/{row.id}",
                       json={"sectors": "", "round_size": " "}).status_code == 200
    db.expire_all()
    back = db.get(VcContact, contact.id)
    assert (back.sectors, back.round_size) == ("AI", "10억")


def test_other_buckets_do_not_sync_sectors(board, db, users):
    """범위는 지금 잇는 그대로 — 시리즈 A 갈래가 아닌 줄은 번호가 같아도 안 따라간다."""
    from app.models import VcContact

    contact = vc(db, users, sectors="AI")
    row = sc(db, bucket=MNA)
    board.patch(f"/api/sourcing/{row.id}", json={"sectors": "M&A 전 분야"})
    db.expire_all()
    assert db.get(VcContact, contact.id).sectors == "AI"


def test_the_flowed_sectors_are_in_the_edit_log_on_both_tables(board, db, users):
    """따라 고친 쪽도 수정 로그 규칙 그대로 남는다 — 같은 flush 에서 적으므로
    로그 훅(`edit_log`)이 본다. 우회하는 길이 없다.

    로그는 **남의 것과 공용**만 남긴다(`edit_log` 머리말). 그래서:
      · 내 투자사 줄을 고치면 — 내 줄은 안 남고, 따라 바뀐 딜 소싱 줄(공용)은 남는다.
      · 다른 팀원이 딜 소싱에서 고치면 — 딜 소싱 줄도, 따라 바뀐 **남의 투자사
        줄**도 남는다(누가 내 명단 값을 바꿨는지가 거기 보인다).
    """
    import json

    from app.models import EditLog

    def fields_since(mark_id):
        return {(log.table_name, log.row_id): {c["field"] for c in json.loads(log.changes_json)}
                for log in db.query(EditLog).filter(EditLog.id > mark_id).all()}

    def last_id():
        return db.query(EditLog.id).order_by(EditLog.id.desc()).limit(1).scalar() or 0

    contact = vc(db, users)
    mark(board, contact.id, "O")
    [row] = sync_rows(db)

    at = last_id()
    assert board.patch(f"/api/contacts/{contact.id}",
                       json={"sectors": "AI", "round_size": "10억"}).status_code == 200
    got = fields_since(at)
    assert {"sectors", "round_size"} <= got.get(("sourcing_contacts", row.id), set()), got
    assert ("vc_contacts", contact.id) not in got     # 내 줄은 남기지 않는다

    login(board, "01000000002")
    at = last_id()
    assert board.patch(f"/api/sourcing/{row.id}",
                       json={"sectors": "바이오", "round_size": "30억"}).status_code == 200
    got = fields_since(at)
    assert {"sectors", "round_size"} <= got.get(("sourcing_contacts", row.id), set()), got
    assert {"sectors", "round_size"} <= got.get(("vc_contacts", contact.id), set()), got


def test_syncing_sectors_leaves_the_room_columns_to_room_joined(board, db, users):
    """같은 칸을 따라 고쳐도 카톡방 두 칸(`room_verified` · `kakao_joined`)은 안
    건드린다 — 그 둘을 적는 자리는 `room_joined` 하나다(`tests/test_room_joined.py`)."""
    from app.models import VcContact
    from app.services import sourcing_sync

    assert not {"room_verified", "kakao_joined", "kakao_room_name"} & set(
        sourcing_sync.SHARED_FIELDS)
    contact = vc(db, users, kakao_joined="O")
    mark(board, contact.id, "O")
    [row] = sync_rows(db)
    board.patch(f"/api/sourcing/{row.id}", json={"sectors": "AI", "round_size": "10억"})
    db.expire_all()
    back = db.get(VcContact, contact.id)
    assert (back.room_verified, back.kakao_joined, back.kakao_room_name) == (
        "verified", "O", "홍길동 방")


def test_the_link_badge_names_every_shared_field(board, db, users):
    contact = vc(db, users)
    mark(board, contact.id, "O")
    body = board.get(f"/sourcing?tab={SYNC}").text
    assert ("두 화면이 같이 바뀌는 칸: 이름 · 직함 · 회사 · 휴대폰 · 전자 메일 주소 · "
            "선호 투자분야 · 라운드 사이즈(투자운영금액) (메모는 따로)") in body
