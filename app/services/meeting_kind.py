"""미팅 한 갈래를 **셋으로 가른다** — 요청 · 확정 · 완료. ★ 판정은 여기 한 곳이다.

## 무엇이 잘못됐었나

시트 머리글에 `미팅` 글자만 있으면 전부 `contact_activities.kind = 'meeting'`
한 칸으로 눌렸다. 그런데 실제 머리글은 제각각이다.

    3~5월 미팅 요청
    6~9월 미팅 진행 여부 · IR 요청기업 미팅 안내전화 · 미팅완료 투자사
    미팅확정/미팅완료
    미팅 요청 / IR 요청기업 미팅 안내전화 TEL

**미팅을 청한 것**과 **실제로 만난 것**이 한 칸에 담기면, 읽는 쪽은 둘을 가릴
길이 없어 전부 "미팅했다" 로 읽는다. 운영 54줄을 내용으로 갈라 보면 요청이
완료보다 세 배 넘게 많았고, 그 때문에 만난 적 없는 담당자가 화면에서
`1차 미팅` 으로 서고 엑셀의 `미팅(누적)` 에도 세어졌다. 고객사가 그걸 짚었다.

## 왜 여기 한 곳인가

머리글을 보고 갈래를 정하는 일은 **세 자리**에서 필요하다.

    시트를 읽어 넣을 때      `services/sheet_import.detect_kind`
    이미 들어온 줄을 가를 때  `scripts/resplit_meeting_kind.py`
    달마다 늘어나는 칸       `ContactColumn.kind` (머리글 뒷말이 그대로 있다)

이 저장소가 되풀이해 덴 자리가 바로 이것이다 — 같은 결정이 두 곳에 적히면
한쪽이 낡고, 그때부터 **앞으로 들어오는 줄과 이미 들어와 있는 줄이 다르게
갈린다**(`services/company_names` 가 같은 까닭으로 한 곳이 되었다). 그래서
말(키워드)도 판정도 이 모듈 하나가 쥔다.

**사다리의 어느 칸인지는 여기서 정하지 않는다.** 그건 사다리를 쥔
`services/deal_stage` 의 일이다 — 그쪽은 이 모듈의 갈래 이름만 읽는다.

## 갈래를 왜 셋으로 하나

    요청  `meeting_request`  미팅을 청했다. **아직 안 만났다.**
    확정  `meeting_set`      날짜가 잡혔다. 그래도 **아직 안 만났다.**
    완료  `meeting_done`     실제로 만났다.

둘(요청/완료)로 하면 `미팅확정` 5줄이 갈 곳이 없다. 요청에 넣으면 날짜가
잡혔다는 사실이 사라지고, 완료에 넣으면 **지금 고치는 바로 그 거짓말**(안
만났는데 만났다고 서는 것)을 다시 만든다. 이 앱은 이미 이 셋을 구분한다 —
`Meeting.status` 가 `planned`(확정) 와 `done`(완료) 로 갈려 있고,
`deal_stage._from_meeting` 이 그 둘을 다른 칸으로 올린다. 시트에서 온 줄만
못 가릴 까닭이 없다.

## `meeting` — 아직 안 가른 줄

옛 값 `meeting` 은 **지우지 않는다.** 이미 들어와 있는 줄이 그 값이고,
가르는 일은 스크립트가 사람 손으로 한 번 도는 일이라(`scripts/
resplit_meeting_kind.py`) 코드가 올라간 순간부터 갈라지는 것이 아니다.

그 사이에 옛 줄의 뜻을 낮춰 잡으면 **진짜로 미팅한 사람들이 화면에서 먼저
빠진다.** 그건 지금 버그의 반대 방향이라 더 나쁘다(`deal_stage` 가
`pending`·`failed` 를 안 세는 것과 같은 결의 판단이다). 그래서 옛 값은
가르기 전까지 **지금 뜻 그대로** 두고, 읽는 자리마다 아래 `MET` 이 그 사실을
한 줄로 말한다.

## 말(키워드)을 고를 때 지킨 것

* 말은 **`미팅` 에 붙여서** 본다. `미팅 요청 완료` 의 `완료` 를 "만났다" 로
  읽으면 안 된다 — 요청을 보낸 줄이다. 그래서 `완료` 가 아니라 `미팅 완료`
  를 찾는다.
* **`여부` 가 붙은 머리글은 갈래를 못 정한다.** `미팅 진행 여부` 는 묻는
  칸이지 답하는 칸이 아니다. 답은 칸 안에 있으므로 내용에게 넘긴다.
* 머리글이 **두 갈래를 함께 이고 있으면**(`미팅확정/미팅완료`) 역시 내용에게
  넘긴다. 한쪽으로 몰면 그 칸의 절반이 틀린다.
* 내용에 **안 했다는 말**(`미진행`·`취소`·`무산` …)이 있으면 그 내용은
  갈래를 못 정한 것으로 본다. 모르는 채로 두는 것이, 안 만난 것을 만났다고
  적는 것보다 낫다.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Sequence, Tuple

#: 갈래 이름. `contact_activities.kind` 에 그대로 들어간다.
REQUEST = "meeting_request"
SET = "meeting_set"
DONE = "meeting_done"

#: **아직 안 가른 줄.** 옛 값이고 새로 만들지 않는다(가를 수 없을 때만 남는다).
LEGACY = "meeting"

LABELS: Dict[str, str] = {
    REQUEST: "미팅 요청",
    SET: "미팅 확정",
    DONE: "미팅 완료",
    LEGACY: "미팅(안 가름)",
}

#: 낮은 → 높은. 머리글과 내용이 다른 말을 하면 **멀리 간 쪽**을 고른다
#: (`미팅 요청` 칸에 `8/20 미팅완료` 라고 적힌 줄은 만난 줄이다).
LADDER: Tuple[str, ...] = (REQUEST, SET, DONE)
_RANK: Dict[str, int] = {key: i for i, key in enumerate(LADDER)}

#: **미팅 이야기가 오간 줄 전부.** 옛 값을 포함한다.
#:
#: 반응이 있었는지(`services/cadence.has_reaction_since`), 대시보드의
#: `IR 미팅 요청 투자사`(`services/dashboard`), 팀 현황의 최근 활동 — 셋 다
#: "청했든 만났든 말이 오갔다" 를 세는 자리라 갈래를 가리지 않는다.
ALL: Tuple[str, ...] = (LEGACY, REQUEST, SET, DONE)

#: **실제로 만났다**는 갈래. 지금은 완료 하나뿐이다.
HELD: Tuple[str, ...] = (DONE,)

#: **세는 자리가 미팅으로 읽는 갈래** — 완료 + 아직 안 가른 옛 줄.
#:
#: 엑셀·화면의 `미팅(최근)`·`미팅(누적)` 이 이것을 센다. 요청·확정은 여기
#: 없다 — 그게 이번에 고치는 것이다. 옛 값이 끼어 있는 것은 위 모듈 설명의
#: 까닭이고, 스크립트를 돌리고 나면 남는 것은 **내용으로도 가릴 수 없었던
#: 줄뿐**이다(스크립트가 그 수를 찍어 준다).
MET: Tuple[str, ...] = (DONE, LEGACY)

# ── 말 ──────────────────────────────────────────────────────────────────────
#
# 위에서 아래로 본다. 여러 갈래가 걸리면 그건 '못 정함' 이지 첫 번째가 아니다
# (아래 `_hits` 가 걸린 것을 전부 모은다).
_WORDS: Sequence[Tuple[str, Tuple[str, ...]]] = (
    (DONE, ("미팅완료", "미팅 완료", "미팅진행", "미팅 진행",
            "미팅함", "미팅했", "미팅 했", "미팅 마침", "미팅 실시")),
    (SET, ("미팅확정", "미팅 확정", "미팅예정", "미팅 예정",
           "미팅일정", "미팅 일정", "미팅잡", "미팅 잡")),
    (REQUEST, ("미팅요청", "미팅 요청", "미팅안내", "미팅 안내",
               "안내전화", "안내 전화", "미팅제안", "미팅 제안",
               "미팅문의", "미팅 문의")),
)

#: 안 했다는 말. 내용에 이것이 있으면 **그 내용으로는 갈래를 못 정한다.**
#: (`미팅 완료 안함` 을 완료로 읽으면 안 만난 사람이 만난 것으로 선다)
_NEGATIVE: Tuple[str, ...] = ("미진행", "미완료", "안함", "안 함", "못함",
                              "못 함", "취소", "무산", "불발", "거절")

#: 묻는 머리글. 답은 칸 안에 있으므로 머리글로는 정하지 않는다.
_ASKS = ("여부",)

#: `미팅` 글자가 아예 없는 글. 이 모듈이 손댈 줄이 아니다.
_MEETING = re.compile(r"미\s*팅")


def _norm(text: str) -> str:
    return (text or "").lower()


def _hits(text: str) -> set:
    """이 글에 걸리는 갈래 전부. 없으면 빈 집합."""
    low = _norm(text)
    return {kind for kind, words in _WORDS if any(w in low for w in words)}


def mentions_meeting(text: str) -> bool:
    """`미팅` 이야기가 있기는 한가. 없으면 스크립트가 손대지 않는다."""
    return bool(_MEETING.search(_norm(text)))


def _strongest(hits: set) -> Optional[str]:
    return max(hits, key=lambda k: _RANK[k]) if hits else None


def of_header(text: str) -> Optional[str]:
    """시트 머리글 → 갈래. **못 정하면 `None`.**

    `ContactColumn.kind`(머리글 뒷말)도 그대로 넣을 수 있다 — 같은 글자다.

    못 정하는 경우가 둘이다. 둘 다 "머리글이 답을 안 들고 있다" 는 뜻이라
    부르는 쪽이 내용을 보게 한다(`refine`).

      · `여부` 가 붙었다 — 묻는 칸이다(`미팅 진행 여부`)
      · 두 갈래를 함께 이고 있다 — `미팅확정/미팅완료`
    """
    low = _norm(text)
    if any(ask in low for ask in _ASKS):
        return None
    hits = _hits(low)
    return next(iter(hits)) if len(hits) == 1 else None


def of_content(text: str) -> Optional[str]:
    """칸에 적힌 글 → 갈래. **못 정하면 `None`.**

    머리글과 달리 여러 말이 걸릴 수 있다(`미팅 요청 → 8/20 미팅완료`). 그때는
    **멀리 간 쪽**이다 — 뒤에 적힌 사실이 앞의 계획을 덮는다.

    안 했다는 말이 섞여 있으면 못 정한 것으로 본다(위 `_NEGATIVE`).
    """
    low = _norm(text)
    if any(no in low for no in _NEGATIVE):
        return None
    return _strongest(_hits(low))


def refine(kind: str, content: str) -> str:
    """머리글이 정한 갈래 + 칸에 적힌 글 → **이 줄의 갈래.**

    시트에서 읽어 넣을 때 칸마다 부른다. 머리글이 이미 가른 칸이면 그것이
    바탕이고, 그 칸의 글이 **더 멀리 간 말**을 하면 글을 따른다 — `미팅 요청`
    칸에 `8/20 미팅완료` 라고 적어 둔 줄은 만난 줄이다.

    머리글이 못 가른 칸(`meeting`)은 글이 정한다. 글도 말이 없으면 `meeting`
    그대로 둔다 — 지어내지 않는다.
    """
    keys = {k for k in (kind if kind in _RANK else None,
                        of_content(content)) if k}
    return _strongest(keys) or LEGACY
