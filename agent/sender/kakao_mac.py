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

# 검색 결과에서 살펴볼 행 수 상한.
#
# 예전에는 이보다 많으면 "필터가 안 먹었다"고 보고 아예 중단했다. 첫 행을 누르는
# 방식이었기 때문이다. 지금은 **제목이 정확히 일치하는 행**을 찾아 누르므로
# 결과가 많아도 위험하지 않다 — 오히려 이름이 흔하면(참여자 이름으로도 걸린다)
# 20건은 너무 적어서 정작 찾는 방이 잘려 나갔다.
MAX_SEARCH_ROWS = 60


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

    def _key_code(self, code: int) -> None:
        _osa(f'tell application "System Events" to key code {code}')

    def _press_enter(self) -> None:
        self._key_code(36)

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
            #    잔뜩 나오고 첫 행은 대개 그중 하나다(실기: '홍길동' 검색 시
            #    본인 방을 못 찾음). 창 제목 검증이 오발송은 막아 주지만,
            #    남의 대화창을 여는 것 자체를 피해야 한다.
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

    def send_text(self, room_name: str, text: str) -> SendResult:
        """기존 방을 열어 텍스트 전송. 제목 불일치면 절대 보내지 않는다."""
        if not room_name or not room_name.strip():
            return SendResult(ok=False, error="room_name empty")

        try:
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
