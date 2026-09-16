"""시트에만 있던 **선호 메모 두 칸**을 `llm_brief` 가 읽는 칸으로 옮긴다.

`심사역 리스트(공통양식)` 탭에는 사람이 손으로 적어 온 글 칸이 둘 있다.

    기타          어떻게 이어져 있는 분인가 — `8/11 딜소싱 네트워크 소개` ·
                  `6/18 전화 완료 / 6/26부터 문자로 딜 소개` · `6/26 카톡 재연결`
    대화내역 메모  주고받은 말이 통째로 쌓인다 — 무엇을 보시겠다 하셨는지가 여기 있다

**둘 다 `llm_brief` 에 안 닿는다.** 고르는 쪽이 읽는 칸은 `sectors` · `stages` ·
`round_size` 와 **메모 셋**(`memo` · `sourcing_note` · `tips_note`) 뿐이다
(`services/llm_brief.INVESTOR_FIELDS`). 그런데

  · `기타` 는 넣는 길에 따라 **`notes["etc"]` 로 가거나**(`import_investor_list`
    의 `NOTES`) **아예 안 읽힌다**(웹 업로드 `sheet_import` 에는 이 칸이 없다).
    `notes` 는 내보내는 칸 목록에 없으므로 어느 쪽이든 안 나간다.
  · `대화내역 메모` 는 `memo` 로 가기는 하지만(`find_column(["메모"])`) 그것도
    CLI 로 넣었을 때뿐이고, **덮어쓰기**라 앱에서 사람이 적어 둔 글을 밀어낸다.

## 어느 칸으로 보내나 — 둘을 **한 칸에 뭉치지 않는다**

    기타         → `sourcing_note`
    대화내역 메모 → `memo`

`기타` 를 `sourcing_note` 로 보내는 이유는 **그 칸이 이미 같은 말을 담고 있어서**
다. 화면 이름은 `딜소싱 참여 투자사` 지만 실제로 들어 있는 값은 자유 문장이고
(`models.VcContact.sourcing_note` 주석의 실측 예: `전화완료 / 부재중 7명`),
`기타` 에 적힌 것도 정확히 그 결이다 — 딜소싱 네트워크에 어떻게 소개했고 전화·
문자·카톡 중 무엇으로 이어져 있는가. 같은 말은 같은 칸에 모여야 `llm_brief` 가
한 번에 읽는다.

`대화내역 메모` 를 `memo` 로 보내는 이유는 **앱이 이미 그렇게 부르고 있어서**다.
이 명단의 배치는 `대화내역 메모` 라는 머리글을 `memo` 칸에 걸어 두었다
(`contact_columns.INVESTOR_MONTHLY_LAYOUT` 의 `tail`). 여기서 다른 칸으로 보내면
**같은 시트 칸이 넣는 길에 따라 두 칸으로 갈린다** — 화면에서 고친 글과 시트에서
옮긴 글이 서로 다른 자리에 앉는다.

**둘을 `memo` 하나로 합치지 않는다.** 성격이 다르다 — 한쪽은 연결 경로고 다른
쪽은 대화 내용이다. 합치면 다시 돌렸을 때 어느 글이 어느 칸에서 왔는지 가릴 수가
없고, 두 칸이 각각 몇 줄인지도 셀 수 없게 된다.

## 덮지 않는다 · 두 번 돌려도 안 늘어난다

붙이는 법은 `group_name.append_memo` 와 **같다**. 줄바꿈으로 뒤에 잇고, 앞에
어디서 왔는지 표시를 세우고, **이미 있는 말이면 안 붙인다.** 같은 것을 두 군데에
적지 않으려고 겹침 판정(`group_name.squash`)도 그쪽 것을 그대로 부른다 — 시트는
여러 번 올라오고 이 스크립트도 여러 번 돈다.

## 껍데기는 안 가져간다

`-` · `.` · `없음` 처럼 **사람이 칸을 비워 두지 못해 적어 둔 글자**는 옮기면
메모만 길어지고 고르는 데는 아무 말도 보태지 못한다. `is_shell()` 이 가른다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from . import group_name

# 옮겨 붙인 글 앞에 서는 표시. `group_name.MOVED_MARK`(`[그룹 칸에서 옮김]`) 과
# 같은 결로 짓되 **어느 칸에서 왔는지**를 적는다 — 두 칸이 서로 다른 앱 칸으로
# 가므로, 표시가 같으면 되돌아볼 때 둘을 구별할 수가 없다.
MARK_ETC = "[시트 기타 칸에서 옮김]"
MARK_TALK = "[시트 대화내역 메모 칸에서 옮김]"


@dataclass(frozen=True)
class Source:
    """시트의 글 칸 하나 — **어디서 읽어 어디로 넣고 뭐라 표시하나**."""

    label: str      # 시트 머리글 (찾는 말이자 화면에 적는 말)
    field: str      # VcContact 의 칸
    mark: str       # 붙일 때 앞에 세우는 표시


# **여기 적힌 것만 옮긴다.** 6~27열(달마다의 딜소개·IR요청·미팅)은 담지 않는다 —
# 앱이 이미 `ContactActivity` 행으로 갖고 있어서, 옮기면 같은 이력이 메모에 한 벌
# 더 쌓인다.
SOURCES = (
    Source("기타", "sourcing_note", MARK_ETC),
    Source("대화내역 메모", "memo", MARK_TALK),
)

#: 손대는 앱 칸. 되돌리기 파일이 뜨는 칸이자 `--restore` 가 되돌리는 칸이다.
FIELDS = tuple(s.field for s in SOURCES)

# 껍데기로 보는 말. **비워 두지 못해 적어 둔 글자**다.
_SHELL_WORDS = {
    "없음", "없슴", "없슴니다", "해당없음", "해당사항없음", "내용없음",
    "무", "미정", "미상", "불명", "확인불가",
    "x", "o", "n/a", "na", "null", "none", "-", "--", ".", "..",
}

# 껍데기인지 볼 때 지우는 글자 — 말이 아니라 **칸을 채우려고 찍은 것**들.
_FILLER = re.compile(r"[\s\-\.\_ㆍ·,/|~()\[\]{}<>:;'\"]+")


def is_shell(value: Optional[str]) -> bool:
    """이 글이 **아무 말도 안 하는가.**

    빈 칸은 여기서 가리지 않는다(`is_empty`). 둘을 한 판정으로 묶으면 "원래
    비어 있던 줄" 과 "뭔가 적혀 있었는데 껍데기라 걸러낸 줄" 이 한 수로 뭉쳐,
    몇 줄을 걸렀는지를 셀 수가 없다.

    남는 글자가 **한 자 이하**면 껍데기로 본다. 두 자부터는 남긴다 — 실제 시트에
    `거부` 처럼 두 자로 뜻이 서는 값이 있다.
    """
    text = (value or "").strip()
    if not text:
        return False
    bare = _FILLER.sub("", text)
    if len(bare) <= 1:
        return True
    return bare.lower() in _SHELL_WORDS


def is_empty(value: Optional[str]) -> bool:
    """빈 칸 · 공백만 있는 칸."""
    return not (value or "").strip()


def append(current: Optional[str], value: str, mark: str) -> Optional[str]:
    """옮길 글을 `current` 뒤에 붙인 결과. 붙일 것이 없으면 `None`(그대로 둔다).

    `group_name.append_memo` 와 **같은 규칙**이다. 겹침은 `group_name.squash` 로
    본다 — 붙일 때 표시가 앞에 서므로 글자 그대로 비교하면 두 번째 실행에서 제
    글을 못 알아보고 한 벌을 더 붙인다.
    """
    text = (value or "").strip()
    if not text:
        return None
    have = (current or "").strip()
    squashed = group_name.squash(text)
    if squashed and squashed in group_name.squash(have):
        return None
    line = f"{mark} {text}"
    return f"{have}\n{line}" if have else line


# `decide()` 가 내놓는 판정. 세는 쪽이 이 값을 열쇠로 쓴다.
EMPTY = "empty"    # 시트 칸이 비어 있다 — 아무 일도 안 한다
SHELL = "shell"    # 껍데기다 — 안 가져간다
SAME = "same"      # 이미 같은 말이 그 칸에 있다 — 안 붙인다 (두 번 돌려도 그대로)
ADD = "add"        # 붙인다


@dataclass(frozen=True)
class Decision:
    """시트 칸 하나를 앱 칸 하나에 어떻게 할 것인가.

    `value` 는 **새 값**이다. `None` 은 "그 칸을 그대로 둔다" — 비우라는 뜻이
    아니다. 이 스크립트는 **어떤 경우에도 칸을 비우지 않는다.**
    """

    action: str
    value: Optional[str] = None

    @property
    def changes(self) -> bool:
        return self.action == ADD


def decide(cell: Optional[str], current: Optional[str], mark: str) -> Decision:
    """시트 칸 `cell` 을 앱 칸의 현재 값 `current` 에 붙일 것인가."""
    if is_empty(cell):
        return Decision(EMPTY)
    if is_shell(cell):
        return Decision(SHELL)
    merged = append(current, cell, mark)
    if merged is None:
        return Decision(SAME)
    return Decision(ADD, value=merged)


# ── 시트 줄과 앱 줄을 **어떻게 잇나** ───────────────────────────────────────
#
# 열쇠는 **투자사명 + 이름**이다. 개발 DB(같은 워크북을 앱의 임포터로 넣어 만든
# 364줄)에 세 후보를 다 대 보고 골랐다 — 옮길 값이 있는 시트 292줄 기준:
#
#     투자사명 + 이름   정확히 한 줄 292 · 여러 줄   0 · 못 찾음   0
#     이름만            정확히 한 줄 243 · 여러 줄  49 · 못 찾음   0
#     투자사명만        정확히 한 줄 207 · 여러 줄  68 · 못 찾음  17
#
# **이름만으로 이으면 49줄이 갈린다.** 이 저장소는 이미 같은 데서 데인 적이
# 있다 — 한 이름이 셋이라 남의 방으로 딜 소개가 나갔다(`import_investor_list`
# 모듈 설명의 `sourcing_link`). 선호 메모를 엉뚱한 투자사에 붙이면 그다음 주
# 딜 고르기가 그 말을 그대로 믿는다.
#
# 투자사명만으로는 한 투자사에 여러 심사역이 있어 애초에 갈린다.
#
# **번호(휴대폰)를 안 쓴다.** 앱 전체를 대조할 때 쓰는 열쇠는 번호지만, 이
# 탭에는 번호 칸이 아예 없다(2행 머리글에 `휴대폰` 이 없다).
#
# 시트마다 `㈜`·`(주)`·공백을 넣고 빼는 법이 달라서 그것만 지우고 본다 —
# `import_investor_list.merge_key` 와 같은 자다.

def match_key(name: Optional[str], firm: Optional[str]) -> Optional[tuple]:
    """`(투자사명, 이름)` 열쇠. 이름이 없으면 `None`(이을 수 없는 줄).

    투자사명이 빈 줄도 **열쇠를 만든다.** 시트에 18줄 있고 앱 쪽도 같이 비어
    있어서 `("", 이름)` 끼리 맞는다. 비었다고 이름만으로 넓히지는 않는다 —
    그러면 그 18줄만 동명이인 위험을 다시 진다.
    """
    from . import sheet_import

    who = re.sub(r"\s+", "", (name or "").strip())
    if not who:
        return None
    where = sheet_import.normalize_company_name(firm or "")
    return (re.sub(r"\s+", "", where), who)
