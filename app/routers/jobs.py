"""Send-job progress JSON + controls (ROADMAP task 1.9, FEATURE_SPEC §5 ⑦~⑧)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import agent_status, get_current_user
from ..models import SendItem, SendJob, User
from ..services import mail_sender

router = APIRouter(prefix="/api", tags=["jobs"])


def _job_or_404(db: Session, job_id: int, user: User) -> SendJob:
    job = db.get(SendJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="발송 잡 없음")
    return job


def _viewable_job_or_404(db: Session, job_id: int, user: User) -> SendJob:
    """조회는 관리자에게도 열어 둔다. 재시도·취소 같은 **조작**은
    `_job_or_404` 를 그대로 쓴다 — 관리자가 실수로 남의 회차를 건드리면 안 된다."""
    job = db.get(SendJob, job_id)
    if job is None or (job.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="발송 잡 없음")
    return job


def _counts(job: SendJob) -> dict:
    pending = sum(1 for i in job.items if i.status == "pending")
    sending = sum(1 for i in job.items if i.status == "sending")
    sent = sum(1 for i in job.items if i.status == "sent")
    failed = sum(1 for i in job.items if i.status == "failed")
    canceled = sum(1 for i in job.items if i.status == "canceled")
    return {"pending": pending, "sending": sending, "sent": sent,
            "failed": failed, "canceled": canceled}


@router.get("/jobs/{job_id}")
def job_status(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Polled by the progress screen every 2s."""
    job = _viewable_job_or_404(db, job_id, user)
    return {
        "id": job.id,
        "status": job.status,
        "total": job.total,
        "counts": _counts(job),
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "items": [
            {
                "id": i.id,
                "contact_id": i.contact_id,
                "contact_name": i.recipient_name,
                "room_name": i.room_name,
                "status": i.status,
                "error": i.error,
                "retry_count": i.retry_count,
                "sent_at": i.sent_at,
            }
            for i in job.items
        ],
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """[중단] — stop the job; pending/sending items become canceled."""
    job = _job_or_404(db, job_id, user)
    if job.status in ("done", "done_with_errors", "canceled"):
        return {"status": job.status}
    job.status = "canceled"
    for item in job.items:
        if item.status in ("pending", "sending"):
            item.status = "canceled"
    db.commit()
    return {"status": job.status, "counts": _counts(job)}


@router.post("/jobs/{job_id}/retry")
def retry_failed(job_id: int, background: BackgroundTasks,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """실패 [재시도] — 실패 건을 다시 대기로 돌린다.

    카톡 건은 발송 프로그램이 다시 집어가고, 메일 건은 **서버가 다시 보낸다**.
    채널마다 나가는 길이 달라서 한쪽만 되돌리면 나머지가 영원히 대기로 남는다.
    """
    job = _job_or_404(db, job_id, user)
    failed_items = [i for i in job.items if i.status == "failed"]
    if not failed_items:
        raise HTTPException(status_code=400, detail="재시도할 실패 건이 없습니다")
    for item in failed_items:
        item.status = "pending"
        item.error = None
    job.status = "queued"
    job.finished_at = None
    db.commit()

    if any(i.channel == "email" for i in failed_items):
        background.add_task(mail_sender.send_job, job.id)
    return {"status": job.status, "requeued": len(failed_items)}


@router.get("/agent-status")
def get_agent_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Sidebar connection badge (FEATURE_SPEC §0.2) — 지금 선택된 사용자의 기기 기준."""
    return agent_status(db, user.id)
