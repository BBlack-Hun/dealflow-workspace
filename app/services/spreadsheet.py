"""엑셀·CSV 를 읽고 쓴다.

업로드는 팀원마다 관리하는 '투자사 관리 현황' 시트를 그대로 올리는 용도다.
구글 시트에서 내려받으면 .xlsx 이고, 가끔 .csv 로 내보내는 사람도 있어 둘 다 받는다.
읽은 결과는 기존 임포트 파서(`sheet_import.parse_sheet_a`)가 쓰는 모양,
즉 **문자열 2차원 배열**로 맞춘다 — 파서를 새로 만들지 않기 위해서다.

내려받기는 화면의 표를 그대로 엑셀로 준다. 숫자는 숫자로 쓴다(엑셀에서 합계·정렬이
되어야 한다). 다만 휴대폰번호처럼 0 으로 시작하는 값은 문자열로 둔다.
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# 업로드 상한. 팀 시트는 수백 행이라 이보다 훨씬 작다. 큰 파일로 메모리를 먹는 것을 막는다.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# .xlsx 는 zip 이다. 위 상한은 압축된 크기라, 풀린 크기도 따로 막는다(작은 파일이 풀리며 커지는 것).
MAX_UNZIPPED_BYTES = 100 * 1024 * 1024
# 시트 하나(read_tabs 는 모든 탭 합)에서 읽는 행 · 열 상한. 팀 시트는 수백 행 · 수십 열이다.
# 열은 **값이 든 칸**으로 잰다 — 시트가 적어 둔 범위가 아니다(`_sheet_rows`).
MAX_ROWS = 50_000
MAX_COLS = 300
EXCEL_SUFFIXES = (".xlsx", ".xlsm")
CSV_SUFFIXES = (".csv", ".tsv", ".txt")


class SpreadsheetError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 실패 사유."""


def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def sheet_names(filename: str, data: bytes) -> List[str]:
    """엑셀이면 시트 이름 목록, CSV 면 빈 목록."""
    _check_upload(filename, data)
    if not _is_excel(filename):
        return []
    wb = _load_workbook(data)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def read_rows(filename: str, data: bytes, sheet: Optional[str] = None) -> List[List[str]]:
    """업로드 파일 → 문자열 2차원 배열.

    엑셀은 시트를 고를 수 있고(없으면 첫 시트), CSV 는 시트 개념이 없다.
    """
    _check_upload(filename, data)
    if _is_excel(filename):
        return _read_excel(data, sheet)
    return _read_csv(data)


def read_tabs(filename: str, data: bytes) -> List[Tuple[str, List[List[str]]]]:
    """업로드 파일 → **탭마다** `(탭 이름, 문자열 2차원 배열)`. CSV 는 이름이 빈 탭 하나.

    어느 탭을 읽을지 **내용을 보고** 고르는 자리가 쓴다(`series_a_import.
    read_upload` — 머리글이 맞는 탭 하나). 탭마다 `read_rows` 를 부르면 그때마다
    워크북을 처음부터 다시 연다. 크기 · 빈 파일 · 형식 검사는 `read_rows` 와 같다.
    """
    _check_upload(filename, data)
    if not _is_excel(filename):
        return [("", _read_csv(data))]
    wb = _load_workbook(data)
    try:
        tabs, left = [], MAX_ROWS
        for ws in wb.worksheets:
            rows = _sheet_rows(ws, left)
            left -= len(rows)
            tabs.append((ws.title, rows))
        return tabs
    finally:
        wb.close()


def _check_upload(filename: str, data: bytes) -> None:
    """올린 파일을 읽기 전에 — 크기 상한 · 빈 파일 · 받는 형식(.xlsx · .csv)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise SpreadsheetError(
            f"파일이 너무 큽니다 ({len(data) // 1024 // 1024}MB). "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024}MB 이하로 올려주세요."
        )
    if not data:
        raise SpreadsheetError("빈 파일입니다.")
    if not (_is_excel(filename) or filename.lower().endswith(CSV_SUFFIXES)):
        raise SpreadsheetError(
            f"읽을 수 없는 형식입니다: {filename}. .xlsx 또는 .csv 로 올려주세요."
        )


def _is_excel(filename: str) -> bool:
    return filename.lower().endswith(EXCEL_SUFFIXES)


_OPEN_FAILED = "엑셀 파일을 열지 못했습니다. 파일이 깨지지 않았는지, .xlsx 로 저장했는지 확인해주세요."


def _load_workbook(data: bytes):
    """올린 엑셀을 여는 유일한 자리 — 열기 전에 풀린 크기를 본다."""
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - 배포 이미지에는 항상 있다
        raise SpreadsheetError("엑셀 읽기 모듈(openpyxl)이 설치되지 않았습니다.")
    try:
        # 목록의 크기를 믿어도 된다 — zipfile 이 풀 때 그 크기를 넘는 내용은 버리고 오류를 낸다.
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            unzipped = sum(i.file_size for i in zf.infolist())
    except Exception:
        log.warning("올린 엑셀을 zip 으로 열지 못함", exc_info=True)
        raise SpreadsheetError(_OPEN_FAILED)
    if unzipped > MAX_UNZIPPED_BYTES:
        raise SpreadsheetError(
            f"엑셀 내용이 너무 큽니다(풀린 크기 {unzipped // 1024 // 1024}MB). "
            f"{MAX_UNZIPPED_BYTES // 1024 // 1024}MB 이하로 줄여 올려주세요."
        )
    try:
        # data_only=True → 수식이 아니라 계산된 값을 읽는다(시트에 수식이 많다).
        return openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        # openpyxl 원문은 내부 경로 · 구조가 드러나서 사용자에게 싣지 않는다 — 로그에만.
        log.warning("올린 엑셀을 열지 못함", exc_info=True)
        raise SpreadsheetError(_OPEN_FAILED)


def _sheet_rows(ws, max_rows: int = MAX_ROWS) -> List[List[str]]:
    """시트 하나 → 문자열 2차원 배열. 행 · 열 상한을 넘으면 읽다 말고 거절한다.

    열은 **값이 든 칸**으로 잰다. 시트가 적어 둔 범위(dimension)는 서식만 넓게 깔려
    있어도 커지고, 실제보다 좁게 적혀 있기도 하다 — 범위로 재면 정상 파일이 막히거나
    값이 말없이 잘린다. 줄 폭은 값이 든 마지막 칸에 맞춰 고르게 채운다 — 예전처럼
    모든 줄의 칸 수가 같다.
    """
    rows: List[List[str]] = []
    width = 0
    try:
        for idx, cells in _written_cells(ws):
            if idx > max_rows:
                raise SpreadsheetError(
                    f"행이 너무 많습니다. 한 파일에서 {MAX_ROWS:,}행까지 읽습니다 — "
                    "쓰지 않는 행을 지우고 올려주세요."
                )
            if idx <= len(rows):        # 순서가 어긋난 줄은 openpyxl 처럼 건너뛴다
                continue
            values = {}
            for cell in cells:
                text = _cell_to_text(cell["value"])
                if not text:
                    continue
                if cell["column"] > MAX_COLS:
                    raise SpreadsheetError(
                        f"'{ws.title}' 시트의 열이 너무 많습니다({MAX_COLS}열 너머에 값이 "
                        f"있습니다). {MAX_COLS}열까지 읽습니다 — 쓰지 않는 열을 지우고 올려주세요."
                    )
                values[cell["column"]] = text
            rows.extend([] for _ in range(idx - 1 - len(rows)))   # 파일에 없는 빈 줄
            last = max(values, default=0)
            rows.append([values.get(col, "") for col in range(1, last + 1)])
            width = max(width, last)
    except SpreadsheetError:
        raise
    except Exception:
        # 칸은 읽으면서 푼다 — 여기서 깨진 것도 원문은 로그에만 남긴다.
        log.warning("올린 엑셀의 '%s' 시트를 읽지 못함", ws.title, exc_info=True)
        raise SpreadsheetError(_OPEN_FAILED)
    return [row + [""] * (width - len(row)) for row in rows]


def _written_cells(ws):
    """줄마다 `(줄 번호, [칸, …])` — **파일에 적힌 칸만**, 빈 칸을 채우지 않고.

    `ws.iter_rows` 는 줄마다 가장 오른쪽 칸까지 빈 칸을 채워 돌려준다. 서식만 끝
    열(16,384번째)까지 깔린 줄이 수만 줄이면 그 채우기에만 수십 초가 든다. 그래서
    openpyxl 이 읽기 전용 시트에서 쓰는 파서를 같은 인자로 직접 돌린다(3.1 의
    `ReadOnlyWorksheet._cells_by_row` 와 같은 부름 — 판을 올리면 시험이 잡는다).
    칸은 `{"column": 열 번호, "value": 값, …}` 이다.
    """
    from openpyxl.worksheet._reader import WorkSheetParser

    wb = ws.parent
    with ws._get_source() as src:
        parser = WorkSheetParser(src, ws._shared_strings, data_only=wb.data_only,
                                 epoch=wb.epoch, date_formats=wb._date_formats,
                                 timedelta_formats=wb._timedelta_formats)
        yield from parser.parse()


def _read_excel(data: bytes, sheet: Optional[str]) -> List[List[str]]:
    wb = _load_workbook(data)
    try:
        if sheet:
            if sheet not in wb.sheetnames:
                raise SpreadsheetError(
                    f"'{sheet}' 시트가 없습니다. 있는 시트: {', '.join(wb.sheetnames)}"
                )
            ws = wb[sheet]
        else:
            ws = wb[wb.sheetnames[0]]
        return _sheet_rows(ws)
    finally:
        wb.close()


def _read_csv(data: bytes) -> List[List[str]]:
    # 구글 시트는 UTF-8(BOM), 국내 엑셀은 CP949 로 내보내는 일이 많다.
    for encoding in ("utf-8-sig", "cp949", "utf-8"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SpreadsheetError("문자 인코딩을 알 수 없습니다. UTF-8 로 저장해 다시 올려주세요.")
    return [[(c or "").strip() for c in row] for row in csv.reader(io.StringIO(text))]


# --- 내려받기 ---------------------------------------------------------------

# 이 컬럼들은 숫자로 보여도 문자열로 써야 한다(앞의 0 이 사라지면 못 쓰는 값이 된다).
TEXT_COLUMNS = ("휴대폰", "연락처", "전화", "번호")


def _looks_numeric(value: str) -> bool:
    try:
        float(value.replace(",", ""))
    except (TypeError, ValueError):
        return False
    return not value.startswith("0") or value in ("0", "0.0")


# 내보낸 파일에 남기는 표식. 이 파일을 그대로 업로드하면 활동 이력이 뻥튀기된다
# (내보내기의 'IR 요청(누적)' 류 컬럼을 임포트 파서가 월별 활동으로 읽는다).
# 업로드에서 이 표식을 보고 막는다.
EXPORT_MARK = "dealflow-export"


def is_export_file(filename: str, data: bytes) -> bool:
    """우리가 내보낸 파일인지."""
    if not _is_excel(filename):
        return False
    try:
        _check_upload(filename, data)
        wb = _load_workbook(data)
    except SpreadsheetError:
        return False
    try:
        return (wb.properties.keywords or "") == EXPORT_MARK
    finally:
        wb.close()


def write_plain_xlsx(sheet_title: str, rows: Sequence[Sequence[Any]],
                     head_row: int = 1, widths: Sequence[int] = ()) -> bytes:
    """머리행 위치를 골라 쓰는 표. **내보내기 표식을 붙이지 않는다.**

    업로드용 샘플 양식이 이걸 쓴다. `write_xlsx` 로 만들면 표식이 붙어서
    그 파일을 그대로 올렸을 때 "내보낸 파일은 올릴 수 없습니다" 로 막힌다 —
    샘플이 샘플 구실을 못 한다.

    실제 명단 시트는 머리글이 2행이고 1행에 월 라벨이 온다. 그 모양을 그대로
    만들 수 있어야 파서가 읽는 것과 같은 양식이 된다.
    """
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:  # pragma: no cover
        raise SpreadsheetError("엑셀 쓰기 모듈(openpyxl)이 설치되지 않았습니다.")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _safe_sheet_title(sheet_title)
    for row in rows:
        ws.append(["" if v is None else v for v in row])

    head_fill = PatternFill("solid", fgColor="EEF2F7")
    for cell in ws[head_row]:
        cell.font = Font(bold=True)
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = f"A{head_row + 1}"

    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    return workbook_bytes(wb)


def write_xlsx(sheet_title: str, headers: Sequence[str],
               rows: Sequence[Sequence[Any]]) -> bytes:
    """표 하나를 담은 .xlsx 바이트. 머리행 고정 + 컬럼 폭 자동."""
    return write_xlsx_sheets([(sheet_title, headers, rows)])


def write_xlsx_sheets(sheets: Sequence[tuple]) -> bytes:
    """표 여러 장 — `(시트 이름, 머리글, 줄)` 마다 한 장. 꾸밈은 `write_xlsx` 와 같다.

    이름이 31자에서 잘려 겹치면 openpyxl 이 뒤에 숫자를 붙인다(`가나다1`)."""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:  # pragma: no cover
        raise SpreadsheetError("엑셀 쓰기 모듈(openpyxl)이 설치되지 않았습니다.")

    wb = openpyxl.Workbook()
    wb.properties.keywords = EXPORT_MARK   # 되올리기 방지 표식
    wb.remove(wb.active)
    for sheet_title, headers, rows in sheets:
        # 엑셀 시트 이름 제한: 31자, : \ / ? * [ ] 금지
        ws = wb.create_sheet(_safe_sheet_title(sheet_title))

        ws.append(list(headers))
        head_fill = PatternFill("solid", fgColor="EEF2F7")
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = head_fill
            cell.alignment = Alignment(vertical="center")

        text_cols = {i for i, h in enumerate(headers)
                     if any(t in str(h) for t in TEXT_COLUMNS)}

        for row in rows:
            out = []
            for i, value in enumerate(row):
                if value is None:
                    out.append("")
                elif isinstance(value, (int, float)):
                    out.append(value)
                elif i not in text_cols and isinstance(value, str) and _looks_numeric(value):
                    out.append(float(value.replace(",", "")))
                else:
                    out.append(str(value))
            ws.append(out)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for i, header in enumerate(headers, start=1):
            longest = max(
                [_display_width(str(header))]
                + [_display_width(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r)]
                or [8]
            )
            ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 8), 55)

    return workbook_bytes(wb)


def workbook_bytes(wb) -> bytes:
    """워크북 → .xlsx 바이트. **앱이 만드는 엑셀은 모두 여기서 저장한다.**

    openpyxl 은 `=` 로 시작하는 글자를 수식으로 저장한다. 내려받는 표의 글은 사람이
    적은 값(이름 · 메모 · 회차명)이라 적힌 그대로 보여야 하고, 앱은 수식을 쓰지
    않는다 — 그래서 수식으로 잡힌 칸은 모두 글자 칸으로 되돌린다. 숫자 · 날짜 칸은
    건드리지 않는다. 저장을 이 한 곳에 모아 두어 새 내려받기도 따로 챙길 것이 없다.
    """
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def _safe_sheet_title(title: str) -> str:
    for ch in ":\\/?*[]":
        title = title.replace(ch, " ")
    return (title.strip() or "Sheet")[:31]


def _display_width(text: str) -> int:
    """한글은 폭이 두 배라 그만큼 세어야 컬럼이 안 잘린다."""
    return sum(2 if ord(ch) > 0x2000 else 1 for ch in text)


def content_disposition(filename: str) -> Dict[str, str]:
    """한글 파일명이 깨지지 않게 RFC 5987 형식으로 넣는다."""
    from urllib.parse import quote

    return {"Content-Disposition":
            f"attachment; filename=\"download.xlsx\"; filename*=UTF-8''{quote(filename)}"}


XLSX_MEDIA_TYPE = ("application/vnd.openxmlformats-officedocument"
                   ".spreadsheetml.sheet")
