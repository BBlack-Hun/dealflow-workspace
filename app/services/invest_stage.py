"""`VcContact.stages` 에 **무엇이 들어가도 되는가** — 판정이 적힌 한 곳.

## 왜 이 칸이 비어 있었나

`stages`(화면 이름 `선호 투자단계`)는 **넣는 길이 없었다.** `sheet_import` 의
`ParsedContact` 에 이 칸이 아예 없었고, 명단을 넣는 세 갈래
(`scripts/import_investor_list.py` · `scripts/import_vc_sheets.py` ·
`services/sheet_import.apply_sheet_a`) 어느 것도 이 칸을 매핑하지 않았다.
시트에서 한 번도 들어온 적이 없어 운영 274줄이 전부 비어 있었다.

**그런데 값은 실제로 있다 — 옆 칸에 섞여서.** 시트 머리글이
`그룹/투자분야/라운드사이즈` 한 칸이라, 단계를 적을 자리가 화면에 없던 사람들이
`round_size` 에 함께 적어 왔다(`Series C 이상 6/30` · `Seed단계 위주로 보심`).

그리고 `stages` 는 **읽는 곳이 있다** — `matcher.evaluate_company` 가 기업의
`series` 와 견주어 `단계 불일치` 경고를 낸다. 비어 있는 동안 그 축이 통째로
죽어 있었다.

## 무엇을 하는가

    `Series C 이상 6/30`          → `SeriesC, Pre-IPO`       (`FILL`)
    `Seed~PreA(딥테크 초기기업)`   → `Seed, Pre-A`            (`FILL`)
    `Seed 단계 검토 어려움`        → **손대지 않는다**        (`NEGATED`)
    `초기 기업보다는 성장단계…`     → **손대지 않는다**        (`VAGUE`)
    `50억 이상`                   → 단계 말이 없다           (`NONE`)

## 넣는 꼴은 `matcher` 가 읽는 꼴이어야 한다

넣어도 판정에 안 걸리면 아무 일도 안 한 것이다. `matcher._split_csv` 가
`[,/|]` 로 쪼개고 `matcher._norm` 이 공백·하이픈을 지워 견준다. 그래서 여기서
내놓는 값은 **쉼표로 구분한 목록**이고, 낱말은 시트가 아니라 **앱의 표기**
(`Seed` · `SeriesA` · `Pre-IPO`)로 맞춘다 — `scripts/bootstrap.py` 의 예시값과
`docs/DATA_MODEL.md` 의 `Seed,SeriesA` 가 같은 표기다.

## 사다리로 편다

`Series C 이상` 은 C 한 칸이 아니라 **C 위로 전부**다. 한 칸만 넣으면
Pre-IPO 딜에 `단계 불일치` 가 잘못 뜬다 — 없던 경고를 새로 만드는 쪽이 비어
있던 것보다 나쁘다. 그래서 `이상`·`이후`·`~` 는 사다리 위쪽으로, `A~B` 꼴
범위는 두 칸 사이를 채워서 편다.

**넓히는 방향으로만 틀린다.** 넓게 잡으면 `판단 불가`(신호 없음)에 가까워지고,
좁게 잡으면 없던 `불일치` 경고가 생긴다. 둘 중 덜 해로운 쪽을 고른 것이다.

## 애매한 것은 건드리지 않는다

`초기` · `후기` · `성장단계` · `얼리스테이지` 는 단계를 가리키는 말이지만 어느
칸인지 사람마다 다르다(`초기` 가 Seed 인지 Pre-A 인지 시트에 적혀 있지 않다).
틀리게 넣으면 딜 고르기가 엉뚱한 단계로 걸러지므로 **세기만 하고 비워 둔다.**

**뜻이 뒤집힌 줄은 더 위험하다.** `IPO 부서라 Seed 단계 검토 어려움` 은 `Seed`
라는 낱말을 품고 있지만 뜻은 정반대다. 그대로 베끼면 Seed 딜에 `단계 일치` 가
떠서, 안 보겠다고 적어 둔 사람에게 그 딜이 권해진다 — 비어 있는 것보다 나쁘다.
그래서 **뒤집는 말이 한 번이라도 보이면 그 줄은 통째로 손대지 않는다.**
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

# ── 사다리 ──────────────────────────────────────────────────────────────────
#
# 낮은 것부터 높은 것으로. **차례가 곧 규칙이다** — `이상`·`~` 를 펴는 것도,
# 내놓는 값을 줄 세우는 것도 이 차례를 쓴다.
LADDER: Tuple[str, ...] = (
    "Pre-seed",
    "Seed",
    "Pre-A",
    "SeriesA",
    "SeriesB",
    "SeriesC",
    "Pre-IPO",
)
_RANK = {name: i for i, name in enumerate(LADDER)}

# `matcher._split_csv` 가 `[,/|]` 로 쪼갠다. 쉼표로 잇고 한 칸 띄운다 —
# 수정창 placeholder(`Seed, SeriesA — 쉼표로 구분`)와 같은 꼴이다.
JOIN = ", "

# ── 판정 ────────────────────────────────────────────────────────────────────
EMPTY = "empty"        # 볼 글이 없다
TAKEN = "taken"        # `stages` 에 이미 값이 있다 — 덮지 않는다
NONE = "none"          # 단계 말이 없다
VAGUE = "vague"        # `초기`·`후기` 같은 말만 있다 — 세기만 한다
NEGATED = "negated"    # 단계 말이 있으나 뜻이 뒤집혔다 — 손대지 않는다
FILL = "fill"          # 확실한 단계 말이다 — 넣는다

# 값이 없는 칸에서 `matcher` 가 볼 수 있는 결과만 낸다.
CHANGES = (FILL,)

# ── 확실한 단계 말 ──────────────────────────────────────────────────────────
#
# 표기가 제각각이다(대소문자 · 띄어쓰기 · `-` · 한글/영문). 실측 52줄에 있던
# 꼴을 전부 받는다:
#
#     Series C · Series C 이상 · series a~b · 시리즈 B-C · 시리즈 B 이후
#     Seed · Seed단계 · Seed~PreA · Pre-seed · Pre-seed ~ Pre-A
#     Pre IPO · Pre-IPO · PreIPO · pre-IPO단계 · PRE-IPO
#
# **뒤에 붙는 글자를 `\b` 로 막지 않는다.** `Seed단계` 처럼 한글이 바로 붙는
# 줄이 있는데, 한글도 낱말 글자라 `\b` 가 서지 않는다(실제로 그 줄을 놓쳤다).
# 대신 ASCII 글자·숫자만 막는다 — `Seeding` 은 걸리지 않고 `Seed단계` 는 걸린다.
_TAIL = r"(?![A-Za-z0-9])"

# 찾는 차례가 중요하다. **긴 것부터** 보고, 잡은 자리는 지워 둔다 —
# `Pre-seed` 를 먼저 안 잡으면 `Seed` 가 그 안에서 한 번 더 걸린다.
_PATTERNS: Sequence[Tuple[str, str]] = (
    # `Series A~B` · `시리즈 B-C` — 뒤쪽이 **글자 하나**다. 이것을 먼저 잡지
    # 않으면 `B` 가 홀로 남아 통째로 빠진다(`Series A~B` 가 A 만 들어갔다).
    ("@series-range", r"(?:series|시리즈)\s*-?\s*([A-Ca-c])\s*[~\-–—]\s*([A-Ca-c])" + _TAIL),
    ("Pre-IPO", r"(?:pre|프리)\s*-?\s*ipo" + _TAIL),
    ("Pre-seed", r"(?:pre\s*-?\s*seed|프리\s*-?\s*시드)" + _TAIL),
    ("@series", r"(?:series|시리즈)\s*-?\s*([A-Ca-c])" + _TAIL),
    # `PreA` · `Pre-A` · `Pre A` · `프리A`. **`Pre Value` 를 잡으면 안 된다** —
    # 실측에 `Pre Value 20-50억` 줄이 있다. 바로 뒤가 `A` 일 때만 선다.
    ("Pre-A", r"(?:pre|프리)\s*-?\s*a" + _TAIL),
    ("Seed", r"(?:seed|시드)" + _TAIL),
)

# 사다리 위쪽으로 편다. `Series C 이상` = C · Pre-IPO.
_UP = re.compile(r"이상|이후|부터|그\s*위|↑")
# 사다리 아래쪽으로 편다. 실측에는 없었지만 `이상` 과 한 짝이다.
#
# **`직전` 은 넣지 않는다.** `Pre-IPO 직전 레벨(시리즈B 혹은 C)` 줄이 있는데,
# 아래로 펴면 Pre-seed 까지 전부가 되어 사실상 아무 말도 안 한 값이 된다.
_DOWN = re.compile(r"이하|미만|까지")
# 낱말 둘 사이가 이것뿐이면 **범위**다(`Seed~PreA` · `Pre-seed ~ Pre-A`).
_BETWEEN = re.compile(r"^\s*(?:[~\-–—]|부터)\s*$")
# 마지막 낱말 뒤에 이것만 남으면 열린 범위다(`Series C ~`).
_TRAILING = re.compile(r"^\s*[~\-–—]\s*$")

# 단계를 가리키기는 하는데 **어느 칸인지 사람마다 다른** 말. 세기만 한다.
_VAGUE = re.compile(
    r"초기|후기|중기|성장\s*단계|성숙\s*단계|"
    r"얼리\s*스테이지|early\s*stage|late\s*stage|레이터\s*스테이지",
    re.IGNORECASE)

# 뜻을 뒤집는 말. 한 번이라도 보이면 그 줄은 통째로 손대지 않는다.
_NEGATIVE = re.compile(
    r"어려|힘들|불가|제외|아님|아닌|지양|미검토|안\s*봄|안\s*보|안\s*함|없음")

# 끝에 붙은 날짜(`6/30` · `7/7`). 시트에서 함께 넘어온 **적은 날**이라 단계와
# 상관이 없다. 떼고 보아야 `Series C ~` 같은 열린 범위를 알아볼 수 있다.
_TRAILING_DATE = re.compile(r"\s*\d{1,2}\s*/\s*\d{1,2}\s*$")


@dataclass(frozen=True)
class Decision:
    """이 줄의 `stages` 를 어떻게 할 것인가.

    `stages` 는 **새 값**이다. `FILL` 일 때만 글자가 들어 있고, 나머지 판정은
    전부 `None`(손대지 않는다)이다. `found` 는 글에서 실제로 읽어낸 낱말이라
    미리보기가 "무엇을 보고 그렇게 판정했나" 를 찍을 수 있다.
    """

    action: str
    stages: Optional[str] = None
    found: Tuple[str, ...] = ()

    @property
    def changes(self) -> bool:
        return self.action in CHANGES


def _strip_trailing_date(text: str) -> str:
    return _TRAILING_DATE.sub("", text)


def _series(letter: str) -> str:
    return "Series" + letter.upper()


def _span_tokens(text: str) -> List[Tuple[int, int, List[str]]]:
    """글에서 단계 낱말을 **자리와 함께** 뽑는다.

    잡은 자리는 공백으로 지워 두고 다음 무늬를 본다. 안 지우면 `Pre-seed` 가
    `Seed` 로 한 번 더 걸리고, `Series A~B` 가 `Series A` 로 또 걸린다.
    """
    left = text
    spans: List[Tuple[int, int, List[str]]] = []
    for name, pattern in _PATTERNS:
        for m in re.finditer(pattern, left, re.IGNORECASE):
            if name == "@series-range":
                lo, hi = _RANK[_series(m.group(1))], _RANK[_series(m.group(2))]
                names = list(LADDER[min(lo, hi):max(lo, hi) + 1])
            elif name == "@series":
                names = [_series(m.group(1))]
            else:
                names = [name]
            spans.append((m.start(), m.end(), names))
        left = re.sub(pattern, lambda m: " " * (m.end() - m.start()), left,
                      flags=re.IGNORECASE)
    return sorted(spans)


def stages_of(text: Optional[str]) -> List[str]:
    """글에서 읽어낸 **확실한** 단계 목록. 사다리 차례로 줄 세워 돌려준다.

    범위를 펴는 자리가 셋이다:

      ① 낱말 둘 사이가 `~`·`-` 뿐이면 그 사이를 채운다(`Seed~PreA`).
      ② 마지막 낱말 뒤에 `~` 만 남으면 위로 연다(`Series C ~`).
      ③ `이상`·`이후` 가 있으면 가장 높은 낱말 위로 연다(`Series C 이상`).
         `이하`·`미만` 은 가장 낮은 낱말 아래로 연다.
    """
    body = _strip_trailing_date((text or "").strip())
    spans = _span_tokens(body)
    if not spans:
        return []

    picked = {name for _s, _e, names in spans for name in names}

    # ① 낱말 사이의 범위
    for (_s1, e1, left), (s2, _e2, right) in zip(spans, spans[1:]):
        if _BETWEEN.match(body[e1:s2]):
            lo = min(_RANK[n] for n in left)
            hi = max(_RANK[n] for n in right)
            picked.update(LADDER[min(lo, hi):max(lo, hi) + 1])

    ranks = {_RANK[n] for n in picked}
    # ② 끝에 매달린 `~`
    if _TRAILING.match(body[spans[-1][1]:]):
        picked.update(LADDER[max(ranks):])
        ranks = {_RANK[n] for n in picked}
    # ③ `이상` · `이하`
    if _UP.search(body):
        picked.update(LADDER[max(ranks):])
    if _DOWN.search(body):
        picked.update(LADDER[:min(ranks) + 1])

    return sorted(picked, key=_RANK.__getitem__)


def decide(round_size: Optional[str], stages: Optional[str] = None) -> Decision:
    """`round_size` 에 섞인 단계 말을 `stages` 로 옮길 것인가.

    **시트를 넣는 쪽과 정리 스크립트가 함께 부른다.** 규칙을 두 군데 적으면
    한쪽이 낡고, 그러면 여기서 정리해 둔 것을 다음 업로드가 되돌린다
    (`services/group_name` 이 같은 이유로 판정을 한 곳에 모았다).

    차례가 곧 규칙이다:

      ① 볼 글이 없으면 아무 일도 하지 않는다.
      ② `stages` 에 이미 값이 있으면 **덮지 않는다** — 사람이 손으로 고쳐 둔
         값을 오래된 시트가 밀어내면 안 된다(옆 칸들과 같은 규칙이다).
      ③ 뜻을 뒤집는 말이 보이면 손대지 않는다. ④ 보다 **앞**이어야 한다 —
         `Seed 단계 검토 어려움` 은 `Seed` 를 품고 있다.
      ④ 확실한 낱말을 읽어내면 넣는다.
      ⑤ `초기`·`후기` 뿐이면 세기만 한다.
    """
    text = (round_size or "").strip()
    if not text:
        return Decision(EMPTY)
    if (stages or "").strip():
        return Decision(TAKEN)

    found = stages_of(text)
    vague = bool(_VAGUE.search(text))
    if not found and not vague:
        return Decision(NONE)
    if _NEGATIVE.search(text):
        return Decision(NEGATED, found=tuple(found))
    if not found:
        return Decision(VAGUE)
    return Decision(FILL, stages=JOIN.join(found), found=tuple(found))
