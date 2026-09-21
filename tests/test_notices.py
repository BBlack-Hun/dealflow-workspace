"""공지 — **이번에 무엇이 바뀌었는지**를 팀이 지나는 자리에 한 번 띄운다.

이 검사가 지키는 것은 넷이다.

1. **닿는다.** 관리자가 올리면 팀원이 여는 **아무 화면에나** 뜬다. 판은
   화면마다 심은 것이 아니라 밑틀(`base.html`)에 서 있고, 그래서 화면 목록을
   손으로 적지 않는다 — 앱에 등록된 화면을 훑는다.
2. **한 번 본 것은 다시 안 뜬다.** [확인] 을 누른 사람에게만 안 뜬다 —
   누르지 않은 사람에게는 그대로 있고, 띄운 것만으로는 읽은 것이 아니다.
3. **끌 수 있다.** 내리면 그 순간 아무에게도 안 뜬다.
4. **남의 이름이 새지 않는다.** 공지 본문에 이름이 실릴 수 있으므로,
   수정 로그에 값이 통째로 옮겨 가면 안 된다.

여기 쓰는 글은 **전부 지어낸 것**이다. 이 저장소는 공개라 실제 공지 문구를
기대값으로 박을 수 없다(`tests/conftest.py` 가 방 이름 접미사를 그렇게
다루는 것과 같은 이유다).
"""
from __future__ import annotations

import re

import pytest

from .conftest import DEMO_PASSWORD

# 지어낸 공지. 제목만으로도 무엇이 바뀌었는지 읽히는 모양이어야 한다.
TITLE = "미팅 종류 칸이 생겼습니다"
BODY = "딜 진행 관리에서 고를 수 있습니다.\n대면 · 비대면 둘 중 하나입니다."


@pytest.fixture()
def people(db, users):
    """관리자 · 투자컨설턴트. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=91, name="관리자시험", phone="01090000001", role="admin",
             password_hash=pw),
        User(id=92, name="컨설턴트시험", phone="01090000002", role="consultant",
             can_view_consulting=1, password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return {"admin": rows[0], "consultant": rows[1]}


@pytest.fixture()
def portal(db, users, people):
    """역할별로 따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여서 어느 사람으로 부른
    것인지 알 수 없게 된다(다른 검사들과 같은 얼개).
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
        "app": app,
        "admin": sign_in("01090000001"),
        "consultant": sign_in("01090000002"),
        "u1": sign_in("01000000001"),
        "u2": sign_in("01000000002"),
    }


def _publish(client, title: str = TITLE, body: str = BODY):
    r = client.post("/team/notices", data={"title": title, "body": body},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def _ids_on(client, path: str = "/") -> list:
    """그 화면의 공지 판이 들고 있는 번호 — 없으면 빈 목록."""
    html = client.get(path).text
    return [int(x) for x in re.findall(r'name="notice_id" value="(\d+)"', html)]


def _confirm(client, path: str = "/"):
    """화면에 뜬 공지를 [확인했습니다] 로 닫는다 — 사람이 누르는 그대로."""
    ids = _ids_on(client, path)
    r = client.post("/notices/seen", data={"notice_id": ids, "back": path},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    return ids


# ═══════════════════════════════════════════════════════════════════════════
# 1. 올리면 닿는다
# ═══════════════════════════════════════════════════════════════════════════

def test_a_notice_reaches_the_team(portal):
    """관리자가 올리면 팀원의 화면에 그대로 뜬다 — 제목도 본문도."""
    _publish(portal["admin"])

    body = portal["u1"].get("/").text
    assert TITLE in body
    assert "대면 · 비대면 둘 중 하나입니다." in body
    # 누가 올린 것인지 모르면 되물을 자리가 없다.
    assert "관리자시험" in body


def test_it_stands_on_every_screen_not_just_one(portal):
    """**화면 이름을 손으로 적지 않는다** — 등록된 화면을 훑는다.

    판을 화면마다 심는 방식이었다면 새 화면이 하나 생길 때 그 화면만 조용히
    아무 말이 없다. 공지는 하필 **그 새 화면이 생겼다**고 알리는 자리라 그게
    특히 나쁘다(`tests/test_mobile_layout.py` 가 화면을 훑는 것과 같은 이유).
    """
    _publish(portal["admin"])

    client = portal["admin"]
    checked = 0
    for route in portal["app"].routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or ()
        if "GET" not in methods or "{" in path:
            continue
        if path.startswith(("/api/", "/static")) or path in ("/logout", "/health", "/login"):
            continue
        resp = client.get(path, follow_redirects=False)
        if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
            continue
        # 밑틀을 쓰는 화면만 센다. FastAPI 가 제 것으로 끼워 넣는 `/docs`
        # 같은 것은 이 앱의 화면이 아니다(사이드바가 없다).
        if 'class="sidebar"' not in resp.text:
            continue
        assert TITLE in resp.text, f"{path} 에 공지가 안 떴습니다"
        checked += 1
    assert checked >= 8, f"훑은 화면이 너무 적습니다({checked}개) — 검사가 헛돕니다"


def test_nothing_is_drawn_when_there_is_no_notice(portal):
    """공지가 없으면 판 자체가 없다. 빈 판이 서면 모든 화면이 그만큼 밀린다."""
    assert "notice-card" not in portal["u1"].get("/").text


# ═══════════════════════════════════════════════════════════════════════════
# 2. 한 번 본 것은 다시 안 뜬다
# ═══════════════════════════════════════════════════════════════════════════

def test_once_confirmed_it_never_comes_back(portal):
    """로그인할 때마다 같은 것이 뜨면 아무도 안 읽는다."""
    _publish(portal["admin"])
    assert _confirm(portal["u1"])

    for path in ("/", "/contacts", "/deals"):
        assert TITLE not in portal["u1"].get(path).text


def test_confirming_is_one_persons_business(portal):
    """한 사람이 닫았다고 남까지 닫히면 그 공지는 아무에게도 안 닿는다."""
    _publish(portal["admin"])
    _confirm(portal["u1"])

    assert TITLE not in portal["u1"].get("/").text
    assert TITLE in portal["u2"].get("/").text


def test_merely_showing_it_does_not_count_as_read(portal, db):
    """**띄운 것만으로는 안 남는다.** 스쳐 지나간 것을 읽은 것으로 세면
    그 공지는 아무도 안 읽은 채로 영영 사라진다."""
    from app.models import NoticeRead

    _publish(portal["admin"])
    for _ in range(3):
        portal["u1"].get("/")

    assert db.query(NoticeRead).count() == 0
    assert TITLE in portal["u1"].get("/").text


def test_pressing_it_twice_does_not_blow_up(portal, db):
    """뒤로가기 한 번이면 일어나는 일이다 — 줄은 그대로 하나다."""
    from app.models import NoticeRead

    _publish(portal["admin"])
    ids = _ids_on(portal["u1"])
    for _ in range(2):
        r = portal["u1"].post("/notices/seen",
                              data={"notice_id": ids, "back": "/"},
                              follow_redirects=False)
        assert r.status_code == 303
    assert db.query(NoticeRead).count() == 1


def test_a_notice_that_arrived_while_the_screen_was_open_is_not_swallowed(portal):
    """화면을 열어 둔 사이에 올라온 공지가 **뜨지도 않고** 읽음이 되면 안 된다.

    그래서 [확인] 은 `지금 켜져 있는 것 전부` 가 아니라 **그때 화면에 실제로
    떠 있던 번호**만 들고 간다.
    """
    _publish(portal["admin"])
    ids = _ids_on(portal["u1"])          # 이 사람이 지금 보고 있는 것

    _publish(portal["admin"], title="이관 메뉴가 접힙니다", body="")

    portal["u1"].post("/notices/seen", data={"notice_id": ids, "back": "/"},
                      follow_redirects=False)
    later = portal["u1"].get("/").text
    assert TITLE not in later
    assert "이관 메뉴가 접힙니다" in later


def test_the_way_back_cannot_leave_the_app(portal):
    """돌아갈 곳이 폼에 실려 온다 — 그대로 믿으면 남의 사이트로 보낼 수 있다."""
    _publish(portal["admin"])
    ids = _ids_on(portal["u1"])
    r = portal["u1"].post("/notices/seen",
                          data={"notice_id": ids, "back": "//example.invalid/x"},
                          follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 끄는 길
# ═══════════════════════════════════════════════════════════════════════════

def test_taking_it_down_stops_it_for_everyone(portal, db):
    """내리면 **아직 확인하지 않은 사람에게도** 그 순간부터 안 뜬다."""
    from app.models import Notice

    _publish(portal["admin"])
    notice = db.query(Notice).one()
    assert TITLE in portal["u1"].get("/").text

    r = portal["admin"].post(f"/team/notices/{notice.id}/off", follow_redirects=False)
    assert r.status_code == 303
    assert TITLE not in portal["u1"].get("/").text
    assert TITLE not in portal["u2"].get("/").text


def test_taking_it_down_keeps_the_line(portal, db):
    """줄은 지우지 않는다 — 지우면 누가 무엇을 언제 알렸는지가 통째로 사라진다."""
    from app.models import Notice

    _publish(portal["admin"])
    notice = db.query(Notice).one()
    portal["admin"].post(f"/team/notices/{notice.id}/off", follow_redirects=False)

    db.expire_all()
    assert db.query(Notice).count() == 1
    assert db.get(Notice, notice.id).is_active == 0
    # 관리자 화면에는 내린 것도 남아 있다.
    assert TITLE in portal["admin"].get("/team").text


def test_putting_it_back_up_does_not_re_ring_people_who_read_it(portal, db):
    """잘못 내린 것을 되돌리는 길이지, 한 번 더 읽히는 길이 아니다."""
    from app.models import Notice

    _publish(portal["admin"])
    notice = db.query(Notice).one()
    _confirm(portal["u1"])

    portal["admin"].post(f"/team/notices/{notice.id}/off", follow_redirects=False)
    portal["admin"].post(f"/team/notices/{notice.id}/on", follow_redirects=False)

    assert TITLE not in portal["u1"].get("/").text     # 이미 읽은 사람
    assert TITLE in portal["u2"].get("/").text         # 아직 안 읽은 사람


def test_a_notice_that_is_down_cannot_be_marked_read(portal, db):
    """내린 공지에 [확인] 이 날아와도 줄이 서지 않는다(열어 둔 화면에서 온다)."""
    from app.models import Notice, NoticeRead

    _publish(portal["admin"])
    notice = db.query(Notice).one()
    ids = _ids_on(portal["u1"])
    portal["admin"].post(f"/team/notices/{notice.id}/off", follow_redirects=False)

    portal["u1"].post("/notices/seen", data={"notice_id": ids, "back": "/"},
                      follow_redirects=False)
    assert db.query(NoticeRead).count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# 4. 누가 적는가
# ═══════════════════════════════════════════════════════════════════════════

def test_only_an_admin_can_publish(portal, db):
    """팀원이 올릴 수 있으면 공지가 아니라 게시판이 된다."""
    from app.models import Notice

    r = portal["u1"].post("/team/notices", data={"title": "아무나", "body": ""},
                          follow_redirects=False)
    assert r.status_code == 403
    assert db.query(Notice).count() == 0


def test_only_an_admin_can_take_one_down(portal, db):
    """내리는 것도 같다 — 팀원이 내리면 나머지 팀이 못 읽는다."""
    from app.models import Notice

    _publish(portal["admin"])
    notice = db.query(Notice).one()

    r = portal["u1"].post(f"/team/notices/{notice.id}/off", follow_redirects=False)
    assert r.status_code == 403
    db.expire_all()
    assert db.get(Notice, notice.id).is_active == 1


def test_an_empty_title_puts_nothing_up(portal, db):
    """제목이 없으면 밑틀에 빈 판이 떠서 모든 화면이 아래로 밀린다."""
    from app.models import Notice

    _publish(portal["admin"], title="   ", body="본문만 있다")
    assert db.query(Notice).count() == 0


def test_the_writing_box_is_on_the_team_screen(portal):
    """손으로 적는 것이면 **적는 화면**이 있어야 한다."""
    body = portal["admin"].get("/team").text
    assert 'action="/team/notices"' in body
    assert 'name="title"' in body


def test_the_team_screen_shows_how_many_read_it(portal, db):
    """올린 사람이 알고 싶은 것은 `떴나` 가 아니라 `읽혔나` 다."""
    from app.services import notices as svc

    _publish(portal["admin"])
    _confirm(portal["u1"])

    db.expire_all()
    row = svc.board(db)[0]
    assert row["seen"] == 1
    assert row["people"] >= 4          # 살아 있는 계정 수가 분모다
    assert "읽음" in portal["admin"].get("/team").text


# ═══════════════════════════════════════════════════════════════════════════
# 5. 투자컨설턴트
# ═══════════════════════════════════════════════════════════════════════════

def test_the_consultant_sees_it_and_can_close_it(portal):
    """판은 밑틀에 서므로 컨설턴트의 화면 위에도 뜬다 — 닫을 길이 없으면
    그 계정에서는 같은 공지가 **영영** 떠 있게 된다."""
    _publish(portal["admin"])

    assert TITLE in portal["consultant"].get("/consulting").text
    _confirm(portal["consultant"], "/consulting")
    assert TITLE not in portal["consultant"].get("/consulting").text


def test_the_consultant_still_cannot_publish(portal, db):
    """열어 준 것은 **자기가 읽었다는 표시** 하나뿐이다."""
    from app.models import Notice

    r = portal["consultant"].post("/team/notices",
                                  data={"title": "아무나", "body": ""},
                                  follow_redirects=False)
    assert r.status_code in (303, 403)     # 미들웨어가 먼저 끊는다
    assert db.query(Notice).count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. 남의 이름이 새지 않는다
# ═══════════════════════════════════════════════════════════════════════════

def test_the_body_never_lands_in_the_edit_log(portal, db):
    """공지 본문에는 사람·기업 이름이 실릴 수 있다 — 로그에 값이 옮겨 가면
    같은 자료가 두 벌이 된다(`edit_log.VALUE_FIELDS` 에 없는 칸이다)."""
    from app.models import EditLog, Notice

    _publish(portal["admin"], title="이름이 없는 제목", body="가나기업 대표님이 바뀌었습니다")
    notice = db.query(Notice).one()
    portal["admin"].post(f"/team/notices/{notice.id}/off", follow_redirects=False)

    dumped = " ".join(x.changes_json for x in db.query(EditLog).all())
    assert "가나기업" not in dumped
    # 바뀐 사실 자체는 남는다 — 내린 것이 로그에 안 남으면 물을 자리가 없다.
    assert any(x.table_name == "notices" for x in db.query(EditLog).all())


def test_closing_a_notice_does_not_fill_the_edit_log(portal, db):
    """사람 수 × 공지 수만큼 쌓이면 로그가 `누가 공지를 닫았다` 로 덮인다."""
    from app.models import EditLog

    _publish(portal["admin"])
    before = db.query(EditLog).count()
    _confirm(portal["u1"])
    _confirm(portal["u2"])

    db.expire_all()
    assert db.query(EditLog).count() == before
