"""딜 소싱 ↔ 투자사 관리 현황 잇기 판(0093) — **확실한 것만 잇는가.**

`tests/test_migrations.py` 는 빈 DB 로 오르내린다 — 그 길에서는 소싱 줄이 한
줄도 없어 처음 한 번 잇기(backfill)가 밟히지 않는다. 운영과 같은 모양을 세워
그 길을 밟는다.

운영 DB 는 이 칸들이 **없는** 표에서 출발한다(`0001` 의 `create_all()` 은 지금
모델로 만들어 이미 칸이 있다). 그래서 0087 까지 올린 뒤 `sourcing_contacts` 를
옛 모양(두 칸 · 색인 없음)으로 다시 세운다 — `0059` 검사가 칸을 손으로 지우는
것과 같은 자리다(외래키가 걸린 칸은 `DROP COLUMN` 이 안 돼 표를 다시 세운다).

이름 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import sqlite3

import pytest

from .test_migrations import _alembic

BEFORE = "0087_sourcing_mail"
SYNC = "시리즈 A 이상 딜 소싱 참여 심사역"
NOW = "2026-10-14T00:00:00+09:00"


def _old_shape(con) -> None:
    cols = [r[1] for r in con.execute('PRAGMA table_info("sourcing_contacts")')
            if r[1] not in ("vc_contact_id", "participation")]
    keep = ", ".join(cols)
    con.execute("DROP INDEX IF EXISTS uq_sourcing_contacts_vc_contact")
    con.execute(f"CREATE TABLE sc_old AS SELECT {keep} FROM sourcing_contacts")
    con.execute("DROP TABLE sourcing_contacts")
    con.execute("ALTER TABLE sc_old RENAME TO sourcing_contacts")


@pytest.fixture()
def old_db(tmp_path):
    db = tmp_path / "old.db"
    done = _alembic(db, "upgrade", BEFORE)
    assert done.returncode == 0, done.stdout + done.stderr

    con = sqlite3.connect(db)
    try:
        _old_shape(con)
        # 계정 줄은 넣지 않는다 — 이 판이 읽는 것은 명단 · 투자사 · 소싱 셋이다
        # (`sqlite3` 는 외래키를 기본으로 안 본다).
        con.execute("INSERT INTO sheet_owners (id, label, user_id, layout, is_hidden, "
                    f"is_deal_list, created_at, updated_at) VALUES "
                    f"(1, '투자사 명단', 1, 'investor', 0, 1, '{NOW}', '{NOW}'), "
                    f"(2, '스타트업 명단', 1, 'startup', 1, 0, '{NOW}', '{NOW}')")
        vc = ("INSERT INTO vc_contacts (id, user_id, name, phone, source_sheet, "
              "is_hidden, channel_kakao, channel_email, room_verified, status, "
              f"connect_stage, created_at, updated_at) VALUES (?, 1, ?, ?, ?, ?, 1, 0, "
              f"'verified', 'active', 'connected', '{NOW}', '{NOW}')")
        con.executemany(vc, [
            (11, "가투자", "010-1111-0001", "투자사 명단", 0),   # ① 깔끔하게 맞는다
            (12, "나투자", "010-1111-0002", "투자사 명단", 0),   # ② 두 줄 — 겹침
            (13, "나투자", "01011110002", "투자사 명단", 0),
            (14, "다투자", "010-1111-0003", "투자사 명단", 1),   # ③ 감춘 줄 + 보이는 줄
            (15, "다투자", "010-1111-0003", "투자사 명단", 0),
            (16, "라대표", "010-1111-0004", "스타트업 명단", 0),  # ④ 투자사가 아니다
            (17, "마투자", "010-1111-0005", "투자사 명단", 0),   # ⑤ 소싱 쪽이 겹친다
            (18, "바투자", "010-1111-0006", "투자사 명단", 0),   # ⑥ 다른 갈래에만
        ])
        sc = ("INSERT INTO sourcing_contacts (id, bucket, position, name, phone, "
              f"room_verified, created_at, updated_at) VALUES (?, ?, ?, ?, ?, "
              f"'unverified', '{NOW}', '{NOW}')")
        con.executemany(sc, [
            (101, SYNC, 1, "가투자", "01011110001"),
            (102, SYNC, 2, "나투자", "010-1111-0002"),
            (103, SYNC, 3, "다투자", "010 1111 0003"),
            (104, SYNC, 4, "라대표", "010-1111-0004"),
            (105, SYNC, 5, "마투자", "010-1111-0005"),
            (106, SYNC, 6, "마투자", "010-1111-0005"),
            (107, "M&A 찾는 투자사", 1000, "바투자", "010-1111-0006"),
            (108, SYNC, 7, "사투자", None),                    # ⑦ 번호 없음
            (109, SYNC, 8, "아투자", "010-9999-0000"),         # ⑧ 맞는 줄 없음
        ])
        # ① 의 두 줄 — 소싱 쪽 메일은 비고 회사는 다르게 적혀 있다
        con.execute("UPDATE vc_contacts SET email = 'ga@example.com', firm = '가나다벤처스' "
                    "WHERE id = 11")
        con.execute("UPDATE sourcing_contacts SET firm = '가나다벤처스(주)' WHERE id = 101")
        con.commit()
    finally:
        con.close()
    return db


def _rows(db) -> dict:
    con = sqlite3.connect(db)
    try:
        return {sid: (cid, part) for sid, cid, part in con.execute(
            "SELECT id, vc_contact_id, participation FROM sourcing_contacts")}
    finally:
        con.close()


def test_only_the_sure_ones_are_linked(old_db):
    up = _alembic(old_db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr

    rows = _rows(old_db)
    linked = {sid: cid for sid, (cid, _p) in rows.items() if cid}
    assert linked == {
        101: 11,   # ① 번호 숫자가 같고 양쪽에 한 줄씩
        103: 15,   # ③ 감춘 줄은 세지 않는다 — 보이는 줄 하나와 맞는다
    }
    # ② 투자사 쪽 겹침 · ④ 스타트업 명단 · ⑤ 소싱 쪽 겹침 · ⑥ 다른 갈래 ·
    # ⑦ 번호 없음 · ⑧ 맞는 줄 없음 — 잇지 않는다
    for sid in (102, 104, 105, 106, 107, 108, 109):
        assert rows[sid][0] is None, sid
    # 있던 줄은 모두 `참여` 로 시작한다
    assert {part for _cid, part in rows.values()} == {"참여"}


def test_only_blank_fields_are_filled(old_db):
    """빈 칸만 채우고, 다르게 적힌 값은 덮지 않는다(`sourcing_sync.link` 와 같다)."""
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    con = sqlite3.connect(old_db)
    try:
        email, firm = con.execute(
            "SELECT email, firm FROM sourcing_contacts WHERE id = 101").fetchone()
        untouched = con.execute(
            "SELECT email FROM sourcing_contacts WHERE id = 109").fetchone()[0]
    finally:
        con.close()
    assert email == "ga@example.com"
    assert firm == "가나다벤처스(주)"
    assert untouched is None


def test_the_rule_matches_the_app(db, users):
    """이주가 이은 짝 = 앱이 딜 소싱에서 넣을 때 저절로 잇는 규칙(`auto_link`)."""
    from app.models import SheetOwner, SourcingContact, VcContact
    from app.services import sourcing_sync

    db.add_all([SheetOwner(label="투자사 명단", user_id=1, layout="investor"),
                SheetOwner(label="스타트업 명단", user_id=1, layout="startup",
                           is_hidden=1)])
    for cid, name, phone, sheet, hidden in (
            (11, "가투자", "010-1111-0001", "투자사 명단", 0),
            (12, "나투자", "010-1111-0002", "투자사 명단", 0),
            (13, "나투자", "01011110002", "투자사 명단", 0),
            (14, "다투자", "010-1111-0003", "투자사 명단", 1),
            (15, "다투자", "010-1111-0003", "투자사 명단", 0),
            (16, "라대표", "010-1111-0004", "스타트업 명단", 0)):
        db.add(VcContact(id=cid, user_id=1, name=name, phone=phone,
                         source_sheet=sheet, is_hidden=hidden))
    db.commit()
    got = {}
    for sid, name, phone in ((101, "가투자", "01011110001"),
                             (102, "나투자", "010-1111-0002"),
                             (103, "다투자", "010 1111 0003"),
                             (104, "라대표", "010-1111-0004")):
        row = SourcingContact(id=sid, bucket=SYNC, position=sid, name=name, phone=phone)
        db.add(row)
        contact = sourcing_sync.auto_link(db, row)
        db.commit()
        if contact is not None:
            got[sid] = contact.id
    assert got == {101: 11, 103: 15}


def test_running_it_again_changes_nothing(old_db):
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    before = _rows(old_db)
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    assert _rows(old_db) == before


def test_it_comes_down_and_goes_back_up(old_db):
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    down = _alembic(old_db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
    con = sqlite3.connect(old_db)
    try:
        cols = {r[1] for r in con.execute('PRAGMA table_info("sourcing_contacts")')}
    finally:
        con.close()
    assert not {"vc_contact_id", "participation"} & cols
    up = _alembic(old_db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert _rows(old_db)[101] == (11, "참여")
