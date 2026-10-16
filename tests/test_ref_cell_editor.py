"""참고 표에 **긴 글**(딜소개 스크립트)을 넣을 수 있는가 — #11 · #13.

사용자 말: "딜소개 스크립트를 넣으면 스크롤이 안 내려가고 내용도 기입이 안 됨."
투자컨설턴트 현황에서도 같은 말이 나왔다. 두 화면이 같은 참고 표 부품을 쓴다
(`_ref_panel.html` · `js/ref_edit.js`).

헤드리스 크롬으로 실제 템플릿·CSS·JS 를 그려 재 본 원인 둘:

1. **칸 편집기가 한 줄짜리**였다(`rows = 1`, 자라지 않음). 쉰 줄 스크립트
   (950px)가 29px 칸 안에 갇혀 한 줄만 보였고, 줄을 나누려고 Enter 를 치는
   순간 칸이 닫히며 저장됐다.
2. 참고 표가 **넓은 표 감싸개**(`.table-wrap.wide`)를 받아 2,030px 로 벌어지고
   키가 화면 높이로 잘렸다. 저장된 쉰 줄이 563px 상자 안에 1,050px 로 갇혀
   페이지 스크롤과 표 스크롤이 두 겹이 됐다.

키 동작은 tests/js/ref_cell_keys_test.js 가 `ref_edit.js` 를 그대로 돌려 본다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD

ROOT = Path(__file__).resolve().parents[1]
KEYS_TEST = ROOT / "tests" / "js" / "ref_cell_keys_test.js"
CSS = ROOT / "app" / "static" / "css" / "app.css"


@pytest.fixture()
def table_sheet(client, db, users):
    """딜소개 스크립트 표 — 투자사 관리 현황과 투자컨설턴트 현황에 하나씩."""
    from app.models import RefSheet

    content = json.dumps({
        "columns": ["구분", "스크립트", "비고"],
        "rows": [["첫인사", "안녕하세요\n딜 소개 드립니다", ""]],
    }, ensure_ascii=False)
    out = {}
    for page in ("contacts", "consulting"):
        row = RefSheet(position=3, kind="table", is_active=1, page=page,
                       title="딜소개 스크립트", content_json=content)
        db.add(row)
        out[page] = row
    # 투자컨설턴트 현황은 켜 준 사람만 들어간다(`require_access`).
    users["u1"].can_view_consulting = 1
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return out


def _ref_wrap(html: str) -> str:
    """참고 표(`#ref-table`)를 감싼 여는 `<div …>` 태그."""
    at = html.index('id="ref-table"')
    return html[html.rindex("<div", 0, at):at].split(">", 1)[0]


@pytest.mark.parametrize("page", ["contacts", "consulting"])
def test_the_reference_table_is_not_cut_to_the_screen(client, table_sheet, page):
    """참고 표는 넓은 표 감싸개를 받지 않는다 — 페이지가 그대로 굴러간다.

    `.wide` 는 여든 줄짜리 명단 표를 위한 것이다(2,030px · 키를 화면 높이로
    자른다). 칸 셋에 문단이 드는 표가 그걸 받으면 스크립트 한 칸이 화면 안의
    작은 상자에서 따로 구른다. 두 화면이 같은 부품을 쓰므로 둘 다 본다.
    """
    r = client.get(f"/{page}?ref={table_sheet[page].id}")
    assert r.status_code == 200
    html = r.text
    wrap = _ref_wrap(html)
    assert 'class="table-wrap"' in wrap, f"{page}: {wrap}"
    assert "wide" not in wrap, (
        f"{page}: 참고 표가 넓은 표 감싸개에 있다 — 2,030px 로 벌어지고 "
        f"키가 화면 높이로 잘려 긴 칸이 작은 상자 안에서 따로 구른다: {wrap}")
    # 칸이 많은 표가 짜부라지지 않게 칸 수를 실어 준다(CSS 가 최소 폭을 곱한다).
    assert "--ref-cols: 3" in html, f"{page}: 칸 수(--ref-cols)를 안 실었다"
    # 줄바꿈은 그대로 그린다 — 칸이 `pre-wrap` 이라 저장된 줄이 살아 있다.
    assert "안녕하세요\n딜 소개 드립니다" in html
    # 고치는 손잡이가 실린다 — 안 실리면 "눌러서 고칩니다" 라고 적어 놓고
    # 아무 일도 안 한다.
    assert "js/ref_edit.js" in html


def test_many_columns_keep_a_minimum_width_inside_the_scroll_box():
    """보통 감싸개로 옮기면서 칸이 많은 표가 화면 폭에 눌리지 않게 한다.

    폭을 못 박는 규칙은 **`.table-wrap` 안쪽에만** 건다 — 받아 줄 상자가
    없으면 그 폭이 그대로 페이지를 밀어낸다(tests/test_mobile_layout.py).
    """
    css = CSS.read_text(encoding="utf-8")
    m = re.search(r"\.table-wrap\s+#ref-table\s*\{([^}]*)\}", css)
    assert m, "참고 표의 최소 폭 규칙이 없다"
    assert "var(--ref-cols" in m.group(1) and "min-width" in m.group(1), m.group(1)


def test_the_editor_grows_instead_of_scrolling_inside_itself():
    """자라는 입력칸에는 손잡이와 안쪽 스크롤을 떼어 둔다 — 둘이 서로 싸운다."""
    css = CSS.read_text(encoding="utf-8")
    m = re.search(r"#ref-table\s+\.cell-input\s*\{([^}]*)\}", css)
    assert m, "참고 표 입력칸 규칙이 없다"
    assert "resize: none" in m.group(1) and "overflow: hidden" in m.group(1), m.group(1)


def test_a_long_multi_line_script_is_saved_as_is(client, table_sheet, db):
    """서버는 줄바꿈을 그대로 담는다 — 앞뒤 공백만 걷는다."""
    sheet = table_sheet["contacts"]
    script = "\n".join(f"{i}번째 줄 · 딜 소개 드립니다" for i in range(1, 51))
    r = client.patch(f"/api/ref-sheets/{sheet.id}/cell",
                     json={"row": 0, "col": 1, "value": "  " + script + "\n"})
    assert r.status_code == 200
    db.refresh(sheet)
    assert json.loads(sheet.content_json)["rows"][0][1] == script


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_enter_breaks_the_line_and_ctrl_enter_saves():
    """Enter 줄바꿈 · Ctrl/Cmd+Enter 저장 · Esc 취소 · 조합 중 Enter 무시 ·
    머리글은 Enter 저장 · 쓰는 만큼 자람 — `ref_edit.js` 를 그대로 돌린다."""
    r = subprocess.run([shutil.which("node"), str(KEYS_TEST)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
