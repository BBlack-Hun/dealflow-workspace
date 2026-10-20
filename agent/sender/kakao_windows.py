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
re-read the **foreground** window title (keys go there) and require an EXACT match
with room_name; any mismatch → close + failed(room_mismatch), never send.

All timings / shortcuts / control identifiers come from selectors.yaml (no hardcoded
automation constants — ROADMAP 공통 원칙 2).

──────────────────────────────────────────────────────────────────────────────
파일 첨부 (`send_file`) — ⚠ **실기 확인 전이다**
──────────────────────────────────────────────────────────────────────────────

**붙여넣기(Ctrl+V)로는 파일이 안 간다**(Windows 실기 0.11.12 — 카톡이 클립보드의
파일을 받지 않는다). 사람이 하는 그대로 **첨부 단추**로 간다:

  ① 이름 빗장(0바이트도 막는다) → ② 방 열고 앞 창 제목 정확 일치
  → ③ 채팅창 아래 줄의 첨부 단추(풍선 도움말 `파일전송 Ctrl+T`). UIA 로 못 찾으면
     그 단추의 단축키 Ctrl+T — 앞 창이 그 채팅창일 때만 누른다
  → ④ Windows **열기 창**(`#32770` · 제목 `열기` · 카톡 프로세스 · 새로 뜬 창 · 주인이
     그 채팅창) — 여기서 [중단]이면 [취소]
  → ⑤ `파일 이름(N):` 칸에 **전체 경로**를 넣고 **되읽어 견준 뒤** [열기(O)]
  → ⑥ ★ 카톡 **`파일 전송` 카드**(채팅창 위에 뜬다) 관문: 후보가 딱 하나 · 제목
     `파일 전송` · [N개 전송] 단추가 딱 하나 · N == 1 · 파일명이 읽히면 같아야 한다
  → ⑦ [중단]을 한 번 더 묻고 [1개 전송] → 카드가 사라졌나

`전송 불가` 카드(실기: 0바이트 파일 — `전송 불가 1 · 비어있는 파일 · [확인]`)는
[확인]으로 닫고 그 까닭을 실패로 남긴다(문구도 안 나간다). 어긋나면 카드를 [×]
(못 찾으면 그 창에 WM_CLOSE → Esc)로 닫는다 — `⋮` 메뉴는 누르지 않는다.
**카드를 못 찾는 것도 실패다** — 모르면 안 보낸다.

열기 창 · 카드가 뜰 때와 실패할 때 카톡 창들과 그 속 컨트롤을 떠서(`ui_dump`)
진단 기록으로 올린다. 실기 확인 전(`verified: false`)에는 **성공해도** 올린다.
창을 읽는 자리(`_confirm_snapshot` · `_wait_open_dialog`)와 그 모양을 적어 둔 값
(`selectors.yaml: file_send`)은 실기에서 본 화면을 본뜬 것이고, UIA 로 무엇이
읽히는지는 아직 모른다. 관문 판단(`check_file_card`)은 창과 떨어진 순수 함수라
이 기계에서 그대로 시험한다.

`can_send_files` 는 **기본이 꺼짐**이다 — 확인 전에 서버가 파일 잡을 내주면
그 회차의 자료 전달이 통째로 실패한다(문구까지 안 나간다). 팀 PC 에서 확인할
때만 `DEALFLOW_WIN_FILE_SEND=1` 로 켜고, 확인이 끝나면 `selectors.yaml` 의
`file_send.verified` 를 참으로 바꿔 저장소에 못박는다.

──────────────────────────────────────────────────────────────────────────────
방 검색 (`discover_rooms` · `verify_room`) — ⚠ **컨트롤 경로는 실기 확인 전이다**
──────────────────────────────────────────────────────────────────────────────

방 제목은 **우리가 만들어 맞출 수 없다**(접미사·담당자 이름이 방마다 다르다).
그래서 이름+직함으로 검색해 **실제 제목을 읽어 온다** — mac 이 먼저 그렇게
했고(`kakao_mac.discover_rooms`), 이쪽도 **같은 모양으로 답한다**. 서버는 둘을
구분하지 않고 같은 칸으로 받는다(`agent/main.py: report_item(candidates=...)`).

  ① 포커스 확인 → ② Ctrl+F → ③ 클립보드 + Ctrl+V → ④ 검색어 되읽기
  → ⑤ **검색어가 든 줄이 나타날 때까지** 기다려 결과 줄의 글자만 읽기 → ⑥ 걸러내기

**방을 열지 않는다.** 글자만 읽으므로 부작용이 없다.

읽는 자리(`_result_rows`)의 컨트롤 경로는 전부 `selectors.yaml: room_search` 에
있고 **추측이다** — Windows 카톡의 검색 결과 목록을 UIA 로 본 사람이 없다.
틀리면 **후보 0건**으로 답하고 넘어간다. 거짓 후보를 지어내지 않는다.

판정(`verify_room`)과 후보(`discover_rooms`)는 **다른 자리**다. 후보는 '검색어가
든 줄' 을 넉넉히 모으고, 판정은 **제목이 글자까지 같은 줄만** 센다. 그 판단은
창과 떨어진 순수 함수라(`verdict_from_titles` · `filter_room_titles`) 이 기계에서
그대로 시험한다.

확인 절차는 `docs/WINDOWS_TEST.md` 의 "I. 방 검색 실기 확인" 에 있다.
"""
from __future__ import annotations

import base64
import logging
import os
import platform
import re
import time
from typing import List, Optional

from .base import (FILE_SEND_UNSUPPORTED, IrPathError, SendResult, Sender, nfc,
                   resolve_ir_file, same_file_name, stop_result)

log = logging.getLogger("agent.kakao")

# ── 파일 첨부 화면의 모양 — 실기 화면(10/20)을 본떴다 ──────────────────────
#
# 실기에서 다르면 `selectors.yaml: file_send` 를 고친다 — 코드를 고치지
# 않는다(ROADMAP 공통 원칙 2).
FILE_SEND_DEFAULTS = {
    # ③ 채팅창 아래 줄의 첨부 단추 — 이름(또는 도움말)이 이 본에 걸리는 Button 하나
    "attach_button_re": r"파일\s*전송",
    # UIA 로 그 단추를 못 찾으면 누르는 단축키(그 단추의 풍선 도움말에 적힌 것)
    "attach_hotkey": ["ctrl", "t"],
    # ④ Windows 열기 창
    "open_dialog_title_re": r"^(열기|Open)$",
    "open_dialog_class": "#32770",
    # ⑤ 열기 창의 컨트롤 — Windows 공통 대화 상자의 AutomationId(언어와 무관)
    "file_name_edit_id": "1148",
    "open_button_id": "1",
    "cancel_button_id": "2",
    # ⑥ 카톡 `파일 전송` 카드 — 창 제목이나 카드 속 글자
    "confirm_title_re": r"파일\s*전송",
    # 보내기 단추. 개수가 박혀 나온다(`1개 전송`) — 그 숫자가 보내려던 개수와 같아야 한다.
    # ⚠ `확인` 은 보내기가 아니다 — `전송 불가` 카드의 [확인]은 닫기다(실기).
    "send_button_re": r"^\s*(\d+)\s*개\s*전송\s*$",
    # 카드를 닫는 [×]. 못 찾으면 그 창에 WM_CLOSE → Esc. `⋮` 메뉴는 누르지 않는다.
    "close_button_re": r"^(닫기|Close|×|✕|X)$",
    # `전송 불가` 카드를 닫는 단추. 그 카드에서만 누른다.
    "dismiss_button_re": r"^(확인|OK)$",
    # 카톡이 파일을 받지 않았다는 글자 (실기: `전송 불가 1` · `비어있는 파일`)
    "unsendable_re": r"전송\s*불가",
    # 실기에서 확인한 뒤 참으로 바꾼다. 그 전에는 `send_file` 이 거절한다.
    "verified": False,
}

#: 실기 확인 전에도 **한 번만** 켜 볼 수 있는 자리. 팀 PC 에서 셋팅할 때 쓴다.
#: 창 하나에만 사는 값이라 다음에 켜면 다시 꺼져 있다 — 그것이 맞다.
FILE_SEND_ENV = "DEALFLOW_WIN_FILE_SEND"

# ── 방 검색의 모양 — ⚠ 컨트롤 경로는 **추측**이다 ─────────────────────────
#
# `selectors.yaml: room_search` 가 덮어쓴다. 코드에 글자로 박지 않는 이유는
# 카톡이 바뀌면 이 파일이 아니라 그 파일만 고쳐야 하기 때문이다
# (ROADMAP 공통 원칙 2). 여기 값은 그 파일이 없을 때의 바닥값이다.
#
# 틀리면 **후보 0건**이다. 지어내지 않는다 — 그것이 이 자리의 규칙이다.
ROOM_SEARCH_DEFAULTS = {
    "list_control_types": ["List", "Tree", "DataGrid", "Table"],
    "list_auto_id": "",
    "item_control_types": ["ListItem", "TreeItem", "DataItem"],
    # 빈 값이면 줄 이름(Name)을 그대로 제목으로 쓴다.
    "item_text_control_type": "Text",
    "max_rows": 60,
    # 빈 값이면 검색어 되읽기를 하지 않는다.
    "input_control_type": "Edit",
    "paste_hotkey": ["ctrl", "v"],
    # 검색창을 연 뒤 붙여넣기 **전에** 누르는 키 묶음들. 카톡은 검색칸에 직전
    # 검색어를 남겨 두어, 지우지 않고 붙이면 회사명이 이어 붙는다(실기 0.11.2).
    # 먼저 UIA 로 검색칸을 비워 보고(`_clear_by_uia`), 안 되면 이 키를 누른다.
    # ⚠⚠ **Ctrl+A 는 쓰지 않는다.** Windows 카톡 메인 창에서 Ctrl+A 는 '친구
    #     추가' 단축키다 — 0.11.3 이 이걸 눌러 친구 추가 창을 띄우고 회사명을
    #     **그 창에** 붙여 넣었다(실기). 검색이 통째로 안 됐다. 그래서 편집칸
    #     안에서만 뜻이 있는 End → Shift+Home → Backspace 로 지운다.
    #     설정에 Ctrl+A 가 들어 있어도 `clear_chords` 가 건너뛴다.
    "clear_keys": [["end"], ["shift", "home"], ["backspace"]],
    # 목록을 못 읽으면 **맨 위 결과 방을 열어** 그 창 제목을 읽는다.
    "open_top_fallback": True,
    # 맨 위 결과를 여는 키. 실기에서 Enter 가 첫 줄을 안 열면 ["down", "enter"].
    "open_top_keys": ["enter"],
}

#: 줄을 못 읽었을 때 한 번만 떠 두는 카톡 창 구조. 셀렉터를 고칠 때 본다.
UIA_MAIN_DUMP_FILE = "kakao_uia_dump.txt"
#: 맨 위 방을 처음 열었을 때 한 번만 떠 두는 채팅창 구조(단톡·1:1 가르기용).
UIA_CHAT_DUMP_FILE = "kakao_uia_chat_dump.txt"
#: 파일 첨부 진단 — 마지막 파일 한 개를 붙일 때 떠 둔 카톡 창들(`ui_dump` 와 같은 것).
UIA_FILE_DUMP_FILE = "kakao_file_send_dump.txt"
#: 진단 한 번에 싣는 줄 수 상한 — 서버로 올라가는 진단 기록이 끝없이 커지지 않게.
UI_DUMP_MAX_LINES = 600

#: 발송할 방을 몇 번까지 찾아 여나 — 처음 한 번 + Enter 로 아무 방도 안 열렸을 때(또는
#: 결과 목록이 읽히는데 그 방이 없을 때 · 다른 방이 열렸을 때 — 0.11.11) **열린 검색창을 닫고**
#: 한 번 더(0.11.10).
#: 실기(0.11.9)에서 같은 방을 다시 찾으면 카톡이 결과를 새로 세우지 않아 Enter 가 열 방이
#: 없었고, 실패한 건의 Esc(열린 검색창을 닫는다) 뒤의 건은 나갔다 — 그 차례를 한 건 안에서
#: 되풀이한다. 채팅 입력란에 키를 넣기 **전**의 일이라 다시 해도 겹쳐 나갈 것이 없다.
OPEN_ROOM_TRIES = 2


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
    #: (0.11.12) 마지막으로 연 방이 **첫 시도에** 막혔다가 다시 찾아 열렸으면 그 까닭.
    #: 성공 결과의 경고로 싣는다(`SendResult.warning`) — 실패는 아니지만 로그에 남긴다.
    _retry_note = ""
    #: 파일 첨부 진단 줄들(`_note_windows`) — 실패 보고에 실린다(`agent/main.py:
    #: collect_diagnostics`). 방을 열 때마다 비운다. 늘 **새 목록으로 바꿔 끼운다**.
    ui_dump: List[str] = []

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
        # 이 발송기가 Ctrl+F 로 연 메인 창 검색창이 **아직 열려 있다고 아는가**(0.11.10 —
        # `_close_search_box`). 모르면 거짓이다 — 닫힌 검색창에 누른 Esc 는 메인 창을 숨긴다.
        self._search_open = False
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
        """카톡 **메인 창 하나**를 고른다.

        ⚠ `Desktop.window(title_re="카카오톡.*")` 로 바로 잡으면 안 된다.
          Windows 카카오톡은 제목이 '카카오톡' 으로 시작하는 **숨은 보조 창**을
          여러 개 띄워 두고, pywinauto 는 그걸 보고 `ElementAmbiguousError`
          ("There are 3 elements that match") 를 던진다(실기, 0.11.0). 그래서
          방 검색·발송이 **한 번도** 돌지 못했다.

        목록(`windows()`)으로 받아 `pick_kakao_window` 로 하나를 고르고, 고른 창은
        **핸들로** 다시 잡아 돌려준다 — 부르는 쪽이 지금까지처럼
        `WindowSpecification` 을 받게 해 동작을 그대로 둔다.
        """
        title_re = self.sel.get("main_window_title_re", "카카오톡.*")
        exact = self.sel.get("main_window_title_kw", "카카오톡")
        deadline = time.monotonic() + self._t("window_wait", 5.0)
        while True:
            try:
                candidates = list(self._desktop.windows(title_re=title_re))
            except Exception as exc:  # noqa: BLE001
                log.debug("카톡 창 목록을 읽지 못했습니다(재시도): %s", exc)
                candidates = []
            chosen = pick_kakao_window(candidates, exact)
            if chosen is not None:
                try:
                    handle = chosen.handle
                except Exception:  # noqa: BLE001 — 그 사이 창이 사라졌다
                    handle = None
                if handle:
                    key = (handle, len(candidates))
                    if getattr(self, "_kakao_window_logged", None) != key:
                        self._kakao_window_logged = key
                        log.info("카톡 창 선택: %r handle=%s (후보 %d개)",
                                 _text_of(chosen), handle, len(candidates))
                    return self._desktop.window(handle=handle)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.25)
        raise RuntimeError(
            "카카오톡 창을 찾지 못했습니다 — 카톡이 켜져 있고 로그인돼 있는지 확인")

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

    # ── 방 검색 ─────────────────────────────────────────────────────────────
    #
    # ★ `discover_rooms` 와 `verify_room` 이 **같은 이 자리**(`_search_titles`)를
    #   쓴다. 파일 첨부에서 `_open_room_verified` 를 둘이 함께 쓰는 것과 같은
    #   이유다 — 검색하는 길이 둘로 갈리면 한쪽만 고쳐질 때 판정이 갈린다.
    #
    # ★★ 그래도 **판정은 나눠져 있다.** 후보 목록(`discover_rooms`)은 사람에게
    #    보여 주려고 넉넉히 모으고, 판정(`verify_room`)은 **제목이 글자까지 같은
    #    줄만** 센다. 후보가 늘었다고 판정이 느슨해지지 않는다
    #    (`agent/sender/base.py` 의 "never guess").

    @property
    def room_search_conf(self) -> dict:
        """방 검색 컨트롤 경로. `selectors.yaml: room_search` 가 바닥값을 덮는다."""
        conf = dict(ROOM_SEARCH_DEFAULTS)
        conf.update((self.sel or {}).get("room_search") or {})
        return conf

    def discover_rooms(self, query: str, marker: str = "",
                       company: bool = False) -> List[str]:
        """검색어로 카톡방을 찾아 **실제 방 제목 목록**을 돌려준다.

        mac 쪽(`kakao_mac.discover_rooms`)과 **같은 모양으로 답한다** — 서버는
        둘을 구분하지 않고 같은 칸(`report_item(..., candidates=...)`)으로 받는다.

        방 이름을 우리가 만들어 맞추는 것은 불가능하다는 게 실기에서 드러났다
        (같은 캠페인 방인데도 접미사·담당자 이름이 방마다 다르다). 그래서
        이름+직함으로 검색해 **실제 제목을 읽어온다.**

        marker 가 주어지면 그 글자가 든 방만 남긴다.

        먼저 **방을 열지 않고** 검색 결과 줄의 글자만 읽는다.

        ★ 그 줄을 못 읽거나(Windows 카톡은 목록을 자체 컨트롤로 그려 UIA 로 안
          보일 수 있다 — 실기 0.11.1 에서 모든 회사가 0건) 읽은 줄에 맞는 것이
          없으면, **맨 위 결과 방을 열어 그 창 제목을 읽는다**
          (`_open_top_room_title`). 읽은 제목에 검색어(회사명)가 들어 있을
          때만 후보 하나로 돌려준다. 그 창에는 **아무것도 입력하지 않고** 바로
          닫는다. 끄려면 `selectors.yaml: room_search.open_top_fallback: false`.

        ★ `company` 가 참이면(받는 쪽이 **스타트업 기업** — 서버가 잡에
          `target: company` 로 알려 준다) 맨 위 방 제목에 **투자사 표식**
          (`INVESTOR_ROOM_MARKERS`)이 들어 있으면 버린다. 회사명이 짧으면 투자사
          방 제목에도 그 글자가 들어 있다(실기 0.11.2). 담당자 쪽 확인에서는
          찾는 방이 곧 투자사 방이라 안 버린다.

        ★ 못 하면 **빈 목록**이다. 카톡이 검색을 안 보여 주거나 컨트롤을 못 찾거나
          포커스를 못 잡으면 0건으로 답하고 넘어간다. **거짓 후보를 지어내지
          않는다** — 화면은 후보가 0건이어도 초안·직접 적기로 돌아간다
          (`app/services/room_match.py`).
        """
        if not (query or "").strip():
            return []
        # `[딜소개 불가]` 같은 꼬리표는 카톡 방 제목에 없다 — 넣으면 검색이 0건이 된다.
        query = strip_annotations(query) or query.strip()
        conf = self.room_search_conf
        try:
            win = self._kakao_window()
            # ★ 포커스가 확인되지 않으면 키 입력을 하지 않는다. 방 이름이 브라우저
            #   등 엉뚱한 창으로 들어간 적이 있다(실기).
            if not self._focus_verified(win):
                log.warning("discover_rooms: 카톡 포커스 실패 — 후보 0건 query=%r", query)
                return []
            fallback = bool(conf.get("open_top_fallback", True))
            titles = self._search_titles(win, query, conf, keep_open=fallback)
            # ↑ keep_open 이면 검색창이 **열린 채** 돌아온다. 아래에서 반드시 닫는다.
            found: List[str] = []
            opened = False
            try:
                if titles is not None:
                    found = filter_room_titles(titles, query, marker=marker,
                                               max_rows=_max_rows(conf))
                state = getattr(self, "_last_search_state", "unread")
                if state == "foreground_lost":
                    # ★ 메인 창이 앞에 없다 — Enter·Esc 모두 누르지 않는다.
                    opened = True
                elif fallback and not found and state != "typed_mismatch":
                    # ★ 목록을 못 읽었거나 읽은 줄에 맞는 것이 없다 — **맨 위 방을
                    #   열어 창 제목을 읽는다.** 검색칸에 남의 글자가 있던 경우
                    #   (typed_mismatch)는 열지 않는다 — 보이는 목록이 남의 결과다.
                    opened = True
                    found = self._open_top_room_title(win, query, marker, conf,
                                                      company=company)
            finally:
                if fallback and not opened:
                    self._close_search()
            return found
        except Exception:  # noqa: BLE001
            log.exception("discover_rooms 실패 — 후보 0건 query=%r", query)
            return []

    def verify_room(self, room_name: str) -> str:
        """Search only; count EXACT-title matches. 1=verified, 0=not_found, >=2=ambiguous.

        **전송하지 않는다.** 검색 결과 줄의 제목만 읽고 센다.

        ⚠ 예전에는 이 자리가 **무조건 `"verified"` 를 돌려주는 자리 채우기**였다
          (화면을 읽을 길이 없었다). 그래서 Windows PC 의 [방 연결 확인]은
          **모든 방을 확인됨으로 올렸다** — 틀린 방 이름까지. 그 말은 발송 당일
          `send_text` 의 제목 대조에서야 드러났다. 지금은 **센다.**

        못 읽으면 `not_found` 다. 모르는 것을 `verified` 로 올리지 않는다 —
        mac 도 검색이 실패하면 `not_found` 로 답한다.
        """
        if not (room_name or "").strip():
            return "not_found"
        titles = None
        try:
            win = self._kakao_window()
            if not self._focus_verified(win):
                log.warning("verify_room: 카톡 포커스 실패 room=%r", room_name)
                return "not_found"
            titles = self._search_titles(win, room_name, self.room_search_conf)
        except Exception:  # noqa: BLE001
            log.exception("verify_room 실패 room=%r", room_name)
            return "not_found"
        if titles is None:
            log.warning("verify_room: 검색 결과를 읽지 못했습니다(확인됨으로 올리지 "
                        "않습니다) room=%r", room_name)
            return "not_found"
        return verdict_from_titles(titles, room_name)

    def _close_search(self) -> None:
        """검색창을 닫는다. 다음 검색이 직전 글자 위에 겹치지 않게.

        ⚠ **검색창을 연 뒤에만** 부른다. 포커스를 못 잡은 채로 Esc 를 누르면 그
          키가 그 순간 포커스를 가진 **다른 앱**으로 간다 — 키를 누르지 않는다는
          원칙은 Esc 에도 걸린다.

        누른 뒤로는 검색창이 열려 있다고 **알지 않는다**(`_search_open`) — 모르는 쪽으로
        둔다. 열린 채 남았으면 다음 건의 다시 찾기가 닫는다.
        """
        self._search_open = False
        try:
            self._pyautogui.press("esc")
        except Exception:  # noqa: BLE001
            pass

    def _close_search_box(self, win) -> bool:
        """이 발송기가 연 메인 창 검색창이 **아직 열려 있으면** 닫는다 (0.11.10). 눌렀으면 True.

        ★ 열려 있는지는 **이 발송기가 적어 둔 것**(`_search_open`)으로만 본다 — 검색칸
          글자로는 못 가른다. 카톡은 방을 열며 검색창을 스스로 닫아도 칸의 글자를 남긴다
          (0.11.5 실기 — 지우지 않고 붙이면 앞 방 이름에 이어 붙었다). 닫힌 검색창에
          누른 Esc 는 **메인 창을 숨긴다** — 모르면 누르지 않는다(0.11.9 는 보낸 뒤 늘 눌렀다).
        ★ **메인 창이 앞에 있을 때만** 누른다(`_foreground_is_main`) — 키는 앞 창으로 간다.

        누른 뒤에는 **기다렸다가** 메인 창이 숨었는지 보고, 숨었으면 다시 띄운다. 숨기기는
        Esc 뒤에 한 박자 늦게 일어나, 곧바로 보면 아직 보인다(`_ensure_visible` 이 못
        본다). 숨었다 다시 뜬 창은 포커스가 없을 수 있다 — 누른 뒤 키를 더 누를 쪽이
        포커스를 다시 확인한다(`_open_room_verified`).
        """
        if not getattr(self, "_search_open", False) or not self._foreground_is_main(win):
            return False
        self._close_search()
        time.sleep(self._t("after_close_search", 0.3))
        self._ensure_visible(win)
        return True

    # ── 맨 위 방 열어 제목 읽기 ──────────────────────────────────────────────
    #
    # 검색 결과 목록을 UIA 로 못 읽는 PC 를 위한 길이다. 목록은 못 읽어도
    # **창 제목은 읽힌다**(`GetWindowText`) — 방을 열면 그 채팅창의 제목이 곧
    # 실제 방 제목이다.
    #
    # ★ 지키는 것
    #   · 채팅창에는 **아무것도 입력하지 않는다.** 누르는 키는 여는 키(Enter)와
    #     닫는 Esc 뿐이고, Esc 도 그 창이 앞에 있음을 확인한 뒤에만 누른다.
    #   · **새로 뜬 창만** 본다. 열기 전·후 창 목록을 견줘 새로 보이게 된 카톡
    #     창 하나만 고른다(`pick_new_window`). 원래 열려 있던 창은 건드리지 않는다.
    #   · 제목에 회사명이 없으면 **버린다**(`title_has_company`). 새 창이 안 뜨면
    #     0건이다 — 지어내지 않는다.

    def _top_windows(self) -> Optional[dict]:
        """보이는 최상위 창들 `{hwnd: (제목, pid)}`. pywin32 가 없으면 None."""
        try:
            import win32gui  # type: ignore
            import win32process  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        out: dict = {}

        def _collect(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd) or ""
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                out[hwnd] = (title, pid)
            except Exception:  # noqa: BLE001 — 그 사이 창이 사라졌다
                pass
            return True

        try:
            win32gui.EnumWindows(_collect, None)
        except Exception:  # noqa: BLE001
            return None
        return out

    def _foreground_hwnd(self) -> int:
        try:
            import win32gui  # type: ignore

            return int(win32gui.GetForegroundWindow() or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _window_pid(self, win) -> int:
        try:
            import win32process  # type: ignore

            return int(win32process.GetWindowThreadProcessId(win.handle)[1])
        except Exception:  # noqa: BLE001
            return 0

    def _is_window_visible(self, hwnd) -> bool:
        try:
            import win32gui  # type: ignore

            return bool(win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd))
        except Exception:  # noqa: BLE001
            return False

    def _ensure_visible(self, win) -> None:
        """검색창이 이미 닫혀 있었으면 Esc 가 카톡 메인 창을 숨길 수 있다 —
        그러면 다음 회사부터 포커스를 못 잡아 전부 0건이 된다. 숨었으면 다시 띄운다."""
        try:
            import win32con  # type: ignore
            import win32gui  # type: ignore

            hwnd = win.handle
            if hwnd and not win32gui.IsWindowVisible(hwnd):
                log.info("카톡 메인 창이 숨어 다시 띄웁니다")
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        except Exception:  # noqa: BLE001
            pass

    def _post_close(self, hwnd) -> None:
        try:
            import win32con  # type: ignore
            import win32gui  # type: ignore

            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:  # noqa: BLE001
            log.debug("WM_CLOSE 실패 hwnd=%s", hwnd)

    def _open_top_room_title(self, win, query: str, marker: str,
                             conf: dict, company: bool = False) -> List[str]:
        """검색 결과 **맨 위 방을 열어** 창 제목을 읽고, 닫고, 검색창도 닫는다.

        부르기 전: 검색어가 든 검색창이 **열려 있다**(`_search_titles(keep_open=True)`).
        돌려주는 값: 회사명이 든 제목이면 `[제목]`, 아니면 `[]`.
        """
        main_title = self.sel.get("main_window_title_kw", "카카오톡")
        refocus_ok = True
        pressed = refocused = False
        try:
            before = self._top_windows()
            if before is None:
                log.info("맨 위 방 열기: 창 목록을 읽을 수 없어 건너뜁니다 query=%r",
                         query)
                return []
            pressed = True
            for key in (conf.get("open_top_keys") or ["enter"]):
                self._pyautogui.press(key)

            pid = self._window_pid(win)
            deadline = time.monotonic() + self._t("open_top_wait", 1.5)
            picked = None
            while True:
                after = self._top_windows() or {}
                picked = pick_new_window(before, after, pid=pid,
                                         foreground=self._foreground_hwnd(),
                                         exclude_titles=(main_title,))
                if picked is not None or time.monotonic() >= deadline:
                    break
                time.sleep(self._t("room_search_poll", 0.15))

            if picked is None:
                log.info("맨 위 방 열기: 새 채팅창이 뜨지 않았습니다 — 후보 0건 "
                         "query=%r", query)
                return []

            hwnd, title = picked
            try:
                self._dump_chat_once(hwnd)
            finally:
                self._close_chat_window(hwnd, title)
                refocused = True
                refocus_ok = self._focus_verified(win)

            if not title_has_company(title, query):
                log.info("맨 위 방 제목에 검색어가 없어 버립니다: %r (query=%r)",
                         title, query)
                return []
            if company and looks_like_investor_room(title, query):
                log.info("맨 위 방이 투자사 방으로 보여 버립니다: %r (query=%r)",
                         title, query)
                return []
            if marker and nfc(marker) not in nfc(title):
                log.info("맨 위 방 제목에 표식 %r 가 없어 버립니다: %r",
                         marker, title)
                return []
            log.info("맨 위 방 제목을 후보로: %r (query=%r)", title, query)
            return [title]
        finally:
            # 검색창 닫기 — ★ 카톡 메인 창이 앞에 있을 때만 Esc 를 누른다.
            #   키를 누른 뒤에는 무엇이 앞에 왔는지 모르니 다시 확인한다.
            if pressed and not refocused:
                refocus_ok = self._focus_verified(win)
            if refocus_ok:
                self._close_search()
                self._ensure_visible(win)
            else:
                log.warning("맨 위 방을 닫은 뒤 카톡 포커스를 못 잡아 검색창을 "
                            "닫지 않았습니다(키 입력 안 함)")

    def _close_chat_window(self, hwnd, title: str) -> None:
        """방금 연 채팅창 **하나만** 닫는다. 앞에 있으면 Esc, 아니면 WM_CLOSE."""
        if (self._foreground_hwnd() == hwnd
                and self._foreground_title() == title):
            try:
                self._pyautogui.press("esc")
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self._t("after_close_chat", 0.3))
        if self._is_window_visible(hwnd):
            # Esc 가 안 먹었거나 앞에 없었다 — 키 대신 그 창에만 닫으라고 보낸다.
            self._post_close(hwnd)
            time.sleep(self._t("after_close_chat", 0.3))

    # ── 진단: UIA 구조 떠 두기 (처음 한 번만) ────────────────────────────────

    def _dump_path(self, filename: str) -> Optional[str]:
        """진단 파일 자리. 로그 폴더를 모르면 None — 아무 데나 쓰지 않는다."""
        base = self.screenshot_dir
        if not base:
            return None
        try:
            os.makedirs(base, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return os.path.join(base, filename)

    def _write_dump(self, root, filename: str, what: str):
        """UIA 구조를 파일로. 쓰면 그 항목들, 못 쓰면 None. 진단이라 터지지 않는다."""
        try:
            if hasattr(root, "wrapper_object"):
                root = root.wrapper_object()
            path = self._dump_path(filename)
            if path is None:
                return None
            entries = uia_tree_entries(root)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(format_uia_entries(entries)) + "\n")
            log.info("%s UIA 구조를 저장했습니다: %s (%d줄)", what, path,
                     len(entries))
            return entries
        except Exception as exc:  # noqa: BLE001
            log.info("%s UIA 구조 저장 실패: %s", what, exc)
            return None

    def _dump_uia_once(self, win, flag: str, filename: str) -> None:
        if getattr(self, flag, False):
            return
        setattr(self, flag, True)
        self._write_dump(win, filename, "카톡 메인 창")

    def _dump_chat_once(self, hwnd) -> None:
        """처음 연 채팅창의 구조를 떠 두고, 제목 옆 인원 수를 **짐작만** 해 본다.

        인원 수는 로그에만 남긴다 — 아직 아무 판단에도 쓰지 않고 서버로도
        보내지 않는다(단톡·1:1 가르기를 나중에 붙일 때 볼 근거다).
        """
        if getattr(self, "_chat_dumped", False) or self._desktop is None:
            return
        self._chat_dumped = True
        try:
            chat = self._desktop.window(handle=hwnd)
        except Exception as exc:  # noqa: BLE001
            log.info("채팅창 UIA 를 잡지 못했습니다: %s", exc)
            return
        entries = self._write_dump(chat, UIA_CHAT_DUMP_FILE, "채팅창")
        if entries:
            count = guess_member_count(entries)
            if count is not None:
                log.info("방 인원 추정: %d", count)

    def _search_titles(self, win, query: str, conf: dict,
                       keep_open: bool = False) -> Optional[List[str]]:
        """검색칸에 `query` 를 넣고 **결과 줄의 제목들**을 읽는다.

        돌려주는 값:
          · 제목 목록 — 읽었다(0줄일 수도 있다. 없는 사람은 정말 없다)
          · `None`    — **못 읽었다.** 0건과 구분한다. 부르는 쪽이 이것을 보고
                        '확인됨' 으로 올리지 않는다.

        ⚠ 카톡 검색 결과는 **한 박자 늦게** 반영된다. 바로 읽으면 직전 검색의
          결과가 잡힌다(mac 에서 '가나' 를 검색했는데 '다라' 방이 나왔다 →
          엉뚱한 방이 저장될 수 있었다). 그래서 **검색어의 첫 낱말이 든 줄이
          나타날 때까지** 기다렸다가 읽는다. mac 과 같은 길이다.

        `keep_open` 이 참이면 **다 읽은 뒤 검색창을 닫지 않는다** — 부르는 쪽
        (`discover_rooms` 의 맨 위 방 열기)이 그 검색 결과 위에서 이어 가고, 닫는
        것도 그쪽이 맡는다. 도중에 터지면 그래도 닫는다.

        어떻게 끝났는지는 `self._last_search_state` 에 남긴다:
          · `"read"`           — 줄을 읽었다
          · `"unread"`         — 줄을 못 읽었다(None)
          · `"typed_mismatch"` — 검색칸에 다른 글자가 들어 있었다(None).
                                 이때 보이는 목록은 **남의 결과**라 맨 위 방을
                                 열면 안 된다.
          · `"foreground_lost"` — 붙이기 전에 메인 창이 아닌 창이 앞에
                                 떴다(None). 붙이지 않았고, 검색창 Esc 도 맨 위
                                 방 열기도 하지 않는다(`_put_query`).
        """
        self._last_search_state = "unread"
        # 1) 검색창 열기. ★ 여기서부터만 Esc 로 닫는다 — 열지도 않은 채 Esc 를
        #    누르면 그 키가 다른 앱으로 간다.
        self._pyautogui.hotkey(*self.sel.get("search_hotkey", ["ctrl", "f"]))
        try:
            titles = self._read_search(win, query, conf)
        except BaseException:
            self._close_search()
            raise
        if self._last_search_state == "foreground_lost":
            # ★ 카톡 메인 창이 앞에 없다 — Esc 를 누르면 그 키가 **앞에 있는 창**
            #   으로 간다. 닫을 것은 `_put_query` 가 이미 따져 닫았다.
            return None
        if not keep_open:
            self._close_search()
        return titles

    def _read_search(self, win, query: str, conf: dict) -> Optional[List[str]]:
        """`_search_titles` 의 ②~④ — 검색창이 **열린 뒤** 글자를 넣고 줄을 읽는다."""
        needle = needle_of(query)
        max_rows = _max_rows(conf)
        time.sleep(self._t("after_search_hotkey", 0.4))

        # 2) 검색어 — **칸을 비우고** 클립보드 + Ctrl+V. 한글은 키 입력으로 못
        #    보낸다. ★ 카톡은 검색칸에 직전 검색어를 남겨 둔다 — 안 비우면
        #    `가나다` 뒤에 `라마바` 가 붙어 `가나다라마바` 로 검색된다(실기 0.11.2).
        if not self._put_query(win, query, conf):
            return None

        # 3) 검색어가 **진짜 그 칸에** 들어갔는지 되읽는다. 다르면 **한 번 더**
        #    비우고 붙인다. 그래도 다르면 남의 글자로 검색하지 않고 접는다.
        typed = self._search_input_text(win, conf)
        if typed is not None and _norm_title(typed) != _norm_title(query):
            log.warning("검색칸 글자가 검색어와 다릅니다(읽은 값=%r, 넣은 값=%r) "
                        "— 비우고 한 번 더 넣습니다", typed, query)
            # ★ 키를 더 누르기 전에 카톡 창이 앞에 있는지 다시 확인한다.
            if self._focus_verified(win):
                if not self._put_query(win, query, conf):
                    return None
                typed = self._search_input_text(win, conf)
            if typed is not None and _norm_title(typed) != _norm_title(query):
                log.warning("검색어가 검색칸에 들어가지 않았습니다(읽은 값=%r, "
                            "넣은 값=%r) — 후보를 읽지 않습니다", typed, query)
                self._last_search_state = "typed_mismatch"
                return None

        # 4) 결과가 갱신될 때까지 기다리며 읽는다.
        deadline = time.monotonic() + self._t("room_search_wait", 2.0)
        titles: Optional[List[str]] = None
        while True:
            rows = self._result_rows(win, conf)
            if rows is not None:
                titles = [row_title(r,
                                    conf.get("item_text_control_type", "Text"))
                          for r in rows[:max_rows]]
                if needle and any(nfc(needle) in nfc(t) for t in titles):
                    self._last_search_state = "read"
                    return titles
            if time.monotonic() >= deadline:
                break
            time.sleep(self._t("room_search_poll", 0.15))

        if titles is None or not any((t or "").strip() for t in titles):
            # 줄을 못 찾았거나, 찾았어도 글자를 하나도 못 읽었다 — 셀렉터가
            # 틀렸다는 뜻이다. 처음 한 번만 창 구조를 파일로 떠 둔다.
            self._dump_uia_once(win, "_uia_dumped", UIA_MAIN_DUMP_FILE)
        if titles is None:
            log.warning("검색 결과 목록을 읽지 못했습니다 — 후보 0건 query=%r "
                        "(`selectors.yaml: room_search` 의 컨트롤 경로를 "
                        "확인하세요)", query)
            return None
        self._last_search_state = "read"
        # 읽기는 읽었는데 검색어가 든 줄이 끝내 없었다 — **없는 것으로 본다.**
        log.info("검색 결과에 %r 가 든 줄이 없습니다 (%d줄 읽음) query=%r",
                 needle, len(titles), query)
        return titles

    def _put_query(self, win, query: str, conf: dict) -> bool:
        """검색칸을 **비우고** 검색어를 붙여 넣는다. 못 붙였으면 False.

        비우는 길(차례로):
          ① UIA — 검색칸(`room_search.input_control_type`)의 글자를 직접 지우고
             비었는지 되읽는다(`_clear_by_uia`). 키를 하나도 안 누른다.
          ② ① 이 안 되면 `room_search.clear_keys`(기본 End → Shift+Home →
             Backspace). ⚠ **Ctrl+A 는 누르지 않는다** — 카톡 메인 창에서
             Ctrl+A 는 '친구 추가' 다(실기 0.11.3). `clear_chords` 가 걸러 낸다.

        붙이기 **전에** 카톡 메인 창이 아직 앞에 있는지 본다
        (`_foreground_is_main`). 다른 창(친구 추가 창 등)이 앞에 떴으면 **붙이지
        않고** False — 회사명이 엉뚱한 창에 들어간다.

        ★ 부르는 쪽이 카톡 창 포커스를 확인한 뒤에만 부른다 — 다른 키와 같은
          규칙이다(`_focus_verified`). 모든 키 묶음은 `hotkey` 하나로 누른다.
        """
        if not self._clear_by_uia(win, conf):
            for chord in clear_chords(conf):
                self._pyautogui.hotkey(*chord)
        if not self._foreground_is_main(win):
            self._abort_foreign_foreground(win)
            self._last_search_state = "foreground_lost"
            return False
        self._pyperclip.copy(query)
        self._pyautogui.hotkey(*(conf.get("paste_hotkey") or ["ctrl", "v"]))
        time.sleep(self._t("after_query_paste", 1.5))
        return True

    def _clear_by_uia(self, win, conf: dict) -> bool:
        """검색칸을 **UIA 로** 비운다. 비웠다고 되읽혔을 때만 True.

        글자가 든 편집칸(`input_control_type`)만 지운다 — 빈 칸은 건드리지
        않는다. 지울 칸이 없거나(못 읽음·이미 빔), 지웠는데 글자가 남으면
        False 이고 부르는 쪽이 키(`clear_keys`)로 지운다. 빈 칸에서 End ·
        Shift+Home · Backspace 는 아무 일도 하지 않는다.
        """
        ctype = (conf.get("input_control_type") or "").strip()
        if not ctype:
            return False
        try:
            boxes = win.descendants(control_type=ctype)
        except Exception:  # noqa: BLE001
            return False
        filled = [b for b in boxes if _box_value(b)]
        if not filled:
            return False
        for box in filled:
            for name in ("set_edit_text", "set_text"):
                setter = getattr(box, name, None)
                if setter is None:
                    continue
                try:
                    setter("")
                    break
                except Exception as exc:  # noqa: BLE001
                    log.debug("검색칸 %s 실패: %s", name, exc)
        # 지운 뒤 **다시** 읽는다 — 지웠다는 말만 믿지 않는다.
        try:
            boxes = win.descendants(control_type=ctype)
        except Exception:  # noqa: BLE001
            return False
        if any(_box_value(b) for b in boxes):
            log.info("검색칸을 UIA 로 못 비웠습니다 — 키로 지웁니다")
            return False
        return True

    def _foreground_is_main(self, win) -> bool:
        """지금 앞에 있는 창이 **카톡 메인 창**인가.

        핸들을 둘 다 알면 핸들로 견준다. 모르면 제목이 메인 창 제목과
        **글자까지 같은지** 본다 — '친구 추가' 같은 카톡의 다른 창도 카톡
        프로세스라 프로세스로는 못 가른다. 모르면(빈 제목) 아니라고 본다.
        """
        fg = self._foreground_hwnd()
        try:
            main = int(getattr(win, "handle", 0) or 0)
        except Exception:  # noqa: BLE001
            main = 0
        if fg and main:
            return fg == main
        want = self.sel.get("main_window_title_kw", "카카오톡")
        return self._foreground_title() == want

    def _abort_foreign_foreground(self, win) -> None:
        """검색 도중 앞에 뜬 **다른 창**을 처리한다. 붙여넣기는 이미 접었다.

        Esc 는 그 창이 **카톡 프로세스의 창이고 메인 창이 아닐 때만** 누른다
        (예: Ctrl+A 로 뜬 '친구 추가' 창). 다른 앱이 앞에 있으면 아무 키도
        누르지 않는다 — Esc 가 그 앱으로 간다.
        """
        fg = self._foreground_hwnd()
        title = self._foreground_title()
        want = self.sel.get("main_window_title_kw", "카카오톡")
        main_pid = self._window_pid(win)
        fg_pid = self._hwnd_pid(fg) if fg else 0
        if fg and title != want and main_pid and fg_pid == main_pid:
            log.warning("검색 중 카톡의 다른 창(%r)이 앞에 떴습니다 — 붙여 넣지 "
                        "않고 Esc 로 닫습니다", title)
            self._close_search()
        else:
            log.warning("검색 중 카톡 메인 창이 앞에 없습니다(앞 창=%r) — 붙여 "
                        "넣지 않고 키를 더 누르지 않습니다", title)

    def _hwnd_pid(self, hwnd) -> int:
        try:
            import win32process  # type: ignore

            return int(win32process.GetWindowThreadProcessId(hwnd)[1])
        except Exception:  # noqa: BLE001
            return 0

    def _search_input_text(self, win, conf: dict) -> Optional[str]:
        """검색칸에 실제로 들어간 글자. **못 읽으면 None**(= 판단 불가).

        None 은 '비었다' 가 아니다. 카톡 빌드마다 컨트롤이 달라 못 읽을 수 있고,
        그것까지 실패로 보면 멀쩡한 PC 에서 후보가 영영 0건이 된다
        (`_input_text` 와 같은 판단). 대신 ④ 의 '검색어가 든 줄을 기다리는 것' 이
        같은 일을 한다.

        ★ 실기에서 엉뚱한 칸을 집으면 `selectors.yaml` 의
          `room_search.input_control_type` 을 비워 이 되읽기를 끈다.
        """
        ctype = (conf.get("input_control_type") or "").strip()
        if not ctype:
            return None
        try:
            boxes = win.descendants(control_type=ctype)
        except Exception:  # noqa: BLE001
            return None
        for box in boxes:
            value = ""
            try:
                value = (box.get_value() or "").strip()
            except Exception:  # noqa: BLE001
                value = _text_of(box)
            if value:
                return value
        return None

    def _result_rows(self, win, conf: dict) -> Optional[list]:
        """검색 결과 **줄 컨트롤들**. 못 찾으면 None(= 못 읽었다).

        목록 컨트롤을 `list_control_types` 차례로 찾아보고, **줄이 든 첫 번째**
        것을 쓴다. 셀렉터가 비어 있으면 아무것도 뒤지지 않는다 — 빈 본으로
        창을 뒤지면 엉뚱한 컨트롤이 잡힌다(`_confirm_snapshot` 과 같은 판단).
        """
        containers = list(conf.get("list_control_types") or [])
        items = list(conf.get("item_control_types") or [])
        if not containers or not items:
            log.warning("room_search 셀렉터가 비어 검색 결과를 찾지 않습니다")
            return None
        want_id = (conf.get("list_auto_id") or "").strip()
        for ctype in containers:
            try:
                found = win.descendants(control_type=ctype)
            except Exception:  # noqa: BLE001
                return None
            for container in found:
                if want_id and _auto_id(container) != want_id:
                    continue
                rows: list = []
                for itype in items:
                    try:
                        rows.extend(container.descendants(control_type=itype))
                    except Exception:  # noqa: BLE001
                        return None
                if rows:
                    return rows
        return None

    def _open_room_verified(self, room_name: str, should_stop=None):
        """방을 찾아 열고 **창 제목이 정확히 일치하는지** 확인한다.

        ★ `send_text` 와 `send_file` 이 **같은 이 자리**를 쓴다. 파일 쪽에 새 길을
          내면 한쪽만 고쳐질 때 오발송 방지가 갈라진다 — 실제로 위험한 것은 그
          갈라짐이다(문구는 막고 파일은 안 막는 상태).

        Sequence (TECH_SPEC §5.2):
          1. focus Kakao main window → **앞 건이 어떻게 끝났든 같은 자리에서**: 그 방
             채팅창이 이미 떠 있으면 닫고(`_close_same_room_windows`), 이 발송기가 열어 둔
             채 끝난 검색창이 있으면 닫는다(`_close_search_box`)
          2. Ctrl+F → paste room_name → wait → 결과 목록이 읽히면 그 방이 섰는지 본다
          3. Enter → open top result
          4. VERIFY **foreground** window title == room_name (exact); mismatch → close + failed
          (0.11.10) 3 에서 아무 방도 안 열리고 메인 창이 그대로 앞이면 — 또는 2 에서 읽은
          목록에 그 방이 없으면 — 열린 검색창을 Esc 로 닫고 2 부터 **한 번 더**
          (`OPEN_ROOM_TRIES`). (0.11.11) 3 에서 **다른 방**(카톡 채팅창)이 열렸으면 그 창만
          닫고 같은 차례로 한 번 더 — 입력란에 키를 넣기 전이다. 다른 앱이 앞이면 멈춘다.

        돌려주는 값: `(채팅창, 실패)`. 실패가 None 이 아니면 **그대로 돌려주고
        끝낸다** — 그 뒤로는 아무 키도 누르지 않는다. 채팅창을 받았으면 다 쓴 뒤
        `_leave_room` 으로 나온다.

        (0.11.12) `should_stop` 을 받으면 **다시 찾기 전에** [중단]을 묻는다 — 다시
        찾기는 몇 초가 걸린다(실기: [중단] 0.4초 뒤 첫 Enter 가 빗나가고, 다시 찾아 약
        7초 뒤 문구가 나갔다). 참이면 키를 더 누르지 않고 `stop_result` 를 돌려준다.
        """
        win = self._kakao_window()
        # ★ 포커스가 확인되지 않으면 키 입력을 하지 않는다.
        #   (브라우저 등 다른 앱에 방 이름이 입력되는 사고 방지)
        if not self._focus_verified(win):
            return None, self._fail(
                room_name,
                "focus_failed: 카카오톡 창을 앞으로 가져오지 못했습니다(전송 안 함, "
                f"{self._focus_cause(win)}). "
                "카톡을 최소화하지 말고 화면에 띄워두세요. "
                "발송 중에는 다른 창을 클릭하지 마세요.",
            )

        # 1) ★ (0.11.10) 앞 건이 어떻게 끝났든 **같은 자리에서** 시작한다. 0.11.9 는
        #    성공한 건의 출구(`_leave_room`)에서만 정리해, room_mismatch · 파일 한 개 실패 ·
        #    예외로 끝난 건 뒤에는 남은 검색창 · 채팅창 위에서 시작했다. Esc 를 눌렀으면
        #    (메인 창이 숨었다 다시 떴을 수 있다) 키를 더 누르기 전에 포커스를 다시 본다.
        self._close_same_room_windows(win, room_name)
        if self._close_search_box(win) and not self._focus_verified(win):
            return None, self._fail(
                room_name,
                "focus_failed: 남은 검색창을 닫은 뒤 카카오톡 창을 다시 앞으로 가져오지 "
                f"못했습니다(전송 안 함, {self._focus_cause(win)})")

        results = "목록 못 읽음"
        missed = ""         # (0.11.12) 첫 시도에 막힌 까닭 — 다시 찾아 열리면 경고로 남긴다
        tries = 0
        for tries in range(1, OPEN_ROOM_TRIES + 1):
            last = tries == OPEN_ROOM_TRIES
            # (0.11.12) 다시 찾기 전 — 검색창은 `_search_again` 이 이미 닫았다
            if tries > 1 and should_stop is not None and should_stop():
                log.warning("[중단] — 방을 다시 찾기 전에 멈춥니다 room=%r", room_name)
                return None, stop_result("방을 다시 찾기 전에 멈췄습니다(전송 안 함)")
            # 2) search — ★ **칸을 비우고** 붙인다(`_put_room_query`).
            #
            #    예전에는 Ctrl+F 뒤에 바로 붙였다. 카톡은 검색칸에 **직전 검색어를
            #    남겨 두어** 앞 방 이름 뒤에 이번 방 이름이 이어 붙었고, 그 글자로는
            #    방이 안 나와 `room_mismatch` 로 떨어졌다(실기 0.11.4). 비워도 **같은 방**
            #    이면 카톡이 결과를 새로 세우지 않는다 — 아래 다시 찾기가 맡는다(0.11.10).
            #    (0.11.12) 다시 찾을 때는 **다른 글자**로 찾는다(`retry_query`).
            self._pyautogui.hotkey(*self.sel.get("search_hotkey", ["ctrl", "f"]))
            self._search_open = True
            time.sleep(self._t("after_search_hotkey", 0.4))
            query = room_name if tries == 1 else retry_query(room_name)
            bad = self._put_room_query(win, room_name, query)
            if bad is not None:
                return None, bad

            # 2-1) (0.11.10) 결과 목록에 그 방이 섰는가 — 읽히면 설 때까지 기다리고, 무엇이
            #      보였는지 남긴다. 읽히는데 끝내 없으면 Enter 전에 한 번 더 찾는다. 못
            #      읽으면(실기 PC — 0.11.1) 그대로 Enter 하고 아래 다시 찾기에 맡긴다.
            #      목록을 읽는 자리는 추측이라(`room_search`) **막는 데는 쓰지 않는다** —
            #      막는 것은 늘 4) 의 앞 창 제목 대조다.
            found, results = self._room_in_results(win, room_name)
            if found is False and not last:
                log.warning("검색 결과에 그 방이 없습니다(%s) — 검색창을 닫고 한 번 더 "
                            "찾습니다 room=%r", results, room_name)
                missed = f"검색 결과에 그 방이 없음({results})"
                if not self._search_again(win):
                    break
                continue

            # 3) open top result — ★ Enter 도 **메인 창이 앞일 때만** 누른다. 결과 목록을
            #    기다리는 사이(2-1) 다른 창이 앞을 가로챌 수 있다 — 그러면 그 창으로 간다.
            if not self._foreground_is_main(win):
                return None, self._fail(
                    room_name,
                    "focus_failed: 검색 중 카카오톡 메인 창이 앞에서 사라졌습니다(전송 안 함). "
                    "발송 중에는 다른 창을 클릭하지 마세요.")
            self._pyautogui.press("enter")
            time.sleep(self._t("after_open_room", 0.8))

            # 4) EXACT title verification (mis-send guard)
            chat = self._opened_chat_window(room_name, win)
            if chat is not None:
                # 방을 열면 카톡이 검색창을 **스스로 닫는다**(0.11.9 실기 — 보낸 뒤의 Esc 가
                # 닫힌 검색창에 떨어져 아무것도 안 지웠다). 열려 있다고 알지 않는다.
                self._search_open = False
                self._retry_note = (f"첫 시도에 {missed} — 다시 찾아 열었습니다"
                                    if missed else "")
                return chat, None
            if not self._foreground_is_main(win):
                # 무엇이 앞에 왔다 — 검색창이 어떤지 모른다(모르는 쪽으로 둔다 —
                # `_close_search_box`). 다른 앱이면 되풀이하지 않는다.
                self._search_open = False
                wrong = self._opened_title_hint(win, room_name)
                if last or not wrong:
                    break
                # (0.11.11) 다른 방(카톡 채팅창)이 열렸다 — 결과가 서기 전에 Enter 가 눌려
                # 대화 목록 맨 위 방이 열린 것으로 본다. 입력란에는 아직 아무것도 안 넣었다.
                # 그 창만 닫고, 검색창을 열었다 아래 다시 찾기의 Esc 로 닫아 검색 상태를
                # 지운다 — 방을 연 뒤 같은 글자로는 결과를 새로 세우지 않는다(0.11.10).
                log.warning("다른 방이 열렸습니다(%r) — 그 창을 닫고 한 번 더 찾습니다 "
                            "room=%r", _clip(wrong), room_name)
                missed = f"다른 방이 열림({_clip(wrong)!r})"
                self._close_wrong_room(win)
                if not self._focus_verified(win):
                    return None, self._fail(
                        room_name,
                        "focus_failed: 다른 방을 닫은 뒤 카카오톡 창을 다시 앞으로 가져오지 "
                        f"못했습니다(전송 안 함, {self._focus_cause(win)})")
                self._pyautogui.hotkey(*self.sel.get("search_hotkey", ["ctrl", "f"]))
                self._search_open = True
                time.sleep(self._t("after_search_hotkey", 0.4))
            elif last:
                break
            else:
                # 아무 방도 안 열렸고 메인 창이 그대로 앞이다 — 실기(0.11.9)에서 같은 방을
                # 연달아 보낼 때 본 그 모양이다. 열린 검색창을 닫고(검색 상태가 지워진다)
                # 다시 찾는다.
                log.warning("Enter 로 방이 열리지 않았습니다(검색 결과: %s) — 검색창을 닫고 "
                            "한 번 더 찾습니다 room=%r", results, room_name)
                missed = f"Enter 로 방이 열리지 않음(검색 결과: {results})"
            if not self._search_again(win):
                break

        # ★ (0.11.6) **실제로 열린 방 제목**을 실패 문구에 붙인다. 방은 찾아
        #   열렸는데(사람 눈에는 "방은 찾는데 붙여 넣지를 못한다") 서버에 적힌
        #   방 이름이 실제 제목과 달라 관문이 막는 경우가 대부분이다 — 실기에서
        #   서버 쪽 이름 뒤에 참여자 이름이 덧붙어 있었다. 무엇으로 고칠지
        #   사람이 바로 보도록 닫기 **전에** 읽는다. 카톡 창일 때만 적는다.
        opened = self._opened_title_hint(win, room_name)
        # ★ (0.11.9) 그 밖이면 **그때 앞에 있던 창 제목**을 적는다. 0.11.8 의
        #   번갈아 실패는 문구가 제목 없이 와서, 방이 안 열린 것인지(앞 창이
        #   `카카오톡`) 다른 창이 앞을 가로챈 것인지 가를 수 없었다.
        seen = _clip(self._foreground_title())
        self._close_wrong_room(win)
        error = "room_mismatch: 열린 방 제목이 정확히 일치하지 않음"
        # ★ (0.11.11) '고치면 나갑니다' 는 열린 제목에 방 이름이 들어 있을 때만(같은 방의 다른
        #   이름) — 다른 사람 방 제목으로 고치면 다음 발송이 그 사람에게 간다.
        if opened and _norm_title(room_name) in _norm_title(opened):
            error += (f" — 실제로 열린 방: {opened!r}. 방 이름을 이 제목과 "
                      f"똑같이 고치면 나갑니다 (전송 안 함)")
        elif opened:
            error += (f" — 다른 방이 열렸습니다: {opened!r}. 방 이름은 그대로 두고 "
                      f"[실패 재시도]를 누르세요 (전송 안 함)")
        elif seen:
            error += f" (전송 안 함, 앞 창: {seen!r})"
        else:
            error += " (전송 안 함, 앞 창 제목을 읽지 못함)"
        # (0.11.10) 그때 결과 목록에 무엇이 있었는지 · 다시 찾았는지 — 다음 실기 실패가
        #   무엇을 보았는지 말하게.
        error += f" · 검색 결과: {results}"
        if tries > 1:
            error += " · 다시 찾아도 안 열림"
        return None, self._fail(room_name, error)

    def _search_again(self, win) -> bool:
        """다시 찾기 전 — 열린 검색창을 Esc 로 닫고(`_close_search_box`) 메인 창 포커스를
        다시 잡는다. 둘 중 하나라도 안 되면 False — 키를 더 누르지 않는다."""
        return self._close_search_box(win) and self._focus_verified(win)

    def _room_in_results(self, win, room_name: str):
        """방을 열기 전 검색 결과 목록 — `(그 방이 섰나, 적어 둘 한 줄)` (0.11.10).

        섰나: `True` · `False`(읽었는데 제목이 글자까지 같은 줄이 없다) · `None`(목록을
        못 읽었다 — 0줄일 수도 있다). 읽히면 그 방 줄이 설 때까지 `room_search_wait` 만큼
        기다린다 — 결과는 한 박자 늦게 선다(`_search_titles` 머리말). **처음부터 못 읽으면
        기다리지 않는다** — 목록을 못 읽는 PC 에서 건마다 시간을 버리지 않게.

        적어 둘 한 줄은 로그와 room_mismatch 문구에 붙는다 — `3줄, 맨 위 '…'`.
        """
        conf = self.room_search_conf
        want = _norm_title(room_name)
        ctype = conf.get("item_text_control_type", "Text")
        deadline = time.monotonic() + self._t("room_search_wait", 2.0)
        titles: Optional[List[str]] = None
        found = False
        while True:
            rows = self._result_rows(win, conf)
            if rows is not None:
                titles = [row_title(r, ctype) for r in rows[:_max_rows(conf)]]
                found = any(_norm_title(t) == want for t in titles)
            if found or titles is None or time.monotonic() >= deadline:
                break
            time.sleep(self._t("room_search_poll", 0.15))
        if titles is None:
            log.info("방 열기 전 검색 결과: 목록 못 읽음 room=%r", room_name)
            return None, "목록 못 읽음"
        note = (f"{len(titles)}줄, 맨 위 {_clip(titles[0])!r}" if titles else "0줄")
        log.info("방 열기 전 검색 결과: %s room=%r", note, room_name)
        return found, note

    def _close_wrong_room(self, win) -> None:
        """제목이 어긋난 채 끝날 때 — **카톡 창에만** 손댄다 (0.11.10).

        0.11.9 까지는 앞에 무엇이 있든 Esc 를 눌렀다(`_safe_close`) — 그사이 다른 앱이
        앞을 가로챘으면 그 Esc 가 그 앱으로 갔다.

          · 앞 창이 카톡의 **채팅창**(다른 방이 열렸다) — 그 창 하나만 닫는다
            (`_close_chat_window` — 앞에 있으면 Esc, 아니면 WM_CLOSE)
          · 앞 창이 **메인 창**(아무 방도 안 열렸다) — 열어 둔 검색창만 닫는다
            (`_close_search_box` — 열려 있다고 알 때만)
          · 그 밖(다른 앱 · 모름 · `카카오톡` 으로 시작하는 카톡의 다른 창) — **아무 키도
            누르지 않는다.** 남은 것은 다음 건이 시작할 때 정리한다
        """
        if self._foreground_is_main(win):
            self._close_search_box(win)
            return
        hwnd = self._foreground_hwnd()
        pid = self._window_pid(win)
        title = self._hwnd_title(hwnd) if hwnd else ""
        main_title = self.sel.get("main_window_title_kw", "카카오톡")
        if (hwnd and pid and self._hwnd_pid(hwnd) == pid and title.strip()
                and not title.startswith(main_title)):
            self._close_chat_window(hwnd, title)

    def _focus_cause(self, win) -> str:
        """focus_failed 의 까닭 한 토막 (0.11.9). 실패 문구만 보고 무엇이 막았는지
        알게 한다 — 메인 창이 트레이로 숨었는지, 다른 창이 앞을 쥐고 있는지.

        숨었는지는 **보이는 창 목록**으로 본다. 숨은 창은 pywinauto 가 핸들로도 못
        잡을 수 있다(`win.handle` 이 던진다)."""
        want = self.sel.get("main_window_title_kw", "카카오톡")
        shown = self._top_windows()
        if shown is not None and not any((title or "").strip() == want
                                         for title, _pid in shown.values()):
            return "카톡 메인 창이 숨어 있음 — 트레이 아이콘을 눌러 다시 여세요"
        seen = _clip(self._foreground_title())
        return f"앞 창: {seen!r}" if seen else "앞 창 제목 없음 — 화면 잠금·절전일 수 있음"

    def _close_same_room_windows(self, win, room_name: str) -> None:
        """그 방 채팅창이 **이미 떠 있으면** 먼저 닫는다 — 키 대신 WM_CLOSE.

        ★ (0.11.9) 떠 있는 방을 검색해 Enter 를 누르면 카톡이 그 창을 앞으로
          올려 줄지는 아무도 확인하지 않았다. 안 올리면 앞 창 대조
          (`_opened_chat_window`)가 막아 안전하게 실패하지만, 그 방으로는 계속
          안 나간다. 닫고 열면 늘 **방금 연 창 하나**가 앞에 온다 — 사람이 열어 둔
          창이든 앞 건이 못 닫은 창이든 같다.

        카톡 프로세스의 창이고 제목이 **글자까지 같은** 것만 닫는다(다른 앱의 폴더
        창 제목이 방 이름과 같을 수 있다). 프로세스를 모르면 아무것도 닫지 않는다.
        """
        pid = self._window_pid(win)
        if not pid:
            return
        try:
            main = int(getattr(win, "handle", 0) or 0)
        except Exception:  # noqa: BLE001
            main = 0
        stale = [hwnd for hwnd, (title, wpid) in (self._top_windows() or {}).items()
                 if hwnd != main and wpid == pid and (title or "").strip() == room_name]
        for hwnd in stale:
            log.info("이미 떠 있는 같은 방 창을 닫고 새로 엽니다 room=%r hwnd=%s",
                     room_name, hwnd)
            self._post_close(hwnd)
        if stale:
            time.sleep(self._t("after_close_chat", 0.3))

    def _leave_room(self, chat, room_name: str) -> None:
        """다 쓴 방에서 나온다 — 채팅창을 닫는다. 메인 창 검색창은 **열려 있을 때만** 닫는다.

        ★ (0.11.10) 0.11.9 는 채팅창을 닫은 뒤 메인 창에 Esc 를 늘 눌러 검색창까지 닫았다
          — 같은 방으로 연달아 보내면 한 건 걸러 실패하던 것(시험 서버 0.11.8)을 그것으로
          고쳤다고 봤다. 실기(0.11.9, 10/17)에서 그래도 번갈았다: 카톡은 방을 열며 검색창을
          **스스로 닫고**, 그 Esc 는 닫힌 검색창에 떨어져 검색 상태를 못 지웠다. 닫힌
          검색창에 누른 Esc 는 메인 창을 숨기기까지 한다(늦게 — `_close_search_box`).
          같은 방 다시 찾기는 이제 `_open_room_verified` 가 맡는다(Enter 로 안 열리면 열린
          검색창을 닫고 한 번 더). 여기서는 이 발송기가 열어 둔 줄 **아는** 검색창만 닫는다
          — 방을 열었으면 그런 검색창은 없다.

        닫는 차례: 그 채팅창 **하나만** 닫고(`_close_chat_window` — 앞에 있으면 Esc,
        아니면 WM_CLOSE) → 열린 검색창이 있다고 알면 메인 창이 앞일 때만 Esc
        (`_close_search_box`). 확인이 안 되면 키를 누르지 않는다.

        보낸 **뒤**의 정리라 여기서 무엇이 실패해도 결과를 바꾸지 않는다 —
        이미 나간 것을 실패로 적으면 다시 보내 겹친다.
        """
        try:
            hwnd = int(getattr(chat, "handle", 0) or 0)
        except Exception:  # noqa: BLE001
            hwnd = 0
        try:
            if hwnd:
                self._close_chat_window(hwnd, room_name)
            else:
                self._safe_close()
            self._close_search_box(self._kakao_window())
        except Exception:  # noqa: BLE001
            log.exception("방에서 나오다 실패했습니다(결과는 그대로) room=%r", room_name)

    def _opened_title_hint(self, win, room_name: str) -> str:
        """방 제목이 어긋났을 때 **앞에 떠 있는 카톡 창의 제목** (없으면 "").

        카톡 프로세스의 창이 아니거나, 메인 창(`카카오톡`)이거나, 기대한 제목과
        같으면 비운다 — 엉뚱한 앱 제목을 "열린 방" 이라고 알려 주지 않는다.
        """
        try:
            title = (self._foreground_title() or "").strip()
            if not title or title == room_name or title.startswith("카카오톡"):
                return ""
            main_pid = self._window_pid(win)
            fg_pid = self._hwnd_pid(self._foreground_hwnd())
            if not main_pid or fg_pid != main_pid:
                return ""
            return title[:200]
        except Exception:  # noqa: BLE001
            return ""

    def _put_room_query(self, win, room_name: str, query: str) -> Optional[SendResult]:
        """검색어(`query` — 첫 시도는 방 이름, 다시 찾을 때는 `retry_query`)를 검색칸에
        **비우고** 넣는다. 못 넣었으면 실패를 돌려준다.

        방 검색(`_read_search`)과 **같은 자리**(`_put_query`)로 비운다 — UIA 로
        먼저, 안 되면 End → Shift+Home → Backspace. Ctrl+A 는 누르지 않는다.

        넣은 뒤 검색칸을 되읽어 **남의 글자가 섞였으면** 한 번 더 비우고 넣고,
        그래도 섞여 있으면 **Enter 를 누르지 않는다.** 엉뚱한 글자로 연 방은
        어차피 제목 대조에서 막히지만, 막힌 이유가 '방 이름이 틀렸다' 로
        보여 사람이 멀쩡한 방 이름을 고치러 간다.

        되읽은 글자가 넣은 글자의 **앞부분**이면 통과시킨다 — 카톡이 긴 글자를
        잘라 보여 주는 빌드가 있을 수 있고, 그때 막으면 모든 건이 안 나간다.
        직전 검색어가 남은 경우(`앞 방 이름` + `이번 방 이름`)는 앞부분이 아니라
        여기서 걸린다. 못 읽으면(None) 판단하지 않는다(`_search_input_text`).
        """
        conf = self.room_search_conf
        lost = self._fail(
            room_name,
            "focus_failed: 검색 중 카카오톡 메인 창이 앞에서 사라졌습니다(전송 안 함). "
            "발송 중에는 다른 창을 클릭하지 마세요.")
        if not self._put_query(win, query, conf):
            return lost
        typed = self._search_input_text(win, conf)
        if query_was_typed(typed, query):
            return None
        log.warning("검색칸 글자가 넣은 글자와 다릅니다(읽은 값=%r, 넣은 값=%r) — "
                    "비우고 한 번 더 넣습니다", typed, query)
        if not self._focus_verified(win):
            # 포커스를 잃었다 — Esc 도 누르지 않는다(다른 앱으로 간다).
            return lost
        if not self._put_query(win, query, conf):
            return lost
        typed = self._search_input_text(win, conf)
        if query_was_typed(typed, query):
            return None
        self._close_search()
        return self._fail(
            room_name,
            "search_not_cleared: 카톡 검색칸에 다른 글자가 남아 방을 열지 "
            f"않았습니다(전송 안 함, 읽은 값={typed!r})")

    def send_text(self, room_name: str, text: str, should_stop=None) -> SendResult:
        """Open the room by exact name and send `text` (drive links are plain text).

        방을 열고 제목을 확인하는 자리는 `_open_room_verified` 하나다
        (`send_file` 과 같은 자리). 여기서는 그 뒤 — 붙여넣기 → Enter → 닫기.
        """
        try:
            chat, bad = self._open_room_verified(room_name, should_stop)
            if bad is not None:
                return bad

            # (0.11.12) 방을 연 뒤 넣기 **직전** — 여는 사이 누른 [중단]을 듣는다
            if should_stop is not None and should_stop():
                log.warning("[중단] — 문구를 넣기 전에 멈춥니다 room=%r", room_name)
                self._leave_room(chat, room_name)
                return stop_result("문구를 넣기 전에 멈췄습니다(전송 안 함)")

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
                self._leave_room(chat, room_name)
                return self._fail(
                    room_name,
                    "input_not_filled: 입력창에 본문이 들어가지 않았습니다(전송 안 함)",
                )

            self._pyautogui.press("enter")
            time.sleep(self._t("after_send", 0.4))

            # 6) ★ 전송 검증: 입력창이 비워졌으면 전송된 것으로 본다.
            leftover = self._input_text(chat)
            if leftover is not None and leftover.strip():
                self._leave_room(chat, room_name)
                return self._fail(
                    room_name,
                    "send_not_confirmed: 전송 후에도 입력창에 본문이 남아 있습니다",
                )

            # 7) 채팅창을 닫는다(열린 검색창이 있다고 알면 그것도) — 다음 건은 시작할
            #    때 한 번 더 같은 자리로 맞춘다(`_open_room_verified` 의 1)
            self._leave_room(chat, room_name)
            return SendResult(ok=True, warning=self._retry_note or None)
        except Exception as exc:  # noqa: BLE001
            log.exception("send_text error room=%r", room_name)
            return self._fail(room_name, f"exception: {exc}")

    # ══════════════════════════════════════════════════════════════════════
    #  파일 첨부 — ⚠ 실기 확인 전. **관문을 통과하지 못하면 무조건 취소한다.**
    # ══════════════════════════════════════════════════════════════════════

    def send_file(self, room_name: str, file_names, should_stop=None) -> SendResult:
        """IR 자료를 첨부해 보낸다. **관문을 통과할 때만 보낸다.**

        `file_names` 는 **공통 폴더 안의 파일명**이다(경로가 아니다). 실제 자리는
        이 PC 가 설정한 뿌리로 조립한다 — mac 과 **같은 빗장**을 쓴다
        (`agent/sender/base.py: resolve_ir_file`). 규칙에 어긋나는 이름이나 이
        PC 에 없는 파일은 **카톡을 건드리기 전에** 거절한다.

        **한 번에 한 파일씩** 보낸다. 열기 창에서 여러 개를 한꺼번에 고를 수
        있지만 그러면 `파일 전송` 카드에 여러 개가 뜨고, 카톡이
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
            chat, bad = self._open_room_verified(room_name, should_stop)
            if bad is not None:
                return bad

            notes = [self._retry_note]      # 성공했지만 남길 말(파일명을 못 읽은 카드 따위)
            for n, path in enumerate(resolved, start=1):
                # (0.11.12) 파일 하나 앞마다 [중단]을 다시 묻는다(`Sender.send_file`)
                if should_stop is not None and should_stop():
                    log.warning("[kakao_windows] [중단] — 파일 %d/%d 앞에서 멈춥니다 room=%r",
                                n, len(resolved), room_name)
                    self._leave_room(chat, room_name)
                    return stop_result(f"파일 {n - 1}/{len(resolved)}개를 보낸 뒤 "
                                       f"멈췄습니다", n - 1)
                result = self._send_one_file(room_name, chat, path, should_stop)
                if result.stopped is not None:
                    # 열기 창 · 카드까지 왔다가 [중단] — 닫고 나왔다(`_send_one_file`)
                    self._leave_room(chat, room_name)
                    return stop_result(f"파일 {n - 1}/{len(resolved)}개를 보낸 뒤 "
                                       f"멈췄습니다", n - 1)
                if not result.ok:
                    if n > 1:
                        result.error = (f"{n - 1}개를 보낸 뒤 {n}번째에서 실패 "
                                        f"— {result.error}")
                    return result
                notes.append(result.warning)

            self._leave_room(chat, room_name)
            log.info("[kakao_windows] SENT FILES room=%r files=%s",
                     room_name, [p.name for p in resolved])
            return SendResult(ok=True, warning=" · ".join(w for w in notes if w) or None)
        except Exception as exc:  # noqa: BLE001
            log.exception("send_file error room=%r", room_name)
            return self._fail(room_name, f"exception: {exc}")

    def _send_one_file(self, room_name: str, chat, path, should_stop=None) -> SendResult:
        """파일 하나 — 첨부 단추 → 열기 창에 전체 경로 → [열기] → `파일 전송` 카드의 [1개 전송].

        카드의 관문이 어긋나면 **닫고 아무것도 보내지 않는다.** [중단]은 [열기] 앞과
        [1개 전송] 앞에서 한 번씩 더 듣는다.
        """
        self.ui_dump = []           # 진단은 이 파일 한 개 것만 — 실패하면 여기서 멈춘다
        conf = self.file_send_conf
        before = self._top_windows()

        # ③ 첨부 단추 → ④ 열기 창
        dlg, how = self._open_file_dialog(chat, room_name, before, conf)
        if not dlg:
            self._note_windows(chat, before, "실패: open_dialog_not_shown", failing=True)
            if how:
                self._safe_close()  # 다른 판이 열렸을 수 있다 — Esc
            return self._fail(room_name,
                              f"open_dialog_not_shown: 첨부({how or '못 누름'}) 뒤 열기 "
                              f"창이 뜨지 않았습니다 (전송 안 함)")
        self._note_windows(chat, before, f"열기 창 ({how})")

        def back_out(error: str) -> SendResult:
            # 진단을 먼저 뜬다 — 물러나면(취소) 그 창은 사라진다.
            self._note_windows(chat, before, f"실패: {error.split(':')[0]}", failing=True)
            self._cancel_open_dialog(dlg, conf)
            return self._fail(room_name, error)

        owner = self._owner_hwnd(dlg)
        if owner not in (0, _handle(chat)):
            return back_out(f"open_dialog_foreign: 열기 창을 띄운 창이 그 방 채팅창이 "
                            f"아닙니다 (주인 {_clip(self._hwnd_title(owner))!r}) (전송 안 함)")

        if should_stop is not None and should_stop():
            log.warning("[중단] — 열기 창을 취소합니다 room=%r file=%r", room_name, path.name)
            self._cancel_open_dialog(dlg, conf)
            return stop_result("열기 창을 취소했습니다(전송 안 함)")

        # ⑤ 파일 이름 칸에 전체 경로 → **되읽어 견준 뒤** [열기]
        typed = self._put_file_name(dlg, str(path), conf)
        if typed is None or nfc(typed) != nfc(str(path)):
            return back_out(f"file_name_not_set: 열기 창의 파일 이름 칸에 경로가 들어가지 "
                            f"않았습니다 (읽힌 값 {typed!r}) (전송 안 함)")
        opened_at = self._top_windows()     # 이 뒤에 뜬 창이 `파일 전송` 카드 후보다
        if not self._click_by_id(dlg, conf.get("open_button_id"), "열기"):
            return back_out("open_button_not_clicked: 열기 창의 [열기] 단추를 누르지 "
                            "못했습니다 (전송 안 함)")
        if not self._wait_gone(dlg, self._t("open_dialog_wait", 5.0)):
            return back_out("open_dialog_stuck: [열기] 뒤에도 열기 창이 그대로입니다 — "
                            "파일을 못 찾았을 수 있습니다 (전송 안 함)")

        # ⑥ ★ 카톡 `파일 전송` 카드 — **못 찾는 것도 실패다.**
        card = self._wait_confirm(chat, opened_at)

        def refuse(error: str) -> SendResult:
            self._note_windows(chat, opened_at, f"실패: {error.split(':')[0]}",
                               failing=True)
            self._dismiss_confirm(card)
            return self._fail(room_name, error)

        if not card.get("present"):
            # 카드가 떠 있는데 못 읽은 것일 수 있다 — Esc 로 닫는다(남기면 다음 문구 때
            # 채팅창이 닫히며 함께 사라진다. 나가지는 않는다).
            return refuse("confirm_window_not_shown: [열기] 뒤 '파일 전송' 창을 찾지 "
                          "못했습니다 — Esc 로 닫았습니다 (전송 안 함)")
        self._note_windows(chat, opened_at, "파일 전송 창")

        refused = unsendable_detail(card, conf)
        if refused is not None:
            return refuse(f"file_refused: 카톡이 파일을 받지 않았습니다(전송 불가) — "
                          f"{refused} (전송 안 함)")
        reason, note = check_file_card(card, [path.name], conf)
        if reason:
            log.warning("파일 전송 창이 어긋났습니다 — 닫습니다: %s | card=%r", reason, card)
            return refuse(f"gate_blocked: {reason} — 닫았습니다 (전송 안 함)")
        if note:
            log.warning("%s | card=%r", note, card)

        # ⑦ 누르기 **직전** — 그 사이 누른 [중단]을 듣는다
        if should_stop is not None and should_stop():
            log.warning("[중단] — 파일 전송 창을 닫습니다 room=%r file=%r",
                        room_name, path.name)
            self._dismiss_confirm(card)
            return stop_result("파일 전송 창을 닫았습니다(전송 안 함)")

        button = _send_button(card, conf)[0]
        if not self._click_dialog_button(card, button):
            return refuse(f"send_button_not_clicked: {button!r} 단추를 누르지 "
                          f"못했습니다 (전송 안 함)")
        time.sleep(self._t("after_confirm_click", 1.0))

        # 카드가 닫혔나. 여기까지가 사후 확인의 한계다 — 보낸 뒤 파일 메시지 줄에서
        # 파일명을 읽는 길은 mac 에서도 없었다.
        if self._is_window_visible(card.get("hwnd")):
            return refuse(
                f"send_unconfirmed: {button!r} 을 눌렀지만 파일 전송 창이 그대로입니다 — "
                f"닫아서 정리했습니다. 카톡을 직접 확인하세요 — 다시 보내면 "
                f"겹칠 수 있습니다")
        log.info("파일 전송 창의 %r 을 눌렀습니다 room=%r file=%r", button, room_name,
                 path.name)
        return SendResult(ok=True, warning=note or None)

    # --- 파일 첨부에 쓰는 자리들 (시험에서 갈아 끼우는 이음매) ---------------

    @property
    def file_send_conf(self) -> dict:
        """첨부 화면의 모양. 기본값 위에 `selectors.yaml: file_send` 를 덮는다."""
        conf = dict(FILE_SEND_DEFAULTS)
        conf.update(self.sel.get("file_send") or {})
        return conf

    def _open_file_dialog(self, chat, room_name: str, before, conf: dict):
        """첨부 단추를 눌러 열기 창을 띄운다. `(열기 창 hwnd 또는 0, 누른 방법)`.

        누르는 차례: 채팅창 속 **이름이 첨부 단추인 Button 하나**(UIA — 그 자리 한가운데를
        누른다) → 열기 창이 안 뜨면 그 단추의 단축키(Ctrl+T). 둘 다 **앞 창이 그 채팅창일
        때만** 누른다 — 두 번째 파일 앞에서는 카드가 막 닫힌 뒤라 무엇이 앞인지 모른다.
        화면 좌표를 짐작해 누르지 않는다 — 창 크기·배율이 PC 마다 달라 엉뚱한 아이콘
        (`+` · 이모티콘)이 눌린다. 누른 방법은 로그와 진단에 남는다.
        """
        tried = ""
        for how in ("첨부 단추(UIA)", "단축키 " + "+".join(conf.get("attach_hotkey") or [])):
            if not self._chat_in_front(chat, room_name):
                log.warning("첨부 직전 앞 창이 채팅창이 아닙니다: %r", self._foreground_title())
                return 0, tried
            if how.startswith("첨부"):
                button = self._attach_button(chat, conf)
                if button is None:
                    continue
                try:
                    button.click_input()
                except Exception as exc:  # noqa: BLE001
                    log.warning("첨부 단추를 누르지 못했습니다: %s", exc)
                    continue
            elif conf.get("attach_hotkey"):
                self._pyautogui.hotkey(*conf["attach_hotkey"])
            else:
                continue
            tried = how
            log.info("파일 첨부: %s 로 열기 창을 엽니다", how)
            dlg = self._wait_open_dialog(chat, before, conf)
            if dlg:
                return dlg, how
        return 0, tried

    def _chat_in_front(self, chat, room_name: str) -> bool:
        hwnd = _handle(chat)
        if hwnd and self._foreground_hwnd() == hwnd:
            return True
        self._focus_verified(chat, room_name)
        return bool(hwnd) and self._foreground_hwnd() == hwnd

    def _attach_button(self, chat, conf: dict):
        """채팅창 속 첨부 단추 — 이름이나 도움말이 `attach_button_re` 인 Button **하나.**
        없거나 여럿이면 None(그러면 단축키로 간다)."""
        rx = _rx(conf.get("attach_button_re"))
        try:
            hits = [b for b in chat.descendants(control_type="Button")
                    if _hit(rx, _control_label(b))]
        except Exception:  # noqa: BLE001
            return None
        if len(hits) != 1:
            log.info("첨부 단추를 UIA 로 %d개 찾았습니다 — 단축키로 갑니다", len(hits))
            return None
        return hits[0]

    def _wait_open_dialog(self, chat, before, conf: dict) -> int:
        """새로 뜬 **열기 창 하나** — 카톡 프로세스 · 제목 `open_dialog_title_re` ·
        클래스 `open_dialog_class`. 없거나 여럿이면 0."""
        pid = self._window_pid(chat) if chat is not None else 0
        title_rx = _rx(conf.get("open_dialog_title_re"))
        want_class = conf.get("open_dialog_class") or ""
        deadline = time.monotonic() + self._t("open_dialog_wait", 5.0)
        while True:
            found = [hwnd for hwnd, (title, wpid) in (self._top_windows() or {}).items()
                     if pid and wpid == pid and (before is None or hwnd not in before)
                     and _hit(title_rx, title)
                     and (not want_class or self._hwnd_class(hwnd) == want_class)]
            if len(found) == 1:
                return found[0]
            if len(found) > 1:
                log.warning("열기 창이 %d개라 고르지 않습니다: %r", len(found), found)
                return 0
            if time.monotonic() >= deadline:
                return 0
            time.sleep(self._t("room_search_poll", 0.15))

    def _put_file_name(self, dlg, path: str, conf: dict) -> Optional[str]:
        """열기 창의 `파일 이름` 칸(AutomationId `file_name_edit_id`)에 경로를 넣고
        **되읽은 값**을 돌려준다. 칸을 못 찾거나 못 넣으면 None."""
        try:
            dialog = self._desktop.window(handle=dlg)
            edits = [e for e in dialog.descendants(control_type="Edit")
                     if _auto_id(e) == str(conf.get("file_name_edit_id") or "")]
            if len(edits) != 1:
                log.warning("열기 창의 파일 이름 칸이 %d개입니다", len(edits))
                return None
            edits[0].set_edit_text(path)
            return _box_value(edits[0])
        except Exception as exc:  # noqa: BLE001
            log.warning("열기 창의 파일 이름 칸에 넣지 못했습니다: %s", exc)
            return None

    def _click_by_id(self, hwnd, auto_id, what: str) -> bool:
        """그 창의 단추(Button · SplitButton) 중 AutomationId 가 `auto_id` 인 것 **하나**를
        누른다 — UIA Invoke, 안 되면 그 자리 한가운데를 클릭."""
        try:
            dialog = self._desktop.window(handle=hwnd)
            hits = [b for kind in ("Button", "SplitButton")
                    for b in dialog.descendants(control_type=kind)
                    if _auto_id(b) == str(auto_id or "")]
            if len(hits) != 1:
                log.warning("%r 단추(id=%r)가 %d개라 누르지 않습니다", what, auto_id, len(hits))
                return False
            try:
                hits[0].invoke()
            except Exception:  # noqa: BLE001
                hits[0].click_input()
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("%r 단추를 누르지 못했습니다: %s", what, exc)
            return False

    def _wait_gone(self, hwnd, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while self._is_window_visible(hwnd):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)
        return True

    def _cancel_open_dialog(self, dlg, conf: dict) -> None:
        """열기 창에서 물러난다 — 그 창이 띄운 알림(파일을 찾을 수 없음 따위)을 닫고
        [취소], 안 되면 그 창에 WM_CLOSE. 키는 누르지 않는다."""
        for hwnd in list((self._top_windows() or {})):
            if self._owner_hwnd(hwnd) == dlg:
                self._post_close(hwnd)
        if self._wait_gone(dlg, 0) or (
                self._click_by_id(dlg, conf.get("cancel_button_id"), "취소")
                and self._wait_gone(dlg, self._t("after_close_chat", 0.3) + 1.0)):
            return
        self._post_close(dlg)

    def _wait_confirm(self, chat, before) -> dict:
        """`파일 전송` 카드가 뜨기를 기다린다. 안 뜨면 마지막으로 본 것을 그대로 돌려준다.

        창만 뜨고 단추가 아직 안 읽히면 조금 더 기다린다(끝까지 안 읽히면 그대로).
        **없는 것을 있는 것으로 만들지 않는다** — 부르는 쪽이 그것을 보고 멈춘다.
        """
        deadline = time.monotonic() + self._t("confirm_wait", 5.0)
        while True:
            snapshot = self._confirm_snapshot(chat, before)
            if (snapshot.get("present") and snapshot.get("buttons")) \
                    or time.monotonic() >= deadline:
                return snapshot
            time.sleep(0.2)

    def _dialog_candidates(self, chat, before, conf: dict) -> List[tuple]:
        """`파일 전송` 카드**일 수 있는** 창들 `(hwnd, 제목, 주인 hwnd)`. 속은 아직 안 본다.

          · 카톡 프로세스(pid)의 보이는 창 중 — [열기] 전에 없던 창 · 채팅창이 띄운
            (owner) 창 · 제목이 `confirm_title_re` 인 창
          · 채팅창 **속** 창(자식 창) 중 제목이 `confirm_title_re` 인 것
        프로세스를 모르면 채팅창이 띄운 창과 채팅창 속 창만 본다.
        """
        chat_hwnd = _handle(chat)
        pid = self._window_pid(chat) if chat is not None else 0
        title_rx = _rx(conf.get("confirm_title_re"))
        out = []
        for hwnd, (title, wpid) in (self._top_windows() or {}).items():
            if hwnd == chat_hwnd or (pid and wpid != pid):
                continue
            owner = self._owner_hwnd(hwnd)
            owned = bool(chat_hwnd) and owner == chat_hwnd
            new = before is not None and hwnd not in before
            if owned or (pid and (new or _hit(title_rx, title))):
                out.append((hwnd, title or "", owner))
        for hwnd, title in self._child_windows(chat_hwnd):
            if _hit(title_rx, title):
                out.append((hwnd, title, chat_hwnd))
        return out

    def _confirm_snapshot(self, chat, before) -> dict:
        """지금 떠 있는 `파일 전송` 카드를 읽는다.

        실기 화면(10/20): 채팅창 위에 뜨는 카드 — 제목 `파일 전송` · [×] · 파일 줄
        (`시험자료.pdf` · `149KB` · `⋮`) · 넓은 [1개 전송] 하나. `전송 불가` 면 `전송 불가 1` ·
        까닭 · [확인] 하나. ⚠ 그 카드가 UIA 로 무엇을 드러내는지는 아직 모른다 — 그래서
        뜰 때와 실패할 때 창들을 떠 둔다(`_note_windows`).

        후보(`_dialog_candidates`) 중 제목(창 제목이나 카드 속 글자)이 맞거나 · 보내기
        단추가 있거나 · `전송 불가` 글자가 든 창이 **딱 하나**일 때만 그 창을 읽는다.
        없거나(0) 여럿이면(2+) 어느 것인지 모른다 — 고르지 않는다(`present=False`).

        돌려주는 모양:
            present   카드를 찾았는가
            hwnd      그 창 — 단추를 누르고 닫혔는지 보는 자리
            title     그 창의 제목
            owner     그 창을 띄운 창(hwnd) — 진단용
            buttons   단추 이름들
            texts     창 안의 모든 컨트롤 이름 (제목 · 파일명이 여기 나오기를 기대한다)
        """
        blank = {"present": False, "hwnd": 0, "title": "", "owner": 0,
                 "buttons": [], "texts": []}
        conf = self.file_send_conf
        try:
            title_rx = _rx(conf.get("confirm_title_re"))
            found = []
            for hwnd, title, owner in self._dialog_candidates(chat, before, conf):
                dialog = self._desktop.window(handle=hwnd)
                shape = {"title": title,
                         "buttons": _control_texts(dialog, "Button"),
                         "texts": _control_texts(dialog)}
                if (_titled(shape, title_rx) or _send_button(shape, conf)
                        or unsendable_detail(shape, conf) is not None):
                    found.append(dict(shape, present=True, hwnd=hwnd, owner=owner))
            if len(found) != 1:
                if found:
                    log.warning("파일 전송 창 후보가 %d개라 고르지 않습니다: %r", len(found),
                                [(f["hwnd"], f["title"], f["buttons"]) for f in found])
                return blank
            return found[0]
        except Exception as exc:  # noqa: BLE001
            log.warning("파일 전송 창을 읽지 못했습니다(전송 안 함): %s", exc)
            return blank

    def _owner_hwnd(self, hwnd) -> int:
        """그 창을 띄운 **주인(owner) 창.** 없거나 못 읽으면 0.

        mac 에서는 시트가 방 창에 붙어 있어 앞 창 제목이 곧 방 이름이었다.
        Windows 의 대화 상자는 제 창이라 주인 창을 물어봐야 한다.
        """
        try:
            import win32gui  # type: ignore

            GW_OWNER = 4
            return int(win32gui.GetWindow(hwnd, GW_OWNER) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _child_windows(self, hwnd) -> List[tuple]:
        """그 창 **속** 보이는 자식 창들 `[(hwnd, 제목)]`. 못 읽으면 빈 목록."""
        if not hwnd:
            return []
        try:
            import win32gui  # type: ignore
        except Exception:  # noqa: BLE001
            return []
        out: list = []

        def _collect(child, _):
            try:
                if win32gui.IsWindowVisible(child):
                    out.append((child, win32gui.GetWindowText(child) or ""))
            except Exception:  # noqa: BLE001
                pass
            return True

        try:
            win32gui.EnumChildWindows(hwnd, _collect, None)
        except Exception:  # noqa: BLE001
            return []
        return out

    def _hwnd_class(self, hwnd) -> str:
        """창 클래스 이름(열기 창은 `#32770`). 못 읽으면 ""."""
        try:
            import win32gui  # type: ignore

            return win32gui.GetClassName(hwnd) or ""
        except Exception:  # noqa: BLE001
            return ""

    def _hwnd_line(self, hwnd) -> str:
        """진단 한 줄: 창 제목 · 클래스 · 자리(rect). 못 읽는 칸은 '?'."""
        rect = "?"
        try:
            import win32gui  # type: ignore

            rect = tuple(win32gui.GetWindowRect(hwnd))
        except Exception:  # noqa: BLE001
            pass
        return (f"hwnd={hwnd} {_clip(self._hwnd_title(hwnd), 60)!r} "
                f"class={self._hwnd_class(hwnd) or '?'!r} rect={rect}")

    def _click_dialog_button(self, snapshot: dict, name: str) -> bool:
        """카드(`snapshot['hwnd']`)의 단추를 **컨트롤로** 누른다.

        이름이 같은 단추가 **딱 하나**일 때만. `click_input` 은 그 컨트롤의 자리
        한가운데를 누른다 — 화면 좌표를 짐작해 누르지 않는다.
        """
        hwnd = (snapshot or {}).get("hwnd")
        if not hwnd:
            return False
        try:
            dialog = self._desktop.window(handle=hwnd)
            hits = [b for b in dialog.descendants(control_type="Button")
                    if _norm_button(_text_of(b)) == _norm_button(name)]
            if len(hits) != 1:
                log.warning("파일 전송 창에서 %r 단추가 %d개라 누르지 않습니다", name, len(hits))
                return False
            hits[0].click_input()
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("파일 전송 창 단추를 누르지 못했습니다(%r): %s", name, exc)
            return False

    def _dismiss_confirm(self, snapshot: Optional[dict]) -> None:
        """보내지 않고 물러난다.

        카드를 알면: `전송 불가` 카드는 [확인], 그 밖에는 [×](`close_button_re`) — `⋮`
        메뉴나 이름 모를 단추는 누르지 않는다. 안 되면 그 창에만 WM_CLOSE. 그래도
        남았거나 카드를 모르면 Esc.
        """
        conf = self.file_send_conf
        snapshot = snapshot or {}
        hwnd = snapshot.get("hwnd")
        if hwnd:
            key = ("dismiss_button_re" if unsendable_detail(snapshot, conf) is not None
                   else "close_button_re")
            picks = _match_buttons(snapshot.get("buttons", []), conf.get(key, ""))
            if picks and self._click_dialog_button(snapshot, picks[0]):
                time.sleep(self._t("after_close_chat", 0.3))
                if not self._is_window_visible(hwnd):
                    return
            self._post_close(hwnd)
            time.sleep(self._t("after_close_chat", 0.3))
            if not self._is_window_visible(hwnd):
                return
        try:
            self._pyautogui.press("esc")
        except Exception:  # noqa: BLE001
            pass

    # --- 파일 첨부 진단 ---------------------------------------------------------

    def _note_windows(self, chat, before, label: str, failing: bool = False) -> None:
        """카톡 창들과 그 속 컨트롤을 떠서 `ui_dump` 에 더한다 — 진단 기록에 실린다.

        실패는 늘, 성공 길(열기 창 · 카드)은 **실기 확인 전(`verified: false`)에만** 뜬다.
        로그에는 창 줄만(단추 이름 포함) 남기고, 전체는 `agent_logs/` 의
        `UIA_FILE_DUMP_FILE` 에 쓴다. 진단이라 무엇이 실패해도 발송을 막지 않는다.
        """
        if not failing and self.file_send_conf.get("verified"):
            return
        try:
            lines = self._kakao_windows_dump(chat, before, label)
        except Exception as exc:  # noqa: BLE001
            lines = [f"[{label}] 진단 실패: {exc}"]
        self.ui_dump = (list(self.ui_dump) + lines)[:UI_DUMP_MAX_LINES]
        path = self._dump_path(UIA_FILE_DUMP_FILE)
        try:
            if path:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(self.ui_dump) + "\n")
        except Exception:  # noqa: BLE001
            path = None
        log.info("파일 첨부 진단 — %s (전체: %s)\n%s", label, path or "파일 못 씀",
                 "\n".join(line for line in lines if not line.startswith("      ")))

    def _kakao_windows_dump(self, chat, before, label: str) -> List[str]:
        """앞 창 + 카톡 프로세스의 보이는 창 전부(제목·클래스·자리·주인) + 채팅창 속 창.

        **속(컨트롤)까지 뜨는 것은** 채팅창 · 새로 뜬 창 · 채팅창이 띄운 창뿐이다.
        메인 창(대화 목록 — 남의 이름과 말이 있다)은 줄 하나로만 적는다. 열기 창
        (`#32770`)은 목록 · 트리 속(폴더 · 남의 파일 이름)을 빼고 단추 · 칸만 적는다.
        """
        chat_hwnd = _handle(chat)
        pid = self._window_pid(chat) if chat is not None else 0
        lines = [f"[{label}] 앞 창 {self._hwnd_line(self._foreground_hwnd())}"]
        shown = self._top_windows()
        if shown is None or not pid:
            lines.append(f"  카톡 창 목록을 읽지 못했습니다 (pid={pid})")
            shown = {}
        for hwnd, (_title, wpid) in shown.items():
            if wpid != pid:
                continue
            owner = self._owner_hwnd(hwnd)
            tags = [tag for tag, on in (
                ("채팅창", hwnd == chat_hwnd),
                ("새 창", before is not None and hwnd not in before),
                ("채팅창이 띄운 창", bool(chat_hwnd) and owner == chat_hwnd)) if on]
            if not tags:
                lines.append(f"  창 {self._hwnd_line(hwnd)} owner={owner}")
                continue
            try:
                root = self._desktop.window(handle=hwnd)
                if hasattr(root, "wrapper_object"):
                    root = root.wrapper_object()
                entries = uia_tree_entries(root, max_depth=8, max_nodes=150)
                if self._hwnd_class(hwnd) == "#32770":
                    entries = without_lists(entries)
            except Exception as exc:  # noqa: BLE001
                entries, tags = [], tags + [f"UIA 못 읽음: {exc}"]
            buttons = [e.get("name") for e in entries
                       if e.get("control_type") in ("Button", "SplitButton")]
            lines.append(f"  창 {self._hwnd_line(hwnd)} owner={owner} "
                         f"[{' · '.join(tags)}] 단추={buttons!r}")
            lines += ["      " + line for line in format_uia_entries(entries)]
        for hwnd, _title in self._child_windows(chat_hwnd):
            lines.append(f"  채팅창 속 창 {self._hwnd_line(hwnd)}")
        return lines

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

    def _opened_chat_window(self, room_name: str, win=None):
        """**앞에 떠 있는** 창의 제목이 room_name 과 정확히 같으면 그 창, 아니면 None.

        ★ (0.11.9) 키(Ctrl+V · Enter)는 **앞 창**으로 간다 — 그래서 앞 창을 본다.
          0.11.8 까지는 제목이 같은 창이 **어딘가에** 있는지만 봤다
          (`Desktop.window(title=…)`). 그 방 창이 뒤에 떠 있으면 검색이 다른 방을
          열었어도 통과했고, 입력란을 못 읽는 PC 에서는 앞에 열린 **그 다른 방으로**
          나갈 수 있었다. 같은 제목 창이 둘이면 pywinauto 가 모호하다고 던져 맞는
          방도 `room_mismatch` 로 떨어졌다.

        제목은 `GetWindowText` 로 읽는다 — 실패 문구의 '실제로 열린 방'(0.11.6)과
        방 검색의 맨 위 방 제목이 같은 자리에서 실기로 읽혔다.

        `win`(메인 창)을 주면 **카톡 프로세스의 창만** 받는다 — 다른 앱의 창 제목이
        방 이름과 같을 수 있다.
        """
        pid = self._window_pid(win) if win is not None else 0
        deadline = time.monotonic() + self._t("chat_wait", 2.0)
        while True:
            hwnd = self._foreground_hwnd()
            if (hwnd and self._hwnd_title(hwnd).strip() == room_name
                    and (not pid or self._hwnd_pid(hwnd) == pid)):
                return self._desktop.window(handle=hwnd)
            if time.monotonic() >= deadline:
                break
            time.sleep(self._t("room_search_poll", 0.15))
        log.warning("title mismatch: expected=%r 앞 창=%r", room_name,
                    self._foreground_title())
        return None

    def _hwnd_title(self, hwnd) -> str:
        try:
            import win32gui  # type: ignore

            return win32gui.GetWindowText(hwnd) or ""
        except Exception:  # noqa: BLE001
            return ""

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
#  방 검색의 판단 — **창과 떨어져 있어 이 기계에서 그대로 시험한다**
#
#  Windows 카톡이 이 기계에 없으니 창을 읽는 자리(`_result_rows` ·
#  `_search_titles`)는 실기 전까지 추측이다. 그래서 **읽은 것을 보고 무엇을
#  후보로 세우고 무엇을 확인됨으로 올릴지** 정하는 자리를 따로 떼어 두었다.
#  그 판단은 추측이어서는 안 된다.
#  (mac 의 `kakao_mac._exact_row` · `discover_rooms` 의 걸러내기와 같은 결)
# ══════════════════════════════════════════════════════════════════════════

def query_was_typed(typed: Optional[str], query: str) -> bool:
    """검색칸에서 되읽은 글자가 **우리가 넣은 글자**인가.

    - 못 읽었다(None) → 참. 판단 불가를 실패로 보면 멀쩡한 PC 에서 아무것도
      안 나간다(`_search_input_text`).
    - 같다 → 참.
    - 넣은 글자의 **앞부분**이다 → 참(긴 글자를 잘라 보여 주는 경우).
    - 그 밖(직전 검색어가 앞에 붙은 경우 등) → 거짓.
    """
    if typed is None:
        return True
    got, want = _norm_title(typed), _norm_title(query)
    if not got:
        return False
    return got == want or want.startswith(got)


def retry_query(room_name: str) -> str:
    """다시 찾을 때 검색칸에 넣을 글자 (0.11.12) — 첫 시도와 **다른** 글자.

    같은 글자로는 카톡이 결과를 새로 세우지 않는다(0.11.10 짐작). 끝의 문장부호 · 이모지 ·
    기호를 떼고(카톡 검색이 그것 때문에 못 찾을 수도 있다), 뗄 것이 없으면 끝 한 글자를
    뗀다. 두 글자보다 짧아지면 그대로 둔다 — 너무 짧으면 맨 위에 다른 방이 선다.
    어떤 글자로 찾든 여는 방은 앞 창 제목 정확 일치로만 통과한다(`_opened_chat_window`).
    """
    text = (room_name or "").strip()
    cut = re.sub(r"[\W_]+$", "", text)
    if cut == text:
        cut = text[:-1].rstrip()
    return cut if len(cut) >= 2 else text


def _clip(text: str, limit: int = 40) -> str:
    """실패 문구에 싣는 창 제목. 공백을 줄이고 `limit` 글자에서 자른다."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def _norm_title(text: str) -> str:
    """제목 비교용. **연속 공백만** 줄이고 한글 자모를 합친 형태로 맞춘다.

    그 밖의 보정은 하지 않는다 — 한 글자만 달라도 다른 방이다(mac 의 `_norm`).

    자모를 합치는 것(NFC)은 느슨해지는 것이 아니다. 눈에 같은 글자가 디스크·UIA
    에서 두 형태로 오는 것을 한 형태로 맞추는 것뿐이고, **다른 글자를 같게
    만들지 않는다**(`base.nfc` 의 NFKC 경고 참고).
    """
    return " ".join(nfc(text or "").split())


def needle_of(query: str) -> str:
    """검색어에서 **제목에 반드시 들어 있어야 할 조각**. mac 과 같은 규칙 — 첫 낱말.

    왜 필요한가: 카톡 검색은 방 제목뿐 아니라 **참여자 이름으로도** 걸리고,
    결과가 한 박자 늦게 반영돼 직전 검색의 목록이 잡히기도 한다. 이름 조각이
    든 줄만 인정하면 둘 다 걸러진다.
    """
    parts = (query or "").split()
    return parts[0] if parts else (query or "").strip()


def filter_room_titles(titles, query: str, marker: str = "",
                       max_rows: int = 60) -> List[str]:
    """읽어 온 줄 글자에서 **후보로 세울 방 제목**만 남긴다 (mac 과 같은 규칙).

    ① 앞 `max_rows` 줄만 본다 — 검색이 안 먹어 전체 대화목록이 잡혀도 끊는다
    ② 빈 줄은 버린다
    ③ **검색어의 첫 낱말이 든 줄만** 남긴다 (`needle_of` 참고)
    ④ marker 가 있으면 그 글자가 든 줄만 남긴다

    ⚠ **같은 제목이 둘 나오면 둘 다 남긴다.** 겹친 것을 하나로 접으면
      `process_verify_job` 이 `len(found) == 1` 을 보고 `verified` 로 올려
      **같은 이름의 방이 여러 개인 것을 하나로 단정**한다. 그것이 곧 짐작이다.
    """
    needle = needle_of(query)
    if not needle:
        return []
    want = nfc(needle)
    mark = nfc(marker) if marker else ""
    out: List[str] = []
    for raw in list(titles or [])[:max(0, int(max_rows))]:
        title = (raw or "").strip()
        if not title:
            continue
        shown = nfc(title)
        if want not in shown:
            continue
        if mark and mark not in shown:
            continue
        out.append(title)
    return out


_ANNOTATION_RE = re.compile(r"\[[^\]]*\]")
_CORP_MARKS = ("(주)", "㈜", "주식회사")


def strip_annotations(text: str) -> str:
    """`[딜소개 불가]` 같은 대괄호 꼬리표를 떼고 공백을 정리한다."""
    return " ".join(_ANNOTATION_RE.sub(" ", nfc(text or "")).split())


def company_key(text: str, *, strip_notes: bool = False) -> str:
    """회사명 견주기용 열쇠. NFC → (꼬리표 떼기) → 법인 표기·공백 제거 → 소문자.

    `(주)가나다 전자` 와 `가나다전자` 이 같은 열쇠가 된다. 방 제목은
    띄어쓰기가 제각각이고 법인 표기가 붙기도 한다(실기).
    """
    t = nfc(text or "")
    if strip_notes:
        t = _ANNOTATION_RE.sub("", t)
    for mark in _CORP_MARKS:
        t = t.replace(mark, "")
    return "".join(t.split()).lower()


#: **투자사 방에만 붙는 글자.** 스타트업 기업의 맨 위 방 제목에 이것이 들어
#: 있으면 후보로 올리지 않는다(`looks_like_investor_room`).
#:
#: ★ 서버에 **같은 목록**이 있다(`app/services/room_match.INVESTOR_ROOM_MARKERS`).
#:   발송기 zip 에 `app/` 이 안 들어가 가져다 쓸 수 없어 한 벌 더 둔다 — 두
#:   벌이 갈리면 `tests/test_startup_room_investor.py` 가 잡는다. 서버가 어차피
#:   한 번 더 거르므로 여기는 덧댄 막이다.
INVESTOR_ROOM_MARKERS = ("인베스트먼트", "벤처스", "캐피탈", "자산운용",
                         "파트너스", "Asset deal")


def looks_like_investor_room(title: str, query: str) -> bool:
    """맨 위 방 제목이 **투자사 방**으로 보이는가.

    표식이 **회사명에도** 들어 있으면 그 표식은 안 본다 — 회사 이름이
    `가나다파트너스` 면 그 회사의 진짜 방에도 `파트너스` 가 든다.
    """
    flat = company_key(title)
    company = company_key(query, strip_notes=True)
    for marker in INVESTOR_ROOM_MARKERS:
        mark = company_key(marker)
        if mark and mark in flat and mark not in company:
            return True
    return False


#: 카톡 메인 창에서 **다른 일을 하는** 키 묶음. 검색칸 비우기에 쓰면 안 된다.
#: Ctrl+A = '친구 추가'(실기 0.11.3 — 친구 추가 창에 회사명이 들어갔다).
_CTRL_KEYS = {"ctrl", "control", "ctrlleft", "ctrlright"}


def _is_forbidden_chord(keys: tuple) -> bool:
    low = {k.strip().lower() for k in keys}
    return "a" in low and bool(low & _CTRL_KEYS)


def clear_chords(conf: dict) -> List[tuple]:
    """`room_search.clear_keys` 를 키 묶음 목록으로. 글자 하나면 묶음 하나로 본다.

    빈 목록(`[]`)이면 아무것도 안 누른다 — 끄는 길이다.

    ⚠ **Ctrl+A 가 든 묶음은 건너뛴다**(경고 남김). 카톡 메인 창에서 Ctrl+A 는
      '친구 추가' 단축키라 검색칸이 아니라 친구 추가 창이 뜬다(실기 0.11.3).
      예전 selectors.yaml 이 남아 있어도 누르지 않게 여기서 막는다.
    """
    raw = conf.get("clear_keys")
    if raw is None:
        raw = ROOM_SEARCH_DEFAULTS["clear_keys"]
    out: List[tuple] = []
    for chord in raw or []:
        if isinstance(chord, str):
            chord = [chord]
        keys = tuple(str(k) for k in chord if str(k).strip())
        if not keys:
            continue
        if _is_forbidden_chord(keys):
            log.warning("clear_keys 의 %r 는 누르지 않습니다 — 카톡에서 Ctrl+A 는 "
                        "'친구 추가' 입니다", "+".join(keys))
            continue
        out.append(keys)
    return out


def _box_value(box) -> str:
    """편집칸의 글자(ValuePattern). 못 읽으면 "" — 이름(라벨)은 글자로 안 친다."""
    try:
        return (box.get_value() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def title_has_company(title: str, query: str) -> bool:
    """맨 위 방 제목에 **검색어(회사명)가 통째로 들어 있는가.**

    검색어 쪽만 꼬리표(`[딜소개 불가]`)를 뗀다 — 방 제목의 대괄호는 방 이름의
    일부일 수 있다. 열쇠가 두 글자 미만이면 아무 방에나 걸리므로 받지 않는다.
    """
    want = company_key(query, strip_notes=True)
    if len(want) < 2:
        return False
    return want in company_key(title)


def pick_new_window(before: dict, after: dict, *, pid: int = 0,
                    foreground: int = 0, exclude_titles=()) -> Optional[tuple]:
    """열기 전·후 창 목록(`{hwnd: (제목, pid)}`)을 견줘 **새로 뜬 채팅창 하나.**

    · 전에 없던(또는 안 보이던) 창만 본다 — 원래 열려 있던 창은 고르지 않는다
    · 제목이 빈 창, 메인 창 제목(`exclude_titles`)과 같은 창은 뺀다
    · `pid` 가 주어지면 **카톡 프로세스의 창만** 본다
    · 여럿이면 지금 앞에 있는 창(`foreground`)을 고르고, 그것도 아니면
      **고르지 않는다**(None) — 어느 것인지 모르는데 아무거나 고르지 않는다
    돌려주는 값: `(hwnd, 제목)` 또는 None.
    """
    skip = {nfc(t).strip() for t in exclude_titles if t}
    fresh = []
    for hwnd, info in (after or {}).items():
        if hwnd in (before or {}):
            continue
        if isinstance(info, (tuple, list)):
            title, wpid = (list(info) + ["", 0])[:2]
        else:
            title, wpid = info, 0
        title = (title or "").strip()
        if not title or nfc(title) in skip:
            continue
        if pid and wpid and wpid != pid:
            continue
        fresh.append((hwnd, title))
    if not fresh:
        return None
    for hwnd, title in fresh:
        if foreground and hwnd == foreground:
            return (hwnd, title)
    return fresh[0] if len(fresh) == 1 else None


def _uia_info(ctrl) -> dict:
    """UIA 컨트롤 하나의 이름표. pywinauto 의 `element_info` 를 먼저 본다."""
    info = getattr(ctrl, "element_info", None)
    src = info if info is not None else ctrl

    def _get(attr):
        try:
            value = getattr(src, attr, "")
            value = value() if callable(value) else value
            return "" if value is None else str(value)
        except Exception:  # noqa: BLE001
            return ""

    top = box = None
    try:
        rect = getattr(src, "rectangle", None)
        rect = rect() if callable(rect) else rect
        if rect is not None:
            top = int(rect.top)
            box = (int(rect.left), top, int(rect.right), int(rect.bottom))
    except Exception:  # noqa: BLE001
        pass
    return {"control_type": _get("control_type"), "class_name": _get("class_name"),
            "name": _get("name"), "automation_id": _get("automation_id"),
            "top": top, "rect": box}


def uia_tree_entries(root, max_depth: int = 12, max_nodes: int = 400) -> List[dict]:
    """UIA 구조를 위에서부터 훑어 항목 목록으로. 깊이·개수 상한에서 끊는다."""
    out: List[dict] = []

    def _walk(node, depth):
        if len(out) >= max_nodes:
            return
        entry = _uia_info(node)
        entry["depth"] = depth
        out.append(entry)
        if depth >= max_depth:
            return
        try:
            kids = list(node.children())
        except Exception:  # noqa: BLE001
            kids = []
        for kid in kids:
            if len(out) >= max_nodes:
                return
            _walk(kid, depth + 1)

    _walk(root, 0)
    return out


def format_uia_entries(entries) -> List[str]:
    return [
        "{}{} class={!r} name={!r} id={!r}{}".format(
            "  " * int(e.get("depth") or 0), e.get("control_type") or "?",
            e.get("class_name") or "", _clip(e.get("name") or "", 80),
            e.get("automation_id") or "",
            f" rect={e['rect']}" if e.get("rect") else "")
        for e in entries or []
    ]


def guess_member_count(entries, near_top_px: int = 120,
                       first_n: int = 40) -> Optional[int]:
    """채팅창 제목 옆 **인원 수 짐작.** 숫자만 든 Text 가 창 위쪽에 있으면 그 값.

    ⚠ 짐작이다 — 로그에만 쓴다. 위치를 읽을 수 있으면 창 꼭대기에서
      `near_top_px` 안쪽만, 못 읽으면 앞쪽 `first_n` 항목만 본다.
    """
    entries = list(entries or [])
    if not entries:
        return None
    win_top = entries[0].get("top")
    for e in entries[:first_n] if win_top is None else entries:
        if (e.get("control_type") or "") != "Text":
            continue
        name = (e.get("name") or "").strip()
        if not name.isdigit() or not (0 < int(name) < 10000):
            continue
        top = e.get("top")
        if win_top is not None and top is not None and top - win_top > near_top_px:
            continue
        return int(name)
    return None


def verdict_from_titles(titles, room_name: str) -> str:
    """읽어 온 줄 글자로 `verified | not_found | ambiguous` 를 **센다.**

    ★ 여기는 **글자까지 정확히 같은 줄만** 센다. 후보 목록(`filter_room_titles`)
      이 '든 글자' 로 넉넉히 모으는 것과 **다른 자리**다. 후보가 많아져도 이
      판정은 느슨해지지 않는다.

    같은 제목이 둘 이상이면 `ambiguous` — 고르지 않는다. 어느 쪽인지 모르는데
    아무거나 고르면 남의 대화방으로 간다.
    """
    want = _norm_title(room_name)
    if not want:
        return "not_found"
    hits = [t for t in (titles or []) if _norm_title(t) == want]
    if len(hits) > 1:
        return "ambiguous"
    return "verified" if hits else "not_found"


def row_title(row, text_control_type: str = "Text") -> str:
    """검색 결과 **한 줄에서 방 제목**을 읽는다. 못 읽으면 빈 값.

    줄의 **첫 글자 조각**을 제목으로 본다 — mac 도 각 줄의 첫 static text 를
    읽는다(그 뒤 조각은 마지막 메시지·시각이다).

    `text_control_type` 이 비면 글자 조각을 찾지 않고 **줄 이름(Name)** 을 쓴다.
    실기에서 줄 이름 자체가 제목이면 `selectors.yaml` 에서 그렇게 바꾼다.
    """
    ctype = (text_control_type or "").strip()
    if ctype:
        for text in _control_texts(row, ctype):
            if text:
                return text
    return _text_of(row)


def _auto_id(control) -> str:
    try:
        return (control.automation_id() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _max_rows(conf: dict) -> int:
    """살펴볼 줄 수 상한. 값이 깨져 있으면 바닥값으로 돌아간다."""
    try:
        value = int(conf.get("max_rows") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else int(ROOM_SEARCH_DEFAULTS["max_rows"])


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


def _rect_area(window) -> int:
    try:
        rect = window.rectangle()
        return max(0, int(rect.width())) * max(0, int(rect.height()))
    except Exception:  # noqa: BLE001
        return 0


def pick_kakao_window(candidates, exact_title: str = "카카오톡"):
    """제목이 '카카오톡…' 인 창들 중 **메인 창 하나**를 고른다. 없으면 None.

    Windows 카카오톡은 같은 제목으로 시작하는 숨은 보조 창을 여럿 띄운다.
    고르는 순서(결정적이다 — 같은 화면이면 늘 같은 창):

      1) **보이는 창**만 본다. 최소화된 메인 창도 Windows 에서는 '보이는' 창이다
         (`IsWindowVisible`) — 최소화했다고 놓치지 않는다
      2) 그중 제목이 **정확히** `exact_title`('카카오톡') 인 창. 열린 채팅창
         ('카카오톡 - 방이름' 따위)보다 메인 창이 먼저다
      3) 그다음 **넓이가 큰** 창
      4) 보이는 창이 하나도 없으면 제목이 정확히 같은 창, 그것도 없으면 첫 창

    창 하나하나를 묻는 자리는 모두 감싼다 — 묻는 사이 창이 사라질 수 있다.
    """
    rows = []
    for order, win in enumerate(candidates or []):
        title = _text_of(win)
        rows.append((win, _visible(win), title == exact_title, _rect_area(win),
                     order))
    if not rows:
        return None
    visible = [r for r in rows if r[1]]
    if visible:
        # 정확한 제목 먼저, 넓이 큰 것 먼저, 같으면 목록 순서.
        visible.sort(key=lambda r: (not r[2], -r[3], r[4]))
        return visible[0][0]
    for r in rows:
        if r[2]:
            return r[0]
    return rows[0][0]


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


def _control_texts(dialog, control_type: Optional[str] = None) -> List[str]:
    """그 창 속 컨트롤 글자들. `control_type` 이 없으면 **모든** 컨트롤의 이름."""
    try:
        kids = (dialog.descendants(control_type=control_type) if control_type
                else dialog.descendants())
        return [t for t in (_text_of(c) for c in kids) if t]
    except Exception:  # noqa: BLE001
        return []


def _control_label(ctrl) -> str:
    """컨트롤 이름 + (있으면) 도움말 · 설명 — 아이콘 단추는 이름 대신 풍선 도움말만 있을 수 있다."""
    parts = [_text_of(ctrl)]
    try:
        legacy = ctrl.legacy_properties() or {}
        parts += [str(legacy.get("Help") or ""), str(legacy.get("Description") or "")]
    except Exception:  # noqa: BLE001
        pass
    return " ".join(p for p in parts if p)


def without_lists(entries) -> List[dict]:
    """UIA 항목에서 목록 · 트리 · 표의 **속**을 뺀다(열기 창의 폴더 · 남의 파일 이름)."""
    out, cut = [], None
    for e in entries or []:
        depth = int(e.get("depth") or 0)
        if cut is not None and depth > cut:
            continue
        cut = None
        out.append(e)
        if e.get("control_type") in ("List", "Tree", "DataGrid", "Table"):
            cut = depth
    return out


def _handle(win) -> int:
    try:
        return int(getattr(win, "handle", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0


def _rx(pattern):
    """설정의 정규식. 비었거나 깨졌으면 None — **빈 본은 아무 글자에나 걸리므로** 안 쓴다."""
    if not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error:
        log.warning("selectors.yaml 의 정규식이 깨졌습니다: %r", pattern)
        return None


def _hit(rx, text) -> bool:
    return bool(rx is not None and rx.search(text or ""))


def unsendable_detail(snapshot: Optional[dict], conf: Optional[dict] = None) -> Optional[str]:
    """카톡이 `전송 불가` 라고 한 창이면 **그 까닭**(파일명 · 이유), 아니면 None.

    실기(0.11.12): `파일 전송` 창에 `전송 불가 1` · `시험자료.pdf` · `비어있는 파일` ·
    [확인]. 일부만 불가여도(`전송 가능 1` 과 함께) 불가로 본다 — 반만 짐작해 보내지 않는다.
    """
    settings = dict(FILE_SEND_DEFAULTS)
    settings.update(conf or {})
    rx = _rx(settings.get("unsendable_re"))
    title_rx = _rx(settings.get("confirm_title_re"))
    snapshot = snapshot or {}
    texts = [snapshot.get("title") or ""] + list(snapshot.get("texts") or [])
    if not any(_hit(rx, t) for t in texts):
        return None
    skip = set(snapshot.get("buttons") or [])
    detail = [t for t in texts if t and t not in skip and not _hit(rx, t)
              and not _hit(title_rx, t)]
    return " · ".join(dict.fromkeys(detail)) or "까닭을 읽지 못했습니다"


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


def _titled(shape: dict, title_rx) -> bool:
    """창 제목이나 카드 속 글자 중 하나가 `파일 전송` 인가(카드는 제목을 글자로 그린다)."""
    return any(_hit(title_rx, t) for t in [shape.get("title") or ""]
               + list(shape.get("texts") or []))


def _button_count(button: str, conf: dict) -> Optional[int]:
    """[N개 전송] 의 N. 본에 숫자 괄호가 없거나 못 읽으면 None."""
    rx = _rx(conf.get("send_button_re"))
    hit = rx.match(_norm_button(button)) if rx is not None else None
    num = next((g for g in hit.groups() if g), "") if hit else ""
    return int(num) if num.isdigit() else None


#: 파일 이름처럼 보이는 글자(끝에 `.확장자`) — 카드에 **다른** 파일이 떠 있는지 보는 데 쓴다.
_FILE_LIKE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def _leaf(text: str) -> str:
    """경로에서 마지막 조각. 확인 창이 파일명 대신 **전체 경로**를 보여 줄 수 있다.

    ⚠ 느슨하게 만드는 것이 아니다. 조각 하나가 파일명과 **정확히** 같아야
      통과한다 — 경로의 마지막 조각이 곧 파일명이기 때문이다.
    """
    return re.split(r"[\\/]", text or "")[-1]


def check_file_card(snapshot: Optional[dict], expected_names: List[str],
                    conf: Optional[dict] = None):
    """★ 관문. `(막는 까닭 또는 None, 남길 말)` — 까닭이 있으면 **닫고 보내지 않는다.**

    실기 카드(10/20): 제목 `파일 전송` · 파일 줄 · [1개 전송] 하나 · [×] (취소 단추는
    없다). 그래서 통과하려면:
      ① 제목(창 제목이나 카드 속 글자)이 `confirm_title_re`
      ② 보내기 단추(`send_button_re` — [N개 전송])가 **딱 하나**
      ③ 그 N 이 보내려던 개수와 **같다** — 한 번에 한 파일이라 늘 1. 남은 선택이 섞이면
         여기서 걸린다
      ④ 파일명: 카드에서 읽히면 보내려던 것과 같아야 한다. 파일처럼 보이는 **다른**
         이름만 보이면 막는다. **아무 이름도 못 읽으면** 통과시키되 그 말을 남긴다 —
         카드는 열기 창에서 되읽어 견준 그 경로를 [열기]한 바로 뒤에 뜬 창이다(방은 앞
         창 제목 · 열기 창의 주인으로 이미 확인했다). 남는 위험: 카드가 다른 파일을
         보여 주는데 UIA 로 아무 글자도 안 읽히는 경우 — 그때는 개수 ③ 만 지킨다.
    `전송 불가` 는 이 앞에서 따로 거른다(`unsendable_detail`).
    """
    want = list(expected_names or [])
    settings = dict(FILE_SEND_DEFAULTS)
    settings.update(conf or {})
    if not snapshot or not snapshot.get("present"):
        return "파일 전송 창이 없습니다", ""

    if not _titled(snapshot, _rx(settings.get("confirm_title_re"))):
        return (f"'파일 전송' 창이 아닙니다: 제목={snapshot.get('title')!r} "
                f"단추={snapshot.get('buttons')!r}"), ""

    senders = _send_button(snapshot, settings)
    if len(senders) != 1:
        return (f"보내기 단추가 {len(senders)}개입니다: "
                f"단추={snapshot.get('buttons')!r}"), ""
    count = _button_count(senders[0], settings)
    if count != len(want):
        return (f"개수가 다릅니다: 창은 {senders[0]!r} 인데 "
                f"보내려던 것은 {len(want)}개"), ""

    #    ★ 두 쪽을 **같은 형태로 맞춘 뒤** 견준다(`base.same_file_name`) — 한글 파일명은
    #      자모 조합 형태가 두 가지다(mac 에서 실제로 겪었다). 전체 경로면 마지막 조각.
    texts = list(snapshot.get("texts", []))
    missing = [n for n in want
               if not any(same_file_name(n, t) or same_file_name(n, _leaf(t))
                          for t in texts)]
    if not missing:
        return None, ""
    others = [t for t in texts if _FILE_LIKE.search(t)]
    if others:
        return f"창에 다른 파일이 있습니다: {others!r} (보내려던 것 {want!r})", ""
    return None, (f"파일명을 '파일 전송' 창에서 읽지 못해 제목과 {senders[0]!r} 로만 "
                  f"확인했습니다 (보낸 것 {want!r})")
