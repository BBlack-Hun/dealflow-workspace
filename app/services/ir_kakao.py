"""`7월 말까지 … IR 자료 요청한투자사 리스트` — **카톡으로 나가는 글** 한 통.

## 왜 문서(#131) 옆에 글이 또 있나

#131 이 만든 것은 **인쇄용 문서 한 장**이다. 그런데 사용자가 실제로 대표에게
보내는 것은 문서가 아니라 **카톡 글**이었다. 실물을 받아 보니 모양이 다르다 —
표가 아니라 줄이고, 한 달치가 아니라 누적이고, 받는 창이 카톡이라 글자 수에
제약이 있다.

문서는 지우지 않는다(Windows 파일 첨부 시험에 쓰인다). **둘 다 남되 세는 자리와
가리는 자리는 하나씩**이다 — 이 파일은 `ir_monthly`(세기)와 `ir_mask`(가리기)를
부르기만 하고, 제 손으로 세지도 가리지도 않는다.

## 기업 리마인드 문구는 **이것 하나다**  ★

`startup_sms`(문구 화면의 **기업 리마인드 — 문자**)와 이 글은 **같은 뜻**이었다 —
둘 다 "IR 자료를 요청한 투자사가 있다, 미팅이 잡히면 연락드리겠다" 를 그 기업
대표에게 알리는 글이다. 그런데 짓는 자리가 둘이었다: 문구틀 쪽은 목록이 없는
옛 글을 냈고(사람이 손으로 목록을 붙였다), 이 파일은 목록을 붙인 글을 냈다.
같은 뜻의 문구가 둘이면 쓰는 사람은 어느 것을 보낼지 모르고, 언젠가 한쪽만
고쳐진다. **그래서 하나로 모았다 — 짓는 자리는 이 파일이다.**

`/setup` 의 시험 자리도, 스타트업 메뉴의 화면도 `compose()` 를 지난다.
`services/startup_msg.py` 는 **지웠다**(#133 이 냈던 파일이다). 남겨 두면
목록 없는 글을 만드는 길이 그대로 남아, 모은 뜻이 없어진다.

## 머리말은 문구틀, 목록은 코드  ★

**머리말 세 줄은 `startup_sms` 문구틀에서 온다** — 팀이 화면에서 고칠 수 있어야
할 문장이기 때문이다. **목록은 코드가 붙인다.** 목록까지 문구틀에 맡기지 않는
까닭은 셋이다.

1. **목록의 몸통이 통째로 자료다.** 줄마다 날짜·기업·투자사가 다르다.
   문구틀에 넣으면 편집자에게 주는 것은 거의 없고, **깨뜨릴 방법**은 하나
   생긴다 — 목록 자리를 지우면 대표에게 머리말만 있는 글이 나간다.
2. **`{기업목록}` 은 이미 다른 뜻이다.** `message_composer.render_template` 의
   그 자리는 투자사에게 보내는 "2번 기업 …" 이다(`deal_numbers` 가 붙인 번호).
   한 토큰이 화면마다 다른 것을 뜻하기 시작하면 문구를 고치는 사람이 무엇이
   나올지 알 수 없다. 그래서 머리말이 쓰는 자리는 **`{달}` · `{기업들}`** 로
   따로 냈다 — 이 문구에서만 쓰는 이름이다.
3. **가리기가 문구틀 밖에 있어야 한다.** 문구틀이 목록을 만들 수 있게 하면
   `{투자사}` 처럼 **안 가려진** 자리도 같은 글에 쓸 수 있게 된다. 가리는 것을
   문구를 고치는 사람 손에 맡기는 셈이라, 한 번 잘못 적히면 그대로 나간다.

### 문구틀이 비어 있으면 — **코드에 적힌 머리말로 짓는다**

#133 은 반대였다(문구틀이 비면 아무것도 안 만들었다). 여기서 그러면 스타트업
화면이 **404** 가 된다 — 요청이 실제로 와 있는 기업인데도 대표에게 보낼 글을
만들 길이 없어지고, 화면은 "요청이 없다" 는 뜻의 안내를 띄운다(있는데 없다고
말하는 거짓말이다). 그래서 `DEFAULT_HEAD` 로 짓되, **문구틀에서 온 것인지**를
`head_from_template` 에 실어 화면이 그 사실을 적게 한다.

## 실물의 띄어쓰기를 그대로 둔다

`요청한투자사` · `드릴예정 입니다` · 기업 사이의 ` , ` 는 사용자가 실제로 쓰는
글자 그대로다. 눈에 띈다고 여기서 고치면 **지금까지 대표들이 받아 온 글과 다른
글**이 나가기 시작하는데, 그 바뀜을 아무도 결정한 적이 없다. 고칠 일이면 사람이
고치는 것이지 옮겨 적는 코드가 할 일이 아니다.

## 발송이 붙었다 — **글을 짓는 자리는 그대로 여기 하나다**  ★

방 칸이 생기고(`IrCompany.kakao_room_name`, 0070) 보내는 자리가 딜 제안 관리에
섰다(`routers/startup_send.py`). 그때 이 파일에 더한 것은 **없다.**

발송 목록을 만드는 자리(`routers/deals.create_send_list`)가 `compose` 가 낸
`text` 와 `parts` 를 그대로 실어 나른다 — 미리 내 두었던 `parts` 가 그 자리에
그대로 쓰였고(`SendItem.parts_json`), 그래서 스타트업 화면이 보여 주는 글과
대표가 받는 글이 **글자 하나까지 같다.**

여기에 발송용 갈래를 하나라도 두면 그 순간 둘이 갈린다. 짓는 것은 여기,
보내는 것은 저기 — 그 선을 넘지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from ..models import IrCompany, User
from . import ir_monthly
from . import message_composer as mc
from . import template_pick

#: 이 문구의 종류. 화면 이름은 `기업 리마인드 — 문자`
#: (`routers/templates_crud.py: KINDS`). 머리말을 여기서 읽어 온다.
KIND = "startup_sms"

#: 머리말 첫 줄. 받는 사람이 대표라 이름을 부르지 않는다 —
#: 이름을 넣으려면 그 이름이 정말 대표인지 아는 칸이 있어야 한다(아래 참고).
HELLO = "안녕하세요 대표님"

#: 머리말 셋째 줄. **실물 그대로**다(위 머리말 참고).
LEAD = ("IR 자료 요청한투자사 리스트 입니다 "
        "미팅요청 투자사가 나오면 연락을 드릴예정 입니다.")

#: 머리말에서 기업을 잇는 글자. 실물이 `(주)가 , (주)나` 다.
COMPANY_SEP = " , "

#: 머리말이 쓰는 자리 둘. **자료라 코드가 채운다** — 사람이 고칠 문장이 아니다.
#: 이름을 `{기업목록}` 과 겹치지 않게 지은 까닭은 위 머리말에 있다.
MONTH_TOKEN = "{달}"
COMPANIES_TOKEN = "{기업들}"

#: 문구틀이 비어 있을 때 쓰는 머리말. **시드 문구와 같은 글**이다
#: (`scripts/bootstrap.py`) — 둘이 갈리면 문구틀을 지운 사람만 다른 글을 받는다.
DEFAULT_HEAD = "\n".join([
    HELLO,
    f"{MONTH_TOKEN} 말까지 {COMPANIES_TOKEN}",
    LEAD,
])

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
    # 머리말이 문구틀에서 왔나. 거짓이면 `DEFAULT_HEAD` 로 지은 것이고,
    # 화면은 **그 사실을 적어야 한다** — 코드에 적힌 글을 팀이 정한 문구로
    # 오해하면 문구틀은 빈 채로 남는다.
    head_from_template: bool = True
    # **보기 자료로 지은 글인가.** 참이면 `assemble` 이 맨 앞에 표시 줄
    # (`test_demo.MARK`)을 얹었다 — `/setup` 의 시험 자리에서 실을 것이 하나도
    # 없을 때만 참이 된다. 스타트업 화면은 이 값이 참인 글을 만들지 않는다.
    demo: bool = False

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


def head_body(db: Session, user: Optional[User]) -> tuple:
    """머리말의 **원문**과 그것이 문구틀에서 왔는지. `(글, 문구틀인가)`.

    무엇을 쓸지(고른 것 > 내 것 > 팀 것)는 `template_pick` 이 정한다 — 딜소개·
    딜 소싱과 같은 곳을 읽어야 같은 사람이 화면마다 다른 문구를 받지 않는다.

    비어 있으면 `DEFAULT_HEAD` 다. 막지 않는 까닭은 이 파일 머리말에 있다.
    """
    found = template_pick.pick(db, user.id, KIND) if user is not None else None
    body = ((found.body if found else "") or "").strip()
    return (body, True) if body else (DEFAULT_HEAD, False)


def contact_of(company: Optional[IrCompany]) -> mc.ContactView:
    """문구틀에 꽂을 상대 — **기업 쪽 연락 담당자**다.

    `title` 도 `firm` 도 주지 않는다. 스타트업 명단에는 직함 칸이 없고
    (`models.IrCompany` 에 성함·연락처·이메일뿐이다), 받는 쪽이 스타트업이라
    투자사도 없다. 빈 채로 두면 `render_template` 이 이미 정해 둔 길을 탄다 —
    `{직함}` 은 '님' 이 되고 `{투자사}` 는 빈칸이 된다. **'대표' 를 지어 넣지
    않는다**: 그 사람이 대표라고 말해 주는 칸이 없어서, 지어 넣으면 재무
    담당자에게 대표님이 나가고 자료가 없으니 시험에서도 안 드러난다.
    """
    return mc.ContactView(name=((company.contact_name if company else "") or "").strip())


def header(month: str, companies: Sequence[str], body: str = "",
           contact: Optional[mc.ContactView] = None) -> str:
    """머리말 세 줄. 기업이 여럿이면 둘째 줄에 **다 적힌다**.

    `body` 는 문구틀에서 온 원문이다(비면 `DEFAULT_HEAD`). 채우는 차례가 둘인
    까닭은 이렇다 — 먼저 **이 저장소가 이미 아는 자리**(`{담당자명}`·`{기업명}`
    …)를 `render_template` 이 채운다. 그래야 운영에 저장돼 있던 옛 문구에 적힌
    `{담당자명}` 이 **글자 그대로** 대표에게 나가지 않는다(이 저장소가 겪은
    사고다). 그 다음에 이 문구만 쓰는 `{달}`·`{기업들}` 을 채운다 —
    `render_template` 은 모르는 `{…}` 를 건드리지 않으므로 남아 있다.
    """
    joined = COMPANY_SEP.join(companies)
    text = mc.render_template((body or "").strip() or DEFAULT_HEAD,
                              contact or mc.ContactView(name=""),
                              company_name=joined)
    return (text.replace(MONTH_TOKEN, month_label(month))
                .replace(COMPANIES_TOKEN, joined)).strip()


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

def assemble(db: Session, user: Optional[User], month: str,
             companies: Sequence[str], lines: Sequence[Line],
             contact: Optional[mc.ContactView] = None,
             skipped: Optional[Sequence] = None, skipped_count: int = 0,
             prefix: str = "") -> KakaoMessage:
    """줄이 다 모인 뒤 — 머리말을 얹고 통을 나눠 **글 한 통으로 묶는다.**

    ## 왜 `compose` 에서 떼어 냈나

    보기 자료로 짓는 길(`services/test_demo.py`)이 **같은 조립을 지나야** 하기
    때문이다. 조립을 두 벌로 두면 시험 자리에서 본 모양과 대표가 받을 모양이
    갈린다 — 이 파일이 이미 그 값을 치렀다(머리말 참고). 다른 것은 **줄을 어디서
    얻느냐** 뿐이라, 갈리는 자리를 그 위로 올렸다.

    ## `prefix` — 맨 앞에 얹는 한 줄

    **진짜 자료로 지을 때는 비어 있다.** 앞에 한 줄이라도 얹으면 실제로 나갈
    모양을 볼 수 없다(`routers/setup.py` 의 "머리말을 붙이지 않는다").
    보기 자료로 지을 때만 채워지고, 그때 그 줄이 **가짜라는 표시**다 —
    시험방으로만 가더라도 진짜와 구별이 안 되면 사람이 헷갈린다.

    표시는 **머리말 앞**에 붙는다. 뒤가 아니라 앞인 까닭은 카톡에서 먼저 읽히는
    자리가 거기이고, 여러 통으로 나뉘어도 **첫 통**에 실리기 때문이다
    (`pack` 이 머리말을 첫 통에만 붙인다).
    """
    body, from_template = head_body(db, user)
    head = header(month, companies, body, contact)
    if prefix:
        head = f"{prefix}\n{head}"
    parts = pack(head, [ln.text for ln in lines])
    return KakaoMessage(
        month=month,
        companies=list(companies),
        lines=list(lines),
        text="\n\n".join(parts),
        # 한 통이면 비운다 — `SendItem.parts_json` 과 같은 약속이다
        # ("비어 있으면 `message` 를 한 통으로 보낸다").
        parts=parts if len(parts) > 1 else [],
        undated=sum(1 for ln in lines if not ln.date),
        skipped=list(skipped or []),
        skipped_count=skipped_count,
        head_from_template=from_template,
        demo=bool(prefix),
    )



def compose(db: Session, user: Optional[User], companies: Sequence[IrCompany],
            month: str) -> Optional[KakaoMessage]:
    """이 기업(들)에 대해 **그 달 말까지 쌓인** 요청을 글 한 통으로.

    **기업 리마인드 문구를 짓는 자리는 여기 하나다.** 스타트업 화면도
    `/setup` 의 시험 자리도 이 함수를 지난다 — 두 곳이 갈리면 시험에서 본 글과
    대표가 받는 글이 달라진다.

    `user` 는 **머리말 문구틀을 고르는 데만** 쓴다(고른 것 > 내 것 > 팀 것).
    `None` 이면 코드에 적힌 머리말로 짓는다.

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

    # 담당자 이름은 **첫 기업 것**이다. 기업이 여럿인 글은 한 대표에게 가는
    # 것이라(위 `compose` 설명) 상대가 하나뿐인데, 앱에는 그 한 사람을 가리키는
    # 칸이 없다. 지금 화면은 모두 기업 하나씩 부르므로 갈릴 일이 없다.
    return assemble(db, user, month, [names[c.id] for c in companies], lines,
                    contact_of(companies[0] if companies else None),
                    data.skipped, data.skipped_count)


def for_company(db: Session, user: Optional[User], company_id: int,
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
    return compose(db, user, [company], month)
