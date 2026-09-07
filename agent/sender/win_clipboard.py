"""Windows 클립보드에 **파일을 담는다** (`CF_HDROP`).

## 왜 클립보드인가

Windows 카톡은 글자를 **클립보드 + Ctrl+V** 로 넣는 길이 실기에서 확인됐다
(`kakao_windows.send_text`). 즉 그 창은 붙여넣기를 받는다. 파일도 같은 길로
갈 수 있다 — 탐색기에서 파일을 복사해 대화창에 붙이는 것과 같은 형식이
`CF_HDROP` 이다.

mac 은 이 길이 **아예 막혀 있었다**(Cmd+V 가 안 먹어서 `파일전송 ⌘O` 단추 →
열기 패널로 돌아갔다). Windows 는 다를 것이라는 것이 이 파일의 전제다.

⚠ **전제이지 확인된 사실이 아니다.** "카톡 입력창이 `CF_HDROP` 붙여넣기를
  받는가" 는 팀 PC 에서 확인할 목록에 올려 두었다(`docs/WINDOWS_TEST.md`).
  여기서 확인된 것은 **클립보드에 담기까지**다 — 담은 것을 다시 읽어 견주는
  자리를 함께 둔 이유가 그것이다(`set_files` → `get_files`).

## 새 의존성을 넣지 않았다

- `ctypes` 는 파이썬에 들어 있다.
- `pywin32` 는 이미 Windows 발송기 의존성에 있다(`requirements-agent-windows.txt`
  의 `pywin32==308`). `kakao_windows.py` 가 `win32gui` 등으로 이미 쓰고 있다.

그런데도 여기서는 **`ctypes` 로 직접 부른다.** `win32clipboard.SetClipboardData`
에 파이썬 바이트열을 그대로 넘겼을 때 pywin32 가 그것을 핸들로 보는지 내용으로
보는지가 형식마다 갈린다(`CF_TEXT` 는 특별 취급하고 나머지는 판마다 다르다).
클립보드는 **메모리 주인이 넘어가는** 자리라 그 모호함을 그대로 두면 안 된다 —
`SetClipboardData` 가 성공한 뒤에는 그 메모리를 우리가 풀면 안 되고, 실패하면
반드시 우리가 풀어야 한다. 어느 쪽인지 분명해야 해서 손으로 잡는다.

## 담는 모양 (`DROPFILES` + 경로 목록)

    ┌─ DROPFILES (20바이트) ────────────────────────┐
    │ pFiles = 20   목록이 시작하는 자리(머리 바로 뒤) │
    │ pt     = 0,0  끌어다 놓은 좌표 — 안 쓴다        │
    │ fNC    = 0                                    │
    │ fWide  = 1    ★ 넓은 글자(UTF-16). 한글 경로용 │
    └───────────────────────────────────────────────┘
    "C:\\...\\가나다.pdf\0"  …  "\0"      ← 널 둘로 끝난다

⚠ `fWide` 를 0 으로 두면 한글 경로가 깨진다. **항상 1 로 담는다.**
"""
from __future__ import annotations

import struct
from typing import List, Optional, Sequence

#: 표준 클립보드 형식 번호(`winuser.h`).
CF_HDROP = 15

GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040

#: `DROPFILES` 머리 — DWORD pFiles · POINT pt(LONG 둘) · BOOL fNC · BOOL fWide.
#: 전부 4바이트라 채움(padding)이 끼지 않는다. 32/64비트에서 같은 20바이트다.
_HEADER = "<Iiiii"
_HEADER_SIZE = struct.calcsize(_HEADER)


class ClipboardError(RuntimeError):
    """클립보드에 담지 못했거나 다시 읽지 못했다.

    부르는 쪽은 이것을 보면 **보내지 않는다.** 클립보드에 무엇이 들었는지
    모르는 채로 Ctrl+V 를 누르면 무엇이 나가는지 알 수 없다.
    """


# ── 순수한 부분 (어느 기계에서나 그대로 시험할 수 있다) ──────────────────────

def hdrop_bytes(paths: Sequence[str]) -> bytes:
    """경로 목록을 `CF_HDROP` 한 덩어리로 만든다. **순수 함수다.**

    Windows 가 없어도 그대로 부를 수 있어서, 담는 모양이 맞는지는 이 기계에서
    시험한다(`tests/test_ir_send_file_windows.py`).
    """
    items = [str(p) for p in (paths or [])]
    if not items:
        raise ClipboardError("클립보드에 담을 파일이 없습니다")
    for item in items:
        if not item.strip():
            raise ClipboardError("빈 경로는 담지 않습니다")
        if "\x00" in item:
            # 널이 들어오면 목록이 거기서 끝난 것으로 읽힌다 — 뒤가 통째로 사라진다.
            raise ClipboardError(f"경로에 널 문자가 있습니다: {item!r}")

    header = struct.pack(_HEADER, _HEADER_SIZE, 0, 0, 0, 1)   # fWide=1
    body = "".join(item + "\0" for item in items) + "\0"      # 널 둘로 끝
    return header + body.encode("utf-16-le")


def parse_hdrop(blob: bytes) -> List[str]:
    """`CF_HDROP` 덩어리를 경로 목록으로 되돌린다. **순수 함수다.**

    우리가 담은 것을 **다시 읽어 견주려고** 있다. 남이 담은 것(탐색기에서 복사한
    파일)도 읽을 수 있어야 하므로 좁은 글자(`fWide=0`)도 다룬다.
    """
    if len(blob) < _HEADER_SIZE:
        raise ClipboardError(f"클립보드 내용이 너무 짧습니다({len(blob)}바이트)")
    offset, _x, _y, _fnc, wide = struct.unpack(_HEADER, blob[:_HEADER_SIZE])
    if offset < _HEADER_SIZE or offset > len(blob):
        raise ClipboardError(f"클립보드 내용의 목록 자리가 이상합니다: {offset}")

    body = blob[offset:]
    if wide:
        text = body.decode("utf-16-le", errors="replace")
    else:
        try:
            text = body.decode("mbcs", errors="replace")   # Windows 기본 코드페이지
        except LookupError:                                # Windows 가 아닌 곳
            text = body.decode("utf-8", errors="replace")
    return [chunk for chunk in text.split("\0") if chunk]


# ── Windows 에서만 도는 부분 ────────────────────────────────────────────────
#
# ⚠ 아래는 이 기계(macOS)에서 돌려 볼 수 없다. 그래서 부르는 쪽은 담은 뒤
#   **반드시 다시 읽어 견준다** — 담긴 줄 알았는데 안 담긴 채로 Ctrl+V 를
#   누르면 엉뚱한 것이 나간다.

def _dlls():
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # ★ 64비트에서 핸들은 8바이트다. restype 을 안 정하면 ctypes 가 int(4바이트)로
    #   잘라서, 멀쩡한 핸들이 쓰레기 값이 된다.
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]

    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    return user32, kernel32


def _open_clipboard(user32, retries: int = 6, gap: float = 0.15) -> None:
    """클립보드를 연다. 다른 앱이 잡고 있으면 잠깐 기다렸다 다시 시도한다.

    클립보드는 한 번에 한 프로세스만 연다. 브라우저·메모장 같은 것이 순간적으로
    잡고 있는 일이 흔해서 한 번 실패했다고 포기하면 발송이 자주 헛돈다.
    """
    import time

    for _ in range(max(1, retries)):
        if user32.OpenClipboard(None):
            return
        time.sleep(gap)
    raise ClipboardError("클립보드를 열지 못했습니다 — 다른 프로그램이 쓰고 있습니다")


def set_files(paths: Sequence[str]) -> None:
    """파일 경로들을 클립보드에 담는다(`CF_HDROP`).

    ★ 메모리 주인이 넘어가는 자리다. `SetClipboardData` 가 성공하면 그 메모리는
      **윈도우 것**이 되므로 우리가 풀면 안 된다. 실패하면 반드시 우리가 푼다.
      그래서 `placed` 를 따로 둔다 — `finally` 하나로 뭉뚱그리면 둘 중 하나가
      틀린다(성공했는데 풀어서 클립보드가 깨지거나, 실패했는데 안 풀어서 샌다).
    """
    import ctypes

    blob = hdrop_bytes(paths)
    user32, kernel32 = _dlls()

    _open_clipboard(user32)
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("클립보드를 비우지 못했습니다")

        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(blob))
        if not handle:
            raise ClipboardError("클립보드 메모리를 잡지 못했습니다")

        placed = False
        try:
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise ClipboardError("클립보드 메모리를 잠그지 못했습니다")
            try:
                ctypes.memmove(pointer, blob, len(blob))
            finally:
                kernel32.GlobalUnlock(handle)

            if not user32.SetClipboardData(CF_HDROP, handle):
                raise ClipboardError("클립보드에 파일을 넣지 못했습니다")
            placed = True          # 여기부터 메모리 주인은 윈도우다
        finally:
            if not placed:
                kernel32.GlobalFree(handle)
    finally:
        user32.CloseClipboard()


def get_files() -> Optional[List[str]]:
    """클립보드에 담긴 파일 목록. 파일이 아니면 None.

    **담은 것을 다시 읽어 견주려고** 있다. None 은 "파일이 안 담겼다" 이고,
    부르는 쪽은 그것을 보면 붙여넣지 않는다.
    """
    import ctypes

    user32, kernel32 = _dlls()

    _open_clipboard(user32)
    try:
        if not user32.IsClipboardFormatAvailable(CF_HDROP):
            return None
        handle = user32.GetClipboardData(CF_HDROP)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ClipboardError("클립보드 내용을 잠그지 못했습니다")
        try:
            size = kernel32.GlobalSize(handle)
            blob = ctypes.string_at(pointer, size)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

    return parse_hdrop(blob)
