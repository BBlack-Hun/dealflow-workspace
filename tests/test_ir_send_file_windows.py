"""Windows 발송기가 자료 파일을 붙여 보낼 때 **무엇이 막아 주는가.**

## 이 파일이 지키는 것

Windows 카카오톡은 **이 기계에 아예 없다.** 그래서 `send_file` 은 실기로 한 번도
못 돌려 봤다 — 확인 창이 뜨는지, 뜬다면 무엇이 적혀 있는지 아무도 모른다.

그런 코드가 실투자사 방으로 파일을 보내면 되돌릴 수 없다. 그래서 만든 원칙은
mac 과 같다: **나가기 직전에 방 제목·파일명·개수를 확인하고, 하나라도 확인이
안 되면 보내지 않는다.** 여기에 한 줄이 더 붙는다 —

    **"확인할 창을 못 찾겠다" 도 실패다.** 못 찾았으니 그냥 보내는 길은 없다.

카톡 창은 흉내(가짜)로 대신한다. 여기서 볼 것은 pywinauto 가 도는가가 아니라
**어긋난 것을 보면 손을 떼는가** 이다. 창을 읽는 자리(`_confirm_snapshot`)는
전부 추측이고, 그 추측이 틀렸을 때 어떻게 되는지가 이 파일의 절반이다
(→ 안 보내고 실패로 남는다).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

from agent.sender import base, win_clipboard  # noqa: E402
from agent.sender import kakao_windows as kw  # noqa: E402

ROOM = "테스트 딜 공유방"


def confirm_window(*, room=ROOM, files=("IR.pdf",), count=None, rows=None,
                   title="파일 전송", buttons=None):
    """확인 창을 읽어 온 모양 — ⚠ **추측한 모양이다.**

        [제목]      파일 전송
        [주인 창]   테스트 딜 공유방      ← 이 창을 띄운 채팅방
        [단추]      취소 · 1개 전송
        [글자]      IR.pdf
    """
    n = len(files) if count is None else count
    return {
        "present": True,
        "title": title,
        "owner_title": room,
        "buttons": buttons if buttons is not None else ["취소", f"{n}개 전송"],
        "texts": list(files),
        "rows": len(files) if rows is None else rows,
    }


NOTHING = {"present": False, "title": "", "owner_title": "",
           "buttons": [], "texts": [], "rows": None}


class FakeWin(kw.KakaoDesktopSender):
    """카톡을 건드리는 자리를 전부 가짜로 바꾼 Windows 발송기.

    ⚠ `__init__` 을 부르지 않는다 — 진짜 `__init__` 은 pywinauto 를 import 하고
      Windows 가 아니면 아예 거절한다. 그래서 필요한 칸만 손으로 세운다.
      (mac 쪽 `FakeMac` 은 맥에서 도니까 super().__init__ 을 부를 수 있었다)
    """

    def __init__(self, snapshot, *, ir_root="", enabled=True, clipboard=None):
        self.sel = {"timings": {"after_file_paste": 0, "confirm_wait": 0,
                                "after_confirm_click": 0}}
        self.screenshot_dir = ""
        self._desktop = None
        self._pyautogui = None
        self._pyperclip = None
        self.ir_root_setting = ir_root
        self.can_send_files = enabled

        self.snapshot = snapshot
        self.clipboard = clipboard          # None 이면 담은 그대로 읽힌다
        self.phase = "idle"
        self.clicked: list = []
        self.pasted: list = []
        self.opened: list = []

    # --- 카톡을 건드리는 자리 --------------------------------------------
    def _open_room_verified(self, room_name):
        self.opened.append(room_name)
        return object(), None               # 방은 열렸고 제목도 맞다고 친다

    def _clipboard_put(self, paths):
        self.clipboard = list(paths) if self.clipboard is None else self.clipboard

    def _clipboard_read(self):
        return self.clipboard

    def _paste_into_chat(self, chat):
        self.pasted.append(self.clipboard)
        self.phase = "confirm"

    def _confirm_snapshot(self, room_name):
        if self.phase == "confirm":
            return dict(self.snapshot)
        return dict(NOTHING)

    def _click_dialog_button(self, room_name, name):
        self.clicked.append(name)
        self.phase = "idle"                 # 눌렀으면 창이 닫힌다
        return True

    def _safe_close(self):
        pass

    def _fail(self, room_name, error):
        return kw.SendResult(ok=False, error=error)   # 스크린샷은 찍지 않는다

    # --- 편의 -----------------------------------------------------------
    @property
    def sent(self) -> bool:
        """전송 단추를 실제로 눌렀는가."""
        return any(kw._match_buttons([c], kw.FILE_SEND_DEFAULTS["send_button_re"])
                   for c in self.clicked)

    @property
    def canceled(self) -> bool:
        return any(kw._match_buttons([c], kw.FILE_SEND_DEFAULTS["cancel_button_re"])
                   for c in self.clicked)


@pytest.fixture()
def ir_dir(tmp_path):
    """사람이 웹에서 넣은 IR 자료 폴더 + **그 형제 자리에 놓인 비밀 폴더.**

    파일명이 `../그폴더/그파일` 이면 그 열쇠가 투자사 카톡방으로 나간다.
    mac 쪽과 같은 모양을 세워 두고, Windows 도 같은 빗장을 쓰는지 본다.
    """
    share = tmp_path / "Share"
    docs = share / "자료폴더"
    docs.mkdir(parents=True)
    (docs / "IR.pdf").write_bytes(b"pretend pdf")

    secrets = share / "backup-keys"          # ← 형제 자리 (가짜 이름)
    secrets.mkdir()
    (secrets / "private_key").write_text("SECRET")

    lookalike = share / "자료폴더-딴것"       # `startswith` 로 막으면 여기서 샌다
    lookalike.mkdir()
    (lookalike / "남의자료.pdf").write_text("nope")
    return docs


# ══════════════════════════════════════════════════════════════════════════
#  ★ 관문 — 어긋나면 취소하고 보내지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_it_sends_when_everything_matches(ir_dir):
    """전부 맞으면 보낸다 — 관문이 늘 막기만 하면 쓸모가 없다."""
    win = FakeWin(confirm_window(files=("IR.pdf",)), ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert win.sent
    assert not win.canceled


def test_a_different_room_is_canceled_not_sent(ir_dir):
    """★ 방이 다르면 **취소**. 붙이는 사이 다른 창이 앞으로 올 수 있다."""
    win = FakeWin(confirm_window(room="남의 회사 단체방"), ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not win.sent, "방이 다른데 보냈다"
    assert win.canceled, "취소를 누르지 않았다"
    assert "방이 다릅니다" in result.error


def test_an_unreadable_room_is_canceled_not_sent(ir_dir):
    """★ 주인 창을 못 읽었으면 **어느 방인지 모른다** — 그것도 실패다."""
    win = FakeWin(confirm_window(room=""), ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not win.sent
    assert win.canceled
    assert "확인 창을 띄운 방을 읽지 못했습니다" in result.error


def test_a_different_file_is_canceled_not_sent(ir_dir):
    """★ 창에 뜬 파일명이 보내려던 것과 다르면 **취소**."""
    win = FakeWin(confirm_window(files=("작년_내부자료.pdf",)), ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not win.sent, "다른 파일인데 보냈다"
    assert win.canceled
    assert "확인 창에 없는 파일" in result.error


def test_a_different_count_is_canceled_not_sent(ir_dir):
    """★ 개수가 다르면 **취소**. 남은 선택이 섞여 들어온 경우다."""
    win = FakeWin(confirm_window(files=("IR.pdf",), count=3, rows=3),
                  ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not win.sent, "개수가 다른데 보냈다"
    assert win.canceled
    assert "개수가 다릅니다" in result.error


def test_no_confirm_window_means_nothing_is_sent(ir_dir):
    """★★ 이 파일에서 제일 중요한 검사.

    **확인 창을 못 찾으면 보내지 않는다.** Windows 카톡이 확인 창을 안 띄울
    수도 있다(붙여넣기가 바로 첨부로 얹힐 수도 있다). 그때 "못 찾았으니 그냥
    보낸다" 는 길을 만들면, 실기 확인 전에 켜졌을 때 무엇이 어디로 나갔는지
    아무도 모른다. 모르면 안 보낸다.
    """
    win = FakeWin(NOTHING, ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not win.sent
    assert "confirm_window_not_shown" in result.error


def test_a_window_that_is_not_the_confirm_window_is_not_trusted(ir_dir):
    """엉뚱한 창을 확인 창으로 착각하지 않는다 — 단추가 없으면 그 창이 아니다."""
    stray = confirm_window(buttons=["닫기"])
    win = FakeWin(stray, ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not win.sent
    assert "confirm_window_not_shown" in result.error


def test_an_unreadable_file_list_is_not_trusted(ir_dir):
    """개수를 어디서도 못 읽으면 통과시키지 않는다 — 못 읽는 것과 맞는 것은 다르다."""
    window = confirm_window(files=("IR.pdf",))
    window["rows"] = None
    window["buttons"] = ["취소", "전송"]        # 개수가 안 박힌 단추
    win = FakeWin(window, ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not win.sent
    assert win.canceled
    assert "개수를 읽지 못했습니다" in result.error


def test_the_gate_is_checked_before_the_send_button(ir_dir):
    """관문이 막으면 전송 단추는 **아예 눌리지 않는다.**"""
    win = FakeWin(confirm_window(files=("남의자료.pdf",)), ir_root=str(ir_dir))
    win.send_file(ROOM, ["IR.pdf"])

    assert not win.sent
    assert win.clicked == ["취소"]


def test_a_send_button_that_leaves_the_window_open_is_not_a_success(ir_dir):
    """단추를 눌렀는데 창이 그대로면 **나갔는지 모른다** — 성공으로 치지 않는다."""
    win = FakeWin(confirm_window(), ir_root=str(ir_dir))
    win._click_dialog_button = lambda room, name: win.clicked.append(name) or True
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "send_unconfirmed" in result.error
    assert "겹칠 수 있습니다" in result.error


# ══════════════════════════════════════════════════════════════════════════
#  클립보드 — 담은 것을 **다시 읽어 견준다**
# ══════════════════════════════════════════════════════════════════════════

def test_a_clipboard_that_holds_something_else_blocks_the_paste(ir_dir):
    """★ 담긴 줄 알았는데 안 담겼으면, Ctrl+V 는 **직전에 복사해 둔 것**을 낸다.

    바로 앞 건의 문구일 수도 있고 사람이 복사해 둔 무엇일 수도 있다. 그래서
    담은 뒤 다시 읽어 견주고, 다르면 **붙여넣지도 않는다.**
    """
    win = FakeWin(confirm_window(), ir_root=str(ir_dir),
                  clipboard=[r"C:\남의폴더\작년_내부자료.pdf"])
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "clipboard_mismatch" in result.error
    assert win.pasted == [], "클립보드가 다른데 붙여넣었다"
    assert not win.sent


def test_an_empty_clipboard_blocks_the_paste(ir_dir):
    win = FakeWin(confirm_window(), ir_root=str(ir_dir), clipboard=[])
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "clipboard_mismatch" in result.error
    assert win.pasted == []


def test_a_clipboard_that_refuses_blocks_the_paste(ir_dir):
    """클립보드를 다른 앱이 잡고 있으면 **보내지 않는다.**"""
    win = FakeWin(confirm_window(), ir_root=str(ir_dir))
    win._clipboard_put = _raise(win_clipboard.ClipboardError("다른 프로그램이 쓰고 있습니다"))
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "clipboard_failed" in result.error
    assert win.pasted == []


def _raise(exc):
    def _boom(*args, **kwargs):
        raise exc
    return _boom


def test_the_clipboard_carries_the_full_path(ir_dir):
    """서버는 파일명만 들고, 실제 경로는 이 PC 가 조립한다 — 담기는 것은 경로다."""
    win = FakeWin(confirm_window(), ir_root=str(ir_dir))
    win.send_file(ROOM, ["IR.pdf"])

    assert win.pasted == [[str(ir_dir / "IR.pdf")]]


# --- CF_HDROP 자체 (Windows 없이 그대로 시험할 수 있다) ---------------------

def test_the_clipboard_bytes_round_trip():
    """담는 모양이 맞나. 담았다 다시 읽으면 그대로 나와야 한다."""
    paths = [r"C:\Users\팀\자료\가나다 회사소개.pdf", r"D:\b.pdf"]
    assert win_clipboard.parse_hdrop(win_clipboard.hdrop_bytes(paths)) == paths


def test_the_clipboard_bytes_use_wide_characters():
    """★ 한글 경로가 깨지지 않으려면 넓은 글자(UTF-16)로 담아야 한다."""
    blob = win_clipboard.hdrop_bytes([r"C:\가나다.pdf"])
    import struct

    offset, _x, _y, _fnc, wide = struct.unpack("<Iiiii", blob[:20])
    assert offset == 20, "목록은 머리 바로 뒤에서 시작한다"
    assert wide == 1, "좁은 글자로 담으면 한글 경로가 깨진다"


def test_the_clipboard_bytes_end_with_two_nulls():
    """목록의 끝은 널 둘이다 — 하나면 윈도우가 목록의 끝을 못 찾는다."""
    blob = win_clipboard.hdrop_bytes([r"C:\a.pdf"])
    assert blob.endswith("\0\0".encode("utf-16-le"))


@pytest.mark.parametrize("bad", [[], [""], ["   "], ["a\x00b"]])
def test_the_clipboard_refuses_junk(bad):
    """빈 목록·빈 경로·널이 든 경로는 담지 않는다 — 담으면 뒤가 통째로 사라진다."""
    with pytest.raises(win_clipboard.ClipboardError):
        win_clipboard.hdrop_bytes(bad)


def test_a_short_clipboard_blob_is_refused():
    with pytest.raises(win_clipboard.ClipboardError):
        win_clipboard.parse_hdrop(b"\x00\x01")


# ══════════════════════════════════════════════════════════════════════════
#  파일명 — mac 과 **같은 빗장**을 쓰는가
#
#  파일명은 웹 화면에서 들어와 서버 DB 에 저장되고 여러 PC 가 함께 쓰는 값이다.
#  즉 화면에 친 글자가 그대로 경로가 된다. 빗장이 mac 에만 걸려 있으면 Windows
#  PC 로 발송하는 날 그대로 샌다.
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("evil", [
    "../backup-keys/private_key",       # ★ 형제 폴더의 비밀 파일
    "..\\backup-keys\\private_key",     # 윈도 구분자
    "../자료폴더-딴것/남의자료.pdf",
    "..",
    "subdir/IR.pdf",
    "C:\\Windows\\win.ini",             # 절대경로
    "/etc/passwd",
    "\\\\서버\\몫\\IR.pdf",              # 윈도 UNC
    ".hidden",
    "",
    "   ",
    "https://drive.google.com/file/d/abc/view",
])
def test_a_rejected_name_never_touches_kakaotalk(ir_dir, evil):
    """★ 규칙에 어긋나면 **카톡을 열지도 않는다.** 반쯤 하다 막히면 되돌릴 수 없다."""
    win = FakeWin(confirm_window(), ir_root=str(ir_dir))
    result = win.send_file(ROOM, [evil])

    assert not result.ok
    assert win.opened == [], "거절할 값인데 방을 열었다"
    assert win.pasted == [] and win.clicked == []
    assert "ir_file_rejected" in result.error


def test_the_sibling_secret_never_resolves(ir_dir):
    """★ 형제 폴더의 비밀 파일은 **실제로 있는데도** 나가지 않는다."""
    secret = ir_dir.parent / "backup-keys" / "private_key"
    assert secret.is_file(), "시험 자체가 헛돌지 않게 실제로 있어야 한다"

    win = FakeWin(confirm_window(), ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["../backup-keys/private_key"])

    assert not result.ok
    assert win.opened == []
    assert "ir_file_rejected" in result.error


def test_a_missing_file_never_touches_kakaotalk(ir_dir):
    """파일명은 함께 쓰지만 실물은 그 PC 에만 있다 — 없으면 분명히 실패한다."""
    win = FakeWin(confirm_window(), ir_root=str(ir_dir))
    result = win.send_file(ROOM, ["없는자료.pdf"])

    assert not result.ok
    assert win.opened == []
    assert "이 PC 에" in result.error


def test_nothing_to_send_is_not_a_success(ir_dir):
    win = FakeWin(confirm_window(), ir_root=str(ir_dir))
    assert not win.send_file(ROOM, []).ok
    assert win.opened == []


def test_no_ir_folder_set_fails_before_kakaotalk(ir_dir):
    """자료 폴더를 안 넣었으면 **카톡을 건드리기 전에** 실패한다."""
    win = FakeWin(confirm_window(), ir_root="")
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert win.opened == []
    assert "IR 자료 폴더" in result.error


# ══════════════════════════════════════════════════════════════════════════
#  ★ 켜지 않으면 아무 일도 없다 (`can_send_files`)
# ══════════════════════════════════════════════════════════════════════════

def test_it_is_off_by_default():
    """실기 확인 전에는 **꺼져 있다.** 켜면 서버가 파일 잡을 내주는데, 그때
    관문이 막으면 그 회차의 자료 전달이 통째로 실패한다(문구까지 안 나간다)."""
    assert kw.KakaoDesktopSender.can_send_files is False
    assert kw.file_send_enabled({}) is False
    assert kw.file_send_enabled({"file_send": {"verified": False}}) is False


def test_it_refuses_while_it_is_off(ir_dir):
    """꺼져 있으면 `send_file` 도 **지원 안 함**으로 거절한다.

    `can_send_files` 와 `send_file` 의 거절은 **같은 사실**을 말해야 한다.
    """
    win = FakeWin(confirm_window(), ir_root=str(ir_dir), enabled=False)
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert base.FILE_SEND_UNSUPPORTED in result.error
    assert win.opened == [] and win.pasted == []


def test_the_repo_switch_turns_it_on():
    """확인이 끝나면 `selectors.yaml` 을 고쳐 저장소에 못박는다."""
    assert kw.file_send_enabled({"file_send": {"verified": True}}) is True


def test_the_env_switch_turns_it_on_for_one_run(monkeypatch):
    """팀 PC 에서 확인하는 그 한 창에서만 켠다 — 코드를 고치지 않는다."""
    monkeypatch.setenv(kw.FILE_SEND_ENV, "1")
    assert kw.file_send_enabled({}) is True
    monkeypatch.setenv(kw.FILE_SEND_ENV, "0")
    assert kw.file_send_enabled({}) is False


def test_the_shipped_selectors_are_still_off():
    """★ 저장소에 켠 채로 들어가지 않게 지킨다 — 실기 확인이 먼저다."""
    import yaml

    root = pathlib.Path(__file__).resolve().parent.parent
    sel = yaml.safe_load((root / "agent" / "selectors.yaml").read_text(encoding="utf-8"))
    assert sel["file_send"]["verified"] is False, (
        "실기 확인 없이 파일 전송을 켰다 — 확인 절차는 docs/WINDOWS_TEST.md 참고")


# ══════════════════════════════════════════════════════════════════════════
#  관문 검사 자체 (창 없이 그대로)
# ══════════════════════════════════════════════════════════════════════════

def test_gate_passes_only_on_an_exact_match():
    assert kw.check_confirm_window(confirm_window(), ROOM, ["IR.pdf"]) is None


@pytest.mark.parametrize("snapshot", [None, {}, {"present": False}])
def test_gate_refuses_when_there_is_no_window(snapshot):
    assert "확인 창이 없습니다" in kw.check_confirm_window(snapshot, ROOM, ["IR.pdf"])


def test_gate_refuses_two_send_buttons():
    """보내기 단추가 둘이면 어느 쪽인지 알 수 없다 — 고르지 않는다."""
    window = confirm_window()
    window["buttons"] = ["취소", "1개 전송", "보내기"]
    assert "여러 개" in kw.check_confirm_window(window, ROOM, ["IR.pdf"])


def test_gate_handles_more_than_one_file():
    """개수 검사는 일반적으로 다룬다 — 나중에 여러 개를 한 번에 붙여도 그대로 쓴다."""
    window = confirm_window(files=("가.pdf", "나.pdf"))
    assert kw.check_confirm_window(window, ROOM, ["가.pdf", "나.pdf"]) is None
    assert kw.check_confirm_window(window, ROOM, ["가.pdf"])


def test_gate_reads_a_count_from_the_text_too():
    """개수가 단추가 아니라 문장에 적혀 있어도 읽는다 — 그리고 어긋나면 막는다."""
    window = confirm_window(files=("IR.pdf",))
    window["rows"] = None
    window["buttons"] = ["취소", "전송"]
    window["texts"] = ["IR.pdf", "파일 2개를 전송하시겠습니까?"]
    assert "개수가 다릅니다" in kw.check_confirm_window(window, ROOM, ["IR.pdf"])


def test_gate_accepts_a_full_path_in_the_window():
    """창이 파일명 대신 전체 경로를 보여 줘도 **같은 파일**이면 통과한다."""
    window = confirm_window(files=(r"C:\Users\팀\자료\IR.pdf",))
    assert kw.check_confirm_window(window, ROOM, ["IR.pdf"]) is None


def test_gate_still_blocks_a_different_file_shown_as_a_path():
    """경로로 보여 줘도 **다른 파일**은 그대로 막힌다 — 느슨해진 것이 아니다."""
    window = confirm_window(files=(r"C:\Users\팀\자료\남의자료.pdf",))
    assert kw.check_confirm_window(window, ROOM, ["IR.pdf"])


def test_gate_lets_through_a_name_typed_in_the_other_form():
    """★ 한글 파일명은 자모 조합 형태가 둘이다 — 같은 파일이면 통과시킨다.

    그냥 `==` 로 견주면 멀쩡한 파일을 "창에 없다" 며 취소한다(가짜 실패).
    mac 에서 실제로 겪은 자리라 Windows 도 같은 자를 쓴다.
    ⚠ 여기 이름은 지어낸 것이다.
    """
    import unicodedata

    nfc_name = unicodedata.normalize("NFC", "가나다_회사소개_최종.pdf")
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    assert nfc_name != nfd_name, "전제 확인 — 글자열로는 다르다"

    window = confirm_window(files=(nfc_name,))
    assert kw.check_confirm_window(window, ROOM, [nfd_name]) is None


def test_gate_ignores_the_underline_marker_in_button_names():
    """`&취소` 처럼 밑줄 표시가 붙어 나와도 같은 단추다."""
    window = confirm_window()
    window["buttons"] = ["&취소", "1개 전송"]
    assert kw.check_confirm_window(window, ROOM, ["IR.pdf"]) is None


@pytest.mark.parametrize("blanked", ["confirm_title_re", "cancel_button_re",
                                     "send_button_re"])
def test_a_blanked_selector_blocks_instead_of_matching_anything(blanked):
    """★ 값을 비워 두면 **아무 창에나 걸리는** 것이 아니라 막힌다.

    빈 정규식은 어떤 글자에나 걸린다. 그것을 그냥 두면 selectors 를 잘못 고친
    날 엉뚱한 창이 확인 창으로 읽힌다 — 비면 판단 불가로 본다.
    """
    conf = {blanked: ""}
    assert kw.check_confirm_window(confirm_window(), ROOM, ["IR.pdf"], conf)


def test_a_count_pattern_without_a_number_slot_blocks():
    """숫자를 꺼낼 괄호가 없는 본이면 개수를 못 읽는 것이다 — 막힌다."""
    window = confirm_window(files=("IR.pdf",))
    window["rows"] = None                       # 목록도 못 읽었다
    window["buttons"] = ["취소", "1개 전송"]
    assert "개수를 읽지 못했습니다" in kw.check_confirm_window(
        window, ROOM, ["IR.pdf"], {"count_re": r"\d+\s*개"})


def test_gate_uses_the_selector_file_when_the_real_window_differs():
    """★ 실기에서 창 모양이 다르면 **코드가 아니라 selectors.yaml 을 고친다.**

    확인하고 나서 무엇을 고쳐야 하는지가 분명해야 해서 여기 못박는다.
    """
    window = {"present": True, "title": "첨부 확인",
              "owner_title": ROOM, "buttons": ["닫기", "보냅니다"],
              "texts": ["IR.pdf"], "rows": 1}
    assert kw.check_confirm_window(window, ROOM, ["IR.pdf"]), "기본값으로는 못 읽는다"

    conf = {"confirm_title_re": "첨부 확인",
            "cancel_button_re": "^닫기$",
            "send_button_re": "^보냅니다$"}
    assert kw.check_confirm_window(window, ROOM, ["IR.pdf"], conf) is None


# ══════════════════════════════════════════════════════════════════════════
#  방을 찾는 자리는 `send_text` 와 **하나여야 한다**
# ══════════════════════════════════════════════════════════════════════════

def test_both_paths_open_the_room_the_same_way():
    """★ 파일 쪽에 새 길을 내면 오발송 방지가 갈라진다.

    한쪽만 고쳐졌을 때 문구는 막고 파일은 안 막는 상태가 되는데, 그것이 제일
    위험하다. 두 길이 **같은 함수**를 부르는지 원문에서 확인한다.
    """
    source = pathlib.Path(kw.__file__).read_text(encoding="utf-8")
    assert source.count("_open_room_verified") >= 3, (
        "send_text 와 send_file 이 같은 자리를 쓰지 않는다")
    assert "_opened_chat_window" in source
    # 방 제목이 어긋났다는 실패는 그 한 자리에서만 만들어져야 한다.
    assert source.count('"room_mismatch:') == 1


def test_the_module_still_imports_off_windows():
    """이 파일이 macOS/Docker 에서 import 만으로 터지면 웹 이미지가 깨진다."""
    assert kw.is_supported() in (True, False)
    assert "agent.sender.win_clipboard" in sys.modules


def test_it_ships_in_the_zip():
    """새 모듈을 빠뜨리면 사용자 PC 에서 ImportError 로 발송기가 아예 안 뜬다."""
    from app.routers.setup import AGENT_FILES

    assert "agent/sender/win_clipboard.py" in {src for src, _dest in AGENT_FILES}
