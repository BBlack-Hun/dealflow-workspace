"""모든 목록 표의 맨 왼쪽 `NO` (#100) — app.css 의 `tr::before` 카운터.

번호 칸은 CSS 가 세우므로 표마다 칸을 더하지 않는다. 그 대신 **이미 `NO` 칸이
있는 표는 빼야** 번호 칸이 둘이 되지 않는다. 빼는 목록(`content: none`)이 템플릿과
어긋나지 않는지를 여기서 본다 — 새 표에 `NO` 칸을 세우면 이 검사가 빼라고 알려 준다.
(보이는 줄만 세는지 · 정렬을 따라가는지는 브라우저가 하는 일이라 헤드리스 크롬으로 쟀다.)
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "app" / "templates"


def _opt_out() -> set:
    m = re.search(r":is\(([^)]*)\)\s*>\s*\*\s*>\s*tr::before\s*\{\s*content:\s*none", CSS)
    assert m, "번호를 빼는 규칙(`:is(…) > * > tr::before { content: none }`)을 못 찾았습니다"
    return {s.strip() for s in m.group(1).split(",")}


def _tables_with_own_no() -> set:
    """`NO` 머리글이나 JS 가 채우는 `.rowno` 칸을 이미 가진 표의 `#id`."""
    found = set()
    for path in TEMPLATES.glob("*.html"):
        text = re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        for m in re.finditer(r"<table\b([^>]*)>(.*?)</table>", text, re.S):
            attrs, body = m.groups()
            if "grid-table" in attrs and (re.search(r">\s*NO\s*</th>", body) or "rowno" in body):
                tid = re.search(r'id="([^"]+)"', attrs)
                assert tid, f"{path.name}: NO 칸이 있는 표에 id 가 없어 번호를 뺄 수 없습니다"
                found.add("#" + tid.group(1))
    return found


def test_번호를_매긴다():
    assert re.search(r"tr::before\s*\{[^}]*content:\s*counter\(rowno\);\s*counter-increment:\s*rowno", CSS)
    # 머리글은 다른 번호 칸과 같은 `NO`(test_ui_layout 의 `#` 금지와 같은 이유).
    assert re.search(r"thead\s*>\s*tr::before\s*\{[^}]*content:\s*\"NO\"", CSS)


def test_NO_칸이_이미_있는_표는_뺀다():
    own, out = _tables_with_own_no(), _opt_out()
    assert own - out == set(), f"번호 칸이 둘이 됩니다 — app.css 의 빼는 목록에 넣으세요: {own - out}"
    # 집계표 말고는 빼는 까닭이 `NO` 칸이어야 한다 — 칸이 없어졌는데 남아 있으면 번호가 빠진다.
    assert out - {".year-report"} == own, f"NO 칸이 없는데 빼고 있습니다: {out - own - {'.year-report'}}"
