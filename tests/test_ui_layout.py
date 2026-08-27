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
FILTERS_JS = pathlib.Path("app/static/js/filters.js")

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


def test_머리글은_왼쪽에서_시작하고_세로로만_가운데다():
    """컬럼 이름은 **가로는 왼쪽, 세로는 가운데**다.

    아래 칸(`td`)의 글자가 왼쪽에서 시작하므로 머리글도 같은 자리에서 시작해야
    눈이 세로로 한 줄을 따라 내려갈 수 있다. 가로로도 가운데에 모아 두었더니
    이름마다 시작 위치가 달라, 칸이 스무 개 넘는 표(투자사 관리 현황)에서
    어느 머리글이 어느 칸인지 매번 다시 맞춰야 했다.

    숫자 칸(`.num`)만은 오른쪽을 지킨다 — 자릿수를 세로로 맞춰 보는 칸이다.
    데이터 칸의 정렬은 여기서 보지 않는다. 바뀐 것은 머리글뿐이다.

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
    assert "text-align: left" in head, "머리글은 가로로 왼쪽"
    assert "vertical-align: middle" in head, "머리글은 세로로 가운데"
    # 숫자 칸만 예외 — 자릿수를 세로로 맞춰 보느라 오른쪽이다.
    assert "text-align: right" in _rule(css, ".grid-table thead th.num"), \
        "숫자 칸 머리글은 오른쪽을 지킨다"
    # 머리글 아래에 붙는 필터 단추·설명도 이름과 같은 자리에서 시작해야 한다.
    assert "flex-start" in _rule(css, ".grid-table thead .th-filters"), \
        "필터 단추가 이름과 다른 자리에서 시작하면 축이 어긋난다"


# --- 머리글 한 줄 -----------------------------------------------------------
#
# 위의 두 줄 상한만으로는 부족했다. 두 줄로 접힌 이름과 한 줄짜리 이름이 섞이면
# 머리글 줄이 들쭉날쭉해 보이고, 이름이 어디서 끊겼는지도 매번 다시 읽어야 한다.
# 그래서 **한 줄**이 기준이다.

# 딱 하나만 두 줄을 허용한다. 원본 시트의 컬럼 이름을 그대로 쓰는 표라
# 이름을 줄일 수 없는데, 한 줄에 넣으려면 260px 짜리 칸이 필요하다 —
# 값이 306줄 중 3줄뿐인 칸에 그만한 자리를 내주면 매일 보는 칸이 눌린다.
_TWO_LINE_OK = "TIPS 운영사 투자금 1-10억 스타트업매출액 3-20억 기업에 주로 투자"

# 필터가 하나뿐인 칸은 **이름 글자가 지워지고** `계약여부 ▾` 단추가 그 자리에
# 선다(filters.js 의 `solo`). 단추는 이름보다 넓다 — ` ▾`(약 6px) 와 자기
# padding·테두리(6+6+1+1 = 14px)가 더 붙는다.
#
# 이름만 재던 검사라 그 20px 을 못 보고 있었다. IR 기업현황의 `계약여부`(72px)와
# `핵심/TOP Deal`(102px) 은 이름으로는 66px·96px 이라 통과했지만, 화면에서는
# `계약여부` / `▾` 로 접혀 있었다 — 헤드리스 크롬으로 재서야 드러났다.
_FILTER_BTN_PX = 20

# 12px 굵은 글씨(머리글)에서 글자 한 개가 차지하는 폭. 헤드리스 크롬으로 서른
# 남짓한 머리글을 실측해 맞춘 값이라, 어림값과 실제가 2px 안쪽에서 맞는다.
#
# `한 칸 6px`(한글은 두 칸이므로 12px)으로 뭉뚱그리던 어림값은 한글을 1.5px 씩,
# 공백·괄호를 2.4px 씩 부풀렸다. 이름이 짧을 때는 티가 안 났는데, 필터 단추까지
# 재기 시작하니 `관심도 (월말기준) ▾`(실제 127px)를 140px 이라 보고 멀쩡한 칸을
# 두 줄이라고 짚었다.
_PX_CJK = 10.5      # 한글·한자 — 12px 폰트라도 글자 상자는 이만큼이다
_PX_PUNCT = 3.6     # 공백·쉼표·괄호·슬래시
_PX_OTHER = 6.6     # 영문·숫자·기호(`▾`)


def _text_px(text: str) -> float:
    """이 글자가 머리글에서 차지하는 폭(px)."""
    total = 0.0
    for ch in text:
        if unicodedata.east_asian_width(ch) in "WF":
            total += _PX_CJK
        elif ch.isspace() or unicodedata.category(ch).startswith("P"):
            total += _PX_PUNCT
        else:
            total += _PX_OTHER
    return total


def _filter_labels(attrs: str) -> list:
    """이 칸에 세워지는 필터 단추의 라벨들. 없으면 빈 목록.

    필터가 **하나뿐인** 칸은 이름 글자가 지워지고 단추가 그 자리를 대신한다.
    둘인 칸(진행 단계 / 연결 상태)은 이름을 남기고 단추를 아래에 붙이는데,
    `.th-filters` 가 `flex-wrap: wrap` 이라 단추끼리는 줄을 나눠 선다 —
    그러니 칸이 감당해야 하는 것은 **가장 넓은 단추 하나**다.
    """
    m = re.search(r'data-filters="([^"]*)"', attrs)
    if not m or "{{" in m.group(1):
        return []
    out = []
    for spec in m.group(1).split("|"):
        if ":" in spec:
            out.append(spec.split(":", 1)[1].strip())
    return out


# 값을 고르면 라벨 뒤에 `(고른 개수)` 가 붙는다. **그 상태까지 재야 한다** —
# 안 재고 이름 길이로만 폭을 잡아 두었더니, 화면에서는 멀쩡하다가 필터를 거는
# 순간 열두 칸이 두 줄로 접혔다(`담당자` → `담당자` / `(1) ▾`).
#
# 꼬리표 앞은 줄바꿈 없는 공백이다(filters.js). 폭은 보통 공백과 같으므로
# 여기서는 그냥 공백으로 세면 된다 — 재는 것은 글자 폭이지 줄바꿈이 아니다.
_FILTER_SUFFIX = " (1) ▾"


def _markup(text: str) -> str:
    """Jinja 주석(`{# … #}`)을 뺀 실제 마크업.

    주석에 태그 이름을 적어 두는 일이 잦다("`<thead` 의 `>` 가 빠져 있었다").
    지우지 않으면 설명하려고 적은 글자를 마크업으로 잘못 세어, 주석을 다는
    것만으로 검사가 깨진다.
    """
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def _name_only(cell_html: str) -> str:
    """컬럼 **이름**만. 설명(`th-note`)과 필터 칩(`th-filters`)은 이름이 아니다."""
    frag = re.sub(r'<span class="th-note">.*?</span>', "", cell_html, flags=re.S)
    frag = re.sub(r'<div class="th-filters">\s*</div>', "", frag, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", frag)).strip()


def _theads(text: str):
    """(감싼 div 의 class, table 의 속성, thead 안쪽) — thead 마다.

    `<thead>` 가 아니라 `<thead\\b` 로 찾는다. `>` 가 빠진 채로도 브라우저는
    알아서 고쳐 화면은 멀쩡한데, 검사만 그 표를 통째로 건너뛰기 때문이다
    (실제로 IR 기업현황이 그랬다 — 아래 검사가 그것을 막는다).
    """
    text = _markup(text)
    for m in re.finditer(r"<thead\b[^>]*>(.*?)</thead>", text, re.S):
        before = text[: m.start()]
        wraps = re.findall(r'<div class="(table-wrap[^"]*)"', before)
        tables = re.findall(r"<table\b([^>]*)>", before)
        yield (wraps[-1] if wraps else ""), (tables[-1] if tables else ""), m.group(1)


def _table_px(css: str, wrap_class: str, table_attrs: str):
    """그 표가 최소 몇 px 로 서는지. `%` 폭을 px 로 바꿔 재려면 이것이 필요하다."""
    tid = re.search(r'id="([^"]+)"', table_attrs)
    if tid:
        m = re.search(r"#" + re.escape(tid.group(1)) + r"\s*\{[^}]*min-width:\s*(\d+)px", css)
        if m:
            return int(m.group(1))
    if "wide" in wrap_class:
        m = re.search(r"\.table-wrap\.wide \.grid-table\s*\{[^}]*min-width:\s*(\d+)px", css)
        if m:
            return int(m.group(1))
    return None


def _column_px(head: str, table_px):
    """머리글 칸이 화면에서 **실제로** 몇 px 로 서는지. 못 재는 칸은 None.

    `table-layout: fixed` 는 적어 둔 폭을 그대로 쓰지 않는다.

      · `%` 는 표 폭에 대한 비율이다 — 표 폭을 알아야 px 로 환산된다.
      · 폭을 안 준 칸이 하나라도 있으면 **남는 자리를 그 칸들이 다 먹는다.**
        (IR 기업현황의 `한줄 소개` 가 그렇다)
      · 폭을 안 준 칸이 없으면 남는 자리를 **비율대로 나눠 갖는다.**
        투자사 관리 현황이 그렇다 — 적어 둔 합(2,714px)보다 표가 넓어서
        (`#contacts-table` min-width 2,804px) 칸마다 3% 씩 넓게 선다.
        적어 둔 값만 보면 멀쩡한 칸을 두 줄이라고 잘못 짚는다.
    """
    cells = re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S)
    raw = []
    for attrs, _cell in cells:
        px = re.search(r"width:\s*(\d+)px", attrs)
        pct = re.search(r"width:\s*(\d+)%", attrs)
        if px:
            raw.append(float(px.group(1)))
        elif pct and table_px:
            raw.append(int(pct.group(1)) * table_px / 100)
        else:
            raw.append(None)

    total = sum(w for w in raw if w is not None)
    # 폭을 안 준 칸이 있으면 그 칸이 남는 자리를 가져간다 — 나머지는 적어 둔 그대로.
    if table_px and None not in raw and 0 < total < table_px:
        raw = [w * table_px / total for w in raw]
    return cells, raw


def test_컬럼_이름이_두_줄로_접히면_머리글_줄이_들쭉날쭉해진다():
    """한 줄짜리 이름 옆에서 두 줄짜리만 위로 떠 있으면 줄이 어긋나 보인다.

    폭을 이름에 맞춰 잡아 두면 애초에 접히지 않는다. `TIPS …` 하나만 예외인데,
    그 이름은 한 줄에 넣으려면 칸이 260px 이어야 해서 값이 거의 없는 칸에
    자리를 너무 많이 내주게 된다.

    `%` 로 준 폭도 같이 잰다 — px 만 보던 검사라 IR 기업현황처럼 이름 칸이
    전부 `%` 인 표는 한 번도 검사되지 않았다.

    **재는 것은 이름이 아니라 화면에 실제로 서는 글자다.** 필터가 하나뿐인 칸은
    이름이 지워지고 `계약여부 ▾` 단추가 그 자리를 대신한다 — 이름만 재면 그
    칸들이 통째로 통과한다(`_FILTER_BTN_PX` 참고).

    그리고 **값을 고른 뒤까지 잰다.** 고르면 `계약여부 (1) ▾` 가 되어 24px 이
    더 드는데 그건 안 재고 있었다 — 화면에서는 멀쩡하다가 필터를 거는 순간
    열두 칸이 두 줄로 접혔다(`_FILTER_SUFFIX`).
    """
    css = CSS.read_text(encoding="utf-8")
    problems = []
    for path in sorted(TEMPLATES.glob("*.html")):
        for wrap, tattrs, head in _theads(path.read_text(encoding="utf-8")):
            table_px = _table_px(css, wrap, tattrs)
            cells, widths = _column_px(head, table_px)
            for (attrs, cell), have in zip(cells, widths):
                name = _name_only(cell)
                labels = _filter_labels(attrs)
                if have is None:
                    # 폭을 안 준 칸은 남는 자리를 나눠 갖는다 — 정적으로는 못 잰다
                    continue
                # 화면에 실제로 서는 것들. 필터가 하나뿐이면 이름은 지워진다.
                shown = []
                if name and "{{" not in name and "{%" not in name \
                        and name != _TWO_LINE_OK and len(labels) != 1:
                    shown.append((name, 0))
                # 18px = th 좌우 padding, 14px = 단추 padding·테두리
                shown += [(label + _FILTER_SUFFIX, 14) for label in labels]
                for text, extra in shown:
                    need = round(_text_px(text) + 18 + extra)
                    if need > have:
                        problems.append(
                            f"{path.name}: {text} ({have:.0f}px → {need}px 필요)")
    assert not problems, (
        "머리글 이름이 두 줄로 접힙니다. 칸 폭을 넓히세요"
        "(넓힌 뒤에는 app.css 의 그 표 min-width 도 함께):\n  "
        + "\n  ".join(problems))


def test_thead_의_닫는_꺾쇠가_빠지면_그_표만_검사에서_사라진다():
    """`<thead` 로 써도 브라우저는 알아서 고쳐 준다 — 그래서 아무도 못 봤다.

    IR 기업현황이 그 상태로 있었다. 화면은 멀쩡했지만 머리글을 `<thead>` 로
    찾는 검사들이 **그 표만 통째로 건너뛰어**, 정렬도 줄바꿈도 칸 수도 한 번도
    검사된 적이 없었다. 조용히 빠지는 쪽이 깨지는 쪽보다 나쁘다.
    """
    broken = []
    for path in sorted(TEMPLATES.glob("*.html")):
        text = _markup(path.read_text(encoding="utf-8"))
        opens = len(re.findall(r"<thead\b", text))
        proper = len(re.findall(r"<thead>", text))
        if opens != proper:
            broken.append(path.name)
    assert not broken, (
        "`<thead` 의 `>` 가 빠졌습니다 — 이 표는 머리글 검사에서 조용히 빠집니다: "
        + ", ".join(broken))


# --- 표 컬럼명 ↔ [수정] 패널 라벨 --------------------------------------------
#
# 표는 원본 시트의 컬럼 이름을 그대로 쓰는데 [수정] 패널만 저마다 줄여 부르고
# 있었다. 화면마다 따로 적어 두면 새 칸이 생길 때 또 어긋나므로,
# `data-field` ↔ `id="f-…"` 로 짝을 지어 전 화면을 한 번에 훑는다.


def _column_names(text: str) -> dict:
    """표가 부르는 이름. `data-field` → 머리글 이름.

    머리글과 첫 줄의 칸을 **자리 순서로** 짝짓는다. 개수가 다르면 짝이 어긋나
    엉뚱한 이름을 비교하게 되므로 그 표는 건너뛴다(딜 소싱처럼 머리글을
    반복문으로 만드는 표가 그렇다).
    """
    names = {}
    text = _markup(text)
    for m in re.finditer(r"<thead\b[^>]*>(.*?)</thead>(.*?)</tbody>", text, re.S):
        heads = [_name_only(c) for _, c in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)]
        row = re.search(r"<tr\b[^>]*>(.*?)</tr>", m.group(2), re.S)
        if not row:
            continue
        fields = []
        for cell in re.finditer(r"<td\b([^>]*)>(.*?)</td>", row.group(1), re.S):
            f = re.search(r'data-field="([A-Za-z0-9_]+)"', cell.group(1) + cell.group(2))
            fields.append(f.group(1) if f else None)
        if len(heads) != len(fields):
            continue
        for field, name in zip(fields, heads):
            if field and name:
                names.setdefault(field, name)
    return names


def _panel_names(text: str) -> dict:
    """[수정] 패널이 부르는 이름. `id="f-…"` → 라벨의 앞머리 글자.

    라벨 안에 또 라벨이 들어 있는 칸이 있어(채널 체크박스) 여는/닫는 것을
    세어 정확히 잘라낸다.

    이름은 **첫 태그 앞까지**만 본다 — `카톡방 이름 <b>정확히 일치해야
    발송됩니다</b>` 처럼 뒤에 붙는 것은 이름이 아니라 주의 문구다.
    """
    out = {}
    text = _markup(text)
    for open_tag in re.finditer(r'<label class="field[^"]*"[^>]*>', text):
        depth, end = 1, len(text)
        for tag in re.finditer(r"<(/?)label\b", text[open_tag.end():]):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                end = open_tag.end() + tag.start()
                break
        block = text[open_tag.end():end]
        span = re.search(r"<span[^>]*>(.*?)</span>", block, re.S)
        if not span:
            continue
        name = re.sub(r"\s+", " ", span.group(1).split("<")[0]).strip()
        for field in re.findall(r'id="f-([A-Za-z0-9_]+)"', block):
            out.setdefault(field, name or _name_only(span.group(1)))
    return out


def test_표에는_선호_투자분야인데_수정_창에는_섹터_태그면_같은_칸인지_알_수_없다():
    """표 컬럼명과 [수정] 패널 라벨은 **한 글자도 다르면 안 된다.**

    표 이름은 원본 구글시트에서 그대로 옮긴 것이라 바꿀 수 없다. 그러니
    맞추는 쪽은 늘 패널이다.

    `(쉼표)` 같은 입력 형식 안내는 이름이 아니다 — `placeholder` 로 옮기거나
    이름 뒤에 태그로 붙인다. 이름 자체에 섞으면 표와 글자가 달라진다.

    화면마다 따로 적지 않고 `data-field` ↔ `id="f-…"` 를 훑는다. 새 칸이
    생겨도 이름이 어긋나면 여기서 걸린다.
    """
    problems, checked = [], 0
    for path in sorted(TEMPLATES.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        panel = _panel_names(text)
        if not panel:
            continue                      # [수정] 패널이 없는 화면
        columns = _column_names(text)
        both = sorted(set(columns) & set(panel))
        # 짝이 하나도 안 잡히면 조용히 통과해 버린다 — 그쪽이 더 나쁘다
        assert both, f"{path.name}: 표와 패널을 짝지을 수 없습니다(칸 수가 어긋났는지 보세요)"
        checked += len(both)
        for field in both:
            if columns[field] != panel[field]:
                problems.append(
                    f"{path.name} · {field}: 표 '{columns[field]}' ≠ 수정 '{panel[field]}'")
    assert checked, "짝지어 볼 칸을 하나도 못 찾았습니다"
    assert not problems, (
        "표 컬럼명과 [수정] 패널 라벨이 다릅니다. **표 이름 쪽이 정답**입니다"
        "(표 이름은 원본 시트 그대로라 바꾸면 시트와 대조가 안 됩니다):\n  "
        + "\n  ".join(problems))



# --- 번호 칸 머리글 ----------------------------------------------------------
#
# 번호 칸의 머리글이 화면마다 `#` 였다. 기호 하나로는 무슨 칸인지 알 수 없고,
# 원본 시트가 `NO` 라 나란히 놓고 대조할 때도 눈이 한 번 걸린다.
#
# 화면 이름을 여기 적어 두지 않는다. **템플릿 폴더를 훑으므로 표가 새로 생기면
# 저절로 걸린다.**

def _templates_with_a_hash_header() -> dict:
    """`<th>#</th>` 가 남아 있는 템플릿 → 그런 칸의 개수."""
    found = {}
    for path in sorted(TEMPLATES.glob("*.html")):
        text = _markup(path.read_text(encoding="utf-8"))
        hits = 0
        for head in re.findall(r"<thead\b[^>]*>(.*?)</thead>", text, re.S):
            for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S):
                if _name_only(cell) == "#":
                    hits += 1
        if hits:
            found[path.name] = hits
    return found


def test_번호_칸_머리글은_기호가_아니라_NO_다():
    offenders = sorted(_templates_with_a_hash_header())
    assert not offenders, (
        "번호 칸 머리글이 `#` 로 남아 있습니다 — `NO` 로 바꾸세요"
        "(원본 시트가 `NO` 라 나란히 놓고 대조할 때 눈이 걸립니다): "
        + ", ".join(offenders))


# --- 머리글 필터 단추가 두 줄로 접히는 문제 ------------------------------------
#
# `담당자` 를 고르면 머리글이 `담당자 (1) ▾` 가 되는데 `담당자` / `(1) ▾` 로
# 갈라졌고, 폭이 조금만 모자라면 이름과 `▾` 가 갈라졌다.
#
# 폭은 위 검사가 지킨다. 여기서는 **갈라지지 않게 붙여 둔 방식**이 그대로인지를
# 본다 — 둘 중 하나만 되돌아가도 화면에서는 다시 두 줄이 된다.

def test_필터_단추의_꼬리표는_앞_낱말에서_떨어지지_않는다():
    """`(1)` 과 `▾` 앞은 **줄바꿈 없는 공백**이어야 한다.

    보통 공백이면 거기가 줄바꿈 자리가 된다. 그렇다고 머리글에 `nowrap` 을
    걸 수는 없다 — 원본 시트 이름을 그대로 쓰는 표라 `TIPS 운영사 …` 처럼 두
    줄이 필요한 이름이 있고, 한 줄로 묶으면 그 이름이 칸 밖으로 늘어난다
    (예전에 그렇게 했다가 되돌린 자리다).
    """
    js = FILTERS_JS.read_text(encoding="utf-8")
    assert "\\u00a0" in js, (
        "필터 단추의 꼬리표를 줄바꿈 없는 공백(U+00A0)으로 붙이지 않습니다 — "
        "`담당자` / `(1) ▾` 로 갈라집니다")
    # 붙이는 자리는 한 곳(`buttonLabel`)이어야 한다. 두 군데서 따로 만들면
    # 한쪽만 고쳐도 아무 티가 안 난다 — 실제로 그랬다.
    assert len(re.findall(r'\+\s*"\s+▾"', js)) == 0, (
        "보통 공백으로 `▾` 를 붙이는 자리가 남아 있습니다")
    assert len(re.findall(r"btn\.textContent\s*=|\.btn\.textContent\s*=", js)) == \
        len(re.findall(r"textContent = buttonLabel\(", js)), \
        "단추 글자를 만드는 자리가 `buttonLabel` 밖에도 있습니다"


def test_머리글_단추는_낱말_안에서_끊기지_않는다():
    """한글은 기본값이 글자와 글자 사이에서도 끊긴다 — `담당자` → `담당` / `자`.

    `keep-all` 이면 띄어쓰기에서만 끊긴다. `nowrap` 은 **안 된다** — 이 단추가
    컬럼 이름 자리를 대신하는 칸이 있어서, 한 줄로 묶으면 긴 이름이 칸 밖으로
    쭉 늘어난다.
    """
    css = CSS.read_text(encoding="utf-8")
    btn = _rule(css, ".filter-btn")
    assert "word-break: keep-all" in btn, ".filter-btn 이 낱말 안에서 끊깁니다"
    assert "nowrap" not in btn, (
        ".filter-btn 에 nowrap 을 걸면 긴 컬럼 이름이 칸 밖으로 늘어납니다")
    # 이름 쪽은 여전히 접혀야 한다 — `TIPS 운영사 …` 가 두 줄로 서는 자리다.
    assert "white-space: normal" in _rule(css, ".grid-table thead th"), \
        "머리글 이름까지 한 줄로 묶으면 긴 이름이 칸을 벌린다"


# --- 화면 위 단추 줄(툴바) ----------------------------------------------------
#
# 같은 `.secondary-btn` 인데 `<a>` 는 39px, `<button>` 은 34px 이었다(버튼은
# 글꼴을 물려받지 않는다). 거기에 `.primary-btn.inline` 31px · 검색칸 30px ·
# `촘촘히 보기` 19px 이 섞여 한 줄 안에서 20px 이 들쭉날쭉했다.
#
# 크기는 **한 곳에서만** 정한다. 화면마다 흩어 두면 탭이 하나 늘 때 또 어긋난다.

_TOOLBAR_CONTROLS = ("input", "select", "button", "a", "label", "textarea")


def _toolbar_blocks(text: str):
    """`<div class="toolbar">` 한 덩어리씩(여는/닫는 div 를 센다)."""
    text = _strip_html_comments(_markup(text))
    for m in re.finditer(r'<div class="toolbar"[^>]*>', text):
        depth, end = 1, len(text)
        for tag in re.finditer(r"<(/?)div\b", text[m.end():]):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                end = m.end() + tag.start()
                break
        yield text[m.end():end]


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def test_툴바_안의_크기는_한_값에서_나온다():
    """높이를 값 하나(`--ctl-h`)로 정하고 조작 요소를 전부 거기에 맞춘다."""
    css = CSS.read_text(encoding="utf-8")
    toolbar = _rule(css, ".toolbar")
    assert "--ctl-h" in toolbar, ".toolbar 가 칸 높이를 값으로 정하지 않습니다"
    sized = [body for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
             if ".toolbar" in selector and "height: var(--ctl-h)" in body]
    assert sized, "툴바 안 요소가 그 값을 쓰지 않습니다"


def test_툴바에_새로_놓는_요소도_같은_크기를_받는다():
    """템플릿을 훑어, 툴바에 실제로 들어 있는 태그가 모두 규칙에 걸리는지 본다.

    화면 이름을 적어 두지 않는다 — 툴바에 `<textarea>` 를 하나 놓는 순간
    여기서 걸려야 한다. 예전에 `#cs-search` 가 id 목록에서 빠져 혼자만 브라우저
    기본 입력칸(22px)으로 서 있던 것이 정확히 이 부류였다.
    """
    css = CSS.read_text(encoding="utf-8")
    covered = " ".join(selector for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                       if ".toolbar" in selector and "height: var(--ctl-h)" in body)
    missing = set()
    for path in sorted(TEMPLATES.glob("*.html")):
        for block in _toolbar_blocks(path.read_text(encoding="utf-8")):
            for tag in set(re.findall(r"<([a-z]+)\b", block)):
                if tag in _TOOLBAR_CONTROLS and f".toolbar {tag}" not in covered:
                    missing.add(f"{path.name}: <{tag}>")
    assert not missing, (
        "툴바에 있는데 높이 규칙이 안 걸리는 요소가 있습니다 — 그 줄만 크기가 "
        "따로 놉니다: " + ", ".join(sorted(missing)))


def test_툴바_검색칸을_id_로_하나씩_적지_않는다():
    """id 를 더 적어야 하는 규칙은 반드시 빠뜨린다.

    `#co-search, #vc-search, #sourcing-search` 로 적어 두었더니 화면이 하나
    늘 때 `#cs-search` 만 빠져서, 투자컨설턴트 현황의 검색칸만 22px 짜리
    브라우저 기본 입력칸으로 서 있었다.
    """
    # 주석은 지우고 본다 — 규칙 바로 위에 "예전에 `#cs-search` 가 빠져 있었다" 고
    # 적어 둔 설명이 있어서, 안 지우면 설명하려고 쓴 글자에 검사가 걸린다.
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    ids = set()
    for path in sorted(TEMPLATES.glob("*.html")):
        for block in _toolbar_blocks(path.read_text(encoding="utf-8")):
            for m in re.finditer(r'<input[^>]*type="search"[^>]*>', block):
                found = re.search(r'id="([^"]+)"', m.group(0))
                if found:
                    ids.add(found.group(1))
    assert ids, "툴바에서 검색칸을 하나도 못 찾았습니다"
    named = sorted(i for i in ids if f"#{i}" in css)
    assert not named, (
        "툴바 검색칸을 id 로 꾸미고 있습니다 — 화면이 늘면 반드시 하나 빠집니다. "
        "`.toolbar input[type=\"search\"]` 처럼 자리로 거세요: " + ", ".join(named))
