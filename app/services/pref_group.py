"""투자사 한 줄을 **선호로 어느 그룹에 넣을 것인가** — 판정이 적힌 한 곳.

## 왜 다시 묶는가

한 딜 소개 명단의 그룹 칸이 `A` 69 · `B` 1 · 빈칸 46 이었다. 그런데 그 `A` 가
**무슨 뜻인지 앱 자료 어디에도 남아 있지 않다** — `A` 69줄 중 선호 투자분야가
적힌 줄이 3, 라운드 사이즈가 3, 투자 단계가 0 이다. 만든 날짜도 전원 같고,
투자사 종류·카톡방 상태와도 안 갈린다. 시트의 `그룹` 열에 적혀 있던 글자가
그대로 들어온 것이고, 그 글자로는 아무도 나눌 수 없다.

사용자가 정했다 — **선호 투자분야와 라운드 사이즈로 다시 묶는다. 특이사항이
없는 분들은 한 갈래(`공통`)로 모은다.**

## 무엇을 읽는가 — **네 곳이고, 메모 전체가 아니다**

    sectors · round_size · stages          선호를 적으라고 만든 칸 셋
    memo 안의 `[그룹 칸에서 옮김]` 줄       예전 그룹 칸에 적혀 있던 글

넷째가 요점이다. 그룹 칸을 갈래만 담는 칸으로 바꾸면서 거기 적혀 있던 문장을
메모 뒤로 옮겼는데(`group_name.MOVED_MARK`), **그 문장이 바로 이 사람의 선호**
다. 실측 117줄 중 43줄에 남아 있고, 모양도 사람이 갈래를 적어 둔 그대로다:

    후기 | Series C ~ | M&A·로보틱스
    초기 | Pre-seed~Pre A | 딥테크
    환경·에너지 | 폐플라스틱 열분해

그룹을 다시 매기는 일에 **예전 그룹 칸의 글보다 맞는 재료는 없다.**

**메모의 나머지는 안 읽는다.** 읽어 보면 그 자리에 기업 이름이 널려 있고,
분야 낱말이 거기에 우연히 걸린다 — 실측으로 메모에서만 분야가 잡힌 6줄 중
3줄이 그것이었다(`○○바이오` 에서 `바이오`, `○○에너지` 에서 `에너지`). 그렇게
잡힌 분야는 그 투자사의 선호가 아니라 **지난주에 소개한 기업의 이름**이다.
`sourcing_note` · `tips_note` 도 같은 이유로 뺀다(전화·부재중 기록이다).

## 차례가 곧 규칙이다

    ① 옮겨 온 글의 맨 앞 딱지가 `보류` 면 `딜 소개 보류`.  **무엇보다 먼저.**
    ② 분야가 읽히면 분야 그룹.      분야가 딜의 성격을 정한다.
    ③ 아니면 라운드 그룹.           분야는 없고 단계만 적어 둔 분들이다.
    ④ 맨 앞 딱지가 `대형`·`지역 한정` 이면 그 그룹.
    ⑤ 아니면 `공통`.                특이사항이 없는 분들 — 사용자가 정한 말이다.

**①이 제일 앞인 것이 이 차례의 요점이다.** 실측 다섯 줄 중 **셋**은 선호 칸에
단계 말이 함께 적혀 있어(`후기 6/16` · `Series C 6/18` · `후기 단계`), ②③을
먼저 돌리면 `Series C 이상` 으로 들어간다. 그러면 그 그룹으로 딜을 보낼 때마다
**"비상장 투자 계획 없음" 이라고 적어 둔 분께 딜이 함께 나간다** — 안 묶는 것보다
나쁘다. 안 보낼 사람을 무슨 분야로 묶든 소용이 없으므로 그 판정이 맨 앞이다.

**④는 맨 뒤다.** `대형`·`지역 한정` 은 안 보낸다는 뜻이 아니라 조건이 있다는
뜻이고, 사용자가 나누기로 한 축은 분야와 라운드다. 그 둘로 읽히면 그쪽이 맞고,
④는 **그러지 않아 `공통` 으로 떨어질 줄만** 받는다. 실측에서도 셋 다 ②③에 한
번도 안 걸린다(걸렸다면 그쪽이 더 구체적인 정보다).

## 딱지는 **맨 앞만** 본다

옮겨 온 글은 사람이 `갈래 | 자세한 것 | 자세한 것` 꼴로 적어 두었고, 맨 앞이
그 사람의 **스스로 붙인 갈래**다. 글 아무 데서나 낱말을 찾으면 `보류 해제`
같은 말까지 걸린다. 실측으로 세 딱지 모두 **맨 앞에서만** 나오고 글 가운데서
나오는 줄은 하나도 없어, 좁게 보아 잃는 것이 없다.

**한 사람은 한 그룹이다.** 딜 소개가 그룹 단위로 나가므로(`deal_queue.targets`
→ `sheet_owner.in_group`) 두 그룹에 들면 같은 분께 같은 주에 두 번 간다. 칸도
하나뿐이라(`VcContact.group_name`) 애초에 두 값을 못 담는다.

**분야가 여럿 읽히면 글에서 먼저 나온 것**으로 넣는다. 사람이 적은 차례가 곧
그 사람의 우선순위다 — 앱이 순위를 지어내는 것보다 낫다.

## 분야 이름은 **지어내지 않는다**

`딥테크·제조` · `ESG·푸드·애그테크` 는 IR 기업의 `사업분야` 표기 그대로다.
딜 소개를 맞출 때 LLM 에게 "분야는 이 이름으로 세라" 고 시키는 목록이
그것이라(`llm_brief.sector_names`), 그룹 이름이 같은 글자여야 시킨 말과 자료가
한 낱말로 만난다. 여기서 새 이름을 지으면 **그 그룹의 수요는 어느 기업에도
안 걸린다** — 사람이 손으로 해 보다 실제로 당한 자리다.

## 낱말 사전을 두는 것이 이 저장소 방침과 어긋나지 않는가

어긋날 뻔한 자리라 선을 그어 둔다. 이 저장소는 낱말 사전으로 딜을 고르던
스크립트를 걷어냈고(`services/llm_brief.py` 머리말), 그 판단은 그대로 옳다.
다른 것은 **여기서 사전이 하는 일이 판단이 아니라는 것**이다.

  · 한 번 매기고 끝이다. 저절로 돌지 않는다.
  · 결과를 **사람이 보고 나서** 저장한다(`scripts/set_group_from_pref.py` 는
    미리보기가 기본이고 `--apply` 가 있어야 쓴다).
  · 틀리면 그 줄의 그룹 하나가 틀릴 뿐이고, 화면에서 고르면 그만이다.

`services/sector_hint.py` 가 같은 선에 서 있다 — 맞히는 비율이 53% 인 추천을
**딱지로만 띄우고 사람이 누르게** 했다. 저절로 칸에 적어 넣지 않는 한, 모자란
사전은 모자란 채로 쓸 만하다.

## 아직 제 이름이 없는 분야

분야 갈래 일곱 중 이름을 가진 것은 둘뿐이다. 나머지 다섯은 이 명단에서 한두
줄씩이라 제 그룹을 만들 만큼이 아니고, 모두 `특정분야` 로 간다 — 옆 명단이
이미 21줄에 쓰고 있는 말이다.

**자라면 그때 이름을 준다.** `group_name.NAMED` 에 이름을 한 줄 더하고 여기
표에서 `NAMED_SECTORS` 로 옮기면 된다 — 그 두 손길이 곧 사람이 한 번 보는
자리다. 열어 두면 그룹 이름이 다시 줄 수만큼 늘어난다(이 칸이 겪은 그것이다).
미리보기가 `특정분야` 안을 갈래별로 세어 찍으므로, 자란 것이 눈에 보인다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from . import group_name as gn
from . import invest_stage as st

# ── 그룹 이름 ───────────────────────────────────────────────────────────────
#
# **전부 `group_name.NAMED` 에 있어야 한다.** 없으면 다음 시트 업로드에서
# `gn.decide()` 가 문장으로 보고 메모로 옮겨 버린다 — 여기서 매겨 둔 것이
# 조용히 되돌려진다. `tests/test_pref_group.py` 가 둘을 맞춰 본다.

#: 특이사항이 없는 분들. **사용자가 정한 말이다.**
COMMON = "공통"

# ── 분야도 라운드도 아닌 축 ─────────────────────────────────────────────────
#
# 사람이 예전 그룹 칸에 스스로 달아 둔 딱지 중 분야·라운드로 안 읽히는 셋이다.
# 이름을 왜 이 말로 골랐는지는 `group_name.NAMED` 주석에 한 곳으로 적혀 있다.

#: **딜을 보내면 안 되는 곳.** 실측 다섯 줄이 `보류 | 비상장 투자 계획 없음` ·
#: `보류 | 이미 딜 소개 받는 중` 꼴이다.
#:
#: **이름일 뿐 발송을 막지 않는다.** 앱에서 실제로 막는 값은 `VcContact.status`
#: 의 `검토중단` 하나이고(`sheet_owner.is_paused` → `can_send_to`), 그룹 이름은
#: 어느 판정도 지나지 않는다. 여기서 막는 코드를 만들지 않은 것은 사용자가
#: 시킨 것이 **갈래를 세우는 데까지**이기 때문이다 — 상태 칸을 대신 바꿔 주면
#: 화면에서 목록이 통째로 사라지고, 그것은 사람이 정할 일이다.
#: `scripts/set_group_from_pref.py` 의 미리보기가 **이 그룹인데 `검토중단` 이
#: 아닌 줄이 몇인지** 늘 찍는다.
HOLD = "딜 소개 보류"

#: 규모가 큰 딜을 본다는 뜻. **라운드 단계가 아니라 금액 규모**라 사다리 이름
#: (`Series C 이상`)과 가른다 — 후기 기업이라고 다 큰 딜이 아니다.
BIG = "대형 딜"

#: 지역 조건이 있는 곳. 어느 지역인지는 사람마다 달라 이름에 못 적고, 자세한
#: 것은 메모가 말한다(`llm_brief` 가 메모를 함께 내보낸다).
REGION = "지역 한정"

#: 맨 앞 딱지 → 그룹. **둘로 나눠 둔 것이 요점이다** — `보류` 는 분야·라운드
#: 보다 **먼저** 보고, 나머지 둘은 **나중에** 본다(위 차례 설명).
#:
#: 열쇠는 `group_name.squash` 를 지난 꼴이다(공백·`|`·`·`·`,`·`/` 를 지우고
#: 소문자). `지역 한정` 과 `지역한정` 이 같은 딱지로 모이게 하려는 것이고,
#: 그 자는 그룹 이름을 알아보는 자와 **같다** — 한 저장소 안에서 같은 말인지를
#: 두 가지 자로 재면 한쪽만 고쳐지는 날이 온다.
HOLD_LABELS = {"보류": HOLD}
AXIS_LABELS = {"대형": BIG, "지역한정": REGION}

#: 분야는 읽혔는데 아직 제 이름이 없는 갈래. 옆 명단이 쓰던 말 그대로다.
SMALL = "특정분야"

#: 라운드만 적어 둔 분들의 갈래. 이름이 `invest_stage.LADDER` 의 칸 이름을
#: 그대로 쓴다 — 그래야 이름만 보고 어디부터 어디까지인지 알 수 있다.
EARLY = "Seed~Pre-A"
MID = "Series A~B"
LATE = "Series C 이상"

#: 사다리의 어느 칸이 어느 갈래인가. **`invest_stage.LADDER` 를 통째로 덮는다**
#: — 한 칸이라도 빠지면 그 단계만 적어 둔 줄이 갈 데가 없어 `공통` 으로 샌다.
ROUND_BANDS: Sequence[Tuple[str, Tuple[str, ...]]] = (
    (LATE, ("SeriesC", "Pre-IPO")),
    (MID, ("SeriesA", "SeriesB")),
    (EARLY, ("Pre-seed", "Seed", "Pre-A")),
)

# ── 분야를 읽는 낱말 ────────────────────────────────────────────────────────
#
# 낱말은 **실측한 값에 실제로 있던 말**이다(선호 투자분야 21줄 · 옮긴 글 43줄).
# 지어낸 말은 넣지 않았다 — 안 걸리는 낱말은 사전만 길게 한다.
#
# **`금융` 은 일부러 뺐다.** 이 바닥에서 `신기술금융본부` · `금융기관` 은
# 부서·기관 이름이지 핀테크 수요가 아니다. 실측에서 그 한 줄이 그대로 걸렸다.
# 같은 이유로 `플랫폼` · `IT` 처럼 아무 데나 붙는 말도 안 넣는다.

#: 제 이름을 가진 분야. 이름은 IR 기업 `사업분야` 표기 그대로다.
NAMED_SECTORS: Sequence[Tuple[str, Tuple[str, ...]]] = (
    ("딥테크·제조", ("딥테크", "반도체", "소부장", "팹리스", "방산", "제조",
                     "소재", "부품", "장비", "우주", "항공", "이차전지", "배터리")),
    ("ESG·푸드·애그테크", ("환경", "친환경", "재생", "폐플라스틱", "열분해",
                            "농식품", "농업", "수산", "해양", "푸드", "에너지",
                            "ESG")),
)

#: 아직 제 이름이 없는 분야 — 잡히면 `특정분야` 로 간다. 갈래 이름을 그대로
#: 두는 것은 **미리보기가 `특정분야` 안을 갈래별로 세어 찍기** 위해서다.
#: 어느 갈래가 자랐는지 안 보이면 이름을 줄 때를 알 수 없다.
OTHER_SECTORS: Sequence[Tuple[str, Tuple[str, ...]]] = (
    ("모빌리티·물류", ("로보틱스", "로봇", "드론", "자율주행", "모빌리티",
                       "휴머노이드", "물류")),
    ("헬스케어·바이오", ("바이오", "헬스케어", "헬스", "의료", "제약", "진단")),
    ("AI·SaaS·데이터", ("인공지능", "SaaS", "데이터센터", "데이터", "클라우드",
                         "ICT", "AI")),
    ("커머스·라이프스타일", ("소비재", "콘텐츠", "커머스", "리테일", "엔터",
                             "유통")),
    ("핀테크·블록체인", ("핀테크", "블록체인", "결제")),
)

SECTORS = tuple(NAMED_SECTORS) + tuple(OTHER_SECTORS)

#: 그룹 이름을 가진 분야 갈래(위 `NAMED_SECTORS` 의 이름들).
_NAMED_SECTOR_NAMES = frozenset(name for name, _ in NAMED_SECTORS)

#: **이 판정이 내놓을 수 있는 이름 전부.** 검사가 이것을 `group_name.KNOWN`
#: 과 맞춘다 — 하나라도 빠지면 그 그룹이 다음 업로드에 메모로 옮겨진다.
OUTPUTS = ((COMMON, SMALL, EARLY, MID, LATE)
           + tuple(name for name, _ in NAMED_SECTORS)
           + tuple(HOLD_LABELS.values()) + tuple(AXIS_LABELS.values()))

# ── 무엇을 읽는가 ───────────────────────────────────────────────────────────
#
# 선호를 적으라고 만든 칸 셋. `memo` 는 여기 없다 — 아래 `moved_text()` 가
# **그 안의 옮겨 온 줄만** 따로 꺼낸다(모듈 설명 참고).
PREF_FIELDS = ("sectors", "round_size", "stages")

#: `초기` · `후기` 처럼 **어느 칸인지는 모르지만 방향은 분명한** 말.
#: `invest_stage` 는 이것을 일부러 안 쓴다 — 거기서는 `stages` 에 틀린 단계를
#: 적으면 없던 `단계 불일치` 경고가 생기기 때문이다. **여기서는 다르다**:
#: 틀려도 그룹 하나가 어긋날 뿐이고 사람이 보고 고친다. 실측에서 이 말만 적힌
#: 줄이 열 넘게 있어, 안 읽으면 그만큼이 통째로 `공통` 으로 샌다.
_ROUGH: Sequence[Tuple[str, str]] = (
    (LATE, r"후기|성장\s*단계|성숙\s*단계|상장\s*직전|late\s*stage|레이터"),
    (MID, r"중기"),
    (EARLY, r"초기|얼리\s*스테이지|early\s*stage|첫\s*라운드"),
)


@dataclass(frozen=True)
class Decision:
    """이 줄을 어느 그룹에 넣을 것인가.

    `group` 은 **늘 값이 있다** — 아무것도 안 읽히면 `공통` 이다. 그룹을 비워
    두는 갈래는 없다.

    `why` 는 무엇을 보고 그렇게 정했는지다(`분야` · `라운드` · `없음`).
    `found` 는 실제로 읽어낸 말이라 미리보기가 근거를 찍을 수 있고,
    `sector` 는 `특정분야` 로 모인 줄이 **원래 어느 갈래였는지**다 — 이것이
    없으면 그 덩어리 안에서 무엇이 자라는지 볼 수 없다.
    """

    group: str
    why: str
    found: Tuple[str, ...] = ()
    sector: Optional[str] = None


BY_SECTOR = "분야"
BY_ROUND = "라운드"
#: 사람이 스스로 달아 둔 맨 앞 딱지를 그대로 읽었다(`보류` · `대형` · `지역 한정`).
BY_LABEL = "딱지"
BY_NONE = "없음"


def moved_text(memo: Optional[str]) -> str:
    """메모에서 **예전 그룹 칸에서 옮겨 온 줄만** 꺼낸다.

    표시는 `group_name.MOVED_MARK` 하나다 — 옮겨 붙인 쪽과 꺼내는 쪽이 같은
    글자를 보아야 한다. 여기 다시 적으면 표시를 고치는 날 이쪽이 낡는다.

    여러 줄일 수 있다(시트가 여러 번 올라오면 붙는 자리가 는다). 한 칸 띄워
    잇는다 — 붙여 버리면 앞 줄의 끝 낱말과 뒷 줄의 첫 낱말이 한 낱말이 된다.
    """
    out = []
    for line in (memo or "").splitlines():
        text = line.strip()
        if text.startswith(gn.MOVED_MARK):
            out.append(text[len(gn.MOVED_MARK):].strip())
    return " ".join(part for part in out if part)


def lead_label(text: str) -> str:
    """옮겨 온 글의 **맨 앞 딱지** — `갈래 | 자세한 것` 에서 `갈래` 쪽.

    모양을 지워 돌려준다(`group_name.squash`) — `지역 한정` 과 `지역한정` 이
    같은 딱지로 모여야 한다. 구분 기호는 `|` 뿐이다: 실측의 옮겨 온 글 43줄이
    전부 그 기호로 갈라져 있고, `·` 나 `,` 는 **딱지 안에서** 쓰인다
    (`환경·에너지` · `M&A·로보틱스`). 그것까지 구분 기호로 보면 딱지가 반토막
    난다.
    """
    return gn.squash((text or "").split("|")[0])


def blob(row) -> str:
    """판정이 읽는 글 전부 — 선호 칸 셋 + 옮겨 온 줄.

    **차례가 뜻을 갖는다.** 분야가 여럿 읽히면 '글에서 먼저 나온 것' 으로
    고르는데, 사람이 선호 칸에 적은 말이 메모에서 옮겨 온 말보다 앞에 서야
    한다 — 선호 칸은 지금 적은 것이고 옮겨 온 글은 예전 것이다.
    """
    parts = [(getattr(row, field, None) or "") for field in PREF_FIELDS]
    parts.append(moved_text(getattr(row, "memo", None)))
    return " ".join(part.strip() for part in parts if part.strip())


def sector_of(text: str) -> Optional[Tuple[str, str]]:
    """글에서 읽어낸 분야 — `(갈래 이름, 걸린 낱말)`. 없으면 `None`.

    **가장 먼저 나온 낱말**이 이긴다. 낱말 차례가 아니라 **글에서의 자리**로
    고르는 것이 요점이다 — `로봇, AI, 소부장` 은 로봇이 먼저다.

    같은 자리에서 둘이 걸리면 **긴 낱말**이 이긴다(`헬스케어` 가 `헬스` 를
    덮는다). 안 그러면 표에 적은 차례가 판정을 좌우한다.
    """
    lowered = text.lower()
    best = None
    for name, words in SECTORS:
        for word in words:
            at = lowered.find(word.lower())
            if at < 0:
                continue
            key = (at, -len(word))
            if best is None or key < best[0]:
                best = (key, name, word)
    return None if best is None else (best[1], best[2])


def round_of(text: str) -> Optional[Tuple[str, Tuple[str, ...]]]:
    """글에서 읽어낸 라운드 갈래 — `(갈래 이름, 읽어낸 단계들)`.

    **단계 말이 먼저다.** `invest_stage.stages_of` 가 `Series C 이상` ·
    `시리즈 B-C` · `PreIPO` · `Seed단계` 를 한 벌로 읽어 주고 범위도 펴 준다 —
    표기 갈림을 여기서 다시 다루지 않는다.

    **여러 칸에 걸치면 가장 높은 칸**으로 둔다. 실측에서 그런 줄이 8개였는데,
    낮은 쪽으로 두면 `Seed~Pre-A`(4줄뿐인 작은 갈래)에 후기까지 보는 분들이
    섞여 **그 갈래가 실제보다 커 보인다** — 자리를 나누는 비례가 그만큼
    흔들린다. 높은 쪽으로 두면 15줄짜리 갈래가 두어 줄 느는 정도다.

    단계 말이 하나도 없으면 `초기`·`후기` 같은 **방향 말**을 본다(`_ROUGH`).
    """
    names = st.stages_of(text)
    if names:
        for band, members in ROUND_BANDS:
            if any(name in members for name in names):
                return band, tuple(names)
    for band, pattern in _ROUGH:
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            return band, (found.group(0),)
    return None


def decide(row) -> Decision:
    """이 줄을 어느 그룹에 넣을 것인가. 차례는 모듈 설명 참고.

    **줄 하나만 본다.** 다른 줄이나 DB 를 안 본다 — 그래야 미리보기와 실제가
    같은 계획을 지나고, 검사도 지어낸 줄 하나로 지을 수 있다.
    """
    note = moved_text(getattr(row, "memo", None))
    label = lead_label(note)

    # ① **안 보낼 사람이 먼저다.** 실측 다섯 줄 중 셋은 선호 칸에 단계 말이
    #    함께 적혀 있어, 이 판정이 뒤로 가면 `Series C 이상` 에 섞여 들어간다.
    if label in HOLD_LABELS:
        return Decision(HOLD_LABELS[label], BY_LABEL, found=(label,))

    text = blob(row)
    if not text:
        return Decision(COMMON, BY_NONE)

    found_sector = sector_of(text)
    if found_sector is not None:
        name, word = found_sector
        group = name if name in _NAMED_SECTOR_NAMES else SMALL
        return Decision(group, BY_SECTOR, found=(word,), sector=name)

    found_round = round_of(text)
    if found_round is not None:
        band, names = found_round
        return Decision(band, BY_ROUND, found=names)

    # ④ 분야·라운드로 안 읽힌 줄만 받는다. 그 둘로 읽히면 그쪽이 더 구체적이다.
    if label in AXIS_LABELS:
        return Decision(AXIS_LABELS[label], BY_LABEL, found=(label,))

    return Decision(COMMON, BY_NONE)
