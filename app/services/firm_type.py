"""투자사 유형 — 어떤 돈인지 알아야 무슨 딜을 줄지 정해진다.

같은 '투자사'라도 성격이 다르다. 엔젤·AC 는 초기 기업을 보고, PE·자산운용은
중후기 성숙 기업을 본다. 유형을 모르고 목록을 보내면 초기 기업 딜이 PE 에게,
중후기 딜이 엔젤에게 간다 — 받는 쪽에서는 이쪽이 자기를 모른다는 뜻으로 읽힌다.

유형은 **투자사 이름에 대개 드러나 있다**(…인베스트먼트 · …자산운용 · …증권).
그래서 이름에서 먼저 추론하고, 틀리면 사람이 고친다. 추론은 근거를 함께 남겨
왜 그렇게 잡혔는지 화면에서 보이게 한다.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# 유형 코드 → 화면 이름. 팀이 쓰는 말을 그대로 쓴다(투자사 성격정리 시트 기준).
TYPE_LABELS = {
    "vc": "VC (벤처캐피탈)",
    "ac": "AC (액셀러레이터)",
    "angel": "엔젤",
    "cvc": "CVC (기업 투자)",
    "pe": "PE · 자산운용",
    "securities": "증권",
    "bank": "은행 · 캐피탈",
    "public": "공공 · 지원기관",
    "other": "기타",
    "unknown": "미분류",
}

# 어느 단계 기업을 주로 보는가. 발송 대상 고를 때의 힌트다.
TYPE_STAGES = {
    "angel": "Seed 이전 ~ Seed",
    "ac": "Seed ~ Pre-A",
    "vc": "Seed ~ Series C",
    "cvc": "Series A 이상 (사업 시너지)",
    "pe": "Series C ~ Pre-IPO, 경영권",
    "securities": "Pre-IPO ~ 상장",
    "bank": "중후기 · 대출 연계",
    "public": "초기 · 지원 프로그램",
}

# 순서가 중요하다. 좁은 단서를 먼저 본다 —
# '우리PE자산운용' 은 PE 이고, '헤스캐피탈파트너스' 는 파트너스보다 캐피탈이 앞선다.
_RULES: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("public", "공공·지원기관 이름", ("창조경제혁신센터", "진흥원", "진흥공단", "공단",
                                  "기술보증", "신용보증", "창업진흥", "테크노파크",
                                  "창업지원", "중소벤처기업", "정부")),
    ("securities", "증권사", ("증권", "securities")),
    ("bank", "은행·캐피탈", ("저축은행", "은행", "bank", "캐피탈", "capital")),
    ("pe", "PE·자산운용", ("프라이빗에쿼티", "private equity", "자산운용",
                        "asset management", "pe파트너스", "사모")),
    ("ac", "액셀러레이터", ("액셀러레이터", "엑셀러레이터", "accelerator",
                        "창업기획자", "인큐베이터", "incubator")),
    ("angel", "엔젤", ("엔젤", "angel")),
    ("cvc", "기업 투자 조직", ("홀딩스", "holdings", "cvc")),
    ("vc", "벤처캐피탈", ("인베스트먼트", "investment", "벤처스", "ventures",
                       "벤처투자", "벤처캐피탈", "인베스트", "invest", "vc")),
    ("vc", "파트너스(투자사)", ("파트너스", "partners")),
]

# 이름에 'PE' 가 낱말로 들어간 경우(우리PE자산운용). 부분 문자열로 잡으면
# 'PEPPER' 같은 이름까지 걸리므로 낱말 경계로 본다.
_PE_TOKEN = re.compile(r"(?<![A-Za-z])PE(?![A-Za-z])", re.IGNORECASE)


def infer(firm: Optional[str], department: Optional[str] = None,
          title: Optional[str] = None) -> Tuple[str, str]:
    """(유형 코드, 그렇게 본 근거). 모르겠으면 ('unknown', '')."""
    text = " ".join(filter(None, [firm, department, title])).strip()
    if not text:
        return "unknown", ""
    low = text.lower()

    if _PE_TOKEN.search(text) and "자산운용" not in text:
        return "pe", "이름에 'PE'"

    for code, why, marks in _RULES:
        for mark in marks:
            if mark.lower() in low:
                return code, f"'{mark}' 이(가) 이름에 있음"
    return "unknown", ""


def label(code: Optional[str]) -> str:
    return TYPE_LABELS.get(code or "unknown", TYPE_LABELS["unknown"])


def stage_hint(code: Optional[str]) -> str:
    return TYPE_STAGES.get(code or "", "")


def guide_rows() -> List[dict]:
    """투자자 분류 안내. 화면 옆에 두어 유형을 고칠 때 참고하게 한다."""
    return [
        {"code": code, "label": TYPE_LABELS[code], "stage": TYPE_STAGES.get(code, "")}
        for code in ("angel", "ac", "vc", "cvc", "pe",
                     "securities", "bank", "public")
    ]
