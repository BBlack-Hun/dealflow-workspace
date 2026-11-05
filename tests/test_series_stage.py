"""`투자라운드` 일곱 단계(#162 · `services/series_stage.py`).

    Seed → Pre-A → Bridge → Series A → Series B → Series C → Pre-IPO

  ① 대응표 — 옛 시트 글 · 표기 갈래는 단계 하나로, 못 읽는 값은 None(그대로 둔다)
  ② 저장하는 길 — IR 기업 현황 · Series A 탭 · 스타트업 명단 PATCH, 시트 가져오기
  ③ 화면 — 세 칸 모두 일곱 단계를 보기로 띄운다
  ④ 맞추기 스크립트(`scripts/series_stage_fill.py`) — 미리보기는 안 쓰고, 저장은
     수정 로그 · 원래 값을 남기고, 다시 돌리면 할 일이 없다
  ⑤ 딜 추천의 단계 맞추기(`matcher`)는 맞춘 값으로도 같다

기업명 · 사람 이름은 전부 가상값이다(공개 저장소).
"""
from __future__ import annotations

import json

import pytest

from tests.test_startup_tab import LIST, sheets  # noqa: F401 — 고정물

STAGES = ("Seed", "Pre-A", "Bridge", "Series A", "Series B", "Series C", "Pre-IPO")


# ── ① 대응표 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value, stage", [
    # 운영에 실제로 있는 꼴(값만 — 개수는 PR 본문)
    ("Angel, Seed (누적투자금 0, 년매출액 3억미만)", "Seed"),
    ("Pre A, Bridge  (누적투자금 5억미만, 년매출액 10억이상)", "Pre-A"),
    ("Pre A, Bridge (누적투자금 5억미만, 년매출액 10억이상)", "Pre-A"),
    ("Series A (누적투자금 10억이상, 년매출액 10억이상)", "Series A"),
    ("Series B (누적투자금 20억 이상, 년매출액 50억이상)", "Series B"),
    ("Series C (누적투자금 50억 이상, 년매출액 80억이상)", "Series C"),
    ("Pre IPO  (누적투자금 80억이상 년매출액 80억이상)", "Pre-IPO"),
    ("series A", "Series A"), ("SeriesA", "Series A"), ("Pre IPO", "Pre-IPO"),
    ("Bridge", "Bridge"), ("Pre-A", "Pre-A"),
    # 사람이 칠 만한 꼴
    ("엔젤", "Seed"), ("시드", "Seed"), ("Pre-seed", "Seed"), ("Seed단계", "Seed"),
    ("프리A", "Pre-A"), ("Pre-Series A", "Pre-A"), ("브릿지", "Bridge"),
    ("시리즈A", "Series A"), ("시리즈 B", "Series B"), ("Series A+", "Series A"),
    ("Series A-1", "Series A"), ("pre-IPO단계", "Pre-IPO"),
    # C 뒤는 Pre-IPO 하나뿐이다
    ("Series D", "Pre-IPO"), ("Series D 이상", "Pre-IPO"),
    *[(s, s) for s in STAGES],
])
def test_읽히는_값은_단계_하나로(value, stage):
    from app.services import series_stage

    assert series_stage.STAGES == STAGES
    assert series_stage.stage_of(value) == stage
    assert series_stage.clean(value) == stage


@pytest.mark.parametrize("value", [
    "Pre IPO 전단계",        # 단계 말 밖의 글이 붙었다 — Series C 인지 Pre-IPO 인지 모른다
    "Series C 이상",         # C 인지 그 위인지 모른다
    "Seed~Pre-A", "Series A~B", "Series A 브릿지",   # 둘 이상
    "M&A", "구주", "상장", "IPO", "Growth", "A",      # 단계 말이 없다
    "Series X (년매출액 10억미만)", "Pre Value", "Seeding",
])
def test_못_읽는_값은_그대로_둔다(value):
    from app.services import series_stage

    assert series_stage.stage_of(value) is None
    assert series_stage.clean(value) == value


@pytest.mark.parametrize("value", [None, "", "  "])
def test_빈칸은_빈칸(value):
    from app.services import series_stage

    assert series_stage.stage_of(value) is None
    assert series_stage.clean(value) == value


# ── ② 저장하는 길 ───────────────────────────────────────────────────────────

def test_IR_기업_현황은_저장할_때_단계로_맞춘다(logged_in, db):
    from app.models import IrCompany

    company = IrCompany(name="샘플라운드")
    db.add(company)
    db.commit()
    r = logged_in.patch(f"/api/companies/{company.id}", json={"series": "시리즈A"})
    assert r.status_code == 200, r.text
    assert r.json()["series"] == "Series A"          # 화면이 이 값으로 다시 그린다
    db.expire_all()
    assert db.get(IrCompany, company.id).series == "Series A"

    r = logged_in.patch(f"/api/companies/{company.id}", json={"series": "M&A"})
    assert r.json()["series"] == "M&A"               # 못 읽는 값은 적힌 그대로
    r = logged_in.post("/api/companies", json={"name": "샘플새기업", "series": "프리 A"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(IrCompany, r.json()["id"]).series == "Pre-A"


def test_IR_수정_기록에_전후_값이_남는다(logged_in, db):
    from app.models import EditLog, IrCompany

    company = IrCompany(name="샘플기록")
    db.add(company)
    db.commit()
    logged_in.patch(f"/api/companies/{company.id}", json={"series": "Angel"})
    log = db.query(EditLog).filter(EditLog.table_name == "ir_companies").all()[-1]
    change = [c for c in json.loads(log.changes_json) if c["field"] == "series"]
    assert change == [{"field": "series", "before": None, "after": "Seed"}]


def test_Series_A_탭도_단계로_맞춘다(logged_in, db):
    from app.models import SeriesACompany

    row = SeriesACompany(name="샘플받은딜", received_at="2026-11-05", series="브릿지")
    db.add(row)
    db.commit()
    assert row.series == "Bridge"                      # 만들 때도
    r = logged_in.patch(f"/api/series-a-companies/{row.id}", json={"series": "Series B 단계"})
    assert r.status_code == 200, r.text
    assert (r.json()["series"], r.json()["series_short"]) == ("Series B", "Series B")


def test_스타트업_명단도_단계로_맞춘다(sheets, db):  # noqa: F811
    from app.models import VcContact

    contact = db.query(VcContact).filter(VcContact.source_sheet == LIST).first()
    r = sheets.patch(f"/api/contacts/{contact.id}",
                     json={"notes": {"company_kind": "Angel, Seed (누적투자금 0)"}})
    assert r.status_code == 200, r.text
    assert r.json()["company_kind"] == "Seed"
    got = sheets.get(f"/api/contacts/{contact.id}").json()["contact"]["notes"]
    assert got["company_kind"] == "Seed"
    # 다른 칸만 고친 응답에는 싣지 않는다(화면이 그 칸을 다시 그릴 까닭이 없다).
    r = sheets.patch(f"/api/contacts/{contact.id}", json={"notes": {"success_fee": "3%"}})
    assert "company_kind" not in r.json()


def test_시트_가져오기도_단계로_맞춘다(db):
    from app.models import IrCompany
    from app.services import series_a_import, sheet_import
    from scripts.import_startup_sheet import parse as parse_startup

    # IR 기업 현황 시트(옛 머리글 `기업구분`) — 저장할 때 맞춘다.
    head = ["NO", "기업명", "사업분야 대분류", "소분류", "기업구분", "한줄 소개"]
    parsed = sheet_import.parse_sheet_b([head, ["1", "샘플시트", "핀테크", "결제",
                                                "Pre A, Bridge (누적투자금 5억미만)", "결제"]],
                                        2026)
    sheet_import.apply_sheet_b(db, parsed)
    db.commit()
    assert db.query(IrCompany).filter(IrCompany.name == "샘플시트").one().series == "Pre-A"

    # Series A 이상 기업 시트 — 견주기 전에 맞춘다(다시 가져올 때 `다르다` 로 안 세게).
    rows = [["수신 일자", "기업명", "공유 심사역", "기업구분"],
            ["2026-11-05", "샘플받은딜", "김샘플 이사", "Series A (누적투자금 10억이상)"],
            ["2026-11-05", "샘플그대로", "김샘플 이사", "구주"]]
    got = [r["series"] for r in series_a_import.parse(rows).records]
    assert got == ["Series A", "구주"]

    # 스타트업 명단 시트(`scripts/import_startup_sheet.py`).
    rows = [["NO", "기업명", "성함", "기업구분"], ["1", "샘플스타트", "김샘플", "시드"]]
    assert parse_startup(rows)["items"][0]["notes"]["company_kind"] == "Seed"


# ── ③ 화면 ──────────────────────────────────────────────────────────────────

def test_세_칸_모두_일곱_단계를_보기로_띄운다(logged_in, db, sheets):  # noqa: F811
    from app.models import IrCompany

    db.add(IrCompany(name="샘플보기", series="Seed"))
    db.commit()
    choices = 'data-choices="' + ",".join(STAGES) + '"'
    html = logged_in.get("/companies").text
    assert 'data-field="series" data-type="pick"' in html and choices in html
    # 수정창 — 고르거나(목록) 그대로 둔다(못 읽은 옛 값이 저장 한 번에 지워지면 안 된다).
    assert 'id="f-series" list="opts-series"' in html
    for stage in STAGES:
        assert f'<option value="{stage}"></option>' in html
    from tests.test_startup_tab import _url

    startup = sheets.get(_url(LIST)).text
    assert 'data-field="company_kind"' in startup and choices in startup


# ── ④ 맞추기 스크립트 ───────────────────────────────────────────────────────

@pytest.fixture()
def old_values(db, users):
    """옛 값이 든 줄 — 저장 길(`@validates`)을 안 지나게 표에 바로 적는다."""
    from app.models import IrCompany, SeriesACompany, SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=LIST, user_id=users["u2"].id, layout=cc.STARTUP))
    rows = {
        "ir_seed": IrCompany(name="샘플옛시드"), "ir_kept": IrCompany(name="샘플옛그대로"),
        "ir_blank": IrCompany(name="샘플옛빈칸"), "ir_done": IrCompany(name="샘플옛단계"),
        "sa": SeriesACompany(name="샘플옛딜", received_at="2026-11-01"),
        "su": VcContact(user_id=users["u2"].id, source_sheet=LIST, name="김샘플",
                        firm="샘플옛스타트", notes=cc.dump_notes({"memo_x": "그대로"})),
    }
    db.add_all(rows.values())
    db.commit()
    raw = {"ir_seed": "Angel, Seed (누적투자금 0, 년매출액 3억미만)",
           "ir_kept": "Pre IPO 전단계", "ir_done": "Series B",
           "sa": "Pre IPO  (누적투자금 80억이상 년매출액 80억이상)"}
    for key, value in raw.items():
        t = rows[key].__table__
        db.execute(t.update().where(t.c.id == rows[key].id).values(series=value))
    t = VcContact.__table__
    db.execute(t.update().where(t.c.id == rows["su"].id).values(notes=json.dumps(
        {"company_kind": "Pre A, Bridge  (누적투자금 5억미만, 년매출액 10억이상)",
         "memo_x": "그대로"}, ensure_ascii=False)))
    db.commit()
    db.expire_all()
    return rows


def _series(db, rows):
    from app.models import IrCompany, SeriesACompany, VcContact

    db.expire_all()
    out = {k: db.get(IrCompany, rows[k].id).series
           for k in ("ir_seed", "ir_kept", "ir_blank", "ir_done")}
    out["sa"] = db.get(SeriesACompany, rows["sa"].id).series
    out["su"] = json.loads(db.get(VcContact, rows["su"].id).notes)
    return out


def test_스크립트_미리보기는_DB_에_안_쓴다(db, old_values, capsys):
    from scripts import series_stage_fill

    before = _series(db, old_values)
    assert series_stage_fill.main([]) == 0
    assert _series(db, old_values) == before
    out = capsys.readouterr().out
    assert "미리보기" in out
    assert "[IR 기업 현황] 바뀜 1 · 이미 단계 1 · 그대로 둠(못 읽음) 1 · 빈칸 1" in out
    assert "Pre IPO 전단계  (그대로)" in out
    assert "[스타트업 명단] 바뀜 1" in out


def test_스크립트_저장은_원래_값을_남기고_다시_돌려도_같다(db, users, old_values, capsys):
    from app.models import EditLog
    from scripts import series_stage_fill

    assert series_stage_fill.main(["--apply"]) == 2      # 수정 로그 계정 없이는 안 돈다
    assert series_stage_fill.main(["--apply", "--user-id", str(users["u1"].id)]) == 0
    got = _series(db, old_values)
    assert (got["ir_seed"], got["ir_kept"], got["ir_blank"], got["ir_done"], got["sa"]) == \
        ("Seed", "Pre IPO 전단계", None, "Series B", "Pre-IPO")
    assert got["su"] == {"company_kind": "Pre-A", "memo_x": "그대로",
                         "company_kind_raw": "Pre A, Bridge  (누적투자금 5억미만, 년매출액 10억이상)"}
    # IR · Series A 는 수정 로그에 전→후 값이 남는다(스크립트 계정으로).
    logs = {(log.table_name, c["before"], c["after"])
            for log in db.query(EditLog).filter(EditLog.actor_user_id == users["u1"].id)
            for c in json.loads(log.changes_json) if c["field"] == "series"}
    assert logs == {("ir_companies", "Angel, Seed (누적투자금 0, 년매출액 3억미만)", "Seed"),
                    ("series_a_companies", "Pre IPO  (누적투자금 80억이상 년매출액 80억이상)",
                     "Pre-IPO")}
    capsys.readouterr()
    # 다시 돌리면 할 일이 없다 · 원래 값은 안 덮는다.
    assert series_stage_fill.main(["--apply", "--user-id", str(users["u1"].id)]) == 0
    assert "[IR 기업 현황] 바뀜 0" in capsys.readouterr().out
    assert _series(db, old_values) == got


def test_스크립트는_이어진_표로_따라가지_않는다(db, users):
    """맞추기만 한 것은 고친 것이 아니다(`company_sync.norm`) — IR 에 못 읽는 값이
    남아 있어도 이어진 스타트업 줄의 맞춤이 그 값을 덮지 않는다."""
    from app.models import IrCompany, SheetOwner, VcContact
    from app.services import contact_columns as cc
    from scripts import series_stage_fill

    db.add(SheetOwner(label=LIST, user_id=users["u2"].id, layout=cc.STARTUP))
    ir = IrCompany(name="샘플이음", series="Pre IPO 전단계")
    db.add(ir)
    db.commit()
    su = VcContact(user_id=users["u2"].id, source_sheet=LIST, name="김샘플",
                   firm="샘플이음", notes=cc.dump_notes({"sector_minor": "결제"}))
    db.add(su)
    db.commit()
    assert su.ir_company_id == ir.id
    t = VcContact.__table__
    db.execute(t.update().where(t.c.id == su.id).values(notes=json.dumps(
        {"company_kind": "Pre IPO (누적투자금 80억이상)"}, ensure_ascii=False)))
    db.commit()
    db.expire_all()
    series_stage_fill.run(db)
    db.commit()
    db.expire_all()
    assert db.get(IrCompany, ir.id).series == "Pre IPO 전단계"
    assert json.loads(db.get(VcContact, su.id).notes)["company_kind"] == "Pre-IPO"


# ── ⑤ 딜 추천의 단계 맞추기 ─────────────────────────────────────────────────

@pytest.mark.parametrize("old", [
    "Angel, Seed (누적투자금 0, 년매출액 3억미만)",
    "Pre A, Bridge (누적투자금 5억미만, 년매출액 10억이상)",
    "Series A (누적투자금 10억이상, 년매출액 10억이상)",
    "Series B (누적투자금 20억 이상, 년매출액 50억이상)",
    "Series C (누적투자금 50억 이상, 년매출액 80억이상)",
])
@pytest.mark.parametrize("stages", ["Seed", "Pre-A", "SeriesA", "SeriesB", "SeriesC, Pre-IPO",
                                    "Seed, Pre-A, SeriesA"])
def test_딜_추천의_단계_판정은_맞춘_값으로도_같다(old, stages):
    from types import SimpleNamespace

    from app.services import matcher, series_stage

    contact = SimpleNamespace(stages=stages, sectors=None, round_size=None)

    def verdict(series):
        return matcher.evaluate_company(contact, SimpleNamespace(series=series)).verdict

    assert verdict(series_stage.clean(old)) == verdict(old)
    assert verdict("Pre-IPO") == verdict("Pre IPO  (누적투자금 80억이상 년매출액 80억이상)")
