"""KakaoDesktopSender — Windows-only Kakao PC automation (ROADMAP task 1.8, TECH_SPEC §5.2).

IMPORTANT — platform guard:
  pywinauto / pyperclip / pyautogui are imported LAZILY inside methods, and the
  module-level `is_supported()` gate + `create()` factory refuse to run off Windows.
  So importing this file on macOS/Docker never raises (imports are deferred), which
  keeps the web image build and MockSender path clean.

  ✅ 실기 검증 완료 (2026-08, Windows 11 + 카카오톡 PC): 실제 방으로 전송 성공.
  검증 과정에서 확인된 것:
    - set_focus() 만으로는 카톡이 앞으로 오지 않는다 → _force_foreground() 필요
    - 포커스 미확보 상태로 키를 누르면 브라우저 등 엉뚱한 창에 입력된다
      → 포커스 확인 전에는 절대 키 입력하지 않음

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

    # --- 포커스 ---
    def _foreground_title(self) -> str:
        """지금 실제로 키 입력을 받는 창의 제목."""
        try:
            import win32gui  # type: ignore

            return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or ""
        except Exception:  # noqa: BLE001
            return ""

    def _force_foreground(self, win) -> None:
        """Windows 의 포그라운드 전환 제한을 우회해 창을 실제로 앞으로 가져온다.

        Windows 는 백그라운드 프로세스가 임의로 창을 앞에 띄우지 못하게 막는다
        (SetForegroundWindow 제한). 그래서 pywinauto 의 set_focus() 만으로는
        실기에서 실패한다(실제로 '카톡이 앞으로 안 나옴' → focus_failed 발생).

        널리 쓰이는 두 가지 우회를 함께 적용한다:
          1) 최소화 상태면 복원(SW_RESTORE)
          2) 현재 포그라운드 스레드에 AttachThreadInput 으로 붙어 권한을 빌린 뒤
             BringWindowToTop + SetForegroundWindow
          3) ALT 키를 한 번 눌러 '사용자 입력이 있었다'는 조건을 만족시킴
        """
        try:
            import ctypes

            import win32api  # type: ignore
            import win32con  # type: ignore
            import win32gui  # type: ignore
            import win32process  # type: ignore
        except Exception:  # noqa: BLE001
            return  # pywin32 없으면 set_focus 폴백에 맡긴다

        try:
            hwnd = win.handle
        except Exception:  # noqa: BLE001
            return

        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            # ALT 탭 조건 충족용 (포그라운드 잠금 해제)
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

            fg = win32gui.GetForegroundWindow()
            fg_tid = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
            cur_tid = win32api.GetCurrentThreadId()

            attached = False
            if fg_tid and fg_tid != cur_tid:
                attached = bool(ctypes.windll.user32.AttachThreadInput(fg_tid, cur_tid, True))
            try:
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    ctypes.windll.user32.AttachThreadInput(fg_tid, cur_tid, False)
        except Exception as exc:  # noqa: BLE001
            log.debug("_force_foreground 실패(무시하고 set_focus 시도): %s", exc)

    def _focus_verified(self, win, expect_title: Optional[str] = None) -> bool:
        """창을 앞으로 올리고, **실제로 포그라운드가 됐는지 확인**한다.

        ★ 이 확인이 없으면 큰 사고가 난다. set_focus() 가 실패했는데 그대로
        Ctrl+F 를 누르면 그 키가 **그 순간 포커스를 가진 다른 앱**(예: 브라우저)으로
        가서 엉뚱한 곳에 방 이름이 입력된다(실기에서 실제로 발생).
        따라서 포커스가 확인되지 않으면 키 입력을 하지 않는다.
        """
        want = expect_title or self.sel.get("main_window_title_kw", "카카오톡")
        for attempt in range(int(self._t("focus_retries", 5))):
            try:
                win.set_focus()
            except Exception:  # noqa: BLE001
                log.debug("set_focus 실패, 재시도")
            # set_focus 만으로는 Windows 포그라운드 제한에 막히므로 강제 전환도 함께 시도.
            self._force_foreground(win)
            time.sleep(self._t("after_focus", 0.4))
            fg = self._foreground_title()
            if fg and (fg == want or want in fg):
                return True
            log.warning("포커스 미확보: 현재 포그라운드=%r, 기대=%r", fg, want)
        return False

    def verify_room(self, room_name: str) -> str:
        """Search only; count EXACT-title matches. 1=verified, 0=not_found, >=2=ambiguous.

        TODO(win): confirm search-result list control path in selectors.yaml on real Kakao.
        """
        try:
            win = self._kakao_window()
            if not self._focus_verified(win):
                log.warning("verify_room: 카톡 포커스 실패")
                return "not_found"
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
            # ★ 포커스가 확인되지 않으면 키 입력을 하지 않는다.
            #   (브라우저 등 다른 앱에 방 이름이 입력되는 사고 방지)
            if not self._focus_verified(win):
                return self._fail(
                    room_name,
                    "focus_failed: 카카오톡 창을 앞으로 가져오지 못했습니다(전송 안 함). "
                    "카톡을 최소화하지 말고 화면에 띄워두세요. "
                    "발송 중에는 다른 창을 클릭하지 마세요.",
                )

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
