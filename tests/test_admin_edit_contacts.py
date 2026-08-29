"""관리자는 팀 전체의 담당자를 **보고 또 고친다**.

투자사 관리 현황을 관리자로 열면 팀 전체가 뜨는데, 그 줄을 눌러 고치면
`담당자를 찾을 수 없습니다`(404) 가 났다 — **보이는데 못 고치는** 상태였다.
보는 쪽(`contact_rows` 의 `team_wide`)과 고치는 쪽(`routers/contacts.py` 의
`_owned`)이 각자 `role == "admin"` 을 들고 있어서 갈린 자리다. 이 저장소가
반복해서 당한 부류라(투자사 수가 화면마다 갈린 일, 좌측 메뉴와 라우터가
갈린 일) 판정을 `deps.may_manage_team_contacts` 한 곳으로 모았다.

여기서 못 박는 것은 두 가지다.

* **관리자에게는 열리고, 팀원·투자컨설턴트에게는 그대로 막힌다.** 막힌 쪽은
  상태 코드만 보지 않는다 — 404 를 받아 놓고 값은 바뀌어 있으면 그게 제일
  나쁜 상태다. 대상 줄을 되읽어 그대로인지 본다.
* **보는 것과 고치는 것이 갈리지 않는다.** 마지막 검사는 관리자 화면에 실제로
  뜬 줄을 훑어 전부 고쳐지는지 대조한다. 고칠 수 있는 줄을 손으로 나열해 두면
  다음에 판정이 하나 늘 때 또 갈린다 — 애초에 그렇게 갈렸다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

# 화면에 그려진 담당자 줄(`<tr class="data-row" data-id="12" …>`)에서 번호만.
# 표를 훑는 검사가 이 규칙 하나만 알면 되도록 여기 한 번만 적는다.
ROW_ID = re.compile(r'<tr class="data-row[^"]*" data-id="(\d+)"')


@pytest.fixture()
def people(db, users):
    """관리자 · 투자컨설턴트. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=61, name="관리자시험", phone="01070000001", role="admin",
             password_hash=pw),
        User(id=63, name="컨설턴트시험", phone="01070000003", role="consultant",
             password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


@pytest.fixture()
def board(db, users, people):
    """두 팀원이 명단을 하나씩 맡은 상태 — 관리자 화면에는 둘 다 뜬다.

    번호로 돌려준다. ORM 객체를 그대로 넘기면 커밋마다 만료되어, 검사가
    보려는 것(값이 바뀌었나)이 아니라 세션 상태를 보게 된다.
    """
    from app.models import SheetOwner, VcContact

    db.add_all([
        SheetOwner(label="가 명단", user_id=users["u1"].id),
        SheetOwner(label="나 명단", user_id=users["u2"].id),
    ])
    rows = [
        VcContact(user_id=users["u1"].id, name="가담당", firm="가나벤처스",
                  source_sheet="가 명단", connect_stage="connected",
                  phone="010-7000-0001", memo="처음 값"),
        VcContact(user_id=users["u2"].id, name="나담당", firm="다라벤처스",
                  source_sheet="나 명단", connect_stage="connected",
                  phone="010-7000-0002", memo="처음 값"),
    ]
    db.add_all(rows)
    db.commit()
    return {"u1_row": rows[0].id, "u2_row": rows[1].id}


@pytest.fixture()
def portal(db, users, people, board):
    """역할별로 따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여서 어느 사람으로 부른
    것인지 알 수 없게 된다(`test_admin_guard.py` 와 같은 방식).
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {
        "admin": sign_in("01070000001"),
        "member": sign_in("01000000002"),      # u2 — `가담당` 은 남의 것이다
        "owner": sign_in("01000000001"),       # u1 — `가담당` 의 주인
        "consultant": sign_in("01070000003"),
    }


def _memo(db, contact_id: int) -> str:
    """저장된 메모를 **다시 읽는다.** 응답만 보면 안 들어간 것을 못 잡는다."""
    from app.models import VcContact

    db.expire_all()
    row = db.get(VcContact, contact_id)
    return "" if row is None else (row.memo or "")


# --- 관리자: 남의 담당자도 보고 고치고 지운다 --------------------------------
#
# `_owned` 를 쓰는 경로는 셋이다. 화면에서 셋 다 **같은 줄 하나**에 걸려 있다 —
# 줄을 누르면 상세가 열리고(GET), [저장]·칸 인라인 수정이 PATCH, [삭제]가
# DELETE 다. 하나만 열어 두면 관리자 화면에 열리지 않는 단추가 남는다.

def test_admin_opens_someone_elses_contact(portal, board):
    """상세 패널(GET) — 표에 뜬 줄을 누르면 열리는 자리."""
    r = portal["admin"].get(f"/api/contacts/{board['u1_row']}")
    assert r.status_code == 200
    assert r.json()["contact"]["name"] == "가담당"


def test_admin_edits_someone_elses_contact(portal, board, db):
    """인라인 수정(PATCH) — 사용자가 실제로 막혔다고 보고한 자리."""
    r = portal["admin"].patch(f"/api/contacts/{board['u1_row']}",
                              json={"memo": "관리자가 고침"})
    assert r.status_code == 200
    # 200 만 보고 넘어가면 `_assign` 에서 칸이 빠졌을 때를 못 잡는다.
    assert _memo(db, board["u1_row"]) == "관리자가 고침"


def test_admin_deletes_someone_elses_contact(portal, board, db):
    """삭제(DELETE) — 상세 패널의 [삭제] 단추.

    관리자에게 연다. 이 단추는 표에 뜬 줄이면 조건 없이 그려지고(contacts.html),
    관리자는 이미 명단의 담당을 통째로 옮기고 명단을 감춘다 — 그보다 작은
    한 줄 지우기만 막아 두면 또 보이는데 안 되는 단추가 된다.
    """
    from app.models import VcContact

    r = portal["admin"].delete(f"/api/contacts/{board['u1_row']}")
    assert r.status_code == 200
    db.expire_all()
    assert db.get(VcContact, board["u1_row"]) is None


# --- 팀원: 남의 것은 그대로 막힌다 -------------------------------------------

def test_member_cannot_open_someone_elses_contact(portal, board):
    """존재 여부도 흘리지 않는다 — 403(있지만 권한 없음)이 아니라 404 다."""
    r = portal["member"].get(f"/api/contacts/{board['u1_row']}")
    assert r.status_code == 404
    assert r.json()["detail"] == "담당자를 찾을 수 없습니다"


def test_member_cannot_edit_someone_elses_contact(portal, board, db):
    r = portal["member"].patch(f"/api/contacts/{board['u1_row']}",
                               json={"memo": "남이 고침"})
    assert r.status_code == 404
    # **상태 코드만 보면 못 잡는다.** 404 를 돌려주면서 값은 들어가 있는 것이
    # 제일 나쁜 상태다 — 되읽어 그대로인지 본다.
    assert _memo(db, board["u1_row"]) == "처음 값"


def test_member_cannot_delete_someone_elses_contact(portal, board, db):
    from app.models import VcContact

    r = portal["member"].delete(f"/api/contacts/{board['u1_row']}")
    assert r.status_code == 404
    db.expire_all()
    assert db.get(VcContact, board["u1_row"]) is not None


# --- 투자컨설턴트: 이 화면에 애초에 볼일이 없다 ------------------------------

def test_consultant_cannot_edit_anyones_contact(portal, board, db):
    """컨설턴트는 `_owned` 까지 가지도 못한다 — 미들웨어가 먼저 끊는다.

    막는 자리가 다르므로 답도 다르다(404 가 아니라 403). 그래도 여기서 함께
    못 박는 것은, 허용 목록(`deps.CONSULTANT_PATHS`)에 `/api/contacts` 가
    실수로 들어가는 날 이 검사가 먼저 울려야 하기 때문이다 — 그때 `_owned` 는
    컨설턴트를 **남인지 아닌지**로만 보고, 자기 앞으로 된 줄이 하나라도 있으면
    통과시킨다.
    """
    r = portal["consultant"].patch(f"/api/contacts/{board['u1_row']}",
                                   json={"memo": "컨설턴트가 고침"})
    assert r.status_code == 403
    assert _memo(db, board["u1_row"]) == "처음 값"


def test_consultant_cannot_delete_anyones_contact(portal, board, db):
    from app.models import VcContact

    r = portal["consultant"].delete(f"/api/contacts/{board['u1_row']}")
    assert r.status_code == 403
    db.expire_all()
    assert db.get(VcContact, board["u1_row"]) is not None


# --- 본인 것은 지금까지대로 -------------------------------------------------

def test_owner_still_edits_own_contact(portal, board, db):
    """관리자에게 열어 준 것이 팀원의 제 담당분을 건드리면 안 된다."""
    r = portal["owner"].patch(f"/api/contacts/{board['u1_row']}",
                              json={"memo": "주인이 고침"})
    assert r.status_code == 200
    assert _memo(db, board["u1_row"]) == "주인이 고침"


def test_owner_still_opens_and_deletes_own_contact(portal, board, db):
    from app.models import VcContact

    assert portal["owner"].get(f"/api/contacts/{board['u1_row']}").status_code == 200
    assert portal["owner"].delete(f"/api/contacts/{board['u1_row']}").status_code == 200
    db.expire_all()
    assert db.get(VcContact, board["u1_row"]) is None


# --- 보는 것과 고치는 것이 갈리지 않는다 -------------------------------------

def test_every_row_on_the_admin_screen_can_be_edited(portal, db):
    """**관리자 화면에 뜬 줄은 전부 고쳐진다.**

    고칠 수 있는 줄을 손으로 적어 두면 다음에 또 갈린다 — 화면이 실제로 그린
    줄을 훑어 하나씩 눌러 본다. 판정이 다시 둘로 쪼개지는 날, 어느 쪽이
    넓어지든 여기서 먼저 걸린다.
    """
    page = portal["admin"].get("/contacts?sheet=all")
    assert page.status_code == 200
    ids = [int(x) for x in ROW_ID.findall(page.text)]

    # 검사가 빈 표를 훑고 통과하는 일이 없게 — 두 사람의 줄이 다 떠 있어야
    # '남의 줄' 을 실제로 눌러 본 것이 된다.
    from app.models import VcContact

    assert len(ids) >= 2
    assert len({db.get(VcContact, i).user_id for i in ids}) >= 2

    for row_id in ids:
        opened = portal["admin"].get(f"/api/contacts/{row_id}")
        saved = portal["admin"].patch(f"/api/contacts/{row_id}",
                                      json={"memo": "훑어 고침"})
        assert opened.status_code == 200, f"{row_id} 번 줄은 화면에 떴는데 안 열린다"
        assert saved.status_code == 200, f"{row_id} 번 줄은 화면에 떴는데 안 고쳐진다"
        assert _memo(db, row_id) == "훑어 고침"


def test_member_screen_and_edit_scope_match(portal, db, board):
    """팀원 쪽도 같은 대조 — 열리는 줄만 뜨고, 뜬 줄은 전부 고쳐진다.

    관리자에게 열어 주면서 팀원 화면이 함께 넓어지지 않았는지 본다. 넓어졌다면
    표에 남의 줄이 뜨고 그 줄이 고쳐질 것이다.
    """
    from app.models import VcContact

    page = portal["member"].get("/contacts?sheet=all")
    ids = [int(x) for x in ROW_ID.findall(page.text)]

    assert ids, "팀원 화면에 제 담당 줄이 하나는 떠야 한다"
    assert all(db.get(VcContact, i).user_id == 2 for i in ids)
    for row_id in ids:
        assert portal["member"].patch(f"/api/contacts/{row_id}",
                                      json={"memo": "본인 줄"}).status_code == 200

    # 남의 줄은 표에도 없고 고쳐지지도 않는다.
    assert board["u1_row"] not in ids
