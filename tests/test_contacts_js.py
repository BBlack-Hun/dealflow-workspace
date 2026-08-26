"""내 투자사 화면(JS)을 node 로 돌려 본다.

로직이 브라우저에 있으므로 테스트도 같은 언어로 둔다(tests/test_filters_js.py 와 같은 방식).
node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저 자산 테스트라
서버 실행에 필요한 의존성이 아니다. 로컬에서는 `node tests/js/contacts_open_test.js` 로도 돈다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

OPEN_TEST = Path(__file__).resolve().parent / "js" / "contacts_open_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_dashboard_link_actually_opens_the_detail_panel():
    """대시보드에서 눌러 와도 상세가 안 열린다 — 함수가 다른 IIFE 안에 갇혀 있다.

    '내 투자사 선호'에서 사람을 누르면 /contacts?contact=<id> 로 온다. 화면은
    window.DEALFLOW_OPEN_CONTACT 에 번호를 적어 두고 contacts.js 가 그것을 보고
    상세를 여는데, 그 몇 줄이 상세 패널과 **다른 IIFE** 에 떨어져 있어서
    loadContact 이라는 이름이 닿지 않았다. ReferenceError 로 죽고 목록만 남는다 —
    오류는 콘솔에만 있어 눈에 안 띈다.

    `<script>` 태그가 그려지는지만 보는 검사(test_dashboard.py)로는 못 잡는다.
    그래서 여기서는 가짜 DOM 위에 contacts.js 를 **실제로 실행**해서, 번호를 주면
    /api/contacts/<id> 를 부르고 패널이 정말 열리는지까지 본다.
    """
    node = shutil.which("node")
    result = subprocess.run(
        [node, str(OPEN_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
