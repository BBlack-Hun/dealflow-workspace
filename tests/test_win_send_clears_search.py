"""Windows 발송이 **한 건 걸러 한 건**만 나가지 않는가 (0.11.5).

## 실제로 난 일

76건 회차가 `실패 · 성공 · 실패 · 성공 …` 으로 번갈았다. 실패는 전부
`room_mismatch: 열린 방 제목이 정확히 일치하지 않음`.

카톡은 검색칸에 **직전 검색어를 남겨 둔다.** 발송(`_open_room_verified`)은
Ctrl+F 뒤에 칸을 비우지 않고 방 이름을 붙였다:

    성공한 건  → Esc 가 **채팅창만** 닫는다. 검색칸에는 그 방 이름이 남는다
    다음 건    → `앞 방 이름` + `이번 방 이름` 으로 검색 → 방이 안 나온다
                → room_mismatch → Esc 가 이번엔 **검색칸을** 비운다
    그다음 건  → 빈 칸에서 시작 → 성공 …

방 검색(`discover_rooms`)은 0.11.3~0.11.4 에서 칸을 비우게 고쳤는데, 발송
쪽은 그 자리를 안 거쳤다.

## 이 파일이 지키는 것

    ① 연달아 보내도 **전부** 나간다 (칸을 UIA 로 비우든 키로 비우든)
    ② 칸을 끝내 못 비우면 **방을 열지 않는다**(Enter 를 안 누른다) — 문구도 안 붙인다
    ③ 검색 중 메인 창이 앞에서 사라지면 붙이지도, Esc 도 누르지 않는다
    ④ 되읽은 글자가 넣은 글자의 앞부분(잘려 보임)이면 그대로 진행한다

방 이름은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from agent.sender import kakao_windows as kw
from tests.test_win_discover_rooms import SELECTORS, FakeKakao, FakePyAutoGui, FakePyperclip

ROOMS = [f"홍길동{n} 심사역님 가나다벤처스 Deal 공유 우리브이씨 Asset" for n in range(1, 7)]


class Chat:
    def __init__(self, title):
        self.title = title


class SendWin(kw.KakaoDesktopSender):
    """카톡을 흉내낸 Windows 발송기 — 검색칸이 **직전 글자를 남기는** 카톡.

    - Ctrl+V : 채팅창이 열려 있으면 입력란에, 아니면 검색칸 **뒤에 이어** 붙는다
    - Enter  : 채팅창이 열려 있으면 보낸다. 아니면 검색칸 글자와 **같은 이름의
               방**이 있을 때만 그 방을 연다
    - Esc    : 채팅창이 열려 있으면 그 창만 닫는다(검색칸은 그대로).
               아니면 검색칸을 비운다
    """

    def __init__(self, kakao, *, focus_ok=True, lose_fg_after=None, stubborn=False):
        self.sel = dict(SELECTORS)
        self.sel["timings"] = {k: 0 for k in SELECTORS.get("timings", {})}
        self.screenshot_dir = ""
        self._desktop = None
        self.ir_root_setting = ""
        self.can_send_files = False
        self.kakao = kakao
        self.focus_ok = focus_ok
        self.lose_fg_after = lose_fg_after   # 이 키 다음부터 메인 창이 앞에 없다
        self.fg_lost = False
        self.stubborn = stubborn             # 키로도 안 지워지는 카톡
        self.rooms = set(ROOMS)
        self.chat = None
        self.chat_input = ""
        self.delivered = []
        self._pyperclip = FakePyperclip()
        self._pyautogui = FakePyAutoGui()
        hotkey, press = self._pyautogui.hotkey, self._pyautogui.press

        def _hotkey(*keys):
            hotkey(*keys)
            self._after(tuple(keys))
            if keys == ("backspace",) and not self.stubborn:
                self.kakao.text = ""      # End → Shift+Home → Backspace 의 끝
            if keys == ("ctrl", "v"):
                if self.chat is not None:
                    self.chat_input += self._pyperclip.text
                else:
                    self.kakao.text += self._pyperclip.text

        def _press(key):
            press(key)
            self._after(key)
            if key == "enter":
                if self.chat is not None:
                    self.delivered.append((self.chat.title, self.chat_input))
                    self.chat_input = ""
                elif self.kakao.text in self.rooms:
                    self.chat = Chat(self.kakao.text)
            elif key == "esc":
                if self.chat is not None:
                    self.chat = None
                else:
                    self.kakao.text = ""

        self._pyautogui.hotkey, self._pyautogui.press = _hotkey, _press

    def _after(self, key):
        if self.lose_fg_after is not None and key == self.lose_fg_after:
            self.fg_lost = True

    def _kakao_window(self):
        return self.kakao

    def _focus_verified(self, win, expect_title=None):
        return self.focus_ok and not self.fg_lost

    def _foreground_hwnd(self):
        return 0

    def _foreground_title(self):
        return "메모장" if self.fg_lost else "카카오톡"

    def _opened_chat_window(self, room_name):
        return self.chat if self.chat is not None and self.chat.title == room_name else None

    def _input_text(self, chat):
        return None

    def _screenshot(self, room_name):
        return None


# ── ① 연달아 보내도 전부 나간다 ────────────────────────────────────────────

@pytest.mark.parametrize("uia_clear", [True, False], ids=["UIA로_비움", "키로_비움"])
def test_연달아_보내도_한_건도_안_빠진다(uia_clear):
    kakao = FakeKakao({}, uia_clear=uia_clear)
    kakao.text = "직전 방 확인 때 넣은 검색어"     # 회차 첫 건부터 남아 있었다
    sender = SendWin(kakao)
    results = [sender.send_text(room, f"{room} 안녕하세요") for room in ROOMS]
    assert [r.ok for r in results] == [True] * len(ROOMS), [r.error for r in results]
    assert [room for room, _ in sender.delivered] == ROOMS


def test_예전처럼_안_비우면_번갈아_실패한다():
    """이 흉내가 실제 증상을 재현하는지 — 비우기를 빼면 성공·실패가 번갈아야 한다."""
    kakao = FakeKakao({})
    sender = SendWin(kakao)

    def old_way(win, room):                       # 0.11.4 까지: 비우지 않고 붙였다
        sender._pyperclip.copy(room)
        sender._pyautogui.hotkey("ctrl", "v")
        return None

    sender._put_room_query = old_way
    oks = [sender.send_text(room, "안녕하세요").ok for room in ROOMS]
    assert oks == [True, False, True, False, True, False]


# ── ② 못 비우면 방을 열지 않는다 ───────────────────────────────────────────

def test_칸을_못_비우면_방을_열지_않고_문구도_안_붙인다():
    kakao = FakeKakao({}, uia_clear=False)
    kakao.text = ROOMS[0]
    sender = SendWin(kakao, stubborn=True)
    result = sender.send_text(ROOMS[1], "안녕하세요")
    assert not result.ok
    assert result.error.startswith("search_not_cleared")
    assert "enter" not in sender._pyautogui.keys
    assert sender.delivered == []
    assert sender._pyautogui.keys.count("esc") == 1     # 검색창만 닫는다


# ── ③ 메인 창이 사라지면 아무것도 안 누른다 ────────────────────────────────

def test_검색_중_메인_창이_사라지면_붙이지도_Esc도_안_누른다():
    kakao = FakeKakao({}, uia_clear=False)
    kakao.text = ROOMS[0]
    sender = SendWin(kakao, lose_fg_after=("backspace",))
    result = sender.send_text(ROOMS[1], "안녕하세요")
    assert not result.ok
    assert result.error.startswith("focus_failed")
    keys = sender._pyautogui.keys
    assert ("ctrl", "v") not in keys
    assert "enter" not in keys
    assert "esc" not in keys


# ── ④ 되읽기 판단 ─────────────────────────────────────────────────────────

def test_되읽기_판단():
    room = ROOMS[0]
    assert kw.query_was_typed(None, room)                  # 못 읽음 — 판단 안 함
    assert kw.query_was_typed(room, room)
    assert kw.query_was_typed(room[:12], room)             # 잘려 보임
    assert kw.query_was_typed("  " + room.replace(" ", "  "), room)
    assert not kw.query_was_typed(ROOMS[1] + room, room)   # 직전 검색어가 앞에 남음
    assert not kw.query_was_typed(room + "x", room)
    assert not kw.query_was_typed("", room)


def test_send_file_도_같은_자리를_거친다():
    """파일 첨부도 `_open_room_verified` 로 방을 연다 — 비우기가 한쪽만 걸리면 안 된다."""
    import inspect

    src = inspect.getsource(kw.KakaoDesktopSender._open_room_verified)
    assert "_put_room_query" in src
    assert 'hotkey("ctrl", "v")' not in src
