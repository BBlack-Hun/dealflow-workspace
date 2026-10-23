"""IR 기업 현황 탭 — **지금 화면 그대로** 내려받기 (10/17 회의 #43).

`엑셀 내려받기`(`/api/export/companies.xlsx`)는 언제나 **전체**다. 화면에서 머리글
필터·검색·정렬로 좁혀 놓고 받으면 다시 엑셀에서 같은 조건을 손으로 걸어야 했다.
그래서 `지금 화면 내려받기` 를 따로 둔다 — 전체 내려받기는 그대로다.

## 화면 글을 긁지 않는다 — **같은 조건을 서버가 다시 건다**

화면이 거르는 조건은 이미 주소에 실려 있다(`filters.js` 가 `?sector=…&ir=…` 로,
`table_sort.js` 가 `?sort=-updated` 로 남긴다). 검색창 글자만 주소에 안 남아서
단추가 누르는 순간 `q=` 로 붙인다(`static/js/companies.js`). 서버는 그 조건을
**화면과 같은 규칙으로** 다시 건다 — 줄은 표가 먹는 그 한 벌(`company_rows`)이다.

  · 필터 — 칸끼리는 AND, 한 칸 안에서는 OR. 빈 값은 `(비어 있음)` 한 덩어리.
    `|` 로 여러 값이 든 칸은 낱낱으로 본다(`filters.js` 의 `splitValues`·`matchRow`).
  · 검색 — 줄의 검색 글자에 친 글자가 들어 있으면. 번호 모양이면 숫자만 남겨
    한 번 더(`companies.js` 의 `textMatch` · `companies.search_text`).
  · 정렬 — `?sort=key` 오름 · `?sort=-key` 내림. 빈 값은 방향과 상관없이 끝,
    같은 값은 서버가 그려 준 차례 그대로(`table_sort.js` 의 `order`). 정렬이
    없으면 표의 기본 차례(수신일 최신순 — `companies.sort_by_received`).

## 아는 차이 — 이름순의 **한글 차례**

화면은 브라우저의 `localeCompare('ko')` 로 이름을 세운다. 파이썬에는 같은 것이
없어서 **흉내 낸다**(`_ko_key` — 한글 먼저, 영문은 대소문자 없이). 영문·숫자가
섞인 이름 몇 곳의 앞뒤가 화면과 다를 수 있다 — 줄은 같고 차례만이다.

## 칸 — **보이는 칸 그대로**

IR 기업 현황 탭의 머리글 순서·이름 그대로다(`VIEW_HEADERS`). `NO` 는 화면처럼
**보이는 것 기준 1, 2, 3…** 이다. `소개 횟수` 는 화면에서 두 수(`6회` · `180명`)가
한 칸에 서는데, 파일에서는 세고 거를 수 있게 두 칸으로 나눈다.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Dict, List

#: 화면의 `(비어 있음)` — `filters.js` 의 `EMPTY` 와 같은 글자.
EMPTY = "(비어 있음)"

#: 머리글 필터 열쇠 → 줄 값. **`companies.html` 의 `data-f-*` 와 한 벌이다** —
#: 화면이 무엇을 거를 값으로 싣는지가 곧 여기다.
FILTER_VALUES = {
    "top": lambda r: r["top_deal_kind"] or "일반",
    "sector": lambda r: r["sector_major"],
    "minor": lambda r: r["sector_minor"],
    "series": lambda r: r["series_short"],
    "assignee": lambda r: r["assignee"],
    "contract": lambda r: r["contract_label"],
    "received": lambda r: r["contract_received"],
    "quote": lambda r: r["quote_attached"],
    "joined": lambda r: r["kakao_joined"],
    "ir": lambda r: "● 있음" if r["has_ir"] else "⚠ 없음",
}

#: 머리글 정렬 열쇠 → 세울 값. `companies.html` 의 `data-s-*` 와 한 벌이다.
SORT_VALUES = {
    "name": lambda r: r["name"],
    "updated": lambda r: r["updated_at"],
    "sent": lambda r: r["sent_rounds"],
    "meeting": lambda r: r["meeting_sort"],
}

#: 친 글자가 **번호 모양**인가 — `companies.js` 의 `PHONEISH` 와 같은 규칙.
PHONEISH = re.compile(r"^[0-9][0-9\s().+-]*$")

#: 파일 머리글 — IR 기업 현황 탭의 머리글 그대로(왼쪽부터).
VIEW_HEADERS = [
    "NO", "기업명", "수신일", "대분류", "소분류", "투자라운드", "수정한 날짜",
    "딜 소개 문구", "담당자", "소개 횟수", "소개 발송(명)", "견적서 첨부 여부",
    "미팅제공일자", "계약여부", "계약서 수신 여부", "성공보수율", "카톡 연결 여부", "홍보메일삭제",
    "핵심/TOP Deal", "IR 자료",
]


def split_values(raw) -> List[str]:
    """`filters.js` 의 `splitValues` — `|` 로 나누고 다듬는다. 비면 `(비어 있음)`."""
    if raw is None:
        return [EMPTY]
    parts = [p.strip() for p in str(raw).split("|")]
    parts = [p for p in parts if p]
    return parts or [EMPTY]


def parse_raw_query(query: str, extra=None) -> Dict[str, List[str]]:
    """**원본 쿼리 문자열**에서 필터를 읽는다 — `filters.js` 의 `parseQuery` 그대로.

    `,` 로 먼저 가르고 **그다음에** 값마다 푼다 — 화면이 값마다 따로
    `encodeURIComponent` 한 뒤 `,` 로 잇기 때문이다(`buildQuery`). 프레임워크가
    다 풀어 준 값을 쉼표로 가르면 값 안의 쉼표(`5%2C10억`)가 두 토막이 된다.
    모르는 열쇠(`sort` · `q` · `tab`)는 버린다. `extra` 는 `FILTER_VALUES` 와 같은
    꼴의 덧붙은 열쇠다(관리자가 붙인 O/X 칸 — `custom_filters`).
    """
    from urllib.parse import unquote

    out: Dict[str, List[str]] = {}
    for pair in (query or "").lstrip("?").split("&"):
        if not pair:
            continue
        key, _, raw = pair.partition("=")
        key = unquote(key)
        if key not in FILTER_VALUES and key not in (extra or {}):
            continue
        values = [unquote(v.replace("+", " ")) for v in raw.split(",")]
        values = [v for v in values if v]
        if values:
            out[key] = values
    return out


def match_filters(row: dict, state: Dict[str, List[str]], extra=None) -> bool:
    """`filters.js` 의 `matchRow` — 칸끼리 AND, 한 칸 안에서는 OR."""
    values = {**FILTER_VALUES, **(extra or {})}
    for key, wanted in state.items():
        if not wanted:
            continue
        have = split_values(values[key](row))
        if not any(w in have for w in wanted):
            return False
    return True


def match_search(row: dict, q: str) -> bool:
    """`companies.js` 의 `textMatch` — 검색 글자 안에 있나, 번호면 숫자만으로 한 번 더."""
    q = (q or "").strip().lower()
    if not q:
        return True
    hay = row.get("search") or ""
    if q in hay:
        return True
    if not PHONEISH.match(q):
        return False
    digits = re.sub(r"[^0-9]", "", q)
    return bool(digits) and digits in hay


def _ko_key(text: str) -> tuple:
    """`localeCompare('ko')` 흉내 — 글자마다 (무리, 글자).

    무리: 공백·기호 0 · 숫자 1 · 한글 2 · 한자 3 · 그 밖의 글자(영문 등) 4.
    ICU 의 한국어 차례가 한글을 다른 글자보다 앞에 두는 것을 따른다. 영문은
    대소문자를 가리지 않는다. 같은 무리 안에서는 글자 값 차례다.
    """
    out = []
    for ch in unicodedata.normalize("NFC", text or ""):
        code = ord(ch)
        if ch.isdigit():
            group = 1
        elif 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF \
                or 0x3130 <= code <= 0x318F:
            group = 2
        elif 0x4E00 <= code <= 0x9FFF:
            group = 3
        elif ch.isalpha():
            group = 4
        else:
            group = 0
        out.append((group, ch.casefold()))
    return tuple(out)


def _compare_key(value):
    """`table_sort.js` 의 `compare` — 숫자로 읽히면 숫자로, 아니면 글자 차례로."""
    text = str(value)
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = None
    # 파이썬만 숫자로 읽는 글(`nan` · `inf` · `1_000`)은 글자로 둔다 — 브라우저의
    # `Number()` 는 그것들을 숫자로 안 읽는다.
    if num is not None and math.isfinite(num) and "_" not in text:
        return (0, num, ())
    return (1, 0.0, _ko_key(text))


def _is_empty(value) -> bool:
    return value is None or value == ""


def sort_rows(rows: List[dict], sort: str) -> List[dict]:
    """`table_sort.js` 의 `order` — 빈 값은 늘 끝, 같은 값은 처음 차례 그대로.

    모르는 열쇠 · 빈 값이면 받은 차례(= 표의 기본 차례)를 그대로 돌려준다.
    """
    raw = (sort or "").strip()
    desc = raw.startswith("-")
    key = raw[1:] if desc else raw
    pick = SORT_VALUES.get(key)
    if pick is None:
        return list(rows)
    filled = [r for r in rows if not _is_empty(pick(r))]
    empty = [r for r in rows if _is_empty(pick(r))]
    # 파이썬 정렬은 안정적이라 같은 값끼리는 받은 차례가 남는다(`x - y` 와 같다).
    # `reverse=True` 도 같은 값끼리의 차례는 안 뒤집는다(파이썬이 보장한다) —
    # 화면도 내림에서 같은 값은 처음 차례 그대로다.
    filled.sort(key=lambda r: _compare_key(pick(r)), reverse=desc)
    return filled + empty


def view_rows(rows: List[dict], filters: Dict[str, List[str]], q: str = "",
              sort: str = "", extra=None) -> List[dict]:
    """표 한 벌 → **지금 화면에 보이는 줄들**(거르고 · 찾고 · 세운 차례)."""
    shown = [r for r in rows
             if match_filters(r, filters, extra) and match_search(r, q)]
    return sort_rows(shown, sort)


def to_cells(rows: List[dict]) -> List[list]:
    """파일 줄 — `VIEW_HEADERS` 차례. `NO` 는 보이는 차례 1, 2, 3…"""
    out = []
    for no, r in enumerate(rows, start=1):
        out.append([
            no, r["name"], r["received_at"], r["sector_major"], r["sector_minor"],
            # 화면은 투자라운드를 **앞부분만** 보인다(`series_short` — 괄호 안 설명
            # 생략). 파일에서는 전체 값을 싣는다 — 짚어야 보이던 것이 칸에 바로 선다.
            r["series"], r["updated_at"], r["one_liner"], r["assignee"],
            # 한 번도 안 나간 기업은 화면이 `–` 로 보인다 — 파일에서는 수 0 이다.
            r["sent_rounds"], r["sent_total"], r["quote_attached"],
            r["meeting_offered_at"], r["contract_label"], r["contract_received"],
            r["success_fee"], r["kakao_joined"], r["contract_month"],
            r["top_deal_kind"] or "", r["ir_file_name"] if r["has_ir"] else "없음",
        ])
    return out


def custom_filters(view: dict) -> dict:
    """관리자가 붙인 O/X 칸의 필터 열쇠 → 줄 값(`_custom_cols.html` 의 `data-f-cc*`).

    `view` 는 `custom_columns.view` 가 준 것이다. 화면이 O/X 칸에만 필터를 세우므로
    여기서도 그 칸만 싣는다.
    """
    vals = view["custom_vals"]
    return {f"cc{c.id}": (lambda r, cid=c.id: vals.get(r["id"], {}).get(cid, ""))
            for c in view["custom_cols"] if c.kind == "ox"}
