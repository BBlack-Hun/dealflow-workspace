"""후속 캐던스 — 딜소개 뒤에 무엇을 언제 보낼지.

딜소개를 보내고 답이 없으면 며칠 뒤 리마인드를, 그래도 없으면 미팅을 청한다.
사람이 달력을 보며 챙기던 일이라 빠지기 쉽다 — 여기서 날짜를 정해 둔다.

**언제 시작하는가.** 딜소개가 *성공한 뒤에만* 시작한다. 발송 목록을 만든 시점에
시작하면 실패한 건까지 후속이 예약되어, 받은 적 없는 사람에게 "지난번 공유드린"
이 나간다.

**언제 멈추는가.** 답이 오면 멈춘다. IR 요청이나 미팅이 잡혔는데도 리마인드가
계속 나가는 것이 이 기능에서 가장 나쁜 실패다.

**날짜는 어떻게 정하는가.** 규칙은 `schedule_rules` 에 있다. 코드에 박아 두면
바뀔 때마다 배포해야 한다(실제로 '매주'에서 '월 2회'로 한 번 바뀌었다).

주기 산출은 **스케줄러 없이** 화면이 볼 때 계산한다. 예약일을 행에 적어 두므로
'오늘 이전인 것'을 고르면 끝이라, 컨테이너를 껐다 켜도 놓치는 날이 없다.
백그라운드 작업을 두면 중복 실행·재시작 유실을 따로 막아야 하는데 얻는 것이 없다.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import (
    ContactActivity,
    DealBatch,
    ScheduleRule,
    SendItem,
    SendJob,
    SendSequence,
    VcContact,
)

# 단계. message_composer 의 STAGE_* 와 같은 값을 쓴다.
STAGE_DAY1 = 1
STAGE_REMIND = 2
STAGE_MEETING = 3

STAGE_LABELS = {
    STAGE_DAY1: "딜소개",
    STAGE_REMIND: "리마인드",
    STAGE_MEETING: "미팅 요청",
}
# 다음 단계를 보낼 때 발송 화면에서 쓸 방식
STAGE_MODES = {STAGE_REMIND: "remind", STAGE_MEETING: "meeting"}

STATUS_LABELS = {
    "active": "예약됨",
    "responded": "답 옴",
    "stopped": "중단",
    "done": "완료",
}

# 규칙이 하나도 없을 때 쓸 기본값. 부트스트랩이 DB 에 넣지만,
# 규칙이 지워져도 화면이 죽지는 않아야 한다.
DEFAULT_RULES = {
    "deal_cycle": dict(label="딜소개 회차", kind="monthly_weekday",
                       weekday=2, nth_weeks="1,3", skip_weekend=1,
                       extra_dates=None, skip_dates=None),
    "remind": dict(label="리마인드", kind="offset_days",
                   offset_min_days=6, offset_max_days=7, skip_weekend=1),
    "meeting": dict(label="미팅 요청", kind="offset_days",
                    offset_min_days=11, offset_max_days=14, skip_weekend=1),
}


# --- 규칙 -------------------------------------------------------------------

def get_rule(db: Session, key: str) -> dict:
    row = db.execute(
        select(ScheduleRule).where(ScheduleRule.key == key,
                                   ScheduleRule.is_active == 1)
    ).scalars().first()
    if row is None:
        return dict(key=key, **DEFAULT_RULES.get(key, {}))
    return dict(
        key=row.key, label=row.label, kind=row.kind, weekday=row.weekday,
        nth_weeks=row.nth_weeks, offset_min_days=row.offset_min_days,
        offset_max_days=row.offset_max_days, skip_weekend=row.skip_weekend,
        effective_from=row.effective_from,
        extra_dates=row.extra_dates, skip_dates=row.skip_dates,
    )


def _date_list(value: Optional[str]) -> List[date]:
    """'2026-08-26,2026-09-09' → [date, date]. 이상한 값은 조용히 버린다."""
    out = []
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(date.fromisoformat(part))
        except ValueError:
            continue
    return out


def _nth_list(value: Optional[str]) -> List[int]:
    out = []
    for part in (value or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out or [1, 3]


def next_business_day(day: date, skip_weekend: bool = True) -> date:
    """주말이면 다음 월요일로 민다. 토요일에 딜소개를 보내지는 않는다."""
    if not skip_weekend:
        return day
    while day.weekday() >= 5:      # 5=토 6=일
        day += timedelta(days=1)
    return day


def nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (nth - 1))


def upcoming_send_dates(db: Optional[Session] = None,
                        today: Optional[date] = None,
                        count: int = 3) -> List[date]:
    """다음 회차일들. 오늘이 회차일이면 오늘도 포함한다.

    오늘을 빼면 그날 아침에 화면을 열었을 때 '다음은 2주 뒤'로 보여 회차를 놓친다.
    """
    today = today or date.today()
    rule = get_rule(db, "deal_cycle") if db is not None else \
        dict(key="deal_cycle", **DEFAULT_RULES["deal_cycle"])
    weekday = rule.get("weekday") if rule.get("weekday") is not None else 2
    nths = _nth_list(rule.get("nth_weeks"))
    skip = bool(rule.get("skip_weekend", 1))

    # 규칙에서 벗어난 일회성 회차일. "다음 회차는 8/26" 처럼 규칙 밖 날짜가
    # 내려오는데, 규칙을 고치면 그 달 이후가 전부 따라 바뀐다.
    skip_days = set(_date_list(rule.get("skip_dates")))
    out: List[date] = [d for d in _date_list(rule.get("extra_dates"))
                       if d >= today and d not in skip_days]

    year, month = today.year, today.month
    # 규칙이 이상해도 무한 루프에 빠지지 않게 살펴볼 달 수를 제한한다.
    for _ in range(36):
        if len(out) >= count:
            break
        for nth in nths:
            day = next_business_day(nth_weekday(year, month, weekday, nth), skip)
            if day >= today and day not in out and day not in skip_days:
                out.append(day)
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return sorted(out)[:count]


def follow_up_date(db: Session, sent_on: date, stage: int,
                   rng: Optional[random.Random] = None) -> Optional[date]:
    """다음 후속을 보낼 날.

    범위 안에서 하루를 무작위로 고른다. 모두 같은 날 같은 시각에 나가면
    받는 쪽에서도 티가 나고, 카카오 쪽에서도 한 번에 몰린 발송으로 보인다.
    """
    key = {STAGE_REMIND: "remind", STAGE_MEETING: "meeting"}.get(stage)
    if key is None:
        return None
    rule = get_rule(db, key)
    lo = rule.get("offset_min_days")
    hi = rule.get("offset_max_days")
    if lo is None:
        return None
    if hi is None or hi < lo:
        hi = lo
    picker = rng or random
    day = sent_on + timedelta(days=picker.randint(lo, hi))
    return next_business_day(day, bool(rule.get("skip_weekend", 1)))


# --- 시퀀스 -----------------------------------------------------------------

def _today() -> date:
    return clock.today()


def _now_iso() -> str:
    return clock.now_iso()


def _as_date(value: Optional[str]) -> Optional[date]:
    """저장된 시각 문자열에서 **보낸 날**을 뽑는다.

    앞 10자를 그냥 자를 수 있는 것은 저장이 지역시간이기 때문이다(`app/clock.py`).
    UTC 로 적히던 때에는 한국 새벽에 보낸 건이 여기서 **어제**로 읽혔고, 그
    어제를 기준으로 리마인드를 잡아 후속이 하루 당겨졌다 — 이 함수가 그 버그가
    드러난 자리다.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def start_or_advance(db: Session, item: SendItem, job: SendJob,
                     rng: Optional[random.Random] = None) -> Optional[SendSequence]:
    """발송이 **성공했을 때** 부른다. 시퀀스를 시작하거나 다음 단계로 넘긴다.

    - 딜소개(stage 1) → 시퀀스 시작, 리마인드 예약
    - 리마인드(stage 2) → 미팅 요청 예약
    - 미팅 요청(stage 3) → 끝
    - IR 자료 전달은 답이 왔다는 뜻이므로 시퀀스를 멈춘다
    """
    if item.status != "sent":
        return None
    # 딜 소싱 제안은 후속 3단(리마인드 → 미팅 요청)을 타지 않는다.
    # 딜을 봐 달라는 초대라 "검토 중이신가요" 를 이어 보낼 것이 없다.
    if item.contact_id is None:
        return None

    seq = db.execute(
        select(SendSequence).where(SendSequence.contact_id == item.contact_id)
        .order_by(SendSequence.id.desc()).limit(1)
    ).scalars().first()

    stage = item.stage or STAGE_DAY1
    sent_on = _as_date(item.sent_at) or _today()

    if job.kind == "ir_delivery":
        # 자료를 보냈다는 것은 상대가 달라고 했다는 뜻이다.
        if seq and seq.status == "active":
            stop(db, seq, "IR 자료를 전달했습니다", status="responded")
        return seq

    if stage == STAGE_DAY1:
        if seq is not None and seq.status == "active":
            # 같은 사람에게 새 회차를 보냈다면 그 회차 기준으로 다시 센다.
            seq.batch_id = job.batch_id
        else:
            seq = SendSequence(user_id=job.user_id, contact_id=item.contact_id,
                               batch_id=job.batch_id)
            db.add(seq)
        seq.stage = STAGE_DAY1
        seq.status = "active"
        seq.stopped_reason = None
        seq.day1_sent_at = item.sent_at or _now_iso()
        seq.last_sent_at = seq.day1_sent_at
        seq.next_stage = STAGE_REMIND
        due = follow_up_date(db, sent_on, STAGE_REMIND, rng)
        seq.next_due_date = due.isoformat() if due else None
        db.flush()
        return seq

    if seq is None or seq.status != "active":
        return seq

    seq.stage = stage
    seq.last_sent_at = item.sent_at or _now_iso()
    if stage == STAGE_REMIND:
        seq.next_stage = STAGE_MEETING
        # 미팅 요청은 **딜소개일 기준**으로 잡는다. 리마인드가 늦어졌다고
        # 미팅 요청까지 밀리면 회차 간격이 뒤엉킨다.
        base = _as_date(seq.day1_sent_at) or sent_on
        due = follow_up_date(db, base, STAGE_MEETING, rng)
        seq.next_due_date = due.isoformat() if due else None
    else:
        seq.next_stage = None
        seq.next_due_date = None
        seq.status = "done"
    db.flush()
    return seq


def stop(db: Session, seq: SendSequence, reason: str,
         status: str = "stopped") -> SendSequence:
    seq.status = status
    seq.stopped_reason = reason
    seq.next_stage = None
    seq.next_due_date = None
    db.flush()
    return seq


def resume(db: Session, seq: SendSequence,
           rng: Optional[random.Random] = None) -> SendSequence:
    """중단했던 시퀀스를 다시 켠다. 다음 단계를 오늘 기준으로 다시 잡는다."""
    next_stage = STAGE_REMIND if seq.stage <= STAGE_DAY1 else STAGE_MEETING
    if seq.stage >= STAGE_MEETING:
        seq.status = "done"
        seq.next_stage = None
        seq.next_due_date = None
        db.flush()
        return seq
    seq.status = "active"
    seq.stopped_reason = None
    seq.next_stage = next_stage
    due = follow_up_date(db, _today(), next_stage, rng)
    seq.next_due_date = due.isoformat() if due else None
    db.flush()
    return seq


def stop_on_reaction(db: Session, contact_id: int, reason: str) -> Optional[SendSequence]:
    """IR 요청·미팅이 생기면 후속을 멈춘다.

    답이 왔는데도 "지난번 공유드린 기업들 검토 중…" 이 나가면
    상대는 이쪽이 자기 답을 못 봤다고 생각한다.
    """
    seq = db.execute(
        select(SendSequence).where(SendSequence.contact_id == contact_id,
                                   SendSequence.status == "active")
        .order_by(SendSequence.id.desc()).limit(1)
    ).scalars().first()
    if seq is None:
        return None
    return stop(db, seq, reason, status="responded")


# --- 화면용 조회 ------------------------------------------------------------

def sweep_reactions(db: Session, user_id: int) -> int:
    """IR 요청·미팅 기록이 생긴 담당자의 후속을 멈춘다.

    활동은 시트 임포트로도 들어오므로, 기록이 생기는 모든 길목에 훅을 다는 대신
    후속 화면을 열 때 한 번 훑는다. 놓치는 경로가 없고 비용도 작다(수십 건).
    """
    active = db.execute(
        select(SendSequence).where(SendSequence.user_id == user_id,
                                   SendSequence.status == "active")
    ).scalars().all()
    stopped = 0
    for seq in active:
        if has_reaction_since(db, seq.contact_id, seq.day1_sent_at):
            stop(db, seq, "IR 요청·미팅 기록이 있습니다", status="responded")
            stopped += 1
    if stopped:
        db.commit()
    return stopped


def due_sequences(db: Session, user_id: int,
                  today: Optional[date] = None) -> List[SendSequence]:
    """오늘까지 보내야 할 후속. 지난 날짜도 포함한다 — 놓친 것이 사라지면 안 된다."""
    today = today or _today()
    return db.execute(
        select(SendSequence)
        .where(SendSequence.user_id == user_id,
               SendSequence.status == "active",
               SendSequence.next_due_date.isnot(None),
               SendSequence.next_due_date <= today.isoformat())
        .order_by(SendSequence.next_due_date)
    ).scalars().all()


def sequence_rows(db: Session, user_id: int,
                  today: Optional[date] = None) -> List[dict]:
    """진행 중 시퀀스 표 한 줄 = 담당자 한 명."""
    today = today or _today()
    rows = db.execute(
        select(SendSequence).where(SendSequence.user_id == user_id)
        .order_by(SendSequence.next_due_date.is_(None),
                  SendSequence.next_due_date, SendSequence.id.desc())
    ).scalars().all()
    if not rows:
        return []

    contacts = {
        c.id: c for c in db.execute(
            select(VcContact).where(VcContact.id.in_([r.contact_id for r in rows]))
        ).scalars().all()
    }
    batches = {
        b.id: b for b in db.execute(
            select(DealBatch).where(
                DealBatch.id.in_([r.batch_id for r in rows if r.batch_id] or [0]))
        ).scalars().all()
    }

    out = []
    for seq in rows:
        contact = contacts.get(seq.contact_id)
        due = _as_date(seq.next_due_date)
        out.append({
            "id": seq.id,
            "contact_id": seq.contact_id,
            "name": contact.name if contact else "-",
            "title": (contact.title or "") if contact else "",
            "firm": (contact.firm or "") if contact else "",
            "room_name": (contact.kakao_room_name or "") if contact else "",
            "stage": seq.stage,
            "stage_label": STAGE_LABELS.get(seq.stage, "-"),
            "next_stage": seq.next_stage,
            "next_label": STAGE_LABELS.get(seq.next_stage or 0, ""),
            "next_mode": STAGE_MODES.get(seq.next_stage or 0, ""),
            "due": seq.next_due_date or "",
            "days_left": (due - today).days if due else None,
            "overdue": bool(due and due < today),
            "due_today": bool(due and due == today),
            "status": seq.status,
            "status_label": STATUS_LABELS.get(seq.status, seq.status),
            "batch_title": (batches.get(seq.batch_id).title
                            if seq.batch_id in batches else ""),
            "day1": (seq.day1_sent_at or "")[:10],
            "reason": seq.stopped_reason or "",
        })
    return out


def backfill_from_history(db: Session, user_id: int,
                          rng: Optional[random.Random] = None) -> int:
    """이미 보낸 딜소개에 대해 시퀀스를 만들어 준다.

    이 기능을 켜기 전에 나간 회차들은 시퀀스가 없어서 후속이 잡히지 않는다.
    한 번 훑어 채워 준다(같은 담당자에게 이미 시퀀스가 있으면 건너뛴다).
    """
    have = {
        seq.contact_id for seq in db.execute(
            select(SendSequence).where(SendSequence.user_id == user_id)
        ).scalars().all()
    }
    rows = db.execute(
        select(SendItem, SendJob)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.user_id == user_id, SendJob.kind == "deal_intro",
               SendItem.status == "sent")
        .order_by(SendItem.id)
    ).all()

    made = 0
    seen: Dict[int, tuple] = {}
    for item, job in rows:
        if item.contact_id is None or item.contact_id in have:
            continue
        seen[item.contact_id] = (item, job)      # 담당자별 마지막 성공 건
    for item, job in seen.values():
        if start_or_advance(db, item, job, rng) is not None:
            made += 1
    db.commit()
    return made


def has_reaction_since(db: Session, contact_id: int, since: Optional[str]) -> bool:
    """딜소개 이후에 IR 요청·미팅이 있었는지. 있으면 후속을 보낼 이유가 없다."""
    if not since:
        return False
    cutoff = since[:10]
    return bool(db.execute(
        select(ContactActivity.id).where(
            ContactActivity.contact_id == contact_id,
            ContactActivity.kind.in_(("ir_request", "meeting")),
            ContactActivity.happened_at.isnot(None),
            ContactActivity.happened_at >= cutoff,
        ).limit(1)
    ).first())

def batch_title(day: Optional[date] = None) -> str:
    """회차명 — `08/26 (8월 4주차)`.

    손으로 적으면 "8월회차" · "8월 셋째주" · "0826" 이 섞여 남는다. 나중에
    "몇 월 며칠에 뭘 보냈지" 를 찾을 때 이력이 갈라져 못 찾는다.
    보내는 날에서 그대로 만든다 — 고쳐 쓸 수는 있다.

    **날짜가 앞에 온다.** 주차만 있으면 며칠이었는지 다시 세어 봐야 한다.
    목록에서 회차를 짚는 기준은 결국 날짜다. 자리를 맞추려고 0 을 채운다
    (`08/26`) — 목록에서 세로로 줄이 맞는다.

    괄호 안에는 **달까지 적는다.** "4주차" 만 떼어 놓으면 어느 달인지 없어져,
    발송 이력을 여러 달에 걸쳐 볼 때 같은 이름이 매달 나온다.

    주차는 **1~7일이 1주차**다(`sheet_import.week_of_month`). 시트 머리글의
    "첫째주 수요일 / 셋째주" 표기가 그 규칙이고, 활동 이력도 그렇게 보여준다.
    한 화면에서 같은 날이 3주차와 4주차로 갈리면 안 된다.
    """
    from . import sheet_import

    day = day or date.today()
    week = sheet_import.week_of_month(day.isoformat())
    return f"{day.month:02d}/{day.day:02d} ({day.month}월 {week}주차)"
