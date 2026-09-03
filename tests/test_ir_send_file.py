"""IR 자료를 카톡으로 붙여 보낼 때 **무엇이 막아 주는가.**

## 이 파일이 지키는 것

자료 파일은 한 번 나가면 되돌릴 수 없다. 게다가 보낸 뒤에는 파일 메시지 줄에
파일명이 AX 로 **안 나온다** — "잘못 보냈다" 를 사후에 알아낼 방법이 없다.
그래서 나가기 직전의 **"파일 전송" 확인 시트가 유일한 진짜 관문**이다.

관문이 실제로 막는지를 여기서 못박는다. 방 제목이 다를 때 · 파일명이 다를 때 ·
개수가 다를 때 **취소를 누르고 아무것도 보내지 않아야 한다.** 이 파일에서 제일
중요한 검사다.

카톡 AX 는 흉내(가짜)로 대신한다. 실기 흐름은 이미 확인됐고, 여기서 볼 것은
"어긋난 것을 보면 손을 떼는가" 이지 AppleScript 가 도는가가 아니다.
"""
from __future__ import annotations

import pytest

kakao_mac = pytest.importorskip("agent.sender.kakao_mac")
from agent.sender import base  # noqa: E402


ROOM = "테스트 딜 공유방"
SEND_BUTTON = kakao_mac.SEND_BUTTON_FMT.format(n=1)


def confirm_sheet(*, room=ROOM, files=("IR.pdf",), count=None, rows=None):
    """실기에서 읽은 그대로의 확인 시트 스냅샷.

        [AXScrollArea → AXTable]     (파일 목록)
        [AXButton] [취소]
        [AXButton] [1개 전송]         ← 개수가 단추 이름에 박혀 있다
        [AXStaticText] [파일 전송]
    """
    n = len(files) if count is None else count
    texts = [kakao_mac.CONFIRM_TITLE]
    for name in files:
        texts += [name, "34.0bytes"]
    return {
        "present": True,
        "front_title": room,
        "identifier": "",
        "buttons": [kakao_mac.CANCEL_BUTTON, kakao_mac.SEND_BUTTON_FMT.format(n=n)],
        "texts": texts,
        "rows": len(files) if rows is None else rows,
    }


class FakeMac(kakao_mac.KakaoMacSender):
    """AX 를 흉내낸 발송기. **어떤 단추를 눌렀는지**만 기록한다.

    실제로 눌린 단추가 `취소` 인지 `1개 전송` 인지가 이 파일의 전부다.
    """

    def __init__(self, confirm, *, room=ROOM, ir_root="", rows=(55, 56)):
        super().__init__({
            "ir_root": ir_root,
            "close_after_send": False,
            # 가짜라 기다릴 것이 없다. 검사를 빨리 끝낸다.
            "file_panel_timeout": 0.3,
            "file_confirm_timeout": 0.3,
            "file_confirm_quick": 0.05,
            "file_sent_timeout": 0.3,
        })
        self.confirm = confirm
        self.room = room
        self.rows = rows
        self.phase = "idle"
        self.clicked: list = []
        self.goto: list = []

    # --- 카톡을 건드리는 자리를 전부 가짜로 -------------------------------
    def _ensure_room_front(self, room_name):
        return None

    def _chat_rows(self, room_name):
        return self.rows[1] if self.phase == "sent" else self.rows[0]

    def _click_file_button(self, room_name):
        self.clicked.append("파일전송")
        self.phase = "panel"
        return True

    def _sheet_snapshot(self, room_name):
        if self.phase == "panel":
            return {"present": True, "front_title": self.room,
                    "identifier": kakao_mac.OPEN_PANEL_ID,
                    "buttons": [kakao_mac.CANCEL_BUTTON, kakao_mac.OPEN_BUTTON_NAME],
                    "texts": [], "rows": None}
        if self.phase == "confirm":
            return dict(self.confirm)
        return {"present": False, "front_title": self.room, "identifier": "",
                "buttons": [], "texts": [], "rows": None}

    def _panel_goto(self, room_name, path):
        self.goto.append(path)
        return True

    def _click_open_button(self, room_name):
        self.clicked.append(kakao_mac.OPEN_BUTTON_NAME)
        self.phase = "confirm"
        return True

    def _click_sheet_button(self, room_name, name):
        self.clicked.append(name)
        self.phase = "sent" if kakao_mac.COUNT_BUTTON_RE.match(name) else "idle"
        return True

    def _keystroke(self, key, *, cmd=False):
        pass

    # 편의
    @property
    def sent(self) -> bool:
        """전송 단추(`N개 전송`)를 실제로 눌렀는가."""
        return any(kakao_mac.COUNT_BUTTON_RE.match(c) for c in self.clicked)

    @property
    def canceled(self) -> bool:
        return kakao_mac.CANCEL_BUTTON in self.clicked


@pytest.fixture()
def ir_dir(tmp_path):
    """사람이 웹에서 넣은 IR 자료 폴더 + **그 형제 자리에 놓인 비밀 폴더.**

    실제 PC 에서 자료 폴더 바로 옆에 서버 접속 열쇠가 든 폴더가 놓여 있었다.
    파일명이 `../그폴더/그파일` 이면 그 열쇠가 투자사 카톡방으로 나간다.
    같은 모양을 가짜 이름으로 세워 두고 정말 막히는지 본다.
    """
    share = tmp_path / "Share"
    docs = share / "자료폴더"
    docs.mkdir(parents=True)
    (docs / "IR.pdf").write_bytes(b"pretend pdf")

    secrets = share / "backup-keys"          # ← 형제 자리 (가짜 이름)
    secrets.mkdir()
    (secrets / "private_key").write_text("SECRET")

    # 이름이 자료 폴더로 시작하는 형제 — `startswith` 로 막으면 여기서 샌다.
    lookalike = share / "자료폴더-딴것"
    lookalike.mkdir()
    (lookalike / "남의자료.pdf").write_text("nope")
    return docs


# ══════════════════════════════════════════════════════════════════════════
#  ★ 관문 — 어긋나면 취소하고 보내지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_it_sends_when_everything_matches(ir_dir):
    """전부 맞으면 보낸다 — 관문이 늘 막기만 하면 쓸모가 없다."""
    mac = FakeMac(confirm_sheet(files=("IR.pdf",)), ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["IR.pdf"])

    assert result.ok, result.error
    assert mac.sent
    assert not mac.canceled


def test_a_different_room_is_canceled_not_sent(ir_dir):
    """★ 방이 다르면 **취소**. 파일을 고르는 사이 다른 창이 앞으로 올 수 있다."""
    sheet = confirm_sheet(room="남의 회사 단체방", files=("IR.pdf",))
    mac = FakeMac(sheet, ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not mac.sent, "방이 다른데 보냈다"
    assert mac.canceled, "취소를 누르지 않았다"
    assert "방이 다릅니다" in result.error


def test_a_different_file_is_canceled_not_sent(ir_dir):
    """★ 시트에 뜬 파일명이 보내려던 것과 다르면 **취소**.

    패널이 마지막 위치를 기억해서 엉뚱한 파일이 잡히는 것이 실제 위험이다.
    """
    sheet = confirm_sheet(files=("작년_내부자료.pdf",))
    mac = FakeMac(sheet, ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not mac.sent, "다른 파일인데 보냈다"
    assert mac.canceled
    assert "시트에 없는 파일" in result.error


def test_a_different_count_is_canceled_not_sent(ir_dir):
    """★ 개수 단추의 숫자가 다르면 **취소**. 남은 선택이 섞여 들어온 경우다."""
    sheet = confirm_sheet(files=("IR.pdf",), count=3, rows=3)
    mac = FakeMac(sheet, ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not mac.sent, "개수가 다른데 보냈다"
    assert mac.canceled
    assert "개수가 다릅니다" in result.error


def test_no_confirm_sheet_means_nothing_is_sent(ir_dir):
    """확인 시트가 안 뜨면 **아무것도 보내지 않는다.**"""
    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    mac._click_open_button = lambda room: True          # 눌렀는데 시트가 안 뜬다
    result = mac.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not mac.sent
    assert "confirm_sheet_not_shown" in result.error


def test_an_unreadable_file_list_is_not_trusted(ir_dir):
    """표를 못 읽었으면 통과시키지 않는다 — 못 읽는 것과 맞는 것은 다르다."""
    sheet = confirm_sheet(files=("IR.pdf",))
    sheet["rows"] = None
    mac = FakeMac(sheet, ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert not mac.sent
    assert mac.canceled


def test_the_gate_is_checked_before_the_send_button(ir_dir):
    """관문이 막으면 전송 단추는 **아예 눌리지 않는다.**"""
    mac = FakeMac(confirm_sheet(files=("남의자료.pdf",)), ir_root=str(ir_dir))
    mac.send_file(ROOM, ["IR.pdf"])

    assert SEND_BUTTON not in mac.clicked


# --- 관문 검사 자체 (AX 없이 그대로) ---------------------------------------

def test_gate_passes_only_on_an_exact_match():
    assert kakao_mac.check_confirm_sheet(confirm_sheet(), ROOM, ["IR.pdf"]) is None


@pytest.mark.parametrize("snapshot, want", [
    (None, "확인 시트가 없습니다"),
    ({"present": False}, "확인 시트가 없습니다"),
])
def test_gate_refuses_when_there_is_no_sheet(snapshot, want):
    assert want in kakao_mac.check_confirm_sheet(snapshot, ROOM, ["IR.pdf"])


def test_gate_refuses_the_open_panel_itself():
    """열기 패널에도 `취소` 는 있다. 개수 단추가 없으면 확인 시트가 아니다."""
    panel = {"present": True, "front_title": ROOM,
             "identifier": kakao_mac.OPEN_PANEL_ID,
             "buttons": [kakao_mac.CANCEL_BUTTON, kakao_mac.OPEN_BUTTON_NAME],
             "texts": [], "rows": None}
    assert kakao_mac.check_confirm_sheet(panel, ROOM, ["IR.pdf"])
    assert not kakao_mac._is_confirm_sheet(panel)
    assert kakao_mac._is_open_panel(panel)


def test_gate_refuses_two_count_buttons():
    """개수 단추가 둘이면 어느 쪽인지 알 수 없다 — 고르지 않는다."""
    sheet = confirm_sheet()
    sheet["buttons"].append("2개 전송")
    assert "여러 개" in kakao_mac.check_confirm_sheet(sheet, ROOM, ["IR.pdf"])


def test_gate_handles_more_than_one_file():
    """개수 검사는 일반적으로 다룬다 — 나중에 여러 개를 한 번에 붙여도 그대로 쓴다."""
    sheet = confirm_sheet(files=("가.pdf", "나.pdf"))
    assert kakao_mac.check_confirm_sheet(sheet, ROOM, ["가.pdf", "나.pdf"]) is None
    assert kakao_mac.check_confirm_sheet(sheet, ROOM, ["가.pdf"])


def test_snapshot_parsing_keeps_one_button_per_name():
    """같은 단추가 두 겹으로 잡혀도 '개수 단추가 여러 개' 로 읽히면 안 된다."""
    raw = ("FRONT\t방\nPRESENT\nIDENT\tx\nBTN\t취소\nBTN\t1개 전송\n"
           "BTN\t1개 전송\nTXT\tIR.pdf\nROWS\t1")
    snapshot = kakao_mac.parse_sheet_snapshot(raw)
    assert snapshot["buttons"] == ["취소", "1개 전송"]
    assert snapshot["rows"] == 1
    assert snapshot["front_title"] == "방"
    assert snapshot["present"] is True


# ══════════════════════════════════════════════════════════════════════════
#  파일명 — 서버가 들고 함께 쓰는 값이라 더 조인다
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("evil", [
    "../../../etc/passwd",
    "../secrets.txt",
    "/etc/passwd",
    "sub/dir/IR.pdf",
    "..",
    "",
    "   ",
])
def test_a_name_that_leaves_the_folder_is_refused(ir_dir, evil):
    """★ 파일명만 받는다. 경로가 섞이면 공통 폴더 밖 파일이 나갈 수 있다."""
    with pytest.raises(base.IrPathError):
        base.resolve_ir_file(evil, str(ir_dir))


@pytest.mark.parametrize("url", [
    "https://drive.google.com/file/d/abc/view",
    "http://example.com/a.pdf",
])
def test_an_old_drive_link_is_not_read_as_a_file_name(ir_dir, url):
    """★ 저 칸에는 폐기된 드라이브 링크가 아직 남아 있다(실측 3건).

    그것을 파일명으로 읽으면 엉뚱한 짓을 한다. 주소는 파일명이 아니다.
    """
    with pytest.raises(base.IrPathError) as exc:
        base.resolve_ir_file(url, str(ir_dir))
    assert "주소는 파일명이 아닙니다" in str(exc.value)


def test_a_file_this_pc_does_not_have_fails_loudly(ir_dir):
    """★ 파일명은 함께 쓰지만 실물은 그 PC 에만 있다.

    없으면 **분명히 실패**해야 한다 — 조용히 아무것도 안 보내고 성공으로
    보고하는 것이 제일 나쁘다.
    """
    with pytest.raises(base.IrFileMissing) as exc:
        base.resolve_ir_file("없는자료.pdf", str(ir_dir))
    assert "이 PC 에" in str(exc.value)


def test_a_rejected_name_never_touches_kakaotalk(ir_dir):
    """규칙에 어긋나면 **카톡을 열지도 않는다.** 반쯤 하다 막히면 되돌릴 수 없다."""
    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["../../etc/passwd"])

    assert not result.ok
    assert mac.clicked == [], "거절할 값인데 카톡을 건드렸다"
    assert "ir_file_rejected" in result.error


def test_a_missing_file_never_touches_kakaotalk(ir_dir):
    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["없는자료.pdf"])

    assert not result.ok
    assert mac.clicked == []
    assert "이 PC 에" in result.error


def test_nothing_to_send_is_not_a_success(ir_dir):
    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    assert not mac.send_file(ROOM, []).ok


def test_the_full_path_is_typed_every_time(ir_dir):
    """열기 패널은 마지막 위치를 기억한다 → 경로를 **매번** 명시한다."""
    mac = FakeMac(confirm_sheet(files=("IR.pdf",)), ir_root=str(ir_dir))
    mac.send_file(ROOM, ["IR.pdf"])

    assert len(mac.goto) == 1
    assert mac.goto[0] == str(ir_dir / "IR.pdf")


# ══════════════════════════════════════════════════════════════════════════
#  ★★ 폴더 밖으로 못 나간다 — 빗장 두 겹 ★★
#
#  파일명은 웹 화면에서 들어와 서버 DB 에 저장되고 여러 PC 가 함께 쓰는 값이다.
#  즉 화면에 친 글자가 그대로 경로가 된다. 자료 폴더 형제 자리에 서버 접속
#  열쇠가 놓여 있으면 `../그폴더/그파일` 한 줄로 그것이 투자사 방에 나간다.
#  관문 검사와 함께 이 파일에서 제일 중요한 축이다.
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("evil", [
    "../backup-keys/private_key",       # ★ 형제 폴더의 비밀 파일
    "../../backup-keys/private_key",
    "../자료폴더-딴것/남의자료.pdf",      # 이름이 자료 폴더로 시작하는 형제
    "..",
    "../",
    "subdir/IR.pdf",
    "/etc/passwd",                      # 절대경로
    "\\\\서버\\몫\\IR.pdf",              # 윈도 UNC
    ".hidden",                          # 숨김 파일
    ".",
    "",
    "   ",
])
def test_a_name_that_leaves_the_folder_is_refused(ir_dir, evil):
    """★ 빗장 ① — 파일명 하나만 받는다. 경로가 섞이면 거부."""
    with pytest.raises(base.IrPathError):
        base.resolve_ir_file(evil, str(ir_dir))


def test_the_sibling_secret_never_resolves(ir_dir):
    """★ 형제 폴더의 비밀 파일은 **실제로 있는데도** 나가지 않는다.

    '파일이 없어서' 막힌 것이 아님을 못박는다 — 파일은 거기 실제로 있다.
    """
    secret = ir_dir.parent / "backup-keys" / "private_key"
    assert secret.is_file(), "시험 자체가 헛돌지 않게 실제로 있어야 한다"

    with pytest.raises(base.IrPathError) as exc:
        base.resolve_ir_file("../backup-keys/private_key", str(ir_dir))
    assert not isinstance(exc.value, base.IrFileMissing)


def test_a_symlink_pointing_out_is_refused(ir_dir):
    """★ 빗장 ② — 폴더 **안**에 밖을 가리키는 링크가 있어도 막는다.

    이름 검사만으로는 통과한다(`link.pdf` 는 멀쩡한 파일명이다).
    `resolve()` 로 링크를 푼 뒤 부모 관계를 봐야 걸린다.
    """
    secret = ir_dir.parent / "backup-keys" / "private_key"
    (ir_dir / "link.pdf").symlink_to(secret)

    assert base.check_ir_file_name("link.pdf") == "link.pdf"   # ①은 통과한다
    with pytest.raises(base.IrPathError):
        base.resolve_ir_file("link.pdf", str(ir_dir))


def test_a_broad_root_is_still_safe(tmp_path):
    """★ 폴더 자리를 넓게 잡아도 **파일명 빗장만으로** 밖으로 못 나간다.

    자리는 사람이 웹에서 넣는 값이라 `~/Share` 처럼 넓게 잡힐 수 있다.
    그래도 이름에 구분자가 못 들어가므로 그 아래를 벗어나지 못한다.
    """
    wide = tmp_path / "Share"
    (wide / "안쪽").mkdir(parents=True)
    (wide / "안쪽" / "비밀.txt").write_text("x")

    with pytest.raises(base.IrPathError):
        base.resolve_ir_file("안쪽/비밀.txt", str(wide))


def test_containment_is_not_a_string_prefix(ir_dir):
    """`…/자료폴더-딴것` 은 `…/자료폴더` 로 **시작한다.**

    앞부분 문자열 비교로 때우면 여기서 샌다 — 부모 관계로 봐야 한다.
    """
    lookalike = ir_dir.parent / "자료폴더-딴것"
    assert str(lookalike).startswith(str(ir_dir)), "시험이 노리는 모양이 맞는지"
    with pytest.raises(base.IrPathError):
        base.resolve_ir_file("../자료폴더-딴것/남의자료.pdf", str(ir_dir))


@pytest.mark.parametrize("url", [
    "https://drive.example.com/file/d/abc/view",
    "http://example.com/a.pdf",
])
def test_an_old_drive_link_is_not_read_as_a_file_name(ir_dir, url):
    """★ 자료 칸에는 폐기된 드라이브 링크가 아직 남아 있다(실측 3건).

    그것을 파일명으로 읽으면 엉뚱한 짓을 한다. 주소는 파일명이 아니다.
    """
    with pytest.raises(base.IrPathError) as exc:
        base.resolve_ir_file(url, str(ir_dir))
    assert "주소는 파일명이 아닙니다" in str(exc.value)


def test_a_file_this_pc_does_not_have_fails_loudly(ir_dir):
    """★ 파일명은 함께 쓰지만 실물은 그 PC 에만 있다.

    없으면 **분명히 실패**해야 한다 — 조용히 아무것도 안 보내고 성공으로
    보고하는 것이 제일 나쁘다.
    """
    with pytest.raises(base.IrFileMissing) as exc:
        base.resolve_ir_file("없는자료.pdf", str(ir_dir))
    assert "이 PC 에" in str(exc.value)


def test_a_rejected_name_never_touches_kakaotalk(ir_dir):
    """규칙에 어긋나면 **카톡을 열지도 않는다.** 반쯤 하다 막히면 되돌릴 수 없다."""
    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["../backup-keys/private_key"])

    assert not result.ok
    assert mac.clicked == [], "거절할 값인데 카톡을 건드렸다"
    assert "ir_file_rejected" in result.error


def test_a_missing_file_never_touches_kakaotalk(ir_dir):
    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    result = mac.send_file(ROOM, ["없는자료.pdf"])

    assert not result.ok
    assert mac.clicked == []
    assert "이 PC 에" in result.error


def test_nothing_to_send_is_not_a_success(ir_dir):
    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    assert not mac.send_file(ROOM, []).ok


def test_the_full_path_is_typed_every_time(ir_dir):
    """열기 패널은 마지막 위치를 기억한다 → 경로를 **매번** 명시한다."""
    mac = FakeMac(confirm_sheet(files=("IR.pdf",)), ir_root=str(ir_dir))
    mac.send_file(ROOM, ["IR.pdf"])

    assert len(mac.goto) == 1
    assert mac.goto[0] == str(ir_dir / "IR.pdf")


# ══════════════════════════════════════════════════════════════════════════
#  자료 폴더 자리 — 웹에서 사람이 넣는다
# ══════════════════════════════════════════════════════════════════════════

def test_an_unset_folder_fails_instead_of_guessing(ir_dir):
    """★ 값이 없으면 **분명히 실패**한다 — 아무 데나 뒤지지 않는다."""
    mac = FakeMac(confirm_sheet(), ir_root="")
    result = mac.send_file(ROOM, ["IR.pdf"])

    assert not result.ok
    assert mac.clicked == []
    assert "정해지지 않았습니다" in result.error


@pytest.mark.parametrize("kind", ["없는자리", "폴더가아님"])
def test_a_bad_folder_fails_before_sending(tmp_path, kind):
    """없는 자리·폴더가 아닌 자리는 보내기 전에 막는다."""
    if kind == "없는자리":
        target = tmp_path / "없는곳"
    else:
        target = tmp_path / "그냥파일.txt"
        target.write_text("x")

    with pytest.raises(base.IrPathError):
        base.ir_root(str(target))


def test_the_folder_is_not_created_on_a_typo(tmp_path):
    """오타 난 경로에 폴더를 만들어 주면 안 된다.

    빈 폴더가 생기고, 넣은 사람은 자료를 넣었다고 생각한다.
    """
    typo = tmp_path / "오타난자리"
    with pytest.raises(base.IrPathError):
        base.ir_root(str(typo))
    assert not typo.exists(), "오타 난 자리에 폴더를 만들었다"


def test_the_agent_says_where_the_folder_is(ir_dir):
    """켤 때 자리를 **눈에 보이게** 알려준다 — 자료를 어디 넣을지 알아야 한다."""
    from agent import main as agent_main

    notes = agent_main.preflight(FakeMac(confirm_sheet(), ir_root=str(ir_dir)))
    assert any(str(ir_dir) in n for n in notes), notes


def test_the_agent_complains_when_the_folder_is_unset():
    from agent import main as agent_main

    notes = agent_main.preflight(FakeMac(confirm_sheet(), ir_root=""))
    assert any("정해지지 않았습니다" in n for n in notes), notes


# ══════════════════════════════════════════════════════════════════════════
#  서버가 자리를 내려준다 (박동 응답에 얹었다)
# ══════════════════════════════════════════════════════════════════════════

def test_the_folder_comes_from_the_server(ir_dir):
    from agent import main as agent_main

    mac = FakeMac(confirm_sheet(), ir_root="")
    assert agent_main.apply_server_settings(mac, {"ir_root": str(ir_dir)})
    assert mac.ir_root_setting == str(ir_dir)


def test_an_unchanged_value_is_not_reported_as_a_change(ir_dir):
    from agent import main as agent_main

    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    assert not agent_main.apply_server_settings(mac, {"ir_root": str(ir_dir)})


def test_a_cleared_value_follows_too(ir_dir):
    """화면에서 지우면 발송기도 따라 잊는다 — 낡은 자리를 계속 뒤지면 안 된다."""
    from agent import main as agent_main

    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    assert agent_main.apply_server_settings(mac, {"ir_root": ""})
    assert mac.ir_root_setting == ""


def test_a_broken_response_changes_nothing(ir_dir):
    from agent import main as agent_main

    mac = FakeMac(confirm_sheet(), ir_root=str(ir_dir))
    assert not agent_main.apply_server_settings(mac, None)
    assert mac.ir_root_setting == str(ir_dir)


def test_a_sender_without_file_support_is_left_alone():
    """파일을 못 보내는 발송기에는 이 설정이 없다."""
    from agent import main as agent_main
    from agent.sender.mock import MockSender

    assert not agent_main.apply_server_settings(MockSender(), {"ir_root": "/x"})


# ══════════════════════════════════════════════════════════════════════════
#  Quartz 사전 점검 — 있던 검사를 실제로 부른다
# ══════════════════════════════════════════════════════════════════════════

def test_a_missing_quartz_is_warned_about_at_startup(ir_dir, monkeypatch):
    """★ `quartz_available()` 은 있었는데 **아무도 부르지 않았다.**

    그래서 빠진 PC 도 켤 때는 멀쩡해 보이고 발송 실패로만 알게 됐다.
    """
    from agent import main as agent_main

    monkeypatch.setattr(kakao_mac, "quartz_available", lambda: False)
    notes = agent_main.preflight(FakeMac(confirm_sheet(), ir_root=str(ir_dir)))
    assert any("Quartz" in n for n in notes), notes


def test_no_quartz_nagging_when_it_is_there(ir_dir, monkeypatch):
    from agent import main as agent_main

    monkeypatch.setattr(kakao_mac, "quartz_available", lambda: True)
    notes = agent_main.preflight(FakeMac(confirm_sheet(), ir_root=str(ir_dir)))
    assert not any("Quartz" in n for n in notes)


def test_other_senders_are_not_asked_about_quartz(monkeypatch):
    """Quartz 는 맥 카톡 발송기에서만 쓴다."""
    from agent import main as agent_main
    from agent.sender.mock import MockSender

    monkeypatch.setattr(kakao_mac, "quartz_available", lambda: False)
    assert not any("Quartz" in n for n in agent_main.preflight(MockSender()))


# ══════════════════════════════════════════════════════════════════════════
#  Windows — 되는 척하지 않는다
# ══════════════════════════════════════════════════════════════════════════

def test_windows_refuses_to_send_files():
    """실기 확인을 못 했다. 확인 못 한 길로 자료를 내보내면 안 된다."""
    from agent.sender import kakao_windows

    sender = kakao_windows.KakaoDesktopSender.__new__(kakao_windows.KakaoDesktopSender)
    result = sender.send_file("아무 방", ["IR.pdf"])

    assert not result.ok
    assert "file_send_unsupported" in result.error


def test_a_sender_without_file_support_fails_instead_of_pretending():
    """구현하지 않은 발송기가 조용히 성공으로 넘어가면 안 된다."""
    result = base.Sender().send_file("아무 방", ["IR.pdf"])

    assert not result.ok
    assert "file_send_unsupported" in result.error


def test_the_mock_sender_does_not_pretend_either():
    from agent.sender.mock import MockSender

    assert not MockSender().send_file("아무 방", ["IR.pdf"]).ok


# ══════════════════════════════════════════════════════════════════════════
#  배포 zip — 새 모듈을 만들면 여기 걸린다
# ══════════════════════════════════════════════════════════════════════════

def test_every_agent_module_ships_in_the_zip():
    """`agent/` 아래 파이썬 파일은 **전부** zip 목록에 있어야 한다.

    빠뜨리면 사용자 PC 에서 ImportError 로 발송기가 아예 뜨지 않는다. 목록은
    `app/routers/setup.py` 가 손으로 들고 있어서 새 모듈을 만들 때 잊기 쉽다.
    """
    import pathlib

    from app.routers.setup import AGENT_FILES

    root = pathlib.Path(__file__).resolve().parent.parent
    shipped = {src for src, _dest in AGENT_FILES}
    on_disk = {
        str(p.relative_to(root))
        for p in (root / "agent").rglob("*.py")
        if "__pycache__" not in p.parts
    }
    missing = sorted(on_disk - shipped)
    assert not missing, (
        f"zip 목록에 없는 발송기 모듈: {missing} — "
        f"app/routers/setup.py 의 AGENT_FILES 에 더하세요")
