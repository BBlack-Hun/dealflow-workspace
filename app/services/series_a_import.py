"""`Series A 이상 기업` 시트 → `series_a_companies` 표.

부르는 쪽은 `scripts/import_series_a.py` 하나다(검사도 여기를 부른다). 시트
주소는 어디에도 적지 않는다 — **내려받은 파일 경로**(CSV · xlsx)를 받는다.

화면의 [딜소개 문구 올리기](`services/series_a_pitch_upload.py`)도 이 파일의
읽기(`read_upload` · `parse`) · 맞추기(`match`) · 칸 판정(`cell_plan`)을 그대로
쓴다 — 줄을 만들지 않고 `딜소개 문구` 칸만 바꾸는 것만 다르다.

## 칸은 **머리글 이름**으로 찾는다

자리로 짐작하지 않는다. 시트는 사람이 계속 쓰는 문서라 칸이 늘면 자리가
밀린다. 머리글은 띄어쓰기를 지우고 견준다 — 원본에 `기업구분 ` 처럼 뒤에
공백이 붙은 머리글이 실제로 있다.

**옛 이름과 화면 이름을 함께 받는다.** 화면은 IR 기업 현황의 두 탭을 따라
`사업분야 대분류` → `대분류`, `기업구분` → `투자라운드` 로 부른다. 시트 머리글은
옛 이름이라, 화면을 따라 여기서 옛 이름을 빼면 **다음 가져오기에서 그 칸이
조용히 빈다**(`scripts/import_company_sheets.py` 가 같은 이유로 둘을 같이 받는다).

## 한 줄을 무엇으로 알아보나 — 가져오기 열쇠(`import_key`)

한 줄은 **받은 딜 한 건**(언제 · 어느 투자사의 누가 넘겨 주었나)이다. 그래서
열쇠는 시트 줄의 **(기업명, 수신 일자, 공유 심사역, 회사)** 다(`import_key`).
같은 기업이 다른 날 또 들어오면 다른 줄이고(후속 투자 연계로 다시 오는 일이
있다), **같은 날이라도 넘겨 준 곳이 다르면 다른 줄이다** — 열쇠가
`(기업명, 수신 일자)` 뿐이던 때는 둘째 딜이 겹친 줄로 버려졌다.

기업명 · 회사는 `deal_history._key` 로 맞춘다 — (주)·띄어쓰기 차이로 같은 딜이
두 줄이 되지 않게. 이 규칙은 **새로 짓지 않는다**: 기업 이름을 맞추는 자리가
저장소에 그 하나다. 공유 심사역은 띄어쓰기만 지운다.

**열쇠는 가져온 그때의 시트 값이고, 줄의 `import_key` 칸에 적어 둔다.** 앱에서
기업명 · 수신 일자를 고쳐도 다시 셈하지 않는다 — 고칠 때마다 열쇠가 바뀌면
다음 가져오기에서 같은 딜이 새 줄로 또 선다.

시트의 `NO` 는 열쇠로 쓰지 않는다 — 원본에 번호가 빈 줄이 있고, 사람이 줄을
끼워 넣으면 번호가 밀린다.

## 열쇠가 없는 줄 — 앱에서 더한 줄 · 열쇠 칸이 생기기 전에 들어온 줄

그런 줄은 예전 열쇠 `(기업명, 수신 일자)` 로 **한 번** 맞추고, 맞으면 그 시트
줄의 열쇠를 적는다(`linked`). 그 뒤로는 열쇠로 맞는다. 고르는 차례(`match`):

  1. 열쇠가 적힌 줄 중 같은 열쇠.
  2. 열쇠가 없는 줄 중 **지금 값으로 셈한 열쇠까지 같은** 줄 — 같은
     `(기업명, 수신 일자)` 의 시트 줄이 둘이어도 제 짝을 먼저 가져간다.
  3. 남은 시트 줄은 `(기업명, 수신 일자)` 로 — **열쇠 없는 줄도 하나, 그 줄을
     바라는 시트 줄도 하나일 때만.** 어느 쪽이든 둘 이상이면 고르지 않고 건너뛰어
     수를 알린다(`ambiguous`). 아무거나 고르면 남의 딜에 값을 채우고, 새로
     만들면 같은 딜이 두 줄이 된다 — 사람이 앱에서 정리한 뒤 다시 돌리면 된다.

## 몇 번을 다시 돌려도 결과가 같다

  · 새 열쇠 → 줄을 만든다.
  · 있는 열쇠 → **앱에서 빈 칸만** 시트 값으로 채운다. 앱에서 고친 값은 덮지
    않는다(`overwrite=True` 일 때만 덮는다) — 화면에서 고친 내용이 가져오기
    한 번에 사라지면 안 된다.
  · 시트에서 빈 칸은 아무것도 지우지 않는다.
  · 시트 안에서 같은 열쇠가 두 번 나오면 **앞 줄만** 쓰고 수를 알린다.
  · 시트에서 사라진 줄은 앱에서 지우지 않는다 — 시트를 지운 것인지 앱에서
    더한 것인지 이 쪽에서는 모른다.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SeriesACompany
from .deal_history import _key as name_key

#: 모델 칸 → 받는 시트 머리글(띄어쓰기를 지우고 소문자로 견준다). **차례가 곧
#: 시트의 차례다.** 옛 이름을 지우지 마라 — 시트 머리글이 그 이름이다(머리말).
HEADERS: Dict[str, Tuple[str, ...]] = {
    "received_at": ("수신 일자", "수신일"),
    "deal_type": ("Type", "유형"),
    "assignee_name": ("담당팀원", "담당자"),
    "shared_by": ("공유 심사역",),
    "source_firm": ("회사", "투자사"),
    "name": ("기업명",),
    "sector_major": ("사업분야 대분류", "대분류"),
    "sector_minor": ("소분류",),
    "series": ("기업구분", "투자라운드"),
    "detail": ("상세 내용",),
    "deal_pitch": ("딜소개 문구", "딜 소개 문구"),
}

#: 이 칸들이 머리글에 다 있어야 이 시트로 본다. 통째로 내려받은 워크북에는
#: 탭이 여럿이라, `기업명` 하나만 보면 IR 기업 현황 탭이 걸린다.
SIGNATURE = ("name", "received_at", "shared_by")

_DATE = re.compile(r"^\s*(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\s*\.?\s*$")


def _norm_head(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


_LOOKUP = {_norm_head(alias): attr for attr, aliases in HEADERS.items()
           for alias in aliases}


def cell_text(value) -> str:
    """칸 하나를 글자로. 날짜는 `YYYY-MM-DD`, 정수 모양의 수는 소수점 없이."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def day_text(value: str) -> str:
    """`2026.7.1` · `2026/07/01` → `2026-07-01`. 날짜가 아니면 **적힌 그대로**.

    날짜로 못 읽는 글자(`날짜 미정`)를 지우지 않는다 — 사람이 적은 사실이고,
    표는 그런 줄을 맨 아래로 보낸다(`routers/series_a.py` 의 `sort_rows`).
    """
    m = _DATE.match(value or "")
    if not m:
        return (value or "").strip()
    y, mo, d = (int(g) for g in m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return (value or "").strip()


def header_map(row: Sequence) -> Dict[int, str]:
    """머리글 한 줄 → `{칸 번호: 모델 칸}`. 모르는 머리글(`NO`)은 빠진다."""
    out: Dict[int, str] = {}
    for i, cell in enumerate(row):
        attr = _LOOKUP.get(_norm_head(cell_text(cell)))
        if attr and attr not in out.values():
            out[i] = attr
    return out


def find_header(rows: Sequence[Sequence]) -> Optional[int]:
    """머리글 줄의 번호. 맨 위 열 줄 안에서 `SIGNATURE` 가 다 있는 첫 줄."""
    for i, row in enumerate(rows[:10]):
        if set(SIGNATURE) <= set(header_map(row).values()):
            return i
    return None


@dataclass
class Parsed:
    records: List[dict] = field(default_factory=list)
    #: 기업명이 빈 줄(합계·메모 줄) — 건너뛰고 수만 알린다.
    no_name: int = 0
    #: 시트에 없는 칸(그 칸은 안 들어온다).
    missing: List[str] = field(default_factory=list)


def parse(rows: Sequence[Sequence]) -> Parsed:
    """시트의 줄들 → 넣을 값들. 머리글을 못 찾으면 `ValueError`."""
    at = find_header(rows)
    if at is None:
        raise ValueError("머리글 줄을 못 찾았습니다 — `기업명` · `수신 일자` · "
                         "`공유 심사역` 이 한 줄에 있어야 합니다")
    columns = header_map(rows[at])
    out = Parsed(missing=[HEADERS[a][0] for a in HEADERS if a not in columns.values()])
    for row in rows[at + 1:]:
        values = {attr: cell_text(row[i]) if i < len(row) else ""
                  for i, attr in columns.items()}
        if not any(values.values()):
            continue                      # 빈 줄
        if not values.get("name"):
            out.no_name += 1
            continue
        if "received_at" in values:
            values["received_at"] = day_text(values["received_at"])
        out.records.append(values)
    return out


def read_rows(path: Path, sheet: Optional[str] = None) -> List[List]:
    """CSV · xlsx 파일 → 줄들. xlsx 는 이 시트로 보이는 탭 하나를 고른다.

    탭을 고르지 않았는데 이 시트로 보이는 탭이 없거나 여럿이면 멈춘다 —
    엉뚱한 탭을 넣는 것보다 묻는 편이 낫다.
    """
    path = Path(path)
    if path.suffix.lower() in (".csv", ".tsv", ".txt"):
        text = path.read_text(encoding="utf-8-sig")
        dialect = "excel-tab" if path.suffix.lower() == ".tsv" else "excel"
        return [list(r) for r in csv.reader(io.StringIO(text), dialect=dialect)]

    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        tabs = [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)])
                for ws in book.worksheets]
    finally:
        book.close()
    return pick_tab(tabs, sheet)[1]


def pick_tab(tabs: Sequence[Tuple[str, List[List]]], sheet: Optional[str] = None,
             ask: str = "--sheet 로 골라 주세요") -> Tuple[str, List[List]]:
    """워크북의 탭들(`[(탭 이름, 줄들), …]`) 중 읽을 탭 하나 — `(탭 이름, 줄들)`.

    고른 탭(`sheet`)이 있으면 그 탭, 없으면 **이 시트로 보이는 탭이 꼭 하나일
    때만** 그 탭이다(`read_rows` 머리말). 파일을 경로로 받는 가져오기와 화면에서
    올리는 딜소개 문구 올리기(`read_upload`)가 이 규칙 하나를 지난다 — 둘이 각자
    고르면 같은 워크북이 두 길에서 다른 탭으로 읽힌다. `ask` 는 어떻게 고르라고
    말할지다(스크립트는 `--sheet`, 화면은 탭 고르개).
    """
    if sheet:
        for title, rows in tabs:
            if title == sheet:
                return title, rows
        raise ValueError(f"`{sheet}` 탭이 없습니다 — 있는 탭: "
                         + ", ".join(t for t, _r in tabs))
    hits = [(title, rows) for title, rows in tabs if find_header(rows) is not None]
    if len(hits) != 1:
        names = ", ".join(t for t, _r in hits) or "없음"
        raise ValueError("이 시트로 보이는 탭이 하나가 아닙니다"
                         f"(찾은 탭: {names}) — {ask}")
    return hits[0]


def read_upload(filename: str, data: bytes,
                sheet: Optional[str] = None) -> Tuple[str, List[List]]:
    """화면에서 올린 파일(**바이트**) → `(읽은 탭 이름, 줄들)`. CSV 는 탭 이름이 빈 글자.

    `read_rows` 의 바이트 판이다 — 임시 파일을 쓰지 않는다. 읽기는 업로드 공용
    부품(`spreadsheet.read_tabs` — 크기 상한 · 깨진 파일 · CSV 인코딩 짐작)이,
    탭 고르기는 `pick_tab` 이 한다. 못 읽으면 `ValueError`
    (`spreadsheet.SpreadsheetError` 도 그 갈래다).
    """
    from . import spreadsheet as sp

    tabs = sp.read_tabs(filename, data)
    if not filename.lower().endswith(sp.EXCEL_SUFFIXES):
        return tabs[0]
    return pick_tab(tabs, sheet, ask="[탭]에서 골라 주세요")


def row_key(name: Optional[str], received_at: Optional[str]) -> Tuple[str, str]:
    """예전 열쇠 — `(기업명, 수신 일자)`. 열쇠가 없는 줄을 맞출 때만 쓴다(머리말)."""
    return name_key(name), (received_at or "").strip()


def import_key(values) -> str:
    """가져오기 열쇠 — 시트 줄의 `(기업명, 수신 일자, 공유 심사역, 회사)`(머리말).

    `values` 는 넣을 값(`parse` 의 한 줄) 또는 표의 줄이다. 칸에 그대로 적을
    글자라 JSON 배열로 만든다 — 사람이 DB 를 열어 봐도 무엇의 열쇠인지 읽힌다.
    """
    get = values.get if isinstance(values, dict) else (
        lambda attr: getattr(values, attr, None))
    parts = [name_key(get("name")),
             day_text(get("received_at") or ""),
             re.sub(r"\s+", "", get("shared_by") or "").lower(),
             name_key(get("source_firm"))]
    return json.dumps(parts, ensure_ascii=False)


@dataclass
class Result:
    created: int = 0
    #: 이미 있던 줄 중 무엇이든 바뀐 줄.
    updated: int = 0
    #: 바뀐 것이 없는 줄.
    unchanged: int = 0
    #: 앱에서 빈 칸이라 채운 칸.
    filled: int = 0
    #: 앱 값과 달라 덮은 칸(`overwrite`).
    overwritten: int = 0
    #: 앱 값과 다르지만 그대로 둔 칸(앱에서 고친 값일 수 있다).
    kept: int = 0
    #: 시트 안에서 열쇠가 겹쳐 건너뛴 줄.
    duplicates: int = 0
    #: 열쇠가 없던 줄(앱에서 더한 줄 · 예전에 들어온 줄)을 맞춰 열쇠를 적은 수.
    linked: int = 0
    #: 열쇠 없는 줄 중 어느 것인지 몰라 건너뛴 시트 줄(머리말 3).
    ambiguous: int = 0


def table(db: Session) -> List[SeriesACompany]:
    """표의 줄 전부, **번호순** — `match` 가 받는 차례다(같은 열쇠가 둘이면 앞 줄)."""
    return list(db.execute(select(SeriesACompany)
                           .order_by(SeriesACompany.id)).scalars())


@dataclass
class Matched:
    """`match` 의 답 — 줄을 고치지 않고 **어느 시트 줄이 어느 표 줄인지만** 적는다."""

    #: `(넣을 값, 열쇠, 맞은 줄 — 없으면 None(표에 없는 딜), 열쇠 없는 줄을 맞춘
    #: 것인가)`. 차례는 열쇠로 맞은 줄들 → 남은 시트 줄들이다 — `upsert` 가 새
    #: 줄을 이 차례로 만든다.
    pairs: List[Tuple[dict, str, Optional[SeriesACompany], bool]] = field(
        default_factory=list)
    #: 시트 안에서 열쇠가 겹쳐 건너뛴 줄(앞 줄만 쓴다).
    duplicates: List[dict] = field(default_factory=list)
    #: 열쇠 없는 줄 중 어느 것인지 몰라 건너뛴 시트 줄(머리말 3).
    ambiguous: List[dict] = field(default_factory=list)


def match(rows: Sequence[SeriesACompany], records: Iterable[dict]) -> Matched:
    """시트 줄들을 표의 줄들(`table`)에 맞춘다 — **아무것도 고치지 않는다.**

    맞추는 차례는 머리말에 있다 — 열쇠 → 열쇠 없는 줄의 지금 값 열쇠 →
    `(기업명, 수신 일자)`(양쪽 다 하나일 때만). 가져오기(`upsert`)와 화면의
    딜소개 문구 올리기(`services/series_a_pitch_upload.py`)가 **이 함수 하나**를
    지난다 — 둘이 각자 맞추면 같은 파일이 두 길에서 다른 줄에 닿는다.

    열쇠 없는 줄을 맞추면 그 줄에 열쇠를 적을지(`linked`)는 부르는 쪽이 정한다 —
    그래서 줄을 건드리지 않고 표시만 한다.
    """
    keyed: Dict[str, SeriesACompany] = {}
    loose: List[SeriesACompany] = []          # 열쇠가 없는 줄
    for row in rows:
        if row.import_key:
            keyed.setdefault(row.import_key, row)
        else:
            loose.append(row)

    # 열쇠 없는 줄의 **지금 값**으로 셈한 열쇠 — 한 번만 셈한다.
    now_key = {id(row): import_key(row) for row in loose}

    out = Matched()
    seen = set()
    later: List[Tuple[dict, str]] = []
    for values in records:
        key = import_key(values)
        if key in seen:
            out.duplicates.append(values)
            continue
        seen.add(key)
        row = keyed.get(key)
        linked = False
        if row is None:
            # 열쇠 없는 줄 중 **지금 값까지 같은** 줄 — 같은 (기업명, 수신 일자) 의
            # 시트 줄이 둘이어도 제 짝을 먼저 가져간다(시트 차례와 상관없이).
            row = next((r for r in loose if now_key[id(r)] == key), None)
            if row is None:
                later.append((values, key))
                continue
            loose.remove(row)
            linked = True
        out.pairs.append((values, key, row, linked))

    # 남은 시트 줄 — 예전 열쇠로, **양쪽 다 하나일 때만** 맞춘다.
    wanted: Dict[Tuple[str, str], int] = {}
    for values, _key in later:
        old = row_key(values.get("name"), values.get("received_at"))
        wanted[old] = wanted.get(old, 0) + 1
    for values, key in later:
        old = row_key(values.get("name"), values.get("received_at"))
        hits = [r for r in loose if row_key(r.name, r.received_at) == old]
        if not hits:
            out.pairs.append((values, key, None, False))
            continue
        if len(hits) > 1 or wanted[old] > 1:
            out.ambiguous.append(values)
            continue
        row = hits[0]
        loose.remove(row)
        out.pairs.append((values, key, row, True))
    return out


#: 칸 하나를 어떻게 하나(`cell_plan` 의 답).
BLANK, SAME, FILL, OVERWRITE, KEEP = "blank", "same", "fill", "overwrite", "keep"


def cell_plan(now: Optional[str], value: str, overwrite: bool) -> str:
    """앱의 칸(`now`)에 시트 값(`value`)을 어떻게 할지 — 머리말 `몇 번을 다시 돌려도`.

      · 시트의 빈 칸 → `BLANK`(아무것도 안 지운다)
      · 같은 글자 → `SAME`
      · 앱이 빈 칸 → `FILL`
      · 다르면 `overwrite` 일 때만 `OVERWRITE`, 아니면 `KEEP`(앱에서 고친 값일 수 있다)

    가져오기(`upsert`)와 딜소개 문구 올리기가 같이 쓴다 — 무엇을 빈 칸 · 같은
    글로 보는지가 두 길에서 갈리면 같은 파일이 다른 결과를 낸다.
    """
    if not value:
        return BLANK
    have = (now or "").strip()
    if have == value:
        return SAME
    if not have:
        return FILL
    return OVERWRITE if overwrite else KEEP


def upsert(db: Session, records: Iterable[dict], overwrite: bool = False) -> Result:
    """넣을 값들을 표에 맞춘다. **커밋하지 않는다** — 부르는 쪽이 정한다.

    어느 줄에 맞는지는 `match` 가 정한다(머리말의 차례). 여기서는 표에 없는
    딜은 만들고, 열쇠 없이 맞은 줄에는 그 시트 줄의 열쇠를 적고(`linked`), 칸마다
    `cell_plan` 대로 채운다.
    """
    found = match(table(db), records)
    result = Result(duplicates=len(found.duplicates),
                    ambiguous=len(found.ambiguous))

    for values, key, row, linked in found.pairs:
        if row is None:
            fields = {k: (v or None) for k, v in values.items()}
            db.add(SeriesACompany(import_key=key, **fields))
            result.created += 1
            continue
        if linked:
            row.import_key = key
            result.linked += 1

        touched = False
        for attr, value in values.items():
            how = cell_plan(getattr(row, attr), value, overwrite)
            if how in (FILL, OVERWRITE):
                setattr(row, attr, value)
                touched = True
                if how == FILL:
                    result.filled += 1
                else:
                    result.overwritten += 1
            elif how == KEEP:
                result.kept += 1
        if touched:
            result.updated += 1
        else:
            result.unchanged += 1
    db.flush()
    return result
