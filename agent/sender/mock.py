"""MockSender — dev/Docker sender (TECH_SPEC §3, ROADMAP task 1.7).

Simulates a human-like send: random delay, occasional failure (configurable
fail_rate). Lets the whole web ↔ queue ↔ agent round trip be tested with no
Windows / Kakao. Logs every send to agent_logs/mock.log.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Optional

from .base import SendResult, Sender, stop_result

log = logging.getLogger("agent.mock")


class MockSender(Sender):
    name = "mock"

    def __init__(self, delay_min: float = 0.5, delay_max: float = 1.5,
                 fail_rate: float = 0.0, ambiguous_rooms: Optional[list] = None):
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.fail_rate = fail_rate
        self.ambiguous_rooms = set(ambiguous_rooms or [])

    def verify_room(self, room_name: str) -> str:
        if room_name in self.ambiguous_rooms:
            return "ambiguous"
        # A blank/placeholder room name is treated as not found.
        return "verified" if room_name and room_name.strip() else "not_found"

    def send_text(self, room_name: str, text: str, should_stop=None) -> SendResult:
        delay = random.uniform(self.delay_min, self.delay_max)
        time.sleep(delay)
        if not room_name or not room_name.strip():
            return SendResult(ok=False, error="room_name empty (mock)")
        # 방을 연 뒤 넣기 직전 [중단]을 묻는 것까지 흉내낸다(`Sender.send_text`)
        if should_stop is not None and should_stop():
            return stop_result("문구를 넣기 전에 멈췄습니다(전송 안 함, mock)")
        if random.random() < self.fail_rate:
            log.warning("[mock] FAILED room=%r (simulated)", room_name)
            return SendResult(ok=False, error="simulated failure (mock)")
        log.info("[mock] SENT room=%r chars=%d delay=%.2fs", room_name, len(text), delay)
        return SendResult(ok=True)
