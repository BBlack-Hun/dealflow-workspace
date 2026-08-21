"""카카오톡 창 진단 도구 (Windows / macOS 공통).

`room_mismatch` 가 났을 때 **실제 창 제목이 무엇인지** 확인하기 위한 것.
발송은 창 제목이 정확히 일치할 때만 이뤄지므로(오발송 방지), 등록한 방 이름과
실제 제목이 한 글자라도 다르면 전송되지 않는다.

사용:
    python -m agent.diagnose                 # 현재 열린 카톡 창 목록
    python -m agent.diagnose "홍길동"         # 그 방을 열어보고 결과 보고

이 도구는 **메시지를 보내지 않는다.** 창을 열어 제목만 읽는다.
"""
from __future__ import annotations

import platform
import sys
import time


def _windows_titles() -> list:
    from pywinauto import Desktop

    titles = []
    for w in Desktop(backend="uia").windows():
        try:
            t = w.window_text()
        except Exception:
            continue
        if t and t.strip():
            titles.append(t)
    return titles


def _mac_titles() -> list:
    import subprocess

    out = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to tell process "KakaoTalk" to return name of windows'],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return [t.strip() for t in out.stdout.split(",") if t.strip()]


def list_titles() -> list:
    return _windows_titles() if platform.system() == "Windows" else _mac_titles()


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    system = platform.system()
    print(f"[진단] OS = {system}\n")

    try:
        titles = list_titles()
    except Exception as exc:
        print(f"[오류] 창 목록을 읽지 못했습니다: {exc}")
        if system == "Darwin":
            print("      → 시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용 에서 터미널을 허용하세요.")
        return

    print("── 현재 열려 있는 창 제목 " + "─" * 30)
    if not titles:
        print("  (없음)")
    for t in titles:
        # 앞뒤 공백이 눈에 보이도록 따옴표로 감싼다 (제목 불일치의 흔한 원인)
        print(f"  {t!r}")
    print()

    if not target:
        print("특정 방을 확인하려면:  python -m agent.diagnose \"방 이름\"")
        print()
        print("※ 카카오톡 설정에서 '채팅방을 하나의 창에서 보기'가 켜져 있으면")
        print("   방마다 별도 창이 생기지 않아 제목 일치 검사가 실패합니다.")
        print("   그 경우 해당 설정을 꺼주세요.")
        return

    print(f"── '{target}' 확인 " + "─" * 34)
    exact = [t for t in titles if t == target]
    if exact:
        print(f"  ✅ 정확히 일치하는 창이 이미 열려 있습니다 ({len(exact)}개)")
        if len(exact) > 1:
            print("     ⚠ 같은 제목의 창이 여러 개라 모호합니다(ambiguous).")
        return

    near = [t for t in titles if target in t or t in target]
    if near:
        print("  ⚠ 정확히 일치하지는 않지만 비슷한 창이 있습니다:")
        for t in near:
            print(f"     실제: {t!r}")
            print(f"     등록: {target!r}")
        print("  → 웹의 담당자 '카톡방 이름'을 위 '실제' 값과 똑같이 고치세요.")
        return

    print("  창 목록에 없습니다. 검색으로 열어봅니다...")
    try:
        _try_open(target)
        time.sleep(1.5)
        after = list_titles()
        new = [t for t in after if t not in titles]
        if any(t == target for t in after):
            print("  ✅ 열렸고 제목이 정확히 일치합니다.")
        elif new:
            print("  ⚠ 창이 열렸지만 제목이 다릅니다:")
            for t in new:
                print(f"     실제: {t!r}  ↔  등록: {target!r}")
        else:
            print("  ❌ 방이 열리지 않았습니다.")
            print("     - 방 이름이 카톡에 실제로 존재하는지 확인하세요.")
            print("     - '채팅방을 하나의 창에서 보기' 설정이 켜져 있으면 꺼주세요.")
    except Exception as exc:
        print(f"  [오류] 열기 시도 실패: {exc}")


def _try_open(room_name: str) -> None:
    """검색으로 방 열기 시도 (전송하지 않음)."""
    if platform.system() == "Windows":
        import pyautogui, pyperclip
        from pywinauto import Desktop

        win = Desktop(backend="uia").window(title_re="카카오톡.*")
        win.wait("exists ready", timeout=5)
        win.set_focus()
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)
        pyperclip.copy(room_name)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(1.0)
        pyautogui.press("enter")
    else:
        from agent.sender import kakao_mac

        kakao_mac.create({})._open_room_via_search(room_name)


if __name__ == "__main__":
    main()
