"""Windows 발송기가 **카톡 창 하나**를 고르는가.

실기(0.11.0)에서 `self._desktop.window(title_re="카카오톡.*")` 가
`ElementAmbiguousError: There are 3 elements that match` 를 던졌다 — 카카오톡은
제목이 '카카오톡' 으로 시작하는 숨은 보조 창을 여럿 띄운다. 그래서 방 검색·발송이
한 번도 돌지 못했다. pywinauto 없이(macOS) 가짜 창으로 고르는 기준을 지킨다.
"""
from __future__ import annotations

import logging

import pytest

from agent.sender import kakao_windows as kw


class Rect:
    def __init__(self, w, h):
        self._w, self._h = w, h

    def width(self):
        return self._w

    def height(self):
        return self._h


class FakeWindow:
    def __init__(self, title, handle, *, visible=True, size=(800, 600),
                 vanish=False):
        self.title = title
        self._handle = handle
        self.visible = visible
        self.size = size
        self.vanish = vanish

    @property
    def handle(self):
        return self._handle

    def window_text(self):
        if self.vanish:
            raise RuntimeError("창이 사라졌다")
        return self.title

    def is_visible(self):
        if self.vanish:
            raise RuntimeError("창이 사라졌다")
        return self.visible

    def rectangle(self):
        if self.vanish:
            raise RuntimeError("창이 사라졌다")
        return Rect(*self.size)


class FakeDesktop:
    def __init__(self, wins):
        self.wins = wins
        self.windows_calls = []
        self.window_calls = []

    def windows(self, **kw_):
        self.windows_calls.append(kw_)
        return list(self.wins)

    def window(self, **kw_):
        # ⚠ title_re 로 잡으면 진짜 pywinauto 는 모호하다고 터진다.
        assert "title_re" not in kw_, "title_re 로 창을 잡으면 모호해진다"
        self.window_calls.append(kw_)
        return ("spec", kw_)


class Sender(kw.KakaoDesktopSender):
    def __init__(self, wins, wait=0.0):
        self.sel = {"main_window_title_re": "카카오톡.*",
                    "main_window_title_kw": "카카오톡",
                    "timings": {"window_wait": wait}}
        self._desktop = FakeDesktop(wins)


def test_hidden_helpers_lose_to_visible_main():
    main = FakeWindow("카카오톡", 30, size=(400, 700))
    wins = [FakeWindow("카카오톡", 10, visible=False, size=(2000, 2000)),
            FakeWindow("카카오톡Helper", 20, visible=False),
            main]
    assert kw.pick_kakao_window(wins, "카카오톡") is main

    s = Sender(wins)
    assert s._kakao_window() == ("spec", {"handle": 30})


def test_exact_title_beats_bigger_chat_window():
    main = FakeWindow("카카오톡", 2, size=(300, 500))
    chat = FakeWindow("카카오톡 - 홍길동", 1, size=(1200, 900))
    assert kw.pick_kakao_window([chat, main], "카카오톡") is main


def test_largest_visible_when_no_exact_title():
    small = FakeWindow("카카오톡 A", 1, size=(100, 100))
    big = FakeWindow("카카오톡 B", 2, size=(900, 900))
    assert kw.pick_kakao_window([small, big], "카카오톡") is big


def test_no_visible_falls_back_to_exact_then_first():
    a = FakeWindow("카카오톡X", 1, visible=False)
    b = FakeWindow("카카오톡", 2, visible=False)
    assert kw.pick_kakao_window([a, b], "카카오톡") is b
    assert kw.pick_kakao_window([a], "카카오톡") is a
    assert kw.pick_kakao_window([], "카카오톡") is None


def test_vanishing_window_is_skipped():
    gone = FakeWindow("카카오톡", 1, vanish=True)
    main = FakeWindow("카카오톡", 2)
    assert kw.pick_kakao_window([gone, main], "카카오톡") is main


def test_timeout_raises_clear_korean_error():
    s = Sender([], wait=0.0)
    with pytest.raises(RuntimeError, match="카카오톡 창을 찾지 못했습니다"):
        s._kakao_window()


def test_logs_choice_once(caplog):
    s = Sender([FakeWindow("카카오톡", 7, visible=False),
                FakeWindow("카카오톡", 8)])
    with caplog.at_level(logging.INFO, logger="agent.kakao"):
        s._kakao_window()
        s._kakao_window()
    picked = [r for r in caplog.records if "카톡 창 선택" in r.getMessage()]
    assert len(picked) == 1
    assert "handle=8" in picked[0].getMessage()
    assert "후보 2개" in picked[0].getMessage()


def test_no_title_re_window_lookup_left():
    """`window(title_re=...)` 는 모호함을 부른다 — 소스에 남지 않게."""
    import inspect
    src = inspect.getsource(kw)
    assert "_desktop.window(title_re" not in src
