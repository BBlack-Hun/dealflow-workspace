"""표 칸에 display 를 덮어쓰지 않는지 — 행이 통째로 어긋나는 부류.

같은 원인으로 **세 번** 깨졌다.

    <td class="clamp2">   display:-webkit-box  → 소개 문구 칸
    <td class="row-acts"> display:flex         → IR 요청 표의 버튼 칸

`<td>` 의 display 를 table-cell 이 아닌 값으로 바꾸면 그 칸이 테이블 레이아웃에서
빠진다. 화면에서는 행이 어긋나거나 칸 하나가 밖으로 튀어나온 것처럼 보인다.
눈으로만 잡던 것이라 자동으로 훑는다.
"""
from __future__ import annotations

import pathlib
import re
import unicodedata

CSS = pathlib.Path("app/static/css/app.css")
TEMPLATES = pathlib.Path("app/templates")

# 칸을 테이블에서 빼내는 값들
BREAKING = ("flex", "grid", "block", "inline-block", "inline-flex", "-webkit-box")


def _classes_that_change_display() -> dict:
    """`.foo { display: flex }` 처럼 **그 클래스 자체**의 display 를 바꾸는 규칙.

    `.foo span { display: flex }` 는 안쪽 요소를 바꾸는 것이라 해당 없다.
    """
    css = CSS.read_text(encoding="utf-8")
    out = {}
    for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        body = block.group(2)
        found = re.findall(r"display\s*:\s*([a-z-]+)", body)
        breaking = [v for v in found if v in BREAKING]
        if not breaking:
            continue
        # 같은 블록에서 table-cell 로 되돌려 놨으면 통과
        if "table-cell" in found:
            continue
        for selector in block.group(1).split(","):
            selector = selector.strip()
            # 마지막 조각이 클래스여야 그 클래스가 붙은 요소가 대상이다
            last = selector.split()[-1] if selector.split() else ""
            m = re.fullmatch(r"\.([a-zA-Z0-9_-]+)", last)
            if m:
                out[m.group(1)] = breaking[-1]
    return out


def _classes_fixed_for_cells() -> set:
    """`td.foo { display: table-cell }` 처럼 칸에서는 되돌려 둔 클래스."""
    css = CSS.read_text(encoding="utf-8")
    safe = set()
    for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if "table-cell" not in block.group(2):
            continue
        for selector in block.group(1).split(","):
            for m in re.finditer(r"\bt[dh]\.([a-zA-Z0-9_-]+)", selector):
                safe.add(m.group(1))
    return safe


def test_no_template_puts_those_classes_on_a_table_cell():
    risky = _classes_that_change_display()
    for name in _classes_fixed_for_cells():
        risky.pop(name, None)
    offenders = []
    for template in sorted(TEMPLATES.glob("*.html")):
        text = template.read_text(encoding="utf-8")
        for m in re.finditer(r'<t[dh]\b[^>]*class="([^"]*)"', text):
            for name in m.group(1).split():
                if name in risky:
                    offenders.append(f"{template.name}: <td class=\"{name}\"> "
                                     f"→ display:{risky[name]}")
    assert not offenders, (
        "표 칸의 display 를 바꾸면 그 칸이 테이블 레이아웃에서 빠져 행이 어긋난다.\n"
        "안쪽 div/span 으로 옮기거나 td 용 규칙을 따로 두세요:\n  "
        + "\n  ".join(sorted(set(offenders))))


def test_every_table_row_has_as_many_cells_as_headers():
    """머리와 셀 개수가 어긋나면 그 뒤 칸이 전부 한 칸씩 밀린다."""
    import itertools

    from fastapi.testclient import TestClient  # noqa: F401  (설치 확인용)

    # 템플릿 단계에서 셀 수를 세면 {% if %} 때문에 정확하지 않다.
    # 여기서는 **머리 개수가 서로 다른 thead 가 한 표에 섞여 있지 않은지**만 본다.
    for template in sorted(TEMPLATES.glob("*.html")):
        text = template.read_text(encoding="utf-8")
        for thead in re.findall(r"<thead>.*?</thead>", text, re.S):
            rows = re.findall(r"<tr>.*?</tr>", thead, re.S)
            counts = {len(re.findall(r"<th[ >]", r)) for r in rows}
            assert len(counts) <= 1, f"{template.name}: thead 안 행마다 머리 수가 다르다"
    assert list(itertools.islice(iter([]), 0)) == []

# --- 표 정렬 ----------------------------------------------------------------
#
# 숫자 칸은 오른쪽으로 민다 — 자릿수가 다른 값이 왼쪽에 붙어 있으면 6 과 117 이
# 같은 자리에서 시작해 크기를 눈으로 비교할 수 없다.
#
# 오래 어긋나 있던 두 가지를 여기서 막는다:
#   1) `td.num` 규칙이 **아예 없어서** 클래스만 달고 효과가 없던 것
#   2) 칸은 오른쪽인데 머리글만 왼쪽이라 어느 머리글이 어느 칸인지 눈이
#      매번 다시 맞춰야 했던 것

def _tables(html: str):
    """(머리글 속성들, 첫 줄 칸 속성들) — 개수가 같은 표만."""
    for m in re.finditer(r"<thead>(.*?)</thead>(.*?)</tbody>", html, re.S):
        ths = re.findall(r"<th\b([^>]*)>", m.group(1))
        tr = re.search(r"<tr[^>]*>(.*?)</tr>", m.group(2), re.S)
        if not tr:
            continue
        tds = re.findall(r"<td\b([^>]*)>", tr.group(1))
        if len(ths) == len(tds):
            yield ths, tds


def test_numeric_cells_are_actually_right_aligned():
    """클래스만 달고 규칙이 없으면 왼쪽에 붙은 채로 남는다."""
    css = CSS.read_text(encoding="utf-8")
    rule = re.search(r"[^}]*\btd\.num\b[^{]*\{([^}]*)\}", css)
    assert rule, "td.num 규칙이 없습니다 — class=\"num\" 이 아무 일도 하지 않습니다"
    assert "text-align: right" in rule.group(1)
    assert "tabular-nums" in rule.group(1)


def _right(attrs: str) -> bool:
    """오른쪽으로 미는 칸인가."""
    return "num" in attrs or "rowno" in attrs


def test_a_numeric_column_header_matches_its_cells():
    """칸은 오른쪽인데 머리글만 왼쪽이면 어느 머리글이 어느 칸인지 헷갈린다."""
    problems = []
    for path in sorted(TEMPLATES.glob("*.html")):
        for ths, tds in _tables(path.read_text(encoding="utf-8")):
            for i, (th, td) in enumerate(zip(ths, tds)):
                # `.rowno`(줄 번호) 도 오른쪽으로 민다 — 이름만 다를 뿐 같은 규칙이다.
                if _right(th) != _right(td):
                    problems.append(f"{path.name} 열{i}")
    assert not problems, "머리글과 칸의 정렬이 다릅니다: " + ", ".join(problems)

# --- 머리글 줄바꿈 ----------------------------------------------------------
#
# 컬럼 이름이 원본 시트를 그대로 따르다 보니 길이가 제각각이다(`NO` 한 글자,
# `TIPS 운영사 투자금 1-10억 …` 마흔 글자). 좁은 칸에 긴 이름을 넣으면 네 줄로
# 늘어나고, 그 옆 한 줄짜리 이름이 위에 떠 있어 머리글 줄이 들쭉날쭉해진다.

def _display_width(text: str) -> int:
    """한글은 두 칸, 영문은 한 칸으로 센 표시 폭."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def test_no_header_wraps_past_two_lines():
    """두 줄까지가 한계다. 세 줄부터는 머리글이 표를 밀어낸다."""
    problems = []
    for path in sorted(TEMPLATES.glob("*.html")):
        for head in re.findall(r"<thead>(.*?)</thead>", path.read_text(encoding="utf-8"), re.S):
            for attrs, label in re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S):
                text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", label)).strip()
                # 반복문으로 만드는 머리글은 값이 실행 때 정해진다 — 셀 수 없다
                if not text or "{{" in text or "{%" in text:
                    continue
                px = re.search(r"width:\s*(\d+)px", attrs)
                if not px:
                    continue
                need = _display_width(text) * 6 + 18      # 12px 글자 기준
                lines = max(1, -(-need // int(px.group(1))))
                if lines >= 3:
                    problems.append(f"{path.name}: {text[:30]} ({lines}줄)")
    assert not problems, "머리글이 세 줄 넘게 접힙니다: " + ", ".join(problems)


def _rule(css: str, selector: str) -> str:
    """`selector { … }` 의 속성 부분. 없으면 빈 문자열."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def _must_not_pin_or_clip(body: str, where: str) -> None:
    """머리글 칸을 높이로 묶거나 잘라내지 않는지."""
    assert not re.search(r"height:\s*\d+px", body), (
        f"{where}: 머리글 높이를 고정하면 짧은 머리글 칸이 비고 긴 이름은 잘린다")
    assert "overflow: hidden" not in body, f"{where}: 잘린 이름은 사람이 알 수가 없다"
    assert "text-overflow: ellipsis" not in body, (
        f"{where}: `…` 로 자르면 이름이 서로 구별되지 않는다"
        "(`근무처 전…` 이 전화인지 팩스인지)")
    assert "white-space: nowrap" not in body, (
        f"{where}: 한 줄로 묶으면 긴 이름이 칸 밖으로 나가거나 잘린다 — "
        "접히게 두고 폭으로 두 줄 안에 넣는다(위 검사)")


def test_header_names_sit_in_the_middle_of_the_cell():
    """컬럼 이름은 **가로·세로 모두 가운데**다.

    이름이 두 줄 안에 들어가게 폭을 잡아 두었으므로(위 검사) 줄 수 차이가
    한 줄뿐이고, 가운데로 모으면 이름이 칸 한복판에 서서 축이 맞는다.

    높이로 묶거나 잘라내는 것은 여전히 안 된다 — 높이를 고정하면 짧은 머리글
    칸이 비고, `…` 로 자르면 `근무처 전…` 이 전화인지 팩스인지 알 수 없다.

    `.grid-table th` 만 보던 검사였다. 뒤따르는 `.grid-table thead th` 가
    nowrap·ellipsis 로 **덮어쓰고 있었는데도** 통과했다 — 그래서 덮어쓰는
    쪽도 같이 본다.
    """
    css = CSS.read_text(encoding="utf-8")

    base = _rule(css, ".grid-table th")
    assert base, ".grid-table th 규칙이 없습니다"
    _must_not_pin_or_clip(base, ".grid-table th")

    head = _rule(css, ".grid-table thead th")
    assert head, ".grid-table thead th 규칙이 없습니다"
    _must_not_pin_or_clip(head, ".grid-table thead th")
    # 숫자 칸만 예외 — 자릿수를 세로로 맞춰 보느라 오른쪽이다.
    assert "text-align: center" in head, "머리글은 가로로 가운데"
    assert "vertical-align: middle" in head, "머리글은 세로로도 가운데"

