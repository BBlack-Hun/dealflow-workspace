"""구글시트(CSV) 임포트 파서 — ROADMAP 2.1, 근거: docs/SHEET_FINDINGS.md.

두 시트를 다룬다.

* **시트 A (투자사 관리)** — 사용자 1명당 1개. 헤더가 2행, 데이터는 4행부터 시작하고
  ``이름`` 칸에는 '홍길동 대표님'처럼 **이름+직함이 합쳐져** 있다. 오른쪽으로는
  ``1차 딜소개 / IR 자료 요청 / 미팅 요청`` **3열 세트가 월마다 반복**되며 달이 갈수록
  무한히 늘어난다.
* **시트 B (IR 기업)** — 팀 공유 기업 마스터.

설계 원칙(왜 이렇게 짰는지):

1. **행/열 위치를 하드코딩하지 않는다.** 시트는 사람이 계속 편집하는 문서라 열이
   밀린다. '그룹/이름/투자사명'이 함께 있는 행을 헤더로 **탐지**하고, 컬럼은 헤더
   텍스트로 찾는다.
2. **월별 3열 세트는 행으로 정규화**한다(``contact_activities``). 시트의 구조적
   한계(달마다 열 증식)를 서비스가 해소하는 지점이라 임포트의 핵심 산출물이다.
3. **파서는 DB를 모른다.** 아래 parse_* 는 순수 함수라 CSV 픽스처만으로 테스트된다.
   DB 반영은 apply_* 가 담당한다(관리자 화면에서도 재사용 가능).
4. **확신 없으면 건드리지 않는다.** 직함 분리·섹터 태그 분해는 애매하면 원문을 남긴다.
   잘못 분리하면 카톡방 이름이 틀어져 발송이 통째로 skip 되기 때문이다.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactActivity, IrCompany, User, VcContact
from . import firm_type, sheet_owner
from .room_name import DEFAULT_SUFFIX, build_room_name, normalize_space, split_name_title

# 활동 종류 (DATA_MODEL §2.6)
KIND_DEAL_INTRO = "deal_intro"
KIND_IR_REQUEST = "ir_request"
KIND_MEETING = "meeting"

# 헤더 텍스트 → 활동 종류. '1차 딜소개'가 'IR'을 포함하는 경우는 없지만 순서를 고정해
# 가장 구체적인 것부터 본다.
_KIND_KEYWORDS: Sequence[Tuple[str, Tuple[str, ...]]] = (
    (KIND_DEAL_INTRO, ("딜소개", "딜 소개")),
    (KIND_IR_REQUEST, ("ir",)),
    (KIND_MEETING, ("미팅",)),
)

_MONTH_RE = re.compile(r"(\d{1,2})\s*월")
# '8/13(목) 기업A, 기업B' · '8.4 핵심 딜' · '08/19(수)' — 요일 괄호는 있을 수도 없을 수도.
_DATE_PREFIX_RE = re.compile(
    r"^\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*(?:\(\s*([월화수목금토일])?[^)]*\))?\s*[:·\-]?\s*"
)
# '핵심 딜 8개사' — 기업명 없이 개수만 적힌 회차.
_COUNT_ONLY_RE = re.compile(r"(\d+)\s*개\s*사")
# '1.샘플가  2.샘플나  3.샘플다' — 번호 매김(구분자가 이중공백일 수 있음).
_NUMBERED_RE = re.compile(r"(?:^|\s)\d{1,2}\s*[.)]\s*")
# 법인 표기 — 같은 기업이 '(주)샘플가 / ㈜샘플가 / 샘플가'로 섞여 적힌다.
_CORP_MARKS = ("(주)", "㈜", "(유)", "주식회사", "유한회사", "(재)", "(사)")


# ── 공통 유틸 ────────────────────────────────────────────────────────────────

def read_csv(path, encoding: str = "utf-8-sig") -> List[List[str]]:
    """CSV를 행 리스트로 읽는다. 구글시트 내보내기 기본 인코딩은 UTF-8(BOM)."""
    with Path(path).open("r", encoding=encoding, newline="") as fh:
        return [list(row) for row in csv.reader(fh)]


def norm(value: Optional[str]) -> str:
    return normalize_space(value or "")


def _cell(row: Sequence[str], idx: Optional[int]) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return norm(row[idx])


def _raw_cell(row: Sequence[str], idx: Optional[int]) -> str:
    """줄바꿈을 살려서 읽는다(딜소개 셀은 회차가 줄바꿈으로 누적된다)."""
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def detect_header_row(rows: Sequence[Sequence[str]], required: Sequence[str],
                      limit: int = 15) -> Optional[int]:
    """필수 토큰이 모두 등장하는 첫 행을 헤더로 본다.

    시트 A는 1행이 제목/메모라 헤더가 2행이지만(SHEET_FINDINGS §2), 사람이 행을
    추가하면 바로 밀린다. 그래서 인덱스를 고정하지 않고 탐지한다.
    """
    for idx, row in enumerate(rows[:limit]):
        joined = " ".join(norm(c) for c in row)
        if all(token in joined for token in required):
            return idx
    return None


def find_column(header: Sequence[str], tokens: Sequence[str],
                exclude: Sequence[str] = ()) -> Optional[int]:
    """헤더에서 tokens 를 모두 포함하고 exclude 는 포함하지 않는 첫 컬럼 인덱스."""
    for idx, cell in enumerate(header):
        text = norm(cell).lower()
        if not text:
            continue
        if all(t.lower() in text for t in tokens) and not any(x.lower() in text for x in exclude):
            return idx
    return None


def first_column(header: Sequence[str], *token_sets: Sequence[str]) -> Optional[int]:
    """여러 후보 표기 중 먼저 맞는 컬럼. (0번 컬럼이 falsy라 ``or`` 로 잇지 않는다)"""
    for tokens in token_sets:
        idx = find_column(header, tokens)
        if idx is not None:
            return idx
    return None


def _column_context(rows: Sequence[Sequence[str]], header_idx: int, col: int) -> str:
    """해당 컬럼의 헤더 문맥 = (헤더 위 1행 + 헤더행 + 헤더 아래 1행).

    월 라벨은 보통 3열을 병합한 **헤더 위 행**에 있고, CSV로 내려받으면 병합 셀은
    첫 칸에만 값이 남고 나머지는 빈칸이 된다(→ 아래 carry-forward 로 처리).
    """
    parts = []
    for r in (header_idx - 1, header_idx, header_idx + 1):
        if 0 <= r < len(rows):
            parts.append(_cell(rows[r], col))
    return " ".join(p for p in parts if p)


def detect_kind(text: str) -> Optional[str]:
    low = text.lower()
    for kind, keywords in _KIND_KEYWORDS:
        if any(k in low for k in keywords):
            return kind
    return None


@dataclass
class ActivityColumn:
    col: int
    month: Optional[str]   # '2026-08'
    kind: str
    header: str


def detect_activity_columns(rows: Sequence[Sequence[str]], header_idx: int,
                            year: int, skip_cols: Sequence[int] = ()) -> List[ActivityColumn]:
    """월별 3열 세트를 **반복 스캔**한다. (기본 정보 컬럼은 skip_cols 로 제외)

    달이 갈수록 열이 늘어나는 구조라 '6·7·8월' 같은 고정 목록을 쓰지 않는다.
    월 라벨이 없는 컬럼은 **직전 컬럼의 월을 이어받는다**(병합 셀 대응).

    '기본 정보 컬럼 오른쪽'이라고 가정하지 않는 이유: 시트마다 담당자·연락처 같은
    컬럼이 활동 컬럼보다 뒤에 오기도 한다. 위치가 아니라 **헤더 문맥**으로 가른다.
    """
    width = max((len(r) for r in rows), default=0)
    skip = set(skip_cols)
    out: List[ActivityColumn] = []
    current_month: Optional[str] = None
    current_year = year
    prev_no: Optional[int] = None
    for col in range(width):
        if col in skip:
            continue
        context = _column_context(rows, header_idx, col)
        if not context:
            continue
        m = _MONTH_RE.search(context)
        if m:
            month_no = int(m.group(1))
            # 해가 바뀌는 자리를 넘긴다. 같은 해로 두면 1년 전(또는 뒤) 기록이
            # 되어 그 달의 회차가 통째로 엉뚱한 자리에 쌓인다.
            #
            # 방향은 시트마다 다르다 — 명단 시트는 **최신 달이 왼쪽**이라
            # 8→7→6월로 줄고, 새로 만든 표는 늘기도 한다. 둘 다 본다.
            # 오타로 한 해가 통째로 밀리지 않게 **연말↔연초 경계에서만** 옮긴다.
            if prev_no is not None:
                if prev_no >= 10 and month_no <= 3:
                    current_year += 1      # 12월 → 1월 (오른쪽이 나중)
                elif prev_no <= 3 and month_no >= 10:
                    current_year -= 1      # 1월 → 12월 (오른쪽이 이전)
            prev_no = month_no
            current_month = f"{current_year:04d}-{month_no:02d}"
        kind = detect_kind(context)
        if kind is None:
            continue
        out.append(ActivityColumn(col=col, month=current_month, kind=kind, header=context))
    return out


# ── 셀 파싱 ─────────────────────────────────────────────────────────────────

@dataclass
class ParsedActivity:
    month: Optional[str]
    kind: str
    content: str
    happened_at: Optional[str] = None
    weekday: Optional[str] = None
    companies: List[str] = field(default_factory=list)
    company_count: Optional[int] = None
    raw_text: Optional[str] = None


def parse_activity_cell(text: str, month: Optional[str], kind: str,
                        year: int) -> List[ParsedActivity]:
    """한 칸에 줄바꿈으로 누적된 **여러 회차**를 회차별 레코드로 분해한다.

        8/4(화) 핵심 딜 8개사
        (빈 줄)
        8/13(목) 샘플애그, 샘플메디
        8/19(수) 샘플페이

    → 3건. 날짜로 시작하지 않는 줄은 직전 회차의 내용에 이어 붙인다
    (기업 목록이 다음 줄로 넘어가는 경우가 잦다).

    회차 안의 기업 목록은 **월마다 표기가 다르다**(쉼표 나열 / `1.A  2.B  3.C` 번호 매김 /
    개수만). 세 형태를 모두 읽고, 원문 조각을 raw_text 로 함께 남긴다.
    """
    entries: List[ParsedActivity] = []
    for raw_line in (text or "").splitlines():
        line = norm(raw_line)
        if not line:
            continue
        m = _DATE_PREFIX_RE.match(line)
        if m:
            mm, dd = int(m.group(1)), int(m.group(2))
            content = norm(line[m.end():])
            happened = _safe_date(_year_for_month(year, month, mm), mm, dd)
            entries.append(ParsedActivity(
                month=month or (happened[:7] if happened else None),
                kind=kind, content=content or line,
                happened_at=happened, weekday=m.group(3),
                raw_text=line,
            ))
        elif entries:
            entries[-1].content = norm(f"{entries[-1].content} {line}")
            entries[-1].raw_text = f"{entries[-1].raw_text}\n{line}"
        else:
            entries.append(ParsedActivity(month=month, kind=kind, content=line, raw_text=line))

    for entry in entries:
        entry.companies, entry.company_count = parse_company_list(entry.content)
        if entry.weekday is None and entry.happened_at:
            entry.weekday = weekday_of(entry.happened_at)
    return entries


def _year_for_month(sheet_year: int, month: Optional[str], cell_month: int) -> int:
    """셀 안의 `8/13` 이 어느 해인지. 컬럼의 월 라벨이 있으면 그쪽 연도를 따른다.

    연말·연초가 섞인 시트(12월 컬럼 옆에 1월 컬럼)에서 --year 만으로는 어긋난다.
    컬럼 월과 셀 월이 다르면 컬럼 쪽을 믿되(그 칸의 소속이 명시적이므로), 연도만 취한다.
    """
    if month and len(month) >= 4 and month[:4].isdigit():
        return int(month[:4])
    return sheet_year


def weekday_of(iso_date: str) -> Optional[str]:
    try:
        from datetime import date as _date

        return "월화수목금토일"[_date.fromisoformat(iso_date[:10]).weekday()]
    except (ValueError, TypeError, IndexError):
        return None


def week_of_month(iso_date: str) -> Optional[int]:
    """그 달의 몇 번째 주인지 (시트 헤더의 '첫째주 수요일 / 셋째주' 표기와 맞춘다)."""
    try:
        return (int(iso_date[8:10]) - 1) // 7 + 1
    except (ValueError, TypeError):
        return None


def parse_company_list(content: str) -> tuple:
    """회차 내용 → (기업명 목록, 기업 수).

    세 가지 표기를 모두 읽는다:
      - `핵심 딜 8개사`            → ([], 8)          개수만 있고 목록이 없다
      - `샘플애그, 샘플메디`        → ([2개], 2)       쉼표 나열
      - `1.(주)샘플가  2.샘플나`    → ([2개], 2)       번호 매김(구분자가 이중공백일 수 있음)
    """
    text = norm(content)
    if not text:
        return ([], None)

    numbered = [norm(p) for p in _NUMBERED_RE.split(text) if norm(p)]
    if len(numbered) >= 2 and _NUMBERED_RE.search(text):
        names = numbered
    elif "," in text:
        names = [norm(p) for p in text.split(",") if norm(p)]
    else:
        names = []

    if not names:
        m = _COUNT_ONLY_RE.search(text)
        if m:
            # 기업명이 적히지 않은 회차 — 개수만 남긴다(없는 목록을 지어내지 않는다).
            return ([], int(m.group(1)))
        # 단일 기업명으로 보이면 1건으로 센다. 서술형 메모는 기업으로 세지 않는다.
        return (([text], 1) if _looks_like_company(text) else ([], None))

    names = [n for n in names if _looks_like_company(n)]
    return (names, len(names) or None)


def _looks_like_company(name: str) -> bool:
    """기업명 후보인지. 문장형 메모('검토 중', '핵심 딜 8개사')를 걸러낸다."""
    t = norm(name)
    if not t or len(t) > 40:
        return False
    if _COUNT_ONLY_RE.search(t):
        return False
    return True


def normalize_company_name(name: str) -> str:
    """법인 표기를 떼어 비교용 이름으로. `(주)샘플가` `㈜샘플가` `샘플가(주)` → `샘플가`.

    ir_companies 매칭에만 쓰고 **저장은 원문 그대로** 한다 — DB에 없는 기업이 훨씬 많고,
    시트 원문을 바꿔 두면 사용자가 자기 기록을 알아보지 못한다.
    """
    t = norm(name)
    for mark in _CORP_MARKS:
        t = t.replace(mark, " ")
    return normalize_space(t)


def _safe_date(year: int, month: int, day: int) -> Optional[str]:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def split_sector_tags(text: str) -> List[str]:
    """투자분야 칸이 **짧은 태그 나열일 때만** 태그로 분해한다.

    실제 시트의 이 칸은 대부분 비어 있고, 있어도 '8/19 : 초기 기업보다는 성장단계
    기업들 위주로 검토' 같은 자유 서술이다(SHEET_FINDINGS §2). 이를 억지로 태그화하면
    발송 전 성향 경고(matcher)가 잘못된 근거로 시끄러워지므로, 확신할 때만 분해하고
    나머지는 round_size 에 원문으로 남긴다.
    """
    t = norm(text)
    if not t or ":" in t or len(t) > 30 or re.search(r"\d", t):
        return []
    tags = [norm(p) for p in re.split(r"[,/·|]", t)]
    tags = [x for x in tags if 1 <= len(x) <= 12]
    return tags[:5] if len(tags) <= 5 else []


# 연결 단계. 카톡방까지 연결됐는가 — 발송 대상이 되기 전 단계다.
STAGE_CONNECTED = "connected"
STAGE_IN_PROGRESS = "in_progress"
STAGE_DECLINED = "declined"
STAGE_NOT_STARTED = "not_started"

CONNECT_LABELS = {
    STAGE_CONNECTED: "연결 완료",
    STAGE_IN_PROGRESS: "진행 중",
    STAGE_DECLINED: "참여 안 함",
    STAGE_NOT_STARTED: "미착수",
}

# 메모에 이런 말이 있으면 더 진행하지 않는다 — 계속 연락하면 민폐가 된다.
_DECLINE_MARKS = ("참여안하심", "참여 안하심", "참여안함", "참여 안 함",
                  "관련업무 안함", "관련 업무 안함", "거절", "관심없", "관심 없",
                  "퇴사", "연결 원하지")
# 연락은 시작했지만 아직 방에 못 들어온 상태
_PROGRESS_MARKS = ("신규연결", "신규 연결", "부재중", "재연락", "카톡 공유",
                   "통화", "전화", "카톡 발송", "초대", "회의중", "진행")


# 담당자 칸에는 사람 이름이 아닌 것도 들어온다 — 'X'(해당 없음), '중복',
# 'X, IRDAY, IRSUMMIT'(태그). 이런 값을 담당자로 저장하면 누구 담당인지가 더 흐려진다.
_NOT_A_NAME = {"x", "o", "-", "중복", "없음", "미정", "해당없음"}


def looks_like_person(value: Optional[str]) -> bool:
    """담당자 칸의 값이 사람 이름으로 보이는가."""
    text = normalize_space(value or "")
    if len(text) < 2 or len(text) > 12:
        return False
    if text.lower() in _NOT_A_NAME:
        return False
    # 쉼표·숫자가 섞이면 이름이 아니라 태그다
    return not any(ch.isdigit() or ch == "," for ch in text)


def connect_stage(kakao_joined: str, memo: str, has_room: bool = False,
                  invited: str = "") -> str:
    """연결이 어디까지 갔는지 한 단어로.

    시트에는 이 값이 따로 없고 여러 칸에 흩어져 있다. 명단 시트는 '카톡방
    참여여부(O/X)', 딜소개현황 시트는 '초대 완료여부(완료)' 를 쓴다. 둘 다 본다.
    거절 표시가 있으면 참여 안 함, 연락한 흔적이 있으면 진행 중,
    아무 것도 없으면 미착수로 본다.
    """
    joined = normalize_space(kakao_joined or "")
    text = normalize_space(memo or "")
    if has_room or is_invited(joined) or is_invited(invited):
        return STAGE_CONNECTED
    haystack = f"{joined} {text}"
    if any(mark in haystack for mark in _DECLINE_MARKS):
        return STAGE_DECLINED
    if any(mark in haystack for mark in _PROGRESS_MARKS):
        return STAGE_IN_PROGRESS
    return STAGE_NOT_STARTED


def is_invited(value: str) -> bool:
    """'초대완료여부' 칸이 완료를 뜻하는가 (표기가 시트마다 제각각)."""
    v = norm(value).lower()
    if not v:
        return False
    return ("완료" in v) or ("완" == v) or v in ("o", "y", "yes", "ok", "v", "√", "○", "●")



# ── 금액 파싱 ────────────────────────────────────────────────────────────────

_MONEY_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만)?")


def parse_money_to_million(text: Optional[str]) -> Optional[int]:
    """'11억', '2.5억', '1억 원', '2억원~5억' → **백만원 단위 정수**.

    시트의 금액 칸은 자유 서술이라 표기가 제각각이다. DB 는 백만원 단위로 저장하므로
    (기존 필드 규약) 여기서 맞춰준다.

    범위('2억원~5억')는 **작은 쪽**을 취한다 — 유치 희망 금액을 크게 잡아
    실제보다 부풀려 소개하는 것보다 보수적인 편이 안전하다.
    숫자를 못 찾으면 None 을 돌려 '값 없음'으로 남긴다(0 으로 채우지 않는다).
    """
    t = norm(text)
    if not t:
        return None
    # 미정/협의 등은 값으로 보지 않는다.
    if any(k in t for k in ("미정", "협의", "비공개", "추후", "없음", "해당없음")):
        return None

    values = []
    for m in _MONEY_RE.finditer(t.replace(" ", "")):
        num, unit = m.group(1), m.group(2)
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        if unit == "억":
            values.append(v * 100)          # 1억 = 100백만
        elif unit == "천만":
            values.append(v * 10)
        elif unit == "백만":
            values.append(v)
        elif unit == "만":
            values.append(v / 100)
        # 단위가 없으면 무시한다 — '2020년' 같은 연도를 금액으로 오인하지 않기 위함.
    if not values:
        return None
    return int(round(min(values)))


# ── 시트 A ──────────────────────────────────────────────────────────────────

@dataclass
class ParsedContact:
    row_no: int
    name: str
    title: Optional[str]
    firm: str
    group_name: Optional[str] = None
    owner_name: Optional[str] = None        # 시트 '담당자' = 우리 팀원 이름
    invited_status: Optional[str] = None
    interest_level: Optional[str] = None    # 관심도(월말 기준)
    kakao_joined: Optional[str] = None      # 카톡방 참여여부
    profile_raw: Optional[str] = None       # 투자분야/라운드사이즈 원문
    sectors: List[str] = field(default_factory=list)
    round_size: Optional[str] = None
    memo: Optional[str] = None
    phone: Optional[str] = None             # 연락처(휴대폰)
    office_phone: Optional[str] = None      # 유선전화
    address: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    connect_stage: Optional[str] = None
    activities: List[ParsedActivity] = field(default_factory=list)


@dataclass
class SkippedRow:
    row_no: int
    reason: str
    preview: str


@dataclass
class SheetAParse:
    contacts: List[ParsedContact] = field(default_factory=list)
    skipped: List[SkippedRow] = field(default_factory=list)
    activity_columns: List[ActivityColumn] = field(default_factory=list)
    header_row: Optional[int] = None
    notes: List[str] = field(default_factory=list)   # 사람이 확인해야 할 판단


def parse_sheet_a(rows: Sequence[Sequence[str]], year: int) -> SheetAParse:
    """투자사 명단 시트 → 담당자 + 월별 활동.

    스프레드시트에는 명단 시트가 여러 장 있고 **컬럼 구성이 서로 다르다**
    (딜소개 현황 시트: 그룹/초대완료여부/월별 3열 세트 · 연결 명단 시트: 관심도/
    카톡방 참여여부/연락처/직책/주소…). 위치가 아니라 **헤더 이름**으로 찾으므로
    한 파서가 두 형태를 모두 읽는다. 없는 컬럼은 그냥 비어 있는 값이 된다.
    """
    out = SheetAParse()
    # 명단 시트마다 머리글이 조금씩 다르다. 딜소개현황은 '이름 + 투자사명',
    # 신규 명단(150/98/30)은 'NO + 회사' 다. 둘 다 받아들인다.
    header_idx = detect_header_row(rows, ["이름", "투자사"])
    if header_idx is None:
        header_idx = detect_header_row(rows, ["NO", "회사"])
    if header_idx is None:
        raise ValueError(
            "헤더 행을 찾지 못했습니다 — '이름'+'투자사명' 또는 'NO'+'회사' 가 있는 행이 필요합니다"
        )
    out.header_row = header_idx
    header = rows[header_idx]

    col_name = first_column(header, ["이름"], ["성함"])
    col_no = find_column(header, ["NO"])
    if col_name is None and col_no is not None and col_no + 1 < len(header) \
            and not norm(header[col_no + 1]):
        # 명단 시트 하나는 이름 칸의 **머리글이 비어 있다**(B1이 빈칸).
        # 번호 바로 오른쪽이고 머리글이 없을 때만 이름으로 본다 — 짐작이 아니라
        # 확인 가능한 조건이며, 리포트에 남겨 사람이 확인할 수 있게 한다.
        col_name = col_no + 1
        out.notes.append(
            f"머리글이 비어 있는 {col_name + 1}번째 열을 '이름' 으로 보았습니다"
        )
    # '딜소싱 참여 투자사'도 '투자사'를 포함한다 → 투자사'명'을 먼저 찾고, 없을 때만 넓게 본다.
    col_firm = find_column(header, ["투자사명"])
    if col_firm is None:
        col_firm = find_column(header, ["투자사"], exclude=["딜소싱", "참여"])
    if col_firm is None:
        # 명단 시트(150 / 98 / 30명)는 투자사를 '회사' 로 적는다.
        col_firm = find_column(header, ["회사"])
    if col_name is None or col_firm is None:
        raise ValueError("'이름' 또는 '투자사명'(또는 '회사') 컬럼을 찾지 못했습니다")

    cols = {
        "name": col_name,
        "firm": col_firm,
        "group": find_column(header, ["그룹"]),
        "owner": find_column(header, ["담당자"]),
        "invited": find_column(header, ["초대"]),
        "interest": find_column(header, ["관심도"]),
        "kakao_joined": first_column(header, ["카톡방", "참여"], ["카톡", "연결"]),
        "sectors": first_column(header, ["선호", "투자분야"], ["투자분야"]),
        "round": find_column(header, ["라운드"]),
        "memo": find_column(header, ["메모"]),
        "phone": first_column(header, ["휴대"], ["연락처"]),
        # 시트는 `근무처 전화` 라고 쓴다. `유선` 만 찾으면 아무것도 못 잡는다.
        "office_phone": first_column(header, ["유선"], ["근무처", "전화"]),
        "position": first_column(header, ["직책"], ["직함"]),
        # `전자 메일 주소` 에도 '주소' 가 들어 있다 — 빼지 않으면 이메일이
        # 주소 칸에 들어간다(실제로 그랬다).
        "address": find_column(header, ["주소"], exclude=["메일", "이메일", "전자"]),
        "department": find_column(header, ["부서"]),
        "email": first_column(header, ["전자", "메일"], ["이메일"]),
    }
    # 활동 컬럼은 기본 정보 컬럼을 빼고 헤더 문맥으로 찾는다(담당자 컬럼이 오른쪽에 있어도 안전).
    out.activity_columns = detect_activity_columns(
        rows, header_idx, year, skip_cols=[c for c in cols.values() if c is not None]
    )

    for offset, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        # 1-based 시트 행번호로 리포트한다(사용자가 시트에서 바로 찾을 수 있게).
        row_no = offset
        name_cell = _cell(row, cols["name"])
        firm = _cell(row, cols["firm"])
        preview = " | ".join(norm(c) for c in row[:6] if norm(c))[:80]

        if not name_cell and not firm:
            continue  # 완전 빈 행은 리포트에 담지 않는다(스킵 목록이 잡음으로 덮이지 않게)
        if not name_cell:
            out.skipped.append(SkippedRow(row_no, "이름 없음", preview))
            continue
        if _looks_like_junk(name_cell):
            out.skipped.append(SkippedRow(row_no, "비정형 행(이름 아님)", preview))
            continue
        if is_placeholder_name(name_cell):
            out.skipped.append(
                SkippedRow(row_no, "머리글과 칸이 어긋난 줄(이름 자리에 라벨)", preview))
            continue
        if not firm:
            out.skipped.append(SkippedRow(row_no, "투자사명 없음", preview))
            continue
        if looks_like_address(firm):
            # 회사 칸에 주소가 들어왔다 = 그 줄은 통째로 밀려 있다.
            # 넣으면 나머지 칸도 전부 엉뚱한 자리에 들어간다.
            out.skipped.append(
                SkippedRow(row_no, "머리글과 칸이 어긋난 줄(회사 자리에 주소)", preview))
            continue

        name, title = split_name_title(name_cell)
        # 직책이 별도 컬럼이면 그쪽이 더 정확하다(이름 칸에서 떼어낸 추정보다 우선).
        title = _cell(row, cols["position"]) or title

        sectors_raw = _cell(row, cols["sectors"])
        round_raw = _cell(row, cols["round"])
        combined = cols["sectors"] is not None and cols["sectors"] == cols["round"]

        contact = ParsedContact(
            row_no=row_no,
            name=name,
            title=title,
            firm=firm,
            group_name=_cell(row, cols["group"]) or None,
            owner_name=_cell(row, cols["owner"]) or None,
            invited_status=_cell(row, cols["invited"]) or None,
            interest_level=_cell(row, cols["interest"]) or None,
            kakao_joined=_cell(row, cols["kakao_joined"]) or None,
            profile_raw=sectors_raw or round_raw or None,
            # 한 칸에 '투자분야/라운드사이즈'가 합쳐진 시트는 원문을 라운드 칸에 남긴다
            # (자유 서술이라 쪼개면 근거 없는 값이 된다 — split_sector_tags 참고).
            sectors=split_sector_tags(sectors_raw),
            round_size=(sectors_raw if combined else round_raw) or None,
            memo=_cell(row, cols["memo"]) or None,
            phone=_cell(row, cols["phone"]) or None,
            office_phone=_cell(row, cols["office_phone"]) or None,
            address=_cell(row, cols["address"]) or None,
            department=_cell(row, cols["department"]) or None,
            email=_cell(row, cols["email"]) or None,
        )
        # 연결이 어디까지 갔는지는 시트에 한 칸으로 있지 않다 —
        # 카톡방 참여여부(O/X)와 메모 문장에서 읽어낸다.
        contact.connect_stage = connect_stage(
            contact.kakao_joined or "",
            contact.memo or "",
            invited=contact.invited_status or "",
        )
        for acol in out.activity_columns:
            cell_text = _raw_cell(row, acol.col)
            if not cell_text:
                continue
            contact.activities.extend(
                parse_activity_cell(cell_text, acol.month, acol.kind, year)
            )
        out.contacts.append(contact)

    return out


# 사람 이름 자리에 들어온 **자리표시 라벨**. 시트에 머리글이 다른 표가
# 아래로 이어 붙는 일이 있는데(`투자사 98명` 시트가 그렇다), 그 블록은 이름
# 칸에 `담당자2` 같은 라벨이 들어 있고 나머지 칸도 통째로 어긋난다.
# 그대로 넣으면 회사 칸에 주소가, 선호분야 칸에 휴대폰이 들어간
# **가짜 담당자**가 생긴다(실제로 58명이 그렇게 들어갔다).
_PLACEHOLDER_NAME = re.compile(r"^(담당자|이름|성명|연락처|번호|no)\s*\d*$",
                               re.IGNORECASE)


def _looks_like_junk(text: str) -> bool:
    """헤더에 섞인 임시 로그인 문자열·URL 등 비정형 행 (DATA_MODEL §6)."""
    t = norm(text)
    if len(t) > 30:
        return True
    return any(mark in t for mark in ("@", "://", "http", "비밀번호", "password", "로그인"))


def is_placeholder_name(text: str) -> bool:
    """이름 자리에 들어온 자리표시 라벨(`담당자2`).

    비정형 행(임시 로그인 문자열 등)과 원인이 다르다 — 이쪽은 **다른 표가
    아래로 이어 붙은 것**이라, 그 줄은 나머지 칸도 통째로 어긋나 있다.
    이유를 갈라 적어야 사용자가 시트에서 무엇을 고쳐야 하는지 안다.
    """
    return bool(_PLACEHOLDER_NAME.match(norm(text)))


# 주소는 회사 이름이 아니다. 칸이 어긋난 줄을 잡아내는 두 번째 그물 —
# 이름 칸이 멀쩡해도 나머지가 밀려 있을 수 있다.
_ADDRESS_RE = re.compile(
    r"(특별시|광역시|[가-힣]+도)\s|[가-힣]+시\s+[가-힣]+[구군]|"
    r"[가-힣]+[로길]\s*\d|\d+층")


def looks_like_address(text: str) -> bool:
    return bool(_ADDRESS_RE.search(norm(text)))


# ── 시트 B ──────────────────────────────────────────────────────────────────

@dataclass
class ParsedCompany:
    row_no: int
    name: str
    sector_major: Optional[str] = None
    sector_minor: Optional[str] = None
    series: Optional[str] = None
    one_liner: Optional[str] = None
    owner_name: Optional[str] = None
    ir_deck_raw: Optional[str] = None
    ir_drive_url: Optional[str] = None
    contract_status: str = "no"
    contract_month: Optional[str] = None
    is_top_deal: int = 0
    funding_status: Optional[str] = None
    note: Optional[str] = None
    # 기업 쪽 연락 담당자('스타트업' 명단 시트의 성함/연락처/이메일)
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None


@dataclass
class SheetBParse:
    companies: List[ParsedCompany] = field(default_factory=list)
    skipped: List[SkippedRow] = field(default_factory=list)
    header_row: Optional[int] = None


def parse_sheet_b(rows: Sequence[Sequence[str]], year: int) -> SheetBParse:
    """시트 B(IR 기업현황) → ir_companies (DATA_MODEL §2.5 매핑)."""
    out = SheetBParse()
    header_idx = detect_header_row(rows, ["기업명"])
    if header_idx is None:
        raise ValueError("헤더 행을 찾지 못했습니다 ('기업명'이 있는 행 필요)")
    out.header_row = header_idx
    header = rows[header_idx]

    deck_col = find_column(header, ["deck"])
    if deck_col is None:
        deck_col = find_column(header, ["ir"], exclude=["기업"])
    cols = {
        "name": find_column(header, ["기업명"]),
        "sector_major": find_column(header, ["대분류"]),
        "sector_minor": find_column(header, ["소분류"]),
        "series": first_column(header, ["기업구분"], ["시리즈"]),
        "one_liner": first_column(header, ["한줄"], ["한 줄"]),
        "owner": find_column(header, ["담당자"]),
        "deck": deck_col,
        # '계약여부'와 '계약 월'을 가르기 위해 '월'을 먼저 잡고 나머지를 여부로 본다.
        "contract_month": find_column(header, ["계약", "월"]),
        "contract": find_column(header, ["계약"], exclude=["월"]),
        "top": first_column(header, ["top"], ["핵심"]),
        "funding": find_column(header, ["투자유치"]),
        "note": find_column(header, ["비고"]),
        # '스타트업' 명단 시트에만 있는 기업 쪽 연락 담당자
        "contact_name": first_column(header, ["성함"], ["담당자명"]),
        "contact_phone": first_column(header, ["연락처"], ["휴대"]),
        "contact_email": find_column(header, ["이메일"]),
    }
    if cols["name"] is None:
        raise ValueError("'기업명' 컬럼을 찾지 못했습니다")

    for offset, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        row_no = offset
        name = _cell(row, cols["name"])
        preview = " | ".join(norm(c) for c in row[:6] if norm(c))[:80]
        if not any(norm(c) for c in row):
            continue
        if not name:
            out.skipped.append(SkippedRow(row_no, "기업명 없음", preview))
            continue

        deck_raw = _cell(row, cols["deck"])
        url = _extract_url(deck_raw)
        note = _cell(row, cols["note"]) or None
        if not url and _has_deck(deck_raw):
            # 링크를 모르면 '보유' 사실만 남기고 URL은 화면에서 수기 등록한다(DATA_MODEL §6).
            note = norm(f"{note or ''} IR deck 보유")

        out.companies.append(ParsedCompany(
            row_no=row_no,
            name=name,
            sector_major=_cell(row, cols["sector_major"]) or None,
            sector_minor=_cell(row, cols["sector_minor"]) or None,
            series=_cell(row, cols["series"]) or None,
            one_liner=_cell(row, cols["one_liner"]) or None,
            owner_name=_cell(row, cols["owner"]) or None,
            ir_deck_raw=deck_raw or None,
            ir_drive_url=url,
            contract_status=_contract_status(_cell(row, cols["contract"])),
            contract_month=_contract_month(_cell(row, cols["contract_month"]), year),
            is_top_deal=1 if _is_top(_cell(row, cols["top"])) else 0,
            funding_status=_cell(row, cols["funding"]) or None,
            note=note,
            contact_name=_cell(row, cols["contact_name"]) or None,
            contact_phone=_cell(row, cols["contact_phone"]) or None,
            contact_email=_cell(row, cols["contact_email"]) or None,
        ))
    return out


def _extract_url(text: str) -> Optional[str]:
    m = re.search(r"https?://\S+", text or "")
    return m.group(0) if m else None


def _has_deck(text: str) -> bool:
    t = norm(text).lower()
    return bool(t) and (("유" in t) or t in ("o", "y", "yes", "있음", "보유", "완료"))


def _contract_status(text: str) -> str:
    t = norm(text).lower()
    if not t:
        return "no"
    if any(k in t for k in ("진행", "협의", "검토", "pending")):
        return "pending"
    if any(k in t for k in ("완료", "체결", "유", "예")) or t in ("o", "y", "yes"):
        return "yes"
    return "no"


def _contract_month(text: str, year: int) -> Optional[str]:
    t = norm(text)
    if not t:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", t):
        return t
    m = _MONTH_RE.search(t)
    if m:
        return f"{year:04d}-{int(m.group(1)):02d}"
    return t


def _is_top(text: str) -> bool:
    t = norm(text).lower()
    if not t:
        return False
    return ("핵심" in t) or ("top" in t) or ("★" in t) or t in ("o", "y", "yes", "v", "●")


# ── DB 반영 (멱등 upsert) ───────────────────────────────────────────────────

@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    activities_created: int = 0
    activities_existing: int = 0
    skipped: List[SkippedRow] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_text(self, title: str) -> str:
        lines = [
            f"[{title}] 생성 {self.created} · 갱신 {self.updated} · "
            f"활동 {self.activities_created}건 추가(중복 {self.activities_existing}건 건너뜀) · "
            f"스킵 {len(self.skipped)}행",
        ]
        for note in self.notes:
            lines.append(f"  - {note}")
        for s in self.skipped:
            lines.append(f"  · {s.row_no}행 스킵 ({s.reason}): {s.preview}")
        return "\n".join(lines)


def _set_if_value(obj, attr: str, value) -> bool:
    """값이 있을 때만 덮어쓴다 — **상태 칸**용(초대완료여부·관심도·계약여부 등).

    이런 칸은 '지금 어떤 상태인가'라서 새 시트 값이 최신 판단이다.
    반대로 시트의 빈 칸이 기존 값을 지우면 안 된다 — 빈 값은 '모름'이지 '지워라'가 아니다.
    """
    if value in (None, "") or getattr(obj, attr) == value:
        return False
    setattr(obj, attr, value)
    return True


def _fill_if_empty(obj, attr: str, value) -> bool:
    """비어 있을 때만 채운다 — **프로필·연락처·메모**용.

    같은 사람이 여러 명단 시트에 조각조각 나뉘어 있어(한쪽엔 연락처, 다른 쪽엔 직책)
    임포트는 병합이 원칙이다. 나중에 넣은 시트가 앞 시트의 값이나 사용자가 화면에서
    다듬은 값을 밀어내면, 어느 시트를 먼저 넣었느냐에 따라 결과가 달라진다.
    """
    if value in (None, "") or getattr(obj, attr):
        return False
    setattr(obj, attr, value)
    return True


def apply_sheet_a(db: Session, parsed: SheetAParse, user_id: int,
                  room_suffix: str = DEFAULT_SUFFIX, dry_run: bool = False,
                  source_label: Optional[str] = None) -> ImportReport:
    """담당자 upsert (이름+투자사 기준) + 활동 이력 정규화 적재.

    소유자(user_id)는 시트의 **담당자 컬럼**이 정한다. 한 시트에 여러 팀원의 담당분이
    섞여 있기 때문이다. 이름이 계정과 매칭되지 않으면 **버리지 않고** 폴백 사용자
    (`user_id` 인자)에게 붙이고 리포트에 남긴다 — 임포트에서 사람을 잃는 것이 가장 나쁘다.

    매칭 키가 (이름, 투자사)뿐인 이유: 같은 사람이 여러 명단 시트에 나뉘어 있고 시트마다
    담당자 표기가 비거나 다르다. 소유자를 키에 넣으면 시트 수만큼 중복 인물이 생긴다.
    """
    report = ImportReport(skipped=list(parsed.skipped),
                          notes=list(getattr(parsed, 'notes', [])))
    # 명단(시트)을 등록한다. 담당은 **처음 정해진 것을 유지**한다 —
    # 시트를 한 번 올린 것만으로 남의 명단 담당이 넘어오면 안 된다.
    if source_label:
        written = next((pc.owner_name for pc in parsed.contacts
                        if looks_like_person(pc.owner_name)), None)
        owner = sheet_owner.ensure(db, source_label, user_id=None,
                                   assignee_name=written)
        if owner.user_id is None and not written:
            # 담당자 칸이 없는 시트는 올린 사람 것으로 본다(딜소개현황이 그렇다).
            owner.user_id = user_id
        db.flush()
    months = sorted({c.month for c in parsed.activity_columns if c.month})
    report.notes.append(
        f"활동 컬럼 {len(parsed.activity_columns)}개 인식"
        + (f" (월: {', '.join(months)})" if months else " (월 라벨 없음)")
    )
    owners: Dict[str, Optional[int]] = {}
    unmatched_owners: Dict[str, int] = {}
    no_owner_rows = 0

    for pc in parsed.contacts:
        owner_id = None
        if pc.owner_name:
            if pc.owner_name not in owners:
                found = db.execute(
                    select(User).where(User.name == pc.owner_name)
                ).scalars().first()
                owners[pc.owner_name] = found.id if found else None
            owner_id = owners[pc.owner_name]
            if owner_id is None:
                unmatched_owners[pc.owner_name] = unmatched_owners.get(pc.owner_name, 0) + 1
        else:
            no_owner_rows += 1

        contact = db.execute(
            select(VcContact).where(VcContact.name == pc.name, VcContact.firm == pc.firm)
        ).scalars().first()

        if contact is None:
            contact = VcContact(user_id=owner_id or user_id, name=pc.name, firm=pc.firm,
                                status="active")
            db.add(contact)
            report.created += 1
        else:
            report.updated += 1
            # 소유자는 시트가 **명시적으로 지목했을 때만** 옮긴다. 담당자 칸이 빈 시트를
            # 나중에 임포트했다고 해서 이미 정해진 담당을 폴백 사용자로 뺏으면 안 된다.
            if owner_id:
                contact.user_id = owner_id

        # 상태 칸: 새 시트가 최신 판단 → 덮어쓴다
        _set_if_value(contact, "invited_status", pc.invited_status)
        _set_if_value(contact, "interest_level", pc.interest_level)
        _set_if_value(contact, "kakao_joined", pc.kakao_joined)
        # 프로필·연락처: 시트마다 조각이 나뉘어 있다 → 비어 있을 때만 채운다(병합)
        _fill_if_empty(contact, "title", pc.title)
        _fill_if_empty(contact, "group_name", pc.group_name)
        _fill_if_empty(contact, "round_size", pc.round_size or pc.profile_raw)
        _fill_if_empty(contact, "memo", pc.memo)
        _fill_if_empty(contact, "phone", pc.phone)
        _fill_if_empty(contact, "office_phone", pc.office_phone)
        _fill_if_empty(contact, "address", pc.address)
        _fill_if_empty(contact, "department", pc.department)
        _fill_if_empty(contact, "email", pc.email)
        if pc.email:
            # 메일 주소가 있으면 메일 채널로도 보낼 수 있다.
            contact.channel_email = 1
        if pc.sectors:
            _fill_if_empty(contact, "sectors", ",".join(pc.sectors))
        if source_label:
            contact.source_sheet = _append_label(contact.source_sheet, source_label)
        # 시트의 담당자 이름은 계정이 없어도 보관한다. 버리면 누구 담당인지가
        # 사라져 임포트한 사람에게 전부 붙어 버린다(실제로 207명이 그렇게 됐다).
        if looks_like_person(pc.owner_name):
            contact.assignee_name = normalize_space(pc.owner_name)
        # 투자사 유형은 이름에 대개 드러나 있다. 비어 있을 때만 추론해 채운다.
        if not contact.firm_type:
            code, _why = firm_type.infer(pc.firm, pc.department, pc.title)
            if code != "unknown":
                contact.firm_type = code
        # '메일로 발송' 처럼 메일 채널로 관리하는 담당자는 카톡 대상이 아니다.
        # 방 확인에서 '실패'로 뜨면 고쳐야 할 건과 섞여 보이므로 채널로 구분한다.
        if "메일" in (pc.invited_status or ""):
            contact.channel_email = 1
        if is_invited(pc.invited_status or "") or is_invited(pc.kakao_joined or ""):
            # 초대/참여 완료 = 카톡방이 이미 있다 → 발송 대상 후보. 반대로 내리지는 않는다
            # (시트가 비어 있어도 서비스에서 연결해 둔 경우가 있으므로).
            contact.channel_kakao = 1
        # 연결 단계. **뒤로 내리지는 않는다** — 이미 방이 붙어 발송까지 한 담당자를
        # 오래된 명단 시트 하나 때문에 '미착수'로 되돌리면 발송 대상에서 빠진다.
        new_stage = pc.connect_stage or connect_stage(
            pc.kakao_joined or "", pc.memo or "",
            has_room=bool(contact.kakao_room_name),
            invited=pc.invited_status or "")
        if contact.kakao_room_name:
            contact.connect_stage = STAGE_CONNECTED
        elif contact.connect_stage != STAGE_CONNECTED:
            contact.connect_stage = new_stage

        # 방 이름은 **연결이 끝난 사람에게만** 지어 준다. 아직 방이 없는 사람에게
        # 이름을 지어 주면 발송 대상처럼 보이고, 실제로는 보낼 방이 없다.
        # 이미 값이 있으면 손대지 않는다 — 사용자가 실제 방 제목에 맞춰 고친 값일 수 있고,
        # 방 제목이 틀리면 발송이 통째로 skip 된다.
        if contact.connect_stage == STAGE_CONNECTED and not contact.kakao_room_name:
            contact.kakao_room_name = build_room_name(pc.name, contact.title, pc.firm,
                                                      suffix=room_suffix)
        db.flush()

        for act in pc.activities:
            if not act.content:
                continue
            exists = db.execute(
                select(ContactActivity.id).where(
                    ContactActivity.contact_id == contact.id,
                    ContactActivity.kind == act.kind,
                    ContactActivity.content == act.content,
                    ContactActivity.month.is_(act.month) if act.month is None
                    else ContactActivity.month == act.month,
                )
            ).first()
            if exists:
                report.activities_existing += 1
                continue
            db.add(ContactActivity(
                contact_id=contact.id, month=act.month, kind=act.kind,
                content=act.content, happened_at=act.happened_at,
                weekday=act.weekday, company_count=act.company_count,
                company_names=json.dumps(act.companies, ensure_ascii=False) if act.companies else None,
                raw_text=act.raw_text, source="import",
            ))
            report.activities_created += 1

    if unmatched_owners:
        detail = ", ".join(f"{n}({c}명)" for n, c in sorted(unmatched_owners.items()))
        report.notes.append(
            f"담당자 계정 미매칭 → 폴백 user_id={user_id} 로 배정(누락 없음): {detail}"
        )
    if no_owner_rows:
        report.notes.append(f"담당자 칸이 빈 행 {no_owner_rows}건 → 폴백 user_id={user_id}")

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report


def _append_label(current: Optional[str], label: str) -> str:
    """어느 시트에서 온 정보인지 누적 기록(중복 없이)."""
    labels = [x for x in (current or "").split(",") if x]
    if label not in labels:
        labels.append(label)
    return ",".join(labels)


def apply_sheet_b(db: Session, parsed: SheetBParse, dry_run: bool = False) -> ImportReport:
    """기업 upsert (기업명 기준). 담당자는 users.name 이 일치할 때만 연결한다."""
    report = ImportReport(skipped=list(parsed.skipped),
                          notes=list(getattr(parsed, 'notes', [])))
    owners: Dict[str, Optional[int]] = {}
    unmatched_owners = set()

    for pc in parsed.companies:
        company = db.execute(
            select(IrCompany).where(IrCompany.name == pc.name)
        ).scalars().first()
        if company is None:
            company = IrCompany(name=pc.name)
            db.add(company)
            report.created += 1
        else:
            report.updated += 1

        # 기업도 명단 시트가 여러 장이라 병합이 원칙(비어 있을 때만 채운다).
        _fill_if_empty(company, "sector_major", pc.sector_major)
        _fill_if_empty(company, "sector_minor", pc.sector_minor)
        _fill_if_empty(company, "series", pc.series)
        _fill_if_empty(company, "one_liner", pc.one_liner)
        _fill_if_empty(company, "ir_drive_url", pc.ir_drive_url)
        _fill_if_empty(company, "note", pc.note)
        _fill_if_empty(company, "contact_name", pc.contact_name)
        _fill_if_empty(company, "contact_phone", pc.contact_phone)
        _fill_if_empty(company, "contact_email", pc.contact_email)
        # 상태 칸은 새 시트가 최신 판단
        _set_if_value(company, "funding_status", pc.funding_status)
        _set_if_value(company, "contract_month", pc.contract_month)
        # 계약·핵심 여부는 시트가 최신 판단이므로 덮어쓴다(빈 칸 = '아니오'가 맞는 칸들).
        company.contract_status = pc.contract_status
        company.is_top_deal = pc.is_top_deal

        if pc.owner_name:
            if pc.owner_name not in owners:
                owner = db.execute(
                    select(User).where(User.name == pc.owner_name)
                ).scalars().first()
                owners[pc.owner_name] = owner.id if owner else None
            owner_id = owners[pc.owner_name]
            if owner_id:
                company.owner_user_id = owner_id
            else:
                unmatched_owners.add(pc.owner_name)
        db.flush()

    if unmatched_owners:
        report.notes.append(
            "담당자 미매칭(계정 없음, owner 비움): " + ", ".join(sorted(unmatched_owners))
        )
    report.notes.append("요약문(summary)은 임포트하지 않는다 — 딜 기업 DB 화면에서 작성/자동조합")

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report


# ── 기업 재무 시트(스타트업DB) ───────────────────────────────────────────────

def apply_company_financials(db, rows, *, dry_run: bool = False) -> ImportReport:
    """'스타트업DB(기업정보)' 탭 → 기존 ir_companies 에 재무 정보를 채운다.

    IR 기업현황 탭에는 한줄 소개·분야만 있고 매출·투자·밸류가 없다.
    그런데 딜소개 문구는 그 숫자들로 만들어지므로, 이 탭을 합쳐야 발송이 가능해진다.

    기업명으로 매칭하며, **이미 값이 있는 칸은 덮어쓰지 않는다**
    (사람이 손봐둔 값을 시트가 밀어내지 않도록).
    """
    report = ImportReport()
    header_idx = detect_header_row(rows, ["기업명"])
    if header_idx is None:
        raise ValueError("헤더 행을 찾지 못했습니다 ('기업명' 필요)")
    header = rows[header_idx]

    cols = {
        "name": find_column(header, ["기업명"]),
        "revenue": first_column(header, ["최근", "매출"], ["매출액"]),
        "raise_target": find_column(header, ["투자유치희망"]),
        "funding_total": find_column(header, ["누적투자"]),
        "pre_value": find_column(header, ["pre", "value"]),
        "competitiveness": first_column(header, ["특이사항"], ["장점"]),
        "sector": find_column(header, ["사업분야"]),
    }
    if cols["name"] is None:
        raise ValueError("'기업명' 컬럼을 찾지 못했습니다")

    # 이름 → 기업 (정규화해서 '(주)' 유무 차이를 흡수)
    index = {}
    for c in db.execute(select(IrCompany)).scalars().all():
        index.setdefault(normalize_company_name(c.name), c)

    for row in rows[header_idx + 1:]:
        raw_name = _cell(row, cols["name"])
        if not raw_name:
            continue
        company = index.get(normalize_company_name(raw_name))
        if company is None:
            # 재무 시트에만 있고 기업 DB 에는 없는 회사 — 새로 만들지 않고 남긴다
            # (IR 기업현황 탭이 기준 명단이므로 여기서 임의로 늘리지 않는다).
            report.skipped.append(SkippedRow(row_no=0, reason="기업 DB 에 없음",
                                             preview=raw_name[:40]))
            continue

        changed = False
        for field, col in (("revenue_recent", "revenue"),
                           ("raise_target", "raise_target"),
                           ("funding_total", "funding_total"),
                           ("pre_value", "pre_value")):
            if getattr(company, field) not in (None, 0):
                continue   # 사람이 넣어둔 값 보존
            value = parse_money_to_million(_raw_cell(row, cols[col]))
            if value:
                setattr(company, field, value)
                changed = True

        if not company.competitiveness:
            note = _raw_cell(row, cols["competitiveness"]).strip()
            if note:
                company.competitiveness = note[:300]
                changed = True
        if not company.one_liner:
            desc = _raw_cell(row, cols["sector"]).strip()
            if desc:
                company.one_liner = desc[:300]
                changed = True

        if changed:
            report.updated += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report
