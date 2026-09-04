"""참고 자료 표 고치기(JS)를 node 로 돌려 본다.

로직이 브라우저에 있으므로 테스트도 같은 언어로 둔다(tests/test_weekly_tasks_js.py
와 같은 방식). node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저
자산 테스트라 서버 실행에 필요한 의존성이 아니다.
로컬에서는 `node tests/js/ref_head_edit_test.js` 로도 돈다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HEAD_TEST = Path(__file__).resolve().parent / "js" / "ref_head_edit_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_a_header_is_edited_the_same_way_a_cell_is():
    """머리글도 눌러서 고친다 — 그리고 **칸과 같은 길**로 고친다.

    표를 화면에서 세울 수 있게 되면서 머리글이 `칸 1 · 칸 2 …` 로 서는데, 한 표
    안에서 머리글과 칸을 고치는 법이 다르면 쓰는 사람이 헷갈리고 나중에 한쪽만
    고쳐진다. 저장이 실패했을 때 되돌리고 이유를 말하는지까지 함께 본다 —
    화면에는 새 이름, 서버에는 옛 이름으로 갈리면 새로고침 전까지 아무도 모른다.
    """
    node = shutil.which("node")
    result = subprocess.run(
        [node, str(HEAD_TEST)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
