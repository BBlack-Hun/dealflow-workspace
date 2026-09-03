"""빈 `사업분야`(sector_major) 칸에 넣을 만한 갈래를 **추천만** 한다.

사용자의 말은 "한줄 소개 내용이 들어가면 IR 기업현황의 사업분야에 자동으로
들어가게" 였다. 그런데 **그대로 만들면 안 된다.** 실데이터를 재 보면 둘은
같은 것이 아니다.

    IR 기업 344곳 · 한줄소개 있음 293 · 사업분야 있음 275
    한줄소개 앞머리 == 사업분야       0건

한줄 소개는 **문장**이고(`B2B 농산물 선도거래 플랫폼 운영사`), 사업분야는
**열 갈래로 정해진 값**이다(`ESG·푸드·애그테크`). 앞머리를 그대로 옮겨 넣으면
갈래가 293가지로 흩어져 **필터도 딜 추천도 못 쓴다** — 지금 이 값으로 걸러
보는 화면(`/deals` 의 분야 필터, `matcher.evaluate_company`)이 통째로 죽는다.

그래서 **옮겨 적지 않고 골라 준다.** 지금 쓰이는 갈래 중 맞아 보이는 것을
최대 세 개까지 딱지로 띄우고, 넣을지는 **사람이 누른다.**

--- 왜 이 방법인가 ---------------------------------------------------------

갈래 목록도 낱말도 **코드에 적지 않고 데이터에서 읽는다.** 이 저장소에서
갈래는 사람이 쌓아 온 것이라, 코드에 목록을 한 벌 더 적어 두면 반드시
어긋난다(계약여부·단계에서 이미 겪은 그 부류다). 새 갈래를 지어내면 그것이
곧 오염이다 — 지어낸 갈래는 아무 필터에도 안 걸린다.

그래서 **이미 둘 다 적혀 있는 행이 곧 교재**다. `한줄소개`·`사업분야` 가 함께
있는 270곳에서 "이런 말을 쓰는 곳을 사람은 무슨 갈래로 불렀는가"를 세어 두고,
빈 칸을 만나면 같은 잣대로 견준다. 사람이 갈래를 새로 만들거나 이름을 고치면
교재도 그날로 따라 바뀐다 — **맞춰 주는 코드가 필요 없다.**

낱말은 **띄어쓴 토막과 글자 2-gram 을 함께** 쓴다. 한국어는 붙여 쓴다 —
`스마트팜`·`푸드테크`·`디지털헬스케어` 는 띄어쓰기로 갈라지지 않아서, 띄어쓴
토막만 세면 `스마트팜` 과 `스마트 팜` 이 남남이 된다. 글자 2-gram(`스마`·`마트`·
`트팜`)을 함께 세면 둘이 겹쳐 걸린다. 실측으로도 2-gram 을 섞은 쪽이 낫다
(띄어쓴 토막만: 44.6% · 2-gram 만: 50.4% · 둘 다: 53.0%).

한 문서 안에서 같은 낱말이 여러 번 나와도 **한 번으로 센다.** 소개가 긴 곳은
같은 말을 반복해서, 횟수를 그대로 세면 긴 소개 하나가 갈래 전체의 어휘를
좌우한다.

--- 얼마나 맞히는가 (실데이터로 잰 값, 절대 반올림해 올리지 않는다) --------

둘 다 적힌 270곳을 하나씩 빼내어(leave-one-out) 나머지 269곳으로 배운 뒤
빼 둔 곳을 맞혀 봤다:

    첫째 제안이 사람이 고른 값과 같음      143/270 = 53.0%
    세 제안 안에 사람이 고른 값이 있음     204/270 = 75.6%

**높지 않다. 그래서 자동으로 쓰지 않는다.** 이 숫자는 방법이 나빠서가 아니라
한줄 소개가 갈래를 결정하지 않기 때문이다 — 소개에 제 갈래의 이름 낱말이
그대로 들어 있는 곳이 270곳 중 49곳(18.4%)뿐이다. 같은 `AI 기반 …` 소개가
사람 손에서 `AI·SaaS·데이터` 도 되고 `모빌리티·물류` 도 된다(무엇을 하는
회사인가로 가르지, 무슨 기술을 쓰는가로 가르지 않기 때문이다). 글만 읽어서
그 판단을 되살릴 방법은 없다.

두 자리 중 하나꼴로 틀리는 제안을 칸에 **저절로 적어 넣으면** 그 순간
`사업분야` 는 믿을 수 없는 칸이 되고, 사람은 틀린 줄도 모른다. 반대로 딱지로
띄워 두면 **틀린 제안은 안 눌리고 끝난다** — 그래서 이 파일에는 값을 쓰는
코드가 아예 없다. 부르는 쪽도 쓰지 못한다(`suggest_for` 는 글자 목록만 준다).

--- 아무것도 제안하지 않는 자리 --------------------------------------------

**이미 골라 둔 값이 있으면 제안하지 않는다.** 사람이 정한 값 옆에 딱지를
띄우면 되묻는 것이 되고, 잘못 눌러 덮을 길이 생긴다.

**자리채움 글에는 제안하지 않는다.** 빈 19곳의 한줄 소개를 열어 보면 13곳이
`회사정보 검색안됨`·`메일함에 참고할 자료 없음`·`내용없음` 이다. 회사가 뭘
하는지 아무도 못 찾았다는 메모지 소개가 아니다. 이런 글로도 억지로 하나
골라 주면, 사람은 그 딱지를 그냥 누른다 — **없는 근거로 만든 값**이 그렇게
칸에 들어간다.

**아는 낱말이 하나도 없어도 제안하지 않는다.** 교재에서 한 번도 못 본 말뿐인
소개는 견줄 근거가 없다. 이때 점수는 갈래 크기 순서(사전확률)만 남아서, 늘
가장 큰 갈래가 1등으로 뽑힌다 — 읽지도 않고 `AI·SaaS·데이터` 를 권하는 꼴이다.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Iterable, List, Optional, Sequence, Tuple

# 몇 곳 이상 쓰인 갈래만 후보로 둔다.
#
# 실데이터에 `물류` 가 **한 곳**에 적혀 있다. `모빌리티·물류` 를 적다 만
# 흔적으로 보이는데, 그대로 후보에 두면 `물류` 라는 말이 든 소개마다 이 갈래가
# 1등으로 뽑힌다(교재가 한 장뿐이라 그 한 장이 곧 전부다). 그러면 사람이
# 딱지를 누를 때마다 **쓰이지 않는 갈래가 하나씩 늘어난다** — 없애려던 오염을
# 제안 기능이 도로 만드는 셈이다.
MIN_EXAMPLES = 3

# 견줄 낱말이 이보다 적으면 제안하지 않는다. `자료없음`(4글자) 같은 토막이
# 우연히 교재에 있는 2-gram 하나에 걸려 갈래를 얻는 일을 막는다.
MIN_KNOWN_TOKENS = 4

# 딱지로 띄우는 최대 개수. 넷을 넘기면 고르는 것이 아니라 훑는 것이 되고,
# 사람은 그냥 맨 앞을 누른다.
MAX_SUGGESTIONS = 3

# 1등이 뚜렷할 때 하나만 띄우는 길도 재 봤다. 점수차가 6 이상인 151곳만
# 보면 첫 제안이 68.2% 맞아, 확신이 실제로 신호이긴 하다. 그런데 그렇게
# 나누면 **정답이 딱지 안에 있는 비율이 75.0% → 66.0% 로 떨어진다** —
# 셋 중에서 고를 기회를 절반 넘는 곳에서 뺏기 때문이다.
#
# 고르는 것은 사람이다. 사람에게 중요한 것은 "첫 딱지가 맞는가"가 아니라
# **"내가 고를 값이 이 안에 있는가"** 라서, 늘 셋을 띄우는 쪽을 골랐다.
# 딱지가 하나뿐이면 그것이 답처럼 보이는데, 셋이면 고르라는 뜻으로 읽힌다 —
# 두 번에 한 번꼴로 틀리는 값에는 그 편이 정직하다.

# 라플라스 보정. 교재에 없는 낱말 하나가 갈래를 0점으로 만들지 않게 한다.
# 0.05·0.2·1.0 을 재 봤고 0.2 가 가장 잘 맞았다(50.4% · 53.0% · 47.8%).
ALPHA = 0.2

# 갈래 이름을 낱말로 가르는 글자 — `AI·SaaS·데이터` → AI / SaaS / 데이터.
NAME_SPLIT = re.compile(r"[·,/]")

# 글자·숫자 덩어리. 한국어·영어·숫자만 남기고 문장부호는 버린다.
WORD = re.compile(r"[0-9A-Za-z가-힣]+")

# 아직 아무것도 못 찾았다는 메모. 실데이터의 한줄 소개·사업분야 칸에 그대로
# 들어 있는 말들이다(`회사정보 검색안됨` 5곳 · `메일함에 참고할 자료 없음` 5곳 ·
# `메일함에 없음, 자료 필요` 2곳 · `내용없음` 1곳). 소개가 아니라 빈 칸이다.
#
# 같은 성격의 글이 매출 칸에도 있어서 one_liner._is_amount 가 따로 걸러내고
# 있다 — 거기서는 '숫자가 있는가'로 갈렸지만, 여기서는 견줄 것이 글뿐이라
# 말로 알아볼 수밖에 없다.
PLACEHOLDER = re.compile(
    r"검색\s*안|확인\s*안|확인\s*X|자료\s*없|내용\s*없|메일함에|해당\s*없|미확인|없음"
)


def _text(value: Optional[str]) -> str:
    return value.strip() if isinstance(value, str) else ""


def readable(text: Optional[str]) -> bool:
    """이 글로 갈래를 견줄 수 있는가. 자리채움 메모면 False."""
    body = _text(text)
    return bool(body) and not PLACEHOLDER.search(body)


def source_text(company) -> str:
    """견줄 글 — `한줄 소개`의 앞머리 + `사업분야`(스타트업DB 의 사업 설명).

    한줄 소개는 `설명 | 매출 13억 | 누적투자금액 11억 | …` 로 조립된다
    (services/one_liner.py). 뒤 토막은 **금액**이라 갈래와 아무 상관이 없고,
    모든 갈래에 골고루 나와서 세어 봐야 잡음만 는다. 그래서 첫 토막만 쓴다.

    `business_desc` 는 같은 설명이 스타트업DB 탭에 적힌 칸이다. 한줄 소개가
    아직 비었어도 이쪽만 차 있는 곳이 있어서 함께 읽는다 — 실측으로도 둘을
    합친 쪽이 조금 낫다(한줄소개만: 50.4% → 합쳐서: 53.0%).
    """
    parts = []
    for attr in ("one_liner", "business_desc"):
        head = _text(getattr(company, attr, None)).split("|")[0].strip()
        if readable(head):
            parts.append(head)
    return " ".join(parts)


def tokens(text: str) -> List[str]:
    """견줄 낱말 — 띄어쓴 토막과 글자 2-gram을 함께.

    한 글자 토막은 버린다. `AI` 처럼 두 글자인 영어는 남는다.
    """
    out: List[str] = []
    for word in WORD.findall(text.lower()):
        if len(word) < 2:
            continue
        out.append("w:" + word)
        for i in range(len(word) - 1):
            out.append("b:" + word[i:i + 2])
    return out


class Hints:
    """이미 적힌 행에서 배운 잣대. **읽기만 하고 아무 값도 고치지 않는다.**"""

    def __init__(self, pairs: Sequence[Tuple[str, str]]):
        counts: defaultdict = defaultdict(Counter)
        totals: Counter = Counter()
        docs: Counter = Counter()
        vocab = set()
        for text, sector in pairs:
            seen = set(tokens(text))          # 한 소개에서 같은 낱말은 한 번만
            if not seen:
                continue
            docs[sector] += 1
            for token in seen:
                counts[sector][token] += 1
                totals[sector] += 1
                vocab.add(token)
        # 교재가 얇은 갈래는 후보에서 뺀다(위 MIN_EXAMPLES 주석).
        self.sectors = [s for s, n in docs.items() if n >= MIN_EXAMPLES]
        self.counts = counts
        self.totals = totals
        self.docs = docs
        self.vocab = vocab
        self.n_docs = sum(docs[s] for s in self.sectors)
        self.n_vocab = max(len(vocab), 1)

    @classmethod
    def learn(cls, companies: Iterable) -> "Hints":
        """`사업분야`가 이미 적힌 기업들에서 배운다."""
        pairs = []
        for company in companies:
            sector = _text(getattr(company, "sector_major", None))
            if not sector:
                continue
            text = source_text(company)
            if text:
                pairs.append((text, sector))
        return cls(pairs)

    def rank(self, text: str) -> List[Tuple[float, str]]:
        """갈래별 점수. 견줄 낱말이 모자라면 빈 목록."""
        if not self.sectors or not readable(text):
            return []
        known = {t for t in tokens(text) if t in self.vocab}
        if len(known) < MIN_KNOWN_TOKENS:
            # 아는 말이 이만큼도 없으면 남는 것은 갈래 크기뿐이다 —
            # 읽지도 않고 가장 큰 갈래를 권하게 된다.
            return []
        ranked = []
        for sector in self.sectors:
            # 사전확률(갈래가 얼마나 흔한가)에서 시작해 낱말마다 더한다.
            score = math.log(self.docs[sector] / self.n_docs)
            total = self.totals[sector]
            counted = self.counts[sector]
            for token in known:
                score += math.log(
                    (counted[token] + ALPHA) / (total + ALPHA * self.n_vocab))
            ranked.append((score, sector))
        ranked.sort(reverse=True)
        return ranked

    def suggest(self, text: str) -> List[str]:
        """딱지로 띄울 갈래 이름들. 맞아 보이는 것이 없으면 빈 목록."""
        return [sector for _score, sector in self.rank(text)[:MAX_SUGGESTIONS]]

    def suggest_for(self, company) -> List[str]:
        """이 기업에 띄울 제안. **이미 값이 있으면 언제나 빈 목록이다.**

        '비었을 때만'을 부르는 쪽마다 적어 두면 한 군데는 반드시 빠뜨린다.
        그래서 여기 한 곳에서 막는다 — 화면이든 API 든 이 함수를 지나간다.
        """
        if _text(getattr(company, "sector_major", None)):
            return []
        return self.suggest(source_text(company))
