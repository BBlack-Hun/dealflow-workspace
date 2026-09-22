"""`VcContact.group_name` 에 **무엇이 들어가도 되는가** — 판정이 적힌 한 곳.

## 왜 한 곳인가

이 칸의 화면 이름은 오랫동안 `그룹/투자분야/라운드사이즈` 였다. 시트 머리글이
그랬고, 사람들은 머리글이 시키는 대로 **셋을 한 칸에 문장으로** 적어 왔다.
그런데 투자 단계·규모·분야는 이미 자기 칸이 있다(`round_size` · `sectors` ·
`stages`). 그래서 같은 말이 두 군데에 갈렸고, 그룹으로 고르려고 열면 목록에
줄 수만큼 항목이 떴다.

사용자가 정했다 — **그룹 칸은 정해 둔 갈래만 담는다. 문장은 안 담는다.**

갈래는 두 줄기다. 처음에는 한 글자 여섯(`A`~`F`)뿐이었는데, 정리한 뒤로
사용자가 **뜻이 있는 이름**을 함께 쓰기 시작했다(`특정분야` · `Pre IPO` ·
`Series B 이상` … 50줄). 물었더니 "일부러 넣은 것이고 앞으로도 쓴다 — 이름으로도
쓸 것 같다" 였다. 그래서 여기 적힌 것은 `A~F` 가 아니라 **`KNOWN`** 이다.

**바뀌지 않은 것**: 문장은 여전히 안 들어온다. 열어 두면 `Seed~PreA 30억` ·
`AI/바이오 선호` 같은 158줄이 그대로 돌아오고, 그룹으로 고르려고 열면 목록에
줄 수만큼 항목이 뜬다 — 이 모듈이 생긴 이유가 그것이다.

그 판정이 필요한 자리가 둘이다. 하나는 시트를 읽어 넣는 쪽
(`services/sheet_import.apply_sheet_a`)이고, 다른 하나는 이미 들어가 있는 값을
정리하는 쪽(`scripts/clean_group_name.py`)이다. **두 군데에 규칙을 적으면 한쪽이
낡는다** — 이 저장소가 반복해서 데인 자리다(`contact_columns.filterable` 주석이
같은 이유로 판정을 한 곳에 모았다). 그래서 둘 다 `decide()` 하나를 부른다.

## 무엇을 하는가

    A · b그룹 · a        → `A` · `B` · `A`          (`fix`)
    `series b이상`        → `Series B 이상`          (`fix` — 이름도 제 글자로)
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
from typing import Iterable, Optional

# ── 그룹으로 **인정되는 값** ────────────────────────────────────────────────
#
# 처음에는 한 글자 여섯뿐이었다. 그런데 사용자가 그 뒤로 **뜻이 있는 이름**을
# 함께 쓰기 시작했다(50줄). 물었더니 "일부러 넣은 것이고 앞으로도 쓴다 —
# 이름으로도 쓸 것 같다" 였다. 그래서 갈래는 **두 줄기**다.
#
# 한 글자. 시트가 오래전부터 쓰던 꼴이고, `A그룹`·`a` 처럼 꼬리말·대소문자가
# 갈려 들어온다 — `letter()` 가 그것을 한 글자로 읽는다.
GROUPS = ("A", "B", "C", "D", "E", "F")

# 뜻이 있는 이름. **글자까지 사용자가 적어 둔 그대로**다(운영에서 세어 온 값) —
# 앱이 줄여 부르거나 차례를 바꾸면 시트·문서와 나란히 놓고 대조할 수가 없다.
# 차례는 **줄 수가 많은 것부터**다. 고르는 칸에서 자주 쓰는 말이 위에 서야
# 목록을 통째로 눈으로 훑지 않는다.
#
# ## 다섯이 늘었다 — 한 명단을 **선호로 다시 묶기로** 했다
#
# 한 딜 소개 명단의 그룹 칸이 `A` 69 · `B` 1 · 빈칸 46 이었는데, 그 `A` 가
# **무슨 뜻인지 앱 자료 어디에도 남아 있지 않았다**(A 69줄 중 선호 투자분야가
# 적힌 줄 3 · 라운드 사이즈 3 · 투자 단계 0). 시트의 `그룹` 열에 적혀 있던
# 글자가 그대로 들어온 것이고, 그 글자로는 아무도 나눌 수 없다.
#
# 사용자가 정했다 — **선호 투자분야와 라운드 사이즈로 다시 묶고, 특이사항이
# 없는 분들은 한 갈래로 모은다.** 그 갈래의 이름이 `공통` 이다.
#
# 매기는 규칙은 여기 적지 않는다. `services/pref_group.py` 한 곳이고, 이
# 목록은 **그 규칙이 내놓을 수 있는 이름이 여기 있는가**만 정한다
# (`tests/test_pref_group.py` 가 둘을 맞춰 본다).
#
# **여기 없으면 다음 시트 업로드가 되돌린다.** `decide()` 가 모르는 이름을
# 문장으로 보고 메모로 옮겨 버린다(`MOVE`) — 그래서 규칙보다 이 목록이 먼저다.
#
# 차례는 **다시 묶은 뒤의 줄 수**로 세운 것이다(명단 117줄이 새 값으로 바뀐다):
#
#     공통 72 · 특정분야 21+6 · Series C 이상 6+13 · Pre IPO 11-1 ·
#     딥테크·제조 8 · ESG·푸드·애그테크 5 · Seed~Pre-A 5 · 딜 소개 보류 5 ·
#     Series B 이상 5 · Seed 5 · 대형 딜 2 · M&A 2 · 지역 한정 1 ·
#     Series A 이상 1 · TIPS 1 · Series A~B 0
#
# `Series A~B` 는 **지금 0줄**이다. 그래도 적어 둔다 — 라운드 갈래를 셋으로
# 가르면서 가운데 칸에 이름을 안 주면, 나중에 `시리즈 A~B` 만 적은 줄이
# 들어왔을 때 갈 데가 없어 **조용히 엉뚱한 갈래로 간다.** 규칙에 구멍을 두는
# 것보다 0줄짜리 이름 하나가 낫다.
#
# **분야 이름 둘(`딥테크·제조` · `ESG·푸드·애그테크`)은 IR 기업의 `사업분야`
# 표기 그대로다.** 딜 소개를 맞출 때 LLM 에게 "분야는 이 이름으로 세라" 고
# 시키는 목록이 그것이라(`llm_brief.sector_names`), 그룹 이름이 같은 글자여야
# 시킨 말과 자료가 한 낱말로 만난다. 여기서 새 이름을 지으면 그 그룹의 수요는
# 어느 기업에도 안 걸린다.
#
# ## 셋은 **분야도 라운드도 아닌 축**이다
#
# 예전 그룹 칸에 사람이 스스로 달아 둔 딱지 중에 분야·라운드로 읽히지 않는
# 것이 셋 있었다(`보류` · `대형` · `지역 한정`). 그대로 두면 전부 `공통` 에
# 섞이는데, **특이사항이 없는 것이 결코 아니다.** 사용자가 따로 세우기로 했다.
#
# 이름은 **사용자가 쓰던 말을 살리되 뜻이 보이게** 했다. 이 값이 딜 소개를
# 맞추는 LLM 에게 그대로 나가므로(`llm_brief.INVESTOR_FIELDS`), 이름만 읽고
# 무슨 조건인지 알 수 있어야 한다.
#
#     보류      → `딜 소개 보류`   무엇이 보류인지가 이름에 있어야 한다.
#                                  `보류` 만으로는 무엇을 멈춘 것인지 모른다.
#     대형      → `대형 딜`        규모가 큰 딜을 본다는 뜻. 라운드 단계가
#                                  아니라 **금액 규모**라 사다리 이름과 가른다.
#     지역 한정 → `지역 한정`      어느 지역인지는 사람마다 달라 이름에 못
#                                  적는다. 자세한 것은 메모가 말한다.
#
# **`딜 소개 보류` 는 이름일 뿐 발송을 막지 않는다.** 앱에서 실제로 막는 값은
# `VcContact.status` 의 `검토중단`(`sheet_owner.is_paused` → `can_send_to`)
# 하나다. 이름을 그렇게 지은 것은 사람이 그 그룹을 골라 보내지 않게 하려는
# 것이고, 정말로 막으려면 그 줄의 상태 칸을 `검토중단` 으로 두어야 한다.
NAMED = ("공통", "특정분야", "Series C 이상", "Pre IPO", "딥테크·제조",
         "ESG·푸드·애그테크", "Seed~Pre-A", "딜 소개 보류", "Series B 이상",
         "Seed", "대형 딜", "M&A", "지역 한정", "Series A 이상", "TIPS",
         "Series A~B")

#: 이 칸이 **받아들이는 값 전부**. 임포트가 통과시키는 값이자 정리 스크립트가
#: `그대로` 로 두는 값이다.
KNOWN = GROUPS + NAMED

#: 화면이 **고를 거리로 세우는 값**(`Column.choices` · `data-choices` ·
#: `<datalist>`). **받아들이는 값에서 그대로 나온다** — 목록을 따로 적으면
#: 화면에서 고른 값이 임포트에서는 없는 값이 되는 날이 온다.
#:
#: 다만 둘은 **같은 것이 아니다.** 여기 있는 것은 *고를 거리*일 뿐이고, 화면은
#: 목록에 없는 말도 새로 적을 수 있다(`<datalist>` 는 `<input>` 을 묶지 않고,
#: 표의 `pick` 창도 글자 칸이다). 사용자가 새 이름을 쓰면 **그 이름은 그때부터
#: 화면의 보기에 함께 뜬다** — 보기는 `고정 목록 + 지금 그 화면이 쓰고 있는 값`
#: 으로 만든다(`routers/pages.py` 의 `group_choices`, `inline_edit.js` 의
#: `startPick` 이 표에서 하는 셈과 같다). 그래서 이름이 하나 는다고 코드를
#: 고쳐야 하는 것은 아니다.
#:
#: 코드를 고쳐야 하는 자리는 **하나뿐이다** — 그 이름이 *시트로도* 들어오거나,
#: 정리 스크립트가 그것을 문장으로 보지 않게 하려면 `NAMED` 에 적어야 한다.
#: 그 둘은 "무엇이 그룹인가" 를 정하는 일이라 열어 둘 수 없다: 열면 예전에
#: 158줄이 문장으로 들어왔던 자리가 그대로 돌아온다.
CHOICES = ",".join(KNOWN)

# 옮겨 붙인 글 앞에 서는 표시. 출처를 적어 두는 자리다.
MOVED_MARK = "[그룹 칸에서 옮김]"

# `decide()` 가 내놓는 판정.
EMPTY = "empty"   # 빈 칸 — 아무 일도 하지 않는다
KEEP = "keep"     # 이미 정해 둔 갈래다(한 글자 또는 이름)
FIX = "fix"       # `b그룹` · `a` · `series b이상` → 제 글자로
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
    """`b그룹` → `B`. **한 글자 갈래**로 읽히지 않으면 `None`.

    골라서 거르는 칸이라, 갈래 이름으로 맞지 않는 값은 **필터에서 따로 떨어져
    나온다** — 저장은 되는데 같은 갈래로는 안 걸리는 값이 된다. 그래서 읽어낼
    수 있는 것은 읽어내고, 못 읽는 것은 `None` 으로 분명히 가른다.

    이름 갈래(`NAMED`)는 여기서 안 본다 — 대문자로 올리면 `Pre IPO` 가
    `PRE IPO` 가 되어 적어 둔 글자와 달라진다. 둘을 함께 보는 자리는
    `canonical()` 이다.
    """
    text = _GROUP_WORD.sub("", (value or "").strip()).strip().upper()
    return text if text in GROUPS else None


def canonical(value: Optional[str]) -> Optional[str]:
    """이 값이 **그룹으로 인정되는가** — 인정되면 정해 둔 글자 그대로 돌려준다.

    받아들이는 값은 `KNOWN` 하나다. 한 글자는 `letter()` 가 읽고, 이름은
    **모양을 지우고**(`squash` — 공백·`|`·`·`·`,`·`/` 를 지우고 소문자)
    맞춘다. `series b이상` · `Series B 이상` 이 같은 값으로 모이게 하려는
    것이고, 그 자는 `overlaps` 가 쓰는 자와 **같다** — 한 모듈 안에서 같은
    말인지를 두 가지 자로 재면 한쪽만 고쳐지는 날이 온다.

    돌려주는 것은 **적어 둔 글자**다(`NAMED` 의 그 꼴). 그래야 표에서 골라
    넣은 값과 창에서 쳐 넣은 값이 한 글자도 다르지 않게 모인다 — 갈리면 딜
    제안 관리의 그룹 칩과 그룹 발송에서 다른 그룹이 된다.
    """
    text = (value or "").strip()
    if not text:
        return None
    one = letter(text)
    if one is not None:
        return one
    key = squash(text)
    for name in NAMED:
        if squash(name) == key:
            return name
    return None


def options(used: Iterable[Optional[str]] = ()) -> str:
    """화면이 세울 **고를 거리** — `고정 목록 + 지금 쓰고 있는 값`.

    `CHOICES` 를 그대로 쓰지 않는 이유는 하나다. 사용자가 **새 이름을 쓸 수
    있다.** 그때마다 코드를 고쳐야 한다면, 어제 자기가 적은 말이 오늘 고를
    목록에 없는 화면이 된다 — 그러면 또 빈 칸에 새로 치게 되고, 그 자리에서
    `Series B 이상` 과 `시리즈B 이상` 이 갈린다.

    표가 이미 같은 셈을 한다(`static/js/inline_edit.js` 의 `startPick` —
    `data-choices` 를 먼저 세우고 그 뒤에 `knownValues`, 즉 다른 줄이 쓰고 있는
    값을 보탠다). 수정창에는 훑을 표가 없으므로 **서버가 같은 셈을 해서 넘긴다**
    — 그래야 표에서 고를 때와 창에서 적을 때 **같은 목록**을 본다.

    **고정 목록이 먼저다.** 정해 둔 갈래가 위에 서야, 새로 적힌 비슷한 말이
    목록 맨 위를 차지해 그것을 또 고르는 일이 없다.

    쉼표가 든 값은 **뺀다.** 이 목록은 쉼표로 이어 붙여 화면으로 가고
    (`data-choices` · `Column.choices`) 거기서 다시 쉼표로 갈린다 — 값 안의
    쉼표가 한 값을 둘로 쪼갠다.

    받아들이는 값(`KNOWN`)과 **같은 것이 아니다.** 여기 있는 것은 고를
    거리일 뿐이고, 여기 없는 말도 화면에서는 그대로 새로 적힌다. 무엇이
    그룹으로 인정되는가는 `decide()` 가 따로 가른다.
    """
    seen = {name: True for name in KNOWN}
    extra = []
    for value in used:
        text = (value or "").strip()
        if not text or "," in text or text in seen:
            continue
        seen[text] = True
        extra.append(text)
    return ",".join(list(KNOWN) + sorted(extra))


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
      ② 정해 둔 갈래로 읽히면 그 글자로 둔다(`KEEP` · `FIX`) — 한 글자든
         이름이든 `canonical()` 한 곳이 가른다. **이것이 ③ 보다 앞이라**
         `Seed` 가 `round_size` 의 `Seed~PreA 30억` 과 겹쳐 보여도 안 지워진다.
      ③ 그 말이 `round_size` 나 `sectors` 에 이미 있으면 **그냥 비운다**
         (`DROP`). memo 로 옮기면 같은 말이 세 군데가 된다.
      ④ 그 밖에는 **여기에만 있는 정보**다. 비우기 전에 memo 로 옮긴다(`MOVE`).

    ③ 이 ④ 보다 앞인 것이 핵심이다. 뒤집으면 이미 제 칸에 있는 말까지 전부
    메모에 다시 적힌다.
    """
    text = (value or "").strip()
    if not text:
        return Decision(EMPTY)

    found = canonical(text)
    if found is not None:
        return Decision(KEEP if text == found else FIX, group=found)

    if overlaps(text, round_size) or overlaps(text, sectors):
        return Decision(DROP)

    new_memo = append_memo(memo, text)
    return Decision(MOVE, memo=new_memo, moved=text if new_memo else "")
