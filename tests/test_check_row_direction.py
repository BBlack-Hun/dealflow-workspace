"""체크박스 칸(`.check-row`)이 **한 줄에 나란히** 서는가.

## 왜 이 검사가 있나

`label.field check-row` 처럼 **둘을 함께 붙이는 자리**가 있다. `.field` 는
`flex-direction: column`(칸 이름 위 · 입력칸 아래)이라, `.check-row` 가 방향을
다시 못 박지 않으면 **세로로 쌓인다** — 체크박스가 위로 뜨고 글자가 아래로
내려간다. 여기에 `.form-grid .check-row` 의 `align-items: center` 까지 걸리면
세로 방향에서는 그것이 **가로 가운데**를 뜻해서, 글자만 칸 한복판에 선다.

실제로 그 모양이었다(사용자 지적: "체크박스는 좌측 상단에 있고 정 중앙에
`추천 딜(★)` 이게 있음"). 화면에서만 보이고 코드에서는 두 클래스가 각각
멀쩡해 보여서 찾기 어려운 자리라, 자로 박아 둔다.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "app.css"


def _rule(name: str) -> str:
    """선택자 하나의 속성 덩어리. 주석은 건너뛴다."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    m = re.search(re.escape(name) + r"\s*\{([^}]*)\}", css)
    assert m, f"`{name}` 규칙이 없다"
    return m.group(1)


def _prop(block: str, key: str) -> str:
    m = re.search(rf"(?:^|;)\s*{re.escape(key)}\s*:\s*([^;]+)", block)
    return (m.group(1).strip() if m else "")


def test_체크박스와_글자가_한_줄에_선다():
    block = _rule(".check-row")
    assert _prop(block, "flex-direction") == "row", (
        "`.check-row` 에 `flex-direction: row` 가 없다 — `label.field` 와 함께 "
        "붙는 자리에서 `.field` 의 `column` 이 이겨 세로로 쌓인다")


def test_세로_가운데는_check_row_가_정한다():
    """`align-items` 가 방향과 **같은 규칙**에 있어야 한다.

    방향은 여기, 정렬은 저기로 갈라 두면 한쪽만 고쳐지는 날 다시 어긋난다 —
    이 버그가 정확히 그렇게 났다.
    """
    assert _prop(_rule(".check-row"), "align-items") == "center"
    grid = _rule(".form-grid .check-row")
    assert not _prop(grid, "flex-direction"), \
        "격자 규칙이 방향을 또 정하고 있다 — 방향은 `.check-row` 한 곳이다"


def test_함께_붙는_field_는_세로_그대로다():
    """`.field` 를 가로로 바꿔 고치면 **다른 모든 칸**이 깨진다."""
    assert _prop(_rule(".field"), "flex-direction") == "column"
