"""`계약년월` 칸(0129 · #122) — IR 기업 현황 · Series A 이상 딜 소싱.

요청: "IR 기업현황 > 미팅제공일자 > 오른쪽에 계약년월 컬럼 넣기 , Series A 이상 딜 소싱 ->
계약여부 왼쪽에 계약년월 컬럼넣기".

  1. 계약 완료로 **바뀌는 순간** 비어 있으면 그 달 — 이미 있으면 그대로, 새 줄 · 무료↔유료는 안 적는다
  2. 사람이 고친다 — `YYYY-MM` 으로 맞추고 못 읽으면 400, 비우기 됨
  3. IR ↔ Series A 따라 고치기
  4. 화면 자리
  5. 판(0129) 오르내리기

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import sqlite3

from .test_migrations import _alembic


def _ym():
    from app import clock

    return clock.today().isoformat()[:7]


def test_계약완료로_바뀌는_순간_빈_계약년월에_그_달이_들어간다(db, users):
    from app.models import IrCompany, SeriesACompany

    ir = IrCompany(name="샘플도장", contract_status="none")
    sa = SeriesACompany(name="샘플받음")
    kept = IrCompany(name="샘플이미", contract_status="review", contract_ym="2025-03")
    old = IrCompany(name="샘플옛계약", contract_status="paid")   # 새 줄 — 옛 계약일 수 있다
    db.add_all([ir, sa, kept, old])
    db.commit()
    assert old.contract_ym is None

    ir.contract_status, sa.contract_status, kept.contract_status = "paid", "free", "유료계약완료"
    db.commit()
    assert (ir.contract_ym, sa.contract_ym, kept.contract_ym) == (_ym(), _ym(), "2025-03")

    ir.contract_ym = None
    ir.contract_status = "free"                                   # 계약 완료끼리 — 안 적는다
    db.commit()
    assert ir.contract_ym is None
    ir.contract_status = "free_meet_done"                         # 계약이 아니다
    db.commit()
    assert ir.contract_ym is None


def test_YYYY_MM_으로_맞춰_고치고_못_읽으면_400(logged_in, db):
    from app.models import IrCompany, SeriesACompany

    ir = IrCompany(name="샘플고침", contract_status="none")
    sa = SeriesACompany(name="샘플받음")
    db.add_all([ir, sa])
    db.commit()

    url = f"/api/companies/{ir.id}"
    assert logged_in.patch(url, json={"contract_ym": "2026.3"}).json()["contract_ym"] == "2026-03"
    bad = logged_in.patch(url, json={"contract_ym": "내년"})
    assert bad.status_code == 400 and "YYYY-MM" in bad.json()["detail"]
    assert logged_in.patch(url, json={"contract_ym": " "}).json()["contract_ym"] == ""
    # 표에서 계약여부만 고쳐도 응답이 채워진 계약년월을 준다 — 화면이 그 칸을 되그린다.
    assert logged_in.patch(url, json={"contract_status": "유료계약완료"}).json()["contract_ym"] == _ym()

    data = logged_in.patch(f"/api/series-a-companies/{sa.id}", json={"contract_ym": "2027-1"}).json()
    assert data["contract_ym"] == "2027-01"
    db.expire_all()
    assert db.get(SeriesACompany, sa.id).contract_ym == "2027-01"


def test_IR_과_Series_A_가_따라_고친다(logged_in, db):
    from app.models import IrCompany, SeriesACompany

    ir = IrCompany(name="(주)샘플가람", contract_status="none")
    db.add(ir)
    db.commit()
    sa = SeriesACompany(name="샘플 가람")
    db.add(sa)
    db.commit()
    assert sa.ir_company_id == ir.id

    logged_in.patch(f"/api/series-a-companies/{sa.id}", json={"contract_ym": "2026-05"})
    db.expire_all()
    assert db.get(IrCompany, ir.id).contract_ym == "2026-05"


# ── 3-1. 저절로 들어간 계약년월도 이어진 줄로 간다(#206 · 11/10) ─────────────────
#
# 계약 완료로 바뀌는 순간 비어 있는 계약년월에 그 달을 적는 자리(`contract_day7.before_flush`)는
# 따라 고치기(`company_sync.before_flush`) **뒤에** 돈다 — 줄에서 IR 로 따라 온 계약여부까지
# 읽어야 해서다. 그래서 그 달이 IR(과 계약여부가 따라 바뀐 Series A 줄)에만 들고 이어진
# 투자컨설턴트 메타 줄은 빈칸으로 남았다(운영 11/10 1건). 이제 빈칸이면 같은 달이 든다.

def _linked_rows(db, users, name):
    from app.models import ConsultingCompany, IrCompany, SeriesACompany
    from app.services import consulting_sheets as cs

    tabs = {s.kind: s.label for s in cs.ensure(db)}
    ir = IrCompany(name=name, contract_status="none")
    db.add(ir)
    db.commit()
    meta = ConsultingCompany(user_id=users["u1"].id, sheet=tabs["startup"], position=1,
                             company_name=name)
    sa = SeriesACompany(name=name)
    db.add_all([meta, sa])
    db.commit()
    assert meta.ir_company_id == ir.id and sa.ir_company_id == ir.id
    return _fresh(db, ir, meta, sa)        # 화면 요청처럼 DB 에서 새로 읽은 줄로 고친다


def _fresh(db, *rows):
    db.expire_all()
    return [db.get(type(r), r.id) for r in rows]


def test_IR_을_계약완료로_바꾸면_저절로_든_계약년월이_이어진_줄에도_든다(db, users):
    ir, meta, sa = _linked_rows(db, users, "샘플달따라")
    ir.contract_status = "paid"
    db.commit()
    ir, meta, sa = _fresh(db, ir, meta, sa)
    assert (ir.contract_ym, meta.contract_ym, sa.contract_ym) == (_ym(), _ym(), _ym())
    assert meta.contract_done == "유료계약완료"


def test_투자컨설턴트에서_계약완료로_고쳐도_그_줄에_계약년월이_든다(db, users):
    ir, meta, sa = _linked_rows(db, users, "샘플줄에서")
    meta.contract_done = "무료계약완료"
    db.commit()
    ir, meta, sa = _fresh(db, ir, meta, sa)
    assert ir.contract_status == "free"
    assert (ir.contract_ym, meta.contract_ym, sa.contract_ym) == (_ym(), _ym(), _ym())


def test_Series_A_에서_계약완료로_고쳐도_IR_과_메타_줄에_든다(db, users):
    ir, meta, sa = _linked_rows(db, users, "샘플딜소싱")
    sa.contract_status = "paid"
    db.commit()
    ir, meta, sa = _fresh(db, ir, meta, sa)
    assert (ir.contract_ym, meta.contract_ym, sa.contract_ym) == (_ym(), _ym(), _ym())


def test_이어진_줄에_적힌_계약년월은_저절로_덮지_않는다(db, users):
    ir, meta, sa = _linked_rows(db, users, "샘플이미적음")
    meta.contract_ym = "2024-07"
    db.commit()
    ir, meta, sa = _fresh(db, ir, meta, sa)
    assert (ir.contract_ym, sa.contract_ym) == ("2024-07", "2024-07")   # 손으로 적은 달은 따라간다
    ir.contract_ym = sa.contract_ym = None      # IR · Series A 만 비운다(비우기는 안 따라간다)
    db.commit()
    ir.contract_status = "paid"
    db.commit()
    ir, meta, sa = _fresh(db, ir, meta, sa)
    # IR · 빈 Series A 에는 그 달, 메타 줄에 적혀 있던 달은 그대로(`값 다름` 에 선다).
    assert (ir.contract_ym, meta.contract_ym, sa.contract_ym) == (_ym(), "2024-07", _ym())


def _heads(html: str, table: str) -> list:
    thead = re.search(rf'id="{table}".*?</thead>', html, re.S).group(0)
    return [re.sub(r"<[^>]+>", "", t).strip()
            for t in re.findall(r"<th\b[^>]*>(.*?)</th>", thead, re.S)]


def test_IR_은_미팅제공일자_오른쪽_Series_A_는_계약여부_왼쪽(logged_in, db):
    from app.models import IrCompany, SeriesACompany

    db.add_all([IrCompany(name="샘플자리", contract_ym="2026-09"), SeriesACompany(name="샘플받음")])
    db.commit()

    heads = _heads(logged_in.get("/companies").text, "co-table")
    at = heads.index("계약년월")
    assert heads[at - 1:at + 2] == ["미팅제공일자", "계약년월", "계약여부"], heads
    heads = _heads(logged_in.get("/companies?tab=series-a").text, "sa-table")
    assert heads[heads.index("계약년월") + 1] == "계약여부", heads


def _cols(db, table) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
    finally:
        con.close()


def test_0129_는_두_표에_칸을_붙이고_되돌리면_뗀다(tmp_path):
    db = tmp_path / "old.db"
    tables = ("ir_companies", "series_a_companies")
    assert _alembic(db, "upgrade", "0128_forecast_follow_round").returncode == 0
    # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
    con = sqlite3.connect(db)
    try:
        for table in tables:
            con.execute(f"ALTER TABLE {table} DROP COLUMN contract_ym")
        con.commit()
    finally:
        con.close()

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert all("contract_ym" in _cols(db, t) for t in tables)

    down = _alembic(db, "downgrade", "0128_forecast_follow_round")
    assert down.returncode == 0, down.stdout + down.stderr
    assert not any("contract_ym" in _cols(db, t) for t in tables)
