"""금액 칸 넷(`최근매출`·`누적투자금액`·`희망투자`·`Pre Value`)을 읽는 **한 곳**.

왜 글자로 저장하는가
--------------------
넷은 `Integer`(백만원)였다. 그래서 화면 입력이 `<input type="number">` 였고,
**정확히 모르는 금액을 적을 길이 없었다** — 실제로 사람이 적고 싶어 한 것은
`5-10억 사이` · `~` 같은 말이다. 숫자 하나로 뭉개면 사람이 적은 뜻이 사라지고,
뭉갠 숫자는 그대로 투자사에게 나간다.

그래서 **사람이 적은 글자를 그대로 저장한다.** 기본 단위는 **억**이다 — 표
머리글도 수정 창(`단위: 억`)도 엑셀 머리글(`누적투자(억)`)도 억이라, 사람이 보는
단위와 저장하는 단위가 같아야 `5-10억` 을 적었을 때 곱하거나 나눌 자리가 생기지
않는다. 곱할 자리가 있으면 `5-10억` 같은 값에서 그 자리가 막히고, 막힌 자리를
우회하는 두 번째 길이 생긴다.

**1억 미만은 억으로 안 읽힌다.** `0.47억` 이라고 적어 두면 사람이 매번 억을
만원으로 되돌려 읽어야 한다. 그래서 `4700만원` · `5천만원` 처럼 **작은 단위를
붙여 적을 수 있다**(사용자 요청). 단위는 글자에 그대로 남고, 숫자로 옮기는 일은
여기 한 곳이 한다.

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

    단일  `5`  `5.6`  `1,200`  `5억`  `5억원`  `약 5억`      → `5.6억`
          `5천만원`  `5천만`  `4700만원`  `5,000만원`       → `5천만원`
    구간  `5-10`  `5~10억`  `5억~10억`  `5-10억 사이`       → `5~10억`
          `3천만원~1억`                                     → `3천만원~1억`

받아들이는 단위는 **억 · 억원 · 천만원 · 천만 · 만원 · 만** 여섯뿐이다.

  · **`백만원` 은 안 받는다.** 옛 저장 단위가 백만원이었어서, 그 낱말을 여기서
    다시 받으면 "이 칸은 백만원이었지" 하는 기억과 섞인다. 시트에서 들어오는
    `1,224백만원` 은 가져오기가 억으로 옮겨 담는다(`sheet_import`).
  · **`5천` 은 안 받는다.** `5천만원` 인지 `5천원` 인지 글자만으로는 못 가른다.
    애매한 것을 짐작해 읽으면 그 짐작이 그대로 투자사에게 나간다.
  · **단위 없는 맨숫자는 언제나 억이다.** 이 칸이 예전부터 억이었고(입력창이
    억이었다) 규칙이 둘이 되는 순간 `18.3` 과 `50000000` 이 서로 다른 단위가 된다.

이 밖에는 **문구에서 토막째 빠진다**(`10억 이상` 같은 한쪽만 열린 구간도 받지
않는다). 빼는 편이 안전하다: 못 읽는 글자를 그대로 실어 보내는 쪽이 훨씬 나쁘다.
표에는 `⚠ 문구에서 빠짐` 딱지가 붙어, 조용히 빠지는 일이 없다.

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
NUMBER = "number"          # `5.6` · `5천만원`
RANGE = "range"            # `5~10억` · `3천만원~1억`
UNKNOWN = "unknown"        # `~` — 적었는데 모른다
UNREADABLE = "unreadable"  # 뭐라고 적었는지 숫자로 읽을 수 없다

#: 단위 → **억으로 옮기는 배수.** 긴 것부터 적는다 — `천만원` 이 `만원` 을
#: 품고 있어서, 짧은 것이 앞에 서면 `5천만원` 의 `천`이 숫자 밖으로 떨어진다.
#:
#: **여기 말고 다른 데 적지 마라.** 아래 정규식도 이 표에서 만들어진다.
UNITS = (
    ("억원", Decimal(1)),
    ("억", Decimal(1)),
    ("천만원", Decimal("0.1")),
    ("천만", Decimal("0.1")),
    ("만원", Decimal("0.0001")),
    ("만", Decimal("0.0001")),
)

#: 단위를 안 적었을 때의 뜻. 이 칸의 기본 단위다.
DEFAULT_UNIT = "억"

#: **문구에 실을 때 쓰는 한 가지 모양.** 같은 단위를 사람마다 다르게 적어서
#: (`억`/`억원` · `천만`/`천만원`) 그대로 두면 `2억원~5억` 처럼 한 줄 안에서
#: 같은 단위가 두 글자로 나온다.
#:
#: 구분자를 `~` 하나로 맞추는 것과 같은 일이다 — **저장된 값은 사람이 친 그대로**
#: 남아 있고(표와 수정창이 그것을 보여준다) 문구에 나갈 때만 한 모양으로 선다.
#: `천만`·`만` 에 `원` 을 붙이는 쪽으로 고른 것은 `누적투자금액 5천만` 이
#: 말이 안 되기 때문이다.
UNIT_SHOWN = {"억": "억", "억원": "억",
              "천만": "천만원", "천만원": "천만원",
              "만": "만원", "만원": "만원"}

# 숫자 한 덩이. 천 단위 쉼표(`1,200`)와 소수점을 받는다.
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"
# 단위 한 덩이. `UNITS` 에 적힌 차례 그대로라 긴 것이 먼저 걸린다.
_UNIT = "|".join(name for name, _scale in UNITS)
# 숫자 + 단위. 구간은 **양쪽을 따로** 읽는다 — `3천만원~1억` 처럼 단위가 섞여도
# 각자의 뜻이 남아야 한다.
_SIDE = rf"({_NUM})\s*({_UNIT})?"
# 구간 구분자. 사람이 실제로 치는 것들이다(`-` 은 `~` 를 치려다 가장 흔히 나오는 글자).
_SEP = r"\s*(?:~|∼|-|–|—|부터)\s*"
# 앞뒤에 붙는 군말. 뜻을 바꾸지 않으므로 떼고 읽는다.
_HEAD = r"(?:약\s*)?"
_TAIL = r"(?:\s*(?:사이|정도|가량|쯤|수준))?"

_SINGLE_RE = re.compile(rf"^{_HEAD}{_SIDE}{_TAIL}$")
_RANGE_RE = re.compile(rf"^{_HEAD}{_SIDE}{_SEP}{_SIDE}{_TAIL}$")

_SCALE = dict(UNITS)


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


def _side(number: str, unit: Optional[str]) -> Optional[Tuple[Decimal, str, str]]:
    """구간 한쪽 → `(억 값, 적힌 숫자, 단위)`. 못 읽으면 `None`."""
    try:
        written = _digits(number)
        name = unit or DEFAULT_UNIT
        return Decimal(written) * _SCALE[name], written, UNIT_SHOWN[name]
    except (InvalidOperation, KeyError):
        return None


def _sides(value) -> Optional[Tuple[tuple, tuple]]:
    """`(아래쪽, 위쪽)` 두 토막. 단일 값은 같은 토막이 둘이다.

    **거꾸로 적어도(`10-5`) 작은 쪽이 아래다** — 적는 순서까지 사람에게 맡기면
    같은 뜻이 두 결과를 낸다.
    """
    raw = text(value)
    if not raw or raw in UNKNOWN_MARKS:
        return None
    matched = _RANGE_RE.match(raw)
    if matched:
        low = _side(matched.group(1), matched.group(2))
        high = _side(matched.group(3), matched.group(4))
        if low is None or high is None:
            return None
        return (low, high) if low[0] <= high[0] else (high, low)
    matched = _SINGLE_RE.match(raw)
    if not matched:
        return None
    one = _side(matched.group(1), matched.group(2))
    return None if one is None else (one, one)


def state(value) -> str:
    """이 칸이 어떤 값인가 — `EMPTY`·`NUMBER`·`RANGE`·`UNKNOWN`·`UNREADABLE`."""
    raw = text(value)
    if not raw:
        return EMPTY
    if raw in UNKNOWN_MARKS:
        return UNKNOWN
    if _sides(raw) is None:
        return UNREADABLE
    return RANGE if _RANGE_RE.match(raw) else NUMBER


def bounds(value) -> Optional[Tuple[Decimal, Decimal]]:
    """`(아래, 위)` — **억 단위**. 숫자로 못 읽으면 `None`.

    단일 값은 아래와 위가 같다. `5천만원` 은 `(0.5, 0.5)` 다 — 단위가 무엇이든
    여기서는 억 하나로 선다. **단위를 아는 것은 이 파일뿐이다.**
    """
    pair = _sides(value)
    return None if pair is None else (pair[0][0], pair[1][0])


def phrase(value) -> Optional[str]:
    """**문구·화면에 실을 금액 표기.** 못 읽으면 `None`(토막째 뺀다).

    **단위까지 붙여 돌려준다.** 예전에는 수량만 주고 부르는 쪽이 `억` 을 붙였는데
    (`누적투자금액 {}억`), 그러면 `5천만원` 을 적은 순간 `5천만원억` 이 된다.
    단위를 아는 곳은 여기 하나여야 한다.

        `5.6`         → `5.6억`      → `누적투자금액 5.6억`
        `5천만원`      → `5천만원`    → `누적투자금액 5천만원`
        `5-10억 사이`  → `5~10억`     → `누적투자금액 5~10억`
        `3천만원~1억`  → `3천만원~1억` → `누적투자금액 3천만원~1억`
        `~`           → None        → 토막이 통째로 빠진다

    **적은 단위를 바꾸지 않는다.** `5천만원` 을 `0.5억` 으로 고쳐 내보내면 사람이
    굳이 그렇게 적은 뜻이 사라지고, `누적투자금액 0.5억` 은 투자사가 실제로 쓰는
    말도 아니다. 구분자만 `~` 한 가지로 맞춘다 — 저장된 값은 사람이 친 그대로
    남아 있고(표와 수정창이 그것을 보여준다) 문구에 나갈 때만 한 모양으로 선다.

    양쪽 단위가 같은 구간은 단위를 **한 번만** 적는다(`5~10억`). 사람이 쓰는
    모양이 그것이고, `5억~10억` 은 같은 말을 두 번 하는 셈이다.
    """
    pair = _sides(value)
    if pair is None:
        return None
    (_low_value, low_number, low_unit), (_high_value, high_number, high_unit) = pair
    if low_number == high_number and low_unit == high_unit and not _is_range(value):
        return f"{low_number}{low_unit}"
    if low_unit == high_unit:
        return f"{low_number}~{high_number}{low_unit}"
    return f"{low_number}{low_unit}~{high_number}{high_unit}"


def _is_range(value) -> bool:
    raw = text(value)
    return bool(raw) and raw not in UNKNOWN_MARKS and bool(_RANGE_RE.match(raw))


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

    억으로 견주는 자리(`services/matcher.py` 의 라운드 규모)와 엑셀이 여기를
    쓴다 — 거기서 `million() / 100` 을 하면 나누는 자리가 하나 더 생기고,
    그 자리가 곧 규칙이 갈리는 자리다.
    """
    pair = bounds(value)
    return None if pair is None else pair[0]


def _one_decimal(value: int) -> str:
    """**옛 화면이 쓰던 계산 그대로.** 백만원 정수 → 억, 소수 한 자리에서 끊는다.

    `format_eok` · `companies.eok` · `data_io._eok` 셋이 이 계산을 하고 있었다.
    옛 값을 옮길 때 "지금 화면에 뜨는 글자" 가 무엇인지 알아야 해서 남겨 둔다.
    """
    amount = value / 100.0
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:.1f}".rstrip("0").rstrip(".")


def from_million(value: Optional[int]) -> Optional[str]:
    """백만원 정수 → 저장 글자. **한 줄도 잃지 않는다.**

    옛 자료를 옮기는 규칙이자(0074), 시트에서 읽어 넣는 규칙이다.

    ## 왜 그냥 반올림하면 안 되나

    처음에는 옛 화면 계산 그대로(`_one_decimal`) 옮겼다. 화면 글자가 한 글자도
    안 바뀌는 대신 **저장값이 조금 달라진다.** 운영 자료로 재 보니 값이 든 262칸
    중 10칸이 그랬고, 그중 하나가 이랬다:

        raise_target  1(백만원)  →  `"0"`     ← 값이 통째로 사라진다

    `1백만원` 이 `0`(= 없음)이 되는 것은 반올림이 아니라 **다른 사실로 바뀌는
    것**이다. 화면 글자를 지키자고 값을 잃을 수는 없다.

    ## 그래서 어떻게 적나

    1. 억으로 적어 **잃는 것이 없으면 억으로.** 옛 화면에 뜨던 글자 그대로다
       (`560 → "5.6"` · `21000 → "210"` · `50 → "0.5"`). 262칸 중 252칸이 이쪽이라
       **화면이 안 바뀐다.**
    2. 잃는데 **1억 미만이면 만원으로**(`47 → "4700만원"` · `1 → "100만원"`).
       `0.47억` 이라고 적어 두면 사람이 매번 억을 만원으로 되돌려 읽어야 하고,
       문구에 `누적투자금액 0.47억` 이 나간다 — 투자사가 쓰는 말이 아니다.
    3. 잃는데 **1억 이상이면 억을 끊지 않고**(`318 → "3.18"` · `1224 → "12.24"`).
       억 단위에서 소수 둘째 자리는 그대로 읽힌다. `31800만원` 이 오히려 어렵다.

    잃는지 아닌지는 **`million()` 에게 되물어** 판단한다. 여기서 `% 10` 같은
    조건을 따로 적으면 읽는 규칙과 쓰는 규칙이 갈릴 자리가 하나 더 생긴다.
    """
    if value is None:
        return None
    if value == 0:
        # `0만원` 은 이상하다. `0` 은 어느 단위에서도 0 이다.
        return "0"
    kept = _one_decimal(value)
    if million(kept) == value:
        return kept
    if value < 100:
        return f"{value * 100}만원"
    return format((Decimal(value) / 100).normalize(), "f")


def is_countable(value) -> bool:
    """소개 가능 판정이 **숫자 하나로 셀 수 있는 값인가.**

    `0` 은 세지 않는다 — 예전 판정(`v not in (None, 0)`)을 그대로 옮긴 것이다.
    `~`·못 읽는 글자도 세지 않는다: 문구에 나가지 못하는 값은 '소개할 수 있다'
    는 근거가 될 수 없다(`introducible` 은 **실제 문구에 들어가는 것**만 본다).
    """
    number = million(value)
    return number is not None and number != 0
