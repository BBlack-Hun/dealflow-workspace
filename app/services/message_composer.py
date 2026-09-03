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
    # 여러 통으로 나눠 보낼 때의 순서. 한 통이면 비어 있다.
    # `text` 는 언제나 이것을 합친 전문이라, parts 를 모르는 쪽은 한 통으로 보낸다.
    parts: List[str] = field(default_factory=list)


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

    # ★ 시트의 '한줄 소개'는 이미 재무까지 담은 완성 문구인 경우가 많다
    #   (예: "… | 매출 30.9억 | 누적투자금액 5.6억 | 투자유치 협의중 | …").
    #   같은 항목을 또 붙이면 '매출 2.2억 … 매출 10억' 처럼 **중복되고 숫자가 어긋난다**.
    #   그래서 항목마다 '한줄 소개에 이미 있는지' 보고 없을 때만 덧붙인다.
    said = (company.one_liner or "")

    revenue = format_eok(company.revenue_recent)
    if revenue is not None and "매출" not in said:
        segments.append(f"매출 {revenue}억")

    funding = format_eok(company.funding_total)
    if funding is not None and "누적투자" not in said:
        segments.append(f"누적투자금액 {funding}억")

    raise_target = format_eok(company.raise_target)
    if raise_target is not None and "투자유치" not in said:
        segments.append(f"{raise_target}억 투자유치중")

    pre_value = format_eok(company.pre_value)
    if pre_value is not None and not any(k in said.lower() for k in ("pre value", "밸류")):
        segments.append(f"Pre Value 약 {pre_value}억원")

    if company.competitiveness and company.competitiveness.strip() not in said:
        segments.append(company.competitiveness.strip())

    return " | ".join(segments)


def company_summary(company: CompanyView) -> str:
    """Return the manual/cached summary if present, else auto-compose (수동 수정본 우선)."""
    if company.summary and company.summary.strip():
        return company.summary.strip()
    return auto_company_summary(company)


def render_template(text: str, contact: ContactView, company_name: Optional[str] = None,
                    ir_drive_url: Optional[str] = None,
                    company_count: Optional[int] = None,
                    company_list: Optional[str] = None,
                    file_links: Optional[str] = None) -> str:
    """Substitute template variables for a given contact.

    Supported: {담당자명} {직함} {투자사} {기업명} {ir_drive_url} {개수} {기업목록} {자료링크}
    Unknown {…} tokens are left untouched (so authors can spot typos).

    `{자료링크}` 는 **더 이상 채우지 않는다**(구글 드라이브 링크 방식 폐기).
    치환 목록에는 남아 있어야 옛 문구에 적힌 토큰이 빈칸으로 지워진다.

    `{기업목록}` 은 IR 자료 전달에서 "1번 기업 샘플애그" 처럼 **지난 회차에서의 번호**로
    채운다. 투자사는 그 번호로 기억하고 있어서, 번호가 없으면 어느 기업인지 못 찾는다.
    """
    mapping = {
        "{담당자명}": contact.name or "",
        # 직함은 항상 존칭을 붙여서 치환한다(아래 greeting_title 참고).
        "{직함}": greeting_title(contact),
        "{투자사}": contact.firm or "",
        "{기업명}": company_name or "",
        "{ir_drive_url}": ir_drive_url or "",
        # 안내문 "핵심 딜 {개수}개사 …" 용 — 선택된 기업 수를 자동 반영.
        "{개수}": str(company_count) if company_count is not None else "",
        "{기업목록}": company_list or "",
        # **폐기한 자리.** 구글 드라이브 링크를 문구에 실어 보내는 방식은
        # 그만뒀다(자료는 사람이 PC 카톡에서 파일로 첨부한다). 그런데 치환
        # 자체는 남겨 둔다 — 모르는 `{…}` 는 그대로 두는 것이 이 함수의 규칙
        # 이라, 여기서 빼면 손으로 고쳐 둔 문구에 남아 있는 `{자료링크}` 가
        # **글자 그대로 투자사 카톡방에 나간다.** 빈칸으로 지우는 편이 맞다.
        "{자료링크}": file_links or "",
    }
    out = text
    for key, value in mapping.items():
        out = out.replace(key, value)
    return _fix_honorific(out)


#: 인사말에서만 직함으로 더 인정하는 낱말.
#:
#: 방 이름의 어휘(`room_name` 의 `_TITLE_WORDS`)를 바탕에 두고 **직급·자격만**
#: 더한다. 방 이름 쪽 어휘를 넓히면 이미 연결해 둔 카톡방과 글자가 어긋나
#: 발송이 조용히 건너뛰어진다 — 인사말에는 그 제약이 없다.
_GREETING_TITLE_WORDS = ("대리", "사원", "주임", "선임", "수석", "책임",
                         "변호사", "회계사", "변리사", "고문", "감사")


def name_carries_title(name: Optional[str]) -> bool:
    """이름 칸에 직함이 함께 적혀 있는가 — '최가온 대리 심사역'.

    딜 소싱 명단은 사람이 시트에 손으로 적어 온 것이라, 이름 칸에 직함이 섞여
    있는 줄이 있다. 그걸 모르고 직함을 또 붙이면 **'… 대리 심사역 심사역님'** 이
    나간다(사용자가 실제로 받은 문구다).

    **낱말이 따로 떨어져 있을 때만** 직함으로 본다. '김이사' 처럼 직함처럼
    보이는 이름을 잘라 내면 안 되기 때문이다(`room_name.split_name_title` 과
    같은 조심).
    """
    from . import room_name

    tokens = room_name.normalize_space(name or "").split(" ")
    if len(tokens) < 2:
        return False
    last = tokens[-1]
    if last.endswith("님"):
        return True
    # '이사/변호사' 처럼 빗금으로 이어 적기도 한다 — 앞쪽 낱말로 가른다.
    return room_name.looks_like_title(last.split("/")[0].strip(),
                                      _GREETING_TITLE_WORDS)


def primary_title(title: Optional[str]) -> str:
    """여러 직함이 이어져 있으면 **앞의 하나**만 부른다.

    명함에는 '팀장 / 수석심사역', '부장 / 본부장 / FRM' 처럼 겸직과 자격을 함께
    적어 둔다. 그대로 부르면 '한지우 팀장 / 수석심사역님' 이 되어 인사말로
    읽히지 않는다. 앞에 적힌 것이 그 사람을 부르는 직함이고, 뒤로 갈수록 겸직·
    자격증이 온다.

    **직함 칸의 값은 고치지 않는다** — 사람이 적어 둔 명함 정보다. 부를 때만
    하나를 고른다.
    """
    t = (title or "").strip()
    if "/" not in t:
        return t
    return t.split("/")[0].strip() or t


def greeting_title(contact: "ContactView") -> str:
    """인사말에 들어갈 직함. `{직함}` 이 이 값으로 바뀐다."""
    if name_carries_title(contact.name):
        # 이름이 이미 직함을 달고 있다. **존칭만** 붙인다 — 여기서 직함을 또
        # 붙이면 '최가온 대리 심사역 심사역님' 이 된다. 빈 직함과 같은 길로
        # 보내면 `_fix_honorific` 이 앞의 공백을 지워 '… 심사역님' 이 된다.
        return "님"
    return honorific_title(primary_title(contact.title))


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
    include_opening: bool = True,
    company_list: Optional[str] = None,
    file_links: Optional[str] = None,
    link_blocks: Optional[List[str]] = None,
) -> ComposeResult:
    """Assemble the final Kakao message text for one contact.

    Day1 includes numbered company summaries; remind/meeting stages omit them.

    ``include_opening=False`` 는 인사말을 빼고 본문만 보낸다. 이미 대화가 오간
    방에 한 줄만 덧붙일 때는 매번 "안녕하세요, ○○○ 님" 을 다시 붙이는 편이
    오히려 어색하다(선호 분야를 되묻는 문구가 그렇다).
    """
    warnings: List[str] = []
    companies = companies or []
    count = len(companies) if stage == STAGE_DAY1 else 0

    opening = render_template(opening_body, contact, company_count=count,
                              company_list=company_list,
                              file_links=file_links).strip()
    # 실제 운영 문구에서 안내문("핵심 딜 N개사 …/관심 가시는 기업 있으시면 IR Deck …")은
    # 기업 목록 '위'에 온다. closing_body는 그 안내문을 담는다.
    intro = render_template(closing_body, contact, company_count=count,
                            company_list=company_list,
                            file_links=file_links).strip()

    parts: List[str] = [opening, "", intro] if include_opening else [intro]

    if stage == STAGE_DAY1:
        if not companies:
            warnings.append("선택된 기업이 없습니다.")
        for idx, company in enumerate(companies, start=1):
            summary = company_summary(company)
            parts.append("")  # blank line separator
            parts.append(f"{idx}) {summary}")

    body = "\n".join(parts).strip()

    # ── 여러 통으로 나눠 보내는 길 ─────────────────────────────────────
    #
    # `link_blocks` 를 받으면 그 덩어리를 한 통씩 순서대로 던지고 마지막에
    # 본문을 붙인다.
    #
    # **지금 이 길을 쓰는 곳은 없다.** 자료 전달이 구글 드라이브 링크를 이렇게
    # 나눠 보냈는데 그 방식을 폐기했다(0053) — 자료는 사람이 PC 카톡에서 파일로
    # 첨부한다. 길 자체는 남겨 둔다: 발송 프로그램이 0.2.0 부터 `parts` 를
    # 그대로 보내게 되어 있어(`SendItem.parts_json`), 다시 나눠 보낼 일이
    # 생겼을 때 양쪽을 함께 되살릴 필요가 없다.
    bubbles: List[str] = []
    if link_blocks:
        bubbles = [b.strip() for b in link_blocks if b.strip()]
        # 템플릿이 {자료링크} 로 링크를 이미 품고 있으면 본문에서 걷어낸다 —
        # 그대로 두면 같은 링크가 두 번 나간다.
        if file_links and file_links in body:
            body = body.replace(file_links, "").strip()
        if body:
            bubbles.append(body)

    text = ("\n\n".join(bubbles) if bubbles else body).strip() + "\n"
    char_count = len(text)
    too_long = char_count > MESSAGE_WARN_CHARS
    if too_long:
        warnings.append(
            f"메시지가 {char_count}자로 {MESSAGE_WARN_CHARS}자를 초과했습니다 "
            "(카톡 장문 붙여넣기 안정성 주의)."
        )

    return ComposeResult(text=text, char_count=char_count, too_long=too_long,
                         warnings=warnings, parts=bubbles)
