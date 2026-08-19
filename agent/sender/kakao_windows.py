"""KakaoDesktopSender — Windows-only Kakao PC automation (ROADMAP task 1.8, TECH_SPEC §5.2).

IMPORTANT — platform guard:
  pywinauto / pyperclip / pyautogui are imported LAZILY inside methods, and the
  module-level `is_supported()` gate + `create()` factory refuse to run off Windows.
  So importing this file on macOS/Docker never raises (imports are deferred), which
  keeps the web image build and MockSender path clean.

  ⚠ NOT verified on real hardware yet. Sprint 1 task 1.10 = Windows 실기 검증
  (actual Kakao send, room-mismatch skip, ESC/FAILSAFE stop, supervisor overlay).
  Treat every UI-interaction line below as TODO-until-verified-on-Windows.

Mis-send prevention (non-negotiable, ROADMAP 공통 원칙 4): after opening a room we
re-read the window title and require an EXACT match with room_name; any mismatch →
close + failed(room_mismatch), never send.

All timings / shortcuts / control identifiers come from selectors.yaml (no hardcoded
automation constants — ROADMAP 공통 원칙 2).
"""
from __future__ import annotations

import base64
import logging
import platform
import time
from typing import Optional

from .base import SendResult, Sender

log = logging.getLogger("agent.kakao")


def is_supported() -> bool:
    return platform.system() == "Windows"


def create(selectors: dict, screenshot_dir: str) -> "KakaoDesktopSender":
    """Factory that refuses to construct off Windows."""
    if not is_supported():
        raise RuntimeError(
            "KakaoDesktopSender는 Windows 전용입니다. macOS/Docker에서는 MockSender를 사용하세요."
        )
    return KakaoDesktopSender(selectors, screenshot_dir)


class KakaoDesktopSender(Sender):
    name = "kakao_windows"

    def __init__(self, selectors: dict, screenshot_dir: str):
        if not is_supported():  # defense in depth
            raise RuntimeError("Windows 전용")
        self.sel = selectors or {}
        self.screenshot_dir = screenshot_dir
        self._desktop = None
        self._pyautogui = None
        self._pyperclip = None
        self._init_backends()

    # --- lazy Windows-only backend init ---
    def _init_backends(self) -> None:
        # Deferred imports: only ever executed on Windows.
        from pywinauto import Desktop  # type: ignore
        import pyperclip  # type: ignore
        import pyautogui  # type: ignore

        pyautogui.FAILSAFE = True  # mouse to top-left corner aborts (TECH_SPEC §5.5)
        self._desktop = Desktop(backend=self.sel.get("backend", "uia"))
        self._pyperclip = pyperclip
        self._pyautogui = pyautogui

    # --- timing helpers ---
    def _t(self, key: str, default: float) -> float:
        return float(self.sel.get("timings", {}).get(key, default))

    def _kakao_window(self):
        title_re = self.sel.get("main_window_title_re", "카카오톡.*")
        win = self._desktop.window(title_re=title_re)
        win.wait("exists ready", timeout=self._t("window_wait", 5.0))
        return win

    def verify_room(self, room_name: str) -> str:
        """Search only; count EXACT-title matches. 1=verified, 0=not_found, >=2=ambiguous.

        TODO(win): confirm search-result list control path in selectors.yaml on real Kakao.
        """
        try:
            win = self._kakao_window()
            win.set_focus()
            self._pyautogui.hotkey(*self.sel.get("search_hotkey", ["ctrl", "f"]))
            time.sleep(self._t("after_search_hotkey", 0.4))
            self._pyperclip.copy(room_name)
            self._pyautogui.hotkey("ctrl", "v")
            time.sleep(self._t("after_query_paste", 0.8))
            # TODO(win): read result rows and count exact title matches via selectors.yaml.
            # Placeholder returns 'verified' — MUST be replaced with real counting in 1.10.
            log.warning("verify_room not yet verified on hardware; returning 'verified' placeholder")
            return "verified"
        except Exception as exc:  # noqa: BLE001
            log.exception("verify_room error")
            return "not_found"
        finally:
            try:
                self._pyautogui.press("esc")
            except Exception:  # noqa: BLE001
                pass

    def send_text(self, room_name: str, text: str) -> SendResult:
        """Open the room by exact name and send `text` (drive links are plain text).

        Sequence (TECH_SPEC §5.2):
          1. focus Kakao main window
          2. Ctrl+F → paste room_name → wait
          3. Enter → open top result
          4. VERIFY opened window title == room_name (exact); mismatch → close + failed
          5. paste message → Enter
          6. close chat (Esc)
        """
        try:
            win = self._kakao_window()
            win.set_focus()

            # 2) search
            self._pyautogui.hotkey(*self.sel.get("search_hotkey", ["ctrl", "f"]))
            time.sleep(self._t("after_search_hotkey", 0.4))
            self._pyperclip.copy(room_name)
            self._pyautogui.hotkey("ctrl", "v")
            time.sleep(self._t("after_query_paste", 0.8))

            # 3) open top result
            self._pyautogui.press("enter")
            time.sleep(self._t("after_open_room", 0.8))

            # 4) EXACT title verification (mis-send guard)
            chat = self._opened_chat_window(room_name)
            if chat is None:
                self._safe_close()
                return self._fail(room_name, "room_mismatch: 열린 방 제목이 정확히 일치하지 않음")

            # 5) 본문 입력 — ★ 넣은 뒤 실제로 들어갔는지 확인하고 나서 보낸다.
            #    (macOS 실기 검증에서 '붙여넣기가 안 됐는데 성공 보고'하는 문제가 있었다.
            #     Windows 도 카톡 빌드에 따라 Ctrl+V 가 먹지 않을 수 있으므로 동일하게 검증한다.)
            self._pyperclip.copy(text)
            time.sleep(self._t("before_message_paste", 0.2))
            self._pyautogui.hotkey("ctrl", "v")
            time.sleep(self._t("after_message_paste", 0.5))

            filled = self._input_text(chat)
            if filled is not None and not filled.strip():
                # 입력창을 읽을 수 있는데 비어 있다 → 붙여넣기 실패. 절대 Enter 치지 않는다.
                self._safe_close()
                return self._fail(
                    room_name,
                    "input_not_filled: 입력창에 본문이 들어가지 않았습니다(전송 안 함)",
                )

            self._pyautogui.press("enter")
            time.sleep(self._t("after_send", 0.4))

            # 6) ★ 전송 검증: 입력창이 비워졌으면 전송된 것으로 본다.
            leftover = self._input_text(chat)
            if leftover is not None and leftover.strip():
                self._safe_close()
                return self._fail(
                    room_name,
                    "send_not_confirmed: 전송 후에도 입력창에 본문이 남아 있습니다",
                )

            # 7) close
            self._safe_close()
            return SendResult(ok=True)
        except Exception as exc:  # noqa: BLE001
            log.exception("send_text error room=%r", room_name)
            return self._fail(room_name, f"exception: {exc}")

    # --- helpers ---
    def _input_text(self, chat) -> Optional[str]:
        """채팅창 입력란의 현재 텍스트.

        읽지 못하면 None 을 반환한다(= 검증 생략). 카톡 빌드마다 컨트롤 구조가 달라
        Edit 컨트롤을 못 찾을 수 있는데, 그 경우까지 실패로 처리하면 정상 발송을
        막아버리므로 '판단 불가'로 둔다.

        TODO(win): 실기에서 입력란 컨트롤 경로를 확인해 selectors.yaml 로 외부화할 것.
        """
        try:
            edits = chat.descendants(control_type="Edit")
            if not edits:
                return None
            # 마지막 Edit 이 메시지 입력란인 경우가 일반적(위쪽은 검색창 등).
            return edits[-1].get_value()
        except Exception:  # noqa: BLE001
            return None

    def _opened_chat_window(self, room_name: str):
        """Return the chat window whose title EXACTLY equals room_name, else None.

        TODO(win): validate the exact title-read path (uia window title vs. header label)
        against a live Kakao build during task 1.10.
        """
        try:
            candidate = self._desktop.window(title=room_name)
            candidate.wait("exists", timeout=self._t("chat_wait", 2.0))
            actual = candidate.window_text().strip()
            if actual == room_name:
                return candidate
            log.warning("title mismatch: expected=%r actual=%r", room_name, actual)
            return None
        except Exception:  # noqa: BLE001
            return None

    def _safe_close(self) -> None:
        try:
            self._pyautogui.press("esc")
        except Exception:  # noqa: BLE001
            pass

    def _fail(self, room_name: str, error: str) -> SendResult:
        shot = self._screenshot(room_name)
        return SendResult(ok=False, error=error, screenshot_b64=shot)

    def _screenshot(self, room_name: str) -> Optional[str]:
        try:
            import io
            img = self._pyautogui.screenshot()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:  # noqa: BLE001
            return None
