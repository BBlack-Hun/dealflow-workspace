"""Windows 발송기가 검색 결과 목록을 **못 읽을 때** 맨 위 방을 열어 제목을 읽는 길.

## 왜 생겼나

실기(0.11.1)에서 카톡 검색 결과는 화면에 보이는데 발송기는 모든 회사에 후보
0건을 올렸다 — Windows 카톡은 목록을 자체 컨트롤로 그려 `selectors.yaml:
room_search` 의 UIA 경로로는 줄이 안 읽힌다. 그래서 검색어를 넣은 채 **맨 위
결과를 열고**, 새로 뜬 채팅창의 제목(`GetWindowText`)을 읽은 뒤 바로 닫는다.

## 이 파일이 지키는 것

    ① 새로 뜬 창의 제목에 **회사명이 들어 있을 때만** 후보 하나로 돌려준다
    ② 새 창이 안 뜨면 **0건** — 지어내지 않는다
    ③ 채팅창에는 **아무것도 입력하지 않는다.** 누르는 키는 여는 키와 Esc 뿐
    ④ 연 그 창만 닫는다 — 앞에 없으면 키 대신 WM_CLOSE
    ⑤ 검색칸에 남의 글자가 있으면(보이는 목록이 남의 결과) **열지 않는다**
    ⑥ 목록을 읽어 맞는 줄이 있으면 예전처럼 **열지 않는다**

창·키보드는 가짜로 대신한다(`test_win_discover_rooms` 의 흉내를 그대로 쓴다).
"""
from __future__ import annotations

import pytest

from agent.sender import kakao_windows as kw
from tests.test_win_discover_rooms import FakeKakao, FakeWin, Ctrl

COMPANY = "가나다 바이오 랩스"
GROUP = "홍길동대표님가나다바이오랩스, 김영희 매니저"
MAIN = 100
CHAT = 200
PID = 7


class OpenWin(FakeWin):
    """맨 위 방 열기까지 흉내낸 Windows 발송기.

    `opens` — Enter 를 누르면 새로 뜰 창 `{hwnd: (제목, pid)}`. 비면 아무것도
    안 뜬다. `chat_foreground` 가 참이면 새 창이 앞으로 온다.
    """

    def __init__(self, kakao, *, opens=None, chat_foreground=True,
                 windows_readable=True, esc_closes=True, refocus_ok=True,
                 **kw_):
        super().__init__(kakao, **kw_)
        self.windows = {MAIN: ("카카오톡", PID), 300: ("메모장", 9)}
        self.opens = dict(opens or {})
        self.chat_foreground = chat_foreground
        self.windows_readable = windows_readable
        self.esc_closes = esc_closes
        self.refocus_ok = refocus_ok
        self.fg = MAIN
        self.posted = []
        self.opened_at = None
        self.paste_after_open = 0
        press = self._pyautogui.press
        hotkey = self._pyautogui.hotkey

        def _press(key):
            press(key)
            if key == "enter" and self.opened_at is None:
                self.opened_at = len(self._pyautogui.keys)
                self.windows.update(self.opens)
                if self.opens and self.chat_foreground:
                    self.fg = next(iter(self.opens))
            elif key == "esc" and self.fg in self.opens and self.esc_closes:
                self.windows.pop(self.fg, None)
                self.fg = MAIN

        def _hotkey(*keys):
            hotkey(*keys)
            if self.opened_at is not None:
                self.paste_after_open += 1

        self._pyautogui.press = _press
        self._pyautogui.hotkey = _hotkey

    def _focus_verified(self, win, expect_title=None):
        self.focus_calls += 1
        if self.opened_at is not None:
            if self.refocus_ok:
                self.fg = MAIN
            return self.refocus_ok
        return self.focus_ok

    def _top_windows(self):
        return dict(self.windows) if self.windows_readable else None

    def _foreground_hwnd(self):
        return self.fg

    def _foreground_title(self):
        return self.windows.get(self.fg, ("", 0))[0]

    def _window_pid(self, win):
        return PID

    def _hwnd_pid(self, hwnd):
        return self.windows.get(hwnd, ("", 0))[1]

    def _is_window_visible(self, hwnd):
        return hwnd in self.windows

    def _post_close(self, hwnd):
        self.posted.append(hwnd)
        self.windows.pop(hwnd, None)

    def _ensure_visible(self, win):
        pass


def unreadable():
    """화면엔 결과가 있는데 목록 컨트롤이 UIA 로 안 보이는 카톡(실기 0.11.1)."""
    return FakeKakao({COMPANY: [GROUP]}, no_list=True)


# ══════════════════════════════════════════════════════════════════════════
#  ① 되는 길
# ══════════════════════════════════════════════════════════════════════════

def test_it_reads_the_top_room_title_when_the_list_is_unreadable():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert "enter" in sender._pyautogui.keys


def test_it_types_nothing_into_the_chat_window():
    """★ 연 뒤로는 Esc 말고 아무 키도 안 누른다 — 붙여넣기는 더더욱."""
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    sender.discover_rooms(COMPANY)
    after = sender._pyautogui.keys[sender.opened_at:]
    assert after and all(k == "esc" for k in after)
    assert sender.paste_after_open == 0


def test_it_closes_the_chat_window_it_opened_and_the_search():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    sender.discover_rooms(COMPANY)
    assert CHAT not in sender.windows
    assert sender.posted == []          # 앞에 있었으니 Esc 로 닫았다
    assert sender._pyautogui.keys[-1] == "esc"   # 검색창도 닫는다
    assert 300 in sender.windows        # 남의 창은 그대로


def test_a_chat_window_that_is_not_in_front_gets_wm_close_not_a_key():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)},
                     chat_foreground=False)
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert sender.posted == [CHAT]
    # Esc 는 검색창 닫기 하나뿐 — 채팅창에 키를 보내지 않았다.
    assert sender._pyautogui.keys[sender.opened_at:] == ["esc"]


def test_esc_that_does_not_close_falls_back_to_wm_close():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)}, esc_closes=False)
    sender.discover_rooms(COMPANY)
    assert sender.posted == [CHAT]


def test_open_keys_come_from_selectors():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel["room_search"],
                                     open_top_keys=["down", "enter"])
    assert sender.discover_rooms(COMPANY) == [GROUP]
    i = sender._pyautogui.keys.index("enter")
    assert sender._pyautogui.keys[i - 1] == "down"


def test_a_tagged_company_name_is_searched_without_the_tag():
    """`[딜소개 불가]` 는 방 제목에 없다 — 넣으면 카톡 검색이 0건이 된다."""
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    assert sender.discover_rooms(f"{COMPANY} [딜소개 불가]") == [GROUP]
    assert sender._pyperclip.text == COMPANY


def test_it_also_opens_when_rows_were_read_but_none_matched():
    kakao = FakeKakao({COMPANY: ["엉뚱한 방"]})
    sender = OpenWin(kakao, opens={CHAT: (GROUP, PID)})
    assert sender.discover_rooms(COMPANY) == [GROUP]


# ══════════════════════════════════════════════════════════════════════════
#  ② 못 하면 0건 — 지어내지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_a_title_without_the_company_is_dropped():
    sender = OpenWin(unreadable(), opens={CHAT: ("홍길동 대표 가나다전자", PID)})
    assert sender.discover_rooms(COMPANY) == []
    assert CHAT not in sender.windows   # 그래도 닫는다


def test_no_new_window_means_zero_candidates():
    sender = OpenWin(unreadable(), opens={})
    assert sender.discover_rooms(COMPANY) == []
    assert sender._pyautogui.keys[-1] == "esc"


def test_a_window_of_another_program_is_not_taken():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, 999)})
    assert sender.discover_rooms(COMPANY) == []
    assert sender.posted == []          # 남의 프로그램 창은 닫지도 않는다


def test_unreadable_window_list_means_no_enter_at_all():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)},
                     windows_readable=False)
    assert sender.discover_rooms(COMPANY) == []
    assert "enter" not in sender._pyautogui.keys
    assert sender._pyautogui.keys[-1] == "esc"


def test_a_search_box_with_someone_elses_text_is_never_opened():
    kakao = FakeKakao({COMPANY: [GROUP]}, no_list=True, edit_value="딴 사람")
    sender = OpenWin(kakao, opens={CHAT: (GROUP, PID)})
    assert sender.discover_rooms(COMPANY) == []
    assert "enter" not in sender._pyautogui.keys


def test_readable_matching_rows_never_open_a_room():
    kakao = FakeKakao({COMPANY: [GROUP]})
    sender = OpenWin(kakao, opens={CHAT: (GROUP, PID)})
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert "enter" not in sender._pyautogui.keys


def test_the_fallback_can_be_switched_off():
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel["room_search"],
                                     open_top_fallback=False)
    assert sender.discover_rooms(COMPANY) == []
    assert "enter" not in sender._pyautogui.keys
    assert sender._pyautogui.keys[-1] == "esc"


def test_no_refocus_means_no_esc_for_the_search():
    """채팅창을 닫은 뒤 카톡이 앞에 안 오면 Esc 가 다른 앱으로 간다 — 안 누른다."""
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)},
                     chat_foreground=False, refocus_ok=False)
    sender.discover_rooms(COMPANY)
    assert sender._pyautogui.keys[sender.opened_at:] == []


def test_verify_room_never_opens_a_room():
    """판정(`verify_room`)은 그대로 — 정확히 같은 줄만 센다. 방을 열지 않는다."""
    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    assert sender.verify_room(GROUP) == "not_found"
    assert "enter" not in sender._pyautogui.keys


# ══════════════════════════════════════════════════════════════════════════
#  ③ 순수 판단
# ══════════════════════════════════════════════════════════════════════════

def test_company_key_ignores_spacing_and_corporate_marks():
    assert kw.company_key("(주)가나다 바이오  랩스") == "가나다바이오랩스"
    assert kw.company_key("㈜가나다전자") == kw.company_key("주식회사 가나다 전자")
    assert kw.company_key("가나다 [딜소개 불가]", strip_notes=True) == "가나다"


def test_company_key_composes_hangul():
    import unicodedata
    decomposed = unicodedata.normalize("NFD", "가나다전자")
    assert kw.company_key(decomposed) == "가나다전자"


def test_title_has_company():
    assert kw.title_has_company(GROUP, COMPANY)
    assert kw.title_has_company("홍길동 (주)가나다 바이오 랩스", COMPANY)
    assert kw.title_has_company(GROUP, f"{COMPANY} [딜소개 불가]")
    assert not kw.title_has_company("홍길동 대표 가나다 바이오", COMPANY)
    assert not kw.title_has_company(GROUP, "가")       # 너무 짧은 열쇠
    assert not kw.title_has_company(GROUP, "[딜소개 불가]")


def test_strip_annotations():
    assert kw.strip_annotations(" 가나다전자  [딜소개 불가] ") == "가나다전자"
    assert kw.strip_annotations("가나다전자") == "가나다전자"


def test_pick_new_window_only_takes_new_kakao_windows():
    before = {MAIN: ("카카오톡", PID), 300: ("메모장", 9)}
    after = {**before, **{CHAT: (GROUP, PID)}}
    assert kw.pick_new_window(before, after, pid=PID) == (CHAT, GROUP)
    # 원래 있던 창만 있으면 없다
    assert kw.pick_new_window(before, before, pid=PID) is None
    # 다른 프로그램 창
    assert kw.pick_new_window(before, {**before, **{CHAT: (GROUP, 9)}},
                              pid=PID) is None
    # 제목이 비었거나 메인 창 제목
    assert kw.pick_new_window(before, {**before, **{CHAT: ("", PID)}}) is None
    assert kw.pick_new_window(before, {**before, **{CHAT: ("카카오톡", PID)}},
                              exclude_titles=("카카오톡",)) is None


def test_pick_new_window_with_several_prefers_foreground_or_none():
    before = {MAIN: ("카카오톡", PID)}
    after = {**before, **{CHAT: (GROUP, PID), 201: ("다른 방", PID)}}
    assert kw.pick_new_window(before, after, pid=PID, foreground=201) == (
        201, "다른 방")
    assert kw.pick_new_window(before, after, pid=PID, foreground=MAIN) is None


class Node:
    def __init__(self, ctype, name="", kids=(), top=None, cls="", aid=""):
        self.control_type = ctype
        self.name = name
        self.class_name = cls
        self.automation_id = aid
        self._kids = list(kids)
        self.rectangle = (type("R", (), {"top": top})() if top is not None
                          else None)

    def children(self):
        return list(self._kids)


def test_uia_tree_entries_are_depth_and_count_limited():
    deep = Node("Pane", "0")
    cur = deep
    for i in range(1, 30):
        nxt = Node("Pane", str(i))
        cur._kids = [nxt]
        cur = nxt
    assert len(kw.uia_tree_entries(deep, max_depth=5)) == 6
    wide = Node("Pane", kids=[Node("Text", str(i)) for i in range(1000)])
    assert len(kw.uia_tree_entries(wide, max_nodes=400)) == 400
    lines = kw.format_uia_entries(kw.uia_tree_entries(
        Node("Window", "카카오톡", cls="EVA_Window", kids=[Node("Text", "가")])))
    assert lines[0] == "Window class='EVA_Window' name='카카오톡' id=''"
    assert lines[1].startswith("  Text")


def test_uia_tree_entries_survive_a_control_that_refuses():
    class Boom(Node):
        def children(self):
            raise RuntimeError("UIA 거절")
    assert len(kw.uia_tree_entries(Node("Pane", kids=[Boom("Pane")]))) == 2


def test_member_count_guess():
    chat = Node("Window", GROUP, top=100, kids=[
        Node("Text", GROUP, top=110), Node("Text", "5", top=112),
        Node("Text", "3", top=600)])
    assert kw.guess_member_count(kw.uia_tree_entries(chat)) == 5
    far = Node("Window", "x", top=100, kids=[Node("Text", "3", top=600)])
    assert kw.guess_member_count(kw.uia_tree_entries(far)) is None
    no_rect = Node("Window", "x", kids=[Node("Text", "abc"), Node("Text", "4")])
    assert kw.guess_member_count(kw.uia_tree_entries(no_rect)) == 4
    assert kw.guess_member_count([]) is None


# ══════════════════════════════════════════════════════════════════════════
#  ④ 진단 — 처음 한 번만 창 구조를 떠 둔다
# ══════════════════════════════════════════════════════════════════════════

def test_main_window_dump_is_written_once(tmp_path):
    sender = OpenWin(unreadable(), opens={})
    sender.screenshot_dir = str(tmp_path)
    sender.discover_rooms(COMPANY)
    path = tmp_path / kw.UIA_MAIN_DUMP_FILE
    assert path.exists()
    first = path.read_text(encoding="utf-8")
    assert "카카오톡" in first
    path.write_text("지움", encoding="utf-8")
    sender.discover_rooms(COMPANY)
    assert path.read_text(encoding="utf-8") == "지움"


def test_chat_window_dump_is_written_once(tmp_path):
    class Desk:
        def __init__(self):
            self.calls = 0

        def window(self, handle):
            self.calls += 1
            return Node("Window", GROUP, top=0,
                        kids=[Node("Text", GROUP, top=5), Node("Text", "3", top=5)])

    sender = OpenWin(unreadable(), opens={CHAT: (GROUP, PID)})
    sender.screenshot_dir = str(tmp_path)
    sender._desktop = Desk()
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert (tmp_path / kw.UIA_CHAT_DUMP_FILE).exists()
    assert sender._desktop.calls == 1


def test_server_search_query_drops_bracket_tags():
    from app.models import IrCompany
    from app.services import room_match

    company = IrCompany(name="(주)가나다전자 [딜소개 불가]")
    assert room_match.search_query(company) == "가나다전자"
    assert room_match.has_company_name("홍길동 대표 가나다전자",
                                       "가나다전자 [딜소개 불가]")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
