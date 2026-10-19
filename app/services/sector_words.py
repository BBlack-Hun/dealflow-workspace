"""글에서 **분야 기준 목록의 말**을 찾아내는 낱말 사전.

쓰는 자리는 하나다(투자사 `선호 투자분야` 재분류 #30 도 이것을 썼는데, 10/18 에
한 번 반영하고 10/19 에 기능을 뺐다).

  · IR 기업 현황 정리(`services/ir_sector_cleanup.py`) — 대분류가 빈 기업의 한 줄
    소개에서 대분류 **제안**을 만든다.

## 무엇을 찾나 — 목록의 이름 + 일반 업종 낱말

목록에 있는 이름(숨긴 · 합친 옛 이름 포함)은 **사전에 따로 안 적어도** 찾는다
(`find` 가 `Resolver` 를 받아 그 이름들을 함께 본다). 관리자가 목록에 소분류를
하나 더하면 다음 판부터 그 말도 걸린다.

그 밖의 말은 아래 `WORDS` 에 적는다. **일반 업종 낱말만** 적는다 — 회사 이름 ·
사람 이름 · 특정 투자사에서만 쓰는 말은 넣지 않는다(저장소가 공개다).

## 판단이 아니라 제안이다

이 사전이 고른 것은 늘 **미리보기에 먼저 뜨고, 관리자가 고른 것만** 반영된다.
`pref_group` 머리말이 그은 선과 같다 — 한 번 매기고 끝이고, 사람이 보고 나서
저장하며, 틀리면 그 줄 하나가 틀릴 뿐이다.

## 일부러 뺀 낱말

  · `플랫폼` · `인프라` — 아무 데나 붙는다(`pref_group` 이 뺀 까닭과 같다).
    `IT` 는 넣었다 — 이 칸에서는 업종 말로만 쓰였고, 라틴 글자 앞뒤 검사가
    `VISIT` 같은 데 걸리는 것을 막는다.
  · `금융` — `신기술금융` 처럼 기관 이름에 붙는다.
  · `EV` — 전기차가 아니라 기업가치(Enterprise Value)로 쓰인 줄이 실제로 있다.
  · `소재` 단독 — `○○지역 소재` 처럼 '있는 곳' 으로 쓰인다(`첨단소재` · `신소재` 는 찾는다).
  · `엔터` 단독 — `엔터프라이즈` 에 걸린다(`엔터테인먼트` 는 찾는다).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from . import taxonomy as tx

# 대분류 이름(목록 처음 값 그대로). 사전이 가리킬 자리를 글자로 한 번만 적는다.
AI = "AI·SaaS·데이터"
HEALTH = "헬스케어·바이오"
ESG = "ESG·푸드·애그테크"
COMMERCE = "커머스·라이프스타일"
DEEP = "딥테크·제조"
CONTENT = "콘텐츠·엔터테인먼트"
EDU = "에듀테크·HR테크"
MOBILITY = "모빌리티·물류"
PROP = "프롭테크·스마트시티"
FIN = "핀테크·블록체인"

#: `(낱말, 대분류, 소분류 또는 None)`. 소분류가 있으면 그 소분류로, 없으면 대분류로
#: 읽는다. **목록에 이미 있는 이름은 적지 않아도 된다**(머리말).
WORDS: Sequence[Tuple[str, str, Optional[str]]] = (
    # AI·SaaS·데이터
    ("AI", AI, None), ("인공지능", AI, None), ("생성형", AI, "생성형AI"),
    ("LLM", AI, "생성형AI"), ("딥러닝", AI, "머신러닝"), ("SaaS", AI, None),
    ("소프트웨어", AI, None), ("Software", AI, None), ("클라우드", AI, None),
    ("빅데이터", AI, "데이터분석"), ("데이터센터", AI, "데이터 인프라"),
    ("데이터", AI, None), ("ICT", AI, None), ("IT", AI, None), ("업무 자동화", AI, "업무자동화"),
    # 헬스케어·바이오
    ("헬스케어", HEALTH, None), ("헬스", HEALTH, None), ("바이오", HEALTH, None),
    ("의료", HEALTH, None), ("메디컬", HEALTH, None), ("제약", HEALTH, "신약개발"),
    ("신약", HEALTH, "신약개발"), ("진단", HEALTH, None),
    ("디지털헬스", HEALTH, "디지털헬스케어"), ("건기식", HEALTH, None),
    ("건강기능식품", HEALTH, None), ("디지털치료", HEALTH, "디지털치료제"),
    ("재생의료", HEALTH, None),
    # ESG·푸드·애그테크
    ("ESG", ESG, None), ("친환경", ESG, None), ("환경", ESG, None),
    ("기후", ESG, None), ("탄소", ESG, "탄소저감"), ("재생에너지", ESG, "에너지"),
    ("재생", ESG, None), ("신재생", ESG, "에너지"), ("전력", ESG, "에너지"),
    ("풍력", ESG, "에너지"), ("태양광", ESG, "에너지"), ("수소", ESG, "에너지"),
    ("페로브스카이트", ESG, "에너지"), ("폐플라스틱", ESG, "순환경제"),
    ("열분해", ESG, "순환경제"), ("리사이클", ESG, "순환경제"),
    ("재활용", ESG, "순환경제"), ("폐자원", ESG, "순환경제"),
    ("푸드", ESG, None), ("Food tech", ESG, "푸드테크"), ("식품", ESG, None),
    ("식음료", ESG, None), ("F&B", ESG, None), ("외식", ESG, None),
    ("농식품", ESG, None), ("농업", ESG, "애그테크"), ("수산", ESG, None),
    ("해양", ESG, None),
    # 커머스·라이프스타일
    ("커머스", COMMERCE, None), ("e커머스", COMMERCE, "이커머스"),
    ("유통", COMMERCE, None), ("리테일", COMMERCE, "리테일테크"),
    ("소비재", COMMERCE, None), ("컨슈머", COMMERCE, None),
    ("컨수머", COMMERCE, None), ("브랜드", COMMERCE, None),
    ("패션", COMMERCE, None), ("라이프스타일", COMMERCE, None),
    ("뷰티", COMMERCE, "뷰티테크"), ("화장품", COMMERCE, "뷰티테크"),
    ("코스메틱", COMMERCE, "뷰티테크"), ("미용", COMMERCE, "뷰티테크"),
    ("펫", COMMERCE, "펫테크"), ("반려", COMMERCE, "펫테크"),
    ("관광", COMMERCE, "여행"), ("리조트", COMMERCE, "레저"),
    # 딥테크·제조
    ("딥테크", DEEP, None), ("하이테크", DEEP, None), ("소부장", DEEP, None),
    ("소재부품", DEEP, None), ("부품", DEEP, None), ("장비", DEEP, None),
    ("제조", DEEP, None), ("신소재", DEEP, "첨단소재"), ("희토류", DEEP, "첨단소재"),
    ("팹리스", DEEP, "반도체"), ("파운드리", DEEP, "반도체"),
    ("후공정", DEEP, "반도체"), ("로보틱스", DEEP, "로봇"),
    ("휴머노이드", DEEP, "로봇"), ("피지컬AI", DEEP, "로봇"),
    ("방산", DEEP, "국방기술"), ("국방", DEEP, "국방기술"),
    ("방위", DEEP, "국방기술"), ("우주", DEEP, None), ("항공", DEEP, None),
    ("위성", DEEP, None), ("양자", DEEP, None), ("조선", DEEP, None),
    ("이차전지", DEEP, "배터리"), ("2차전지", DEEP, "배터리"),
    ("전고체", DEEP, "배터리"), ("기계", DEEP, None),
    # 콘텐츠·엔터테인먼트
    ("콘텐츠", CONTENT, None), ("컨텐츠", CONTENT, None),
    ("엔터테인먼트", CONTENT, None), ("미디어", CONTENT, None),
    ("웹툰", CONTENT, "IP"), ("크리에이터", CONTENT, "크리에이터 플랫폼"),
    # 에듀테크·HR테크
    ("에듀테크", EDU, None), ("에듀", EDU, None), ("교육", EDU, None),
    ("HR", EDU, None), ("채용", EDU, "채용플랫폼"), ("인재", EDU, "인재매칭"),
    # 모빌리티·물류
    ("모빌리티", MOBILITY, None), ("교통", MOBILITY, None),
    ("전기차", MOBILITY, None), ("배송", MOBILITY, "배송테크"),
    ("드론", MOBILITY, None),
    # 프롭테크·스마트시티
    ("프롭테크", PROP, None), ("부동산", PROP, None), ("건설", PROP, None),
    ("건축", PROP, None),
    # 핀테크·블록체인
    ("핀테크", FIN, None), ("결제", FIN, None), ("가상자산", FIN, "블록체인"),
    ("웹3", FIN, "블록체인"), ("Web3", FIN, "블록체인"),
    ("토큰증권", FIN, "블록체인"), ("레그테크", FIN, "RegTech"),
)

#: 라틴 글자 낱말은 **앞뒤가 라틴 글자가 아닐 때만** 걸린다 — `AI` 가 `PAID` 에,
#: `IP` 가 `IPO` 에, `HR` 이 `THREE` 에 걸리면 안 된다.
_LATIN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class Hit:
    """글에서 찾은 말 하나. `start`·`end` 는 **원래 글**의 자리다."""

    start: int
    end: int
    word: str
    major: str
    minor: Optional[str]

    @property
    def token(self) -> str:
        """선호분야 칸에 적을 말 — 소분류가 있으면 소분류, 없으면 대분류."""
        return self.minor or self.major


def _squeeze(text: str) -> Tuple[str, List[int]]:
    """견주는 꼴(`taxonomy.norm`)과, 그 꼴의 글자마다 원래 글의 자리."""
    out, where = [], []
    for i, ch in enumerate(text):
        if tx.norm(ch):
            out.append(ch.lower())
            where.append(i)
    return "".join(out), where


def _vocabulary(resolver: Optional["tx.Resolver"]) -> List[Tuple[str, str, Optional[str]]]:
    """찾을 말 전부 — 목록의 이름(옛 이름 포함, 기준 이름으로 돌려서) + `WORDS`.

    목록의 이름이 사전보다 **먼저** 선다. 같은 꼴이면 목록 쪽이 이긴다 — 관리자가
    목록에서 고친 것이 코드에 적힌 사전보다 앞서야 한다.
    """
    vocab: List[Tuple[str, str, Optional[str]]] = []
    seen = set()
    if resolver is not None:
        for term in resolver.terms.values():
            canon = resolver.canonical(term.id)
            if canon is None:
                continue
            if canon.parent_id is None:
                entry = (term.name, canon.name, None)
            else:
                parent = resolver.parent_of(canon)
                if parent is None:
                    continue
                entry = (term.name, parent.name, canon.name)
            key = tx.norm(term.name)
            if key and key not in seen:
                seen.add(key)
                vocab.append(entry)
    for word, major, minor in WORDS:
        key = tx.norm(word)
        if key and key not in seen:
            seen.add(key)
            vocab.append((word, major, minor))
    return vocab


def find(text: Optional[str], resolver: Optional["tx.Resolver"] = None) -> List[Hit]:
    """글에서 찾은 말들 — **글에서의 자리 차례**로, 겹치지 않게.

    같은 자리에서 둘이 걸리면 **긴 말**이 이긴다(`의료기기` 가 `의료` 를,
    `피지컬AI` 가 `AI` 를 덮는다). 띄어쓰기·가운뎃점은 안 본다(`디지털 헬스` =
    `디지털헬스`).

    사전이 가리키는 대분류·소분류가 **지금 목록에 없으면**(관리자가 이름을 바꿨다)
    목록에서 다시 찾아 본다 — 못 찾으면 그 말은 버린다. 없는 이름을 지어내 적으면
    그것이 곧 목록 밖의 말이다.
    """
    source = text or ""
    squeezed, where = _squeeze(source)
    if not squeezed:
        return []
    candidates = []
    for word, major, minor in _vocabulary(resolver):
        key = tx.norm(word)
        start = squeezed.find(key)
        while start >= 0:
            end = start + len(key)
            begin, finish = where[start], where[end - 1] + 1
            if _LATIN.match(word[0]) and begin > 0 and _LATIN.match(source[begin - 1]):
                start = squeezed.find(key, start + 1)
                continue
            if (_LATIN.match(word[-1]) and finish < len(source)
                    and _LATIN.match(source[finish])):
                start = squeezed.find(key, start + 1)
                continue
            candidates.append((start, -len(key), begin, finish, word, major, minor))
            start = squeezed.find(key, start + 1)
    candidates.sort()
    hits: List[Hit] = []
    taken_to = -1
    for start, neg_len, begin, finish, word, major, minor in candidates:
        if start < taken_to:
            continue
        resolved = _resolve(resolver, major, minor)
        if resolved is None:
            continue
        taken_to = start - neg_len
        hits.append(Hit(begin, finish, word, resolved[0], resolved[1]))
    return hits


def _resolve(resolver: Optional["tx.Resolver"], major: str,
             minor: Optional[str]) -> Optional[Tuple[str, Optional[str]]]:
    """사전이 가리키는 자리를 **지금 목록의 기준 이름**으로. 목록이 없으면 그대로."""
    if resolver is None:
        return major, minor
    if minor:
        term = resolver.minor(minor)
        if term is not None and not term.is_hidden:
            parent = resolver.parent_of(term)
            if parent is not None and not parent.is_hidden:
                return parent.name, term.name
    term = resolver.major(major)
    if term is None or term.is_hidden:
        return None
    return term.name, None
