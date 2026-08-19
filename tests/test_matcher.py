"""투자 성향 매칭 테스트 (분야/단계/라운드 규모)."""
from dataclasses import dataclass
from typing import Optional

from app.services import matcher


@dataclass
class C:  # contact
    id: int = 1
    sectors: Optional[str] = None
    stages: Optional[str] = None
    round_size: Optional[str] = None


@dataclass
class K:  # company
    id: int = 10
    name: str = "샘플애그"
    sector_major: Optional[str] = None
    sector_minor: Optional[str] = None
    series: Optional[str] = None
    raise_target: Optional[int] = None  # 백만원


def test_sector_match_and_mismatch():
    fit = matcher.evaluate_company(C(sectors="애그테크,푸드"), K(sector_major="애그테크"))
    assert fit.verdict == matcher.FIT

    fit = matcher.evaluate_company(C(sectors="헬스케어"), K(sector_major="핀테크"))
    assert fit.verdict == matcher.MISMATCH


def test_stage_mismatch_seed_vs_preipo():
    """DRAFT_REFERENCE 예시: Seed 전문 담당자에게 Pre-IPO 딜은 경고 대상."""
    fit = matcher.evaluate_company(C(stages="Seed"), K(series="Pre-IPO"))
    assert fit.verdict == matcher.MISMATCH


def test_stage_normalization():
    # "Series A" == "SeriesA" == "series-a"
    fit = matcher.evaluate_company(C(stages="Series A"), K(series="SeriesA"))
    assert fit.verdict == matcher.FIT


def test_round_size_range():
    # 선호 100억~1,000억인데 5억 유치면 규모 미달
    small = matcher.evaluate_company(C(round_size="건당 100억~1,000억"), K(raise_target=500))
    assert small.verdict == matcher.MISMATCH
    # 200억 유치면 적합
    ok = matcher.evaluate_company(C(round_size="건당 100억~1,000억"), K(raise_target=20000))
    assert ok.verdict == matcher.FIT


def test_parse_round_size():
    assert matcher.parse_round_size_eok("건당 100억~1,000억") == (100, 1000)
    # 앞 숫자에 단위가 생략된 표기 — 뒤 숫자만 읽어 '최소 100억'으로 오해하면 안 된다.
    assert matcher.parse_round_size_eok("라운드 30~100억") == (30, 100)
    assert matcher.parse_round_size_eok("100~1,000억") == (100, 1000)
    assert matcher.parse_round_size_eok("50억 이상") == (50, None)
    assert matcher.parse_round_size_eok("30억 이하") == (None, 30)
    assert matcher.parse_round_size_eok("") is None
    assert matcher.parse_round_size_eok("협의") is None


def test_unknown_when_contact_has_no_profile():
    """시트에 투자성향이 비어 있는 담당자가 많다 — 정보 없음은 '부적합'이 아니다."""
    fit = matcher.evaluate_company(C(), K(sector_major="핀테크", series="Seed"))
    assert fit.verdict == matcher.UNKNOWN


def test_contact_warning_when_all_mismatch():
    contact = C(sectors="헬스케어", stages="Seed")
    companies = [K(id=1, name="A", sector_major="핀테크"), K(id=2, name="B", sector_major="게임")]
    res = matcher.evaluate_contact(contact, companies)
    assert res.mismatch_count == 2
    assert res.warnings and "모두" in res.warnings[0]


def test_contact_warning_lists_only_mismatched():
    contact = C(sectors="애그테크")
    companies = [K(id=1, name="샘플애그", sector_major="애그테크"),
                 K(id=2, name="샘플페이", sector_major="핀테크")]
    res = matcher.evaluate_contact(contact, companies)
    assert res.fit_count == 1 and res.mismatch_count == 1
    assert "샘플페이" in res.warnings[0] and "샘플애그" not in res.warnings[0]
