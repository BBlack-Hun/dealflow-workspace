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

## 보고서 모양 — 제목 · 요약 · 구분선 · 맺음말  ★

사용자가 모양 몇 개를 보고 하나를 골랐다. 나가는 글은 이렇게 생겼다.

```
[01. 월간 IR 진행 현황]
CONTACTVC ASSET | 2026.09

안녕하세요 대표님
(주)샘플가 IR 자료 요청 현황을 보고드립니다.

■ 누적 12곳 · 9월 신규 3곳
────────────
09/02  케***파트너스  김*** 심사역
────────────
미팅 요청 투자사가 나오면 별도로 연락드리겠습니다.
```

**갈라 놓은 자리가 둘이다.** 사람이 고칠 **문장**은 문구틀에 있고
(제목 두 줄 · 인사 · 맺음말), **자료**는 코드가 짓는다(요약 숫자 · 목록 ·
구분선). 요약의 `12곳` 을 문구틀에 맡기면 사람이 손으로 적게 되고, 손으로 적은
숫자는 목록과 갈린다.

### 맺음말이 목록 **아래**로 내려갔다 — 문구틀에 `{목록}` 을 주지 않는다

맺음말은 이제 목록 뒤에 온다. 그렇다고 문구틀에 `{목록}` 같은 자리를 내주지는
않았다 — 그것은 아래 3번(**가리기가 문구틀 밖에 있어야 한다**)과 정면으로
어긋난다. 대신 **문구를 둘로 나눴다**: 머리말(`startup_sms`)과 맺음말
(`startup_sms_tail`). 문구틀은 여전히 **문장만** 갖고, 목록을 어디에 놓을지는
코드가 정한다. 문구를 고치는 사람에게 목록을 만들 방법은 **생기지 않았다.**

### 이미 저장돼 있던 옛 문구는 — 맺음말 줄을 **내려 준다**

운영 DB 의 `startup_sms` 에는 인사 + `{달} 말까지 {기업들}` + 맺음말이 한
덩어리로 들어 있다(`LEAD`). 그대로 두면 맺음말이 목록 위에 한 번, 아래에 또 한
번 적힌다. 그래서 **저장소가 시드로 내보냈던 그 문장과 글자까지 같을 때만**
머리말에서 떼어 목록 아래로 내린다(`split_lead`). 팀이 고쳐 쓴 문장은 건드리지
않는다 — 남의 문장을 코드가 짐작해서 옮기기 시작하면 무엇이 나갈지 아무도
모른다.

## 머리말은 문구틀, 목록은 코드  ★

**머리말 세 줄은 `startup_sms` 문구틀에서 온다** — 팀이 화면에서 고칠 수 있어야
할 문장이기 때문이다. **목록은 코드가 붙인다.** 목록까지 문구틀에 맡기지 않는
까닭은 셋이다.

1. **목록의 몸통이 통째로 자료다.** 줄마다 날짜·기업·투자사가 다르다.
   문구틀에 넣으면 편집자에게 주는 것은 거의 없고, **깨뜨릴 방법**은 하나
   생긴다 — 목록 자리를 지우면 대표에게 머리말만 있는 글이 나간다.
2. **`{기업목록}` 은 이미 다른 뜻이다.** `message_composer.render_template` 의
   그 자리는 투자사에게 보내는 "[기업2] …" 다(`deal_numbers` 가 붙인 번호).
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

#: **맺음말** 문구의 종류. 목록 아래에 오는 한 줄이다.
#: 종류를 따로 낸 까닭은 위 머리말에 있다(짧게: 목록 뒤에 오는 문장이라
#: 머리말과 같은 덩어리에 둘 수 없고, 그렇다고 문구틀에 목록 자리를 내줄 수는
#: 없다).
TAIL_KIND = "startup_sms_tail"

#: 머리말 첫 줄. 받는 사람이 대표라 이름을 부르지 않는다 —
#: 이름을 넣으려면 그 이름이 정말 대표인지 아는 칸이 있어야 한다(아래 참고).
HELLO = "안녕하세요 대표님"

#: **옛 문구틀의 맺음말 줄.** 실물 그대로다(띄어쓰기까지).
#:
#: 보고서 모양이 되면서 이 문장은 목록 **아래**로 내려갔다. 이미 저장돼 있는
#: 문구에서 이 줄을 알아보려고 남겨 둔다(`split_lead`) — 지우면 옛 문구를 쓰는
#: 팀에게 같은 말이 두 번 적힌 글이 나간다.
LEAD = ("IR 자료 요청한투자사 리스트 입니다 "
        "미팅요청 투자사가 나오면 연락을 드릴예정 입니다.")

#: 머리말에서 기업을 잇는 글자. 실물이 `(주)가 , (주)나` 다.
COMPANY_SEP = " , "

#: 머리말이 쓰는 자리 셋. **자료라 코드가 채운다** — 사람이 고칠 문장이 아니다.
#: 이름을 `{기업목록}` 과 겹치지 않게 지은 까닭은 위 머리말에 있다.
#: `{연월}` 은 제목 줄이 쓰는 `2026.09` 다(`{달}` 은 `9월` — 둘 다 남긴다:
#: 옛 문구가 `{달}` 을 쓰고 있어서 글자 그대로 나가면 안 된다).
MONTH_TOKEN = "{달}"
YEARMONTH_TOKEN = "{연월}"
COMPANIES_TOKEN = "{기업들}"

#: 목록의 위·아래 테두리. **짧게 잡는다** — 카톡은 글자폭도 화면 너비도
#: 기기마다 달라서, 길면 줄바꿈이 되어 모양이 되레 나빠진다.
RULE = "─" * 12

#: 요약 줄 앞의 표. 글머리 기호가 있어야 줄이 목록과 구별된다.
SUMMARY_MARK = "■"

#: 문구틀이 비어 있을 때 쓰는 머리말. **시드 문구와 같은 글**이다
#: (`scripts/bootstrap.py`) — 둘이 갈리면 문구틀을 지운 사람만 다른 글을 받는다.
#:
#: 제목 두 줄이 여기 있는 까닭: 제목은 **사람이 고칠 문장**이다(회사 이름이
#: 들어가고, `01.` 같은 번호도 팀이 정한다). 요약 숫자만 코드가 짓는다.
DEFAULT_HEAD = "\n".join([
    "[01. 월간 IR 진행 현황]",
    f"CONTACTVC ASSET | {YEARMONTH_TOKEN}",
    "",
    HELLO,
    f"{COMPANIES_TOKEN} IR 자료 요청 현황을 보고드립니다.",
])

#: 맺음말 문구가 비어 있을 때 쓰는 한 줄. 시드와 같은 글이다.
DEFAULT_TAIL = "미팅 요청 투자사가 나오면 별도로 연락드리겠습니다."

#: 한 통이 이보다 길면 나눈다. **새 숫자를 짓지 않는다** —
#: 이 저장소가 이미 카톡 한 통의 한계로 쓰는 값이다(`message_composer`).
LIMIT = mc.MESSAGE_WARN_CHARS


@dataclass(frozen=True)
class Line:
    """목록 한 줄 — `05/22  (주)가  W…  김*** 심사역`.

    `firm` 도 `person` 도 **이미 가려진 값**이다. 원래 이름은 이 자료구조에
    담지 않는다(`ir_monthly.Requester` 와 같은 규칙, 같은 까닭). 가리는 자리는
    `ir_mask` 하나이고, 이 파일은 **가려진 채로 받기만** 한다.

    `title`(직함)만 원문 그대로다 — 이름이 아니라서 가릴 것이 없다. 까닭은
    `ir_monthly.Requester` 에 한 번 적혀 있다.

    **기업 자리는 글 하나에 기업이 여럿일 때만 찬다.** 기업이 하나면 그 이름은
    이미 머리말에 있고, 줄마다 또 적으면 같은 말이 스무 번 되풀이된다
    (보고서 모양으로 바뀌면서 정한 것이다 — 위 머리말 참고). 여럿이면 **반드시
    남는다**: 안 적히면 어느 기업 몫인지가 글에서 사라진다.
    """

    date: str       # `05/22` — **두 자리**다(까닭은 `day_label`). 모르면 빈 문자열
    company: str    # 어느 기업 몫인지. **기업이 하나인 글에서는 빈 문자열**
    firm: str       # 가려진 투자사명
    person: str = ""   # 가려진 심사역 이름. 모르면 빈 문자열
    title: str = ""    # 직함 원문(`심사역`·`이사`). 모르면 빈 문자열

    @property
    def text(self) -> str:
        # **비어 있는 자리는 통째로 뺀다.** 빈 칸을 남기면 줄 가운데가 벌어지고,
        # `?` 나 `담당` 같은 말을 끼워 넣으면 없는 사실을 지어내는 것이다 —
        # 그 글은 대표에게 그대로 간다.
        #
        # 날짜가 그 규칙을 먼저 썼고(모르는 날짜 자리를 비운다), 직함도 같다:
        # 명단에 직함이 안 적힌 심사역은 **이름에서 줄이 끝난다.**
        #
        # ## 자리 사이는 **두 칸**, 이름과 직함 사이만 한 칸
        #
        # 사용자가 고른 모양이다(`09/02  케***파트너스  김*** 심사역`). 날짜를
        # 두 자리로 맞춘 것과 같은 뜻이다 — 자리가 자리로 보여야 대표가 훑어
        # 읽는다. 직함은 **그 사람의 말**이라 이름에 붙여 둔다: 두 칸으로
        # 떼어 놓으면 직함이 또 하나의 자리처럼 보인다.
        who = " ".join(bit for bit in (self.person, self.title) if bit)
        return "  ".join(bit for bit in (self.date, self.company, self.firm,
                                         who) if bit)


@dataclass
class KakaoMessage:
    """카톡으로 나갈 글 한 통 전부."""

    month: str                  # `2026-07`
    companies: List[str]        # 이 글이 다루는 기업 이름(머리말 순서 그대로)
    lines: List[Line] = field(default_factory=list)
    text: str = ""              # 합친 전문. 화면이 보여 주고 사람이 복사하는 것
    summary: str = ""           # 요약 줄(`■ 누적 …`). 화면이 그대로 보여 준다
    tail: str = ""              # 맺음말 — **목록 아래**에 붙은 한 줄
    parts: List[str] = field(default_factory=list)  # 나눠 보낼 순서. 한 통이면 빈다
    # 날짜를 모르는 줄 수. 조용히 다른 모양으로 나가면 아무도 모른다.
    undated: int = 0
    skipped: List[ir_monthly.Skip] = field(default_factory=list)
    skipped_count: int = 0
    # 머리말이 문구틀에서 왔나. 거짓이면 `DEFAULT_HEAD` 로 지은 것이고,
    # 화면은 **그 사실을 적어야 한다** — 코드에 적힌 글을 팀이 정한 문구로
    # 오해하면 문구틀은 빈 채로 남는다.
    head_from_template: bool = True
    # 맺음말이 문구틀에서 왔나. 거짓이면 코드에 적힌 것(`DEFAULT_TAIL`)이거나,
    # 옛 머리말에서 **내려온 줄**이다(`split_lead`).
    tail_from_template: bool = True
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


def ym_label(month: str) -> str:
    """`2026-07` → `2026.07`. 제목 줄의 오른쪽에 붙는다.

    여기는 **두 자리**다(`07`). 목록 줄의 날짜와 같은 까닭이고, 달마다 제목
    줄의 길이가 달라지지 않아야 해서다. 머리말 문장 안의 `7월`(`month_label`)
    과는 쓰는 자리가 다르다.
    """
    if not ir_monthly.is_month(month):
        return ""
    return f"{month[:4]}.{month[5:7]}"


def count_label(firms: int, people: int) -> str:
    """`3곳` · `12곳 15명` — **둘이 다를 때만** 둘 다 적는다.

    줄은 사람마다 하나씩 선다(`ir_monthly`). `12곳` 이라고만 적힌 글에 줄이 15개
    있으면 대표는 셈이 안 맞는다고 읽는다. 늘 둘 다 적으면 `3곳 3명` 처럼 같은
    말이 두 번 나오므로, 갈릴 때만 적는다.
    """
    return f"{firms}곳" if firms == people else f"{firms}곳 {people}명"


def summary_line(month: str, tally) -> str:
    """`■ 누적 12곳 15명 · 9월 신규 3곳` — **자료라 코드가 짓는다.**

    `신규` 는 그 달에 **처음** 물어본 것이다. 목록이 누적이라
    (`cumulative=True`) 이번 달에 무엇이 늘었는지가 따로 안 보이면, 대표는 지난
    달과 같은 글을 또 받은 줄로 읽는다.
    """
    if tally is None or not tally.people:
        return ""
    piled = count_label(tally.firms, tally.people)
    fresh = count_label(tally.new_firms, tally.new_people)
    return f"{SUMMARY_MARK} 누적 {piled} · {month_label(month)} 신규 {fresh}"


def day_label(date: str) -> str:
    """`2026-05-22` → `05/22`. **두 자리**다. 날짜가 아니면 빈 문자열.

    ## 왜 앞에 0 을 붙이나 — **바뀐 규칙이다**

    예전에는 `5/22` 였다(실물이 그랬다). 사용자가 **줄이 가지런히 서게** 두
    자리로 바꿔 달라고 정했다 — 날짜 자리의 글자 수가 줄마다 달라지면 그
    뒷자리(기업 · 투자사)가 줄마다 다른 데서 시작한다.

    **가지런해지는 데에는 한계가 있다.** 카톡 글꼴은 글자폭이 일정하지 않아서
    숫자를 두 자리로 맞춰도 완전히 줄이 맞지는 않는다. 그래도 `5/3` 과 `11/22`
    가 섞이던 때보다는 낫고, 이것이 이 자리에서 할 수 있는 전부다.

    `month_label` 의 `7월` 은 **그대로 둔다.** 저것은 머리말의 문장 안에 있는
    말이라 줄을 맞출 것이 없고, 실물이 `7월 말까지` 다.

    달만 적힌 기록(`2026-05`)은 빈 문자열이다 — 일(日)을 모르는데 `05/01` 로
    적으면 대표는 그날 요청이 온 줄로 읽는다.
    """
    bits = (date or "").split("-")
    if len(bits) < 3 or not (bits[1].isdigit() and bits[2][:2].isdigit()):
        return ""
    return f"{int(bits[1]):02d}/{int(bits[2][:2]):02d}"


def head_body(db: Session, user: Optional[User]) -> tuple:
    """머리말의 **원문**과 그것이 문구틀에서 왔는지. `(글, 문구틀인가)`.

    무엇을 쓸지(고른 것 > 내 것 > 팀 것)는 `template_pick` 이 정한다 — 딜소개·
    딜 소싱과 같은 곳을 읽어야 같은 사람이 화면마다 다른 문구를 받지 않는다.

    비어 있으면 `DEFAULT_HEAD` 다. 막지 않는 까닭은 이 파일 머리말에 있다.
    """
    found = template_pick.pick(db, user.id, KIND) if user is not None else None
    body = ((found.body if found else "") or "").strip()
    return (body, True) if body else (DEFAULT_HEAD, False)


def split_lead(body: str) -> tuple:
    """옛 머리말에서 **맺음말 줄을 떼어 낸다**. `(머리말, 떼어 낸 줄)`.

    보고서 모양이 되면서 맺음말은 목록 아래로 갔다. 그런데 운영 DB 에 저장된
    `startup_sms` 에는 그 문장이 머리말 셋째 줄로 들어 있다 — 그대로 두면 같은
    말이 목록 위에 한 번, 아래에 또 한 번 적힌다.

    **저장소가 시드로 내보냈던 문장(`LEAD`)과 글자까지 같을 때만** 뗀다. 팀이
    고쳐 쓴 문장은 건드리지 않는다: 남의 문장을 짐작해서 옮기기 시작하면 무엇이
    나갈지 아무도 모른다(고쳐 쓴 문구를 쓰는 팀은 맺음말이 위에 한 번 더 적힌
    글을 받는다 — 사람이 문구 화면에서 지우면 된다).
    """
    kept = [ln for ln in (body or "").splitlines() if ln.strip() != LEAD]
    moved = LEAD if len(kept) != len((body or "").splitlines()) else ""
    return "\n".join(kept).strip(), moved


def tail_body(db: Session, user: Optional[User], moved: str = "") -> tuple:
    """맺음말과 그것이 문구틀에서 왔는지. `(글, 문구틀인가)`.

    차례는 **문구틀 > 옛 머리말에서 내려온 줄 > 코드에 적힌 것**이다. 가운데가
    있는 까닭은 `split_lead` 에 있다.
    """
    found = template_pick.pick(db, user.id, TAIL_KIND) if user is not None else None
    body = ((found.body if found else "") or "").strip()
    if body:
        return body, True
    return (moved or DEFAULT_TAIL), False


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
    return (text.replace(YEARMONTH_TOKEN, ym_label(month))
                .replace(MONTH_TOKEN, month_label(month))
                .replace(COMPANIES_TOKEN, joined)).strip()


def pack(head: str, lines: Sequence[str], tail: str = "",
         limit: int = LIMIT) -> List[str]:
    """머리말 + 줄들 + 맺음말을 **한 통에 들어가는 만큼씩** 담는다.

    ### 줄 수가 아니라 글자 수로 자른다

    누적이라 계약이 오래된 기업은 줄이 계속 는다. 자를 자리를 `20줄` 처럼
    줄 수로 정하면 기업명 길이에 따라 어떤 통은 넉넉하고 어떤 통은 넘친다 —
    한계는 글자 수라서, 세는 것도 글자 수여야 한다.

    ### 머리말(제목 · 요약)은 **첫 통에만** 붙인다

    통마다 붙이면 같은 인사가 서너 번 온다. 시험 발송의 보기 표시 줄도 같은
    결로 첫 통에만 실린다(`assemble(prefix=...)`).

    ### 맺음말은 **마지막 통**에, 그리고 **잘리지 않는다**  ★

    맺음말은 목록 아래에 오는 문장이라 첫 통에 붙으면 글이 거기서 끝난 것처럼
    읽힌다. 마지막 통에 넣되 **들어갈 자리가 있는지 먼저 재고**, 없으면 맺음말만
    한 통으로 따로 보낸다 — 넘치는 채로 붙이면 카톡에서 뒤가 잘려 나가고, 잘린
    자리가 하필 마지막 문장이다.

    머리말과 첫 줄 사이의 빈 줄은 **머리말 쪽이 들고 있다**(요약 줄과 구분선이
    거기 붙어 있어, 목록은 구분선 바로 다음 줄에서 시작해야 한다).
    """
    parts: List[str] = []
    cur = head
    for line in lines:
        if cur and len(cur) + 1 + len(line) > limit:
            parts.append(cur)
            cur = line
            continue
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    if tail:
        if parts and len(parts[-1]) + 1 + len(tail) <= limit:
            parts[-1] = f"{parts[-1]}\n{tail}"
        else:
            parts.append(tail)
    return parts


# ── 글 짓기 ─────────────────────────────────────────────────────────────────

def tally_of(lines: Sequence[Line]) -> ir_monthly.Tally:
    """줄만 보고 센 요약 — **보기 자료용**이다.

    진짜 자료로 지을 때는 `ir_monthly` 가 센 값이 들어온다(`compose`). 저기서
    세는 까닭은 **가려진 이름으로는 곳 수를 셀 수 없기** 때문이다(`가***` 은
    여럿이다). 여기서는 지어낸 이름이 서로 다른 곳이라는 것을 아는 자리
    (`services/test_demo.py`)에서만 쓴다 — 그 글은 그 달 것만 짓는다.
    """
    firms = len({ln.firm for ln in lines})
    return ir_monthly.Tally(firms=firms, people=len(lines),
                            new_firms=firms, new_people=len(lines))


def assemble(db: Session, user: Optional[User], month: str,
             companies: Sequence[str], lines: Sequence[Line],
             contact: Optional[mc.ContactView] = None,
             skipped: Optional[Sequence] = None, skipped_count: int = 0,
             prefix: str = "",
             tally: Optional[ir_monthly.Tally] = None) -> KakaoMessage:
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
    (`pack` 이 머리말을 첫 통에만 붙인다). 보고서 모양이 되면서 맨 앞줄이
    **제목**이 됐지만, 표시는 여전히 그보다 앞이다 — 가짜라는 표시가 제목 아래로
    내려가면 먼저 읽히는 것이 제목이 된다.

    ## 쌓는 차례

    `제목·인사(문구틀)` → `요약(코드)` → `구분선` → `목록` → `구분선` →
    `맺음말(문구틀)`. 구분선을 목록의 앞뒤에 **줄로 끼워 넣는** 까닭은, 통이
    나뉠 때 그것이 목록과 같이 움직여야 하기 때문이다.
    """
    body, from_template = head_body(db, user)
    body, moved = split_lead(body)
    head = header(month, companies, body, contact)
    if prefix:
        head = f"{prefix}\n{head}"
    summary = summary_line(month, tally if tally is not None else tally_of(lines))
    tail, tail_from_template = tail_body(db, user, moved)
    block = "\n\n".join(bit for bit in (head, summary) if bit)
    parts = pack(f"{block}\n{RULE}", [ln.text for ln in lines] + [RULE], tail)
    return KakaoMessage(
        month=month,
        companies=list(companies),
        lines=list(lines),
        text="\n\n".join(parts),
        summary=summary,
        tail=tail,
        tail_from_template=tail_from_template,
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

    # 기업이 하나면 줄에서 기업명을 뺀다 — 그 이름은 이미 머리말에 있다.
    # 여럿이면 **반드시 적는다**: 섞인 목록에서 기업이 안 적히면 대표는 남의
    # 회사 요청까지 제 것으로 읽는다(`Line` 의 기업 자리 설명).
    single = len(companies) == 1

    lines: List[Line] = []
    for company in companies:
        for req in data.of(company.id):
            # `req` 가 내놓는 투자사명·심사역 이름은 **이미 가려져 있다**
            # (`ir_monthly.Requester`). 여기서 다시 가리지도, 원래 이름을
            # 다시 찾아오지도 않는다.
            lines.append(Line(date=day_label(req.date),
                              company="" if single else names[company.id],
                              firm=req.firm,
                              person=req.person, title=req.title))
    if not lines:
        return None

    # 날짜 순. 날짜를 모르는 줄은 **맨 뒤**로 — 사이에 끼면 그 앞뒤 날짜
    # 사이에 온 것처럼 읽힌다.
    def order(line: Line):
        # 같은 날 같은 기업이면 투자사 → 심사역 차례다. 심사역까지 보는 까닭은
        # 한 투자사에서 두 사람이 물어보면 그 두 줄의 차례가 돌릴 때마다
        # 달라지기 때문이다(줄 자체는 사람마다 하나씩 선다 — `ir_monthly` 가
        # **투자사가 아니라 사람**으로 묶는다).
        # 기업 자리는 기업이 하나인 글에서 비어 있다 — 그때는 모든 줄이 같은
        # 값이라 차례에 아무 영향이 없다.
        if not line.date:
            return (1, 0, 0, line.company, line.firm, line.person)
        # 두 자리로 찍힌 뒤에도 그대로다 — `int("05")` 는 5 다. 글자로 견주면
        # `11/2` 가 `5/3` 앞에 서므로 여기서는 반드시 숫자로 본다.
        m, d = line.date.split("/")
        return (0, int(m), int(d), line.company, line.firm, line.person)

    lines.sort(key=order)

    # 담당자 이름은 **첫 기업 것**이다. 기업이 여럿인 글은 한 대표에게 가는
    # 것이라(위 `compose` 설명) 상대가 하나뿐인데, 앱에는 그 한 사람을 가리키는
    # 칸이 없다. 지금 화면은 모두 기업 하나씩 부르므로 갈릴 일이 없다.
    # 요약 수는 **세는 자리에서** 받아 온다(`ir_monthly`) — 가려진 이름으로는
    # 곳 수를 셀 수 없다. 기업이 여럿이면 한 번에 묻는다: 한 투자사가 두 기업에
    # 물어봤어도 그것은 한 곳이라, 기업별로 세어 더하면 수가 부푼다.
    return assemble(db, user, month, [names[c.id] for c in companies], lines,
                    contact_of(companies[0] if companies else None),
                    data.skipped, data.skipped_count,
                    tally=data.tally_of(*(c.id for c in companies)))


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
