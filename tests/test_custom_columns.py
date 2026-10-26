"""표에 붙이는 추가 칸 — 개선 과제 #6 · #7 · #8 · #12 · #46.

10/16 · 10/18 사용자 결정:

  · 형식은 **메모(글)** · **O/X** 둘. 팀원은 표에서 값만 적는다.
  · 칸 추가 · 이름 변경 · 숨김은 관리자 메뉴 `컬럼 관리` 에서만. 삭제는 없다(숨김).
  · IR 기업 현황은 탭 셋(기업현황 · 스타트업DB · Series A)이 **같은 칸**을 쓴다.
  · 투자컨설턴트의 [월 열 추가](달 칸)는 그대로 두고, 새 칸은 일반 칸으로만 붙인다.
  · 딜 소싱 · 스타트업 · 매출예상리스트에도 같은 기능.

이름 · 회사 · 번호는 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

JS_TEST = Path(__file__).resolve().parent / "js" / "custom_column_save_test.js"


@pytest.fixture()
def portal(db, users):
    """역할별로 따로 로그인한 클라이언트 — 팀원 둘 · 관리자 · 투자컨설턴트."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    db.add_all([
        User(id=91, name="관리자시험", phone="01000000091", role="admin",
             can_view_consulting=1, password_hash=pw),
        User(id=92, name="컨설턴트시험", phone="01000000092", role="consultant",
             can_view_consulting=1, password_hash=pw),
    ])
    users["u1"].can_view_consulting = 1
    db.commit()
    app = create_app()

    def sign_in(phone):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {"u1": sign_in("01000000001"), "u2": sign_in("01000000002"),
            "admin": sign_in("01000000091"), "consultant": sign_in("01000000092")}


def _add(portal, target, name, kind="memo"):
    return portal["admin"].post("/columns", data={"target": target, "name": name,
                                                  "kind": kind},
                                follow_redirects=False)


def _col(db, target, name):
    from sqlalchemy import select

    from app.models import CustomColumn

    db.expire_all()
    return db.execute(select(CustomColumn).where(
        CustomColumn.target == target, CustomColumn.name == name)).scalar_one()


def _put(client, table, row_id, column_id, value):
    return client.put(f"/api/custom-values/{table}/{row_id}",
                      json={"column_id": column_id, "value": value})


def _values(db):
    from app.models import CustomColumnValue

    db.expire_all()
    return {(v.column_id, v.row_table, v.row_id): v.value
            for v in db.query(CustomColumnValue).all()}


def _sheet(resp):
    import openpyxl

    assert resp.status_code == 200, resp.text
    rows = list(openpyxl.load_workbook(io.BytesIO(resp.content)).active.iter_rows(
        values_only=True))
    return [list(r) for r in rows]


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플테크")
    db.add(row)
    db.commit()
    return row


# ═══════════════════════════════════════════════════════════════════════════
# 1. 칸 관리는 관리자만
# ═══════════════════════════════════════════════════════════════════════════

def test_관리자는_칸을_붙이고_이름을_바꾸고_옮기고_숨긴다(portal, db):
    assert _add(portal, "companies", "검토 메모").status_code == 303
    assert _add(portal, "companies", "투자 검토", "ox").status_code == 303
    memo, ox = _col(db, "companies", "검토 메모"), _col(db, "companies", "투자 검토")
    assert (memo.kind, ox.kind) == ("memo", "ox")
    assert memo.position < ox.position

    admin = portal["admin"]
    page = admin.get("/columns?target=companies")
    assert page.status_code == 200 and "검토 메모" in page.text and "투자 검토" in page.text

    admin.post(f"/columns/{memo.id}/rename", data={"name": "검토  의견 "})
    assert _col(db, "companies", "검토 의견").id == memo.id      # 공백은 하나로 다듬는다

    admin.post(f"/columns/{ox.id}/move", data={"step": -1})
    assert _col(db, "companies", "투자 검토").position < _col(db, "companies", "검토 의견").position

    admin.post(f"/columns/{ox.id}/hidden", data={"hidden": 1})
    assert _col(db, "companies", "투자 검토").is_hidden == 1
    admin.post(f"/columns/{ox.id}/hidden", data={"hidden": 0})
    assert _col(db, "companies", "투자 검토").is_hidden == 0


def test_팀원은_칸을_못_붙이고_못_고친다(portal, db):
    _add(portal, "companies", "검토 메모")
    col = _col(db, "companies", "검토 메모")
    member = portal["u1"]
    for url, data in (("/columns", {"target": "companies", "name": "몰래", "kind": "memo"}),
                      (f"/columns/{col.id}/rename", {"name": "바꿈"}),
                      (f"/columns/{col.id}/move", {"step": 1}),
                      (f"/columns/{col.id}/hidden", {"hidden": 1})):
        assert member.post(url, data=data, follow_redirects=False).status_code == 403, url
    # 화면은 안내창으로 답한다(주소창이 여는 GET — `deps.admin_block_response`).
    page = member.get("/columns")
    assert 'data-testid="column-add"' not in page.text and "검토 메모" not in page.text
    col = _col(db, "companies", "검토 메모")
    assert (col.name, col.is_hidden) == ("검토 메모", 0)
    # 좌측 메뉴에도 관리자에게만 보인다.
    assert 'href="/columns"' in portal["admin"].get("/").text
    assert 'href="/columns"' not in member.get("/").text


def test_삭제하는_길은_없다(portal):
    from app.main import create_app

    paths = {getattr(r, "path", "") for r in create_app().routes}
    assert not any("delete" in p for p in paths if p.startswith("/columns"))


def test_같은_화면에_같은_이름은_막는다_숨긴_칸까지(portal, db):
    _add(portal, "companies", "검토 메모")
    resp = _add(portal, "companies", "검토 메모")
    assert "msg=" in resp.headers["location"]
    from app.models import CustomColumn
    assert db.query(CustomColumn).count() == 1

    col = _col(db, "companies", "검토 메모")
    portal["admin"].post(f"/columns/{col.id}/hidden", data={"hidden": 1})
    _add(portal, "companies", "검토 메모")          # 숨겨도 이름은 그 칸 것이다
    assert db.query(CustomColumn).count() == 1

    _add(portal, "companies", "다른 칸")
    other = _col(db, "companies", "다른 칸")
    portal["admin"].post(f"/columns/{other.id}/rename", data={"name": "검토 메모"})
    assert _col(db, "companies", "다른 칸").id == other.id

    # 다른 화면에는 같은 이름이 서도 된다.
    _add(portal, "sourcing", "검토 메모")
    assert db.query(CustomColumn).count() == 3


def test_모르는_화면_형식_빈_이름은_안_붙는다(portal, db):
    from app.models import CustomColumn

    _add(portal, "nowhere", "칸")
    _add(portal, "companies", "칸", "date")
    _add(portal, "companies", "   ")
    assert db.query(CustomColumn).count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. 값 적기 — 메모는 글, O/X 는 그 둘만
# ═══════════════════════════════════════════════════════════════════════════

def test_메모와_OX를_적고_OX_아닌_값은_거절한다(portal, db, company):
    _add(portal, "companies", "검토 메모")
    _add(portal, "companies", "투자 검토", "ox")
    memo, ox = _col(db, "companies", "검토 메모"), _col(db, "companies", "투자 검토")
    member = portal["u1"]

    r = _put(member, "ir_companies", company.id, memo.id, "  다음 주 다시 보기 ")
    assert r.status_code == 200 and r.json()["value"] == "다음 주 다시 보기"
    assert r.json()["updated_at"]

    assert _put(member, "ir_companies", company.id, ox.id, "o").json()["value"] == "O"
    bad = _put(member, "ir_companies", company.id, ox.id, "아마도")
    assert bad.status_code == 400
    assert _values(db)[(ox.id, "ir_companies", company.id)] == "O"

    # 비우면 줄째 지운다.
    assert _put(member, "ir_companies", company.id, ox.id, "").status_code == 200
    assert (ox.id, "ir_companies", company.id) not in _values(db)


def test_다른_화면의_칸은_이_표에_못_적는다(portal, db, company):
    _add(portal, "sourcing", "소싱 메모")
    col = _col(db, "sourcing", "소싱 메모")
    assert _put(portal["u1"], "ir_companies", company.id, col.id, "x").status_code == 400
    assert _put(portal["u1"], "nowhere", company.id, col.id, "x").status_code == 404
    assert _put(portal["u1"], "ir_companies", 9999, col.id, "x").status_code == 404


def test_값은_줄을_고칠_수_있는_사람만_적는다(portal, db, users):
    """그 표의 판정 그대로 — 남의 매출예상리스트 줄 404 · 투자현황 꺼진 계정 403 ·
    투자컨설턴트는 자기 화면 줄만."""
    from app.models import ConsultingCompany, IrCompany, RevenueForecast

    for target, name in (("forecast", "후속 메모"), ("consulting", "컨설팅 메모"),
                         ("companies", "검토 메모")):
        _add(portal, target, name)
    theirs = RevenueForecast(user_id=users["u2"].id, company_name="샘플랩")
    mine = ConsultingCompany(user_id=92, company_name="샘플바이오")
    ir = IrCompany(name="샘플에너지")
    db.add_all([theirs, mine, ir])
    db.commit()

    fc = _col(db, "forecast", "후속 메모")
    assert _put(portal["u1"], "revenue_forecasts", theirs.id, fc.id, "몰래").status_code == 404
    assert _put(portal["u2"], "revenue_forecasts", theirs.id, fc.id, "내 것").status_code == 200
    assert _put(portal["admin"], "revenue_forecasts", theirs.id, fc.id, "관리").status_code == 200

    cs = _col(db, "consulting", "컨설팅 메모")
    assert _put(portal["consultant"], "consulting_companies", mine.id, cs.id,
                "적음").status_code == 200
    # 투자현황이 꺼진 팀원 — 그 화면의 PATCH 와 같이 막힌다.
    assert _put(portal["u2"], "consulting_companies", mine.id, cs.id, "몰래").status_code == 403

    co = _col(db, "companies", "검토 메모")
    assert _put(portal["consultant"], "ir_companies", ir.id, co.id, "몰래").status_code == 403
    assert (co.id, "ir_companies", ir.id) not in _values(db)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 화면 — IR 탭 셋이 같은 칸 · 숨긴 칸은 빠지고 값은 남는다
# ═══════════════════════════════════════════════════════════════════════════

def test_IR_탭_셋이_같은_칸을_쓰고_값은_표마다_따로다(portal, db, company):
    from app.models import SeriesACompany

    deal = SeriesACompany(name="샘플딜", received_at="2026-10-01")
    db.add(deal)
    db.commit()
    _add(portal, "companies", "검토 메모")
    col = _col(db, "companies", "검토 메모")
    member = portal["u1"]
    _put(member, "ir_companies", company.id, col.id, "기업 쪽 메모")
    _put(member, "series_a_companies", deal.id, col.id, "딜 쪽 메모")

    for tab, table, text in (("", "ir_companies", "기업 쪽 메모"),
                             ("?tab=db", "ir_companies", "기업 쪽 메모"),
                             ("?tab=series-a", "series_a_companies", "딜 쪽 메모")):
        html = member.get("/companies" + tab).text
        assert "검토 메모" in html, tab
        assert f'data-custom="{col.id}" data-custom-rows="{table}"' in html, tab
        assert text in html, tab
    # 번호가 같아도 표가 다르면 다른 값이다.
    vals = _values(db)
    assert vals[(col.id, "ir_companies", company.id)] == "기업 쪽 메모"
    assert vals[(col.id, "series_a_companies", deal.id)] == "딜 쪽 메모"


def test_OX_칸은_필터를_세우고_메모는_안_세운다(portal, db, company):
    _add(portal, "companies", "검토 메모")
    _add(portal, "companies", "투자 검토", "ox")
    memo, ox = _col(db, "companies", "검토 메모"), _col(db, "companies", "투자 검토")
    _put(portal["u1"], "ir_companies", company.id, ox.id, "X")
    html = portal["u1"].get("/companies").text
    assert f'data-filters="cc{ox.id}:투자 검토"' in html
    assert f'data-f-cc{ox.id}="X"' in html
    assert f"data-filters=\"cc{memo.id}:" not in html
    assert f"data-f-cc{memo.id}=" not in html
    assert 'data-choices="O,X"' in html


def test_숨긴_칸은_화면과_엑셀에서_빠지고_값은_남는다(portal, db, company):
    _add(portal, "companies", "검토 메모")
    col = _col(db, "companies", "검토 메모")
    member = portal["u1"]
    _put(member, "ir_companies", company.id, col.id, "남아야 할 메모")
    assert "남아야 할 메모" in member.get("/companies").text
    full = _sheet(member.get("/api/export/companies.xlsx"))
    assert full[0][-1] == "검토 메모" and full[1][-1] == "남아야 할 메모"
    view = _sheet(member.get("/api/export/companies-view.xlsx"))
    assert view[0][-1] == "검토 메모" and view[1][-1] == "남아야 할 메모"

    portal["admin"].post(f"/columns/{col.id}/hidden", data={"hidden": 1})
    html = member.get("/companies").text
    assert "남아야 할 메모" not in html and "검토 메모" not in html
    assert "검토 메모" not in _sheet(member.get("/api/export/companies.xlsx"))[0]
    assert "검토 메모" not in _sheet(member.get("/api/export/companies-view.xlsx"))[0]
    assert _values(db)[(col.id, "ir_companies", company.id)] == "남아야 할 메모"
    # 숨긴 칸에는 적지 못한다 — 화면에 없는 칸이다.
    assert _put(member, "ir_companies", company.id, col.id, "새 글").status_code == 400

    portal["admin"].post(f"/columns/{col.id}/hidden", data={"hidden": 0})
    assert "남아야 할 메모" in member.get("/companies").text


def test_화면_엑셀의_OX_필터도_추가_칸을_건다(portal, db):
    from app.models import IrCompany

    a, b = IrCompany(name="샘플가"), IrCompany(name="샘플나")
    db.add_all([a, b])
    db.commit()
    _add(portal, "companies", "투자 검토", "ox")
    ox = _col(db, "companies", "투자 검토")
    _put(portal["u1"], "ir_companies", a.id, ox.id, "O")
    got = _sheet(portal["u1"].get(f"/api/export/companies-view.xlsx?cc{ox.id}=O"))
    assert [r[1] for r in got[1:]] == ["샘플가"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. 줄이 지워지면 값도 함께
# ═══════════════════════════════════════════════════════════════════════════

def test_줄을_지우면_그_줄의_값이_함께_지워진다(portal, db, company, users):
    from app.models import ConsultingCompany, SourcingContact

    _add(portal, "companies", "검토 메모")
    _add(portal, "sourcing", "소싱 메모")
    co, so = _col(db, "companies", "검토 메모"), _col(db, "sourcing", "소싱 메모")
    keep = SourcingContact(bucket="샘플갈래", name="샘플심사역")
    gone = SourcingContact(bucket="샘플갈래", name="샘플심사역둘")
    db.add_all([keep, gone])
    db.commit()
    member = portal["u1"]
    _put(member, "ir_companies", company.id, co.id, "기업 메모")
    _put(member, "sourcing_contacts", keep.id, so.id, "남는 메모")
    _put(member, "sourcing_contacts", gone.id, so.id, "지워질 메모")

    assert member.delete(f"/api/companies/{company.id}").status_code == 200
    db.delete(db.get(SourcingContact, gone.id))
    db.commit()
    assert _values(db) == {(so.id, "sourcing_contacts", keep.id): "남는 메모"}

    # 시트를 통째로 다시 올리는 길(한꺼번에 지우기)도 값을 남기지 않는다.
    from app.routers.consulting import apply_rows

    _add(portal, "consulting", "컨설팅 메모")
    cs = _col(db, "consulting", "컨설팅 메모")
    row = ConsultingCompany(user_id=users["u1"].id, company_name="샘플옛기업")
    db.add(row)
    db.commit()
    _put(member, "consulting_companies", row.id, cs.id, "옛 메모")
    apply_rows(db, {"columns": [], "companies": []}, users["u1"], replace=True)
    db.commit()
    assert not any(k[1] == "consulting_companies" for k in _values(db))


# ═══════════════════════════════════════════════════════════════════════════
# 5. 투자컨설턴트 — [월 열 추가]는 그대로, 새 칸은 따로
# ═══════════════════════════════════════════════════════════════════════════

def test_투자컨설턴트_월_열은_그대로이고_새_칸은_따로_선다(portal, db, users):
    from app.models import ConsultingColumn, ConsultingCompany, CustomColumn

    db.add(ConsultingCompany(user_id=users["u1"].id, company_name="샘플컨설팅",
                             sheet="스타트업"))
    db.commit()
    member = portal["u1"]
    r = member.post("/consulting/columns", data={"label": "10월 리마인드", "sheet": "스타트업"},
                    follow_redirects=False)
    assert r.status_code == 303
    _add(portal, "consulting", "컨설팅 메모")
    _add(portal, "consulting", "견적 확인", "ox")

    db.expire_all()
    assert [c.label for c in db.query(ConsultingColumn).all()] == ["10월 리마인드"]
    assert {c.name for c in db.query(CustomColumn).all()} == {"컨설팅 메모", "견적 확인"}
    html = member.get("/consulting?sheet=스타트업").text
    assert "10월 리마인드" in html and 'action="/consulting/columns"' in html
    assert "컨설팅 메모" in html and "견적 확인" in html
    # 이 표의 편집기는 `td.cell` 만 연다 — 추가 칸도 td 에 선다.
    memo = _col(db, "consulting", "컨설팅 메모")
    assert f'<td class="cell multi" data-field="cc{memo.id}" data-custom="{memo.id}"' in html

    row = db.query(ConsultingCompany).one()
    _put(member, "consulting_companies", row.id, memo.id, "컨설팅 쪽 글")
    got = _sheet(member.get("/api/export/consulting.xlsx"))
    assert "10월 리마인드" in got[0]
    assert got[0][-2:] == ["컨설팅 메모", "견적 확인"]
    assert got[1][-2:] == ["컨설팅 쪽 글", None]


# ═══════════════════════════════════════════════════════════════════════════
# 6. 딜 소싱 · 매출예상리스트 · 스타트업
# ═══════════════════════════════════════════════════════════════════════════

def test_딜_소싱에_칸이_선다(portal, db):
    from app.models import SourcingContact

    row = SourcingContact(bucket="샘플갈래", name="샘플심사역")
    db.add(row)
    db.commit()
    _add(portal, "sourcing", "소싱 메모")
    col = _col(db, "sourcing", "소싱 메모")
    _put(portal["u1"], "sourcing_contacts", row.id, col.id, "소싱 쪽 글")
    html = portal["u2"].get("/sourcing").text
    assert "소싱 메모" in html and "소싱 쪽 글" in html


def test_매출예상리스트에_칸이_서고_엑셀에도_나간다(portal, db, users):
    from app.models import RevenueForecast

    row = RevenueForecast(user_id=users["u1"].id, company_name="샘플랩")
    db.add(row)
    db.commit()
    _add(portal, "forecast", "후속 메모")
    col = _col(db, "forecast", "후속 메모")
    _put(portal["u1"], "revenue_forecasts", row.id, col.id, "다음 미팅 준비")
    html = portal["u1"].get("/report/forecast").text
    assert "후속 메모" in html and "다음 미팅 준비" in html
    got = _sheet(portal["u1"].get("/api/export/forecast.xlsx"))
    assert got[0][-1] == "후속 메모" and got[1][-1] == "다음 미팅 준비"


def test_스타트업_명단에만_서고_투자사_관리_현황에는_안_선다(portal, db, users):
    from urllib.parse import quote

    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label="샘플 스타트업 명단", user_id=users["u1"].id,
                      layout=cc.STARTUP, is_hidden=1))
    db.add(SheetOwner(label="샘플 투자사 명단", user_id=users["u1"].id,
                      layout=cc.INVESTOR, is_hidden=0))
    db.flush()
    startup = VcContact(user_id=users["u1"].id, source_sheet="샘플 스타트업 명단",
                        name="대표", firm="샘플스타트업")
    vc = VcContact(user_id=users["u1"].id, source_sheet="샘플 투자사 명단",
                   name="심사역", firm="샘플벤처스")
    db.add_all([startup, vc])
    db.commit()
    _add(portal, "startup", "온보딩 메모")
    col = _col(db, "startup", "온보딩 메모")
    member = portal["u1"]
    assert _put(member, "vc_contacts", startup.id, col.id, "다음 달 연락").status_code == 200

    html = member.get("/startup?sheet=" + quote("샘플 스타트업 명단")).text
    assert "온보딩 메모" in html and "다음 달 연락" in html
    assert "온보딩 메모" not in member.get("/contacts").text
    got = _sheet(member.get("/api/export/contacts.xlsx?sheet=" + quote("샘플 스타트업 명단")))
    assert got[0][-1] == "온보딩 메모" and got[1][-1] == "다음 달 연락"
    # 남의 줄은 그 표처럼 못 고친다.
    assert _put(portal["u2"], "vc_contacts", startup.id, col.id, "몰래").status_code == 404


def test_메모_칸은_화면마다_적은_줄바꿈을_살린다(portal, db, users, company):
    """#69 — 한 칸 내려 「1. 2. 3.」 을 적는다. 값은 줄바꿈째 저장되고, 메모 칸을
    쓰는 화면 전부가 줄을 살리는 칸(`keep-lines` · 투자컨설턴트는 `td.cell multi`)으로 그린다."""
    from urllib.parse import quote

    from app.models import (ConsultingCompany, RevenueForecast, SeriesACompany,
                            SheetOwner, SourcingContact, VcContact)
    from app.services import contact_columns as cc

    db.add(SheetOwner(label="샘플 스타트업 명단", user_id=users["u1"].id,
                      layout=cc.STARTUP, is_hidden=1))
    db.flush()
    rows = {
        "ir_companies": company,
        "series_a_companies": SeriesACompany(name="샘플딜", received_at="2026-10-01"),
        "sourcing_contacts": SourcingContact(bucket="샘플갈래", name="샘플심사역"),
        "revenue_forecasts": RevenueForecast(user_id=users["u1"].id, company_name="샘플랩"),
        "vc_contacts": VcContact(user_id=users["u1"].id, source_sheet="샘플 스타트업 명단",
                                 name="대표", firm="샘플스타트업"),
        "consulting_companies": ConsultingCompany(user_id=users["u1"].id,
                                                  company_name="샘플컨설팅", sheet="스타트업"),
    }
    db.add_all(rows.values())
    db.commit()
    text = "다음 단계\n1. 자료 받기\n2. 미팅 잡기"
    member = portal["u1"]
    screens = (("companies", "ir_companies", ["/companies", "/companies?tab=db"]),
               ("companies", "series_a_companies", ["/companies?tab=series-a"]),
               ("sourcing", "sourcing_contacts", ["/sourcing"]),
               ("forecast", "revenue_forecasts", ["/report/forecast"]),
               ("startup", "vc_contacts", ["/startup?sheet=" + quote("샘플 스타트업 명단")]),
               ("consulting", "consulting_companies", ["/consulting?sheet=스타트업"]))
    for target in {t for t, _table, _urls in screens}:
        _add(portal, target, "단계 메모")
    for target, table, urls in screens:
        col = _col(db, target, "단계 메모")
        r = _put(member, table, rows[table].id, col.id, text)
        assert r.status_code == 200 and r.json()["value"] == text, table
        cell = (f'<td class="cell multi" data-field="cc{col.id}"' if target == "consulting"
                else f'<div class="cell clamp2 keep-lines" data-field="cc{col.id}"')
        for url in urls:
            html = member.get(url).text
            assert cell in html, url
            assert text in html, url
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "app.css").read_text()
    assert ".clamp2.keep-lines { white-space: pre-line; }" in css


# ═══════════════════════════════════════════════════════════════════════════
# 7. 수정 로그 — 그 줄의 주인 판정 그대로
# ═══════════════════════════════════════════════════════════════════════════

def test_공용_줄의_칸을_고치면_로그가_남고_자기_줄은_안_남는다(portal, db, company, users):
    from app.models import EditLog, RevenueForecast

    _add(portal, "companies", "검토 메모")
    _add(portal, "forecast", "후속 메모")
    co, fc = _col(db, "companies", "검토 메모"), _col(db, "forecast", "후속 메모")
    mine = RevenueForecast(user_id=users["u1"].id, company_name="샘플랩")
    db.add(mine)
    db.commit()

    db.expire_all()
    before = db.query(EditLog).count()
    _put(portal["u1"], "ir_companies", company.id, co.id, "공용 메모")
    _put(portal["u1"], "revenue_forecasts", mine.id, fc.id, "내 메모")
    db.expire_all()
    logs = db.query(EditLog).order_by(EditLog.id).all()[before:]
    assert [(x.table_name, x.scope) for x in logs] == [("ir_companies", "shared")]
    assert "추가 칸 · 검토 메모" in logs[0].changes_json
    assert "공용 메모" not in logs[0].changes_json       # 메모 값은 싣지 않는다

    # 관리자가 남의 줄을 고치면 남는다.
    _put(portal["admin"], "revenue_forecasts", mine.id, fc.id, "관리자 메모")
    db.expire_all()
    last = db.query(EditLog).order_by(EditLog.id.desc()).first()
    assert (last.table_name, last.scope) == ("revenue_forecasts", "others")


# ═══════════════════════════════════════════════════════════════════════════
# 8. 브라우저 — 칸을 눌러 적으면 칸 값 길로 간다
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_추가_칸은_칸_값_길로_저장된다():
    """`inline_edit.js` · `consulting.js` — `data-custom` 칸은 줄의 표가 아니라
    `PUT /api/custom-values/{표}/{줄}` 로 간다. 다른 칸은 그대로다.

    로컬에서는 `node tests/js/custom_column_save_test.js` 로도 돈다.
    """
    result = subprocess.run([shutil.which("node"), str(JS_TEST)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


# ═══════════════════════════════════════════════════════════════════════════
# 9. 자리 — 어느 기존 칸 뒤에 둘지(0110)
# ═══════════════════════════════════════════════════════════════════════════

JS_POSITION = Path(__file__).resolve().parent / "js" / "custom_column_position_test.js"
VOID = {"input", "br", "img", "hr", "meta", "link", "source", "col", "wbr"}


def _custom_head(html):
    """추가 칸이 선 머리 줄 — `[(추가 칸인가, data-after, 이름)]`.

    이름은 `custom_cols.js` 의 `label` 처럼 칸 바로 밑의 글자만 모은다.
    """
    from html.parser import HTMLParser

    class Heads(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.row, self.depth = [], None, 0

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "tr":
                self.row = []
            elif tag == "th" and self.row is not None:
                self.row.append(["custom-col" in (a.get("class") or ""), a.get("data-after"), ""])
                self.depth = 1
            elif self.depth and tag not in VOID:
                self.depth += 1

        def handle_endtag(self, tag):
            if tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row = None
            elif tag == "th":
                self.depth = 0
            elif self.depth > 1:
                self.depth -= 1

        def handle_data(self, data):
            if self.depth == 1 and self.row:
                self.row[-1][2] += data

    parser = Heads()
    parser.feed(html)
    row = next(r for r in parser.rows if any(custom for custom, _a, _l in r))
    return [(custom, after, " ".join(label.split())) for custom, after, label in row]


def test_관리자만_자리를_고르고_그_화면에_없는_칸은_거절한다(portal, db):
    from app.models import EditLog

    _add(portal, "companies", "투자 검토", "ox")
    col = _col(db, "companies", "투자 검토")
    admin = portal["admin"]

    page = admin.get("/columns?target=companies").text
    assert f'action="/columns/{col.id}/place"' in page
    assert '<option value="">맨 끝</option>' in page
    # 몇 탭에만 있는 칸은 그 탭을 적는다 — 없는 탭에서는 맨 끝에 선다.
    assert ">기업명 뒤</option>" in page
    assert ">정책자금 뒤 (스타트업DB 탭만)</option>" in page

    before = db.query(EditLog).count()
    r = admin.post(f"/columns/{col.id}/place", data={"after": "기업명"},
                   follow_redirects=False)
    assert r.status_code == 303
    assert _col(db, "companies", "투자 검토").after_key == "기업명"
    assert 'value="기업명" selected' in admin.get("/columns?target=companies").text
    # 수정 로그 — 칸 정의를 고친 다른 일(이름 · 숨김)과 같은 자리에 전→후로 남는다.
    db.expire_all()
    log = db.query(EditLog).order_by(EditLog.id.desc()).first()
    assert db.query(EditLog).count() == before + 1
    assert (log.table_name, log.scope) == ("custom_columns", "shared")
    assert '"after_key"' in log.changes_json and "기업명" in log.changes_json

    # 그 화면에 없는 칸 · 다른 화면의 칸은 안 받는다.
    for bad in ("없는 칸", "투자사명"):
        r = admin.post(f"/columns/{col.id}/place", data={"after": bad},
                       follow_redirects=False)
        assert "msg=" in r.headers["location"]
        assert _col(db, "companies", "투자 검토").after_key == "기업명"
    # 팀원은 못 바꾼다.
    assert portal["u1"].post(f"/columns/{col.id}/place", data={"after": "대분류"},
                             follow_redirects=False).status_code == 403
    assert _col(db, "companies", "투자 검토").after_key == "기업명"
    # 비우면 맨 끝(처음 동작)으로 돌아간다.
    admin.post(f"/columns/{col.id}/place", data={"after": ""})
    assert _col(db, "companies", "투자 검토").after_key is None


def test_자리를_고른_칸은_머리글에_싣고_스크립트는_필터보다_먼저_돈다(portal, db, company):
    _add(portal, "companies", "투자 검토", "ox")
    _add(portal, "companies", "검토 메모")
    ox = _col(db, "companies", "투자 검토")
    portal["admin"].post(f"/columns/{ox.id}/place", data={"after": "대분류"})

    html = portal["u1"].get("/companies").text
    head = _custom_head(html)
    assert (True, "대분류", "투자 검토") in head
    assert (True, None, "검토 메모") in head          # 안 고른 칸은 지금처럼 맨 끝
    # 옮기는 스크립트가 필터 · 칸 고치기 · 정렬보다 먼저 실린다 — 필터가 머리글
    # 이름을 단추로 바꾸기 전에 이름을 읽어야 한다(`custom_cols.js`).
    at = {name: html.index(f"js/{name}") for name in
          ("custom_cols.js", "filters.js", "inline_edit.js", "table_sort.js")}
    assert at["custom_cols.js"] < min(at["filters.js"], at["inline_edit.js"],
                                      at["table_sort.js"])


def test_자리_목록의_칸이_그_화면_머리글에_다_있다(portal, db, users, company):
    """`anchors` 는 머리글 이름이다 — 템플릿에서 이름을 고치면 여기서 깨진다."""
    from urllib.parse import quote

    from app.models import (ConsultingCompany, RevenueForecast, SeriesACompany,
                            SheetOwner, SourcingContact, VcContact)
    from app.services import contact_columns as cc
    from app.services import custom_columns as svc

    u1 = users["u1"].id
    db.add(SeriesACompany(name="샘플딜", received_at="2026-10-01"))
    for sheet in ("스타트업", "경영본부 전달 기업", "월간 계약 업무현황표"):
        db.add(ConsultingCompany(user_id=u1, company_name="샘플컨설팅", sheet=sheet))
    db.add(SheetOwner(label="샘플 스타트업 명단", user_id=u1, layout=cc.STARTUP))
    db.flush()
    db.add(VcContact(user_id=u1, source_sheet="샘플 스타트업 명단", name="대표",
                     firm="샘플스타트업"))
    db.add(SourcingContact(bucket="샘플갈래", name="샘플심사역"))
    db.add(RevenueForecast(user_id=u1, company_name="샘플랩"))
    db.commit()
    for target in svc.TARGETS:
        _add(portal, target, "자리 시험")

    pages = {
        ("companies", "IR 기업 현황"): "/companies",
        ("companies", "스타트업DB"): "/companies?tab=db",
        ("companies", "Series A 이상 딜 소싱"): "/companies?tab=series-a",
        ("consulting", "스타트업"): "/consulting?sheet=" + quote("스타트업"),
        ("consulting", "그 밖의"): "/consulting?sheet=" + quote("경영본부 전달 기업"),
        ("consulting", "월간 계약 업무현황표"):
            "/consulting?sheet=" + quote("월간 계약 업무현황표"),
        ("startup", "스타트업 명단"): "/startup?sheet=" + quote("샘플 스타트업 명단"),
        ("sourcing", "딜 소싱"): "/sourcing",
        ("forecast", "매출예상리스트"): "/report/forecast",
    }
    assert set(pages) == {(t, tab) for t in svc.TARGETS for tab in svc.anchor_groups(t)}
    for (target, tab), url in pages.items():
        resp = portal["u1"].get(url)
        assert resp.status_code == 200, url
        labels = {label for custom, _a, label in _custom_head(resp.text) if not custom}
        missing = {svc.label_key(x) for x in svc.anchor_groups(target)[tab]} - labels
        assert not missing, f"{target} · {tab} 머리글에 없는 자리: {missing}"


def test_엑셀도_고른_자리에_서고_파일에_없는_칸이면_맨_끝이다(portal, db, users, company):
    from app.models import RevenueForecast

    _add(portal, "companies", "투자 검토", "ox")
    _add(portal, "companies", "검토 메모")
    _add(portal, "companies", "둘째 메모")
    ox, memo, memo2 = (_col(db, "companies", n) for n in ("투자 검토", "검토 메모", "둘째 메모"))
    admin = portal["admin"]
    admin.post(f"/columns/{ox.id}/place", data={"after": "기업명"})
    admin.post(f"/columns/{memo2.id}/place", data={"after": "기업명"})
    member = portal["u1"]
    _put(member, "ir_companies", company.id, ox.id, "O")
    _put(member, "ir_companies", company.id, memo2.id, "둘째 글")

    for url in ("/api/export/companies.xlsx", "/api/export/companies-view.xlsx"):
        got = _sheet(member.get(url))
        at = got[0].index("기업명")
        # 같은 칸 뒤 둘은 `position` 차례, 안 고른 칸은 맨 끝.
        assert got[0][at + 1:at + 3] == ["투자 검토", "둘째 메모"], url
        assert got[1][at + 1:at + 3] == ["O", "둘째 글"], url
        assert got[0][-1] == "검토 메모", url

    # 파일 머리글에 그 칸이 없으면(화면에만 있는 칸) 맨 끝이다.
    admin.post(f"/columns/{ox.id}/place", data={"after": "홍보메일삭제"})
    got = _sheet(member.get("/api/export/companies.xlsx"))
    assert "홍보메일삭제" not in got[0]
    assert got[0][-2:] == ["투자 검토", "검토 메모"]

    db.add(RevenueForecast(user_id=users["u1"].id, company_name="샘플랩"))
    db.commit()
    _add(portal, "forecast", "후속 메모")
    fc = _col(db, "forecast", "후속 메모")
    admin.post(f"/columns/{fc.id}/place", data={"after": "기업명"})
    got = _sheet(member.get("/api/export/forecast.xlsx"))
    assert got[0][got[0].index("기업명") + 1] == "후속 메모"


def test_마이그레이션_0110은_올리고_내려도_칸과_값이_남는다(tmp_path):
    import sqlite3

    from .test_migrations import _alembic

    db = tmp_path / "pos.db"
    # 빈 DB 는 `0001` 이 지금 모델로 짓는다(칸이 이미 있다) — 0109 로 내려 운영 DB 의
    # 꼴(칸 없음)을 만든 뒤 올린다.
    assert _alembic(db, "upgrade", "head").returncode == 0
    down = _alembic(db, "downgrade", "0109_custom_columns")
    assert down.returncode == 0, down.stdout + down.stderr

    def run(sql, *args):
        con = sqlite3.connect(db)
        try:
            out = con.execute(sql, args).fetchall()
            con.commit()
            return out
        finally:
            con.close()

    def cols():
        return {r[1] for r in run("PRAGMA table_info(custom_columns)")}

    add = ("INSERT INTO custom_columns (created_at, updated_at, target, name, kind, "
           "position, is_hidden) VALUES ('t', 't', 'companies', '검토 메모', 'memo', ?, 0)")
    run(add, 0)
    assert "after_key" not in cols()

    up = _alembic(db, "upgrade", "0110_custom_column_position")
    assert up.returncode == 0, up.stdout + up.stderr
    assert "after_key" in cols()
    # 이미 붙은 칸은 비어 있다 = 지금처럼 맨 끝.
    assert run("SELECT name, after_key FROM custom_columns") == [("검토 메모", None)]
    run("UPDATE custom_columns SET after_key = '기업명'")

    down = _alembic(db, "downgrade", "0109_custom_columns")
    assert down.returncode == 0, down.stdout + down.stderr
    assert "after_key" not in cols()
    assert run("SELECT name FROM custom_columns") == [("검토 메모",)]
    # 표를 새로 짓는 되돌리기라 이름 겹침 막기가 살아 있는지도 본다.
    with pytest.raises(sqlite3.IntegrityError):
        run(add, 1)
    assert _alembic(db, "upgrade", "head").returncode == 0
    assert "after_key" in cols()


def test_옛_머리글_이름으로_고른_자리는_새_이름_칸_뒤에_선다(portal, db):
    """#63 — 같은 칸을 같은 이름으로 맞추며 머리글 몇 개의 이름이 바뀌었다
    (딜 소싱 `투자분야` → `선호 투자분야` · Series A 탭 `핸드폰` → `연락처` …).
    `after_key` 는 고른 그때의 글자라 그대로 두면 그 칸이 맨 끝으로 물러난다 —
    저장값은 두고 **읽을 때** 새 이름으로 본다(`custom_columns.anchor_of`)."""
    from types import SimpleNamespace as C

    from app.models import SeriesACompany, SourcingContact
    from app.services.custom_columns import arranger

    db.add(SourcingContact(bucket="샘플갈래", name="샘플심사역"))
    db.add(SeriesACompany(name="샘플딜", received_at="2026-10-01"))
    db.commit()
    _add(portal, "sourcing", "소싱 메모")
    _add(portal, "companies", "연락 메모")
    _col(db, "sourcing", "소싱 메모").after_key = "투자분야"       # 옛 이름 그대로 저장된 칸
    db.commit()                      # `_col` 이 expire_all 을 부르므로 하나씩 적는다
    _col(db, "companies", "연락 메모").after_key = "핸드폰"
    db.commit()

    assert (True, "선호 투자분야", "소싱 메모") in _custom_head(portal["u1"].get("/sourcing").text)
    assert (True, "연락처", "연락 메모") in _custom_head(
        portal["u1"].get("/companies?tab=series-a").text)
    # 관리 화면도 그 자리를 고른 것으로 보인다 — 저장값은 안 바뀐다.
    assert '<option value="선호 투자분야" selected>' in \
        portal["admin"].get("/columns?target=sourcing").text
    assert _col(db, "sourcing", "소싱 메모").after_key == "투자분야"
    # 엑셀 차례도 같은 판정.
    put = arranger(["이름", "선호 투자분야", "메모"],
                   {"custom_cols": [C(target="sourcing", after_key="투자분야")]})
    assert put(["a", "b", "c", "x"]) == ["a", "b", "x", "c"]


def test_엑셀_차례_고르기는_같은_칸_뒤_여럿과_없는_칸을_가린다():
    from types import SimpleNamespace as C

    from app.services.custom_columns import arranger

    v = {"custom_cols": [C(after_key="가"), C(after_key=None), C(after_key="없음"),
                         C(after_key=" 가 ")]}
    put = arranger(["가", "", "나"], v)
    assert put(["가", "", "나", "c1", "c2", "c3", "c4"]) == ["가", "c1", "c4", "", "나",
                                                          "c2", "c3"]


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_고른_자리로_옮긴_칸에서_필터_정렬_칸고치기가_맞는_칸을_가리킨다():
    """`custom_cols.js` 를 먼저, 그다음 `inline_edit.js` · `filters.js` ·
    `table_sort.js` 를 화면 차례대로 돌린다.

    로컬에서는 `node tests/js/custom_column_position_test.js` 로도 돈다.
    """
    result = subprocess.run([shutil.which("node"), str(JS_POSITION)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
