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


def _requeue(db: Session, job: SendJob, items: list[SendItem],
             background: BackgroundTasks) -> dict:
    """고른 건들을 다시 대기로 돌리고 **채널마다 제 길에** 태운다.

    카톡 건은 발송 프로그램이 다시 집어가고, 메일 건은 **서버가 다시 보낸다**.
    채널마다 나가는 길이 달라서 한쪽만 되돌리면 나머지가 영원히 대기로 남는다.

    실패 재시도와 취소분 재발송이 이 한 곳을 함께 쓴다 — 되살리는 절차를 두 벌로
    두면 한쪽만 고쳐져 어긋난다(카톡은 되살아나는데 메일은 안 나가는 식으로).

    **어떤 건을 되살릴지는 부르는 쪽이 정한다.** 여기서는 받은 것만 손댄다.
    """
    for item in items:
        item.status = "pending"
        item.error = None
    # 잡이 다시 `queued` 여야 발송 프로그램의 선점(`WHERE status='queued'`)에 걸린다.
    # `canceled`·`done` 인 채로 두면 카톡 건이 대기인 채로 영영 집혀 가지 않고,
    # 메일 쪽 `_finish()` 도 `canceled` 잡은 건드리지 않아 화면이 멈춘 것처럼 보인다.
    job.status = "queued"
    job.finished_at = None
    db.commit()

    if any(i.channel == "email" for i in items):
        background.add_task(mail_sender.send_job, job.id)
    return {"status": job.status, "requeued": len(items)}


@router.post("/jobs/{job_id}/retry")
def retry_failed(job_id: int, background: BackgroundTasks,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """실패 [재시도] — 실패 건을 다시 대기로 돌린다."""
    job = _job_or_404(db, job_id, user)
    failed_items = [i for i in job.items if i.status == "failed"]
    if not failed_items:
        raise HTTPException(status_code=400, detail="재시도할 실패 건이 없습니다")
    return _requeue(db, job, failed_items, background)


@router.post("/jobs/{job_id}/resend-canceled")
def resend_canceled(job_id: int, background: BackgroundTasks,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """취소분 [재발송] — [중단] 으로 남은 취소 건을 다시 대기로 돌린다.

    ## 왜 필요한가

    발송 도중 [중단]을 누르면 아직 안 나간 사람이 `canceled` 로 남는데, 그 회차를
    되살릴 길이 없었다. 남은 사람에게 보내려면 발송 목록을 처음부터 다시 만들어야
    했고, 그러면 **이미 받은 사람을 손으로 골라내야 한다** — 한 명만 실수해도 같은
    사람에게 두 번 나간다. 중단은 잠깐 멈추려고 누르는 것이지 회차를 버리려고
    누르는 것이 아니다.

    ## 이미 나간 사람은 절대 건드리지 않는다

    되살릴 대상을 `status == "canceled"` **인 것만** 고른다. `!= "sent"` 처럼 반대로
    쓰면 나중에 상태가 하나 늘었을 때 그것까지 조용히 딸려 들어온다. 발송은 되돌릴
    수 없으므로 넓게 고르는 쪽이 아니라 좁게 고르는 쪽이 맞다. 실패 건도 여기서
    함께 되살리지 않는다 — 실패는 [실패 재시도] 가 따로 맡고, 취소분만 보내려던
    사람이 사유를 못 본 실패 건까지 다시 내보내게 되면 그것도 예상 밖의 발송이다.

    ## 새 회차를 만들지 않고 **원래 회차를 되살린다**

    발송 이력은 `send_items` 한 줄이 곧 "이 사람에게 이 회차로 보냈다" 이고, 회차
    번호(`send_jobs.batch_id`)·종류(`kind`)·후속 단계(`stage`)·문구 스냅샷이 그 줄에
    붙어 있어야 이력이 이어진다. 담당자 상세의 발송 이력, "몇 번 기업" 번호 찾기,
    후속 예약이 모두 **가장 최근에 `sent` 된 줄의 회차**를 거슬러 올라가 본다.

    새 회차를 만들면 그 값들을 하나하나 옮겨 담아야 하고, 하나라도 빠지면 받은
    사람인데 "보낸 적 없음" 으로 보이거나 회차 번호가 옛 회차로 잡혀 "5번 기업" 이
    서로 다른 기업을 가리킨다. 같은 줄을 되살리면 옮길 것이 아예 없다.

    취소는 발송 이력이 아니라 **아직 안 보낸 상태**다. 그 줄이 그대로 `sent` 가 되는
    편이 사실에 가깝고, 화면에서도 한 회차가 한 줄로 남아 끊기지 않는다.
    """
    job = _job_or_404(db, job_id, user)
    canceled_items = [i for i in job.items if i.status == "canceled"]
    if not canceled_items:
        raise HTTPException(status_code=400, detail="재발송할 취소 건이 없습니다")
    return _requeue(db, job, canceled_items, background)


@router.get("/agent-status")
def get_agent_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Sidebar connection badge (FEATURE_SPEC §0.2) — 지금 선택된 사용자의 기기 기준."""
    return agent_status(db, user.id)
