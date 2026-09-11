"""메일 칸의 도메인 후보(JS)를 node 로 돌려 본다.

로직이 브라우저에 있으므로 테스트도 같은 언어로 둔다(tests/test_filters_js.py 와
같은 방식). node 가 없는 환경(운영 도커 이미지)에서는 건너뛴다 — 브라우저 자산
테스트라 서버 실행에 필요한 의존성이 아니다.

서버 쪽(무엇을 세고 어디를 자르나 · 화면이 그것을 어떻게 싣나)은
`tests/test_email_domains.py` 가 본다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HINT_TEST = Path(__file__).resolve().parent / "js" / "email_domain_hint_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치 — 브라우저 로직 테스트 생략")
def test_메일_칸의_도메인_후보가_저장_흐름을_안_깨는가():
    """`이름@` 까지 치면 뜨고, **고르기 전에 저장되거나 창이 닫히지 않는가.**

    이 기능은 저장 흐름 **위에 얹히는** 물건이다. 이 저장소의 표 편집은 칸
    안 입력이 `blur` 될 때 저장되는 자리가 있어서, 후보 목록을 편집창 바깥에
    띄우면 그것을 누르는 순간 "바깥을 눌렀다" 로 읽혀 **고르기도 전에 저장되고
    창이 닫힌다** — #152 가 `.cell-pop` 여백에서 고친 것과 같은 함정이다.

    그래서 여기서 잠그는 것은 뜨느냐만이 아니다.

    · `이름@` 까지 쳤을 때 도메인 후보가 뜨는가(`<datalist>` 로는 안 되는 자리).
    · 고르면 `이름@도메인` 이 되고 **`@` 앞이 한 글자도 안 바뀌는가.**
    · 후보를 누르거나 목록을 눌렀을 때 **저장이 안 나가고 창이 안 닫히는가.**
    · 짚어 둔 것이 없는 Enter 가 첫 줄을 대신 고르지 않는가 — 고르면 사람이
      친 것과 저장된 것이 달라져, 후보에 없는 도메인을 치는 길이 막힌다.
    · `Esc` 가 목록만 닫는가(한 번 더 눌러야 창이 닫힌다).
    · ↑↓·Enter 로 고를 수 있는가 — 마우스만 되면 타이핑 중에 손이 뜬다.
    · 도메인 목록을 읽는 자리가 **한 곳**인가.
    · 표에서 고치는 길과 수정창에서 고치는 길이 **같은 부품**을 쓰는가.
    · 메일이 하나도 없는(또는 후보 칸이 아예 없는) 화면에서 안 깨지는가.

    로컬에서는 `node tests/js/email_domain_hint_test.js` 로도 돈다.
    """
    result = subprocess.run(
        [shutil.which("node"), str(HINT_TEST)], capture_output=True, text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
