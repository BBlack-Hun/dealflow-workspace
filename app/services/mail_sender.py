"""메일 발송 실행 — 서버가 직접 보낸다.

카톡과 **나가는 길이 다르다**. 카톡은 각자 PC 의 발송 프로그램이 창을 눌러 보내지만
메일은 서버가 SMTP 로 바로 보낸다. PC 를 켜 둘 필요가 없고 방 제목을 맞출 일도 없다.

발송 목록을 만든 요청 안에서 다 보내면 안 된다. 110명이면 몇 분이 걸려 요청이
끊긴다. 그래서 목록만 만들고 **뒤에서 한 건씩** 보낸다 — 진행 화면은 카톡과
똑같이 폴링해서 결과를 본다.

한 건 실패가 나머지를 막지 않는다. 주소가 틀린 한 사람 때문에 109명이 못 받는 것이
가장 나쁜 결과다.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import SendItem, SendJob
from . import mailer

log = logging.getLogger(__name__)

# 한 통 보내고 쉬는 시간. 한꺼번에 쏟으면 메일 서버가 막는다.
GAP_SEC = 1.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def send_job(job_id: int, gap_sec: float = GAP_SEC) -> dict:
    """이 잡의 **메일 건**을 한 건씩 보낸다. 백그라운드에서 부른다.

    자기 세션을 연다 — 요청이 끝난 뒤에도 도는 일이라 요청 세션을 쓰면 안 된다.
    """
    db = SessionLocal()
    try:
        return _run(db, job_id, gap_sec)
    finally:
        db.close()


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

    sent = failed = 0
    for index, item in enumerate(items):
        db.refresh(item)
        if item.status != "pending":
            continue        # 그 사이 중단됐다
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
        _recount(db, job)
        db.commit()

        if gap_sec and index < len(items) - 1:
            time.sleep(gap_sec)

    _finish(db, job)
    db.commit()
    return {"sent": sent, "failed": failed, "detail": f"{sent}건 발송 · {failed}건 실패"}


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
    address = (getattr(contact, "email", "") or "").strip()
    if not address:
        return "메일 주소가 없습니다"
    if "@" not in address or address.startswith("@") or address.endswith("@"):
        return f"메일 주소 형식이 이상합니다: {address}"
    return None
