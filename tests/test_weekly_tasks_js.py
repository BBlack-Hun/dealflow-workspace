"""주간 업무 화면(JS)을 node 로 돌려 본다.

로직이 브라우저에 있으므로 테스트도 같은 언어로 둔다(tests/test_contacts_js.py 와
같은 방식). node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저 자산
테스트라 서버 실행에 필요한 의존성이 아니다.
로컬에서는 `node tests/js/weekly_status_test.js` 로도 돈다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

STATUS_TEST = Path(__file__).resolve().parent / "js" / "weekly_status_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_status_reverts_when_the_save_fails():
    """상태 칸은 고르는 순간 저장한다. 실패하면 알림만 뜨고 칸은 고른 그대로
    서 있었다 — 화면에는 `완료`, 서버에는 `예정`. 새로고침 전까지 다 한 줄로
    보인다. 칸 수정(inline_edit.js)은 실패하면 이미 되돌린다."""
    node = shutil.which("node")
    result = subprocess.run(
        [node, str(STATUS_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
