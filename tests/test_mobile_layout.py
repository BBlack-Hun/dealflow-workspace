"""폰에서 화면이 가로로 밀리지 않는가.

이 앱은 **표가 핵심**이라 칸을 좁혀 짜부라뜨릴 수 없다. 그래서 넓은 표는
그대로 두고 **표 안에서만** 가로로 민다. 문제는 그 폭을 받아 줄 상자가 없을
때다 — 표가 페이지 본문을 통째로 밀어내서, 폰에서는 글 한 줄 읽을 때마다
좌우로 흔들어야 했다.

실제로 이렇게 깨져 있었다(390px 아이폰에서 잰 값, 본문 폭은 390 이어야 한다):

    주간 업무        791px   ← 반복 업무 표가 감싸지지 않았다
    딜 진행 관리    1,065px   ← 표가 든 칸이 표 폭만큼 벌어졌다
    업무 보고        804px
    팀 현황          808px

원인은 셋이고, 아래 검사는 그 셋을 못 박는다.

  1. `min-width` 를 준 표가 **`.table-wrap` 밖**에 있었다.
     받아 줄 상자가 없으니 그 폭이 그대로 페이지를 밀었다.
  2. 표가 든 격자 칸이 `1fr` 이었다. `1fr` 은 `minmax(auto, 1fr)` 이라
     **속 내용의 최소폭 아래로는 안 줄어든다** — 한 줄로 세워 놓고도 칸이
     표 폭(2,030px)만큼 벌어졌다.
  3. 표가 아닌 것도 밀었다. 여러 칸으로 나뉜 **줄**(`.due-list li`)이 폰에서
     그대로 서 있었고, 폰 규칙에 적혀 있던 `flex-wrap` 은 격자에 아무 일도
     하지 않았다 — 딜 진행 관리가 422·441px 이었다(7절).

화면 이름을 여기 적어 두지 않는다. 템플릿 폴더를 훑으므로 **화면이 새로
생기면 저절로 걸린다.**
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

CSS = pathlib.Path("app/static/css/app.css")
TEMPLATES = pathlib.Path("app/templates")
FILTERS_JS = pathlib.Path("app/static/js/filters.js")

# 화면 폭. 폰은 이 값 아래로는 안 내려간다고 보고 규칙을 건다.
PHONE = "@media (max-width: 720px)"
TABLET = "@media (max-width: 1100px)"


def _strip_comments(text: str) -> str:
    """주석 안의 예시 마크업이 진짜 태그로 세어지지 않게 지운다."""
    text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _css() -> str:
    """주석을 지운 CSS. 안 지우면 규칙 바로 위의 설명이 선택자에 딸려 온다."""
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _block(css: str, header: str) -> str:
    """`@media …{ … }` 한 덩어리를 통째로 꺼낸다(중괄호 짝을 센다)."""
    start = css.index(header)
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        if css[j] == "{":
            depth += 1
        elif css[j] == "}":
            depth -= 1
            if depth == 0:
                return css[start:j + 1]
    raise AssertionError(f"{header} 블록이 안 닫혔다")


def _rules(css: str):
    """(선택자, 속성들) 쌍. @media 안쪽까지 평평하게 훑는다."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = m.group(1).strip()
        if selector.startswith("@"):
            continue
        yield selector, m.group(2)


def _screen_templates():
    """부분 조각(`_` 로 시작)이 아닌 **화면** 템플릿."""
    return [p for p in sorted(TEMPLATES.glob("*.html"))
            if not p.name.startswith("_") and p.name != "base.html"]


# ── 1. 화면은 전부 반응형 뼈대를 쓴다 ───────────────────────────────────────

def test_every_screen_is_built_on_the_responsive_base():
    """새 화면이 생겨도 저절로 폰 규칙을 받아야 한다.

    `base.html` 을 안 거치는 화면(로그인)은 제 머리에 뷰포트를 달고 있어야
    한다 — `width=1280` 이던 때는 폰에서 축소된 PC 화면이 떠서 글자를 읽으려면
    매번 확대해야 했다.
    """
    for path in _screen_templates():
        text = path.read_text(encoding="utf-8")
        if 'extends "base.html"' in text:
            continue
        assert "width=device-width" in text, f"{path.name} 이 base 도 안 쓰고 뷰포트도 없다"


# ── 2. 표는 반드시 스크롤 상자 안에 ─────────────────────────────────────────

def _tables_outside_a_wrap():
    """`grid-table` 중 `.table-wrap` 안에 안 들어 있는 것.

    div 여닫는 것을 세어 어느 상자 안인지 따라간다. Jinja 조건문이 끼어
    있어도 가지 안에서 짝이 맞으므로 실제 템플릿에서는 어긋나지 않는다.
    """
    tag = re.compile(r"<(/?)(div|table)\b([^>]*)>", re.I)
    css_class = re.compile(r'class\s*=\s*"([^"]*)"', re.I)
    loose = []
    for path in sorted(TEMPLATES.glob("*.html")):
        text = _strip_comments(path.read_text(encoding="utf-8"))
        stack: list[set] = []
        for m in tag.finditer(text):
            closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
            if name == "div":
                if closing:
                    if stack:
                        stack.pop()
                elif not attrs.rstrip().endswith("/"):
                    found = css_class.search(attrs)
                    stack.append(set(found.group(1).split()) if found else set())
                continue
            if closing:
                continue
            found = css_class.search(attrs)
            classes = set(found.group(1).split()) if found else set()
            if "grid-table" not in classes:
                continue
            if not any("table-wrap" in box for box in stack):
                line = text[:m.start()].count("\n") + 1
                loose.append(f"{path.name}:{line}")
    return loose


def test_every_table_sits_in_a_horizontal_scroll_box():
    """감싸지 않은 표는 제 폭으로 **페이지 전체**를 민다.

    폰 규칙이 표에 `min-width: 760px` 을 주는데, 받아 줄 상자가 없으면 그
    760px 이 그대로 본문 폭이 된다 — 주간 업무가 791px 이었다.
    """
    loose = _tables_outside_a_wrap()
    assert not loose, (
        "다음 표가 `.table-wrap` 밖에 있다 — 폰에서 페이지가 통째로 가로로 "
        f"밀린다: {', '.join(loose)}")


def test_the_sweep_would_notice_a_bare_table(tmp_path, monkeypatch):
    """검사 자체가 진짜로 잡는지. (안 잡히는 검사는 없는 것과 같다)

    새 화면을 하나 만들어 놓고, 감싸지 않은 표를 집어내는지 본다.
    """
    fake = tmp_path / "templates"
    fake.mkdir()
    (fake / "new_screen.html").write_text(
        '<section class="panel"><table class="grid-table"><tr><td>a</td></tr></table></section>',
        encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "TEMPLATES", fake)
    assert _tables_outside_a_wrap() == ["new_screen.html:1"]

    # 감싸 두면 통과해야 한다 — 아무거나 잡는 검사여도 곤란하다
    (fake / "new_screen.html").write_text(
        '<div class="table-wrap"><table class="grid-table"><tr><td>a</td></tr></table></div>',
        encoding="utf-8")
    assert _tables_outside_a_wrap() == []


def test_the_scroll_box_really_scrolls():
    """상자가 가로 스크롤을 안 받으면 감싸 봐야 소용없다."""
    for selector, body in _rules(_css()):
        if selector == ".table-wrap":
            assert re.search(r"overflow-x:\s*auto", body), \
                ".table-wrap 이 가로 스크롤을 안 받는다"
            return
    raise AssertionError(".table-wrap 규칙이 없다")


def test_table_widths_are_pinned_only_inside_the_scroll_box():
    """폭을 못 박는 규칙과 가로 스크롤은 **늘 한 쌍**이어야 한다.

    예전에는 `.grid-table { min-width: 760px }` 처럼 **모든 표**에 걸어서,
    감싸지 않은 표까지 760px 로 벌어졌다.
    """
    bad = []
    for selector, body in _rules(_css()):
        if not re.search(r"min-width:\s*\d", body):
            continue
        for one in selector.split(","):
            one = one.strip()
            # 표를 가리키는 규칙인가 (마지막 조각이 표 클래스)
            last = one.split()[-1] if one.split() else ""
            if not re.search(r"(^|\.)(grid-table|sheet-table)$", last):
                continue
            # `.table-wrap` 안쪽으로 한정돼 있으면 통과
            if ".table-wrap" in one:
                continue
            bad.append(f"{one} {{{body.strip()}}}")
    assert not bad, ("표 폭을 `.table-wrap` 밖에서 못 박고 있다 — 받아 줄 상자가 "
                     f"없는 표까지 벌어진다: {bad}")


# ── 3. 표가 든 칸은 화면만큼만 ──────────────────────────────────────────────

def _classes_wrapping_a_table() -> set:
    """`.table-wrap` 을 품고 있는 **바깥 상자들의 클래스**.

    이 상자들이 표를 안고 있으므로, 얘들이 안 줄어들면 표 폭이 그대로
    페이지 폭이 된다. 템플릿을 훑어 모으므로 새 화면도 저절로 들어온다.
    """
    box = re.compile(r"<(/?)(div|section|main|aside|form|li|ul)\b([^>]*)>", re.I)
    css_class = re.compile(r'class\s*=\s*"([^"]*)"', re.I)
    holders: set = set()
    for path in sorted(TEMPLATES.glob("*.html")):
        text = _strip_comments(path.read_text(encoding="utf-8"))
        stack: list[set] = []
        for m in box.finditer(text):
            closing, attrs = m.group(1), m.group(3)
            if closing:
                if stack:
                    stack.pop()
                continue
            if attrs.rstrip().endswith("/"):
                continue
            found = css_class.search(attrs)
            classes = set(found.group(1).split()) if found else set()
            if "table-wrap" in classes:
                for outer in stack:
                    holders |= outer
            stack.append(classes)
    return holders


def test_stacked_columns_can_shrink_below_their_contents():
    """`1fr` 은 `minmax(auto, 1fr)` 이라 **속 내용의 최소폭**이 바닥이다.

    안에 2,030px 짜리 표가 있으면 한 줄로 세워 놓고도 칸이 2,030px 로 벌어져
    페이지가 밀린다 — 딜 진행 관리가 1,065px 이었다.

    표를 안고 있는 상자에만 건다. 글자만 든 격자(`.tl-item` 같은 활동 이력
    줄)는 `1fr` 이어도 밀어낼 것이 없다.
    """
    holders = _classes_wrapping_a_table()
    assert holders, "표를 감싼 상자를 하나도 못 찾았다 — 훑기가 고장 났다"
    css = _css()
    for header in (TABLET, PHONE):
        for selector, body in _rules(_block(css, header)):
            m = re.search(r"grid-template-columns:\s*([^;]+)", body)
            if not m or "minmax" in m.group(1):
                continue
            for one in selector.split(","):
                hit = {c.lstrip(".") for c in re.findall(r"\.[a-zA-Z0-9_-]+", one)} & holders
                assert not hit, (
                    f"{header} 의 `{one.strip()}` 가 `{m.group(1).strip()}` 다 — "
                    f"{sorted(hit)} 는 표를 안고 있으므로 `minmax(0, 1fr)` 이어야 "
                    "칸이 화면만큼만 쓴다")


def test_boxes_inside_a_stacked_column_can_shrink_too():
    """칸을 줄여도 **그 안의 상자**가 안 줄면 상자가 칸 밖으로 삐져나온다."""
    block = _block(_css(), TABLET)
    assert re.search(r"\.panel\s*\{[^}]*min-width:\s*0", block), \
        f"{TABLET} 에서 .panel 이 0 까지 안 줄어든다"


def test_wide_screens_are_left_alone():
    """넓은 폭의 모양은 그대로여야 한다 — 좁은 화면 규칙이 밖으로 새면 안 된다.

    `.panel { min-width: 0 }` 을 전역에 걸었더니 딜 제안 관리의 세 칸이
    1440px 에서 493·314·345 → 372·372·409 로 바뀌었다. 그래서 좁은 폭
    안쪽에만 둔다.
    """
    css = _css()
    outside = css[:css.index(TABLET)]
    for selector, body in _rules(outside):
        if selector.strip() == ".panel":
            assert "min-width" not in body, \
                ".panel 의 min-width 는 좁은 폭 규칙 안에만 있어야 한다"


# ── 4. 떠 있는 것들은 화면 안에 ─────────────────────────────────────────────

def test_overlays_stay_inside_the_screen():
    """상세 패널·칸 편집창이 화면 밖으로 나가면 손댈 수가 없다."""
    phone = _block(_css(), PHONE)
    assert "width: 100vw" in phone, "폰에서 상세 패널이 화면을 다 쓰지 않는다"
    assert ".cell-pop" in phone, "폰에서 칸 편집창이 화면 안으로 안 들어온다"


def test_the_filter_dropdown_is_pulled_back_into_view():
    """필터 창은 누른 칸에 붙어 뜬다 — 표는 화면보다 넓어서 **오른쪽 칸일수록**
    창이 보이는 자리 밖으로 나갔다(390px 에서 오른쪽 절반이 잘렸다)."""
    js = FILTERS_JS.read_text(encoding="utf-8")
    assert "clampIntoView" in js, "필터 창을 화면 안으로 끌어당기는 처리가 없다"
    # 열 때마다 불려야 한다 — 만들어만 두고 안 부르면 그대로다
    assert re.search(r"appendChild\(panel\);\s*clampIntoView\(panel\)", js), \
        "필터 창을 띄운 뒤 clampIntoView 를 안 부른다"


# ── 5. 손가락으로 눌리는 크기 ───────────────────────────────────────────────

def test_controls_are_big_enough_for_a_finger():
    """마우스 화살표는 끝이 1px 이지만 손가락은 대략 9mm(≈44px)로 눌린다.

    로그인·비밀번호 변경의 단추와 입력칸이 22px, 대시보드 칩이 26px,
    `수정`·`삭제` 같은 글자 단추가 16px 이었다.
    """
    phone = _block(_css(), PHONE)
    sized = [selector for selector, body in _rules(phone)
             if re.search(r"min-height:\s*44px", body)]
    assert sized, f"{PHONE} 에 44px 규칙이 없다"
    covered = " ".join(sized)
    for control in (".primary-btn", ".secondary-btn", ".chip", ".menu-item",
                    ".sheet-tab", ".linkbtn", "select", "textarea"):
        assert control in covered, f"{control} 이 눌릴 크기가 아니다"
    # 입력칸도 — 단, 체크박스는 44px 로 키우면 네모가 우스꽝스럽게 커진다
    assert re.search(r"input:not\(\[type=checkbox\]\)", covered), \
        "입력칸이 눌릴 크기가 아니다"


def test_table_rows_keep_their_density():
    """표 안까지 44px 로 키우면 한 화면에 보이는 행이 반으로 준다.

    특히 머리글 칸의 필터 단추를 키우면 컬럼 이름이 두 줄을 넘겨 **머리글
    모양이 바뀐다** — 여러 번 고쳐 확정한 자리다.
    """
    phone = _block(_css(), PHONE)
    reset = [selector for selector, body in _rules(phone)
             if re.search(r"min-height:\s*0", body)]
    assert reset, "표 안에서 44px 을 되돌리는 규칙이 없다"
    covered = " ".join(reset)
    for cell in ("td button", "th button", "td input", "th input"):
        assert cell in covered, f"{cell} 이 표 밀도를 안 지킨다"
    assert ".filter-btn" not in " ".join(
        selector for selector, body in _rules(phone)
        if re.search(r"min-height:\s*44px", body)), \
        "머리글 필터 단추를 키우면 컬럼 이름 두 줄 규칙이 깨진다"


# ── 6. 확정된 머리글 모양은 못 건드린다 ─────────────────────────────────────

def test_the_desktop_header_shape_is_untouched():
    """머리글 정렬은 여러 번 고쳐 확정한 자리다.

    **가로는 왼쪽, 세로는 가운데**에 줄바꿈 허용 — `TIPS…` 처럼 긴 이름만 두
    줄이 되고 그 미만은 한 줄이다. 폰 작업이 이걸 건드리면 안 된다.

    한동안 가로도 가운데였는데, 칸이 스무 개 넘는 표에서 이름마다 시작 위치가
    달라 어느 머리글이 어느 칸인지 매번 다시 맞춰야 했다. 아래 칸의 글자가
    왼쪽에서 시작하니 머리글도 같은 자리에서 시작한다(숫자 칸만 오른쪽 —
    `.grid-table thead th.num`).
    """
    css = _css()
    rule = re.search(r"\.grid-table thead th\s*\{([^}]*)\}", css)
    assert rule, ".grid-table thead th 규칙이 없어졌다"
    body = rule.group(1)
    for prop, value in (("text-align", "left"),
                        ("vertical-align", "middle"),
                        ("white-space", "normal")):
        assert re.search(rf"{prop}:\s*{value}", body), \
            f"머리글의 {prop} 이 {value} 가 아니다"

    # 좁은 폭 규칙이 머리글 정렬을 덮어쓰지 않는지
    for header in (TABLET, PHONE):
        for selector, decl in _rules(_block(css, header)):
            if "thead th" not in selector:
                continue
            for prop in ("text-align", "vertical-align", "white-space"):
                assert prop not in decl, \
                    f"{header} 의 `{selector}` 가 머리글 {prop} 을 덮어쓴다"


# ── 7. 여러 칸으로 나뉜 줄은 좁은 폭에서 다시 짜야 한다 ─────────────────────
#
# 표가 아닌 것이 페이지를 민 세 번째 원인이다. 딜 진행 관리의 리마인드·미팅
# 후기 줄(`.due-list li`)은 **격자**인데(`날짜 84px | 이름 1fr | 무엇 200px |
# 단추 auto`), 폰 규칙에 적혀 있던 것은 `flex-wrap: wrap` 하나뿐이었다.
# **격자에는 `flex-wrap` 이 아무 일도 하지 않는다** — 접히는 줄로 알고 있었지만
# 네 칸이 그대로 서서 마지막 칸이 화면 밖으로 나갔다. 390px 에서 잰 값:
#
#     리마인드(#remind)      422px
#     미팅 후기(#meetings)   441px
#
# 눈에 안 띄던 까닭은 **아무 일도 안 하는 선언이 일하는 것처럼 보였기**
# 때문이다. 그래서 아래 둘을 못 박는다.
#
#   1. 격자에 `flex-wrap` 을 걸지 않는다 — 걸어 봐야 안 접힌다.
#   2. 칸이 셋 이상인 격자는 좁은 폭 규칙에서 **칸을 다시 정해야** 한다.
#
# 표와는 다른 처방이다. 넓은 표는 `.table-wrap` 안에서 **가로로 굴리고**(위 2절),
# 글자·단추가 든 줄은 **접는다**. 굴릴 것과 접을 것을 뒤바꾸면, 표는 짜부라져
# 못 읽고 단추 줄에는 쓸데없는 스크롤바가 생긴다.

# 좁은 폭 규칙이 사는 곳. 화면 종류가 아니라 **폭**으로 갈린다.
NARROW = ("@media (max-width: 1100px)", "@media (max-width: 1080px)",
          "@media (max-width: 900px)", "@media (max-width: 860px)",
          "@media (max-width: 720px)", "@media (max-width: 400px)")


def _pieces(selector: str):
    """`a, b c` → `['a', 'b c']`. 공백을 한 칸으로 맞춰 앞뒤를 견줄 수 있게."""
    return [re.sub(r"\s+", " ", one).strip() for one in selector.split(",") if one.strip()]


def _narrow_css(css: str) -> str:
    """좁은 폭 규칙을 전부 이어 붙인 것."""
    return "\n".join(_block(css, header) for header in NARROW if header in css)


def _outside_media(css: str) -> str:
    """`@media` 블록을 전부 걷어낸 나머지 — **넓은 폭에서의 본 모습**.

    맨 앞을 잘라 쓰면 안 된다. 규칙은 첫 `@media` 뒤에도 계속 나온다 —
    `.due-list li` 자체가 1100px 블록보다 **아래**에 적혀 있었다.
    """
    out, i = [], 0
    while True:
        j = css.find("@media", i)
        if j < 0:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:j])
        depth, k = 0, css.index("{", j)
        for k in range(k, len(css)):
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    break
        i = k + 1


def _grid_selectors(css: str) -> set:
    """`display: grid` 로 선언된 선택자들."""
    grids: set = set()
    for selector, body in _rules(_outside_media(css)):
        if re.search(r"display:\s*(inline-)?grid", body):
            grids |= set(_pieces(selector))
    return grids


def test_격자에는_줄바꿈을_걸지_않는다():
    """`flex-wrap` 은 flex 상자에만 듣는다 — 격자에 걸면 조용히 아무 일도 없다.

    이 한 줄 때문에 `.due-list li` 가 '폰에서 접힌다' 고 적힌 채로 안 접혔다.
    고쳐 놓고도 안 고쳐진 것이 가장 나쁘다 — 아무도 다시 안 본다.
    """
    css = _css()
    grids = _grid_selectors(css)
    assert grids, "격자 규칙을 하나도 못 찾았다 — 훑기가 고장 났다"
    bad = []
    for selector, body in _rules(_narrow_css(css)):
        if "flex-wrap" not in body:
            continue
        bad += [one for one in _pieces(selector) if one in grids]
    assert not bad, (
        "다음은 `display: grid` 인데 `flex-wrap` 이 걸려 있다 — 격자에는 듣지 "
        f"않아서 칸이 그대로 선다: {sorted(set(bad))}")


def _tracks(value: str) -> int:
    """`84px 1fr 200px auto` → 4. 괄호 안(`repeat(...)`)은 한 덩어리로 센다."""
    depth, count, seen = 0, 0, False
    for ch in value.strip():
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and ch.isspace():
            if seen:
                count += 1
                seen = False
        else:
            seen = True
    return count + (1 if seen else 0)


def _wide_grids(css: str):
    """칸이 셋 이상인 격자. `auto-fit`·`auto-fill` 은 스스로 접으므로 뺀다."""
    found = {}
    for selector, body in _rules(_outside_media(css)):
        m = re.search(r"grid-template-columns:\s*([^;]+)", body)
        if not m:
            continue
        value = m.group(1).strip()
        if "auto-fit" in value or "auto-fill" in value:
            continue
        if _tracks(value) < 3:
            continue
        for one in _pieces(selector):
            found[one] = value
    return found


def test_칸이_셋_이상인_줄은_좁은_폭에서_다시_짠다():
    """칸을 그대로 두면 `84 + 이름 + 200 + 단추` 가 390px 을 넘긴다.

    좁은 폭에서 칸을 다시 정하기만 하면 되고(한 줄로 세우든 폭을 줄이든),
    **아예 손대지 않은 것**만 잡는다 — `.bar-row` 처럼 좁혀서 들어가는 줄도
    있으므로 '무조건 한 칸' 을 강요하지 않는다.
    """
    css = _css()
    narrow = _narrow_css(css)
    touched = set()
    for selector, body in _rules(narrow):
        if "grid-template-columns" in body:
            touched |= set(_pieces(selector))
    missing = {one: value for one, value in _wide_grids(css).items() if one not in touched}
    assert not missing, (
        "다음 격자가 좁은 폭에서 그대로다 — 칸을 합친 폭이 화면을 넘겨 마지막 "
        f"칸이 밖으로 나간다: {missing}")


def test_리마인드_줄은_폰에서_한_줄로_선다():
    """`.due-list li` 는 딜 진행 관리·업무 화면이 함께 쓰는 줄이다.

    여기가 다시 여러 칸이 되면 세 화면이 한꺼번에 가로로 밀린다. 위 훑기는
    '손댔는가' 만 보므로, 실제로 밀렸던 이 자리는 **한 칸**임을 못 박는다.
    """
    for selector, body in _rules(_block(_css(), PHONE)):
        if ".due-list li" not in _pieces(selector):
            continue
        m = re.search(r"grid-template-columns:\s*([^;]+)", body)
        if not m:
            continue
        assert _tracks(m.group(1)) == 1, \
            f"폰에서 `.due-list li` 가 아직 여러 칸이다: {m.group(1).strip()}"
        assert "minmax(0" in m.group(1), (
            "`1fr` 은 속 내용의 최소폭 아래로 안 줄어든다 — `minmax(0, 1fr)` 이어야 "
            f"한다: {m.group(1).strip()}")
        return
    raise AssertionError(f"{PHONE} 에 `.due-list li` 의 칸 규칙이 없다")


def test_훑기가_진짜로_잡는지(monkeypatch):
    """안 잡히는 검사는 없는 것과 같다 — 고쳐 놓기 전 모습을 그대로 넣어 본다."""
    broken = """
      .due-list li { display: grid; grid-template-columns: 84px 1fr 200px auto; }
      @media (max-width: 1100px) { .x { color: red; } }
      @media (max-width: 720px) { .due-list li { flex-wrap: wrap; } }
    """
    monkeypatch.setattr(sys.modules[__name__], "_css", lambda: broken)
    assert _grid_selectors(broken) == {".due-list li"}
    assert list(_wide_grids(broken)) == [".due-list li"]        # 좁은 폭에서 안 짜였다
    with pytest.raises(AssertionError):
        test_격자에는_줄바꿈을_걸지_않는다()
    with pytest.raises(AssertionError):
        test_칸이_셋_이상인_줄은_좁은_폭에서_다시_짠다()
    with pytest.raises(AssertionError):
        test_리마인드_줄은_폰에서_한_줄로_선다()
