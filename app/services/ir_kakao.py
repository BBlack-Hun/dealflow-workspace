"""`7월 말까지 … IR 자료 요청한투자사 리스트` — **카톡으로 나가는 글** 한 통.

## 왜 문서(#131) 옆에 글이 또 있나

#131 이 만든 것은 **인쇄용 문서 한 장**이다. 그런데 사용자가 실제로 대표에게
보내는 것은 문서가 아니라 **카톡 글**이었다. 실물을 받아 보니 모양이 다르다 —
표가 아니라 줄이고, 한 달치가 아니라 누적이고, 받는 창이 카톡이라 글자 수에
제약이 있다.

문서는 지우지 않는다(Windows 파일 첨부 시험에 쓰인다). **둘 다 남되 세는 자리와
가리는 자리는 하나씩**이다 — 이 파일은 `ir_monthly`(세기)와 `ir_mask`(가리기)를
부르기만 하고, 제 손으로 세지도 가리지도 않는다.

## 왜 문구틀(`message_templates`)이 아니라 코드인가

이 저장소는 나가는 글을 문구틀에 두는 결이 있다(`template_pick` · `startup_msg`).
여기서는 **따르지 않는다.** 까닭이 셋이다.

1. **글의 몸통이 통째로 자료다.** 문구틀이 쓸모 있는 것은 사람이 고칠 문장이
   있을 때다. 이 글에서 사람이 고칠 수 있는 것은 머리말 세 줄뿐이고, 나머지는
   줄마다 날짜·기업·투자사가 다른 **목록**이다. 문구틀에 넣으면 편집자에게
   주는 것은 거의 없고, **깨뜨릴 방법**은 하나 생긴다 — 목록 자리를 지우면
   대표에게 머리말만 있는 글이 나간다.
2. **`{기업목록}` 은 이미 다른 뜻이다.** `message_composer.render_template` 의
   그 자리는 투자사에게 보내는 "2번 기업 …" 이다(`deal_numbers` 가 붙인 번호).
   한 토큰이 화면마다 다른 것을 뜻하기 시작하면 문구를 고치는 사람이 무엇이
   나올지 알 수 없다.
3. **가리기가 문구틀 밖에 있어야 한다.** 문구틀이 목록을 만들 수 있게 하면
   `{투자사}` 처럼 **안 가려진** 자리도 같은 글에 쓸 수 있게 된다. 가리는 것을
   문구를 고치는 사람 손에 맡기는 셈이라, 한 번 잘못 적히면 그대로 나간다.

머리말을 팀이 고치고 싶어지면 그때 머리말**만** 문구틀로 뺄 수 있다 — 목록을
짓는 이 함수는 그대로 둔 채로.

## 실물의 띄어쓰기를 그대로 둔다

`요청한투자사` · `드릴예정 입니다` · 기업 사이의 ` , ` 는 사용자가 실제로 쓰는
글자 그대로다. 눈에 띈다고 여기서 고치면 **지금까지 대표들이 받아 온 글과 다른
글**이 나가기 시작하는데, 그 바뀜을 아무도 결정한 적이 없다. 고칠 일이면 사람이
고치는 것이지 옮겨 적는 코드가 할 일이 아니다.

## 발송은 아직 없다

스타트업 카톡방이 자료에 없다(`IrCompany` 에 방 칸 자체가 없다). 그래서 이
파일은 **글을 짓는 데까지**만 한다. 나중에 발송을 붙일 때 다시 짜지 않아도
되도록 화면 밖 함수로 두고, 나눠 보낼 때의 순서(`parts`)까지 미리 낸다 —
발송 프로그램은 그 모양을 이미 읽을 줄 안다(`SendItem.parts_json`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from ..models import IrCompany
from . import ir_monthly
from . import message_composer as mc

#: 머리말 첫 줄. 받는 사람이 대표라 이름을 부르지 않는다 —
#: 이름을 넣으려면 그 이름이 정말 대표인지 아는 칸이 있어야 한다(아래 참고).
HELLO = "안녕하세요 대표님"

#: 머리말 셋째 줄. **실물 그대로**다(위 머리말 참고).
LEAD = ("IR 자료 요청한투자사 리스트 입니다 "
        "미팅요청 투자사가 나오면 연락을 드릴예정 입니다.")

#: 머리말에서 기업을 잇는 글자. 실물이 `(주)가 , (주)나` 다.
COMPANY_SEP = " , "

#: 한 통이 이보다 길면 나눈다. **새 숫자를 짓지 않는다** —
#: 이 저장소가 이미 카톡 한 통의 한계로 쓰는 값이다(`message_composer`).
LIMIT = mc.MESSAGE_WARN_CHARS


@dataclass(frozen=True)
class Line:
    """목록 한 줄 — `5/22 (주)가 W…`.

    `firm` 은 **이미 가려진 값**이다. 원래 이름은 이 자료구조에 담지 않는다
    (`ir_monthly.Requester` 와 같은 규칙, 같은 까닭).
    """

    date: str       # `5/22` — 앞에 0 을 붙이지 않는다. 모르면 빈 문자열
    company: str    # 어느 기업 몫인지. 한 대표가 여러 기업이면 줄마다 갈린다
    firm: str       # 가려진 투자사명

    @property
    def text(self) -> str:
        # 날짜를 모르는 줄은 **날짜 자리를 비운다.** `?` 나 그 달 1일 같은 것을
        # 넣으면 없는 사실을 지어내는 것이고, 그 글은 대표에게 그대로 간다.
        return f"{self.date} {self.company} {self.firm}".strip() \
            if self.date else f"{self.company} {self.firm}"


@dataclass
class KakaoMessage:
    """카톡으로 나갈 글 한 통 전부."""

    month: str                  # `2026-07`
    companies: List[str]        # 이 글이 다루는 기업 이름(머리말 순서 그대로)
    lines: List[Line] = field(default_factory=list)
    text: str = ""              # 합친 전문. 화면이 보여 주고 사람이 복사하는 것
    parts: List[str] = field(default_factory=list)  # 나눠 보낼 순서. 한 통이면 빈다
    # 날짜를 모르는 줄 수. 조용히 다른 모양으로 나가면 아무도 모른다.
    undated: int = 0
    skipped: List[ir_monthly.Skip] = field(default_factory=list)
    skipped_count: int = 0

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def part_count(self) -> int:
        return len(self.parts) or 1


# ── 조각 ────────────────────────────────────────────────────────────────────

def month_label(month: str) -> str:
    """`2026-07` → `7월`. 앞에 0 을 붙이지 않는다 — 실물이 `7월 말까지` 다."""
    if not ir_monthly.is_month(month):
        return ""
    return f"{int(month[5:7])}월"


def day_label(date: str) -> str:
    """`2026-05-22` → `5/22`. 앞에 0 이 없다. 날짜가 아니면 빈 문자열.

    달만 적힌 기록(`2026-05`)도 빈 문자열이다 — 일(日)을 모르는데 `5/1` 로
    적으면 대표는 그날 요청이 온 줄로 읽는다.
    """
    bits = (date or "").split("-")
    if len(bits) < 3 or not (bits[1].isdigit() and bits[2][:2].isdigit()):
        return ""
    return f"{int(bits[1])}/{int(bits[2][:2])}"


def header(month: str, companies: Sequence[str]) -> str:
    """머리말 세 줄. 기업이 여럿이면 둘째 줄에 **다 적힌다**."""
    return "\n".join([
        HELLO,
        f"{month_label(month)} 말까지 {COMPANY_SEP.join(companies)}",
        LEAD,
    ])


def pack(head: str, lines: Sequence[str], limit: int = LIMIT) -> List[str]:
    """머리말 + 줄들을 **한 통에 들어가는 만큼씩** 담는다.

    ### 줄 수가 아니라 글자 수로 자른다

    누적이라 계약이 오래된 기업은 줄이 계속 는다. 자를 자리를 `20줄` 처럼
    줄 수로 정하면 기업명 길이에 따라 어떤 통은 넉넉하고 어떤 통은 넘친다 —
    한계는 글자 수라서, 세는 것도 글자 수여야 한다.

    ### 머리말은 **첫 통에만** 붙인다

    통마다 붙이면 같은 인사가 서너 번 온다. 이 저장소가 이미 그렇게 한다
    (`routers/deals._apply_test_room_to_parts`).
    """
    parts: List[str] = []
    cur, sep = head, "\n\n"     # 머리말과 첫 줄 사이에만 빈 줄
    for line in lines:
        if cur and len(cur) + len(sep) + len(line) > limit:
            parts.append(cur)
            cur, sep = line, "\n"
            continue
        cur, sep = (f"{cur}{sep}{line}" if cur else line), "\n"
    if cur:
        parts.append(cur)
    return parts


# ── 글 짓기 ─────────────────────────────────────────────────────────────────

def compose(db: Session, companies: Sequence[IrCompany],
            month: str) -> Optional[KakaoMessage]:
    """이 기업(들)에 대해 **그 달 말까지 쌓인** 요청을 글 한 통으로.

    요청이 **한 곳도 없으면 `None`** 이다. 빈 목록을 보내면 대표는 우리가
    아무것도 안 한 줄로 읽는다 — 문서 화면이 이미 그렇게 한다(#131).

    `companies` 를 **여럿 받는다.** 실물이 한 글에 두 기업을 담고 있었다.
    다만 지금 화면은 **한 기업씩** 부른다 — 한 대표가 여러 기업을 갖는지
    앱이 알 길이 없기 때문이다(`routers/startup.py` 의 설명). 묶는 근거가
    생기면 이 함수는 그대로 두고 부르는 쪽만 바꾸면 된다.
    """
    if not ir_monthly.is_month(month) or not companies:
        return None

    data = ir_monthly.monthly_requests(db, month, cumulative=True)
    names: Dict[int, str] = {c.id: (c.name or "").strip() for c in companies}

    lines: List[Line] = []
    for company in companies:
        for req in data.of(company.id):
            lines.append(Line(date=day_label(req.date),
                              company=names[company.id], firm=req.firm))
    if not lines:
        return None

    # 날짜 순. 날짜를 모르는 줄은 **맨 뒤**로 — 사이에 끼면 그 앞뒤 날짜
    # 사이에 온 것처럼 읽힌다.
    def order(line: Line):
        if not line.date:
            return (1, 0, 0, line.company, line.firm)
        m, d = line.date.split("/")
        return (0, int(m), int(d), line.company, line.firm)

    lines.sort(key=order)

    head = header(month, [names[c.id] for c in companies])
    parts = pack(head, [ln.text for ln in lines])
    return KakaoMessage(
        month=month,
        companies=[names[c.id] for c in companies],
        lines=lines,
        text="\n\n".join(parts),
        # 한 통이면 비운다 — `SendItem.parts_json` 과 같은 약속이다
        # ("비어 있으면 `message` 를 한 통으로 보낸다").
        parts=parts if len(parts) > 1 else [],
        undated=sum(1 for ln in lines if not ln.date),
        skipped=data.skipped,
        skipped_count=data.skipped_count,
    )


def for_company(db: Session, company_id: int,
                month: str) -> Optional[KakaoMessage]:
    """기업 하나짜리 글. 계약을 안 마친/없는 기업이면 `None`.

    계약 여부는 **여기서 다시 적지 않는다** — 문서와 같은 목록
    (`ir_monthly.contracted`)을 지난다. 두 곳이 갈리면 문서는 안 나가는데
    글은 나가는 기업이 생긴다.
    """
    company = next((c for c in ir_monthly.contracted(db) if c.id == company_id),
                   None)
    if company is None:
        return None
    return compose(db, [company], month)
