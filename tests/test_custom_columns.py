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
