"""올린 엑셀을 읽기 전 · 읽는 중의 상한(`services/spreadsheet`).

지키는 것:
1. 시트 목록 보기도 로그인해야 하고 크기 검사를 지난다.
2. 압축이 풀리며 커지는 파일은 **열기 전에** 거절한다.
3. 시트가 적어 둔 범위가 커도 행 · 열 상한까지만 읽고, 넘으면 분명히 거절한다.
4. 보통 시트는 예전과 똑같이 읽힌다.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from .conftest import DEMO_PASSWORD

openpyxl = pytest.importorskip("openpyxl")

from app.services import spreadsheet as sp  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _book(*tabs) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for i, rows in enumerate(tabs):
        ws = wb.create_sheet(f"탭{i + 1}")
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _sheet_xml(dimension: str, cells) -> str:
    """`cells` = [(행, 열 글자)] — 숫자 1 을 적은 칸들. dimension 이 빈 글자면 범위 태그를 뺀다."""
    dim = f'<dimension ref="{dimension}"/>' if dimension else ""
    rows = "".join(f'<row r="{r}"><c r="{col}{r}"><v>1</v></c></row>' for r, col in cells)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"{dim}<sheetData>{rows}</sheetData></worksheet>")


def _forged(*sheet_xmls: str) -> bytes:
    """탭 수만큼 정상 워크북을 만든 뒤 시트 XML 만 바꿔 끼운다 — 파일은 몇 KB 다."""
    src = zipfile.ZipFile(io.BytesIO(_book(*[[["x"]] for _ in sheet_xmls])))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            for i, xml in enumerate(sheet_xmls, start=1):
                if item.filename == f"xl/worksheets/sheet{i}.xml":
                    data = xml.encode()
            dst.writestr(item.filename, data)
    return out.getvalue()


# --- 1. 시트 목록 ------------------------------------------------------------

def test_sheet_list_needs_login(client):
    r = client.post("/api/import/contacts/sheets",
                    files={"file": ("현황.xlsx", _book([["a"]]), XLSX)})
    assert r.status_code == 401


def test_sheet_list_works_when_logged_in(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.post("/api/import/contacts/sheets",
                    files={"file": ("현황.xlsx", _book([["a"]], [["b"]]), XLSX)})
    assert r.status_code == 200, r.text
    assert r.json()["sheets"] == ["탭1", "탭2"]


def test_sheet_names_checks_size_and_empty():
    with pytest.raises(sp.SpreadsheetError, match="너무 큽니다"):
        sp.sheet_names("a.xlsx", b"x" * (sp.MAX_UPLOAD_BYTES + 1))
    with pytest.raises(sp.SpreadsheetError, match="빈 파일"):
        sp.sheet_names("a.xlsx", b"")


# --- 2. 풀린 크기 ------------------------------------------------------------

def test_inflating_zip_is_refused_before_opening(monkeypatch, client, users):
    """압축된 크기는 작아도 풀린 크기가 상한을 넘으면 openpyxl 에 넘기지 않는다."""
    buf = io.BytesIO(_book([["a"]]))
    with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
        with zf.open("xl/media/pad.bin", "w") as f:   # 0 바이트를 흘려 써서 메모리를 안 쓴다
            chunk = bytes(1024 * 1024)
            for _ in range(sp.MAX_UNZIPPED_BYTES // len(chunk) + 1):
                f.write(chunk)
    data = buf.getvalue()
    assert len(data) < sp.MAX_UPLOAD_BYTES       # 크기 상한은 지나는 파일

    opened = []
    monkeypatch.setattr(openpyxl, "load_workbook", lambda *a, **k: opened.append(1))
    for call in (lambda: sp.read_rows("a.xlsx", data), lambda: sp.read_tabs("a.xlsx", data),
                 lambda: sp.sheet_names("a.xlsx", data)):
        with pytest.raises(sp.SpreadsheetError, match="풀린 크기"):
            call()
    assert sp.is_export_file("a.xlsx", data) is False
    assert opened == []

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.post("/api/import/contacts", files={"file": ("a.xlsx", data, XLSX)},
                    data={"dry_run": "true"})
    assert r.status_code == 400 and "풀린 크기" in r.json()["detail"]


def test_broken_file_message_does_not_carry_library_text():
    # zip 이 아님 / zip 이지만 엑셀 구조가 아님 — 둘 다 같은 일반 문구
    not_xlsx = io.BytesIO()
    with zipfile.ZipFile(not_xlsx, "w") as zf:
        zf.writestr("hello.txt", "hi")
    for data in (b"not a zip at all", not_xlsx.getvalue()):
        with pytest.raises(sp.SpreadsheetError) as err:
            sp.read_rows("a.xlsx", data)
        assert str(err.value) == sp._OPEN_FAILED


# --- 3. 행 · 열 상한 ---------------------------------------------------------

def test_huge_declared_columns_are_refused():
    data = _forged(_sheet_xml("A1:XFD1048576", [(1, "A"), (1048576, "XFD")]))
    with pytest.raises(sp.SpreadsheetError, match="열이 너무 많습니다"):
        sp.read_rows("a.xlsx", data)
    with pytest.raises(sp.SpreadsheetError, match="열이 너무 많습니다"):
        sp.read_tabs("a.xlsx", data)


def test_far_away_row_is_refused_not_padded():
    """1행과 맨 끝 행만 있는 시트 — 사이를 빈 줄로 다 채우지 않고 상한에서 멈춘다."""
    data = _forged(_sheet_xml("A1:B1048576", [(1, "A"), (1048576, "B")]))
    with pytest.raises(sp.SpreadsheetError, match="행이 너무 많습니다"):
        sp.read_rows("a.xlsx", data)


def test_missing_dimension_caps_columns():
    """범위 태그가 없으면 열 상한까지만 읽는다."""
    rows = sp.read_rows("a.xlsx", _forged(_sheet_xml("", [(1, "A"), (2, "XFD")])))
    assert len(rows) == 2 and {len(r) for r in rows} == {sp.MAX_COLS}


def test_row_cap_counts_all_tabs_together():
    """탭마다 상한 안이어도 모든 탭을 합쳐 넘으면 거절한다(read_tabs)."""
    half = sp.MAX_ROWS // 2 + 1
    tab = _sheet_xml(f"A1:A{half}", [(1, "A"), (half, "A")])
    assert len(sp.read_rows("a.xlsx", _forged(tab))) == half
    with pytest.raises(sp.SpreadsheetError, match="행이 너무 많습니다"):
        sp.read_tabs("a.xlsx", _forged(tab, tab))


# --- 4. 보통 시트 ------------------------------------------------------------

def test_normal_sheet_reads_the_same():
    data = _book([["이름", "회사", None], ["홍길동", "가나벤처스", 3.0]], [["둘째"]])
    assert sp.read_rows("a.xlsx", data) == [["이름", "회사", ""], ["홍길동", "가나벤처스", "3"]]
    assert sp.read_tabs("a.xlsx", data) == [
        ("탭1", [["이름", "회사", ""], ["홍길동", "가나벤처스", "3"]]),
        ("탭2", [["둘째"]]),
    ]
    assert sp.sheet_names("a.xlsx", data) == ["탭1", "탭2"]
