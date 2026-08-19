"""Message composition service (ROADMAP task 1.4, FEATURE_SPEC §5 조합 규칙).

Pure functions with no DB dependency so they are trivially unit-testable.
Callers adapt SQLAlchemy models into the light dataclasses below.

Assembly (Day 1):
    {오프닝}
    <blank>
    [1] {기업A 요약}
    <blank>
    [2] {기업B 요약}
    <blank>
    [3] {기업C 요약}
    <blank>
    {클로징}

Remind / meeting stages repeat NO company summaries — short opening + closing only.
Money fields are stored in 백만원 (millions of KRW) and rendered in 억 (÷100).
Empty summary segments are dropped entirely (no "매출 억").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Stage constants
STAGE_DAY1 = 1
STAGE_REMIND = 2
STAGE_MEETING = 3

# Length warning threshold (kept in sync with app.config.MESSAGE_WARN_CHARS).
MESSAGE_WARN_CHARS = 3000

# 1회 딜소개에 담을 수 있는 기업 수 상한.
# 실제 운영 문구가 "핵심 딜 7개사" 형태로 나가므로 3개 제한은 현실과 맞지 않는다.
MAX_COMPANIES_PER_SEND = 10


@dataclass
class CompanyView:
    """Minimal company projection used for summary composition."""

    name: str
    sector_major: Optional[str] = None
    sector_minor: Optional[str] = None
    one_liner: Optional[str] = None
    revenue_recent: Optional[int] = None   # 백만원
    funding_total: Optional[int] = None    # 백만원
    raise_target: Optional[int] = None     # 백만원
    pre_value: Optional[int] = None        # 백만원
    competitiveness: Optional[str] = None
    summary: Optional[str] = None          # manual/cached summary; takes priority when set


@dataclass
class ContactView:
    """Minimal contact projection for template substitution."""

    name: str
    title: Optional[str] = None
    firm: Optional[str] = None


@dataclass
class ComposeResult:
    text: str
    char_count: int
    too_long: bool
    warnings: List[str] = field(default_factory=list)


def format_eok(value_baekman: Optional[int]) -> Optional[str]:
    """Convert 백만원 (millions of KRW) into a 억 display string.

    100 백만원 == 1억. Trailing ".0" is stripped. Returns None for empty input
    so the caller can drop the whole segment.
    """
    if value_baekman is None:
        return None
    eok = value_baekman / 100.0
    if eok == int(eok):
        return str(int(eok))
    # One decimal place is enough for these figures (e.g. 3090 -> "30.9").
    return f"{eok:.1f}".rstrip("0").rstrip(".")


def auto_company_summary(company: CompanyView) -> str:
    """Compose the deal summary line from raw fields.

    Format: [분야] | 한줄소개 | 매출 N억 | 누적투자금액 N억 | N억 투자유치중
            | Pre Value 약 N억원 | 경쟁력
    Empty segments are omitted entirely.
    """
    segments: List[str] = []

    if company.sector_major:
        segments.append(f"[{company.sector_major}]")
    if company.one_liner:
        segments.append(company.one_liner.strip())

    revenue = format_eok(company.revenue_recent)
    if revenue is not None:
        segments.append(f"매출 {revenue}억")

    funding = format_eok(company.funding_total)
    if funding is not None:
        segments.append(f"누적투자금액 {funding}억")

    raise_target = format_eok(company.raise_target)
    if raise_target is not None:
        segments.append(f"{raise_target}억 투자유치중")

    pre_value = format_eok(company.pre_value)
    if pre_value is not None:
        segments.append(f"Pre Value 약 {pre_value}억원")

    if company.competitiveness:
        segments.append(company.competitiveness.strip())

    return " | ".join(segments)


def company_summary(company: CompanyView) -> str:
    """Return the manual/cached summary if present, else auto-compose (수동 수정본 우선)."""
    if company.summary and company.summary.strip():
        return company.summary.strip()
    return auto_company_summary(company)


def render_template(text: str, contact: ContactView, company_name: Optional[str] = None,
                    ir_drive_url: Optional[str] = None,
                    company_count: Optional[int] = None) -> str:
    """Substitute template variables for a given contact.

    Supported: {담당자명} {직함} {투자사} {기업명} {ir_drive_url} {개수}
    Unknown {…} tokens are left untouched (so authors can spot typos).
    """
    mapping = {
        "{담당자명}": contact.name or "",
        # 직함은 항상 존칭을 붙여서 치환한다(아래 honorific_title 참고).
        "{직함}": honorific_title(contact.title),
        "{투자사}": contact.firm or "",
        "{기업명}": company_name or "",
        "{ir_drive_url}": ir_drive_url or "",
        # 안내문 "핵심 딜 {개수}개사 …" 용 — 선택된 기업 수를 자동 반영.
        "{개수}": str(company_count) if company_count is not None else "",
    }
    out = text
    for key, value in mapping.items():
        out = out.replace(key, value)
    return _fix_honorific(out)


def honorific_title(title: Optional[str]) -> str:
    """직함에 존칭('님')을 보장한다.

    시트 데이터가 뒤섞여 있다:
      - '대표님', '팀장님', '이사님'  → 이미 '님' 포함
      - '심사역', '파트너'            → '님' 없음 → 붙여야 함
    직함이 비어 있으면 '님'만 반환해 '{담당자명} {직함}' 이 '홍길동님' 이 되게 한다
    (뒤의 _fix_honorific 가 이름과 '님' 사이 공백을 정리).
    """
    t = (title or "").strip()
    if not t:
        return "님"
    return t if t.endswith("님") else t + "님"


def _fix_honorific(text: str) -> str:
    """존칭 표기 정리.

    1) '대표님님' 처럼 겹친 존칭을 하나로 (템플릿이 '{직함}님' 으로 쓰인 경우).
    2) 이름과 존칭 사이 공백 제거: '홍길동 님' → '홍길동님'
       (직함이 비어 '{직함}' 이 '님' 만으로 치환된 경우를 자연스럽게 만든다.
        '대표님' 처럼 앞이 공백이 아닌 경우는 영향 없음.)
    """
    while "님님" in text:
        text = text.replace("님님", "님")
    text = re.sub(r"[ \t]+님", "님", text)
    return text


def pick_opening_kind(has_history: bool) -> str:
    """First-contact vs re-contact opening selection based on prior send history."""
    return "opening_re" if has_history else "opening_first"


def compose_message(
    opening_body: str,
    closing_body: str,
    contact: ContactView,
    companies: Optional[List[CompanyView]] = None,
    stage: int = STAGE_DAY1,
) -> ComposeResult:
    """Assemble the final Kakao message text for one contact.

    Day1 includes numbered company summaries; remind/meeting stages omit them.
    """
    warnings: List[str] = []
    companies = companies or []
    count = len(companies) if stage == STAGE_DAY1 else 0

    opening = render_template(opening_body, contact, company_count=count).strip()
    # 실제 운영 문구에서 안내문("핵심 딜 N개사 …/관심 가시는 기업 있으시면 IR Deck …")은
    # 기업 목록 '위'에 온다. closing_body는 그 안내문을 담는다.
    intro = render_template(closing_body, contact, company_count=count).strip()

    parts: List[str] = [opening, "", intro]

    if stage == STAGE_DAY1:
        if not companies:
            warnings.append("선택된 기업이 없습니다.")
        for idx, company in enumerate(companies, start=1):
            summary = company_summary(company)
            parts.append("")  # blank line separator
            parts.append(f"{idx}) {summary}")

    text = "\n".join(parts).strip() + "\n"
    char_count = len(text)
    too_long = char_count > MESSAGE_WARN_CHARS
    if too_long:
        warnings.append(
            f"메시지가 {char_count}자로 {MESSAGE_WARN_CHARS}자를 초과했습니다 "
            "(카톡 장문 붙여넣기 안정성 주의)."
        )

    return ComposeResult(text=text, char_count=char_count, too_long=too_long, warnings=warnings)
