"""시트 값과 앱 값이 **다른 칸**을 찾아 나란히 놓는다.

왜 만드는가
-----------
고객사가 말했다 — *"제가 드리는 내용이 왜 그대로 엑셀이 반영이 안 되나."*
사실이었다. 넣는 길이 둘인데 **둘 다 빈 칸만 채운다.**

  · `scripts/import_investor_list.py` 의 채우기(`fill_plan`) — 월별 칸에 이미
    글이 있으면 새 값을 아예 안 얹는다.
  · `services/sheet_import._fill_if_empty` — 프로필·연락처·메모도 같다.

빈 칸만 채우는 것 자체는 틀린 판단이 아니다. 그렇게 두지 않으면 **화면에서
사람이 다듬어 둔 값이 시트 한 장에 조용히 날아간다** — 두 파일이 그 이유를
나란히 적어 두었고, 지금도 맞는 말이다. 틀린 것은 **말을 안 해 준다**는 쪽이다.
시트와 앱이 갈렸다는 사실 자체가 어디에도 안 뜨니, 고객은 고쳐 보내고 또
고쳐 보내면서 화면이 그대로인 까닭을 알 수 없었다.

그래서 이 파일이 하는 일은 **덮는 것이 아니라 보여 주는 것**이다. 임포트가
"안 얹고 지나간 칸" 을 세어 `지금 값 → 시트 값` 으로 나란히 편다. 사람이
그것을 보고 덮을지 말지 정한다.

**기본은 그대로다.** 아무 것도 고르지 않으면 지금까지처럼 빈 칸만 채운다 —
이 목록이 늘어날 뿐 DB 에 닿는 것은 달라지지 않는다. 기본을 덮어쓰기로 바꾸면
이 길을 쓰던 다른 일이 조용히 망가진다.

어느 칸까지 덮을 수 있나 — **칸마다 누가 이기는지가 다르다**
------------------------------------------------------------
세 갈래로 가른다. 갈래는 **여기 한 곳**에만 적는다. 두 임포트가 같은 판정을
따로 적으면 한쪽이 낡고, 그날부터 같은 시트가 길에 따라 다른 결과를 낸다.

``MONTHS``  **월별 칸**(`note:c7`). 시트가 원본이다 — 달마다 딜소개·IR 요청·
            미팅을 적는 자리이고, 앱 화면에서 이 칸을 손보는 일은 드물다.
            고객이 고쳐 보내는 칸이 바로 이것이라, 덮기의 첫째 대상이다.

``CARD``    **명함·분류 칸**(직함 · 부서 · 연락처 · 라운드 · 분야 · 관심도 …).
            시트가 원본이고 값이 짧아 나란히 놓고 보면 어느 쪽이 맞는지
            사람이 바로 안다. 다만 연락처가 섞여 있어 **한꺼번에 덮는 것을
            기본으로 두지 않는다** — 고르거나 `all` 을 적어야 닿는다.

``HELD``    **사람이 이긴다. 덮는 길을 아예 만들지 않는다.** 다름은 보여 준다
            (값을 그대로 찍을지는 `shows_value` 가 `edit_log` 의 허용
            목록을 읽어 정한다 — 메모는 길이만, 카톡방 이름은 값까지).

              memo               앱에서 사람이 **이어 쓰는** 칸이다. 시트의
                                 메모와 뜻이 다르고(대화 내역 · 한 줄 평),
                                 덮으면 사람이 쓴 글이 사라진다. 게다가 이
                                 칸은 수정 로그에 **값이 안 실린다**
                                 (`edit_log.VALUE_FIELDS` 밖 — 개인정보라
                                 일부러 뺐다). 곧 덮고 나면 되짚을 자리가
                                 어디에도 없다.
              name · firm        줄을 찾는 **열쇠**다(`merge_key`). 열쇠를
                                 덮으면 다음 임포트가 그 줄을 못 찾아 같은
                                 사람이 두 줄이 된다.
              kakao_room_name    한 글자만 달라도 그 담당자에게는 발송이
              connect_stage      통째로 skip 된다(README `방 연결 확인`).
                                 시트에 없는 값이고 사람이 실제 방 제목에
                                 맞춰 고쳐 둔 값이다.
              그 밖의 모든 칸     **목록에 없으면 안 덮는다.** 막을 칸을 적는
                                 방식이면 칸이 하나 늘 때 적는 것을 잊고, 잊은
                                 칸이 조용히 덮인다 — 이 저장소가 허용 목록을
                                 쓰는 이유 그대로다(`edit_log.VALUE_FIELDS`).

전부 덮기와 고른 것만 덮기 — **둘 다 둔다**
--------------------------------------------
칸 수가 백을 넘으면 하나씩 고르는 것은 일이 아니다. 반대로 "이 줄의 이 칸만
틀렸다" 는 것이 뻔한 날 백 칸을 통째로 덮는 것도 위험하다. 그래서 **가리키는
말**을 하나 정해 둔다 — `줄id:칸` (`418:note:c31` · `418:phone`). 미리보기가 칸마다
그 말을 찍어 주므로, 그대로 베껴 `--overwrite 418:note:c31,502:phone` 으로 넘기면
된다. `months` · `all` 은 그 말을 갈래로 묶은 것뿐이다.

**줄 id 로 가리킨다.** 이름+투자사명은 이 임포트 안에서만 쓰는 열쇠라
(`import_investor_list` 모듈 설명) 다른 명단에는 안 통하고, 시트를 한 줄 고치면
그 말이 달라진다. 줄 id 는 앱이 쥐고 있는 값이라 시트를 어떻게 고쳐도 같다.

활동 줄(`contact_activities`)은 **지우지 않는다**
--------------------------------------------------
시트에서 한 줄을 지워도 앱에는 남는다. 지우는 길이 아예 없어서다. 그래도
**"시트에 없으면 지운다" 를 만들지 않았다.** 그 표에는 시트 말고 다른 길로
들어온 줄이 함께 산다.

  · 사람이 화면에서 손으로 적은 줄(`source="manual"` · `services/manual_send.py`)
  · 실제 발송이 만든 줄(회차 한 번에 수십 건)
  · 다른 명단·다른 달의 줄

시트 한 장에 없다는 것은 **그 시트가 그 달을 안 적었다**는 뜻이지 그 일이
없었다는 뜻이 아니다. 없다고 지우면 사람이 적은 기록과 실제 발송 자취가 함께
날아가고, 그것은 화면 어디에도 다시 없다.

대신 **세어서 알린다** — `stale_activities()`. 이 시트가 다루는 달 안에서,
임포트가 만든 줄(`source="import"`) 중 이번 시트에 없는 것이 몇 건인지 보여
준다. 지울지는 사람이 보고 정하고, 지우는 일은 이미 있는 전용 길
(`scripts/drop_shifted_activities.py` — 되돌릴 파일을 뜨고 줄을 하나씩 골라
지운다)이 맡는다. 임포트가 곁다리로 지우는 길을 열지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set

#: 갈래. 바깥에서 `--overwrite` 의 말로 그대로 쓴다.
MONTHS = "months"
CARD = "card"
HELD = "held"

#: 갈래를 묶어 부르는 말. `all` = 덮을 수 있는 칸 **전부**.
ALL = "all"

#: 월별 칸의 열쇠 모양. `contact_columns.note_key()` 가 짓는 이름이다
#: (`c7`) — 여기서 새로 짓지 않고 그 모양을 알아보기만 한다.
_MONTH_KEY = re.compile(r"^note:c\d+$")

#: **명함·분류 칸.** 시트가 원본인 짧은 값들. 여기 없는 칸은 전부 `HELD` 다.
#:
#: `name` · `firm` 이 없는 것에 주의 — 줄을 찾는 열쇠라 일부러 뺐다(위 설명).
#: `memo` 도 없다. `invited_status` · `interest_level` · `kakao_joined` 는
#: 지금도 임포트가 덮는 칸이라(`sheet_import._set_if_value`) 애초에 '안 얹고
#: 지나간 칸' 으로 잡히지 않는다 — 그래도 적어 둔다, 한쪽 길에서 그 규칙이
#: 달라지면 이 목록이 판정을 대신한다.
CARD_FIELDS = frozenset({
    "title", "department", "round_size", "stages", "sectors", "group_name",
    "interest_level", "invited_status", "kakao_joined",
    "phone", "email", "office_phone", "office_fax", "address",
    "card_registered_at", "sourcing_note", "tips_note",
})


def shows_value(key: str) -> bool:
    """이 칸의 **값을 그대로 보여 줘도 되는가.**

    덮을 수 있는 칸(`MONTHS` · `CARD`)은 보여 준다 — 나란히 놓고 보지 못하면
    덮을지 말지를 판단할 수가 없고, 그것이 이 파일이 있는 까닭이다.

    `HELD` 갈래는 갈린다. **판정을 여기서 새로 짓지 않고 `edit_log` 가 이미
    정해 둔 허용 목록을 읽는다** — 같은 물음("이 칸의 값을 사람이 보는 자리에
    남겨도 되는가")에 두 곳이 다른 답을 하면, 로그에는 안 남기기로 한 값이
    미리보기에는 그대로 찍힌다.

        보여 준다   카톡방 이름 · 이름 · 투자사명 · 연결 단계 — 짧고, 한 글자가
                    달라지면 발송이 어긋나는 칸이라 값을 봐야 뜻이 있다.
        안 보여 준다 메모와 목록에 없는 칸 — 길고 사람 이야기가 섞여 있다.
                    몇 자짜리가 다른지만 보이면 화면에서 그 줄을 열어 본다.
    """
    if group_of(key) != HELD:
        return True
    from .edit_log import VALUE_FIELDS

    return key in VALUE_FIELDS


def group_of(key: str) -> str:
    """이 칸이 어느 갈래인가. **모르는 칸은 `HELD`** — 안 덮는 쪽이 기본이다."""
    if _MONTH_KEY.match(key):
        return MONTHS
    if key.startswith("note:"):
        # 명단에만 있는 고정 칸(`기타`). 시트 칸이라 명함과 같은 갈래다.
        return CARD
    return CARD if key in CARD_FIELDS else HELD


#: 갈래마다 미리보기에 적는 말. 갈래를 늘리면 여기도 늘어난다.
GROUP_NOTE = {
    MONTHS: "월별 칸 — 시트가 원본입니다. `--overwrite months` 로 덮습니다",
    CARD: "명함·분류 칸 — `--overwrite all` 또는 칸을 골라야 덮습니다",
    HELD: "**안 덮습니다** — 앱에서 사람이 쥐는 칸입니다(메모·열쇠·카톡방 이름)",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. 무엇이 다른가
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Diff:
    """**앱에 값이 있는데 시트 값이 다른** 칸 하나.

    빈 칸은 여기 오지 않는다 — 그것은 다름이 아니라 채울 자리이고, 임포트가
    지금도 채운다. 시트가 빈 것도 오지 않는다(빈 값은 `모름` 이지 `지워라`
    가 아니다 — `sheet_import._set_if_value` 와 같은 판단이다).
    """

    row_id: int
    #: 앱의 칸 이름(`phone`) 또는 `note:<키>`. `--overwrite` 가 받는 그 말이다.
    key: str
    #: 사람이 읽을 이름. **시트가 그 칸을 부르는 말**을 그대로 쓴다 —
    #: 따로 적어 두면 시트와 글자가 갈려 나란히 놓고 대조할 수가 없다.
    label: str
    before: str
    after: str

    @property
    def token(self) -> str:
        """`--overwrite` 에 그대로 베껴 넣는 말."""
        return f"{self.row_id}:{self.key}"

    @property
    def group(self) -> str:
        return group_of(self.key)

    @property
    def can_overwrite(self) -> bool:
        return self.group != HELD


def compare(row_id: int, values: Dict[str, str], sheet: Dict[str, str],
            labels: Optional[Dict[str, str]] = None) -> List[Diff]:
    """한 줄에서 **다른 칸**만 골라 낸다.

    `values` 는 지금 앱의 값, `sheet` 는 이번 시트의 값. 둘 다 `{칸: 글자}` 다.
    앞뒤 공백만 다른 것은 다름으로 세지 않는다 — 시트마다 공백을 넣고 빼는
    법이 달라서, 세면 목록이 그 잡음으로 덮인다.
    """
    labels = labels or {}
    out = []
    for key, after in sheet.items():
        after = (after or "").strip()
        before = (values.get(key) or "").strip()
        if not after or not before or before == after:
            continue
        out.append(Diff(row_id=row_id, key=key, label=labels.get(key, key),
                        before=before, after=after))
    return out


def stale_activities(existing: Sequence, wanted: Set[tuple],
                     months: Set[str]) -> List:
    """이 시트가 다루는 달 안에서 **시트에 없어진** 활동 줄. 세기만 한다.

    지우지 않는 까닭은 이 파일 머리글에 적었다. 좁히는 자가 둘이다.

      · `months` — 이번 시트가 실제로 읽은 달만 본다. 시트에 9월 칸이 없다고
        9월 기록이 사라져야 하는 것은 아니다.
      · `source="import"` — 사람이 적은 줄과 발송이 만든 줄은 애초에 이 시트가
        만든 것이 아니라 비교할 상대가 아니다.
    """
    out = []
    for row in existing:
        if getattr(row, "source", "") != "import":
            continue
        month = getattr(row, "month", None)
        if not month or month not in months:
            continue
        if (getattr(row, "kind", ""), month, getattr(row, "content", "")) in wanted:
            continue
        out.append(row)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 2. 무엇을 덮으라고 했나
# ─────────────────────────────────────────────────────────────────────────────

class Picks:
    """`--overwrite` 로 받은 말 → **이 칸을 덮느냐** 하나만 답하는 것.

    받는 말은 셋이다.

        months          월별 칸 전부
        all             덮을 수 있는 칸 전부(월별 + 명함·분류)
        418:note:c31,502:phone   미리보기가 찍어 준 말을 베낀 것(`@파일` 도 된다)

    **`HELD` 갈래는 어느 말로도 안 덮인다.** 고른 것만 덮는 길에서도 막는다 —
    미리보기에 뜨는 말을 그대로 베끼는 자리라, 막지 않으면 메모 칸의 말이
    섞여 들어온 날 그대로 덮인다.
    """

    __slots__ = ("groups", "tokens")

    def __init__(self, groups: Set[str], tokens: Set[str]) -> None:
        self.groups = groups
        self.tokens = tokens

    def __bool__(self) -> bool:
        return bool(self.groups or self.tokens)

    def wants(self, diff: Diff) -> bool:
        if not diff.can_overwrite:
            return False
        return diff.group in self.groups or diff.token in self.tokens


def parse_picks(spec: str) -> Picks:
    """`--overwrite` 의 말을 읽는다. 빈 말이면 **아무 것도 안 덮는다**(기본)."""
    spec = (spec or "").strip()
    if not spec:
        return Picks(set(), set())
    if spec.startswith("@"):
        from pathlib import Path

        spec = Path(spec[1:]).read_text(encoding="utf-8")
    groups, tokens = set(), set()
    for word in re.split(r"[\s,]+", spec):
        word = word.strip()
        if not word:
            continue
        if word == ALL:
            groups |= {MONTHS, CARD}
        elif word in (MONTHS, CARD):
            groups.add(word)
        elif ":" in word:
            tokens.add(word)
        else:
            raise ValueError(
                f"`{word}` 를 못 읽었습니다. `months` · `all` · "
                f"미리보기가 찍어 준 `418:note:c31` 같은 말을 주세요.")
    return Picks(groups, tokens)


# ─────────────────────────────────────────────────────────────────────────────
# 3. 어떻게 보여 주나
# ─────────────────────────────────────────────────────────────────────────────

#: 한 칸의 값을 몇 글자까지 펴 놓을까. 월별 칸에는 회차가 줄바꿈으로 쌓여
#: 있어 통째로 찍으면 한 칸이 화면 열 줄을 먹는다.
VALUE_WIDTH = 72


def shorten(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= VALUE_WIDTH else text[:VALUE_WIDTH] + "…"


def lines(diffs: Sequence[Diff], *, limit: int = 40,
          show_values: bool = True, head: Optional[str] = None) -> List[str]:
    """미리보기에 찍을 줄들. 갈래로 묶고, 갈래 안에서 칸 이름으로 묶는다.

    **어느 칸의 값을 찍을지는 `shows_value` 가 정한다** — 메모처럼 길고 사람
    이야기가 섞인 칸은 몇 자짜리가 다른지만 찍는다(`clean_group_name.py` 와
    같은 판단).
    """
    if not diffs:
        return []
    rows = len({d.row_id for d in diffs})
    # 머리글을 받는 까닭: 같은 목록이 길에 따라 **다른 뜻**이다. 채우기에서는
    # `안 덮었습니다` 이고, 만들기에서는 `이 칸들이 덮입니다` 다. 세는 자와
    # 펴는 모양은 하나여야 하지만 그 한 줄까지 같을 수는 없다.
    out = [head or (f"  다른 칸 {len(diffs)}개 · 줄 {rows}개 — 시트 값이 앱 값과 "
                    f"다릅니다. **기본은 안 덮습니다.**")]
    for group in (MONTHS, CARD, HELD):
        mine = [d for d in diffs if d.group == group]
        if not mine:
            continue
        out.append(f"    ── {len(mine)}칸 · {GROUP_NOTE[group]}")
        shown = 0
        for label in sorted({d.label for d in mine}):
            same = [d for d in mine if d.label == label]
            out.append(f"       [{label}] {len(same)}칸")
            for diff in same:
                if shown >= limit:
                    break
                shown += 1
                if not show_values or not shows_value(diff.key):
                    out.append(f"         {diff.token:<18} "
                               f"지금 {len(diff.before)}자 · 시트 "
                               f"{len(diff.after)}자")
                    continue
                out.append(f"         {diff.token:<18} 지금 "
                           f"`{shorten(diff.before)}`")
                out.append(f"         {'':<18} 시트 `{shorten(diff.after)}`")
            if shown >= limit:
                break
        if len(mine) > shown:
            out.append(f"       … {len(mine) - shown}칸 더 "
                       f"(`--diff-limit 0` 으로 전부 편다)")
    return out


def summary(diffs: Sequence[Diff]) -> Dict[str, int]:
    """갈래마다 몇 칸인가 — 리포트·로그에 싣는 한 줄짜리 셈."""
    out = {MONTHS: 0, CARD: 0, HELD: 0}
    for diff in diffs:
        out[diff.group] += 1
    return out


def as_rows(diffs: Iterable[Diff]) -> List[dict]:
    """화면(업로드 미리보기)이 그대로 그릴 수 있는 모양.

    값을 싣는 칸과 길이만 싣는 칸을 `lines` 와 **같은 자**로 가른다
    (`shows_value`). 이쪽은 값이 HTTP 응답으로 나가 브라우저에 남으므로
    두 자리가 갈리면 한쪽에서 막은 것이 다른 쪽으로 샌다.
    """
    out = []
    for diff in diffs:
        item = {"row_id": diff.row_id, "key": diff.key, "label": diff.label,
                "group": diff.group, "token": diff.token,
                "can_overwrite": diff.can_overwrite}
        if shows_value(diff.key):
            item["before"] = shorten(diff.before)
            item["after"] = shorten(diff.after)
        else:
            item["before_len"] = len(diff.before)
            item["after_len"] = len(diff.after)
        out.append(item)
    return out
