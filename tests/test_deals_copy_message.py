"""미리보기 문구를 **복사할 수 있는가.**

자료 전달은 앱이 보내 주지 않는다 — 사람이 PC 카톡에 자료를 손으로 붙이고
문구도 손으로 보낸다. 그러면 화면에 그린 문구를 집어갈 수 있어야 한다.

규칙은 브라우저에 있으므로 검사도 브라우저에서 돈다
(`tests/js/deals_copy_message_test.js` — deals.js 를 **그대로 실행**한다).
여기서는 그 검사를 CI 가 잊지 않도록 감싸고, 파이썬으로만 볼 수 있는 것
(무엇을 담느냐)을 따로 못박는다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_미리보기_문구를_지금_보고_있는_담당자_것으로_복사한다():
    """★ 담기는 것이 나갈 문구 그대로인지 · 탭을 따르는지 · 클립보드가 없어도 되는지."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 미설치 — 브라우저 로직 테스트 생략 "
                    "(호스트에서 `node tests/js/deals_copy_message_test.js`)")
    js = Path(__file__).resolve().parent / "js" / "deals_copy_message_test.js"
    result = subprocess.run([node, str(js)], capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_복사하는_것은_고칠_수_있는_그_칸의_값이다():
    """★ 담는 자리가 **실제로 나갈 문구**여야 한다.

    화면은 문구 위에 머리말을 얹고("가담당 심사역 · 💬 방이름 · 재연락"),
    여러 통으로 나갈 때는 안내도 붙인다. 그것까지 담으면 카톡에 그대로 붙는다.

    나가는 문구는 `#bubble-edit` 의 값이다 — 고친 것이 그대로 서버로 간다
    (`editedOverrides`). 그래서 복사도 같은 칸을 봐야 한다.

    복사하는 손 자체는 **공용 한 벌**이다(`ir_attach_list.js`) — IR 진행 관리의
    [자료 보내기] 창이 같은 단추를 단다.
    """
    js = (ROOT / "app" / "static" / "js" / "deals.js").read_text(encoding="utf-8")
    shared = (ROOT / "app" / "static" / "js" / "ir_attach_list.js").read_text(
        encoding="utf-8")

    assert "copyMessage(ta, copyBtn)" in js, "복사가 문구 칸을 안 본다"
    assert "IrAttach.copyText" in js, "복사를 공용 한 벌로 안 넘긴다 — 두 벌이 된다"
    assert "navigator.clipboard.writeText(ta.value)" in shared, \
        "복사하는 것이 문구 칸의 값이 아니다 — 화면 장식이 섞인다"
    # 미리보기 칸(`previewArea.innerHTML`)을 통째로 담으면 머리말까지 딸려 간다.
    assert "previewArea.innerHTML" not in js.split("function copyMessage")[1] \
        .split("function renderPreview")[0], "화면에 그린 것을 통째로 담는다"


def test_복사_단추는_저장소에_이미_있는_방식을_따른다():
    """복사 단추가 두 방식으로 갈리면, 한쪽만 고쳐진 채 남는다.

    이미 있는 것은 `llm_brief.js` 다 — 클립보드가 없거나 거절하면 **골라 두고
    그렇게 말해 준다**. 조용히 실패하면 복사된 줄 알고 빈 것을 붙여 넣는다.

    발송 화면 쪽 복사는 `ir_attach_list.js` 한 벌이고, 딜 제안 관리와 IR 진행
    관리의 [자료 보내기] 창이 그것을 같이 쓴다.
    """
    js = (ROOT / "app" / "static" / "js" / "ir_attach_list.js").read_text(encoding="utf-8")
    brief = (ROOT / "app" / "static" / "js" / "llm_brief.js").read_text(encoding="utf-8")

    for src, who in ((js, "ir_attach_list.js"), (brief, "llm_brief.js")):
        # 있는지 보고 부른다 — https·localhost 가 아니면 물건 자체가 없다.
        assert "navigator.clipboard" in src, f"{who}: 클립보드를 안 쓴다"
        assert "navigator.clipboard.writeText(" in src, f"{who}: 담는 자리가 없다"
        assert "Ctrl/⌘+C" in src, f"{who}: 손으로 복사하라는 말이 없다"
    # 클립보드가 아예 없는 곳(https·localhost 가 아닌 화면)에서도 한 번 더 해 본다.
    assert 'document.execCommand("copy")' in js, \
        "클립보드가 없는 화면에서 복사를 아예 안 해 본다"
