"""내려받는 엑셀의 글자 칸 — `=` 로 시작해도 적힌 그대로 글자로 나간다.

openpyxl 은 `=` 로 시작하는 글자를 수식으로 저장한다. 앱이 만드는 엑셀은 모두
`spreadsheet.workbook_bytes` 한 곳에서 저장하고, 거기서 수식 칸을 글자 칸으로
되돌린다.

지키는 것:
1. 표 내려받기 · 업로드 양식 · 업무 보고 — `=` 로 시작하는 글이 글자 칸으로 나간다.
2. 숫자 · 날짜 칸은 그대로다.
3. 앱에서 워크북을 저장하는 자리는 `workbook_bytes` 하나뿐이다.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD
from .test_report_sends import _round

openpyxl = pytest.importorskip("openpyxl")

from app.services import spreadsheet as sp  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _cells(content: bytes) -> dict:
    """값 → 칸. 다시 열어 본 그대로다(수식이면 `data_type` 이 `f`)."""
    wb = openpyxl.load_workbook(io.BytesIO(content))
    return {c.value: c for ws in wb.worksheets for row in ws.iter_rows()
            for c in row if c.value is not None}


def test_table_writes_equals_text_as_text():
    content = sp.write_xlsx("표", ["이름", "메모", "건수", "휴대폰"],
                            [["=가나다", "=1+2", 3, "010-0000-0001"]])
    cells = _cells(content)
    assert cells["=가나다"].data_type == "s"
    assert cells["=1+2"].data_type == "s"
    assert cells[3].data_type == "n"                  # 숫자는 숫자
    assert cells["010-0000-0001"].data_type == "s"


def test_plain_sheet_writes_equals_text_as_text():
    content = sp.write_plain_xlsx("양식", [["머리"], ["=1+2", 5, date(2026, 8, 27)]])
    cells = _cells(content)
    assert cells["=1+2"].data_type == "s"
    assert cells[5].data_type == "n"
    assert datetime(2026, 8, 27) in cells               # 날짜는 날짜


def test_contacts_export_keeps_memo_as_text(client, db, users):
    from app.models import VcContact

    db.add(VcContact(user_id=1, name="홍길동", firm="가나벤처스", memo="=1+2",
                     status="active"))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.get("/api/export/contacts.xlsx")
    assert r.status_code == 200
    assert _cells(r.content)["=1+2"].data_type == "s"


def test_report_keeps_round_title_as_text(client, db, users):
    _round(db, users, title="=1+1 회차", when=date(2026, 8, 27), sent=1)
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.get("/api/export/report.xlsx?month=2026-08")
    assert r.status_code == 200
    assert _cells(r.content)["=1+1 회차"].data_type == "s"


def test_workbooks_are_saved_in_one_place():
    """워크북을 만드는 곳은 저장을 `workbook_bytes` 에 맡긴다 — 새 내려받기도 같다."""
    makers = [p for p in (ROOT / "app").rglob("*.py")
              if "Workbook(" in p.read_text(encoding="utf-8")]
    assert makers, "워크북을 만드는 곳을 못 찾았다 — 검사가 헛돈다"
    for path in makers:
        text = path.read_text(encoding="utf-8")
        saves = len(re.findall(r"\.save\(", text))
        if path.name == "spreadsheet.py":
            assert saves == 1, "spreadsheet.py 의 저장은 workbook_bytes 하나여야 한다"
        else:
            assert saves == 0 and "workbook_bytes(" in text, path
