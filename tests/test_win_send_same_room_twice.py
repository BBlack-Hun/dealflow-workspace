"""Windows 발송이 **같은 방으로 연달아** 보내면 한 건 걸러 실패하지 않는가 (0.11.9 → 0.11.11).

## 실제로 난 일

**0.11.8 (시험 서버)** — 시험방 하나로 네 건씩 보낸 회차가 `성공 · room_mismatch · 성공 ·
room_mismatch` 로 번갈았다. 0.11.9 는 '보낸 뒤 Esc 한 번이 채팅창만 닫아 검색창이 열린
채 남는다' 고 보고 보낸 뒤 검색창까지 닫게 고쳤다(`_leave_room`).

**0.11.9 (실기, 10/17)** — 그래도 번갈았다. 같은 '나와의 채팅' 시험방으로 한 건짜리 잡
다섯을 5초 간격으로 보냈더니 `성공 · 실패 · 성공 · 실패 · 성공`. 실패는 모두
`room_mismatch (전송 안 함, 앞 창: '카카오톡')` — 그때 앞 창은 메인 창이고 열린 채팅창이
**하나도 없었다.** Enter 가 아무 방도 안 열었다. 실패한 건 바로 뒤의 건은 나갔다.

## 짐작 — 흉내(`SameRoomWin`)가 이대로 움직인다

  · 방을 열면 카톡이 검색창을 **스스로 닫는다** — 칸의 글자와 '마지막으로 찾은 글자'
    는 남는다. 그래서 0.11.9 가 보낸 뒤 누른 Esc 는 닫힌 검색창에 떨어져 아무것도 안
    지웠다(메인 창이 숨으면 `_ensure_visible` 이 다시 띄웠다).
  · 같은 글자를 다시 넣으면 카톡은 **새로 찾지 않는다** — 결과가 안 서고 Enter 가 열 방이
    없다. 칸을 비우는 것만으로는 '마지막으로 찾은 글자' 가 안 바뀐다(0.11.5 의 비우기가
    같은 방에서 안 먹은 까닭).
  · **열린 검색창에** 누른 Esc 는 검색 상태를 지운다 — 실패한 건의 Esc 가 그것이었고,
    그래서 그 뒤의 건이 나갔다.

⚠ 위는 실기 기록을 설명하는 짐작이다. 0.11.10 이 고친 길(Enter 로 아무 방도 안 열리면
  **열린 검색창을 Esc 로 닫고 한 번 더 찾는다**)은 실기에서 이미 통한 차례 — 실패한 건의
  Esc → 다음 건의 검색 — 를 한 건 안에서 되풀이하는 것이라 짐작이 틀려도 해가 없다.
  0.11.9 코드를 이 흉내로 돌리면 실기와 똑같이 `[성공, 실패, 성공, 실패, 성공]` 이고 실패
  문구도 같다(고치기 전에 확인했다 — 아래 ② 는 다시 찾기를 끄고 같은 것을 본다).

## 이 파일이 지키는 것

    ① 같은 방으로 연달아 보내도 **전부** 나간다 — Enter 로 안 열리면 한 번 더 찾는다
    ② 다시 찾기가 없으면 실기처럼 번갈아 실패한다 (흉내가 증상을 재현하는지)
    ③ 그 방 창이 **이미 떠 있어도** 나간다 — 먼저 닫고 새로 연다
    ④ 키가 가는 **앞 창**이 그 방이 아니면 안 보낸다 (같은 제목 창이 뒤에 있어도)
    ⑤ 제목이 어긋나면 여전히 room_mismatch 이고, **앞 창 제목** · 검색 결과를 적는다.
       앞 창이 카톡 창이 아니면 Esc 를 누르지 않는다
    ⑥ focus_failed 에 까닭을 적는다
    ⑦ 앞 건이 **어떻게 끝났든**(실패 · 예외) 다음 건은 같은 자리에서 시작한다
    ⑧ 메인 창을 숨기지 않는다 — 닫힌 검색창에 Esc 를 누르지 않고, 누른 뒤에는 기다렸다 본다
    ⑨ 결과 목록이 읽히면 그 방이 선 뒤에 Enter 를 누른다
    ⑩ (0.11.11) **다른 방**이 열리면 그 창만 닫고 한 번만 더 찾는다. 실패 문구는 같은 방의
       다른 이름일 때만 '방 이름을 고치라' 고 하고, 다른 방이면 '그대로 두고 재시도' 다.
       Enter 전 대기는 1.5초다
    ⑪ (0.11.12) 다시 찾을 때는 **다른 글자**로 찾는다(`retry_query`). 첫 시도에 막혔다가
       나간 건은 실패가 아니라 경고(`SendResult.warning`)를 싣는다

방 이름은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import inspect
import logging
import time
from types import SimpleNamespace

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


class FieldKakao(FakeKakao):
    """메인 창의 UIA — 검색칸(글자는 닫혀도 남는다)과, 읽히면 결과 목록."""

    def __init__(self, win, **kw_):
        super().__init__({}, **kw_)
        self.win = win

    def _uia_set(self, text):
        super()._uia_set(text)
        self.win._typed()

    def _titles(self):
        return self.win._shown()


class SameRoomWin(kw.KakaoDesktopSender):
    """창 목록까지 흉내낸 카톡 — **실기에서 본 대로** 움직인다(머리말의 짐작).

    - Ctrl+F : 메인 창이 앞이고 검색창이 닫혀 있으면 연다 — 칸의 글자는 **남긴 채**
    - 칸의 글자가 바뀌면(붙여넣기 · Backspace · UIA) — 비면 결과가 빈다. 비지 않았고
               **마지막으로 찾은 글자와 다를 때만** 새로 찾는다
    - Enter  : 채팅창이 앞이면 보낸다. 검색창이면 **새로 선** 결과의 맨 위 방을 열고
               검색창을 **스스로 닫는다**(글자 · 마지막으로 찾은 글자는 남긴다). 새 결과가
               없으면 아무것도 안 연다. 그 방 창이 이미 떠 있으면 `activate_existing` 에
               따라 앞으로 올리거나 아무것도 안 한다
    - Esc    : 채팅창이 앞이면 그 창만 닫는다. 메인 창이 앞이고 검색창이 **열려 있으면**
               닫고 검색 상태를 지운다. 닫혀 있으면 메인 창이 숨는다(`hide_late` 면
               다음 대기 뒤에 — 숨기기는 한 박자 늦게 일어난다)

    `wrong_opens` 가 있으면 검색창에서 누른 Enter 가 그 방을 **차례로 하나씩** 연다 — 결과가
    서기 전에 Enter 가 눌려 대화 목록 맨 위의 다른 방이 열리는 것(0.11.10 실기 뒤의 짐작).

    결과 목록은 `list_readable` 일 때만 UIA 로 읽힌다(실기 PC 는 못 읽었다 — 0.11.1).
    새로 찾은 뒤 `lag_reads` 번째 읽기까지는 `stale` 줄이 보인다 — 결과가 한 박자 늦게
    선다(`_search_titles` 머리말 — 직전 검색의 결과가 잡혔다).
    """

    def __init__(self, *, rooms=(ROOM, OTHER), opens=None, uia_clear=True,
                 activate_existing=True, input_readable=True, list_readable=False,
                 lag_reads=0, stale=(), hide_late=False, wrong_opens=(), esc_forgets=True):
        self.sel = dict(SELECTORS)
        self.sel["timings"] = {k: 0 for k in SELECTORS.get("timings", {})}
        self.screenshot_dir = ""
        self.ir_root_setting = ""
        self.can_send_files = False
        self._desktop = FakeDesktop(self)
        self._pyperclip = FakePyperclip()
        self._pyautogui = FakePyAutoGui()

        self.kakao = FieldKakao(self, uia_clear=uia_clear, no_list=not list_readable)
        self.kakao.handle = MAIN
        self.windows = {MAIN: ("카카오톡", PID)}
        self.fg = MAIN
        self.main_hidden = False
        self.hide_late = hide_late
        self.pending_hide = False
        self.hides = 0
        self.stray_keys = []                # 아무 창도 앞에 없을 때 눌린 키
        self.blocker = None                 # 포커스를 쥐고 안 놓는 다른 앱 창
        self.rooms = set(rooms)
        self.opens = dict(opens or {})      # 검색어 → 실제로 열리는 방 제목
        self.activate_existing = activate_existing
        self.input_readable = input_readable
        self.search_open = False
        self.last_query = None
        self.results, self.fresh = [], False
        self.lag_reads, self.lag_left, self.stale = lag_reads, 0, list(stale)
        self.inputs = {}
        self.delivered = []
        self.next_hwnd = 500
        self.opened_at = []                 # 방을 연 Enter 의 키 순번
        self.wrong_opens = list(wrong_opens)
        self.enter_queries = []             # 검색창에서 Enter 를 누른 때의 검색칸 글자
        self.pasted_into = []               # 채팅 입력란에 붙여 넣은 방 제목
        self.resets = 0                     # 열린 검색창을 Esc 로 닫은 수
        self.esc_forgets = esc_forgets      # 거짓이면 Esc 뒤에도 '마지막으로 찾은 글자' 가 남는다
        hotkey, press = self._pyautogui.hotkey, self._pyautogui.press

        def _hotkey(*keys):
            hotkey(*keys)
            self._on_hotkey(tuple(keys))

        def _press(key):
            press(key)
            self._on_press(key)

        self._pyautogui.hotkey, self._pyautogui.press = _hotkey, _press

    # ── 카톡 흉내 ──────────────────────────────────────────────────────
    def _typed(self):
        """칸의 글자가 바뀌었다 — 비면 결과가 비고, 마지막으로 찾은 글자와 다르면 찾는다."""
        text = self.kakao.text
        if not text:
            self.results, self.fresh = [], False
        elif text != self.last_query:
            self.last_query = text
            # 그 글자로 **시작하는** 방을 찾는다 — 다시 찾을 때 줄인 글자(`retry_query`,
            # 0.11.12)로도 같은 방이 선다. `opens` 도 같은 규칙(그 방 이름의 앞부분이면 그 창)
            title = next((v for k, v in self.opens.items() if k.startswith(text)),
                         next((r for r in sorted(self.rooms) if r.startswith(text)), None))
            self.results = [title] if title else []
            self.fresh, self.lag_left = bool(title), self.lag_reads

    def _shown(self):
        if not self.search_open:
            return []
        if self.lag_left > 0:
            self.lag_left -= 1
            return list(self.stale)
        return list(self.results)

    def _on_hotkey(self, keys):
        on_main = self.fg == MAIN
        if not self.fg:
            self.stray_keys.append(keys)
        if keys == ("ctrl", "f") and on_main and not self.search_open:
            self.search_open = True                      # 글자는 남긴 채
        elif keys == ("backspace",) and on_main and self.search_open:
            self.kakao.text = ""
            self._typed()
        elif keys == ("ctrl", "v"):
            if self.fg in self.inputs:
                self.inputs[self.fg] += self._pyperclip.text
                self.pasted_into.append(self.windows[self.fg][0])
            elif on_main and self.search_open:
                self.kakao.text += self._pyperclip.text
                self._typed()

    def _on_press(self, key):
        if not self.fg:
            self.stray_keys.append(key)
        if key == "enter":
            if self.fg in self.inputs:
                self.delivered.append((self.windows[self.fg][0], self.inputs[self.fg]))
                self.inputs[self.fg] = ""
            elif self.fg == MAIN and self.search_open and (
                    self.wrong_opens or (self.fresh and self.results)):
                self.enter_queries.append(self.kakao.text)
                title = self.wrong_opens.pop(0) if self.wrong_opens else self.results[0]
                self.fresh = False
                self.opened_at.append(len(self._pyautogui.keys))
                self._open(title)
                self.search_open = False                 # 카톡이 검색창을 스스로 닫는다
        elif key == "esc":
            if self.fg in self.inputs:
                self._post_close(self.fg)
            elif self.fg == MAIN and self.search_open:
                self.search_open, self.kakao.text = False, ""
                self.results, self.fresh = [], False
                if self.esc_forgets:
                    self.last_query = None
                self.resets += 1
            elif self.fg == MAIN:
                self.hides += 1
                if self.hide_late:
                    self.pending_hide = True
                else:
                    self.main_hidden, self.fg = True, 0

    def tick(self, _seconds=0):
        """시간이 조금 흘렀다 — 늦게 오는 숨기기가 이때 일어난다(`hide_late`)."""
        if self.pending_hide:
            self.pending_hide = False
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
        # 진짜와 같다 — **지금** 숨어 있을 때만 다시 띄운다(늦게 올 숨기기는 못 본다).
        self.main_hidden = False

    def _input_text(self, chat):
        return self.inputs.get(chat.handle) if self.input_readable else None

    def _screenshot(self, room_name):
        return None


def _late_clock(monkeypatch, sender):
    """발송기의 `time.sleep` 이 흉내의 시계를 돌린다 — 늦게 오는 숨기기를 재현한다."""
    monkeypatch.setattr(kw, "time", SimpleNamespace(sleep=sender.tick,
                                                    monotonic=time.monotonic))


# ── ① 같은 방으로 연달아 보내도 전부 나간다 ────────────────────────────────

@pytest.mark.parametrize("uia_clear", [True, False], ids=["UIA로_비움", "키로_비움"])
def test_같은_방으로_연달아_보내도_전부_나간다(uia_clear):
    """실기와 같은 차례 — 같은 방 한 건짜리 다섯."""
    sender = SameRoomWin(uia_clear=uia_clear)
    results = [sender.send_text(ROOM, f"{n}번째 안녕하세요") for n in range(1, 6)]
    assert [r.ok for r in results] == [True] * 5, [r.error for r in results]
    assert sender.delivered == [(ROOM, f"{n}번째 안녕하세요") for n in range(1, 6)]
    assert sender.stray_keys == []


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


def test_다시_찾기는_열린_검색창을_닫고_처음부터_찾는다(caplog):
    """두 번째 건 — Enter 로 아무 방도 안 열리자 Esc 로 **열린** 검색창을 닫고(검색 상태가
    지워진다) Ctrl+F 부터 다시. 방은 한 번만 열리고, 채팅 입력란에는 한 통만 들어간다."""
    sender = SameRoomWin()
    assert sender.send_text(ROOM, "첫 건").ok
    sender._pyautogui.keys.clear()
    with caplog.at_level(logging.WARNING, logger="agent.kakao"):
        assert sender.send_text(ROOM, "둘째 건").ok
    keys = sender._pyautogui.keys
    assert keys.count(("ctrl", "f")) == 2
    assert keys.count("enter") == 3                 # 안 열린 Enter · 연 Enter · 보내기
    assert sender.resets == 1
    assert "한 번 더 찾습니다" in caplog.text
    assert sender.delivered[-1] == (ROOM, "둘째 건")


# ── ② 흉내가 증상을 재현하는가 ────────────────────────────────────────────

def test_다시_찾기가_없으면_실기처럼_번갈아_실패한다(monkeypatch):
    """0.11.9 의 실기 기록 — 같은 방 다섯 건이 성공 · 실패 · 성공 · 실패 · 성공, 실패는
    `room_mismatch … 앞 창: '카카오톡'`. 다시 찾기(`OPEN_ROOM_TRIES`)를 끄면 흉내도 그렇다."""
    monkeypatch.setattr(kw, "OPEN_ROOM_TRIES", 1)
    sender = SameRoomWin()
    results = [sender.send_text(ROOM, "안녕하세요") for _ in range(5)]
    assert [r.ok for r in results] == [True, False, True, False, True]
    for r in results[1::2]:
        assert r.error.startswith("room_mismatch: 열린 방 제목이 정확히 일치하지 않음")
        assert "앞 창: '카카오톡'" in r.error
    assert sender.room_windows() == []                          # 열린 채팅창이 없다


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
    입력란을 못 읽는 PC 에서는 **앞에 열린 다른 방으로** 나갔다. (0.11.11) 다른 방이면
    그 창만 닫고 **한 번만** 더 찾는다 — 또 다른 방이면 멈춘다. 어느 창에도 안 붙였다."""
    sender = SameRoomWin(opens={ROOM: OTHER}, input_readable=False)
    sender.open_beforehand(400, ROOM)
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok
    assert result.error.startswith("room_mismatch:")
    assert sender.delivered == [] and sender.pasted_into == []
    assert len(sender.opened_at) == 2                           # 한 번만 더 찾았다
    assert sender.room_windows(OTHER) == []                     # 연 다른 방은 닫았다
    assert sender.stray_keys == [] and sender.hides == 0


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
    """방 이름이 든 다른 제목(같은 방의 다른 이름)이 열렸다 — 그 제목으로 고치라고 안내한다."""
    actual = ROOM + " 외 1명"
    sender = SameRoomWin(opens={ROOM: actual})
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok
    assert result.error.startswith("room_mismatch:")
    assert f"실제로 열린 방: {actual!r}" in result.error
    assert "똑같이 고치면 나갑니다" in result.error
    assert "그대로 두고" not in result.error
    assert sender.delivered == [] and sender.pasted_into == []  # 붙여 넣지 않았다
    after_open = sender._pyautogui.keys[sender.opened_at[-1]:]
    assert after_open and all(k == "esc" for k in after_open)   # 연 뒤로는 Esc 뿐
    assert sender.room_windows(actual) == []                    # 그 창만 닫았다


def test_방이_안_열리면_앞에_있던_창_제목과_검색_결과를_적는다():
    """다시 찾아도 안 열린다(그런 방이 없다) — 앞 창(메인 창)과 결과 목록을 적는다."""
    sender = SameRoomWin(rooms=())
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok
    assert result.error.startswith("room_mismatch:")
    assert "앞 창: '카카오톡'" in result.error
    assert "검색 결과: 목록 못 읽음" in result.error
    assert "다시 찾아도" in result.error
    assert sender._pyautogui.keys.count(("ctrl", "f")) == 2       # 한 번만 더 찾았다
    assert not sender.search_open and not sender.main_hidden      # 검색창은 닫고 나왔다


def test_앞_창_제목은_40자에서_자르고_다른_앱에는_Esc_를_누르지_않는다():
    """Enter 뒤에 다른 앱이 앞을 가로챘다 — 그 앱 제목을 40자로 적고, **아무 키도 더
    누르지 않는다**. 0.11.9 는 앞에 무엇이 있든 Esc 를 눌러 그 앱으로 보냈다."""
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
    keys = sender._pyautogui.keys
    assert keys[-1] == "enter" and "esc" not in keys[keys.index("enter"):]


def test_결과_목록이_읽히고_그_방이_끝내_없으면_한_번_더_찾고_제목_대조가_막는다(caplog):
    """목록에 선 줄이 그 방 이름과 다르다 — 한 번 더 찾아도 그대로면 Enter 는 누르되
    (목록을 읽는 자리는 추측이다) 앞 창 제목 대조가 막는다. 무엇이 보였는지 남긴다."""
    actual = ROOM + " 외 1명"
    sender = SameRoomWin(opens={ROOM: actual}, list_readable=True)
    with caplog.at_level(logging.INFO, logger="agent.kakao"):
        result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok and result.error.startswith("room_mismatch:")
    assert sender.delivered == []
    assert sender._pyautogui.keys.count(("ctrl", "f")) == 2
    assert len(sender.opened_at) == 1
    assert "검색 결과: 1줄" in result.error
    assert f"맨 위 {actual!r}" in caplog.text


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
    """자료 전달은 파일 → 문구가 **같은 방**으로 간다. 파일 쪽만 다른 길로 나오면
    바로 다음 문구가 이 버그를 그대로 밟는다."""
    src = inspect.getsource(kw.KakaoDesktopSender.send_file)
    assert "_leave_room(" in src
    assert "_safe_close()" not in src


# ── ⑦ 앞 건이 어떻게 끝났든 같은 자리에서 시작한다 ────────────────────────

def test_예외로_끝나_검색창이_열린_채_남아도_다음_건은_닫고_시작한다():
    """검색칸에 붙인 뒤 터졌다 — 검색창이 그 방 이름을 든 채 열려 남는다. 다음 건은
    **시작할 때** 그 검색창을 닫고 시작해 첫 Enter 로 연다(다시 찾기까지 안 간다)."""
    sender = SameRoomWin()
    real = sender._search_input_text

    def boom(*_a):
        sender._search_input_text = real
        raise RuntimeError("UIA 가 거절했다")

    sender._search_input_text = boom
    first = sender.send_text(ROOM, "첫 건")
    assert not first.ok and first.error.startswith("exception:")
    assert sender.search_open                                   # 열린 채 남았다

    sender._pyautogui.keys.clear()
    second = sender.send_text(ROOM, "둘째 건")
    assert second.ok, second.error
    keys = sender._pyautogui.keys
    assert keys[0] == "esc" and keys.count(("ctrl", "f")) == 1   # 닫고 한 번에 열었다
    assert sender.delivered == [(ROOM, "둘째 건")]
    assert sender.hides == 0


def test_파일_보내기가_한_파일에서_실패해도_다음_문구가_같은_방으로_나간다(tmp_path):
    """파일의 관문에서 막히면 그 채팅창을 연 채 돌아온다(`_send_one_file` 의 실패 출구).
    다음 건(같은 방 문구)은 그 창을 닫고 새로 열어 나간다."""
    docs = tmp_path / "자료"
    docs.mkdir()
    (docs / "IR.pdf").write_bytes(b"pretend pdf")
    sender = SameRoomWin()
    sender.can_send_files, sender.ir_root_setting = True, str(docs)
    sender._send_one_file = lambda room, chat, path: kw.SendResult(
        ok=False, error="gate_blocked: 시험 — 취소했습니다 (전송 안 함)")

    failed = sender.send_file(ROOM, ["IR.pdf"])
    assert not failed.ok and failed.error.startswith("gate_blocked")
    assert len(sender.room_windows()) == 1                      # 창이 남았다

    result = sender.send_text(ROOM, "자료 보내드렸습니다")
    assert result.ok, result.error
    assert sender.delivered == [(ROOM, "자료 보내드렸습니다")]
    assert sender.room_windows() == []


# ── ⑧ 메인 창을 숨기지 않는다 ──────────────────────────────────────────────

def test_보낸_뒤_닫힌_검색창에_Esc_를_누르지_않는다(monkeypatch):
    """카톡은 방을 열며 검색창을 스스로 닫는다 — 보낸 뒤 메인 창에 누르는 Esc 는 닫힌
    검색창에 떨어져 메인 창을 숨긴다. 숨기기는 한 박자 늦게 일어나 곧바로 보면 아직
    보이고(`_ensure_visible` 이 못 본다), 다음 건이 focus_failed 로 떨어진다."""
    sender = SameRoomWin(hide_late=True)
    _late_clock(monkeypatch, sender)
    results = [sender.send_text(room, "안녕하세요") for room in (ROOM, ROOM, OTHER, ROOM)]
    assert [r.ok for r in results] == [True] * 4, [r.error for r in results]
    assert sender.hides == 0
    assert sender.stray_keys == []


def test_검색창이_닫혔는데_열렸다고_알고_Esc_를_눌러도_기다렸다_다시_띄운다(monkeypatch):
    """발송기가 열어 둔 줄 아는 검색창을 사람이 그사이 닫았다 — 시작할 때 누른 Esc 가
    메인 창을 (늦게) 숨긴다. 기다렸다가 숨었는지 보고 다시 띄우고, 포커스를 다시 잡은
    뒤에만 Ctrl+F 를 누른다. 숨은 창에는 키가 하나도 안 간다."""
    sender = SameRoomWin(hide_late=True)
    _late_clock(monkeypatch, sender)
    sender._search_open = True                       # 발송기의 기억 — 실제로는 닫혀 있다
    result = sender.send_text(ROOM, "안녕하세요")
    assert result.ok, result.error
    assert sender.hides == 1 and not sender.main_hidden
    assert sender.stray_keys == []
    assert sender.delivered == [(ROOM, "안녕하세요")]


# ── ⑨ 결과 목록이 읽히면 그 방이 선 뒤에 Enter ─────────────────────────────

def test_목록을_기다리는_사이_다른_창이_앞을_가로채면_Enter_를_누르지_않는다():
    """결과 목록을 읽는 사이 다른 앱이 앞에 왔다 — Enter 는 그 앱으로 간다. 누르지 않고
    focus_failed 로 끝낸다."""
    sender = SameRoomWin(list_readable=True)
    real = sender._room_in_results

    def read_then_lose(win, room):
        found = real(win, room)
        sender.windows[OTHER_APP] = ("메모장", 9)
        sender.blocker = OTHER_APP
        return found

    sender._room_in_results = read_then_lose
    result = sender.send_text(ROOM, "안녕하세요")
    assert result.error.startswith("focus_failed:")
    assert "enter" not in sender._pyautogui.keys
    assert sender.delivered == []


def test_목록이_늦게_서면_그_방이_보일_때까지_기다렸다_연다(caplog):
    """직전에 찾은 방의 줄이 잠깐 보인다 — 그 방 줄이 설 때까지(`room_search_wait`)
    기다렸다가 Enter. 다시 찾지 않는다."""
    sender = SameRoomWin(list_readable=True, lag_reads=6, stale=[OTHER])
    sender.sel["timings"]["room_search_wait"] = 5
    with caplog.at_level(logging.INFO, logger="agent.kakao"):
        result = sender.send_text(ROOM, "안녕하세요")
    assert result.ok, result.error
    assert sender._pyautogui.keys.count(("ctrl", "f")) == 1      # 다시 찾지 않았다
    assert sender.resets == 0
    assert "방 열기 전 검색 결과: 1줄" in caplog.text
    assert f"맨 위 {ROOM!r}" in caplog.text


def test_목록이_읽히면_같은_방_다섯_건도_다시_찾아_전부_나간다():
    sender = SameRoomWin(list_readable=True)
    results = [sender.send_text(ROOM, f"{n}번째") for n in range(1, 6)]
    assert [r.ok for r in results] == [True] * 5, [r.error for r in results]


# ── ⑩ 다른 방이 열리면 그 창만 닫고 한 번 더 찾는다 (0.11.11) ──────────────

@pytest.mark.parametrize("uia_clear,list_readable",
                         [(True, False), (False, False), (True, True)],
                         ids=["UIA로_비움", "키로_비움", "목록_읽힘"])
def test_다른_방이_열리면_그_창만_닫고_한_번_더_찾아_보낸다(caplog, uia_clear, list_readable):
    """Enter 가 다른 방을 열었다(결과가 서기 전에 눌린 것으로 본다). 입력란에는 아직 아무것도
    안 넣었다 — 그 창만 닫고, 검색 상태를 지우고(열린 검색창에 Esc) 칸을 비워 다시 넣고
    찾아 그 방으로 보낸다. 다른 방에는 한 글자도 안 들어간다."""
    sender = SameRoomWin(wrong_opens=[OTHER], input_readable=False,
                         uia_clear=uia_clear, list_readable=list_readable)
    with caplog.at_level(logging.WARNING, logger="agent.kakao"):
        result = sender.send_text(ROOM, "안녕하세요")
    assert result.ok, result.error
    assert sender.delivered == [(ROOM, "안녕하세요")]
    assert sender.pasted_into == [ROOM]                         # 다른 방에는 안 붙였다
    # 칸에는 늘 검색어 하나만 — 다시 찾을 때는 다른 글자(0.11.12 `retry_query`)
    assert sender.enter_queries == [ROOM, kw.retry_query(ROOM)]
    assert len(sender.opened_at) == 2
    assert sender.resets == 1                                   # 검색 상태를 지웠다
    assert sender.room_windows(OTHER) == [] and sender.room_windows() == []
    assert sender.stray_keys == [] and sender.hides == 0
    assert f"다른 방이 열렸습니다({OTHER!r})" in caplog.text


def test_다시_찾아도_다른_방이면_멈추고_그대로_두고_재시도하라고_적는다():
    """두 번 다 다른 방 — 한 번만 더 찾고 멈춘다. 그 제목으로 방 이름을 고치면 다음 발송이
    엉뚱한 사람에게 가므로, '고치라' 가 아니라 '그대로 두고 [실패 재시도]' 라고 적는다."""
    sender = SameRoomWin(wrong_opens=[OTHER, OTHER])
    result = sender.send_text(ROOM, "안녕하세요")
    assert not result.ok and result.error.startswith("room_mismatch:")
    assert f"다른 방이 열렸습니다: {OTHER!r}" in result.error
    assert "방 이름은 그대로 두고 [실패 재시도]를 누르세요" in result.error
    assert "고치면" not in result.error
    assert sender.delivered == [] and sender.pasted_into == []
    assert len(sender.opened_at) == 2
    assert sender.room_windows(OTHER) == []


def test_다른_방을_닫은_뒤_포커스를_못_잡으면_키를_더_누르지_않는다():
    sender = SameRoomWin(wrong_opens=[OTHER])
    real = sender._close_wrong_room

    def close_then_lose(win):
        real(win)
        sender.windows[OTHER_APP] = ("메모장", 9)
        sender.blocker = OTHER_APP

    sender._close_wrong_room = close_then_lose
    result = sender.send_text(ROOM, "안녕하세요")
    assert result.error.startswith("focus_failed:")
    assert "앞 창: '메모장'" in result.error
    assert sender._pyautogui.keys.count(("ctrl", "f")) == 1    # 다시 찾지 않았다
    assert sender.delivered == [] and sender.pasted_into == []


def test_검색어를_넣고_Enter_전에_1_5초_기다린다(monkeypatch):
    """목록을 못 읽는 PC 는 붙여 넣은 뒤 이만큼만 기다리고 Enter 를 누른다 — 짧으면 결과가
    서기 전에 눌려 대화 목록 맨 위 방이 열린다(짐작). 목록이 읽히면 그 방 줄이 보이는 대로
    넘어간다(목록을 더 기다리지 않는다)."""
    assert SELECTORS["timings"]["after_query_paste"] == 1.5
    for list_readable in (False, True):
        sender = SameRoomWin(list_readable=list_readable)
        sender.sel["timings"] = {"after_query_paste": 1.5}
        slept = []
        monkeypatch.setattr(kw, "time", SimpleNamespace(
            sleep=lambda s: slept.append(s), monotonic=time.monotonic))
        assert sender.send_text(ROOM, "안녕하세요").ok
        assert slept.count(1.5) == 1
        assert 0.15 not in slept                                # 목록을 다시 읽지 않았다
    sender.sel["timings"] = {}                                  # 설정에 없어도 1.5
    slept.clear()
    sender._put_query(sender.kakao, OTHER, sender.room_search_conf)
    assert 1.5 in slept


# ── ⑪ (0.11.12) 다시 찾을 때는 다른 글자 · 첫 시도에 막힌 것은 경고로 ────────

def test_다시_찾을_글자는_끝의_기호를_떼고_뗄_것이_없으면_한_글자를_뗀다():
    assert kw.retry_query("가나다 시험방 🙂") == "가나다 시험방"
    assert kw.retry_query("가나다 시험방!!") == "가나다 시험방"
    assert kw.retry_query(" 가나다_ ") == "가나다"
    assert kw.retry_query(ROOM) == "가나다 시험"
    assert kw.retry_query("가나") == "가나"                      # 너무 짧아지면 그대로


def test_Esc_뒤에도_같은_글자로는_안_찾는_카톡에서도_다른_글자로_다시_찾아_나간다():
    """같은 글자는 열린 검색창을 Esc 로 닫은 뒤에도 새로 안 찾는 카톡이라면 — 0.11.11 의
    다시 찾기(같은 글자)는 같은 방 둘째 건에서 실패한다. 다른 글자는 새로 찾는다."""
    sender = SameRoomWin(esc_forgets=False)
    results = [sender.send_text(ROOM, f"{n}번째") for n in range(1, 6)]
    assert [r.ok for r in results] == [True] * 5, [r.error for r in results]
    assert kw.retry_query(ROOM) in sender.enter_queries
    assert sender.pasted_into == [ROOM] * 5


def test_같은_글자로_다시_찾으면_그_카톡에서는_실패한다(monkeypatch):
    """흉내가 그 증상을 재현하는지 — 다시 찾는 글자를 바꾸지 않으면 둘째 건이 막힌다."""
    monkeypatch.setattr(kw, "retry_query", lambda room: room)
    sender = SameRoomWin(esc_forgets=False)
    results = [sender.send_text(ROOM, "안녕하세요") for _ in range(2)]
    assert [r.ok for r in results] == [True, False]
    assert sender.delivered == [(ROOM, "안녕하세요")]


def test_첫_시도에_막혔다가_다시_찾아_나가면_실패가_아니라_경고를_싣는다():
    sender = SameRoomWin()
    first = sender.send_text(ROOM, "첫 건")
    assert first.ok and first.warning is None
    second = sender.send_text(ROOM, "둘째 건")          # 같은 방 — 첫 Enter 로 안 열린다
    assert second.ok, second.error
    assert second.warning.startswith("첫 시도에 Enter 로 방이 열리지 않음")
    assert second.warning.endswith("다시 찾아 열었습니다")
    third = sender.send_text(ROOM, "셋째 건")           # 첫 시도에 열렸다 — 경고가 남지 않는다
    assert third.ok and third.warning is None


def test_다른_방이_열렸다가_다시_찾아_나가면_그_방_제목을_경고에_적는다():
    sender = SameRoomWin(wrong_opens=[OTHER])
    result = sender.send_text(ROOM, "안녕하세요")
    assert result.ok, result.error
    assert f"다른 방이 열림({OTHER!r})" in result.warning
