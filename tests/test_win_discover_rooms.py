"""Windows 발송기가 **카톡 방 제목을 읽어 올 때** 무엇이 막아 주는가.

## 이 파일이 지키는 것

방 제목은 우리가 만들어 맞출 수 없다 — 그래서 카톡에서 **읽어 온다.** macOS 에만
있던 자리(`kakao_mac.discover_rooms`)를 Windows 에도 채웠다.

그런데 **Windows 카카오톡은 이 기계에 아예 없다.** 검색 결과 목록이 어떤
컨트롤인지, 방 제목이 줄의 어디에 적히는지 아무도 못 봤다
(`selectors.yaml: room_search` 는 전부 추측이고 그렇게 표시해 두었다).

그런 코드가 틀렸을 때 **무슨 일이 나야 하는가** 가 이 파일이다:

    ① 못 읽으면 **후보 0건.** 거짓 후보를 지어내지 않는다.
    ② [방 연결 확인]은 **확인됨으로 올리지 않는다.** 모르는 것을 맞다고 하지 않는다.
    ③ 포커스를 못 잡으면 **키를 한 번도 누르지 않는다.** 방 이름이 브라우저로
       들어간 적이 있다(실기).
    ④ 후보를 넉넉히 모으는 것과 **판정**은 다른 자리다. 후보가 늘어도 판정은
       느슨해지지 않는다 (`agent/sender/base.py` 의 "never guess").

카톡 창은 흉내(가짜 UIA 트리)로 대신한다. 셀렉터는 **저장소에 실제로 실린
`agent/selectors.yaml` 을 그대로 읽어** 쓴다 — 코드에 글자로 박지 않았는지까지
여기서 함께 지킨다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest
import yaml

from agent.sender import kakao_mac as km
from agent.sender import kakao_windows as kw

ROOM = "홍길동 대표 가나다컴퍼니 , 김영희 매니저"
NEEDLE = "홍길동"

SELECTORS = yaml.safe_load(
    pathlib.Path("agent/selectors.yaml").read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════════
#  가짜 UIA 트리
# ══════════════════════════════════════════════════════════════════════════

class Ctrl:
    """가짜 UIA 컨트롤. pywinauto 가 주는 것 중 **우리가 쓰는 것만** 흉내낸다."""

    def __init__(self, control_type, name="", value=None, children=(),
                 auto_id="", boom=False):
        self.control_type = control_type
        self.name = name
        self.value = value          # None 이면 get_value() 가 터진다(패턴 없음)
        self.children = list(children)
        self.auto_id = auto_id
        self.boom = boom            # UIA 가 거절하는 컨트롤

    def window_text(self):
        return self.name

    def get_value(self):
        if self.value is None:
            raise RuntimeError("ValuePattern 이 없는 컨트롤")
        return self.value

    def automation_id(self):
        return self.auto_id

    def descendants(self, control_type=None):
        if self.boom:
            raise RuntimeError("UIA 가 거절했다")
        out = []
        for child in self.children:
            if control_type is None or child.control_type == control_type:
                out.append(child)
            out.extend(child.descendants(control_type=control_type))
        return out


def result_row(title, *, last_message="어제 보낸 글", blank=False):
    """검색 결과 한 줄 — 첫 글자 조각이 방 제목, 그 뒤는 마지막 메시지."""
    texts = [] if blank else [Ctrl("Text", name=title),
                              Ctrl("Text", name=last_message)]
    return Ctrl("ListItem", name="", children=texts)


class FakeKakao(Ctrl):
    """검색어에 따라 결과가 바뀌는 가짜 카톡 메인 창.

    `index` 가 '검색어 → 보일 제목들' 이다. `stale_reads` 번째 읽기까지는
    `stale` 을 보여 준다 — 카톡 검색 결과가 **한 박자 늦게** 반영되는 것을
    흉내내기 위한 것이다.
    """

    def __init__(self, index, *, stale=None, stale_reads=0, no_list=False,
                 list_boom=False, blank_rows=False, edit_value=None,
                 row_name_is_title=False):
        super().__init__("Window", name="카카오톡")
        self.index = index
        self.text = ""
        self.stale = stale or []
        self.stale_reads = stale_reads
        self.reads = 0
        self.no_list = no_list
        self.list_boom = list_boom
        self.blank_rows = blank_rows
        self.edit_value = edit_value      # None 이면 검색칸에 넣은 글자가 읽힌다
        self.row_name_is_title = row_name_is_title

    def _titles(self):
        self.reads += 1
        if self.reads <= self.stale_reads:
            return list(self.stale)
        return list(self.index.get(self.text, []))

    def descendants(self, control_type=None):
        value = self.text if self.edit_value is None else self.edit_value
        kids = [Ctrl("Edit", name="검색", value=value)]
        if not self.no_list:
            if self.row_name_is_title:
                rows = [Ctrl("ListItem", name=t) for t in self._titles()]
            else:
                rows = [result_row(t, blank=self.blank_rows)
                        for t in self._titles()]
            kids.append(Ctrl("List", name="검색결과", children=rows,
                             boom=self.list_boom))
        self.children = kids
        return super().descendants(control_type=control_type)


class FakePyAutoGui:
    def __init__(self):
        self.keys = []

    def hotkey(self, *keys):
        self.keys.append(tuple(keys))

    def press(self, key):
        self.keys.append(key)


class FakePyperclip:
    def __init__(self):
        self.text = ""

    def copy(self, text):
        self.text = text


class FakeWin(kw.KakaoDesktopSender):
    """카톡을 건드리는 자리만 가짜로 바꾼 Windows 발송기.

    ⚠ `__init__` 을 부르지 않는다 — 진짜 `__init__` 은 pywinauto 를 import 하고
      Windows 가 아니면 거절한다(`test_ir_send_file_windows.FakeWin` 과 같다).

    셀렉터는 **저장소에 실린 것을 그대로** 쓰고 대기시간만 0 으로 줄인다.
    """

    def __init__(self, kakao, *, focus_ok=True, window_boom=False, timings=None):
        self.sel = dict(SELECTORS)
        self.sel["timings"] = {k: 0 for k in SELECTORS.get("timings", {})}
        self.sel["timings"].update(timings or {})
        self.screenshot_dir = ""
        self._desktop = None
        self.ir_root_setting = ""
        self.can_send_files = False

        self.kakao = kakao
        self.focus_ok = focus_ok
        self.window_boom = window_boom
        self._pyautogui = FakePyAutoGui()
        self._pyperclip = FakePyperclip()
        self.focus_calls = 0

    # --- 가짜로 바꾸는 자리 ---
    def _kakao_window(self):
        if self.window_boom:
            raise RuntimeError("카톡 창이 없다")
        return self.kakao

    def _focus_verified(self, win, expect_title=None):
        self.focus_calls += 1
        return self.focus_ok

    # --- 흉내: Ctrl+V 가 검색칸에 글자를 넣는다 ---
    def _search_titles(self, win, query, conf, keep_open=False):
        # 붙여넣기 흉내를 끼워 넣고 진짜 자리를 그대로 부른다.
        original_hotkey = self._pyautogui.hotkey

        def hotkey(*keys):
            original_hotkey(*keys)
            if tuple(keys) == tuple(conf.get("paste_hotkey") or ["ctrl", "v"]):
                win.text = self._pyperclip.text

        self._pyautogui.hotkey = hotkey
        try:
            return super()._search_titles(win, query, conf, keep_open=keep_open)
        finally:
            self._pyautogui.hotkey = original_hotkey


@pytest.fixture
def kakao():
    return FakeKakao({ROOM: [ROOM]})


# ══════════════════════════════════════════════════════════════════════════
#  ① 되는 길 — mac 과 같은 모양으로 답한다
# ══════════════════════════════════════════════════════════════════════════

def test_it_reads_the_real_room_titles(kakao):
    sender = FakeWin(kakao)
    assert sender.discover_rooms(ROOM) == [ROOM]


def test_it_answers_in_the_same_shape_as_mac():
    """서버는 둘을 **구분하지 않고** 같은 칸으로 받는다 — 모양이 갈리면 안 된다."""
    mac = inspect.signature(km.KakaoMacSender.discover_rooms)
    win = inspect.signature(kw.KakaoDesktopSender.discover_rooms)
    assert list(mac.parameters) == list(win.parameters)
    assert mac.parameters["marker"].default == win.parameters["marker"].default == ""
    assert str(mac.return_annotation) == str(win.return_annotation)


def test_it_hands_back_a_list_of_plain_strings(kakao):
    found = FakeWin(kakao).discover_rooms(ROOM)
    assert isinstance(found, list)
    assert all(isinstance(t, str) for t in found)


def test_it_finds_a_room_by_the_name_alone():
    """시트의 직함이 방과 다를 수 있다 — 이름만으로도 찾아진다."""
    kakao = FakeKakao({NEEDLE: [ROOM, f"{NEEDLE} 대표 다른회사 , 박철수 이사"]})
    assert FakeWin(kakao).discover_rooms(NEEDLE) == [
        ROOM, f"{NEEDLE} 대표 다른회사 , 박철수 이사"]


def test_the_marker_narrows_it_down():
    kakao = FakeKakao({NEEDLE: [f"{NEEDLE} 딜공유방", f"{NEEDLE} 잡담방"]})
    assert FakeWin(kakao).discover_rooms(NEEDLE, marker="딜공유") == [
        f"{NEEDLE} 딜공유방"]


def test_a_title_in_the_row_name_is_read_too():
    """실기에서 줄 이름 자체가 제목이면 셀렉터 한 칸만 비우면 된다."""
    kakao = FakeKakao({ROOM: [ROOM]}, row_name_is_title=True)
    sender = FakeWin(kakao)
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel["room_search"],
                                     item_text_control_type="")
    assert sender.discover_rooms(ROOM) == [ROOM]


def test_it_never_opens_a_room(kakao):
    """글자만 읽는다. Enter 를 누르면 남의 대화창이 열린다."""
    sender = FakeWin(kakao)
    sender.discover_rooms(ROOM)
    assert "enter" not in sender._pyautogui.keys


def test_it_closes_the_search_when_it_is_done(kakao):
    """다음 검색이 직전 글자 위에 겹치지 않게."""
    sender = FakeWin(kakao)
    sender.discover_rooms(ROOM)
    assert sender._pyautogui.keys[-1] == "esc"


# ══════════════════════════════════════════════════════════════════════════
#  ② 못 할 때 — **후보 0건.** 지어내지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_an_empty_query_never_touches_kakaotalk(kakao):
    sender = FakeWin(kakao)
    assert sender.discover_rooms("   ") == []
    assert sender.focus_calls == 0
    assert sender._pyautogui.keys == []


def test_no_focus_means_no_candidates_and_no_keystrokes(kakao):
    """★ 포커스를 못 잡았는데 키를 누르면 **브라우저에** 방 이름이 들어간다."""
    sender = FakeWin(kakao, focus_ok=False)
    assert sender.discover_rooms(ROOM) == []
    assert sender._pyautogui.keys == []


def test_an_unreadable_result_list_means_zero_candidates():
    sender = FakeWin(FakeKakao({ROOM: [ROOM]}, no_list=True))
    assert sender.discover_rooms(ROOM) == []


def test_a_list_that_refuses_means_zero_candidates():
    sender = FakeWin(FakeKakao({ROOM: [ROOM]}, list_boom=True))
    assert sender.discover_rooms(ROOM) == []


def test_rows_with_no_readable_title_mean_zero_candidates():
    sender = FakeWin(FakeKakao({ROOM: [ROOM]}, blank_rows=True))
    assert sender.discover_rooms(ROOM) == []


def test_a_missing_kakao_window_means_zero_candidates(kakao):
    sender = FakeWin(kakao, window_boom=True)
    assert sender.discover_rooms(ROOM) == []


def test_empty_selectors_read_nothing_rather_than_anything(kakao):
    """빈 본으로 창을 뒤지면 엉뚱한 컨트롤이 잡힌다 — 안 뒤지는 편이 낫다."""
    sender = FakeWin(kakao)
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel["room_search"],
                                     list_control_types=[])
    assert sender.discover_rooms(ROOM) == []


def test_a_search_box_that_holds_something_else_blocks_the_read():
    """검색어가 그 칸에 안 들어갔으면 지금 보이는 목록은 **남의 결과**다."""
    kakao = FakeKakao({ROOM: [ROOM]}, edit_value="딴 사람 이름")
    assert FakeWin(kakao).discover_rooms(ROOM) == []


def test_an_unreadable_search_box_does_not_block_the_read(kakao):
    """못 읽는 것까지 실패로 보면 멀쩡한 PC 에서 후보가 영영 0건이 된다."""
    sender = FakeWin(kakao)
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = dict(sender.sel["room_search"],
                                     input_control_type="")
    assert sender.discover_rooms(ROOM) == [ROOM]


def test_a_stale_result_list_is_waited_out():
    """카톡 검색 결과는 한 박자 늦다 — 바로 읽으면 **직전 검색**이 잡힌다."""
    kakao = FakeKakao({ROOM: [ROOM]}, stale=["딴사람 대표 저쪽회사"], stale_reads=2)
    sender = FakeWin(kakao, timings={"room_search_wait": 5.0,
                                     "room_search_poll": 0})
    assert sender.discover_rooms(ROOM) == [ROOM]


def test_a_stale_list_that_never_updates_yields_nothing():
    kakao = FakeKakao({ROOM: [ROOM]}, stale=["딴사람 대표 저쪽회사"],
                      stale_reads=10_000)
    sender = FakeWin(kakao, timings={"room_search_poll": 0})
    assert sender.discover_rooms(ROOM) == []


# ══════════════════════════════════════════════════════════════════════════
#  ③ 판정 — 여기는 **글자까지 같아야** 한다
# ══════════════════════════════════════════════════════════════════════════

def test_one_exact_room_is_verified(kakao):
    assert FakeWin(kakao).verify_room(ROOM) == "verified"


def test_two_rooms_with_the_same_title_are_ambiguous():
    kakao = FakeKakao({ROOM: [ROOM, ROOM]})
    assert FakeWin(kakao).verify_room(ROOM) == "ambiguous"


def test_a_room_that_is_merely_similar_is_not_verified():
    """★ 후보로는 설 수 있어도 **확인됨은 아니다.** 한 글자 다르면 다른 방이다."""
    kakao = FakeKakao({ROOM: [ROOM + " 2"]})
    sender = FakeWin(kakao)
    assert sender.discover_rooms(ROOM) == [ROOM + " 2"]   # 후보로는 선다
    assert FakeWin(FakeKakao({ROOM: [ROOM + " 2"]})).verify_room(ROOM) == "not_found"


def test_an_unreadable_list_is_not_verified():
    """★ 0.11.0 전에는 이 자리가 **무조건 verified** 였다. 그것이 거짓이었다."""
    sender = FakeWin(FakeKakao({ROOM: [ROOM]}, no_list=True))
    assert sender.verify_room(ROOM) == "not_found"


def test_no_focus_is_not_verified(kakao):
    sender = FakeWin(kakao, focus_ok=False)
    assert sender.verify_room(ROOM) == "not_found"
    assert sender._pyautogui.keys == []


def test_an_empty_room_name_is_not_found(kakao):
    sender = FakeWin(kakao)
    assert sender.verify_room("  ") == "not_found"
    assert sender.focus_calls == 0


def test_the_placeholder_that_always_said_yes_is_gone():
    """자리 채우기가 남아 있으면 Windows PC 의 [방 연결 확인]이 전부 통과한다."""
    src = pathlib.Path("agent/sender/kakao_windows.py").read_text(encoding="utf-8")
    assert "returning 'verified' placeholder" not in src
    assert 'return "verified"\n' not in src, "조건 없이 verified 를 돌려주는 자리"


# ══════════════════════════════════════════════════════════════════════════
#  ④ 판단만 떼어 놓고 — 창 없이 그대로 시험한다
# ══════════════════════════════════════════════════════════════════════════

def test_the_needle_is_the_first_word():
    assert kw.needle_of("홍길동 대표") == "홍길동"
    assert kw.needle_of("  홍길동  ") == "홍길동"
    assert kw.needle_of("") == ""


def test_only_rows_that_carry_the_name_are_kept():
    """카톡 검색은 **참여자 이름으로도** 걸린다 — 제목에 이름이 없는 단체방이 섞인다."""
    rows = [ROOM, "그냥 단체방", f"{NEEDLE} 1:1"]
    assert kw.filter_room_titles(rows, ROOM) == [ROOM, f"{NEEDLE} 1:1"]


def test_blank_rows_are_dropped():
    assert kw.filter_room_titles([ROOM, "", "   ", None], ROOM) == [ROOM]


def test_duplicates_are_kept_so_ambiguity_survives():
    """★ 겹친 것을 하나로 접으면 `len(found) == 1` 이 되어 **확인됨으로 올라간다.**"""
    assert kw.filter_room_titles([ROOM, ROOM], ROOM) == [ROOM, ROOM]


def test_too_many_rows_are_cut_off():
    rows = [f"{NEEDLE} 방 {i}" for i in range(200)]
    assert len(kw.filter_room_titles(rows, NEEDLE, max_rows=60)) == 60


def test_a_broken_row_cap_falls_back_to_the_default():
    assert kw._max_rows({"max_rows": "이상한값"}) == 60
    assert kw._max_rows({"max_rows": 0}) == 60
    assert kw._max_rows({"max_rows": 5}) == 5


def test_an_empty_query_keeps_nothing():
    assert kw.filter_room_titles([ROOM], "  ") == []


def test_the_verdict_counts_exact_titles_only():
    assert kw.verdict_from_titles([ROOM], ROOM) == "verified"
    assert kw.verdict_from_titles([ROOM, "딴방"], ROOM) == "verified"
    assert kw.verdict_from_titles([ROOM, ROOM], ROOM) == "ambiguous"
    assert kw.verdict_from_titles(["딴방"], ROOM) == "not_found"
    assert kw.verdict_from_titles([], ROOM) == "not_found"
    assert kw.verdict_from_titles([ROOM], "") == "not_found"


def test_only_runs_of_spaces_are_forgiven():
    """줄 사이에서 공백이 겹쳐 올 수 있다. 그 밖의 보정은 하지 않는다."""
    assert kw.verdict_from_titles([f"{NEEDLE}  대표"], f"{NEEDLE} 대표") == "verified"
    assert kw.verdict_from_titles([f"{NEEDLE}대표"], f"{NEEDLE} 대표") == "not_found"


def test_the_same_hangul_in_two_forms_is_one_room():
    """UIA 가 자모를 쪼갠 형태로 줄 수도 있다 — 눈에 같은 글자는 같은 방이다."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", ROOM)
    assert decomposed != ROOM
    assert kw.verdict_from_titles([decomposed], ROOM) == "verified"


def test_a_row_title_comes_from_the_first_text_chunk():
    row = result_row(ROOM, last_message="마지막 글")
    assert kw.row_title(row) == ROOM


def test_a_row_with_nothing_readable_has_no_title():
    assert kw.row_title(result_row(ROOM, blank=True)) == ""


def test_a_row_that_refuses_has_no_title():
    assert kw.row_title(Ctrl("ListItem", name="", boom=True)) == ""


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ 셀렉터는 **파일에** 있다 — 코드에 글자로 박지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_the_shipped_selectors_describe_the_search():
    conf = SELECTORS["room_search"]
    assert conf["list_control_types"], "결과 목록 컨트롤이 비면 아무것도 못 읽는다"
    assert conf["item_control_types"], "줄 컨트롤이 비면 아무것도 못 읽는다"
    assert int(conf["max_rows"]) > 0


def test_the_code_defaults_and_the_file_carry_the_same_keys():
    assert set(SELECTORS["room_search"]) <= set(kw.ROOM_SEARCH_DEFAULTS)
    for key in ("list_control_types", "item_control_types",
                "item_text_control_type", "max_rows", "input_control_type"):
        assert key in SELECTORS["room_search"], key


def test_the_waits_live_in_the_one_timings_block():
    """⚠ `timings:` 가 두 번 있으면 뒤엣것이 앞엣것을 통째로 덮는다(겪었다)."""
    raw = pathlib.Path("agent/selectors.yaml").read_text(encoding="utf-8")
    assert raw.count("\ntimings:") == 1
    assert "room_search_wait" in SELECTORS["timings"]
    assert "room_search_poll" in SELECTORS["timings"]


def test_the_file_overrides_the_code(kakao):
    """파일 값이 코드 바닥값을 덮는가 — 카톡이 바뀌면 파일만 고쳐야 한다."""
    sender = FakeWin(kakao)
    sender.sel = dict(sender.sel)
    sender.sel["room_search"] = {"max_rows": 3}
    conf = sender.room_search_conf
    assert conf["max_rows"] == 3
    assert conf["list_control_types"] == kw.ROOM_SEARCH_DEFAULTS["list_control_types"]


def test_the_search_uses_the_hotkey_from_the_file(kakao):
    sender = FakeWin(kakao)
    sender.discover_rooms(ROOM)
    assert tuple(SELECTORS["search_hotkey"]) in sender._pyautogui.keys


def test_the_query_goes_through_the_clipboard(kakao):
    """한글은 키 입력으로 못 보낸다."""
    sender = FakeWin(kakao)
    sender.discover_rooms(ROOM)
    assert sender._pyperclip.text == ROOM


# ══════════════════════════════════════════════════════════════════════════
#  ⑥ 판 번호 — 팀원 PC 가 새것을 받았는지 서버가 알아야 한다
# ══════════════════════════════════════════════════════════════════════════

def test_the_version_went_up_for_this():
    from app import version

    assert version.as_tuple(version.VERSION) >= (0, 11, 0)


def test_it_is_not_a_new_job_kind():
    """새 종류를 만들면 그 종류를 모르는 발송기가 잡을 **큐에 세워 둔다.**

    `verify_room` 은 이미 있던 갈래다 — 낡은 발송기도 그대로 집어가고, 후보만
    0건으로 올린다. 그래서 옛 판이 깔린 PC 에서도 **멈추지 않는다.**
    """
    from agent.main import SUPPORTED_KINDS, VERIFY_KIND

    assert VERIFY_KIND == "verify_room"
    assert VERIFY_KIND in SUPPORTED_KINDS


def test_old_agents_are_not_told_to_update_for_this():
    """후보가 안 올라오는 것은 '멈춰야 할 발송이 안 멈추는 것' 과 무게가 다르다."""
    from app import version

    assert not version.agent_is_old("0.10.0")


# ══════════════════════════════════════════════════════════════════════════
#  ⑦ 잡과 이어 붙여 — 후보가 **서버까지** 올라가는가
#
#  `process_verify_job` 은 `hasattr(sender, "discover_rooms")` 로 갈린다.
#  그 자리가 비어 있던 것이 이 과제의 시작이었다.
# ══════════════════════════════════════════════════════════════════════════

class FakeAgentClient:
    """서버로 올라간 것을 적어 두는 가짜 통로."""

    def __init__(self):
        self.items = []
        self.jobs = []

    def job_state(self, job_id):
        return {"canceled": False, "canceled_items": []}

    def report_item(self, item_id, status, error=None, screenshot_b64=None,
                    verify_result=None, found_room=None, candidates=None):
        self.items.append({"id": item_id, "status": status, "error": error,
                           "verify_result": verify_result,
                           "found_room": found_room, "candidates": candidates})

    def report_job(self, job_id, status):
        self.jobs.append((job_id, status))


NO_WAIT = {"verify_delay_min_sec": 0, "verify_delay_max_sec": 0, "room_marker": ""}


def _verify_job(sender):
    import agent.main as agent_main

    client = FakeAgentClient()
    job = {"job_id": 7, "kind": "verify_room",
           "items": [{"id": 1, "room_name": ROOM, "query": ROOM, "name": NEEDLE}]}
    agent_main.process_verify_job(client, sender, job, dict(NO_WAIT))
    return client


def test_the_candidates_reach_the_server(kakao):
    """★ 이 자리가 비어 있어서 Windows PC 는 후보를 **한 건도** 못 올리고 있었다."""
    client = _verify_job(FakeWin(kakao))
    assert client.items[0]["candidates"] == [ROOM]
    assert client.items[0]["verify_result"] == "verified"
    assert client.items[0]["found_room"] == ROOM


def test_two_candidates_are_reported_as_ambiguous():
    """둘 중 하나를 골라 주지 않는다 — 고르는 것은 사람이다."""
    other = f"{NEEDLE} 대표 다른회사 , 박철수 이사"
    client = _verify_job(FakeWin(FakeKakao({ROOM: [ROOM, other]})))
    assert client.items[0]["candidates"] == [ROOM, other]
    assert client.items[0]["verify_result"] == "ambiguous"
    assert client.items[0]["found_room"] is None, "모르는데 방 이름을 정하면 안 된다"


def test_nothing_readable_reports_no_candidates_not_a_made_up_one():
    """★ 못 할 때는 **후보 0건**이다. 화면은 0건이어도 초안으로 돌아간다."""
    client = _verify_job(FakeWin(FakeKakao({ROOM: [ROOM]}, no_list=True)))
    assert client.items[0]["candidates"] is None
    assert client.items[0]["verify_result"] == "not_found"
    assert client.items[0]["status"] == "failed"


def test_the_job_still_finishes_when_nothing_was_found():
    """한 건을 못 찾아도 잡은 끝난다 — 큐에 서지 않는다."""
    client = _verify_job(FakeWin(FakeKakao({ROOM: [ROOM]}, no_list=True)))
    assert client.jobs == [(7, "done_with_errors")]


def test_the_job_is_wired_through_discover_rooms(kakao):
    """`hasattr(sender, "discover_rooms")` 가 갈림길이다 — 이름이 바뀌면 조용히 꺼진다."""
    assert hasattr(FakeWin(kakao), "discover_rooms")
    assert hasattr(km.KakaoMacSender, "discover_rooms")
