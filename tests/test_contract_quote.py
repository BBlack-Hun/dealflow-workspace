"""계약 완료면 빈 `견적서 첨부 여부` 에 `O`(i255 · `services/contract_quote`).

요청: "IR 기업현황 > 계약여부 칼럼에서 계약완료이면 견적서 첨부여부에 O 자동으로 기입되게,
투자컨설턴트 메뉴에서도 동일하게 적용해 주세요".

  1. IR — 무료 · 유료계약완료로 적히면 빈 견적서 칸이 `O`. 이미 적힌 값(`X`)은 그대로,
     다른 계약 값(진행중 · 검토중 · 미팅 · 딜소개 불가)은 안 바뀐다. 새 줄도 같다.
  2. 투자컨설턴트 — 관리 스타트업 탭의 같은 두 칸(`contract_done` → `contract_management`).
  3. 이어진 줄은 따라 고치기로 — 빈칸만(사람이 적은 `X` 는 그대로).
  4. 시트 올리기(IR · 투자컨설턴트)도 같은 자리를 지난다.
  5. 이미 계약 완료였던 줄은 다른 칸을 고쳐도 저절로 안 채운다(한 번 채우기는 스크립트).

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def tabs(db, users):
    from app.services import consulting_sheets as cs

    users["u1"].can_view_consulting = 1
    db.commit()
    return {s.kind: s.label for s in cs.ensure(db)}


def _fresh(db, *rows):
    db.expire_all()
    return [db.get(type(r), r.id) for r in rows]


def _meta(db, users, sheet, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=users["u1"].id, sheet=sheet, position=1, **kw)
    db.add(row)
    db.commit()
    return row


# ── 1. IR 기업 현황 ─────────────────────────────────────────────────────────

def test_IR_계약완료로_바꾸면_빈_견적서_칸이_O(db, users):
    from app.models import IrCompany

    paid = IrCompany(name="샘플유료", contract_status="none")
    free = IrCompany(name="샘플무료", contract_status="in_progress")
    kept = IrCompany(name="샘플엑스", contract_status="none", quote_attached="X")
    db.add_all([paid, free, kept])
    db.commit()

    paid.contract_status, free.contract_status = "paid", "무료계약완료"
    kept.contract_status = "유료계약완료"
    db.commit()
    paid, free, kept = _fresh(db, paid, free, kept)
    assert (paid.quote_attached, free.quote_attached) == ("O", "O")
    assert kept.quote_attached == "X"           # 사람이 적은 값은 덮지 않는다


@pytest.mark.parametrize("status", ["in_progress", "review", "free_meet_planned",
                                    "free_meet_done", "blocked", "none"])
def test_IR_다른_계약_값이면_안_바뀐다(db, users, status):
    from app.models import IrCompany

    ir = IrCompany(name="샘플다른값", contract_status="no")
    db.add(ir)
    db.commit()
    ir.contract_status = status
    db.commit()
    assert _fresh(db, ir)[0].quote_attached is None


def test_IR_새_줄도_계약완료면_O(db, users):
    from app.models import IrCompany

    new = IrCompany(name="샘플새줄", contract_status="paid")
    plain = IrCompany(name="샘플미계약")
    db.add_all([new, plain])
    db.commit()
    new, plain = _fresh(db, new, plain)
    assert new.quote_attached == "O" and plain.quote_attached is None


def test_IR_화면에서_고치면_응답에_채워진_견적서_칸이_온다(logged_in, db):
    from app.models import IrCompany

    ir = IrCompany(name="샘플화면", contract_status="none")
    db.add(ir)
    db.commit()
    data = logged_in.patch(f"/api/companies/{ir.id}",
                           json={"contract_status": "유료계약완료"}).json()
    assert data["quote_attached"] == "O"     # 표가 이 값으로 견적서 칸을 되그린다(companies.js)
    assert _fresh(db, ir)[0].quote_attached == "O"


def test_이미_계약완료인_줄은_다른_칸을_고쳐도_안_채운다(db, users):
    """한 번 채우기는 스크립트가 한다(i255 — 백업 뒤 운영에서)."""
    from app.models import IrCompany

    ir = IrCompany(name="샘플옛계약", contract_status="paid")
    db.add(ir)
    db.commit()
    ir.quote_attached = None
    db.commit()
    ir = _fresh(db, ir)[0]
    ir.note = "메모만 고침"
    db.commit()
    assert _fresh(db, ir)[0].quote_attached is None


# ── 2. 투자컨설턴트 ─────────────────────────────────────────────────────────

def test_투자컨설턴트_계약완료로_바꾸면_빈_견적서_칸이_O(db, users, tabs):
    paid = _meta(db, users, tabs["startup"], company_name="샘플컨설유료")
    kept = _meta(db, users, tabs["startup"], company_name="샘플컨설엑스",
                 contract_management="X")
    hand = _meta(db, users, tabs["handover"], company_name="샘플전달")
    paid.contract_done = kept.contract_done = "유료계약완료"
    hand.contract_done = "무료계약완료"     # 그 탭에는 두 칸이 안 선다 — 안 건드린다
    db.commit()
    paid, kept, hand = _fresh(db, paid, kept, hand)
    assert paid.contract_management == "O" and paid.ir_company_id is None
    assert kept.contract_management == "X"
    assert hand.contract_management is None
    assert "contract_management" in (paid.field_stamps or "")   # `수정한 날짜` 도 찍힌다


def test_투자컨설턴트_다른_값이면_안_바뀐다(db, users, tabs):
    row = _meta(db, users, tabs["startup"], company_name="샘플컨설진행")
    row.contract_done = "무료계약진행중"     # 옛 자유 글 — 계약 완료가 아니다
    db.commit()
    assert _fresh(db, row)[0].contract_management is None


def test_투자컨설턴트_화면에서_고치면_응답에_채워진_견적서_칸이_온다(client, db, users, tabs):
    from .conftest import DEMO_PASSWORD

    row = _meta(db, users, tabs["startup"], company_name="샘플컨설화면")
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    res = client.patch(f"/api/consulting/{row.id}", json={"contract_done": "무료계약완료"})
    assert res.status_code == 200, res.text
    assert res.json()["values"] == {"contract_done": "무료계약완료", "contract_management": "O"}


# ── 3. 이어진 줄 ────────────────────────────────────────────────────────────

def _linked(db, users, tabs, name, **meta_kw):
    from app.models import IrCompany

    ir = IrCompany(name=name, contract_status="none")
    db.add(ir)
    db.commit()
    meta = _meta(db, users, tabs["startup"], company_name=name, **meta_kw)
    assert meta.ir_company_id == ir.id
    return _fresh(db, ir, meta)


def test_IR_에서_바꾸면_이어진_투자컨설턴트_줄의_빈칸도_O(db, users, tabs):
    ir, meta = _linked(db, users, tabs, "샘플이음하나")
    ir.contract_status = "paid"
    db.commit()
    ir, meta = _fresh(db, ir, meta)
    assert meta.contract_done == "유료계약완료"
    assert (ir.quote_attached, meta.contract_management) == ("O", "O")


def test_투자컨설턴트에서_바꾸면_IR_의_빈칸도_O(db, users, tabs):
    ir, meta = _linked(db, users, tabs, "샘플이음둘")
    meta.contract_done = "무료계약완료"
    db.commit()
    ir, meta = _fresh(db, ir, meta)
    assert ir.contract_status == "free"
    assert (ir.quote_attached, meta.contract_management) == ("O", "O")


def test_이어진_줄에_사람이_적은_X_는_그대로(db, users, tabs):
    from app.services import company_sync

    ir, meta = _linked(db, users, tabs, "샘플이음셋")
    meta.contract_management = "X"
    db.commit()
    ir, meta = _fresh(db, ir, meta)
    assert ir.quote_attached == "X"            # 따라 고치기로 IR 에도 들었다
    ir.quote_attached = None                   # IR 만 비워 둔다(비우기는 안 따라간다)
    db.commit()
    ir, meta = _fresh(db, ir, meta)
    ir.contract_status = "paid"
    db.commit()
    ir, meta = _fresh(db, ir, meta)
    assert ir.quote_attached == "O" and meta.contract_management == "X"
    assert [d["field"] for d in company_sync.differences(db, [meta])[meta.id]] == \
        ["quote_attached"]                     # 사람이 `값 다름` 에서 고른다


# ── 4. 시트 올리기 ──────────────────────────────────────────────────────────

def test_IR_시트_가져오기도_계약완료면_O(db, users):
    from app.models import IrCompany
    from app.services import sheet_import as si

    ir = IrCompany(name="샘플시트", contract_status="no")
    db.add(ir)
    db.commit()
    si.apply_sheet_b(db, si.SheetBParse(companies=[
        si.ParsedCompany(row_no=1, name="샘플시트", contract_status="paid"),
        si.ParsedCompany(row_no=2, name="샘플시트새줄", contract_status="free"),
        si.ParsedCompany(row_no=3, name="샘플시트미계약", contract_status="no")]))
    db.expire_all()
    got = {c.name: c.quote_attached for c in db.query(IrCompany).all()}
    assert got == {"샘플시트": "O", "샘플시트새줄": "O", "샘플시트미계약": None}


def test_투자컨설턴트_시트_올리기도_계약완료면_O(db, users, tabs):
    from app.models import ConsultingCompany
    from app.routers.consulting import apply_rows

    _meta(db, users, tabs["startup"], company_name="샘플올림기존")
    parsed = {"columns": [], "companies": [
        {"notes": {}, "company_name": "샘플올림기존", "contract_done": "유료계약완료"},
        {"notes": {}, "company_name": "샘플올림새줄", "contract_done": "무료계약완료"},
        {"notes": {}, "company_name": "샘플올림엑스", "contract_done": "유료계약완료",
         "contract_management": "X"},
        {"notes": {}, "company_name": "샘플올림진행", "contract_done": "계약 진행중"}]}
    apply_rows(db, parsed, users["u1"])
    db.expire_all()
    got = {r.company_name: r.contract_management for r in db.query(ConsultingCompany).all()}
    assert got == {"샘플올림기존": "O", "샘플올림새줄": "O", "샘플올림엑스": "X",
                   "샘플올림진행": None}


# ── 5. 한 번 채우기 — 스크립트가 부르는 같은 함수 ──────────────────────────

def test_fill_은_계약완료인_빈칸만_채운다(db, users, tabs):
    from app.models import IrCompany
    from app.services import company_sync, contract_quote

    rows = [IrCompany(name="샘플채움1", contract_status="paid"),
            IrCompany(name="샘플채움2", contract_status="free", quote_attached="X"),
            IrCompany(name="샘플채움3", contract_status="in_progress")]
    db.add_all(rows)
    db.commit()
    rows[0].quote_attached = None
    db.commit()
    kinds = company_sync.sheet_kinds(db)
    rows = _fresh(db, *rows)
    assert [contract_quote.fill(r, kinds) for r in rows] == [True, False, False]
    db.commit()
    assert [r.quote_attached for r in _fresh(db, *rows)] == ["O", "X", None]
