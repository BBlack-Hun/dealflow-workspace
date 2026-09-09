"""예약 발송 — **정한 시각에 나가게 한다.** 고르고 만드는 것은 그대로 사람이다.

지금까지 [발송 시작] 은 누르는 순간 나갔다. 여기서 바뀌는 것은 그 한 가지뿐이다:
**언제 나갈지를 함께 정할 수 있다.** 누구에게 보낼지 고르는 것도, 문구를 보고
회차를 세우는 것도 지금과 똑같다. 서버가 스스로 대상을 고르는 자리는 **없다.**

## 어떻게 기다리게 하나  ★ 이 파일의 모양이 여기서 나온다

회차를 `draft` 로 세워 두고 `send_jobs.scheduled_at` 에 시각을 단다. 발송기는
`queued` 인 회차만 집어가므로(`routers/agent_api.py: poll`) **시각이 되기 전에는
집어갈 것이 없다.**

`queued` 로 미리 만들어 두고 폴링 쪽에서 시각을 보고 거르는 길도 있다. 그렇게
하지 않는다 — 거르는 자리가 한 곳이라는 보장이 없고, 한 곳이라도 새면
55~114명에게 한꺼번에 나간다. 되돌릴 수 없는 일에는 **샐 수 없는 쪽**을 고른다.
결과 문의 대기 목록이 같은 이유로 `draft` 를 골랐다(`services/auto_send.py`).

## 시각을 재는 곳은 여기 하나다

`state()` 가 "지금 보낼 때인가" 를 정하고, **예약을 푸는 쪽도 화면도 그 한
함수를 읽는다.** 각자 판단하면 화면에는 `대기 중` 인데 이미 나갔거나, 화면에는
`나갈 시각` 인데 서버는 지났다고 보는 상태가 생긴다.

## 푸는 것은 [발송 시작] 과 **같은 길**이다

`routers/jobs.py: _requeue` 를 그대로 부른다. 두 번째 발송 경로를 만들면
한쪽만 고쳐진다 — 카톡은 되살아나는데 메일은 안 나가는 식으로(그 함수의 설명
참고). 여기서 새로 하는 일은 **언제 부르는가**뿐이다.

## 고를 수 있는 시각

`auto_send.EARLIEST_HOUR`~`LATEST_HOUR`(09~19시) 를 그대로 쓴다. 같은 판단을
두 번 적지 않는다 — 받는 쪽이 투자사라 새벽에 카톡이 가면 그것만으로 관계가
상한다는 그 이유가 여기서도 같다. **화면에서도 막고 서버에서도 막는다**
(`check`) — 화면만 막으면 주소로 폼을 흉내 내는 순간 뚫린다.

요일은 막지 않는다. 사람이 날짜를 짚어 고르는 자리이고, 토요일에 보내려면
지금도 그날 [발송 시작] 을 누르면 된다 — 예약만 막아도 막히는 것이 없다.
대신 **화면에 요일을 적는다**(`label` 의 `9/12(토)`) — 잘못 고른 날은 눈에
보여야 한다. 목록이 저절로 서는 `auto_send` 쪽은 사람이 안 보는 자리라
평일만 남긴다.

## 지나 버린 예약은 **저절로 나가지 않는다**  ★

서버가 멈춰 있었거나 한참 뒤에 깨어난 경우다. 몇 시간 늦게 조용히 나가는 것이
더 위험하다 — 받는 쪽에서는 한밤중에 오는 것으로 보인다. 그래서 `EXPIRE_MINUTES`
가 지나면 풀지 않고 서 있고, 화면이 `예약 시각이 지났습니다` 라고 적는다.
사람이 [발송 시작] 을 누르면 그때 나간다.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..db import SessionLocal
from ..models import SendJob
from . import auto_send

log = logging.getLogger(__name__)

#: **고를 수 있는 시각의 폭.** `auto_send` 가 정한 그 값이다 — 여기에 숫자를
#: 다시 적으면 한쪽만 고쳐지는 날이 온다.
EARLIEST_HOUR = auto_send.EARLIEST_HOUR
LATEST_HOUR = auto_send.LATEST_HOUR

#: **얼마나 지나면 '지난 것' 인가.** 정한 시각으로부터 한 시간.
#:
#: 값이 여기 한 곳에만 있어야 한다. 푸는 쪽과 화면이 각자 세면 화면에는
#: `대기 중` 인데 서버는 이미 포기한 상태가 생긴다.
EXPIRE_MINUTES = 60

#: 얼마나 자주 깨어나 볼 것인가. 14:00 예약이 14:00~14:00:30 사이에 풀린다.
#:
#: 백업·결과 문의 문자는 30분마다 깨어나지만 여기는 그럴 수 없다 — 사람이
#: 분 단위로 시각을 골랐는데 30분 뒤에 나가면 그것은 예약이 아니다.
CHECK_INTERVAL_SEC = 30

#: `state()` 가 돌려주는 값. **화면도 푸는 쪽도 이 글자를 읽는다.**
STATE_NONE = "none"          # 예약이 없다 — 지금까지와 같다
STATE_WAITING = "waiting"    # 아직 그 시각이 안 됐다. 발송기는 집어갈 것이 없다
STATE_DUE = "due"            # 시각이 됐다. 다음 깨어남에 풀린다
STATE_EXPIRED = "expired"    # 지나 버렸다. **저절로 안 나간다**
STATE_RELEASED = "released"  # 이미 풀렸다(나갔거나 나가는 중)

_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")

_SCHEDULER: Optional[threading.Thread] = None


# --- 시각 다루기 -------------------------------------------------------------

def _aware(when: datetime) -> datetime:
    """오프셋이 없는 시각에 **이 프로세스의 시간대**를 붙인다.

    저장값에는 오프셋이 붙어 있고(`clock.now_iso`), 화면의 `datetime-local`
    칸은 오프셋 없이 온다. 둘을 그냥 빼면 `TypeError` 다 — 한쪽으로 맞춘다.
    시간대를 코드에 박지 않는 이유는 `app/clock.py` 머리말과 같다.
    """
    return when if when.tzinfo else when.astimezone()


def parse(raw: str) -> datetime:
    """사람이 고른 시각을 읽는다. 못 읽으면 `ValueError`.

    화면의 `<input type="datetime-local">` 은 `2026-09-10T14:00` 로 준다.
    저장값(`2026-09-10T14:00:00+09:00`)도 같은 함수로 읽힌다 — 읽는 자리가
    하나여야 저장한 것과 고른 것이 같은 뜻이 된다.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("예약 시각이 비어 있습니다")
    try:
        return _aware(datetime.fromisoformat(text)).replace(microsecond=0)
    except ValueError:
        raise ValueError("예약 시각을 읽을 수 없습니다") from None


def check(at: datetime, now: Optional[datetime] = None) -> datetime:
    """고른 시각이 쓸 수 있는 값인가. 아니면 **까닭을 담은** `ValueError`.

    **화면이 이미 막았더라도 여기서 다시 본다.** 주소로 폼을 흉내 내면 무엇이든
    들어오고, 그 한 번이 새벽 3시에 투자사 카톡방을 여는 값이다(`auto_send.save`
    가 같은 이유로 라우터가 아니라 저장 자리에서 자른다).
    """
    at = _aware(at)
    now = _aware(now or clock.now())
    if at <= now:
        raise ValueError("이미 지난 시각입니다 — 지금 보내려면 [발송 시작] 을 누르세요")
    if not (EARLIEST_HOUR <= at.hour < LATEST_HOUR):
        raise ValueError(
            f"예약은 {EARLIEST_HOUR:02d}:00~{LATEST_HOUR:02d}:00 안에서만 "
            "고를 수 있습니다 — 받는 분들의 업무시간입니다")
    return at


def deadline(at: datetime) -> datetime:
    """**언제까지 안 나가면 포기하나.** 정한 시각 + `EXPIRE_MINUTES`.

    그날 `LATEST_HOUR` 를 넘기지 않는다. 18:40 예약이 19:40 에 풀리면 그것은
    고를 수도 없던 시각이다 — 막아 둔 창을 뒷문으로 넘는 셈이 된다.
    """
    at = _aware(at)
    edge = at.replace(hour=LATEST_HOUR, minute=0, second=0, microsecond=0)
    return min(at + timedelta(minutes=EXPIRE_MINUTES), edge)


def label(at: datetime) -> str:
    """화면에 적는 `9/10(목) 14:00`.

    **요일을 함께 적는다.** 토요일을 잘못 고른 것은 날짜만 봐서는 안 보인다.
    """
    at = _aware(at)
    return f"{at.month}/{at.day}({_WEEKDAYS[at.weekday()]}) {at:%H:%M}"


# --- 지금 어떤 상태인가 (판단은 **여기 하나**) --------------------------------

def scheduled_at(job: SendJob) -> Optional[datetime]:
    """이 회차에 걸린 예약 시각. 없거나 읽을 수 없으면 `None`."""
    if not job.scheduled_at:
        return None
    try:
        return parse(job.scheduled_at)
    except ValueError:
        # 손으로 넣은 값이 망가져 있어도 **발송이 멈추지는 않게** 한다.
        # 예약이 없는 것으로 보고 사람이 누르기를 기다린다.
        log.warning("회차 %s 의 예약 시각을 읽을 수 없습니다: %r",
                    job.id, job.scheduled_at)
        return None


def state(job: SendJob, now: Optional[datetime] = None) -> str:
    """**지금 보낼 때인가.** 푸는 쪽도 화면도 이 한 함수를 읽는다.

    `released_at` 이나 상태가 `draft` 를 벗어난 것은 **이미 풀린 것**이다.
    다시 풀지 않는다 — 예약이 두 번 풀리면 같은 사람에게 두 번 나간다.
    """
    at = scheduled_at(job)
    if at is None:
        return STATE_NONE
    if job.released_at or job.status != "draft":
        return STATE_RELEASED
    now = _aware(now or clock.now())
    if now < at:
        return STATE_WAITING
    if now < deadline(at):
        return STATE_DUE
    return STATE_EXPIRED


def pending_count(job: SendJob) -> int:
    """이 예약으로 **몇 명에게** 나가나. 화면과 오늘 할 일이 같은 수를 본다."""
    return sum(1 for i in job.items if i.status == "pending")


def sentence(job: SendJob, now: Optional[datetime] = None) -> str:
    """`9/10(목) 14:00 에 55명에게 나갑니다` — 사람이 읽는 한 줄.

    **몇 명에게 가는지 반드시 함께 적는다.** 한 회차가 55~114명이고 나간 뒤에는
    되돌릴 수 없다 — 진행 화면의 단추들이 같은 이유로 수를 적는다.

    문장을 서버에서 만든다. 화면마다 지어 놓으면(진행 화면·오늘 할 일) 두 벌이
    되고, 둘이 어긋나도 아무도 모른다.
    """
    at = scheduled_at(job)
    if at is None:
        return ""
    who = f"{pending_count(job)}명에게"
    now_state = state(job, now)
    if now_state == STATE_EXPIRED:
        return (f"예약 시각이 지났습니다 ({label(at)} · {who}) — "
                "저절로 나가지 않습니다. 보내려면 [발송 시작] 을 누르세요")
    if now_state == STATE_DUE:
        return f"{label(at)} · {who} 곧 나갑니다"
    if now_state == STATE_RELEASED:
        # **무슨 일이 있었는지는 여기서 말하지 않는다.** 이 자리에 온 회차는
        # 예약이 풀린 것일 수도, 사람이 먼저 누른 것일 수도, [중단] 된 것일
        # 수도 있다. 어디까지 갔는지는 회차 화면의 상태와 표가 말한다 —
        # 여기서 짐작해 적으면 화면이 거짓말을 한다.
        return f"{label(at)} 로 걸어 두었던 예약입니다"
    return f"{label(at)} 에 {who} 나갑니다"


def describe(job: SendJob, now: Optional[datetime] = None) -> dict:
    """진행 화면이 읽는 예약 한 덩이. **화면은 판정하지 않는다.**"""
    at = scheduled_at(job)
    return {
        "at": job.scheduled_at or "",
        # 화면의 `datetime-local` 칸에 도로 채워 넣을 값(오프셋·초 없이).
        "input": at.strftime("%Y-%m-%dT%H:%M") if at else "",
        "label": label(at) if at else "",
        "state": state(job, now),
        "sentence": sentence(job, now),
        "count": pending_count(job) if at else 0,
        "earliest": EARLIEST_HOUR,
        "latest": LATEST_HOUR,
    }


# --- 걸고 · 바꾸고 · 푼다 -----------------------------------------------------

def can_schedule(job: SendJob) -> bool:
    """예약을 걸거나 고칠 수 있는 회차인가 — **아직 안 나간 것만.**

    이미 `queued` 가 된 뒤에는 기존 [중단] 이 맡는다. 나간 회차에 시각을 달면
    화면이 "아직 안 나갔다" 고 거짓말을 한다.
    """
    return job.status == "draft" and not job.released_at


def set_at(db: Session, job: SendJob, raw: str,
           now: Optional[datetime] = None) -> dict:
    """예약을 걸거나 **시각을 바꾼다.** 못 걸 값이면 `ValueError`.

    거는 것과 바꾸는 것이 같은 자리다 — 나뉘어 있으면 한쪽만 검사를 지나간다.
    """
    at = check(parse(raw), now)
    job.scheduled_at = at.isoformat(timespec="seconds")
    job.released_at = None
    db.commit()
    return describe(job, now)


def clear(db: Session, job: SendJob, now: Optional[datetime] = None) -> dict:
    """**예약만 뗀다.** 회차는 `draft` 인 채로 남는다.

    회차를 함께 버리지 않는다 — 시각만 잘못 고른 것일 수 있고, 그때 회차까지
    사라지면 대상을 처음부터 다시 골라야 한다(고른 사람을 손으로 다시 맞추다
    한 명이라도 틀리면 그것이 곧 사고다).
    """
    job.scheduled_at = None
    job.released_at = None
    db.commit()
    return describe(job, now)


def _claim(db: Session, job: SendJob, now: datetime) -> bool:
    """이 예약을 **내가 푼다**고 자리를 잡는다. 이미 잡혀 있으면 거짓.

    `agent_api.poll` 의 선점과 같은 방식이다 — 읽고 나서 조건을 붙여 한 줄만
    바꾸고, 바뀐 줄 수로 이겼는지 진다. 웹 프로세스가 여럿이거나 사람이 같은
    순간 [발송 시작] 을 눌러도 **한 번만** 풀린다.

    상태(`draft`)로 잡지 않는 이유는 `models.SendJob.released_at` 에 적어 두었다.
    """
    from sqlalchemy import text

    done = db.execute(
        text("UPDATE send_jobs SET released_at=:t "
             "WHERE id=:id AND status='draft' "
             "AND scheduled_at IS NOT NULL AND released_at IS NULL"),
        {"t": now.isoformat(timespec="seconds"), "id": job.id},
    )
    db.commit()
    if done.rowcount == 0:
        return False
    db.refresh(job)
    return True


class _ThreadTasks:
    """`BackgroundTasks` 자리에 끼우는 아주 작은 대역.

    `jobs._requeue` 는 메일 건이 섞여 있으면 **서버가 다시 보내도록**
    백그라운드에 일을 건다. 요청 안이 아니라 실 안에서 부르면 그 일을 돌려줄
    FastAPI 가 없어서, 걸어 둔 채로 아무 일도 일어나지 않는다 — 카톡은
    나가는데 메일만 조용히 안 나간다.

    `mail_sender.send_job` 은 제 세션을 열므로(그 함수 설명) 실 하나로 그냥
    돌리면 된다. 예약을 푸는 실이 55통을 보내는 동안 멈춰 있지 않게 따로 띄운다.
    """

    def add_task(self, func, *args, **kwargs) -> None:
        threading.Thread(target=func, args=args, kwargs=kwargs,
                         daemon=True).start()


def release(db: Session, job: SendJob, now: Optional[datetime] = None) -> bool:
    """때가 된 예약 하나를 푼다. 실제로 풀었으면 참.

    **[발송 시작] 과 같은 길**을 탄다(`jobs._requeue`). 여기서 대기 건을 따로
    세우거나 상태를 손으로 올리지 않는다 — 두 벌이 되면 한쪽만 고쳐진다.
    """
    from ..routers import jobs as jobs_view

    now = _aware(now or clock.now())
    if state(job, now) != STATE_DUE:
        return False
    if not _claim(db, job, now):
        return False

    pending = [i for i in job.items if i.status == "pending"]
    if not pending:
        # 보낼 것이 없는 회차. 자리는 잡은 채로 둔다 — 다시 들여다보지 않게.
        log.warning("예약 회차 %s 에 대기 건이 없습니다 — 풀지 않습니다", job.id)
        return False
    jobs_view._requeue(db, job, pending, _ThreadTasks())
    log.info("예약 발송 — 회차 %s, %s명, 예약 %s",
             job.id, len(pending), job.scheduled_at)
    return True


def due_jobs(db: Session, now: Optional[datetime] = None) -> list:
    """지금 풀 때가 된 회차들. **`state()` 한 곳으로 가린다.**

    SQL 로 시각을 견주지 않는다 — 그러면 "지금 보낼 때인가" 가 여기와 `state()`
    두 곳에 적힌다. DB 는 **예약이 걸린 `draft` 회차**까지만 좁혀 주고
    (한 번에 몇 줄 안 된다), 판단은 한 함수가 한다.
    """
    now = _aware(now or clock.now())
    rows = db.execute(
        select(SendJob).where(SendJob.status == "draft",
                              SendJob.scheduled_at.isnot(None),
                              SendJob.released_at.is_(None))
        .order_by(SendJob.id)
    ).scalars().all()
    return [j for j in rows if state(j, now) == STATE_DUE]


def run_once(db: Session, now: Optional[datetime] = None) -> dict:
    """때가 된 예약을 전부 푼다. 실이 깰 때마다 부른다.

    아무것도 안 하고 돌아오는 것이 보통이다 — 그것이 정상 동작이다.
    """
    now = _aware(now or clock.now())
    released = [j.id for j in due_jobs(db, now) if release(db, j, now)]
    return {"released": released, "count": len(released)}


# --- 사람 눈에 보이게 -----------------------------------------------------

def standing_for(db: Session, user, now: Optional[datetime] = None) -> list:
    """이 계정이 **걸어 둔 채 아직 안 나간** 예약들. 오늘 할 일이 읽는다.

    ## 왜 오늘 할 일에도 서는가  ★

    **예약해 놓고 잊는 것이 이 기능에서 가장 흔한 사고다.** 회차 화면은 그 주소를
    아는 사람만 다시 열어 보고, 예약은 걸어 두면 화면을 닫는다. 그러니 아침에
    여는 화면에 서 있어야 한다 — 결과 문의 대기 목록이 같은 이유로 여기 선다
    (`services/today.py`).

    **다음 날짜 것도 함께 보인다.** 오늘 것만 보이면 모레 14:00 짜리 예약은
    모레까지 아무 데도 안 뜨고, 그사이 대상이 바뀌어도 아무도 모른다. 대신
    급한 차례를 나눈다: 지나 버린 것 > 오늘 > 그 뒤.

    문장은 여기서 짓지 않는다 — `sentence()` 한 곳이 짓는다.
    """
    now = _aware(now or clock.now())
    rows = db.execute(
        select(SendJob).where(SendJob.user_id == user.id,
                              SendJob.status == "draft",
                              SendJob.scheduled_at.isnot(None),
                              SendJob.released_at.is_(None))
        .order_by(SendJob.scheduled_at)
    ).scalars().all()

    out = []
    for job in rows:
        now_state = state(job, now)
        if now_state not in (STATE_WAITING, STATE_DUE, STATE_EXPIRED):
            continue
        at = scheduled_at(job)
        if now_state == STATE_EXPIRED:
            level = "urgent"
        elif at.date() == now.date():
            level = "soon"
        else:
            level = "info"
        out.append({"job_id": job.id, "state": now_state, "level": level,
                    "count": pending_count(job), "label": label(at),
                    "sentence": sentence(job, now)})
    return out


# --- 실 -----------------------------------------------------------------------

def start_scheduler() -> None:
    """웹 프로세스 안에서 30초마다 깨어나 본다.

    백업·결과 문의 문자·결과 문의 목록과 **같은 얼개**다(그쪽은 30분마다).
    크론도 워커도 두지 않는다 — 새 프로세스를 늘리면 배포와 감시가 한 벌 더
    는다.
    """
    global _SCHEDULER
    if _SCHEDULER is not None and _SCHEDULER.is_alive():
        return

    def loop() -> None:
        while True:
            time.sleep(CHECK_INTERVAL_SEC)
            db = SessionLocal()
            try:
                run_once(db)
            except Exception:  # noqa: BLE001 - 실이 죽으면 예약이 조용히 멎는다
                log.exception("예약 발송을 살피다 실패했습니다")
            finally:
                db.close()

    _SCHEDULER = threading.Thread(target=loop, daemon=True,
                                  name="scheduled-send")
    _SCHEDULER.start()
