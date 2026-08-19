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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ContactActivity, IrCompany, User, VcContact
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
# '8/13(목) 기업A, 기업B' · '8.4 핵심 딜' · '08/19(수)'
_DATE_PREFIX_RE = re.compile(r"^\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*(?:\([^)]*\))?\s*[:·\-]?\s*")


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
                            start_col: int, year: int) -> List[ActivityColumn]:
    """start_col 오른쪽의 월별 3열 세트를 **반복 스캔**한다.

    달이 갈수록 열이 늘어나는 구조라 '6·7·8월' 같은 고정 목록을 쓰지 않는다.
    월 라벨이 없는 컬럼은 **직전 컬럼의 월을 이어받는다**(병합 셀 대응).
    """
    width = max((len(r) for r in rows), default=0)
    out: List[ActivityColumn] = []
    current_month: Optional[str] = None
    for col in range(start_col, width):
        context = _column_context(rows, header_idx, col)
        if not context:
            continue
        m = _MONTH_RE.search(context)
        if m:
            current_month = f"{year:04d}-{int(m.group(1)):02d}"
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


def parse_activity_cell(text: str, month: Optional[str], kind: str,
                        year: int) -> List[ParsedActivity]:
    """한 칸에 줄바꿈으로 누적된 **여러 회차**를 회차별 레코드로 분해한다.

        8/4(화) 핵심 딜 8개사
        (빈 줄)
        8/13(목) 샘플기업A, 샘플기업B
        8/19(수) 샘플기업C

    → 3건. 날짜로 시작하지 않는 줄은 직전 회차의 내용에 이어 붙인다
    (기업 목록이 다음 줄로 넘어가는 경우가 잦다).
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
            happened = _safe_date(year, mm, dd)
            entries.append(ParsedActivity(month=month or (happened[:7] if happened else None),
                                          kind=kind, content=content or line,
                                          happened_at=happened))
        elif entries:
            entries[-1].content = norm(f"{entries[-1].content} {line}")
        else:
            entries.append(ParsedActivity(month=month, kind=kind, content=line))
    return entries


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


def is_invited(value: str) -> bool:
    """'초대완료여부' 칸이 완료를 뜻하는가 (표기가 시트마다 제각각)."""
    v = norm(value).lower()
    if not v:
        return False
    return ("완료" in v) or ("완" == v) or v in ("o", "y", "yes", "ok", "v", "√", "○", "●")


# ── 시트 A ──────────────────────────────────────────────────────────────────

@dataclass
class ParsedContact:
    row_no: int
    name: str
    title: Optional[str]
    firm: str
    group_name: Optional[str] = None
    invited_status: Optional[str] = None
    profile_raw: Optional[str] = None       # 투자분야/라운드사이즈 원문
    sectors: List[str] = field(default_factory=list)
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


def parse_sheet_a(rows: Sequence[Sequence[str]], year: int) -> SheetAParse:
    """시트 A(투자사 관리) → 담당자 + 월별 활동."""
    out = SheetAParse()
    header_idx = detect_header_row(rows, ["그룹", "이름", "투자사"])
    if header_idx is None:
        raise ValueError("헤더 행을 찾지 못했습니다 ('그룹/이름/투자사명'이 있는 행 필요)")
    out.header_row = header_idx
    header = rows[header_idx]

    col_group = find_column(header, ["그룹"])
    col_name = first_column(header, ["이름"], ["성함"])
    col_firm = find_column(header, ["투자사"])
    col_invited = find_column(header, ["초대"])
    col_profile = first_column(header, ["투자분야"], ["라운드"])
    if col_name is None or col_firm is None:
        raise ValueError("'이름' 또는 '투자사명' 컬럼을 찾지 못했습니다")

    base_last = max(x for x in (col_group, col_name, col_firm, col_invited, col_profile)
                    if x is not None)
    out.activity_columns = detect_activity_columns(rows, header_idx, base_last + 1, year)

    for offset, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        # 1-based 시트 행번호로 리포트한다(사용자가 시트에서 바로 찾을 수 있게).
        row_no = offset
        name_cell = _cell(row, col_name)
        firm = _cell(row, col_firm)
        preview = " | ".join(norm(c) for c in row[:6] if norm(c))[:80]

        if not name_cell and not firm:
            continue  # 완전 빈 행은 리포트에 담지 않는다(스킵 목록이 잡음으로 덮이지 않게)
        if not name_cell:
            out.skipped.append(SkippedRow(row_no, "이름 없음", preview))
            continue
        if _looks_like_junk(name_cell):
            out.skipped.append(SkippedRow(row_no, "비정형 행(이름 아님)", preview))
            continue
        if not firm:
            out.skipped.append(SkippedRow(row_no, "투자사명 없음", preview))
            continue

        name, title = split_name_title(name_cell)
        profile = _cell(row, col_profile)
        contact = ParsedContact(
            row_no=row_no,
            name=name,
            title=title,
            firm=firm,
            group_name=_cell(row, col_group) or None,
            invited_status=_cell(row, col_invited) or None,
            profile_raw=profile or None,
            sectors=split_sector_tags(profile),
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


def _looks_like_junk(text: str) -> bool:
    """헤더에 섞인 임시 로그인 문자열·URL 등 비정형 행 (DATA_MODEL §6)."""
    t = norm(text)
    if len(t) > 30:
        return True
    return any(mark in t for mark in ("@", "://", "http", "비밀번호", "password", "로그인"))


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
    """값이 있을 때만 덮어쓴다.

    재임포트 시 시트의 빈 칸이 서비스에서 채워 넣은 값을 지우면 안 된다
    (특히 방 이름·메모). 빈 값은 '모름'이지 '지워라'가 아니다.
    """
    if value in (None, "") or getattr(obj, attr) == value:
        return False
    setattr(obj, attr, value)
    return True


def apply_sheet_a(db: Session, parsed: SheetAParse, user_id: int,
                  room_suffix: str = DEFAULT_SUFFIX, dry_run: bool = False) -> ImportReport:
    """담당자 upsert (이름+투자사 기준) + 활동 이력 정규화 적재."""
    report = ImportReport(skipped=list(parsed.skipped))
    months = sorted({c.month for c in parsed.activity_columns if c.month})
    report.notes.append(
        f"활동 컬럼 {len(parsed.activity_columns)}개 인식"
        + (f" (월: {', '.join(months)})" if months else " (월 라벨 없음)")
    )

    for pc in parsed.contacts:
        contact = db.execute(
            select(VcContact).where(
                VcContact.user_id == user_id,
                VcContact.name == pc.name,
                VcContact.firm == pc.firm,
            )
        ).scalars().first()

        if contact is None:
            contact = VcContact(user_id=user_id, name=pc.name, firm=pc.firm, status="active")
            db.add(contact)
            report.created += 1
        else:
            report.updated += 1

        _set_if_value(contact, "title", pc.title)
        _set_if_value(contact, "group_name", pc.group_name)
        _set_if_value(contact, "invited_status", pc.invited_status)
        _set_if_value(contact, "round_size", pc.profile_raw)
        if pc.sectors:
            _set_if_value(contact, "sectors", ",".join(pc.sectors))
        if is_invited(pc.invited_status or ""):
            # 초대 완료 = 카톡방이 이미 있다 → 발송 대상 후보. 반대로 내리지는 않는다
            # (시트가 비어 있어도 서비스에서 연결해 둔 경우가 있으므로).
            contact.channel_kakao = 1
        if not contact.kakao_room_name:
            # 방 이름은 이름·직함·투자사에서 자동 생성한다(126명 수기 입력 회피).
            # 이미 값이 있으면 손대지 않는다 — 사용자가 실제 방 제목에 맞춰 고친 값일 수 있고,
            # 방 제목이 틀리면 발송이 통째로 skip 된다.
            contact.kakao_room_name = build_room_name(pc.name, pc.title, pc.firm,
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
                content=act.content, happened_at=act.happened_at, source="import",
            ))
            report.activities_created += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report


def apply_sheet_b(db: Session, parsed: SheetBParse, dry_run: bool = False) -> ImportReport:
    """기업 upsert (기업명 기준). 담당자는 users.name 이 일치할 때만 연결한다."""
    report = ImportReport(skipped=list(parsed.skipped))
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

        _set_if_value(company, "sector_major", pc.sector_major)
        _set_if_value(company, "sector_minor", pc.sector_minor)
        _set_if_value(company, "series", pc.series)
        _set_if_value(company, "one_liner", pc.one_liner)
        _set_if_value(company, "ir_drive_url", pc.ir_drive_url)
        _set_if_value(company, "funding_status", pc.funding_status)
        _set_if_value(company, "note", pc.note)
        _set_if_value(company, "contract_month", pc.contract_month)
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
