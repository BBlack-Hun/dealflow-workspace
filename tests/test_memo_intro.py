"""딜소개 메모 → 활동 이력 (#52 — `services/memo_intro.py`).

그룹웨어로 안 보내고 탭의 `N월 1차 딜소개` 칸에 메모로 적는 탭이 있다. 그
메모의 회차가 손으로 보낸 기록(`source="manual"`)으로 옮겨져 활동 이력 ·
업무 보고에 서는지를 잠근다.

  1. 해석 — 대괄호 날짜 · 머리말 · 줄바꿈 기업 목록
  2. 날짜 — 해 정하기 · 앞날 · 시작 달(2026-10) 이전은 건너뜀
  3. 이미 있음(시트 줄과 같은 회차) · 같은 입력이면 몇 번 돌려도 같다
  4. 메모를 고치면 그 칸에서 온 줄만 거두고 새 회차는 적는다 · 되돌린 줄은 안 살린다
  5. 권한 — 남의 탭 403 · 남의 줄이 섞이면 404 · 미리보기는 안 쓴다
  6. 업무 보고에 `손으로 보냄(메모)` 줄이 서고 합계에 들어간다

이름 · 회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from app.services import manual_send, memo_intro

from .conftest import DEMO_PASSWORD

SHEET = "투자사 시험 탭"
TODAY = date(2026, 10, 18)


@pytest.fixture()
def tab(db, users):
    """u1 의 탭 하나 — 10월 딜소개 · IR 요청 · 미팅, 9월 딜소개, 숨긴 딜소개 칸."""
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id,
                      layout=cc.INVESTOR_MONTHLY))
    cols = {}
    for pos, label in enumerate(("10월 1차 딜소개", "10월 IR 요청", "10월 미팅",
                                 "9월 1차 딜소개", "10월 2차 딜소개")):
        cols[label] = ContactColumn(sheet=SHEET, label=label, position=pos,
                                    is_hidden=1 if label == "10월 2차 딜소개" else 0)
        db.add(cols[label])
    people = {}
    for name in ("가담당", "나담당"):
        people[name] = VcContact(user_id=users["u1"].id, source_sheet=SHEET,
                                 name=name, firm="가나벤처스")
        db.add(people[name])
    db.commit()
    return {"cols": cols, **people}


def _memo(db, tab, person, values):
    """{칸 이름: 메모} → 그 사람의 notes."""
    from app.services import contact_columns as cc

    person.notes = json.dumps(
        {cc.note_key(tab["cols"][k].id): v for k, v in values.items()},
        ensure_ascii=False)
    db.commit()


def _plan(db):
    return memo_intro.plan(db, SHEET, today=TODAY)


def _run(db):
    p = _plan(db)
    memo_intro.apply(db, p)
    db.commit()
    return p


def _acts(db):
    from app.models import ContactActivity

    return db.query(ContactActivity).order_by(ContactActivity.id).all()


# ── 1. 해석 ────────────────────────────────────────────────────────────────

def test_bracket_date_header_and_wrapped_company_list(db, tab):
    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": (
        "10월 딜소개 기록\n"
        "[10/5] [핵심 딜 공유]\n"
        "샘플가, 샘플나\n"
        "10/12(월) 샘플다")})

    p = _plan(db)
    got = [(i["day"], i["companies"], i["count"]) for i in p["add"]]
    assert got == [("2026-10-05", ["샘플가", "샘플나"], 2),
                   ("2026-10-12", ["샘플다"], 1)]
    # 날짜 없는 머리 줄은 건너뛰고 목록으로 보여 준다.
    assert [i["raw"] for i in p["no_date"]] == ["10월 딜소개 기록"]
    # 원문은 줄바꿈째 남는다.
    assert p["add"][0]["raw"] == "[10/5] [핵심 딜 공유]\n샘플가, 샘플나"


# ── 2. 날짜 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("md, today, want", [
    ((10, 5), date(2026, 10, 18), date(2026, 10, 5)),
    ((10, 25), date(2026, 10, 18), date(2026, 10, 25)),    # 앞날 — 부르는 쪽이 건너뜀
    ((1, 3), date(2026, 12, 29), date(2027, 1, 3)),        # 연말에 미리 적은 새해 날짜
    ((12, 28), date(2027, 1, 5), date(2026, 12, 28)),      # 1월에 읽는 지난 12월
    ((4, 10), date(2026, 10, 18), date(2026, 4, 10)),
    ((2, 29), date(2027, 3, 1), date(2024, 2, 29)),
    ((2, 30), date(2026, 10, 18), None),
])
def test_year_is_the_nearest_past_day(md, today, want):
    assert memo_intro.resolve_day(*md, today) == want


def test_future_before_start_and_no_company_are_skipped(db, tab):
    _memo(db, tab, tab["가담당"], {
        "10월 1차 딜소개": ("9/30 샘플라\n10/25 샘플마\n10/6 소개기업 없음\n"
                        "10/7 리마인드 카톡\n10/8 핵심 딜 8개사"),
        "9월 1차 딜소개": "9/15 샘플바",
        # 대상 아닌 칸 — IR 요청 · 미팅 · 숨긴 딜소개 칸은 읽지도 않는다.
        "10월 IR 요청": "10/9 샘플사",
        "10월 미팅": "10/9 샘플사",
        "10월 2차 딜소개": "10/10 샘플아",
    })

    p = _plan(db)
    assert [i["day"] for i in p["before_start"]] == ["2026-09-30", "2026-09-15"]
    assert [i["day"] for i in p["future"]] == ["2026-10-25"]
    assert [i["day"] for i in p["no_company"]] == ["2026-10-06", "2026-10-07"]
    # 이름 없이 개수만 적은 회차는 그 수로 센다.
    assert [(i["day"], i["companies"], i["count"]) for i in p["add"]] == [
        ("2026-10-08", [], 8)]
    assert p["columns"] == ["10월 1차 딜소개", "9월 1차 딜소개"]


# ── 3. 이미 있음 · 몇 번 돌려도 같다 ───────────────────────────────────────

def test_same_round_from_the_sheet_is_already_there_and_reruns_add_nothing(db, tab):
    from app.models import ContactActivity

    db.add(ContactActivity(contact_id=tab["가담당"].id, kind="deal_intro",
                           source="import", content="샘플가, 샘플나",
                           happened_at="2026-10-05", month="2026-10",
                           company_names=json.dumps(["샘플가", "샘플나"],
                                                    ensure_ascii=False),
                           company_count=2))
    db.commit()
    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": "10/5 샘플가, 샘플나\n10/12 샘플다"})

    first = _run(db)
    assert [i["day"] for i in first["already"]] == ["2026-10-05"]
    assert [i["day"] for i in first["add"]] == ["2026-10-12"]
    rows = _acts(db)
    assert len(rows) == 2
    new = rows[-1]
    assert (new.source, new.kind, new.batch_key) == (
        "manual", "deal_intro",
        f"memo-{tab['cols']['10월 1차 딜소개'].id}-2026-10-12")
    assert new.raw_text == "10/12 샘플다" and new.companies == ["샘플다"]
    assert memo_intro.BY_MEMO in new.content
    # 리마인드는 안 세운다.
    assert new.sequence_trace is None

    again = _run(db)
    assert again["add"] == [] and again["retract"] == []
    assert len(_acts(db)) == 2


def test_count_only_round_matching_a_named_row_stays_put(db, tab):
    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": "10/5 샘플가, 샘플나, 샘플다"})
    _run(db)
    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": "10/5 핵심 딜 3개사"})

    for _ in range(2):
        p = _run(db)
        assert p["add"] == [] and p["retract"] == []
    assert len(_acts(db)) == 1


# ── 4. 메모를 고치면 ───────────────────────────────────────────────────────

def test_editing_the_memo_retracts_only_rows_from_that_column(db, tab):
    from app.models import ContactActivity

    person = tab["가담당"]
    # 시트에서 온 줄 · 앱에서 손으로 적은 줄 — 메모에 없어도 건드리지 않는다.
    db.add(ContactActivity(contact_id=person.id, kind="deal_intro", source="import",
                           content="샘플카", happened_at="2026-10-13",
                           month="2026-10", company_count=1,
                           company_names=json.dumps(["샘플카"], ensure_ascii=False)))
    manual_send.record(db, [person], manual_send.DEAL_INTRO, "2026-10-14",
                       company_names=["샘플타"], today=TODAY)
    db.commit()
    _memo(db, tab, person, {"10월 1차 딜소개": "10/5 샘플가\n10/12 샘플다"})
    _run(db)

    _memo(db, tab, person, {"10월 1차 딜소개": "10/5 샘플가\n10/15 샘플라"})
    p = _run(db)
    assert [r["day"] for r in memo_intro.view(p)["retract"]] == ["2026-10-12"]
    assert [i["day"] for i in p["add"]] == ["2026-10-15"]

    seen = sorted((a.happened_at, a.source) for a in _acts(db))
    assert seen == [("2026-10-05", "manual"), ("2026-10-13", "import"),
                    ("2026-10-14", "manual"), ("2026-10-15", "manual")]
    # 거둔 줄은 지우지 않고 숨긴다(되돌리기와 같은 숨김).
    from app.models import including_undone

    with including_undone(db):
        gone = [a for a in _acts(db) if a.happened_at == "2026-10-12"]
    assert len(gone) == 1 and gone[0].undone_at


def test_a_row_the_person_undid_is_not_revived(db, tab):
    person = tab["가담당"]
    _memo(db, tab, person, {"10월 1차 딜소개": "10/5 샘플가"})
    _run(db)
    key = memo_intro.batch_key(tab["cols"]["10월 1차 딜소개"].id, "2026-10-05")
    manual_send.undo(db, manual_send.rows_of(db, key, contact_id=person.id))
    db.commit()

    p = _run(db)
    assert [i["day"] for i in p["undone"]] == ["2026-10-05"]
    assert p["add"] == []
    assert _acts(db) == []


# ── 5. API · 권한 ─────────────────────────────────────────────────────────

@pytest.fixture()
def today_is(monkeypatch):
    monkeypatch.setattr("app.clock.today", lambda: TODAY)


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def _post(client, confirm, sheet=SHEET):
    return client.post("/api/contacts/memo-intro",
                       json={"sheet": sheet, "confirm": confirm})


def test_preview_writes_nothing_and_confirm_writes(client, db, tab, today_is):
    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": "10/5 샘플가\n10/12 샘플다"})
    _memo(db, tab, tab["나담당"], {"10월 1차 딜소개": "10/5 샘플가"})
    _login(client, "01000000001")

    got = _post(client, False)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["confirmed"] is False and len(body["plan"]["add"]) == 3
    assert body["plan"]["rounds"] == [
        {"column": "10월 1차 딜소개", "day": "2026-10-05", "people": 2},
        {"column": "10월 1차 딜소개", "day": "2026-10-12", "people": 1}]
    assert _acts(db) == []

    got = _post(client, True)
    assert got.status_code == 200, got.text
    assert got.json()["added"] == 3
    db.expire_all()
    assert len(_acts(db)) == 3
    assert _post(client, True).json()["added"] == 0


def test_someone_elses_tab_is_refused(client, db, tab, today_is):
    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": "10/5 샘플가"})
    _login(client, "01000000002")

    assert _post(client, True).status_code == 403
    assert _post(client, True, sheet="없는 탭").status_code == 400
    db.expire_all()
    assert _acts(db) == []


def test_a_foreign_row_in_the_tab_blocks_the_whole_run(client, db, tab, users,
                                                       today_is):
    from app.models import VcContact

    other = VcContact(user_id=users["u2"].id, source_sheet=SHEET, name="라담당",
                      firm="다라파트너스")
    db.add(other)
    db.commit()
    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": "10/5 샘플가"})
    _memo(db, tab, other, {"10월 1차 딜소개": "10/5 샘플가"})
    _login(client, "01000000001")

    assert _post(client, True).status_code == 404
    db.expire_all()
    assert _acts(db) == []


def test_the_button_stands_only_on_a_tab_with_a_deal_intro_column(client, db, tab):
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label="딜소개 칸 없는 탭", user_id=1))
    db.add(VcContact(user_id=1, source_sheet="딜소개 칸 없는 탭", name="마담당",
                     firm="가나벤처스"))
    db.commit()
    _login(client, "01000000001")

    mine = client.get(f"/contacts?sheet={SHEET}")
    bare = client.get("/contacts?sheet=딜소개 칸 없는 탭")
    assert mine.status_code == bare.status_code == 200
    assert 'id="memo-intro-btn"' in mine.text and "js/memo_intro.js" in mine.text
    assert "딜소개 칸 없는 탭" in bare.text and 'id="memo-intro-btn"' not in bare.text


# ── 6. 업무 보고 ──────────────────────────────────────────────────────────

def test_report_shows_the_memo_row_and_counts_it(db, tab, users):
    from app.services import report

    _memo(db, tab, tab["가담당"], {"10월 1차 딜소개": "10/5 샘플가, 샘플나"})
    _memo(db, tab, tab["나담당"], {"10월 1차 딜소개": "10/5 샘플가, 샘플나"})
    _run(db)

    data = report.monthly(db, 2026, 10, users["u1"], today=TODAY)
    deal = next(g for g in data["sends"]["groups"] if g["key"] == "deal_intro")
    memo_rows = [r for r in deal["rows"] if r.get("manual")]
    assert [r["title"] for r in memo_rows] == ["손으로 보냄(메모) · 딜 소개"]
    assert memo_rows[0]["sent"] == 2 and memo_rows[0]["companies"] == 2
    assert deal["contacts"] == 2 and deal["sent"] == 2
