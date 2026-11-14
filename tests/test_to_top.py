"""'맨 위로' 단추가 **모든 화면에 실리는가.**

언제 뜨고 무엇을 올리는지는 브라우저 쪽 검사(tests/js/to_top_test.js)가 본다.
여기서는 단추가 밑틀(`base.html`)에서 화면까지 닿는지와, 떠 있는 자리가 다른
창을 가리지 않는 층에 있는지를 본다.
"""
from __future__ import annotations

import pathlib
import re

import pytest

CSS = pathlib.Path("app/static/css/app.css")


def _z(css: str, selector: str) -> int:
    m = re.search(re.escape(selector) + r"\s*\{[^}]*z-index:\s*(\d+)", css)
    assert m, f"{selector} 의 z-index 를 못 찾았다"
    return int(m.group(1))


@pytest.mark.parametrize("url", ["/contacts", "/companies"])
def test_화면마다_맨_위로_단추가_선다(logged_in, url):
    html = logged_in.get(url).text
    tag = re.search(r'<button[^>]*id="to-top"[^>]*>', html)
    assert tag, f"{url} 에 '맨 위로' 단추가 없다"
    tag = tag.group(0)
    # 폼 안에 서도 제출 단추가 되지 않게 · 읽는 사람에게 화살표가 아니라 이름으로.
    assert 'type="button"' in tag and 'aria-label="맨 위로"' in tag
    # 맨 위에서는 숨어 있다가 내려가면 `to_top.js` 가 띄운다. 종이에는 안 나간다.
    assert " hidden" in tag and "no-print" in tag
    assert "/static/js/to_top.js" in html


def test_맨_위로_단추는_다른_창_밑에_선다():
    """이동 바·표 머리보다는 위, 수정창 뒷막보다는 아래 — 창이 열리면 그 밑으로 들어간다."""
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    rule = re.search(r"\.to-top\s*\{([^}]*)\}", css)
    assert rule and "position: fixed" in rule.group(1)
    z = _z(css, ".to-top")
    assert _z(css, ".jump-bar.flow-jump") < z < _z(css, ".panel-backdrop"), z
