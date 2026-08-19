"""투자사 담당자 ↔ 딜(기업) 적합도 매칭.

근거: DRAFT_REFERENCE "투자 성격 태그와 안 맞는 조합은 발송 전 경고
(예: Seed 전문 ↔ Pre-IPO 딜)", FEATURE_SPEC §5.

시트 데이터 기준:
  - 담당자(vc_contacts): sectors(CSV), stages(CSV), round_size(자유 텍스트)
      예) sectors="AI,헬스케어" / stages="Seed,SeriesA" / round_size="건당 100억~1,000억"
  - 기업(ir_companies): sector_major, sector_minor, series, raise_target(백만원)

담당자 데이터는 비어 있는 경우가 흔하다(시트 '투자분야/라운드사이즈' 공란).
**정보가 없으면 '부적합'이 아니라 '판단 불가'로 처리**한다 — 근거 없이 발송을 막지 않기 위함.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# 판정 결과
FIT = "fit"              # 성향에 맞음
MISMATCH = "mismatch"    # 명확히 어긋남
UNKNOWN = "unknown"      # 담당자 정보 부족 → 판단 불가


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip().lower() for v in re.split(r"[,/|]", value) if v.strip()]


def _norm(value: Optional[str]) -> str:
    """비교용 정규화: 소문자 + 공백/하이픈 제거 (SeriesA == series a == Series-A)."""
    return re.sub(r"[\s\-_]", "", (value or "").lower())


def parse_round_size_eok(text: Optional[str]) -> Optional[tuple]:
    """'건당 100억~1,000억' 같은 자유 텍스트에서 (최소, 최대) 억 단위 범위를 뽑는다.

    한쪽만 있으면 나머지는 None. 숫자를 못 찾으면 None을 반환해 '판단 불가'로 남긴다.
    """
    if not text:
        return None

    # "30~100억" / "30억~100억" / "100~1,000억" 처럼 앞 숫자에 단위가 생략된 범위 표기.
    # (이 케이스를 먼저 잡지 않으면 뒤 숫자만 읽혀 '최소 100억'으로 잘못 해석된다.)
    m = re.search(r"(\d[\d,]*)\s*억?\s*[~\-–—]\s*(\d[\d,]*)\s*억", text)
    if m:
        lo = int(m.group(1).replace(",", ""))
        hi = int(m.group(2).replace(",", ""))
        return (min(lo, hi), max(lo, hi))

    nums = [int(n.replace(",", "")) for n in re.findall(r"(\d[\d,]*)\s*억", text)]
    if not nums:
        return None
    if len(nums) == 1:
        # "100억 이상" / "100억 이하" 구분
        if re.search(r"(이상|~|부터|↑|\+)", text):
            return (nums[0], None)
        if re.search(r"(이하|미만|까지)", text):
            return (None, nums[0])
        return (nums[0], None)
    return (min(nums), max(nums))


@dataclass
class CompanyFit:
    company_id: Optional[int]
    company_name: str
    verdict: str                      # fit | mismatch | unknown
    reasons: List[str] = field(default_factory=list)


@dataclass
class ContactFit:
    contact_id: Optional[int]
    fits: List[CompanyFit] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def mismatch_count(self) -> int:
        return sum(1 for f in self.fits if f.verdict == MISMATCH)

    @property
    def fit_count(self) -> int:
        return sum(1 for f in self.fits if f.verdict == FIT)


def evaluate_company(contact, company) -> CompanyFit:
    """담당자 1명 × 기업 1개의 적합도.

    contact: sectors / stages / round_size 속성을 가진 객체 (VcContact 또는 뷰)
    company: sector_major / sector_minor / series / raise_target 속성을 가진 객체
    """
    reasons: List[str] = []
    signals: List[str] = []  # 각 축의 판정

    # ── 섹터 ──────────────────────────────────────────────────────────────
    want_sectors = _split_csv(getattr(contact, "sectors", None))
    comp_sectors = [
        s for s in (getattr(company, "sector_major", None), getattr(company, "sector_minor", None)) if s
    ]
    if want_sectors and comp_sectors:
        want_n = [_norm(w) for w in want_sectors]
        hit = next(
            (c for c in comp_sectors
             if any(w and (w in _norm(c) or _norm(c) in w) for w in want_n)),
            None,
        )
        if hit:
            signals.append(FIT)
            reasons.append(f"분야 일치({hit})")
        else:
            signals.append(MISMATCH)
            reasons.append(f"분야 불일치(선호 {', '.join(want_sectors)} ↔ 딜 {', '.join(comp_sectors)})")

    # ── 투자 단계(시리즈) ─────────────────────────────────────────────────
    want_stages = _split_csv(getattr(contact, "stages", None))
    series = getattr(company, "series", None)
    if want_stages and series:
        s_n = _norm(series)
        if any(_norm(w) == s_n or _norm(w) in s_n or s_n in _norm(w) for w in want_stages):
            signals.append(FIT)
            reasons.append(f"단계 일치({series})")
        else:
            signals.append(MISMATCH)
            reasons.append(f"단계 불일치(선호 {', '.join(want_stages)} ↔ 딜 {series})")

    # ── 라운드 사이즈 ─────────────────────────────────────────────────────
    rng = parse_round_size_eok(getattr(contact, "round_size", None))
    raise_target = getattr(company, "raise_target", None)  # 백만원
    if rng and raise_target:
        target_eok = raise_target / 100.0
        lo, hi = rng
        if (lo is not None and target_eok < lo) or (hi is not None and target_eok > hi):
            signals.append(MISMATCH)
            bound = f"{lo or ''}~{hi or ''}".strip("~")
            reasons.append(f"라운드 규모 벗어남(선호 {bound}억 ↔ 유치 {target_eok:g}억)")
        else:
            signals.append(FIT)
            reasons.append(f"라운드 규모 적합({target_eok:g}억)")

    name = getattr(company, "name", "") or ""
    company_id = getattr(company, "id", None)

    if not signals:
        return CompanyFit(company_id, name, UNKNOWN, ["담당자 투자성향 정보 없음"])
    # 한 축이라도 명확히 어긋나면 경고 대상으로 본다(오발송 방지 우선).
    if MISMATCH in signals:
        return CompanyFit(company_id, name, MISMATCH, reasons)
    return CompanyFit(company_id, name, FIT, reasons)


def evaluate_contact(contact, companies: Sequence) -> ContactFit:
    """담당자 1명에게 보낼 기업 묶음 전체의 적합도 + 발송 전 경고."""
    fits = [evaluate_company(contact, c) for c in companies]
    result = ContactFit(contact_id=getattr(contact, "id", None), fits=fits)

    if fits and all(f.verdict == MISMATCH for f in fits):
        result.warnings.append("선택한 딜이 모두 이 담당자의 투자 성향과 맞지 않습니다.")
    elif any(f.verdict == MISMATCH for f in fits):
        names = ", ".join(f.company_name for f in fits if f.verdict == MISMATCH)
        result.warnings.append(f"투자 성향과 맞지 않는 딜: {names}")
    return result
