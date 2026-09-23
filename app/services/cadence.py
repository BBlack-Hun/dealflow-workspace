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
from . import meeting_kind as mk

# 단계. message_composer 의 STAGE_* 와 같은 값을 쓴다.
STAGE_DAY1 = 1
STAGE_REMIND = 2
STAGE_MEETING = 3
#: 미팅 요청을 보내고 사흘 뒤 **전화로** 다시 청한다.
#:
#: 이 단계만 `message_composer` 에 짝이 없다 — 나가는 문구가 없기 때문이다.
#: 앞의 셋은 앱이 카톡을 보내지만 **전화는 사람이 건다.** 그래서 값도 여기서
#: 정한다(문구를 짓는 쪽이 모르는 단계다).
STAGE_CALL = 4

STAGE_LABELS = {
    STAGE_DAY1: "딜소개",
    STAGE_REMIND: "리마인드",
    STAGE_MEETING: "미팅 요청",
    STAGE_CALL: "전화 요청",
}
#: 다음 단계를 보낼 때 발송 화면에서 쓸 방식.
#:
#: **전화는 여기 없다.** 앱이 대신 걸 수 없으므로 갈 발송 화면이 없다 —
#: 화면은 이 표에 값이 있는 단계에만 [보내기] 를 세우고, 전화 단계에는
#: [전화함] 을 세운다(`templates/ir.html` 의 `전화 요청` 구역).
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
    # 미팅 요청 뒤 **사흘.** 앞 단계들처럼 범위를 벌리지 않는다(11~14 · 6~7).
    #
    # 범위를 두고 하루를 무작위로 고르는 까닭은 **한꺼번에 나가는 티를 없애려는
    # 것**이다(아래 `follow_up_date`) — 같은 날 같은 시각에 수십 통이 나가면
    # 받는 쪽에도 카카오 쪽에도 그렇게 보인다. 전화는 앱이 보내지 않는다.
    # 사람이 하루에 몇 통 거는 일이라 몰릴 것이 없고, 사용자가 말한 것도
    # "3일 후" 하나다. 그래서 최소·최대를 같은 값으로 둔다 — `follow_up_date`
    # 의 `randint(3, 3)` 은 늘 3이다.
    #
    # **주말은 그대로 건너뛴다**(`skip_weekend=1`). 여기만 안 건너뛰면 토요일
    # 아침에 걸 곳이 목록에 서고, 월요일에는 이미 '이틀 지남' 이 된다.
    #
    # 고정이되 **박아 둔 것은 아니다.** 다른 단계와 같은 `schedule_rules` 줄이라
    # 관리자가 화면에서 늘릴 수 있다(`/ir#rules`) — 주기가 코드에 박혀 있어
    # 바뀔 때마다 배포해야 했던 것이 이 표를 만든 까닭이다.
    "call": dict(label="전화 요청", kind="offset_days",
                 offset_min_days=3, offset_max_days=3, skip_weekend=1),
}


#: 날짜 간격 규칙이 **무엇을 기준으로 세는가.** 화면의 `발송 주기` 판이 이 말을
#: 그대로 쓴다 — 전에는 전부 `딜소개 …일 뒤` 라고 적혀 있었는데, 전화는 딜소개가
#: 아니라 **미팅 요청을 보낸 날**에서 센다(`advance`). 화면이 코드와 다른 말을
#: 하면 사람은 화면을 믿고 날짜를 잘못 짚는다.
OFFSET_BASE = {"remind": "딜소개", "meeting": "딜소개", "call": "미팅 요청"}


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
    extra = [d for d in _date_list(rule.get("extra_dates"))
             if d >= today and d not in skip_days]

    out: List[date] = []
    year, month = today.year, today.month
    # 규칙이 이상해도 무한 루프에 빠지지 않게 살펴볼 달 수를 제한한다.
    for _ in range(36):
        # **규칙에서 나온 날만 세어 멈춘다.** 일회성 회차일을 함께 세면, 그 날이
        # 뒤에 있어도 개수가 먼저 차서 규칙 날짜를 찾기 전에 멈춘다 —
        # `count=1` 로 물으면 **더 이른 회차일을 건너뛴 답**이 나왔다
        # (8/26 이 일회성으로 잡힌 달에 8/10 에서 물으면 8/19 대신 8/26).
        if len(out) >= count:
            break
        for nth in nths:
            day = next_business_day(nth_weekday(year, month, weekday, nth), skip)
            if day >= today and day not in out and day not in skip_days:
                out.append(day)
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return sorted(set(out) | set(extra))[:count]


def follow_up_date(db: Session, sent_on: date, stage: int,
                   rng: Optional[random.Random] = None) -> Optional[date]:
    """다음 후속을 보낼 날.

    범위 안에서 하루를 무작위로 고른다. 모두 같은 날 같은 시각에 나가면
    받는 쪽에서도 티가 나고, 카카오 쪽에서도 한 번에 몰린 발송으로 보인다.
    """
    key = {STAGE_REMIND: "remind", STAGE_MEETING: "meeting",
           STAGE_CALL: "call"}.get(stage)
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
    """**앱이 보낸 건**이 성공했을 때 부른다.

    판정은 하지 않는다 — 발송 건에서 값을 꺼내 아래 `advance` 에 넘기기만
    한다. 단계를 어떻게 올리고 다음 날짜를 언제로 잡는지는 거기 한 곳이다.
    """
    if item.status != "sent":
        return None
    # 딜 소싱 제안은 후속 3단(리마인드 → 미팅 요청)을 타지 않는다.
    # 딜을 봐 달라는 초대라 "검토 중이신가요" 를 이어 보낼 것이 없다.
    if item.contact_id is None:
        return None
    return advance(db, user_id=job.user_id, contact_id=item.contact_id,
                   batch_id=job.batch_id, kind=job.kind,
                   stage=item.stage or STAGE_DAY1, sent_at=item.sent_at,
                   rng=rng)


def advance(db: Session, *, user_id: int, contact_id: int,
            batch_id: Optional[int], kind: str, stage: Optional[int],
            sent_at: Optional[str],
            rng: Optional[random.Random] = None) -> Optional[SendSequence]:
    """**무엇이 나갔다**는 사실 하나로 시퀀스를 시작하거나 다음 단계로 넘긴다.

    - 딜소개(stage 1) → 시퀀스 시작, 리마인드 예약
    - 리마인드(stage 2) → 미팅 요청 예약
    - 미팅 요청(stage 3) → 끝
    - IR 자료 전달은 답이 왔다는 뜻이므로 시퀀스를 멈춘다

    ## 왜 `SendItem` 을 안 받는가

    손으로 보낸 것을 적는 길이 생겼다(`services/manual_send.py`). 그쪽에는
    발송 건도 회차도 없다 — 사람이 카톡에서 직접 보내고 나서 적는 것이다.
    그렇다고 **판정을 두 벌로 만들지 않는다.** 단계 사다리와 다음 예정일
    계산이 두 곳에 있으면, 한쪽만 고쳐진 날 손으로 보낸 사람의 후속만 다른
    날짜로 잡힌다 — 그런 어긋남은 몇 달 뒤에야 드러난다.

    그래서 **받는 것을 값으로 내렸다.** 앱이 보낸 건은 위 `start_or_advance`
    가 발송 건에서 값을 꺼내 넘기고, 손으로 적은 것은 그 값을 직접 넘긴다.
    둘 다 여기 한 함수를 지난다.

    `kind` 는 `SendJob.kind` 의 말이고 `stage` 는 `SendItem.stage` 의 말이다 —
    부르는 쪽이 자기 말로 바꾸지 않는다(`manual_send.AS_SEND` 가 옮긴다).
    """
    seq = db.execute(
        select(SendSequence).where(SendSequence.contact_id == contact_id)
        .order_by(SendSequence.id.desc()).limit(1)
    ).scalars().first()

    stage = stage or STAGE_DAY1
    sent_on = _as_date(sent_at) or _today()

    if kind == "ir_delivery":
        # 자료를 보냈다는 것은 상대가 달라고 했다는 뜻이다.
        if seq and seq.status == "active":
            stop(db, seq, "IR 자료를 전달했습니다", status="responded")
        return seq

    if stage == STAGE_DAY1:
        if seq is not None and seq.status == "active":
            # 같은 사람에게 새 회차를 보냈다면 그 회차 기준으로 다시 센다.
            seq.batch_id = batch_id
        else:
            seq = SendSequence(user_id=user_id, contact_id=contact_id,
                               batch_id=batch_id)
            db.add(seq)
        seq.stage = STAGE_DAY1
        seq.status = "active"
        seq.stopped_reason = None
        seq.day1_sent_at = sent_at or _now_iso()
        seq.last_sent_at = seq.day1_sent_at
        seq.next_stage = STAGE_REMIND
        due = follow_up_date(db, sent_on, STAGE_REMIND, rng)
        seq.next_due_date = due.isoformat() if due else None
        db.flush()
        return seq

    if seq is None or seq.status != "active":
        return seq

    seq.stage = stage
    seq.last_sent_at = sent_at or _now_iso()
    if stage == STAGE_REMIND:
        seq.next_stage = STAGE_MEETING
        # 미팅 요청은 **딜소개일 기준**으로 잡는다. 리마인드가 늦어졌다고
        # 미팅 요청까지 밀리면 회차 간격이 뒤엉킨다.
        base = _as_date(seq.day1_sent_at) or sent_on
        due = follow_up_date(db, base, STAGE_MEETING, rng)
        seq.next_due_date = due.isoformat() if due else None
    elif stage == STAGE_MEETING:
        seq.next_stage = STAGE_CALL
        # 전화는 **미팅 요청을 보낸 날 기준**이다 — 사용자가 말한 것이
        # "미팅 요청 보내고 3일 후" 다. 위 미팅 요청이 딜소개일을 기준으로
        # 잡는 것과 다른데, 그 까닭도 다르다: 미팅 요청은 회차 간격에 매인
        # 일이라 딜소개일에서 세야 간격이 안 뒤엉키지만, 전화는 **그 카톡에
        # 대한 답을 기다리는 사흘**이다. 딜소개일에서 세면 미팅 요청이 늦게
        # 나간 건은 보내기도 전에 전화할 날이 지나 있다.
        due = follow_up_date(db, sent_on, STAGE_CALL, rng)
        seq.next_due_date = due.isoformat() if due else None
    else:
        seq.next_stage = None
        seq.next_due_date = None
        seq.status = "done"
    db.flush()
    return seq


def mark_called(db: Session, seq: SendSequence,
                when: Optional[str] = None,
                rng: Optional[random.Random] = None) -> Optional[SendSequence]:
    """**전화를 걸었다**고 적는다 — 흐름의 마지막 단계다.

    앞 단계들은 앱이 보내고 나서 저절로 올라간다(`start_or_advance`). 전화는
    앱이 대신 걸 수 없으니 사람이 눌러 줘야 하고, 그래서 화면의 단추가
    **[보내기] 가 아니라 [전화함]** 이다(`templates/ir.html`).

    **단계를 여기서 올리지 않는다.** 사다리도 다음 예정일도 `advance` 한 곳이
    쥐고 있다 — 손으로 적는 길이 제 손으로 단계를 올리면 두 벌이 되고, 한쪽만
    고쳐지는 날 전화로 끝낸 건만 다른 상태로 남는다(`services/manual_send.py`
    가 같은 까닭으로 같은 함수를 지난다).

    `kind` 는 딜소개 흐름 그대로다 — 전화는 **그 흐름의 한 단계**이지 다른
    갈래가 아니다. 새 갈래를 만들면 `kind` 로 거르는 자리가 그 값을 몰라 이
    건을 안 읽는다.
    """
    return advance(db, user_id=seq.user_id, contact_id=seq.contact_id,
                   batch_id=seq.batch_id, kind="deal_intro",
                   stage=STAGE_CALL, sent_at=when or _now_iso(), rng=rng)


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
    # 사다리는 **한 줄**이다 — 여기서 단계를 손으로 세지 않는다. 미팅 요청까지
    # 보낸 건은 그 다음이 전화 요청이고, 전화까지 한 건은 더 할 것이 없다.
    nxt = {STAGE_DAY1: STAGE_REMIND, STAGE_REMIND: STAGE_MEETING,
           STAGE_MEETING: STAGE_CALL}
    next_stage = nxt.get(max(seq.stage, STAGE_DAY1))
    if next_stage is None:
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
    리마인드 구역을 열 때 한 번 훑는다. 놓치는 경로가 없고 비용도 작다(수십 건).
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
            # 마지막으로 **끝낸 단계가 언제 것인가.** 전화 구역이 "미팅 요청
            # 언제 보냈는지" 를 이 값으로 적는다 — 딜소개일(`day1`)을 적으면
            # 사흘을 어디서부터 셌는지가 화면에서 안 맞아 보인다.
            "last_sent": (seq.last_sent_at or "")[:10],
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
            # 미팅은 갈래가 넷이다 — **청한 것도 반응**이라 넷을 다 본다
            # (갈래 목록은 `services/meeting_kind` 한 곳).
            ContactActivity.kind.in_(("ir_request",) + mk.ALL),
            ContactActivity.happened_at.isnot(None),
            ContactActivity.happened_at >= cutoff,
        ).limit(1)
    ).first())

def cycle_anchor(db: Optional[Session] = None,
                 today: Optional[date] = None) -> date:
    """오늘이 속한 **회차의 기준일**. 회차명은 이 날짜에서 나온다.

    회차를 가르는 것은 **주**다. 같은 주에 나눠 보낸 것은 한 회차다 — 회차일에
    다 못 보내고 다음 날 이어 보내는 일이 실제로 있고, 그때 회차가 넘어가면
    한 번 보낸 것이 두 회차로 갈라져 남는다.

    `upcoming_send_dates` 를 **오늘이 아니라 그 주 월요일부터** 찾는 것이 전부다.
    오늘부터 찾으면 회차일이 하루라도 지나는 순간 다음 회차일로 건너뛴다 —
    8/26(수)에 보내다 8/27(목)에 이어 보내면 회차명이 `09/02` 로 바뀌었다.
    주 월요일부터 찾으면 그 주에 있는 회차일을 **지났더라도** 집는다.

    회차일이 없는 주는 그대로 다음 회차일을 집는다(찾기 시작하는 날만 당겼을
    뿐이라, 그 주에 아무것도 없으면 오늘부터 찾은 것과 같은 날이 나온다).

    주 경계는 **주간 업무와 같은 것**을 쓴다(`weekly.week_start`, 월요일 시작).
    두 벌로 정의하면 한쪽만 고쳐지는 날 같은 날이 다른 주로 갈린다.
    딜 주기는 수요일(`ScheduleRule`)이라 월~일 주 안에 온전히 들어간다 —
    주 경계가 회차일을 가르지 않는다.
    """
    from . import weekly

    today = today or date.today()
    return upcoming_send_dates(db, weekly.week_start(today), count=1)[0]


def batch_title(day: Optional[date] = None,
                cycle_day: Optional[date] = None) -> str:
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

    `cycle_day` — **괄호 안 달·주차를 어느 날에서 셀지.** 기본은 `day` 자신이라
    받은 날짜 하나로 정해지는 순수 함수 그대로다(저장된 회차 이름은 이 길로
    만들어졌고, 오늘이 언제든 같은 값이어야 한다).

    앞 날짜와 괄호 안이 갈릴 수 있는 것은 **회차 주차가 회차의 이름**이기
    때문이다 — 사람들은 "첫째주 회차 / 셋째주 회차" 라고 부른다. 주차 칸은
    1~7일씩 끊으므로 회차일이 7·14·21일이면 그 다음 날은 다음 칸으로 넘어간다.
    2/7 회차를 2/8 에 보내면서 `2월 2주차` 라 적으면 같은 회차가 두 이름으로
    남아, 이력을 주차로 찾을 때 갈라진다. 그래서 날짜는 보낸 날, 주차는 회차다
    (`default_batch_title` 가 그렇게 부른다).
    """
    from . import sheet_import

    day = day or date.today()
    cycle_day = cycle_day or day
    week = sheet_import.week_of_month(cycle_day.isoformat())
    return f"{day.month:02d}/{day.day:02d} ({cycle_day.month}월 {week}주차)"


def default_batch_title(db: Optional[Session] = None,
                        today: Optional[date] = None,
                        label: Optional[str] = None) -> str:
    """새 회차를 만들 때 화면에 채워 줄 회차명 — 앞 날짜는 **오늘**이다.

    `label` 을 주면 **정규 발송이 아닌** 회차다 — `09/09 (리마인드)` 처럼
    괄호 안에 주차 대신 **무엇을 보내는지**가 들어가고, 앞 날짜는 언제나
    오늘이다. 아래 회차 기준일 이야기는 전부 정규 발송(딜 소개) 것이다.

    회차명 앞 날짜는 회차 기준일이었다. 그래서 9/2 회차 주의 9/3 에 화면을
    열면 `09/02 (9월 1주차)` 가 채워졌다 — 오늘 만드는 회차인데 이름에는
    어제가 적힌다. 나중에 "몇 월 며칠에 뭘 보냈지" 를 찾는 기준은 결국
    **보낸 날**이라, 앞 날짜는 오늘이어야 한다.

    **다만 회차일이 아직 오지 않았으면 회차 기준일을 쓴다.** 그때는 보낸
    날이 없다 — 다음 회차를 미리 준비하는 중이고, 이름도 그 회차의 날짜여야
    한다. 오늘을 그냥 쓰면 8/31(월)에 준비한 9/2 회차가 `08/31 (8월 5주차)`
    로 남아 **9월 회차가 8월 이름을 단다.** 회차 주 밖에서도 마찬가지다 —
    9/10 에 오늘을 쓰면 `09/10 (9월 2주차)` 가 되어 9/16(3주차) 회차가
    2주차로 적힌다.

    그래서 가르는 것은 **오늘이 회차 기준일보다 앞이냐** 하나다. 요일로 적지
    않는다 — 지금은 딜 주기가 첫째·셋째 수요일이라 월·화가 그 앞이지만,
    주기는 `ScheduleRule` 이 정하고 실제로 한 번 바뀌었다. 요일을 박아 두면
    그날 낡는다.

    **주 판단은 여기에 없다.** `cycle_anchor` 가 이번 주 월요일부터 찾으므로
    기준일이 오늘보다 앞이면 반드시 같은 주다 — 회차 주 밖은 늘 '기준일이
    아직 안 왔다' 쪽에 걸린다. 주 경계를 여기서 또 재면 `weekly.week_start`
    와 두 벌이 되어 한쪽만 고쳐지는 날 회차와 이름이 갈린다.

    **이미 저장된 회차 이름은 건드리지 않는다.** 여기서 나오는 것은 화면
    입력칸의 기본값뿐이고, 저장되는 이름은 사람이 화면에서 확정한 그 값이다
    (`deals.py` 가 `req.title` 을 그대로 넣는다). 지난 회차 이름이 오늘에
    따라 달라지면 발송 이력이 갈라진다 — `batch_title(day)` 는 받은 날짜만으로
    정해지는 그대로 둔다.

    **괄호 안 주차는 언제나 회차 기준일의 것이다**(`cycle_day=anchor`). 앞 날짜에서
    다시 세지 않는다 — 주차 칸은 1~7일씩 끊으므로(`sheet_import.week_of_month`)
    회차일이 7·14·21일이면 그 다음 날은 다음 칸으로 넘어간다. 2/7 회차를 2/8 에
    보내면서 `2월 2주차` 라 적으면 같은 회차가 두 이름으로 남는다.

    주차가 곧 **회차의 이름**이기 때문이다 — 사람들은 "첫째주 회차 / 셋째주 회차"
    라고 부르고, 시트 머리글도 "첫째주 수요일 / 셋째주" 다. 이력을 주차로 찾을 때
    갈라지지 않으려면 주차는 회차를 가리켜야 한다. 그래서 **날짜는 보낸 날,
    주차는 회차**로 출처가 갈린다 — 주차를 세는 규칙 자체는 하나뿐이다.

    **정규 발송이 아니면 주차를 빼고 무엇을 보내는지 적는다**(`label`).
    리마인드·미팅 요청은 회차에 매인 것이 아니다 — 딜 소개를 받은 사람이
    답이 없어서, 미팅을 잡으려고, 그날 그때 보낸다. 그런데 이름은 전부
    `09/16 (9월 3주차)` 로 같았다. 발송 이력에 같은 이름이 여러 줄 남아
    무엇이 딜 소개고 무엇이 리마인드인지 이름만으로는 갈라지지 않았다.

    **앞 날짜도 회차 기준일이 아니라 오늘이다.** 회차 기준일을 쓰는 까닭은
    괄호 안 주차가 그 회차를 가리키기 때문인데(위), 주차를 빼고 나면 회차를
    가리킬 것이 없다. 9/14(월)에 보내는 리마인드가 `09/16 (리마인드)` 로
    남으면 **보내지도 않은 이틀 뒤 날짜**가 적힌다 — 정규 발송은 그 이틀 뒤가
    회차일이라 뜻이 있었지만, 여기서는 그냥 틀린 날이다. 날짜를 보고 "언제
    보냈지" 를 찾는 것은 두 쪽이 같다.

    **괄호 안 말은 여기서 짓지 않는다.** 화면 탭에 쓰는 이름을 그대로 받는다
    (`deals.MODE_TITLES`) — 두 군데 적으면 탭 이름만 고쳐지는 날 회차명이
    낡은 말을 단 채 남는다.
    """
    today = today or _today()
    if label:
        return f"{today.month:02d}/{today.day:02d} ({label})"
    anchor = cycle_anchor(db, today)
    return batch_title(today if today >= anchor else anchor, cycle_day=anchor)
