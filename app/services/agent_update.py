"""옛 발송기 알림 — 로그인한 **본인** 발송기가 최신보다 낡았으면 화면마다 창을 띄운다.

## '최신' 은 어디서 오나

`app/version.VERSION` 하나다. 내려받기(`/download/agent`)가 zip 에 싣는
`agent/version.py` 와 같은 값이고(`tests/test_version.py` 가 지킨다), 그래서
발송기 판을 올리면 이 알림도 따로 고칠 것 없이 따라간다.

## `version.agent_is_old` 와 무엇이 다른가

그쪽은 `MIN_AGENT_VERSION` 보다 낡아 **위험한** 판이다(팀 현황 경고 · [중단]이
안 먹는다). 여기는 새 판이 나왔으니 받으라는 안내다. 판을 모르면 그쪽은 낡은
것으로 보지만 여기서는 **건너뛴다** — 모르는 판을 두고 모든 화면을 가리면,
받아도 안 사라지는 창이 된다.

## 언제 안 띄우나

- 마지막 보고가 `STALE_DAYS` 일보다 오래된 기기 — 버린 PC 하나 때문에 창이
  영영 뜨지 않게.
- 내려받기 화면 자체(`SKIP_PATHS`) — 거기서 띄우면 [내려받기]가 같은 화면을
  다시 열어 창이 또 뜬다.
- 비밀번호를 아직 안 바꾼 계정 — 어디를 눌러도 비밀번호 화면으로 돌아간다.

닫는 것은 **그 화면에서만**이다(`_agent_update.html`). 다른 화면을 열면 또
뜨고, 새 판을 받아 기기가 새 판을 보고하면 바로 안 뜬다.

## [오늘 하루 보지 않기]

고르고 닫으면 브라우저가 쿠키(`HIDE_COOKIE`)에 **오늘 날짜**를 적는다 — 날짜는
서버가 창에 실어 준 값이다(`today`, 한국 날짜 `clock.today()`). 쿠키 날짜가 오늘과
같으면 띄우지 않고, 자정이 지나면 날짜가 어긋나 저절로 다시 뜬다. 쿠키는 그
브라우저 것이라 다른 PC·다른 브라우저에서는 그대로 뜬다. 적는 쪽은
`static/js/agent_badge.js` 다(모든 화면이 이미 불러오는 파일).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock, version
from ..models import AgentDevice, User

#: 이보다 오래 보고가 없는 기기는 버린 PC 로 보고 알리지 않는다.
STALE_DAYS = 30
#: 내려받기 화면 — 여기서는 띄우지 않는다.
SKIP_PATHS = ("/setup", "/download")
#: [오늘 하루 보지 않기] 를 고르고 닫으면 브라우저가 오늘 날짜를 적는 쿠키(`agent_badge.js`).
HIDE_COOKIE = "agent_update_hide"

_VERSION = re.compile(r"\d+(?:\.\d+)*")


def parse(value: Optional[str]) -> Optional[tuple]:
    """`"0.10.0"` → `(0, 10, 0)`. 숫자·점 말고 다른 것이 섞였으면 None(모른다)."""
    text = (value or "").strip()
    if not _VERSION.fullmatch(text):
        return None
    return tuple(int(x) for x in text.split("."))


def is_older(reported: Optional[str], latest: str = version.VERSION) -> bool:
    """`reported` 가 `latest` 보다 낡았는가 — 숫자 단위로(0.10.0 > 0.9.0).

    자리 수가 달라도 빈 자리는 0 으로 본다(`0.11` == `0.11.0`). 어느 쪽이든
    못 읽으면 낡았다고 하지 않는다.
    """
    mine, top = parse(reported), parse(latest)
    if mine is None or top is None:
        return False
    width = max(len(mine), len(top))
    return mine + (0,) * (width - len(mine)) < top + (0,) * (width - len(top))


def outdated(device: Optional[AgentDevice]) -> bool:
    """이 기기가 지금 쓰이는 옛 발송기인가 — 최근 `STALE_DAYS` 일 안에 보고했고 판이 낡았다."""
    if device is None or not device.last_poll_at:
        return False
    try:
        # 저장값에 오프셋이 붙어 있다 — 순간끼리 뺀다(`deps.agent_status` 와 같다).
        age = clock.now() - datetime.fromisoformat(device.last_poll_at)
    except (ValueError, TypeError):
        return False
    return age <= timedelta(days=STALE_DAYS) and is_older(device.agent_version)


def notice(db: Session, me: User, path: str,
           hidden_on: Optional[str] = None) -> Optional[dict]:
    """밑틀이 띄울 창의 내용 — 띄울 것이 없으면 None.

    `me` 는 **로그인한 본인**이다(`deps.doer`). 관리자가 팀원 화면으로 보는 중이어도
    그 팀원 기기가 아니라 관리자 본인 기기를 본다 — 대리 보기는 보기·수정만이다.

    `hidden_on` 은 요청에 실린 `HIDE_COOKIE` 값이다. 오늘(한국 날짜)과 같으면
    [오늘 하루 보지 않기] 를 고르고 닫은 날이라 띄우지 않는다.
    """
    if me is None or me.must_change_password:
        return None
    if any(path == p or path.startswith(p + "/") for p in SKIP_PATHS):
        return None
    today = clock.today().isoformat()
    if hidden_on == today:
        return None
    old = [d for d in db.execute(
        select(AgentDevice).where(AgentDevice.user_id == me.id)
        .order_by(AgentDevice.id)).scalars() if outdated(d)]
    if not old:
        return None
    return {"latest": version.VERSION,
            "today": today,
            "devices": [{"name": (d.hostname or "").strip() or "이름 없는 PC",
                         "version": d.agent_version.strip()} for d in old]}
