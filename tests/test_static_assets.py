"""브라우저 자산의 '조용한 고장'을 막는 검사.

기업 검색 필터가 동작하지 않은 적이 있다. JS 로직 테스트는 전부 통과했는데
화면에서는 아무 것도 걸러지지 않았다. 원인은 CSS 였다 — `.pick-card { display: flex }`
가 브라우저 기본 `[hidden] { display: none }` 을 우선순위로 이겨서, JS 가
`el.hidden = true` 를 해도 카드가 계속 보였다.

검색·필터·탭·상세패널이 모두 el.hidden 에 기대고 있어서 같은 함정이 언제든
다시 생길 수 있다. 그래서 로직이 아니라 **규칙의 존재 자체**를 검사한다.
"""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
CSS = STATIC / "css" / "app.css"


def test_hidden_attribute_always_wins():
    """el.hidden = true 가 어떤 클래스에도 지지 않아야 한다."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important", css), (
        "`[hidden] { display: none !important }` 가 없습니다. "
        "display 를 지정한 클래스가 [hidden] 을 이겨서 JS 의 숨김이 무시됩니다."
    )


def test_js_hidden_users_have_the_guard():
    """el.hidden 을 쓰는 스크립트가 있는 한 위 규칙은 필수다(둘이 함께 산다)."""
    users = [p.name for p in (STATIC / "js").glob("*.js")
             if re.search(r"\.hidden\s*=", p.read_text(encoding="utf-8"))]
    assert users, "el.hidden 을 쓰는 스크립트가 사라졌다면 이 검사도 함께 지우세요."
