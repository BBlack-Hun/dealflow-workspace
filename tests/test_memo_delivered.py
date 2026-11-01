"""명단 `N월 IR 요청` 칸의 `전달` → 업무 보고 `IR 자료 전달함` (`services/memo_delivered.py`).

  1. 읽기 — 한 줄 한 기업 · 한 줄 여러 기업 · 여러 줄 · `전달` 없는 줄 · `[전달]`/`[요청]` 태그
  2. 앱 기록과 같은 달 · 같은 사람 · 같은 기업이면 한 번만 센다
  3. 달 — 글 앞 날짜의 달이 칸의 달보다 앞선다 · 날짜가 없으면 칸의 달
  4. 사람 — 명단 주인으로 센다
  5. 화면 · 엑셀에 `앱 N + 명단 기록 M` 이 같은 글자로 선다

이름 · 회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import io
import json
from datetime import date

import pytest

from app.services import memo_delivered, report

SHEET = "투자사 시험 탭"
TODAY = date(2026, 11, 1)


@pytest.mark.parametrize("text, want", [
    ("8/5 샘플가 전달", [((8, 5), ["샘플가"])]),
    ("8/5 샘플가 전달, 샘플나 IR 전달", [((8, 5), ["샘플가", "샘플나"])]),
    ("8/5 샘플가IR전달 / 샘플나IR전달", [((8, 5), ["샘플가", "샘플나"])]),
    ("8/5 샘플가 전달\n8/12 샘플나 IR 전달 → 8/20 미팅",
     [((8, 5), ["샘플가"]), ((8, 12), ["샘플나"])]),
    # `전달` 이 붙은 조각만 — 앞 조각(`샘플가`)은 요청만 받은 것이다.
    ("8/5 샘플가 / (주)샘플나 IR 전달", [((8, 5), ["(주)샘플나"])]),
    ("8/5 샘플가 요청", []),
    ("8/5 샘플가 전달 예정\n8/6 미전달 샘플나", []),
    ("[전달] 샘플가, 샘플나", [(None, ["샘플가", "샘플나"])]),
    ("8/5 [요청] 샘플가 → 8/7 [전달]", [((8, 5), ["샘플가"])]),
    ("8/5 [요청] 샘플다", []),
    # 기업을 못 읽은 회차 — 빈 목록으로 남아 1건으로 센다.
    ("8/5 IR 전달", [((8, 5), [])]),
])
def test_parse(text, want):
    assert memo_delivered.parse(text) == want


@pytest.fixture()
def tab(db, users):
    """u1 의 딜공유 탭 — 9월 · 10월 IR 요청 칸, 담당자 둘."""
    from app.models import ContactColumn, SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id, layout=cc.INVESTOR_MONTHLY))
    cols = {label: ContactColumn(sheet=SHEET, label=label, position=pos, month=month)
            for pos, (label, month) in enumerate((("9월 IR 요청", "2026-09"),
                                                  ("10월 IR 요청", "2026-10"),
                                                  ("10월 미팅", "2026-10")))}
    db.add_all(cols.values())
    people = {name: VcContact(user_id=users["u1"].id, source_sheet=SHEET,
                              name=name, firm="가나벤처스")
              for name in ("가담당", "나담당")}
    db.add_all(people.values())
    db.commit()
    return {"cols": cols, **people}


def _memo(db, tab, person, values):
    from app.services import contact_columns as cc

    person.notes = json.dumps({cc.note_key(tab["cols"][k].id): v for k, v in values.items()},
                              ensure_ascii=False)
    db.commit()


def test_report_adds_memo_and_dedupes_app(db, users, tab):
    from app.models import IrRequest

    _memo(db, tab, tab["가담당"], {"10월 IR 요청": "10/5 샘플가 전달, 샘플나 전달\n10/9 샘플다 요청",
                                  "10월 미팅": "10/20 샘플가 전달 미팅"})
    _memo(db, tab, tab["나담당"], {"10월 IR 요청": "10/7 IR 전달"})
    # 같은 사람 · 같은 달 · 같은 기업을 앱에서도 전달함으로 적었다 → 한 번만.
    db.add(IrRequest(user_id=users["u1"].id, contact_id=tab["가담당"].id,
                     company_name="(주)샘플가", requested_at="2026-10-05",
                     status="delivered", delivered_at="2026-10-05"))
    db.commit()

    data = report.monthly(db, 2026, 10, users["u1"], today=TODAY)
    # 앱 1(샘플가) + 명단 2(샘플나 · 기업 못 읽은 줄 1). 미팅 칸 · `요청` 줄은 안 센다.
    assert data["ir_delivered"] == 3
    assert data["ir_delivered_memo"] == 2
    assert data["ir_delivered_note"] == "앱 1 + 명단 기록 2 (기업명 못 읽은 줄 1건 포함)"


def test_month_prefers_written_date(db, users, tab):
    # 9월 칸에 적었지만 날짜는 10/2 → 10월. 날짜 없는 줄은 칸의 달(9월).
    # (날짜 없는 줄이 **뒤에** 오면 앞 회차에 이어 붙는다 — `company_names.rounds`.)
    _memo(db, tab, tab["가담당"], {"9월 IR 요청": "샘플나 전달\n10/2 샘플가 전달"})

    sep = report.monthly(db, 2026, 9, users["u1"], today=TODAY)
    oct_ = report.monthly(db, 2026, 10, users["u1"], today=TODAY)
    assert (sep["ir_delivered"], oct_["ir_delivered"]) == (1, 1)
    # 연간도 같은 수를 더한다 — 앱 기록이 없는 달도 접히지 않는다.
    year = report.yearly(db, 2026, users["u1"], today=TODAY)
    assert year["totals"]["ir_delivered"] == 2
    assert not year["month_reports"][8]["empty"]


def test_counted_for_list_owner(db, users, tab):
    _memo(db, tab, tab["가담당"], {"10월 IR 요청": "10/5 샘플가 전달"})

    assert report.monthly(db, 2026, 10, users["u1"], today=TODAY)["ir_delivered"] == 1
    assert report.monthly(db, 2026, 10, users["u2"], today=TODAY)["ir_delivered"] == 0
    assert report.monthly(db, 2026, 10, None, today=TODAY)["ir_delivered"] == 1


def test_screen_and_excel_show_split(db, users, tab, logged_in):
    from openpyxl import load_workbook

    _memo(db, tab, tab["가담당"], {"10월 IR 요청": "10/5 샘플가 전달"})

    page = logged_in.get("/report?month=2026-10")
    assert "앱 0 + 명단 기록 1" in page.text

    got = logged_in.get("/api/export/report.xlsx?month=2026-10")
    cells = [str(c.value) for ws in load_workbook(io.BytesIO(got.content)).worksheets
             for row in ws.iter_rows() for c in row if c.value is not None]
    assert any("앱 0 + 명단 기록 1" in c for c in cells)
