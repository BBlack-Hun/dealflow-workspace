"""기업 동기화 3단계 — Series A 이상 딜 소싱 줄 ↔ IR 기업 현황.

사용자 제보(10/26): Series A 탭에 IR 기업 현황과 같은 기업명을 넣었는데 대표자명 등이
연동되지 않는다. 1 · 2단계(`tests/test_company_sync.py`)와 같은 규칙을 Series A 에 건다
(`services/company_sync.py` 머리말 · 10/22 결정).

이름 · 번호는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import html as htmllib
import json
import re

import pytest


@pytest.fixture()
def ir(db):
    from app.models import IrCompany

    company = IrCompany(name="(주)샘플가람", contact_name="김샘플",
                        contact_phone="010-0000-1111", pre_value="100",
                        revenue_recent="12", revenue_2025="8.2억")
    db.add_all([company, IrCompany(name="샘플쌍둥"), IrCompany(name="샘플 쌍둥(주)")])
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


def _raw_set(db, row, **values):
    """따라 고치기를 지나지 않고 줄만 바꾼다 — 이을 때부터 달랐던 값 · 옛 줄을 흉내 낸다."""
    db.execute(row.__table__.update().where(row.__table__.c.id == row.id).values(**values))
    db.commit()
    return _fresh(db, row)[0]


# ── 잇기 ────────────────────────────────────────────────────────────────────

def test_새_줄은_이름이_하나_맞으면_저절로_잇고_빈칸을_채운다(logged_in, db, ir):
    from app.models import SeriesACompany

    data = logged_in.post("/api/series-a-companies", json={"name": "샘플 가람"}).json()
    row = db.get(SeriesACompany, data["id"])
    assert (row.ir_company_id, row.ir_link_auto) == (ir.id, 1)
    # 빈칸은 IR 값으로 — 응답에도 실린다(화면이 다시 그린다).
    assert (data["ceo_name"], data["ceo_phone"], data["pre_value"]) == \
        ("김샘플", "010-0000-1111", "100")


def test_이름이_같은_IR_기업이_둘이면_안_잇는다(logged_in, db, ir):
    from app.models import SeriesACompany

    data = logged_in.post("/api/series-a-companies", json={"name": "샘플쌍둥"}).json()
    assert db.get(SeriesACompany, data["id"]).ir_company_id is None


def test_잇는_순간에는_양쪽_빈칸만_채우고_다른_값은_값_다름에_선다(db, ir):
    from app.services import company_sync

    row = _deal(db, name="샘플가람", ceo_name="박샘플", ceo_email="ceo@example.com",
                pre_value="90")
    row, company = _fresh(db, row, ir)
    assert row.ir_company_id == ir.id
    # 다른 값은 그대로 — 어느 쪽도 덮지 않는다.
    assert (row.ceo_name, company.contact_name) == ("박샘플", "김샘플")
    assert (row.pre_value, company.pre_value) == ("90", "100")
    # 한쪽만 빈 칸은 서로 채운다.
    assert company.contact_email == "ceo@example.com"
    assert row.ceo_phone == "010-0000-1111"
    fields = [d["field"] for d in company_sync.differences(db, [row])[row.id]]
    assert fields == ["contact_name", "pre_value"]


def test_기업명을_고치면_그_자리에서_잇고_채운_값을_응답으로_준다(logged_in, db, ir):
    """10/26 사용자: "버튼을 눌러서 가져오는게 아니라 기업명을 넣었을때 자동으로"."""
    row = _deal(db, name="샘플없음")
    assert row.ir_company_id is None
    data = logged_in.patch(f"/api/series-a-companies/{row.id}",
                           json={"name": "샘플가람"}).json()
    assert (data["ceo_name"], data["revenue_2026"]) == ("김샘플", "12")
    assert data["ir_link"]["linked"] and data["ir_link"]["auto"]
    row = _fresh(db, row)[0]
    assert (row.ir_company_id, row.ir_link_auto) == (ir.id, 1)


def test_저절로_이은_줄은_다른_기업명으로_고치면_옮기고_사람이_이은_줄은_둔다(logged_in, db, ir):
    from app.models import IrCompany

    other = IrCompany(name="샘플나래", contact_name="이샘플")
    db.add(other)
    db.commit()
    auto = _deal(db, name="샘플가람")
    hand = _raw_set(db, _deal(db, name="샘플가람"), ir_link_auto=0)
    for row in (auto, hand):
        logged_in.patch(f"/api/series-a-companies/{row.id}", json={"name": "샘플나래"})
    auto, hand = _fresh(db, auto, hand)
    assert auto.ir_company_id == other.id and auto.ir_link_auto == 1
    assert hand.ir_company_id == ir.id, "사람이 고른 연결을 기업명 고치기가 바꿨다"
    # 이름이 맞는 IR 기업이 없으면 지금 연결을 둔다.
    logged_in.patch(f"/api/series-a-companies/{auto.id}", json={"name": "샘플없음"})
    assert _fresh(db, auto)[0].ir_company_id == other.id


def test_IR에_기업이_새로_생기면_그_이름의_안_이은_줄이_이어지고_채워진다(logged_in, db):
    from app.models import SeriesACompany

    row = _deal(db, name="샘플보람", ceo_name="박샘플")
    assert row.ir_company_id is None
    r = logged_in.post("/api/companies", json={"name": "(주)샘플보람",
                                               "contact_phone": "010-0000-2222"})
    assert r.status_code == 200, r.text
    row = db.get(SeriesACompany, row.id)
    db.refresh(row)
    assert (row.ir_company_id, row.ir_link_auto) == (r.json()["id"], 1)
    assert row.ceo_phone == "010-0000-2222"
    db.expire_all()
    assert _company(db, r.json()["id"]).contact_name == "박샘플"


def _company(db, company_id):
    from app.models import IrCompany

    return db.get(IrCompany, company_id)


def test_IR_기업명을_고치면_그_이름의_안_이은_줄이_이어진다(logged_in, db, ir):
    row = _deal(db, name="샘플다온")
    assert row.ir_company_id is None
    logged_in.patch(f"/api/companies/{ir.id}", json={"name": "샘플다온"})
    row = _fresh(db, row)[0]
    assert row.ir_company_id == ir.id and row.ceo_name == "김샘플"


def test_IR에_같은_이름이_둘이_되면_안_잇는다(logged_in, db, ir):
    row = _deal(db, name="샘플쌍둥")
    logged_in.post("/api/companies", json={"name": "샘플쌍둥 (주)"})
    assert _fresh(db, row)[0].ir_company_id is None


# ── 따라 고치기 ─────────────────────────────────────────────────────────────

def test_Series_A에서_고치면_IR과_다른_날_줄이_따라오고_IR을_고치면_줄이_따라온다(
        logged_in, db, ir):
    first = _deal(db, name="샘플가람", received_at="2026-07-01")
    second = _deal(db, name="샘플가람", received_at="2026-09-01")
    r = logged_in.patch(f"/api/series-a-companies/{first.id}",
                        json={"ceo_email": "new@example.com", "raise_target": "50"})
    assert r.status_code == 200, r.text
    company, second = _fresh(db, ir, second)
    assert (company.contact_email, company.raise_target) == ("new@example.com", "50")
    assert (second.ceo_email, second.raise_target) == ("new@example.com", "50")

    r = logged_in.patch(f"/api/companies/{ir.id}", json={"contact_name": "최샘플"})
    assert r.status_code == 200, r.text
    first, second = _fresh(db, first, second)
    assert first.ceo_name == "최샘플" and second.ceo_name == "최샘플"


def test_비운_칸은_안_따라간다(logged_in, db, ir):
    row = _deal(db, name="샘플가람")
    logged_in.patch(f"/api/series-a-companies/{row.id}", json={"ceo_name": ""})
    company, row = _fresh(db, ir, row)
    assert row.ceo_name is None and company.contact_name == "김샘플"


def test_수정_로그에_남는다(logged_in, db, ir):
    from app.models import EditLog

    row = _deal(db, name="샘플가람")
    logged_in.patch(f"/api/series-a-companies/{row.id}", json={"ceo_email": "x@example.com"})
    logs = db.query(EditLog).filter(EditLog.table_name == "ir_companies").all()
    assert any("contact_email" in (log.changes_json or "") for log in logs)


# ── 연도 매출 — 해마다 짝이 바뀐다 ─────────────────────────────────────────

def test_2026년에는_26년_칸이_최근_매출액이고_27년_칸은_안_잇는다(logged_in, db, ir):
    from app.services import company_sync

    row = _deal(db, name="샘플가람")
    row = _fresh(db, row)[0]
    # 잇는 순간: IR `최근 매출액(26년)` → 26년 칸, IR 25년 → 25년 칸.
    assert (row.revenue_2026, row.revenue_2025) == ("12", "8.2억")
    logged_in.patch(f"/api/series-a-companies/{row.id}",
                    json={"revenue_2026": "15", "revenue_2024": "3", "revenue_2027": "30"})
    company = _fresh(db, ir)[0]
    assert company.revenue_recent == "15"
    # 지난 해 칸은 단위를 붙여 적는다 — 연도 칸은 적힌 그대로 한줄 소개에 실린다.
    assert company.revenue_2024 == "3억"
    assert company.revenue_2027 is None, "앞으로 올 해는 IR 에 받을 칸이 없다"
    # `3` 과 `3억` 은 같은 값이다 — 값 다름에 안 선다.
    assert company_sync.differences(db, [_fresh(db, row)[0]]) == {}
    assert company_sync.label("revenue_recent") == "최근 매출액(26년)"


def test_2027년에는_27년_칸이_최근_매출액이고_26년_칸은_IR_26년과_잇는다(
        logged_in, db, ir, monkeypatch):
    from app.services import revenue_years

    row = _deal(db, name="샘플가람", revenue_2026="20")
    monkeypatch.setattr(revenue_years, "this_year", lambda: 2027)
    logged_in.patch(f"/api/series-a-companies/{row.id}", json={"revenue_2027": "25"})
    company = _fresh(db, ir)[0]
    assert company.revenue_recent == "25"
    # 해가 바뀌어 옮겨 적기(`roll_over`)가 IR 26년 칸을 채워도, 저절로 하는 일이라
    # 사람이 적은 Series A 26년 값을 덮지 않는다 — 값 다름에 선다.
    company.revenue_recent = "18"
    db.commit()
    revenue_years.roll_over(db, actor_id=1)
    company, row = _fresh(db, ir, row)
    assert company.revenue_2026 == "18억" and row.revenue_2026 == "20"
    logged_in.patch(f"/api/series-a-companies/{row.id}", json={"revenue_2026": "21"})
    assert _fresh(db, ir)[0].revenue_2026 == "21억"


# ── 시트 다시 올리기 ───────────────────────────────────────────────────────

def test_시트를_다시_올려도_연결과_적은_값이_남고_새_딜도_저절로_잇는다(db, ir):
    from app.models import SeriesACompany
    from app.services import series_a_import as svc

    sheet = [["수신 일자", "공유 심사역", "회사", "기업명", "상세 내용"],
             ["2026-07-01", "홍샘플", "샘플투자", "샘플가람", "첫 내용"]]
    svc.upsert(db, svc.parse(sheet).records)
    db.commit()
    row = db.query(SeriesACompany).one()
    assert row.ir_company_id == ir.id and row.ceo_name == "김샘플"
    row.ceo_name = "박샘플"
    db.commit()

    sheet[1][4] = "고친 내용"
    sheet.append(["2026-09-01", "홍샘플", "샘플투자", "샘플가람", "둘째 딜"])
    svc.upsert(db, svc.parse(sheet).records, overwrite=True)
    db.commit()
    db.expire_all()
    first, second = db.query(SeriesACompany).order_by(SeriesACompany.id).all()
    assert first.detail == "고친 내용", "시트 줄이 이 줄에 안 맞았습니다"
    assert (first.ir_company_id, first.ceo_name) == (ir.id, "박샘플")
    assert second.ir_company_id == ir.id and second.ceo_name == "박샘플"


# ── 딜소개 불가 ─────────────────────────────────────────────────────────────

def test_Series_A_줄은_계약여부를_건드리지_않는다(logged_in, db, ir):
    from app.services import company_sync

    ir.contract_status = "blocked"
    db.commit()
    row = _deal(db, name="샘플가람")
    logged_in.patch(f"/api/series-a-companies/{row.id}", json={"ceo_name": "박샘플"})
    company, row = _fresh(db, ir, row)
    assert company.contact_name == "박샘플"
    assert company.contract_status == "blocked", "딜 발송 대상이 저절로 바뀌면 안 된다"
    assert company_sync.slot(row, "contract_status", {}) is None


# ── 화면 ────────────────────────────────────────────────────────────────────

def test_표에_자동_연결과_연결_풀기가_서고_풀면_풀린다(logged_in, db, ir):
    row = _deal(db, name="샘플가람")
    page = logged_in.get("/companies?tab=series-a").text
    # 그리는 것은 `series_a.js` — 서버는 무엇을 보일지 실어 준다(tests/js/series_a_test.js ⑥).
    raw = re.search(r"data-ir-link='([^']*)'", page).group(1)
    info = json.loads(htmllib.unescape(raw))
    assert info["linked"] and info["auto"] and info["company_id"] == ir.id
    assert info["link_href"] == f"/ir-link?tab=series-a&row={row.id}"
    focus = logged_in.get(f"/ir-link?tab=series-a&row={row.id}")
    assert focus.status_code == 200 and "연결 해제" in focus.text
    r = logged_in.post("/ir-link/unlink", data={"tab": "series-a", "row_id": row.id},
                       follow_redirects=False)
    assert r.status_code == 303
    assert _fresh(db, row)[0].ir_company_id is None


def test_연결_화면_Series_A_탭에_일괄_연결과_값_다름이_선다(logged_in, db, ir):
    from app.models import SeriesACompany

    # 옛 줄 — 3단계 전에 들어와 안 이어진 줄을 흉내 낸다.
    old = _raw_set(db, _deal(db, name="샘플가람"), ir_company_id=None, ir_link_auto=0,
                   ceo_name="박샘플", ceo_phone=None, pre_value=None, revenue_2026=None,
                   revenue_2025=None)
    html = logged_in.get("/ir-link?tab=series-a").text
    assert "Series A 이상 딜 소싱" in html and "후보가 하나인 줄 일괄 연결 (1줄)" in html
    confirm = logged_in.get("/ir-link/bulk?tab=series-a").text
    assert f'value="{old.id}:{ir.id}"' in confirm
    r = logged_in.post("/ir-link/bulk", data={"tab": "series-a", "pair": f"{old.id}:{ir.id}"},
                       follow_redirects=False)
    assert r.status_code == 303
    old = db.get(SeriesACompany, old.id)
    db.refresh(old)
    assert (old.ir_company_id, old.ir_link_auto, old.ceo_phone) == (ir.id, 1, "010-0000-1111")

    diff = logged_in.get("/ir-link?tab=series-a&show=diff").text
    assert "대표자명</b> 값 다름" in diff and "/ir-link/resolve" in diff
    r = logged_in.post("/ir-link/resolve", data={"tab": "series-a", "row_id": old.id,
                                                 "field": "contact_name", "pick": "row"},
                       follow_redirects=False)
    assert r.status_code == 303
    assert _fresh(db, ir)[0].contact_name == "박샘플"


def test_스크립트는_일괄_연결과_같은_함수로_잇고_수만_센다(db, ir):
    from scripts.series_a_ir_link import run

    old = _raw_set(db, _deal(db, name="샘플가람"), ir_company_id=None, ir_link_auto=0,
                   ceo_name=None, ceo_phone=None)
    _raw_set(db, _deal(db, name="샘플쌍둥"), ir_company_id=None)
    counts = run(db)
    db.commit()
    old = _fresh(db, old)[0]
    assert (old.ir_company_id, old.ir_link_auto, old.ceo_name) == (ir.id, 1, "김샘플")
    assert (counts["single"], counts["done"], counts["multi"]) == (1, 1, 1)
    assert counts["sa:contact_name"] == 1 and counts["ir:contact_name"] == 0
