"""**계정을 만들면 그 사람의 탭도 선다** — 그리고 있는 탭은 안 건드린다.

사용자가 든 말 그대로다: "팀 현황에서 팀원이 추가되는 경우에는 그와 동일하게
투자사 관리현황에서 팀원에 해당하는 탭이 자동으로 추가되게끔" · "그외에
개인화된 탭이 필요한 경우에 같이 생성" (스타트업처럼).

여기서 지키는 것이 넷이다.

  ① 계정을 만드는 **세 자리가 같은 함수 하나**를 부른다. 각자 들고 있으면
    그중 하나만 낡는다(`deps.consulting_default_for` 와 같은 이유).
  ② 탭이 **화면에 실제로 선다.** 탭은 원래 줄이 있는 명단만 섰다 — 빈 탭이
    안 뜨면 만들어 줘도 그 사람은 빈 화면을 본다.
  ③ **이미 있는 탭은 안 건드린다**(담당·이름·배치 어느 것도).
  ④ 스타트업 탭은 숨기고 투자사 탭은 안 숨긴다 — **딜 소개 발송 대상**이
    이 값으로 갈린다(`is_hidden` → `is_investor` · `is_deal_list`).

이름은 전부 지어낸 값이다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import SheetOwner, User, VcContact
from app.services import contact_columns as cc
from app.services import sheet_owner

from .conftest import DEMO_PASSWORD


# ═══════════════════════════════════════════════════════════════════════════
# 판정 — 누구에게 어떤 탭인가
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def team(db):
    """관리자 한 명 · 팀원 한 명 · 투자컨설턴트 한 명. 탭은 아직 없다."""
    from app.services import auth as auth_svc

    rows = {}
    for uid, name, phone, role in (
        (301, "가나다", "01077770001", "admin"),
        (302, "라마바", "01077770002", "user"),
        (303, "사아자", "01077770003", "consultant"),
    ):
        rows[role] = User(id=uid, name=name, phone=phone, role=role,
                          password_hash=auth_svc.hash_password(DEMO_PASSWORD),
                          must_change_password=0)
        db.add(rows[role])
    db.commit()
    return rows


def test_팀원과_관리자는_투자사_스타트업_두_탭을_받는다(db, team):
    for role in ("user", "admin"):
        made = sheet_owner.ensure_member_tabs(db, team[role])
        db.commit()
        pages = sorted(cc.page_of(row.layout) for row in made)
        assert pages == [cc.PAGE_CONTACTS, cc.PAGE_STARTUP], \
            f"{role} 이 받은 탭이 두 화면이 아닙니다: {pages}"


def test_투자컨설턴트는_탭을_안_받는다(db, team):
    """그 권한으로는 두 화면을 못 연다(`deps.CONSULTANT_PATHS`).

    만들면 **아무도 못 보는 탭**이 생긴다. 운영에 그런 탭이 이미 있다.
    """
    assert sheet_owner.ensure_member_tabs(db, team["consultant"]) == []
    db.commit()
    assert db.execute(
        select(SheetOwner).where(SheetOwner.user_id == team["consultant"].id)
    ).scalars().first() is None


def test_역할_목록을_따로_들고_있지_않다(db, team):
    """판정은 **화면을 열 수 있는가** 하나다 — 권한 표를 그대로 읽는다.

    권한이 바뀌면 탭 규칙도 같이 움직여야 한다. 컨설턴트를 팀원으로 고치면
    그 순간부터 탭을 받는다.
    """
    from app import deps

    assert sheet_owner.tab_specs(team["consultant"]) == []
    team["consultant"].role = "user"
    db.flush()
    specs = sheet_owner.tab_specs(team["consultant"])
    assert len(specs) == 2
    assert all(deps.can_open(team["consultant"], f"/{s.page}") for s in specs)


# ═══════════════════════════════════════════════════════════════════════════
# 배치와 숨김 — 발송 대상이 여기서 갈린다
# ═══════════════════════════════════════════════════════════════════════════

def test_투자사_탭은_안_숨기고_스타트업_탭은_숨긴다(db, team):
    made = {cc.page_of(row.layout): row
            for row in sheet_owner.ensure_member_tabs(db, team["user"])}
    db.commit()
    assert made[cc.PAGE_CONTACTS].layout == cc.INVESTOR
    assert made[cc.PAGE_CONTACTS].is_hidden == 0, \
        "투자사 탭을 숨기면 그 탭 사람들이 투자사 수와 발송 대상에서 빠집니다"
    assert made[cc.PAGE_STARTUP].layout == cc.STARTUP
    assert made[cc.PAGE_STARTUP].is_hidden == 1, \
        "스타트업 탭을 안 숨기면 그 기업들이 투자사로 세어지고 딜 소개가 나갑니다"


def test_배치를_비워_두지_않는다(db, team):
    """`layout` 이 비면 그 탭은 투자사 명함 표로 서고, 스타트업 화면에서 사라진다."""
    for row in sheet_owner.ensure_member_tabs(db, team["user"]):
        assert row.layout, "배치가 비었습니다 — 탭이 엉뚱한 화면에 섭니다"
        assert row.layout in cc.LAYOUTS


def test_새_탭이_딜_소개_발송_대상을_흔들지_않는다(db, team):
    """줄이 하나도 없는 탭이라 **수가 안 움직인다.**

    새 스타트업 탭은 숨김이라 `is_investor` 가 그 이름만 보면 뺀다. 그런데
    사람이 여러 명단에 겹쳐 있으면 살아 있는 명단 쪽이 이기므로(`is_investor`),
    남의 투자사 줄이 새 탭 때문에 발송에서 빠질 일도 없다.
    """
    db.add(VcContact(user_id=team["user"].id, name="심사역갑", firm="가벤처스",
                     source_sheet="어떤 투자사 풀", connect_stage="connected",
                     status=sheet_owner.STATUS_ACTIVE))
    db.commit()
    before = len(sheet_owner.recipients(db, team["user"]))
    sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    assert len(sheet_owner.recipients(db, team["user"])) == before, \
        "탭만 만들었는데 발송 대상 수가 바뀌었습니다"


# ═══════════════════════════════════════════════════════════════════════════
# 이미 있는 탭 — 안 건드린다
# ═══════════════════════════════════════════════════════════════════════════

def test_두_번_불러도_탭이_늘지_않는다(db, team):
    first = sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    again = sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    assert len(first) == 2 and again == []


def test_그_화면의_탭이_이미_있으면_안_만든다(db, team):
    """이름이 달라도 **화면으로** 센다 — 시트를 올려 만든 탭도 그 사람 탭이다."""
    db.add(SheetOwner(label="투자사 올린표 12명", user_id=team["user"].id,
                      layout=cc.INVESTOR_MONTHLY, is_hidden=0))
    db.commit()
    made = sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    pages = [cc.page_of(row.layout) for row in made]
    assert pages == [cc.PAGE_STARTUP], \
        f"투자사 화면 탭을 이미 가진 사람에게 또 만들었습니다: {pages}"


def test_남의_탭_이름과_겹치면_계정_번호로_가른다(db, team):
    """겹친 이름을 집으면 `ensure` 가 **남의 명단 줄**을 돌려주고, 거기에 배치와
    숨김을 적게 된다 — 그 명단의 줄이 통째로 다른 화면으로 옮겨 간다."""
    other = sheet_owner.ensure_member_tabs(db, team["admin"])
    db.commit()
    taken = next(r for r in other if r.layout == cc.INVESTOR)
    team["user"].name = team["admin"].name        # 동명이인
    db.flush()

    made = sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    labels = {row.label for row in made}
    assert taken.label not in labels, "남의 탭 이름을 집었습니다"
    assert taken.user_id == team["admin"].id, "남의 탭 담당이 넘어갔습니다"
    assert taken.layout == cc.INVESTOR and taken.is_hidden == 0
    assert any(f"({team['user'].id})" in label for label in labels), \
        f"계정 번호로 가르지 않았습니다: {labels}"


def test_이름_짓는_규칙은_가운뎃점_하나다(db, team):
    """새로 만드는 것은 `화면 이름 · 팀원 이름` 한 가지 모양뿐이다.

    옛 이름은 고치지 않는다 — 이름이 곧 열쇠라 네 곳에 박혀 있다.
    """
    from app import ui

    made = sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    for row in made:
        assert sheet_owner.NAME_SEP in row.label, f"이름 규칙이 다릅니다: {row.label}"
        assert row.label.endswith(team["user"].name)
        page = cc.page_of(row.layout)
        # 앞머리는 **화면 이름 한 곳**에서 온다 — 명단 이름을 코드에 적지 않는다.
        assert row.label.startswith(ui.screen_label(f"/{page}")), \
            f"앞머리가 화면 이름이 아닙니다: {row.label}"


def test_이름_앞머리를_코드에_적어_두지_않았다():
    """화면 이름을 고치면 새 탭 이름도 같이 움직여야 한다.

    `tests/test_startup_tab.py` 의 `test_명단_이름이_코드에_박혀_있지_않다` 와
    같은 것을 지킨다 — 이름을 코드가 알면 다음 명단에서 또 적어야 한다.
    """
    import pathlib

    from app import ui

    body = (pathlib.Path(__file__).resolve().parent.parent
            / "app" / "services" / "sheet_owner.py").read_text(encoding="utf-8")
    assert "screen_label" in body
    for page in (cc.PAGE_CONTACTS, cc.PAGE_STARTUP):
        label = ui.screen_label(f"/{page}")
        assert label, f"{page} 화면이 메뉴에 없습니다"
        assert f'"{label}"' not in body, \
            f"화면 이름을 코드에 또 적어 두었습니다: {label}"


# ═══════════════════════════════════════════════════════════════════════════
# 화면 — 빈 탭이 실제로 선다
# ═══════════════════════════════════════════════════════════════════════════

def test_줄이_없는_내_탭도_화면에_선다(db, team):
    """**이게 안 되면 만들어 줘도 그 사람은 빈 화면을 본다.**

    탭은 원래 *지금 보이는 사람들*을 세어 만들었다 — 0줄 명단은 어느 화면에도
    안 떴다(운영에 그런 명단이 셋 있다).
    """
    sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    mine = sheet_owner.tab_owner_ids(db, team["user"], team_wide=False)
    for page in (cc.PAGE_CONTACTS, cc.PAGE_STARTUP):
        tabs = sheet_owner.sheet_rows(db, [], page=page, empty_for=mine)
        assert len(tabs) == 1, f"{page} 에 내 빈 탭이 안 섰습니다: {tabs}"
        assert tabs[0]["count"] == 0 and tabs[0]["hidden_rows"] == 0
        assert tabs[0]["owner_id"] == team["user"].id


def test_남의_빈_탭은_내_화면에_안_선다(db, team):
    sheet_owner.ensure_member_tabs(db, team["admin"])
    db.commit()
    mine = sheet_owner.tab_owner_ids(db, team["user"], team_wide=False)
    tabs = sheet_owner.sheet_rows(db, [], page=cc.PAGE_CONTACTS, empty_for=mine)
    assert tabs == [], f"남의 빈 명단이 내 탭으로 섰습니다: {tabs}"


def test_안_주면_지금까지와_똑같다(db, team):
    """`empty_for` 를 안 주는 자리(내려받기 등)는 동작이 안 바뀌어야 한다."""
    sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    assert sheet_owner.sheet_rows(db, [], page=cc.PAGE_CONTACTS) == []


def test_관리자는_팀_전체의_빈_탭을_본다(db, team):
    sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    ids = sheet_owner.tab_owner_ids(db, team["admin"], team_wide=True)
    tabs = sheet_owner.sheet_rows(db, [], page=cc.PAGE_CONTACTS, empty_for=ids)
    assert [t["owner_id"] for t in tabs] == [team["user"].id]


# ═══════════════════════════════════════════════════════════════════════════
# 계정을 만드는 세 자리 — 같은 한 곳을 부른다
# ═══════════════════════════════════════════════════════════════════════════

def test_팀_현황에서_계정을_만들면_탭이_함께_선다(client, db, team):
    from app.services import auth as auth_svc

    client.post("/login", data={"phone": team["admin"].phone,
                                "password": DEMO_PASSWORD},
                follow_redirects=False)
    r = client.post("/team/members",
                    data={"name": "차카타", "phone": "010-7777-0009",
                          "role": "user"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    db.expire_all()
    member = db.execute(
        select(User).where(User.phone == auth_svc.normalize_phone("01077770009"))
    ).scalars().one()
    rows = db.execute(
        select(SheetOwner).where(SheetOwner.user_id == member.id)
    ).scalars().all()
    assert sorted(cc.page_of(r_.layout) for r_ in rows) == \
        [cc.PAGE_CONTACTS, cc.PAGE_STARTUP], f"탭이 안 섰습니다: {rows}"


def test_권한을_고치면_그때_탭이_선다(client, db, team):
    """컨설턴트로 잘못 만들어진 계정을 고치는 길이다 — 그때까지 탭이 없다."""
    client.post("/login", data={"phone": team["admin"].phone,
                                "password": DEMO_PASSWORD},
                follow_redirects=False)
    r = client.post(f"/team/members/{team['consultant'].id}/role",
                    data={"role": "user"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    db.expire_all()
    rows = db.execute(
        select(SheetOwner).where(SheetOwner.user_id == team["consultant"].id)
    ).scalars().all()
    assert len(rows) == 2, f"권한을 고쳤는데 탭이 안 섰습니다: {rows}"


def test_계정_만드는_세_자리가_한_곳을_부른다():
    """**목록이 셋이면 하나는 반드시 낡는다.** 부르는 자리를 글자로 견준다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    for path in ("app/routers/dashboard.py", "scripts/add_user.py",
                 "scripts/bootstrap.py"):
        body = (root / path).read_text(encoding="utf-8")
        assert "ensure_member_tabs" in body, f"{path} 가 탭을 안 만듭니다"


def test_이름을_바꿔도_탭_이름은_안_따라간다(client, db, team):
    """이름이 곧 열쇠라 네 곳에 박혀 있다 — 물려주는 자리에서 옮기지 않는다.

    판단의 근거는 `routers/dashboard.edit_member_profile` 주석에 있다.
    """
    made = sheet_owner.ensure_member_tabs(db, team["user"])
    db.commit()
    before = sorted(row.label for row in made)

    client.post("/login", data={"phone": team["admin"].phone,
                                "password": DEMO_PASSWORD},
                follow_redirects=False)
    r = client.post(f"/team/members/{team['user'].id}/profile",
                    data={"name": "타파하", "phone": team["user"].phone},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    db.expire_all()
    now = sorted(row.label for row in db.execute(
        select(SheetOwner).where(SheetOwner.user_id == team["user"].id)
    ).scalars().all())
    assert now == before, f"탭 이름이 따라갔습니다: {now}"
