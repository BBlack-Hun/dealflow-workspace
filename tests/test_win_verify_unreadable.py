"""Windows 방 찾기가 **하나도 못 읽었을 때** 무엇을 하는가 (0.11.16).

운영의 윈도우 PC 한 대에서 방 찾기 한 회차가 전부 `못 찾음` 으로 끝났다. 로그로는
검색 결과 줄을 한 번도 못 읽었고(UIA), 맨 위 방을 여는 Enter 도 매번 새 창을 못
띄웠다 — **방이 없는 것**과 **확인을 못 한 것**이 같은 말로 섰고, 그 PC 화면이 어땠는지
볼 증거는 하나도 안 올라왔다.

지키는 것:

    ① 여는 키를 눌렀는데 새 창이 안 뜨면 검색창을 닫고 **한 번만** 더 찾는다 —
       검색칸에 남의 글자가 있었거나(`typed_mismatch`) 메인 창이 앞에 없었으면
       (`foreground_lost`) 다시 찾지 않는다. 포커스를 못 잡으면 키를 더 안 누른다
    ② 한 건의 검색이 하나도 안 읽혔으면 그 **까닭**이 남는다 — 판정은 그대로 `not_found`
    ③ 증거(화면 한 장 · 메인 창 자식 창 줄)는 검색 결과가 **떠 있을 때**(Esc 전에) 뜨고,
       잡마다 처음 몇 건만 올리며, 뜨다 · 올리다 터져도 **판정은 그대로**다
    ④ 채팅 탭 판정은 **읽기뿐**이다 — 모르면 아무 키도 안 누르고 예전처럼 찾는다.
       바꾸는 키 · 검색 건너뛰기는 설정으로 켰을 때만 움직인다
    ⑤ 맥 발송기는 그대로다

카톡 · 키보드 · 화면 찍기는 흉내로 대신한다(`test_win_room_open_top.OpenWin`). 이름 ·
방 제목은 모두 지어낸 값이다.
"""
from __future__ import annotations

import base64
import inspect
import sys
import types

import pytest

import agent.diagnose
import agent.main as agent_main
from agent.sender import kakao_mac
from agent.sender import kakao_windows as kw
from tests.test_verify_closes_rooms import LoopMac
from tests.test_verify_closes_rooms import _Client as OldClient
from tests.test_win_discover_rooms import SELECTORS, FakeKakao
from tests.test_win_room_open_top import (CHAT, COMPANY, GROUP, MAIN, PID, OpenWin,
                                          unreadable)
from tests.test_win_search_no_ctrl_a import PopupWin

NAME = "홍길동"
ROOMS = ("홍길동 심사역님 가나다벤처스 딜방", "김영희 이사님 다라마인베스트 딜방",
         "박철수 대표님 바사아파트너스 딜방", "이민수 팀장님 자차카캐피탈 딜방")
SEARCH = ("ctrl", "f")
PASTE = ("ctrl", "v")

# 메인 창 자식 창 흉내 `(제목, 클래스, 보이는가)` — 이름은 설정에 적어 준 것만 본다.
MAIN_VIEW = ("OnlineMainView", "EVA_ChildWindow", True)
CHAT_KIDS = [MAIN_VIEW, ("ChatRoomListView", "EVA_VH_ListControl_Dblclk", True)]
FRIEND_KIDS = [MAIN_VIEW, ("ContactListView", "EVA_VH_ListControl_Dblclk", True)]
LOCK_KIDS = [("LockModeView", "EVA_ChildWindow", True)]
TAB_NAMES = {"chat_view_titles": ["ChatRoomListView"],
             "other_view_titles": ["ContactListView"]}


@pytest.fixture(autouse=True)
def nothing_real(monkeypatch):
    """어느 시험도 이 PC 의 창 목록을 읽거나 AppleScript 를 부르지 않는다."""
    monkeypatch.setattr(agent.diagnose, "list_titles", lambda: ["카카오톡"])

    def boom(script, timeout=20):
        raise AssertionError(f"진짜 AppleScript 를 불렀다: {script[:60]!r}")
    monkeypatch.setattr(kakao_mac, "_osa", boom)


class BlindWin(OpenWin):
    """결과 줄을 UIA 로 못 읽는 PC. `open_on` 번째 Enter 에서야 채팅창이 뜬다
    (0 이면 끝내 안 뜬다). 화면 찍기 · 메인 창 자식 창 읽기는 적어 두기만 한다."""

    def __init__(self, kakao=None, *, open_on=0, later=None, children=(),
                 shot_boom=False, **kw_):
        super().__init__(kakao if kakao is not None else unreadable(), **kw_)
        self.later = dict(later or {CHAT: (GROUP, PID)})
        self.open_on = open_on
        self.enters = 0
        self.pasted = []          # 검색칸에 넣은 글자들(차례대로)
        self.children = list(children)
        self.shot_boom = shot_boom
        self.shots = []           # 화면을 찍은 때까지 누른 키 수
        press = self._pyautogui.press
        copy = self._pyperclip.copy

        def _press(key):
            press(key)
            if key == "enter":
                self.enters += 1
                if self.enters == self.open_on:
                    self.windows.update(self.later)
                    self.fg = next(iter(self.later))
            elif key == "esc" and self.fg in self.later:
                self.windows.pop(self.fg, None)
                self.fg = MAIN

        def _copy(text):
            self.pasted.append(text)
            copy(text)

        self._pyautogui.press = _press
        self._pyperclip.copy = _copy

    def _main_children(self, win):
        return list(self.children)

    def _shot_window(self, win):
        self.shots.append(len(self._pyautogui.keys))
        if self.shot_boom:
            raise RuntimeError("화면을 못 찍었다")
        return "PNG"

    @property
    def keys(self):
        return self._pyautogui.keys


def _conf(sender, section, **values):
    sender.sel = dict(sender.sel)
    sender.sel[section] = dict(sender.sel.get(section) or {}, **values)
    return sender


# ══════════════════════════════════════════════════════════════════════════
#  ① 새 창이 안 뜨면 한 번만 더 찾는다
# ══════════════════════════════════════════════════════════════════════════

def test_a_second_search_opens_the_room_the_first_enter_missed():
    sender = BlindWin(open_on=2)
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert sender.enters == 2
    # 같은 글자로는 카톡이 결과를 새로 세우지 않는다 — 보낼 때처럼 다른 글자로 찾는다.
    assert sender.pasted == [COMPANY, kw.retry_query(COMPANY)]
    assert sender.pasted[1] != COMPANY


def test_the_search_is_closed_before_it_searches_again():
    sender = BlindWin(open_on=2)
    sender.discover_rooms(COMPANY)
    first_enter = sender.keys.index("enter")
    second_search = [i for i, k in enumerate(sender.keys) if k == SEARCH][1]
    assert sender.keys[first_enter + 1:second_search] == ["esc"]


def test_it_retries_only_once():
    sender = BlindWin(open_on=3)
    assert sender.discover_rooms(COMPANY) == []
    assert sender.enters == 2
    assert sender.keys.count(SEARCH) == 2
    assert sender.keys[-1] == "esc"            # 마지막 검색창도 닫고 끝낸다


def test_a_room_that_opens_on_the_first_enter_is_not_searched_twice():
    """0.11.15 까지의 길 그대로 — 처음에 열리면 더 찾지 않는다."""
    sender = BlindWin(open_on=1)
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert sender.keys.count(SEARCH) == 1
    assert sender.pasted == [COMPANY]


def test_the_retry_can_be_switched_off():
    sender = _conf(BlindWin(open_on=2), "room_search", open_top_retry=False)
    assert sender.discover_rooms(COMPANY) == []
    assert sender.enters == 1
    assert sender.keys.count(SEARCH) == 1


def test_the_retried_title_is_still_checked_against_the_first_query():
    """다시 찾을 때 넣는 글자는 짧다 — 제목은 여전히 **처음 검색어**로 거른다."""
    sender = BlindWin(open_on=2, later={CHAT: ("홍길동 대표 가나다 바이오 랩", PID)})
    assert sender.discover_rooms(COMPANY) == []
    assert CHAT not in sender.windows          # 그래도 연 창은 닫는다


def test_no_retry_when_someone_elses_text_is_in_the_search_box():
    """`typed_mismatch` — 보이는 목록이 남의 결과다. 열지도, 다시 찾지도 않는다."""
    sender = BlindWin(FakeKakao({COMPANY: [GROUP]}, no_list=True, edit_value="딴 사람"),
                      open_on=1)
    assert sender.discover_rooms(COMPANY) == []
    assert sender._last_search_state == "typed_mismatch"
    assert sender.enters == 0
    assert sender.keys.count(SEARCH) == 1


def test_no_retry_when_the_main_window_is_not_in_front():
    """`foreground_lost` — Enter 도 누르지 않고, 다시 찾지도 않는다."""
    sender = PopupWin(unreadable(), opens={CHAT: (GROUP, PID)})
    assert sender.discover_rooms(COMPANY) == []
    assert sender._last_search_state == "foreground_lost"
    assert "enter" not in sender._pyautogui.keys
    assert sender._pyautogui.keys.count(SEARCH) == 1


def test_no_key_at_all_when_focus_is_lost_after_the_enter():
    """Enter 뒤 카톡을 앞에 못 두면 검색창 Esc 도 안 누른다 — 다시 찾을 일도 없다."""
    sender = BlindWin(open_on=2, refocus_ok=False)
    assert sender.discover_rooms(COMPANY) == []
    assert sender.keys[-1] == "enter"
    assert sender.keys.count(SEARCH) == 1


def test_no_second_search_when_focus_cannot_be_checked_again():
    """검색창은 닫았는데, 다시 찾기 **직전**에 카톡이 앞에 없다 — 키를 더 안 누른다."""
    sender = BlindWin(open_on=2)
    answers = iter([True, True, False])        # 시작 · Enter 뒤 · 다시 찾기 직전
    sender._focus_verified = lambda win, expect_title=None: next(answers)
    assert sender.discover_rooms(COMPANY) == []
    assert sender.keys.count(SEARCH) == 1
    assert sender.keys[-1] == "esc"            # 첫 검색창을 닫은 것이 마지막 키다


# ══════════════════════════════════════════════════════════════════════════
#  ② 하나도 안 읽혔으면 까닭이 남는다 — 판정은 그대로
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("marks, tab, want", [
    ([], "unknown", ""),                              # 검색을 안 했다 — 모르면 예전대로
    (["blind"], "unknown", "unreadable"),
    (["blind", "blind", "blind"], "chat", "unreadable"),
    (["blind", "read"], "unknown", ""),               # 한 번이라도 읽혔다
    (["opened", "blind"], "unknown", ""),
    (["read"], "locked", ""),                         # 읽혔으면 탭 판정보다 먼저다
    (["blind"], "locked", "locked"),
    (["not_ready"], "locked", "locked"),
    (["blind"], "other", "not_chat_tab"),
    (["no_focus"], "unknown", "no_focus"),
    (["blind", "foreground_lost"], "unknown", "no_focus"),
    (["typed_mismatch"], "unknown", "unreadable"),
    (["error"], "unknown", "unreadable"),
])
def test_the_reason_for_an_item_that_read_nothing(marks, tab, want):
    assert kw.blind_reason(marks, tab) == want


def test_a_blind_item_is_still_not_found_and_says_why():
    sender = BlindWin()
    sender.begin_verify_item()
    assert sender.discover_rooms(COMPANY) == []
    assert sender.verify_room(COMPANY) == "not_found"   # ★ 판정은 안 바뀐다
    note = sender.end_verify_item()
    assert note["marks"] == ["blind", "blind", "blind"]  # 찾기 두 번 + 이름 대조 한 번
    assert note["reason"] == "unreadable"


def test_an_item_whose_room_opened_has_no_reason():
    sender = BlindWin(open_on=2)
    sender.begin_verify_item()
    sender.discover_rooms(COMPANY)
    note = sender.end_verify_item()
    assert note["marks"] == ["blind", "opened"]
    assert note["reason"] == ""


def test_rows_that_were_read_make_it_a_plain_not_found():
    """줄은 읽혔고 맞는 방이 없었다 — 그것은 `못 찾음` 이다."""
    sender = BlindWin(FakeKakao({COMPANY: ["엉뚱한 방"]}))
    sender.begin_verify_item()
    assert sender.discover_rooms(COMPANY) == []
    assert sender.verify_room(COMPANY) == "not_found"
    note = sender.end_verify_item()
    assert note["marks"][0] == "read"           # 다시 찾기(짧은 글자)는 못 읽어도
    assert note["reason"] == ""                 # 한 번 읽혔으면 까닭을 싣지 않는다


def test_no_focus_is_its_own_reason_and_presses_nothing():
    sender = BlindWin(focus_ok=False)
    sender.begin_verify_item()
    assert sender.discover_rooms(COMPANY) == []
    assert sender.verify_room(COMPANY) == "not_found"
    note = sender.end_verify_item()
    assert note["marks"] == ["no_focus", "no_focus"]
    assert note["reason"] == "no_focus"
    assert sender.keys == []


def test_a_popup_in_front_counts_as_no_focus():
    sender = PopupWin(unreadable(), opens={CHAT: (GROUP, PID)})
    sender.begin_verify_item()
    sender.discover_rooms(COMPANY)
    note = sender.end_verify_item()
    assert note["marks"] == ["foreground_lost"]
    assert note["reason"] == "no_focus"


def test_nothing_is_noted_outside_a_verify_item():
    """보낼 때 · 후보 찾기만 할 때는 적지 않는다 — 건이 끝나면 비운다."""
    sender = BlindWin()
    sender.discover_rooms(COMPANY)
    assert sender._verify_marks is None
    assert sender.end_verify_item()["reason"] == ""
    sender.begin_verify_item()
    sender.discover_rooms(COMPANY)
    assert sender.end_verify_item()["reason"] == "unreadable"
    assert sender.end_verify_item() == {"reason": "", "marks": [], "tab": "unknown",
                                        "screenshot_b64": None, "ui_dump": []}


# ══════════════════════════════════════════════════════════════════════════
#  ③ 증거 — 검색 결과가 떠 있을 때 뜬다 · 키를 누르지 않는다 · 판정을 안 바꾼다
# ══════════════════════════════════════════════════════════════════════════

def test_the_screen_is_taken_while_the_results_are_still_up():
    sender = BlindWin(children=CHAT_KIDS)
    sender.begin_verify_item(want_evidence=True)
    sender.discover_rooms(COMPANY)
    sender.verify_room(COMPANY)
    note = sender.end_verify_item()
    assert note["screenshot_b64"] == "PNG"
    assert len(sender.shots) == 1               # 건마다 한 장 — 다시 찾기에서 또 안 찍는다
    before = sender.keys[:sender.shots[0]]
    assert before[-1] == "enter"                # 여는 키를 누른 뒤
    assert "esc" not in before                  # 검색창을 닫기 **전**
    assert note["ui_dump"][0] == "메인 창 자식 창 2개 · 탭 판정 unknown"
    assert any("ChatRoomListView" in line and line.startswith("보임")
               for line in note["ui_dump"])


def test_taking_the_evidence_presses_no_key():
    asked, plain = BlindWin(children=CHAT_KIDS), BlindWin(children=CHAT_KIDS)
    asked.begin_verify_item(want_evidence=True)
    plain.begin_verify_item(want_evidence=False)
    for sender in (asked, plain):
        sender.discover_rooms(COMPANY)
        sender.verify_room(COMPANY)
    assert asked.keys == plain.keys
    assert plain.shots == [] and plain.end_verify_item()["screenshot_b64"] is None


def test_no_evidence_outside_a_verify_item():
    sender = BlindWin()
    sender.discover_rooms(COMPANY)
    assert sender.shots == []


def test_no_evidence_when_the_rows_were_read():
    """줄은 읽혔는데 Enter 로 아무 방도 안 열렸다 — `못 찾음` 이라 찍을 일이 아니다.
    그 건의 뒤 검색(다시 찾기 · 이름 대조)이 못 읽혀도 마찬가지다."""
    sender = BlindWin(FakeKakao({COMPANY: ["엉뚱한 방"]}))
    sender.begin_verify_item(want_evidence=True)
    sender.discover_rooms(COMPANY)
    sender.verify_room("없는 방 이름")
    assert sender.shots == []
    assert sender.end_verify_item()["screenshot_b64"] is None


def test_a_failing_screenshot_changes_nothing():
    sender = BlindWin(children=CHAT_KIDS, shot_boom=True)
    sender.begin_verify_item(want_evidence=True)
    assert sender.discover_rooms(COMPANY) == []
    assert sender.verify_room(COMPANY) == "not_found"
    note = sender.end_verify_item()
    assert note["reason"] == "unreadable"
    assert note["screenshot_b64"] is None
    assert note["ui_dump"]                      # 자식 창 줄은 그래도 실린다


def test_unreadable_child_windows_change_nothing():
    sender = BlindWin()
    sender._main_children = lambda win: (_ for _ in ()).throw(RuntimeError("못 읽었다"))
    sender.begin_verify_item(want_evidence=True)
    assert sender.discover_rooms(COMPANY) == []
    note = sender.end_verify_item()
    assert note["reason"] == "unreadable" and note["ui_dump"] == []
    assert note["screenshot_b64"] == "PNG"


def test_the_real_capture_reads_only(monkeypatch):
    """진짜 `_shot_window` · `_main_child_lines` — 창 자리만 찍고 키는 안 누른다."""
    grabbed = []

    class Image:
        def save(self, buf, format=None):
            buf.write(b"png-bytes")

    def grab(bbox=None, **more):
        grabbed.append((bbox, more))
        return Image()

    monkeypatch.setitem(sys.modules, "PIL",
                        types.SimpleNamespace(ImageGrab=types.SimpleNamespace(grab=grab)))
    sender = OpenWin(unreadable())
    sender._hwnd_rect = lambda hwnd: (10, 20, 410, 720)
    shot = sender._shot_window(sender.kakao)
    assert base64.b64decode(shot) == b"png-bytes"
    assert grabbed[0][0] == (10, 20, 410, 720)
    assert sender._main_child_lines(sender.kakao) == ["메인 창 자식 창 0개 · 탭 판정 unknown"]
    assert sender._pyautogui.keys == []


def test_the_real_capture_gives_up_quietly(monkeypatch):
    """창 자리를 모르고 화면 전체도 못 찍으면 None — 던지지 않는다."""
    def grab(**_):
        raise OSError("화면을 못 잡았다")

    monkeypatch.setitem(sys.modules, "PIL",
                        types.SimpleNamespace(ImageGrab=types.SimpleNamespace(grab=grab)))
    sender = OpenWin(unreadable())
    assert sender._shot_window(sender.kakao) is None          # 자리를 모른다
    sender._hwnd_rect = lambda hwnd: (10, 20, 410, 720)
    assert sender._shot_window(sender.kakao) is None          # 찍다가 터졌다
    assert sender._pyautogui.keys == []


# ── 잡 고리 — 까닭 · 증거가 서버로 올라가는 자리 ─────────────────────────────

class Client:
    """서버로 올라간 것을 적어 두는 가짜 통로(0.11.16 — `verify_reason` · 진단 기록)."""

    def __init__(self, diag_boom=False):
        self.items, self.jobs, self.diags = [], [], []
        self.diag_boom = diag_boom

    def job_state(self, job_id):
        return {"canceled": False, "canceled_items": []}

    def report_item(self, item_id, status, error=None, screenshot_b64=None,
                    verify_result=None, found_room=None, candidates=None,
                    verify_reason=None):
        self.items.append({"id": item_id, "status": status, "error": error,
                           "screenshot_b64": screenshot_b64,
                           "verify_result": verify_result, "found_room": found_room,
                           "candidates": candidates, "verify_reason": verify_reason})

    def report_job(self, job_id, status):
        self.jobs.append(status)

    def report_diagnostics(self, payload):
        if self.diag_boom:
            raise RuntimeError("서버가 받지 않았다")
        self.diags.append(payload)


NO_WAIT = {"verify_delay_min_sec": 0, "verify_delay_max_sec": 0, "room_marker": ""}


def _run(sender, client=None, rooms=ROOMS, **cfg):
    client = client if client is not None else Client()
    job = {"job_id": 5, "kind": "verify_room",
           "items": [{"id": i, "room_name": r, "query": r, "name": r.split()[0]}
                     for i, r in enumerate(rooms, start=1)]}
    agent_main.process_verify_job(client, sender, job, dict(NO_WAIT, **cfg))
    return client


def _verdicts(client):
    return [(i["status"], i["verify_result"], i["candidates"]) for i in client.items]


ALL_NOT_FOUND = [("failed", "not_found", None)] * len(ROOMS)


def test_a_job_that_read_nothing_says_so_for_every_item():
    client = _run(BlindWin(children=CHAT_KIDS))
    assert _verdicts(client) == ALL_NOT_FOUND            # ★ 판정은 예전 그대로다
    assert [i["verify_reason"] for i in client.items] == ["unreadable"] * len(ROOMS)
    assert client.jobs == ["done_with_errors"]


def test_evidence_goes_up_for_the_first_two_items_only():
    sender = BlindWin(children=CHAT_KIDS)
    client = _run(sender)
    assert [i["screenshot_b64"] for i in client.items] == ["PNG", "PNG", None, None]
    assert len(sender.shots) == 2                        # 뒤 건은 찍지도 않는다
    assert [d["kind"] for d in client.diags] == ["verify_unreadable"] * 2
    assert [d["target_room"] for d in client.diags] == list(ROOMS[:2])
    first = client.diags[0]
    assert "unreadable" in first["error"] and "blind" in first["error"]
    assert first["ui_dump"][0].startswith("메인 창 자식 창 2개")
    assert first["window_titles"] == ["카카오톡"]


def test_the_evidence_count_comes_from_the_config():
    sender = BlindWin()
    client = _run(sender, verify_evidence_per_job=0)
    assert sender.shots == [] and client.diags == []
    assert [i["screenshot_b64"] for i in client.items] == [None] * len(ROOMS)
    # 증거를 안 올려도 까닭은 올라간다.
    assert [i["verify_reason"] for i in client.items] == ["unreadable"] * len(ROOMS)
    assert len(_run(BlindWin(), verify_evidence_per_job="많이").diags) == 2


def test_a_failing_upload_never_changes_the_verdict():
    client = _run(BlindWin(), Client(diag_boom=True))
    assert _verdicts(client) == ALL_NOT_FOUND
    assert [i["verify_reason"] for i in client.items] == ["unreadable"] * len(ROOMS)
    assert client.jobs == ["done_with_errors"]


def test_a_failing_screenshot_never_changes_the_verdict():
    client = _run(BlindWin(shot_boom=True))
    assert _verdicts(client) == ALL_NOT_FOUND
    assert [i["screenshot_b64"] for i in client.items] == [None] * len(ROOMS)
    assert len(client.diags) == 2                        # 화면이 없어도 기록은 올린다
    assert client.jobs == ["done_with_errors"]


def test_a_client_without_diagnostics_still_gets_every_verdict():
    class Bare(Client):
        report_diagnostics = None

    client = _run(BlindWin(), Bare())
    assert _verdicts(client) == ALL_NOT_FOUND


def test_a_found_room_carries_no_reason():
    """찾은 건에는 새 칸을 싣지 않는다 — 옛 모양의 통로(`verify_reason` 을 모른다)로도 간다."""
    client = OldClient()
    _run(BlindWin(open_on=1), client, rooms=(COMPANY,))
    assert [(i["status"], i["verify_result"]) for i in client.items] == [
        ("sent", "verified")]


class Scripted:
    """건마다 정해 둔 기록을 돌려주는 발송기 — 잡 고리의 셈만 본다."""

    name = "scripted"

    def __init__(self, *notes):
        self.notes = [dict(n) for n in notes]
        self.wants = []
        self.ended = 0

    def begin_verify_item(self, want_evidence=False):
        self.wants.append(want_evidence)

    def end_verify_item(self):
        self.ended += 1
        note = self.notes[len(self.wants) - 1]
        if note.get("end_boom"):
            raise RuntimeError("기록을 못 읽었다")
        return note

    def discover_rooms(self, query, marker="", **_):
        note = self.notes[len(self.wants) - 1]
        if note.get("boom"):
            raise RuntimeError("검색하다 터졌다")
        return list(note.get("found") or [])

    def verify_room(self, room):
        return "not_found"


BLIND = {"reason": "unreadable", "marks": ["blind"]}
READ = {"reason": "", "marks": ["read"]}


def test_once_a_search_was_read_later_blind_items_are_plain_not_found():
    """결과 줄을 못 읽는 PC 에서는 방이 **정말 없을 때**도 하나도 안 읽힌다. 같은 잡의
    앞 건에서 읽힌 적이 있으면 그 PC 카톡은 검색이 되는 상태다 — 예전처럼 `못 찾음`."""
    sender = Scripted(BLIND, READ, BLIND, BLIND)
    client = _run(sender)
    assert [i["verify_reason"] for i in client.items] == ["unreadable", None, None, None]
    assert _verdicts(client) == ALL_NOT_FOUND
    assert sender.wants == [True, True, False, False]    # 읽힌 뒤로는 증거도 안 뜬다
    assert len(client.diags) == 1


def test_a_found_room_also_counts_as_read():
    sender = Scripted({"reason": "", "marks": ["opened"], "found": [ROOMS[0]]}, BLIND)
    client = _run(sender, rooms=ROOMS[:2])
    assert [i["verify_result"] for i in client.items] == ["verified", "not_found"]
    assert [i["verify_reason"] for i in client.items] == [None, None]


def test_a_known_reason_is_kept_even_after_a_read():
    """잠금모드 · 포커스처럼 **확인된** 까닭은 앞 건이 읽혔어도 그대로 올린다."""
    sender = Scripted(READ, {"reason": "locked", "marks": ["blind"]},
                      {"reason": "no_focus", "marks": ["no_focus"]},
                      {"reason": "not_chat_tab", "marks": ["blind"]})
    client = _run(sender)
    assert [i["verify_reason"] for i in client.items] == [
        None, "locked", "no_focus", "not_chat_tab"]


def test_a_reason_never_rides_on_a_found_room():
    sender = Scripted({"reason": "unreadable", "marks": ["blind"], "found": [ROOMS[0]]})
    client = _run(sender, rooms=ROOMS[:1])
    assert client.items[0]["verify_result"] == "verified"
    assert client.items[0]["verify_reason"] is None
    assert client.items[0]["screenshot_b64"] is None and client.diags == []


def test_an_item_that_blew_up_reports_the_error_not_a_reason():
    sender = Scripted({"boom": True, **BLIND}, BLIND)
    client = _run(sender, rooms=ROOMS[:2])
    assert client.items[0]["error"].startswith("verify error:")
    assert client.items[0]["verify_reason"] is None
    assert sender.ended == 2                             # 터진 건의 기록도 비운다
    assert client.items[1]["verify_reason"] == "unreadable"


def test_broken_notes_never_change_the_verdict():
    class NoBegin(Scripted):
        def begin_verify_item(self, want_evidence=False):
            super().begin_verify_item(want_evidence)
            raise RuntimeError("기록을 시작하지 못했다")

    for sender in (NoBegin(BLIND), Scripted({"end_boom": True})):
        client = _run(sender, rooms=ROOMS[:1])
        assert _verdicts(client) == [("failed", "not_found", None)]
        assert client.jobs == ["done_with_errors"]


# ══════════════════════════════════════════════════════════════════════════
#  ④ 채팅 탭 — 읽기만 한다. 모르면 아무 키도 안 누른다
# ══════════════════════════════════════════════════════════════════════════

NAMED = dict(kw.CHAT_TAB_DEFAULTS, **TAB_NAMES)


@pytest.mark.parametrize("children, conf, want", [
    ([], NAMED, "unknown"),
    (LOCK_KIDS, NAMED, "locked"),
    ([("LockModeView_0x1F", "EVA_ChildWindow", True)], NAMED, "locked"),   # 머리 글자로 본다
    (LOCK_KIDS, kw.CHAT_TAB_DEFAULTS, "locked"),                          # 기본값으로도 본다
    ([("LockModeView", "EVA_ChildWindow", False), MAIN_VIEW], NAMED, "unknown"),  # 숨은 창
    (LOCK_KIDS + [MAIN_VIEW], NAMED, "unknown"),                          # 둘 다 보인다
    (CHAT_KIDS, NAMED, "chat"),
    (FRIEND_KIDS, NAMED, "other"),
    (FRIEND_KIDS + [("ChatRoomListView", "EVA_VH_ListControl_Dblclk", False)],
     NAMED, "other"),
    (CHAT_KIDS + FRIEND_KIDS, NAMED, "unknown"),                          # 둘 다 보이면 모른다
    (FRIEND_KIDS, kw.CHAT_TAB_DEFAULTS, "unknown"),                       # 이름을 안 적었다
    (CHAT_KIDS, kw.CHAT_TAB_DEFAULTS, "unknown"),
    ([("", "", True), (None, None, True)], NAMED, "unknown"),
])
def test_the_tab_is_read_from_the_child_windows(children, conf, want):
    assert kw.tab_state_of(children, conf) == want


def test_by_default_no_key_is_configured_and_no_search_is_skipped():
    """★ Windows 카톡에는 채팅 탭으로 가는 공식 단축키가 없다 — 기본은 안 누른다.
    탭 이름도 실기 확인 전이라 비워 둔다(= 모른다)."""
    for conf in (kw.CHAT_TAB_DEFAULTS, SELECTORS["chat_tab"]):
        assert conf["switch_keys"] == []
        assert conf["skip_search"] is False
        assert conf["chat_view_titles"] == [] and conf["other_view_titles"] == []
    assert set(SELECTORS["chat_tab"]) <= set(kw.CHAT_TAB_DEFAULTS)
    assert kw.tab_switch_chords(kw.CHAT_TAB_DEFAULTS) == []


def test_official_shortcuts_that_do_something_else_are_never_pressed():
    conf = {"switch_keys": [["ctrl", "a"], ["Ctrl", "L"], ["alt", "x"], ["alt", "f4"],
                            ["control", "n"], ["ctrl", "shift", "w"], ["alt", "n"],
                            [], ["f9"], "f8"]}
    assert kw.tab_switch_chords(conf) == [("f9",), ("f8",)]


def test_when_the_tab_is_unknown_the_configured_key_is_not_pressed():
    """★ 모르면 누르지 않는다 — 그리고 예전처럼 찾는다."""
    sender = _conf(BlindWin(open_on=1), "chat_tab", switch_keys=[["f9"]], **TAB_NAMES)
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert ("f9",) not in sender.keys
    assert sender._last_tab_state == "unknown"


def test_an_unreadable_main_window_is_unknown():
    sender = _conf(BlindWin(open_on=1), "chat_tab", switch_keys=[["f9"]],
                   skip_search=True, **TAB_NAMES)
    sender._main_children = lambda win: (_ for _ in ()).throw(RuntimeError("못 읽었다"))
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert ("f9",) not in sender.keys


def test_the_configured_key_is_pressed_once_before_the_search_on_another_tab():
    sender = _conf(BlindWin(open_on=2, children=FRIEND_KIDS), "chat_tab",
                   switch_keys=[["f9"]], **TAB_NAMES)
    hotkey = sender._pyautogui.hotkey

    def _hotkey(*keys):
        hotkey(*keys)
        if keys == ("f9",):
            sender.children = list(CHAT_KIDS)   # 그 키로 채팅 탭이 됐다

    sender._pyautogui.hotkey = _hotkey
    assert sender.discover_rooms(COMPANY) == [GROUP]
    assert sender.keys[:2] == [("f9",), SEARCH]
    assert sender.keys.count(("f9",)) == 1      # 채팅 탭이 된 뒤의 검색에서는 안 누른다
    assert sender._last_tab_state == "chat"


def test_the_configured_key_is_not_pressed_when_the_main_window_is_not_in_front():
    sender = _conf(BlindWin(open_on=1, children=FRIEND_KIDS), "chat_tab",
                   switch_keys=[["f9"]], **TAB_NAMES)
    sender.fg = 300                             # 메모장이 앞에 있다
    assert sender.discover_rooms(COMPANY) == []
    assert ("f9",) not in sender.keys
    assert PASTE not in sender.keys and "enter" not in sender.keys


@pytest.mark.parametrize("children", [FRIEND_KIDS, LOCK_KIDS])
def test_by_default_a_detected_state_adds_no_key_and_still_searches(children):
    """다른 탭 · 잠금모드로 보여도 기본값은 예전과 **똑같이** 움직인다 — 판정이 틀렸을 때
    잘 되던 PC 를 막지 않는다. 달라지는 것은 로그와 `확인 못 함` 의 까닭뿐이다."""
    seen = _conf(BlindWin(open_on=1, children=children), "chat_tab", **TAB_NAMES)
    plain = BlindWin(open_on=1)
    assert seen.discover_rooms(COMPANY) == plain.discover_rooms(COMPANY) == [GROUP]
    assert seen.keys == plain.keys
    assert seen._last_tab_state in ("other", "locked")


def test_a_detected_lock_becomes_the_reason_of_a_blind_item():
    sender = BlindWin(children=LOCK_KIDS)       # 잠금모드 이름은 기본값으로 본다
    sender.begin_verify_item(want_evidence=True)
    sender.discover_rooms(COMPANY)
    note = sender.end_verify_item()
    assert (note["reason"], note["tab"]) == ("locked", "locked")
    assert note["ui_dump"][0] == "메인 창 자식 창 1개 · 탭 판정 locked"


@pytest.mark.parametrize("children, reason", [(LOCK_KIDS, "locked"),
                                              (FRIEND_KIDS, "not_chat_tab")])
def test_skip_search_presses_nothing_when_the_state_is_known(children, reason):
    sender = _conf(BlindWin(open_on=1, children=children), "chat_tab",
                   skip_search=True, **TAB_NAMES)
    sender.begin_verify_item(want_evidence=True)
    assert sender.discover_rooms(COMPANY) == []
    assert sender.verify_room(COMPANY) == "not_found"
    note = sender.end_verify_item()
    assert sender.keys == []                    # 검색 단축키 · Enter · Esc 어느 것도
    assert note["marks"] == ["not_ready", "not_ready"]
    assert note["reason"] == reason
    assert sender.shots == []                   # 검색을 안 걸었으니 찍을 화면도 없다


@pytest.mark.parametrize("children", [[], CHAT_KIDS])
def test_skip_search_does_not_skip_what_it_cannot_tell(children):
    sender = _conf(BlindWin(open_on=1, children=children), "chat_tab",
                   skip_search=True, **TAB_NAMES)
    assert sender.discover_rooms(COMPANY) == [GROUP]


def test_only_the_search_path_looks_at_the_tab():
    """보내는 길(`_open_room_verified`)은 이번에 손대지 않았다."""
    assert "_chat_tab_ok" in inspect.getsource(kw.KakaoDesktopSender._search_titles)
    assert "_chat_tab_ok" not in inspect.getsource(
        kw.KakaoDesktopSender._open_room_verified)


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ 맥 발송기는 그대로다
# ══════════════════════════════════════════════════════════════════════════

def test_the_mac_sender_keeps_no_notes():
    assert not hasattr(kakao_mac.KakaoMacSender, "begin_verify_item")
    assert not hasattr(kakao_mac.KakaoMacSender, "end_verify_item")


def test_a_mac_job_reports_exactly_what_it_did_before():
    """옛 모양의 통로(`verify_reason` 칸이 없다)로도 그대로 돈다 — 새 칸을 안 보낸다."""
    client = OldClient()
    _run(LoopMac(opens=[]), client, rooms=ROOMS[:2])
    assert [(i["status"], i["verify_result"], i["error"]) for i in client.items] == [
        ("failed", "not_found", None)] * 2
    assert client.jobs == ["done_with_errors"]
