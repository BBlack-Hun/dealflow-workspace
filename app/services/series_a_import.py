"""`Series A 이상 기업` 시트 → `series_a_companies` 표.

부르는 쪽은 `scripts/import_series_a.py` 하나다(검사도 여기를 부른다). 시트
주소는 어디에도 적지 않는다 — **내려받은 파일 경로**(CSV · xlsx)를 받는다.

## 칸은 **머리글 이름**으로 찾는다

자리로 짐작하지 않는다. 시트는 사람이 계속 쓰는 문서라 칸이 늘면 자리가
밀린다. 머리글은 띄어쓰기를 지우고 견준다 — 원본에 `기업구분 ` 처럼 뒤에
공백이 붙은 머리글이 실제로 있다.

**옛 이름과 화면 이름을 함께 받는다.** 화면은 IR 기업 현황의 두 탭을 따라
`사업분야 대분류` → `대분류`, `기업구분` → `투자라운드` 로 부른다. 시트 머리글은
옛 이름이라, 화면을 따라 여기서 옛 이름을 빼면 **다음 가져오기에서 그 칸이
조용히 빈다**(`scripts/import_company_sheets.py` 가 같은 이유로 둘을 같이 받는다).

## 한 줄을 무엇으로 알아보나 — `(기업명, 수신 일자)`

한 줄은 **받은 딜 한 건**이다. 같은 기업이 다른 날 또 들어오면 다른 줄이다
(후속 투자 연계로 다시 오는 일이 있다). 기업명은 `deal_history._key` 로 맞춘다
— (주)·띄어쓰기 차이로 같은 딜이 두 줄이 되지 않게. 이 규칙은 **새로 짓지
않는다**: 기업 이름을 맞추는 자리가 저장소에 그 하나다.

시트의 `NO` 는 열쇠로 쓰지 않는다 — 원본에 번호가 빈 줄이 있고, 사람이 줄을
끼워 넣으면 번호가 밀린다.

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
        if sheet:
            if sheet not in book.sheetnames:
                raise ValueError(f"`{sheet}` 탭이 없습니다 — 있는 탭: "
                                 + ", ".join(book.sheetnames))
            return [list(r) for r in book[sheet].iter_rows(values_only=True)]
        hits = []
        for ws in book.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            if find_header(rows) is not None:
                hits.append((ws.title, rows))
        if len(hits) != 1:
            names = ", ".join(t for t, _r in hits) or "없음"
            raise ValueError("이 시트로 보이는 탭이 하나가 아닙니다"
                             f"(찾은 탭: {names}) — --sheet 로 골라 주세요")
        return hits[0][1]
    finally:
        book.close()


def row_key(name: Optional[str], received_at: Optional[str]) -> Tuple[str, str]:
    """한 줄을 알아보는 열쇠 — `(기업명, 수신 일자)`(머리말)."""
    return name_key(name), (received_at or "").strip()


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


def upsert(db: Session, records: Iterable[dict], overwrite: bool = False) -> Result:
    """넣을 값들을 표에 맞춘다. **커밋하지 않는다** — 부르는 쪽이 정한다."""
    existing: Dict[Tuple[str, str], SeriesACompany] = {}
    for row in db.execute(select(SeriesACompany)
                          .order_by(SeriesACompany.id)).scalars():
        existing.setdefault(row_key(row.name, row.received_at), row)

    result = Result()
    seen = set()
    for values in records:
        key = row_key(values.get("name"), values.get("received_at"))
        if key in seen:
            result.duplicates += 1
            continue
        seen.add(key)

        row = existing.get(key)
        if row is None:
            db.add(SeriesACompany(**{k: (v or None) for k, v in values.items()}))
            result.created += 1
            continue

        touched = False
        for attr, value in values.items():
            if not value:
                continue                  # 시트의 빈 칸은 아무것도 안 지운다
            now = (getattr(row, attr) or "").strip()
            if now == value:
                continue
            if not now:
                setattr(row, attr, value)
                result.filled += 1
                touched = True
            elif overwrite:
                setattr(row, attr, value)
                result.overwritten += 1
                touched = True
            else:
                result.kept += 1
        if touched:
            result.updated += 1
        else:
            result.unchanged += 1
    db.flush()
    return result
