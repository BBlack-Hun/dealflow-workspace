"""스타트업 — 참고 자료를 별도 메뉴로 뺀 것.

투자사 관리 현황의 참고 탭에 성격이 다른 자료가 섞여 있었다. 나머지는
**심사역에게 딜을 보내는** 이야기인데 그것만 **스타트업 대표에게 보내는**
매월 리마인드 안내다. 탭 이름만 보고는 갈리지 않아 열어 읽어 봐야 알 수 있었다.

**옮긴 자료는 하나다.** 처음에 둘을 옮겼는데(0043) `업무 프로세스` 는 스타트업
시트에서 왔다는 것만으로 따라온 것이고, 적힌 내용은 팀이 딜을 돌리는 순서였다
— 0044 가 투자사 관리 현황으로 되돌린다. **자료가 어느 화면에 사는지는 그
자료가 무슨 말을 하는지로 정하지, 어느 시트에서 왔는지로 정하지 않는다.**

명단(사람 데이터)이 이 화면에 서는 것은 `tests/test_startup_list_move.py` 가
따로 본다 — 딸려 오는 것이 많아(명단 소유 · 월별 칸 · 감춤 · 수정 · 필터 ·
엑셀 · 발송 대상) 검사도 그만큼 다르다.

여기서 막는 것은 넷이다.

  1. 메뉴가 있고, 눌러서 열린다
  2. 옮긴 자료가 **새 화면에만** 있다 — 두 곳에 다 뜨면 어느 것이 최신인지 모른다
  3. 권한이 맞다 — 새 화면의 기본값은 **막힘**이다(투자컨설턴트)
  4. 자료가 하나도 없어도 화면이 깨지지 않는다

3번은 **경로를 손으로 적지 않는다.** 목록을 적어 두면 라우터가 하나 늘 때
넣는 것을 잊고, 잊은 것은 열린 채로 나간다 — 이 저장소가 실제로 겪은 일이라
`tests/test_consultant_access.py` 가 앱의 라우트를 통째로 훑는다. 여기서는
**그 전수 검사가 이 새 라우트를 실제로 집었는지**를 확인한다.

자료 제목은 원본 시트의 탭 이름이다. 본문은 옮기지 않는다 — 실제 이름·번호가
들어 있고 이 저장소는 공개다.
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD

MENU_LABEL = "스타트업"
PATH = "/startup"
PAGE = "startup"

GUIDE = "40개사 스타트업 매월 1회 리마인드 카톡 가이드"
# **투자사 관리 현황으로 되돌린 자료.** 0043 이 스타트업 시트에서 왔다는 이유로
# 같이 옮겼는데, 적힌 것은 팀이 딜을 돌리는 순서였다(0044 가 되돌린다).
PROCESS = "업무 프로세스"
# 투자사 쪽에 처음부터 남아 있던 자료 — 옮기면서 같이 끌려가면 안 된다.
VC_SCRIPT = "카톡연결 전화응대 스크립트"


def _ref(db, title, page=PAGE, body="달마다 한 번 안부를 묻는다.",
         kind="text", position=0):
    from app.models import RefSheet

    row = RefSheet(page=page, title=title, kind=kind, position=position,
                   is_active=1,
                   content_json=json.dumps({"body": body}, ensure_ascii=False))
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def moved(client, db, users):
    """옮긴 뒤의 상태 — 새 화면에 남는 자료는 **가이드 하나**다.

    `업무 프로세스` 는 투자사 관리 현황으로 되돌렸다(0044). 스타트업 시트에서
    왔다는 것만으로 옮겼는데 실제로 적힌 것은 팀이 딜을 돌리는 순서라, 그
    화면에서 찾을 자료가 아니었다.
    """
    rows = {
        "guide": _ref(db, GUIDE, position=5),
        "process": _ref(db, PROCESS, page="contacts", position=4),
        "vc": _ref(db, VC_SCRIPT, page="contacts", position=6,
                   body="심사역에게 거는 전화"),
    }
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return rows


# --- 메뉴가 있는가 ----------------------------------------------------------

def test_the_menu_is_there_and_opens(moved, client):
    """좌측 메뉴에 있고, 눌러서 열린다.

    캐치올(`/{placeholder}`)이 먼저 잡으면 `준비 중` 안내만 뜬다 — 등록 순서가
    어긋나면 여기서 걸린다.
    """
    body = client.get("/").text
    assert f'href="{PATH}"' in body
    assert MENU_LABEL in body

    page = client.get(PATH)
    assert page.status_code == 200
    assert "준비 중" not in page.text


def test_the_screen_title_comes_from_the_menu(moved, client):
    """제목과 좌측 메뉴가 어긋나면 같은 화면이 두 이름을 갖는다."""
    from app import ui

    assert ui.screen_label(PATH) == MENU_LABEL
    assert f"<h1>{MENU_LABEL}</h1>" in client.get(PATH).text


# --- 옮긴 자료가 새 화면에만 있는가 -----------------------------------------

def test_the_moved_material_shows_on_the_new_screen(moved, client):
    body = client.get(PATH).text
    assert GUIDE in body
    assert f"ref={moved['guide'].id}" in body
    # 되돌린 자료는 여기 없다.
    assert PROCESS not in body


def test_the_moved_material_is_gone_from_the_old_screen(moved, client):
    """두 곳에 다 뜨면 어느 것이 최신인지 알 수 없다."""
    body = client.get("/contacts").text
    assert GUIDE not in body
    # 옮기지 않은 자료도, 되돌린 자료도 여기 그대로 있어야 한다.
    assert VC_SCRIPT in body
    assert PROCESS in body


def test_the_investor_material_did_not_follow(moved, client):
    body = client.get(PATH).text
    assert VC_SCRIPT not in body


def test_the_material_actually_opens(moved, client):
    """탭을 눌러 자료가 펼쳐지고, 그 자리에서 고칠 수 있다."""
    row = moved["guide"]
    body = client.get(f"{PATH}?ref={row.id}").text
    assert "달마다 한 번 안부를 묻는다." in body
    assert f'action="/ref-sheets/{row.id}/rename"' in body
    assert f'action="/ref-sheets/{row.id}/body"' in body


def test_editing_comes_back_to_the_new_screen(moved, client, db):
    """자료가 붙은 화면으로 돌아와야 한다 — 옛 화면으로 튀면 보던 자리를 잃는다."""
    row = moved["guide"]
    r = client.post(f"/ref-sheets/{row.id}/body", data={"body": "고친 안내문"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith(f"{PATH}?ref={row.id}")
    db.refresh(row)
    assert json.loads(row.content_json)["body"] == "고친 안내문"


def test_hiding_a_tab_comes_back_to_the_new_screen(moved, client, db):
    row = moved["guide"]
    r = client.post(f"/ref-sheets/{row.id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == PATH
    db.refresh(row)
    assert row.is_active == 0
    assert GUIDE not in client.get(PATH).text


# --- 자료가 없을 때 ---------------------------------------------------------

def test_an_empty_screen_does_not_break(client, db, users):
    """명단도 자료도 없는 상태. 빈 화면이 500 이면 고장으로 읽힌다.

    옮기기 전이거나 전부 감췄을 때다. **무엇이 없는지 화면이 말해 준다** —
    빈 표만 뜨면 옮겨 오다 만 것인지 다 감춘 것인지 알 수가 없다.
    """
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.get(PATH)
    assert r.status_code == 200
    assert MENU_LABEL in r.text
    assert "올려 둔 명단이 없습니다" in r.text


def test_an_unknown_ref_number_does_not_break(moved, client):
    """주소에 아무 번호나 적어도 화면은 그대로 열린다."""
    for bad in ("9999", "abc", ""):
        r = client.get(f"{PATH}?ref={bad}")
        assert r.status_code == 200, bad


def test_another_screens_material_cannot_be_opened_here(moved, client):
    """번호만 바꿔 남의 화면 자료를 이 화면에 펼칠 수 없다."""
    body = client.get(f"{PATH}?ref={moved['vc'].id}").text
    assert "심사역에게 거는 전화" not in body


# --- 권한 -------------------------------------------------------------------

@pytest.fixture()
def roles(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    rows = [
        User(id=81, name="컨설턴트시험", phone="01000000081",
             role="consultant", password_hash=pw),
        User(id=82, name="관리자시험", phone="01000000082",
             role="admin", password_hash=pw),
    ]
    db.add_all(rows)
    db.commit()
    return rows


@pytest.fixture()
def portal(db, users, roles):
    """역할별로 따로 로그인한 클라이언트. 한 클라이언트로 갈아타면 쿠키가 덮인다."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        c = TestClient(app)
        assert c.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                      follow_redirects=False).status_code == 303
        return c

    return {
        "consultant": sign_in("01000000081"),
        "admin": sign_in("01000000082"),
        "user": sign_in("01000000001"),
    }


@pytest.mark.parametrize("who", ["user", "admin"])
def test_the_team_and_the_admin_can_open_it(portal, who):
    """팀원도 관리자도 본다 — 이 화면은 팀 전체가 쓰는 안내문이다."""
    r = portal[who].get(PATH)
    assert r.status_code == 200
    assert f'href="{PATH}"' in r.text


def test_a_consultant_is_sent_back_to_their_own_screen(portal):
    """새 화면의 기본값은 **막힘**이다 — 컨설턴트는 자기 화면 하나만 쓴다."""
    r = portal["consultant"].get(PATH, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/consulting"


def test_a_consultant_does_not_see_the_menu(portal):
    """메뉴와 라우터가 같은 목록을 본다 — 하나만 걸러 두면 다시 어긋난다."""
    assert f'href="{PATH}"' not in portal["consultant"].get("/consulting").text


def test_a_consultant_cannot_touch_the_material(portal, db, moved):
    """참고 자료 주소는 화면 셋이 같이 쓴다 — 번호만 바꿔 건드릴 수 없다."""
    row = moved["guide"]
    client = portal["consultant"]
    assert client.post(f"/ref-sheets/{row.id}/rename",
                       data={"title": "가로채기"}).status_code == 403
    assert client.post(f"/ref-sheets/{row.id}/delete").status_code == 403
    db.refresh(row)
    assert row.title == GUIDE and row.is_active == 1


def test_the_route_sweep_actually_covers_the_new_screen():
    """전수 검사가 이 라우트를 **집었는지** 확인한다.

    `tests/test_consultant_access.py` 는 앱에 등록된 라우트를 통째로 훑어
    허용 목록 밖을 전부 막는다. 그 검사가 도는 것만으로는 새 화면이 실제로
    그 그물에 걸렸는지 알 수 없다 — 라우트가 등록조차 안 됐어도 통과하기
    때문이다(그때는 캐치올이 조용히 `준비 중` 을 그린다).
    """
    from app import deps
    from app.main import create_app

    from .test_consultant_access import _routes

    paths = {path for _, path in _routes(create_app())}
    assert PATH in paths, "새 화면이 앱에 등록되지 않았다 — 캐치올이 대신 잡는다"
    assert not deps.consultant_may_open(PATH)


def test_the_menu_and_the_router_read_the_same_list():
    """좌측 메뉴가 라우터와 다른 판정을 들면 보이는데 안 열리거나 그 반대가 된다."""
    from app import deps, ui
    from app.models import User

    item = next(m for m in ui.MENU if m["href"] == PATH)
    for role in ("user", "admin"):
        assert ui.can_see(User(role=role), item) is True, role
    assert ui.can_see(User(role="consultant"), item) is False
    assert not deps.consultant_may_open(PATH)


# --- 옮기는 마이그레이션 ----------------------------------------------------

def _migration(name: str):
    import importlib.util
    from pathlib import Path

    path = (Path(__file__).resolve().parent.parent
            / "alembic" / "versions" / f"{name}.py")
    spec = importlib.util.spec_from_file_location(name.replace(".", "_"), path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


def test_the_migration_titles_match_the_screen():
    """마이그레이션이 찾는 이름과 화면이 다루는 자료가 같은가.

    옮긴 것(0043)에서 되돌린 것(0044)을 빼면 **지금 새 화면에 있는 자료**다.
    이름을 두 곳에 따로 적어 두면 하나만 고쳐지는 날, 마이그레이션은 옮기는데
    화면은 다른 것을 보여 준다.
    """
    from app.routers import startup as startup_router

    moved_mig = _migration("0043_startup_ref_page")
    back_mig = _migration("0044_process_ref_back")

    assert set(moved_mig.TITLES) - set(back_mig.TITLES) == {GUIDE}
    assert set(back_mig.TITLES) == {PROCESS}
    # 자료가 붙는 값과 주소 조각이 같아야 한다 — 고칠 권한이 `/{page}` 로 판정한다.
    assert (moved_mig.STARTUP == back_mig.STARTUP
            == startup_router.PAGE == PATH.lstrip("/"))


def test_the_revert_can_run_twice():
    """운영 DB 에 실데이터가 있다 — **두 번 돌려도 죽지 않아야** 한다.

    컨테이너는 기동할 때마다 마이그레이션을 돌린다. 두 번째 실행에서 걸리는
    줄이 0이어야 하고, 그때 다른 자료를 건드려서도 안 된다.
    """
    from sqlalchemy import create_engine, text

    back = _migration("0044_process_ref_back")
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE ref_sheets (id INTEGER PRIMARY KEY, "
                          "page TEXT, title TEXT)"))
        conn.execute(text("INSERT INTO ref_sheets (id, page, title) VALUES "
                          "(1, 'startup', :p), (2, 'startup', :g), "
                          "(3, 'contacts', :v)"),
                     {"p": PROCESS, "g": GUIDE, "v": VC_SCRIPT})

    def pages():
        with engine.begin() as conn:
            return dict(conn.execute(text("SELECT title, page FROM ref_sheets")).all())

    # 마이그레이션 본문을 그대로 흉내 낸다 — `op` 없이 같은 조건으로 돈다.
    def run_upgrade():
        with engine.begin() as conn:
            return conn.execute(
                text("UPDATE ref_sheets SET page = :to "
                     "WHERE page = :frm AND title IN (:t)"),
                {"to": back.CONTACTS, "frm": back.STARTUP, "t": back.TITLES[0]},
            ).rowcount

    assert run_upgrade() == 1
    first = pages()
    assert first[PROCESS] == "contacts"
    assert first[GUIDE] == "startup", "되돌리면서 가이드까지 끌고 갔습니다"

    # 두 번째 — 걸리는 줄이 없고 아무것도 안 바뀐다.
    assert run_upgrade() == 0
    assert pages() == first
