"""투자사 관리 현황 — 고른 줄 **여러 개**를 한 번에 이관(`/api/contacts/bulk-transfer`).

줄 하나 넘기기(`tests/test_contact_transfer.py`)와 같은 판정을 줄마다 되풀이한다.
여기서 못 박는 것은 넷이다.

  1. **여러 줄이 한 번에 넘어간다** — 담당 · 명단이 함께 바뀐다
  2. **권한은 줄 하나와 같다** — 남의 줄이 섞이면 통째로 404, 한 줄도 안 옮긴다
  3. **건너뛴 줄은 이유와 함께 돌려준다** — 이미 그 명단 · 다른 화면의 명단
  4. **수정 기록이 줄마다 남는다** — 한 요청의 주소로

이름 · 회사 · 번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

MINE = "가 명단"
YOURS = "나 명단"
POOL = "투자사 풀"
STARTUP_LIST = "스타트업 명단"
URL = "/api/contacts/bulk-transfer"


@pytest.fixture()
def board(db, users):
    """u1 명단에 셋, u2 명단에 하나, u2 의 스타트업 명단에 하나. 관리자 · 컨설턴트."""
    from app.models import SheetOwner, User, VcContact
    from app.services import auth as auth_svc
    from app.services import contact_columns as cc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    db.add_all([
        User(id=71, name="관리자시험", phone="01070000011", role="admin",
             can_view_consulting=1, password_hash=pw),
        User(id=73, name="컨설턴트시험", phone="01070000013", role="consultant",
             can_view_consulting=1, password_hash=pw),
        SheetOwner(label=MINE, user_id=users["u1"].id),
        SheetOwner(label=YOURS, user_id=users["u2"].id),
        SheetOwner(label=POOL),
        SheetOwner(label=STARTUP_LIST, user_id=users["u2"].id, layout=cc.STARTUP),
    ])
    u1, u2 = users["u1"].id, users["u2"].id
    rows = {
        "a": VcContact(user_id=u1, source_sheet=MINE, name="가상하나", firm="가상벤처스"),
        "b": VcContact(user_id=u1, source_sheet=MINE, name="가상두리", firm="가상파트너스"),
        "c": VcContact(user_id=u1, source_sheet=MINE, name="가상세찌", firm="가상캐피탈"),
        "d": VcContact(user_id=u2, source_sheet=YOURS, name="가상네찌", firm="가상인베스트"),
        "e": VcContact(user_id=u2, source_sheet=STARTUP_LIST, name="가상다섯", firm="가상랩스"),
    }
    db.add_all(rows.values())
    db.commit()
    return {k: v.id for k, v in rows.items()}


def sign_in(client, phone):
    r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    assert r.status_code in (200, 303)
    return client


def row(db, contact_id):
    from app.models import VcContact

    db.expire_all()
    return db.get(VcContact, contact_id)


# ── 1. 여러 줄이 한 번에 넘어간다 ───────────────────────────────────────────

def test_내_줄_여러_개를_한_번에_넘긴다(client, db, users, board):
    sign_in(client, "01000000001")
    r = client.post(URL, json={"contact_ids": [board["a"], board["b"]], "label": YOURS})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [m["id"] for m in d["moved"]] == [board["a"], board["b"]]
    assert d["skipped"] == []
    assert d["owner"] == users["u2"].name

    for key in ("a", "b"):
        moved = row(db, board[key])
        assert moved.user_id == users["u2"].id, "담당이 안 바뀌었습니다"
        assert YOURS in moved.source_sheet and MINE not in moved.source_sheet, (
            "옛 명단에 그대로 남았습니다 — 딜 소개가 두 번 나갑니다")
    # 안 고른 줄은 그대로다.
    assert row(db, board["c"]).source_sheet == MINE


# ── 2. 권한은 줄 하나와 같다 ────────────────────────────────────────────────

def test_남의_줄이_섞이면_한_줄도_안_넘어간다(client, db, users, board):
    """반만 넘어가면 사람이 고른 것과 실제로 바뀐 것이 달라진다."""
    sign_in(client, "01000000001")
    r = client.post(URL, json={"contact_ids": [board["a"], board["d"]], "label": MINE})
    assert r.status_code == 404, r.text
    assert row(db, board["a"]).source_sheet == MINE
    kept = row(db, board["d"])
    assert kept.user_id == users["u2"].id and kept.source_sheet == YOURS, (
        "막혔다면서 남의 줄이 바뀌었습니다")


def test_투자컨설턴트는_이_길에_닿지_못한다(client, db, board):
    sign_in(client, "01070000013")
    r = client.post(URL, json={"contact_ids": [board["a"]], "label": YOURS})
    assert r.status_code == 403, r.text
    assert row(db, board["a"]).source_sheet == MINE


@pytest.mark.parametrize("label", [POOL, "없는 명단", ""])
def test_담당이_없는_곳으로는_통째로_거절한다(client, db, board, label):
    sign_in(client, "01000000001")
    r = client.post(URL, json={"contact_ids": [board["a"], board["b"]], "label": label})
    assert r.status_code == 400, r.text
    assert row(db, board["a"]).source_sheet == MINE
    assert row(db, board["b"]).source_sheet == MINE


def test_아무_줄도_안_고르면_거절한다(client, board):
    sign_in(client, "01000000001")
    assert client.post(URL, json={"contact_ids": [], "label": YOURS}).status_code == 400


# ── 3. 건너뛴 줄은 이유와 함께 ──────────────────────────────────────────────

def test_건너뛴_줄은_이유와_함께_돌려준다(client, db, users, board):
    """관리자가 세 줄을 고른다 — 넘길 줄 · 이미 그 명단인 줄 · 다른 화면의 줄."""
    sign_in(client, "01070000011")
    r = client.post(URL, json={"contact_ids": [board["a"], board["d"], board["e"]],
                               "label": YOURS})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [m["id"] for m in d["moved"]] == [board["a"]]
    why = {s["id"]: s["why"] for s in d["skipped"]}
    assert "이미" in why[board["d"]]
    assert "다른 화면" in why[board["e"]]
    assert row(db, board["e"]).source_sheet == STARTUP_LIST, (
        "스타트업 명단의 줄이 투자사 명단으로 넘어갔습니다")


# ── 4. 수정 기록이 줄마다 남는다 ────────────────────────────────────────────

def test_수정_기록이_줄마다_남는다(client, db, users, board):
    """관리자가 남(u1)의 줄 둘을 넘긴다 — 한 요청의 주소로 줄마다 한 줄씩."""
    from app.models import EditLog

    sign_in(client, "01070000011")
    r = client.post(URL, json={"contact_ids": [board["a"], board["b"]], "label": YOURS})
    assert r.status_code == 200, r.text

    logs = db.query(EditLog).filter(EditLog.table_name == "vc_contacts").all()
    assert sorted(log.row_id for log in logs) == sorted([board["a"], board["b"]])
    for log in logs:
        assert log.path == URL
        assert log.actor_user_id == 71
        # 넘기기 **전** 주인으로 남는다(`edit_log._row_scope`).
        assert log.target_user_id == users["u1"].id
        assert log.scope == "others"


# ── 화면 ────────────────────────────────────────────────────────────────────

def test_투자사_관리_현황에_체크_칸과_막대가_선다(client, board):
    sign_in(client, "01000000001")
    html = client.get("/contacts", params={"sheet": MINE}).text
    assert 'id="transfer-pick-all"' in html
    assert html.count('class="transfer-cb"') == 3
    assert 'id="transfer-bar"' in html and "js/bulk_transfer.js" in html


def test_스타트업_화면에는_안_선다(client, board):
    sign_in(client, "01000000002")
    html = client.get("/startup").text
    assert 'class="transfer-cb"' not in html and 'id="transfer-bar"' not in html


def test_넘길_곳이_없으면_안_선다(client, db, users):
    """담당이 정해진 명단이 하나도 없으면 수정창의 [이관] 도 안 선다 — 같이 간다."""
    from app.models import SheetOwner, VcContact

    db.add_all([SheetOwner(label=POOL),
                VcContact(user_id=users["u1"].id, source_sheet=POOL, name="가상여섯")])
    db.commit()
    sign_in(client, "01000000001")
    html = client.get("/contacts", params={"sheet": "all"}).text
    assert 'class="transfer-cb"' not in html and 'id="transfer-bar"' not in html
