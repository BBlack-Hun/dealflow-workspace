"""딜 소개 문구 자동 기입 · 27년 예상매출 칸(과제 168 · 169 · 170 — 11/07).

요청:
  · 169 — IR 기업 현황 · Series A 이상 딜 소싱에 `27년 예상매출` 칸
  · 168 · 170 — 매출 · 누적투자금액 · 투자유치희망금액 · Pre Value … 칸에 값을 넣으면 딜소개
    문구에도 저절로. 차례는 `사업분야 | 23 · 24 · 25 · 26년 매출, 27년 예상 | 누적투자금액 |
    투자유치 희망금액 | Pre Value | 특이사항`

지키는 것 — 사람이 쓴 문구는 **안 덮는다**(예전 결정 '기본은 사용자 정의 문구'). 따라 바뀌는 것은
비었거나 고치기 전 재료로 만든 조합값 그대로인 칸뿐이다(`services/one_liner.follow`).

검사의 올해는 2026 이다(tests/conftest.py). 이름 · 값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.services.one_liner import compose_one_liner, series_a_revenue

FULL = ("물류 최적화 SaaS | 매출 23년 1억, 24년 2억, 25년 3억, 26년 4억, 27년(예상) 8억 | "
        "누적투자금액 10억 | 30억 투자유치중 | Pre Value 200억 | TIPS 선정")


def _full(**kw):
    values = dict(name="샘플가나물류", business_desc="물류 최적화 SaaS", revenue_2023="1억",
                  revenue_2024="2억", revenue_2025="3억", revenue_recent="4", revenue_2027="8",
                  funding_total="10", raise_target="30", pre_value="200",
                  competitiveness="TIPS 선정", one_liner=None)
    values.update(kw)
    return values


@pytest.fixture()
def company(db):
    """재료는 있고 문구만 빈 기업 — 운영의 빈 칸. 새 줄은 저절로 채워지므로 재료를 안 건드리고 비운다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플가나물류", business_desc="물류 최적화 SaaS", revenue_2024="2억")
    db.add(row)
    db.commit()
    row.one_liner = None
    db.commit()
    return row


def _get(db, model, row_id):
    db.expire_all()
    return db.get(model, row_id)


# ── 169 · 칸 ────────────────────────────────────────────────────────────────

def test_IR_표와_창에_27년_예상매출이_26년_매출_바로_뒤에_선다(logged_in, company):
    html = logged_in.get("/companies").text
    head = html.split("</thead>")[0]
    names = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S)]
    at = names.index("26년 매출")
    assert names[at + 1:at + 3] == ["27년 예상매출", "누적투자금액"]
    assert 'data-field="revenue_2027"' in html, "표에서 눌러 고칠 칸이 없다"
    assert 'id="f-revenue_2027"' in html and "<span>27년 예상매출</span>" in html, "창에 칸이 없다"


def test_Series_A_탭의_27년_칸이_예상매출이다(logged_in, db):
    from app.models import SeriesACompany

    db.add(SeriesACompany(name="샘플다라소재"))
    db.commit()
    html = logged_in.get("/companies?tab=series-a").text
    assert ">27년 예상매출</th>" in html and ">27년 매출</th>" not in html


def test_엑셀_내려받기에도_27년_예상매출이_선다(logged_in, company, u1_admin):
    import io

    import openpyxl

    company.revenue_2027 = "8억"
    company.one_liner = "사람이 쓴 소개"
    _commit(company)
    resp = logged_in.get("/api/export/companies-view.xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    head, row = [[c.value for c in r] for r in ws.iter_rows(max_row=2)]
    assert row[head.index("27년 예상매출")] == "8억"


def _commit(row):
    from sqlalchemy.orm import object_session

    object_session(row).commit()


# ── 168 · 170 · 차례 ────────────────────────────────────────────────────────

def test_차례는_사업분야_매출_23에서_27예상_누적_희망_Pre_특이사항():
    assert compose_one_liner(SimpleNamespace(**_full())) == FULL


def test_회사명은_싣지_않는다():
    """딜 소개는 기업을 `[기업1]` 번호로 부르고 이름을 가린다 — 문구에 이름이 실리면 샌다."""
    assert "샘플가나물류" not in compose_one_liner(SimpleNamespace(**_full()))


def test_예상뿐이면_연도를_붙여_실제_매출과_가른다():
    only = SimpleNamespace(**_full(business_desc=None, revenue_2023=None, revenue_2024=None,
                                   revenue_2025=None, revenue_recent=None, funding_total=None,
                                   raise_target=None, pre_value=None, competitiveness=None))
    assert compose_one_liner(only) == "매출 27년(예상) 8억"
    # 실제 매출 한 해뿐이면 예전처럼 연도 없이.
    only.revenue_2027, only.revenue_recent = None, "4"
    assert compose_one_liner(only) == "매출 4억"


def test_Series_A_는_그_줄의_매출_금액으로_만든다():
    row = SimpleNamespace(revenue_2024="2", revenue_2025="3", revenue_2026="4", revenue_2027="8",
                          funding_total="10", raise_target="30", pre_value="200")
    assert compose_one_liner(row, series_a_revenue()) == (
        "매출 24년 2억, 25년 3억, 26년 4억, 27년(예상) 8억 | 누적투자금액 10억 | "
        "30억 투자유치중 | Pre Value 200억")


# ── 168 · 170 · 따라 고치기 ─────────────────────────────────────────────────

def test_빈_문구는_매출을_적으면_채워진다(logged_in, db, company):
    from app.models import IrCompany

    r = logged_in.patch(f"/api/companies/{company.id}", json={"revenue_2027": "8"})
    assert r.status_code == 200, r.text
    made = "물류 최적화 SaaS | 매출 24년 2억, 27년(예상) 8억"
    assert r.json()["one_liner"] == made and r.json()["one_liner_applied"] is True
    assert _get(db, IrCompany, company.id).one_liner == made


def test_자동으로_만든_문구는_재료를_고치면_따라_바뀐다(logged_in, db, company):
    from app.models import IrCompany

    logged_in.patch(f"/api/companies/{company.id}", json={"funding_total": "10"})
    logged_in.patch(f"/api/companies/{company.id}", json={"pre_value": "200"})
    assert _get(db, IrCompany, company.id).one_liner == \
        "물류 최적화 SaaS | 매출 2억 | 누적투자금액 10억 | Pre Value 200억"


def test_손으로_쓴_문구는_재료를_고쳐도_안_덮는다(logged_in, db, company):
    from app.models import IrCompany

    company.one_liner = "사람이 다듬어 쓴 소개"
    _commit(company)
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"revenue_2027": "8", "funding_total": "10"})
    body = r.json()
    assert body["one_liner"] == "사람이 다듬어 쓴 소개" and body["one_liner_applied"] is False
    assert body["one_liner_kept_manual"] is True
    assert _get(db, IrCompany, company.id).one_liner == "사람이 다듬어 쓴 소개"


def test_창이_모든_칸을_보내도_문구_글자가_그대로면_따라온다(logged_in, db, company):
    """[수정] 창은 문구 칸까지 한 번에 보낸다 — 글자가 그대로면 '고친 것' 이 아니다."""
    from app.models import IrCompany

    logged_in.patch(f"/api/companies/{company.id}", json={"funding_total": "10"})
    auto = _get(db, IrCompany, company.id).one_liner
    logged_in.patch(f"/api/companies/{company.id}",
                    json={"one_liner": auto, "business_desc": "물류 최적화 SaaS",
                          "funding_total": "10", "raise_target": "30"})
    assert _get(db, IrCompany, company.id).one_liner == \
        "물류 최적화 SaaS | 매출 2억 | 누적투자금액 10억 | 30억 투자유치중"


def test_같은_저장에서_문구를_비우면_빈_채로_둔다(logged_in, db, company):
    """비우는 것도 사람의 결정이다."""
    from app.models import IrCompany

    company.one_liner = "사람이 다듬어 쓴 소개"
    _commit(company)
    logged_in.patch(f"/api/companies/{company.id}",
                    json={"one_liner": "", "funding_total": "10"})
    assert not (_get(db, IrCompany, company.id).one_liner or "")


def test_기업_한줄_소개가_없으면_숫자뿐인_문구는_안_만든다(logged_in, db):
    """숫자만 든 문구는 딜 소개에 기업 설명 없이 나가고, 그 기업을 '소개 가능' 에 세운다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플사아로보", sector_major="로보틱스")
    db.add(row)
    db.commit()
    logged_in.patch(f"/api/companies/{row.id}", json={"raise_target": "30"})
    assert not (_get(db, IrCompany, row.id).one_liner or "")


def test_과제_168_전에_만든_자동_문구도_따라온다(logged_in, db):
    """26년 · 27년을 싣기 전 모양(지난 세 해만)으로 만들어 둔 줄 — 손글씨로 굳지 않는다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플라마핀테크", business_desc="결제 대행", revenue_2025="3억",
                    revenue_recent="4")
    db.add(row)
    db.commit()
    row.one_liner = "결제 대행 | 매출 3억"          # 예전 조합값(올해 칸을 안 실었다)
    db.commit()
    logged_in.patch(f"/api/companies/{row.id}", json={"funding_total": "10"})
    assert _get(db, IrCompany, row.id).one_liner == \
        "결제 대행 | 매출 25년 3억, 26년 4억 | 누적투자금액 10억"


def test_따라_바뀐_문구도_수정_로그에_남는다(logged_in, db, company):
    from app.models import EditLog

    logged_in.patch(f"/api/companies/{company.id}", json={"funding_total": "10"})
    logs = db.query(EditLog).filter(EditLog.table_name == "ir_companies",
                                    EditLog.row_id == company.id).all()
    fields = {c["field"] for log in logs for c in json.loads(log.changes_json)}
    assert {"funding_total", "one_liner"} <= fields, fields


# ── Series A 이상 딜 소싱 ────────────────────────────────────────────────────

def test_Series_A_빈_문구는_매출_금액을_적으면_채워진다(logged_in, db):
    from app.models import SeriesACompany

    row = SeriesACompany(name="샘플마바에듀")
    db.add(row)
    db.commit()
    r = logged_in.patch(f"/api/series-a-companies/{row.id}",
                        json={"revenue_2026": "4", "revenue_2027": "8", "raise_target": "30"})
    assert r.json()["deal_pitch"] == "매출 26년 4억, 27년(예상) 8억 | 30억 투자유치중"
    # 사람이 고쳐 쓰면 그다음부터는 안 덮는다.
    logged_in.patch(f"/api/series-a-companies/{row.id}", json={"deal_pitch": "사람이 쓴 딜 소개"})
    logged_in.patch(f"/api/series-a-companies/{row.id}", json={"pre_value": "200"})
    assert _get(db, SeriesACompany, row.id).deal_pitch == "사람이 쓴 딜 소개"


def test_IR_의_27년_예상매출이_이어진_Series_A_줄로_따라간다(logged_in, db):
    """기업 동기화(`company_sync`)로 따라 고친 매출도 그 줄의 문구를 따라 바꾼다."""
    from app.models import IrCompany, SeriesACompany

    company = IrCompany(name="샘플바사푸드", one_liner="사람이 쓴 IR 소개")
    db.add(company)
    db.commit()
    row = SeriesACompany(name="샘플바사푸드")
    db.add(row)
    db.commit()
    assert _get(db, SeriesACompany, row.id).ir_company_id == company.id

    logged_in.patch(f"/api/companies/{company.id}", json={"revenue_2027": "8"})
    row = _get(db, SeriesACompany, row.id)
    assert row.revenue_2027 == "8억"
    assert row.deal_pitch == "매출 27년(예상) 8억"
    assert _get(db, IrCompany, company.id).one_liner == "사람이 쓴 IR 소개"
