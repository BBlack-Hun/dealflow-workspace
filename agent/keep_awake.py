"""보낼 일이 있는 동안 PC 화면이 꺼지거나 잠기지 않게 한다 (0.11.18).

잠긴 화면에서는 카톡을 조작하지 못한다 — 11/27 아침 회차가 08:59 화면 자동
잠금 하나로 통째로 `room_not_found` 가 됐다. 서버가 폴 응답 머리글
(`X-Pending-Work`)로 **대기 · 진행 중 회차가 있는지** 알려 주면, 그동안만 깨어 있고
없으면 놓아서 평소대로 꺼지고 잠기게 둔다.

- 맥: `caffeinate -d -i -w <이 발송기 pid>` 하나를 붙들고 있다가 끈다. `-w` 라
  발송기가 죽어도 남지 않는다.
- 윈도우: `SetThreadExecutionState` — 같은 스레드(폴링 고리)에서 켜고 끈다.
- 그 밖(Mock 등)이거나 실패하면 조용히 넘어간다 — 발송을 막지 않는다.

이미 잠긴 화면은 풀지 못한다(비밀번호가 필요하다). 대기 회차가 밤새 있으면 밤새
깨어 있다 — 아침 9시 전에 잠기지 않게 하려는 것이 바로 그 뜻이다.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys

log = logging.getLogger("dealflow.agent")

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class KeepAwake:
    def __init__(self, platform: str = sys.platform):
        self.platform = platform
        self.on = False
        self._proc = None
        self._failed = False

    def set(self, want: bool) -> None:
        """`want` 이 지금 상태와 다를 때만 바꾼다(맥은 붙든 것이 죽었으면 다시 띄운다)."""
        if self._failed:
            return
        alive = self._proc is not None and self._proc.poll() is None
        if want == self.on and (not want or self.platform != "darwin" or alive):
            return
        try:
            if self.platform == "darwin":
                self._mac(want)
            elif self.platform == "win32":
                self._windows(want)
            else:
                return
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            log.warning("화면 깨워 두기를 못 합니다(발송은 계속): %s", exc)
            return
        self.on = want
        log.info("보낼 일이 %s — 화면 깨워 두기 %s", "있음" if want else "없음",
                 "켬" if want else "끔")

    def _mac(self, want: bool) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None
        if want:
            self._proc = subprocess.Popen(["caffeinate", "-d", "-i", "-w", str(os.getpid())],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _windows(self, want: bool) -> None:
        import ctypes

        flags = ES_CONTINUOUS | (ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED if want else 0)
        if not ctypes.windll.kernel32.SetThreadExecutionState(flags):
            raise OSError("SetThreadExecutionState 실패")
