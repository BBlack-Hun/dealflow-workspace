"""메일 발송 실행 — 서버가 직접 보낸다.

카톡과 **나가는 길이 다르다**. 카톡은 각자 PC 의 발송 프로그램이 창을 눌러 보내지만
메일은 서버가 SMTP 로 바로 보낸다. PC 를 켜 둘 필요가 없고 방 제목을 맞출 일도 없다.

발송 목록을 만든 요청 안에서 다 보내면 안 된다. 110명이면 몇 분이 걸려 요청이
끊긴다. 그래서 목록만 만들고 **뒤에서 한 건씩** 보낸다 — 진행 화면은 카톡과
똑같이 폴링해서 결과를 본다.

한 건 실패가 나머지를 막지 않는다. 주소가 틀린 한 사람 때문에 109명이 못 받는 것이
가장 나쁜 결과다.

## 메일도 보내는 시간(09~19시)과 하루 상한을 지킨다

카톡은 발송기에게 내주는 자리(`agent_api.poll`)에서 막는데, 메일은 그 자리를
지나지 않는다. 그래서 **한 통 보내기 직전마다** 같은 관문을 본다
(`send_guard.window_open` · `remaining_today(mail=True)` — 메일끼리 센다).
밖이면 실패로 닫지 않고 **대기로 둔다**(그 건에 까닭을 적는다 — `HELD`). 예약
실이 30초마다 깨어 보내는 시간이 열리면 거기서 이어 보낸다(`resume_waiting`).
테스트 서버에서 시간 관문을 끈 스위치(`send_window.off`)도 그대로 먹는다.

## 같은 사람에게 두 번 나가지 않게

보내기 전에 그 건의 **자리를 먼저 잡는다**(`pending` → `sending`, 원자적). 같은
회차를 두 실이 함께 돌아도 한 건은 한 번만 나간다. 보내는 도중 서버가 내려가
`sending` 으로 남은 건은 저절로 다시 보내지 않는다 — 나갔는지 모르는 건을 또
보내는 것보다 사람이 보고 고르는 쪽이 낫다.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, exists, select, text
from sqlalchemy.orm import Session

from .. import clock
from ..db import SessionLocal
from ..models import SendItem, SendJob, User
from . import mailer, send_guard, sourcing_sync

log = logging.getLogger(__name__)

# 한 통 보내고 쉬는 시간. 한꺼번에 쏟으면 메일 서버가 막는다.
GAP_SEC = 1.0

#: 시간 · 하루 상한에 걸려 **기다리는** 메일 건에 적는 말. 진행 화면의 그 줄에
#: 그대로 보이고, 다음 창에서 이어 보낼 건을 고르는 표시도 된다(`resume_waiting`)
#: — 서버가 내려가 대기로 남은 옛 건까지 저절로 나가면 안 된다(그쪽은 사람이
#: [이어 보내기] 로 고른다).
HELD_WINDOW = "보내는 시간이 아니라 기다립니다 — 보내는 시간이 되면 이어 나갑니다"
HELD_CAP = "오늘 메일 발송 한도를 다 써서 기다립니다 — 다음 날 보내는 시간에 이어 나갑니다"
HELD = (HELD_WINDOW, HELD_CAP)

#: 지금 이 프로세스에서 돌고 있는 회차(번호 → 실 수). 이어 보내기 실이 같은
#: 회차를 겹쳐 띄우지 않게 본다. 겹쳐도 한 건은 한 번만 나간다(`_claim`).
_ACTIVE: dict = {}
_ACTIVE_LOCK = threading.Lock()


def _now() -> str:
    # 저장용 시각은 `app/clock.py` 하나에서만 만든다 — 왜 지역시간인지는 그쪽에.
    return clock.now_iso()


def send_job(job_id: int, gap_sec: float = GAP_SEC) -> dict:
    """이 잡의 **메일 건**을 한 건씩 보낸다. 백그라운드에서 부른다.

    자기 세션을 연다 — 요청이 끝난 뒤에도 도는 일이라 요청 세션을 쓰면 안 된다.
    """
    with _ACTIVE_LOCK:
        _ACTIVE[job_id] = _ACTIVE.get(job_id, 0) + 1
    db = SessionLocal()
    try:
        return _run(db, job_id, gap_sec)
    finally:
        db.close()
        with _ACTIVE_LOCK:
            _ACTIVE[job_id] -= 1
            if _ACTIVE[job_id] <= 0:
                del _ACTIVE[job_id]


def _busy(job_id: int) -> bool:
    with _ACTIVE_LOCK:
        return job_id in _ACTIVE


def _run(db: Session, job_id: int, gap_sec: float) -> dict:
    job = db.get(SendJob, job_id)
    if job is None:
        return {"sent": 0, "failed": 0, "detail": "잡을 찾을 수 없습니다"}

    items = db.execute(
        select(SendItem).where(SendItem.job_id == job_id,
                               SendItem.channel == "email",
                               SendItem.status == "pending")
        .order_by(SendItem.id)
    ).scalars().all()
    if not items:
        return {"sent": 0, "failed": 0, "detail": "보낼 메일이 없습니다"}

    settings = mailer.load_settings()
    if not settings.configured:
        # 설정이 없으면 전부 실패로 남긴다 — 조용히 pending 으로 두면
        # 화면에서는 '보내는 중'으로 영원히 멈춰 있다.
        for item in items:
            _fail(item, "메일 서버 설정이 없습니다")
        _recount(db, job)
        db.commit()
        return {"sent": 0, "failed": len(items), "detail": "메일 서버 설정이 없습니다"}

    gated = job.kind in send_guard.GATED_KINDS
    owner = db.get(User, job.user_id)
    sent = failed = 0
    for index, item in enumerate(items):
        db.refresh(item)
        if item.status != "pending":
            continue        # 그 사이 중단됐다
        # ★ 보내는 시간 · 하루 상한 — **한 통마다** 본다(19시를 넘기는 회차도
        #   그 자리에서 멈춘다). 밖이면 남은 건을 대기로 두고 나간다.
        why = _held(db, owner) if gated else None
        if why:
            _hold(db, job, why)
            return {"sent": sent, "failed": failed, "held": _pending(job),
                    "detail": f"{sent}건 발송 · {failed}건 실패 · 나머지는 대기"}
        if not _claim(db, item):
            continue        # 다른 실이 먼저 잡았다 — 두 번 보내지 않는다
        if not job.started_at:
            # 나가기 시작한 회차 — 시간 · 상한에 걸려 이어 나가는 중이지 예약 시각을
            # 놓친 것이 아니다(`scheduled_send.missed` 가 `started_at` 을 본다).
            job.started_at = _now()
        try:
            mailer.send_mail(item.room_name, item.subject or "딜 소개",
                             item.message, settings=settings)
        except Exception as exc:      # noqa: BLE001 - 한 건 실패가 나머지를 막지 않는다
            _fail(item, _reason(exc))
            failed += 1
            log.warning("메일 발송 실패 item=%s: %s", item.id, exc)
        else:
            item.status = "sent"
            item.sent_at = _now()
            item.error = None
            sent += 1
            # 카톡과 같다 — 참여 안내가 나간 `제안 대기중` 줄 → `물어보는 중`.
            sourcing_sync.mark_invited(db, item, "mail_sender")
        _recount(db, job)
        db.commit()

        if gap_sec and index < len(items) - 1:
            time.sleep(gap_sec)

    _finish(db, job)
    db.commit()
    return {"sent": sent, "failed": failed, "detail": f"{sent}건 발송 · {failed}건 실패"}


def _held(db: Session, owner: Optional[User],
          now: Optional[datetime] = None) -> Optional[str]:
    """지금 이 계정으로 메일을 보내면 안 되는 까닭. 보내도 되면 `None`.

    시간은 카톡과 **같은 관문**(`send_guard.window_open` — 테스트 서버 스위치까지)
    이고, 하루 상한은 같은 숫자를 메일끼리 센다. 계정을 모르면 보내지 않는다
    (`send_guard.gate` 와 같다).
    """
    now = now or clock.now()
    if not send_guard.window_open(now):
        return HELD_WINDOW
    if owner is None or send_guard.remaining_today(db, owner, now.date(), mail=True) <= 0:
        return HELD_CAP
    return None


def _hold(db: Session, job: SendJob, why: str) -> None:
    """남은 메일 건을 **대기 그대로** 두고 까닭을 적는다 — 실패로 닫지 않는다."""
    for item in job.items:
        if item.status == "pending" and item.channel == "email":
            item.error = why
    db.commit()
    log.info("메일 회차 %s — %s (대기 %s건)", job.id, why, _pending(job))


def _pending(job: SendJob) -> int:
    return sum(1 for i in job.items if i.status == "pending" and i.channel == "email")


def _claim(db: Session, item: SendItem) -> bool:
    """이 건의 자리를 잡는다(`pending` → `sending`). 이미 누가 잡았으면 거짓.

    `agent_api.poll` 의 잡 선점과 같은 방식 — 줄 수로 이긴 쪽만 보낸다.
    """
    done = db.execute(
        text("UPDATE send_items SET status='sending' "
             "WHERE id=:id AND status='pending'"), {"id": item.id})
    db.commit()
    if done.rowcount == 0:
        return False
    db.refresh(item)
    return True


def _dispatch(func, *args) -> None:
    """따로 띄운 실에서 보낸다 — 예약 실이 수십 통을 보내는 동안 멈춰 있지 않게.
    검사는 이 함수를 바꿔 끼워 그 자리에서 돌린다."""
    threading.Thread(target=func, args=args, daemon=True,
                     name="mail-resume").start()


def resume_waiting(db: Session, now: Optional[datetime] = None) -> list:
    """시간 · 하루 상한에 걸려 **기다리던** 메일 회차를 이어 보낸다. 띄운 회차 번호들.

    예약 실이 30초마다 부른다(`scheduled_send.start_scheduler`). 고르는 것은
    기다림 표시(`HELD`)가 붙은 대기 메일 건이 있는 `queued` 회차뿐이다 — [중단]
    · 정지로 닫힌 회차, 예약 시각을 놓쳐 `draft` 로 내려간 회차, 까닭 없이 대기로
    남은 옛 건은 건드리지 않는다. 이미 이 프로세스에서 돌고 있는 회차도 건너뛴다.
    """
    now = now or clock.now()
    if not send_guard.window_open(now):
        return []
    waiting = exists().where(and_(SendItem.job_id == SendJob.id,
                                  SendItem.channel == "email",
                                  SendItem.status == "pending",
                                  SendItem.error.in_(HELD)))
    ids = db.execute(select(SendJob.id).where(SendJob.status == "queued", waiting)
                     .order_by(SendJob.id)).scalars().all()
    out = []
    for job_id in ids:
        if _busy(job_id):
            continue
        job = db.get(SendJob, job_id)
        if _held(db, db.get(User, job.user_id), now):
            continue        # 오늘 한도를 다 쓴 계정 — 내일 이어 간다
        _dispatch(send_job, job_id)
        out.append(job_id)
    return out


def _fail(item: SendItem, reason: str) -> None:
    item.status = "failed"
    item.error = reason


def _reason(exc: Exception) -> str:
    """화면에 그대로 보여줄 실패 사유. 무엇을 고쳐야 하는지 알아야 한다."""
    import smtplib

    if isinstance(exc, mailer.MailerNotConfigured):
        return str(exc)
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "메일 서버 로그인 실패 — 계정·비밀번호를 확인하세요"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "받는 주소를 메일 서버가 거부했습니다 — 주소를 확인하세요"
    if isinstance(exc, ValueError):
        return str(exc)
    return f"메일 발송 실패: {exc}"


def _recount(db: Session, job: SendJob) -> None:
    job.sent = sum(1 for i in job.items if i.status == "sent")
    job.failed = sum(1 for i in job.items if i.status == "failed")


def _finish(db: Session, job: SendJob) -> None:
    """메일 건이 다 끝났으면 잡 상태를 맞춘다.

    카톡 건이 섞여 있으면 그쪽은 발송 프로그램이 처리하므로 건드리지 않는다.
    """
    if any(i.status == "pending" for i in job.items):
        return
    if job.status in ("canceled",):
        return
    job.status = "done" if job.failed == 0 else "done_with_errors"
    job.finished_at = _now()


def address_problem(contact) -> Optional[str]:
    """이 담당자에게 메일을 보낼 수 있는가. 못 보내면 사유를 돌려준다."""
    address = mailer.primary_email(getattr(contact, "email", ""))  # 보낼 주소(정)만 본다
    if not address:
        return "메일 주소가 없습니다"
    if "@" not in address or address.startswith("@") or address.endswith("@"):
        return f"메일 주소 형식이 이상합니다: {address}"
    return None
