"""Windows 발송기가 자료 파일을 붙여 보낼 때 **카톡을 건드리기 전에** 무엇이 막아 주는가.

## 이 파일이 지키는 것

파일명은 웹 화면에서 들어와 서버 DB 에 저장되고 여러 PC 가 함께 쓰는 값이다 — 화면에
친 글자가 그대로 경로가 된다. 그래서 mac 과 **같은 빗장**(`base.resolve_ir_file`)을
지나지 못하면 방을 열지도 않는다. 그리고 실기 확인 전에는 **꺼져 있다**
(`can_send_files` · `file_send.verified`).

카톡을 건드리는 길(첨부 단추 → 열기 창 → `파일 전송` 카드)과 그 관문은
`tests/test_win_file_confirm.py` 에 있다 — 여기서는 그 흉내(`Kakao`)를 빌려 쓴다.
"""
from __future__ import annotations

import pathlib

import pytest

from agent.sender import base  # noqa: E402
from agent.sender import kakao_windows as kw  # noqa: E402
from tests.test_win_file_confirm import Kakao

ROOM = "테스트 딜 공유방"


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
    win = Kakao(str(ir_dir))
    result = win.send_file(ROOM, [evil])

    assert not result.ok
    assert win.opened == [], "거절할 값인데 방을 열었다"
    assert win.clicks == [] and win._pyautogui.keys == []
    assert "ir_file_rejected" in result.error


def test_the_sibling_secret_never_resolves(ir_dir):
    """★ 형제 폴더의 비밀 파일은 **실제로 있는데도** 나가지 않는다."""
    secret = ir_dir.parent / "backup-keys" / "private_key"
    assert secret.is_file(), "시험 자체가 헛돌지 않게 실제로 있어야 한다"

    win = Kakao(str(ir_dir))
    result = win.send_file(ROOM, ["../backup-keys/private_key"])

    assert not result.ok
    assert win.opened == []
    assert "ir_file_rejected" in result.error


def test_a_missing_file_never_touches_kakaotalk(ir_dir):
    """파일명은 함께 쓰지만 실물은 그 PC 에만 있다 — 없으면 분명히 실패한다."""
    win = Kakao(str(ir_dir))
    result = win.send_file(ROOM, ["없는자료.pdf"])

    assert not result.ok
    assert win.opened == []
    assert "이 PC 에" in result.error


def test_nothing_to_send_is_not_a_success(ir_dir):
    win = Kakao(str(ir_dir))
    assert not win.send_file(ROOM, []).ok
    assert win.opened == []


def test_no_ir_folder_set_fails_before_kakaotalk(ir_dir):
    """자료 폴더를 안 넣었으면 **카톡을 건드리기 전에** 실패한다."""
    win = Kakao("")
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
    win = Kakao(str(ir_dir), enabled=False)
    result = win.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert base.FILE_SEND_UNSUPPORTED in result.error
    assert win.opened == [] and win._pyautogui.keys == []


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


def test_the_paste_path_is_gone():
    """Windows 카톡은 붙여넣기로 파일을 받지 않는다(실기) — 그 길과 클립보드 모듈은 뺐다."""
    from app.routers.setup import AGENT_FILES

    source = pathlib.Path(kw.__file__).read_text(encoding="utf-8")
    assert "win_clipboard" not in source
    assert not any("win_clipboard" in src for src, _dest in AGENT_FILES)
