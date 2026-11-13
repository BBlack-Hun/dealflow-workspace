"""[방 연결 확인]이 **확인하느라 연 카톡 채팅창을 닫는가** (0.11.15).

사용자(11/13): "방 연결 확인하면서 열어둔 카톡은 왜 닫지 않고 그대로 나두는 거야?"

Mac 발송기는 찾기(`discover_rooms` — 검색 결과 줄만 읽는다)로 못 찾으면 방 이름으로
검색해 **방을 열어** 확인한다(`verify_room` → `_open_room_via_search`). 보낼 때는
`close_after_send` 로 닫지만 확인할 때는 닫는 줄이 없어, 확인한 방마다 창이 쌓였다.

지키는 것:

    ① 확인하느라 **연 창은 닫는다** — 확인됨 · 못 찾음 · 여럿 · 오류 어느 쪽이든
    ② 열기 **전부터** 떠 있던 창(사람이 열어 둔 같은 방 창)은 닫지 않는다
    ③ 닫기가 안 돼도 **판정은 그대로** 서버에 올라간다
    ④ 회차가 끝나면 검색칸 정리(`tidy_after_verify`)를 부르고, 그것이 터져도 보고는 그대로
    ⑤ Windows 맨 위 방 열기 — 새 창이 여럿이거나 고르기 전에 터져도 연 창은 닫는다

카톡은 흉내로 대신한다 — 이 PC 의 카톡을 열거나 닫지 않는다. 이름 · 방 제목은
모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest

from agent.sender import kakao_mac
from agent.sender import kakao_windows as kw
from tests.test_win_room_open_top import (CHAT, COMPANY, PID, OpenWin, unreadable)
from tests.test_win_room_open_top import GROUP as WIN_GROUP
from tests.test_win_room_open_top import MAIN as WIN_MAIN

ROOM = "홍길동 심사역님 가나다벤처스 딜방"
GROUP = "홍길동, 김영희, 박철수"          # 단톡방 기본 제목 — 쉼표가 든다
MAIN = kakao_mac.MAIN_WINDOW


# ══════════════════════════════════════════════════════════════════════════
#  Mac — 가짜 카톡
# ══════════════════════════════════════════════════════════════════════════

class FakeMac(kakao_mac.KakaoMacSender):
    """창 목록 · 검색으로 열기 · 창 닫기만 흉내낸 맥 발송기.

    `opens` — 검색으로 열면 새로 뜰 창 이름들(빈 목록이면 아무것도 안 뜬다).
    `already` — 확인 전부터 떠 있던 창 이름들.
    """

    def __init__(self, *, opens=(), already=(), boom_on_open=None,
                 names_boom_at=(), close_boom=False, close_ok=True):
        super().__init__({})
        self.windows = [MAIN, *already]
        self.opens = list(opens)
        self.boom_on_open = boom_on_open
        self.names_boom_at = set(names_boom_at)   # 몇 번째 창 목록 읽기에서 터지나
        self.names_calls = 0
        self.close_boom = close_boom
        self.close_ok = close_ok
        self.searched = []
        self.closed = []

    def _window_names(self):
        self.names_calls += 1
        if self.names_calls in self.names_boom_at:
            raise RuntimeError("창 목록을 못 읽었다")
        return list(self.windows)

    def _open_room_via_search(self, room_name):
        self.searched.append(room_name)
        self.windows.extend(self.opens)
        if self.boom_on_open is not None:
            raise self.boom_on_open

    def _close_window(self, name):
        self.closed.append(name)
        if self.close_boom:
            raise RuntimeError("닫기 단추를 못 눌렀다")
        if self.close_ok:
            self.windows = [w for w in self.windows if w != name]
        return self.close_ok


@pytest.fixture(autouse=True)
def no_real_applescript(monkeypatch):
    """어느 시험도 진짜 `osascript` 를 부르지 않는다 — 부르면 이 PC 의 카톡이 움직인다."""
    def boom(script, timeout=20):
        raise AssertionError(f"진짜 AppleScript 를 불렀다: {script[:60]!r}")
    monkeypatch.setattr(kakao_mac, "_osa", boom)


# ── ① 연 창은 닫는다 ─────────────────────────────────────────────────────────

def test_mac_closes_the_room_it_opened_to_verify():
    mac = FakeMac(opens=[ROOM])
    assert mac.verify_room(ROOM) == "verified"
    assert mac.searched == [ROOM]
    assert mac.closed == [ROOM]
    assert mac.windows == [MAIN]


def test_mac_closes_even_when_the_opened_title_is_not_the_room():
    """검색으로 연 창 제목이 방 이름과 달라 `not_found` 여도 — 연 창은 닫는다."""
    other = ROOM + " 2기"
    mac = FakeMac(opens=[other])
    assert mac.verify_room(ROOM) == "not_found"
    assert mac.closed == [other]


def test_mac_closes_every_window_it_opened_when_ambiguous():
    mac = FakeMac(opens=[ROOM, ROOM])
    assert mac.verify_room(ROOM) == "ambiguous"
    assert mac.closed == [ROOM]                 # 이름으로 닫으면 둘 다 닫힌다
    assert mac.windows == [MAIN]


def test_mac_closes_even_when_reading_after_opening_fails():
    """연 뒤 창 목록 읽기가 터져 `not_found` 로 끝나도, 연 창은 닫는다."""
    mac = FakeMac(opens=[ROOM], names_boom_at={2})
    assert mac.verify_room(ROOM) == "not_found"
    assert mac.closed == [ROOM]


def test_mac_tries_to_close_even_on_an_accessibility_error():
    """접근성 오류는 위로 올리되(사람이 권한을 줘야 한다), 그 전에 연 창은 닫아 본다."""
    mac = FakeMac(opens=[ROOM],
                  boom_on_open=kakao_mac.AccessibilityError("권한 없음"))
    with pytest.raises(kakao_mac.AccessibilityError):
        mac.verify_room(ROOM)
    assert mac.closed == [ROOM]


def test_mac_opens_nothing_and_closes_nothing_when_search_finds_nothing():
    mac = FakeMac(opens=[])
    assert mac.verify_room(ROOM) == "not_found"
    assert mac.closed == []


def test_mac_never_closes_the_main_window():
    """카톡 메인 창이 숨어 있다가 검색하며 다시 떴다 — 그것은 닫을 창이 아니다."""
    mac = FakeMac(opens=[MAIN, ROOM])
    mac.windows = []                             # 열기 전에는 메인 창도 안 보였다
    mac.verify_room(ROOM)
    assert mac.closed == [ROOM]


# ── ② 사람이 열어 둔 창은 닫지 않는다 ───────────────────────────────────────

def test_mac_leaves_a_room_the_user_already_had_open():
    mac = FakeMac(already=[ROOM], opens=[ROOM])
    assert mac.verify_room(ROOM) == "verified"
    assert mac.searched == []                    # 열지도 않았다
    assert mac.closed == []
    assert ROOM in mac.windows


def test_mac_leaves_a_users_window_whose_title_differs_only_in_spacing():
    """같은 방이 띄어쓰기만 다른 제목으로 떠 있다 — 검색으로 열어도 그 창이 앞으로
    올 뿐 새 창은 안 뜬다. 원래 있던 창이니 닫지 않는다."""
    spaced = "홍길동  심사역님 가나다벤처스 딜방"
    mac = FakeMac(already=[spaced], opens=[])
    mac.verify_room(ROOM)
    assert mac.searched == [ROOM]
    assert mac.closed == []
    assert spaced in mac.windows


def test_mac_leaves_other_windows_that_were_open_before():
    mac = FakeMac(already=["다른 방"], opens=[ROOM])
    assert mac.verify_room(ROOM) == "verified"
    assert mac.closed == [ROOM]
    assert "다른 방" in mac.windows


# ── ③ 닫기가 안 돼도 판정은 그대로 ──────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [{"close_boom": True}, {"close_ok": False}])
def test_mac_close_failure_keeps_the_verdict(kwargs):
    mac = FakeMac(opens=[ROOM], **kwargs)
    assert mac.verify_room(ROOM) == "verified"
    assert mac.closed == [ROOM]


def test_mac_unreadable_window_list_after_verdict_keeps_the_verdict():
    mac = FakeMac(opens=[ROOM], names_boom_at={3})   # 닫으려고 읽을 때만 터진다
    assert mac.verify_room(ROOM) == "verified"
    assert mac.closed == []


# ── 창 이름 읽기 · 닫기 · 검색칸 지우기 — AppleScript 모양 ─────────────────────

def _scripted(monkeypatch, answers):
    scripts = []
    answers = list(answers)

    def fake(script, timeout=20):
        scripts.append(script)
        return answers.pop(0) if answers else ""

    monkeypatch.setattr(kakao_mac, "_osa", fake)
    return scripts


def test_mac_window_names_keep_commas_and_spaces(monkeypatch):
    """쉼표로 나눠 읽으면 `홍길동, 김영희, 박철수` 가 세 토막이 나 떠 있는 방도 못 알아본다."""
    _scripted(monkeypatch, [f"|{MAIN}|\n|{GROUP}|\n| 앞뒤 공백 |"])
    mac = kakao_mac.KakaoMacSender({})
    assert mac._window_names() == [MAIN, GROUP, " 앞뒤 공백 "]
    _scripted(monkeypatch, [f"|{MAIN}|\n|{GROUP}|\n| 앞뒤 공백 |"])
    assert mac.window_titles() == [MAIN, GROUP, "앞뒤 공백"]


def test_mac_a_comma_title_already_open_is_verified_without_opening(monkeypatch):
    scripts = _scripted(monkeypatch, [f"|{MAIN}|\n|{GROUP}|"])
    mac = kakao_mac.KakaoMacSender({})
    assert mac.verify_room(GROUP) == "verified"
    assert len(scripts) == 1                       # 창 목록만 읽었다 — 열지도 닫지도 않았다


def test_mac_close_presses_the_windows_close_button_first(monkeypatch):
    scripts = _scripted(monkeypatch, ["closed"])
    assert kakao_mac.KakaoMacSender({})._close_window(GROUP) is True
    assert len(scripts) == 1
    assert f'every window whose name is "{GROUP}"' in scripts[0]
    assert 'subrole is "AXCloseButton"' in scripts[0]
    assert "key code" not in scripts[0] and "keystroke" not in scripts[0]


def test_mac_close_falls_back_to_cmd_w_only_on_that_front_window(monkeypatch):
    scripts = _scripted(monkeypatch, ["left", "closed"])
    assert kakao_mac.KakaoMacSender({})._close_window(ROOM) is True
    second = scripts[1]
    guard = f'if not (frontmost and (name of front window) is "{ROOM}") then return "left"'
    press = f"key code {kakao_mac.CLOSE_KEY_CODE} using command down"
    assert guard in second and press in second
    assert second.index(guard) < second.index(press)   # 확인한 뒤에만 누른다
    assert "keystroke" not in second                    # 입력원을 타지 않는 물리 키


def test_mac_close_reports_a_window_that_stays(monkeypatch):
    _scripted(monkeypatch, ["left", "left"])
    assert kakao_mac.KakaoMacSender({})._close_window(ROOM) is False


def test_mac_tidy_clears_the_main_search_field(monkeypatch):
    scripts = _scripted(monkeypatch, ["cleared"])
    kakao_mac.KakaoMacSender({}).tidy_after_verify()
    assert len(scripts) == 1
    assert f'first window whose name is "{MAIN}"' in scripts[0]
    assert 'set value of sf to ""' in scripts[0]
    assert 'if (value of sf) is "" then return "empty"' in scripts[0]


# ══════════════════════════════════════════════════════════════════════════
#  ③ · ④ 발송기 고리 — 판정은 서버까지, 정리는 끝에 한 번
# ══════════════════════════════════════════════════════════════════════════

class _Client:
    def __init__(self, canceled=False):
        self.items = []
        self.jobs = []
        self.canceled = canceled

    def job_state(self, job_id):
        return {"canceled": self.canceled, "canceled_items": []}

    def report_item(self, item_id, status, error=None, screenshot_b64=None,
                    verify_result=None, found_room=None, candidates=None):
        self.items.append({"id": item_id, "status": status, "error": error,
                           "verify_result": verify_result})

    def report_job(self, job_id, status):
        self.jobs.append(status)


NO_WAIT = {"verify_delay_min_sec": 0, "verify_delay_max_sec": 0, "room_marker": ""}


def _run(sender, client=None, rooms=(ROOM,)):
    import agent.main as agent_main

    client = client or _Client()
    job = {"job_id": 5, "items": [{"id": i, "room_name": r, "query": r, "exact": True}
                                  for i, r in enumerate(rooms, start=1)]}
    agent_main.process_verify_job(client, sender, job, dict(NO_WAIT))
    return client


class LoopMac(FakeMac):
    """찾기(`discover_rooms`)는 0건 → 발송기 고리가 `verify_room` 으로 넘어간다."""

    def __init__(self, **kw_):
        super().__init__(**kw_)
        self.tidied = 0
        self.tidy_boom = False

    def discover_rooms(self, query, marker="", **_):
        return []

    def tidy_after_verify(self):
        self.tidied += 1
        if self.tidy_boom:
            raise RuntimeError("검색칸을 못 지웠다")


def test_the_job_reports_verified_even_when_closing_fails():
    mac = LoopMac(opens=[ROOM], close_boom=True)
    client = _run(mac)
    assert [(i["status"], i["verify_result"]) for i in client.items] == [
        ("sent", "verified")]
    assert client.jobs == ["done"]
    assert mac.closed == [ROOM]


def test_the_job_closes_each_room_it_opened():
    other = "김영희 대표님 다라마벤처스 딜방"

    class Two(LoopMac):
        def _open_room_via_search(self, room_name):
            self.searched.append(room_name)
            self.windows.append(room_name)

    mac = Two()
    client = _run(mac, rooms=(ROOM, other))
    assert [i["verify_result"] for i in client.items] == ["verified", "verified"]
    assert mac.closed == [ROOM, other]
    assert mac.windows == [MAIN]


def test_tidy_runs_once_at_the_end():
    mac = LoopMac(opens=[ROOM])
    _run(mac, rooms=(ROOM, ROOM + " 2"))
    assert mac.tidied == 1


def test_tidy_runs_even_when_the_job_is_stopped():
    mac = LoopMac(opens=[ROOM])
    client = _run(mac, client=_Client(canceled=True))
    assert client.items == [] and client.jobs == ["canceled"]
    assert mac.tidied == 1


def test_a_failing_tidy_does_not_change_the_report():
    mac = LoopMac(opens=[ROOM])
    mac.tidy_boom = True
    client = _run(mac)
    assert [i["verify_result"] for i in client.items] == ["verified"]
    assert client.jobs == ["done"]


def test_senders_without_tidy_still_work():
    """시험용 가짜 · 옛 발송기처럼 `tidy_after_verify` 가 없어도 돈다."""
    class Bare:
        def discover_rooms(self, query, marker="", **_):
            return [query]

        def verify_room(self, room_name):  # pragma: no cover - 안 불린다
            return "not_found"

    client = _run(Bare())
    assert [i["verify_result"] for i in client.items] == ["verified"]


def test_the_base_sender_has_a_quiet_tidy():
    from agent.sender.base import Sender

    assert Sender().tidy_after_verify() is None


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ Windows — 맨 위 방 열기에서 연 창은 어떻게 끝나든 닫는다
# ══════════════════════════════════════════════════════════════════════════

def test_windows_closes_every_new_chat_when_it_cannot_pick_one():
    """새 창이 둘 뜨고 어느 것도 앞에 없다 — 고르지 않지만(후보 0건) 둘 다 닫는다."""
    sender = OpenWin(unreadable(), opens={CHAT: (WIN_GROUP, PID), 201: ("다른 방", PID)},
                     chat_foreground=False)
    assert sender.discover_rooms(COMPANY) == []
    assert sorted(sender.posted) == sorted([CHAT, 201])
    assert 300 in sender.windows and WIN_MAIN in sender.windows   # 남의 창 · 메인 창은 그대로
    assert sender._pyautogui.keys[-1] == "esc"                      # 검색창도 닫는다


def test_windows_closes_the_opened_chat_when_picking_blows_up(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("창 고르기에서 터졌다")

    monkeypatch.setattr(kw, "pick_new_window", boom)
    sender = OpenWin(unreadable(), opens={CHAT: (WIN_GROUP, PID)})
    assert sender.discover_rooms(COMPANY) == []
    assert CHAT not in sender.windows


def test_windows_leaves_a_chat_the_user_already_had_open():
    """같은 방이 이미 떠 있다 — Enter 로 새 창이 안 뜬다. 원래 있던 창은 닫지 않는다."""
    sender = OpenWin(unreadable(), opens={})
    sender.windows[CHAT] = (WIN_GROUP, PID)
    assert sender.discover_rooms(COMPANY) == []
    assert CHAT in sender.windows
    assert sender.posted == []


def test_windows_never_closes_another_programs_new_window():
    sender = OpenWin(unreadable(), opens={CHAT: (WIN_GROUP, 999), 201: ("다른 방", PID)},
                     chat_foreground=False)
    sender.discover_rooms(COMPANY)
    assert CHAT in sender.windows
    assert sender.posted == [201]


def test_fresh_windows_lists_every_new_window():
    before = {WIN_MAIN: ("카카오톡", PID)}
    after = {**before, CHAT: (WIN_GROUP, PID), 201: ("다른 방", PID), 202: ("", PID)}
    assert kw.fresh_windows(before, after, pid=PID, exclude_titles=("카카오톡",)) == [
        (CHAT, WIN_GROUP), (201, "다른 방")]
