"""탭이 정하는 차례 — 스타트업DB 는 **수신일 최신순**.

## 왜 이 검사가 있나

두 탭은 같은 기업 레코드의 두 가지 보기지만 **읽는 이유가 다르다.**
`IR 기업 현황` 은 아는 기업을 찾아 여는 자리라 이름순이 맞고, `스타트업DB` 는
홍보메일 답장이 들어온 순서로 훑는 자리라 **방금 들어온 곳이 맨 위**여야 한다.

## 걸리는 자리

`수신일` 은 **글자 칸**이다(모델 주석 참고 — 시트에 `2025-01-07` 도 있고
`날짜 미정` 도 있다). 그냥 내림차순으로 세우면 `날` 이 숫자보다 커서
**`날짜 미정` 이 맨 위로 올라온다** — 가장 최근을 보려고 정렬해 놓고 정작
날짜 없는 줄부터 읽게 된다.

날짜는 **못박아 둔다.** 오늘 날짜로 만들면 내일 다른 것을 재는 검사가 된다.
이름·값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re

import pytest

from app.routers.companies import sort_for_tab

# 운영과 같은 분포를 작게 줄인 표본. **섞어서 넣는다** — 이미 정렬된 것을
# 넣으면 정렬이 아무 일도 안 해도 통과한다.
SAMPLE = [
    {"name": "샘플다라소재", "received_at": "2025-01-07"},
    {"name": "샘플가나헬스", "received_at": ""},            # 아직 안 적음
    {"name": "샘플마바에듀", "received_at": "2026-08-11"},
    {"name": "샘플나다물류", "received_at": "날짜 미정"},   # 날짜가 아니다
    {"name": "샘플바사푸드", "received_at": "2026-08-11"},  # 같은 날 — 이름순
    {"name": "샘플라마핀테크", "received_at": "2025-12-31"},
]


def _order(tab: str) -> list:
    return [r["name"] for r in sort_for_tab([dict(r) for r in SAMPLE], tab)]


def test_스타트업DB_는_수신일_최신순이다():
    assert _order("db")[:3] == ["샘플마바에듀", "샘플바사푸드", "샘플라마핀테크"]


def test_같은_날에_들어온_곳은_이름순이다():
    """차례가 요청마다 흔들리면 어제 본 자리에서 못 찾는다."""
    same_day = [n for n in _order("db") if n in ("샘플마바에듀", "샘플바사푸드")]
    assert same_day == ["샘플마바에듀", "샘플바사푸드"]


def test_날짜가_아닌_줄과_빈_줄은_맨_아래로_간다():
    """`날짜 미정` 은 글자로 세우면 **맨 위**로 온다 — 그 순간 '최신순' 이 거짓말이 된다."""
    order = _order("db")
    assert order[-2:] == ["샘플가나헬스", "샘플나다물류"], order
    assert order.index("샘플라마핀테크") < order.index("샘플나다물류")


def test_IR_기업_현황의_차례는_안_바뀐다():
    """이 탭에는 `수신일` 칸 자체가 없다 — 차례를 바꾸면 왜 그 순서인지 알 길이 없다."""
    assert _order("status") == [r["name"] for r in SAMPLE]
    assert _order("") == [r["name"] for r in SAMPLE]


def test_뒤에_말이_붙은_날짜도_날짜로_본다():
    """통째로 '날짜 없음' 으로 밀어 내는 것보다 앞의 날짜로 자리를 잡는 편이 낫다."""
    rows = [{"name": "샘플아자바이오", "received_at": "2026-09-01 (재확인)"},
            {"name": "샘플자차모빌", "received_at": "2026-08-11"}]
    assert [r["name"] for r in sort_for_tab(rows, "db")] == ["샘플아자바이오", "샘플자차모빌"]


# --- 화면 --------------------------------------------------------------------

@pytest.fixture()
def rows(db):
    from app.models import IrCompany

    for spec in SAMPLE:
        db.add(IrCompany(name=spec["name"], received_at=spec["received_at"] or None))
    db.commit()


def _shown(html: str) -> list:
    """표에 실제로 그려진 차례 — 첫 칸(`data-field="name"`)의 글자."""
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r'data-field="name"[^>]*>([^<]+)<', body)


def test_화면에서도_스타트업DB_가_최신순으로_그려진다(logged_in, rows):
    shown = _shown(logged_in.get("/companies?tab=db").text)
    assert shown[0] == "샘플마바에듀", shown
    assert shown[-2:] == ["샘플가나헬스", "샘플나다물류"], shown


def test_화면에서도_IR_기업_현황은_이름순_그대로다(logged_in, rows):
    shown = _shown(logged_in.get("/companies").text)
    assert shown == sorted(shown), shown
