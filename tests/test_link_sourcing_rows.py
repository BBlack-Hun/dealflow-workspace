"""`scripts/link_sourcing_rows.py` — 대표 · 개인참여 갈래의 **이미 있는 줄**을 투자사 관리 현황과
잇는다(2026-10-22 두 갈래도 잇기로 한 뒤 한 번 돌린다).

  ① [추가]와 같은 규칙(`add_from_sourcing`) — 이름 + 번호가 하나면 잇고, 같은 분일 수 있는
     줄이 있으면 안 만들고, `(딜 소개 X)` 는 막고, 아무도 없으면 새 투자사 줄
  ② 새 투자사 줄의 계정 — 딜 소싱 담당자 칸의 지금 맡은 사람 → 같은 이름 계정 → 그 사람
     이름 탭의 주인 계정 → `--user-id` → 없으면 안 만든다
  ③ `불참여` 줄은 새로 만들지 않는다 · 다른 갈래 줄은 건드리지 않는다
  ④ 미리보기(기본)는 DB 에 안 쓴다 · `--apply` 는 쓰고, 다시 돌리면 더 할 일이 없다

이름 · 회사 · 번호는 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import pytest

from tests.test_sourcing_vc_sync import SHEET, SYNC, sc, vc

CEO = "딜 소싱  참여 투자사 대표"
SOLO = "딜 소싱  개인참여 심사역"
TAB = "한서준 투자사 50명"            # 계정 이름이 사람 이름이 아닌 계정의 탭


@pytest.fixture()
def rows(db, users):
    from app.models import SheetOwner, User

    team = User(id=3, name="백업계정", phone="01000000003", role="user", password_hash="x")
    db.add(team)
    db.flush()
    db.add_all([SheetOwner(label=SHEET, user_id=users["u1"].id, layout="investor"),
                SheetOwner(label=TAB, user_id=3, layout="investor")])
    db.commit()
    users = dict(users, u3=team)
    exact = vc(db, users)                                             # 홍길동 010-1234-5678
    vc(db, users, name="김서연", phone="010-9000-0000", who="u3", sheet=TAB)
    made = {
        "exact": sc(db, bucket=CEO, phone="01012345678", assignee_name="가팀"),
        "to_u2": sc(db, bucket=CEO, name="새대표", phone="010-2000-0001",
                    assignee_name="가팀 > 7/1 윤서아"),
        "to_tab": sc(db, bucket=SOLO, name="새개인", phone="010-2000-0002",
                     assignee_name="한서준"),
        "team": sc(db, bucket=SOLO, name="팀담당", phone="010-2000-0003", assignee_name="가팀"),
        "held": sc(db, bucket=SOLO, name="김서연", phone="010-2000-0004",
                   assignee_name="강민준"),
        "left": sc(db, bucket=CEO, name="빠진분", phone="010-2000-0005",
                   assignee_name="강민준", participation="불참여"),
        "blocked": sc(db, bucket=CEO, name="막힌분 (딜 소개 X)", phone="010-2000-0006",
                      assignee_name="강민준"),
        "other": sc(db, bucket=SYNC, name="시리즈분", phone="010-2000-0007",
                    assignee_name="강민준"),
    }
    return {"exact_contact": exact, **made}


def _state(db):
    from app.models import SourcingContact, VcContact

    db.expire_all()
    return ({r.id: r.vc_contact_id for r in db.query(SourcingContact)},
            db.query(VcContact).count())


def test_each_row_goes_the_way_add_would(db, users, rows):
    from app.models import VcContact
    from scripts import link_sourcing_rows

    got = {rid: (action, uid) for rid, action, uid in link_sourcing_rows.run(db)}
    ids = {key: row.id for key, row in rows.items() if key != "exact_contact"}
    assert got == {
        ids["exact"]: ("linked", None),
        ids["to_u2"]: ("created", users["u2"].id),        # 담당자 칸의 지금 맡은 사람
        ids["to_tab"]: ("created", 3),                    # 그 사람 이름 탭의 주인 계정
        ids["team"]: ("no_owner", None),                  # 팀 이름 — 계정을 모른다
        ids["held"]: ("held", None),                      # 이름만 같은 투자사 줄이 있다
        ids["left"]: ("left", None),
        ids["blocked"]: ("blocked", None),
    }                                                     # 시리즈 A 줄은 안 건드린다
    db.commit()
    made = db.get(VcContact, rows["to_u2"].vc_contact_id)
    assert (made.user_id, made.name, made.source_sheet) == (users["u2"].id, "새대표", None)
    assert rows["exact"].vc_contact_id == rows["exact_contact"].id
    assert rows["other"].vc_contact_id is None


def test_user_id_is_the_fallback_owner(db, users, rows):
    from scripts import link_sourcing_rows

    got = {rid: (action, uid) for rid, action, uid
           in link_sourcing_rows.run(db, fallback=users["u1"])}
    assert got[rows["team"].id] == ("created", users["u1"].id)
    assert got[rows["to_u2"].id] == ("created", users["u2"].id)   # 찾은 계정이 먼저
    assert got[rows["left"].id] == ("left", None)                 # 불참여는 그래도 안 만든다


def test_dry_run_writes_nothing_and_apply_is_one_shot(db, users, rows, capsys):
    from scripts import link_sourcing_rows

    before = _state(db)
    assert link_sourcing_rows.main([]) == 0
    out = capsys.readouterr().out
    assert "미리보기" in out and "새 투자사 줄 만들어 이음 2" in out
    assert "투자사 줄과 이음 1" in out and "(모두 7)" in out
    assert "새대표" not in out and "가팀" not in out             # 이름을 찍지 않는다
    assert _state(db) == before

    assert link_sourcing_rows.main(["--apply"]) == 0
    links, contacts = _state(db)
    assert contacts == before[1] + 2
    assert sum(1 for v in links.values() if v) == 3

    # 다시 돌리면 이미 이은 줄은 빠진다
    assert link_sourcing_rows.main([]) == 0
    assert "(모두 4)" in capsys.readouterr().out
