"""넓은 표의 키를 **상수로 짐작하지 않고 재는가.**

## 왜 이 검사가 있나

넓은 표는 화면 높이에 맞춰 자른다. 안 자르면 표가 페이지만큼 길어져서 가로
스크롤바가 문서 맨 아래로 밀리고, 옆으로 밀려면 끝까지 내려갔다가 다시
올라와야 한다(까닭은 app.css 에 적혀 있다).

문제는 **어디서부터 자르느냐**였다. 예전에는 표 위쪽 머리 영역(머리말·툴바·
요약 패널)을 `--head: 320px` 이라고 짐작했는데, 감싸개는 화면 맨 위가 아니라
그 머리 **밑**에서 시작한다. 머리가 320px 을 넘으면 잘라 낸 표의 아래쪽 끝이
화면 밖으로 나가, 막으려던 사고가 그대로 났다. 브라우저에서 잰 값:

    딜 소싱 291 · IR 기업 현황 301 · 투자사 관리 현황 443 · 스타트업DB 478px

투자사 관리 현황·스타트업DB 는 스크롤바가 화면 아래 123·158px 밖에 있었다.
머리 높이는 화면마다 다르고 칸·패널이 붙을 때마다 또 자란다 — **어떤 상수를
골라도 언젠가는 틀린다.** 그래서 `table_fit.js` 가 감싸개의 실제 자리를 재서
`--head` 를 채운다.

## 여기서 보는 것

셈이 맞는지는 브라우저 쪽 검사(tests/js/table_fit_test.js)가 본다. 여기서는
그 셈이 **화면에 닿는 길**을 지킨다 — 재는 코드가 모든 화면에 실리는지,
CSS 가 그 값을 실제로 쓰는지, 그리고 폰 경계가 두 벌이 되지 않았는지.
"""
from __future__ import annotations

import pathlib
import re

CSS = pathlib.Path("app/static/css/app.css")
BASE = pathlib.Path("app/templates/base.html")
FIT_JS = pathlib.Path("app/static/js/table_fit.js")
TEMPLATES = pathlib.Path("app/templates")

PHONE = "@media (max-width: 720px)"


def _css() -> str:
    """주석을 지운 CSS. 안 지우면 규칙 바로 위의 설명이 선택자에 딸려 온다."""
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _block(css: str, header: str) -> str:
    """`@media …{ … }` 한 덩어리를 통째로 꺼낸다(중괄호 짝을 센다)."""
    start = css.index(header)
    depth = 0
    for j in range(css.index("{", start), len(css)):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                return css[start:j + 1]
    raise AssertionError(f"{header} 블록이 안 닫혔다")


def _wide_rule(css: str) -> str:
    """`.table-wrap.wide { … }` 본체. 다른 선택자가 딸려 붙은 것은 뺀다."""
    hits = [m.group(2) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)
            if m.group(1).strip() == ".table-wrap.wide"]
    assert hits, ".table-wrap.wide 규칙이 없다"
    return " ".join(hits)


def test_모든_화면이_재는_코드를_싣는다():
    """표가 있는 화면마다 붙이면 새 화면에서 빠뜨렸을 때 조용히 사라진다.

    그래서 base 에 둔다 — 여기서 빠지면 모든 화면이 한꺼번에 예전으로 돌아간다.
    """
    assert "js/table_fit.js" in BASE.read_text(encoding="utf-8"), (
        "base.html 이 table_fit.js 를 안 싣는다 — 표 키가 다시 상수로 돌아간다"
    )
    assert FIT_JS.exists(), "table_fit.js 가 없다"
    assert 'setProperty("--head"' in FIT_JS.read_text(encoding="utf-8"), (
        "table_fit.js 가 `--head` 를 안 채운다 — CSS 의 대비값만 쓰이게 된다"
    )


def test_표_키는_잰_값으로_정해진다():
    """`max-height` 도 `min-height` 도 잰 값(`--head`)을 거쳐야 한다.

    `min-height` 가 `max-height` 를 이기므로, 최소 키를 상수로 두면 자리가
    좁은 화면에서 표가 다시 화면 밖으로 삐져나간다(1512×768 의 스타트업DB —
    머리 478px 에 최소 키 320px 이면 30px 이 잘렸다).
    """
    rule = _wide_rule(_css())
    max_h = re.search(r"max-height:\s*([^;]+);", rule)
    min_h = re.search(r"min-height:\s*([^;]+);", rule)
    assert max_h and "var(--head)" in max_h.group(1), (
        f"`.table-wrap.wide` 의 max-height 가 잰 값을 안 쓴다: {max_h and max_h.group(1)}"
    )
    assert min_h and "var(--head)" in min_h.group(1), (
        "`.table-wrap.wide` 의 min-height 가 상수다 — 자리가 좁으면 그만큼 "
        f"화면 밖으로 밀린다: {min_h and min_h.group(1)}"
    )


def test_폰_경계는_CSS_한_곳에만_있다():
    """맞춤 방식(`--fit`)은 CSS 가 정하고 JS 는 읽기만 한다.

    폰은 사이드바가 표 위로 쌓여 머리가 650~1,030px 이라, 머리 밑에 맞추면
    표에 남는 자리가 없다 — 거기서는 화면 한 장을 통째로 준다. 그 경계를
    JS 가 다시 재면 화면 크기 기준이 두 벌이 되어, 한쪽만 고쳐졌을 때
    아무도 모른다.
    """
    css = _css()
    assert re.search(r"--fit:\s*under", _wide_rule(css)), (
        "`.table-wrap.wide` 에 기본 맞춤 방식(`--fit: under`)이 없다"
    )
    assert re.search(r"--fit:\s*screen", _block(css, PHONE)), (
        f"{PHONE} 안에 폰용 맞춤 방식(`--fit: screen`)이 없다"
    )
    js = FIT_JS.read_text(encoding="utf-8")
    assert '--fit' in js, "table_fit.js 가 `--fit` 을 안 읽는다"
    assert "matchMedia" not in js and "720" not in js, (
        "table_fit.js 가 폰 경계를 다시 적었다 — 경계는 CSS 한 곳에만 둔다"
    )


def test_넓은_표_감싸개의_이름은_하나다():
    """감싸개는 `.table-wrap` 이거나 `.table-wrap.wide` 다 — 세 번째는 없다.

    투자컨설턴트 현황이 `table-wrap wide-scroll` 이라는 자기만의 이름을 달고
    있었다. 그 화면이 만들어질 때(#19) 공용 `.wide` 가 아직 없어서 `overflow-x`
    한 줄을 따로 적어 둔 것인데, 나흘 뒤 같은 뜻의 공용 규칙이 생기고도(#38)
    이 화면만 안 옮겨 왔다. 그래서 그 뒤 `.wide` 에 붙은 것이 **하나도** 안
    붙었다 — 표 키 자르기·머리행 세로 고정·최소 키. 셋 다 이 표에도 필요한
    것이었고, 마지막 것이 없어서 줄이 적은 탭에서 머리글 필터 창이 감싸개
    밖으로 잘렸다(PC 33px · 폰 26px).

    이름이 두 벌이면 한쪽만 고쳐진다. 새 이름을 세우는 대신 `.wide` 를 쓰고,
    그 표만의 사정(폭 등)은 그 표의 선택자에 적는다
    (`.table-wrap.wide .sheet-table` 의 min-width 가 그 예다).
    """
    bad = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'class="table-wrap([^"]*)"', text):
            extra = [c for c in m.group(1).split() if c != "wide"]
            if extra:
                bad.append(f"{path.name}: table-wrap {' '.join(extra)}")
    assert not bad, (
        "감싸개에 `.wide` 말고 다른 이름이 붙었다 — 그 표만 `.wide` 의 규칙"
        "(표 키 자르기·머리행 고정·최소 키)에서 빠진다: " + ", ".join(bad)
    )


def test_투자컨설턴트_표도_넓은_표다():
    """55줄짜리 탭이 있고 폭이 1,200px 인 표다 — `.wide` 가 아니면 다시 샌다.

    위 검사가 이름이 갈리는 것을 막지만, 감싸개에서 `wide` 를 **지우는** 것은
    못 막는다. 이 화면이 그 사고가 난 자리라 못 박아 둔다.
    """
    text = (TEMPLATES / "consulting.html").read_text(encoding="utf-8")
    assert 'class="table-wrap wide"' in text, (
        "투자컨설턴트 현황의 표 감싸개가 `.table-wrap.wide` 가 아니다 — "
        "표가 화면 밖으로 길어지고(가로 스크롤바가 문서 아래로 밀린다) "
        "줄이 적은 탭에서는 머리글 필터 창이 잘린다"
    )


def test_컨설턴트_표는_공용_폭을_안_받는다():
    """`.wide` 의 공용 min-width(2,030px)는 컬럼이 다른 이 표의 값이 아니다.

    이 표는 `grid-table sheet-table` 두 이름을 같이 달고 있어서, 감싸개가
    `.wide` 가 되는 순간 `.table-wrap.wide .grid-table { min-width: 2030px }`
    를 함께 받는다. 폭 합은 1,200px 이라 830px 이 빈 채로 가로로 밀린다.
    그래서 자기 규칙도 `.wide` 를 같이 적어 **셈을 맞춰** 이기게 해 뒀다 —
    선택자에서 `.wide` 가 빠지면 조용히 공용 값에 진다.
    """
    css = _css()
    assert re.search(r"\.table-wrap\.wide\s+\.sheet-table\s*\{[^}]*min-width", css), (
        "`.table-wrap.wide .sheet-table` 의 min-width 규칙이 없다 — "
        "컨설턴트 표가 공용 폭(2,030px)을 받아 빈 채로 가로로 밀린다"
    )
