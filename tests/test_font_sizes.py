"""글자 크기가 다시 갈라지지 않게 못 박는다.

한 화면 안에서 같은 종류의 글자가 서로 다른 크기로 서 있었다. 원인은 모양새가
아니라 **규칙을 안 쓴 자리**였다:

    단추 · 고르개 55곳    13.3333px   ← `<button>` 은 크기를 물려받지 않는다
    표 칸                12px / 14px  ← `.grid-table td` 에 크기가 없어서
    화면 제목 세 곳         28px        ← `.page-title` 규칙이 아예 없었다
    컨설턴트 머리글          11.5px      ← 다른 표 머리글만 12px

`13.3333px` 은 고른 값이 아니다. `<button>`·`<select>` 는 글꼴도 크기도 물려받지
않아서, 크기를 안 적으면 브라우저가 제 기본값으로 그린다. 헤드리스 크롬으로 재
보면 화면마다 그 값이 섞여 있었다 — 1440px 에서 **보이는 것만 93곳**이었다.

여기 있는 검사는 전부 **CSS 글자를 읽어서** 판단한다. 브라우저가 없어도 돌고,
되돌아가면 그 자리에서 깨진다.
"""
from __future__ import annotations

import pathlib
import re

CSS = pathlib.Path("app/static/css/app.css")

# 표 글자 한 값. 사용자가 정한 값이다("13으로 통일해줘").
TABLE_TEXT = "13px"


def _css() -> str:
    """주석을 지운 CSS. 안 지우면 규칙 위의 설명이 선택자에 딸려 온다."""
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _rules(css: str):
    """(선택자 한 개, 속성들) 쌍. `@media` 안쪽까지 평평하게 훑는다.

    `a, b { … }` 는 두 쌍으로 풀어서 낸다 — 검사는 선택자 **하나**를 찾는다.
    """
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        group = m.group(1).strip()
        if group.startswith("@"):
            continue
        for selector in group.split(","):
            selector = " ".join(selector.split())
            if selector:
                yield selector, m.group(2)


def _top_level(css: str) -> str:
    """`@media`·`@print` 덩어리를 통째로 뺀 바깥 규칙만.

    미디어 규칙 안에서는 같은 선택자를 다시 적는 것이 정상이라(폰에서 값을
    바꾸는 자리), 중복을 셀 때 섞으면 안 된다.
    """
    out, i = [], 0
    while i < len(css):
        m = re.compile(r"@[a-z-]+[^{]*\{").search(css, i)
        if not m:
            out.append(css[i:])
            break
        out.append(css[i:m.start()])
        depth, j = 1, m.end()
        while j < len(css) and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def _size_of(selector: str, css: str | None = None) -> str | None:
    """그 선택자가 **마지막으로** 정한 font-size. 없으면 None."""
    css = _css() if css is None else css
    found = None
    for sel, body in _rules(css):
        if sel != selector:
            continue
        m = re.findall(r"font-size:\s*([^;}]+)", body)
        if m:
            found = m[-1].strip()
    return found


# ── 1. 규칙 없이 브라우저 기본값으로 서는 자리가 없다 ────────────────────────

def test_form_controls_inherit_a_size():
    """`<button>`·`<select>`·`<input>` 은 크기를 **안 물려받는다.**

    글꼴만 물려주고 크기를 빼 두었더니, 크기를 안 적은 자리가 전부 브라우저
    기본값(13.3333px)으로 섰다. 뿌리에서 한 번에 막는다.
    """
    css = _css()
    root = [body for sel, body in _rules(css)
            if sel in ("button", "input", "select", "textarea")
            and "font-family" in body]
    assert root, "글꼴을 물려주는 뿌리 규칙이 없어졌다"
    assert any(re.search(r"font-size:\s*inherit", body) for body in root), (
        "`body, button, input, select, textarea, table` 에 `font-size: inherit` 이 없다 — "
        "크기를 안 적은 단추·고르개가 다시 브라우저 기본값(13.3333px)으로 선다"
    )


def test_every_button_says_its_size():
    """단추는 **제 크기를 적어 둔다.**

    `inherit` 만으로는 부모를 따라가 자리마다 갈린다 — 같은 `.secondary-btn` 이
    툴바 안에서는 13px, 밖에서는 다른 값이 되던 자리다.
    """
    css = _css()
    for selector in (".btn", ".secondary-btn", ".danger-btn", ".primary-btn"):
        assert _size_of(selector, css), f"{selector} 에 글자 크기가 없다"
    for selector in (".btn", ".secondary-btn", ".danger-btn"):
        assert _size_of(selector, css) == "13px", \
            f"{selector} 이 단추 한 값(13px)에서 벗어났다"


# ── 2. 표 내용은 한 값이다 ───────────────────────────────────────────────────

def test_table_text_is_one_size():
    """`.grid-table td` 와 `td.cell` 이 **같은 값**이다.

    한쪽에만 크기가 있어서 한 줄 안에 12px 과 14px 이 섞여 있었다.
    """
    css = _css()
    for selector in (".grid-table td", "td.cell", ".sheet-table td"):
        assert _size_of(selector, css) == TABLE_TEXT, \
            f"{selector} 이 표 글자 한 값({TABLE_TEXT})이 아니다"


def test_nothing_quietly_overrides_the_table_size():
    """밀도만 바꾸는 규칙이 **크기까지** 쥐고 있으면 안 된다.

    `.grid-table.compact` 가 12px 을 들고 있던 동안, 같은 `<td class=cell>` 이
    표에 따라 12px 과 13px 로 갈렸다 — 그 표가 앱 표의 절반 이상이다.
    """
    css = _css()
    for selector in (".grid-table.compact td", ".grid-table.compact th",
                     ".grid-table.dense td", ".todo-page .grid-table td",
                     ".ref-cell"):
        size = _size_of(selector, css)
        assert size is None or size == TABLE_TEXT, (
            f"{selector} 이 표 글자를 {size} 로 덮어쓴다 — "
            f"크기를 정하는 자리는 `.grid-table td` 한 곳이다"
        )


def test_the_cell_editor_matches_the_cell():
    """칸을 눌러 여는 편집칸이 칸보다 작으면, 누르는 순간 글자가 줄어든다."""
    assert _size_of(".cell-input") == TABLE_TEXT, \
        "칸 편집창이 칸(13px)과 다른 크기다"


# ── 3. 머리글·제목 ──────────────────────────────────────────────────────────

def test_the_sheet_header_matches_the_grid_header():
    """컨설턴트 표 머리글만 11.5px 이라 반 픽셀 작았다."""
    css = _css()
    assert _size_of(".sheet-table th", css) == _size_of(".grid-table th", css), \
        "시트형 표 머리글이 다른 표 머리글과 다른 크기다"


def test_the_page_title_has_a_rule():
    """`.page-title` 은 규칙이 **아예 없어서** h1 기본값(2em = 28px)으로 섰다.

    문구 관리·설치 안내·비밀번호 변경 세 화면만 제목이 6px 컸다.
    """
    css = _css()
    assert _size_of(".page-title", css), ".page-title 에 글자 크기가 없다"
    assert _size_of(".page-title", css) == _size_of(".page-head h1", css), \
        "`.page-title` 과 `.page-head h1` 이 다른 크기다 — 둘 다 화면 제목이다"


# ── 4. 일부러 작게 한 자리는 그대로다 ───────────────────────────────────────

# 값 하나하나가 이유를 갖고 정해진 자리다. 표 글자를 올릴 때 **딸려 올라가면**
# 안 된다 — 머리글 필터 단추는 키우면 컬럼 이름이 두 줄로 접힌다
# (tests/test_mobile_layout.py 가 같은 자리를 다른 쪽에서 지킨다).
ON_PURPOSE_SMALL = {
    ".filter-btn": "11px",          # 머리글 필터 단추 — 키우면 컬럼 이름이 접힌다
    ".th-note": "10.5px",           # 머리글 부연
    ".th-unit": "10.5px",           # 금액 칸의 단위
    ".rowno": "11px",               # 줄번호
    ".cell-sub": "11.5px",          # 칸 아래 보조줄
    ".sheet-table td.owner-cell": "11.5px",   # 담당 칸
    ".tod-pick": "10.5px",          # 오전/오후 고르개
    ".chip-note": "10.5px",         # 이름 옆 역할
    ".grid-table th": "12px",       # 표 머리글
}


def test_the_small_ones_stay_small():
    css = _css()
    for selector, size in ON_PURPOSE_SMALL.items():
        assert _size_of(selector, css) == size, \
            f"{selector} 은 일부러 {size} 로 둔 자리다"


def test_the_row_number_outweighs_the_table_rule():
    """줄번호는 `.grid-table td`(클래스 1 + 태그 1)와 **같은 무게**여야 한다.

    `.rowno` 로만 적어 두면 표 규칙에 져서 11px 이 조용히 13px 이 된다 —
    화면에서는 번호 칸만 커지는데, CSS 를 읽으면 11px 이라 적혀 있다.
    """
    css = _css()
    owners = [sel for sel, body in _rules(css)
              if "font-size: 11px" in body.replace("  ", " ")
              and sel.endswith("rowno")]
    assert "td.rowno" in owners, \
        "`td.rowno` 가 없다 — `.rowno` 만으로는 `.grid-table td` 에 진다"


# ── 5. 같은 선택자를 두 번 적지 않는다 ──────────────────────────────────────

# 두 벌로 적혀 있으면 다음 사람이 한쪽만 고치고, 화면이 안 바뀌는 이유를 못 찾는다.
# 실제로 `.kv th`·`.kv td` 가 두 곳에 있었고 뒤쪽이 앞쪽을 통째로 덮고 있었다.
WRITE_ONCE = (".kv", ".kv th", ".kv td",
              ".grid-table td", "td.cell", ".sheet-table td", ".sheet-table th",
              ".btn", ".page-title")


def test_each_rule_is_written_once():
    outer = _top_level(_css())
    seen = {}
    for selector, _body in _rules(outer):
        seen[selector] = seen.get(selector, 0) + 1
    for selector in WRITE_ONCE:
        assert seen.get(selector, 0) <= 1, (
            f"`{selector}` 이 {seen[selector]} 번 적혀 있다 — "
            f"한 곳에서만 정한다(두 벌이면 한쪽만 고치게 된다)"
        )


def test_the_kv_table_says_its_size():
    """`.kv` 는 크기를 안 적어 두어 본문(14px)을 물려받았다."""
    assert _size_of(".kv") == TABLE_TEXT, ".kv 표가 표 글자 한 값이 아니다"
