"""Windows 발송기가 파일을 붙인 뒤 **카톡의 `파일 전송` 창을 어떻게 찾고 다루는가** (0.11.12).

## 왜 생겼나

실기(잡 78/79)에서 Ctrl+V 뒤 카톡이 제 창 `파일 전송` 을 띄웠다 — 시험 파일이 0바이트라
`전송 불가 1 · 시험자료.pdf · 비어있는 파일 · [확인]` 이었다. 발송기는 제목에 더해 [취소]와
보내기 단추가 **둘 다** 있어야 확인 창으로 봐서 그 창을 놓쳤고(`confirm_window_not_shown`),
남은 진단에는 창 제목 목록뿐이라 무엇이 떴는지 알 수 없었다.

## 이 파일이 지키는 것

    ① 제목이 `파일 전송` 이 아니어도(비어도) **붙인 뒤 새로 뜬 카톡 창 · 채팅창이 띄운 창 ·
       채팅창 속 창** 중 보내기 단추가 든 것이 **딱 하나**면 그 창을 쓴다
    ② 둘 이상이면 고르지 않는다 · 하나도 없으면 안 보낸다 — 둘 다 진단을 남기고 Esc 로 턴다
    ③ `전송 불가` 면 [확인]으로 닫고 그 까닭을 실패로 남긴다 — **문구도 안 나간다**
    ④ 진단에는 카톡 창들과 그 속 컨트롤이 실린다 — **메인 창(대화 목록)의 속은 싣지 않는다**
    ⑤ 0바이트 파일은 카톡을 열기 **전에** 막는다

창 · 컨트롤 · 키보드는 가짜로 대신한다. 창을 고르고 누르고 닫는 코드는 진짜다.
"""
from __future__ import annotations

import pytest

from agent.sender import base
from agent.sender import kakao_windows as kw

ROOM = "가나다 시험방"
MAIN, CHAT, NOTEPAD, DIALOG, DIALOG2 = 100, 200, 300, 500, 501
PID = 7
SECRET = "남의 이름 — 지난 대화"          # 메인 창(대화 목록)에만 있는 글자


class Node:
    """가짜 UIA 컨트롤. `uia_tree_entries` · `descendants` · 단추 누르기만 흉내낸다."""

    def __init__(self, ctype, name="", kids=(), on_click=None):
        self.control_type = ctype
        self.name = name
        self.class_name = ""
        self.automation_id = ""
        self.rectangle = None
        self._kids = list(kids)
        self.on_click = on_click

    def children(self):
        return list(self._kids)

    def descendants(self, control_type=None):
        out = []
        for kid in self._kids:
            if control_type is None or kid.control_type == control_type:
                out.append(kid)
            out.extend(kid.descendants(control_type))
        return out

    def window_text(self):
        return self.name

    def click_input(self):
        self.on_click(self.name)


class Desktop:
    def __init__(self, trees):
        self.trees = trees

    def window(self, handle):
        return self.trees[handle]


class Keys:
    def __init__(self, kakao):
        self.kakao = kakao
        self.keys = []

    def hotkey(self, *keys):
        self.keys.append(keys)
        if keys == ("ctrl", "v"):
            self.kakao.paste()

    def press(self, key):
        self.keys.append(key)


class Chat:
    handle = CHAT


class Kakao(kw.KakaoDesktopSender):
    """Win32 · UIA 를 부르는 맨 끝 자리만 가짜로 바꾼 Windows 발송기.

    `appears` — Ctrl+V 를 누르면 뜰 창들 `[(hwnd, 제목, 주인, 트리)]`.
    `as_child` — 참이면 그 창들이 채팅창 **속**(자식 창)으로 뜬다.
    """

    def __init__(self, ir_root, appears=(), as_child=False):
        self.sel = {"timings": {"after_file_paste": 0, "confirm_wait": 0,
                                "after_confirm_click": 0, "after_close_chat": 0}}
        self.screenshot_dir = ""
        self.ir_root_setting = ir_root
        self.can_send_files = True
        self.windows = {MAIN: ("카카오톡", PID), CHAT: (ROOM, PID), NOTEPAD: ("메모장", 9)}
        self.children = []
        self.owners = {}
        self.trees = {
            MAIN: Node("Window", "카카오톡", [Node("ListItem", SECRET)]),
            CHAT: Node("Window", ROOM, [Node("Edit", "메시지 입력"),
                                        Node("Button", "전송")]),
        }
        self._desktop = Desktop(self.trees)
        self._pyautogui = Keys(self)
        self.appears = list(appears)
        self.as_child = as_child
        self.clicks = []
        self.closed = []
        self.clipboard = None

    # --- Ctrl+V 에 카톡이 하는 일 ---
    def paste(self):
        for hwnd, title, owner, tree in self.appears:
            self.trees[hwnd] = tree
            if self.as_child:
                self.children.append((hwnd, title))
                self.windows[hwnd] = (title, PID)     # 보이는지는 같은 자리로 본다
                continue
            self.windows[hwnd] = (title, PID)
            self.owners[hwnd] = owner

    def dialog(self, hwnd, title, *, texts=(), buttons=("취소", "전송"), closes_on=None):
        """`closes_on` — 누르면 창이 닫히는 단추들. None 이면 어느 단추든 닫힌다."""
        def _click(name):
            self.clicks.append(name)
            if closes_on is None or name in closes_on:
                self.windows.pop(hwnd, None)
                self.children = [c for c in self.children if c[0] != hwnd]
        kids = [Node("Text", t) for t in texts]
        kids += [Node("Button", b, on_click=_click) for b in buttons]
        return Node("Window", title, kids)

    # --- Win32 ---
    def _top_windows(self):
        return {h: w for h, w in self.windows.items()
                if h not in {c[0] for c in self.children}}

    def _owner_hwnd(self, hwnd):
        return self.owners.get(hwnd, 0)

    def _child_windows(self, hwnd):
        return list(self.children) if hwnd == CHAT else []

    def _window_pid(self, win):
        return PID

    def _foreground_hwnd(self):
        return CHAT

    def _foreground_title(self):
        return ROOM

    def _hwnd_title(self, hwnd):
        return self.windows.get(hwnd, ("", 0))[0]

    def _is_window_visible(self, hwnd):
        return hwnd in self.windows

    def _post_close(self, hwnd):
        self.closed.append(hwnd)
        self.windows.pop(hwnd, None)

    # --- 방 · 클립보드 · 실패 ---
    def _open_room_verified(self, room_name, should_stop=None):
        self.ui_dump = []
        return Chat(), None

    def _leave_room(self, chat, room_name):
        pass

    def _fail(self, room_name, error):
        return kw.SendResult(ok=False, error=error)

    def _clipboard_put(self, paths):
        self.clipboard = list(paths)

    def _clipboard_read(self):
        return self.clipboard

    @property
    def esc(self) -> bool:
        return "esc" in self._pyautogui.keys


@pytest.fixture()
def ir_dir(tmp_path):
    docs = tmp_path / "자료"
    docs.mkdir()
    (docs / "IR.pdf").write_bytes(b"pretend pdf")
    return docs


def sendable(kakao, hwnd=DIALOG, title="파일 전송", owner=CHAT, **kw_):
    kw_.setdefault("texts", ("전송 가능 1", "IR.pdf"))
    return (hwnd, title, owner, kakao.dialog(hwnd, title, **kw_))


# ══════════════════════════════════════════════════════════════════════════
#  ① 보낼 수 있는 창 — 딱 하나면 그 창의 [전송]을 컨트롤로 누른다
# ══════════════════════════════════════════════════════════════════════════

def test_a_titled_dialog_with_a_send_button_is_used(ir_dir):
    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao)]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert kakao.clicks == ["전송"]
    assert DIALOG not in kakao.windows


def test_an_untitled_dialog_owned_by_the_chat_is_now_accepted(ir_dir):
    """★ 제목이 없어도 — 붙인 뒤 새로 뜬 카톡 창이 채팅창이 띄운 창이고 [전송]이 있으면."""
    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao, title="", texts=("IR.pdf",),
                              buttons=("취소", "1개 전송"))]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert kakao.clicks == ["1개 전송"]


def test_a_dialog_inside_the_chat_window_is_found_by_its_title(ir_dir):
    """채팅창 **속**(자식 창)으로 뜨는 경우 — 제목이 맞으면 후보다. 방은 그 채팅창이다."""
    kakao = Kakao(str(ir_dir), as_child=True)
    kakao.appears = [sendable(kakao, owner=0)]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert kakao.clicks == ["전송"]


def test_a_new_dialog_nobody_owns_is_not_trusted(ir_dir):
    """새로 떴어도 **어느 방이 띄웠는지 모르면** 안 보낸다 — [취소]로 물러난다."""
    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao, owner=0)]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "확인 창을 띄운 방을 읽지 못했습니다" in result.error
    assert kakao.clicks == ["취소"]


def test_a_send_click_that_leaves_the_dialog_open_is_cleaned_up(ir_dir):
    """[전송]을 눌렀는데 창이 그대로면 성공이 아니다 — [취소]로 정리하고 알린다."""
    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao, closes_on=("취소",))]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "send_unconfirmed" in result.error and "겹칠 수 있습니다" in result.error
    assert kakao.clicks == ["전송", "취소"]
    assert DIALOG not in kakao.windows


# ══════════════════════════════════════════════════════════════════════════
#  ② 고를 수 없으면 — 안 보내고, 진단을 남기고, Esc 로 턴다
# ══════════════════════════════════════════════════════════════════════════

def test_two_candidates_are_refused(ir_dir):
    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao), sendable(kakao, hwnd=DIALOG2, title="")]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "confirm_window_not_shown" in result.error
    assert kakao.clicks == [], "어느 창인지 모르는데 눌렀다"
    assert kakao.esc
    dump = "\n".join(kakao.ui_dump)
    assert f"hwnd={DIALOG} " in dump and f"hwnd={DIALOG2} " in dump


def test_no_candidate_is_refused_with_diagnostics_and_cleanup(ir_dir, tmp_path):
    """★ 아무것도 안 뜨면 안 보낸다. 붙인 직후 · 실패할 때 카톡 창들을 떠 두고 Esc."""
    kakao = Kakao(str(ir_dir))
    kakao.screenshot_dir = str(tmp_path / "logs")
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "confirm_window_not_shown" in result.error
    assert kakao.clicks == [] and kakao.esc

    dump = "\n".join(kakao.ui_dump)
    assert "[붙여넣기 직후]" in dump and "[실패: confirm_window_not_shown]" in dump
    assert "메시지 입력" in dump, "채팅창 속 컨트롤이 진단에 없다"
    assert "단추=['전송']" in dump, "창 줄에 단추 이름이 없다"
    assert "'카카오톡'" in dump, "메인 창 줄은 있어야 한다"
    assert SECRET not in dump, "메인 창(대화 목록)의 속까지 실었다"
    assert "메모장" not in dump, "카톡이 아닌 창을 실었다"
    saved = (tmp_path / "logs" / kw.UIA_FILE_DUMP_FILE).read_text(encoding="utf-8")
    assert "[실패: confirm_window_not_shown]" in saved


def test_an_unrelated_new_kakao_window_is_not_a_candidate(ir_dir):
    """붙이는 사이 뜬 알림 창 같은 것 — 제목도 단추도 안 맞으면 후보가 아니다."""
    kakao = Kakao(str(ir_dir))
    popup = Node("Window", "", [Node("Text", "새 메시지")])
    kakao.appears = [(DIALOG2, "", 0, popup), sendable(kakao)]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert kakao.clicks == ["전송"]


# ══════════════════════════════════════════════════════════════════════════
#  ③ `전송 불가` — [확인]으로 닫고 까닭을 남긴다. 아무것도 안 나간다
# ══════════════════════════════════════════════════════════════════════════

REFUSED = ("전송 불가 1", "IR.pdf", "비어있는 파일")


def test_an_unsendable_dialog_is_dismissed_with_its_reason(ir_dir):
    """실기에서 본 그 창 — `전송 불가 1 · 파일명 · 비어있는 파일 · [확인]`."""
    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao, texts=REFUSED, buttons=("확인",))]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert result.error.startswith("file_refused")
    assert "IR.pdf · 비어있는 파일" in result.error
    assert kakao.clicks == ["확인"]
    assert DIALOG not in kakao.windows


def test_a_partly_unsendable_dialog_is_canceled_not_sent(ir_dir):
    """일부만 불가여도 불가다 — [전송]이 있어도 누르지 않고 [취소]."""
    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao, texts=("전송 가능 1", "IR.pdf", "전송 불가 1",
                                            "나.pdf", "용량 초과"))]
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and result.error.startswith("file_refused")
    assert "용량 초과" in result.error
    assert kakao.clicks == ["취소"]


def test_an_unsendable_file_stops_the_message_too(ir_dir):
    """★ 자료가 막히면 문구도 안 나간다(`send_item`) — '자료 보내드렸습니다' 만 가지 않게."""
    from agent.main import send_item

    kakao = Kakao(str(ir_dir))
    kakao.appears = [sendable(kakao, texts=REFUSED, buttons=("확인",))]
    sent_texts = []
    kakao.send_text = lambda room, text, should_stop=None: (
        sent_texts.append(text) or kw.SendResult(ok=True))
    result = send_item(kakao, {"room_name": ROOM, "message": "자료 보내드립니다",
                               "files": ["IR.pdf"]}, {"part_gap_sec": 0})

    assert not result.ok
    assert sent_texts == []
    assert "문구도 보내지 않았습니다" in result.error and "비어있는 파일" in result.error


def test_unsendable_detail_reads_only_refusals():
    assert kw.unsendable_detail({"texts": ["전송 가능 1", "IR.pdf"],
                                 "buttons": ["취소", "전송"]}) is None
    assert kw.unsendable_detail({"title": "파일 전송", "texts": ["전송 불가 1"],
                                 "buttons": ["확인"]}) == "까닭을 읽지 못했습니다"


def test_confirm_is_never_a_send_button():
    """`전송 불가` 창의 [확인]은 닫기다 — 보내기로 치면 닫고서 '보냈다' 고 적는다."""
    assert kw._send_button({"buttons": ["확인"]}) == []
    assert kw._send_button({"buttons": ["OK"]}) == []
    assert kw._send_button({"buttons": ["1개 전송"]}) == ["1개 전송"]


def test_the_count_can_come_from_a_sendable_line():
    window = {"present": True, "title": "", "owner_title": ROOM,
              "buttons": ["취소", "전송"], "texts": ["전송 가능 1", "IR.pdf"], "rows": None}
    assert kw.check_confirm_window(window, ROOM, ["IR.pdf"]) is None
    window["texts"] = ["전송 가능 2", "IR.pdf"]
    assert "개수가 다릅니다" in kw.check_confirm_window(window, ROOM, ["IR.pdf"])


# ══════════════════════════════════════════════════════════════════════════
#  ④ 진단이 서버까지 간다
# ══════════════════════════════════════════════════════════════════════════

def test_the_dump_rides_on_the_diagnostics(monkeypatch):
    import agent.diagnose
    from agent.main import collect_diagnostics

    monkeypatch.setattr(agent.diagnose, "list_titles", lambda: ["카카오톡"])

    class Sender:
        name = "kakao_windows"
        ui_dump = ["[붙여넣기 직후] 앞 창 hwnd=200 '가나다 시험방'"]

    payload = collect_diagnostics(Sender(), "send_failed", error="x")
    assert payload["ui_dump"] == Sender.ui_dump
    assert "ui_dump" not in collect_diagnostics(object(), "startup")


def test_the_server_keeps_the_dump():
    """서버가 모르는 칸은 버린다(pydantic) — 칸이 없으면 진단이 조용히 사라진다."""
    from app.routers.agent_api import Diagnostics

    body = Diagnostics(kind="send_failed", ui_dump=["창 hwnd=500"])
    assert body.model_dump(exclude_none=True)["ui_dump"] == ["창 hwnd=500"]


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ 0바이트 파일은 카톡을 열기 전에 막는다
# ══════════════════════════════════════════════════════════════════════════

def test_an_empty_file_never_touches_kakaotalk(ir_dir):
    (ir_dir / "빈자료.pdf").write_bytes(b"")
    kakao = Kakao(str(ir_dir))
    result = kakao.send_file(ROOM, ["빈자료.pdf"])

    assert not result.ok
    assert "ir_file_rejected" in result.error
    assert "비어있는 파일(0바이트): 빈자료.pdf" in result.error
    assert kakao._pyautogui.keys == [] and kakao.clipboard is None


def test_the_empty_file_check_is_shared_with_mac(ir_dir):
    """빗장은 mac 과 같은 자리(`base.resolve_ir_file`)다 — 한쪽만 막히지 않게."""
    (ir_dir / "빈자료.pdf").write_bytes(b"")
    with pytest.raises(base.IrPathError, match="비어있는 파일"):
        base.resolve_ir_file("빈자료.pdf", str(ir_dir))
    assert base.resolve_ir_file("IR.pdf", str(ir_dir)).name == "IR.pdf"
