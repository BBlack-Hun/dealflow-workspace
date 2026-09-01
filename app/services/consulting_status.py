"""`기업 관리` 칸이 어느 갈래인가 — **판정은 여기 한 곳에서만 한다.**

이 판단이 세 곳에 흩어져 있었다. 라우터의 KPI(`"드랍" in r["management"]`),
화면의 줄 표시(`data-dropped="{{ 1 if '드랍' in r.management }}"`), 그리고 머리글
필터가 쓰는 태그. 셋이 지금은 같은 말을 보고 있었지만, 한 곳만 고치면 나머지가
조용히 낡는다 — 위에는 `드랍 8` 이라고 적혀 있는데 칩을 누르면 7곳이 나오는
식이다. 어느 쪽이 맞는지 화면 어디에도 안 나온다.

이 저장소는 같은 사고를 반복해 겪었고 그때마다 판단을 한 곳으로 모아 고쳤다
(`deps.may_view_consulting` · `services/sheet_owner.py` ·
`services/contact_columns.py`). 같은 자리다.

**칸에 적힌 문장 그대로는 필터에 올릴 수 없다.** 원본 시트가 머리글부터
`기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로 전환 ]` 이라, 실제
값이 `드랍 : ir 진행 계약 완료 -> 기업 회생 신청 -> ir 진행 불가` 처럼 여든
자짜리 문장이다 — 34줄에 열여섯 가지가 나와 고를 것이 없고 목록 한 줄에
들어가지도 않는다. 그래서 **시트가 정해 둔 세 마디만** 본다.

**칩 넷이 무엇을 잡는가도 여기서 정한다.** `연락 기록 없음` 은 원래 월별
리마인드 칸만 봤는데, 그러면 `기업 관리` 에 적어 둔 줄이 리마인드가 비었다는
이유로 `관리 중` 과 `연락 기록 없음` 에 **동시에** 뜬다 — 칩이 나란히 붙어 한
갈래로 읽히는 자리에서 두 갈래를 섞어 놓은 셈이라 사용자에게는 틀려 보인다.
이제 두 칸을 같이 본다(`no_contact`).

그리고 값이 적힌 줄은 **하나도 안 흘린다**(`is_other`). 값이 자유 서술이라
종류가 무한하므로 값마다 칩을 세울 수는 없다 — 값별로 고르는 일은 머리글
`기업 관리 ▾` 가 이미 하고 있으니, 칩은 그보다 굵은 갈래만 맡는다.

브라우저에도 같은 규칙이 있어야 한다(`static/js/consulting.js` 의
`managementTags`). 칸을 눌러 그 자리에서 고치는 표라, 고친 직후를 다시 세는
것은 브라우저이기 때문이다. 두 벌이 되는 것은 언어가 둘이라 어쩔 수 없지만
**각 언어에 한 벌씩**이고, 아래 마디가 그대로 저쪽에도 있는지는
`tests/test_filter_columns.py` 가 지킨다.
"""
from __future__ import annotations

from typing import Iterable, List

# 시트가 정해 둔 세 마디. 화면·브라우저가 그대로 쓰는 말이라 바꾸면 양쪽이 같이 바뀐다.
MANAGED = "관리 중"
DROPPED = "드랍"
BACKUP = "백업팀 전환"
# 적혀 있기는 한데 셋 중 어느 것도 아닌 줄. 빈칸과 한 덩어리로 묶으면
# "아직 안 적었다" 와 "적었는데 분류가 안 된다" 가 구별되지 않는다.
OTHER = "기타 메모"

# 한 줄에 두 마디가 같이 있을 수 있어(`백업팀으로 전환 … 드랍`) 이것으로 잇는다.
# filters.js 가 같은 구분자로 나눠 태그 단위로 건다.
SEP = "|"


def tags(text: str, contract: bool = False) -> List[str]:
    """이 줄이 걸릴 마디들.

    `월간 계약 업무현황표` 탭은 예외다. 그 탭에서 이 칸은 `기업 관리` 가 아니라
    `계약여부` 이고, 값이 `무료`/`유료` 두 가지뿐인 **이미 추려진 값**이다.
    아래 규칙을 그대로 태우면 셋 중 어느 마디도 아니라 전부 `기타 메모` 로
    묶여, 필터에 고를 것이 하나도 남지 않는다. 적힌 그대로 쓴다.
    """
    body = text or ""
    if contract:
        value = body.strip()
        return [value] if value else []
    out = []
    if "관리" in body:
        out.append(MANAGED)
    if "드랍" in body:
        out.append(DROPPED)
    if "백업팀" in body:
        out.append(BACKUP)
    if body.strip() and not out:
        out.append(OTHER)
    return out


def tag_value(text: str, contract: bool = False) -> str:
    """줄에 실어 보낼 값(`data-f-mgmt`). 머리글 필터가 이것을 나눠 본다."""
    return SEP.join(tags(text, contract=contract))


def is_managed(text: str, contract: bool = False) -> bool:
    """`관리 중` 칩과 KPI 가 세는 줄.

    태그에서 되짚는다 — 여기서 `"관리" in text` 를 한 번 더 적으면 그것이 곧
    두 번째 규칙이 되고, 위 `tags` 를 고칠 때 같이 안 고쳐진다.
    """
    return MANAGED in tags(text, contract=contract)


def is_dropped(text: str, contract: bool = False) -> bool:
    """`드랍` 칩과 KPI 가 세는 줄.

    `백업팀으로 전환 … 드랍` 처럼 두 마디가 같이 있는 줄도 드랍이다 —
    적힌 그대로 읽는다. 그 줄은 `백업팀 전환` 으로도 걸린다.
    """
    return DROPPED in tags(text, contract=contract)


def is_other(text: str, contract: bool = False) -> bool:
    """`그 외` 칩이 세는 줄 — **적혀 있는데 관리 중도 드랍도 아닌 줄.**

    이 칸은 자유 서술이라 값의 종류가 사실상 무한하다(34줄에 열여섯 가지).
    값마다 칩을 세우면 칩이 끝없이 늘어나므로, 두 마디에 안 걸리는 나머지를
    **하나로 받는다.** 값별로 고르는 일은 머리글 `기업 관리 ▾` 가 이미 한다 —
    거기에는 `기타 메모` 와 `백업팀 전환` 이 따로 서 있고, 이 칩은 그 둘을
    묶은 굵은 갈래일 뿐이라 서로 어긋나지 않는다.

    태그에서 되짚는다. 여기서 문장을 한 번 더 읽으면 그것이 곧 두 번째
    규칙이고, 위 `tags` 를 고칠 때 같이 안 고쳐진다.

    `tags` 는 적힌 것이 있으면 반드시 하나는 돌려주므로(`기타 메모` 가 받는다),
    **값이 있는 줄은 관리 중·드랍·그 외 중 하나에 반드시 걸린다.** 예전에는
    자유 서술 줄이 어느 칩에도 안 걸려, 화면에서 찾을 방법이 없었다.
    """
    found = tags(text, contract=contract)
    return bool(found) and MANAGED not in found and DROPPED not in found


def no_contact(text: str, values: Iterable[str], contract: bool = False) -> bool:
    """`연락 기록 없음` 칩이 세는 줄 — **아무것도 안 적힌 줄.**

    예전에는 월별 리마인드 칸만 봤다. 그래서 `기업 관리` 에
    `관리 중 : 미팅 완. -> 견적서 보내기 완료.` 라고 적어 둔 줄이, 리마인드가
    비었다는 이유로 `관리 중` 과 `연락 기록 없음` 에 **동시에** 떴다. 화면에서는
    칩이 나란히 붙어 한 갈래로 읽히는데 실제로는 두 갈래를 섞어 놓은 것이라,
    관리 중인 기업이 "연락 기록 없음" 에 뜨는 것이 사용자에게는 틀려 보인다.

    `기업 관리` 가 비었는지는 `tags` 로 본다 — 적힌 것이 있으면 반드시 하나는
    나오므로 태그가 없다는 것이 곧 안 적었다는 뜻이다. 여기서 `text.strip()`
    을 다시 쓰면 계약 탭(값이 `무료`/`유료`)에서 규칙이 갈린다.
    """
    return not tags(text, contract=contract) and not contacted(values)


def contacted(values: Iterable[str]) -> bool:
    """월별 리마인드 칸에 **적힌 것이 있는가.** (`연락 기록 없음` 칩의 반대)

    앞뒤 공백을 뗀다. 원본 시트에서 올라온 값은 다듬어지지 않아서
    (`/consulting/import` 는 칸을 적힌 그대로 넣는다) 공백만 든 칸이 실제로
    생기는데, 그런 칸을 기록으로 세면 그 줄은 **아무 칸이나 고치는 순간**
    `연락 기록 없음` 으로 넘어갔다 — 브라우저는 앞뒤 공백을 떼고 보기 때문이다.
    화면에 안 보이는 차이라 고친 사람은 이유를 알 수가 없다.
    """
    return any((v or "").strip() for v in values)
