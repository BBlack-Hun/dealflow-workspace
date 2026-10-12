"""표의 차례 — **두 탭 다 수신일 최신순**, 규칙은 하나.

## 왜 이 검사가 있나

두 탭은 같은 기업 레코드의 두 가지 보기다. 예전에는 차례만 달랐다 —
`스타트업DB` 는 수신일 최신순, `IR 기업 현황` 은 이름순. 그 탭에는 `수신일`
칸이 없어서 "차례를 바꾸면 왜 그 순서인지 화면에서 알 길이 없다" 는 까닭이었다.

사용자가 IR 기업 현황도 **새로 들어온 곳이 맨 위**이기를 원했다(「등록일
최신순」 — 여기서는 `수신일`(`received_at`)로 읽었다. 까닭은
`routers/companies.py` 의 `sort_by_received`). 그래서 지키는 것이 넷이다.

  1. **규칙이 하나다.** 두 탭이 같은 함수를 부르고, 그 함수는 탭을 묻지 않는다.
     탭마다 두면 `날짜 미정` 을 어디에 두느냐가 한쪽에서만 고쳐지는 날이 온다.
  2. **왜 그 순서인지 보인다.** IR 기업 현황에도 `수신일` 칸이 서고, 표 위에
     기본 차례가 한 줄로 적힌다 — 옛 까닭을 피하지 않고 없앤다.
  3. **이름순으로 돌아갈 길이 있다.** `기업명` 머리글을 누르거나 `?sort=name`.
     세우는 일은 브라우저가 한다(`table_sort.js`) — 서버는 그 값을 모른다.
  4. 날짜 없는 줄은 **맨 아래**, 그 안은 이름순(예전 스타트업DB 규칙 그대로).

## 걸리는 자리

`수신일` 은 **글자 칸**이다(모델 주석 참고 — 시트에 `2025-01-07` 도 있고
`날짜 미정` 도 있다). 그냥 내림차순으로 세우면 `날` 이 숫자보다 커서
**`날짜 미정` 이 맨 위로 올라온다** — 가장 최근을 보려고 정렬해 놓고 정작
날짜 없는 줄부터 읽게 된다.

날짜는 **못박아 둔다.** 오늘 날짜로 만들면 내일 다른 것을 재는 검사가 된다.
이름·값은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import inspect
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.routers.companies import company_rows, sort_by_received

ROOT = Path(__file__).resolve().parent.parent

# 운영과 같은 분포를 작게 줄인 표본. **섞어서 넣는다** — 이미 정렬된 것을
# 넣으면 정렬이 아무 일도 안 해도 통과한다. 이름순과 수신일순이 **서로 다르게**
# 고른다 — 같으면 IR 기업 현황이 예전 차례(이름순) 그대로여도 통과한다.
SAMPLE = [
    {"name": "샘플다라소재", "received_at": "2025-01-07"},
    {"name": "샘플가나헬스", "received_at": ""},            # 아직 안 적음
    {"name": "샘플마바에듀", "received_at": "2026-08-11"},
    {"name": "샘플나다물류", "received_at": "날짜 미정"},   # 날짜가 아니다
    {"name": "샘플바사푸드", "received_at": "2026-08-11"},  # 같은 날 — 이름순
    {"name": "샘플라마핀테크", "received_at": "2025-12-31"},
]

# 수신일 최신순 · 같은 날은 이름순 · 날짜 없는 둘은 맨 아래(그 안은 이름순)
NEWEST_FIRST = ["샘플마바에듀", "샘플바사푸드", "샘플라마핀테크", "샘플다라소재",
                "샘플가나헬스", "샘플나다물류"]


def _order() -> list:
    return [r["name"] for r in sort_by_received([dict(r) for r in SAMPLE])]


# --- 규칙 ----------------------------------------------------------------------

def test_수신일_최신순이다():
    assert _order() == NEWEST_FIRST


def test_표본이_이름순과_다르다():
    """이름순과 같은 표본이면 '이름순 그대로' 인 옛 차례도 통과한다 — 검사가 빈다."""
    assert NEWEST_FIRST != sorted(NEWEST_FIRST)


def test_같은_날에_들어온_곳은_이름순이다():
    """차례가 요청마다 흔들리면 어제 본 자리에서 못 찾는다."""
    same_day = [n for n in _order() if n in ("샘플마바에듀", "샘플바사푸드")]
    assert same_day == ["샘플마바에듀", "샘플바사푸드"]


def test_날짜가_아닌_줄과_빈_줄은_맨_아래로_간다():
    """`날짜 미정` 은 글자로 세우면 **맨 위**로 온다 — 그 순간 '최신순' 이 거짓말이 된다."""
    order = _order()
    assert order[-2:] == ["샘플가나헬스", "샘플나다물류"], order
    assert order.index("샘플라마핀테크") < order.index("샘플나다물류")


def test_뒤에_말이_붙은_날짜도_날짜로_본다():
    """통째로 '날짜 없음' 으로 밀어 내는 것보다 앞의 날짜로 자리를 잡는 편이 낫다."""
    rows = [{"name": "샘플아자바이오", "received_at": "2026-09-01 (재확인)"},
            {"name": "샘플자차모빌", "received_at": "2026-08-11"}]
    assert [r["name"] for r in sort_by_received(rows)] == ["샘플아자바이오", "샘플자차모빌"]


def test_규칙은_탭을_묻지_않는다():
    """**두 벌로 갈라질 자리가 없어야 한다.**

    탭을 받는 순간 `if tab == …` 한 줄로 다시 갈라질 수 있다 — 예전 모양이
    바로 그것이었다(`sort_for_tab(rows, tab)`). 표 한 벌을 만드는 쪽도 탭을
    안 받는다: 거기서 탭을 받으면 차례 말고는 쓸 데가 없다.
    """
    assert list(inspect.signature(sort_by_received).parameters) == ["rows"]
    assert "tab" not in inspect.signature(company_rows).parameters


# --- 화면 ----------------------------------------------------------------------

@pytest.fixture()
def rows(db):
    from app.models import IrCompany

    for spec in SAMPLE:
        db.add(IrCompany(name=spec["name"], received_at=spec["received_at"] or None))
    db.commit()


def _body(html: str) -> str:
    return html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def _head(html: str) -> str:
    return html.split("<thead>", 1)[1].split("</thead>", 1)[0]


def _shown(html: str) -> list:
    """표에 실제로 그려진 차례 — 이름 칸(`data-field="name"`)의 글자."""
    return re.findall(r'data-field="name"[^>]*>([^<]+)<', _body(html))


def _head_names(html: str) -> list:
    out = []
    for inner in re.findall(r"<th\b[^>]*>(.*?)</th>", _head(html), re.S):
        out.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip())
    return out


@pytest.mark.parametrize("url", ["/companies", "/companies?tab=db"])
def test_두_탭_다_수신일_최신순으로_그려진다(logged_in, rows, url):
    assert _shown(logged_in.get(url).text) == NEWEST_FIRST


def test_서버는_sort_를_모른다(logged_in, rows):
    """`?sort=name` 이 와도 **서버가 그리는 차례는 그대로**다 — 세우는 것은 브라우저다.

    서버까지 그 값으로 차례를 바꾸면 한 주소를 두 손이 읽는다. 그러면 머리글을
    세 번 눌러 정렬을 '끄면' 돌아갈 자리(서버가 그린 차례)가 이름순이 되어,
    기본 차례(수신일 최신순)로 돌아갈 길이 사라진다.
    """
    for url in ("/companies?sort=name", "/companies?tab=db&sort=name"):
        assert _shown(logged_in.get(url).text) == NEWEST_FIRST, url


# --- 왜 그 순서인지 보인다 ---------------------------------------------------

def test_IR_기업_현황에도_수신일_칸이_선다(logged_in, rows):
    """예전 까닭("이 탭에는 `수신일` 칸이 없다")을 **없앤다.**

    자리는 `기업명` 바로 오른쪽 — 고정된 두 칸 바로 뒤라 표를 열자마자
    이름과 날짜가 나란히 보인다(`companies.html` 의 그 머리글 주석).
    (머리와 칸 수가 함께 늘었는지는 tests/test_company_updated_at.py 의
    `test_머리와_칸이_같은_수만큼_늘었다` 가 빈 표 안내줄까지 센다.)
    """
    html = logged_in.get("/companies").text
    names = _head_names(html)
    assert "수신일" in names, f"IR 기업 현황에 `수신일` 머리글이 없습니다: {names}"
    assert names.index("수신일") == names.index("기업명") + 1, (
        f"`수신일` 이 `기업명` 바로 뒤가 아닙니다 — 지금 차례: {names}")


def test_수신일_칸에_값이_그대로_보인다(logged_in, rows):
    """`날짜 미정` 도 그대로 보여야 한다 — 그 줄이 왜 맨 아래인지가 그 글자다."""
    body = _body(logged_in.get("/companies").text)
    shown = re.findall(r'data-field="received_at"[^>]*>([^<]*)<', body)
    assert shown == [next(s["received_at"] for s in SAMPLE if s["name"] == n)
                     for n in NEWEST_FIRST], shown


@pytest.mark.parametrize("url", ["/companies", "/companies?tab=db"])
def test_기본_차례가_화면에_적혀_있다(logged_in, rows, url):
    """칸이 있어도 **그 칸으로 세워져 있다는 표시**는 머리글 어디에도 없다.

    꼬리표(`▲`/`▼`)는 사람이 눌러 고른 차례에만 선다(`table_sort.js`). 그래서
    한 줄로 적는다 — 이름순으로 바꾸는 자리도 함께.
    """
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", logged_in.get(url).text))
    assert "기본 차례는 수신일 최신순" in text
    assert "기업명 머리글을 누르면 이름순" in text


# --- 이름순으로 돌아갈 길 -----------------------------------------------------

@pytest.mark.parametrize("url", ["/companies", "/companies?tab=db"])
def test_이름순은_기업명_머리글로_고른다(logged_in, rows, url):
    """두 탭 다 `기업명` 머리글이 `name` 으로 세운다고 선언하고, 줄마다 그 값을 싣는다.

    셋 중 하나만 빠져도 화면은 멀쩡하다 — 머리글이 그냥 글자로 남거나 눌러도
    아무 줄도 안 움직인다(tests/test_contacts_sort.py 머리말).
    """
    html = logged_in.get(url).text
    heads = dict((name, attrs) for attrs, name in (
        (a, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip())
        for a, inner in re.findall(r"<th\b([^>]*)>(.*?)</th>", _head(html), re.S)))
    assert 'data-sort="name"' in heads.get("기업명", ""), heads.get("기업명")

    carried = re.findall(r'<tr data-id="\d+"[^>]*?data-s-name="([^"]*)"', _body(html), re.S)
    assert carried == NEWEST_FIRST, (
        "줄마다 이름(`data-s-name`)을 안 싣습니다 — 그 줄은 정렬에서 빠집니다: "
        f"{carried}")
    assert re.search(r'src="/static/js/table_sort\.js\?v=[a-f0-9]{8}"', html)


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_sort_name_은_브라우저에서_이름순으로_선다():
    """`?sort=name` 으로 열면 이름순, 기업명을 눌러 오름 → 내림 → 끔(=수신일순).

    두 탭 모두. 세우는 일은 브라우저 코드라 파일을 그대로 돌려 본다
    (tests/js/company_received_order_test.js). 로컬에서는
    `node tests/js/company_received_order_test.js` 로도 돈다.
    """
    script = ROOT / "tests" / "js" / "company_received_order_test.js"
    out = subprocess.run([shutil.which("node"), str(script)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
