"""메일에 붙일 IR 자료 파일 — **발송 PC 가 올리고**, 서버는 보낼 때까지만 들고 있다.

IR 자료 파일은 각자 PC 의 자료 폴더에만 있고(`agent/sender/base.py: resolve_ir_file`)
메일은 서버가 보낸다(`services/mail_sender.py`). 그래서 메일로 나가는 IR 자료 전달은
**파일이 올라올 때까지 대기**하고, 발송기가 박동 응답에서 그 건을 받아
(`routers/agent_api.py: heartbeat`) 파일을 올리면 다음 예약 실 바퀴에 나간다
(`mail_sender.resume_waiting`).

## 올라온 파일은 어디에, 무슨 이름으로

    <data>/mail_attachments/<건 번호>/<차례 번호>

**이름을 받지 않는다.** 발송기는 그 건 `files_json` 의 몇 번째 파일인지만 말하고,
받는 쪽에 보일 이름은 서버가 `files_json` 에서 읽는다 — 올라온 글자가 경로가 될
자리가 없다. "다 올라왔는가" 도 이 폴더로 안다(칸을 늘리지 않는다).

## 언제 지우나

건이 끝나면(보냄 · 실패) 그 자리에서(`drop`), 취소 · 사라진 건 · 묵은 폴더는
예약 실이 30초마다 치운다(`sweep`). 아무 데서도 다시 내주지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from sqlalchemy.orm import Session

from .. import config
from ..models import SendItem

#: 메일 한 통에 붙는 파일 합계의 상한(MB, 원본 크기). base64 로 실리면 약 1.37배가
#: 되고 받는 쪽 메일함은 대개 25MB 에서 막는다.
MAX_MB_ENV = "DEALFLOW_MAIL_ATTACH_MAX_MB"
DEFAULT_MAX_MB = 18

#: 올라온 지 이만큼 지난 폴더는 건이 살아 있어도 지운다 — 보내다 서버가 내려가
#: `sending` 으로 굳은 건의 파일이 끝없이 남지 않게. 대기 건이면 다시 올라온다.
STALE_DAYS = 3

#: 파일을 기다리는 메일 건에 적는 말. 진행 화면의 그 줄에 그대로 보이고, 파일이
#: 다 올라온 건을 이어 보낼 때 고르는 표시도 된다(`mail_sender.resume_waiting`).
#: ★ 글자를 바꾸면 그 순간 기다리던 건이 저절로 이어지지 않는다(표시가 달라진다) —
#: 판 번호처럼 낡을 값을 넣지 않는다.
WAIT = ("발송 PC에서 자료 파일을 올리기를 기다립니다 — 발송 프로그램이 켜져 있어야 "
        "하고, 낡은 판이면 새로 받아야 합니다")
#: 딜 제안 관리에서 메일로 IR 자료를 보내려는데 붙일 길이 없을 때.
NO_ATTACH = ("메일로 IR 자료를 보내려면 자료 파일 자동 첨부가 켜져 있고(관리자가 팀 "
             "현황에서 켭니다) [발송 프로그램] 화면에 발송 PC 의 IR 자료 폴더가 정해져 "
             "있어야 합니다")


class TooBig(ValueError):
    """합계가 상한을 넘었다 — 그 건은 실패로 닫는다."""


def max_bytes() -> int:
    try:
        mb = float(os.environ.get(MAX_MB_ENV, "") or DEFAULT_MAX_MB)
    except ValueError:
        mb = DEFAULT_MAX_MB
    return int((mb if mb > 0 else DEFAULT_MAX_MB) * 1024 * 1024)


def too_big_note() -> str:
    return (f"첨부 용량 초과 — 자료 파일 합계가 {max_bytes() // (1024 * 1024)}MB 를 "
            "넘어 메일을 보내지 않았습니다")


def root() -> Path:
    return Path(config.DATA_DIR) / "mail_attachments"


def _dir(item_id: int) -> Path:
    return root() / str(int(item_id))


def names(item: SendItem) -> list:
    """이 건에 붙을 파일 이름 — 붙는 차례 그대로. 없으면 빈 목록."""
    return [str(n) for n in json.loads(item.files_json or "[]")]


def attachments(item: SendItem) -> list:
    """(받는 쪽에 보일 이름, 서버에 둔 자리) 들."""
    return [(name, _dir(item.id) / str(n)) for n, name in enumerate(names(item))]


def ready(item: SendItem) -> bool:
    """붙일 파일이 **다 올라왔는가.** 붙일 것이 없는 건은 늘 참이다."""
    return all(path.is_file() for _name, path in attachments(item))


async def save(item_id: int, index: int, chunks) -> int:
    """올라오는 파일 하나를 받아 적는다. 적은 바이트 수.

    **흘려 받으며 센다** — 이 건의 다른 파일까지 합쳐 상한을 넘는 순간 멈추고
    `TooBig`. 다 받은 뒤에야 제자리로 옮기므로(`os.replace`) 받다 만 파일이
    "다 올라왔다" 로 읽히지 않고, 같은 파일을 다시 올리면 바꿔 놓는다.
    """
    folder = _dir(item_id)
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / str(int(index))
    left = max_bytes() - sum(p.stat().st_size for p in folder.iterdir()
                             if p.is_file() and p.name.isdigit() and p != final)
    part = folder / f"{int(index)}.part"
    size = 0
    try:
        with part.open("wb") as fh:
            async for chunk in chunks:
                size += len(chunk)
                if size > left:
                    raise TooBig(too_big_note())
                fh.write(chunk)
        if not size:
            raise ValueError("빈 파일은 받지 않습니다")
        os.replace(part, final)
    finally:
        part.unlink(missing_ok=True)
    return size


def drop(item_id: int) -> None:
    """이 건의 파일을 지운다 — 건이 끝났다."""
    shutil.rmtree(_dir(item_id), ignore_errors=True)


def sweep(db: Session) -> None:
    """남은 폴더를 치운다 — 끝난 건 · 취소된 건 · 없는 건 · `STALE_DAYS` 묵은 것.

    건 번호가 아닌 이름은 건드리지 않는다(모르는 것은 지우지 않는다).
    """
    base = root()
    if not base.is_dir():
        return
    edge = time.time() - STALE_DAYS * 86400
    for path in base.iterdir():
        if not path.name.isdigit():
            continue
        item = db.get(SendItem, int(path.name))
        try:
            stale = path.stat().st_mtime < edge
        except OSError:
            continue
        if item is None or item.status not in ("pending", "sending") or stale:
            shutil.rmtree(path, ignore_errors=True)
