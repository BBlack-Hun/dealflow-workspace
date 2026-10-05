"""Windows 발송기가 검색칸을 비울 때 **Ctrl+A 를 누르지 않는가** (0.11.4).

## 실제로 난 일

0.11.3 은 카톡 검색칸에 남은 직전 검색어를 지우려고 Ctrl+F 다음에
Ctrl+A → Backspace 를 눌렀다. 그런데 Windows 카톡 메인 창에서 **Ctrl+A 는
'친구 추가' 단축키**다. 친구 추가 창이 떴고, 회사명은 검색칸이 아니라 **그 창에**
붙었다. 검색이 통째로 안 됐다(실기).

## 이 파일이 지키는 것

    ① 바닥값·selectors.yaml 의 비우기 키에 Ctrl+A 가 없다. 설정에 들어 있어도
       경고를 남기고 **건너뛴다**
    ② 먼저 UIA 로 검색칸을 비우고 되읽는다 — 비었으면 키를 하나도 안 누른다.
       못 비우면 End → Shift+Home → Backspace
    ③ 붙이기 전에 카톡 메인 창이 앞에 있는지 본다. 다른 창이 떴으면 **붙이지
       않는다.** 그 창이 카톡의 창이면 Esc 로 닫고, 다른 앱이면 아무 키도 안 누른다
    ④ 그때 맨 위 방 열기(Enter)도 하지 않는다

카톡의 '통합검색' 설정과 상관없다 — 우리는 Ctrl+F → 비우기 → 붙이기만 한다.
이름·회사명은 **전부 지어낸 값**이다 — 저장소가 공개다.
"""
from __future__ import annotations

import logging

from agent.sender import kakao_windows as kw
from tests.test_win_discover_rooms import SELECTORS, FakeKakao, FakeWin
from tests.test_win_room_open_top import CHAT, COMPANY, GROUP, MAIN, PID, OpenWin

CTRL_A = ("ctrl", "a")
DIALOG = 400                     # Ctrl+A 로 뜨던 '친구 추가' 창
OTHER_APP = 300                  # OpenWin 의 '메모장'(다른 프로세스)


def _has_ctrl_a(chord) -> bool:
    low = {str(k).lower() for k in (chord if isinstance(chord, (list, tuple))
                                    else [chord])}
    return "a" in low and bool(low & {"ctrl", "control", "ctrlleft", "ctrlright"})


# ── ① Ctrl+A 는 어디에도 없다 ──────────────────────────────────────────────

def test_바닥값과_selectors_에_ctrl_a_가_없다():
    for chord in kw.ROOM_SEARCH_DEFAULTS["clear_keys"]:
        assert not _has_ctrl_a(chord), chord
    for chord in SELECTORS["room_search"]["clear_keys"]:
        assert not _has_ctrl_a(chord), chord
    for chord in kw.clear_chords({}):
        assert not _has_ctrl_a(chord), chord


def test_설정에_ctrl_a_가_있어도_건너뛴다(caplog):
    caplog.set_level(logging.WARNING, logger=kw.log.name)
    conf = {"clear_keys": [["ctrl", "a"], ["Ctrl", "A"], ["control", "a"],
                           ["backspace"]]}
    assert kw.clear_chords(conf) == [("backspace",)]
    assert "친구 추가" in caplog.text


def test_설정에_ctrl_a_를_넣어도_한_번도_안_누른다():
    kakao = FakeKakao({COMPANY: [GROUP]}, uia_clear=False)
    kakao.text = "가나"
    sender = FakeWin(kakao)
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel["room_search"],
                                     clear_keys=[["ctrl", "a"], ["backspace"]])
    sender.discover_rooms(COMPANY)
    assert CTRL_A not in sender._pyautogui.keys


def test_기본_설정으로_돌려도_ctrl_a_를_안_누른다():
    kakao = FakeKakao({COMPANY: [GROUP]}, uia_clear=False)
    sender = FakeWin(kakao)
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert sender.verify_room(GROUP) in ("verified", "not_found", "ambiguous")
    assert CTRL_A not in sender._pyautogui.keys


# ── ② UIA 로 먼저 비운다 ───────────────────────────────────────────────────

def _between_f_and_v(keys):
    f = keys.index(("ctrl", "f"))
    v = keys.index(("ctrl", "v"))
    return keys[f + 1:v]


def test_UIA_로_비우면_키를_안_누른다():
    kakao = FakeKakao({COMPANY: [GROUP]})
    kakao.text = "가나다"                       # 직전 검색어가 남았다
    sender = FakeWin(kakao)
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert kakao.uia_sets == 1
    assert _between_f_and_v(sender._pyautogui.keys) == []


def test_UIA_로_못_비우면_안전한_키로_지운다():
    kakao = FakeKakao({COMPANY: [GROUP]}, uia_clear=False)
    kakao.text = "가나다"
    sender = FakeWin(kakao)
    sender.discover_rooms(COMPANY)
    assert _between_f_and_v(sender._pyautogui.keys) == [
        ("end",), ("shift", "home"), ("backspace",)]


def test_빈_칸이면_UIA_로_건드리지_않는다():
    kakao = FakeKakao({COMPANY: [GROUP]})
    sender = FakeWin(kakao)
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert kakao.uia_sets == 0


# ── ③④ 메인 창이 아닌 창이 앞에 뜨면 붙이지 않는다 ───────────────────────

class PopupWin(OpenWin):
    """Ctrl+F 직후 `popup` 창이 앞에 뜨는 카톡(0.11.3 의 친구 추가 창 흉내)."""

    def __init__(self, kakao, *, popup=(DIALOG, ("친구 추가", PID)), **kw_):
        super().__init__(kakao, **kw_)
        self.popup_hwnd, self.popup_info = popup
        press = self._pyautogui.press
        hotkey = self._pyautogui.hotkey

        def _hotkey(*keys):
            hotkey(*keys)
            if keys == ("ctrl", "f"):
                self.windows[self.popup_hwnd] = self.popup_info
                self.fg = self.popup_hwnd

        def _press(key):
            press(key)
            if key == "esc" and self.fg == DIALOG:
                self.windows.pop(DIALOG, None)
                self.fg = MAIN

        self._pyautogui.hotkey = _hotkey
        self._pyautogui.press = _press


def test_카톡의_다른_창이_뜨면_붙이지_않고_Esc_로_닫는다():
    sender = PopupWin(FakeKakao({COMPANY: [GROUP]}), opens={CHAT: (GROUP, PID)})
    assert sender.discover_rooms(COMPANY) == []
    keys = sender._pyautogui.keys
    assert ("ctrl", "v") not in keys
    assert "enter" not in keys                 # 맨 위 방도 안 연다
    assert keys.count("esc") == 1              # 친구 추가 창만 닫는다
    assert DIALOG not in sender.windows
    assert sender._last_search_state == "foreground_lost"


def test_다른_앱이_앞에_있으면_아무_키도_더_안_누른다():
    sender = PopupWin(FakeKakao({COMPANY: [GROUP]}), opens={CHAT: (GROUP, PID)},
                      popup=(OTHER_APP, ("메모장", 9)))
    assert sender.discover_rooms(COMPANY) == []
    keys = sender._pyautogui.keys
    assert ("ctrl", "v") not in keys
    assert "enter" not in keys
    assert "esc" not in keys                   # Esc 가 메모장으로 가면 안 된다


def test_확인도_못_읽은_것으로_답한다():
    sender = PopupWin(FakeKakao({GROUP: [GROUP]}))
    assert sender.verify_room(GROUP) == "not_found"
    assert ("ctrl", "v") not in sender._pyautogui.keys
