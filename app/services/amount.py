"""금액 칸 넷(`최근매출`·`누적투자금액`·`희망투자`·`Pre Value`)을 읽는 **한 곳**.

왜 글자로 저장하는가
--------------------
넷은 `Integer`(백만원)였다. 그래서 화면 입력이 `<input type="number">` 였고,
**정확히 모르는 금액을 적을 길이 없었다** — 실제로 사람이 적고 싶어 한 것은
`5-10억 사이` · `~` 같은 말이다. 숫자 하나로 뭉개면 사람이 적은 뜻이 사라지고,
뭉갠 숫자는 그대로 투자사에게 나간다.

그래서 **사람이 적은 글자를 그대로 저장한다.** 단위는 **억**이다 — 표도
`(억)` 이고 수정 창도 `단위: 억` 이라, 사람이 보는 단위와 저장하는 단위가
같아야 `5-10억` 을 적었을 때 곱하거나 나눌 자리가 생기지 않는다. 곱할 자리가
있으면 `5-10억` 같은 값에서 그 자리가 막히고, 막힌 자리를 우회하는 두 번째
길이 생긴다.

숫자로 쓰는 곳은 여섯이다. **뽑는 규칙은 이 파일 하나뿐이다.**
  1. 딜 소개 문구      `services/message_composer.py`
  2. 한줄소개          `services/one_liner.py`
  3. 소개 가능 판정    `models.py: IrCompany.introducible`
  4. LLM 자료 구간화   `services/llm_brief.py: amount_band`
  5. 엑셀 내보내기     `routers/data_io.py`
  6. 투자사 매칭 점수  `services/matcher.py`
여섯이 각자 해석하면 문구·LLM·엑셀 숫자가 갈린다. 갈린 숫자는 겉보기에
멀쩡해서 알아채기까지 오래 걸린다.

무엇까지 받아들이나
-------------------
사람이 아무 글자나 넣을 수 있게 되면 **그것이 그대로 투자사에게 나간다.**
그래서 문구에 실리는 모양을 둘로 못 박는다.

    단일    `5`  `5.6`  `1,200`  `5억`  `5억원`  `약 5억`   → `5.6`
    구간    `5-10`  `5~10억`  `5억~10억`  `5-10억 사이`      → `5~10`

이 둘 말고는 **문구에서 토막째 빠진다**(`10억 이상` 같은 한쪽만 열린 구간도
받지 않는다 — 문구 틀이 `누적투자금액 {}억` 이라 `10 이상억` 이 되고, 틀을
고치면 옛 문구가 같이 바뀐다). 빼는 편이 안전하다: 못 읽는 글자를 그대로
실어 보내는 쪽이 훨씬 나쁘다.

`~`(모름)과 `0`(없음)은 다르다
------------------------------
`0` 은 **아는 사실**이다 — 예전과 똑같이 문구에 `누적투자금액 0억` 으로 나가고,
LLM 자료에도 `"0"` 구간으로 실린다.
`~` 는 **모른다는 표시**다. 화면·엑셀에는 적은 그대로 남지만(빈 칸과 눈으로
구별된다 — 빈 칸은 '아직 안 봤다', `~` 는 '보고 왔는데 모른다'), 문구·LLM·
매칭에서는 값이 없는 것과 똑같이 다뤄진다. 없는 숫자를 지어낼 수 없기 때문이다.

소개 가능 판정에서는 **둘 다 세지 않는다.** `0` 을 안 세는 것은 예전 그대로다
(`introducible` 이 `v not in (None, 0)` 이었다) — 넷이 다 0 이면 '이름만
나열' 이라는 원래 근거가 그대로 서고, 여기서 규칙을 바꾸면 지금 쌓여 있는
줄들의 소개 가능 여부가 조용히 달라진다.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

#: 값을 모른다는 표시. 적어 두면 화면에 남고, 문구·LLM·매칭에서는 빈 칸과 같다.
#:
#: `-` 는 일부러 뺐다 — 표에서 빈 칸을 `-` 로 그려 둔 자리가 있어
#: (`static/js/inline_edit.js`) 같은 글자가 두 뜻을 갖는다. 못 읽는 값도
#: 결과는 모름과 같으므로(문구에서 빠진다) 잃는 것은 없다.
UNKNOWN_MARKS = ("~", "?", "미상", "모름", "확인중", "확인 중", "미정", "비공개")

#: 어떤 값인가. 화면이 딱지를 붙이는 데 쓴다.
EMPTY = "empty"            # 아직 안 적었다
NUMBER = "number"          # `5.6`
RANGE = "range"            # `5~10`
UNKNOWN = "unknown"        # `~` — 적었는데 모른다
UNREADABLE = "unreadable"  # 뭐라고 적었는지 숫자로 읽을 수 없다

# 숫자 한 덩이. 천 단위 쉼표(`1,200`)와 소수점을 받는다.
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"
# 단위 꼬리. 저장 단위가 이미 억이라 붙여도 안 붙여도 같은 뜻이다.
_UNIT = r"(?:\s*억\s*원?)?"
# 구간 구분자. 사람이 실제로 치는 것들이다(`-` 은 `~` 를 치려다 가장 흔히 나오는 글자).
_SEP = r"\s*(?:~|∼|-|–|—|부터)\s*"
# 앞뒤에 붙는 군말. 뜻을 바꾸지 않으므로 떼고 읽는다.
_HEAD = r"(?:약\s*)?"
_TAIL = r"(?:\s*(?:사이|정도|가량|쯤|수준))?"

_SINGLE_RE = re.compile(rf"^{_HEAD}({_NUM}){_UNIT}{_TAIL}$")
_RANGE_RE = re.compile(rf"^{_HEAD}({_NUM}){_UNIT}{_SEP}({_NUM}){_UNIT}{_TAIL}$")


def text(value) -> str:
    """저장값을 글자로. 아직 정수가 실려 오는 자리(옛 시험·시트)를 막지 않는다."""
    if value is None:
        return ""
    return str(value).strip()


def _digits(token: str) -> str:
    """`1,200` → `1200`. **적은 자릿수는 손대지 않는다** — 반올림은 여기서 안 한다.

    사람이 `5.25` 라고 적었으면 표에도 문구에도 `5.25` 로 나가야 한다.
    표와 문구가 다른 숫자를 보이는 것이 이 저장소가 가장 자주 겪은 고장이다.
    """
    return token.replace(",", "")


def state(value) -> str:
    """이 칸이 어떤 값인가 — `EMPTY`·`NUMBER`·`RANGE`·`UNKNOWN`·`UNREADABLE`."""
    raw = text(value)
    if not raw:
        return EMPTY
    if raw in UNKNOWN_MARKS:
        return UNKNOWN
    if _RANGE_RE.match(raw):
        return RANGE
    if _SINGLE_RE.match(raw):
        return NUMBER
    return UNREADABLE


def bounds(value) -> Optional[Tuple[Decimal, Decimal]]:
    """`(아래, 위)` — **억 단위**. 숫자로 못 읽으면 `None`.

    단일 값은 아래와 위가 같다. 구간을 거꾸로 적어도(`10-5`) 작은 쪽이 아래다 —
    적는 순서까지 사람에게 맡기면 같은 뜻이 두 결과를 낸다.
    """
    raw = text(value)
    if not raw or raw in UNKNOWN_MARKS:
        return None
    matched = _RANGE_RE.match(raw)
    if matched:
        try:
            low = Decimal(_digits(matched.group(1)))
            high = Decimal(_digits(matched.group(2)))
        except InvalidOperation:
            return None
        return (low, high) if low <= high else (high, low)
    matched = _SINGLE_RE.match(raw)
    if not matched:
        return None
    try:
        one = Decimal(_digits(matched.group(1)))
    except InvalidOperation:
        return None
    return (one, one)


def quantity(value) -> Optional[str]:
    """**문구·화면에 실을 수량 표기.** 못 읽으면 `None`(토막째 뺀다).

    돌려주는 글자는 단위(`억`)를 빼고 수만 담는다 — 부르는 쪽의 틀이
    `누적투자금액 {}억` · `{}억 투자유치중` · `Pre Value 약 {}억원` 이라
    단위를 여기서 붙이면 틀마다 두 번 붙는다.

        `5.6`        → `5.6`         → `누적투자금액 5.6억`
        `5-10억 사이` → `5~10`        → `누적투자금액 5~10억`
        `~`          → None          → 토막이 통째로 빠진다

    구분자를 `~` 하나로 맞추는 것은 **적은 뜻을 지키면서 모양만 고르는 일**이다.
    저장된 값은 사람이 친 그대로 남아 있고(표와 수정창이 그것을 보여준다),
    문구에 나갈 때만 한 모양으로 선다.
    """
    raw = text(value)
    if not raw or raw in UNKNOWN_MARKS:
        return None
    matched = _RANGE_RE.match(raw)
    if matched:
        low, high = _digits(matched.group(1)), _digits(matched.group(2))
        # 거꾸로 적은 구간은 바로 세운다(`bounds` 와 같은 판단이어야 한다).
        pair = bounds(raw)
        if pair is not None and Decimal(low) > Decimal(high):
            low, high = high, low
        return f"{low}~{high}"
    matched = _SINGLE_RE.match(raw)
    return _digits(matched.group(1)) if matched else None


def million(value) -> Optional[int]:
    """**백만원 정수 하나.** 구간이면 **아래**를 쓴다. 못 읽으면 `None`.

    ## 왜 아래인가

    금액을 크게 잡아 **실제보다 부풀려 소개하는 것**이 가장 나쁘다. 투자사는
    그 숫자를 보고 규모가 맞는다고 판단해 미팅까지 가고, 어긋난 것은 그 자리에서
    드러난다. 아래를 쓰면 "적어도 이만큼" 이라는 **적힌 사실**이고, 가운데를
    쓰면 아무도 적지 않은 숫자를 지어내는 것이다.

    이 저장소가 이미 같은 자리에서 같은 선택을 했다 —
    `services/sheet_import.py: parse_money_to_million` 이 `2억원~5억` 에서
    작은 쪽을 취하며 같은 근거를 적어 두었다. 두 곳이 다른 쪽을 고르면
    시트에서 들어온 값과 손으로 적은 값이 서로 다른 규모로 읽힌다.

    ## 구간 표(`llm_brief.AMOUNT_EDGES`)와의 관계

    경계는 1000·5000·10000 백만원(10억·50억·100억)이다. 아래를 쓰면 구간이
    한 칸 아래로 잡힐 수는 있어도 **위로 부풀지는 않는다** — 맞추는 쪽이
    규모를 과대평가하지 않는 방향이다.
    """
    pair = bounds(value)
    if pair is None:
        return None
    return int((pair[0] * 100).to_integral_value(rounding="ROUND_HALF_UP"))


def eok(value) -> Optional[Decimal]:
    """**억 단위 수 하나.** 구간이면 아래를 쓴다(`million` 과 같은 판단).

    억으로 견주는 자리(`services/matcher.py` 의 라운드 규모)가 여기를 쓴다 —
    거기서 `million() / 100` 을 하면 나누는 자리가 하나 더 생기고, 그 자리가
    곧 규칙이 갈리는 자리다.
    """
    pair = bounds(value)
    return None if pair is None else pair[0]


def from_million(value: Optional[int]) -> Optional[str]:
    """백만원 정수 → 저장 글자(억). `1830` → `"18.3"`. 비면 `None`.

    **옛 자료를 옮기는 규칙이자, 시트에서 읽어 넣는 규칙이다.** 소수 한 자리에서
    끊는 것은 화면·딜소개 문구·엑셀이 **예전부터 이미 그 자리에서 끊고 있었기**
    때문이다(`companies.eok` · `format_eok` · `data_io._eok`). 여기서 자릿수를
    더 살리면 옛 값이 화면에서 다른 글자로 보인다.

    끊이면서 잃는 것은 최대 5백만원이고, 구간 경계(10억·50억·100억)는 모두
    백만원 자리가 0 이라 **경계를 넘나들지 않는다.**
    """
    if value is None:
        return None
    eok = value / 100.0
    if eok == int(eok):
        return str(int(eok))
    return f"{eok:.1f}".rstrip("0").rstrip(".")


def is_countable(value) -> bool:
    """소개 가능 판정이 **숫자 하나로 셀 수 있는 값인가.**

    `0` 은 세지 않는다 — 예전 판정(`v not in (None, 0)`)을 그대로 옮긴 것이다.
    `~`·못 읽는 글자도 세지 않는다: 문구에 나가지 못하는 값은 '소개할 수 있다'
    는 근거가 될 수 없다(`introducible` 은 **실제 문구에 들어가는 것**만 본다).
    """
    number = million(value)
    return number is not None and number != 0
