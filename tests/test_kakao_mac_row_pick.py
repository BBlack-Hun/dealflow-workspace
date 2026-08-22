"""맥 발송기 — 검색 결과에서 어느 방을 열 것인가.

카톡 검색은 방 제목뿐 아니라 **참여자 이름으로도** 걸린다. 이름이 흔하면
그 사람이 낀 단체방이 잔뜩 나오고, 첫 행은 대개 그중 하나다.
실기에서 '홍길동' 을 검색했더니 본인 방을 못 찾았다.

그래서 **제목이 정확히 같은 행**만 누른다. 창 제목 검증이 오발송은 막아 주지만,
남의 대화창을 여는 것 자체를 피해야 한다.
"""
from __future__ import annotations

import pytest

mac = pytest.importorskip("agent.sender.kakao_mac")


def test_picks_the_exact_title_not_the_first_row():
    """참여자로 걸린 단체방이 위에 오더라도 정확한 방을 고른다."""
    titles = [
        "○○벤처스 딜 공유방",        # 홍길동이 참여자로 들어 있는 방
        "스타트업 IR 네트워킹",
        "홍길동",                    # ← 이게 찾는 방
        "홍길동 심사역님 ○○벤처스",
    ]
    assert mac._exact_row(titles, "홍길동") == 3


def test_no_exact_match_returns_none():
    """비슷한 이름만 있으면 고르지 않는다 — 아무거나 열면 남의 대화창이다."""
    titles = ["홍길동 심사역님 ○○벤처스", "홍길동님과의 대화"]
    assert mac._exact_row(titles, "홍길동") is None


def test_duplicate_titles_are_not_picked():
    """같은 제목이 둘이면 어느 쪽인지 알 수 없다."""
    titles = ["홍길동", "다른 방", "홍길동"]
    assert mac._exact_row(titles, "홍길동") is None


def test_row_number_is_one_based():
    assert mac._exact_row(["홍길동"], "홍길동") == 1


def test_blank_rows_keep_their_place():
    """제목을 못 읽은 행도 자리를 지켜야 행 번호가 안 밀린다."""
    titles = ["", "", "홍길동"]
    assert mac._exact_row(titles, "홍길동") == 3


@pytest.mark.parametrize("title, want", [
    ("  홍길동  ", True),                     # 앞뒤 공백은 무시
    ("홍길동 심사역님  ○○벤처스", True),      # 연속 공백만 줄인다
])
def test_whitespace_is_normalised(title, want):
    target = " ".join(title.split())
    assert (mac._exact_row([title], target) == 1) is want


def test_other_differences_are_not_forgiven():
    """한 글자만 달라도 다른 방이다 — 임의로 맞춰 주면 엉뚱한 방을 연다."""
    assert mac._exact_row(["홍길동 심사역님 ○○벤처스"],
                          "홍길동 심사역 ○○벤처스") is None
    assert mac._exact_row(["홍길동"], "김정 훈") is None


def test_long_result_lists_are_capped():
    """이름이 흔하면 결과가 수십 건이다 — 살펴볼 범위는 정해 둔다."""
    assert mac.MAX_SEARCH_ROWS >= 40
