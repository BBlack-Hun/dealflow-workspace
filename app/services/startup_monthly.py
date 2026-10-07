"""스타트업 월간 발송 — **매월 30일에 저절로 예약을 세운다.**

## 무엇을 하나

팀 현황의 스타트업 월간 발송 판에서 `매월 자동 발송` 을 켜 두면, 매월
**30일**(30일이 없는 2월은 **말일**) 아침 `PREPARE_HOUR` 시 이후 첫 깨어남에

1. 그 달의 보낼 수 있는 기업 전부(`startup_send.sendable_ids` — 화면의
   [N곳 대기 목록 만들기] 가 고르는 그 규칙)로
2. **같은 함수**(`routers/deals.create_send_list`, `draft=True`)를 지나
3. 그날 정한 시각(기본 17:00)에 나가도록 예약을 걸어 목록을 세운다.

나가는 것은 이미 있는 예약(`services/scheduled_send.py`)이 그 시각에 푼다.
**세운 목록은 그 시각까지 진행 화면과 오늘 할 일에 서 있다** — 사람이 보고
빼거나 취소할 수 있다. 발송 경로를 한 벌 더 만들지 않는다.

## 한 달에 한 번만

`auto_send_runs` 의 `(kind, ref_id)` 유일 색인을 그대로 쓴다 — `kind` 는
`RUN_KIND`, `ref_id` 는 `YYYYMM`. **목록을 만들기 전에** 자리를 먼저 잡는다
(`auto_send` 와 같은 까닭: 만든 뒤에 적으면 그 틈에 한 벌 더 선다).

그 달 회차가 이미 있으면(사람이 먼저 세웠거나, 취소되지 않은 것) **세우지
않고** 그 사실만 남긴다. 같은 대표방에 같은 달 글이 두 번 가면 안 된다.

보낼 곳이 0곳이면 세우지 않는다. 이것만은 **그날 다시 본다** — 아침에 방
이름을 넣으면 낮에 서야 한다. 시각이 지나도록 못 세웠으면 그 달은 건너뛴다
(늦게 조용히 나가는 것이 더 위험하다 — `scheduled_send` 머리말).

## 알림

앱에는 서버가 직접 보내는 메신저 알림이 없다. 세운 목록은 예약 발송이라
보내는 계정의 **오늘 할 일**에 그대로 서고(`scheduled_send.standing_for`),
못 세운 달은 그 사유가 오늘 할 일과 팀 현황·발송 화면에 뜬다(`today_items`).

## 시각

전부 `clock.now()` 를 읽는다 — 한국시간은 프로세스 시간대(compose 의 `TZ`)가
정하고, 검사는 `clock.now` 하나만 바꿔 날을 고정한다.
"""
from __future__ import annotations

import calendar
import logging
import re
import threading
import time as _time
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..db import SessionLocal
from ..models import (STARTUP_SEND_KIND, AutoSendRun, DealBatch, SendJob,
                      User)
from . import scheduled_send

log = logging.getLogger(__name__)

#: 매월 며칠에 나가나. 이 달에 그날이 없으면(2월) 말일이다.
DAY = 30

#: 기본 시각.
DEFAULT_TIME = "17:00"

#: 그날 몇 시부터 목록을 세우나. 사람이 출근해 오늘 할 일에서 볼 수 있게
#: 아침에 세운다 — 나가는 시각까지 고칠 틈이 남는다.
PREPARE_HOUR = 8

#: 얼마나 자주 깨어나 보나. 하루 한 번 서는 일이라 촘촘할 까닭이 없다.
CHECK_INTERVAL_SEC = 5 * 60

#: `auto_send_runs.kind` — 한 달 한 줄의 열쇠.
RUN_KIND = "startup_ir_monthly"

#: 이 달 자리의 상태.
STATUS_CLAIMED = "claimed"   # 세우는 중
STATUS_READY = "ready"       # 목록이 섰다(예약 걸림)
STATUS_EXISTS = "exists"     # 이 달 회차가 이미 있어 세우지 않았다
STATUS_EMPTY = "empty"       # 보낼 곳이 0곳 — 그날 다시 본다
STATUS_FAILED = "failed"     # 만들다 거절됐다 — 사유를 남긴다

_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
_MONTH_IN_TITLE = re.compile(r"(\d{4}-\d{2})")

_SCHEDULER: Optional[threading.Thread] = None


# ── 날짜 ────────────────────────────────────────────────────────────────────

def run_day(year: int, month: int) -> date:
    """그 달에 나가는 날 — 30일, 없으면 말일."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(DAY, last))


def parse_time(raw: Optional[str]) -> str:
    """`HH:MM` 으로 다듬는다. 예약이 고를 수 있는 폭(09~19시) 밖이면
    `ValueError` — **저장 자리에서 자른다**(`scheduled_send.check` 와 같은 폭)."""
    value = (raw or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", value)
    if not m:
        raise ValueError("자동 발송 시각을 읽을 수 없습니다 — 17:00 처럼 적으세요")
    hour, minute = int(m.group(1)), int(m.group(2))
    if minute > 59 or not (scheduled_send.EARLIEST_HOUR <= hour
                           < scheduled_send.LATEST_HOUR):
        raise ValueError(
            f"자동 발송 시각은 {scheduled_send.EARLIEST_HOUR:02d}:00~"
            f"{scheduled_send.LATEST_HOUR:02d}:00 안에서만 고를 수 있습니다")
    return f"{hour:02d}:{minute:02d}"


def _time_of(row) -> tuple:
    try:
        hhmm = parse_time(getattr(row, "monthly_time", None) or DEFAULT_TIME)
    except ValueError:
        hhmm = DEFAULT_TIME
    hour, minute = hhmm.split(":")
    return int(hour), int(minute)


def at_on(day: date, row) -> datetime:
    """그날 나가는 시각(이 프로세스 시간대)."""
    hour, minute = _time_of(row)
    return datetime(day.year, day.month, day.day, hour, minute).astimezone()


def next_run(row, now: Optional[datetime] = None) -> datetime:
    """다음에 나갈 시각. 이 달 시각이 지났으면 다음 달이다."""
    now = scheduled_send._aware(now or clock.now())
    at = at_on(run_day(now.year, now.month), row)
    if now < at:
        return at
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return at_on(run_day(year, month), row)


def label(at: datetime) -> str:
    """`10/30(금) 17:00` — 예약과 같은 모양."""
    return scheduled_send.label(at)


def month_key(day: date) -> int:
    return day.year * 100 + day.month


# ── 설정 ────────────────────────────────────────────────────────────────────

def _setting(db: Session):
    from . import startup_send
    return startup_send.setting(db)


def is_on(row) -> bool:
    """매월 자동 예약이 켜져 있는가. **메뉴가 켜져 있어야**(보낼 계정이 있어야)
    켜진 것이다 — 보낼 사람 없는 자동은 반쯤 켜진 상태다."""
    from . import startup_send
    return bool(startup_send.is_on(row) and getattr(row, "monthly_auto", 0))


# ── 이 달 회차 ──────────────────────────────────────────────────────────────

def _job_month(job: SendJob, batch_title: str) -> str:
    """이 회차가 어느 달치인가. 회차명에 `YYYY-MM` 이 있으면 그 달(화면의
    기본 회차명이 `… (스타트업 월간 발송 2026-10)` 이다), 없으면 만든 달."""
    found = _MONTH_IN_TITLE.search(batch_title or "")
    return found.group(1) if found else (job.created_at or "")[:7]


def month_job(db: Session, month: str) -> Optional[SendJob]:
    """그 달치 스타트업 회차(취소되지 않은 것). 없으면 `None`."""
    rows = db.execute(
        select(SendJob, DealBatch.title)
        .outerjoin(DealBatch, DealBatch.id == SendJob.batch_id)
        .where(SendJob.kind == STARTUP_SEND_KIND, SendJob.status != "canceled")
        .order_by(SendJob.id)
    ).all()
    for job, title in rows:
        if _job_month(job, title or "") == month:
            return job
    return None


def run_row(db: Session, day: date) -> Optional[AutoSendRun]:
    return db.execute(
        select(AutoSendRun).where(AutoSendRun.kind == RUN_KIND,
                                  AutoSendRun.ref_id == month_key(day))
    ).scalars().first()


def _claim(db: Session, day: date, user_id: int) -> Optional[AutoSendRun]:
    """이 달 자리를 잡는다. 이미 끝난 달이면 `None`.

    `empty`(0곳) 인 자리만 다시 잡을 수 있다 — 그날 방 이름을 넣으면 서야 한다.
    """
    row = run_row(db, day)
    if row is None:
        row = AutoSendRun(kind=RUN_KIND, ref_id=month_key(day), user_id=user_id,
                          day=day.isoformat(), status=STATUS_CLAIMED)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None
        return row
    if row.status != STATUS_EMPTY:
        return None
    done = db.execute(
        text("UPDATE auto_send_runs SET status=:c WHERE id=:id AND status=:e"),
        {"c": STATUS_CLAIMED, "id": row.id, "e": STATUS_EMPTY})
    db.commit()
    if done.rowcount == 0:
        return None
    db.refresh(row)
    return row


def _finish(db: Session, row: AutoSendRun, status: str, *,
            job_id: Optional[int] = None, error: str = "") -> dict:
    row.status = status
    row.job_id = job_id
    row.error = error or None
    db.commit()
    return {"status": status, "job_id": job_id, "error": error}


# ── 세우기 ──────────────────────────────────────────────────────────────────

def run_once(db: Session, now: Optional[datetime] = None) -> dict:
    """오늘이 그날이면 이 달 목록을 세운다. 아니면 아무것도 안 한다.

    돌려주는 `status` 는 무엇을 했는가다 — `off`/`not_today`/`too_early`/
    `too_late`/`done`(이미 처리한 달) 이면 아무것도 바꾸지 않았다.
    """
    from fastapi import BackgroundTasks, HTTPException

    from ..routers.deals import MODE_STARTUP, SendRequest, create_send_list
    from . import cadence, ir_monthly, startup_send

    now = scheduled_send._aware(now or clock.now())
    row = _setting(db)
    if not is_on(row):
        return {"status": "off"}
    today = now.date()
    if today != run_day(today.year, today.month):
        return {"status": "not_today"}
    if now.hour < PREPARE_HOUR:
        return {"status": "too_early"}
    at = at_on(today, row)
    if now >= at:
        # 시각이 지나도록 못 세웠다(서버가 멈춰 있었다 등). 늦게 세우지 않는다.
        return {"status": "too_late"}

    sender = db.get(User, row.user_id)
    if not startup_send.may_send(db, sender):
        return {"status": "off"}

    claim = _claim(db, today, sender.id)
    if claim is None:
        return {"status": "done"}

    month = ir_monthly.this_month()
    existing = month_job(db, month)
    if existing is not None:
        log.info("스타트업 월간 자동 발송 — %s 회차가 이미 있습니다(#%s)",
                 month, existing.id)
        return _finish(db, claim, STATUS_EXISTS, job_id=existing.id,
                       error=f"이 달 회차가 이미 있어 세우지 않았습니다 (#{existing.id})")

    ids = startup_send.sendable_ids(db, month)
    if not ids:
        log.warning("스타트업 월간 자동 발송 — %s 보낼 곳이 0곳입니다", month)
        return _finish(db, claim, STATUS_EMPTY,
                       error="보낼 수 있는 곳이 0곳입니다 — 대표 카톡방 이름·요청을 확인하세요")

    try:
        made = create_send_list(
            SendRequest(contact_ids=ids, mode=MODE_STARTUP, month=month,
                        draft=True,
                        title=cadence.default_batch_title(
                            db, label=f"{startup_send.LABEL} {month} 자동"),
                        scheduled_at=at.isoformat(timespec="seconds")),
            BackgroundTasks(), db=db, user=sender)
    except HTTPException as exc:
        db.rollback()
        log.warning("스타트업 월간 자동 발송 — 못 세웠습니다: %s", exc.detail)
        claim = run_row(db, today)
        return _finish(db, claim, STATUS_FAILED, error=str(exc.detail))

    log.info("스타트업 월간 자동 발송 — %s %s곳, 회차 %s, 예약 %s",
             month, len(ids), made["job_id"], at.isoformat())
    return _finish(db, claim, STATUS_READY, job_id=made["job_id"]) | {
        "count": len(ids)}


# ── 화면 ────────────────────────────────────────────────────────────────────

def _sendable_count(db: Session, month: str) -> int:
    from . import startup_send
    try:
        return len(startup_send.sendable_ids(db, month))
    except Exception:  # noqa: BLE001 - 세는 데 실패해도 설정 화면은 떠야 한다
        log.exception("스타트업 월간 자동 발송 — 곳 수를 세지 못했습니다")
        return 0


def status(db: Session, now: Optional[datetime] = None) -> dict:
    """팀 현황·발송 화면이 읽는 한 덩이. **화면은 판정하지 않는다.**"""
    now = scheduled_send._aware(now or clock.now())
    row = _setting(db)
    on = is_on(row)
    hour, minute = _time_of(row)
    out = {
        "on": on,
        "enabled": bool(row and getattr(row, "monthly_auto", 0)),
        "time": f"{hour:02d}:{minute:02d}",
        "day": DAY,
        "prepare_hour": PREPARE_HOUR,
        "earliest": scheduled_send.EARLIEST_HOUR,
        "latest": scheduled_send.LATEST_HOUR,
        "next_label": "",
        "next_count": 0,
        "this_month": None,
    }
    if not on:
        return out
    nxt = next_run(row, now)
    out["next_label"] = label(nxt)
    out["next_count"] = _sendable_count(db, f"{nxt.year:04d}-{nxt.month:02d}")
    run = run_row(db, now.date())
    if run is not None:
        out["this_month"] = {"status": run.status, "job_id": run.job_id,
                             "error": run.error or ""}
    return out


def today_items(db: Session, user: User, now: Optional[datetime] = None) -> list:
    """보내는 계정의 오늘 할 일에 **못 세운 달**을 적는다.

    선 목록은 예약이라 `scheduled_send.standing_for` 가 이미 띄운다 — 여기서
    또 적지 않는다.
    """
    now = scheduled_send._aware(now or clock.now())
    row = _setting(db)
    if not is_on(row) or row.user_id != user.id:
        return []
    run = run_row(db, now.date())
    if run is None or run.status not in (STATUS_EMPTY, STATUS_FAILED):
        return []
    return [{"error": run.error or "", "status": run.status}]


# ── 실 ──────────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """웹 프로세스 안에서 5분마다 깨어나 본다 — 예약 발송과 같은 얼개."""
    global _SCHEDULER
    if _SCHEDULER is not None and _SCHEDULER.is_alive():
        return

    def loop() -> None:
        while True:
            _time.sleep(CHECK_INTERVAL_SEC)
            db = SessionLocal()
            try:
                run_once(db)
            except Exception:  # noqa: BLE001 - 실이 죽으면 다음 달이 조용히 멎는다
                log.exception("스타트업 월간 자동 발송을 살피다 실패했습니다")
            finally:
                db.close()

    _SCHEDULER = threading.Thread(target=loop, daemon=True,
                                  name="startup-monthly")
    _SCHEDULER.start()

