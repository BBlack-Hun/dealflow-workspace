"""고르는 카드의 체크박스가 **이름 첫 줄에 서는가.**

「딜 제안 관리」의 카드(`.pick-card`)는 `<label>` 하나에 [고른 차례 번호]
[체크박스][이름·꼬리표·방 이름] 을 flex 로 늘어놓는다. 카드 키는 카드마다
다르다 — 꼬리표(★ · 시리즈 · `내용 부족` · `3일 전 소개` · `3회`)가 늘면 이름이
두 줄로 접히고, 담당자 카드에는 방 이름 줄까지 붙는다.

체크박스에 키를 안 주면 `align-items` 기본값(stretch)이 그것을 **카드 키만큼**
늘리고, 브라우저는 그 한가운데에 네모를 그린다. 그래서 카드가 클수록 체크박스가
아래로 내려갔다. 헤드리스 크롬으로 재 본 값이다(고치기 전, 1440px):

    카드                  카드 키   체크박스 상자   이름 첫 줄에서
    한 줄                  61.0     13 × 33.0        +9.5px
    두 줄(꼬리표 넷)        82.0     13 × 54.0       +20.0px
    thin(내용 부족)         79.5     13 × 51.5       +18.7px
    담당자                 106.8     13 × 78.8       +32.4px
    담당자 두 줄           148.8     13 × 120.8      +53.3px

여기 있던 `margin-top: 3px` 은 그때의 브라우저 기본 체크박스(13px)에 눈으로
맞춘 값이라, 폰에서 체크박스를 20px 로 키운 뒤(#195)에는 이미 틀린 값이었다.
그래서 자리를 **계산해서** 정한다: `(줄 키 − 상자) ÷ 2`.

어긋남을 px 으로 못 박는 것은 `tests/js/pick_card_align_test.js` 다(값을 CSS
원본에서 뽑아 자리를 세워 본다). 여기서는 그 검사를 돌리고, 그 계산이 딛고 선
전제 — 줄 키가 본문 줄 높이와 같은가, 누를 자리는 라벨 통째인가 — 를 본다.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

CSS = pathlib.Path("app/static/css/app.css")
DEALS = pathlib.Path("app/templates/deals.html")
JS_TEST = pathlib.Path(__file__).resolve().parent / "js" / "pick_card_align_test.js"


def _css() -> str:
    """주석을 지운 CSS. 안 지우면 규칙 바로 위의 설명이 선택자에 딸려 온다."""
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _rule(css: str, selector: str) -> str:
    """선택자 하나의 선언 덩어리(마지막 것)."""
    # 선택자 앞을 막는다 — 안 막으면 `.pick-body {` 안의 `body {` 가 걸린다.
    found = re.findall(r"(?:^|[};])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}",
                       css, flags=re.M)
    assert found, f"CSS 에 `{selector}` 규칙이 없다"
    return found[-1]


def _prop(decls: str, name: str) -> str | None:
    m = re.search(r"(?:^|;)\s*" + re.escape(name) + r"\s*:\s*([^;]+)", decls)
    return m.group(1).strip() if m else None


def _base_css() -> str:
    """`@media` 를 걷어낸 본문 — 폰 규칙의 같은 선택자가 섞이지 않게."""
    css, out, depth, skipping = _css(), [], 0, False
    i = 0
    while i < len(css):
        if not skipping and css.startswith("@media", i):
            skipping, depth = True, 0
        if not skipping:
            out.append(css[i])
        elif css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                skipping = False
        i += 1
    return "".join(out)


# ── 1. 어긋남을 px 으로 재는 검사 ───────────────────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 자산 검사 생략")
def test_the_checkbox_sits_on_the_first_line_of_the_name():
    """체크박스·번호가 이름 첫 줄 한가운데에서 0.5px 안에 서는가.

    PC(16px)와 폰(20px) 두 크기 모두에서 본다 — 크기만 키우고 맞춤이 읽는 값을
    안 올리면 폰에서만 2px 어긋난다.
    """
    node = shutil.which("node")
    result = subprocess.run([node, str(JS_TEST)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


# ── 2. 그 계산이 딛고 선 전제 ───────────────────────────────────────────────

def test_the_line_height_it_aligns_to_is_the_real_one():
    """`--pick-line` 은 본문 줄 높이 그 값이어야 한다.

    체크박스는 이 값의 한가운데에 선다. 본문 글자 크기나 줄 높이만 바뀌고 이
    값이 그대로 남으면, 맞춘 자리가 조용히 어긋난다 — 이 검사가 그때 빨개진다.
    """
    body = _rule(_base_css(), "body")
    size = float(re.sub("px", "", _prop(body, "font-size")))
    height = float(_prop(body, "line-height"))
    card = _rule(_base_css(), ".pick-card")
    line = float(re.sub("px", "", _prop(card, "--pick-line")))
    assert line == pytest.approx(size * height), (
        f"맞추는 줄 키가 {line}px 인데 본문 줄은 {size} × {height} = "
        f"{size * height}px 이다")


def test_no_hand_nudged_offset_comes_back():
    """`margin-top: 3px` 같은 값이 다시 생기지 않았는가.

    손으로 민 값은 그때 쓰던 체크박스 크기에만 맞는다. 폰에서 체크박스가
    커지거나(#195) 글자가 커지면 그 값만 제자리에 남아 어긋난다.

    **자리는 `align-items: center` 가 정한다** — 사용자가 카드 세로 한가운데로
    정했다(한 번 이름 첫 줄에 맞췄다가 되돌렸다). 그러니 체크박스에는 미는 값이
    아예 없어야 한다.
    """
    css = _base_css()
    card = _rule(css, ".pick-card")
    assert _prop(card, "align-items") == "center", (
        "카드 세로 한가운데 정렬이 아니다 — 사용자가 정한 자리다")
    box = _rule(css, ".pick-card > input[type=checkbox]")
    margin = (_prop(box, "margin") or _prop(box, "margin-top") or "0").strip()
    assert not re.search(r"[1-9]", margin), (
        f"체크박스를 손으로 밀고 있다: {margin} — 자리는 정렬이 정한다")
    assert not re.search(r"\.pick-card\s+input\s*\{[^}]*margin-top:\s*\d", css), \
        "`.pick-card input { margin-top: …px }` 이 되살아났다"


# ── 3. 누를 자리 ────────────────────────────────────────────────────────────

def test_the_whole_card_stays_the_tap_target():
    """카드는 `<label>` 통째로 누르는 자리다 — 체크박스를 세우느라 줄이지 않는다.

    셋 다 본다(기업 · 담당자 · 소싱). 체크박스가 라벨 **바로 밑**에 있어야
    위 CSS 선택자(`.pick-card > input`)가 닿고, 라벨 밖으로 나가면 네모만
    누르는 자리가 된다.
    """
    html = DEALS.read_text(encoding="utf-8")
    cards = re.findall(r'<label class="pick-card[^>]*>(.*?)</label>', html, flags=re.S)
    assert len(cards) == 3, f"고르는 카드가 3 벌이 아니다({len(cards)} 벌) — 새 목록도 함께 봐야 한다"
    for body in cards:
        # 라벨 → (주석) → 체크박스 → `.pick-body`. 사이에 다른 상자가 끼면
        # `.pick-card > input` 이 닿지 않는다.
        stripped = re.sub(r"\{#.*?#\}", "", body, flags=re.S).strip()
        assert stripped.startswith("<input type=\"checkbox\""), \
            "체크박스가 라벨 바로 밑에 있지 않다"

    card = _rule(_base_css(), ".pick-card")
    assert _prop(card, "cursor") == "pointer", "카드가 누를 자리가 아니게 됐다"
    assert _prop(card, "padding") == "10px", "카드 안쪽 여백이 줄었다 — 누를 자리가 좁아진다"
