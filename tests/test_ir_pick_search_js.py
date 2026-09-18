"""딜 진행 관리의 **고르는 두 칸**(JS)을 node 로 돌려 본다.

로직이 브라우저에 있으므로 테스트도 같은 언어로 둔다(`tests/test_filters_js.py`
와 같은 방식). node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저
자산 테스트라 서버 실행에 필요한 의존성이 아니다.

**래퍼가 여기 있어야 CI 가 돈다.** node 검사를 만들어 두고 파이썬 쪽에서 안
부르면, 그 검사는 손으로 부르는 사람이 있을 때만 도는 검사가 된다.

서버 쪽(화면이 무엇을 싣나 · 안 고르고 보낼 수 있나 · 질의가 몇 번인가)은
`tests/test_ir_pick_search.py` 가 본다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path(__file__).resolve().parent / "js"


def _run(name: str) -> None:
    node = shutil.which("node")
    result = subprocess.run([node, str(JS_DIR / name)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_담당자_검색이_고르는_값을_안_흔드는가():
    """133명에서 찾아지는가, 그리고 **번호가 그대로 실려 가는가.**

    · 이름·투자사 가운데 글자로도 좁혀진다(`<datalist>` 로는 안 되는 자리).
    · 검색은 **거르기만 한다** — 좁혀졌다고 대신 골라 주지 않는다.
    · 하나로 좁혀졌을 때의 Enter 는 고르고, 그 Enter 가 **폼을 안 보낸다.**
    · 골랐다고 알린다 — 지난 회차 번호가 그 알림을 듣는다(`ir_numbers.js`).
    · 고른 사람은 검색어와 무관하게 남는다(딜 제안 관리와 같은 규칙).
    · 아무도 안 맞으면 빈 보기만 남는다 — `required` 가 막을 수 있어야 한다.
    · 폼 둘 다 붙는다. [미팅 잡기] 로 넣는 길이 걸러 둔 목록에 안 막힌다.

    로컬에서는 `node tests/js/ir_contact_search_test.js` 로도 돈다.
    """
    _run("ir_contact_search_test.js")


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_기업명_후보가_번호로_적는_길을_안_깨는가():
    """치는 줄에만 뜨는가, 그리고 **숫자 줄은 건드리지 않는가.**

    · 이름 가운데 글자로도 뜬다.
    · 숫자만 친 조각에는 **안 뜬다** — 그 줄은 지난 회차 번호로 읽는 줄이다.
    · 여러 줄 중 **지금 치는 줄만** 갈아 끼운다(`2, 샘` 의 `2, ` 는 그대로).
    · ↑↓·Enter 로 고른다. 짚어 둔 것이 없는 Enter 는 **줄바꿈**이다 —
      여러 개를 줄바꿈으로 적는 칸이라 Enter 를 뺏으면 안 된다.
    · `Esc` 는 목록만 닫고, 후보가 없으면 조용히 아무 일도 안 한다.
    · 후보 목록을 읽는 자리가 한 곳이다.

    로컬에서는 `node tests/js/ir_company_hint_test.js` 로도 돈다.
    """
    _run("ir_company_hint_test.js")
