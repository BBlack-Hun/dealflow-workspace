"""딜 소싱 [추가] → 투자사 관리 현황에도 (사용자 요청 2026-10-22 — "쌍방으로 입력").

여기서 못 박는 것(`sourcing_sync.add_from_sourcing`).

  ① 잇는 갈래에 넣은 분이 투자사 관리 현황에 없으면 **넣은 사람의 `직접 추가` 명단**에
     새로 만들고 잇는다 — 그쪽 표 · `딜 소싱` 칸에 곧바로 선다. 카톡방은 비운다
  ② 이름 + 번호가 같은 투자사 줄이 딱 하나면 **그 줄과 잇는다** — 새로 만들지 않는다
  ③ 같은 분일 수 있는 줄이 여럿이거나 이름 · 번호 하나만 같으면 **아무것도 안 만든다** —
     후보에서 사람이 확정한다
  ④ `(딜 소개 X)` · `딜 소개 보류` 인 분은 막는다 — 딜 소싱 줄도 안 생긴다
  ⑤ 넣은 뒤에는 같은 칸이 어느 쪽에서 고쳐도 같이 바뀐다
  ⑥ 잇지 않는 갈래(대표 · 개인)는 예전 그대로 딜 소싱에만 들어간다

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

from tests.test_sourcing_link_confirm import other_list, picks, OTHER_SHEET  # noqa: F401
from tests.test_sourcing_vc_sync import (  # noqa: F401 - 픽스처를 함께 쓴다
    MNA, SHEET, SYNC, board, column, sc, sync_rows, vc)

CEO = "딜 소싱  참여 투자사 대표"


def add(client, bucket=SYNC, **body):
    return client.post("/api/sourcing", params={"bucket": bucket}, json=body)


def investors(db):
    from app.models import VcContact

    db.expire_all()
    return db.query(VcContact).order_by(VcContact.id).all()


# ── ① 없으면 만들어 잇는다 ───────────────────────────────────────────────────

def test_a_new_person_is_made_in_my_manual_list_and_linked(board, db, users):
    r = add(board, name="박도윤", phone="010-2222-3333", firm="라마바투자",
            title="심사역", email="park@example.com")
    assert r.status_code == 200, r.text
    assert "직접 추가" in r.json()["linked_msg"]

    [contact] = investors(db)
    [row] = sync_rows(db)
    assert row.vc_contact_id == contact.id and row.vc_link_confirmed == 1
    assert contact.user_id == users["u1"].id               # 넣은 사람
    assert not contact.source_sheet                         # = `직접 추가`
    assert (contact.name, contact.phone, contact.firm, contact.title, contact.email) == (
        "박도윤", "010-2222-3333", "라마바투자", "심사역", "park@example.com")
    # 딜소개 방은 지어내지 않는다 — 연결은 그 담당이 한다(발송 대상도 아니다)
    assert not contact.kakao_room_name and contact.connect_stage == "not_started"
    # 투자사 관리 현황(넣은 사람의 표)에 서고, `딜 소싱` 칸에 이 갈래가 선다
    assert column(board, contact.id) == "O"
    # [추가] 의 참여 기본값은 예전 그대로 `참여`
    assert row.participation == "참여"


def test_a_name_alone_is_enough_to_make_one(board, db, users):
    r = add(board, name="박도윤")
    assert r.status_code == 200, r.text
    [contact] = investors(db)
    assert contact.name == "박도윤" and not contact.phone


def test_the_other_synced_buckets_also_make_one(board, db, users):
    r = add(board, bucket=MNA, name="박도윤", phone="010-2222-3333")
    assert r.status_code == 200, r.text
    from app.models import SourcingContact

    [contact] = investors(db)
    row = db.get(SourcingContact, r.json()["id"])
    assert row.bucket == MNA and row.vc_contact_id == contact.id


# ── ② 있으면 잇는다 ─────────────────────────────────────────────────────────

def test_an_existing_investor_is_linked_not_copied(board, db, users):
    contact = vc(db, users, phone="010-5555-6666")
    r = add(board, bucket=MNA, name="홍길동", phone="01055556666")
    assert r.status_code == 200, r.text
    assert SHEET in r.json()["linked_msg"]
    assert [c.id for c in investors(db)] == [contact.id]   # 새로 안 만들었다
    from app.models import SourcingContact
    assert db.get(SourcingContact, r.json()["id"]).vc_contact_id == contact.id


# ── ③ 헷갈리면 아무것도 안 만든다 ───────────────────────────────────────────

def test_two_matching_investors_make_nothing(board, db, users):
    other_list(db, users)
    mine = vc(db, users)
    theirs = vc(db, users, who="u2", sheet=OTHER_SHEET)
    r = add(board, name="홍길동", phone="010-1234-5678")
    assert r.status_code == 200, r.text
    assert "linked_msg" not in r.json()
    assert "새로 만들지 않았습니다" in r.json()["vc_msg"]
    assert {c.id for c in investors(db)} == {mine.id, theirs.id}
    [row] = sync_rows(db)
    assert row.vc_contact_id is None
    assert {c["id"] for c in picks(db, row)} == {mine.id, theirs.id}   # 후보로 뜬다


def test_a_name_only_match_makes_nothing(board, db, users):
    contact = vc(db, users, phone="010-1234-5678")
    r = add(board, name="홍길동")                              # 번호 없이
    assert "vc_msg" in r.json()
    assert [c.id for c in investors(db)] == [contact.id]
    [row] = sync_rows(db)
    assert [c["id"] for c in picks(db, row)] == [contact.id]


def test_a_hidden_lookalike_also_stops_a_copy(board, db, users):
    """표에서 감춘 줄이어도 같은 분이면 또 만들지 않는다."""
    contact = vc(db, users, is_hidden=1)
    r = add(board, name="홍길동", phone="010-1234-5678")
    assert "vc_msg" in r.json()
    assert [c.id for c in investors(db)] == [contact.id]


# ── ④ 딜 소개 X · 딜 소개 보류 ──────────────────────────────────────────────

def test_an_on_hold_investor_is_refused(board, db, users):
    vc(db, users, group_name="딜 소개 보류")
    r = add(board, name="홍길동", phone="010-1234-5678")
    assert r.status_code == 400
    assert "딜 소개 보류" in r.json()["detail"]
    assert sync_rows(db) == [] and len(investors(db)) == 1


def test_a_no_intro_investor_is_refused_in_any_bucket(board, db, users):
    vc(db, users, name="홍길동 (딜 소개 X)")
    r = add(board, bucket=CEO, name="홍길동", phone="010-1234-5678")   # 잇지 않는 갈래도
    assert r.status_code == 400
    from app.models import SourcingContact
    db.expire_all()
    assert db.query(SourcingContact).count() == 0


def test_a_typed_no_intro_mark_is_refused(board, db, users):
    r = add(board, name="박도윤(딜소개X)")
    assert r.status_code == 400
    assert investors(db) == [] and sync_rows(db) == []


# ── ⑤ 넣은 뒤에는 같이 바뀐다 ───────────────────────────────────────────────

def test_edits_flow_both_ways_after_adding(board, db, users):
    r = add(board, name="박도윤")
    row_id = r.json()["id"]
    [contact] = investors(db)

    # 딜 소싱에서 번호 · 회사를 적으면 투자사 줄에도
    r = board.patch(f"/api/sourcing/{row_id}", json={"phone": "010-2222-3333",
                                                     "firm": "라마바투자"})
    assert r.status_code == 200, r.text
    [contact] = investors(db)
    assert (contact.phone, contact.firm) == ("010-2222-3333", "라마바투자")

    # 투자사 관리 현황에서 직함을 고치면 딜 소싱 줄에도
    r = board.patch(f"/api/contacts/{contact.id}", json={"title": "이사"})
    assert r.status_code == 200, r.text
    [row] = sync_rows(db)
    assert row.title == "이사"
    # 메모는 따로다
    board.patch(f"/api/sourcing/{row_id}", json={"memo": "딜 소싱 방 이야기"})
    assert not investors(db)[0].memo


# ── ⑥ 잇지 않는 갈래 ────────────────────────────────────────────────────────

def test_an_unsynced_bucket_stays_sourcing_only(board, db, users):
    from app.models import SourcingContact

    r = add(board, bucket=CEO, name="최대표", phone="010-7777-8888")
    assert r.status_code == 200, r.text
    assert "linked_msg" not in r.json() and "vc_msg" not in r.json()
    assert investors(db) == []
    assert db.get(SourcingContact, r.json()["id"]).vc_contact_id is None


def test_the_add_button_says_which_tabs_are_linked(board, db, users):
    sc(db)
    sc(db, bucket=CEO, name="최대표", position=1000)
    synced = board.get("/sourcing", params={"tab": SYNC}).text
    assert "투자사 관리 현황에도 같이 들어갑니다" in synced
    assert 'data-testid="sourcing-add-unsynced"' not in synced
    assert 'data-testid="sourcing-add-unsynced"' in board.get(
        "/sourcing", params={"tab": CEO}).text
