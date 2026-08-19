"""필터 컴포넌트(JS)의 순수 로직을 node 로 돌린다.

로직이 브라우저에 있으므로 테스트도 같은 언어로 두는 편이 정직하다
(파이썬으로 다시 구현하면 두 벌이 되고, 어긋나도 알아채지 못한다).
node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저 자산 테스트라
서버 실행에 필요한 의존성이 아니다. 로컬에서는 `node tests/js/filters_test.js` 로도 돈다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_TEST = Path(__file__).resolve().parent / "js" / "filters_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_filters_js_rules():
    result = subprocess.run(
        [shutil.which("node"), str(JS_TEST)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
