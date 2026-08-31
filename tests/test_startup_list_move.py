"""명단(사람 데이터)을 스타트업 화면으로 옮긴 것.

자료만 옮겼던 것과 다르다(`tests/test_ref_menu.py`). **명단은 딸려 오는 것이
많다** — 명단 소유(담당자별 보기) · 달마다 늘어나는 칸 · 줄 단위 감춤 · 인라인
수정 · 수정창 · 필터 · 엑셀 내려받기 · 발송 대상 판정. 하나라도 빠지면 **화면은
뜨는데 고칠 수가 없거나, 수가 어긋난다.**

여기서 막는 것은 다섯이다.

  1. 명단이 **새 화면에만** 있다 — 두 곳에 다 뜨면 어느 쪽이 최신인지 모른다
  2. 딸려 오는 것이 **새 화면에서 다 된다**
  3. 투자사 집계·발송 대상이 **한 명도 안 바뀐다** — 옮기는 것과 세는 것은 다른 값이다
  4. 무엇을 옮길지 **이름으로 정하지 않는다** — 명단에 붙은 배치가 정한다
  5. `계약여부` 가 이메일 바로 뒤에 서고, 보기 네 가지가 그대로다

이름·회사·번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

# 원본 시트가 그렇듯 이름에 괄호와 숫자가 붙는다. 담당이 다른 명단이 여럿이다 —
# **코드가 이 이름들을 알면 안 된다**(`test_startup_tab.py` 가 그것을 지킨다).
STARTUP_LISTS = ["샘플 스타트업(9)", "샘플 스타트업", "샘플 스타트업(40)"]
VC_LIST = "샘플 투자사 20"


def _pages():
    from app.services import contact_columns as cc

    return {"startup": f"/{cc.page_of(cc.STARTUP)}",
            "contacts": f"/{cc.page_of(cc.INVESTOR)}"}


def _thead(html: str) -> list:
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    cells = re.findall(r"<th\b[^>]*>(.*?)</th>", m.group(1), re.S)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells]


@pytest.fixture()
def lists(client, db, users):
    """스타트업 명단 셋(담당이 다르다) + 투자사 명단 하나.

    담당을 갈라 두는 이유는 **명단 소유가 따라오는지** 보기 위해서다. 셋 다 한
    사람 것이면 담당이 안 따라와도 화면이 똑같아 보인다.
    """
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    u1, u2 = users["u1"], users["u2"]
    owners = [u1.id, u2.id, None]
    for label, owner in zip(STARTUP_LISTS, owners):
        db.add(SheetOwner(label=label, user_id=owner, layout=cc.STARTUP,
                          is_hidden=1))
    db.add(SheetOwner(label=VC_LIST, user_id=u1.id, layout=cc.INVESTOR,
                      is_hidden=0))
    # 달마다 늘어나는 칸은 **명단마다** 따로 선다.
    for label in STARTUP_LISTS:
        db.add(ContactColumn(sheet=label, label=f"{_month()}월 리마인드 문자",
                             position=0))
    db.flush()

    for idx, label in enumerate(STARTUP_LISTS):
        col = cc.month_columns(db, label)[0]
        for i in range(1, 3):
            db.add(VcContact(
                user_id=u1.id, source_sheet=label, name=f"김대표{idx}{i}",
                firm=f"샘플기업{idx}{i}", phone=f"010000003{idx}{i}",
                email=f"founder{idx}{i}@example.com",
                # 마지막 명단의 둘째 줄만 감춘다 — 감춤이 따라오는지 본다.
                is_hidden=1 if (idx == 2 and i == 2) else 0,
                notes=cc.dump_notes({"contract": "미계약",
                                     cc.note_key(col.id): "O"})))
    for i in range(1, 3):
        db.add(VcContact(user_id=u1.id, source_sheet=VC_LIST,
                         name=f"박심사{i}", firm=f"샘플벤처스{i}",
                         connect_stage="connected", channel_kakao=1,
                         kakao_room_name=f"박심사{i} 방"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _month() -> int:
    from app import clock

    return clock.today().month


@pytest.fixture()
def admin(db, users):
    """관리자로 로그인한 별도 클라이언트.

    한 클라이언트로 갈아타면 쿠키가 덮여 앞의 로그인이 사라진다.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=91, name="관리자시험", phone="01000000091", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    c = TestClient(create_app())
    c.post("/login", data={"phone": "01000000091", "password": DEMO_PASSWORD})
    return c


# ── 1. 한 곳에만 있다 ───────────────────────────────────────────────────────

def test_명단은_새_화면에만_뜬다(lists):
    """두 곳에 다 뜨면 **어느 쪽이 최신인지 알 수 없다.**

    탭이 남아 있으면 거기서도 고치게 되는데, 같은 줄을 두 화면에서 고친 뒤에는
    무엇이 마지막인지 화면 어디에도 안 적힌다.
    """
    startup = lists.get(_pages()["startup"]).text
    contacts = lists.get(_pages()["contacts"] + "?sheet=all").text

    for label in STARTUP_LISTS:
        assert label in startup, f"새 화면에 `{label}` 탭이 없습니다"
        assert label not in contacts, f"투자사 관리 현황에 `{label}` 탭이 남았습니다"

    # 투자사 명단은 반대다 — 옮기면서 같이 끌려가면 안 된다.
    assert VC_LIST in contacts
    assert VC_LIST not in startup


def test_옛_주소로_들어와도_남의_화면에_안_뜬다(lists, db):
    """**북마크와 옛 링크가 남는다.**

    `/contacts?sheet=<스타트업 명단>` 은 옮기기 전 주소다. 주소에 적힌 이름을
    그대로 믿으면 그 명단이 투자사 화면에 다시 서고, 두 곳에서 고칠 수 있게
    된다 — 옮긴 뜻이 없어진다. 반대 방향도 같다.
    """
    from app.models import VcContact

    startup_names = {c.name for c in db.query(VcContact).filter(
        VcContact.source_sheet == STARTUP_LISTS[0]).all()}
    vc_names = {c.name for c in db.query(VcContact).filter(
        VcContact.source_sheet == VC_LIST).all()}

    old = lists.get(f"{_pages()['contacts']}?sheet={quote(STARTUP_LISTS[0])}").text
    for name in startup_names:
        assert name not in old, "옛 주소로 스타트업 명단이 투자사 화면에 떴습니다"

    crossed = lists.get(f"{_pages()['startup']}?sheet={quote(VC_LIST)}").text
    for name in vc_names:
        assert name not in crossed, "투자사 명단이 스타트업 화면에 떴습니다"


def test_투자사_명단_사람은_새_화면에_안_보인다(lists, db):
    """섞이면 거기서 고친 값이 **어느 명단 것인지** 알 수 없다."""
    from app.models import VcContact

    startup = lists.get(_pages()["startup"]).text
    for c in db.query(VcContact).filter(VcContact.source_sheet == VC_LIST).all():
        assert c.name not in startup


# ── 2. 딸려 오는 것들 ───────────────────────────────────────────────────────

def test_명단_소유가_따라온다(lists, admin, db, users):
    """담당이 안 따라오면 **누구 명단인지 화면에서 사라진다.**

    관리자에게는 담당을 바꾸는 자리까지 있어야 한다 — 그 자리가 옛 화면에만
    남으면 담당을 옮기려고 없는 탭을 찾게 된다.
    """
    body = lists.get(_pages()["startup"] + f"?sheet={quote(STARTUP_LISTS[0])}").text
    assert f"담당 {users['u1'].name}" in body, "탭에 담당이 안 적혀 있습니다"

    page = admin.get(_pages()["startup"] + f"?sheet={quote(STARTUP_LISTS[0])}").text
    assert 'action="/api/contacts/sheets/assign"' in page, "담당 지정 자리가 없습니다"
    # 관리자는 담당이 갈린 명단 셋을 다 본다.
    for label in STARTUP_LISTS:
        assert label in page


def test_월별_칸을_새_화면에서_세우고_고치고_지운다(lists, db):
    """달마다 세 칸씩 붙는 표다. 그 조작이 옛 화면으로 튀면 **고친 것이 사라진
    것처럼** 보인다 — 거기엔 그 탭이 없어 빈 표가 뜬다.
    """
    from app.models import ContactColumn

    home, label = _pages()["startup"], STARTUP_LISTS[0]
    url = f"{home}?sheet={quote(label)}"

    r = lists.post("/api/contacts/columns",
                   data={"sheet": label, "label": f"{_month()}월 카톡 연결"},
                   follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith(home), (
        f"칸을 세운 뒤 남의 화면으로 갔습니다: {r.headers['location']}")
    assert f"{_month()}월 카톡 연결" in _thead(lists.get(url).text)

    col = db.query(ContactColumn).filter(
        ContactColumn.sheet == label,
        ContactColumn.label == f"{_month()}월 카톡 연결").one()
    for path in (f"/api/contacts/columns/{col.id}/rename",
                 f"/api/contacts/columns/{col.id}/delete"):
        r = lists.post(path, data={"label": f"{_month()}월 카톡"},
                       follow_redirects=False)
        assert r.headers["location"].startswith(home), path


def test_감춘_줄과_되돌리는_자리가_따라온다(lists, db):
    """그냥 안 보이면 **지워진 줄 안다.** 몇 줄을 감췄는지와 되돌릴 길이 있어야 한다."""
    from app.models import VcContact

    home, label = _pages()["startup"], STARTUP_LISTS[2]
    hidden = db.query(VcContact).filter(VcContact.source_sheet == label,
                                        VcContact.is_hidden == 1).one()

    body = lists.get(f"{home}?sheet={quote(label)}").text
    assert hidden.name not in body
    assert "감춘 줄" in body and "함께 보기" in body

    both = lists.get(f"{home}?sheet={quote(label)}&hidden=1").text
    assert hidden.name in both, "[함께 보기] 로도 감춘 줄이 안 나옵니다"


def test_필터와_인라인_수정이_새_화면에서_붙는다(lists):
    """필터 꼬리표(`data-filters`)와 바로 고치기(`data-inline-url`)가 있어야 한다.

    표만 그려 놓고 이 표시가 없으면 **보이는데 고칠 수가 없다.**
    """
    body = lists.get(_pages()["startup"] + f"?sheet={quote(STARTUP_LISTS[0])}").text
    assert 'data-inline-url="/api/contacts"' in body
    assert 'data-filters="contract:계약여부"' in body
    assert "data-f-contract=" in body
    # 표에서 뺀 칸까지 수정창에 선다 — 값은 있는데 볼 자리가 없으면 안 된다.
    assert 'data-note="one_liner"' in body


def test_새_화면에서_고친_값이_저장되고_되읽힌다(lists, db):
    """PATCH 는 200 인데 아무것도 안 들어가는 부류를 막는다.

    한 칸만 고쳐 보내도 **그 달의 기록이 살아 있어야** 한다 — 통째로 덮으면
    이번 달 `O` 를 찍는 순간 지난 기록이 사라진다.
    """
    from app.models import VcContact
    from app.services import contact_columns as cc

    label = STARTUP_LISTS[0]
    month_key = cc.note_key(cc.month_columns(db, label)[0].id)
    row = db.query(VcContact).filter(VcContact.source_sheet == label).first()

    res = lists.patch(f"/api/contacts/{row.id}",
                      json={"notes": {"contract": "유료계약완료"}})
    assert res.status_code == 200, res.text
    got = lists.get(f"/api/contacts/{row.id}").json()["contact"]["notes"]
    assert got["contract"] == "유료계약완료"
    assert got.get(month_key) == "O", "한 칸을 고쳤더니 그 달 기록이 사라졌습니다"


def test_엑셀이_이_명단의_칸으로_나온다(lists):
    """투자사 표 한 장으로만 내보내면 **매달 채우는 칸이 한 칸도 안 나온다.**

    받는 사람은 열어 보고 나서야 다른 것을 받았다는 걸 안다.
    """
    from app.services import spreadsheet as sp

    label = STARTUP_LISTS[0]
    res = lists.get(f"/api/export/contacts.xlsx?sheet={quote(label)}")
    assert res.status_code == 200
    rows = sp.read_rows("x.xlsx", res.content, None)
    head = [str(c or "") for c in rows[0]]
    for want in ("기업명", "성함", "이메일", "계약여부", f"{_month()}월 리마인드 문자"):
        assert want in head, f"엑셀에 `{want}` 칸이 없습니다: {head}"
    # 투자사 명함 칸이 딸려 오면 빈 칸만 스무 개다.
    assert "근무처 팩스" not in head

    # 없는 명단은 빈 파일을 주지 않는다 — 받는 쪽은 줄이 없는 것으로 읽는다.
    assert lists.get("/api/export/contacts.xlsx?sheet=없는명단").status_code == 404


# ── 3. 투자사 집계·발송 대상은 안 바뀐다 ────────────────────────────────────

def test_옮겨도_투자사_수와_발송_대상이_그대로다(lists, db, users):
    """**옮기는 것과 세는 것은 다른 값이 정한다.**

    화면(`Layout.page`)을 옮겨도 투자사로 세는지(`is_hidden`)·딜소개를 보내는지
    (`is_deal_list`)는 그대로여야 한다. 여기가 흔들리면 회차가 통째로 어긋난다.
    """
    from app.services import sheet_owner

    u1 = users["u1"]
    # 투자사로 세는 사람 = 투자사 명단 둘뿐. 스타트업 여섯 줄은 안 센다.
    assert len(sheet_owner.managed(db, u1)) == 2
    assert {c.source_sheet for c in sheet_owner.managed(db, u1)} == {VC_LIST}
    # 발송 대상도 마찬가지다.
    assert all(c.source_sheet == VC_LIST for c in sheet_owner.recipients(db, u1))
    assert sheet_owner.recipient_counts(db, u1)["managed"] == 2

    for label in STARTUP_LISTS:
        assert label in sheet_owner.hidden_labels(db)
        assert label in sheet_owner.off_deal_labels(db)


def test_새_화면_사람은_딜_제안_관리에_안_뜬다(lists, db):
    """목록에 없는 것만으로 모자라다 — **보내기 직전에도** 막혀야 한다."""
    from app.models import User, VcContact
    from app.routers.deals import _load_recipients

    rows = db.query(VcContact).filter(
        VcContact.source_sheet.in_(STARTUP_LISTS)).all()
    html = lists.get("/deals").text
    for c in rows:
        assert c.name not in html

    picked = _load_recipients(db, db.get(User, 1), "kakao", [c.id for c in rows])
    assert picked == [], "목록에는 없는데 보내기는 됩니다 — 오발송으로 이어집니다"


def test_새_화면에는_투자사_조작이_없다(lists):
    """딜소개 깔때기·방 연결 확인·명함 업로드는 투자사 이야기다.

    여기 사람은 딜을 받는 쪽이 아니라 우리가 챙기는 쪽이라, 세워 두면 눌러도
    아무 일이 없거나 엉뚱한 칸이 든 줄이 생긴다.
    """
    body = lists.get(_pages()["startup"]).text
    for what in ('id="verify-btn"', 'id="import-btn"', 'id="add-btn"',
                 'class="funnel"'):
        assert what not in body, f"스타트업 화면에 투자사 조작(`{what}`)이 있습니다"
    # 투자사 화면에서는 그대로 있어야 한다 — 감추다 같이 지우면 안 된다.
    vc = lists.get(_pages()["contacts"]).text
    for what in ('id="verify-btn"', 'id="import-btn"', 'id="add-btn"',
                 'class="funnel"'):
        assert what in vc, f"투자사 화면에서 `{what}` 이 사라졌습니다"


# ── 4. 이름으로 정하지 않는다 ───────────────────────────────────────────────

def test_배치를_바꾸면_명단이_화면을_옮긴다(lists, db):
    """**무엇을 옮길지는 명단에 붙은 값이 정한다.**

    이름으로 갈랐다면 이 검사가 통과할 수 없다 — 이름은 그대로 두고 배치만
    바꾼다. 다음 명단이 들어와도 코드를 고칠 일이 없다는 뜻이다.
    """
    from app.models import SheetOwner
    from app.services import contact_columns as cc

    label = STARTUP_LISTS[0]
    row = db.query(SheetOwner).filter(SheetOwner.label == label).one()
    row.layout = cc.INVESTOR
    db.commit()

    assert label not in lists.get(_pages()["startup"]).text
    assert label in lists.get(_pages()["contacts"] + "?sheet=all").text


def test_화면을_정하는_판정은_한_곳뿐이다():
    """두 화면이 각자 "내 명단은 이런 것" 을 들면 **양쪽에 다 뜨거나 어디에도 안 뜬다.**"""
    import inspect

    from app.routers import pages, startup
    from app.services import contact_columns, sheet_owner

    assert "def page_of" in inspect.getsource(contact_columns)
    assert "def page_of" in inspect.getsource(sheet_owner)
    # 두 화면이 **같은 함수**로 그린다 — 표를 새로 짜면 딸려 오는 것이 두 벌 된다.
    assert "list_page" in inspect.getsource(startup)
    body = inspect.getsource(pages)
    assert body.count("def list_page") == 1


# ── 5. 계약여부 ─────────────────────────────────────────────────────────────

def test_계약여부가_이메일_바로_뒤에_선다(lists):
    """월별 칸 뒤에 두면 달이 쌓일수록 표 끝으로 밀린다 — 가로로 밀어야 닿는다."""
    head = _thead(lists.get(
        _pages()["startup"] + f"?sheet={quote(STARTUP_LISTS[0])}").text)
    assert head.index("계약여부") == head.index("이메일") + 1, head
    # 월별 칸보다 앞이다.
    assert head.index("계약여부") < head.index(f"{_month()}월 리마인드 문자")


def test_계약여부_보기가_네_가지다(lists, db):
    """골라서 저장되고 되읽혀야 한다. 새로 타이핑하면 표기가 갈려 세는 것이 달라진다."""
    from app.models import VcContact
    from app.services import contact_columns as cc

    want = ["유료계약완료", "무료계약완료", "계약검토중", "미계약"]
    column = next(c for c in cc.STARTUP_LAYOUT.head if c.key == "contract")
    assert column.choices.split(",") == want
    assert column.kind == "pick"

    body = lists.get(_pages()["startup"] + f"?sheet={quote(STARTUP_LISTS[0])}").text
    assert f'data-choices="{column.choices}"' in body

    row = db.query(VcContact).filter(
        VcContact.source_sheet == STARTUP_LISTS[0]).first()
    for value in want:
        assert lists.patch(f"/api/contacts/{row.id}",
                           json={"notes": {"contract": value}}).status_code == 200
        got = lists.get(f"/api/contacts/{row.id}").json()["contact"]["notes"]
        assert got["contract"] == value, f"`{value}` 가 되읽기에서 빠졌습니다"


# ── 메뉴 이름 ───────────────────────────────────────────────────────────────

def test_메뉴_이름은_한_곳에서_나온다(lists):
    """화면 제목·권한 안내가 전부 이 목록에서 나온다 — 두 곳에 적으면 하나가 낡는다."""
    from app import ui

    assert ui.screen_label("/companies") == "IR 기업 현황"
    assert ui.menu_label("su") == "IR 기업 현황"
    body = lists.get("/companies").text
    assert "<h1>IR 기업 현황</h1>" in body
    # 붙여 쓰던 옛 이름이 화면에 남아 있으면 같은 화면이 두 이름을 갖는다.
    assert "IR 기업현황" not in body


def test_옛_이름이_화면에_남아_있지_않다(lists, admin):
    """메뉴에서 부르는 이름과 다른 화면이 가리키는 이름이 같아야 한다."""
    for path in ("/", "/deals", "/companies", "/team", "/followups"):
        assert "IR 기업현황" not in admin.get(path).text, path
