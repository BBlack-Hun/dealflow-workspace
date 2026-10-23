"""같은 기업 칸 따라 고치기(1단계) — IR 기업 현황 ↔ 투자컨설턴트 ↔ 스타트업 명단.

지키는 것(`services/company_sync.py` 머리말 · 10/22 결정):

1. 새 줄은 이름이 **정확히 하나** 맞으면 저절로 잇고 `자동 연결` 로 적는다(결정 2).
2. 잇는 순간에는 **양쪽 빈칸만** 채운다. 다른 값은 덮지 않고 `값 다름` 에 선다(결정 5).
3. 고치면 따라 고친다 — 줄 → IR → 다른 줄, IR → 줄. 빈칸은 안 따라간다(결정 6).
4. O/X 칸은 O · X 만 옮기고, 자유 글은 옮기지도 덮지도 않는다.
5. 월간 계약 탭은 1단계에서 안 잇는다. 견적서 · 카톡 칸은 메타 탭만.
6. 시트 다시 올리기는 이어진 줄의 빈칸만 채우고, [전체 바꾸기]도 연결을 안 끊는다(결정 7).
7. IR 시트 가져오기는 앱에서 정한 계약여부를 덮지 않는다.

이름 · 번호는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json

import pytest

LIST = "샘플 스타트업 명단"
INVESTORS = "샘플 투자사 명단"


@pytest.fixture()
def stage(db, users):
    from app.models import IrCompany, SheetOwner
    from app.services import consulting_sheets as cs
    from app.services import contact_columns as cc

    users["u1"].can_view_consulting = 1
    db.add_all([
        SheetOwner(label=LIST, user_id=users["u1"].id, layout=cc.STARTUP, is_hidden=1),
        SheetOwner(label=INVESTORS, user_id=users["u1"].id, layout=cc.INVESTOR),
    ])
    ir = IrCompany(name="(주)샘플가람", contact_phone="010-0000-1111")
    twin1, twin2 = IrCompany(name="샘플쌍둥"), IrCompany(name="샘플 쌍둥(주)")
    db.add_all([ir, twin1, twin2])
    db.commit()
    sheets = {s.kind: s.label for s in cs.ensure(db)}
    return {"ir": ir, "sheets": sheets}


def _consulting(db, users, sheet, **kw):
    from app.models import ConsultingCompany

    row = ConsultingCompany(user_id=users["u1"].id, sheet=sheet, position=1, **kw)
    db.add(row)
    db.commit()
    return row


def _startup(db, users, **kw):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, source_sheet=LIST, **kw)
    db.add(row)
    db.commit()
    return row


def _fresh(db, *rows):
    db.expire_all()
    return [db.get(type(r), r.id) for r in rows]


# ── 1. 새 줄 자동 연결 ──────────────────────────────────────────────────────

def test_새_줄은_이름이_하나_맞으면_저절로_잇는다(db, users, stage):
    from app.models import VcContact

    meta = _consulting(db, users, stage["sheets"]["startup"],
                       company_name="샘플가람 / 무료 / 3%")
    su = _startup(db, users, name="", firm="샘플 가람")
    inv = VcContact(user_id=users["u1"].id, source_sheet=INVESTORS, name="투자담당",
                    firm="샘플가람")
    twin = _startup(db, users, name="", firm="샘플쌍둥")
    db.add(inv)
    db.commit()
    meta, su, inv, twin = _fresh(db, meta, su, inv, twin)
    assert (meta.ir_company_id, meta.ir_link_auto) == (stage["ir"].id, 1)
    assert (su.ir_company_id, su.ir_link_auto) == (stage["ir"].id, 1)
    # 투자사 줄의 `firm` 은 투자사다 · 같은 이름의 IR 이 둘이면 사람이 고른다.
    assert inv.ir_company_id is None and twin.ir_company_id is None


# ── 2. 잇는 순간 빈칸만 ─────────────────────────────────────────────────────

def test_잇는_순간에는_양쪽_빈칸만_채우고_다른_값은_목록에_세운다(db, users, stage):
    from app.services import company_sync

    ir = stage["ir"]
    # IR 이 생기기 전부터 있던 줄 — 저절로 안 이어졌다.
    db.delete(ir)
    db.commit()
    meta = _consulting(db, users, stage["sheets"]["startup"], company_name="샘플가람",
                       ceo_name="김샘플", phone="010-9999-0000", kakao_joined="10/1 초대함",
                       region="서울")
    from app.models import IrCompany

    ir = IrCompany(name="(주)샘플가람", contact_phone="010-0000-1111", kakao_joined="O")
    db.add(ir)
    db.commit()
    assert _fresh(db, meta)[0].ir_company_id is None
    meta.ir_company_id = ir.id
    db.commit()
    meta, ir = _fresh(db, meta, ir)
    # 빈칸 채움 — IR 대표자명 · 지역은 줄에서
    assert ir.contact_name == "김샘플" and ir.region == "서울"
    # 다른 값은 그대로 — 연락처 · 카톡(자유 글)
    assert ir.contact_phone == "010-0000-1111" and meta.phone == "010-9999-0000"
    assert meta.kakao_joined == "10/1 초대함" and ir.kakao_joined == "O"
    diffs = {d["field"]: d for d in company_sync.differences(db, [meta])[meta.id]}
    assert set(diffs) == {"contact_phone", "kakao_joined"}
    assert diffs["kakao_joined"]["movable"] is False
    assert diffs["contact_phone"]["movable"] is True


# ── 3. 고치면 따라 고친다 ───────────────────────────────────────────────────

@pytest.fixture()
def linked(db, users, stage):
    """메타 줄 · 스타트업 줄 · 경영본부 줄 · 계약 줄이 한 IR 기업에 이어진 무대."""
    s = stage["sheets"]
    rows = {
        "meta": _consulting(db, users, s["startup"], company_name="샘플가람"),
        "handover": _consulting(db, users, s["handover"], company_name="샘플가람"),
        "contract": _consulting(db, users, s["contract"], company_name="샘플가람",
                                region="누적"),
        "startup": _startup(db, users, name="", firm="샘플가람"),
    }
    rows = dict(zip(rows, _fresh(db, *rows.values())))
    assert all(r.ir_company_id == stage["ir"].id for r in rows.values())
    return rows


def test_컨설턴트가_고치면_IR과_스타트업이_따라온다(logged_in, db, stage, linked):
    meta = linked["meta"]
    r = logged_in.patch(f"/api/consulting/{meta.id}",
                        json={"ceo_name": "박샘플", "kakao_joined": "O",
                              "contract_management": "X", "region": "부산"})
    assert r.status_code == 200, r.text
    ir, su, hand, con = _fresh(db, stage["ir"], linked["startup"], linked["handover"],
                               linked["contract"])
    assert (ir.contact_name, ir.kakao_joined, ir.quote_attached, ir.region) == \
        ("박샘플", "O", "X", "부산")
    assert su.name == "박샘플" and su.kakao_joined == "O"
    assert json.loads(su.notes)["quote_attached"] == "X"
    # 경영본부 줄은 대표자명 · 지역만(견적서 · 카톡은 메타 탭 칸이다).
    assert hand.ceo_name == "박샘플" and hand.region == "부산"
    assert hand.kakao_joined is None and hand.contract_management is None
    # 월간 계약 탭은 1단계에서 안 잇는다 — 그 `region` 은 달 묶음 이름이다.
    assert con.ceo_name is None and con.region == "누적"


def test_IR을_고치면_이어진_줄이_따라오고_도장도_찍힌다(logged_in, db, stage, linked):
    r = logged_in.patch(f"/api/companies/{stage['ir'].id}",
                        json={"contact_email": "ceo@example.com", "kakao_joined": "X"})
    assert r.status_code == 200, r.text
    meta, su = _fresh(db, linked["meta"], linked["startup"])
    assert meta.email == "ceo@example.com" and su.email == "ceo@example.com"
    assert meta.kakao_joined == "X" and su.kakao_joined == "X"
    assert "kakao_joined" in json.loads(meta.field_stamps)


def test_스타트업에서_고쳐도_따라온다(db, stage, linked):
    from app.services import contact_columns as cc

    su = linked["startup"]
    notes = cc.load_notes(su.notes)
    notes["quote_attached"] = "o"
    su.notes = cc.dump_notes(notes)
    su.phone = "010-2222-3333"
    db.commit()
    ir, meta = _fresh(db, stage["ir"], linked["meta"])
    assert ir.quote_attached == "O" and meta.contract_management == "O"
    assert ir.contact_phone == "010-2222-3333" and meta.phone == "010-2222-3333"


def test_비운_칸과_자유_글은_안_따라간다(logged_in, db, stage, linked):
    meta = linked["meta"]
    logged_in.patch(f"/api/consulting/{meta.id}", json={"ceo_name": "최샘플"})
    # 비운다 → 다른 쪽은 그대로(결정 6).
    logged_in.patch(f"/api/consulting/{meta.id}", json={"ceo_name": ""})
    # O/X 칸의 자유 글 → 안 옮긴다.
    logged_in.patch(f"/api/consulting/{meta.id}", json={"kakao_joined": "10/2 초대함"})
    ir, su = _fresh(db, stage["ir"], linked["startup"])
    assert ir.contact_name == "최샘플" and su.name == "최샘플"
    assert ir.kakao_joined is None and su.kakao_joined is None
    # 자유 글이 적힌 줄은 IR 에서 고쳐도 덮지 않는다 — 그 글이 그날의 기록이다.
    logged_in.patch(f"/api/companies/{stage['ir'].id}", json={"kakao_joined": "O"})
    meta, su = _fresh(db, meta, linked["startup"])
    assert meta.kakao_joined == "10/2 초대함" and su.kakao_joined == "O"


def test_컨설턴트가_IR_공용_칸을_바꾸면_수정_로그에_남는다(logged_in, db, stage, linked):
    from app.models import EditLog

    logged_in.patch(f"/api/consulting/{linked['meta'].id}", json={"region": "대구"})
    logs = db.query(EditLog).filter(EditLog.table_name == "ir_companies").all()
    assert logs, "IR 공용 칸이 바뀌었는데 로그가 없습니다"
    assert any("region" in (log.changes_json or "") for log in logs)


# ── 4. 값 다름 고르기 ───────────────────────────────────────────────────────

def test_값_다름은_사람이_한쪽을_고르면_같아진다(db, users, stage, linked, logged_in):
    from app.services import company_sync

    meta = linked["meta"]
    # 이을 때부터 달랐던 값을 흉내 낸다 — 따라 고치기를 끈 채 줄만 바꾼다.
    db.execute(meta.__table__.update().where(meta.__table__.c.id == meta.id)
               .values(phone="010-7777-0000"))
    db.commit()
    meta = _fresh(db, meta)[0]
    assert [d["field"] for d in company_sync.differences(db, [meta])[meta.id]] == \
        ["contact_phone"]
    r = logged_in.post("/ir-link/resolve", data={"tab": "consulting", "row_id": meta.id,
                                                 "field": "contact_phone", "pick": "row"},
                       follow_redirects=False)
    assert r.status_code == 303
    ir, su = _fresh(db, stage["ir"], linked["startup"])
    assert ir.contact_phone == "010-7777-0000" and su.phone == "010-7777-0000"
    assert company_sync.differences(db, [_fresh(db, meta)[0]]) == {}


def test_값_다름은_연결_화면에_칩과_단추로_선다(db, users, stage, linked, logged_in):
    meta = linked["meta"]
    db.execute(meta.__table__.update().where(meta.__table__.c.id == meta.id)
               .values(phone="010-7777-0000"))
    db.commit()
    users["u1"].role = "admin"
    db.commit()
    html = logged_in.get("/ir-link?tab=consulting&show=diff").text
    assert "값 다름" in html and "/ir-link/resolve" in html
    assert "자동 연결" in html


# ── 4-2. 둘 다 남기기(연락처 · 이메일 — 10/23) ──────────────────────────────

def _raw_set(db, row, **values):
    """이을 때부터 달랐던 값을 흉내 낸다 — 따라 고치기를 지나지 않고 줄만 바꾼다."""
    db.execute(row.__table__.update().where(row.__table__.c.id == row.id).values(**values))
    db.commit()
    return _fresh(db, row)[0]


def test_합치기는_앞이_정이고_같은_값은_한_번(db):
    from app.services.company_sync import combine

    # 꼴만 다른 같은 번호 · 대소문자만 다른 같은 메일은 하나로(앞의 꼴을 둔다).
    assert combine("contact_phone", ["010-0000-1111", "01000001111, 02-123-4567"]) == \
        ("010-0000-1111, 02-123-4567", 1)
    assert combine("contact_email", ["Ceo@Example.com", "ceo@example.com", "", None,
                                     "ceo@example.com, sub@example.net"]) == \
        ("Ceo@Example.com, sub@example.net", 2)


def test_둘_다_남기기는_IR값을_앞에_두고_이어진_줄_모두에_적는다(db, users, stage, linked,
                                                    logged_in):
    from app.models import EditLog
    from app.services import company_sync

    meta = _raw_set(db, linked["meta"], phone="010-7777-0000")
    users["u1"].role = "admin"
    db.commit()
    html = logged_in.get("/ir-link?tab=consulting&show=diff").text
    assert "둘 다 남기기" in html
    r = logged_in.post("/ir-link/resolve", data={"tab": "consulting", "row_id": meta.id,
                                                 "field": "contact_phone", "pick": "both"},
                       follow_redirects=False)
    assert r.status_code == 303
    ir, meta, su, hand = _fresh(db, stage["ir"], meta, linked["startup"], linked["handover"])
    both = "010-0000-1111, 010-7777-0000"
    assert ir.contact_phone == both and meta.phone == both
    assert su.phone == both and hand.phone == both
    assert company_sync.differences(db, [meta]) == {}
    logs = db.query(EditLog).filter(EditLog.table_name == "ir_companies").all()
    assert any("contact_phone" in (log.changes_json or "") for log in logs)


def test_둘_다_남기기는_대표자명_같은_칸에는_안_된다(db, stage, linked):
    from app.services import company_sync

    meta = _raw_set(db, linked["meta"], ceo_name="박샘플")
    with pytest.raises(ValueError):
        company_sync.resolve(db, meta, "contact_name", "both")


def test_연락처_칸의_메일은_이메일_칸으로_옮겨_잇는다(db, stage, linked):
    from app.services import company_sync

    ir = stage["ir"]
    ir.contact_email = "ir@example.com"
    db.commit()
    # 경영본부 전달 탭 — 연락처 칸에 메일이 적혀 있다.
    hand = _raw_set(db, linked["handover"], phone="ceo@example.com")
    assert [d["field"] for d in company_sync.differences(db, [hand])[hand.id]] == \
        ["contact_phone"]
    done = company_sync.keep_both(db, hand, "contact_phone")
    db.commit()
    assert done == {"moved": 1, "folded": 0, "odd": 0}
    ir, hand, su = _fresh(db, ir, hand, linked["startup"])
    assert ir.contact_phone == "010-0000-1111" and hand.phone == "010-0000-1111"
    assert ir.contact_email == "ir@example.com, ceo@example.com"
    assert hand.email == ir.contact_email and su.email == ir.contact_email
    assert company_sync.differences(db, [hand]) == {}


def test_둘_다_남기기는_다른_이어진_줄의_셋째_값도_잃지_않는다(db, stage, linked):
    from app.services import company_sync

    ir = _raw_set(db, stage["ir"], contact_email="ir@example.com")
    meta = _raw_set(db, linked["meta"], email="meta@example.com")
    su = _raw_set(db, linked["startup"], email="su@example.com")
    company_sync.keep_both(db, _fresh(db, meta)[0], "contact_email")
    db.commit()
    ir, meta, su = _fresh(db, ir, meta, su)
    assert ir.contact_email == "ir@example.com, meta@example.com, su@example.com"
    assert meta.email == su.email == ir.contact_email


def test_메일이_여럿인_칸에는_정_표시가_선다(db, users, stage, linked, logged_in):
    """첫 주소(정)에만 메일이 간다 — 표가 그 칸에 `정` 을 단다(CSS `td.mail-primary`)."""
    from app.services import company_sync

    _raw_set(db, stage["ir"], contact_email="ir@example.com")
    meta = _raw_set(db, linked["meta"], email="meta@example.com")
    company_sync.keep_both(db, meta, "contact_email")
    db.commit()
    assert _fresh(db, stage["ir"])[0].contact_email == "ir@example.com, meta@example.com"
    for page in ("/companies?tab=db", "/consulting"):
        html = logged_in.get(page).text
        assert 'mail-primary" data-field="' in html, page


def test_일괄_스크립트는_같은_규칙으로_잇는다(db, stage, linked):
    from scripts import ir_link_keep_both

    from app.services import company_sync

    ir = stage["ir"]
    ir.contact_email = "ir@example.com"
    db.commit()
    _raw_set(db, linked["meta"], phone="010 7777 0000")
    _raw_set(db, linked["handover"], phone="ceo@example.com")
    _raw_set(db, linked["startup"], phone="01000001111")     # 꼴만 다른 같은 번호
    counts, _trace = ir_link_keep_both.run(db)
    db.commit()
    # 메타 줄 하나가 같은 IR 의 줄 모두를 맞춘다 — 경영본부 줄의 값 다름도 함께 닫힌다.
    assert (counts["contact_phone"], counts["contact_email"]) == (1, 0)
    assert (counts["moved"], counts["folded"], counts["odd"], counts["left"]) == (1, 1, 0, 0)
    ir, meta, hand, su = _fresh(db, ir, linked["meta"], linked["handover"], linked["startup"])
    both = "010-0000-1111, 010 7777 0000"
    assert ir.contact_phone == meta.phone == hand.phone == su.phone == both
    assert ir.contact_email == hand.email == "ir@example.com, ceo@example.com"
    assert company_sync.differences(db, [meta, hand]) == {}


def test_일괄_스크립트는_모양이_이상한_값이_끼면_사람에게_남긴다(db, stage, linked):
    from scripts import ir_link_keep_both

    from app.services import company_sync

    ir = stage["ir"]
    ir.contact_email = "ir@example.com"
    db.commit()
    hand = _raw_set(db, linked["handover"], email="메일 없음 10/2 확인")
    counts, _trace = ir_link_keep_both.run(db)
    db.commit()
    assert (counts["contact_email"], counts["odd"], counts["left"]) == (0, 1, 1)
    hand, ir = _fresh(db, hand, ir)
    assert hand.email == "메일 없음 10/2 확인" and ir.contact_email == "ir@example.com"
    assert [d["field"] for d in company_sync.differences(db, [hand])[hand.id]] == \
        ["contact_email"]


# ── 5. 시트 다시 올리기 ─────────────────────────────────────────────────────

def test_시트를_다시_올려도_이어진_줄과_IR을_덮지_않는다(db, users, stage):
    from app.routers.consulting import apply_rows

    # 올리기는 기업명으로 내 줄을 찾는다 — 이 기업은 내 표에 한 줄뿐이다.
    meta = _consulting(db, users, stage["sheets"]["startup"], company_name="샘플가람")
    meta.phone = "010-1000-2000"
    db.commit()
    parsed = {"columns": [], "companies": [
        {"notes": {}, "company_name": "샘플가람", "phone": "010-5555-5555",
         "ceo_name": "시트대표"}]}
    apply_rows(db, parsed, users["u1"])
    meta, ir = _fresh(db, meta, stage["ir"])
    assert meta.phone == "010-1000-2000" and ir.contact_phone == "010-1000-2000"
    # 비어 있던 대표자명은 받고, IR 도 빈칸이라 채워진다.
    assert meta.ceo_name == "시트대표" and ir.contact_name == "시트대표"


def test_전체_바꾸기도_연결을_끊지_않는다(db, users, stage):
    from app.models import ConsultingCompany, IrCompany
    from app.routers.consulting import apply_rows

    # 이름이 다른 IR 기업에 사람이 이어 둔 줄 — 이름으로는 다시 못 찾는다.
    other = IrCompany(name="샘플다른이름")
    db.add(other)
    db.commit()
    row = _consulting(db, users, stage["sheets"]["startup"], company_name="샘플별칭")
    row.ir_company_id, row.ir_link_auto = other.id, 0
    db.commit()
    parsed = {"columns": [], "companies": [{"notes": {}, "company_name": "샘플별칭"}]}
    apply_rows(db, parsed, users["u1"], replace=True)
    db.expire_all()
    again = db.query(ConsultingCompany).filter_by(company_name="샘플별칭").one()
    assert again.id is not None and again.ir_company_id == other.id
    assert again.ir_link_auto == 0


def test_IR_시트_가져오기는_앱의_계약여부를_덮지_않는다(db, stage):
    from app.services import sheet_import as si

    ir = stage["ir"]
    ir.contract_status = "blocked"
    db.commit()
    # 시트가 빈칸(미계약)이어도 · 다른 계약 값이어도 앱 값을 둔다.
    report = si.apply_sheet_b(db, si.SheetBParse(companies=[
        si.ParsedCompany(row_no=1, name=ir.name, contract_status="no")]))
    assert _fresh(db, ir)[0].contract_status == "blocked"
    report = si.apply_sheet_b(db, si.SheetBParse(companies=[
        si.ParsedCompany(row_no=1, name=ir.name, contract_status="paid")]))
    assert _fresh(db, ir)[0].contract_status == "blocked"
    assert any("앱 값을 둔 기업 1곳" in n for n in report.notes), report.notes
    # 앱이 아직 미계약이면 시트 값을 받는다(예전 그대로).
    ir = _fresh(db, ir)[0]
    ir.contract_status = "no"
    db.commit()
    si.apply_sheet_b(db, si.SheetBParse(companies=[
        si.ParsedCompany(row_no=1, name=ir.name, contract_status="paid")]))
    assert _fresh(db, ir)[0].contract_status == "paid"


# ── 6. 보내기는 연결을 물려준다 ─────────────────────────────────────────────

def test_스타트업으로_보내면_원래_줄의_연결을_물려받는다(logged_in, db, users, stage):
    from app.models import IrCompany, VcContact

    other = IrCompany(name="샘플물림")
    db.add(other)
    db.commit()
    # 이름은 다른 IR(`(주)샘플가람`)과 같지만 사람이 `샘플물림` 에 이어 둔 줄.
    row = _consulting(db, users, stage["sheets"]["startup"], company_name="샘플가람")
    row.ir_company_id, row.ir_link_auto = other.id, 0
    db.commit()
    row.ceo_name = "김보냄"
    db.commit()
    r = logged_in.post("/api/contacts/from-consulting",
                       json={"label": LIST, "company_ids": [row.id]})
    assert r.status_code == 200, r.text
    made = db.query(VcContact).filter_by(firm="샘플가람").one()
    assert made.ir_company_id == other.id
    # 이름으로 먼저 `(주)샘플가람` 에 붙었다 옮겨 가며 그 IR 을 채우지 않았다.
    ga, mul = _fresh(db, stage["ir"], other)
    assert ga.contact_name is None and mul.contact_name == "김보냄"


def test_투자사_현황_업로드도_이어진_줄은_덮지_않는다(db, users, stage):
    from app.services import sheet_import as si

    su = _startup(db, users, name="김샘플", firm="샘플가람", kakao_joined="O")
    assert _fresh(db, su)[0].ir_company_id == stage["ir"].id
    ir = _fresh(db, stage["ir"])[0]
    assert ir.kakao_joined == "O"
    parsed = si.parse_sheet_a([["번호", "그룹", "이름", "투자사명", "카톡방 참여여부"],
                               ["1", "", "김샘플", "샘플가람", "X"]], 2026)
    report = si.apply_sheet_a(db, parsed, user_id=users["u1"].id)
    assert report.updated == 1, (report.created, report.updated)
    su, ir = _fresh(db, su, stage["ir"])
    assert su.kakao_joined == "O" and ir.kakao_joined == "O"


def test_스타트업_시트_가져오기도_이어진_줄은_빈칸만_채운다(db, users, stage, tmp_path,
                                               monkeypatch):
    import csv
    import sys

    from scripts import import_startup_sheet

    su = _startup(db, users, name="", firm="샘플가람", phone="010-1000-2000")
    assert _fresh(db, su)[0].ir_company_id == stage["ir"].id
    path = tmp_path / "sheet.csv"
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["NO", "기업명", "성함", "연락처"])
        writer.writerow(["1", "샘플가람", "시트대표", "010-5555-5555"])
    monkeypatch.setattr(sys, "argv", ["import_startup_sheet", str(path),
                                      "--sheet", LIST, "--apply"])
    assert import_startup_sheet.main() == 0
    su, ir = _fresh(db, su, stage["ir"])
    assert su.phone == "010-1000-2000" and ir.contact_phone == "010-0000-1111"
    assert su.name == "시트대표" and ir.contact_name == "시트대표"
