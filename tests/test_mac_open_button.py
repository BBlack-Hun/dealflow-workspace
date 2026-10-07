"""mac 열기 패널에서 `열기` 단추를 **못 찾을 때** 무엇을 하는가 (0.11.6).

실기(10/7): 열기 패널은 떴는데(`open-panel`) 시트 바로 아래 단추 중에
`OKButton`/`열기` 가 없어 8초 내내 `open_button_not_found` 로 끝났다. 자료가
막히니 문구도 안 나갔다.

고친 것:
  · 단추를 세 겹까지, 이름은 앞부분(`열기…`, `Open`)으로 찾는다
  · '폴더로 이동' 시트가 남아 있으면 누르지 않고 기다린다(한 번 더 Enter)
  · 그래도 못 찾으면 Return 을 **한 번만** — 맨 앞이 그 방의 열기 패널일 때만
  · 끝내 실패하면 패널 구조를 로그에 한 줄로 떠 둔다

어느 길로 열었든 **확인 시트 관문은 그대로다** — 여기서도 그것을 본다.
"""
from __future__ import annotations

import logging

import pytest

kakao_mac = pytest.importorskip("agent.sender.kakao_mac")

from tests.test_ir_send_file import ROOM, FakeMac, confirm_sheet  # noqa: E402


@pytest.fixture()
def root(tmp_path):
    d = tmp_path / "자료폴더"
    d.mkdir()
    (d / "IR.pdf").write_bytes(b"pretend pdf")
    return d


class NoButtonPanel(FakeMac):
    """열기 패널은 떴는데 `열기` 단추가 안 잡힌다 (10/7 실기 모양)."""

    def __init__(self, *a, front=True, return_works=True, **kw):
        super().__init__(*a, **kw)
        self.front = front
        self.return_works = return_works
        self.returns = 0
        self.dumps: list = []
        self.t_open_retry = 0.01

    def _click_open_button(self, room_name):
        return False

    def _open_by_return(self, room_name):
        if not self.front:
            return False
        self.returns += 1
        if self.return_works:
            self.phase = "confirm"
        return True

    def _dump_sheet_tree(self, room_name):
        self.dumps.append(room_name)
        return "0:AXSheet/#open-panel[]true | 1:AXGroup/#[]true"


# ── 단추 알아보기 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["열기", "열기…", "열기(O)", "Open", "Open…", "선택"])
def test_open_button_names_are_matched_by_prefix(name):
    assert kakao_mac.is_open_button(name=name)


def test_open_button_is_matched_by_identifier_whatever_its_title():
    assert kakao_mac.is_open_button(name="첨부", identifier="OKButton")


@pytest.mark.parametrize("name", ["취소", "1개 전송", "2 개 전송", "새로운 폴더", ""])
def test_other_buttons_are_not_the_open_button(name):
    assert not kakao_mac.is_open_button(name=name)


def test_a_count_button_is_never_the_open_button_even_with_the_id():
    assert not kakao_mac.is_open_button(name="1개 전송", identifier="OKButton")


def test_panel_with_a_renamed_open_button_is_still_the_open_panel():
    snap = {"present": True, "identifier": "", "buttons": ["취소", "열기…"]}
    assert kakao_mac._is_open_panel(snap)


def test_the_confirm_sheet_is_never_taken_for_the_open_panel():
    snap = confirm_sheet()
    snap["identifier"] = kakao_mac.OPEN_PANEL_ID
    assert not kakao_mac._is_open_panel(snap)


def test_snapshot_reads_the_goto_subsheet():
    snap = kakao_mac.parse_sheet_snapshot("FRONT\t방\nPRESENT\nSUBSHEET\nIDENT\topen-panel\n")
    assert snap["subsheet"] is True
    assert not kakao_mac.parse_sheet_snapshot("PRESENT\n")["subsheet"]


# ── 단추를 못 찾을 때 ─────────────────────────────────────────────────────

def test_return_opens_the_file_when_the_button_cannot_be_found(root):
    mac = NoButtonPanel(confirm_sheet(), ir_root=str(root))
    result = mac.send_file(ROOM, ["IR.pdf"])
    assert result.ok, result.error
    assert mac.returns == 1
    assert mac.sent                       # 관문을 지나 `1개 전송` 으로 나갔다


def test_return_is_pressed_only_once(root):
    """Return 이 먹지 않아도 **다시 치지 않는다** — 확인 시트가 막 뜨는 찰나에
    또 치면 그것이 곧 전송이다."""
    mac = NoButtonPanel(confirm_sheet(), ir_root=str(root), return_works=False)
    result = mac.send_file(ROOM, ["IR.pdf"])
    assert not result.ok
    assert mac.returns == 1
    assert "confirm_sheet_not_shown" in result.error
    assert not mac.sent and mac.canceled
    assert mac.dumps                      # 구조를 떠 두었다


def test_no_return_when_kakaotalk_is_not_in_front(root, caplog):
    """다른 앱이 앞에 있으면 키를 치지 않고 실패한다. 문구도 안 나간다."""
    mac = NoButtonPanel(confirm_sheet(), ir_root=str(root), front=False)
    with caplog.at_level(logging.WARNING, logger="agent.kakao_mac"):
        result = mac.send_file(ROOM, ["IR.pdf"])
    assert not result.ok
    assert "open_button_not_found" in result.error
    assert not mac.sent and mac.canceled
    assert mac.dumps == [ROOM]
    assert any("열기 패널 구조" in r.getMessage() and "AXSheet" in r.getMessage()
               for r in caplog.records)


def test_return_fallback_can_be_turned_off(root):
    mac = NoButtonPanel(confirm_sheet(), ir_root=str(root))
    mac.open_by_return = False
    result = mac.send_file(ROOM, ["IR.pdf"])
    assert not result.ok and mac.returns == 0
    assert "open_button_not_found" in result.error


def test_the_found_button_is_preferred_over_return(root):
    class Found(NoButtonPanel):
        def _click_open_button(self, room_name):
            self.clicked.append("열기…")
            self.phase = "confirm"
            return True

    mac = Found(confirm_sheet(), ir_root=str(root))
    assert mac.send_file(ROOM, ["IR.pdf"]).ok
    assert mac.returns == 0 and mac.sent


# ── '폴더로 이동' 시트가 남아 있을 때 ─────────────────────────────────────

class GotoStuck(NoButtonPanel):
    """Enter 를 쳤는데 '폴더로 이동' 시트가 안 닫힌다."""

    def __init__(self, *a, clears_on_second_enter=True, **kw):
        super().__init__(*a, **kw)
        self.subsheet = True
        self.clears = clears_on_second_enter
        self.goto_again = 0
        self.open_clicks_while_subsheet = 0
        self.t_goto_settle = 0.0

    def _sheet_snapshot(self, room_name):
        snap = super()._sheet_snapshot(room_name)
        if self.phase == "panel":
            snap["subsheet"] = self.subsheet
        return snap

    def _goto_again(self, room_name, path):
        self.goto_again += 1
        if self.clears:
            self.subsheet = False
        return True

    def _click_open_button(self, room_name):
        if self.subsheet:
            self.open_clicks_while_subsheet += 1
            return False
        self.clicked.append(kakao_mac.OPEN_BUTTON_NAME)
        self.phase = "confirm"
        return True


def test_a_lingering_goto_sheet_gets_one_more_enter(root):
    mac = GotoStuck(confirm_sheet(), ir_root=str(root))
    result = mac.send_file(ROOM, ["IR.pdf"])
    assert result.ok, result.error
    assert mac.goto_again == 1
    assert mac.open_clicks_while_subsheet == 0   # 시트가 떠 있는 동안 안 눌렀다
    assert mac.returns == 0


def test_a_goto_sheet_that_never_closes_fails_without_sending(root):
    mac = GotoStuck(confirm_sheet(), ir_root=str(root), clears_on_second_enter=False)
    result = mac.send_file(ROOM, ["IR.pdf"])
    assert not result.ok
    assert "goto_sheet_stuck" in result.error
    assert mac.goto_again == 1 and mac.returns == 0
    assert not mac.sent and mac.canceled


# ── AppleScript 모양 (실행하지 않고 글자만 본다) ──────────────────────────

class Recorder(kakao_mac.KakaoMacSender):
    pass


@pytest.fixture()
def scripts(monkeypatch):
    seen: list = []

    def fake(script, timeout=20):
        seen.append(script)
        return "none"

    monkeypatch.setattr(kakao_mac, "_osa", fake)
    return seen


def test_click_script_searches_nested_groups_and_skips_the_goto_sheet(scripts):
    Recorder({})._click_open_button(ROOM)
    s = scripts[-1]
    assert '{"OKButton"}' in s
    assert '"열기"' in s and '"Open"' in s
    assert "UI elements of e1" in s           # 두 겹 안쪽까지
    assert 'is not "AXSheet"' in s            # '폴더로 이동' 시트 안은 뒤지지 않는다
    assert "starts with" in s
    assert "entire contents" not in s         # 카톡 AX 가 먹통이 된다
    # 확인 시트에서는 누르지 않는다 — 그 검사가 click 보다 먼저다
    assert s.index('ends with "개 전송"') < s.index("click target")


def test_click_script_uses_configured_names(scripts):
    Recorder({"open_button_names": ["첨부"], "open_button_ids": ["Pick"]}) \
        ._click_open_button(ROOM)
    s = scripts[-1]
    assert '{"Pick"}' in s and '{"첨부"}' in s


def test_return_script_checks_front_app_room_and_sheet_before_the_key(scripts):
    Recorder({})._open_by_return(ROOM)
    s = scripts[-1]
    key = s.index("key code 36")
    assert s.index("frontmost is true") < key
    assert s.index(f'is not "{ROOM}"') < key
    assert s.index("exists sheet 1 of sh") < key
    assert s.index('ends with "개 전송"') < key


def test_dump_is_depth_limited_and_one_line(monkeypatch):
    seen: list = []

    def fake(script, timeout=20):
        seen.append(script)
        return "0:AXSheet/#open-panel[]true | \n1:AXGroup/#[]true | "

    monkeypatch.setattr(kakao_mac, "_osa", fake)
    out = Recorder({})._dump_sheet_tree(ROOM)
    assert "\n" not in out and "AXGroup" in out
    assert "entire contents" not in seen[-1]
    assert f"d < {kakao_mac.DUMP_DEPTH}" in seen[-1]
    assert f"n < {kakao_mac.DUMP_MAX_NODES}" in seen[-1]
