"""Windows 발송기가 **첨부 단추 → 열기 창 → 카톡 `파일 전송` 카드** 로 파일을 보내는 길 (0.11.12).

## 왜 이 길인가

실기(10/20): Windows 카톡은 **붙여넣기(Ctrl+V)로 파일을 받지 않는다.** 사람이 하는 그대로
채팅창 아래 줄의 첨부 단추(풍선 도움말 `파일전송 Ctrl+T`)를 누르면 Windows **열기** 창이
뜨고, 파일을 고르면 카톡이 채팅창 위에 **`파일 전송` 카드**를 띄운다:

    보낼 수 있으면   제목 `파일 전송` · [×] · `시험자료.pdf` `149KB` `⋮` · [1개 전송]
    0바이트 파일이면  제목 `파일 전송` · `전송 불가 1` · 파일명 · `비어있는 파일` · [확인]

## 이 파일이 지키는 것

    ① 첨부는 UIA 로 찾은 첨부 단추 하나 → 없으면 그 단축키(Ctrl+T). 좌표로 누르지 않는다
    ② 열기 창에 **전체 경로**를 넣고 되읽어 같을 때만 [열기]. 아니면 [취소]
    ③ 카드: 후보가 딱 하나 · 제목 `파일 전송` · [N개 전송] 하나 · N == 1 일 때만 누른다.
       파일명이 읽히면 같아야 하고, 못 읽으면 통과시키되 말을 남긴다
    ④ `전송 불가` 는 [확인]으로 닫고 까닭을 남긴다 — **문구도 안 나간다**
    ⑤ [중단]은 [열기] 앞에서 [취소], [1개 전송] 앞에서 [×]
    ⑥ 진단에는 카톡 창들과 그 속 컨트롤이 실린다(실기 확인 전에는 **성공해도**) —
       메인 창(대화 목록)의 속 · 열기 창의 파일 목록은 싣지 않는다
    ⑦ 0바이트 파일은 카톡을 열기 **전에** 막는다

창 · 컨트롤 · 키보드는 가짜로 대신한다. 창을 고르고 누르고 닫는 코드는 진짜다.
"""
from __future__ import annotations

import pytest

from agent.sender import base
from agent.sender import kakao_windows as kw
from tests.test_cancel_mid_item import FAST, FakeClient, agent_main, ir_item, ir_job  # noqa: F401

ROOM = "가나다 시험방"
MAIN, CHAT, NOTEPAD, OPEN, NOTICE, CARD, CARD2, OVERLAY = 100, 200, 300, 400, 401, 500, 501, 502
PID = 7
SECRET = "남의 이름 — 지난 대화"          # 메인 창(대화 목록)에만 있는 글자
PRIVATE_FILE = "남의사진_승차권.jpg"       # 열기 창의 파일 목록에만 있는 이름


class Node:
    """가짜 UIA 컨트롤. 우리가 부르는 것(`descendants` · 단추 누르기 · 칸 넣기)만 흉내낸다."""

    def __init__(self, ctype, name="", kids=(), *, aid="", on_click=None, on_set=None):
        self.control_type = ctype
        self.name = name
        self.class_name = ""
        self.rectangle = None
        self._aid = aid
        self._kids = list(kids)
        self.on_click = on_click
        self.on_set = on_set
        self.value = ""

    def automation_id(self):
        return self._aid

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

    invoke = click_input

    def set_edit_text(self, text):
        self.value = self.on_set(text) if self.on_set else text

    def get_value(self):
        return self.value


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
        if keys == ("ctrl", "t") and self.kakao.hotkey_opens:
            self.kakao.open_dialog()

    def press(self, key):
        self.keys.append(key)


class Kakao(kw.KakaoDesktopSender):
    """Win32 · UIA 를 부르는 맨 끝 자리만 가짜로 바꾼 Windows 발송기.

    `attach_button` — 채팅창 속 첨부 단추가 UIA 로 보이는가(아니면 Ctrl+T 로 간다).
    `card` — [열기] 뒤 뜰 카드의 모양(`card_shape`). None 이면 아무것도 안 뜬다.
    `file_missing` — [열기] 를 누르면 '파일을 찾을 수 없습니다' 알림이 뜨고 열기 창이 남는다.
    """

    def __init__(self, ir_root, *, card=None, attach_button=True, hotkey_opens=True,
                 opens=True, open_owner=CHAT, file_missing=False, edit_echo=None,
                 enabled=True):
        self.sel = {"timings": {"open_dialog_wait": 0, "confirm_wait": 0,
                                "after_confirm_click": 0, "after_close_chat": 0,
                                "room_search_poll": 0}}
        self.screenshot_dir = ""
        self.ir_root_setting = ir_root
        self.can_send_files = enabled
        self.windows = {MAIN: ("카카오톡", PID), CHAT: (ROOM, PID), NOTEPAD: ("메모장", 9)}
        self.classes = {OPEN: "#32770", NOTICE: "#32770"}
        self.owners = {}
        self.children = []
        self.clicks = []
        self.typed = []
        self.opened = []
        self.card = card
        self.hotkey_opens = hotkey_opens
        self.opens = opens
        self.open_owner = open_owner
        self.file_missing = file_missing
        self.edit_echo = edit_echo
        chat_kids = [Node("Edit", "메시지 입력"), Node("Button", "전송")]
        if attach_button:
            chat_kids.append(Node("Button", "파일전송 Ctrl+T", on_click=self._attach))
        self.chat = Node("Window", ROOM, chat_kids)
        self.chat.handle = CHAT
        self.trees = {MAIN: Node("Window", "카카오톡", [Node("ListItem", SECRET)]),
                      CHAT: self.chat}
        self._desktop = Desktop(self.trees)
        self._pyautogui = Keys(self)
        self.ui_dump = []

    # --- 카톡이 하는 일 ---
    def _attach(self, name):
        self.clicks.append(name)
        self.open_dialog()

    def open_dialog(self):
        if not self.opens:
            return
        edit = Node("Edit", "파일 이름(N):", aid="1148", on_set=self._typed)
        self.trees[OPEN] = Node("Window", "열기", [
            Node("List", "항목 보기", [Node("ListItem", PRIVATE_FILE)]),
            Node("ComboBox", "파일 이름(N):", [edit], aid="1148"),
            Node("SplitButton", "열기(O)", aid="1", on_click=self._press_open),
            Node("Button", "취소", aid="2", on_click=self._press_cancel),
        ])
        self.windows[OPEN] = ("열기", PID)
        self.owners[OPEN] = self.open_owner

    def _typed(self, text):
        self.typed.append(text)
        return self.edit_echo if self.edit_echo is not None else text

    def _press_open(self, name):
        self.clicks.append(name)
        if self.file_missing:
            self.windows[NOTICE] = ("열기", PID)
            self.owners[NOTICE] = OPEN
            self.trees[NOTICE] = Node("Window", "열기", [Node("Text", "파일을 찾을 수 없습니다")])
            return
        self.windows.pop(OPEN, None)
        if self.card is not None:
            for hwnd, title, owner, tree in self.card(self):
                self.windows[hwnd] = (title, PID)
                self.owners[hwnd] = owner
                self.trees[hwnd] = tree

    def _press_cancel(self, name):
        self.clicks.append(name)
        self.windows.pop(OPEN, None)

    def card_node(self, hwnd, title="", *, texts=("파일 전송", "IR.pdf", "149KB"),
                  buttons=("닫기", "1개 전송"), closes_on=None):
        """`closes_on` — 누르면 카드가 닫히는 단추들. None 이면 어느 단추든 닫힌다."""
        def _click(name):
            self.clicks.append(name)
            if closes_on is None or name in closes_on:
                self.windows.pop(hwnd, None)
        kids = [Node("Text", t) for t in texts]
        kids += [Node("Button", b, on_click=_click) for b in buttons]
        kids.append(Node("Button", "더보기", on_click=_click))      # `⋮` — 누르면 안 된다
        return Node("Window", title, kids)

    # --- Win32 ---
    def _top_windows(self):
        return dict(self.windows)

    def _owner_hwnd(self, hwnd):
        return self.owners.get(hwnd, 0)

    def _child_windows(self, hwnd):
        return []

    def _hwnd_class(self, hwnd):
        return self.classes.get(hwnd, "EVA_Window")

    def _window_pid(self, win):
        return PID

    def _foreground_hwnd(self):
        return CHAT

    def _foreground_title(self):
        return ROOM

    def _focus_verified(self, win, expect_title=None):
        return True

    def _hwnd_title(self, hwnd):
        return self.windows.get(hwnd, ("", 0))[0]

    def _is_window_visible(self, hwnd):
        return hwnd in self.windows

    def _post_close(self, hwnd):
        self.closed.append(hwnd)
        self.windows.pop(hwnd, None)

    closed: list

    # --- 방 · 실패 ---
    def _open_room_verified(self, room_name, should_stop=None):
        self.opened.append(room_name)
        self.closed = []
        return self.chat, None

    def _leave_room(self, chat, room_name):
        pass

    def _fail(self, room_name, error):
        return kw.SendResult(ok=False, error=error)

    @property
    def esc(self) -> bool:
        return "esc" in self._pyautogui.keys

    @property
    def sent(self) -> bool:
        return any(kw._match_buttons([c], kw.FILE_SEND_DEFAULTS["send_button_re"])
                   for c in self.clicks)

    @property
    def dump(self) -> str:
        return "\n".join(self.ui_dump)


def sendable(title="", owner=CHAT, **kw_):
    """[열기] 뒤 뜨는 보낼 수 있는 카드 — 채팅창이 띄운 새 창."""
    return lambda k: [(CARD, title, owner, k.card_node(CARD, title, **kw_))]


REFUSED = dict(texts=("파일 전송", "전송 불가 1", "IR.pdf", "비어있는 파일"),
               buttons=("확인",))


@pytest.fixture()
def ir_dir(tmp_path):
    docs = tmp_path / "자료"
    docs.mkdir()
    (docs / "IR.pdf").write_bytes(b"pretend pdf")
    return docs


# ══════════════════════════════════════════════════════════════════════════
#  ① ② ③ 끝까지 — 첨부 단추 → 열기 → [1개 전송]
# ══════════════════════════════════════════════════════════════════════════

def test_attach_button_open_dialog_and_card_send_the_file(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable())
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert result.warning is None
    assert kakao.clicks == ["파일전송 Ctrl+T", "열기(O)", "1개 전송"]
    assert kakao.typed == [str(ir_dir / "IR.pdf")], "열기 창에 전체 경로가 아니다"
    assert ("ctrl", "t") not in kakao._pyautogui.keys
    assert CARD not in kakao.windows and OPEN not in kakao.windows


def test_without_a_visible_attach_button_it_uses_the_shortcut(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable(), attach_button=False)
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert ("ctrl", "t") in kakao._pyautogui.keys
    assert kakao.clicks == ["열기(O)", "1개 전송"]


def test_a_card_titled_by_its_window_is_also_found(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable(title="파일 전송",
                                             texts=("IR.pdf", "149KB")))
    assert kakao.send_file(ROOM, ["IR.pdf"]).ok


def test_an_unreadable_file_name_passes_on_title_and_button_with_a_note(ir_dir):
    """카드가 파일명을 UIA 로 안 드러내도 — 제목 + [1개 전송] 하나면 보내고 말을 남긴다."""
    kakao = Kakao(str(ir_dir), card=sendable(texts=("파일 전송",)))
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert "파일명을" in result.warning and "1개 전송" in result.warning


def test_several_files_go_one_card_at_a_time(ir_dir):
    (ir_dir / "나.pdf").write_bytes(b"x")
    kakao = Kakao(str(ir_dir), card=lambda k: [(CARD, "", CHAT, k.card_node(
        CARD, texts=("파일 전송", k.typed[-1].split("/")[-1])))])
    result = kakao.send_file(ROOM, ["IR.pdf", "나.pdf"])

    assert result.ok, result.error
    assert kakao.clicks.count("1개 전송") == 2
    assert [t.split("/")[-1] for t in kakao.typed] == ["IR.pdf", "나.pdf"]


# ══════════════════════════════════════════════════════════════════════════
#  ③ 카드 관문 — 어긋나면 [×] 로 닫고 보내지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_a_count_that_is_not_one_is_refused_and_closed(ir_dir):
    """★ [2개 전송] — 남은 선택이 섞였다. 누르지 않고 [×]."""
    kakao = Kakao(str(ir_dir), card=sendable(buttons=("닫기", "2개 전송")))
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "개수가 다릅니다" in result.error
    assert "2개 전송" not in kakao.clicks and "더보기" not in kakao.clicks
    assert kakao.clicks[-1] == "닫기" and CARD not in kakao.windows


def test_another_file_on_the_card_is_refused(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable(texts=("파일 전송", "작년_내부자료.pdf")))
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "다른 파일" in result.error
    assert not kakao.sent


def test_a_card_without_a_close_button_is_closed_by_wm_close(ir_dir):
    """[×] 이 UIA 로 안 보이면 그 창에만 WM_CLOSE — `⋮` 는 누르지 않는다."""
    kakao = Kakao(str(ir_dir), card=sendable(buttons=("2개 전송",)))
    kakao.send_file(ROOM, ["IR.pdf"])

    assert kakao.closed == [CARD]
    assert "더보기" not in kakao.clicks and not kakao.sent


def test_a_send_click_that_leaves_the_card_open_is_cleaned_up(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable(closes_on=("닫기",)))
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert "send_unconfirmed" in result.error and "겹칠 수 있습니다" in result.error
    assert kakao.clicks[-2:] == ["1개 전송", "닫기"]


def test_two_candidates_are_refused(ir_dir):
    kakao = Kakao(str(ir_dir), card=lambda k: [
        (CARD, "", CHAT, k.card_node(CARD)), (CARD2, "", CHAT, k.card_node(CARD2))])
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "confirm_window_not_shown" in result.error
    assert not kakao.sent and kakao.esc
    assert f"hwnd={CARD} " in kakao.dump and f"hwnd={CARD2} " in kakao.dump


def test_an_empty_overlay_does_not_count_as_a_candidate(ir_dir):
    """카드 뒤 채팅창을 어둡게 덮는 창(속이 빈 새 창)은 후보가 아니다."""
    kakao = Kakao(str(ir_dir), card=lambda k: [
        (OVERLAY, "", CHAT, kw_node("Pane")), (CARD, "", CHAT, k.card_node(CARD))])
    assert kakao.send_file(ROOM, ["IR.pdf"]).ok


def kw_node(ctype):
    return Node(ctype)


def test_no_card_is_refused_with_diagnostics_and_cleanup(ir_dir, tmp_path):
    """★ [열기] 뒤 카드를 못 찾으면 안 보낸다(그 카드가 떠 있을 수 있다 — Esc)."""
    kakao = Kakao(str(ir_dir), card=None)
    kakao.screenshot_dir = str(tmp_path / "logs")
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "confirm_window_not_shown" in result.error
    assert kakao.esc
    assert "[열기 창 (첨부 단추(UIA))]" in kakao.dump
    assert "[실패: confirm_window_not_shown]" in kakao.dump
    assert "메시지 입력" in kakao.dump, "채팅창 속 컨트롤이 진단에 없다"
    assert "'카카오톡'" in kakao.dump, "메인 창 줄은 있어야 한다"
    assert SECRET not in kakao.dump, "메인 창(대화 목록)의 속까지 실었다"
    assert "메모장" not in kakao.dump, "카톡이 아닌 창을 실었다"
    saved = (tmp_path / "logs" / kw.UIA_FILE_DUMP_FILE).read_text(encoding="utf-8")
    assert "[실패: confirm_window_not_shown]" in saved


# ══════════════════════════════════════════════════════════════════════════
#  ② 열기 창 — 어긋나면 [취소]
# ══════════════════════════════════════════════════════════════════════════

def test_no_open_dialog_fails_and_cleans_up(ir_dir):
    kakao = Kakao(str(ir_dir), opens=False)
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "open_dialog_not_shown" in result.error
    assert ("ctrl", "t") in kakao._pyautogui.keys, "단추가 안 먹으면 단축키도 해 봐야 한다"
    assert kakao.esc
    assert "[실패: open_dialog_not_shown]" in kakao.dump


def test_a_file_the_dialog_cannot_find_is_canceled(ir_dir):
    """[열기] 뒤 '파일을 찾을 수 없습니다' — 알림을 닫고 [취소]. 아무것도 안 나간다."""
    kakao = Kakao(str(ir_dir), card=sendable(), file_missing=True)
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "open_dialog_stuck" in result.error
    assert NOTICE in kakao.closed and kakao.clicks[-1] == "취소"
    assert OPEN not in kakao.windows and not kakao.sent
    assert "파일을 찾을 수 없습니다" in kakao.dump


def test_a_path_that_does_not_read_back_is_not_opened(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable(), edit_echo="C:\\다른\\곳.pdf")
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "file_name_not_set" in result.error
    assert "열기(O)" not in kakao.clicks and kakao.clicks[-1] == "취소"


def test_an_open_dialog_from_another_window_is_canceled(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable(), open_owner=MAIN)
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and "open_dialog_foreign" in result.error
    assert kakao.typed == [] and kakao.clicks[-1] == "취소"


def test_the_open_dialog_dump_leaves_out_the_file_list(ir_dir):
    """열기 창의 파일 목록(폴더 · 남의 파일 이름)은 진단에 싣지 않는다 — 칸과 단추만."""
    kakao = Kakao(str(ir_dir), card=sendable())
    kakao.send_file(ROOM, ["IR.pdf"])

    assert "열기(O)" in kakao.dump and "파일 이름(N):" in kakao.dump
    assert PRIVATE_FILE not in kakao.dump


# ══════════════════════════════════════════════════════════════════════════
#  ④ `전송 불가`
# ══════════════════════════════════════════════════════════════════════════

def test_an_unsendable_card_is_dismissed_with_its_reason(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable(**REFUSED))
    result = kakao.send_file(ROOM, ["IR.pdf"])

    assert not result.ok and result.error.startswith("file_refused")
    assert "IR.pdf · 비어있는 파일" in result.error
    assert kakao.clicks[-1] == "확인" and CARD not in kakao.windows


def test_an_unsendable_file_stops_the_message_too(ir_dir):
    """★ 자료가 막히면 문구도 안 나간다(`send_item`) — '자료 보내드렸습니다' 만 가지 않게."""
    from agent.main import send_item

    kakao = Kakao(str(ir_dir), card=sendable(**REFUSED))
    texts = []
    kakao.send_text = lambda room, text, should_stop=None: (
        texts.append(text) or kw.SendResult(ok=True))
    result = send_item(kakao, {"room_name": ROOM, "message": "자료 보내드립니다",
                               "files": ["IR.pdf"]}, {"part_gap_sec": 0})

    assert not result.ok and texts == []
    assert "자료 파일을 보내지 못해 문구도 보내지 않았습니다" in result.error
    assert "**" not in result.error, "화면에 별표가 글자로 보인다"


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ [중단]
# ══════════════════════════════════════════════════════════════════════════

def test_stop_before_the_first_file_touches_nothing(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable())
    result = kakao.send_file(ROOM, ["IR.pdf"], should_stop=lambda: True)

    assert not result.ok and result.stopped == 0
    assert kakao.clicks == [] and kakao._pyautogui.keys == []


def test_stop_at_the_open_dialog_cancels_it(ir_dir):
    """열기 창까지 왔다가 [중단] — [열기] 대신 [취소]. 경로도 넣지 않는다."""
    kakao = Kakao(str(ir_dir), card=sendable())
    answers = iter([False, True])
    result = kakao.send_file(ROOM, ["IR.pdf"], should_stop=lambda: next(answers))

    assert not result.ok and result.stopped == 0
    assert kakao.clicks == ["파일전송 Ctrl+T", "취소"] and kakao.typed == []
    assert OPEN not in kakao.windows


def test_stop_at_the_card_closes_it(ir_dir):
    """카드까지 왔다가 [중단] — [1개 전송] 대신 [×]."""
    kakao = Kakao(str(ir_dir), card=sendable())
    answers = iter([False, False, True])
    result = kakao.send_file(ROOM, ["IR.pdf"], should_stop=lambda: next(answers))

    assert not result.ok and result.stopped == 0
    assert kakao.clicks[-1] == "닫기" and not kakao.sent
    assert CARD not in kakao.windows


def test_stop_between_files_sends_no_more(ir_dir):
    """파일마다 세 번 묻는다(첨부 앞 · [열기] 앞 · [1개 전송] 앞) — 둘째 앞이면 하나만."""
    kakao = Kakao(str(ir_dir), card=sendable())
    answers = iter([False, False, False, True])
    result = kakao.send_file(ROOM, ["IR.pdf", "IR.pdf"], should_stop=lambda: next(answers))

    assert not result.ok and result.stopped == 1
    assert kakao.clicks.count("1개 전송") == 1


# ══════════════════════════════════════════════════════════════════════════
#  ⑥ 진단이 서버까지 간다 — 성공해도
# ══════════════════════════════════════════════════════════════════════════

def test_a_successful_send_still_reports_the_dump_while_unverified(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable())
    assert kakao.send_file(ROOM, ["IR.pdf"]).ok
    assert "[열기 창 (첨부 단추(UIA))]" in kakao.dump and "[파일 전송 창]" in kakao.dump


def test_a_verified_success_keeps_quiet(ir_dir):
    kakao = Kakao(str(ir_dir), card=sendable())
    kakao.sel["file_send"] = {"verified": True}
    assert kakao.send_file(ROOM, ["IR.pdf"]).ok
    assert kakao.ui_dump == []


def test_the_job_loop_uploads_the_dump_after_a_clean_send(agent_main):  # noqa: F811
    class Sent:
        name = "test"
        ui_dump = []

        def send_file(self, room, files, should_stop=None):
            self.ui_dump = ["[파일 전송 창] …"]
            return kw.SendResult(ok=True)

        def send_text(self, room, text, should_stop=None):
            return kw.SendResult(ok=True)     # 문구가 진단을 지우지 않는다

    client = FakeClient()
    agent_main.process_job(client, Sent(), ir_job(ir_item(files=["가.pdf"])), FAST)

    assert client.items == [(1, "sent", None)]
    assert client.diags == [{"kind": "file_sent", "target_room": ROOM, "error": None}]


def test_the_dump_rides_on_the_diagnostics_once(monkeypatch):
    import agent.diagnose
    from agent.main import collect_diagnostics

    monkeypatch.setattr(agent.diagnose, "list_titles", lambda: ["카카오톡"])

    class Sender:
        name = "kakao_windows"
        ui_dump = ["[파일 전송 창] 앞 창 hwnd=200"]

    sender = Sender()
    assert collect_diagnostics(sender, "send_failed")["ui_dump"] == Sender.ui_dump
    assert "ui_dump" not in collect_diagnostics(sender, "send_failed"), "두 번 실렸다"


def test_the_server_keeps_the_dump():
    """서버가 모르는 칸은 버린다(pydantic) — 칸이 없으면 진단이 조용히 사라진다."""
    from app.routers.agent_api import Diagnostics

    body = Diagnostics(kind="file_sent", ui_dump=["창 hwnd=500"])
    assert body.model_dump(exclude_none=True)["ui_dump"] == ["창 hwnd=500"]


def test_list_contents_are_cut_from_entries():
    entries = [{"control_type": "Window", "depth": 0}, {"control_type": "List", "depth": 1},
               {"control_type": "ListItem", "name": PRIVATE_FILE, "depth": 2},
               {"control_type": "Edit", "depth": 1}]
    assert [e["control_type"] for e in kw.without_lists(entries)] == ["Window", "List", "Edit"]


# ══════════════════════════════════════════════════════════════════════════
#  관문 검사 자체 (창 없이 그대로)
# ══════════════════════════════════════════════════════════════════════════

def card(texts=("파일 전송", "IR.pdf"), buttons=("1개 전송",), title=""):
    return {"present": True, "hwnd": CARD, "title": title,
            "texts": list(texts) + list(buttons), "buttons": list(buttons)}


def test_the_gate_passes_the_real_card():
    assert kw.check_file_card(card(), ["IR.pdf"]) == (None, "")


@pytest.mark.parametrize("button, ok", [("1개 전송", True), (" 1 개  전송 ", True),
                                        ("2개 전송", False), ("전송", False),
                                        ("확인", False), ("1개 보내기", False)])
def test_the_send_button_must_carry_the_right_count(button, ok):
    reason, _note = kw.check_file_card(card(buttons=(button,)), ["IR.pdf"])
    assert (reason is None) is ok, reason


def test_the_gate_refuses_two_send_buttons_or_none():
    assert "2개" in kw.check_file_card(card(buttons=("1개 전송", "1개 전송")), ["IR.pdf"])[0]
    assert "0개" in kw.check_file_card(card(buttons=("닫기",)), ["IR.pdf"])[0]


def test_the_gate_wants_the_title():
    assert "'파일 전송' 창이 아닙니다" in kw.check_file_card(
        card(texts=("IR.pdf",)), ["IR.pdf"])[0]


def test_the_gate_accepts_a_full_path_and_the_other_hangul_form():
    import unicodedata

    assert kw.check_file_card(card(texts=("파일 전송", r"C:\자료\IR.pdf")), ["IR.pdf"])[0] is None
    name = unicodedata.normalize("NFC", "가나다_회사소개.pdf")
    other = unicodedata.normalize("NFD", name)
    assert kw.check_file_card(card(texts=("파일 전송", name)), [other])[0] is None


@pytest.mark.parametrize("blanked", ["confirm_title_re", "send_button_re"])
def test_a_blanked_selector_blocks_instead_of_matching_anything(blanked):
    """빈 정규식은 어떤 글자에나 걸린다 — 비면 판단 불가로 본다(막는다)."""
    assert kw.check_file_card(card(), ["IR.pdf"], {blanked: ""})[0]


def test_the_selector_file_is_where_a_different_card_is_fixed():
    """실기에서 카드가 다르면 **코드가 아니라 selectors.yaml 을 고친다.**"""
    other = card(texts=("첨부 확인", "IR.pdf"), buttons=("보냅니다 1",))
    assert kw.check_file_card(other, ["IR.pdf"])[0], "기본값으로는 못 읽는다"
    conf = {"confirm_title_re": "첨부 확인", "send_button_re": r"^보냅니다 (\d+)$"}
    assert kw.check_file_card(other, ["IR.pdf"], conf)[0] is None


def test_unsendable_detail_reads_only_refusals():
    assert kw.unsendable_detail(card()) is None
    assert kw.unsendable_detail({"title": "파일 전송", "texts": ["전송 불가 1"],
                                 "buttons": ["확인"]}) == "까닭을 읽지 못했습니다"


# ══════════════════════════════════════════════════════════════════════════
#  ⑦ 0바이트 파일은 카톡을 열기 전에 막는다
# ══════════════════════════════════════════════════════════════════════════

def test_an_empty_file_never_touches_kakaotalk(ir_dir):
    (ir_dir / "빈자료.pdf").write_bytes(b"")
    kakao = Kakao(str(ir_dir), card=sendable())
    result = kakao.send_file(ROOM, ["빈자료.pdf"])

    assert not result.ok
    assert "ir_file_rejected" in result.error
    assert "비어있는 파일(0바이트): 빈자료.pdf" in result.error
    assert kakao.opened == [] and kakao._pyautogui.keys == []


def test_the_empty_file_check_is_shared_with_mac(ir_dir):
    """빗장은 mac 과 같은 자리(`base.resolve_ir_file`)다 — 한쪽만 막히지 않게."""
    (ir_dir / "빈자료.pdf").write_bytes(b"")
    with pytest.raises(base.IrPathError, match="비어있는 파일"):
        base.resolve_ir_file("빈자료.pdf", str(ir_dir))
    assert base.resolve_ir_file("IR.pdf", str(ir_dir)).name == "IR.pdf"
