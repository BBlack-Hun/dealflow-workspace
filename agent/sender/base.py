"""Sender interface — the single seam that isolates the platform gap (TECH_SPEC §3).

Windows-only imports (pywinauto) live ONLY inside kakao_windows.py, so macOS/Docker
never import them. The agent picks a concrete Sender at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SendResult:
    ok: bool
    error: Optional[str] = None
    screenshot_b64: Optional[str] = None


class Sender:
    """Abstract sender. Implementations must be safe against mis-send:
    verify_room / send_text must FAIL (never guess) on an inexact room match."""

    name = "base"

    def verify_room(self, room_name: str) -> str:
        """Return 'verified' | 'not_found' | 'ambiguous'. (Used by Sprint 2 [방 연결 확인].)"""
        raise NotImplementedError

    def send_text(self, room_name: str, text: str) -> SendResult:
        """Send `text` to the chat room whose title EXACTLY equals `room_name`."""
        raise NotImplementedError

    def close(self) -> None:
        pass
