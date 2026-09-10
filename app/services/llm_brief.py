"""딜 소개 상대를 맞추는 데 쓸 자료 — **꺼내기만** 한다.

왜 꺼내기만 하는가
------------------
매주 "딜 소개할 기업 N곳" 을 고르는 일을 앱 밖 스크립트가 **낱말을 세어**
하고 있었다. `딥테크`·`AI`·`초기` 를 사전에 적어 두고 몇 번 나오는지 센다.
사전에 없는 말은 안 잡혀서 `콘텐츠`·`에듀테크`·`프롭테크` 를 손으로 계속
더해야 했고, **"규모가 좀 더 큰 곳 위주로"** 같은 문장은 아예 못 읽는다.
낱말 사전은 앞으로도 계속 모자랄 것이다 — 사람이 쓰는 말이 사전보다 넓다.

그래서 **맞추는 일은 LLM 에 맡기고 앱은 자료만 꺼낸다.** 여기에 점수·추천·
정렬을 넣으면 사전을 세던 때와 같은 자리로 돌아온다 — 앱이 먼저 걸러 낸
것은 LLM 이 볼 수조차 없기 때문이다. 이 파일에 판단이 없는 것이 요점이다.

왜 투자사는 번호로만 나가는가
-----------------------------
이 자료는 **앱 밖으로**(다른 LLM 서비스로) 나간다. 투자사 담당자의 이름·
투자사명·연락처·이메일·카톡방 이름은 맞추는 데 필요 없다 — 무엇을 좋아하고
어느 라운드를 보는지만 있으면 된다. 필요 없는 것을 내보내지 않는 것이
가장 확실한 보호다.

번호(`V-31`)는 **되찾을 수 있는 열쇠**다. LLM 이 `V-31` 로 답해 오면
`resolve()` 가 앱 안에서 다시 이름으로 바꾼다 — 그 길이 없으면 번호로
내보내는 순간 답을 못 쓴다.

**기업도 이름 없이 번호로 나간다.** 처음에는 이름을 넣었다 — 소개하려고 모아
둔 자료라 이름이 없으면 읽히지 않는다고 보았다. 그런데 맞추는 데 쓰이는 것은
분야·단계·요약·규모이지 이름이 아니고, 답은 `C-7` 로 돌아와 `resolve()` 가 앱
안에서 이름으로 되돌린다 — **사람이 잃는 것이 없다.** 개발 자료로 재 보니
IR 기업 344곳 중 한줄소개·요약 문장 안에 자기 이름이 또 적힌 곳은 5곳뿐이라,
이름 칸을 빼도 남는 설명이 그대로다.

바로 위 문단이 말하는 "필요 없는 것을 내보내지 않는 것이 가장 확실한 보호" 가
**기업 쪽에서는 지켜지지 않고 있었다.** 이제 양쪽이 같은 규칙이다.

왜 금액이 구간으로 나가는가
--------------------------
이름 칸을 빼고 나니 **남은 숫자가 이름 노릇을 하고 있었다.** 실제 자료로 재
보니 나가는 317곳 중 분야+단계+수치 조합이 그 기업 하나만 가리키는 곳이
123곳(38.8%)이었고, **수치가 있는 114곳만 보면 112곳(98.2%)**이 유일했다.
값 하나만으로도 특정됐다 — 최근 매출값이 있는 82곳 중 49곳이 그 값 하나로
유일했다. 이름을 뺀 뜻이 숫자에서 그대로 풀리는 셈이다.

그래서 금액 넷은 **정확한 숫자 대신 구간**으로 나간다(`amount_band`). 맞추는
쪽이 판단하는 것은 "이 기업이 이 투자사 규모에 맞는가" 이고, 시드 규모인지
시리즈B 규모인지가 갈리면 그 판단은 그대로 선다 — 정확한 숫자는 애초에
필요하지 않았다. 경계는 지어내지 않고 기업구분(`series`) 칸이 이미 적어 둔
단계 정의에서 가져왔다(`AMOUNT_EDGES` 참고).

무엇을 이미 보냈는지도 함께 나간다
----------------------------------
맞추는 쪽이 제일 먼저 하는 일이 **이미 보낸 것을 빼는 것**이다. 그 사실이
자료에 없으면 LLM 은 지난달에 보낸 기업을 다시 고르고, 사람이 그것을 매번
손으로 걸러야 한다. 그래서 투자사 줄마다 `sent_before` 로 **이미 보낸 기업
번호**를 싣는다 — 번호만이다. 회차 제목·문구 같은 자유 문장은 싣지 않는다
(안 내보내는 것이 가리는 것보다 낫다).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import IrCompany, User
from . import sheet_owner
# 방이 살아 있는지는 **대시보드가 세는 그 판정**을 그대로 쓴다. 여기에 다시
# 적으면 화면 숫자와 어긋난다 — 투자사 관리 현황 117명 · 대시보드 123명으로
# 갈렸던 사고가 판정을 두 벌로 적어 둔 탓이었다(`readiness.py` 도 같은 것을
# 읽는다).
#
# `room_confirmed` 는 갈래 이름을 `_room_state` 에서 받아 오고, `ROOM_LABELS`
# 는 화면(투자사 관리 현황)이 그 칸을 거를 때 쓰는 **바로 그 말**이다 — 자료가
# "카톡방 확인됨" 이라고 적고 화면이 같은 말로 링크를 걸어야, 눌렀을 때 실제로
# 그 줄만 남는다(표가 모르는 말로 걸면 눌러도 아무것도 안 걸러진다).
from .dashboard import ROOM_CONFIRMED, ROOM_LABELS, room_confirmed, room_href

# 번호 앞에 붙는 글자. 투자사와 기업이 섞여 오므로 무엇의 번호인지가 필요하다.
INVESTOR_PREFIX = "V"
COMPANY_PREFIX = "C"

# 저장은 백만원이다(`IrCompany` 참고). 화면은 억으로 보여주지만 여기서는
# **바꾸지 않고 단위만 밝힌다** — 두 표기를 같이 내보내면 언젠가 둘이
# 어긋나고, 어긋난 쪽을 읽은 답은 100배가 틀어진 채 돌아온다.
#
# **구간 표기도 같은 단위다**(`AMOUNT_EDGES`). `1000~5000` 은 백만원 기준이고
# 억으로 고쳐 적지 않는다 — 한 자료 안에 두 단위가 섞이는 순간, 어느 쪽으로
# 읽었는지에 따라 답이 100배 틀어진다.
AMOUNT_UNIT = "백만원"

#: 금액을 나누는 **자리**(단위는 `AMOUNT_UNIT` = 백만원). 10억 · 50억 · 100억.
#:
#: **여기 말고 다른 데 적지 마라.** 화면도 자료도 검사도 이 값 하나를 읽는다 —
#: 경계를 두 곳에 적으면 반드시 갈리고, 갈린 자료는 겉보기에 멀쩡하다
#: (`PICK_COUNT` · 투자사 수 117명·123명이 같은 사고였다).
#: `tests/test_llm_brief.py` 가 이 값을 바꿔 보고 자료와 설명이 따라오는지 본다.
#:
#: ## 왜 이 자리인가
#:
#: 기업구분(`series`) 칸이 **자기 규모를 이미 적어 두고 있다** — 실제 값이
#: `Angel, Seed (누적투자금 0, 년매출액 3억미만)` · `Pre A, Bridge (누적투자금
#: 5억미만…)` · `Series A (누적투자금 10억이상, 년매출액 10억이상)` ·
#: `Series B (누적투자금 20억 이상, 년매출액 50억이상)` ·
#: `Series C (누적투자금 50억 이상, 년매출액 80억이상)` 이다. 경계를 지어내지
#: 않고 **그 단계 정의에서 가져왔다**: 10억(A 라인) · 50억(B~C 라인) ·
#: 100억(그 위). 투자사가 보는 것도 같은 눈금이라, 시드 규모인지 시리즈B
#: 규모인지는 이것만으로 갈린다.
#:
#: ## 왜 더 잘게 나누지 않았나
#:
#: 개발 자료(317곳)로 분포를 재고 정했다. 더 잘게 나눌수록 구간 조합이 다시
#: 그 기업 하나만 가리킨다 — 3억·10억·20억·50억 넷으로 나눠 보면 유일한 곳이
#: 116곳으로 거의 안 줄었고, 지금 셋으로는 105곳이다(정확한 숫자일 때 123곳).
#: 반대로 너무 거칠면 한 구간에 다 몰려 맞추는 데 못 쓴다 — 셋으로 나눈 지금
#: 가장 큰 구간이 각 칸의 50~64%다.
AMOUNT_EDGES = (1000, 5000, 10000)

#: 정확히 `0` 인 값의 표. **없는 것과 갈라 두려고 따로 둔다** — 없는 칸은
#: 자료에 아예 안 실리고(`_fill`), 0 은 이 표로 실린다. 0 을 맨 아래 구간
#: (`~1000`)에 넣으면 "아직 매출이 없다" 와 "얼마인지 모른다" 가 한 칸이 되어,
#: 읽는 쪽이 없는 사실을 되찾을 길이 사라진다.
ZERO_BAND = "0"

#: 구간으로 내보내는 칸. 이 넷만 숫자가 아니라 구간 이름으로 나간다.
AMOUNT_FIELDS = ("revenue_recent", "funding_total", "raise_target", "pre_value")


def amount_band(value) -> Optional[str]:
    """정확한 금액 대신 **구간 이름**. 값이 없으면 `None`.

    ## 왜 정확한 숫자를 안 보내나

    이름을 빼도 **숫자로 특정된다.** 개발 자료로 재 보니 나가는 317곳 중
    분야+단계+수치 조합이 그 기업 하나만 가리키는 곳이 123곳(38.8%)이었고,
    수치가 있는 114곳만 보면 112곳(98.2%)이 유일했다. 값 하나만으로도
    특정됐다 — `revenue_recent` 값이 있는 82곳 중 49곳, `funding_total`
    42곳 중 22곳, `pre_value` 52곳 중 16곳, `raise_target` 81곳 중 8곳이
    그 값 하나로 유일했다. 이름을 뺀 뜻이 숫자에서 그대로 풀린다.

    맞추는 데 필요한 것은 **규모의 자리**다 — 시드 규모인가 시리즈B 규모인가.
    구간이면 그 판단이 그대로 서고, 특정은 안 된다.

    ## 경계에 딱 걸리는 값

    **앞 숫자는 포함, 뒤 숫자는 미포함**(`1000` → `1000~5000`,
    `5000` → `5000~10000`). 한쪽으로 못 박아 두지 않으면 같은 값이 사람마다
    다른 구간으로 읽히고, 그 어긋남은 자료만 봐서는 안 보인다.

    ## 표 모양

    `~1000` (0 초과 1000 미만) · `1000~5000` · `5000~10000` · `10000+`,
    그리고 정확히 0 은 `0`. 맨 아래를 `0~1000` 으로 적지 않는 것은 그 표가
    `0` 과 헷갈리기 때문이다.
    """
    if value is None or value == "":
        return None
    if value == 0:
        return ZERO_BAND
    index = 0
    while index < len(AMOUNT_EDGES) and value >= AMOUNT_EDGES[index]:
        index += 1
    if index == 0:
        return f"~{AMOUNT_EDGES[0]}"
    if index == len(AMOUNT_EDGES):
        return f"{AMOUNT_EDGES[-1]}+"
    return f"{AMOUNT_EDGES[index - 1]}~{AMOUNT_EDGES[index]}"


def amount_bands() -> List[str]:
    """나올 수 있는 구간 이름을 **작은 것부터**. 설명문이 이것을 읽는다.

    손으로 또 적지 않는다 — `AMOUNT_EDGES` 를 고치면 설명도 같이 따라와야
    하고, 따라오지 않으면 사람이 읽는 표와 실제로 나가는 표가 갈린다.
    """
    edges = AMOUNT_EDGES
    return [ZERO_BAND] + [amount_band(v) for v in
                          (edges[0] - 1, *edges)]


#: 시트에서 옮겨 온 지난 발송 기록의 종류(`ContactActivity.kind`).
#: `services/deal_history.py` 가 같은 값을 읽는다 — 기업별 '최근에 보냄' 표시가
#: 세는 것과 여기서 세는 것이 같은 기록이어야 한다.
ACTIVITY_KIND = "deal_intro"

#: 이력에 담는 기업 번호의 **최대 개수**(투자사 한 명당, 최근 것부터).
#:
#: 회차가 쌓이면 한 사람의 이력만 수백 개가 된다. 300여 명분이면 자료가
#: 통째로 무거워지는데, 정작 쓰이는 것은 "이건 이미 보냈다" 는 사실뿐이라
#: 오래된 것까지 다 실을 값어치가 없다. **자른 사실은 자료 안에 밝힌다**
#: (`sent_before_more`) — 조용히 자르면 읽는 쪽이 그게 전부인 줄 안다.
HISTORY_LIMIT = 60

#: 한 투자사에게 **몇 곳을 골라 달라고 할지.**
#:
#: **이 수를 여기 말고 다른 데 적지 마라.** 프롬프트도 화면도 이 값을 읽는다
#: — 두 곳에 적으면 한쪽만 고쳐지고, 사람은 8곳을 시켰다고 믿는데 10곳이
#: 온다. `tests/test_llm_brief.py` 가 이 값을 바꿔 보고 프롬프트가 따라오는지
#: 확인한다.
PICK_COUNT = 8

#: 답이 어떤 모양이어야 하는지 보여 주는 한 줄.
#:
#: **화면의 붙여넣기 칸 예시(`templates/deals.html`)와 같은 문장이다.** 둘이
#: 갈리면 사람이 보는 예시와 LLM 이 받은 지시가 달라지고, 그러면
#: [번호 → 이름 찾기] 가 못 읽는 모양으로 답이 온다(맨숫자는 일부러 안 읽는다).
ANSWER_EXAMPLE = "V-31 님께는 C-7, C-12 를 소개하시면 좋겠습니다"


def note() -> str:
    """자료 맨 앞에 싣는 **읽는 법**.

    상수가 아니라 함수인 것은 **구간 표(`AMOUNT_EDGES`)를 여기서 읽기**
    때문이다. 문장에 경계를 손으로 적어 두면 경계를 고치는 날 설명만 옛말이
    되고, 그러면 읽는 쪽은 없는 구간을 찾게 된다.
    """
    return ("투자사도 기업도 이름 없이 번호로만 나갑니다. 답하실 때 V-… · C-… 를 "
            "그대로 적어 주시면 앱에서 누구인지 다시 찾을 수 있습니다. "
            # **무엇이 담겼는지**를 자료가 스스로 말한다. 몇 곳인지는 `scope` 가
            # 적고, 여기서는 그 수가 왜 그런지를 적는다 — 담기지 않은 투자사가
            # 있다는 사실을 모르면 "왜 이 투자사가 없지" 를 알 길이 없다.
            f"투자사 목록에는 **{ROOM_LABELS[ROOM_CONFIRMED][0]}인 카톡방이 있는 "
            "본인 담당 투자사만** 담겨 있습니다 — 지금 딜 소개를 실제로 보낼 수 "
            "있는 곳입니다. 방이 없거나 확인되지 않은 곳, 다른 담당자의 투자사는 "
            "담기지 않았습니다(맞춰 드려도 보낼 수가 없습니다). 몇 곳이 담겼는지는 "
            "`scope` 에 적혀 있습니다. "
            f"금액 단위는 {AMOUNT_UNIT} 입니다. "
            # 금액은 **정확한 숫자가 아니다.** 그 사실을 밝히지 않으면 읽는
            # 쪽이 구간 표를 무슨 뜻인지 몰라 그냥 버리거나, 더 나쁘게는 앞
            # 숫자를 값으로 읽는다.
            f"{' · '.join(AMOUNT_FIELDS)} 는 정확한 금액이 아니라 **구간**으로 "
            f"나갑니다({' · '.join(amount_bands())}). "
            f"앞 숫자는 포함, 뒤 숫자는 미포함입니다(예: {AMOUNT_EDGES[0]} 은 "
            f"`{amount_band(AMOUNT_EDGES[0])}` 입니다). "
            f"구간 표가 `{ZERO_BAND}` 인 칸은 정확히 0 이라는 뜻이고, "
            "**칸이 아예 없으면 값을 모른다**는 뜻입니다 — 이 둘은 다른 "
            "사실입니다. "
            "규모가 맞는지만 보시면 됩니다. 정확한 숫자는 필요하지 않습니다. "
            "`sent_before` 는 그 투자사에게 **이미 보낸** 기업 번호입니다 — "
            "실제로 발송된 것만 셉니다(만들다 만 것·실패·취소는 세지 않습니다). "
            f"최근 {HISTORY_LIMIT}개까지만 싣고, 더 있으면 `sent_before_more` 에 "
            "남은 개수를 적습니다. 이력의 번호 중에는 아래 기업 목록에 없는 것이 "
            "있을 수 있습니다 — 지금은 소개할 수 없게 된 기업이며, 그래도 "
            "**이미 보낸 것**이므로 다시 고르지 마세요. "
            "`sent_before_unmatched` 는 옛 기록에는 남아 있지만 지금 기업 목록에서 "
            "찾지 못한 곳의 **개수**입니다 — 그만큼 더 보냈다는 뜻입니다.")


def investor_ref(contact_id: int) -> str:
    return f"{INVESTOR_PREFIX}-{contact_id}"


def company_ref(company_id: int) -> str:
    return f"{COMPANY_PREFIX}-{company_id}"


# `V-031` · `v-31` · `C - 7` 을 모두 같은 번호로 읽는다.
#
# **자릿수를 채우지 않는다.** `V-031` 로 내보내면 번호가 1000 을 넘는 순간
# 같은 사람을 가리키는 표기가 둘이 된다(`V-031` 과 `V-1000` 은 폭이 다르다).
# 대신 **읽을 때 앞의 0 을 버려서** 어느 쪽으로 답해 와도 찾아 준다.
#
# **맨숫자(`31`)는 일부러 안 받는다.** 답에는 `30억` · `3곳` · `2026년` 처럼
# 번호가 아닌 숫자가 널려 있다. 그것까지 번호로 읽으면 엉뚱한 사람이 목록에
# 뜨고, 그 목록은 겉보기에 멀쩡하다 — 틀린 것을 알아채기 어려운 쪽이 나쁘다.
_REF = re.compile(rf"(?<![0-9A-Za-z])([{INVESTOR_PREFIX}{COMPANY_PREFIX}])"
                  r"\s*-\s*0*(\d+)", re.IGNORECASE)


def parse_refs(text: str) -> Dict[str, List[int]]:
    """붙여 넣은 글에서 번호만 골라낸다 — `{"investors": [...], "companies": [...]}`.

    사람은 LLM 의 답을 **통째로** 붙여 넣는다("V-031 님께 C-7, C-12 를 …").
    번호만 뽑아 달라고 하면 손으로 옮겨 적다 틀린다. 순서는 나온 순서대로
    두되 같은 번호는 한 번만 담는다 — 한 답 안에서 같은 사람이 여러 번
    거론되는 것은 흔한 일이고, 그때마다 줄이 늘면 읽기 어렵다.
    """
    found: Dict[str, List[int]] = {"investors": [], "companies": []}
    for prefix, digits in _REF.findall(text or ""):
        key = "investors" if prefix.upper() == INVESTOR_PREFIX else "companies"
        number = int(digits)
        if number and number not in found[key]:
            found[key].append(number)
    return found


# ── 내보내는 칸 ─────────────────────────────────────────────────────────────
#
# **여기 적힌 것만 나간다.** 모델의 칸을 통째로 훑어 내보내면 칸이 하나 늘
# 때마다 조용히 같이 나가고, 그중 하나가 이름이면 그게 곧 유출이다.
# `tests/test_llm_brief.py` 가 여기 없는 칸에 표식을 심어 두고 결과에 그
# 표식이 섞여 나오는지 본다 — 칸이 늘어도 검사가 먼저 걸린다.
INVESTOR_FIELDS = ("sectors", "round_size", "stages",
                   "sourcing_note", "memo", "tips_note", "interest_level")
# **`name` 이 없다 — 일부러다.** 맞추는 데 쓰이는 것은 분야·단계·요약·규모이고,
# 이름은 `resolve()` 가 앱 안에서 되돌린다(모듈 설명 참고).
#: **금액 넷은 구간으로 나간다**(`AMOUNT_FIELDS` · `amount_band`). 목록을 여기
#: 다시 적지 않는다 — 한쪽만 늘면 새 금액 칸이 정확한 숫자로 새어 나간다.
COMPANY_FIELDS = ("sector_major", "series", "one_liner", "summary") + AMOUNT_FIELDS


# ── 자유 문장에 섞여 든 이름·연락처 ────────────────────────────────────────
#
# 칸을 고르는 것만으로는 부족하다. **메모 안에 그대로 적혀 있는** 경우가 있다.
# 실데이터 274곳을 꺼내 훑어 보니 4곳의 메모에 자기 투자사명·연락처·이메일이
# 문장째 들어 있었고("○○벤처스 이사님", "010-… 로 연락 요망"), 전화번호 모양이
# 2곳, 이메일 모양이 1곳에 있었다. 칸만 막으면 이것이 그대로 나간다 — 번호로만
# 내보내는 뜻이 그 한 줄에서 사라진다.
#
# **사람 이름·연락처는 그 줄 자신의 것만 지운다.** 남의 것까지 전부 지우려면
# 300여 명의 값을 300여 줄에 다 대 봐야 하는데, 담당자 이름·직함은 두세 글자라
# 멀쩡한 문장이 통째로 뭉개진다(실제로 세 글자 담당자 이름이 남의 메모 261곳에
# 우연히 들어맞았다). 지켜야 하는 것은 **이 줄이 누구인지 알아볼 수 없는 것**
# 이므로, 그 줄을 가리키는 값만 지우면 번호로 내보내는 뜻이 유지된다.
#
# **상호(기업명·투자사명)는 다르다 — 남의 것도 지운다.** 아래 `_org_pattern`
# 참고. 짧아서 뭉개지는 문제가 상호에는 없고, 지금 이 자료는 기업도 번호로만
# 내보내므로 남의 메모에 적힌 기업명 하나가 그 규칙을 통째로 무르게 한다.
INVESTOR_IDENTIFYING_FIELDS = ("kakao_room_name", "firm", "name", "email",
                               "phone", "office_phone", "office_fax")

# 기업도 같은 처리를 받는다. 이름 칸을 빼도 **문장 안에 자기 이름이 남는**
# 줄이 있다(개발 자료 344곳 중 5곳). 칸만 막고 끝내면 번호로 내보내는 뜻이
# 그 다섯 줄에서 사라진다 — 투자사 쪽에서 이미 겪은 것과 같은 일이다.
#
# **같은 `_scrub` 을 쓴다.** 기업용 함수를 따로 만들면 한쪽이 낡는다(전화·
# 이메일 모양을 한쪽에만 더하는 식으로). 다른 것은 "그 줄 자신을 가리키는
# 값" 의 목록뿐이라, 목록만 갈라 둔다.
COMPANY_IDENTIFYING_FIELDS = ("name", "kakao_room_name", "contact_name",
                              "contact_email", "contact_phone", "assignee_name")

# 지운 자리는 **비우지 않고 표시한다.** 그냥 빼면 "이사님과 통화" 처럼 문장이
# 멀쩡해 보여서, 뭔가 지워졌다는 것을 읽는 쪽도 사람도 알 수 없다.
MASK = "[가림]"

# 값이 어느 칸에도 없이 문장에만 있는 연락처. 누구 것이든 나가면 안 된다.
_PHONE = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

#: 남의 상호를 지울 때의 **최소 길이**.
#:
#: 짧은 값으로 지우기 시작하면 멀쩡한 문장이 뭉개진다(`카카오` 를 지우면
#: `카카오톡` 이야기가 `[가림]톡` 이 된다). 개발 자료로 3·4·5·6자를 다 재
#: 보니 3자와 4자가 잡아내는 것이 **똑같았고**(걸린 칸 9개 · 76자), 값의
#: 개수만 582개에서 541개로 줄었다 — 잡는 것이 같다면 덜 지우는 쪽이 낫다.
CROSS_MIN_LEN = 4


def _org_pattern(db: Session):
    """자료에 나오면 안 되는 **상호**를 한 번에 잡는 그물. 없으면 `None`.

    ## 왜 남의 것까지 지우나

    `_scrub` 은 그 줄 자신의 값만 지운다. 그런데 실데이터를 훑어 보니 **투자사
    메모에 다른 기업의 이름이 적혀 있었다**("○○ 소개드렸습니다" 류로 12곳,
    남의 투자사명이 3곳, 남의 기업명이 다른 기업 소개 문장에 1곳). 기업을
    번호로만 내보내기로 해 놓고 그 이름이 옆줄 메모로 나가면, 규칙이 지켜지는
    줄과 안 지켜지는 줄이 섞인 채로 나간다 — 그런 보호는 없는 것과 같다.

    ## 얼마나 뭉개지나

    개발 자료로 재 보니 자유 문장 1,018칸 47,226자 중 **9칸 76자**가 가려진다
    (0.16%). 남는 문장은 그대로다 — 상호는 문장의 뼈대가 아니라 이름표다.

    ## 사람 이름은 여기 넣지 않는다

    두세 글자라 남의 멀쩡한 문장에 우연히 들어맞는다(바로 위 문단). 사람
    이름은 지금까지대로 **그 줄 자신의 것만** 지운다.

    ## 한 번만 짓는다

    자료 한 벌에 문장이 1,000칸 넘게 들어 있어서, 칸마다 상호 500여 개를 대
    보면 느리다. `brief()` 가 한 번 지어 두 함수에 넘긴다.
    """
    from ..models import VcContact

    values = {(c.name or "").strip()
              for c in db.execute(select(IrCompany)).scalars().all()}
    values |= {(c.firm or "").strip()
               for c in db.execute(select(VcContact)).scalars().all()}
    # 긴 것부터 — 짧은 것을 먼저 지우면 긴 상호의 나머지가 남는다.
    picked = sorted((v for v in values if len(v) >= CROSS_MIN_LEN),
                    key=len, reverse=True)
    if not picked:
        return None
    return re.compile("|".join(re.escape(v) for v in picked))


def _scrub(text: str, row=None,
           identifying=INVESTOR_IDENTIFYING_FIELDS, others=None) -> str:
    """문장에서 그 줄을 알아볼 수 있는 것을 지운다.

    **투자사와 기업이 같이 쓴다.** 다른 것은 `identifying` — 그 줄 자신을
    가리키는 칸이 무엇인가뿐이다.

    **날짜는 건드리지 않는다**(`8/19 : 초기 기업보다는…`). 언제 들은 요청인지가
    그 자체로 정보라 사람이 남겨 달라고 못 박은 자리다 — 여기서 지우는 것은
    이름·투자사명·연락처·이메일·카톡방 이름뿐이다.

    긴 값부터 지운다. 카톡방 이름이 대개 투자사명을 품고 있어서(`○○벤처스
    Deal 공유`), 짧은 쪽을 먼저 지우면 방 이름의 나머지가 남는다.
    """
    for value in sorted(
            {(getattr(row, f, None) or "").strip() for f in identifying},
            key=len, reverse=True):
        # 한 글자짜리 값으로 지우기 시작하면 멀쩡한 문장이 통째로 뭉개진다.
        if len(value) >= 2:
            text = text.replace(value, MASK)
    # 남의 상호(`_org_pattern`). 자기 값을 먼저 지운 뒤에 훑는다 — 순서가
    # 바뀌어도 결과는 같지만, 자기 값이 더 정확해서 먼저 잡는 편이 낫다.
    if others is not None:
        text = others.sub(MASK, text)
    text = _PHONE.sub(MASK, text)
    return _EMAIL.sub(MASK, text)


def _fill(row, fields, scrub_with=None,
          identifying=INVESTOR_IDENTIFYING_FIELDS, others=None,
          banded=()) -> dict:
    """값이 있는 칸만 담는다.

    투자사 300여 명 중 소싱메모·팁스메모가 든 사람은 소수다. 빈 칸을 전부
    `null` 로 채우면 자료의 절반이 빈 칸 이름이 되어, 읽는 쪽이 실제 내용을
    그 사이에서 찾아야 한다. **날짜가 붙은 메모(`8/19 : 초기 기업보다는…`)는
    다듬지 않고 그대로 담는다** — 언제 들은 요청인지가 그 자체로 정보다.

    `banded` 에 적힌 칸은 **정확한 값 대신 구간 이름**으로 담는다
    (`amount_band`). 이 자리에서 바꾸는 것이 요점이다 — 담고 나서 다시 훑어
    고치는 길로 짜면, 사이에 낀 코드가 정확한 값을 한 번 보게 된다.

    **0 은 살아남는다.** 아래에서 떨어져 나가는 `0` 은 `_fill` 이 원래 빈
    값으로 치던 정수 0 이고, 구간 칸의 0 은 그 전에 `"0"` 표가 되어 있다 —
    값이 없는 것과 정확히 0 인 것은 다른 사실이라 갈라 두어야 한다.
    """
    out = {}
    for field in fields:
        value = getattr(row, field, None)
        if field in banded:
            value = amount_band(value)
        elif isinstance(value, str):
            value = _scrub(value.strip(), scrub_with, identifying, others)
        if value not in (None, "", 0):
            out[field] = value
    return out


# ── 이미 보낸 기업 ──────────────────────────────────────────────────────────

#: `SendItem.status` 중 **실제로 나간 것**. 이 값 하나만 이력에 든다.
#:
#: 나머지는 `pending`(아직 안 감) · `sending`(가는 중) · `failed`(못 감) ·
#: `canceled`(사람이 멈춤)이고, 잡 쪽에도 `draft`(만들다 만 목록)가 있다.
#: **그것들을 "보냈다" 로 세면 안 된다** — 안 나간 기업이 이력에 들면 LLM 이
#: 멀쩡한 후보를 빼 버리고, 빠진 이유가 자료 어디에도 안 보인다.
#: 앱의 다른 자리도 모두 이 값 하나로 센다(`routers/deals.py: _has_history` ·
#: `services/deal_numbers.py: for_contact` · 대시보드).
SENT_STATUS = "sent"


def sent_history(db: Session, contact_ids) -> Dict[int, tuple]:
    """`{담당자 id: ([기업 번호…], 못 실은 개수)}` — **최근 것부터**.

    ## 이력은 **두 곳**에 있다

      ① 이 시스템으로 보낸 회차 — `SendItem`(누구에게) → `SendJob`(어느 회차)
         → `DealBatchCompany`(그 회차에 어떤 기업이 실렸나). 회차에 기업이 없는
         발송(리마인드·미팅 요청 등)은 이어지는 줄이 없어 저절로 빠진다.
      ② 시트에서 옮겨 온 지난 발송 기록 — `ContactActivity`. 담당자 줄에
         **기업 이름**이 적혀 있다.

    **②를 빼면 이 기능이 거의 헛돈다.** 개발 자료로 재 보니 ①이 30짝인데 ②가
    2,495짝이었다(투자사 274명 중 ①로 이력이 생기는 사람이 5명, ②까지 세면
    125명). 이 시스템으로 보내기 시작한 것이 최근이라 지난 것은 거의 다 ②에
    있다 — ①만 세면 274명 중 269명이 "보낸 적 없음" 으로 나가고, 그건 사실이
    아니다. `services/deal_history.py` 도 같은 이유로 둘을 합쳐 읽는다.

    ## ② 는 이름으로 잇는다 — 못 이으면 **개수로 밝힌다**

    ②에는 기업 번호가 아니라 이름이 적혀 있어서 지금 IR 기업 목록과 이름으로
    맞춘다. 맞추는 규칙은 `deal_history._key` **그 한 곳**이다((주)·띄어쓰기
    차이로 다른 기업이 되지 않게 다듬는다) — 여기에 다시 적으면 화면의
    `최근에 보냄` 표시와 갈린다.

    못 맞춘 이름이 있다(개발 자료로 2,913건 중 339건). **그것을 조용히 버리면
    안 된다** — 읽는 쪽은 목록이 전부인 줄 알고 그 기업을 다시 고른다. 그렇다고
    이름을 내보낼 수도 없다. 그래서 **몇 곳인지만** 세 번째 값으로 돌려준다.

    ## 무엇을 "보냈다" 로 세는가

    둘 다여야 한다 — **실제로 나갔고**(`SENT_STATUS`), **문구가 나가는 종류의
    잡**(`SEND_KINDS`)이어야 한다. 뒤쪽은 이 저장소가 이미 한 번 데인 자리다:
    방 연결 확인·시험 발송·스타트업 월간 발송도 `sent` 로 남는데, 그것을 세면
    투자사에게 보낸 적 없는 기업이 이력에 든다. 세는 자리마다 따로 거르면 한
    곳이 빠지므로 `models.SEND_KINDS` 한 곳을 읽는다.

    소싱 명단으로 나간 건은 `contact_id` 가 비어 있어(받는 줄이 다른 표에 있다)
    담당자 번호로 묶는 이 질의에 애초에 걸리지 않는다.

    ## 같은 기업이 여러 번 나갔으면 한 번만

    한 기업을 두 회차에 걸쳐 보냈어도 사람이 알아야 하는 것은 "보냈다" 하나다.
    **자르는 것은 겹치는 것을 지운 뒤**라, 60개라면 서로 다른 기업 60곳이다.
    """
    from ..models import (ContactActivity, DealBatchCompany, SendItem, SendJob,
                          SEND_KINDS)
    # 이름을 맞추는 규칙은 그 한 곳뿐이다(밑줄로 시작하지만 이 저장소에서는
    # 이미 공유되는 판정이다 — `_room_state` 와 같은 자리).
    from .deal_history import _key

    ids = set(contact_ids)
    if not ids:
        return {}

    # `(언제, 기업 id)` — 두 곳에서 모아 뒤에서 한 번에 추린다.
    found: Dict[int, List[tuple]] = {}
    unmatched: Dict[int, set] = {}

    # ① 이 시스템으로 보낸 회차
    for contact_id, when, company_id in db.execute(
        select(SendItem.contact_id, SendItem.sent_at, DealBatchCompany.company_id)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .join(DealBatchCompany, DealBatchCompany.batch_id == SendJob.batch_id)
        .where(SendItem.contact_id.in_(ids),
               SendItem.status == SENT_STATUS,
               SendJob.kind.in_(SEND_KINDS))
        .order_by(SendItem.id.desc(), DealBatchCompany.position)
    ).all():
        found.setdefault(contact_id, []).append((when or "", company_id))

    # ② 시트에서 옮겨 온 지난 발송 기록 — 이름으로 잇는다.
    by_name: Dict[str, int] = {}
    for c in db.execute(select(IrCompany)).scalars().all():
        by_name.setdefault(_key(c.name), c.id)
    by_name.pop("", None)

    for act in db.execute(
        select(ContactActivity).where(ContactActivity.contact_id.in_(ids),
                                      ContactActivity.kind == ACTIVITY_KIND)
    ).scalars().all():
        try:
            names = json.loads(act.company_names or "[]")
        except (TypeError, ValueError):
            continue
        for name in names:
            key = _key(name or "")
            if not key:
                continue
            company_id = by_name.get(key)
            if company_id:
                found.setdefault(act.contact_id, []).append(
                    (act.happened_at or "", company_id))
            else:
                # **이름은 담지 않는다** — 몇 곳인지만 센다.
                unmatched.setdefault(act.contact_id, set()).add(key)

    out: Dict[int, tuple] = {}
    for contact_id in ids:
        seen: set = set()
        refs: List[str] = []
        more = 0
        # 최근 것부터. 날짜가 비어 있는 줄은 뒤로 밀린다 — 자를 일이 생겼을 때
        # 언제 것인지 아는 쪽을 먼저 남긴다.
        for _when, company_id in sorted(found.get(contact_id, []),
                                        key=lambda pair: pair[0], reverse=True):
            if company_id in seen:
                continue
            seen.add(company_id)
            if len(refs) < HISTORY_LIMIT:
                refs.append(company_ref(company_id))
            else:
                more += 1
        out[contact_id] = (refs, more, len(unmatched.get(contact_id, ())))
    return out


def investor_rows(db: Session, user: User, *,
                  held: Optional[List] = None) -> List:
    """자료에 담기는 투자사 줄 — **자료도 화면도 `resolve()` 도 여기서 나온다.**

    문이 둘이다.

    ## ① 자기 담당분 — 관리자여도 팀 전체는 담지 않는다

    `sheet_owner.managed` 는 **투자사 관리 현황이 세는 그 모집단**이라, 감춘
    줄·투자사가 아닌 명단은 이미 빠져 있다(여기서 또 거르면 두 수가 갈린다).
    거기에 `team_wide` 를 주지 않는다: 딜 소개는 담당자별로 나가므로 남의 담당
    투자사를 추천받아도 **보낼 수가 없다.** 관리자 계정으로 꺼내면 팀 전체
    677곳이 담기고 그중 실제로 보낼 수 있는 곳은 114곳이던 자리다 — 추천 대부분이
    처음부터 쓸 수 없는 것이었다. 팀 전체를 보고 고르는 것은 투자사 관리 현황에서
    할 일이고, 이 자료는 **받는 사람이 바로 쓸 수 있는 것**만 담는다.

    ## ② 카톡방 확인이 끝난 곳 — 맞춰 놓고 보낼 수 없으면 못 쓴다

    판정은 **여기서 짓지 않고** 대시보드가 방 갈래를 나누는 그 함수를 부른다
    (`dashboard.room_confirmed` → `_room_state`). 같은 판정을 두 곳에 적으면
    화면 숫자와 자료 수가 갈린다 — 이 저장소가 반복해 겪은 사고다.

    `held` 는 이미 꺼내 둔 담당분을 다시 질의하지 않으려는 것뿐이다. **거르는
    식은 이 함수 한 줄뿐**이라, 넘기든 안 넘기든 담기는 사람은 같다.
    """
    rows = sheet_owner.managed(db, user) if held is None else held
    return [c for c in rows if room_confirmed(c)]


def scope(db: Session, user: User) -> dict:
    """무엇이 담기는지 — **몇 곳이고 왜 그 수인지.**

    자료의 `scope` 칸과 화면의 안내문이 **이 한 곳에서 나온다.** 677곳이 담기던
    동안 화면은 아무 말도 하지 않았고, 사람은 114곳만 보낼 수 있다는 것을 자료
    어디에서도 읽을 수 없었다 — 수가 갈렸다는 사실 자체를 모르는 것이 제일 나쁘다.

    `count` 는 `investor_rows` 를 세어 얻는다. 자료에 담기는 목록과 **같은
    함수**라 둘이 갈릴 수 없다.
    """
    held = sheet_owner.managed(db, user)
    rows = investor_rows(db, user, held=held)
    label = ROOM_LABELS[ROOM_CONFIRMED][0]
    text = (f"본인 담당 · 카톡방 {label} {len(rows)}곳"
            f" (내가 맡은 투자사 {len(held)}곳 중)")
    if not rows:
        # **빈 자료를 조용히 내보내지 않는다.** 그대로 붙여 넣으면 LLM 은
        # 아무것도 못 고르고, 사람은 시킨 말이 잘못된 줄 안다.
        text += " — 담을 투자사가 없습니다. [방 연결 확인]을 먼저 돌리세요"
    return {
        "count": len(rows),
        "held": len(held),
        "label": label,
        "text": text,
        "empty": not rows,
        # 어디를 보면 그 사람들이 있는지. 거르는 값(`확인됨`)은 투자사 관리
        # 현황이 그 칸을 거를 때 쓰는 말 그대로다(`ROOM_LABELS`) — 손으로 적으면
        # 눌러도 아무것도 안 걸러진 채 화면만 열린다(이 저장소가 두 번 당했다).
        #
        # **줄 수가 이 수와 꼭 같지는 않다.** 관리자의 투자사 관리 현황은 팀
        # 전체를 보여 주고 `내 담당만` 으로 거르는 칸이 없다. 그래서 화면의 링크
        # 글도 "담기는 투자사" 가 아니라 거르는 조건 그대로 적는다.
        "href": room_href(ROOM_CONFIRMED),
    }


def investors(db: Session, user: User, *, others=None) -> List[dict]:
    """맞추는 데 쓸 투자사 자료 — **이름 없이 번호로만**.

    누구를 담느냐는 `investor_rows` 한 곳이 정한다(그 설명 참고). 여기서 다시
    거르면 화면에 적힌 수·`resolve()` 가 찾는 범위와 갈린다.
    """
    rows = investor_rows(db, user)
    history = sent_history(db, [c.id for c in rows])
    out = []
    for c in rows:
        item = {"id": investor_ref(c.id)}
        item.update(_fill(c, INVESTOR_FIELDS, scrub_with=c, others=others))
        # 이미 보낸 기업 — **번호만**. 비어 있어도 칸을 남긴다: 다른 칸과
        # 달리 여기서 칸이 없는 것과 "보낸 적 없다" 는 것을 읽는 쪽이 구별할
        # 길이 없고, 그 둘을 헷갈리면 이력을 실은 뜻이 사라진다.
        refs, more, unmatched = history.get(c.id, ([], 0, 0))
        item["sent_before"] = refs
        if more:
            item["sent_before_more"] = more
        # 옛 기록의 이름 중 지금 기업 목록에서 못 찾은 것. **개수만** 나간다 —
        # 조용히 버리면 읽는 쪽이 목록을 전부인 줄 안다.
        if unmatched:
            item["sent_before_unmatched"] = unmatched
        # `room_open` 칸은 **없앴다.** 예전에는 방이 막힌 사람도 담고 그 사실을
        # 칸으로 알렸는데(막힌 사람을 골라 주면 그때 방부터 뚫으면 된다는
        # 생각이었다), 실제로는 677곳 중 563곳이 그런 줄이라 추천 대부분이
        # 쓸 수 없는 것으로 돌아왔다. 지금은 `investor_rows` 가 아예 담지 않으므로
        # 이 칸은 늘 참이다 — 늘 같은 값인 칸은 읽는 쪽을 헷갈리게만 한다.
        out.append(item)
    return out


def companies(db: Session, *, others=None) -> List[dict]:
    """소개할 수 있는 IR 기업 자료 — 이름 없이 번호와 규모만.

    기업은 **팀 공용**이다(`/companies` 화면도 담당으로 나누지 않는다).
    누구 담당이든 소개할 딜은 같은 목록에서 고른다.

    `딜소개 불가` 로 표시된 기업만 빠진다. 이것은 판단이 아니라 **보내면 안
    되는 곳**이고, 발송 화면이 이미 같은 이유로 목록에서 빼고 있다
    (`routers/pages.py` 의 `deals_page`) — 여기 남겨 두면 보낼 수 없는 곳을
    추천받는다. 판정은 그 화면이 쓰는 상수를 그대로 읽는다.

    내용이 모자란 기업은 **감추지 않고** `introducible` 로 표시만 한다.
    다시 계산하지 않고 `IrCompany.introducible` 을 그대로 읽는다 — 여기서
    조건을 새로 적으면 화면의 `내용 부족` 표시와 갈린다.

    **이름은 나가지 않는다**(모듈 설명 참고). 칸을 뺐다고 끝이 아니라, 한줄
    소개·요약 **문장 안에 자기 이름이 또 적힌** 줄이 있어(개발 자료 344곳 중
    5곳) 투자사와 **같은 `_scrub`** 을 지나게 한다. 기업 쪽 연락 담당자·대표
    카톡방·우리 팀 담당자 이름도 같은 자리에서 지워진다
    (`COMPANY_IDENTIFYING_FIELDS`).

    **금액은 구간으로 나간다**(`AMOUNT_FIELDS` · `amount_band`). 이름을 빼도
    숫자가 남으면 그 숫자로 특정된다 — 재 본 값은 `amount_band` 에 적어 두었다.
    """
    from ..routers.companies import BLOCKED_CONTRACT, contract_key

    rows = db.execute(select(IrCompany).order_by(IrCompany.id)).scalars().all()
    out = []
    for c in rows:
        if contract_key(c.contract_status) == BLOCKED_CONTRACT:
            continue
        item = {"id": company_ref(c.id)}
        item.update(_fill(c, COMPANY_FIELDS, scrub_with=c,
                          identifying=COMPANY_IDENTIFYING_FIELDS,
                          others=others, banded=AMOUNT_FIELDS))
        item["introducible"] = bool(c.introducible)
        out.append(item)
    return out


# ── 시킬 말 ────────────────────────────────────────────────────────────────

def prompt() -> str:
    """LLM 창에 자료와 함께 붙여 넣을 **지시문**.

    ## 짓는 자리는 여기 하나다

    화면(`templates/deals.html`)도 스크립트(`static/js/llm_brief.js`)도 이
    문장을 들고 있지 않다. 스크립트는 이 함수가 지어 `/api/llm-brief.json` 에
    실어 보낸 `prompt` 를 **받아서** 쓴다. 화면과 API 가 각자 문장을 들고
    있으면 반드시 갈린다 — 이 저장소가 반복해 당한 사고다(좌측 메뉴와 라우터,
    투자사 수 117명·123명).

    ## 뽑을 개수는 `PICK_COUNT` 하나뿐이다

    문장 안에 `8` 을 적지 않는다. 여기저기 흩어 적으면 한 곳만 고쳐지고,
    사람은 8곳을 시켰다고 믿는데 다른 수가 온다.

    ## 번호로 답해 달라는 요구가 반드시 든다

    이 요구가 빠지면 답이 이름·설명으로 돌아오고, 그러면
    [번호 → 이름 찾기] 가 아무것도 못 읽는다(맨숫자는 일부러 안 읽는다).
    예시는 화면의 붙여넣기 칸과 **같은 문장**이다(`ANSWER_EXAMPLE`).

    ## 끝을 `── 자료 ──` 로 맺는다

    복사하면 이 글 바로 뒤에 자료가 붙는다. 경계가 없으면 지시문과 자료가
    한 덩어리로 읽혀서, 자료 안의 메모 문장이 지시로 읽힐 수 있다.
    """
    return "\n".join([
        "아래 자료(JSON)를 보고, 투자사마다 소개하면 좋을 기업을 골라 주세요.",
        "",
        f"1. 투자사마다 기업 {PICK_COUNT}곳을 골라 주세요.",
        "2. 그 투자사에게 **이미 보낸 기업(`sent_before`)은 빼 주세요.**",
        "3. 투자사의 성향 — 관심 분야(`sectors`) · 투자 단계(`stages`) · "
        "투자 규모(`round_size`) · 메모(`memo` · `sourcing_note` · `tips_note`) "
        "— 를 보고 맞는 곳을 골라 주세요.",
        f"4. 빼고 나니 {PICK_COUNT}곳이 안 되면 되는 만큼만 적고 몇 곳인지 "
        "밝혀 주세요. 수를 채우려고 안 맞는 곳을 넣지 마세요.",
        f"5. 답은 **번호로** 적어 주세요. 예) {ANSWER_EXAMPLE}",
        "",
        "투자사도 기업도 이름 없이 번호로만 나갑니다. 자료 맨 앞의 `note` 에 "
        "나머지 규칙이 적혀 있으니 함께 읽어 주세요.",
        "",
        "── 자료 ──",
    ])


def brief(db: Session, user: User, *, now: Optional[str] = None) -> dict:
    """화면 단추와 API 가 **같이 부르는 함수**.

    둘을 따로 만들면 한쪽이 낡는다 — 이 저장소가 반복해 당한 사고다
    (좌측 메뉴 목록과 라우터 목록, 투자사 수 117명·123명). 화면의
    [자료 내려받기] 는 이 함수를 부르는 주소를 그대로 여는 링크다.
    """
    # 상호를 잡는 그물은 **한 번만** 짓는다(`_org_pattern` 참고). 두 함수가
    # 각자 지으면 같은 것을 두 번 짓고, 언젠가 한쪽만 안 쓰게 된다.
    others = _org_pattern(db)
    return {
        # 언제 꺼낸 자료인지. 메모에 날짜가 섞여 있어서(`8/19 : …`) 자료 자체가
        # 언제 것인지 없으면 그 날짜들을 어디에 견줘야 할지 알 수 없다.
        "generated_at": now or clock.now_iso(),
        # **무엇이 담겼는지 자료가 스스로 말한다.** 화면도 같은 문장을 읽는다
        # (`scope`) — 두 곳이 각자 적으면 갈린다.
        "scope": scope(db, user)["text"],
        "amount_unit": AMOUNT_UNIT,
        "note": note(),
        # 시킬 말도 **자료와 함께** 나간다. 화면의 [복사] 는 이것을 앞에
        # 붙여 한 덩어리로 담고, [자료 내려받기] 로 받은 파일만 봐도 무엇을
        # 시키는 자료인지 알 수 있다.
        "prompt": prompt(),
        "investors": investors(db, user, others=others),
        "companies": companies(db, others=others),
    }


# ── 번호를 다시 이름으로 ────────────────────────────────────────────────────

def resolve(db: Session, user: User, text: str) -> dict:
    """LLM 이 답해 온 번호를 앱 안에서 이름으로 되돌린다.

    이 길이 없으면 번호로 내보내는 기능은 반쪽이다 — 답을 받아도 누구인지
    알 수 없다.

    **찾는 범위는 자료를 꺼낼 때와 같다** — `investor_rows` 한 함수를 부른다.
    두 방향으로 갈리면 안 된다: 내보낸 적 없는 번호가 이름을 돌려주면 그것은
    유출이고(번호만 바꿔 넣어 남의 담당·방이 막힌 곳을 알아내는 길이 된다),
    반대로 자료에 담긴 번호가 안 찾아지면 답을 받아도 쓸 수가 없다.

    못 찾은 번호는 **버리지 않고 그대로 돌려준다.** 조용히 빠지면 다섯을
    붙여 넣고 셋만 뜬 것을 눈치채지 못한다.
    """
    refs = parse_refs(text)

    contacts = {c.id: c for c in investor_rows(db, user)}
    found_investors = []
    for number in refs["investors"]:
        c = contacts.get(number)
        found_investors.append({
            "id": investor_ref(number),
            "found": c is not None,
            # 이름은 **앱 안에서만** 붙는다 — 내보내는 자료에는 없다.
            "name": c.name if c else "",
            "firm": (c.firm or "") if c else "",
            # 눌러서 바로 그 사람 상세를 연다. 목록만 띄우면 300명 중에서
            # 다시 찾아야 한다(대시보드의 '내 투자사 선호' 와 같은 주소다).
            "href": f"/contacts?contact={number}" if c else "",
        })

    ir_rows = {c.id: c for c in db.execute(select(IrCompany)).scalars().all()}
    found_companies = []
    for number in refs["companies"]:
        c = ir_rows.get(number)
        found_companies.append({
            "id": company_ref(number),
            "found": c is not None,
            "name": c.name if c else "",
            # IR 기업 현황에는 번호로 여는 길이 없고 검색만 있다 —
            # 이름으로 걸어 준다(`/companies?q=`).
            "href": f"/companies?q={quote(c.name)}" if c else "",
        })

    return {"investors": found_investors, "companies": found_companies}
