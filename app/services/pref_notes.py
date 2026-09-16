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

## 옮기기 전에 **우리 쪽 사람 이름을 가린다**

`기타` 는 원래 살림 칸이라 **팀원 이름이 그대로 적혀 있다**(`○○○님 카톡방 임시
관리` · `이후 ○○○님 연결`). 시트에만 있을 때는 아무 일도 아니었는데, `memo`
칸으로 옮기는 순간 `llm_brief` 가 그 글을 읽어 내보낸다.

**`llm_brief` 는 이것을 못 막는다.** 저쪽이 지우는 사람 이름은 **그 줄 자신의
것**뿐이다(`llm_brief._scrub`). 남의 이름까지 지우지 않기로 한 것도 거기 적힌
실측 때문이다 — 세 글자 이름을 300여 줄에 그냥 대 보니 **남의 멀쩡한 문장 261곳**
에 우연히 들어맞았다. 그 판단은 그대로 옳다. 여기서 다른 것은 **대는 이름이 팀원
몇 명뿐**이라는 것이고, 그래서 앞뒤를 볼 여유가 생긴다.

**지우지 않고 가린다**(`TEAM_MASK`). 줄째 안 옮기면 그 줄의 쓸모 있는 딜소싱
경로까지 같이 잃는다 — `[팀원]님 카톡방 임시 관리` 는 여전히 읽히는 말이다.

## 껍데기는 안 가져간다

`-` · `.` · `없음` 처럼 **사람이 칸을 비워 두지 못해 적어 둔 글자**는 옮기면
메모만 길어지고 고르는 데는 아무 말도 보태지 못한다. `is_shell()` 이 가른다.

## 이 방법이 **못 거르는 것**

이름 목록은 앱이 아는 것에서만 나온다(`NAME_SOURCES`). 그러므로

  · **앱에 계정도 담당 표시도 없는 팀원 이름은 못 거른다.** 새로 온 사람,
    계정을 안 만든 사람, 시트에만 별명으로 적힌 사람이 그렇다.
  · **성을 뗀 이름은 호칭·직함이 붙었거나 대화 로그의 발화자 자리일 때만**
    가린다(아래 `team_pattern`). 그냥 문장에 섞여 있으면 못 알아본다 — 두 자라
    남의 멀쩡한 말에 박힐 위험이 더 크다.
  · **투자사 쪽 사람 이름은 여기서 안 가린다.** 아래 `NAME_SOURCES` 설명 참고.

사용자가 이 한계를 알고 고른 길이다. 미리보기도 마지막 줄에 이 사실을 찍는다 —
안 적으면 "자동으로 다 걸러진다" 고 믿게 된다.
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


def already_in(current: Optional[str], value: Optional[str]) -> bool:
    """`value` 가 이미 `current` 안에 있는가 — **모양을 지우고** 본다.

    판정은 `group_name.squash` 를 그대로 부른다. 붙일 때 표시가 앞에 서므로
    글자 그대로 비교하면 두 번째 실행에서 제 글을 못 알아본다.
    """
    text = group_name.squash((value or "").strip())
    return bool(text) and text in group_name.squash((current or "").strip())


def append(current: Optional[str], value: str, mark: str) -> Optional[str]:
    """옮길 글을 `current` 뒤에 붙인 결과. 붙일 것이 없으면 `None`(그대로 둔다).

    `group_name.append_memo` 와 **같은 규칙**이다 — 덮지 않고 줄바꿈으로 잇고,
    앞에 어디서 왔는지 표시를 세우고, 이미 있는 말은 안 붙인다.
    """
    text = (value or "").strip()
    if not text or already_in(current, text):
        return None
    have = (current or "").strip()
    line = f"{mark} {text}"
    return f"{have}\n{line}" if have else line


# `decide()` 가 내놓는 판정. 세는 쪽이 이 값을 열쇠로 쓴다.
EMPTY = "empty"      # 시트 칸이 비어 있다 — 아무 일도 안 한다
SHELL = "shell"      # 껍데기다 — 안 가져간다
BLANK = "blanked"    # **가리고 나니 남는 말이 없다** — 안 가져간다
SAME = "same"        # 이미 같은 말이 그 칸에 있다 — 안 붙인다 (두 번 돌려도 그대로)
ADD = "add"          # 붙인다


@dataclass(frozen=True)
class Decision:
    """시트 칸 하나를 앱 칸 하나에 어떻게 할 것인가.

    `value` 는 **새 값**이다. `None` 은 "그 칸을 그대로 둔다" — 비우라는 뜻이
    아니다. 이 스크립트는 **어떤 경우에도 칸을 비우지 않는다.**

    `masked` 는 이 칸에서 **가린 자리 수**, `text` 는 가린 뒤의 글이다. 둘 다
    미리보기가 찍는 자리라 판정과 함께 돌려준다 — 미리보기가 따로 다시 가리면
    본 것과 들어가는 것이 갈린다.
    """

    action: str
    value: Optional[str] = None
    masked: int = 0
    text: str = ""
    #: 가리기 **전** 글이 이미 그 칸에 있고, 그 글에 이름이 들어 있다.
    #: 먼저 들어온 판에 이름이 그대로 남아 있다는 뜻이라 따로 센다.
    stale: bool = False

    @property
    def changes(self) -> bool:
        return self.action == ADD


def decide(cell: Optional[str], current: Optional[str], mark: str,
           pattern=None) -> Decision:
    """시트 칸 `cell` 을 앱 칸의 현재 값 `current` 에 붙일 것인가.

    **가리는 일이 여기 한 번만 일어난다.** 미리보기도 저장도 이 함수를 지나므로,
    미리 본 글과 실제로 들어가는 글이 같다.
    """
    if is_empty(cell):
        return Decision(EMPTY)
    # 껍데기 판정은 **가리기 전**에 한다. 껍데기에는 이름이 들어 있을 수 없고,
    # 가린 뒤에 보면 `[팀원]` 이 남아 있어 껍데기로 안 보인다.
    if is_shell(cell):
        return Decision(SHELL)
    safe, masked = mask_team(cell, pattern)
    if masked and not has_words_left(safe):
        # 이름 말고는 거의 없던 줄. 옮길 값이 없다 — **따로 센다.**
        return Decision(BLANK, masked=masked, text=safe)
    # **가리기 전 글**이 이미 그 칸에 있으면 안 붙인다.
    #
    # 다른 길로 먼저 들어온 값이다 — `import_investor_list` 는 `대화내역 메모`
    # 를 `memo` 에 **덮어쓴다.** 그 뒤에 가린 판을 한 벌 더 붙이면 같은 말이 두
    # 번 서고, 먼저 들어온 판에는 이름이 그대로 남아 있어 **가린 뜻도 안 산다.**
    # 실측으로 이 경우가 110줄 있었다.
    #
    # 먼저 들어온 판을 여기서 고쳐 쓰지는 않는다 — 이 도구는 덮지 않는다.
    # 대신 미리보기가 그런 줄이 몇인지 찍는다(`stale`).
    if already_in(current, cell):
        return Decision(SAME, masked=masked, text=safe, stale=bool(masked))
    merged = append(current, safe, mark)
    if merged is None:
        return Decision(SAME, masked=masked, text=safe)
    return Decision(ADD, value=merged, masked=masked, text=safe)



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


# ── 우리 쪽 사람 이름 가리기 ───────────────────────────────────────────────
#
# 지운 자리는 **비우지 않고 표시한다.** 그냥 빼면 `님 카톡방 임시 관리` 처럼
# 문장이 멀쩡해 보여서, 뭔가 지워졌다는 것을 읽는 쪽도 사람도 알 수 없다.
#
# `llm_brief.MASK`(`[가림]`) 와 **일부러 다른 말을 쓴다.** 저쪽은 "이 줄이
# 누구인지 가린다" 이고 여기는 "우리 쪽 사람 이름이 있던 자리" 다. 뜻이 다르면
# 말도 달라야 한다 — `[팀원]님 카톡방 임시 관리` 는 읽으면 무슨 일인지 알겠는데
# `[가림]님 카톡방 임시 관리` 는 누가 가려진 것인지가 사라진다. 모양(`[…]`)은
# `[그룹 칸에서 옮김]` · `MARK_ETC` 와 같은 결로 맞춘다.
TEAM_MASK = "[팀원]"

# 이름을 **어디서 얻나.** `(표, 칸)` — 여기 적힌 것이 전부다.
#
# **한 곳에만 적는다.** 목록이 두 군데로 갈리면 한쪽이 낡고, 낡은 쪽을 쓰는
# 미리보기가 "안 걸러진다" 를 못 보여 준다.
#
#     users.name              계정이 있는 팀원. 가장 확실하다.
#     sheet_owners.assignee_name  명단의 담당 팀원 **원문**. 계정이 아직 없어도
#                             여기 남아 있다(`SheetOwner` 설명) — 계정만 보면
#                             그 사람이 통째로 빠진다.
#     vc_contacts.assignee_name   시트의 `담당자` 원문. 우리 쪽 연결 담당이라
#                             팀원 이름이고, 값이 몇 가지뿐이라 대기에 싸다.
#
# **`vc_contacts.name`(투자사 쪽 사람 297명)은 넣지 않는다.** 실측으로 정했다.
#
#   · **얻는 것이 없다.** 같은 워크북의 `기타`·`대화내역 메모` 를 훑어 보니
#     **다른 줄의 투자사 이름이 박힌 자리는 0곳**이었다(유일하게 걸린 한 이름은
#     팀원이라 아래 목록이 이미 덮는다). 제 줄 자신의 이름은 `llm_brief._scrub`
#     이 이미 지운다 — `대화내역 메모` 67줄이 그 경우였다.
#   · **잃는 것이 크다.** 그 297명을 넣고 같은 글을 훑으면 부분문자열로 428자리가
#     걸리는데 그중 **241자리가 한글 낱말 한가운데**였다 — `카톡 재연결` 의
#     `재연`, `부사장님` 의 `장님`, `전무님` 의 `전무` 같은 것들이다. 가리면
#     `카톡 [팀원]결` 이 된다. `llm_brief` 가 261곳을 재고 그만둔 바로 그 방식이고,
#     같은 자리에서 같은 수가 나왔다.
#
# 아래 `team_pattern` 의 앞뒤 보기가 저 241자리를 막기는 한다. 그래도 안 넣는다 —
# **막아야 할 것이 없는데 막는 장치에 기대는 것**이라, 이름이 하나 늘 때마다
# 위험만 늘고 얻는 것은 0 이다.
NAME_SOURCES = (
    ("users", "name"),
    ("sheet_owners", "assignee_name"),
    ("vc_contacts", "assignee_name"),
)

# 사람 이름 **뒤에 붙는 말**. 이것이 뒤따르면 앞의 덩어리는 이름이다.
#
# 조사(`이`·`가`·`은`·`는`)는 **안 넣는다.** 넣어 보고 실측으로 견주니 가려지는
# 자리가 한 곳도 안 늘었다(기타 154 · 대화내역 12 로 같았다). 얻는 것이 없는데
# 한 글자 흔한 말이 판정에 끼면 헛맞음만 는다.
_TITLES = (
    "님", "씨", "선생", "기사",
    "부장", "차장", "과장", "대리", "팀장", "실장", "본부장", "센터장",
    "이사", "상무", "전무", "부사장", "사장", "회장", "대표",
    "심사역", "수석", "책임", "선임", "주임", "매니저", "파트너",
    "소장", "원장", "국장", "처장", "위원", "컨설턴트",
)
_TITLE_ALT = "|".join(sorted(_TITLES, key=len, reverse=True))

# 카톡 대화를 통째로 붙여 넣은 칸의 **발화자 자리**. `오후 5:15 민진 넵 …` 처럼
# 시각 다음 한 덩어리가 말한 사람이다.
#
# 이 자리를 따로 보는 이유는 **호칭이 안 붙어서**다. `대화내역 메모` 131줄 중
# 67줄이 이 꼴이고, 거기서 팀원의 성 뗀 이름이 35번 발화자로 선다 — 앞뒤만
# 보아서는 못 잡고, 그렇다고 두 자 이름을 아무 데서나 잡으면 헛맞음이 는다.
# **시각이 바로 앞에 있다는 것**이 그 자리가 이름 자리라는 증거다.
_SPEAKER = r"(?:오전|오후)\s*\d{1,2}:\d{2}\s+"

# 이름으로 받아들이는 모양. 한글 두~네 자.
_NAME_SHAPE = re.compile(r"^[가-힣]{2,4}$")

# `담당자` 칸에 이름이 여럿 적히거나 직함이 붙어 온다 — `김샘플 팀장` · `샘플/샘플`.
_SPLIT = re.compile(r"[\s/,·|()\[\]]+")


def team_names(values) -> tuple:
    """적힌 대로의 담당자 값들 → **대 볼 이름 목록**. 한 곳에서만 만든다.

    `담당자` 칸은 자유 글자라 `김샘플 팀장` · `샘플가/샘플나` 처럼 온다. 쪼개서
    **한글 두~네 자**만 남기고 직함은 버린다 — `팀장` 을 이름으로 대면 남의
    문장에 든 `팀장` 이 통째로 가려진다.
    """
    out = []
    for value in values:
        for token in _SPLIT.split((value or "").strip()):
            if _NAME_SHAPE.match(token) and token not in _TITLES:
                if token not in out:
                    out.append(token)
    return tuple(out)


def team_pattern(names):
    """이름 목록 → 그물 하나. 없으면 `None`.

    ## 헛맞음을 어떻게 줄이나 — **앞뒤를 본다**

    한글 이름은 두세 자라 보통 글자에 그냥 박힌다. 그래서 세 갈래로 나눠 잡는다.

        ① 온 이름 (`김샘플`)   앞이 한글이 아니고, **뒤가 한글이 아니거나**
                               호칭·직함이다. `김샘플님` · `김샘플 /` 는 잡고
                               `김샘플리` 같은 낱말 속은 안 잡는다.
        ② 성 뗀 이름 (`샘플`)  두 자라 더 엄하게 본다 — **호칭·직함이 뒤따를
                               때만.** 실제 시트에 `○○부장` 꼴로 여덟 번 있다.
        ③ 발화자 자리          카톡 로그에서 **시각 바로 뒤**의 성 뗀 이름.
                               호칭이 안 붙는 자리라 ②로는 못 잡는다.

    **왼쪽은 늘 본다**(`(?<![가-힣])`). 이름이 낱말 한가운데서 시작하는 일은
    없으므로, 이것만으로도 가장 흔한 헛맞음이 걸러진다.

    같은 워크북으로 재 보니 순진하게 부분문자열로 지우면 201자리가 가려지는데,
    그중 35자리가 ③의 발화자 자리였고 나머지는 이 그물과 같았다. 즉 **앞뒤를
    보면서도 잡을 것은 다 잡는다.**

    성은 **세 자 이름에서만** 뗀다. 두 자 이름에서 떼면 한 자가 남아 아무 말에나
    맞고, 네 자는 성이 한 자인지 두 자인지(`남궁…`) 알 수가 없다.
    """
    full = [n for n in names if n]
    short = {n[1:] for n in names if len(n) == 3}
    if not full:
        return None
    # 긴 것부터 — 짧은 것을 먼저 잡으면 긴 이름의 나머지가 남는다
    # (`llm_brief._org_pattern` 과 같은 이유다).
    full_alt = "|".join(re.escape(n) for n in sorted(full, key=len, reverse=True))
    parts = []
    if short:
        short_alt = "|".join(re.escape(n) for n in sorted(short, key=len, reverse=True))
        # ③ 발화자 자리. 시각은 **다시 적어 놓아야** 하므로 따로 잡아 둔다.
        parts.append(rf"(?P<stamp>{_SPEAKER})(?P<spoke>{short_alt})(?![가-힣])")
    parts.append(rf"(?<![가-힣])(?:{full_alt})(?:(?={_TITLE_ALT})|(?![가-힣]))")
    if short:
        parts.append(rf"(?<![가-힣])(?:{short_alt})(?={_TITLE_ALT})")
    return re.compile("|".join(parts))


def mask_team(text: Optional[str], pattern) -> tuple:
    """`(가린 글, 가린 자리 수)`. **미리보기와 저장이 이 함수 하나를 쓴다.**

    둘이 다른 길로 가리면 미리보기에서 본 것과 실제로 들어가는 것이 달라져
    사람이 확인할 자리가 사라진다.
    """
    value = text or ""
    if pattern is None or not value:
        return value, 0
    found = 0

    def swap(match) -> str:
        nonlocal found
        found += 1
        # 발화자 자리는 **시각을 그대로 두고** 이름만 바꾼다. 시각을 같이 지우면
        # 대화가 언제 오갔는지가 사라진다(`llm_brief._scrub` 도 날짜는 안 지운다).
        stamp = match.groupdict().get("stamp") if match.groupdict() else None
        return f"{stamp}{TEAM_MASK}" if stamp else TEAM_MASK

    return pattern.sub(swap, value), found


def has_words_left(text: Optional[str]) -> bool:
    """가리고 **남은 말이 있는가.**

    이름 말고는 거의 없던 줄이 있다. 가리고 나면 `[팀원]` 만 남는데, 그것을
    옮기면 메모에 표시만 쌓이고 고르는 데 보탤 말은 한 마디도 없다.
    """
    left = (text or "").replace(TEAM_MASK, " ")
    return not is_empty(left) and not is_shell(left)
