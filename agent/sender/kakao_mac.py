"""KakaoMacSender — macOS 카카오톡 데스크톱 앱 UI 자동화.

Windows(pywinauto) 판과 **동일한 Sender 인터페이스**를 구현한다. 팀이 Mac에서
실제 카톡 발송을 검증할 수 있게 하려는 것이며, 운영은 Windows/Mac 어느 쪽이든
같은 잡 큐·재시도·이력 경로를 탄다.

전제(사용자 확인): **채팅방은 이미 만들어져 있다.** 따라서 방을 새로 만들지 않고
"기존 방을 열어 → 붙여넣기 → 전송"만 수행한다.

오발송 방지(양보 불가, ROADMAP 공통 원칙 4):
  방을 연 뒤 창 제목을 다시 읽어 room_name 과 **정확히 일치**할 때만 전송한다.
  하나라도 어긋나면 전송하지 않고 failed(room_mismatch) 로 보고한다.

필요 권한: 시스템 설정 → 개인정보 보호 및 보안 → **손쉬운 사용(Accessibility)** 에
  이 에이전트를 실행하는 앱(터미널/iTerm 등)을 허용해야 한다. 없으면 -1728 오류.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import List, Optional

from .base import (IrPathError, SendResult, Sender, ir_root, nfc,
                   resolve_ir_file, same_file_name)

log = logging.getLogger("agent.kakao_mac")

APP = "KakaoTalk"

# 검색 결과에서 살펴볼 행 수 상한.
#
# 예전에는 이보다 많으면 "필터가 안 먹었다"고 보고 아예 중단했다. 첫 행을 누르는
# 방식이었기 때문이다. 지금은 **제목이 정확히 일치하는 행**을 찾아 누르므로
# 결과가 많아도 위험하지 않다 — 오히려 이름이 흔하면(참여자 이름으로도 걸린다)
# 20건은 너무 적어서 정작 찾는 방이 잘려 나갔다.
MAX_SEARCH_ROWS = 60

# ── 파일 전송 (실기로 확인된 값들) ──────────────────────────────────────────
# 채팅창의 첨부 단추는 `help='파일전송 ⌘O'` 로 찾는다. **인덱스로 찾으면 안 된다**
# — 창마다 단추 순서가 흔들린다.
FILE_BUTTON_HELP = "파일전송"
# `열기` 를 눌러도 바로 안 나간다. "파일 전송" 확인 시트가 한 번 더 뜨고,
# 개수가 단추 이름에 박혀 있다(`1개 전송`). 그 시트가 유일한 진짜 관문이다.
CONFIRM_TITLE = "파일 전송"
CANCEL_BUTTON = "취소"
SEND_BUTTON_FMT = "{n}개 전송"
COUNT_BUTTON_RE = re.compile(r"^(\d+)\s*개\s*전송$")
# 표준 NSOpenPanel. '폴더로 이동'은 `Cmd+Shift+G` — **키 코드**로 보낸다
# (`keystroke "g"` 는 입력원이 한글이면 먹지 않는다. 실기에서 잡았다).
GOTO_KEY_CODE = 5          # 자판의 `g` 자리
OPEN_PANEL_ID = "open-panel"
OPEN_BUTTON_ID = "OKButton"
OPEN_BUTTON_NAME = "열기"


def is_supported() -> bool:
    import platform
    return platform.system() == "Darwin"


class AccessibilityError(RuntimeError):
    pass


def _osa(script: str, timeout: int = 20) -> str:
    """AppleScript 실행. 접근성 권한 없으면 AccessibilityError."""
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if "-1728" in err or "보조 접근" in err or "not allowed assistive" in err:
            raise AccessibilityError(
                "접근성(Accessibility) 권한이 없습니다. 시스템 설정 → 개인정보 보호 및 보안 → "
                "손쉬운 사용에서 터미널(또는 이 에이전트를 실행한 앱)을 허용하세요."
            )
        raise RuntimeError(err or "osascript 실패")
    return (proc.stdout or "").strip()


def _set_clipboard(text: str) -> None:
    """pbcopy 로 클립보드 설정.

    참고: 카톡 Mac 은 검색창·입력창 모두 Cmd+V 가 무시될 때가 있어
    본문/검색어 입력에는 쓰지 않는다(AX value 직접 설정 사용).
    """
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def _type_text(text: str) -> None:
    """ASCII 전용 타이핑.

    ⚠ AppleScript 의 keystroke 는 **한글을 보내지 못한다**. 한글을 넘기면
    'ㅁㅁㅁ' 또는 'aaa' 처럼 깨진 문자가 입력된다(실기 확인).
    한글이 섞일 수 있는 값(방 이름 등)은 AX value 직접 설정을 쓸 것.
    """
    if not text.isascii():
        raise ValueError("keystroke 는 한글을 보낼 수 없습니다 — 클립보드 붙여넣기를 쓰세요.")
    _osa(f'tell application "System Events" to keystroke "{_esc(text)}"')


class QuartzUnavailable(RuntimeError):
    """pyobjc-framework-Quartz 미설치. 방 자동 열기만 불가하고 발송은 가능하다."""


def quartz_available() -> bool:
    try:
        import Quartz  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _double_click(x: int, y: int) -> None:
    """실제 마우스 더블클릭. 카톡 채팅 목록은 AXPress/Enter 로 열리지 않는다.

    Quartz(pyobjc)로 클릭 이벤트를 합성한다.

    ★ Quartz 는 **선택적 의존성**이다. Python 3.9 처럼 미리 빌드된 휠이 없는 환경에서는
    설치에 컴파일러가 필요해 실패하는데(실기에서 발생), 그렇다고 발송 전체를 막을 이유는 없다.
    이 함수는 '검색해서 방을 새로 여는' 경로에서만 쓰이므로, 대상 채팅방 창이 이미 열려
    있으면 Quartz 없이도 발송된다. 없으면 명확한 예외를 던져 호출부가 안내하도록 한다.
    """
    try:
        import Quartz
    except Exception as exc:  # noqa: BLE001
        raise QuartzUnavailable(
            "pyobjc-framework-Quartz 가 설치되지 않아 채팅방을 자동으로 열 수 없습니다. "
            "카카오톡에서 대상 채팅방 창을 미리 열어두면 발송됩니다. "
            "(자동 열기까지 쓰려면 Python 3.10+ 에서 설치하거나 xcode-select --install)"
        ) from exc

    for click_state in (1, 2):
        for kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            ev = Quartz.CGEventCreateMouseEvent(None, kind, (x, y), Quartz.kCGMouseButtonLeft)
            Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, click_state)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.06)


def _wait_until(check, timeout: float, interval: float = 0.1):
    """조건이 참이 될 때까지 짧게 반복 확인하고, 그 값을 돌려준다.

    고정 sleep 은 느린 쪽에 맞춰 잡아야 해서 평소에도 그만큼 기다리게 된다.
    조건이 충족되면 즉시 넘어가므로 체감 속도가 빨라지고, 느린 순간에는
    timeout 까지 기다려 주므로 안정성도 함께 올라간다.
    """
    deadline = time.time() + timeout
    while True:
        try:
            got = check()
        except Exception:  # noqa: BLE001
            got = None
        if got:
            return got
        if time.time() >= deadline:
            return None
        time.sleep(interval)


class KakaoMacSender(Sender):
    name = "kakao_mac"

    def __init__(self, cfg: Optional[dict] = None):
        cfg = cfg or {}
        self.t_activate = float(cfg.get("after_activate", 1.0))
        self.t_search_open = float(cfg.get("after_search_hotkey", 0.8))
        self.t_query = float(cfg.get("after_query_paste", 1.2))
        self.t_open_room = float(cfg.get("after_open_room", 1.5))
        self.t_paste = float(cfg.get("after_paste", 0.6))
        self.t_send = float(cfg.get("after_send", 0.8))
        self.search_hotkey = cfg.get("search_hotkey", "f")   # Cmd+F
        self.close_after_send = bool(cfg.get("close_after_send", True))
        # 파일 전송. 시트가 뜨기까지가 사람 손보다 느릴 수 있어 넉넉히 잡는다 —
        # 짧게 잡으면 '안 떴다'고 보고 취소해 버린다.
        self.file_button_help = cfg.get("file_button_help", FILE_BUTTON_HELP)
        self.t_panel = float(cfg.get("file_panel_timeout", 6.0))
        self.t_confirm = float(cfg.get("file_confirm_timeout", 8.0))
        # Enter 만으로 패널이 닫히는 판이 있어, `열기` 를 누르기 전에 확인 시트가
        # 이미 떴는지 잠깐만 본다.
        self.t_confirm_quick = float(cfg.get("file_confirm_quick", 1.2))
        # `열기` 를 다시 누르기까지의 간격 (아래 `_open_until_confirm`).
        self.t_open_retry = float(cfg.get("file_open_retry_sec", 0.6))
        self.t_sent = float(cfg.get("file_sent_timeout", 8.0))
        # IR 자료 뿌리는 PC 마다 다르다 → 설정으로 받는다(agent/config.yaml 의
        # `ir_root`, 또는 환경변수 DEALFLOW_IR_ROOT).
        self.ir_root_setting = str(cfg.get("ir_root", "") or "")

    # --- 기본 조작 -----------------------------------------------------------

    def _activate(self) -> None:
        _osa(f'tell application "{APP}" to activate')
        # 앱이 실제로 앞에 오면 즉시 진행(고정 대기 대신).
        _wait_until(
            lambda: _osa(
                f'tell application "System Events" to return frontmost of process "{APP}"'
            ) == "true",
            timeout=self.t_activate + 1.0,
        )

    def window_titles(self) -> List[str]:
        """카카오톡의 모든 창 제목. 방 열림 여부/정확 일치 검증의 근거."""
        out = _osa(
            f'tell application "System Events" to tell process "{APP}" '
            f'to return name of windows'
        )
        return [w.strip() for w in out.split(",") if w.strip()]

    def _focus_window(self, title: str) -> bool:
        """이미 열려 있는 창을 앞으로 올린다. 성공하면 True.

        순서 주의: 앱을 먼저 활성화(frontmost)한 뒤 AXRaise 해야 한다.
        반대로 하면 앱 활성화가 '직전에 보던 창'을 다시 앞으로 끌어와
        대상 창이 뒤로 밀린다(실기 확인: 대상 '나와의 채팅' 인데 '여행 & 개발' 이 앞에 옴).
        올린 뒤에는 창 순서가 반영될 때까지 잠깐 기다렸다가 검증한다.
        """
        esc = _esc(title)
        # 올리기와 '실제로 앞에 왔는지' 확인을 **한 번의 AppleScript** 안에서 처리한다.
        # 파이썬에서 폴링하면 osascript 프로세스를 매번 새로 띄우는데(1회 ~84ms),
        # 그 오버헤드가 대기시간을 지배해 체감이 느려진다.
        script = (
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  set frontmost to true\n'
            f'  set matches to (every window whose name is "{esc}")\n'
            f'  if (count of matches) is 0 then return "none"\n'
            f'  perform action "AXRaise" of item 1 of matches\n'
            f'  repeat 40 times\n'
            f'    if (name of front window) is "{esc}" then return "front"\n'
            f'    delay 0.05\n'
            f'  end repeat\n'
            f'  return "timeout"\n'
            f'end tell'
        )
        return _osa(script) == "front"

    def _keystroke(self, key: str, *, cmd: bool = False) -> None:
        mods = ' using command down' if cmd else ''
        _osa(f'tell application "System Events" to keystroke "{key}"{mods}')

    def _key_code(self, code: int, *, cmd: bool = False,
                  shift: bool = False) -> None:
        """**물리 키**를 보낸다. `keystroke` 와 달리 입력원(한/영)을 타지 않는다."""
        mods = [m for m, on in (("command down", cmd), ("shift down", shift)) if on]
        using = f' using {{{", ".join(mods)}}}' if mods else ''
        _osa(f'tell application "System Events" to key code {code}{using}')

    def _press_enter(self) -> None:
        self._key_code(36)

    def _ensure_search_open(self, main: str) -> None:
        """검색 입력칸이 없으면 **돋보기를 눌러** 연다.

        지금까지는 검색창이 이미 열려 있다고 보고 바로 입력칸을 찾았다. 사람이
        직접 한 번 열어 둔 상태에서 만들어진 절차라 그랬는데, 카톡을 새로
        띄우거나 Esc 로 검색을 닫으면 입력칸 자체가 없어서 그 자리에서 멎었다.

        먼저 단축키(Cmd+F)를 쓰고, 그래도 안 열리면 돋보기 버튼을 눌러 본다 —
        버전에 따라 단축키가 다르다(설정의 `search_hotkey`).
        """
        field = f'first UI element of ({main}) whose role is "AXTextField"'

        def opened() -> bool:
            return _osa(
                f'tell application "System Events" to tell process "{APP}" '
                f'to return (exists ({field}))'
            ).strip() == "true"

        if opened():
            return

        _osa(f'tell application "System Events" to keystroke "{self.search_hotkey}" '
             f'using command down')
        if _wait_until(lambda: True if opened() else None,
                       timeout=self.t_search_open + 0.7):
            return

        # 단축키가 안 먹는 버전 — 돋보기 버튼을 직접 누른다.
        _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  set btns to (every button of ({main}) whose '
            f'description contains "검색" or name contains "검색" '
            f'or description contains "Search" or name contains "Search")\n'
            f'  if (count of btns) > 0 then click item 1 of btns\n'
            f'end tell'
        )
        if not _wait_until(lambda: True if opened() else None,
                           timeout=self.t_search_open + 0.7):
            raise RuntimeError(
                "카카오톡 검색창을 열지 못했습니다. "
                "메인 창에서 돋보기를 한 번 눌러 검색창을 띄운 뒤 다시 시도하세요."
            )

    def _open_room_via_search(self, room_name: str) -> None:
        """메인창 검색으로 기존 방 열기 (방은 이미 존재한다는 전제).

        실기 확인으로 굳어진 절차:
          - 검색어는 **AX value 직접 설정**이 유일하게 안정적이다.
            (keystroke 는 한글을 못 보내고, Cmd+V 는 이 필드에서 자주 무시된다)
          - 결과 행은 Enter/AXPress 로 열리지 않고 **실제 더블클릭**이 필요하다.
        """
        self._activate()
        main = 'first window whose name is "카카오톡"'
        try:
            # 0) 메인 창을 반드시 앞으로. 다른 채팅창이 앞에 있으면 이후 키 입력이
            #    그 채팅창으로 들어간다(실기 확인). 실패하면 아예 입력하지 않는다.
            if not self._focus_window("카카오톡"):
                raise RuntimeError(
                    "카카오톡 메인 창을 앞으로 가져오지 못했습니다. "
                    "열려 있는 채팅창을 닫고 다시 시도하세요."
                )

            # 0.5) 검색창이 닫혀 있으면 연다. 예전에는 열려 있다고 보고 바로
            #      입력칸을 찾아서, 카톡을 새로 띄운 뒤에는 그 자리에서 멎었다.
            self._ensure_search_open(main)

            # 1) 검색어 입력 — ★ AX value 직접 설정.
            #    다른 방법은 전부 실패한다(실기 확인):
            #      - keystroke: 한글을 못 보내 'ㅁㅁㅁ'/'aaa' 로 깨짐
            #      - Cmd+V(클립보드): 이 필드에서 동작하지 않을 때가 있음
            #    value 설정은 한글도 정확히 들어가고 카톡의 검색 필터도 반응한다.
            field = f'first UI element of ({main}) whose role is "AXTextField"'
            # 값 설정 + 목록이 걸러질 때까지의 대기를 한 번의 호출로 끝낸다.
            _osa(
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  set sf to {field}\n'
                f'  set focused of sf to true\n'
                f'  set value of sf to "{_esc(room_name)}"\n'
                f'  repeat 40 times\n'
                f'    if (count of rows of (first table of first scroll area of ({main}))) '
                f'≤ {MAX_SEARCH_ROWS} then exit repeat\n'
                f'    delay 0.05\n'
                f'  end repeat\n'
                f'end tell'
            )
            # 입력이 반영될 때까지 폴링(고정 대기 대신)
            typed = _wait_until(
                lambda: _osa(
                    f'tell application "System Events" to tell process "{APP}" '
                    f'to return value of ({field})'
                ) or None,
                timeout=self.t_query + 1.0,
            ) or ""
            if typed != room_name:
                raise RuntimeError(
                    f"검색어가 제대로 입력되지 않았습니다(입력됨={typed!r}, 기대={room_name!r})"
                )

            # 2) ★ 결과가 실제로 걸러졌는지 확인한 뒤에만 클릭한다.
            #    검색이 안 먹은 상태에서 첫 행을 더블클릭하면 **전체 대화목록의 맨 위 방**이
            #    열린다(실기에서 엉뚱한 방이 열림). 오발송 방지는 창 제목 검증이 막아주지만,
            #    애초에 남의 대화창을 여는 것 자체를 피해야 한다.
            def _rows():
                r = _osa(
                    f'tell application "System Events" to tell process "{APP}" '
                    f'to return count of rows of (first table of first scroll area of ({main}))'
                )
                # 필터가 반영돼 목록이 줄어들면 그때 통과시킨다.
                return r if (r.isdigit() and 0 < int(r) <= MAX_SEARCH_ROWS) else None

            rows = _wait_until(_rows, timeout=self.t_query + 1.5) or _osa(
                f'tell application "System Events" to tell process "{APP}" '
                f'to return count of rows of (first table of first scroll area of ({main}))'
            )
            if not rows.isdigit() or int(rows) == 0:
                raise RuntimeError(f"검색 결과가 없습니다: {room_name!r}")
            # 결과가 아주 많으면 검색이 안 먹은 것이다(전체 대화목록). 그래도
            # 제목이 정확히 같은 행만 누르므로, 살펴볼 범위만 제한하면 된다.
            if int(rows) > MAX_SEARCH_ROWS:
                log.info("검색 결과 %s건 — 앞 %d건만 살펴봅니다 room=%r",
                         rows, MAX_SEARCH_ROWS, room_name)

            # 3) **제목이 정확히 일치하는 행**을 찾아 더블클릭.
            #
            #    첫 행을 그냥 누르면 안 된다. 카톡 검색은 방 제목뿐 아니라
            #    **참여자 이름으로도** 걸린다. 이름이 흔하면 그 사람이 낀 단체방이
            #    잔뜩 나오고 첫 행은 대개 그중 하나다.
            #
            #    운영 방 이름은 '○○○ 심사역님 △△벤처스 Deal 공유 …' 처럼 길고
            #    고유해서 부딪힐 일이 드물다. 문제가 드러난 건 **테스트 방**이었다 —
            #    이름 두세 글자라 그 사람이 낀 방이 죄다 걸렸다.
            #    드물다고 안 막을 이유는 없다. 남의 대화창을 여는 것 자체를 피한다.
            titles = self._result_titles(main)
            index = _exact_row(titles, room_name)
            if index is None:
                near = ", ".join(titles[:5]) or "(제목을 읽지 못함)"
                raise RuntimeError(
                    f"제목이 정확히 같은 방을 찾지 못했습니다: {room_name!r} · "
                    f"검색 결과 {len(titles)}건 [{near}]"
                )

            raw = _osa(
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  set c to UI element 1 of (row {index} of first table of '
                f'first scroll area of ({main}))\n'
                f'  set p to position of c\n'
                f'  set s to size of c\n'
                f'  return ((item 1 of p) as text) & "|" & ((item 2 of p) as text) & "|" '
                f'& ((item 1 of s) as text) & "|" & ((item 2 of s) as text)\n'
                f'end tell'
            )
            x, y, w, h = [int(v) for v in raw.split("|")]
            _double_click(x + w // 2, y + h // 2)
            # 창이 뜨는 즉시 넘어간다 (대기는 AppleScript 안에서).
            _osa(
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  repeat 40 times\n'
                f'    if (exists window "{_esc(room_name)}") then return "open"\n'
                f'    delay 0.05\n'
                f'  end repeat\n'
                f'  return "timeout"\n'
                f'end tell'
            )
        except (AccessibilityError, QuartzUnavailable):
            raise
        except Exception:
            log.exception("_open_room_via_search 실패 room=%r", room_name)

    def _result_titles(self, main: str) -> List[str]:
        """검색 결과 각 행의 **방 제목**. 행 순서를 그대로 유지한다.

        제목을 못 읽은 행도 빈 줄로 남긴다 — 자리를 건너뛰면 행 번호가 밀려
        엉뚱한 방을 누르게 된다.
        """
        raw = _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  set t to first table of first scroll area of ({main})\n'
            f'  set acc to ""\n'
            f'  repeat with rw in rows of t\n'
            f'    set one to ""\n'
            f'    try\n'
            f'      set one to value of (first static text of (UI element 1 of rw))\n'
            f'    end try\n'
            f'    set acc to acc & one & "\\n"\n'
            f'  end repeat\n'
            f'  return acc\n'
            f'end tell'
        )
        return [line.strip() for line in raw.split("\n")][:MAX_SEARCH_ROWS]

    def _input_ref(self, room_name: str) -> str:
        return (
            f'text area 1 of scroll area 2 of '
            f'(first window whose name is "{_esc(room_name)}")'
        )

    def _get_input_text(self, room_name: str) -> str:
        try:
            return _osa(
                f'tell application "System Events" to tell process "{APP}" '
                f'to return value of ({self._input_ref(room_name)})'
            )
        except Exception:
            return ""

    def _set_input_text(self, room_name: str, text: str) -> bool:
        """입력창에 본문을 넣고, 실제로 들어갔는지 확인한다.

        AppleScript 문자열 이스케이프(따옴표/줄바꿈/한글)를 피하려고 임시 파일 경유.
        """
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(text)
            path = fh.name
        try:
            _osa(
                f'set msg to (read POSIX file "{path}" as «class utf8»)\n'
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  set focused of ({self._input_ref(room_name)}) to true\n'
                f'  set value of ({self._input_ref(room_name)}) to msg\n'
                f'  repeat 30 times\n'
                f'    if (value of ({self._input_ref(room_name)})) is not "" then exit repeat\n'
                f'    delay 0.05\n'
                f'  end repeat\n'
                f'end tell'
            )
            return bool(self._get_input_text(room_name).strip())
        except AccessibilityError:
            raise
        except Exception:
            log.exception("_set_input_text 실패")
            return False
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    # --- Sender 인터페이스 ---------------------------------------------------

    def discover_rooms(self, query: str, marker: str = "") -> List[str]:
        """검색어로 카톡방을 찾아 **실제 방 제목 목록**을 돌려준다.

        방 이름을 우리가 만들어 맞추는 건 불가능하다는 게 실기에서 드러났다:
        같은 캠페인 방인데도 어떤 방은 'Deal 공유'가 있고 없고, 끝에 담당자
        이름이 붙기도 한다(예: '… 우리브이씨 Asset 담당자이름').
        그래서 이름+직함으로 검색해 **실제 제목을 읽어온다.**

        marker 가 주어지면 그 문자열을 포함한 방만 남긴다. 같은 사람과의 다른
        대화방(1:1 등)을 걸러내고 딜소개 방만 고르기 위함이다.

        방을 열지 않는다 — 검색 결과 행의 텍스트만 읽으므로 빠르고 부작용이 없다.
        """
        if not query.strip():
            return []
        self._activate()
        if not self._focus_window("카카오톡"):
            raise RuntimeError("카카오톡 메인 창을 앞으로 가져오지 못했습니다.")

        main = 'first window whose name is "카카오톡"'
        field = f'first UI element of ({main}) whose role is "AXTextField"'

        # 검색어를 넣고, **결과가 실제로 갱신될 때까지** 기다린다.
        # 카톡 검색 결과는 한 박자 늦게 반영돼서, 바로 읽으면 직전 검색의 결과가
        # 잡힌다(실기 확인: '가나' 검색인데 '다라' 방이 나옴 → 엉뚱한 방 저장 위험).
        # 그래서 "검색어의 이름이 포함된 행"이 나타날 때까지만 통과시킨다.
        needle = query.split()[0] if query.split() else query
        raw = _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  set sf to {field}\n'
            f'  set focused of sf to true\n'
            f'  set value of sf to "{_esc(query)}"\n'
            f'  set acc to ""\n'
            f'  set emptyHits to 0\n'
            f'  repeat 25 times\n'
            f'    delay 0.08\n'
            f'    set acc to ""\n'
            f'    try\n'
            f'      set t to first table of first scroll area of ({main})\n'
            f'      set n to (count of rows of t)\n'
            f'      -- 결과가 아예 없으면 몇 번만 더 보고 빨리 포기한다(없는 사람 대기 단축).\n'
            f'      if n is 0 then\n'
            f'        set emptyHits to emptyHits + 1\n'
            f'        if emptyHits ≥ 3 then exit repeat\n'
            f'      end if\n'
            f'      if n ≤ {MAX_SEARCH_ROWS} and n > 0 then\n'
            f'        repeat with rw in rows of t\n'
            f'          try\n'
            f'            set acc to acc & (value of (first static text of (UI element 1 of rw))) & "\\n"\n'
            f'          end try\n'
            f'        end repeat\n'
            f'        if acc contains "{_esc(needle)}" then exit repeat\n'
            f'      end if\n'
            f'    end try\n'
            f'  end repeat\n'
            f'  return acc\n'
            f'end tell'
        )
        titles = [t.strip() for t in raw.split("\n") if t.strip()]
        # 이전 검색 결과가 섞이지 않도록 이름이 포함된 것만 인정한다.
        # (카톡은 참여자 이름으로도 검색되므로, 제목에 이름이 없는 단체방이
        #  섞여 들어온다 — 그건 우리가 찾는 방이 아니다)
        titles = [t for t in titles if needle and needle in t]
        if marker:
            titles = [t for t in titles if marker in t]
        return titles

    def verify_room(self, room_name: str) -> str:
        """방 존재/모호성 확인. 전송은 하지 않는다."""
        if not room_name or not room_name.strip():
            return "not_found"
        try:
            titles = self.window_titles()
            exact = [t for t in titles if t == room_name]
            if len(exact) > 1:
                return "ambiguous"
            if exact:
                return "verified"
            self._open_room_via_search(room_name)
            titles = self.window_titles()
            exact = [t for t in titles if t == room_name]
            if len(exact) > 1:
                return "ambiguous"
            return "verified" if exact else "not_found"
        except AccessibilityError:
            raise
        except Exception:
            log.exception("verify_room 실패")
            return "not_found"

    def _front_title(self) -> str:
        """지금 최전면 카톡 창의 제목. 오발송 방지 검증의 근거."""
        return _osa(
            f'tell application "System Events" to tell process "{APP}" '
            f'to return name of front window'
        )

    def _ensure_room_front(self, room_name: str) -> Optional[SendResult]:
        """방을 앞으로 올리고 **최전면 창 제목이 정확히 일치하는지** 확인한다.

        문제가 없으면 None, 있으면 그대로 돌려줄 실패 결과를 준다.

        ★ 이 판단이 사는 자리는 여기 하나뿐이다. `send_text` 와 `send_file` 이
        같이 쓴다 — 두 군데에 적어 놓으면 한쪽이 낡는다(이 저장소에서 되풀이된
        사고 유형이다).
        """
        # 1) 이미 열린 창이 있으면 그걸 쓰고, 없으면 검색으로 연다.
        #    방이 막 열리는 순간 포커스가 잡히지 않아 실패하는 일이 있었다
        #    (실기: 1회차 room_not_found → 2회차 성공). 일시적 타이밍 문제이므로
        #    한 번 더 시도한다. 재시도해도 안 되면 그대로 실패로 남긴다.
        if not self._focus_window(room_name):
            opened = False
            for attempt in (1, 2):
                try:
                    self._open_room_via_search(room_name)
                except QuartzUnavailable as exc:
                    # 창이 안 열려 있고 자동 열기도 불가 → 사용자가 창만 열어두면 된다.
                    return SendResult(ok=False, error=f"room_not_open: {exc}")
                except Exception as exc:  # noqa: BLE001
                    log.warning("방 열기 %d회차 실패: %s", attempt, exc)
                if self._focus_window(room_name):
                    opened = True
                    break
                time.sleep(0.6)
            if not opened:
                return SendResult(ok=False, error=f"room_not_found: {room_name!r}")

        # 2) ★ 오발송 방지: 최전면 창 제목이 room_name 과 정확히 일치하는지 재확인
        front = self._front_title()
        if front != room_name:
            log.warning("room mismatch: front=%r expected=%r", front, room_name)
            return SendResult(
                ok=False,
                error=f"room_mismatch: 열린 창 {front!r} != 대상 {room_name!r} (전송 안 함)",
            )
        return None

    def send_text(self, room_name: str, text: str) -> SendResult:
        """기존 방을 열어 텍스트 전송. 제목 불일치면 절대 보내지 않는다."""
        if not room_name or not room_name.strip():
            return SendResult(ok=False, error="room_name empty")

        try:
            # 1~2) 방을 열고 창 제목을 확인한다 (send_file 과 같은 판단을 쓴다).
            bad = self._ensure_room_front(room_name)
            if bad is not None:
                return bad

            # 3) 본문 입력
            # 실기 확인 결과: Cmd+V(클립보드 붙여넣기)는 카톡 Mac 입력창에 들어가지 않는다.
            # AX 로 value 를 직접 설정하는 방식은 동작하며 한글/줄바꿈도 안전하다.
            # 문자열 이스케이프 문제를 피하려고 임시 파일을 경유해 읽는다.
            if not self._set_input_text(room_name, text):
                return SendResult(
                    ok=False,
                    error="input_not_filled: 입력창에 본문을 넣지 못했습니다(전송 안 함)",
                )

            # 4) 전송 버튼 클릭 (Enter 보다 확실)
            _osa(
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  click (button "전송" of (first window whose name is "{_esc(room_name)}"))\n'
                f'  repeat 30 times\n'
                f'    if (value of ({self._input_ref(room_name)})) is "" then exit repeat\n'
                f'    delay 0.05\n'
                f'  end repeat\n'
                f'end tell'
            )

            # 5) ★ 실제 전송 검증: 입력창이 비었으면 전송된 것으로 본다.
            #    (예전엔 이 확인이 없어 '보냈다'고 거짓 보고하는 문제가 있었다.)
            leftover = self._get_input_text(room_name)
            if leftover.strip():
                return SendResult(
                    ok=False,
                    error="send_not_confirmed: 전송 후에도 입력창에 본문이 남아 있습니다",
                )

            if self.close_after_send:
                try:
                    self._keystroke("w", cmd=True)   # 창 닫기(목록만 남김)
                except Exception:
                    pass

            log.info("[kakao_mac] SENT room=%r chars=%d", room_name, len(text))
            return SendResult(ok=True)

        except AccessibilityError as exc:
            return SendResult(ok=False, error=str(exc))
        except Exception as exc:
            log.exception("send_text 실패")
            return SendResult(ok=False, error=f"kakao_mac: {exc}")

    # --- 파일 전송 (IR 자료) -------------------------------------------------
    #
    # 실기로 확인된 길이다. 요약하면:
    #   채팅창의 `파일전송 ⌘O` 단추 → 표준 열기 패널(NSOpenPanel) →
    #   Cmd+Shift+G 로 경로 지정 → `열기` → **"파일 전송" 확인 시트** → `N개 전송`
    #
    # ★ 확인 시트가 **유일한 진짜 관문**이다. 보낸 뒤에는 파일 메시지 줄에 파일명이
    #   AX 로 안 나와서, 사후 검증은 "대화 줄 수가 늘었다" 까지가 한계다.
    #   그러니 나가기 **전에** 전부 맞는지 보고, 하나라도 어긋나면 취소한다.
    #
    # ⚠ 클립보드(Cmd+V)는 쓰지 않는다 — 카톡 Mac 은 붙여넣기를 통째로 무시한다
    #   (글자도 파일도). 열기 패널은 시스템 창이라 별개다.
    # ⚠ `send_text` 의 "입력창에 글자가 찼나" 검증을 여기 갖다 쓰면 안 된다.
    #   파일은 입력창에 글자로 안 들어가서 성공해도 실패로 처리된다.

    def _chat_rows(self, room_name: str) -> Optional[int]:
        """대화 줄 수. 전송 전후를 견주어 실제로 나갔는지 보는 데 쓴다."""
        try:
            raw = _osa(
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  set w to (first window whose name is "{_esc(room_name)}")\n'
                f'  set n to -1\n'
                f'  repeat with sa in (scroll areas of w)\n'
                f'    try\n'
                f'      set n to (count of rows of (first table of sa))\n'
                f'      exit repeat\n'
                f'    end try\n'
                f'  end repeat\n'
                f'  return n as text\n'
                f'end tell'
            )
            value = int(raw)
        except Exception:  # noqa: BLE001
            return None
        return value if value >= 0 else None

    def _click_file_button(self, room_name: str) -> bool:
        """`파일전송 ⌘O` 단추를 **help 값으로 찾아** 누른다.

        ⚠ 인덱스로 찾지 않는다 — 창마다 단추 순서가 흔들린다.
        ⚠ `entire contents` 를 쓰지 않는다 — 카톡 AX 가 먹통이 된다(창이 0개가
          되고 카톡을 재시작해야 산다). 자식을 세 겹까지만 훑는다.
        """
        needle = _esc(self.file_button_help)
        find = (
            f'      set cands to (every button of {{ref}} whose help contains "{needle}")\n'
            f'      if (count of cands) > 0 then\n'
            f'        set target to item 1 of cands\n'
            f'      end if\n'
        )
        raw = _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  set w to (first window whose name is "{_esc(room_name)}")\n'
            f'  set target to missing value\n'
            f'  try\n'
            + find.format(ref="w") +
            f'  end try\n'
            f'  if target is missing value then\n'
            f'    repeat with e1 in (UI elements of w)\n'
            f'      try\n'
            + find.format(ref="e1") +
            f'      end try\n'
            f'      if target is not missing value then exit repeat\n'
            f'      repeat with e2 in (UI elements of e1)\n'
            f'        try\n'
            + find.format(ref="e2") +
            f'        end try\n'
            f'        if target is not missing value then exit repeat\n'
            f'      end repeat\n'
            f'      if target is not missing value then exit repeat\n'
            f'    end repeat\n'
            f'  end if\n'
            f'  if target is missing value then return "none"\n'
            f'  click target\n'
            f'  return "clicked"\n'
            f'end tell'
        )
        return raw.strip() == "clicked"

    def _sheet_snapshot(self, room_name: str) -> dict:
        """방 창에 떠 있는 시트를 **한 번의 AX 호출로** 통째로 읽는다.

        ⚠ 반복 변수 이름을 한두 글자로 줄이지 말 것. `st` 로 두었더니 AppleScript 가
          예약어로 읽어 `-2741 syntax error` 로 죽었다(실기에서 잡았다).

        열기 패널인지 확인 시트인지, 어떤 단추·파일명이 있는지가 한 스냅샷에
        들어온다. 한 번에 읽어야 하는 이유: 검사 사이에 창이 바뀌면 '봤을 때는
        맞았는데 누를 때는 달라진' 상태가 된다.
        """
        raw = _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  set acc to ""\n'
            f'  set fr to ""\n'
            f'  try\n'
            f'    set fr to (name of front window)\n'
            f'  end try\n'
            f'  set acc to acc & "FRONT\\t" & fr & "\\n"\n'
            f'  try\n'
            f'    set w to (first window whose name is "{_esc(room_name)}")\n'
            f'  on error\n'
            f'    return acc & "NOWIN\\n"\n'
            f'  end try\n'
            f'  if not (exists sheet 1 of w) then return acc\n'
            f'  set sh to sheet 1 of w\n'
            f'  set acc to acc & "PRESENT\\n"\n'
            f'  try\n'
            f'    set acc to acc & "IDENT\\t" & '
            f'(value of attribute "AXIdentifier" of sh) & "\\n"\n'
            f'  end try\n'
            f'  repeat with btnEl in (buttons of sh)\n'
            f'    try\n'
            f'      set acc to acc & "BTN\\t" & (name of btnEl) & "\\n"\n'
            f'    end try\n'
            f'  end repeat\n'
            f'  repeat with txtEl in (static texts of sh)\n'
            f'    try\n'
            f'      set acc to acc & "TXT\\t" & (value of txtEl) & "\\n"\n'
            f'    end try\n'
            f'  end repeat\n'
            f'  repeat with sa in (scroll areas of sh)\n'
            f'    try\n'
            f'      set tb to (first table of sa)\n'
            f'      set acc to acc & "ROWS\\t" & ((count of rows of tb) as text) & "\\n"\n'
            f'      repeat with rowEl in (rows of tb)\n'
            f'        repeat with cellEl in (UI elements of rowEl)\n'
            f'          try\n'
            f'            if (role of cellEl) is "AXStaticText" then set acc to '
            f'acc & "TXT\\t" & (value of cellEl) & "\\n"\n'
            f'          end try\n'
            f'          try\n'
            f'            repeat with subText in (static texts of cellEl)\n'
            f'              set acc to acc & "TXT\\t" & (value of subText) & "\\n"\n'
            f'            end repeat\n'
            f'          end try\n'
            f'        end repeat\n'
            f'      end repeat\n'
            f'      exit repeat\n'
            f'    end try\n'
            f'  end repeat\n'
            f'  return acc\n'
            f'end tell'
        )
        return parse_sheet_snapshot(raw)

    def _goto_field_do(self, room_name: str, body: str = "") -> Optional[str]:
        """열기 패널의 '폴더로 이동' 입력칸을 찾아 `body` 를 수행하고 값을 되읽는다.

        칸을 못 찾으면 None. 되읽는 것이 핵심이다 — 넣었다고 믿고 Enter 를 치면
        엉뚱한 폴더가 열린다.

        ★ **'폴더로 이동' 시트 안에서만 찾는다.** 열기 패널 자신에게도 텍스트
          칸이 하나 있는데 그것은 **검색칸**(`AXIdentifier` = `Search`)이다.
          예전에는 시트가 없으면 패널까지 뒤져서 그 검색칸을 잡았고, 거기에
          경로를 넣고 **되읽어 같으니 통과**시켰다 — 되읽기 검증이 엉뚱한 칸을
          확인해 주는 셈이라 아무 소용이 없었다. 그러고 Enter 를 치면 폴더로
          가는 대신 **검색**이 돌아, 아무 파일도 골리지 않은 채 `열기` 가 먹지
          않고 확인 시트가 끝내 뜨지 않는다(실기에서 이렇게 막혔다).

          시트가 없으면 None 을 돌려준다 — **막히는 쪽이 맞다.** 엉뚱한 칸에
          경로를 적어 넣는 것보다 "경로를 못 넣었다"고 실패하는 편이 낫다.
        """
        raw = _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  try\n'
            f'    set w to (first window whose name is "{_esc(room_name)}")\n'
            f'    set p to (sheet 1 of w)\n'
            f'  on error\n'
            f'    return "NOFIELD"\n'
            f'  end try\n'
            f'  if not (exists sheet 1 of p) then return "NOFIELD"\n'
            f'  set g to (sheet 1 of p)\n'
            f'  set target to missing value\n'
            f'  try\n'
            f'    set cands to (every combo box of g)\n'
            f'    if (count of cands) is 0 then set cands to (every text field of g)\n'
            f'    if (count of cands) > 0 then set target to item 1 of cands\n'
            f'  end try\n'
            f'  if target is missing value then\n'
            f'    repeat with e1 in (UI elements of g)\n'
            f'      try\n'
            f'        set cands to (every combo box of e1)\n'
            f'        if (count of cands) is 0 then set cands to (every text field of e1)\n'
            f'        if (count of cands) > 0 then\n'
            f'          set target to item 1 of cands\n'
            f'          exit repeat\n'
            f'        end if\n'
            f'      end try\n'
            f'    end repeat\n'
            f'  end if\n'
            f'  if target is missing value then return "NOFIELD"\n'
            f'  try\n'
            f'    set focused of target to true\n'
            f'  end try\n'
            f'{body}'
            f'  set out to ""\n'
            f'  try\n'
            f'    set out to (value of target) as text\n'
            f'  end try\n'
            f'  return "VALUE\\t" & out\n'
            f'end tell'
        )
        if raw.strip() == "NOFIELD":
            return None
        _, _, value = raw.partition("\t")
        return value

    def _panel_goto(self, room_name: str, path: str) -> bool:
        """열기 패널에서 `Cmd+Shift+G` 로 **경로를 명시해** 넣는다.

        ★ 파일마다 매번 한다. 패널은 마지막 위치를 기억하므로 생략하면
          엉뚱한 폴더가 잡힌다.

        한글이 섞인 경로가 들어온다(기업 폴더 이름). AppleScript 의 keystroke 는
        한글을 못 보내므로 **AX value 직접 설정**을 먼저 쓰고, 안 되면 클립보드,
        그래도 안 되면(ASCII 경로일 때만) 타이핑 순으로 내려간다.
        여기서 쓰는 클립보드는 **시스템 열기 패널** 쪽이라 카톡 입력창과 다르다.

        어느 길로 넣었든 **되읽어 같은지 확인한 뒤에만** Enter 를 친다.

        ⚠ `Cmd+Shift+G` 는 **키 코드**(key code 5)로 보낸다. `keystroke "g"` 로
          보내면 입력원이 한글일 때 통째로 먹히지 않는다 — 글자를 찍는 방식이라
          자판 배열을 타기 때문이다. 실기에서 이것 때문에 '폴더로 이동' 시트가
          안 뜨고, 위 검색칸 문제와 겹쳐 **경로를 넣었다고 착각한 채** 확인
          시트가 뜨지 않았다. 물리 키는 입력원과 무관하다.
        """
        self._key_code(GOTO_KEY_CODE, cmd=True, shift=True)
        if _wait_until(lambda: self._goto_field_do(room_name) is not None,
                       timeout=self.t_panel) is None:
            log.warning("'폴더로 이동' 입력칸을 찾지 못했습니다")
            return False

        # ① AX value 직접 설정 (한글 포함 어떤 경로든 들어간다)
        got = self._goto_field_do(
            room_name,
            f'  try\n'
            f'    set value of target to "{_esc(path)}"\n'
            f'  end try\n'
            f'  delay 0.15\n',
        )
        if got == path:
            self._press_enter()
            return True

        # ② 클립보드 붙여넣기
        try:
            _set_clipboard(path)
            self._goto_field_do(room_name, '  try\n    set value of target to ""\n  end try\n')
            self._keystroke("v", cmd=True)
            time.sleep(0.2)
            if self._goto_field_do(room_name) == path:
                self._press_enter()
                return True
        except Exception:  # noqa: BLE001
            log.warning("클립보드로 경로 넣기 실패", exc_info=True)

        # ③ 타이핑 (ASCII 경로에서만 가능)
        if path.isascii():
            try:
                self._goto_field_do(room_name,
                                    '  try\n    set value of target to ""\n  end try\n')
                _type_text(path)
                time.sleep(0.2)
                if self._goto_field_do(room_name) == path:
                    self._press_enter()
                    return True
            except Exception:  # noqa: BLE001
                log.warning("타이핑으로 경로 넣기 실패", exc_info=True)

        log.warning("경로를 입력칸에 넣지 못했습니다: %r (읽은 값=%r)", path, got)
        return False

    def _click_open_button(self, room_name: str) -> bool:
        """열기 패널의 `열기`(OKButton)를 누른다."""
        raw = _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  try\n'
            f'    set sh to (sheet 1 of (first window whose name is '
            f'"{_esc(room_name)}"))\n'
            f'  on error\n'
            f'    return "none"\n'
            f'  end try\n'
            f'  set target to missing value\n'
            f'  repeat with btnEl in (buttons of sh)\n'
            f'    try\n'
            f'      if (value of attribute "AXIdentifier" of btnEl) is '
            f'"{OPEN_BUTTON_ID}" then\n'
            f'        set target to btnEl\n'
            f'        exit repeat\n'
            f'      end if\n'
            f'    end try\n'
            f'  end repeat\n'
            f'  if target is missing value then\n'
            f'    try\n'
            f'      set target to (first button of sh whose name is "{OPEN_BUTTON_NAME}")\n'
            f'    end try\n'
            f'  end if\n'
            f'  if target is missing value then return "none"\n'
            f'  click target\n'
            f'  return "clicked"\n'
            f'end tell'
        )
        return raw.strip() == "clicked"

    def _open_until_confirm(self, room_name: str) -> Optional[str]:
        """`열기` 를 눌러 "파일 전송" 확인 시트를 띄운다. 실패 사유(없으면 None).

        ★ **뜰 때까지 다시 누른다.** 열기 패널이 경로를 훑고 그 파일을 고르기
          전에 누르면 `열기` 가 아직 꺼져 있어 **아무 일도 일어나지 않는데**,
          AX 로는 '눌렀다' 로 보인다 — 단추가 있는지만 보고 누르기 때문이다.
          그래서 한 번만 누르고 기다리면 아무 일도 안 일어난 채 시간만 보내고
          "확인 창이 안 떴다" 로 실패한다. 실기에서 자료 5개 중 1개가 이렇게
          걸렸다(다시 돌리니 그대로 갔다 — 느려서 생기는 어긋남이다).

          다시 눌러도 두 번 나가지 않는다. 확인 시트가 떠 있으면 애초에 누르지
          않고, 실제로 내보내는 것은 관문을 지난 뒤의 `N개 전송` 이다.
        """
        found_button = False
        deadline = time.time() + self.t_confirm
        while True:
            snapshot = self._sheet_snapshot(room_name)
            if _is_confirm_sheet(snapshot):
                return None
            if not snapshot.get("present"):
                # 패널이 사라졌다. 무엇이 열렸는지 모르는 상태로 더 누르지 않는다.
                return "open_panel_gone: 파일 열기 창이 사라졌습니다 (전송 안 함)"
            if self._click_open_button(room_name):
                found_button = True
            if time.time() >= deadline:
                break
            time.sleep(self.t_open_retry)
        if not found_button:
            return ("open_button_not_found: 열기 단추를 찾지 못했습니다 (전송 안 함)")
        return ("confirm_sheet_not_shown: 파일 전송 확인 창이 뜨지 "
                "않았습니다 (전송 안 함)")

    def _click_sheet_button(self, room_name: str, name: str) -> bool:
        """시트 안의 이름이 정확히 같은 단추를 누른다."""
        raw = _osa(
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  try\n'
            f'    click (first button of (sheet 1 of (first window whose name is '
            f'"{_esc(room_name)}")) whose name is "{_esc(name)}")\n'
            f'  on error\n'
            f'    return "none"\n'
            f'  end try\n'
            f'  return "clicked"\n'
            f'end tell'
        )
        return raw.strip() == "clicked"

    def _dismiss_sheet(self, room_name: str) -> None:
        """열려 있는 시트를 **보내지 않고** 닫는다. 실패해도 넘어간다."""
        if not self._click_sheet_button(room_name, CANCEL_BUTTON):
            try:
                self._key_code(53)      # Esc
            except Exception:  # noqa: BLE001
                pass
        _wait_until(lambda: not self._sheet_snapshot(room_name).get("present"),
                    timeout=2.0)

    def send_file(self, room_name: str, file_names) -> SendResult:
        """IR 자료를 첨부해 보낸다. **관문을 통과할 때만 보낸다.**

        `file_names` 는 **공통 폴더 안의 파일명**이다(경로가 아니다). 실제 자리는
        이 PC 가 설정한 뿌리로 조립한다 — 경로는 PC 마다 다른 설정이고 파일명은
        서버가 들고 함께 쓰는 값이라, 나눠 갖는 지점이 여기다.
        규칙에 어긋나는 이름이나 이 PC 에 없는 파일은 **카톡을 건드리기 전에**
        거절한다 — 엉뚱한 파일이 나가는 것을 막는 선이다.

        **한 번에 한 파일씩** 보낸다. 열기 패널의 경로 입력칸은 한 번에 한 경로만
        받으므로, 여러 개를 한 시트에 몰아넣으려면 목록에서 마우스로 골라야 한다.
        그 길은 실기로 확인하지 않았다 — 확인한 길로만 간다. 대신 관문 검사는
        개수를 일반적으로 다루므로(`check_confirm_sheet`), 나중에 여러 개를 한
        번에 붙이게 되어도 검사는 그대로 쓴다.

        여러 개를 보내다 중간에 실패하면 **거기서 멈춘다.** 몇 개가 이미 나갔는지
        실패 문구에 적는다 — 다시 보내면 그만큼 겹친다는 것을 사람이 알아야 한다.
        """
        if not room_name or not room_name.strip():
            return SendResult(ok=False, error="room_name empty")

        wanted = list(file_names or [])
        if not wanted:
            return SendResult(ok=False, error="no_files: 보낼 파일이 없습니다")

        # ① 이름을 걸러 내고 이 PC 의 실제 경로로 조립한다.
        #    **카톡을 건드리기 전에** 한다. 반쯤 보내 놓고 막히면 되돌릴 수 없다.
        try:
            resolved = [resolve_ir_file(n, self.ir_root_setting) for n in wanted]
        except IrPathError as exc:
            return SendResult(ok=False, error=f"ir_file_rejected: {exc}")

        try:
            # ② 방 열기 + 창 제목 정확 일치 (send_text 와 **같은 판단**)
            bad = self._ensure_room_front(room_name)
            if bad is not None:
                return bad

            for n, path in enumerate(resolved, start=1):
                result = self._send_one_file(room_name, path)
                if not result.ok:
                    if n > 1:
                        result.error = (f"{n - 1}개를 보낸 뒤 {n}번째에서 실패 "
                                        f"— {result.error}")
                    return result

            if self.close_after_send:
                try:
                    self._keystroke("w", cmd=True)   # 창 닫기(목록만 남김)
                except Exception:  # noqa: BLE001
                    pass

            log.info("[kakao_mac] SENT FILES room=%r files=%s",
                     room_name, [p.name for p in resolved])
            return SendResult(ok=True)

        except AccessibilityError as exc:
            return SendResult(ok=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("send_file 실패")
            return SendResult(ok=False, error=f"kakao_mac: {exc}")

    def _send_one_file(self, room_name: str, path) -> SendResult:
        """파일 하나. 확인 시트가 어긋나면 **취소하고 아무것도 보내지 않는다.**"""
        rows_before = self._chat_rows(room_name)

        # ③ `파일전송 ⌘O` 단추 (help 값으로 찾는다)
        if not self._click_file_button(room_name):
            return SendResult(
                ok=False,
                error=f"file_button_not_found: 채팅창에서 "
                      f"'{self.file_button_help}' 단추를 찾지 못했습니다 (전송 안 함)")

        # ④ 열기 패널이 떴는지 확인 → 매번 Cmd+Shift+G 로 경로를 명시
        if _wait_until(lambda: _is_open_panel(self._sheet_snapshot(room_name)),
                       timeout=self.t_panel) is None:
            return SendResult(ok=False,
                              error="open_panel_not_shown: 파일 열기 창이 뜨지 "
                                    "않았습니다 (전송 안 함)")

        if not self._panel_goto(room_name, str(path)):
            self._dismiss_sheet(room_name)
            return SendResult(ok=False,
                              error=f"path_not_entered: 열기 창에 경로를 넣지 "
                                    f"못했습니다: {path} (전송 안 함)")

        # ⑤ Enter 만으로 확인 시트가 바로 뜨는 판도 있다 — 잠깐만 본다.
        if _wait_until(lambda: _is_confirm_sheet(self._sheet_snapshot(room_name)),
                       timeout=self.t_confirm_quick) is None:
            # ⑥ `열기` → "파일 전송" 확인 시트. 안 뜨면 **아무것도 보내지 않는다.**
            reason = self._open_until_confirm(room_name)
            if reason:
                self._dismiss_sheet(room_name)
                return SendResult(ok=False, error=reason)

        # ⑦ ★ 관문. 전부 맞을 때만 보낸다.
        snapshot = self._sheet_snapshot(room_name)
        reason = check_confirm_sheet(snapshot, room_name, [path.name])
        if reason:
            log.warning("확인 시트가 어긋났습니다 — 취소합니다: %s | snapshot=%r",
                        reason, snapshot)
            self._dismiss_sheet(room_name)
            return SendResult(ok=False,
                              error=f"gate_blocked: {reason} "
                                    f"— 취소했습니다 (전송 안 함)")

        # ⑧ `1개 전송`
        button = SEND_BUTTON_FMT.format(n=1)
        if not self._click_sheet_button(room_name, button):
            self._dismiss_sheet(room_name)
            return SendResult(ok=False,
                              error=f"send_button_not_clicked: {button!r} 단추를 "
                                    f"누르지 못했습니다 (전송 안 함)")

        # ⑨ 줄 수가 늘었는지 확인.
        #    보낸 뒤에는 파일 메시지 줄에 파일명이 AX 로 안 나온다 — 여기까지가
        #    사후 검증의 한계다. 줄 수를 못 읽었으면 견주지 않는다(못 읽는 것과
        #    안 나간 것은 다르다).
        if rows_before is None:
            log.warning("전송 전 대화 줄 수를 읽지 못해 결과를 견주지 못했습니다 room=%r",
                        room_name)
            return SendResult(ok=True)

        grew = _wait_until(
            lambda: (self._chat_rows(room_name) or 0) > rows_before,
            timeout=self.t_sent,
        )
        if not grew:
            # 단추는 이미 눌렀다. 나갔는지 아닌지 모르는 상태라 사람이 봐야 한다.
            return SendResult(
                ok=False,
                error=f"send_unconfirmed: {button!r} 을 눌렀지만 대화 줄 수가 "
                      f"늘지 않았습니다({rows_before}). 카톡을 직접 확인하세요 "
                      f"— 다시 보내면 겹칠 수 있습니다")
        return SendResult(ok=True)


# ── 확인 시트 읽기·검사 (AX 와 떨어져 있어 그대로 시험할 수 있다) ────────────

def parse_sheet_snapshot(raw: str) -> dict:
    """`_sheet_snapshot` 이 읽어 온 줄들을 풀어 놓는다.

    `KEY\tVALUE` 꼴이다. 단추 이름은 겹치면 하나만 남긴다 — 같은 단추가 두 겹으로
    잡히면 "개수 단추가 여러 개" 로 잘못 읽힌다.
    """
    snapshot = {"front_title": "", "present": False, "identifier": "",
                "buttons": [], "texts": [], "rows": None}
    for line in (raw or "").splitlines():
        key, _, value = line.partition("\t")
        key, value = key.strip(), value.strip()
        if key == "FRONT":
            snapshot["front_title"] = value
        elif key == "PRESENT":
            snapshot["present"] = True
        elif key == "IDENT":
            snapshot["identifier"] = value
        elif key == "BTN":
            if value and value not in snapshot["buttons"]:
                snapshot["buttons"].append(value)
        elif key == "TXT":
            if value:
                snapshot["texts"].append(value)
        elif key == "ROWS":
            try:
                snapshot["rows"] = int(value)
            except ValueError:
                pass
    return snapshot


def _is_open_panel(snapshot: dict) -> bool:
    """지금 떠 있는 시트가 **파일 열기 패널**인가."""
    if not snapshot.get("present"):
        return False
    return (snapshot.get("identifier") == OPEN_PANEL_ID
            or OPEN_BUTTON_NAME in snapshot.get("buttons", []))


def _is_confirm_sheet(snapshot: dict) -> bool:
    """지금 떠 있는 시트가 **"파일 전송" 확인 시트**인가.

    열기 패널에도 `취소` 는 있다. 개수가 박힌 단추(`N개 전송`)는 확인 시트에만
    있으므로 그것으로 가른다.
    """
    if not snapshot.get("present"):
        return False
    buttons = snapshot.get("buttons", [])
    return any(COUNT_BUTTON_RE.match(b) for b in buttons)


def check_confirm_sheet(snapshot: dict, room_name: str,
                        expected_names: List[str]) -> Optional[str]:
    """★ 관문. 보내려던 것과 **정확히 같을 때만** None 을 돌려준다.

    어긋나면 그 이유를 문자열로 돌려주고, 부르는 쪽은 **취소하고 아무것도 보내지
    않는다.** 보낸 뒤에는 파일 메시지 줄에 파일명이 AX 로 안 나와서 되돌아볼
    방법이 없다 — 그래서 나가기 전 이 자리가 유일한 진짜 관문이다.

    AX 에서 떼어 놓은 **순수 함수**다. 가짜 스냅샷으로 그대로 시험할 수 있다.
    """
    want = list(expected_names or [])
    if not snapshot or not snapshot.get("present"):
        return "확인 시트가 없습니다"

    # ① 방이 맞나 — 파일을 고르는 사이에 다른 창이 앞으로 나올 수 있다.
    #    한글은 자모 조합 형태가 두 가지라 그것만 맞춰 견준다(`base.nfc`).
    front = snapshot.get("front_title", "")
    if nfc(front) != nfc(room_name):
        return f"방이 다릅니다: 앞에 있는 창 {front!r} != 대상 {room_name!r}"

    buttons = snapshot.get("buttons", [])
    if CANCEL_BUTTON not in buttons:
        return f"확인 시트가 아닙니다({CANCEL_BUTTON!r} 단추가 없음): {buttons!r}"

    # ② 개수 단추의 숫자 — 실기에서 개수가 단추 이름에 박혀 나온다(`1개 전송`).
    counters = [b for b in buttons if COUNT_BUTTON_RE.match(b)]
    if not counters:
        return f"개수 단추를 찾지 못했습니다: {buttons!r}"
    if len(counters) > 1:
        return f"개수 단추가 여러 개입니다: {counters!r}"
    shown = int(COUNT_BUTTON_RE.match(counters[0]).group(1))
    if shown != len(want):
        return (f"개수가 다릅니다: 시트는 {shown}개인데 "
                f"보내려던 것은 {len(want)}개")

    # ③ 표의 줄 수 = 파일 개수. 못 읽었으면 **통과시키지 않는다** —
    #    못 읽는 것과 맞는 것은 다르다.
    rows = snapshot.get("rows")
    if rows is None:
        return "시트의 파일 목록을 읽지 못했습니다"
    if rows != len(want):
        return f"파일 목록이 {rows}줄인데 보내려던 것은 {len(want)}개"

    # ④ 파일명이 전부 있나.
    #
    #    ★ 두 쪽을 **같은 형태로 맞춘 뒤** 견준다(`base.same_file_name`).
    #      시트에서 읽어 온 이름과 보내려던 이름은 한글 자모 조합 형태가
    #      서로 다를 수 있다 — macOS 디스크는 쪼갠 형태(NFD), 웹 화면에
    #      타이핑한 값은 합친 형태(NFC). 눈에는 같은데 `==` 로는 다르다.
    #      그냥 견주면 **멀쩡한 파일을 "시트에 없다"며 취소**한다(가짜 실패).
    #
    #    ⚠ 무르게 하는 정규화가 아니다. 형태만 맞출 뿐 글자가 다른 이름은
    #      그대로 걸린다 — 관문이 하는 일(다른 파일을 막는 것)은 그대로다.
    texts = snapshot.get("texts", [])
    missing = [n for n in want
               if not any(same_file_name(n, shown) for shown in texts)]
    if missing:
        return f"시트에 없는 파일: {missing!r} (시트에 있는 것: {texts!r})"
    return None


def _norm(text: str) -> str:
    """제목 비교용. 연속 공백만 줄인다 — 그 밖의 보정은 하지 않는다.

    한 글자만 달라도 다른 방이므로, 임의로 맞춰 주면 엉뚱한 방을 열게 된다.
    """
    return " ".join((text or "").split())


def _exact_row(titles: List[str], room_name: str) -> Optional[int]:
    """제목이 정확히 같은 행 번호(1부터). 없으면 None.

    같은 제목이 여러 개면 **고르지 않는다** — 어느 쪽인지 알 수 없는데
    아무거나 열면 남의 대화창일 수 있다.
    """
    want = _norm(room_name)
    hits = [i for i, title in enumerate(titles, start=1) if _norm(title) == want]
    return hits[0] if len(hits) == 1 else None


def _esc(text: str) -> str:
    """AppleScript 문자열 리터럴용 이스케이프."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def create(cfg: Optional[dict] = None) -> "KakaoMacSender":
    if not is_supported():
        raise RuntimeError("KakaoMacSender 는 macOS 전용입니다.")
    return KakaoMacSender(cfg)
