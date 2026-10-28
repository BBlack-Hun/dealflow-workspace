"""`Series A 이상 딜 소싱` 탭 — `계약여부` · `계약서 수신 여부`(0125).

10/28 요청: "Series A 이상 딜 소싱 탭의 이메일 오른쪽으로 계약여부랑 계약서 수신여부
컬럼 추가". IR 기업 현황의 같은 두 칸과 같은 보기 · 같은 판정이고, IR 기업에 이어진 줄은
따라 고친다(`services/company_sync.FIELDS` — 3단계 규칙 그대로).

  1. 화면 — `이메일` 바로 오른쪽 · 보기 · 필터 · 기본 `미계약`
  2. 고치기 — 말도 열쇠로 받고 모르는 값은 막는다
  3. 따라 고치기 — IR ↔ Series A, 딜 소싱 값 보호, 딜소개 불가, 계약 Day7 날짜
  4. 이미 이어진 줄 채우기 스크립트 · 값 다름 화면
  5. 판(0125) 오르내리기

이름 · 번호는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from .test_migrations import _alembic


@pytest.fixture()
def ir(db):
    from app.models import IrCompany

    company = IrCompany(name="(주)샘플가람", contract_status="none")
    db.add(company)
    db.commit()
    return company


def _deal(db, **kw):
    from app.models import SeriesACompany

    row = SeriesACompany(**kw)
    db.add(row)
    db.commit()
    return row


def _fresh(db, *rows):
    db.expire_all()
    return [db.get(type(r), r.id) for r in rows]


def _patch(client, row, **body):
    return client.patch(f"/api/series-a-companies/{row.id}", json=body)


# ── 1. 화면 ────────────────────────────────────────────────────────────────

def test_이메일_바로_오른쪽에_두_칸이_서고_보기와_필터가_IR_표와_같다(logged_in, db):
    from app.routers.companies import CONTRACT_LABELS

    _deal(db, name="샘플없음", received_at="2026-10-01")
    html = logged_in.get("/companies?tab=series-a").text
    thead = re.search(r'id="sa-table".*?</thead>', html, re.S).group(0)
    labels = [re.sub(r"<[^>]+>", "", t).strip()
              for t in re.findall(r"<th\b[^>]*>(.*?)</th>", thead, re.S)]
    at = labels.index("이메일")
    assert labels[at + 1:at + 3] == ["계약여부", "계약서 수신 여부"], labels
    assert 'data-filters="contract:계약여부"' in thead
    assert 'data-filters="received:계약서 수신 여부"' in thead

    row = re.search(r"<tr data-id=.*?</tr>", html, re.S).group(0)
    fields = re.findall(r'data-field="([^"]+)"', row)
    at = fields.index("ceo_email")
    assert fields[at + 1:at + 3] == ["contract_status", "contract_received"], fields
    # 비어 있으면 IR 표처럼 `미계약` — 보기는 늘 다 선다(`data-choices`).
    assert ('data-choices="' + ", ".join(CONTRACT_LABELS.values()) + '">미계약</td>') in row
    assert 'data-f-contract="미계약"' in row and 'data-f-received=""' in row
    assert 'data-choices="O,X"></td>' in row


# ── 2. 고치기 ──────────────────────────────────────────────────────────────

def test_칸에_보이는_말로_고치면_열쇠로_저장하고_말을_돌려준다(logged_in, db):
    from app.models import SeriesACompany

    row = _deal(db, name="샘플없음")
    data = _patch(logged_in, row, contract_status="유료계약완료").json()
    assert (data["contract_status"], data["contract_label"]) == ("paid", "유료계약완료")
    data = _patch(logged_in, row, contract_status="딜소개불가").json()   # 띄어쓰기 없이 쳐도
    assert data["contract_label"] == "딜소개 불가"
    data = _patch(logged_in, row, contract_received="o").json()
    assert data["contract_received"] == "O"
    db.expire_all()
    saved = db.get(SeriesACompany, row.id)
    assert (saved.contract_status, saved.contract_received) == ("blocked", "O")
    html = logged_in.get("/companies?tab=series-a").text
    assert 'data-f-contract="딜소개 불가"' in html and ">딜소개 불가</td>" in html

    # 비우면 계약서 수신은 지운다(미정), 계약여부는 `미계약`.
    data = _patch(logged_in, row, contract_status="", contract_received=" ").json()
    assert (data["contract_label"], data["contract_received"]) == ("미계약", "")


@pytest.mark.parametrize("body", [{"contract_status": "계약함"}, {"contract_received": "△"}])
def test_모르는_값은_막고_아무것도_안_바꾼다(logged_in, db, body):
    from app.models import SeriesACompany

    row = _deal(db, name="샘플없음", contract_status="free")
    res = _patch(logged_in, row, **body)
    assert res.status_code == 400 and "중에서 고르" in res.json()["detail"]
    db.expire_all()
    assert db.get(SeriesACompany, row.id).contract_status == "free"


# ── 3. 따라 고치기 ─────────────────────────────────────────────────────────

def test_이은_줄에서_유료계약완료로_고치면_IR이_따라오고_계약_Day7_날이_적힌다(logged_in, db, ir):
    """계약 Day7 은 IR 의 `contract_done_at` 으로 센다 — Series A 에서 고쳐도 IR 로 따라간
    값을 같은 flush 가 읽어 오늘을 적는다(`models._stamp_contract_done` 이 따라 고치기 뒤)."""
    from app import clock

    row = _deal(db, name="샘플 가람")
    assert row.ir_company_id == ir.id
    data = _patch(logged_in, row, contract_status="유료계약완료", contract_received="X").json()
    assert data["contract_label"] == "유료계약완료"
    company, = _fresh(db, ir)
    assert (company.contract_status, company.contract_received) == ("paid", "X")
    assert company.contract_done_at == clock.today().isoformat()


def test_안_이은_줄은_IR을_건드리지_않는다(logged_in, db, ir):
    row = _deal(db, name="샘플없음")
    assert row.ir_company_id is None
    _patch(logged_in, row, contract_status="유료계약완료")
    company, = _fresh(db, ir)
    assert (company.contract_status, company.contract_done_at) == ("none", None)


def test_잇는_순간_빈칸은_IR_값으로_채운다(logged_in, db, ir):
    ir.contract_status, ir.contract_received = "free", "O"
    db.commit()
    data = logged_in.post("/api/series-a-companies", json={"name": "샘플가람"}).json()
    assert (data["contract_label"], data["contract_received"]) == ("무료계약완료", "O")


def test_IR을_고치면_빈칸과_같던_값만_따라오고_딜_소싱_값은_둔다(logged_in, db, ir):
    same = _deal(db, name="샘플가람")            # 빈칸 — 따라온다
    own = _deal(db, name="샘플가람")
    _patch(logged_in, own, contract_status="계약검토중")
    company, = _fresh(db, ir)
    assert company.contract_status == "review"   # 줄에서 고친 값은 IR 로 간다
    _patch(logged_in, same, contract_status="계약검토중")
    db.execute(own.__table__.update().where(own.__table__.c.id == own.id)
               .values(contract_status="free"))   # 딜 소싱에서 따로 적어 둔 값
    db.commit()
    res = logged_in.patch(f"/api/companies/{ir.id}", json={"contract_status": "paid"})
    assert res.status_code == 200, res.text
    same, own = _fresh(db, same, own)
    assert same.contract_status == "paid", "IR 의 이전 값과 같던 줄이 안 따라왔다"
    assert own.contract_status == "free", "딜 소싱에서 따로 쓰는 값을 덮었다"


# ── 4. 채우기 스크립트 · 값 다름 ─────────────────────────────────────────────

def test_채우기_스크립트가_이미_이어진_Series_A_줄의_빈칸을_채운다(db, ir):
    from scripts import company_sync_fill

    row = _deal(db, name="샘플가람")
    # 이 칸이 생기기 전에 이어진 줄 — 따라 고치기를 안 지나고 IR 값만 넣는다.
    table = ir.__table__
    db.execute(table.update().where(table.c.id == ir.id)
               .values(contract_status="paid", contract_received="O"))
    db.commit()
    row, = _fresh(db, row)
    assert row.contract_status is None
    counts = company_sync_fill.run(db)
    db.commit()
    row, = _fresh(db, row)
    assert (row.contract_status, row.contract_received) == ("paid", "O")
    assert counts["contract_status"] == 1 and counts["ir:contract_status"] == 0


def test_값_다름에는_Series_A_줄의_계약여부도_말로_보인다(db, ir):
    from app.services import company_sync

    row = _deal(db, name="샘플가람", contract_status="free")
    table = ir.__table__
    db.execute(table.update().where(table.c.id == ir.id).values(contract_status="paid"))
    db.commit()
    row, = _fresh(db, row)
    diff = {d["field"]: d for d in company_sync.differences(db, [row])[row.id]}
    assert (diff["contract_status"]["row"], diff["contract_status"]["ir"]) == \
        ("무료계약완료", "유료계약완료")


# ── 5. 판(0125) ────────────────────────────────────────────────────────────

def _cols(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("series_a_companies")')}
    finally:
        con.close()


def test_0125_는_칸_둘을_붙이고_되돌리면_뗀다(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", "0124_firm_research_cols").returncode == 0
    # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE series_a_companies DROP COLUMN contract_status")
        con.execute("ALTER TABLE series_a_companies DROP COLUMN contract_received")
        con.execute("INSERT INTO series_a_companies (name, ir_link_auto, created_at, updated_at) "
                    "VALUES ('샘플가람', 0, '2026-10-28T00:00:00+09:00', "
                    "'2026-10-28T00:00:00+09:00')")
        con.commit()
    finally:
        con.close()
    assert {"contract_status", "contract_received"} & _cols(db) == set()

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert {"contract_status", "contract_received"} <= _cols(db)

    down = _alembic(db, "downgrade", "0124_firm_research_cols")
    assert down.returncode == 0, down.stdout + down.stderr
    assert {"contract_status", "contract_received"} & _cols(db) == set()
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT name FROM series_a_companies").fetchall() == [("샘플가람",)]
    finally:
        con.close()
