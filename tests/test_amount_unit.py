"""금액 칸에 숫자만 적으면 `억` 이 붙어 저장된다(#217).

팀원 요청: "투자유치희망금액, Pre value, 년도별 매출액 — 만원 단위 안 쓰면 억 단위 자동으로".

  ① 규칙(`amount.with_unit`) — 단위 없는 맨숫자에만 `억` 을 붙인다. 단위 · 구간 · 글 · `0` ·
     억으로 읽기엔 너무 큰 숫자(만원 · 원으로 적었을 수 있다)는 적은 그대로.
  ② IR 기업 현황 · Series A 표에서 고치면 저장값이 `30억` 이고, 응답도 그 값을 준다(화면이 되그린다).
  ③ [수정] 창은 모든 칸을 한 번에 보낸다 — 안 고친 칸(이미 적혀 있던 `40`)은 손대지 않는다.
  ④ 이미 저장된 맨숫자를 한 번 맞추는 스크립트 — 미리보기가 기본, 다시 돌리면 할 일이 없다.

값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize("typed, stored", [
    ("30", "30억"),
    (" 30 ", "30억"),
    ("2.5", "2.5억"),
    ("0.5", "0.5억"),
    ("1,200", "1200억"),
    ("9999", "9999억"),
])
def test_맨숫자에는_억이_붙는다(typed, stored):
    from app.services import amount

    assert amount.with_unit(typed) == stored


@pytest.mark.parametrize("typed", [
    "", "0", "-", "~", "확인중", "30억", "30억원", "5천만원", "4700만원", "5천만",
    "5-10", "10~20", "5-10억 사이", "약 30", "30억(예상)", "$5M", "1,224백만원",
    # 1만 이상은 억으로 읽기엔 너무 크다(1조) — 만원 · 원으로 적었을 수 있어 짐작하지 않는다.
    "10000", "35000", "1,500,000,000",
])
def test_그_밖은_적은_그대로(typed):
    from app.services import amount

    assert amount.with_unit(typed) == typed.strip()


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플금액테크", funding_total="40", pre_value="120억")
    db.add(row)
    db.commit()
    return row


def test_IR_표에서_숫자만_적으면_억으로_저장되고_응답이_그_값을_준다(logged_in, db, company):
    r = logged_in.patch(f"/api/companies/{company.id}", json={"raise_target": "30"})
    assert r.status_code == 200, r.text
    assert r.json()["amounts"] == {"raise_target": "30억"}
    for field, typed, stored in (("revenue_2025", "12.5", "12.5억"),
                                 ("revenue_recent", "3", "3억"),
                                 ("pre_value", "5천만원", "5천만원"),
                                 ("revenue_2027", "10-20", "10-20")):
        r = logged_in.patch(f"/api/companies/{company.id}", json={field: typed})
        assert r.json()["amounts"] == {field: stored}
    db.refresh(company)
    assert (company.raise_target, company.revenue_2025, company.revenue_recent,
            company.pre_value, company.revenue_2027) == ("30억", "12.5억", "3억", "5천만원", "10-20")


def test_수정_창이_다시_보낸_안_고친_칸은_그대로(logged_in, db, company):
    """[수정] 창은 모든 칸을 보낸다 — 이미 적혀 있던 맨숫자 `40` 을 몰래 고치지 않는다
    (수정 로그에 사람이 안 고친 칸이 고친 것으로 남는다). 이미 있는 값은 스크립트가 맞춘다."""
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"funding_total": "40", "raise_target": "25", "note": "메모"})
    assert r.status_code == 200, r.text
    db.refresh(company)
    assert (company.funding_total, company.raise_target) == ("40", "25억")


def test_새_기업도_억으로_저장된다(logged_in, db):
    from app.models import IrCompany

    r = logged_in.post("/api/companies", json={"name": "샘플새기업", "pre_value": "80"})
    assert r.status_code == 200, r.text
    assert db.get(IrCompany, r.json()["id"]).pre_value == "80억"


def test_Series_A_표도_억으로_저장되고_응답이_그_값을_준다(logged_in, db):
    from app.models import SeriesACompany

    row = SeriesACompany(name="샘플시리즈에이", raise_target="50")
    db.add(row)
    db.commit()
    r = logged_in.patch(f"/api/series-a-companies/{row.id}",
                        json={"raise_target": "30", "revenue_2026": "4.5", "funding_total": "~"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert (data["raise_target"], data["revenue_2026"], data["funding_total"]) == ("30억", "4.5억", "~")


# --- 이미 저장된 맨숫자를 한 번 맞추는 스크립트 ------------------------------------

@pytest.fixture()
def old_values(db):
    from app.models import IrCompany, SeriesACompany

    rows = {"ir": IrCompany(name="샘플옛값", raise_target="30", revenue_recent="2.5",
                            pre_value="100억", funding_total="0", revenue_2024="50000000"),
            "sa": SeriesACompany(name="샘플옛딜", pre_value="70", revenue_2025="확인중")}
    db.add_all(rows.values())
    db.commit()
    return rows


def _values(db, rows):
    from app.models import IrCompany, SeriesACompany

    db.expire_all()
    ir, sa = db.get(IrCompany, rows["ir"].id), db.get(SeriesACompany, rows["sa"].id)
    return (ir.raise_target, ir.revenue_recent, ir.pre_value, ir.funding_total, ir.revenue_2024,
            sa.pre_value, sa.revenue_2025)


def test_스크립트_미리보기는_DB_에_안_쓴다(db, old_values, capsys):
    from scripts import amount_unit_fill

    before = _values(db, old_values)
    assert amount_unit_fill.main([]) == 0
    assert _values(db, old_values) == before
    out = capsys.readouterr().out
    assert "미리보기" in out
    assert "[IR 기업 현황] 바뀜 2" in out
    assert "raise_target 1" in out and "revenue_recent 1" in out
    assert "[Series A 이상 딜 소싱] 바뀜 1" in out


def test_스크립트_저장은_수정_로그에_남고_다시_돌려도_같다(db, users, old_values, capsys):
    from app.models import EditLog
    from scripts import amount_unit_fill

    assert amount_unit_fill.main(["--apply"]) == 2      # 수정 로그 계정 없이는 안 돈다
    assert amount_unit_fill.main(["--apply", "--user-id", str(users["u1"].id)]) == 0
    got = _values(db, old_values)
    assert got == ("30억", "2.5억", "100억", "0", "50000000", "70억", "확인중")
    fields = {c["field"] for log in db.query(EditLog).filter(EditLog.actor_user_id == users["u1"].id)
              for c in json.loads(log.changes_json)}
    assert {"raise_target", "revenue_recent", "pre_value"} <= fields
    capsys.readouterr()
    assert amount_unit_fill.main(["--apply", "--user-id", str(users["u1"].id)]) == 0
    assert "[IR 기업 현황] 바뀜 0" in capsys.readouterr().out
    assert _values(db, old_values) == got


def test_스크립트가_붙인_억은_이어진_줄의_다른_값을_덮지_않는다(db, users):
    """`70` → `70억` 은 고친 것이 아니다(`company_sync.norm`) — 이어진 IR 의 다른 값(`100억`)을
    덮지 않고, IR 의 `30` → `30억` 도 Series A 의 따로 쓰는 값을 안 덮는다."""
    from app.models import IrCompany, SeriesACompany
    from scripts import amount_unit_fill

    ir = IrCompany(name="샘플이음", pre_value="100억", raise_target="30")
    db.add(ir)
    db.commit()
    sa = SeriesACompany(name="샘플이음")
    db.add(sa)
    db.commit()
    assert sa.ir_company_id == ir.id
    table = SeriesACompany.__table__
    db.execute(table.update().where(table.c.id == sa.id).values(pre_value="70", raise_target="25"))
    db.commit()

    assert amount_unit_fill.main(["--apply", "--user-id", str(users["u1"].id)]) == 0
    db.expire_all()
    ir, sa = db.get(IrCompany, ir.id), db.get(SeriesACompany, sa.id)
    assert (ir.pre_value, ir.raise_target) == ("100억", "30억")
    assert (sa.pre_value, sa.raise_target) == ("70억", "25억")
