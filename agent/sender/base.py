"""Sender interface — the single seam that isolates the platform gap (TECH_SPEC §3).

Windows-only imports (pywinauto) live ONLY inside kakao_windows.py, so macOS/Docker
never import them. The agent picks a concrete Sender at runtime.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass
class SendResult:
    ok: bool
    error: Optional[str] = None
    screenshot_b64: Optional[str] = None


class Sender:
    """Abstract sender. Implementations must be safe against mis-send:
    verify_room / send_text / send_file must FAIL (never guess) on an inexact
    room match."""

    name = "base"

    def verify_room(self, room_name: str) -> str:
        """Return 'verified' | 'not_found' | 'ambiguous'. (Used by Sprint 2 [방 연결 확인].)"""
        raise NotImplementedError

    def send_text(self, room_name: str, text: str) -> SendResult:
        """Send `text` to the chat room whose title EXACTLY equals `room_name`."""
        raise NotImplementedError

    def send_file(self, room_name: str, file_names: Sequence[str]) -> SendResult:
        """IR 자료 공통 폴더의 `file_names` 를 첨부해 `room_name` 방으로 보낸다.

        **경로가 아니라 파일명을 받는다** — 실제 자리는 각 PC 가 설정한 뿌리로
        조립한다(`resolve_ir_file`).

        **기본은 '지원 안 함' 이다 — 되는 척하지 않는다.** 구현하지 않은 발송기가
        이 호출을 받으면 조용히 성공으로 넘어가서는 안 된다. 자료가 안 나갔는데
        나갔다고 기록되면 아무도 모른다.

        구현하는 쪽은 `send_text` 와 **같은 오발송 방지 원칙**을 지켜야 한다:
        창 제목이 방 이름과 정확히 일치할 때만, 그리고 보내기 직전 확인 화면이
        보내려던 파일과 정확히 같을 때만 보낸다.
        """
        return SendResult(
            ok=False,
            error=f"file_send_unsupported: {self.name} 발송기는 파일 전송을 지원하지 않습니다",
        )

    def close(self) -> None:
        pass


# ── IR 자료 폴더 ────────────────────────────────────────────────────────────
#
# ⓐ 왜 이 파일에 있나
#   발송기 zip 에 들어가는 파일 목록은 `app/routers/setup.py: AGENT_FILES` 가
#   따로 들고 있다. `agent/` 아래 새 모듈을 만들면 그 목록도 같이 고쳐야 하고,
#   빠뜨리면 사용자 PC 에서 ImportError 로 발송기가 **아예 뜨지 않는다**.
#   "어떤 값을 받아 주는가" 는 `send_file` 규약의 일부이므로 그 옆에 둔다.
#   (`tests/test_ir_send_file.py` 가 agent/ 의 모든 모듈이 zip 목록에 있는지 지킨다)
#
# ⓑ 자료 폴더 자리는 어디서 오나  ★ 규칙
#
#   **웹에 로그인해 자기 PC 의 경로를 자기가 넣는다.** 발송기는 그것을 서버에서
#   받아 간다(회차를 받아 가는 그 통로에 얹었다 — `heartbeat` 응답).
#
#   `config.yaml` 에 적지 않는다. 발송기를 새로 내려받으면 설치 스크립트가
#   `config.yaml` 을 다시 만들어서 손으로 적은 값이 데모 값으로 되돌아간다.
#   서버가 들고 있으면 갱신해도 남는다.
#
#   값이 없으면 **분명히 실패한다.** 조용히 아무 데나 뒤지지 않는다.
#   실제로 있는 폴더여야 한다 — 오타 난 경로에 폴더를 새로 만들면 자료가 없는
#   빈 폴더가 생기고, 넣은 사람은 넣었다고 생각한다.
#
# ⓒ 어느 기업 자료인지 어떻게 아나  ★ 규칙
#
#   **서버는 파일명만 들고, 실제 경로는 각 PC 가 조립한다.**
#   기업마다 자료 칸에 **파일명**을 적어 둔다(예전 구글 드라이브 링크를 담던
#   자리). 발송기는 `<그 PC 의 자료 폴더> + 파일명` 으로 실제 경로를 만든다.
#   경로는 PC 마다 다른 값, 파일명은 서버가 들고 함께 쓰는 값 — 나눠 갖는
#   지점이 여기다.
#
# ⓓ ★★ 폴더 밖으로 나가지 못하게 — **빗장 두 겹** ★★
#
#   파일명은 웹 화면에서 들어와 서버 DB 에 저장되고 여러 PC 가 함께 쓰는 값이다.
#   즉 **화면에 친 글자가 그대로 경로가 된다.** 자료 폴더의 형제 폴더에 서버
#   접속 열쇠 같은 것이 놓여 있으면, `../그폴더/그파일` 한 줄로 그것이 투자사
#   카톡방에 나간다. 되돌릴 수 없다.
#
#   그래서 두 겹으로 건다:
#
#     ① 파일명 검사 (`check_ir_file_name`)
#        경로 구분자(`/`·`\\`)·상위 이동(`..`)·절대경로·빈 값·숨김 파일(`.` 로
#        시작)·널바이트를 전부 거부한다. **파일명 하나만** 받는다.
#        폴더 자리를 넓게 잡아도 이 빗장만으로 밖으로 못 나간다.
#
#     ② 조립한 뒤 실제 위치 확인 (`resolve_ir_file`)
#        `Path.resolve()` 로 심볼릭 링크까지 푼 **실제 경로**가 자료 폴더 안인지
#        다시 본다. 폴더 안에 밖을 가리키는 링크가 있어도 여기서 걸린다.
#
#        ⚠ 문자열 앞부분 비교(`startswith`)로 때우면 안 된다 —
#          `…/자료폴더-딴것` 이 `…/자료폴더` 로 시작해서 통과한다.
#          `relative_to` 로 **부모 관계**를 본다.
#
#   ⚠ 파일명은 함께 쓰지만 **파일 자체는 그 PC 에만 있다.** 없으면 "이 PC 에
#     그 파일이 없다"고 분명히 실패해야 한다 — 조용히 아무것도 안 보내고
#     성공으로 보고하는 것이 제일 나쁘다.

#   ⓔ ★ 한글 파일명은 **두 형태로 들어온다** — 비교할 때만 맞춘다
#
#     macOS 는 한글 파일명을 **자모를 쪼갠 형태(NFD)** 로 디스크에 적는다.
#     반면 웹 화면에 타이핑한 글자는 **합친 형태(NFC)** 로 들어온다. 눈에는
#     똑같은데 글자열로는 다르다.
#
#     파일을 **여는 것**은 어느 쪽이든 된다 — 이 볼륨이 형태를 가려 준다
#     (`exists()` 도 `open()` 도 통과한다). 그래서 이 어긋남은 조용하다.
#
#     터지는 자리는 **문자열끼리 맞춰 보는 곳**이다. 카톡 확인 시트에서 읽어 온
#     이름과 보내려던 이름을 그냥 `==` 로 견주면, 멀쩡한 파일인데 "시트에 없는
#     파일" 이라며 취소한다 — **가짜 실패**다(실기에서 그대로 재현했다).
#     `iterdir()` 목록과 견주는 자리도 같다.
#
#     그래서 **비교하는 두 쪽을 같은 형태로 맞춘 뒤** 견준다(`nfc`).
#
#     ⚠ NFC 여야 한다. **NFKC 를 쓰면 안 된다** — NFKC 는 겉모습이 비슷한
#       글자를 ASCII 로 바꿔 놓아서, 전각 슬래시(`／` U+FF0F)가 진짜 `/` 가
#       된다. 빗장을 통과한 뒤에 경로 구분자가 생기는 셈이다. NFC 는 그런
#       바꿔치기를 하지 않는다(자모를 합치기만 한다).
#
#     ⚠ 정규화는 **비교할 때만** 한다. 빗장(`check_ir_file_name`)은 들어온
#       값 **그대로** 검사한다 — 검사 전에 글자를 주무르면, 무엇을 검사한
#       것인지가 흐려진다.


def nfc(text: str) -> str:
    """한글 파일명 비교용 — 자모를 **합친 형태**로 맞춘다 (위 ⓔ).

    쪼갠 형태(NFD)로 적힌 디스크 이름과 합친 형태(NFC)로 들어온 이름을 같은
    파일로 보기 위한 것이다. **NFKC 가 아니라 NFC** 다 — 이유는 위에 적었다.
    """
    return unicodedata.normalize("NFC", text or "")


def same_file_name(left: str, right: str) -> bool:
    """두 파일명이 **같은 파일을 가리키나.** 자모 조합 형태만 맞춰 견준다.

    대소문자는 맞추지 않는다 — 형태만 다른 것과 글자가 다른 것은 다른 이야기다.
    """
    return nfc(left) == nfc(right)


def _same_name_in(root: Path, name: str) -> Optional[Path]:
    """폴더 안에서 **형태만 다른 같은 이름**을 찾는다. 없으면 None (위 ⓔ).

    `iterdir()` 는 디스크에 적힌 형태를 그대로 돌려준다 — 맥이면 쪼갠 형태다.
    합친 형태로 들어온 이름과 그냥 견주면 하나도 안 맞는다.

    ⚠ 맥에서는 여기까지 오지 않는다. 그 볼륨이 형태를 가려 줘서 `exists()` 가
      이미 통과하기 때문이다. **그것에 기대지 않으려고** 둔다 — 형태를 가리지
      않는 자리(다른 파일 시스템·네트워크 드라이브·시험 환경)에서는 이 되짚기가
      없으면 멀쩡한 파일을 "이 PC 에 없다" 고 한다.

    ⚠ 형태만 다른 이름이 **둘 이상**이면 고르지 않는다 — 어느 쪽인지 알 수
      없는데 아무거나 보내면 엉뚱한 자료가 나간다(방 고르기와 같은 원칙).

    폴더의 **바로 아래**만 본다. 빗장이 이미 이름 하나만 통과시켰으므로 여기서
    폴더 밖으로 나갈 길은 없다.
    """
    want = nfc(name)
    try:
        hits = [p for p in root.iterdir() if nfc(p.name) == want]
    except OSError:
        return None
    return hits[0] if len(hits) == 1 else None


# `scheme://` 로 시작하는 값. 자료 칸에 남아 있는 옛 드라이브 링크를 파일명으로
# 읽지 않기 위한 것이다.
_URL_LIKE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")

# 파일명에 절대 들어올 수 없는 글자. `:` 은 옛 맥 경로 구분자이자 URL 의 일부다.
_NAME_BANNED = ("/", "\\", ":", "\x00")


class IrPathError(ValueError):
    """IR 자료 규칙을 벗어난 값. **전송하지 않고** 실패로 보고한다."""


class IrFileMissing(IrPathError):
    """규칙은 맞는데 **이 PC 에** 그 파일이 없다.

    파일명은 서버가 들고 함께 쓰지만 파일 실물은 각 PC 에만 있다. 이 둘은
    사람이 할 일이 서로 달라서(고치기 ↔ 파일 넣기) 따로 구분한다.
    """


def ir_root(configured: str) -> Path:
    """이 PC 의 IR 자료 폴더. **웹에서 사람이 넣은 값**이다 (위 ⓑ).

    비었거나, 없는 자리거나, 폴더가 아니면 **발송을 시도하기 전에** 실패한다.
    """
    text = (configured or "").strip()
    if not text:
        raise IrPathError(
            "IR 자료 폴더가 정해지지 않았습니다 — 웹에 로그인해 [발송 프로그램] "
            "화면에서 이 PC 의 자료 폴더 경로를 넣어 주세요"
        )
    root = Path(text).expanduser()
    if not root.exists():
        raise IrPathError(f"IR 자료 폴더가 없습니다: {root} — 경로를 확인하세요")
    if not root.is_dir():
        raise IrPathError(f"IR 자료 폴더가 폴더가 아닙니다: {root}")
    return root.resolve()


def check_ir_file_name(file_name: str) -> str:
    """★ 빗장 ① — 서버가 준 값이 **파일명**인지 본다. 아니면 거부한다.

    경로가 아니라 이름 하나여야 한다. 이 빗장만으로도 자료 폴더 밖으로 못 나간다.
    통과하면 앞뒤 공백을 턴 이름을 돌려준다.
    """
    name = (file_name or "").strip()
    if not name:
        raise IrPathError("보낼 파일명이 비어 있습니다")
    if _URL_LIKE.match(name):
        raise IrPathError(
            f"주소는 파일명이 아닙니다: {name!r} — 이 칸에는 자료 폴더에 넣어 둔 "
            f"**파일명**을 적어야 합니다"
        )
    for bad in _NAME_BANNED:
        if bad in name:
            raise IrPathError(
                f"파일명에 경로를 넣을 수 없습니다({bad!r}): {name!r} — "
                f"자료 폴더 안의 파일명만 적으세요"
            )
    if name.startswith("."):
        # `..` 도 여기서 함께 걸린다. 숨김 파일은 사람이 눈으로 확인할 수 없어
        # 자료로 보내지 않는다.
        raise IrPathError(f"숨김 파일이나 폴더 밖으로 나가는 이름입니다: {name!r}")
    return name


def resolve_ir_file(file_name: str, configured_root: str) -> Path:
    """서버가 준 **파일명**을 이 PC 의 실제 경로로 조립하고 확인한다 (빗장 ①+②)."""
    name = check_ir_file_name(file_name)          # ① 이름부터 거른다
    root = ir_root(configured_root)
    path = (root / name).resolve()                 # 링크까지 푼 실제 자리

    # ② 정말 자료 폴더 **안**인가. 부모 관계로 본다 — 앞부분 문자열 비교는
    #    `…/자료폴더-딴것` 을 통과시킨다.
    try:
        path.relative_to(root)
    except ValueError:
        raise IrPathError(
            f"IR 자료 폴더({root}) 밖의 파일은 보내지 않습니다: {file_name!r}"
        ) from None

    if not path.exists():
        # 한글 이름은 **형태가 두 가지**다(위 ⓔ). 글자 그대로는 없어도 형태만
        # 다른 같은 이름이 폴더에 있을 수 있다 — 그러면 같은 파일이다.
        twin = _same_name_in(root, name)
        if twin is None:
            raise IrFileMissing(
                f"이 PC 에 {name!r} 파일이 없습니다 — {root} 에 넣어 주세요"
            )
        path = twin
    if not path.is_file():
        raise IrPathError(f"파일이 아닙니다: {path}")
    return path
