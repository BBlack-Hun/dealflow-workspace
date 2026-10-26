"""인라인 이벤트 속성(onsubmit · onclick · onchange …) 안의 값은 `|tojson` 으로만 넣는다.

자동 이스케이프는 `'` 를 `&#39;` 로 바꾸지만 브라우저는 속성 값을 먼저 풀어 다시 `'` 로
만든 뒤 JS 로 읽는다 — JS 문자열 안에 그냥 넣은 값은 그 문자열을 닫고 나올 수 있다.
`columns.html` · `templates.html` 이 쓰던 방식(`confirm({{ (…)|tojson }})`)으로 맞춘다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .conftest import DEMO_PASSWORD

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
TRICKY = "x'+alert(1)+'"


def _raw_values_in_handlers(text: str) -> list:
    text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    text = re.sub(r"\{\{(.*?)\}\}",
                  lambda m: "@SAFE@" if m.group(1).strip().endswith("|tojson") else "@RAW@",
                  text, flags=re.S)
    return [m.group(0) for m in re.finditer(r"""\son[a-z]+\s*=\s*("[^"]*"|'[^']*')""", text)
            if "@RAW@" in m.group(1)]


def test_no_template_puts_raw_values_in_inline_handlers():
    found = {p.name: hits for p in sorted(TEMPLATES.rglob("*.html"))
             if (hits := _raw_values_in_handlers(p.read_text(encoding="utf-8")))}
    assert found == {}


def test_the_scan_catches_the_old_form():
    old = """<form onsubmit="return confirm('{{ c.label }} 칸을 지울까요?')">"""
    new = """<form onsubmit='return confirm({{ (c.label ~ " 칸을 지울까요?")|tojson }})'>"""
    assert _raw_values_in_handlers(old) and not _raw_values_in_handlers(new)


def test_member_name_is_encoded_in_team_confirms(client, db, users):
    users["u2"].role = "admin"
    users["u1"].name = TRICKY
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    page = client.get("/team").text

    handlers = re.findall(r"onsubmit='(return confirm\(.*?\))'", page)
    asks = [json.loads(re.fullmatch(r"return confirm\((\".*\")\)", h).group(1)) for h in handlers]
    assert TRICKY + " 님의 비밀번호를 초기 비밀번호로 되돌릴까요?\n로그인된 기기가 모두 끊기고, " \
        "첫 로그인 때 새 비밀번호를 정하게 됩니다." in asks
    assert TRICKY + " 계정을 정지할까요?\n담당 투자사와 이력은 남습니다." in asks
    # 속성 안에는 따옴표도 엔티티도 날것으로 남지 않는다
    assert not any("'" in h or "&#39;" in h for h in handlers)
    assert f"confirm('{TRICKY}" not in page and "confirm('x&#39;" not in page
