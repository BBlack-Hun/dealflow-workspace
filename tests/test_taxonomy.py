"""분야 기준 목록(#2) — 정규화 · 처음 값 · 이름 바꾸기/합치기/옮기기 전파 · 관리자 전용.

기업·사람 이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.conftest import DEMO_PASSWORD


# ── 고정물 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def seeded(db):
    from app.services import taxonomy as tx

    assert tx.ensure_seed(db) is True
    return db


@pytest.fixture()
def admin(client, db, users):
    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def member(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _term(db, name):
    from sqlalchemy import select

    from app.models import SectorTerm
    from app.services import taxonomy as tx

    for row in db.execute(select(SectorTerm)).scalars():
        if tx.norm(row.name) == tx.norm(name):
            return row
    raise AssertionError(f"목록에 없다: {name}")


def _company(db, name, major, minor, one_liner=None):
    from app.models import IrCompany

    row = IrCompany(name=name, sector_major=major, sector_minor=minor,
                    one_liner=one_liner)
    db.add(row)
    db.commit()
    return row


def _contact(db, users, name, sectors, firm="가상벤처스", **kw):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name=name, firm=firm, sectors=sectors, **kw)
    db.add(row)
    db.commit()
    return row


# ── 1. 같은 말인지 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("a, b", [
    ("AI·SaaS·데이터", "AI · SaaS · 데이터"),
    ("AI·SaaS·데이터", "ai saas 데이터"),
    ("AI·SaaS·데이터", "AIㆍSaaSㆍ데이터"),
    ("AI·SaaS·데이터", "AI•SaaS•데이터"),
    ("건물관리 SaaS", "건물관리saas"),
    ("DID·인증", "did 인증"),
])
def test_가운뎃점_공백_대소문자는_안_본다(a, b):
    from app.services import taxonomy as tx

    assert tx.norm(a) == tx.norm(b)


def test_다른_말은_다르다():
    from app.services import taxonomy as tx

    assert tx.norm("반도체") != tx.norm("반도체 소재")
    assert tx.norm("AI SaaS") != tx.norm("AI·SaaS·데이터")


def test_소분류_칸은_쉼표와_빗금으로_가르고_가운뎃점은_이름_안이다():
    from app.services import taxonomy as tx

    assert tx.split_minor("생성형AI / AI SaaS, 업무자동화") == ["생성형AI", "AI SaaS", "업무자동화"]
    assert tx.split_minor("DID·인증") == ["DID·인증"]
    assert tx.split_minor("") == []


# ── 2. 처음 값 ──────────────────────────────────────────────────────────────

def test_처음_값은_사용자가_정한_표_그대로다(seeded):
    from app.services import taxonomy as tx

    tree = tx.tree(seeded)
    assert [m["name"] for m in tree] == [name for name, _ in tx.SEED]
    deep = next(m for m in tree if m["name"] == "딥테크·제조")
    assert "배터리" in [x["name"] for x in deep["minors"]]
    assert "첨단소재" in [x["name"] for x in deep["minors"]]
    commerce = next(m for m in tree if m["name"] == "커머스·라이프스타일")
    assert "뷰티테크" in [x["name"] for x in commerce["minors"]]


def test_처음_값은_비어_있을_때만_넣는다(seeded):
    from sqlalchemy import func, select

    from app.models import SectorTerm
    from app.services import taxonomy as tx

    count = seeded.execute(select(func.count(SectorTerm.id))).scalar()
    assert tx.ensure_seed(seeded) is False
    assert seeded.execute(select(func.count(SectorTerm.id))).scalar() == count


def test_옛_이름은_숨긴_채_기준_이름으로_합쳐져_있다(seeded):
    from app.services import taxonomy as tx

    resolver = tx.Resolver.load(seeded)
    assert resolver.minor("신약개").name == "신약개발"
    assert resolver.minor("비추얼휴먼").name == "버추얼휴먼"
    assert resolver.minor("건물 빌딩 관리").name == "건물관리 SaaS"
    assert resolver.major("뷰티").name == "커머스·라이프스타일"
    assert resolver.major("물류").name == "모빌리티·물류"
    # 고르는 목록에는 안 선다.
    names = {m["name"] for m in tx.picker_tree(seeded)}
    assert "뷰티" not in names and "물류" not in names
    minors = {x for m in tx.picker_tree(seeded) for x in m["minors"]}
    assert "신약개" not in minors


def test_철자만_다른_이름도_기준_이름으로_돌아온다(seeded):
    from app.services import taxonomy as tx

    resolver = tx.Resolver.load(seeded)
    assert resolver.major("AI SaaS 데이터").name == "AI·SaaS·데이터"
    assert resolver.minor("ai saas").name == "AI SaaS"
    assert resolver.parent_of(resolver.minor("배터리")).name == "딥테크·제조"


# ── 3. 이름 바꾸기 — 값도 같이 바뀐다 ───────────────────────────────────────

def test_소분류_이름을_바꾸면_IR_값과_투자사_값이_같이_바뀐다(seeded, users):
    from app.services import taxonomy as tx

    a = _company(seeded, "가상기업A", "딥테크·제조", "로봇, 반도체")
    b = _company(seeded, "가상기업B", "딥테크·제조", "센서")
    c1 = _contact(seeded, users, "가나다", "로봇, AI·SaaS·데이터")
    c2 = _contact(seeded, users, "라마바", "6/17 로봇 위주로 보심")   # 아직 자유 글

    term = _term(seeded, "로봇")
    _row, _name, edits = tx.plan_rename(seeded, term.id, "로보틱스")
    assert tx.impact(edits) == {"ir": 1, "vc": 1}
    # 미리보기는 쓰지 않는다.
    seeded.refresh(a)
    assert a.sector_minor == "로봇, 반도체"

    tx.rename(seeded, term.id, "로보틱스")
    seeded.commit()
    for row in (a, b, c1, c2):
        seeded.refresh(row)
    assert a.sector_minor == "로보틱스, 반도체"
    assert a.sector_minor_raw == "로봇, 반도체"       # 원래 값
    assert b.sector_minor == "센서" and b.sector_minor_raw is None
    assert c1.sectors == "로보틱스, AI·SaaS·데이터"
    assert c1.sectors_raw == "로봇, AI·SaaS·데이터"
    # 낱말이 통째로 같을 때만 — 자유 글은 그대로다.
    assert c2.sectors == "6/17 로봇 위주로 보심" and c2.sectors_raw is None
    assert _term(seeded, "로보틱스").id == term.id


def test_대분류_이름을_바꾸면_IR_대분류와_투자사_값이_바뀐다(seeded, users):
    from app.services import taxonomy as tx

    a = _company(seeded, "가상기업A", "AI SaaS 데이터", "업무자동화")   # 철자만 다름
    c = _contact(seeded, users, "가나다", "AI·SaaS·데이터")
    tx.rename(seeded, _term(seeded, "AI·SaaS·데이터").id, "AI·데이터")
    seeded.commit()
    seeded.refresh(a)
    seeded.refresh(c)
    assert a.sector_major == "AI·데이터"
    assert c.sectors == "AI·데이터"


def test_대분류_이름을_바꿔도_낱말_사전이_그_분야를_찾고_되돌릴_수_있다(seeded):
    """낱말 사전(`sector_words`)은 코드에 적힌 처음 이름으로 대분류를 찾는다. 옛 이름이
    숨긴 채 합친 줄로 남아야 이름을 바꾼 뒤에도 그 분야 낱말이 걸린다."""
    from app.services import sector_words
    from app.services import taxonomy as tx

    def majors(text):
        return {h.major for h in sector_words.find(text, tx.Resolver.load(seeded))}

    row = _term(seeded, "AI·SaaS·데이터")
    tx.rename(seeded, row.id, "AI·데이터")
    seeded.commit()
    assert majors("클라우드 기반 소프트웨어") == {"AI·데이터"}
    old = [t for t in tx.all_terms(seeded) if t.name == "AI·SaaS·데이터"]
    assert [(t.is_hidden, t.merged_into_id) for t in old] == [(1, row.id)]

    # 원래 이름으로 되돌리는 것은 그 옛 이름에 막히지 않는다
    tx.rename(seeded, row.id, "AI·SaaS·데이터")
    seeded.commit()
    assert majors("클라우드 기반 소프트웨어") == {"AI·SaaS·데이터"}


def test_백업은_처음_한_번만_적는다(seeded, users):
    from app.services import taxonomy as tx

    a = _company(seeded, "가상기업A", "딥테크·제조", "로봇")
    tx.rename(seeded, _term(seeded, "로봇").id, "로보틱스")
    seeded.commit()
    tx.rename(seeded, _term(seeded, "로보틱스").id, "로봇 공학")
    seeded.commit()
    seeded.refresh(a)
    assert a.sector_minor == "로봇 공학"
    assert a.sector_minor_raw == "로봇", "두 번째 판이 원래 값을 덮었다"


@pytest.mark.parametrize("name, why", [
    ("", "이름을 적어"),
    ("반도체", "같은 이름"),
    ("반 도 체", "같은 이름"),           # 띄어쓰기만 다른 것도 같은 이름
    ("신약개", "숨긴 줄"),               # 숨긴 옛 이름과 겹친다
    ("광학, 센서", "쉼표"),
])
def test_못_쓰는_이름은_막는다(seeded, name, why):
    from app.services import taxonomy as tx

    with pytest.raises(tx.TaxonomyError) as err:
        tx.plan_rename(seeded, _term(seeded, "로봇").id, name)
    assert why in str(err.value)


# ── 4. 합치기 ───────────────────────────────────────────────────────────────

def test_소분류를_다른_대분류의_소분류로_합치면_기업의_대분류도_따라간다(seeded, users):
    from app.services import taxonomy as tx

    # 지어낸 상황: `대체식품` 을 `푸드테크` 로 합치는 것은 같은 대분류라 대분류가
    # 안 바뀌고, `라스트마일` 을 `스마트물류` 로 — 같은 대분류. 다른 대분류끼리를
    # 보려고 `디지털치료제`(헬스케어) 를 `AI SaaS`(AI) 로 합쳐 본다.
    a = _company(seeded, "가상기업A", "헬스케어·바이오", "디지털치료제")
    b = _company(seeded, "가상기업B", "헬스케어·바이오", "디지털치료제, 의료기기")
    c = _contact(seeded, users, "가나다", "디지털치료제, AI SaaS")

    source, target = _term(seeded, "디지털치료제"), _term(seeded, "AI SaaS")
    result = tx.merge(seeded, source.id, target.id)
    seeded.commit()
    assert result["ir"] == 2 and result["vc"] == 1
    for row in (a, b, c, source):
        seeded.refresh(row)
    assert (a.sector_major, a.sector_minor) == ("AI·SaaS·데이터", "AI SaaS")
    # 다른 소분류(의료기기)가 옛 대분류를 붙들고 있으면 대분류는 그대로다.
    assert (b.sector_major, b.sector_minor) == ("헬스케어·바이오", "AI SaaS, 의료기기")
    assert c.sectors == "AI SaaS", "합친 뒤 같은 말이 두 번 남았다"
    assert source.is_hidden == 1 and source.merged_into_id == target.id
    # 합친 이름은 옛 이름으로 남아 정리할 때 화살표를 따라간다.
    assert tx.Resolver.load(seeded).minor("디지털치료제").name == "AI SaaS"


def test_같은_이름의_소분류는_다른_대분류에도_못_더한다(seeded):
    from app.services import taxonomy as tx

    with pytest.raises(tx.TaxonomyError):
        tx.add(seeded, "로봇", _term(seeded, "AI·SaaS·데이터").id)


def test_대분류끼리_합친다(seeded, users):
    from app.services import taxonomy as tx

    source = tx.add(seeded, "도시기술")
    moved = tx.add(seeded, "도시 데이터", source.id)
    seeded.commit()
    a = _company(seeded, "가상기업A", "도시기술", "도시 데이터")
    c = _contact(seeded, users, "가나다", "도시기술, 로봇")
    target = _term(seeded, "프롭테크·스마트시티")
    tx.merge(seeded, source.id, target.id)
    seeded.commit()
    for row in (a, c, moved, source):
        seeded.refresh(row)
    assert a.sector_major == "프롭테크·스마트시티"
    assert a.sector_minor == "도시 데이터"
    assert c.sectors == "프롭테크·스마트시티, 로봇"
    assert moved.parent_id == target.id
    assert source.merged_into_id == target.id and source.is_hidden == 1


def test_단계가_다르면_못_합친다(seeded):
    from app.services import taxonomy as tx

    with pytest.raises(tx.TaxonomyError):
        tx.plan_merge(seeded, _term(seeded, "로봇").id, _term(seeded, "딥테크·제조").id)


# ── 5. 옮기기 · 숨기기 · 순서 ───────────────────────────────────────────────

def test_소분류를_옮기면_옛_대분류에_서_있던_기업만_따라간다(seeded):
    from app.services import taxonomy as tx

    a = _company(seeded, "가상기업A", "모빌리티·물류", "자율주행")
    b = _company(seeded, "가상기업B", "모빌리티·물류", "자율주행, EV충전")
    c = _company(seeded, "가상기업C", "AI·SaaS·데이터", "자율주행")   # 이미 다른 대분류
    term = _term(seeded, "자율주행")
    target = _term(seeded, "딥테크·제조")
    _row, _parent, edits = tx.plan_move(seeded, term.id, target.id)
    assert tx.impact(edits) == {"ir": 1, "vc": 0}
    tx.move(seeded, term.id, target.id)
    seeded.commit()
    for row in (a, b, c, term):
        seeded.refresh(row)
    assert a.sector_major == "딥테크·제조"
    assert b.sector_major == "모빌리티·물류", "EV충전 이 옛 대분류를 붙들고 있다"
    assert c.sector_major == "AI·SaaS·데이터"
    assert term.parent_id == target.id


def test_숨기면_고르는_목록에서만_빠지고_값은_그대로다(seeded, users):
    from app.services import taxonomy as tx

    c = _contact(seeded, users, "가나다", "로봇")
    term = _term(seeded, "로봇")
    tx.set_hidden(seeded, term.id, True)
    seeded.commit()
    seeded.refresh(c)
    assert c.sectors == "로봇"
    minors = {x for m in tx.picker_tree(seeded) for x in m["minors"]}
    assert "로봇" not in minors
    admin_tree = tx.tree(seeded, include_hidden=True)
    assert any(x["name"] == "로봇" and x["hidden"]
               for m in admin_tree for x in m["minors"])
    tx.set_hidden(seeded, term.id, False)
    seeded.commit()
    assert "로봇" in {x for m in tx.picker_tree(seeded) for x in m["minors"]}


def test_숨긴_줄로는_합치거나_옮기거나_더하지_못한다(seeded):
    from app.services import taxonomy as tx

    hidden_minor, hidden_major = _term(seeded, "반도체"), _term(seeded, "핀테크·블록체인")
    tx.set_hidden(seeded, hidden_minor.id, True)
    tx.set_hidden(seeded, hidden_major.id, True)
    seeded.commit()
    with pytest.raises(tx.TaxonomyError):
        tx.plan_merge(seeded, _term(seeded, "로봇").id, hidden_minor.id)
    with pytest.raises(tx.TaxonomyError):
        tx.plan_move(seeded, _term(seeded, "로봇").id, hidden_major.id)
    with pytest.raises(tx.TaxonomyError):
        tx.add(seeded, "가상소분류", hidden_major.id)


def test_합쳐진_이름은_다시_보이게_못_한다(seeded):
    from app.services import taxonomy as tx

    with pytest.raises(tx.TaxonomyError):
        tx.set_hidden(seeded, _term(seeded, "신약개").id, False)


def test_순서를_바꾼다(seeded):
    from app.services import taxonomy as tx

    second = tx.picker_tree(seeded)[1]["name"]
    tx.reorder(seeded, _term(seeded, second).id, -1)
    seeded.commit()
    assert tx.picker_tree(seeded)[0]["name"] == second


# ── 6. 화면 · 권한 ─────────────────────────────────────────────────────────

def test_팀원은_분야_기준_목록에_못_들어간다(member, db):
    page = member.get("/taxonomy")
    assert "대분류 → 소분류" not in page.text
    for method, url, body in (
        ("post", "/api/taxonomy/terms", {"name": "가상분야"}),
        ("post", "/api/taxonomy/terms/1/rename", {"name": "가상"}),
        ("post", "/api/taxonomy/terms/1/preview/rename", {"name": "가상"}),
        ("get", "/api/taxonomy/ir-cleanup", None),
        ("post", "/api/taxonomy/ir-cleanup", {"items": [{"id": 1}]}),
    ):
        r = getattr(member, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (method, url, r.status_code)


def test_좌측_메뉴는_관리자에게만(users):
    from app.ui import visible_menu

    users["u1"].role = "user"
    assert "/taxonomy" not in {m["href"] for m in visible_menu(users["u1"])}
    users["u1"].role = "admin"
    assert "/taxonomy" in {m["href"] for m in visible_menu(users["u1"])}


def test_관리자_화면은_목록을_그린다(admin):
    import html
    import json
    import re

    page = admin.get("/taxonomy")
    assert page.status_code == 200
    found = re.search(r"id=\"tx-tree\" data-tree='([^']*)'", page.text)
    assert found, "목록을 실은 자리가 없다"
    tree = json.loads(html.unescape(found.group(1)))
    assert "딥테크·제조" in [m["name"] for m in tree]
    # 관리자 화면에는 숨긴 옛 이름도 실린다(`→ 합친 곳` 으로 보인다).
    assert any(x["merged_into"] == "신약개발" for m in tree for x in m["minors"])
    assert admin.get("/taxonomy?tab=ir").status_code == 200


def test_선호분야_재분류_탭은_없다(admin):
    """10/18 에 한 번 반영했다. 다시 돌리면 원치 않는 데이터 이동이 생긴 적이 있어
    탭도 길도 뺐다 — 관리자도 다시 누를 수 없어야 한다."""
    page = admin.get("/taxonomy").text
    assert "tab=pref" not in page and "투자사 선호분야 재분류" not in page
    for method, body in (("get", None), ("post", {"all": True})):
        r = getattr(admin, method)("/api/taxonomy/pref-sectors",
                                   **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (method, r.status_code)
    # 옛 주소로 와도 오류 없이 기본 탭(기준 목록)이 뜬다.
    old = admin.get("/taxonomy?tab=pref")
    assert old.status_code == 200
    assert 'id="tx-tree"' in old.text and "pref-preview" not in old.text


def test_미리보기는_수만_세고_반영은_한_번에_한다(admin, db, users):
    from app.models import IrCompany, SectorTerm, VcContact

    admin.get("/taxonomy")    # 처음 값이 선다
    _company(db, "가상기업A", "딥테크·제조", "로봇")
    _contact(db, users, "가나다", "로봇")
    term_id = _term(db, "로봇").id

    preview = admin.post(f"/api/taxonomy/terms/{term_id}/preview/rename",
                         json={"name": "로보틱스"}).json()
    assert (preview["ir"], preview["vc"]) == (1, 1)
    db.expire_all()
    assert db.get(SectorTerm, term_id).name == "로봇"

    done = admin.post(f"/api/taxonomy/terms/{term_id}/rename", json={"name": "로보틱스"})
    assert done.status_code == 200, done.text
    assert (done.json()["ir"], done.json()["vc"]) == (1, 1)
    db.expire_all()
    assert db.get(SectorTerm, term_id).name == "로보틱스"
    company = db.query(IrCompany).filter_by(name="가상기업A").one()
    contact = db.query(VcContact).filter_by(name="가나다").one()
    assert company.sector_minor == "로보틱스" and contact.sectors == "로보틱스"


def test_반영이_실패하면_아무것도_안_바뀐다(admin, db, users):
    from app.models import IrCompany

    admin.get("/taxonomy")
    _company(db, "가상기업A", "딥테크·제조", "로봇")
    r = admin.post(f"/api/taxonomy/terms/{_term(db, '로봇').id}/rename",
                   json={"name": "반도체"})          # 이미 있는 이름
    assert r.status_code == 400
    db.expire_all()
    assert db.query(IrCompany).filter_by(name="가상기업A").one().sector_minor == "로봇"


def test_수정_로그에_목록_고침이_남는다(admin, db):
    from app.models import EditLog

    admin.get("/taxonomy")
    admin.post("/api/taxonomy/terms", json={"name": "가상분야"})
    rows = db.query(EditLog).all()
    assert any(r.table_name == "sector_terms" for r in rows)


# ── 7. 고르는 부품(브라우저) ───────────────────────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_선호_투자분야는_목록에서_여러_개_고르고_옛_값은_안_지운다():
    """표 칸을 눌러 고르는 일은 브라우저 코드를 그대로 돌려 본다
    (`tests/js/sector_picker_test.js` — `node` 로 혼자도 돈다)."""
    script = Path(__file__).resolve().parent / "js" / "sector_picker_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


def test_투자사_화면은_고를_목록과_부품을_싣는다(member, db, users):
    import html
    import json
    import re

    from app.models import VcContact

    db.add(VcContact(user_id=users["u1"].id, name="가나다", firm="가상벤처스",
                     sectors="로봇"))
    db.commit()
    page = member.get("/contacts?sheet=all").text
    found = re.search(r"id=\"sector-taxonomy\" hidden data-tree='([^']*)'", page)
    assert found, "고를 목록이 화면에 없다"
    tree = json.loads(html.unescape(found.group(1)))
    assert [m["name"] for m in tree][:2] == ["AI·SaaS·데이터", "헬스케어·바이오"]
    assert page.index("js/sector_picker.js") < page.index("js/inline_edit.js")
    assert 'data-field="sectors" data-type="sectors"' in page
    assert 'id="f-sectors" data-sector-picker' in page
