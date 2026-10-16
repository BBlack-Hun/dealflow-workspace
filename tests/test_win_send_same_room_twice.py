"""Windows 발송이 **같은 방으로 연달아** 보내면 한 건 걸러 실패하지 않는가 (0.11.9).

## 실제로 난 일 (시험 서버, 발송기 0.11.8)

시험방 **하나로** 네 건씩 보낸 회차가 `성공 · room_mismatch · 성공 ·
room_mismatch` 로 번갈았다. 7 분 뒤 새 회차의 첫 건도 실패했다 — 바로 앞 회차의
마지막 건이 성공으로 끝났기 때문이다. 실패 문구에 '실제로 열린 방' 이 붙지
않았으니, 그때 앞에 있던 창은 카톡 메인 창(`카카오톡`)이었다.

## 원인

보낸 뒤의 Esc 한 번(`_safe_close`)은 **채팅창만** 닫는다. 메인 창의 검색창은 그
방 이름이 든 채로 **열려 남는다.** 실패한 건의 Esc 는 (앞에 메인 창이 있으니)
**검색창을** 닫는다 — 0.11.5 가 적어 둔 그 비대칭이 그대로 남아 있었다.

0.11.5 는 남은 **글자**만 지웠다. 다른 방이면 지우고 새 이름을 넣는 순간 글자가
바뀌어 카톡이 다시 검색한다. 같은 방이면 지우고 넣은 글자가 **남아 있던 글자와
같아서** 새 결과가 안 서고, Enter 가 열 방이 없다 → room_mismatch.

⚠ 아래 흉내는 그 짐작을 그대로 옮긴 것이다 — "같은 검색어로는 카톡이 다시
  검색하지 않는다" 는 실기에서 확인한 사실이 아니다. 고친 길(보낸 뒤 검색창까지
  닫기)은 실패한 건이 이미 밟던 길이라, 짐작이 틀려도 해가 없다.

## 이 파일이 지키는 것

    ① 같은 방으로 연달아 보내도 **전부** 나간다 — 보낸 뒤 채팅창과 검색창을 둘 다 닫는다
    ② 예전처럼 채팅창만 닫으면 번갈아 실패한다 (흉내가 증상을 재현하는지)
    ③ 그 방 창이 **이미 떠 있어도** 나간다 — 먼저 닫고 새로 연다
    ④ 키가 가는 **앞 창**이 그 방이 아니면 안 보낸다 (같은 제목 창이 뒤에 있어도)
    ⑤ 제목이 어긋나면 여전히 room_mismatch 이고, **앞 창 제목**을 적는다
    ⑥ focus_failed 에 까닭을 적는다

방 이름은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import inspect

import pytest

from agent.sender import kakao_windows as kw
from tests.test_win_discover_rooms import (SELECTORS, FakeKakao, FakePyAutoGui,
                                           FakePyperclip)

MAIN, PID = 100, 7
OTHER_APP = 300
ROOM = "가나다 시험방"
OTHER = "라마바 시험방"


class Chat:
    """`Desktop.window(…)` 이 돌려주는 채팅창."""

    def __init__(self, handle, title=""):
        self.handle, self.title = handle, title

    # 0.11.8 까지의 길(`window(title=…).wait("exists")`) — 고치기 전 코드로 이
    # 파일을 돌려 증상을 재현할 때 쓴다. 못 잡았으면(0개·여러 개) 던진다.
    def wait(self, *_a, **_k):
        if self.handle is None:
            raise RuntimeError("창을 하나로 잡지 못했다")

    def window_text(self):
        return self.title


class FakeDesktop:
    def __init__(self, sender):
        self.sender = sender

    def window(self, handle=None, title=None):
        if handle is None:
            hits = [h for h, (t, _p) in self.sender.windows.items() if t == title]
            handle = hits[0] if len(hits) == 1 else None
        return Chat(handle, title or "")


class SameRoomWin(kw.KakaoDesktopSender):
    """창 목록까지 흉내낸 카톡 — 검색창이 **열린 채 남는** 카톡.

    - Ctrl+F : 메인 창이 앞이고 검색창이 닫혀 있으면 **빈** 검색창을 연다
    - Ctrl+V : 채팅창이 앞이면 입력란에. 검색창이면 뒤에 이어 붙이고, 글자가
               **마지막으로 검색한 글자와 다를 때만** 새 결과를 세운다
    - Enter  : 채팅창이 앞이면 보낸다. 검색창이면 새 결과의 맨 위 방을 연다 —
               결과는 한 번 열면 쓴 것이 된다. 그 방 창이 이미 떠 있으면
               `activate_existing` 에 따라 앞으로 올리거나 아무것도 안 한다
    - Esc    : 채팅창이 앞이면 그 창만 닫는다. 메인 창이 앞이면 검색창을 닫는다
               (검색창도 닫혀 있으면 메인 창이 숨는다)
    """

    def __init__(self, *, rooms=(ROOM, OTHER), opens=None, uia_clear=True,
                 activate_existing=True, input_readable=True):
        self.sel = dict(SELECTORS)
        self.sel["timings"] = {k: 0 for k in SELECTORS.get("timings", {})}
        self.screenshot_dir = ""
        self.ir_root_setting = ""
        self.can_send_files = False
        self._desktop = FakeDesktop(self)
        self._pyperclip = FakePyperclip()
        self._pyautogui = FakePyAutoGui()

        self.kakao = FakeKakao({}, uia_clear=uia_clear)
        self.kakao.handle = MAIN
        self.windows = {MAIN: ("카카오톡", PID)}
        self.fg = MAIN
        self.main_hidden = False
        self.blocker = None                 # 포커스를 쥐고 안 놓는 다른 앱 창
        self.rooms = set(rooms)
        self.opens = dict(opens or {})      # 검색어 → 실제로 열리는 방 제목
        self.activate_existing = activate_existing
        self.input_readable = input_readable
        self.search_open = False
        self.last_query = None
        self.fresh = False
        self.inputs = {}
        self.delivered = []
        self.next_hwnd = 500
        self.opened_at = []                 # 방을 연 Enter 의 키 순번
        hotkey, press = self._pyautogui.hotkey, self._pyautogui.press

        def _hotkey(*keys):
            hotkey(*keys)
            self._on_hotkey(tuple(keys))

        def _press(key):
            press(key)
            self._on_press(key)

        self._pyautogui.hotkey, self._pyautogui.press = _hotkey, _press

    # ── 카톡 흉내 ──────────────────────────────────────────────────────
    def _on_hotkey(self, keys):
        on_main = self.fg == MAIN
        if keys == ("ctrl", "f") and on_main and not self.search_open:
            self.search_open, self.kakao.text = True, ""
            self.last_query, self.fresh = None, False
        elif keys == ("backspace",) and on_main and self.search_open:
            self.kakao.text = ""
        elif keys == ("ctrl", "v"):
            if self.fg in self.inputs:
                self.inputs[self.fg] += self._pyperclip.text
            elif on_main and self.search_open:
                self.kakao.text += self._pyperclip.text
                if self.kakao.text != self.last_query:
                    self.last_query, self.fresh = self.kakao.text, True

    def _on_press(self, key):
        if key == "enter":
            if self.fg in self.inputs:
                self.delivered.append((self.windows[self.fg][0], self.inputs[self.fg]))
                self.inputs[self.fg] = ""
            elif self.fg == MAIN and self.search_open and self.fresh:
                self.fresh = False
                query = self.kakao.text
                title = self.opens.get(query, query if query in self.rooms else None)
                if title:
                    self.opened_at.append(len(self._pyautogui.keys))
                    self._open(title)
        elif key == "esc":
            if self.fg in self.inputs:
                self._post_close(self.fg)
            elif self.fg == MAIN and self.search_open:
                self.search_open, self.kakao.text = False, ""
                self.last_query, self.fresh = None, False
            elif self.fg == MAIN:
                self.main_hidden, self.fg = True, 0

    def _open(self, title):
        same = [h for h, (t, p) in self.windows.items()
                if t == title and p == PID and h != MAIN]
        if same:
            if self.activate_existing:
                self.fg = same[0]
            return
        hwnd, self.next_hwnd = self.next_hwnd, self.next_hwnd + 1
        self.windows[hwnd] = (title, PID)
        self.inputs[hwnd] = ""
        self.fg = hwnd

    def open_beforehand(self, hwnd, title, pid=PID):
        """사람이(또는 앞 건이) 열어 둔 채팅창 — 뒤에 떠 있다."""
        self.windows[hwnd] = (title, pid)
        if pid == PID:
            self.inputs[hwnd] = ""

    def room_windows(self, title=ROOM):
        return [h for h, (t, _p) in self.windows.items() if t == title]

    # ── 발송기가 창을 보는 자리 ────────────────────────────────────────
    def _kakao_window(self):
        return self.kakao

    def _focus_verified(self, win, expect_title=None):
        if self.main_hidden or self.blocker:
            return False
        self.fg = MAIN
        return True

    def _foreground_hwnd(self):
        return self.blocker or self.fg

    def _foreground_title(self):
        return self.windows.get(self._foreground_hwnd(), ("", 0))[0]

    def _hwnd_title(self, hwnd):
        return self.windows.get(hwnd, ("", 0))[0]

    def _hwnd_pid(self, hwnd):
        return self.windows.get(hwnd, ("", 0))[1]

    def _window_pid(self, win):
        return PID

    def _top_windows(self):
        return {h: v for h, v in self.windows.items() if self._is_window_visible(h)}

    def _is_window_visible(self, hwnd):
        return hwnd in self.windows and not (hwnd == MAIN and self.main_hidden)

    def _post_close(self, hwnd):
        self.windows.pop(hwnd, None)
        self.inputs.pop(hwnd, None)
        if self.fg == hwnd:
            self.fg = MAIN

    def _ensure_visible(self, win):
        self.main_hidden = False

    def _input_text(self, chat):
        return self.inputs.get(chat.handle) if self.input_readable else None

    def _screenshot(self, room_name):
        return None


# ── ① 같은 방으로 연달아 보내도 전부 나간다 ────────────────────────────────

@pytest.mark.parametrize("uia_clear", [True, False], ids=["UIA로_비움", "키로_비움"])
def test_같은_방으로_연달아_보내도_전부_나간다(uia_clear):
    sender = SameRoomWin(uia_clear=uia_clear)
    results = [sender.send_text(ROOM, f"{n}번째 안녕하세요") for n in range(1, 5)]
    assert [r.ok for r in results] == [True] * 4, [r.error for r in results]
    assert sender.delivered == [(ROOM, f"{n}번째 안녕하세요") for n in range(1, 5)]


def test_보낸_뒤에는_채팅창도_검색창도_닫혀_있다():
    """다음 건이 실패한 건 뒤와 **같은 자리**(검색창 닫힘)에서 시작한다."""
    sender = SameRoomWin()
    assert sender.send_text(ROOM, "안녕하세요").ok
    assert sender.room_windows() == []
    assert not sender.search_open
    assert not sender.main_hidden


def test_다른_방을_섞어_보내도_전부_나간다():
    sender = SameRoomWin()
    order = [ROOM, ROOM, OTHER, ROOM, OTHER, OTHER]
    results = [sender.send_text(room, "안녕하세요") for room in order]
    assert [r.ok for r in results] == [True] * len(order), [r.error for r in results]
    assert [room for room, _ in sender.delivered] == order


# ── ② 흉내가 증상을 재현하는가 ────────────────────────────────────────────

def test_예전처럼_채팅창만_닫으면_번갈아_실패한다():
    """0.11.8 까지: 보낸 뒤 Esc 한 번 — 채팅창만 닫히고 검색창은 남는다."""
    sender = SameRoomWin()
    sender._leave_room = lambda chat, room_name: sender._safe_close()
    results = [sender.send_text(ROOM, "안녕하세요") for _ in range(4)]
    assert [r.ok for r in results] == [True, False, True, False]
    # 시험 서버에서 본 문구 그대로 — 0.11.9 부터는 앞에 있던 창(메인 창)이 붙는다.
    for r in results[1::2]:
        assert r.error.startswith("room_mismatch: 열린 방 제목이 정확히 일치하지 않음")
        assert "앞 창: '카카오톡'" in r.error


# ── ③ 그 방 창이 이미 떠 있어도 나간다 ────────────────────────────────────

@pytest.mark.parametrize("activate_existing", [True, False],
                         ids=["카톡이_앞으로_올림", "카톡이_안_올림"])
def test_그_방_창이_이미_떠_있어도_나간다(activate_existing):
    sender = SameRoomWin(activate_existing=activate_existing)
    sender.open_beforehand(400, ROOM)
    result = sender.send_text(ROOM, "안녕하세요")
    assert result.ok, result.error
    assert sender.delivered == [(ROOM, "안녕하세요")]
    assert sender.room_windows() == []          # 열어 둔 창도, 새로 연 창도 닫혔다


def test_다른_앱의_같은_제목_창은_닫지_않는다():
    """폴더 창처럼 **다른 앱** 의 창 제목이 방 이름과 같을 수 있다."""
    sender = SameRoomWin()
    sender.open_beforehand(OTHER_APP, ROOM, pid=9)
    assert sender.send_text(ROOM, "안녕하세요").ok
    assert sender.room_windows() == [OTHER_APP]


# ── ④ 키가 가는 앞 창이 그 방이어야 한다 ──────────────────────────────────

def test_뒤에_같은_제목_창이_있어도_앞_창이_다른_방이면_안_보낸다():
    """검색이 다른 방을 열었는데 그 방 창이 뒤에 떠 있었다 — 0.11.8 은 통과시켰고,
    입력란을 못 읽는 PC 에서는 **앞에 열린 다른 방으로** 나갔다."""
    sender = SameRoomWin(opens={ROOM: OTHER}, input_readable=False)
    sender.open_beforehand(400, ROOM)
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok
    assert result.error.startswith("room_mismatch:")
    assert sender.delivered == []


def test_앞_창_대조():
    sender = SameRoomWin()
    sender.open_beforehand(401, ROOM)
    sender.open_beforehand(402, OTHER)
    sender.open_beforehand(403, ROOM, pid=9)
    win = sender.kakao

    sender.fg = 402                                   # 같은 제목 창은 뒤에 있다
    assert sender._opened_chat_window(ROOM, win) is None
    sender.fg = 403                                   # 제목은 같은데 다른 앱
    assert sender._opened_chat_window(ROOM, win) is None
    sender.fg = 401
    assert sender._opened_chat_window(ROOM, win).handle == 401


# ── ⑤ 제목이 어긋나면 여전히 막고, 앞 창 제목을 적는다 ────────────────────

def test_제목이_어긋나면_안_보내고_열린_방_제목을_알려준다():
    actual = ROOM + " 외 1명"
    sender = SameRoomWin(opens={ROOM: actual})
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok
    assert result.error.startswith("room_mismatch:")
    assert actual in result.error
    assert sender.delivered == []
    after_open = sender._pyautogui.keys[sender.opened_at[0]:]
    assert after_open and all(k == "esc" for k in after_open)   # 붙여 넣지 않았다


def test_방이_안_열리면_앞에_있던_창_제목을_적는다():
    sender = SameRoomWin(rooms=())
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok
    assert result.error.startswith("room_mismatch:")
    assert "앞 창: '카카오톡'" in result.error


def test_앞_창_제목은_40자에서_자른다():
    long_title = "가" * 30 + "나" * 30
    sender = SameRoomWin(rooms=())

    def other_app_takes_focus():                   # Enter 뒤에 다른 앱이 앞에 왔다
        sender.windows[OTHER_APP] = (long_title, 9)
        sender.blocker = OTHER_APP

    press = sender._pyautogui.press
    sender._pyautogui.press = lambda key: (press(key), key == "enter"
                                           and other_app_takes_focus())
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok and result.error.startswith("room_mismatch:")
    assert "가" * 30 + "나" * 10 + "…" in result.error
    assert long_title not in result.error


# ── ⑥ focus_failed 에 까닭을 적는다 ───────────────────────────────────────

def test_메인_창이_숨어_있으면_그렇게_적는다():
    sender = SameRoomWin()
    sender.main_hidden = True
    result = sender.send_text(ROOM, "안녕하세요")
    assert result.error.startswith("focus_failed:")
    assert "숨어" in result.error
    assert sender._pyautogui.keys == []                 # 키는 하나도 안 눌렀다


def test_다른_앱이_앞을_쥐고_있으면_그_창_제목을_적는다():
    sender = SameRoomWin()
    sender.windows[OTHER_APP] = ("메모장", 9)
    sender.blocker = OTHER_APP
    result = sender.send_text(ROOM, "안녕하세요")
    assert result.error.startswith("focus_failed:")
    assert "앞 창: '메모장'" in result.error
    assert sender._pyautogui.keys == []


def test_send_file_도_보낸_뒤_같은_자리로_나온다():
    """자료 전달은 파일 → 문구가 **같은 방**으로 간다. 파일 쪽만 검색창을 남기면
    바로 다음 문구가 이 버그를 그대로 밟는다."""
    src = inspect.getsource(kw.KakaoDesktopSender.send_file)
    assert "_leave_room(" in src
    assert "_safe_close()" not in src
