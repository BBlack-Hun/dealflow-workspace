"""문구 관리 화면의 **문구 검색** — 검색칸이 그려지고, 거를 단위를 싣는가.

거르는 일은 브라우저가 한다(`static/js/templates_search.js`). 여기서는 서버가
그리는 쪽만 본다 — 검색칸 · 개수 · 스크립트, 그리고 문구 줄마다 붙는 표시.
판단(이름 · 본문 · 여러 낱말 · 빈 구간 숨김 · 되돌리기)은 node 로 돌린다 —
맨 아래 래퍼가 그것이다.

문구는 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

JS_TEST = Path(__file__).resolve().parent / "js" / "templates_search_test.js"


@pytest.fixture()
def two_templates(db, users):
    from app.models import MessageTemplate

    db.add_all([
        MessageTemplate(user_id=None, kind="closing_day1", name="가 안내",
                        body="검색용 지어낸 문구 하나", is_active=1),
        MessageTemplate(user_id=users["u1"].id, kind="closing_remind", name="나 리마인드",
                        body="검색용 지어낸 문구 둘", is_active=1),
    ])
    db.commit()


def test_검색칸이_그려지고_개수가_문구_수와_같다(logged_in, two_templates):
    body = logged_in.get("/templates").text
    box = re.search(r'<input type="search" id="tpl-search" placeholder="([^"]*)"', body)
    assert box, "문구 검색칸이 안 그려진다"
    rows = body.count("data-tpl-row")
    assert rows >= 2
    assert f"({rows}개)" in box.group(1), "placeholder 의 개수가 그려진 문구 수와 다르다"
    assert 'id="tpl-search-empty" hidden>검색 결과 없음<' in body
    assert "/static/js/templates_search.js" in body
    # 검색칸은 구간보다 위에 선다.
    assert body.index('id="tpl-search"') < body.index('id="closing_day1"')


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_문구_검색_브라우저_판단():
    result = subprocess.run([shutil.which("node"), str(JS_TEST)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
