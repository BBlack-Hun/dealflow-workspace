"""스타트업 화면에서 줄(기업)을 **새로 넣는 길**.

사용자가 든 말은 한 줄이다 — "스타트업 메뉴에서는 데이터 추가가 안됨".

## 왜 안 됐나

단추가 `{% if page.investors %}` 안에 있었다(`templates/contacts.html` 의
도구 막대). 그 자리에 적혀 있던 이유는 **맞는 이유였다** —

    [담당자 추가] 가 만드는 줄도 투자사 명함이다.
    스타트업 화면에 세우면 눌러서 엉뚱한 칸이 든 줄이 생긴다.

만드는 길(`routers/contacts.py` 의 `create_contact`)이 실제로 투자사 전용
이었다. 이름(`name`)을 반드시 받고, 명단 이름을 안 적고(`source_sheet` 가
비어 `직접 추가` 로 밀린다), 회사명이 있으면 **카톡방 이름까지 지었다.**
그대로 세웠다면 성함을 모르는 기업 줄은 못 넣고, 넣은 줄은 어느 탭에도 안
뜨며, 아무도 연결한 적 없는 방 이름이 붙어 발송 대상에 섰을 것이다.

그래서 이유를 지운 것이 아니라 **없앴다** — 만드는 길이 명단에 따라 움직이게
고치고 나서 단추를 꺼냈다.

## 여기서 잠그는 것

  1. 스타트업 화면에서 줄을 더할 수 있다
  2. **지금 보고 있는 명단**에 들어간다 — 다른 탭으로 안 샌다
  3. 담당·명단이 채워져 더한 줄이 **바로 그 화면에 보인다**
  4. 필수 칸이 비면 안 들어간다 — 그 칸이 무엇인지는 **명단이 정한다**
  5. 권한 없는 계정은 못 더한다 — **서버가 막는다**(단추만 감추지 않는다)
  6. 투자사 관리 현황이 안 깨진다 — 이름 필수·카톡방 이름·`전체` 탭 그대로
  7. 남의 명단에 더한 것은 수정 로그에 남는다

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

# 원본 시트가 그렇듯 이름에 괄호와 숫자가 붙는다. **코드가 이 이름들을 알면
# 안 된다** — 어느 명단이 어느 화면에 사는지는 배치가 정한다.
MINE = "샘플 스타트업(9)"        # u1 담당
MINE_B = "샘플 스타트업(12)"     # u1 담당 — 같은 화면의 **다른 탭**
YOURS = "샘플 스타트업(40)"      # u2 담당
POOL = "샘플 스타트업 풀"        # 담당 없음
VC = "샘플 투자사 20"            # u1 담당, 투자사 명함 배치


def _pages() -> dict:
    """주소를 여기 적어 두지 않는다 — 명단의 배치가 화면을 정한다."""
    from app.services import contact_columns as cc

    return {"startup": f"/{cc.page_of(cc.STARTUP)}",
            "contacts": f"/{cc.page_of(cc.INVESTOR)}"}


def _url(sheet: str) -> str:
    from app.services import contact_columns as cc
    from app.services import sheet_owner

    # 그 명단이 사는 화면으로 간다. 못 박아 두면 명단이 화면을 옮겼을 때
    # 검사만 옛 화면을 계속 보고, 새 화면이 비어 있어도 통과한다.
    page = cc.page_of({MINE: cc.STARTUP, MINE_B: cc.STARTUP, YOURS: cc.STARTUP,
                       POOL: cc.STARTUP, VC: cc.INVESTOR}[sheet])
    assert sheet_owner is not None
    return f"/{page}?sheet={quote(sheet)}"


@pytest.fixture()
def people(db, users):
    """관리자 한 명 더. conftest 의 두 계정은 둘 다 일반 팀원이다."""
    from app.models import User
    from app.services import auth as auth_svc

    admin = User(id=81, name="관리자시험", phone="01090000001", role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.commit()
    return admin


@pytest.fixture()
def stage(client, db, users, people):
    """담당이 다른 스타트업 명단 셋 + 투자사 명단 하나.

    담당을 갈라 두어야 **명단의 주인이 담당이 되는지**가 드러난다. 셋 다 한
    사람 것이면 넣는 사람을 담당으로 적어도 화면이 똑같아 보인다.
    """
    from app.models import SheetOwner
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    db.add_all([
        SheetOwner(label=MINE, user_id=u1.id, layout=cc.STARTUP, is_hidden=1),
        SheetOwner(label=MINE_B, user_id=u1.id, layout=cc.STARTUP, is_hidden=1),
        SheetOwner(label=YOURS, user_id=u2.id, layout=cc.STARTUP, is_hidden=1),
        SheetOwner(label=POOL, user_id=None, layout=cc.STARTUP, is_hidden=1),
        SheetOwner(label=VC, user_id=u1.id, layout=cc.INVESTOR, is_hidden=0),
    ])
    db.commit()
    return db


def _sign_in(client, phone: str):
    r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                    follow_redirects=False)
    assert r.status_code == 303
    return client


@pytest.fixture()
def me(client, stage):
    """u1 — `MINE` 의 주인."""
    return _sign_in(client, "01000000001")


def _seed_row(db, sheet: str, user_id: int, firm: str):
    """그 명단에 줄 하나. 탭은 **줄이 있는 명단**만 선다(`sheet_rows`)."""
    from app.models import VcContact

    db.add(VcContact(user_id=user_id, source_sheet=sheet, name="", firm=firm))
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 더할 수 있다 — 그리고 단추 이름이 그 화면의 말이다
# ═══════════════════════════════════════════════════════════════════════════

def test_스타트업_화면에_줄을_더하는_단추가_선다(me, db, users):
    """사용자가 든 말 그대로 — **여기서 데이터 추가가 되어야 한다.**

    단추 이름도 그 화면의 말이어야 한다. 이 명단의 주인공은 사람이 아니라
    기업이라(`ListPage.row_label`), `담당자 추가` 가 서 있으면 누구를 넣는
    자리인지 잘못 읽는다.
    """
    _seed_row(db, MINE, users["u1"].id, "샘플기업1")
    body = me.get(_url(MINE)).text
    assert 'id="add-btn"' in body, "스타트업 화면에 줄을 더할 자리가 없습니다"
    assert "기업 추가" in body
    assert "담당자 추가" not in body.split('id="add-btn"')[1][:40]


def test_투자사_화면의_단추는_그대로다(me, db, users):
    """옮기다 남의 화면을 깨면 안 된다 — 거기 말은 지금까지 그대로 `담당자` 다."""
    _seed_row(db, VC, users["u1"].id, "샘플벤처스1")
    body = me.get(_url(VC)).text
    assert 'id="add-btn"' in body
    assert "담당자 추가" in body


# ═══════════════════════════════════════════════════════════════════════════
# 2. 지금 보고 있는 명단에 들어간다
# ═══════════════════════════════════════════════════════════════════════════

def test_더한_줄이_지금_보던_명단에_들어가고_그_화면에_보인다(me, db, users):
    """**명단을 안 적으면 어느 탭에도 안 뜬다.**

    탭은 `source_sheet` 로 갈린다(`routers/pages.py` 의 `list_page`). 예전
    길은 그 칸을 아예 안 적어서 새 줄이 `직접 추가` 로 밀렸고, `전체` 탭이
    있는 투자사 화면에서만 겨우 보였다 — 그 탭이 없는 스타트업 화면에서는
    넣어 놓고도 안 들어간 줄 안다.

    담당도 함께 본다. 명단의 주인이 담당이어야 그 사람 화면에 뜬다
    (`sheet_owner.managed` 가 `user_id` 로 좁힌다).
    """
    from app.models import VcContact

    # **두 탭 다 내 것이어야** 새는지를 볼 수 있다. 남의 탭을 주소로 열면
    # 내 명단으로 떨어져(`list_page`), 안 샌 것인지 탭이 안 열린 것인지 모른다.
    _seed_row(db, MINE, users["u1"].id, "샘플기업1")
    _seed_row(db, MINE_B, users["u1"].id, "샘플기업2")

    r = me.post("/api/contacts",
                json={"firm": "새로넣은기업", "name": "김대표", "sheet": MINE})
    assert r.status_code == 200, r.text

    db.expire_all()
    row = db.query(VcContact).filter(VcContact.firm == "새로넣은기업").one()
    assert row.source_sheet == MINE
    assert row.user_id == users["u1"].id

    # 그 화면에 **바로 보인다.**
    assert "새로넣은기업" in me.get(_url(MINE)).text
    # 다른 탭으로 안 샌다.
    assert "새로넣은기업" not in me.get(_url(MINE_B)).text


def test_스타트업_줄에는_카톡방_이름이_안_지어진다(me, db, users):
    """방 이름은 **딜소개를 보낼 방**이다 — 기업 줄에는 지을 것이 없다.

    지으면 두 가지가 한꺼번에 어긋난다. 방 제목 규칙이 `이름·직함·투자사` 라
    기업명이 심사역 자리에 박히고(`services/room_name.py`), 방 이름이 서면
    연결 상태가 `연결 완료` 로 따라 서서(`_assign`) 아무도 연결한 적 없는
    줄이 발송 대상에 뜬다.
    """
    from app.models import VcContact

    r = me.post("/api/contacts", json={"firm": "방없는기업", "sheet": MINE})
    assert r.status_code == 200, r.text
    assert not r.json()["kakao_room_name"]

    db.expire_all()
    row = db.query(VcContact).filter(VcContact.firm == "방없는기업").one()
    assert not (row.kakao_room_name or "")
    # 방이 없으니 연결 상태도 그대로 미착수다.
    assert row.connect_stage == "not_started"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 필수 칸 — **무엇이 필수인지는 명단이 정한다**
# ═══════════════════════════════════════════════════════════════════════════

def test_기업명이_비면_안_들어간다(me, db):
    """이 명단에서 줄 하나를 알아보는 이름은 **기업명**이다(`Layout.required`).

    성함은 비어 있는 줄이 흔하다 — 담당자를 아직 모르는 기업이 그렇다.
    성함만 받고 기업명을 안 받으면 표에 이름 없는 줄이 서서, 어느 기업인지
    알 수도 없고 지울 때 확인창이 무엇을 지우는지 말해 주지도 못한다.
    """
    from app.models import VcContact

    before = db.query(VcContact).count()
    r = me.post("/api/contacts", json={"name": "김대표", "sheet": MINE})
    assert r.status_code == 400, r.text
    assert "기업명" in r.json()["detail"]
    db.expire_all()
    assert db.query(VcContact).count() == before, "막았다면서 줄이 생겼습니다"


def test_성함은_비어도_들어간다(me, db):
    """담당자를 아직 모르는 기업도 명단에 서야 한다."""
    from app.models import VcContact

    r = me.post("/api/contacts", json={"firm": "성함모르는기업", "sheet": MINE})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(VcContact).filter(
        VcContact.firm == "성함모르는기업").one().name == ""


def test_투자사_명단은_이름이_필수다(me, db):
    """같은 길인데 **명단이 다르면 필수 칸도 다르다.** 여기는 사람이 주인공이다."""
    from app.models import VcContact

    before = db.query(VcContact).count()
    r = me.post("/api/contacts", json={"firm": "샘플벤처스9", "sheet": VC})
    assert r.status_code == 400, r.text
    assert "담당자명" in r.json()["detail"]
    db.expire_all()
    assert db.query(VcContact).count() == before


def test_필수_칸의_이름은_표_머리글과_같은_말이다():
    """안내에 뜨는 말과 표 머리글이 갈리면 **어느 칸을 채우라는 건지 모른다.**

    두 곳에 적어 두면 한쪽만 고쳐지는 날 표는 `기업명`, 안내는 `회사명` 이
    된다 — 그래서 말은 배치가 준 목록 하나에서 나온다.
    """
    from app.services import contact_columns as cc

    layout = cc.layout_of(cc.STARTUP)
    head = {c.key: c.label for c in layout.head if c.source == "field"}
    assert layout.required in head, "필수 칸이 이 표에 서 있지 않습니다"
    assert layout.required_label == head[layout.required]


# ═══════════════════════════════════════════════════════════════════════════
# 4. 권한 — **서버가 막는다**
# ═══════════════════════════════════════════════════════════════════════════

def test_남의_명단에는_못_넣는다(client, stage, db, users):
    """단추를 감추는 것만으로는 모자라다 — 주소를 직접 두드려도 막혀야 한다.

    남의 명단에 줄이 끼면 그 팀원의 화면과 발송 대상이 조용히 늘어난다.
    """
    from app.models import VcContact

    you = _sign_in(client, "01000000002")   # u2 — `MINE` 의 주인이 아니다
    before = db.query(VcContact).count()
    r = you.post("/api/contacts", json={"firm": "몰래넣은기업", "sheet": MINE})
    assert r.status_code == 403, r.text
    db.expire_all()
    assert db.query(VcContact).count() == before


def test_못_넣는_명단에서는_단추가_아예_안_선다(client, stage, db, users):
    """**눌러도 아무 일이 없는 단추가 더 나쁘다.**

    화면과 서버가 같은 판정 하나를 읽는지 본다(`sheet_owner.may_add_row`).
    """
    # 남의 명단 탭이 **내 화면에 뜨는** 자리를 만든다 — 내 담당 줄 하나가 그
    # 명단에 올라 있으면 탭이 선다(`sheet_owner.sheet_rows`). 탭은 뜨는데
    # 명단의 주인은 남이다.
    _seed_row(db, MINE, users["u1"].id, "샘플기업1")
    _seed_row(db, MINE, users["u2"].id, "겹친기업")
    you = _sign_in(client, "01000000002")
    body = you.get(_url(MINE)).text
    assert "겹친기업" in body, "그 탭이 안 열렸습니다 — 단추만 안 선 것이 아닙니다"
    assert 'id="add-btn"' not in body


def test_담당이_없는_명단에는_관리자만_넣는다(client, stage, db, users):
    """투자사 풀은 누구의 담당도 아니다.

    거기 새 줄을 세우면 그 줄의 담당을 아무도 정한 적이 없는 상태가 된다 —
    그런 줄은 어느 팀원의 화면에도 안 뜬다(`managed` 가 `user_id` 로 좁힌다).
    """
    from app.models import VcContact

    me_ = _sign_in(client, "01000000001")
    r = me_.post("/api/contacts", json={"firm": "풀에넣은기업", "sheet": POOL})
    assert r.status_code == 403, r.text

    admin = _sign_in(client, "01090000001")
    r = admin.post("/api/contacts", json={"firm": "풀에넣은기업", "sheet": POOL})
    assert r.status_code == 200, r.text
    db.expire_all()
    row = db.query(VcContact).filter(VcContact.firm == "풀에넣은기업").one()
    # 주인이 없는 명단이라 넣은 사람이 담당이다 — 담당 없는 줄을 만들지 않는다.
    assert row.user_id == 81


def test_투자컨설턴트는_아예_못_부른다(client, db, users):
    """컨설턴트는 자기 화면 하나만 쓴다 — 판정은 미들웨어 한 곳이다."""
    from app.models import User, VcContact
    from app.services import auth as auth_svc

    db.add(User(id=83, name="컨설턴트시험", phone="01090000003", role="consultant",
                can_view_consulting=1,
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    before = db.query(VcContact).count()

    who = _sign_in(client, "01090000003")
    r = who.post("/api/contacts", json={"firm": "컨설턴트기업", "sheet": MINE},
                 headers={"Accept": "application/json"})
    assert r.status_code == 403, r.text
    db.expire_all()
    assert db.query(VcContact).count() == before


# ═══════════════════════════════════════════════════════════════════════════
# 5. 투자사 관리 현황이 안 깨진다
# ═══════════════════════════════════════════════════════════════════════════

def test_명단을_안_고르면_지금까지_그대로다(me, db, users):
    """투자사 `전체` 탭에서 넣는 길은 **한 글자도 안 바뀌어야 한다.**

    거기서 넣은 줄은 예전처럼 `직접 추가` 로 가고(그것은 언제나 넣은 사람
    본인의 것이다), 회사명이 있으면 카톡방 이름이 지어진다.
    """
    from app.models import VcContact

    r = me.post("/api/contacts", json={"name": "박심사", "title": "심사역",
                                       "firm": "샘플벤처스7"})
    assert r.status_code == 200, r.text
    assert r.json()["kakao_room_name"], "투자사 줄인데 카톡방 이름이 안 지어졌습니다"

    db.expire_all()
    row = db.query(VcContact).filter(VcContact.name == "박심사").one()
    assert not row.source_sheet          # = `직접 추가`
    assert row.user_id == users["u1"].id


def test_투자사_명단_탭에_넣으면_그_탭에_선다(me, db, users):
    """`전체` 만이 아니라 **탭을 골라서도** 넣을 수 있어야 한다 — 두 화면이 같다."""
    from app.models import VcContact

    _seed_row(db, VC, users["u1"].id, "샘플벤처스1")
    r = me.post("/api/contacts",
                json={"name": "최심사", "firm": "샘플벤처스8", "sheet": VC})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(VcContact).filter(
        VcContact.name == "최심사").one().source_sheet == VC
    assert "최심사" in me.get(_url(VC)).text


# ═══════════════════════════════════════════════════════════════════════════
# 6. 수정 로그
# ═══════════════════════════════════════════════════════════════════════════

def test_남의_명단에_더한_것은_수정_로그에_남는다(client, stage, db, users):
    """남의 명단이 늘어나는 일은 **물을 자리가 있어야 한다.**

    이 명단은 곧 발송 대상이라, 모르는 줄이 끼어 있으면 그대로 오발송이다.

    남기는 자리를 새로 붙이지 않았다 — 세션 이벤트 한 곳이 ORM 으로 들어가는
    INSERT 를 전부 지난다(`services/edit_log.py`). 여기서 보는 것은 **그 자리를
    실제로 지나는가**와, 그때 담당이 명단의 주인으로 적히는가다(주인이 넣은
    사람으로 적히면 범위가 `내 것` 이 되어 아무 것도 안 남는다).
    """
    import json

    from app.models import EditLog, VcContact
    from app.services import edit_log

    admin = _sign_in(client, "01090000001")
    r = admin.post("/api/contacts", json={"firm": "관리자가넣은기업", "sheet": MINE})
    assert r.status_code == 200, r.text

    db.expire_all()
    row = db.query(VcContact).filter(VcContact.firm == "관리자가넣은기업").one()
    # 담당은 **명단의 주인**이다 — 안 그러면 그 팀원 화면에 안 뜬다.
    assert row.user_id == users["u1"].id

    logs = [x for x in db.query(EditLog).order_by(EditLog.id).all()
            if x.table_name == "vc_contacts"]
    assert len(logs) == 1, "남의 명단에 줄을 더했는데 로그가 없습니다"
    log = logs[0]
    assert log.action == edit_log.ACTION_CREATE
    assert log.scope == edit_log.SCOPE_OTHERS
    assert log.actor_user_id == 81
    assert log.target_user_id == users["u1"].id
    assert log.row_label == "관리자가넣은기업"
    # 어느 명단에 들어갔는지가 로그에 실려야 되짚을 수 있다.
    changed = {c["field"]: c.get("after") for c in json.loads(log.changes_json)}
    assert changed.get("source_sheet") == MINE


def test_내_명단에_더한_것은_안_남는다(me, db):
    """자기 것만 고친 것은 안 남긴다 — 하루에 수백 줄이 쌓이면 아무도 안 본다.

    그 규칙은 그대로다(`edit_log._row_scope`). 여기서 새 예외를 만들지 않았다는
    것을 잠근다.
    """
    from app.models import EditLog

    r = me.post("/api/contacts", json={"firm": "내가넣은기업", "sheet": MINE})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert [x for x in db.query(EditLog).all()
            if x.table_name == "vc_contacts"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 7. 이름으로 정하지 않는다
# ═══════════════════════════════════════════════════════════════════════════

def test_배치를_바꾸면_필수_칸도_따라_바뀐다(me, db):
    """**명단 이름이 코드에 박혀 있지 않다는 것**을 잰다.

    이름은 그대로 두고 배치만 바꾼다. 이름으로 갈랐다면 필수 칸이 안 따라온다.
    """
    from app.models import SheetOwner
    from app.services import contact_columns as cc

    row = db.query(SheetOwner).filter(SheetOwner.label == MINE).one()
    row.layout = cc.INVESTOR
    db.commit()

    r = me.post("/api/contacts", json={"firm": "배치바꾼기업", "sheet": MINE})
    assert r.status_code == 400, r.text
    assert "담당자명" in r.json()["detail"]
