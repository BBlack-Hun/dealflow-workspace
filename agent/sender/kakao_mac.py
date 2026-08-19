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
import subprocess
import time
from typing import List, Optional

from .base import SendResult, Sender

log = logging.getLogger("agent.kakao_mac")

APP = "KakaoTalk"


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

    참고: 카톡 Mac 입력창은 Cmd+V 를 받지 않아 본문 입력에는 쓰지 않는다(값 직접 설정 사용).
    """
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def _type_text(text: str) -> None:
    """실제 키 입력으로 타이핑 (검색어처럼 앱이 입력 이벤트를 요구하는 곳에 사용)."""
    _osa(f'tell application "System Events" to keystroke "{_esc(text)}"')


def _double_click(x: int, y: int) -> None:
    """실제 마우스 더블클릭. 카톡 채팅 목록은 AXPress/Enter 로 열리지 않는다.

    Quartz 로 클릭 이벤트를 합성한다(pyobjc-framework-Quartz 필요).
    """
    import Quartz

    for click_state in (1, 2):
        for kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            ev = Quartz.CGEventCreateMouseEvent(None, kind, (x, y), Quartz.kCGMouseButtonLeft)
            Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, click_state)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.06)


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

    # --- 기본 조작 -----------------------------------------------------------

    def _activate(self) -> None:
        _osa(f'tell application "{APP}" to activate')
        time.sleep(self.t_activate)

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
        script = (
            f'tell application "System Events" to tell process "{APP}"\n'
            f'  set frontmost to true\n'
            f'  delay 0.3\n'
            f'  set matches to (every window whose name is "{esc}")\n'
            f'  if (count of matches) is 0 then return "none"\n'
            f'  perform action "AXRaise" of item 1 of matches\n'
            f'  return "ok"\n'
            f'end tell'
        )
        if _osa(script) != "ok":
            return False

        # 창 순서가 실제로 바뀔 때까지 짧게 재확인(최대 ~2초).
        for _ in range(10):
            time.sleep(0.2)
            try:
                front = _osa(
                    f'tell application "System Events" to tell process "{APP}" '
                    f'to return name of front window'
                )
            except Exception:
                continue
            if front == title:
                return True
        return False

    def _keystroke(self, key: str, *, cmd: bool = False) -> None:
        mods = ' using command down' if cmd else ''
        _osa(f'tell application "System Events" to keystroke "{key}"{mods}')

    def _key_code(self, code: int) -> None:
        _osa(f'tell application "System Events" to key code {code}')

    def _press_enter(self) -> None:
        self._key_code(36)

    def _open_room_via_search(self, room_name: str) -> None:
        """메인창 검색으로 기존 방 열기 (방은 이미 존재한다는 전제).

        실기 확인으로 굳어진 절차(다른 방법은 동작하지 않음):
          - 검색 필드는 AXTextField. value 를 직접 넣으면 카톡이 검색을 인식하지 않아
            **실제 키 입력**(Cmd+A → 타이핑)이 필요하다.
          - 결과 행은 Enter/AXPress 로 열리지 않고 **실제 더블클릭**이 필요하다.
        """
        self._activate()
        main = 'first window whose name is "카카오톡"'
        try:
            # 1) 검색 필드 포커스 + 기존 내용 지우고 방 이름 입력(실제 키 이벤트)
            _osa(
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  set sf to first UI element of ({main}) whose role is "AXTextField"\n'
                f'  set focused of sf to true\n'
                f'end tell'
            )
            time.sleep(0.3)
            self._keystroke("a", cmd=True)
            time.sleep(0.2)
            _type_text(room_name)
            time.sleep(self.t_query)

            # 2) 첫 결과 행 더블클릭
            raw = _osa(
                f'tell application "System Events" to tell process "{APP}"\n'
                f'  set c to UI element 1 of (first row of first table of '
                f'first scroll area of ({main}))\n'
                f'  set p to position of c\n'
                f'  set s to size of c\n'
                f'  return ((item 1 of p) as text) & "|" & ((item 2 of p) as text) & "|" '
                f'& ((item 1 of s) as text) & "|" & ((item 2 of s) as text)\n'
                f'end tell'
            )
            x, y, w, h = [int(v) for v in raw.split("|")]
            _double_click(x + w // 2, y + h // 2)
            time.sleep(self.t_open_room)
        except AccessibilityError:
            raise
        except Exception:
            log.exception("_open_room_via_search 실패 room=%r", room_name)

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
                f'end tell'
            )
            time.sleep(self.t_paste)
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

    def send_text(self, room_name: str, text: str) -> SendResult:
        """기존 방을 열어 텍스트 전송. 제목 불일치면 절대 보내지 않는다."""
        if not room_name or not room_name.strip():
            return SendResult(ok=False, error="room_name empty")

        try:
            # 1) 이미 열린 창이 있으면 그걸 쓰고, 없으면 검색으로 연다.
            if not self._focus_window(room_name):
                self._open_room_via_search(room_name)
                if not self._focus_window(room_name):
                    return SendResult(ok=False, error=f"room_not_found: {room_name!r}")

            # 2) ★ 오발송 방지: 최전면 창 제목이 room_name 과 정확히 일치하는지 재확인
            front = _osa(
                f'tell application "System Events" to tell process "{APP}" '
                f'to return name of front window'
            )
            if front != room_name:
                log.warning("room mismatch: front=%r expected=%r", front, room_name)
                return SendResult(
                    ok=False,
                    error=f"room_mismatch: 열린 창 {front!r} != 대상 {room_name!r} (전송 안 함)",
                )

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
                f'tell application "System Events" to tell process "{APP}" '
                f'to click (button "전송" of (first window whose name is "{_esc(room_name)}"))'
            )
            time.sleep(self.t_send)

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


def _esc(text: str) -> str:
    """AppleScript 문자열 리터럴용 이스케이프."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def create(cfg: Optional[dict] = None) -> "KakaoMacSender":
    if not is_supported():
        raise RuntimeError("KakaoMacSender 는 macOS 전용입니다.")
    return KakaoMacSender(cfg)
