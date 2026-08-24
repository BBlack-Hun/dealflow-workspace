"""서버가 '오늘' 을 한국 날짜로 봐야 한다.

컨테이너 기본값은 UTC 다. 그러면 **자정부터 아침 9시까지 서버는 어제**라고
생각한다 — 8월 25일 아침에 대시보드가 "8/26 발송까지 2일 남음" 이라고 떴다.
하루가 어긋나면 회차를 통째로 놓친다.

회차일·후속 예약일·"오늘 보낼 것" 이 전부 이 날짜로 계산된다.
"""
from __future__ import annotations

import pathlib
import re


def test_compose_pins_the_timezone():
    """도커 기본값(UTC)이면 한국 새벽에 날짜가 하루 밀린다."""
    compose = pathlib.Path("docker-compose.yml").read_text(encoding="utf-8")
    # 웹과 발송 프로그램 양쪽 — 발송 로그 시각도 한국 시간이어야 대조된다
    assert compose.count("TZ:") >= 2, "TZ 설정이 빠진 서비스가 있다"
    assert "Asia/Seoul" in compose


def test_the_image_can_resolve_that_timezone():
    """`TZ` 만 주고 tzdata 가 없으면 조용히 UTC 로 남는다."""
    dockerfile = pathlib.Path("Dockerfile").read_text(encoding="utf-8")
    # python:*-slim 은 tzdata 를 포함한다. 베이스를 바꾸면 이 테스트가 알려 준다.
    assert re.search(r"FROM python:3\.\d+-slim", dockerfile), \
        "베이스 이미지를 바꿨다면 tzdata 가 들어 있는지 확인하세요"


def test_days_left_counts_calendar_days(db, users):
    """'내일 발송' 이면 1일이다. 시각이 아니라 날짜로 센다."""
    from datetime import date

    from app.services import readiness

    got = readiness.report(db, users["u1"], today=date(2026, 8, 25))
    # 8/26 은 넷째 수요일 — 기본 규칙(첫째·셋째)에는 없다.
    # 여기서 재는 것은 **날짜 빼기가 맞는가** 이다.
    assert got["days_left"] == (got["next_send"] - date(2026, 8, 25)).days
