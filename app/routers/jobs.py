"""Send-job progress JSON + controls (ROADMAP task 1.9, FEATURE_SPEC §5 ⑦~⑧)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..clock import now_iso
from ..db import get_db
from ..deps import agent_status, get_current_user
from ..models import SendItem, SendJob, User
from ..services import mail_sender, scheduled_send

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
        # **예약이 걸려 있는가.** 판정도 문장도 서버가 만든다
        # (`services/scheduled_send.py`) — 화면이 따로 세면 화면에는 `대기 중`
        # 인데 서버는 이미 지났다고 보는 상태가 생긴다.
        "scheduled": scheduled_send.describe(job),
        # **발송기가 붙어 있는가.** `queued` 인 회차가 안 나가고 있을 때,
        # 막힌 것인지 그냥 서 있는 것인지는 이것으로 갈린다 — PC 가 꺼져 있으면
        # 잡은 큐에 그대로 서서 기다린다(고장이 아니다). 화면이 그 둘을
        # 구분하지 못하면 사람이 [중단] 을 누르거나 회차를 다시 만든다.
        #
        # 그 회차 **주인의** 기기를 본다(보고 있는 사람이 아니라) — 관리자가
        # 남의 회차를 열어 봐도 실제로 그 잡을 집어갈 기기는 주인 것이다.
        "agent": agent_status(db, job.user_id),
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


@router.post("/jobs/{job_id}/start")
def start_draft(job_id: int, background: BackgroundTasks,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """[발송 시작] — **미리 세워 둔 대기 목록을 그때 내보낸다.**

    ## 무엇이 `draft` 로 서 있나

    결과 문의(미팅 후기)는 물어볼 때가 되면 서버가 **대기 목록만** 만들어 둔다
    (`services/auto_send.py`). 그 회차는 `draft` 라 발송 프로그램이 집어가지
    않는다(`agent_api.poll` 은 `queued` 만 고른다). 여기를 눌러야 나간다 —
    **누르는 것은 사람이다.**

    ## 누르기 전에 무엇을 보게 되나  ★

    이 화면이 곧 대기 목록이다. 표에 **누구에게 · 어느 방으로** 가는지가 줄마다
    있고, `대기` 칸이 몇 건인지 말한다. 단추에도 인원수가 적힌다. 발송은 되돌릴
    수 없으므로 **누른 뒤에 숫자를 아는 것은 늦다** — 취소분 재발송·이어 보내기가
    같은 이유로 단추에 수를 적는다.

    ## 왜 [이어 보내기] 를 쓰지 않나

    하는 일은 같다(대기 건을 큐에 올린다). 그래서 **되살리는 절차는 같은 곳**을
    쓴다(`_requeue`) — 두 벌로 두면 한쪽만 고쳐져 카톡은 되살아나는데 메일은
    안 나간다. 다른 것은 **말**이다. 이어 보내기는 **가다 만 회차**를 마저
    보내는 자리이고, 여기는 아직 **한 건도 나가지 않은** 회차를 처음 내보내는
    자리다. 한 단추에 두 뜻을 담으면 화면이 거짓말을 한다.

    ## `draft` 만 받는다

    이미 돌고 있거나 끝난 회차를 여기로 되살리지 않는다. 그쪽은 [실패 재시도] ·
    [취소분 재발송] · [이어 보내기] 가 각자 맡고, 무엇을 되살릴지 좁게 고르는
    것이 그 셋의 규칙이다 — 발송은 되돌릴 수 없다.
    """
    job = _job_or_404(db, job_id, user)
    if job.status != "draft":
        raise HTTPException(status_code=400,
                            detail="이미 시작된 회차입니다")
    pending_items = [i for i in job.items if i.status == "pending"]
    if not pending_items:
        raise HTTPException(status_code=400, detail="보낼 대기 건이 없습니다")
    # 예약이 걸린 회차를 사람이 먼저 눌렀다면 **그 예약은 여기서 끝난다.**
    # 상태가 `queued` 로 올라가는 것만으로도 예약은 못 풀리지만(`_claim` 은
    # `status='draft'` 인 줄만 집는다), 자물쇠를 함께 잠가 둔다 — 나중에 누가
    # 이 회차를 다시 `draft` 로 되돌려도 같은 회차가 두 번 나가지 않는다.
    if job.scheduled_at and not job.released_at:
        job.released_at = now_iso()
    return _requeue(db, job, pending_items, background)


@router.post("/jobs/{job_id}/resume")
def resume_pending(job_id: int, background: BackgroundTasks,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """이어 보내기 — **아직 안 나간 대기 건**을 다시 큐에 올린다.

    ## 왜 필요한가

    97명짜리 회차에서 60명에게만 나갔는데 회차가 `done` 으로 끝났다. 나머지
    37명은 `pending` 인 채로 남았다(발송 프로그램이 1잡 상한에 걸려 앞 60건만
    처리하고 잡 전체를 완료로 보고했다 — `routers/agent_api.py: _settle` 참고).

    그런데 손쓸 방법이 하나도 없었다. [실패 재시도]는 `failed` 만, [취소분
    재발송]은 `canceled` 만 고른다. **대기 건은 어느 쪽에도 안 걸린다.** 남은
    37명에게 보내려면 발송 목록을 처음부터 다시 만들어야 하고, 그러면 이미 받은
    60명을 손으로 골라내야 한다 — 한 명만 실수해도 같은 사람에게 두 번 나간다.

    앞으로는 서버가 대기 건을 두고 완료 보고를 받지 않으므로 이렇게 끝난 회차가
    새로 생기지는 않는다. 그래도 이 길은 계속 필요하다.

    - 진행이 없어 `paused` 로 멈춘 회차에 대기 건이 남는다(무한 반복을 막느라
      일부러 멈춘 것이다). 사람이 원인을 고친 뒤 이어 보낼 곳이 여기다.
    - 발송 프로그램이 도중에 죽으면 잡이 `running` 인 채로 대기 건이 남는다.
    - 메일 건은 서버가 보내는데(`services/mail_sender.py`), 그 사이 서버가
      내려가면 대기로 남는다. 카톡 쪽 완료 판정은 메일 건을 세지 않는다 —
      세면 잡이 영영 안 끝난다.

    ## 이미 나간 사람은 절대 건드리지 않는다

    `status == "pending"` **인 것만** 고른다. `!= "sent"` 처럼 반대로 쓰면 나중에
    상태가 하나 늘었을 때 그것까지 조용히 딸려 들어온다(취소분 재발송과 같은
    이유다). 발송은 되돌릴 수 없으므로 넓게 고르는 쪽이 아니라 좁게 고르는 쪽이
    맞다. 실패 건도 여기서 함께 되살리지 않는다 — 사유를 못 본 실패 건이 딸려
    나가면 그것도 예상 밖의 발송이다.

    되살리는 절차 자체는 [실패 재시도]·[취소분 재발송]과 **같은 곳**(`_requeue`)을
    쓴다. 카톡과 메일은 나가는 길이 달라서, 절차를 두 벌로 두면 한쪽만 고쳐져
    카톡은 되살아나는데 메일은 안 나간다.
    """
    job = _job_or_404(db, job_id, user)
    pending_items = [i for i in job.items if i.status == "pending"]
    if not pending_items:
        raise HTTPException(status_code=400, detail="이어 보낼 대기 건이 없습니다")
    return _requeue(db, job, pending_items, background)


@router.get("/agent-status")
def get_agent_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Sidebar connection badge (FEATURE_SPEC §0.2) — 지금 선택된 사용자의 기기 기준."""
    return agent_status(db, user.id)


# ── 예약 발송 ────────────────────────────────────────────────────────────────
#
# **누르면 바로 나가던 것을, 정한 시각에 나가게 한다.** 대상을 고르고 회차를
# 세우는 것까지는 지금과 똑같다(`services/scheduled_send.py` 머리말).
#
# 여기서 발송 경로를 새로 만들지 않는다. 시각이 되면 예약을 푸는 쪽이
# **위 `_requeue`** 를 그대로 부른다 — [발송 시작] 이 지나는 그 길이다.


class ScheduleRequest(BaseModel):
    """언제 보낼지. 화면의 `<input type="datetime-local">` 값 그대로다."""

    at: str


@router.post("/jobs/{job_id}/schedule")
def schedule_job(job_id: int, req: ScheduleRequest,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """[예약] — 아직 안 나간 회차에 **나갈 시각**을 단다. 시각 변경도 여기다.

    ## 아직 안 나간 것만

    `draft` 인 회차만 받는다. 이미 `queued` 가 된 뒤에는 발송기가 언제든
    집어갈 수 있어서, 시각을 달아 봐야 화면이 "아직 안 나갔다" 고 거짓말을
    하게 된다 — 그쪽은 기존 [중단] 이 맡는다.

    ## 되는 값인지는 **서버가** 본다

    화면이 고르개를 09~19시로 좁혀 두었어도 여기서 다시 본다
    (`scheduled_send.check`). 주소로 폼을 흉내 내면 무엇이든 들어오고, 한
    회차가 55~114명이라 그 한 번이 새벽에 투자사 카톡방을 여는 값이다.
    """
    job = _job_or_404(db, job_id, user)
    if not scheduled_send.can_schedule(job):
        raise HTTPException(status_code=400,
                            detail="이미 시작된 회차입니다 — 예약할 수 없습니다")
    if not any(i.status == "pending" for i in job.items):
        raise HTTPException(status_code=400, detail="보낼 대기 건이 없습니다")
    try:
        return scheduled_send.set_at(db, job, req.at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete("/jobs/{job_id}/schedule")
def unschedule_job(job_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """[예약 취소] — **예약만 뗀다.** 회차는 `draft` 로 남아 그대로 기다린다.

    회차까지 버리지 않는 이유는 `scheduled_send.clear` 에 적어 두었다. 이미
    나간 회차에는 듣지 않는다 — 그쪽은 [중단] 이다.
    """
    job = _job_or_404(db, job_id, user)
    if not scheduled_send.can_schedule(job):
        raise HTTPException(status_code=400,
                            detail="이미 시작된 회차입니다 — [중단] 을 쓰세요")
    return scheduled_send.clear(db, job)
