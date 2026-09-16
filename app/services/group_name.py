"""`VcContact.group_name` 에 **무엇이 들어가도 되는가** — 판정이 적힌 한 곳.

## 왜 한 곳인가

이 칸의 화면 이름은 오랫동안 `그룹/투자분야/라운드사이즈` 였다. 시트 머리글이
그랬고, 사람들은 머리글이 시키는 대로 **셋을 한 칸에 문장으로** 적어 왔다.
그런데 투자 단계·규모·분야는 이미 자기 칸이 있다(`round_size` · `sectors` ·
`stages`). 그래서 같은 말이 두 군데에 갈렸고, 그룹으로 고르려고 열면 목록에
줄 수만큼 항목이 떴다.

사용자가 정했다 — **그룹 칸은 A~F 만 담는다.**

그 판정이 필요한 자리가 둘이다. 하나는 시트를 읽어 넣는 쪽
(`services/sheet_import.apply_sheet_a`)이고, 다른 하나는 이미 들어가 있는 값을
정리하는 쪽(`scripts/clean_group_name.py`)이다. **두 군데에 규칙을 적으면 한쪽이
낡는다** — 이 저장소가 반복해서 데인 자리다(`contact_columns.filterable` 주석이
같은 이유로 판정을 한 곳에 모았다). 그래서 둘 다 `decide()` 하나를 부른다.

## 무엇을 하는가

    A · b그룹 · a        → `A` · `B` · `A`          (`fix`)
    `Seed~PreA 30억`     → round_size 에 이미 있다   (`drop` — 그냥 비운다)
    `AI/바이오 선호`      → sectors 에 이미 있다      (`drop`)
    여기에만 있는 문장    → memo 뒤에 옮겨 붙인다     (`move`)

**겹침은 모양을 지우고 본다.** 같은 말인데 `Seed~Pre A | 30억` 과
`Seed~PreA/30억` 처럼 띄어쓰기와 구분 기호만 다른 줄이 많다. 공백 · `|` · `·` ·
`,` · `/` 를 지우고 소문자로 만든 뒤 **한쪽이 다른 쪽에 들어가는지**를 본다.

**옮길 때는 어디서 왔는지 적는다**(`MOVED_MARK`). 나중에 되돌리거나 사람이 볼
때 그 글이 원래 그룹 칸에 있던 것임을 알아야 한다 — 표시가 없으면 메모에 갑자기
낯선 문장이 하나 늘어난 것으로만 보인다.

**이미 memo 에 있는 말은 안 붙인다.** 시트는 여러 번 올라오고 정리 스크립트도
다시 돌 수 있다. 붙일 때마다 같은 문장이 쌓이면 메모가 읽을 수 없게 된다 —
그래서 `decide()` 는 몇 번을 돌려도 같은 자리에 멈춘다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# 그룹은 이 여섯 가지다. 화면의 고르는 칸도 이 목록을 쓴다
# (`contact_columns` 의 `Column("그룹", "group_name", …, choices=CHOICES)`) —
# 거기에 글자를 따로 적어 두면 필터에 서는 보기와 여기 통과 규칙이 갈린다.
GROUPS = ("A", "B", "C", "D", "E", "F")
CHOICES = ",".join(GROUPS)

# 옮겨 붙인 글 앞에 서는 표시. 출처를 적어 두는 자리다.
MOVED_MARK = "[그룹 칸에서 옮김]"

# `decide()` 가 내놓는 판정.
EMPTY = "empty"   # 빈 칸 — 아무 일도 하지 않는다
KEEP = "keep"     # 이미 A~F 한 글자다
FIX = "fix"       # `b그룹` · `a` → `B` · `A`
DROP = "drop"     # round_size 나 sectors 에 이미 있는 말 — 그냥 비운다
MOVE = "move"     # 여기에만 있는 말 — memo 뒤로 옮기고 비운다

# `A그룹` · `그룹 B` — 앞뒤 어느 쪽에 붙어 있어도 떼어 낸다. 실측에 있던 것은
# 뒤에 붙은 꼴뿐이지만, 떼어 낸 결과가 어차피 한 글자 A~F 여야 통과하므로
# 앞쪽까지 보아도 통과 범위가 넓어지지 않는다.
_GROUP_WORD = re.compile(r"^\s*그룹\s*|\s*그룹\s*$")

# 겹침을 볼 때 지우는 것들. 같은 말이 `Seed~Pre A | 30억` 과 `Seed~PreA/30억`
# 로 갈려 적혀 있어서, 이것을 안 지우면 같은 말이 다른 말로 보인다.
_NOISE = re.compile(r"[\s|·,/]+")


@dataclass(frozen=True)
class Decision:
    """이 줄의 그룹 칸을 어떻게 할 것인가.

    `group` · `memo` 는 **새 값**이다. `None` 은 "그대로 두라" 가 아니라 칸마다
    뜻이 다르다:

        group=None   그 칸을 **비운다**(DROP · MOVE). EMPTY 일 때만 손대지 않는다.
        memo=None    memo 는 **그대로 둔다**(붙일 것이 없거나 이미 있다).

    `moved` 는 실제로 memo 에 붙인 글이다. 아무것도 안 붙였으면 빈 글자다 —
    같은 말이 이미 memo 에 있어서 안 붙인 경우가 그렇다.
    """

    action: str
    group: Optional[str] = None
    memo: Optional[str] = None
    moved: str = ""

    @property
    def changes(self) -> bool:
        """이 줄을 실제로 건드리는가. 세는 쪽이 이것으로 고른다."""
        return self.action in (FIX, DROP, MOVE)


def letter(value: Optional[str]) -> Optional[str]:
    """`b그룹` → `B`. A~F 한 글자로 읽히지 않으면 `None`.

    `A,B,C,D,E,F` 로 골라야 하는 칸이라, 한 글자로 맞지 않는 값은 **필터에서
    통째로 빠진다** — 저장은 되는데 걸러지지 않는 값이 된다. 그래서 읽어낼 수
    있는 것은 읽어내고, 못 읽는 것은 `None` 으로 분명히 가른다.
    """
    text = _GROUP_WORD.sub("", (value or "").strip()).strip().upper()
    return text if text in GROUPS else None


def squash(value: Optional[str]) -> str:
    """겹침을 보려고 모양을 지운 글자. 위 `_NOISE` 주석 참고."""
    return _NOISE.sub("", (value or "").strip()).lower()


def overlaps(value: Optional[str], other: Optional[str]) -> bool:
    """두 글이 **같은 말인가** — 한쪽이 다른 쪽에 들어가는가.

    **양쪽 다 값이 있어야 한다.** 빈 글자는 어느 글에나 들어가므로, 안 막으면
    `round_size` 가 빈 줄이 전부 "겹친다" 로 판정돼 그룹 칸의 글이 소리 없이
    사라진다.
    """
    left, right = squash(value), squash(other)
    if not left or not right:
        return False
    return left in right or right in left


def append_memo(memo: Optional[str], value: str) -> Optional[str]:
    """옮길 글을 memo 뒤에 붙인 결과. 붙일 것이 없으면 `None`(그대로 둔다).

    이미 있는 말은 안 붙인다 — 위 모듈 설명 참고. 판정은 `overlaps` 와 **같은
    자로** 한다(모양을 지우고 본다): 붙일 때 표시(`MOVED_MARK`)가 앞에 서므로
    글자 그대로 비교하면 두 번째 실행에서 못 알아본다.
    """
    text = (value or "").strip()
    if not text:
        return None
    current = (memo or "").strip()
    if squash(text) and squash(text) in squash(current):
        return None
    mark = f"{MOVED_MARK} {text}"
    return f"{current}\n{mark}" if current else mark


def decide(value: Optional[str], round_size: Optional[str] = None,
           sectors: Optional[str] = None,
           memo: Optional[str] = None) -> Decision:
    """이 줄의 그룹 값을 어떻게 할 것인가. **시트 쪽과 정리 스크립트가 함께 부른다.**

    차례가 곧 규칙이다:

      ① 빈 칸은 손대지 않는다.
      ② A~F 로 읽히면 그 한 글자로 둔다(`KEEP` · `FIX`).
      ③ 그 말이 `round_size` 나 `sectors` 에 이미 있으면 **그냥 비운다**
         (`DROP`). memo 로 옮기면 같은 말이 세 군데가 된다.
      ④ 그 밖에는 **여기에만 있는 정보**다. 비우기 전에 memo 로 옮긴다(`MOVE`).

    ③ 이 ④ 보다 앞인 것이 핵심이다. 뒤집으면 이미 제 칸에 있는 말까지 전부
    메모에 다시 적힌다.
    """
    text = (value or "").strip()
    if not text:
        return Decision(EMPTY)

    found = letter(text)
    if found is not None:
        return Decision(KEEP if text == found else FIX, group=found)

    if overlaps(text, round_size) or overlaps(text, sectors):
        return Decision(DROP)

    new_memo = append_memo(memo, text)
    return Decision(MOVE, memo=new_memo, moved=text if new_memo else "")
