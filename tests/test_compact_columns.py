"""표 칸 사이 간격 줄이기(#167 · 11/06 팀원 요청).

「모든 컬럼 들 > 공간폭을 최대한 줄여주세요 읽기좋게 — 가령 IR 기업 현황 대분류 , 소분류 ,
23년 매출 사이간격을 줄이면 좀더 보기 좋을거 같습니다.」

간격이 벌어진 까닭은 둘이었다.

  1. **칸 안쪽 여백** — 표마다 9px · 12px · 8px 로 갈려 있었다. 이제 `:root` 의 `--cell-x`
     한 값(6px)을 모든 표가 쓴다.
  2. **`%` 로 준 칸** — IR 기업 현황의 `기업명` · `대분류` · `소분류` · `투자라운드` 는 13 · 10 ·
     9 · 9% 라, 칸이 들 때마다 표 min-width 를 올리면 넷도 따라 넓어져 278 · 214 · 192 ·
     192px 까지 갔다(값은 80px 안팎). px 로 못 박고 표 폭을 칸 폭 합에 맞췄다.
"""
from __future__ import annotations

import pathlib
import re

CSS = pathlib.Path("app/static/css/app.css")
TEMPLATES = pathlib.Path("app/templates")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def test_칸_여백은_한_값에서_나온다():
    css = _css()
    m = re.search(r":root\s*\{[^}]*--cell-x:\s*(\d+)px", css)
    assert m, "`:root` 에 `--cell-x` 가 없습니다"
    assert int(m.group(1)) <= 6, f"칸 여백이 다시 늘었습니다({m.group(1)}px)"
    # 표 목록의 칸 규칙이 숫자를 따로 들고 있으면 한쪽만 고쳐진다.
    for selector in (r"\.grid-table th", r"\.grid-table td", r"\.table-wrap\.wide \.grid-table td",
                     r"\.grid-table\.dense td", r"\.grid-table\.compact td, \.grid-table\.compact th",
                     r"\.log-table th, \.log-table td", r"\.grid-table tfoot th"):
        rule = re.search(r"(?m)^" + selector + r"\s*\{([^}]*)\}", css)
        assert rule, f"`{selector}` 규칙이 없습니다"
        pad = re.search(r"padding:\s*([^;]+);", rule.group(1))
        assert pad and "var(--cell-x)" in pad.group(1), \
            f"`{selector}` 의 좌우 여백이 `--cell-x` 가 아닙니다: {pad and pad.group(1)}"


def _thead(name: str, table_id: str) -> str:
    text = re.sub(r"\{#.*?#\}", "", (TEMPLATES / name).read_text(encoding="utf-8"), flags=re.S)
    at = text.index(f'id="{table_id}"')
    return text[text.index("<thead", at):text.index("</thead>", at)]


def test_IR_기업_현황에는_퍼센트_칸이_없다():
    """`%` 칸은 표가 넓어질수록 따라 넓어진다 — 간격이 벌어진 바로 그 까닭이다."""
    head = _thead("companies.html", "co-table")
    assert not re.findall(r"width:\s*\d+%", head), "IR 기업 현황 머리글에 `%` 폭이 다시 섰습니다"
    widths = {}
    for attrs, body in re.findall(r"<th\b([^>]*)>(.*?)</th>", head, re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        px = re.search(r"width:\s*(\d+)px", attrs)
        if px:
            widths[name] = int(px.group(1))
    # 팀원이 짚은 칸 — 값(80px 안팎)과 단추가 서는 만큼만.
    assert widths["대분류"] <= 100 and widths["소분류"] <= 120 and widths["투자라운드"] <= 110, widths


def test_IR_표_폭은_칸_폭_합이다(logged_in):
    """남는 자리를 나눠 갖는 `%` 칸이 없으니, 표 폭이 칸 폭 합보다 넓으면 **모든 칸이 비율대로
    늘어** 줄인 간격이 도로 벌어진다. 좁으면 칸이 눌려 머리글이 접힌다. 같아야 한다.

    화면 그대로 잰다(해마다 바뀌는 매출 칸 · `NO` 폭이 템플릿 변수라). 이 검사의 계정은
    투자컨설턴트 화면을 못 봐서 그 두 칸이 안 선다 — min-width 도 그 두 칸을 뺀 값이다.
    """
    html = logged_in.get("/companies").text
    at = html.index('id="co-table"')
    head = html[html.index("<thead", at):html.index("</thead>", at)]
    assert ">컨설팅 상태<" not in head
    total = sum(int(w) for w in re.findall(r"width:\s*(\d+)px", head))
    got = int(re.search(r"#co-table \{\s*min-width:\s*(\d+)px", _css()).group(1))
    assert got == total, f"`#co-table` min-width {got}px ≠ 칸 폭 합 {total}px"


def test_투자사_관리_현황_표는_칸_폭_합을_담는다():
    head = _thead("contacts.html", "contacts-table")
    total = sum(int(w) for w in re.findall(r"width:\s*(\d+)px", head))
    got = int(re.search(r"#contacts-table \{ min-width: (\d+)px", _css()).group(1))
    assert total <= got <= total + 80, (
        f"`#contacts-table` min-width {got}px · 칸 폭 합 {total}px — 표가 합보다 한참 넓으면 "
        "칸마다 비율대로 늘어 줄인 간격이 도로 벌어진다")
