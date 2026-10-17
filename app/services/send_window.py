"""보내는 시간(09:00~19:00) — 이 규칙이 사는 **한 곳**.

받는 쪽이 투자사·기업이라 새벽이나 밤에 카톡이 가면 그것만으로 관계가 상한다.
그래서 문구가 나가는 자리가 전부 이 폭을 지킨다:

- 발송기에게 잡을 내주는 자리(`send_guard.window_open` → `agent_api.poll`)
- 예약을 고르는 자리와 푸는 자리(`scheduled_send.check` · `deadline`)
- 자동화 팀 공통의 '자동 발송 가능 시간대'(`automation.guard_window`)
- 자동화·스타트업 월간 발송의 시각 칸(`startup_monthly.parse_time`)
- 미팅 후기 자동 준비의 시간 창(`auto_send.clamp_hours`)
- 회차를 아침에 세우는 시각(`prepare_hour`)
- 위 폭을 화면에 적는 자리(예약 칸 안내 · 팀 현황)

각 자리는 숫자를 들고 있지 않고 **여기 함수를 부른다.** 숫자를 들고 있으면
한쪽만 바뀌어 고를 수는 있는데 안 나가는(또는 그 반대) 시각이 생긴다.

## 테스트 서버에서만 끈다  ★

`DEALFLOW_TEST_SERVER_NO_SEND_WINDOW=1`(`config.send_window_off`). 사용자가
정했다: "운영서버는 발송제한이 있어야하지만 테스트서버는 없어도 됨". 테스트
서버의 자동화는 시험 모드라 본인 '나와의 채팅' 시험방으로만 간다.

끄면 폭이 00:00~24:00 이 된다 — **위의 자리가 전부 함께.** 끄는 것은 시간 폭
하나다. 하루 상한 · 같은 분 하루 최대 · 회차 사이 간격 · 건 사이 간격 · 중복
방지 · 시험 모드는 그대로다.

운영에서는 켜지지 않는다: `DEALFLOW_ENV=production` 이면 값이 있어도 끈 것으로
보지 않고, 그 전에 `config.assert_ready` 가 뜨지 않게 막는다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Tuple

from .. import config

log = logging.getLogger(__name__)

#: **운영의 폭.** 9시는 출근 직후, 19시 이후는 퇴근한 사람의 폰이다
#: (`auto_send` 머리말). 판정은 이 숫자를 직접 읽지 말고 `hours()` 를 부른다.
EARLIEST_HOUR = 9
LATEST_HOUR = 19

#: 테스트 서버에서 껐을 때의 폭 — 하루 전부.
ALL_DAY = (0, 24)

#: 화면 띠와 시작 로그에 적는 말.
BANNER = "테스트 서버 — 발송 시간 제한 꺼짐"


def off() -> bool:
    """테스트 서버에서 보내는 시간 제한을 껐는가(`config.send_window_off`)."""
    return config.send_window_off()


def hours() -> Tuple[int, int]:
    """보내는 시간의 폭 `(시작 시, 끝 시)` — 끝은 들지 않는다."""
    return ALL_DAY if off() else (EARLIEST_HOUR, LATEST_HOUR)


def earliest() -> int:
    return hours()[0]


def latest() -> int:
    return hours()[1]


def contains_hour(hour: int) -> bool:
    start, end = hours()
    return start <= int(hour) < end


def contains(when: datetime) -> bool:
    """이 시각이 보내는 시간 안인가."""
    return contains_hour(when.hour)


def label() -> str:
    """`09:00~19:00` (껐으면 `00:00~24:00`)."""
    start, end = hours()
    return f"{start:02d}:00~{end:02d}:00"


def until_close(start: datetime, minutes: int) -> datetime:
    """`start` 에서 `minutes` 분 뒤 — 단 **그날 보내는 시간이 닫히는 시각을 넘지 않는다.**

    예약이 버티는 끝(`scheduled_send.deadline`)과 간격 때문에 기다린 회차가 버티는
    끝(`scheduled_send.expire_missed`)이 이것을 읽는다. 18:40 예약이 19:40 에 풀리면
    그것은 고를 수도 없던 시각이다 — 막아 둔 창을 뒷문으로 넘는 셈이 된다.

    껐으면 닫히는 시각이 없다 — 자르지 않는다(23:30 예약도 00:30 까지 버틴다).
    """
    later = start + timedelta(minutes=minutes)
    end = latest()
    if end >= 24:
        return later
    edge = start.replace(hour=end, minute=0, second=0, microsecond=0)
    return min(later, edge)


def prepare_hour(normal: int) -> int:
    """회차를 아침에 세우는 시각. 보내는 시간이 열리기 **전**이어야 한다.

    운영은 `normal`(08시) 그대로다. 껐으면 0시 — 00:30 에 나갈 회차를 08시에
    세우면 이미 지난 뒤다.
    """
    return min(int(normal), earliest())


def announce() -> None:
    """껐으면 시작할 때 경고를 남긴다. 켜져 있으면(기본) 아무 말도 없다."""
    if off():
        log.warning("[경고] %s (%s=1) — 보내는 시간이 %s 입니다. "
                    "하루 상한·중복 방지·간격·시험 모드는 그대로입니다. "
                    "운영에서는 켜지 않습니다.",
                    BANNER, config.NO_SEND_WINDOW_ENV, label())
