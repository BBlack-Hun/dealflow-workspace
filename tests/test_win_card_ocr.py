"""Windows 카톡 `파일 전송` 카드를 **글자로 읽는 자리** (0.11.13) — 창 없이 그대로 시험한다.

실기(잡 82): 그 카드는 손으로 그린 창이라 UIA 로는 글자도 단추도 안 보였다. 그래서 카드
자리를 찍어 윈도우 내장 OCR(Windows.Media.Ocr, 한국어)로 읽는다 — PowerShell 5.1 이 부르는
`agent/sender/win_ocr.ps1`. 여기서는 그 결과를 읽어 판단하는 순수 함수들과, PowerShell 을
부르는 자리(가짜 `subprocess.run`)를 본다. 카드를 고르고 누르는 길은
`tests/test_win_file_confirm.py` 에 있다.
"""
from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from agent.sender import kakao_windows as kw
from tests.test_win_file_confirm import CARD_RECT, ocr_lines

ROOT = pathlib.Path(__file__).resolve().parent.parent
SIZE = (CARD_RECT[2] - CARD_RECT[0], CARD_RECT[3] - CARD_RECT[1])


def read(*rows, wide=("1개 전송", "확인")):
    card = kw.ocr_card(ocr_lines([(t, t in wide) for t in rows]))
    card.update(rect=CARD_RECT, size=SIZE)
    return card


# ══════════════════════════════════════════════════════════════════════════
#  OCR 줄 → 카드 모양
# ══════════════════════════════════════════════════════════════════════════

def test_ocr_lines_become_the_card_the_gate_reads():
    card = read("파일 전송", "시험자료.pdf", "149KB", "1개 전송")
    assert card["texts"] == ["파일전송", "시험자료.pdf", "149KB", "1개전송"]
    assert card["buttons"] == ["1개전송"]
    assert kw.check_file_card(card, ["시험자료.pdf"]) == (None, "")


def test_spacing_the_ocr_invents_is_ignored():
    """OCR 이 낱자마다 띄워 읽어도 본(`\\s*`)에 걸린다."""
    card = read("파 일 전 송", "1 개 전 송")
    assert card["buttons"] == ["1개전송"]
    assert kw.check_file_card(card, ["IR.pdf"])[0] is None


def test_the_refused_card_reads_its_reason():
    card = read("파일 전송", "전송 불가 1", "시험자료.pdf", "비어있는 파일", "확인")
    assert card["buttons"] == ["확인"]
    assert kw.unsendable_detail(card) == "시험자료.pdf · 비어있는파일"


def test_a_line_without_word_boxes_has_no_point():
    card = kw.ocr_card([{"text": "1개 전송", "words": []}])
    card.update(rect=CARD_RECT, size=SIZE)
    assert card["buttons"] == ["1개전송"]
    assert kw.card_point(card, kw.FILE_SEND_DEFAULTS["send_button_re"]) is None


# ══════════════════════════════════════════════════════════════════════════
#  누를 점 — 그림 속 글자 한가운데 + 카드 왼쪽 위
# ══════════════════════════════════════════════════════════════════════════

SEND = kw.FILE_SEND_DEFAULTS["send_button_re"]


def test_the_point_is_the_middle_of_the_word_box_on_screen():
    card = kw.ocr_card([{"text": "1개 전송", "words": [
        {"text": "1개", "x": 180, "y": 220, "w": 30, "h": 20},
        {"text": "전송", "x": 214, "y": 221, "w": 40, "h": 20}]}])
    card.update(rect=CARD_RECT, size=SIZE)
    assert kw.card_point(card, SEND) == (1000 + 217, 500 + 230)


def test_the_point_undoes_the_upscale_for_ocr():
    """OCR 앞에 그림을 키웠으면(`ocr_upscale`) 그림 속 자리를 그만큼 되돌려 셈한다."""
    card = kw.ocr_card([{"text": "1개 전송", "words": [
        {"text": "1개 전송", "x": 360, "y": 440, "w": 80, "h": 40}]}])
    card.update(rect=CARD_RECT, size=SIZE, scale=2)
    assert kw.card_point(card, SEND) == (1000 + 200, 500 + 230)


def test_no_point_when_the_picture_is_not_the_card_size():
    """찍은 그림 크기가 카드 자리와 다르면 배율 셈이 틀어진 것 — 누르지 않는다."""
    card = read("파일 전송", "1개 전송")
    card["size"] = (SIZE[0] * 2, SIZE[1] * 2)
    assert kw.card_point(card, SEND) is None


def test_no_point_for_two_matching_lines_or_none():
    assert kw.card_point(read("1개 전송", "1개 전송"), SEND) is None
    assert kw.card_point(read("파일 전송"), SEND) is None
    assert kw.card_point(read("1개 전송"), "") is None, "빈 본은 아무 줄에나 걸린다"


def test_no_point_outside_the_card():
    card = kw.ocr_card([{"text": "1개 전송", "words": [
        {"text": "1개 전송", "x": 500, "y": 10, "w": 40, "h": 20}]}])
    card.update(rect=CARD_RECT, size=SIZE)
    assert kw.card_point(card, SEND) is None


# ══════════════════════════════════════════════════════════════════════════
#  파일명 — OCR 이 흔히 어긋나는 것만 봐준다
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("seen", [
    "시험자료.pdf", "시험자료 .pdf", "시험자료.PDF", "시험 자료.pdf",
])
def test_a_name_read_with_spacing_or_case_matches(seen):
    assert kw.card_name_matches("시험자료.pdf", seen)


def test_underscores_the_ocr_drops_still_match():
    assert kw.card_name_matches("가나다_회사소개서_v2.pdf", "가나다 회사소개서v2.pdf")


@pytest.mark.parametrize("seen, ok", [
    ("가나다라마바사_회사…최종.pdf", True),
    ("가나다라마바사_회사...최종.pdf", True),
    ("가나다라마바사_회사…작년.pdf", False),     # 끝이 다르다
    ("다른회사_소개…최종.pdf", False),            # 처음이 다르다
    ("…", False),
])
def test_a_truncated_name_matches_on_its_ends(seen, ok):
    assert kw.card_name_matches("가나다라마바사_회사소개서_최종.pdf", seen) is ok


def test_a_different_name_does_not_match():
    assert not kw.card_name_matches("시험자료.pdf", "작년_내부자료.pdf")
    assert not kw.card_name_matches("", "")


def test_the_gate_refuses_a_different_file_read_by_ocr():
    card = read("파일 전송", "작년_내부자료.pdf", "149KB", "1개 전송")
    assert "다른 파일" in kw.check_file_card(card, ["시험자료.pdf"])[0]


# ══════════════════════════════════════════════════════════════════════════
#  PowerShell 로 윈도우 OCR 을 부르는 자리
# ══════════════════════════════════════════════════════════════════════════

class Run:
    """가짜 `subprocess.run` — `-Out` 자리에 PowerShell 스크립트가 남길 JSON 을 쓴다."""

    def __init__(self, result=None, *, raises=None, returncode=0, stderr=b""):
        self.result, self.raises = result, raises
        self.returncode, self.stderr = returncode, stderr
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.raises:
            raise self.raises
        if self.result is not None:
            out = cmd[cmd.index("-Out") + 1]
            pathlib.Path(out).write_text(json.dumps(self.result, ensure_ascii=False),
                                         encoding="utf-8")
        return subprocess.CompletedProcess(cmd, self.returncode, b"", self.stderr)


def test_it_runs_the_shipped_script_without_a_window(monkeypatch, tmp_path):
    lines = ocr_lines([("파일 전송", False), ("1개 전송", True)])
    run = Run({"ok": True, "lang": "ko", "lines": lines})
    monkeypatch.setattr(kw.subprocess, "run", run)

    png = tmp_path / "card.png"
    assert kw.windows_ocr(str(png), "ko", 5) == lines

    cmd, kwargs = run.calls[0]
    assert cmd[0] == "powershell.exe", "pwsh 7 은 WinRT 를 못 부른다 — Windows PowerShell 5.1"
    assert cmd[cmd.index("-ExecutionPolicy") + 1] == "Bypass"
    assert cmd[cmd.index("-File") + 1] == kw.OCR_SCRIPT
    assert cmd[cmd.index("-Image") + 1] == str(png)
    assert cmd[cmd.index("-Lang") + 1] == "ko"
    assert kwargs["timeout"] == 5 and "creationflags" in kwargs


def test_no_korean_recognizer_says_how_to_install_it(monkeypatch, tmp_path):
    monkeypatch.setattr(kw.subprocess, "run", Run(
        {"ok": False, "error": "no_recognizer", "lang": "ko", "available": ["en-US"]}))
    with pytest.raises(kw.OcrUnavailable) as err:
        kw.windows_ocr(str(tmp_path / "card.png"))
    assert "설정 > 언어에서 한국어 OCR 설치 필요" in str(err.value)
    assert "en-US" in str(err.value)


def test_powershell_that_cannot_run_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(kw.subprocess, "run", Run(raises=FileNotFoundError("powershell.exe")))
    with pytest.raises(kw.OcrUnavailable, match="PowerShell 을 돌리지 못했습니다"):
        kw.windows_ocr(str(tmp_path / "card.png"))

    monkeypatch.setattr(kw.subprocess, "run",
                        Run(raises=subprocess.TimeoutExpired("powershell.exe", 5)))
    with pytest.raises(kw.OcrUnavailable):
        kw.windows_ocr(str(tmp_path / "card.png"))


def test_a_blocked_script_leaves_no_result_and_is_unavailable(monkeypatch, tmp_path):
    """실행 정책(그룹 정책)에 막히면 결과 파일이 없다 — 그 까닭(stderr)을 싣는다."""
    png = tmp_path / "card.png"
    (tmp_path / "card.png.json").write_text('{"ok": true, "lines": []}')   # 지난번 것
    monkeypatch.setattr(kw.subprocess, "run", Run(returncode=1, stderr=b"running scripts is disabled"))
    with pytest.raises(kw.OcrUnavailable, match="running scripts is disabled"):
        kw.windows_ocr(str(png))


def test_a_failed_recognition_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(kw.subprocess, "run", Run({"ok": False, "error": "boom"}, returncode=1))
    with pytest.raises(kw.OcrUnavailable, match="boom"):
        kw.windows_ocr(str(tmp_path / "card.png"))


# ══════════════════════════════════════════════════════════════════════════
#  zip · 설치
# ══════════════════════════════════════════════════════════════════════════

def test_the_ocr_script_ships_in_the_windows_zip_only():
    from app.routers.setup import AGENT_FILES, OS_FILES

    entry = ("agent/sender/win_ocr.ps1", "agent/sender/win_ocr.ps1")
    assert entry in OS_FILES["windows"], "빠지면 PC 에서 카드를 못 읽어 파일이 하나도 안 나간다"
    assert entry not in OS_FILES["mac"] and entry not in AGENT_FILES
    assert pathlib.Path(kw.OCR_SCRIPT) == ROOT / entry[0]
    assert kw.OCR_SCRIPT.endswith(entry[1].split("/")[-1])


def test_the_ocr_script_is_ascii_only():
    """Windows PowerShell 5.1 은 BOM 없는 스크립트를 ANSI(CP949)로 읽는다 — 한글이 깨진다."""
    assert (ROOT / "agent" / "sender" / "win_ocr.ps1").read_bytes().isascii()


def test_pillow_is_installed_on_the_windows_pc():
    """파이썬 3.12+ 에서는 pyautogui 가 Pillow 를 끌어오지 않는다 — 0.11.12 까지 실패 화면이
    서버에 한 장도 안 올라간 까닭. 카드를 찍는 데도 쓴다."""
    reqs = (ROOT / "requirements-agent-windows.txt").read_text(encoding="utf-8")
    assert any(line.lower().startswith("pillow") for line in reqs.splitlines())
