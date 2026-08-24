"""폰에서 열었을 때 깨지지 않는가.

**보기 전용**이다 — 발송은 PC 의 발송 프로그램이 하므로 폰에서 하지 않는다.
밖에서 "지금 뭐가 밀렸나" 를 확인하는 용도라, 읽는 것만 편하면 된다.

브라우저 없이 실제 화면을 볼 수는 없으므로 **깨지는 원인**을 못 박는다.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from .conftest import DEMO_PASSWORD

CSS = pathlib.Path("app/static/css/app.css")
PAGES = ["/", "/todo", "/deals", "/companies", "/companies?tab=db",
         "/contacts", "/ir", "/templates", "/report", "/setup"]


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def test_every_page_uses_a_responsive_viewport(logged, client):
    """`width=1280` 이던 때는 폰에서 축소된 PC 화면이 떠서 글자를 읽으려면
    매번 확대해야 했다."""
    for path in PAGES:
        body = logged.get(path).text
        assert "width=device-width" in body, path
        assert "width=1280" not in body, path

    # 로그인 화면도 마찬가지 — base.html 을 안 거칠 수 있다
    assert "width=device-width" in client.get("/login").text


def test_wide_things_are_covered_by_a_breakpoint():
    """화면보다 넓은 고정 폭은 반드시 모바일 규칙이 받아 줘야 한다.
    안 그러면 페이지 전체가 가로로 밀린다."""
    css = CSS.read_text(encoding="utf-8")
    mobile = "\n".join(
        m.group(0) for m in re.finditer(r"@media[^{]*max-width[^{]*\{.*?\n\}", css, re.S))

    # 폰 화면(360px)보다 넓은 고정 폭을 쓰는 것들
    for selector in (".detail-panel", ".login-card"):
        assert selector in mobile, f"{selector} 를 좁히는 규칙이 없다"

    # 상세 패널은 폰에서 화면을 다 써야 한다
    assert "width: 100vw" in mobile


def test_wide_tables_scroll_instead_of_squeezing():
    """표는 좁히면 못 읽는다 — 폭을 지키고 가로로 민다."""
    css = CSS.read_text(encoding="utf-8")
    assert ".table-wrap { overflow-x: auto" in css or \
           re.search(r"\.table-wrap\s*\{[^}]*overflow-x:\s*auto", css)
    # 폰이라고 더 좁히지 않는다
    assert ".table-wrap.wide .grid-table { min-width: 2030px; }" in css


def test_horizontal_strips_can_be_swiped():
    """탭·칩 줄은 접지 않고 민다 — 접으면 눌러야 보인다."""
    css = CSS.read_text(encoding="utf-8")
    mobile = css[css.index("@media (max-width: 720px)"):]
    for strip in (".sheet-tabs", ".jump-bar", ".funnel", ".mode-tabs", ".chip-row"):
        assert strip in mobile, f"{strip} 이 모바일에서 밀리지 않는다"


def test_multi_column_grids_stack_on_a_phone():
    """두세 칸으로 나뉜 것을 폰에서 그대로 두면 글자가 세로로 눌린다."""
    css = CSS.read_text(encoding="utf-8")
    mobile = css[css.index("@media (max-width: 720px)"):]
    for grid in (".kpi-row", ".dash-grid", ".deal-grid", ".form-grid", ".mini-charts"):
        assert grid in mobile, f"{grid} 이 폰에서 한 줄로 안 선다"


def test_the_menu_lies_down_on_a_narrow_screen():
    """좌측 200px 메뉴를 폰에서 그대로 두면 본문이 손바닥만 해진다."""
    css = CSS.read_text(encoding="utf-8")
    assert "@media (max-width: 1080px)" in css
    tablet = css[css.index("@media (max-width: 1080px)"):]
    assert ".layout { flex-direction: column; }" in tablet
    assert ".menu { flex-direction: row" in tablet
