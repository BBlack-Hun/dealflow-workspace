"""딜소개 칸에 적힌 **기업 이름을 쪼개는 규칙 한 곳**.

시트의 `1차 딜소개` 칸은 사람이 손으로 적는 칸이라 한 칸 안에 회차가 쌓이고,
회차 한 줄 안에 **날짜 · 꼬리말 · 기업 여럿**이 함께 들어 있다. 실제 칸 값을
세어 보면 줄의 모양이 이렇다(1,988줄 기준).

    1,365줄   `9/2 샘플가, 샘플나, …`          날짜가 맨 앞
      453줄   `[8/5] [핵심 딜 공유]`           **날짜에 대괄호**가 씌워져 있다
      165줄   날짜 없는 줄(앞 회차에서 이어지는 기업 목록 또는 메모)
        5줄   그 밖(날짜가 줄 가운데)

옛 규칙은 대괄호 씌운 날짜를 **날짜로 못 읽었다.** 그래서 그 줄이 앞 회차에
통째로 이어 붙고, 쉼표로만 쪼개니 `앞기업 [8/12] 뒷기업` 같은 **덩어리 하나**가
기업 이름으로 남았다. 이름이 뭉치면 `deal_history._key` 로 맞출 수가 없고,
앱은 그 기업들을 **"소개한 적 없음"** 으로 본다.

## 왜 이 파일 하나인가

쪼개는 규칙이 두 벌이면 **앞으로 들어오는 것과 이미 들어와 있는 것이 다르게
쪼개진다.** 시트를 읽는 쪽(`services/sheet_import`)과 이미 들어와 있는 줄을 다시
쪼개는 쪽(`scripts/resplit_deal_companies.py`)이 **같은 이 함수**를 부른다 —
`services/group_name.decide()` 를 임포트와 정리 스크립트가 함께 쓰는 것과 같은
자리다.

## 부분일치로 기업을 찾지 않는다

`가나` 같은 두 글자 이름은 `가나다라전자` 한가운데에 **우연히 박힌다.** 그래서
여기서 하는 일은 **구분자로 쪼개는 것**뿐이고, 쪼갠 조각을 기업 목록과 맞추는
일은 `deal_history._key` 가 **글자 그대로** 한다. 이 파일은 기업 목록을 읽지
않는다 — 목록을 보면서 쪼개기 시작하면 그 순간 부분일치가 된다.

## 날짜는 떼되 **버리지 않는다**

이름에서 뗀 날짜는 `Split.dates` · `Chunk.month/day` 로 그대로 돌려준다.
`happened_at` 이 비어 있는 줄이 있고, 그 줄에서는 이 조각이 **날짜가 남아 있는
유일한 자리**다. 떼어서 흘리면 그 회차는 언제 일인지 영영 알 수 없다.

## 꼬리말은 실제 기업 목록과 대조해서 골랐다

`전달` · `공유` · `카톡딜` 같은 말은 회차에 붙는 꼬리말이지 기업 이름이 아니다.
다만 **회사 이름의 일부일 수도** 있으므로, 여기 적은 낱말이 실제 IR 기업 이름을
삼키지 않는지 실기업 목록 344곳으로 확인했고, 그 성질을 시험으로 못 박아 두었다
(`tests/test_company_names_split.py`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .room_name import normalize_space

#: 이름 한 조각의 최대 길이. 이보다 길면 기업명이 아니라 문장이다.
NAME_MAX = 40

#: 법인 표기 — `(주)` 의 괄호는 **구분자가 아니다.** 쪼개기 전에 잠시 감춰 둔다.
#: (`sheet_import.normalize_company_name` 이 비교할 때 떼는 그 표기들이다.)
_GUARDED = {
    "(주)": "\x01", "(유)": "\x02", "(재)": "\x03",
    "(사)": "\x04", "(합)": "\x05",
}

#: 날짜 조각. `9/2` · `8/13(목)` · `[8/5]` · `8.4` · `2026.9.2` 를 모두 읽는다.
#: 앞뒤로 숫자가 더 붙는 것은 날짜로 보지 않는다(`456/789` 같은 값 보호).
_DATE = re.compile(
    r"[\[(]?\s*(?:\d{4}\s*[/.\-]\s*)?(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})(?!\d)"
    r"\s*(?:\(\s*([월화수목금토일])[^)]*\))?\s*[\])]?"
)

#: `핵심 딜 8개사` — 기업명 없이 개수만 적힌 회차.
_COUNT_ONLY = re.compile(r"(\d+)\s*개\s*사")

#: `1.샘플가  2.샘플나` — 번호 매김. 구분자가 이중공백일 수 있다.
_NUMBERED = re.compile(r"(?:^|\s)\d{1,2}\s*[.)]\s*")

#: 조각을 가르는 글자. **띄어쓰기는 없다** — `샘플 가나다` 처럼 이름 안에
#: 공백이 들어가는 기업이 실제로 있다(실목록 344곳 중 81곳이 그렇다).
_SEPARATORS = ",、;|·ㆍ/>→\n\t()[]"

#: 마침표는 **뒤에 공백이 올 때만** 구분자다. `샘플가. 샘플나` 는 나열이고,
#: `R.O.C.K` 은 한 이름이다.
_DOT_SPLIT = re.compile(r"\.\s+")

#: 조각 끝에서 떼는 군더더기.
_EDGE = " \t.,·ㆍ/-–—:;~()[]<>\"'"

#: 회차에 붙는 꼬리말. 이 낱말들로만 이뤄진 조각은 기업이 아니다.
#: **실기업 목록 344곳과 대조해서 골랐다** — 이 낱말들만으로 이름이 되는 기업은
#: 한 곳도 없다(시험이 그 성질을 지킨다).
NOISE_WORDS = (
    "카톡", "딜", "소개", "공유", "전달", "핵심", "기업", "없음", "리마인드",
    "문자", "메일", "미팅", "요청", "안내", "다시", "발송", "공지", "회신",
    "개사", "제외", "금지", "진행", "예정",
)


@dataclass
class Chunk:
    """한 칸 안의 **회차 하나**. 날짜를 뗀 내용과 원문을 함께 들고 있다."""

    month: Optional[int] = None
    day: Optional[int] = None
    weekday: Optional[str] = None
    content: str = ""          # 날짜를 뗀 나머지
    raw: str = ""              # 원문 줄(날짜 포함) — 그대로 보존한다

    @property
    def dated(self) -> bool:
        return self.month is not None and self.day is not None


@dataclass
class Split:
    """한 회차 내용을 쪼갠 결과."""

    names: List[str] = field(default_factory=list)
    count: Optional[int] = None
    #: 내용 안에서 **떼어 낸** 날짜 조각들 `(월, 일)`. 버리지 않는다.
    dates: List[Tuple[int, int]] = field(default_factory=list)
    weekday: Optional[str] = None


# ── 날짜 ────────────────────────────────────────────────────────────────────

def round_prefix(line: str) -> Optional[Chunk]:
    """줄이 **날짜로 시작하는가.** 시작하면 그 줄은 새 회차다.

    대괄호가 씌워진 `[8/5]` 도 날짜다 — 실제 칸 값 1,988줄 중 453줄이 이 꼴이라,
    이것을 날짜로 못 읽으면 그 회차가 통째로 앞 회차에 붙는다.
    """
    m = _DATE.match(line)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    rest = normalize_space(line[m.end():].lstrip(_EDGE))
    return Chunk(month=month, day=day, weekday=m.group(3),
                 content=rest, raw=normalize_space(line))


def rounds(text: str) -> List[Chunk]:
    """한 칸(줄바꿈으로 회차가 쌓인 글) → **회차 목록**.

    날짜로 시작하지 않는 줄은 직전 회차에 이어 붙인다 — 기업 목록이 다음 줄로
    넘어가는 일이 잦다(`[8/5] [핵심 딜 공유]` 다음 줄에 기업 여덟).
    """
    out: List[Chunk] = []
    for raw_line in (text or "").splitlines():
        line = normalize_space(raw_line)
        if not line:
            continue
        head = round_prefix(line)
        if head is not None:
            out.append(head)
        elif out:
            out[-1].content = normalize_space(f"{out[-1].content} {line}")
            out[-1].raw = f"{out[-1].raw}\n{line}"
        else:
            out.append(Chunk(content=line, raw=line))
    return out


# ── 쪼개기 ──────────────────────────────────────────────────────────────────

def _guard(text: str) -> str:
    for mark, ch in _GUARDED.items():
        text = text.replace(mark, ch)
    return text


def _unguard(text: str) -> str:
    for mark, ch in _GUARDED.items():
        text = text.replace(ch, mark)
    return text


def is_noise_word(token: str) -> bool:
    """이 낱말이 **꼬리말뿐인가.** `카톡딜`·`소개기업` 처럼 붙여 쓴 것도 본다."""
    rest = token
    changed = True
    while changed:
        changed = False
        for word in NOISE_WORDS:
            if word in rest:
                rest = rest.replace(word, "")
                changed = True
    return not re.sub(r"[\s\d" + re.escape(_EDGE) + r"]", "", rest)


def _has_letter(text: str) -> bool:
    """글자가 하나라도 있는가. 숫자·기호만 남은 조각은 이름이 아니다."""
    return bool(re.search(r"[0-9]*[^\W\d_]", text))


def _trim_noise(text: str) -> str:
    """조각의 **앞뒤**에 붙은 꼬리말만 뗀다.

    가운데는 손대지 않는다 — 이름 안에 공백이 든 기업이 넷 중 하나꼴이라,
    가운데를 건드리기 시작하면 이름이 잘린다.
    """
    parts = text.split()
    while len(parts) > 1 and is_noise_word(parts[-1]):
        parts.pop()
    while len(parts) > 1 and is_noise_word(parts[0]):
        parts.pop(0)
    return " ".join(parts)


def _segments(text: str) -> List[str]:
    """내용을 조각으로 가른다. **날짜 조각도 구분자다.**

    이미 들어와 있는 줄에는 `앞기업 [8/12] 뒷기업` 처럼 날짜가 이름 사이에
    끼어 있다(옛 규칙이 회차를 못 갈라 붙여 놓은 자리다). 날짜에서 갈라야 그
    줄의 기업이 모두 제자리를 찾는다.
    """
    work = _guard(text)
    work = _DATE.sub(",", work)
    work = _NUMBERED.sub(",", work)
    work = _DOT_SPLIT.sub(",", work)
    for ch in _SEPARATORS:
        work = work.replace(ch, ",")
    # **감춘 채로** 돌려준다 — `(주)` 의 괄호가 군더더기로 떨어져 나가지 않게,
    # 앞뒤를 다듬는 일까지 끝난 뒤에 되돌린다(`split`).
    return work.split(",")


def split(content: str) -> Split:
    """회차 내용 → **기업 이름 목록 · 개수 · 떼어 낸 날짜**.

    읽어 내는 표기는 이렇다(모두 실제 칸 값이다).

        `샘플가, 샘플나`                → 이름 둘
        `1.샘플가  2.샘플나`            → 이름 둘 (번호 매김)
        `[핵심 딜 공유] 샘플가`         → 이름 하나 (꼬리말은 뗀다)
        `카톡딜 공유/샘플가, 샘플나`     → 이름 둘 (`/` 뒤가 목록이다)
        `핵심 딜 8개사`                 → 이름 없음, 개수 8
        `핵심 딜 8개사 샘플가, 샘플나`   → 이름 둘 (개수 말은 이름에서 뗀다)
        `샘플가 [8/12] 샘플나`          → 이름 둘 + 날짜 `(8, 12)`
    """
    out = Split()
    text = normalize_space(content)
    if not text:
        return out

    for m in _DATE.finditer(_guard(text)):
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            out.dates.append((month, day))
            if out.weekday is None and m.group(3):
                out.weekday = m.group(3)

    count: Optional[int] = None
    for segment in _segments(text):
        piece = normalize_space(segment)
        m = _COUNT_ONLY.search(piece)
        if m:
            # 개수 말은 **이름에서 떼고**, 남은 글자는 계속 본다.
            # `핵심 딜 8개사 샘플가` 의 그 기업이 여기서 살아난다.
            count = int(m.group(1))
            piece = normalize_space(_COUNT_ONLY.sub(" ", piece))
        piece = _unguard(_trim_noise(piece).strip(_EDGE))
        if not piece or len(piece) > NAME_MAX:
            continue
        if is_noise_word(piece.replace(" ", "")) or not _has_letter(piece):
            continue
        if piece not in out.names:
            out.names.append(piece)

    out.count = len(out.names) or count
    return out
