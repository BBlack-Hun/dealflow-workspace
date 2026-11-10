"""딜 소개 문구에 연도별 매출이 **한 해만** 실리던 줄 · `(예상)` 이 두 번 찍히던 줄(과제 214 — 11/10).

요청: "IR 기업현황 년매출액 > 딜소개 문구에 한해 거만 들어간 경우가 보입니다. 년매출액
딜소개문구에 모두 빠지지 않게 자동으로 기입되게 해주세요."

조합(`services/one_liner.compose_one_liner`)은 이미 칸에 든 해를 모두 싣는다. 한 해만
실리던 것은 **기업 한줄 소개 안에 `매출 13억` 토막이 따로 적혀 온 줄**이다 — 앞에서 이미
'매출' 을 말했다고 보고 칸의 여러 해를 통째로 건너뛰었다. 이제 그 토막이 **매출만 적힌
토막**이면 그 자리에 칸의 여러 해를 싣는다. 문장 속에 섞인 매출은 예전처럼 둔다.

`27년(예상)` 칸에 값을 `30억(예상)` 으로 적으면 `27년(예상) 30억(예상)` 으로 두 번 찍혔다.

규칙이 바뀌면 **예전 규칙으로 만든 자동 문구가 '사람이 쓴 글' 로 오판**된다 — 그 줄은
재료를 고쳐도 안 따라온다. 예전 규칙의 조합값도 자동으로 알아보고(`_auto_texts`), 배포 뒤
한 번 그 줄들을 새 규칙으로 다시 조합하는 스크립트(`scripts/one_liner_214_recompose.py`)를
둔다. 사람이 쓴 문구는 어느 쪽에서도 안 바뀐다.

검사의 올해는 2026 이다(tests/conftest.py). 이름 · 값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.one_liner import compose_one_liner, one_liner_status, series_a_revenue


def make(**kw):
    fields = dict(business_desc=None, revenue_2022=None, revenue_2023=None, revenue_2024=None,
                  revenue_2025=None, revenue_recent=None, revenue_2027=None, funding_total=None,
                  raise_target=None, pre_value=None, competitiveness=None, one_liner=None)
    fields.update(kw)
    return SimpleNamespace(**fields)


# ── 매출만 적힌 토막은 칸의 여러 해로 ────────────────────────────────────────

def test_한줄_소개의_매출_토막_자리에_칸의_여러_해가_선다():
    made = compose_one_liner(make(business_desc="물류 최적화 SaaS | 매출 3억 | 누적투자금액 10억",
                                  revenue_2024="2억", revenue_2025="3억", revenue_recent="4"))
    assert made == "물류 최적화 SaaS | 매출 24년 2억, 25년 3억, 26년 4억 | 누적투자금액 10억"


@pytest.mark.parametrize("written", ["매출 3억", "매출액 3억", "25년 매출 3억", "2025년 매출 3억",
                                     "매출액: 3.2억", "매출 3억(25년 기준)", "매출 3억 예상"])
def test_매출만_적힌_토막은_모양이_달라도_바뀐다(written):
    made = compose_one_liner(make(business_desc=f"결제 대행 | {written}",
                                  revenue_2024="2억", revenue_2025="3억"))
    assert made == "결제 대행 | 매출 24년 2억, 25년 3억"


@pytest.mark.parametrize("desc", ["작년 매출 30억을 달성한 결제 대행",
                                  "결제 대행 | 매출 3억 흑자 전환"])
def test_말이_섞인_매출은_예전처럼_두고_칸을_덧붙이지_않는다(desc):
    """문장 속 매출을 떼어 내면 사람이 쓴 말이 잘린다 — 겹쳐 적지도 않는다(예전 그대로)."""
    made = compose_one_liner(make(business_desc=desc, revenue_2024="2억", revenue_2025="3억"))
    assert made == desc


def test_칸에_한_해뿐이면_한줄_소개의_매출을_그대로_둔다():
    """연도 없는 `매출 13억` 을 다른 해 한 칸으로 바꾸면 어느 해인지 흐려진다 — 예전 그대로."""
    made = compose_one_liner(make(business_desc="측정 엔진 | 매출 13억", revenue_2024="9억"))
    assert made == "측정 엔진 | 매출 13억"


def test_매출_토막이_둘이면_첫_자리에_하나만_선다():
    made = compose_one_liner(make(business_desc="결제 대행 | 매출 3억 | TIPS | 25년 매출 3억",
                                  revenue_2024="2억", revenue_2025="3억"))
    assert made == "결제 대행 | 매출 24년 2억, 25년 3억 | TIPS"


# ── (예상) 이 두 번 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("written, shown", [("30억(예상)", "30억"), ("30억 (예상)", "30억"),
                                            ("30억+(예상)", "30억+"), ("예상 30억", "30억"),
                                            ("30", "30억")])
def test_예상_칸의_값에_예상이_적혀도_한_번만_찍힌다(written, shown):
    made = compose_one_liner(make(business_desc="결제 대행", revenue_2025="3억",
                                  revenue_2027=written))
    assert made == f"결제 대행 | 매출 25년 3억, 27년(예상) {shown}"
    assert made.count("예상") == 1


def test_예상_칸만_있어도_한_번만():
    assert compose_one_liner(make(revenue_2027="8억(예상)")) == "매출 27년(예상) 8억"


def test_올해_칸의_예상은_그대로_둔다():
    """`26년` 에는 `(예상)` 이 안 붙으므로 사람이 적은 `(예상)` 이 그 해가 예상임을 알리는 유일한 표시다."""
    made = compose_one_liner(make(business_desc="결제 대행", revenue_2025="3억",
                                  revenue_recent="15억(예상)"))
    assert made == "결제 대행 | 매출 25년 3억, 26년 15억(예상)"


def test_Series_A_줄도_예상이_한_번만():
    row = SimpleNamespace(revenue_2025="3", revenue_2027="8억(예상)")
    assert compose_one_liner(row, series_a_revenue()) == "매출 25년 3억, 27년(예상) 8억"


# ── 예전 규칙으로 만든 자동 문구 ────────────────────────────────────────────

OLD_DESC = "물류 최적화 SaaS | 매출 3억"
#: 과제 214 전 규칙의 조합값 — 한줄 소개의 `매출 3억` 때문에 칸의 여러 해가 빠졌다.
OLD_AUTO = "물류 최적화 SaaS | 매출 3억"
NEW_AUTO = "물류 최적화 SaaS | 매출 24년 2억, 25년 3억"


def test_예전_규칙의_조합값도_자동으로_읽는다():
    row = make(business_desc=OLD_DESC, revenue_2024="2억", revenue_2025="3억", one_liner=OLD_AUTO)
    status = one_liner_status(row)
    assert status["suggestion"] == NEW_AUTO
    assert status["origin"] == "auto" and status["kept"] is False

    doubled = make(business_desc="결제 대행", revenue_2025="3억", revenue_2027="8억(예상)",
                   one_liner="결제 대행 | 매출 25년 3억, 27년(예상) 8억(예상)")
    assert one_liner_status(doubled)["origin"] == "auto"


def test_사람이_쓴_한_해짜리_문구는_사람_문구다():
    row = make(business_desc=OLD_DESC, revenue_2024="2억", revenue_2025="3억",
               one_liner="물류 SaaS, 작년 매출 3억")
    assert one_liner_status(row)["origin"] == "manual"


def _old_auto_company(db, one_liner=OLD_AUTO):
    from app.models import IrCompany

    row = IrCompany(name="샘플가나물류", business_desc=OLD_DESC, revenue_2024="2억",
                    revenue_2025="3억")
    db.add(row)
    db.commit()
    # 예전 규칙이 만들어 둔 문구(또는 사람이 쓴 문구)를 재료는 그대로 둔 채 넣는다.
    t = IrCompany.__table__
    db.execute(t.update().where(t.c.id == row.id).values(one_liner=one_liner))
    db.commit()
    db.expire_all()
    return row


def test_예전_규칙의_자동_문구는_재료를_고치면_새_규칙으로_따라온다(logged_in, db):
    from app.models import IrCompany

    row = _old_auto_company(db)
    r = logged_in.patch(f"/api/companies/{row.id}", json={"funding_total": "10"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(IrCompany, row.id).one_liner == NEW_AUTO + " | 누적투자금액 10억"


def test_사람이_쓴_문구는_재료를_고쳐도_그대로(logged_in, db):
    from app.models import IrCompany

    row = _old_auto_company(db, one_liner="물류 SaaS, 작년 매출 3억")
    logged_in.patch(f"/api/companies/{row.id}", json={"funding_total": "10"})
    db.expire_all()
    assert db.get(IrCompany, row.id).one_liner == "물류 SaaS, 작년 매출 3억"


# ── 배포 뒤 한 번 돌리는 스크립트 ───────────────────────────────────────────

@pytest.fixture()
def rows(db):
    """예전 자동 · 예상 두 번 · 사람이 쓴 문구 · 이미 새 모양 · 빈 문구 — 다섯 줄."""
    from app.models import IrCompany

    made = {
        "old": IrCompany(name="샘플가나", business_desc=OLD_DESC, revenue_2024="2억",
                         revenue_2025="3억"),
        "dbl": IrCompany(name="샘플다라", business_desc="결제 대행", revenue_2025="3억",
                         revenue_2027="8억(예상)"),
        "man": IrCompany(name="샘플마바", business_desc=OLD_DESC, revenue_2024="2억",
                         revenue_2025="3억"),
        "new": IrCompany(name="샘플사아", business_desc="교육 플랫폼", revenue_2024="1억",
                         revenue_2025="2억"),
        "emp": IrCompany(name="샘플자차", business_desc="교육 플랫폼", revenue_2025="2억"),
    }
    db.add_all(made.values())
    db.commit()
    text = {"old": OLD_AUTO, "dbl": "결제 대행 | 매출 25년 3억, 27년(예상) 8억(예상)",
            "man": "물류 SaaS, 작년 매출 3억", "new": "교육 플랫폼 | 매출 24년 1억, 25년 2억",
            "emp": None}
    t = IrCompany.__table__
    for key, value in text.items():
        db.execute(t.update().where(t.c.id == made[key].id).values(one_liner=value))
    db.commit()
    db.expire_all()
    return {k: v.id for k, v in made.items()}


def _texts(db, rows):
    from app.models import IrCompany

    db.expire_all()
    return {k: db.get(IrCompany, i).one_liner for k, i in rows.items()}


def test_스크립트_미리보기는_DB_에_안_쓴다(db, rows, capsys):
    from scripts import one_liner_214_recompose as script

    before = _texts(db, rows)
    assert script.main([]) == 0
    assert _texts(db, rows) == before
    out = capsys.readouterr().out
    assert "미리보기" in out
    assert "다시 조합 2" in out and "사람 문구 그대로 1" in out
    assert "샘플" not in out, "기업명은 찍지 않는다"


def test_스크립트_저장은_예전_자동만_바꾸고_되돌릴_수_있다(db, users, rows, logged_in, u1_admin,
                                              capsys):
    from app.models import EditLog, OneLinerBackup
    from scripts import one_liner_214_recompose as script

    before = _texts(db, rows)
    assert script.main(["--apply"]) == 2          # 수정 로그 계정 없이는 안 돈다
    assert script.main(["--apply", "--user-id", str(users["u1"].id)]) == 0
    got = _texts(db, rows)
    assert got["old"] == NEW_AUTO
    assert got["dbl"] == "결제 대행 | 매출 25년 3억, 27년(예상) 8억"
    assert {k: got[k] for k in ("man", "new", "emp")} == \
        {k: before[k] for k in ("man", "new", "emp")}, "사람 문구 · 새 모양 · 빈 문구는 그대로"

    saved = db.query(OneLinerBackup).all()
    assert {(s.company_id, s.previous) for s in saved} == \
        {(rows["old"], before["old"]), (rows["dbl"], before["dbl"])}
    assert len({s.batch for s in saved}) == 1
    assert db.query(EditLog).filter(EditLog.actor_user_id == users["u1"].id,
                                    EditLog.table_name == "ir_companies").count() == 2

    capsys.readouterr()
    assert script.main(["--apply", "--user-id", str(users["u1"].id)]) == 0
    assert "다시 조합 0" in capsys.readouterr().out, "다시 돌리면 할 일이 없다"

    # [전체 자동조합] 의 [되돌리기] 가 이 묶음을 되돌린다.
    r = logged_in.post("/api/one-liner/bulk/undo")
    assert r.status_code == 200, r.text
    assert r.json()["restored"] == 2
    assert _texts(db, rows) == before
