"""발송 안전장치 — **발송기에게 내주는 자리에서** 막는다.

자동화가 사람 확인 없이 돌기 시작하면, 지금까지 사람이 눈으로 막아 주던 것들을
서버가 대신 막아야 한다. 여기 모은 것은 셋이다.

1. **보내는 시간** — 09:00~19:00 밖에는 문구를 보내는 잡을 내주지 않는다.
2. **계정마다 하루 상한** — 그날 그 계정으로 나간 수가 상한에 닿으면 더 내주지
   않는다.
3. **자동 회차가 실패하거나 시각을 놓치면 알린다** — 오늘 할 일과 메일로.

## 왜 내주는 자리(`agent_api.poll`)인가  ★

예약을 푸는 쪽(`scheduled_send`)은 이미 09~19시 안에서만 푼다. 그런데 풀린 뒤
`queued` 로 서 있는 회차는 **발송기가 켜지는 순간** 나간다 — PC 가 21시에
켜지면 21시에 나간다(지난 60일 동안 20시대에 265통, 0~3시에 7통이 나갔다).
막을 수 있는 마지막 자리는 발송기가 잡을 집어가는 순간이고, 그 자리는
`poll` 하나뿐이다. 여기서 막으면 낡은 발송기를 쓰는 PC 에도 그대로 걸린다 —
발송기를 다시 배포하지 않아도 된다.

**못 내주는 잡은 큐에 그대로 둔다.** 실패로 닫으면 사람이 다시 만들어야 한다.
시간이 되면(다음 날 09시) 그대로 이어 나간다 — 자료 파일을 못 붙이는 발송기
에게 잡을 안 내주는 것(`poll` 의 `can_attach`)과 같은 방식이다.

## 무엇을 막고 무엇을 안 막나

`GATED_KINDS` — **받는 사람에게 문구가 가는** 잡 전부다(딜소개 · IR 자료 ·
소싱 제안 · 스타트업 월간 발송 · 스타트업 안내 카톡).

- 방 확인(`verify_room`, 스타트업 방 **후보 찾기** 포함)은 막지 않는다 — 카톡에서
  방 제목을 찾아볼 뿐 아무것도 보내지 않는다.
- 시험 발송(`test_send`)도 막지 않는다 — 가는 곳이 우리 시험방 하나뿐이다
  (`models.TEST_SEND_KIND`). 밤에 발송기를 설치하며 시험을 눌렀는데 다음 날
  아침 9시에 시험 문구가 나가면 그것이 더 헷갈린다.

## 시간의 폭은 **한 곳**에서 온다

`scheduled_send.EARLIEST_HOUR`~`LATEST_HOUR`(= `auto_send` 의 그 값). 예약을
고를 수 있는 폭과 실제로 나갈 수 있는 폭이 다르면, 고를 수는 있는데 안 나가는
시각이 생긴다.

## 하루 상한은 **서버가** 센다

발송기의 `?cap=` 은 **잡 하나**에 몇 건을 받을지다(계정 보호를 위한 1회 상한).
하루 총량은 아니다 — 60건짜리 잡을 하루에 다섯 번 받으면 300건이 나간다.
그날 몇 건이 나갔는지는 서버만 안다(`send_items.sent_at`). 그래서 상한도
서버가 지킨다: 남은 만큼만 내주고, 다 쓰면 그 계정의 문구 잡을 내주지 않는다.
남은 사람은 큐에 서 있다가 다음 날 이어 나간다(`agent_api._settle` 이 남은 건을
`queued` 로 되돌린다).

**나간 것(`sent`)만 센다.** 실패의 대부분은 방을 못 찾은 것이라 카톡에 아무것도
나가지 않았다. 실패까지 세면 방 이름이 틀린 사람이 많은 날 정작 보낼 사람에게
못 보낸다.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from .. import clock
from ..models import (SEND_KINDS, STARTUP_MSG_KIND, STARTUP_SEND_KIND,
                      AutoSendRun, SendItem, SendJob, User)
from . import scheduled_send

log = logging.getLogger(__name__)

#: **문구가 받는 사람에게 가는** 잡 종류. 시간·하루 상한이 여기에만 걸린다.
#: 방 확인과 시험 발송이 빠진 까닭은 머리말.
GATED_KINDS = tuple(SEND_KINDS) + (STARTUP_SEND_KIND, STARTUP_MSG_KIND)

#: 보내는 시간의 폭 — 예약을 고를 수 있는 폭과 **같은 값**이다.
EARLIEST_HOUR = scheduled_send.EARLIEST_HOUR
LATEST_HOUR = scheduled_send.LATEST_HOUR

#: 계정마다 하루 상한의 기본값. 지난 두 달 동안 한 계정이 하루에 보낸 것이
#: 가장 많은 날 139통이었다 — 지금 쓰는 만큼은 막지 않고, 자동화가 잘못 돌아
#: 몇 배로 나가는 것은 막는 자리다.
DEFAULT_DAILY_CAP = 200
#: 팀 현황에서 고를 수 있는 폭. 0 은 받지 않는다 — 0 이면 그 계정의 발송이
#: 조용히 전부 멈추는데, 멈추려던 것인지 잘못 넣은 것인지 화면이 가릴 수 없다.
MIN_DAILY_CAP = 1
MAX_DAILY_CAP = 1000

#: 오늘 할 일에 **실패한 자동 회차**를 며칠 세워 둘까. 사흘이면 주말을 넘긴다.
ALERT_DAYS = 3

#: 알림 메일 받는 곳(쉼표로 여럿). 비어 있으면 **보내는 주소 자신**에게 보낸다 —
#: 팀 메일함이고, 관리자가 보는 곳이다. 계정 표에는 메일 칸이 없다.
ALERT_EMAIL_ENV = "DEALFLOW_ALERT_EMAIL"

REASON_FAILED = "failed"
REASON_MISSED = "missed"


# ── 보내는 시간 ──────────────────────────────────────────────────────────────

def window_open(now: Optional[datetime] = None) -> bool:
    """지금 문구를 보내도 되는 시각인가 — 09:00 이상 19:00 미만.

    요일은 보지 않는다. 예약이 요일을 막지 않는 것과 같다(`scheduled_send`
    머리말) — 토요일에 보내려면 사람이 그날 누르면 된다.
    """
    now = now or clock.now()
    return EARLIEST_HOUR <= now.hour < LATEST_HOUR


def window_label() -> str:
    return f"{EARLIEST_HOUR:02d}:00~{LATEST_HOUR:02d}:00"


# ── 하루 상한 ────────────────────────────────────────────────────────────────

def clamp_daily_cap(value) -> int:
    """팀 현황에서 넣은 값을 폭 안으로 자른다. 못 읽으면 기본값."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAILY_CAP
    return max(MIN_DAILY_CAP, min(number, MAX_DAILY_CAP))


def daily_cap(user: Optional[User]) -> int:
    """이 계정의 하루 상한. 값이 비었으면 기본값이다."""
    raw = getattr(user, "daily_send_cap", None) if user is not None else None
    return clamp_daily_cap(raw) if raw else DEFAULT_DAILY_CAP


def sent_today(db: Session, user_id: int, day: Optional[date] = None) -> int:
    """그날 이 계정으로 **카톡으로 나간** 문구 수.

    `sent_at` 은 지역 시각 문자열이라(`clock.now_iso`) 앞 10자가 곧 그날이다.
    메일 건은 세지 않는다 — 서버가 SMTP 로 보내 카톡 계정과 상관이 없다.
    """
    day = day or clock.today()
    start = day.isoformat()
    end = (day + timedelta(days=1)).isoformat()
    return int(db.execute(
        select(func.count(SendItem.id))
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.user_id == user_id,
               SendJob.kind.in_(GATED_KINDS),
               SendItem.status == "sent",
               SendItem.channel != "email",
               SendItem.sent_at >= start,
               SendItem.sent_at < end)
    ).scalar_one())


def remaining_today(db: Session, user: User, day: Optional[date] = None) -> int:
    """오늘 이 계정으로 더 보낼 수 있는 수. 0 아래로 내려가지 않는다."""
    return max(0, daily_cap(user) - sent_today(db, user.id, day))


@dataclass(frozen=True)
class Gate:
    """`poll` 한 번이 읽는 판정. **한 번 세어 두 곳에 쓴다** — 막을지와 몇 건
    내줄지를 따로 세면, 그 사이에 결과가 올라와 둘이 다른 수를 볼 수 있다."""

    #: 지금 내주면 안 되는 잡 종류. 막을 것이 없으면 빈 튜플.
    blocked: tuple
    #: 오늘 이 계정으로 더 보낼 수 있는 수.
    left: int


def gate(db: Session, user: Optional[User],
         now: Optional[datetime] = None) -> Gate:
    """지금 이 계정에 **무엇을 몇 건까지** 내줄 수 있나.

    `poll` 이 발송기가 밝힌 종류에서 `blocked` 를 빼고, 문구 잡이면 `left` 만큼만
    내준다. 막는 까닭은 둘 — 시간 밖이거나, 오늘 상한을 다 썼거나. 둘 다 같은
    종류(`GATED_KINDS`)를 막는다. 계정을 못 찾으면 막는다(모르면 안 보낸다).
    """
    now = now or clock.now()
    if user is None or not window_open(now):
        # 시간 밖이면 셀 것도 없다 — 발송기는 몇 초마다 묻는다.
        return Gate(blocked=GATED_KINDS, left=0)
    left = remaining_today(db, user, now.date())
    return Gate(blocked=GATED_KINDS if left <= 0 else (), left=left)


def describe(db: Session, job: SendJob, now: Optional[datetime] = None) -> dict:
    """진행 화면이 읽는 한 덩이 — 이 회차가 지금 왜 안 나가는지까지.

    **화면은 판정하지 않는다.** 문장도 여기서 만든다(`scheduled_send.describe`
    와 같은 까닭: 화면마다 지으면 두 벌이 되고, 어긋나도 아무도 모른다).
    """
    now = now or clock.now()
    gated = job.kind in GATED_KINDS
    owner = db.get(User, job.user_id)
    cap = daily_cap(owner)
    used = sent_today(db, job.user_id, now.date()) if gated else 0
    left = max(0, cap - used)
    is_open = window_open(now)
    waiting = job.status == "queued" and any(
        i.status == "pending" and i.channel != "email" for i in job.items)

    sentence = ""
    if gated:
        sentence = f"오늘 남은 발송 한도 {left}/{cap}건"
        if waiting and not is_open:
            sentence = (f"지금은 보내는 시간({window_label()})이 아닙니다 — "
                        f"큐에 서서 기다리다 {EARLIEST_HOUR:02d}:00 에 나갑니다 · "
                        + sentence)
        elif waiting and left <= 0:
            sentence = (f"오늘 발송 한도({cap}건)를 다 썼습니다 — 남은 건은 "
                        f"내일 {EARLIEST_HOUR:02d}:00 에 이어 나갑니다")
    return {"gated": gated, "open": is_open, "window": window_label(),
            "cap": cap, "sent_today": used, "remaining": left,
            "held": bool(gated and waiting and (not is_open or left <= 0)),
            "sentence": sentence}


def status(db: Session, today: Optional[date] = None) -> dict:
    """팀 현황의 `발송 안전장치` 판이 읽는 값."""
    from .. import deps

    day = today or clock.today()
    users = db.execute(
        select(User).where(User.is_active == 1).order_by(User.id)
    ).scalars().all()
    rows = []
    for user in users:
        if not deps.sends_deals(user):
            continue
        cap = daily_cap(user)
        used = sent_today(db, user.id, day)
        rows.append({"id": user.id, "name": user.name, "cap": cap,
                     "sent_today": used, "remaining": max(0, cap - used)})
    return {"window": window_label(), "earliest": EARLIEST_HOUR,
            "latest": LATEST_HOUR, "default_cap": DEFAULT_DAILY_CAP,
            "min_cap": MIN_DAILY_CAP, "max_cap": MAX_DAILY_CAP,
            "rows": rows}


# ── 자동 회차 알림 ───────────────────────────────────────────────────────────

def auto_job_ids(db: Session, job_ids=None) -> set:
    """**스케줄러가 세운** 회차 번호들.

    자동으로 서는 회차는 전부 `auto_send_runs.job_id` 로 이어져 있다 —
    미팅 후기 자동 준비(`auto_send`)도, 스타트업 월간 자동 예약
    (`startup_monthly`)도 목록을 세우기 **전에** 그 표에 자리를 잡고 세운 뒤
    회차 번호를 적는다. 앞으로 붙을 자동화도 같은 표를 쓴다(`auto_send` 머리말의
    `다음 종류를 붙일 자리`). 그래서 회차에 따로 표시를 달지 않고 이것을 읽는다.

    `exists`(이 달 회차가 이미 있어 세우지 않았다)는 빼고 센다 — 그 줄은 사람이
    세운 회차를 가리킬 뿐이다(`startup_monthly.STATUS_EXISTS`).
    """
    query = select(AutoSendRun.job_id).where(AutoSendRun.job_id.isnot(None),
                                             AutoSendRun.status != "exists")
    if job_ids is not None:
        ids = list(job_ids)
        if not ids:
            return set()
        query = query.where(AutoSendRun.job_id.in_(ids))
    return set(db.execute(query).scalars().all())


def is_auto(db: Session, job: SendJob) -> bool:
    return job.id in auto_job_ids(db, [job.id])


def alert_recipients() -> List[str]:
    """알림 메일을 받을 곳. `DEALFLOW_ALERT_EMAIL` → 없으면 보내는 주소 자신."""
    from . import mailer

    raw = os.environ.get(ALERT_EMAIL_ENV, "")
    picked = [p.strip() for p in raw.split(",") if p.strip()]
    if picked:
        return picked
    sender = mailer.load_settings().from_address
    return [sender] if sender else []


def _subject_body(db: Session, job: SendJob, reason: str) -> tuple:
    owner = db.get(User, job.user_id)
    who = owner.name if owner else f"#{job.user_id}"
    failed = sum(1 for i in job.items if i.status == "failed")
    sent = sum(1 for i in job.items if i.status == "sent")
    pending = sum(1 for i in job.items if i.status == "pending")
    if reason == REASON_MISSED:
        at = scheduled_send.scheduled_at(job)
        when = scheduled_send.label(at) if at else "-"
        subject = f"[딜플로우] 자동 회차 #{job.id} 가 예약 시각을 놓쳤습니다"
        lines = [f"{who} 님 계정의 자동 회차 #{job.id} 가 예약 시각({when})에 "
                 "나가지 못했습니다.",
                 "발송 프로그램이 그 시각에 연결되어 있지 않았던 것으로 보입니다.",
                 f"아직 아무것도 나가지 않았습니다 — 대기 {pending}건.",
                 "저절로 나가지 않습니다. 회차 화면에서 다시 예약하거나 [발송 시작] 을 누르세요."]
    else:
        subject = f"[딜플로우] 자동 회차 #{job.id} 에 실패 {failed}건"
        lines = [f"{who} 님 계정의 자동 회차 #{job.id} 가 끝났습니다 — "
                 f"성공 {sent}건 · 실패 {failed}건.",
                 "실패 사유는 회차 화면의 표에 있습니다(대부분 카톡방을 못 찾은 경우입니다)."]
    lines.append(f"회차 화면: /jobs/{job.id}")
    return subject, "\n".join(lines)


def _send_alert_mail(subject: str, body: str) -> None:
    """메일 한 통씩. **실패해도 올리지 않는다** — 알림이 발송을 막으면 안 된다."""
    from . import mailer

    if not mailer.is_configured():
        log.info("메일 설정이 없어 자동 회차 알림 메일을 건너뜁니다: %s", subject)
        return
    for to in alert_recipients():
        try:
            mailer.send_mail(to, subject, body)
        except Exception:  # noqa: BLE001 - 알림 하나 때문에 실이 죽으면 안 된다
            log.exception("자동 회차 알림 메일을 보내지 못했습니다 (%s)", subject)


def _dispatch(func, *args) -> None:
    """메일은 **따로 띄운 실**에서 보낸다. SMTP 가 20초를 붙잡고 있어도 발송기
    보고(`job_status_update`)와 예약 실이 그동안 멈추지 않게.

    검사는 이 함수를 바꿔 끼워 그 자리에서 돌린다.
    """
    threading.Thread(target=func, args=args, daemon=True,
                     name="auto-job-alert").start()


def mail_admins(subject: str, body: str) -> None:
    """관리자에게 짧은 메일 한 통 — 자동 회차 알림과 **같은 곳, 같은 길**.

    받는 곳은 `alert_recipients`, 보내는 것은 따로 띄운 실이다. 메일 설정이
    없으면 아무것도 안 한다. 딜 소싱 메일 확인의 요약(`sourcing_mail.announce`)
    이 쓴다.
    """
    _dispatch(_send_alert_mail, subject, body)


def notify(db: Session, job: SendJob, reason: str) -> bool:
    """자동 회차가 실패로 끝났거나 시각을 놓쳤다 — **관리자에게 메일 한 통.**

    자동이 아닌 회차는 아무것도 안 한다(사람이 보고 누른 회차는 그 사람이 진행
    화면을 보고 있다). 같은 회차로 두 번 보내지 않는다: `send_jobs.alerted_at`
    이 빈 줄만 원자적으로 집는다(`agent_api.poll` 의 선점과 같은 방식). 사람이
    회차를 다시 살리면(`jobs._requeue`) 그 칸이 비워져, 그다음 결과로 다시
    알릴 수 있다.

    오늘 할 일은 따로 적지 않는다 — 회차의 상태를 그대로 읽는다(`alerts_for`).
    """
    if not is_auto(db, job):
        return False
    done = db.execute(
        text("UPDATE send_jobs SET alerted_at=:t "
             "WHERE id=:id AND alerted_at IS NULL"),
        {"t": clock.now_iso(), "id": job.id})
    db.commit()
    if done.rowcount == 0:
        return False
    subject, body = _subject_body(db, job, reason)
    log.warning("%s", subject)
    _dispatch(_send_alert_mail, subject, body)
    return True


def alerts_for(db: Session, user: User, today: Optional[date] = None,
               now: Optional[datetime] = None) -> List[dict]:
    """오늘 할 일에 세울 **자동 회차의 사고**. 주인과 관리자에게 보인다.

    - 실패가 있는 채로 끝난 자동 회차(`done_with_errors`) — 끝난 지 `ALERT_DAYS`
      일 안. 사람이 [실패 재시도] 로 다 살리면 상태가 바뀌어 저절로 사라진다.
    - 예약 시각을 놓친 자동 회차 — **관리자에게만** 여기서 세운다. 주인에게는
      이미 `scheduled_send.standing_for` 가 같은 회차를 세운다(두 줄이 되면
      같은 일을 두 번 하라는 것으로 읽힌다).
    """
    today = today or clock.today()
    now = now or clock.now()
    admin = user.role == "admin"
    since = (today - timedelta(days=ALERT_DAYS - 1)).isoformat()

    query = select(SendJob).where(or_(
        and_(SendJob.status == "done_with_errors", SendJob.finished_at >= since),
        SendJob.status == "draft"))
    if not admin:
        query = query.where(SendJob.user_id == user.id)
    rows = db.execute(query.order_by(SendJob.id)).scalars().all()
    autos = auto_job_ids(db, [j.id for j in rows])

    out = []
    for job in rows:
        if job.id not in autos:
            continue
        owner = db.get(User, job.user_id)
        who = owner.name if owner else f"#{job.user_id}"
        if job.status == "done_with_errors":
            failed = sum(1 for i in job.items if i.status == "failed")
            out.append({"job_id": job.id, "reason": REASON_FAILED,
                        "title": "자동 회차에 실패가 있습니다",
                        "detail": f"{who} · #{job.id} 실패 {failed}건 — 사유를 보고 다시 보내세요",
                        "count": failed})
        elif (job.user_id != user.id
              and scheduled_send.state(job, now) == scheduled_send.STATE_EXPIRED):
            out.append({"job_id": job.id, "reason": REASON_MISSED,
                        "title": "자동 회차가 예약 시각을 놓쳤습니다",
                        "detail": f"{who} · {scheduled_send.sentence(job, now)}",
                        "count": scheduled_send.pending_count(job)})
    return out
