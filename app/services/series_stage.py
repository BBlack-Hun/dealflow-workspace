"""`투자라운드` 칸의 **일곱 단계** — 값을 맞추는 한 곳(과제 #162 · 11/05 팀 요청).

    Seed → Pre-A → Bridge → Series A → Series B → Series C → Pre-IPO

머리글이 `투자라운드` 인 칸 셋이 이 목록에서 고른다 — IR 기업 현황(`IrCompany.series`) ·
Series A 이상 딜 소싱(`SeriesACompany.series`) · 스타트업 명단(`notes.company_kind`).
머리글 이름은 그대로다.

## 들어오는 값은 여기서 맞춘다

표에서 고치기 · 수정창 · 시트 가져오기 · 기업 동기화 어느 길로 와도 `clean` 을 지난다
(두 표는 `models` 의 `@validates`, 스타트업 명단은 `routers/contacts._assign` · 시트
임포터). 옛 시트 값은 단계 이름 뒤 괄호에 기준을 적었다(`Angel, Seed (누적투자금 0,
년매출액 3억미만)`) — 괄호를 떼고 단계 말만 읽는다.

    Angel · 엔젤 · Pre-seed · 시드          → Seed
    Pre A · 프리A · Pre-Series A           → Pre-A
    `Pre A, Bridge`(옛 시트의 한 갈래)     → Pre-A   ← 앞 단계. Bridge 는 사람이 고른다
    브릿지                                 → Bridge
    series A · SeriesA · 시리즈A · A-1    → Series A (B · C 도 같다)
    Pre IPO · 프리IPO · Series D 이상      → Pre-IPO ← C 뒤 단계가 Pre-IPO 뿐이다

**못 읽는 값은 그대로 둔다** — 단계 말이 없는 값(`M&A` · `구주` · `상장`), 둘 이상을 가리키는
값(`Seed~Pre-A`), 단계 말 밖의 글이 붙은 값(`Pre IPO 전단계`). 억지로 고르면 틀린 단계가
딜 고르기에 그대로 쓰인다. 빈칸도 그대로다.

## 괄호 안 기준은 `CRITERIA` 로 옮겼다

`llm_brief.revenue_over` 가 그 괄호의 `년매출액 …` 을 읽어 왔다. 값을 단계 이름만으로
맞춘 뒤에도 같은 판정이 나오게 옛 시트 글을 단계마다 여기 둔다.
"""
from __future__ import annotations

import re
from typing import Optional

STAGES = ("Seed", "Pre-A", "Bridge", "Series A", "Series B", "Series C", "Pre-IPO")
#: 고르는 칸의 `data-choices` · `Column.choices` 꼴.
CHOICES = ",".join(STAGES)

#: 옛 시트가 단계 뒤 괄호에 적던 기준(그 글 그대로). Bridge 는 `Pre A, Bridge` 한 갈래였다.
CRITERIA = {
    "Seed": "누적투자금 0, 년매출액 3억미만",
    "Pre-A": "누적투자금 5억미만, 년매출액 10억이상",
    "Bridge": "누적투자금 5억미만, 년매출액 10억이상",
    "Series A": "누적투자금 10억이상, 년매출액 10억이상",
    "Series B": "누적투자금 20억 이상, 년매출액 50억이상",
    "Series C": "누적투자금 50억 이상, 년매출액 80억이상",
    "Pre-IPO": "누적투자금 80억이상 년매출액 80억이상",
}

# ASCII 글자 · 숫자가 바로 붙으면 다른 낱말이다(`Seeding` · `Pre Value`). 한글은 붙어도 된다
# (`Seed단계`) — `\b` 는 한글 앞에서 안 서서 못 쓴다(`invest_stage._TAIL` 과 같은 까닭).
_TAIL = r"(?![a-z0-9])"
_HEAD = r"(?<![a-z0-9])"
# 긴 것부터 찾고 찾은 자리는 지운다 — `Pre-seed` 를 먼저 안 지우면 `Seed` 가 또 걸린다.
_WORDS = (
    ("Pre-A", _HEAD + r"(?:pre|프리)\s*-?\s*(?:series|시리즈)\s*-?\s*a" + _TAIL),
    ("Pre-IPO", _HEAD + r"(?:pre|프리)\s*-?\s*ipo" + _TAIL),
    ("Seed", _HEAD + r"(?:pre\s*-?\s*seed|프리\s*-?\s*시드)" + _TAIL),
    ("Pre-A", _HEAD + r"(?:pre|프리)\s*-?\s*a" + _TAIL),
    ("@series", _HEAD + r"(?:series|시리즈)\s*-?\s*([a-z])(?:\s*-?\s*\d)?\+?" + _TAIL),
    ("Seed", _HEAD + r"(?:seed|angel)" + _TAIL + r"|시드|엔젤"),
    ("Bridge", _HEAD + r"bridge" + _TAIL + r"|브릿지|브리지"),
)
_SERIES = {"a": "Series A", "b": "Series B", "c": "Series C"}
# Series D 부터는 C 뒤 — 일곱 단계에서 C 뒤는 Pre-IPO 하나다.
_LATE = set("defg")
# 옛 시트의 괄호 기준(`(누적투자금 …, 년매출액 …)`). 다른 괄호(`(전단계)`)는 남겨 본다.
_CRITERIA_NOTE = re.compile(r"\([^()]*(?:누적|매출)[^()]*\)")
# 단계 말을 지우고 나서 남아도 되는 것 — 이것 말고 남으면 못 읽는 값이다.
_FILLER = re.compile(r"단계|라운드|round|stage|투자|[\s,./·&+~\-()\[\]]")
# `Series D 이상` 처럼 **맨 위 단계**에서만 받는 말(그 위가 없어 뜻이 안 갈린다).
_UPWARD = re.compile(r"이상|이후")


def stage_of(value: Optional[str]) -> Optional[str]:
    """값이 가리키는 단계 하나(`STAGES` 의 글자). 못 읽거나 빈칸이면 None."""
    text = (value or "").strip().lower()
    if not text:
        return None
    left = _CRITERIA_NOTE.sub(" ", text)
    found = set()
    for name, pattern in _WORDS:
        for hit in re.finditer(pattern, left):
            if name == "@series":
                letter = hit.group(1)
                if letter in _SERIES:
                    found.add(_SERIES[letter])
                elif letter in _LATE:
                    found.add("Pre-IPO")
                else:
                    return None          # `Series X` — 모르는 글자
            else:
                found.add(name)
        left = re.sub(pattern, " ", left)
    if found == {"Pre-A", "Bridge"}:
        found = {"Pre-A"}                # 옛 시트의 `Pre A, Bridge` 한 갈래 → 앞 단계
    if len(found) != 1:
        return None
    stage = found.pop()
    rest = _FILLER.sub("", left)
    if stage == "Pre-IPO":
        rest = _UPWARD.sub("", rest)
    return None if rest else stage


def clean(value):
    """저장할 값 — 읽히면 그 단계, 못 읽으면 **받은 그대로**(빈칸 · None 도 그대로)."""
    if not isinstance(value, str):
        return value
    return stage_of(value) or value


def same(a: Optional[str], b: Optional[str]) -> bool:
    """두 값이 같은 단계인가 — 못 읽는 값은 띄어쓰기만 맞춰 글자로 견준다."""
    def key(v):
        text = " ".join((v or "").split())
        return stage_of(text) or text
    return key(a) == key(b)
