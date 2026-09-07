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

──────────────────────────────────────────────────────────────────────────────
파일 첨부 (`send_file`) — ⚠ **실기 확인 전이다**
──────────────────────────────────────────────────────────────────────────────

글자는 클립보드 + Ctrl+V 로 넣는 길이 실기에서 확인됐다. 파일도 같은 길로 간다
(`CF_HDROP` — 탐색기에서 파일을 복사해 붙이는 것과 같은 형식). mac 은 이 길이
아예 막혀서 `파일전송 ⌘O` 단추로 돌아갔지만 Windows 는 다를 것이다.

**다를 것이라는 것까지가 아는 것이고, 확인 창이 어떻게 생겼는지는 모른다.**
그래서 이렇게 만들었다:

  ① 이름 빗장 → ② 방 열고 제목 정확 일치 → ③ 클립보드에 담고 **다시 읽어 견줌**
  → ④ Ctrl+V → ⑤ ★ **확인 창 관문**(방·파일명·개수) → ⑥ 보내기

⑤ 에서 하나라도 어긋나면 취소하고 아무것도 보내지 않는다. **확인 창을 못 찾는
것도 실패다** — 못 찾았으니 그냥 보내는 길은 만들지 않았다. 모르면 안 보낸다.

그래서 실기 확인 전에 켜지면 **잘못 보내는 대신 안 보내고 실패로 남는다.**
그것이 맞는 실패다. 확인 창을 읽는 자리(`_confirm_snapshot`)와 그 모양을 적어
둔 값(`selectors.yaml: file_send`)은 전부 **추측**이고 그렇게 표시해 두었다.
관문 판단 자체(`check_confirm_window`)는 창과 떨어진 순수 함수라 이 기계에서
그대로 시험한다.

`can_send_files` 는 **기본이 꺼짐**이다 — 확인 전에 서버가 파일 잡을 내주면
그 회차의 자료 전달이 통째로 실패한다(문구까지 안 나간다). 팀 PC 에서 확인할
때만 `DEALFLOW_WIN_FILE_SEND=1` 로 켜고, 확인이 끝나면 `selectors.yaml` 의
`file_send.verified` 를 참으로 바꿔 저장소에 못박는다.
"""
from __future__ import annotations

import base64
import logging
import os
import platform
import re
import time
from typing import List, Optional

from . import win_clipboard
from .base import (FILE_SEND_UNSUPPORTED, IrPathError, SendResult, Sender, nfc,
                   resolve_ir_file, same_file_name)

log = logging.getLogger("agent.kakao")

# ── 확인 창의 모양 — ⚠ 전부 **추측**이다 ───────────────────────────────────
#
# mac 에서는 이 자리가 실기로 확인된 값이었다(`파일 전송` 시트, `1개 전송` 단추).
# Windows 카톡은 아무도 못 봤다. 그래서 아래는 "이렇게 생겼을 것" 이고,
# **틀리면 관문이 막아서 안 보낸다**(잘못 보내지 않는다).
#
# 실기에서 확인한 뒤 `selectors.yaml: file_send` 를 고친다 — 코드를 고치지
# 않는다(ROADMAP 공통 원칙 2).
FILE_SEND_DEFAULTS = {
    # 확인 창의 제목. mac 은 `파일 전송` 이었다.
    "confirm_title_re": r"파일\s*전송|전송\s*확인",
    # 취소 단추. 이것이 없으면 확인 창으로 보지 않는다.
    "cancel_button_re": r"^(취소|아니오|Cancel)(\(.\))?$",
    # 보내기 단추. mac 처럼 개수가 박혀 나오면(`1개 전송`) 그 숫자도 함께 읽는다.
    "send_button_re": r"^((\d+)\s*개\s*)?(전송|보내기|확인|Send|OK)(\(.\))?$",
    # 창 안의 글자에서 개수를 읽어 내는 본. (`파일 2개를 전송하시겠습니까?`)
    "count_re": r"(\d+)\s*개",
    "paste_hotkey": ["ctrl", "v"],
    # 실기에서 확인한 뒤 참으로 바꾼다. 그 전에는 `send_file` 이 거절한다.
    "verified": False,
}

#: 실기 확인 전에도 **한 번만** 켜 볼 수 있는 자리. 팀 PC 에서 셋팅할 때 쓴다.
#: 창 하나에만 사는 값이라 다음에 켜면 다시 꺼져 있다 — 그것이 맞다.
FILE_SEND_ENV = "DEALFLOW_WIN_FILE_SEND"


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
        # IR 자료 폴더 자리. **서버가 박동 응답에 실어 준다**
        # (`agent/main.py: apply_server_settings`) — config 에 적지 않는다.
        self.ir_root_setting = ""
        # ★ 파일을 붙일 줄 안다고 밝히는가. 클래스 기본값은 **아니오**이고
        #   (`Sender.can_send_files`), 켜졌을 때만 이 줄이 덮어쓴다.
        #   밝히지 않으면 서버가 파일이 실린 잡을 아예 안 준다.
        self.can_send_files = file_send_enabled(self.sel)
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

    def _open_room_verified(self, room_name: str):
        """방을 찾아 열고 **창 제목이 정확히 일치하는지** 확인한다.

        ★ `send_text` 와 `send_file` 이 **같은 이 자리**를 쓴다. 파일 쪽에 새 길을
          내면 한쪽만 고쳐질 때 오발송 방지가 갈라진다 — 실제로 위험한 것은 그
          갈라짐이다(문구는 막고 파일은 안 막는 상태).

        Sequence (TECH_SPEC §5.2):
          1. focus Kakao main window
          2. Ctrl+F → paste room_name → wait
          3. Enter → open top result
          4. VERIFY opened window title == room_name (exact); mismatch → close + failed

        돌려주는 값: `(채팅창, 실패)`. 실패가 None 이 아니면 **그대로 돌려주고
        끝낸다** — 그 뒤로는 아무 키도 누르지 않는다.
        """
        win = self._kakao_window()
        # ★ 포커스가 확인되지 않으면 키 입력을 하지 않는다.
        #   (브라우저 등 다른 앱에 방 이름이 입력되는 사고 방지)
        if not self._focus_verified(win):
            return None, self._fail(
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
            return None, self._fail(
                room_name, "room_mismatch: 열린 방 제목이 정확히 일치하지 않음")
        return chat, None

    def send_text(self, room_name: str, text: str) -> SendResult:
        """Open the room by exact name and send `text` (drive links are plain text).

        방을 열고 제목을 확인하는 자리는 `_open_room_verified` 하나다
        (`send_file` 과 같은 자리). 여기서는 그 뒤 — 붙여넣기 → Enter → 닫기.
        """
        try:
            chat, bad = self._open_room_verified(room_name)
            if bad is not None:
                return bad

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

    # ══════════════════════════════════════════════════════════════════════
    #  파일 첨부 — ⚠ 실기 확인 전. **관문을 통과하지 못하면 무조건 취소한다.**
    # ══════════════════════════════════════════════════════════════════════

    def send_file(self, room_name: str, file_names) -> SendResult:
        """IR 자료를 첨부해 보낸다. **관문을 통과할 때만 보낸다.**

        `file_names` 는 **공통 폴더 안의 파일명**이다(경로가 아니다). 실제 자리는
        이 PC 가 설정한 뿌리로 조립한다 — mac 과 **같은 빗장**을 쓴다
        (`agent/sender/base.py: resolve_ir_file`). 규칙에 어긋나는 이름이나 이
        PC 에 없는 파일은 **카톡을 건드리기 전에** 거절한다.

        **한 번에 한 파일씩** 보낸다. 클립보드에는 여러 개를 한꺼번에 담을 수
        있지만(`CF_HDROP` 는 목록이다) 그러면 확인 창에 여러 개가 뜨고, 카톡이
        차례를 지키는지 묶어 버리는지를 모른다. 파일 차례는 **투자사가 기억하는
        번호의 차례**라(딜 소개에서 붙인 번호) 뒤집히면 문구와 어긋난다. 한 개씩
        보내면 차례가 확실하고, 확인 창의 개수는 **항상 1** 이라 관문이 제일
        빡빡해진다 — 하나라도 더 붙어 있으면 그 자리에서 걸린다.

        여러 개를 보내다 중간에 실패하면 **거기서 멈춘다.** 몇 개가 이미 나갔는지
        실패 문구에 적는다 — 다시 보내면 그만큼 겹친다는 것을 사람이 알아야 한다.
        """
        # ★ 켜지 않았으면 여기서 끝. 실기 확인 전에는 이 길이 기본이다.
        #   (`can_send_files` 와 **같은 사실**을 말한다 — 어긋나면 시험이 잡는다)
        if not self.can_send_files:
            log.warning("[kakao_windows] 파일 전송 요청을 거절합니다 room=%r files=%r",
                        room_name, list(file_names or []))
            return SendResult(
                ok=False,
                error=f"{FILE_SEND_UNSUPPORTED}: Windows 발송기의 파일 전송은 "
                      f"아직 켜지 않았습니다 (실기 확인 전 — 자료는 PC 에서 직접 "
                      f"첨부하세요). 확인할 때만 {FILE_SEND_ENV}=1 로 켭니다",
            )

        if not room_name or not room_name.strip():
            return SendResult(ok=False, error="room_name empty")

        wanted = [str(f) for f in (file_names or [])]
        if not wanted:
            return SendResult(ok=False, error="no_files: 보낼 파일이 없습니다")

        # ① 이름을 걸러 내고 이 PC 의 실제 경로로 조립한다.
        #    **카톡을 건드리기 전에** 한다. 반쯤 보내 놓고 막히면 되돌릴 수 없다.
        try:
            resolved = [resolve_ir_file(n, self.ir_root_setting) for n in wanted]
        except IrPathError as exc:
            return SendResult(ok=False, error=f"ir_file_rejected: {exc}")

        try:
            # ② 방 열기 + 창 제목 정확 일치 (send_text 와 **같은 자리**)
            chat, bad = self._open_room_verified(room_name)
            if bad is not None:
                return bad

            for n, path in enumerate(resolved, start=1):
                result = self._send_one_file(room_name, chat, path)
                if not result.ok:
                    if n > 1:
                        result.error = (f"{n - 1}개를 보낸 뒤 {n}번째에서 실패 "
                                        f"— {result.error}")
                    return result

            self._safe_close()
            log.info("[kakao_windows] SENT FILES room=%r files=%s",
                     room_name, [p.name for p in resolved])
            return SendResult(ok=True)
        except Exception as exc:  # noqa: BLE001
            log.exception("send_file error room=%r", room_name)
            return self._fail(room_name, f"exception: {exc}")

    def _send_one_file(self, room_name: str, chat, path) -> SendResult:
        """파일 하나. 확인 창이 어긋나면 **취소하고 아무것도 보내지 않는다.**"""
        # ③ 클립보드에 담고 **다시 읽어 견준다.**
        #    담긴 줄 알았는데 안 담긴 채로 Ctrl+V 를 누르면 **직전에 복사해 둔
        #    것**(바로 앞 건의 문구일 수도 있다)이 그대로 나간다.
        try:
            self._clipboard_put([str(path)])
            placed = self._clipboard_read()
        except Exception as exc:  # noqa: BLE001
            return self._fail(room_name,
                              f"clipboard_failed: 클립보드에 파일을 담지 못했습니다: "
                              f"{exc} (전송 안 함)")
        if not _same_paths(placed, [str(path)]):
            return self._fail(room_name,
                              f"clipboard_mismatch: 클립보드에 담긴 것이 보내려던 "
                              f"것과 다릅니다 {placed!r} (전송 안 함)")

        # ④ 붙여넣기
        self._paste_into_chat(chat)

        # ⑤ ★ 관문. 확인 창을 찾는다 — **못 찾는 것도 실패다.**
        snapshot = self._wait_confirm(room_name)
        if not _is_confirm_window(snapshot, self.file_send_conf):
            # 붙여넣기가 입력창에 첨부로 얹혔을 수 있다. 남겨 두면 **다음 문구와
            # 함께 나간다** — Esc 로 털고 실패로 남긴다.
            self._dismiss_confirm(room_name)
            return self._fail(
                room_name,
                "confirm_window_not_shown: 파일 전송 확인 창을 찾지 못했습니다 "
                "(전송 안 함). 확인 창을 못 찾으면 보내지 않습니다")

        reason = check_confirm_window(snapshot, room_name, [path.name],
                                      self.file_send_conf)
        if reason:
            log.warning("확인 창이 어긋났습니다 — 취소합니다: %s | snapshot=%r",
                        reason, snapshot)
            self._dismiss_confirm(room_name)
            return self._fail(room_name,
                              f"gate_blocked: {reason} — 취소했습니다 (전송 안 함)")

        # ⑥ 보내기 단추
        button = _send_button(snapshot, self.file_send_conf)[0]
        if not self._click_dialog_button(room_name, button):
            self._dismiss_confirm(room_name)
            return self._fail(room_name,
                              f"send_button_not_clicked: {button!r} 단추를 누르지 "
                              f"못했습니다 (전송 안 함)")
        time.sleep(self._t("after_confirm_click", 1.0))

        # ⑦ 확인 창이 닫혔나. 여기까지가 사후 확인의 한계다 — 보낸 뒤 파일 메시지
        #    줄에서 파일명을 읽는 길은 mac 에서도 없었고 Windows 는 더 모른다.
        if _is_confirm_window(self._confirm_snapshot(room_name), self.file_send_conf):
            return self._fail(
                room_name,
                f"send_unconfirmed: {button!r} 을 눌렀지만 확인 창이 그대로입니다. "
                f"카톡을 직접 확인하세요 — 다시 보내면 겹칠 수 있습니다")
        return SendResult(ok=True)

    # --- 파일 첨부에 쓰는 자리들 (시험에서 갈아 끼우는 이음매) ---------------

    @property
    def file_send_conf(self) -> dict:
        """확인 창의 모양. 추측값 위에 `selectors.yaml: file_send` 를 덮는다."""
        conf = dict(FILE_SEND_DEFAULTS)
        conf.update(self.sel.get("file_send") or {})
        return conf

    def _clipboard_put(self, paths: List[str]) -> None:
        win_clipboard.set_files(paths)

    def _clipboard_read(self) -> Optional[List[str]]:
        return win_clipboard.get_files()

    def _paste_into_chat(self, chat) -> None:
        hotkey = self.file_send_conf.get("paste_hotkey") or ["ctrl", "v"]
        self._pyautogui.hotkey(*hotkey)
        time.sleep(self._t("after_file_paste", 1.0))

    def _wait_confirm(self, room_name: str) -> dict:
        """확인 창이 뜨기를 기다린다. 안 뜨면 마지막으로 본 것을 그대로 돌려준다.

        **없는 것을 있는 것으로 만들지 않는다** — 부르는 쪽이 그것을 보고 멈춘다.
        """
        deadline = time.monotonic() + self._t("confirm_wait", 5.0)
        snapshot = self._confirm_snapshot(room_name)
        while not _is_confirm_window(snapshot, self.file_send_conf):
            if time.monotonic() >= deadline:
                break
            time.sleep(0.2)
            snapshot = self._confirm_snapshot(room_name)
        return snapshot

    def _confirm_snapshot(self, room_name: str) -> dict:
        """지금 떠 있는 파일 전송 확인 창을 읽는다.

        ⚠⚠ **이 함수 전체가 추측이다.** Windows 카톡의 확인 창을 아무도 못 봤다.
          창이 뜨는지, 제목이 무엇인지, 파일명이 어디에 적히는지, 개수가 어떻게
          나오는지 — 전부 팀 PC 에서 확인할 목록에 올려 두었다
          (`docs/WINDOWS_TEST.md`).

        읽지 못하면 `present=False` 를 돌려준다. 그러면 부르는 쪽이 **안 보낸다.**
        되는 척하는 값을 지어내지 않는다.

        돌려주는 모양(mac 의 `_sheet_snapshot` 과 같은 결):
            present      확인 창을 찾았는가
            title        그 창의 제목
            owner_title  그 창을 띄운 창의 제목 ← **방 확인은 이것으로 한다**
            buttons      단추 이름들
            texts        창 안의 글자들 (파일명이 여기 나오기를 기대한다)
            rows         파일 목록의 줄 수. 못 읽으면 None
        """
        blank = {"present": False, "title": "", "owner_title": "",
                 "buttons": [], "texts": [], "rows": None}
        conf = self.file_send_conf
        title_re = conf.get("confirm_title_re") or ""
        if not title_re:
            # 빈 본으로 창을 찾으면 **아무 창이나** 잡힌다. 안 찾는 편이 낫다.
            log.warning("file_send.confirm_title_re 가 비어 확인 창을 찾지 않습니다")
            return blank
        try:
            dialogs = [w for w in self._desktop.windows(title_re=title_re)
                       if _visible(w)]
            if len(dialogs) != 1:
                # 없거나(0) 여러 개(2+)면 어느 것인지 모른다 — 고르지 않는다.
                if dialogs:
                    log.warning("확인 창 후보가 여러 개입니다: %r",
                                [_text_of(w) for w in dialogs])
                return blank
            dialog = dialogs[0]
            return {
                "present": True,
                "title": _text_of(dialog),
                "owner_title": self._owner_title(dialog),
                "buttons": _control_texts(dialog, "Button"),
                "texts": (_control_texts(dialog, "Text")
                          + _control_texts(dialog, "ListItem")
                          + _control_texts(dialog, "DataItem")),
                "rows": _list_rows(dialog),
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("확인 창을 읽지 못했습니다(전송 안 함): %s", exc)
            return blank

    def _owner_title(self, dialog) -> str:
        """확인 창을 띄운 창의 제목. 읽지 못하면 빈 값.

        mac 에서는 시트가 방 창에 붙어 있어 앞 창 제목이 곧 방 이름이었다.
        Windows 의 대화 상자는 제 창이라 **주인(owner) 창**을 물어봐야 한다.

        빈 값이면 관문이 막는다 — **모르면 안 보낸다.**
        """
        try:
            import win32gui  # type: ignore

            GW_OWNER = 4
            owner = win32gui.GetWindow(dialog.handle, GW_OWNER)
            return (win32gui.GetWindowText(owner) or "").strip() if owner else ""
        except Exception as exc:  # noqa: BLE001
            log.warning("확인 창의 주인 창을 읽지 못했습니다: %s", exc)
            return ""

    def _click_dialog_button(self, room_name: str, name: str) -> bool:
        """확인 창의 단추를 이름으로 누른다.

        ⚠ 좌표로 누르지 않는다 — 창 크기·해상도가 다르면 엉뚱한 것이 눌린다.
        """
        try:
            title_re = self.file_send_conf.get("confirm_title_re") or ""
            dialog = self._desktop.window(title_re=title_re)
            for button in dialog.descendants(control_type="Button"):
                if _norm_button(_text_of(button)) == _norm_button(name):
                    button.click_input()
                    return True
            log.warning("확인 창에서 %r 단추를 찾지 못했습니다", name)
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("확인 창 단추를 누르지 못했습니다(%r): %s", name, exc)
            return False

    def _dismiss_confirm(self, room_name: str) -> None:
        """보내지 않고 물러난다. 확인 창이 떠 있으면 취소, 아니면 Esc.

        ⚠ 확인 창을 못 찾은 경우에도 반드시 부른다. 붙여넣기가 **입력창에 첨부로
          얹혀 있을 수 있고**, 남겨 두면 다음에 보내는 문구와 함께 나간다.
          Esc 로 털리는지는 실기에서 확인할 목록에 있다.
        """
        conf = self.file_send_conf
        snapshot = self._confirm_snapshot(room_name)
        if _is_confirm_window(snapshot, conf):
            cancels = _match_buttons(snapshot.get("buttons", []),
                                     conf.get("cancel_button_re", ""))
            if cancels and self._click_dialog_button(room_name, cancels[0]):
                return
        try:
            self._pyautogui.press("esc")
        except Exception:  # noqa: BLE001
            pass

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


# ══════════════════════════════════════════════════════════════════════════
#  확인 창 읽기·검사 — **창과 떨어져 있어 이 기계에서 그대로 시험한다**
#
#  Windows 카톡이 없어도 도는 순수 함수들이다. 위쪽 `_confirm_snapshot` 이
#  창을 읽는 자리(전부 추측)라면, 여기는 **읽은 것을 보고 보낼지 말지 정하는
#  자리**다. 그 판단은 추측이 아니어야 해서 따로 떼어 두었다.
#  (mac 의 `kakao_mac.check_confirm_sheet` 와 같은 결)
# ══════════════════════════════════════════════════════════════════════════

def file_send_enabled(selectors: Optional[dict] = None) -> bool:
    """Windows 발송기가 파일을 붙일 줄 안다고 밝힐 것인가.

    **기본은 아니오다.** 실기 확인 전에 밝히면 서버가 파일이 실린 잡을 내주고,
    관문이 막아 그 회차의 자료 전달이 통째로 실패한다(문구까지 안 나간다).
    지금은 사람이 PC 에서 직접 붙이는 편이 낫다.

    켜는 길이 둘이다:
      · `DEALFLOW_WIN_FILE_SEND=1`  — 팀 PC 에서 **확인할 때만** 한 창에서
      · `selectors.yaml: file_send.verified: true` — 확인이 끝난 뒤 저장소에 못박기
    """
    env = (os.environ.get(FILE_SEND_ENV) or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    conf = dict(FILE_SEND_DEFAULTS)
    conf.update((selectors or {}).get("file_send") or {})
    return bool(conf.get("verified"))


def _visible(window) -> bool:
    try:
        return bool(window.is_visible())
    except Exception:  # noqa: BLE001
        return False


def _text_of(control) -> str:
    try:
        return (control.window_text() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _control_texts(dialog, control_type: str) -> List[str]:
    try:
        return [t for t in (_text_of(c)
                            for c in dialog.descendants(control_type=control_type)) if t]
    except Exception:  # noqa: BLE001
        return []


def _list_rows(dialog) -> Optional[int]:
    """확인 창의 파일 목록이 몇 줄인가. **못 읽으면 None** (= 판단 불가).

    None 이면 관문이 막는다 — 못 읽는 것과 맞는 것은 다르다(mac 과 같은 원칙).
    """
    for container in ("List", "DataGrid", "Table", "Tree"):
        try:
            found = dialog.descendants(control_type=container)
        except Exception:  # noqa: BLE001
            return None
        if not found:
            continue
        rows = 0
        for item in ("ListItem", "DataItem", "TreeItem"):
            try:
                rows += len(found[0].descendants(control_type=item))
            except Exception:  # noqa: BLE001
                return None
        return rows
    return None


def _norm_button(text: str) -> str:
    """단추 이름 비교용. `&` 는 밑줄 표시라 이름의 일부가 아니다."""
    return " ".join((text or "").replace("&", "").split())


def _match_buttons(buttons: List[str], pattern: str) -> List[str]:
    """`pattern` 에 걸리는 단추들. 본이 비었거나 깨졌으면 빈 목록."""
    if not pattern:
        return []
    try:
        rx = re.compile(pattern)
    except re.error:
        log.warning("selectors.yaml 의 단추 본이 깨졌습니다: %r", pattern)
        return []
    return [b for b in buttons if b and rx.match(_norm_button(b))]


def _send_button(snapshot: dict, conf: Optional[dict] = None) -> List[str]:
    conf = conf or FILE_SEND_DEFAULTS
    return _match_buttons(snapshot.get("buttons", []),
                          conf.get("send_button_re", ""))


def _is_confirm_window(snapshot: Optional[dict], conf: Optional[dict] = None) -> bool:
    """지금 떠 있는 것이 **파일 전송 확인 창**인가.

    제목이 맞고, 취소 단추와 보내기 단추가 둘 다 있어야 한다. 하나라도 없으면
    확인 창으로 보지 않는다 — 확인 창이 아닌 것을 확인 창으로 보면 관문이
    헛돈다.
    """
    conf = conf or FILE_SEND_DEFAULTS
    if not snapshot or not snapshot.get("present"):
        return False
    title_re = conf.get("confirm_title_re") or ""
    if not title_re:
        # ⚠ 빈 본을 `re.search` 에 주면 **아무 제목에나 걸린다.** 그러면 엉뚱한
        #   창을 확인 창으로 보게 된다 — 비어 있으면 판단 불가로 둔다.
        #   (제목이 정말 없는 창이면 `^$` 로 적는다)
        log.warning("selectors.yaml 의 file_send.confirm_title_re 가 비었습니다")
        return False
    try:
        if not re.search(title_re, snapshot.get("title") or ""):
            return False
    except re.error:
        log.warning("selectors.yaml 의 확인 창 제목 본이 깨졌습니다: %r", title_re)
        return False
    buttons = snapshot.get("buttons", [])
    return bool(_match_buttons(buttons, conf.get("cancel_button_re", ""))
                and _match_buttons(buttons, conf.get("send_button_re", "")))


def _counts(snapshot: dict, conf: dict) -> List[int]:
    """확인 창에서 **읽어 낼 수 있는 개수**를 전부 모은다.

    셋 중 어디서든 나온다: 목록 줄 수 · 개수가 박힌 단추(`1개 전송`) · 창의
    글자(`파일 2개를 …`). 하나도 못 읽으면 빈 목록이고, 그러면 관문이 막는다.
    """
    found: List[int] = []
    rows = snapshot.get("rows")
    if isinstance(rows, int) and not isinstance(rows, bool):
        found.append(rows)

    pattern = conf.get("count_re") or ""
    if not pattern:
        return found
    try:
        rx = re.compile(pattern)
    except re.error:
        log.warning("selectors.yaml 의 개수 본이 깨졌습니다: %r", pattern)
        return found
    if rx.groups < 1:
        # 숫자를 꺼낼 자리가 없는 본이다. 못 읽는 것으로 두면 관문이 막는다.
        log.warning("개수 본에 숫자를 담는 괄호가 없습니다: %r", pattern)
        return found

    for text in list(snapshot.get("buttons", [])) + list(snapshot.get("texts", [])):
        hit = rx.search(_norm_button(text))
        if hit and hit.group(1) and hit.group(1).isdigit():
            found.append(int(hit.group(1)))
    return found


def _leaf(text: str) -> str:
    """경로에서 마지막 조각. 확인 창이 파일명 대신 **전체 경로**를 보여 줄 수 있다.

    ⚠ 느슨하게 만드는 것이 아니다. 조각 하나가 파일명과 **정확히** 같아야
      통과한다 — 경로의 마지막 조각이 곧 파일명이기 때문이다.
    """
    return re.split(r"[\\/]", text or "")[-1]


def check_confirm_window(snapshot: Optional[dict], room_name: str,
                         expected_names: List[str],
                         conf: Optional[dict] = None) -> Optional[str]:
    """★ 관문. 보내려던 것과 **정확히 같을 때만** None 을 돌려준다.

    어긋나면 그 이유를 문자열로 돌려주고, 부르는 쪽은 **취소하고 아무것도 보내지
    않는다.** mac 과 같은 원칙이다(`kakao_mac.check_confirm_sheet`) — 방 제목 ·
    파일명 · 개수를 나가기 직전에 확인하고, **하나라도 확인이 안 되면 안 보낸다.**

    "못 읽었다" 는 "맞다" 가 아니다. 주인 창을 못 읽어도, 개수를 못 읽어도 막는다.
    """
    want = list(expected_names or [])
    settings = dict(FILE_SEND_DEFAULTS)
    settings.update(conf or {})

    if not snapshot or not snapshot.get("present"):
        return "확인 창이 없습니다"

    # ① 확인 창이 맞나. 제목·취소 단추·보내기 단추가 다 있어야 한다.
    if not _is_confirm_window(snapshot, settings):
        return (f"파일 전송 확인 창이 아닙니다: 제목={snapshot.get('title')!r} "
                f"단추={snapshot.get('buttons')!r}")

    # ② 방이 맞나 — 파일을 붙이는 사이에 다른 창이 앞으로 올 수 있다.
    #    Windows 의 대화 상자는 제 창이라 **주인 창**의 제목을 본다.
    #    한글은 자모 조합 형태가 두 가지라 그것만 맞춰 견준다(`base.nfc`).
    owner = (snapshot.get("owner_title") or "").strip()
    if not owner:
        # ★ 못 읽은 것은 맞은 것이 아니다. 어느 방인지 모르면 안 보낸다.
        return "확인 창을 띄운 방을 읽지 못했습니다"
    if nfc(owner) != nfc(room_name):
        return f"방이 다릅니다: 확인 창을 띄운 창 {owner!r} != 대상 {room_name!r}"

    # ③ 보내기 단추가 하나여야 한다 — 둘이면 어느 쪽인지 알 수 없다.
    senders = _send_button(snapshot, settings)
    if len(senders) > 1:
        return f"보내기 단추가 여러 개입니다: {senders!r}"

    # ④ 개수. 목록 줄 수 · 개수가 박힌 단추 · 창의 글자 중 **읽히는 것은 전부**
    #    맞아야 하고, 하나도 못 읽으면 막는다(못 읽는 것과 맞는 것은 다르다).
    counts = _counts(snapshot, settings)
    if not counts:
        return (f"보낼 개수를 읽지 못했습니다: 단추={snapshot.get('buttons')!r} "
                f"목록={snapshot.get('rows')!r}")
    wrong = sorted({c for c in counts if c != len(want)})
    if wrong:
        return (f"개수가 다릅니다: 창은 {wrong}개인데 "
                f"보내려던 것은 {len(want)}개")

    # ⑤ 파일명이 전부 있나.
    #
    #    ★ 두 쪽을 **같은 형태로 맞춘 뒤** 견준다(`base.same_file_name`).
    #      한글 파일명은 자모 조합 형태가 두 가지라 그냥 `==` 로 견주면 멀쩡한
    #      파일을 "창에 없다" 며 취소한다 — 가짜 실패(mac 에서 실제로 겪었다).
    #
    #    창이 파일명 대신 **전체 경로**를 보여 줄 수도 있어 마지막 조각도 함께
    #    본다. 느슨해지는 것이 아니다 — 조각이 파일명과 정확히 같아야 한다.
    texts = list(snapshot.get("texts", []))
    missing = [n for n in want
               if not any(same_file_name(n, shown) or same_file_name(n, _leaf(shown))
                          for shown in texts)]
    if missing:
        return f"확인 창에 없는 파일: {missing!r} (창에 있는 것: {texts!r})"
    return None


def _same_paths(placed: Optional[List[str]], wanted: List[str]) -> bool:
    """클립보드에서 다시 읽은 목록이 담으려던 것과 **정확히 같은가.**

    개수·차례까지 본다. 한글 경로는 자모 조합 형태가 두 가지라 그것만 맞춘다.
    """
    if placed is None:
        return False
    if len(placed) != len(wanted):
        return False
    return all(nfc(a) == nfc(b) for a, b in zip(placed, wanted))
