"""스타트업 월간 발송 — **시각 칸 판정과 '이 달 회차' 판정** 두 가지만 남은 자리.

## 매월 30일 자동은 걷었다 (#31)

여기는 원래 매월 30일(2월은 말일) 아침에 그 달 대기 목록을 세우던 실이었다
(`monthly_auto` · `monthly_time`). 날짜·문구를 돌리는 2단계 자동화 A5
(`services/automations/startup_monthly.py`)가 생긴 뒤로 둘이 같은 달을 두고
나란히 서 있었고, 그 사이로 사고가 새었다 — 사람이 A5 회차를 [중단] 하면 30일에
옛 자동이 다시 보냈고, A5 가 실패한 달에는 옛 자동이 **다른 글**을 조용히 보냈다.
사용자 결정(2026-10-17)으로 매월은 A5 하나다. 실도 판도 걷고, 표와 이력
(`auto_send_settings` 의 두 칸 · `auto_send_runs` 의 `startup_ir_monthly` 줄)은
그대로 남긴다 — 이주(0105)가 옛 설정으로 A5 줄을 꺼진 채 세웠다.

## 남은 둘

- `parse_time` — 자동화 시각 칸이 고를 수 있는 폭(예약과 같은 09~19시,
  `send_window`). `automation_runner.parse_time` 이 그대로 부른다.
- `month_job` — **그 달 회차가 이미 있는가.** A5 가 같은 달 두 번 보내지 않게
  하는 판정이다. 사람이 세운 것 · 옛 30일 자동이 세운 것도 센다.

## 시각

전부 `clock.now()` 를 읽는다 — 한국시간은 프로세스 시간대(compose 의 `TZ`)가
정하고, 검사는 `clock.now` 하나만 바꿔 날을 고정한다.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import STARTUP_SEND_KIND, DealBatch, SendItem, SendJob
from . import send_window

_MONTH_IN_TITLE = re.compile(r"(\d{4}-\d{2})")


def parse_time(raw: Optional[str]) -> str:
    """`HH:MM` 으로 다듬는다. 예약이 고를 수 있는 폭(09~19시) 밖이면
    `ValueError` — **저장 자리에서 자른다**(`scheduled_send.check` 와 같은 폭)."""
    value = (raw or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", value)
    if not m:
        raise ValueError("자동 발송 시각을 읽을 수 없습니다 — 17:00 처럼 적으세요")
    hour, minute = int(m.group(1)), int(m.group(2))
    if minute > 59 or not send_window.contains_hour(hour):
        raise ValueError(
            f"자동 발송 시각은 {send_window.label()} 안에서만 고를 수 있습니다")
    return f"{hour:02d}:{minute:02d}"


def _job_month(job: SendJob, batch_title: str) -> str:
    """이 회차가 어느 달치인가. 회차명에 `YYYY-MM` 이 있으면 그 달(화면의
    기본 회차명이 `… (스타트업 월간 발송 2026-10)` 이다), 없으면 만든 달."""
    found = _MONTH_IN_TITLE.search(batch_title or "")
    return found.group(1) if found else (job.created_at or "")[:7]


def month_job(db: Session, month: str) -> Optional[SendJob]:
    """그 달치 스타트업 회차(취소되지 않은 것 — 또는 취소됐어도 **한 곳이라도
    나간 것**). 없으면 `None`.

    A5 가 같은 달에 두 번 보내지 않게 하는 판정이다(사람이 먼저 세웠거나 옛 30일
    자동이 세운 회차도 센다). 중간에 [중단] 한 회차도 이미 나간 곳이 있으면 그
    달은 보낸 달이다.
    """
    from sqlalchemy import exists, or_

    sent = exists().where(SendItem.job_id == SendJob.id,
                          SendItem.status.in_(("sent", "sending")))
    rows = db.execute(
        select(SendJob, DealBatch.title)
        .outerjoin(DealBatch, DealBatch.id == SendJob.batch_id)
        .where(SendJob.kind == STARTUP_SEND_KIND,
               or_(SendJob.status != "canceled", sent))
        .order_by(SendJob.id)
    ).all()
    for job, title in rows:
        if _job_month(job, title or "") == month:
            return job
    return None
