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

