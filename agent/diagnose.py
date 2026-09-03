"""카카오톡 창 진단 도구 (Windows / macOS 공통).

`room_mismatch` 가 났을 때 **실제 창 제목이 무엇인지** 확인하기 위한 것.
발송은 창 제목이 정확히 일치할 때만 이뤄지므로(오발송 방지), 등록한 방 이름과
실제 제목이 한 글자라도 다르면 전송되지 않는다.

사용:
    python -m agent.diagnose                    # 현재 열린 카톡 창 목록
    python -m agent.diagnose "홍길동"            # 그 방을 열어보고 결과 보고
    python -m agent.diagnose --search "홍길동"   # 검색 결과의 **실제 제목** 목록 (macOS)

`--search` 가 필요한 이유: 카톡 검색은 방 제목뿐 아니라 **참여자 이름으로도**
걸린다. 이름이 흔하면 그 사람이 낀 단체방이 잔뜩 나온다. 발송기는 그중
**제목이 정확히 같은 방**만 여는데, 등록해 둔 이름과 실제 제목이 다르면
아무 것도 못 연다. 무엇이 나오는지 눈으로 봐야 어떤 값을 넣을지 정할 수 있다.

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


def search_titles(query: str) -> None:
    """검색 결과에 **실제로 어떤 제목이 나오는지** 보여준다 (macOS).

    발송기가 고를 수 있는 후보를 그대로 보여주고, 정확히 일치하는 것이
    있는지 표시한다. 없으면 어떤 값을 등록해야 하는지 바로 알 수 있다.
    """
    if platform.system() != "Darwin":
        print("  --search 는 macOS 에서만 됩니다.")
        return
    from agent.sender import kakao_mac

    sender = kakao_mac.create()
    sender._activate()
    if not sender._focus_window("카카오톡"):
        print("  [오류] 카카오톡 메인 창을 앞으로 가져오지 못했습니다.")
        return

    main_ref = 'first window whose name is "카카오톡"'
    field = f'first UI element of ({main_ref}) whose role is "AXTextField"'
    kakao_mac._osa(
        f'tell application "System Events" to tell process "{kakao_mac.APP}"\n'
        f'  set sf to {field}\n'
        f'  set focused of sf to true\n'
        f'  set value of sf to "{kakao_mac._esc(query)}"\n'
        f'end tell'
    )
    time.sleep(1.2)      # 카톡 검색 결과는 한 박자 늦게 반영된다
    titles = sender._result_titles(main_ref)

    print(f"── '{query}' 검색 결과 " + "─" * 30)
    if not any(titles):
        print("  (결과 없음 — 검색어를 확인하세요)")
        return
    want = kakao_mac._norm(query)
    hit = None
    for i, title in enumerate(titles, start=1):
        if not title:
            print(f"  {i:2}. (제목을 읽지 못함)")
            continue
        same = kakao_mac._norm(title) == want
        if same:
            hit = i
        print(f"  {i:2}. {title!r}{'   ← 정확히 일치' if same else ''}")
    print()
    if hit:
        print(f"  ✅ {hit}번을 열게 됩니다.")
    else:
        print("  ❌ 제목이 정확히 같은 방이 없습니다.")
        print("     위 목록에서 실제 방 제목을 골라 그대로 등록하세요.")
        print("     (테스트 방이면 .env 의 DEALFLOW_TEST_ROOM,")
        print("      담당자 방이면 웹의 '카톡방 이름')")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--search":
        if len(args) < 2:
            print('사용: python -m agent.diagnose --search "검색어"')
            return
        search_titles(args[1])
        return

    target = args[0] if args else None
    system = platform.system()
    print(f"[진단] OS = {system}\n")

    try:
        titles = list_titles()
    except Exception as exc:
        print(f"[오류] 창 목록을 읽지 못했습니다: {exc}")
        if system == "Darwin":
            print("      → 시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용 에서 터미널을 허용하세요.")
        return

    # ★ Quartz 는 '채팅방 자동 열기' 에만 쓰이지만, 없으면 창을 미리 열어두지
    #   않은 방은 통째로 실패한다. 발송 실패로 알게 되기 전에 여기서 알린다.
    if system == "Darwin":
        from agent.sender.kakao_mac import quartz_available

        if quartz_available():
            print("[진단] Quartz(pyobjc) ✅ — 채팅방 자동 열기 가능\n")
        else:
            print("[진단] Quartz(pyobjc) ❌ — 채팅방을 자동으로 열 수 없습니다.")
            print("      → 보낼 채팅방 창을 카카오톡에서 미리 열어두면 발송됩니다.")
            print("      → 자동 열기까지 쓰려면 setup.sh 를 다시 돌리세요.\n")

    print("── 현재 열려 있는 창 제목 " + "─" * 30)
    if not titles:
        print("  (없음)")
    for t in titles:
        # 앞뒤 공백이 눈에 보이도록 따옴표로 감싼다 (제목 불일치의 흔한 원인)
        print(f"  {t!r}")
    print()

    if not target:
        print("특정 방을 확인하려면:  python -m agent.diagnose \"방 이름\"")
        print("검색 결과 제목을 보려면:  python -m agent.diagnose --search \"검색어\"")
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
