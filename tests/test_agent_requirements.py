"""발송기 의존성 — **팀원 PC 의 파이썬 판에 따라 깨지지 않는가.**

이 두 파일은 서버가 아니라 팀원 PC 에 깔린다. 그 PC 의 파이썬은 python.org
에서 그날 받은 최신 판이라 우리가 고르지 못한다. 판을 `==` 로 박으면 새
파이썬이 나온 날 설치가 통째로 멈춘다 — 2026-10 에 `pywin32==308` 로 실제로
그랬다(새 파이썬용 설치본은 311 부터만 있었다).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _reqs(name: str):
    out = []
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


@pytest.mark.parametrize("name", ["requirements-agent-windows.txt",
                                  "requirements-agent-mac.txt"])
def test_발송기_의존성은_판을_박지_않는다(name):
    pinned = [r for r in _reqs(name) if re.search(r"==", r)]
    assert not pinned, (
        f"{name} 에 `==` 로 박힌 판이 있습니다: {pinned}\n"
        "팀원 PC 의 새 파이썬에서 설치가 멈춥니다 — `>=` 바닥값으로 적으세요.")


def test_윈도우_발송기에_필요한_것이_다_있다():
    names = {re.split(r"[<>=!~ ]", r, 1)[0].lower() for r in
             _reqs("requirements-agent-windows.txt")}
    for need in ("pywinauto", "pywin32", "pyperclip", "pyautogui",
                 "requests", "pyyaml"):
        assert need in names, f"{need} 가 빠졌습니다"


def test_설치_창이_파이썬_판을_보여_준다():
    """설치가 실패하면 대개 판 탓이다. 찍어 보낸 화면에서 판을 읽을 수 있어야 한다."""
    bat = (ROOT / "packaging" / "windows" / "setup.bat").read_text(encoding="utf-8")
    assert "python --version" in bat
