"""2단계 자동화의 **공통 틀** — 언제 세우고, 누구에게, 몇 시에.

스타트업 월간 자동 예약(`services/startup_monthly.py`)과 결과 문의 대기 목록
(`services/auto_send.py`)이 각자 들고 있던 얼개를 하나로 모은다. 자동화
하나가 아는 것은 둘뿐이다.

  `plan(db, 설정, 날)`        → 그날 세울 회차가 있나. 있으면 (회차 열쇠, 나갈 시각)
  `collect(db, 설정, 계정, 회차)` → 누구에게 무엇을 — `automation.Out` 목록

나머지는 전부 여기 한 곳이다.

1. **아침에 세운다** — 그날 `PREPARE_HOUR`(08시) 이후 첫 깨어남에 회차를
   `draft` 로 세우고 나갈 시각을 예약으로 건다(`scheduled_send`). 푸는 것은
   예약이다 — 발송 경로를 새로 만들지 않는다.
2. **보내는 계정 것으로** — `automation.sender`. 그 계정 PC 의 발송기만
   집어간다.
3. **시험 모드면 시험방으로** — `automation.build_job` 이 한 통마다 바꾼다.
4. **한 회차는 한 번** — `auto_send_runs` 의 `(kind, ref_id)` 유일 색인에
   **목록을 만들기 전에** 자리를 잡는다(`startup_monthly` 와 같은 까닭: 만든
   뒤에 적으면 그 틈에 한 벌 더 선다). `kind` 는 `auto:<열쇠>`(시험 모드면
   `auto:<열쇠>:test` — 시험이 실제 회차를 막지 않게).
5. **한 대상은 한 번** — `automation_sends` 의 `(자동화, ref, 시험)`.
6. **오늘 할 일에 선다** — 선 회차는 보내는 계정의 오늘 할 일에 예약으로 서고
   (`scheduled_send.standing_for`), 그 시각 전에 진행 화면에서 [중단] 할 수
   있다. 못 세운 날(0건 · 실패)은 그 사유가 보내는 계정과 관리자의 오늘 할
   일에 선다(`today_items`).
7. **보내는 시간 · 하루 상한 · 실패 알림은 `send_guard` 가 지킨다** — 자동
   회차는 전부 `auto_send_runs.job_id`(또는 `automation_sends.job_id`)로
   이어져 있어 실패 메일·오늘 할 일 알림이 그대로 걸린다.

## 늦게 세우지 않는다

나갈 시각이 지나도록 못 세웠으면(서버가 멈춰 있었다 등) 그 회차는 건너뛴다.
몇 시간 늦게 조용히 나가는 것이 더 위험하다 — `scheduled_send` 머리말과 같은
판단이다. 날마다 도는 자동화(미팅 후 문의 · 미팅 요청)는 대상을 며칠 치
돌아보므로 다음 날 회차가 그 대상을 줍는다.

## 0건이면

세우지 않는다. 그날 시각 전까지 **다시 본다**(아침에 방 이름을 넣으면 낮에
서야 한다). 끝내 0건이면 그 사유가 오늘 할 일에 남는다.

## 풀기 직전에 한 번 더 본다 (`prune`)

아침에 세운 뒤 14시 전에 결과를 적었거나 미팅이 취소됐을 수 있다. 예약이
풀리는 순간 자동화마다 `still_ok` 로 다시 보고, 더는 보낼 까닭이 없는 건은
`canceled` 로 뺀다 — 그 사유가 진행 화면의 표에 남는다.

## 스타트업 월간 자동 예약

이 틀이 그 얼개를 일반화한 것이지만, 이 PR 에서는 **옮기지 않는다** — 월간
발송은 지금 운영에서 켜져 돌고 있고, 날짜·문구 순환을 바꾸는 PR(A5)이 이
틀 위로 옮긴다.
"""
from __future__ import annotations

import logging
import random
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..db import SessionLocal
from ..models import (AutoSendRun, Automation, AutomationSend, SendItem,
                      SendJob, User)
from . import automation, scheduled_send

log = logging.getLogger(__name__)

#: 그날 몇 시부터 회차를 세우나. 사람이 출근해 오늘 할 일에서 보고 나가기
#: 전에 빼거나 [중단] 할 틈이 남게 아침에 세운다(`startup_monthly` 와 같은 값).
PREPARE_HOUR = 8

#: 얼마나 자주 깨어나 보나. 하루 한 번 서는 일이라 촘촘할 까닭이 없다.
CHECK_INTERVAL_SEC = 5 * 60

#: `auto_send_runs.kind` 머리.
RUN_PREFIX = "auto:"

STATUS_CLAIMED = "claimed"   # 세우는 중
STATUS_READY = "ready"       # 회차가 섰다(예약 걸림)
STATUS_EMPTY = "empty"       # 보낼 곳이 0곳 — 그날 다시 본다
STATUS_FAILED = "failed"     # 세우다 실패했다 — 사유를 남긴다

_SCHEDULER: Optional[threading.Thread] = None


# ── 자동화 하나가 아는 것 ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Plan:
    """그날 세울 회차 하나."""

    #: `auto_send_runs.ref_id` — 날(`YYYYMMDD`) · 주(`YYYYWW`) · 달 등 그 자동화의
    #: 한 회차를 가리키는 수. 이 수가 같으면 두 번 세우지 않는다.
    period: int
    #: 첫 한 통이 나갈 시각.
    at: datetime


@dataclass
class Batch:
    """`collect` 가 돌려주는 것 — 보낼 것과 **뺀 것**."""

    outs: List[automation.Out] = field(default_factory=list)
    #: 뺀 대상과 사유(`홍길동(가나다벤처스) — 방 이름 없음`). 화면에 남는다.
    skipped: List[str] = field(default_factory=list)
    #: 0건일 때 오늘 할 일에 적을 말. 비면 기본 문장.
    note: str = ""
    #: 한 통마다 회차를 따로 세워 **분 단위로 띄울** 폭(최소, 최대 분). 채널방처럼
    #: 여러 방에 같은 글이 몰려 나가지 않게 할 때.
    spacing: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class Field:
    """자동화마다 다른 값 하나 — 팀 현황 판에 칸 하나로 선다.

    `kind` 가 받는 모양을 정한다. 값을 가리는 것은 `clean_params` 한 곳이다.
      int   — 정수(`low`~`high`)
      time  — `HH:MM`, 보내는 시간(09~19시) 안
      text  — 한 줄 글
      lines — 여러 줄(한 줄에 하나) → 목록
    """

    name: str
    label: str
    kind: str
    default: object
    low: int = 0
    high: int = 0
    hint: str = ""


@dataclass(frozen=True)
class Spec:
    key: str
    #: 실제 모드에서 회차의 종류(`deal_intro` · `sourcing_intro` …).
    kind: str
    plan: Callable[[Session, Automation, date], Optional[Plan]]
    collect: Callable[[Session, Automation, User, Plan], Batch]
    #: 예약이 풀리기 직전에 한 번 더 — 빈 글자면 보낸다, 아니면 그 사유로 뺀다.
    still_ok: Optional[Callable[[Session, AutomationSend], str]] = None
    #: 이 자동화가 오늘 할 일에 따로 세울 줄(예: 내일 나갈 곳). `today.py` 모양.
    notes: Optional[Callable[[Session, User, Automation, datetime], List[dict]]] = None
    #: 팀 현황 판에서 고치는 값들(며칠 뒤 · 몇 시 …). 기본값이 곧 동작이다.
    fields: Tuple[Field, ...] = ()
    #: 칸들을 넘어선 검사(예: 두 날짜의 차례). 못 받을 값이면 `ValueError`.
    check: Optional[Callable[[dict], None]] = None
    #: 팀 현황 판에 덧붙일 한 줄(예: 채널방 최근 발송). 빈 글자면 안 적는다.
    describe: Optional[Callable[[Session, Optional[Automation]], str]] = None
    #: 실제 모드 회차의 `SendJob.topic` — 같은 종류 안에서 **무슨 글이었나**
    #: (예: 딜 소싱 `sourcing_remind`). 손으로 보낸 회차와 같은 이름으로 남는다.
    topic: Optional[str] = None


REGISTRY: Dict[str, Spec] = {}


def register(spec: Spec) -> Spec:
    """자동화 하나를 틀에 단다. 열쇠는 `automation.KINDS` 에 있어야 한다."""
    if spec.key not in automation.BY_KEY:
        raise ValueError(f"모르는 자동화: {spec.key}")
    REGISTRY[spec.key] = spec
    return spec


def _load_all() -> None:
    """자동화 모듈들을 읽어 틀에 달리게 한다(각 모듈이 읽힐 때 `register`)."""
    from . import automations  # noqa: F401


# ── 자동화마다 다른 값 ────────────────────────────────────────────────────────

def parse_time(raw) -> str:
    """`HH:MM` 으로 다듬는다. 보내는 시간(09~19시) 밖이면 `ValueError`.

    고르는 폭은 예약과 같다 — 저장 자리에서 자른다(`startup_monthly.parse_time`
    와 같은 규칙을 그대로 부른다).
    """
    from . import startup_monthly

    return startup_monthly.parse_time(str(raw or ""))


def _clean_one(field_: Field, raw):
    if field_.kind == "int":
        try:
            number = int(str(raw).strip())
        except (TypeError, ValueError):
            raise ValueError(f"{field_.label} — 숫자를 넣으세요") from None
        if not (field_.low <= number <= field_.high):
            raise ValueError(f"{field_.label} — {field_.low}~{field_.high} 사이로 넣으세요")
        return number
    if field_.kind == "time":
        try:
            return parse_time(raw)
        except ValueError as exc:
            raise ValueError(f"{field_.label} — {exc}") from None
    if field_.kind == "lines":
        if isinstance(raw, (list, tuple)):
            items = [str(v).strip() for v in raw]
        else:
            items = [line.strip() for line in str(raw or "").splitlines()]
        return [v for v in items if v]
    return str(raw or "").strip()


def values(row: Optional[Automation], key: str) -> dict:
    """이 자동화가 지금 쓰는 값 — 저장된 값, 없거나 못 읽으면 기본값."""
    _load_all()
    spec = REGISTRY.get(key)
    stored = automation.params(row)
    out = {}
    for field_ in (spec.fields if spec else ()):
        if field_.name in stored:
            try:
                out[field_.name] = _clean_one(field_, stored[field_.name])
                continue
            except ValueError:
                log.warning("자동화 %s 의 %s 값이 맞지 않아 기본값을 씁니다",
                            key, field_.name)
        out[field_.name] = field_.default
    return out


def clean_params(key: str, raw: dict) -> dict:
    """화면에서 온 값들을 가린다. **못 받을 값이면 `ValueError`** — 까닭이 화면에 간다.

    폼에 없는 칸은 기본값이다. 화면만 막으면 주소로 폼을 흉내 내는 순간 뚫린다
    — 저장 자리에서 자른다(`auto_send.save` 와 같은 까닭).
    """
    _load_all()
    spec = REGISTRY.get(key)
    if spec is None:
        return {}
    out = {}
    for field_ in spec.fields:
        out[field_.name] = (_clean_one(field_, raw[field_.name])
                            if field_.name in raw else field_.default)
    if spec.check is not None:
        spec.check(out)
    return out


def save_params(db: Session, key: str, raw: dict) -> dict:
    """값을 저장한다(줄이 없으면 꺼짐 · 시험 모드로 선다). 커밋까지 한다."""
    cleaned = clean_params(key, raw)
    row = automation.load(db, key)
    if row is None:
        row = Automation(key=key, enabled=0, test_mode=1)
        db.add(row)
    automation.set_params(row, cleaned)
    db.commit()
    return cleaned


def at_on(day: date, hhmm: str) -> datetime:
    """그날 그 시각(이 프로세스 시간대)."""
    hour, minute = (int(part) for part in parse_time(hhmm).split(":"))
    return datetime(day.year, day.month, day.day, hour, minute).astimezone()


def day_key(day: date) -> int:
    return day.year * 10000 + day.month * 100 + day.day


# ── 회차 자리 ────────────────────────────────────────────────────────────────

def run_kind(key: str, test: bool) -> str:
    return f"{RUN_PREFIX}{key}{':test' if test else ''}"


def run_row(db: Session, key: str, test: bool, period: int) -> Optional[AutoSendRun]:
    return db.execute(
        select(AutoSendRun).where(AutoSendRun.kind == run_kind(key, test),
                                  AutoSendRun.ref_id == period)
    ).scalars().first()


def _claim(db: Session, key: str, test: bool, period: int, user_id: int,
           day: date) -> Optional[AutoSendRun]:
    """이 회차 자리를 잡는다. 이미 끝난 회차면 `None`.

    `empty`(0곳) 인 자리만 다시 잡을 수 있다 — 그날 방 이름을 넣으면 서야 한다
    (`startup_monthly._claim` 과 같은 규칙).
    """
    row = run_row(db, key, test, period)
    if row is None:
        row = AutoSendRun(kind=run_kind(key, test), ref_id=period,
                          user_id=user_id, day=day.isoformat(),
                          status=STATUS_CLAIMED)
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
            job_id: Optional[int] = None, error: str = "") -> None:
    row.status = status
    row.job_id = job_id
    row.error = (error or None) and error[:1000]
    db.commit()


# ── 대상 자리 ────────────────────────────────────────────────────────────────

def sent_refs(db: Session, key: str, test: bool, refs) -> set:
    """이미 '보냈다' 줄이 선 `ref` 들."""
    refs = list(refs)
    if not refs:
        return set()
    return set(db.execute(
        select(AutomationSend.ref).where(AutomationSend.automation == key,
                                         AutomationSend.test == (1 if test else 0),
                                         AutomationSend.ref.in_(refs))
    ).scalars().all())


def _rows_for(key: str, test: bool, run: AutoSendRun, job: SendJob,
              out: automation.Out) -> List[AutomationSend]:
    common = dict(automation=key, test=1 if test else 0, run_id=run.id,
                  job_id=job.id, item_id=out.item_id, room=out.room,
                  contact_id=out.contact_id,
                  sourcing_contact_id=out.sourcing_contact_id)
    if out.company_ids:
        return [AutomationSend(ref=f"{out.ref}:{cid}", company_id=cid, **common)
                for cid in out.company_ids]
    return [AutomationSend(ref=out.ref, **common)]


# ── 하루 한 번 ───────────────────────────────────────────────────────────────

def _offsets(batch: Batch, period: int, key: str, count: int) -> List[int]:
    """한 통마다 회차를 띄울 분. 띄우지 않으면 전부 0.

    **회차마다 같은 값**이 나온다(씨앗이 자동화 × 회차) — 같은 회차를 다시
    계산해도(화면 미리보기 등) 시각이 흔들리지 않는다.
    """
    if not batch.spacing or count <= 1:
        return [0] * count
    low, high = batch.spacing
    rng = random.Random(f"{key}:{period}")
    out, total = [0], 0
    for _ in range(count - 1):
        total += rng.randint(low, max(low, high))
        out.append(total)
    return out


def run_once(db: Session, key: str, now: Optional[datetime] = None) -> dict:
    """오늘이 그날이면 회차를 세운다. 아니면 아무것도 안 한다.

    돌려주는 `status` 는 무엇을 했는가다 — `off` · `not_ready` · `no_sender` ·
    `no_test_room` · `not_today` · `too_early` · `too_late` · `done` 이면
    아무것도 바꾸지 않았다.
    """
    _load_all()
    now = scheduled_send._aware(now or clock.now())
    row = automation.load(db, key)
    if not automation.is_on(row):
        return {"status": "off"}
    spec = REGISTRY.get(key)
    if spec is None:
        return {"status": "not_ready"}
    who = automation.sender(db, row)
    if who is None:
        return {"status": "no_sender"}
    test = automation.is_test(row)
    test_room = None
    if test:
        if automation.test_room_problem(db, row.test_room):
            return {"status": "no_test_room"}
        test_room = automation.clean_room(row.test_room)

    today = now.date()
    plan = spec.plan(db, row, today)
    if plan is None:
        return {"status": "not_today"}
    if now.hour < PREPARE_HOUR:
        return {"status": "too_early"}
    at = scheduled_send._aware(plan.at)
    if now >= at:
        return {"status": "too_late"}

    claim = _claim(db, key, test, plan.period, who.id, today)
    if claim is None:
        return {"status": "done"}

    try:
        batch = spec.collect(db, row, who, plan)
    except Exception as exc:  # noqa: BLE001 - 자동화 하나가 실을 죽이면 안 된다
        db.rollback()
        log.exception("자동화 %s — 대상을 모으다 실패했습니다", key)
        _finish(db, run_row(db, key, test, plan.period), STATUS_FAILED,
                error=f"대상을 모으다 실패했습니다: {exc}")
        return {"status": STATUS_FAILED}

    done = sent_refs(db, key, test, [o.ref for o in batch.outs if not o.company_ids])
    done |= {ref.rsplit(":", 1)[0] for ref in sent_refs(
        db, key, test, [f"{o.ref}:{c}" for o in batch.outs for c in o.company_ids])}
    fresh = [o for o in batch.outs if o.ref not in done]
    if not fresh:
        note = batch.note or "보낼 곳이 0곳입니다"
        if batch.skipped:
            note += f" (뺀 곳 {len(batch.skipped)}: " + "; ".join(batch.skipped[:5]) + ")"
        _finish(db, claim, STATUS_EMPTY, error=note)
        return {"status": STATUS_EMPTY, "skipped": batch.skipped}

    label = automation.BY_KEY[key].label
    title = f"{label} 자동{' (시험)' if test else ''} {scheduled_send.label(at)}"
    offsets = _offsets(batch, plan.period, key, len(fresh))
    groups = ([[o] for o in fresh] if batch.spacing else [fresh])
    try:
        jobs = []
        for index, outs in enumerate(groups):
            when = at + timedelta(minutes=offsets[index] if batch.spacing else 0)
            scheduled_send.check(when, now)
            job = automation.build_job(
                db, sender=who, kind=spec.kind, title=title, outs=outs,
                scheduled_at=when.isoformat(timespec="seconds"),
                test_room=test_room, topic=spec.topic)
            for out in outs:
                for rec in _rows_for(key, test, claim, job, out):
                    db.add(rec)
            jobs.append(job)
        db.flush()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        log.warning("자동화 %s — 회차를 못 세웠습니다: %s", key, exc)
        _finish(db, run_row(db, key, test, plan.period), STATUS_FAILED,
                error=str(exc))
        return {"status": STATUS_FAILED, "error": str(exc)}

    note = ""
    if batch.skipped:
        note = f"뺀 곳 {len(batch.skipped)}: " + "; ".join(batch.skipped[:10])
    _finish(db, claim, STATUS_READY, job_id=jobs[0].id, error=note)
    log.info("자동화 %s — %s건, 회차 %s, 예약 %s%s", key, len(fresh),
             [j.id for j in jobs], at.isoformat(), " (시험 모드)" if test else "")
    return {"status": STATUS_READY, "job_ids": [j.id for j in jobs],
            "count": len(fresh), "skipped": batch.skipped, "test": test}


def run_all(db: Session, now: Optional[datetime] = None) -> Dict[str, dict]:
    """달린 자동화 전부를 한 번씩. 하나가 넘어져도 나머지는 돈다."""
    _load_all()
    out = {}
    for key in REGISTRY:
        try:
            out[key] = run_once(db, key, now)
        except Exception:  # noqa: BLE001 - 실이 죽으면 다음 날이 조용히 멎는다
            db.rollback()
            log.exception("자동화 %s 를 살피다 실패했습니다", key)
            out[key] = {"status": "error"}
    return out


# ── 풀기 직전 ────────────────────────────────────────────────────────────────

def prune(db: Session, job: SendJob) -> int:
    """예약이 풀리기 직전 — **더는 보낼 까닭이 없는 건을 뺀다.** 남은 대기 수.

    자동화 회차가 아니면 아무것도 안 한다. 뺀 건은 `canceled` 로, 사유는
    `error` 칸에 — 진행 화면의 표가 그대로 적는다.
    """
    _load_all()
    rows = db.execute(
        select(AutomationSend).where(AutomationSend.job_id == job.id)
    ).scalars().all()
    if not rows:
        return sum(1 for i in job.items if i.status == "pending")
    by_item: Dict[int, List[AutomationSend]] = {}
    for rec in rows:
        if rec.item_id:
            by_item.setdefault(rec.item_id, []).append(rec)
    for item in job.items:
        if item.status != "pending":
            continue
        for rec in by_item.get(item.id, []):
            spec = REGISTRY.get(rec.automation)
            if spec is None or spec.still_ok is None:
                continue
            why = spec.still_ok(db, rec)
            if why:
                item.status = "canceled"
                item.error = f"자동 제외 — {why}"
                log.info("자동화 %s — 건 %s 를 뺍니다: %s", rec.automation,
                         item.id, why)
                break
    db.commit()
    return sum(1 for i in job.items if i.status == "pending")


# ── 화면 ────────────────────────────────────────────────────────────────────

def next_plan(db: Session, row: Optional[Automation], now: datetime,
              days: int = 62) -> Optional[Plan]:
    """다음에 설 회차(오늘 것이 아직 안 지났으면 오늘 것)."""
    _load_all()
    spec = REGISTRY.get(row.key) if row is not None else None
    if spec is None:
        return None
    now = scheduled_send._aware(now)
    for offset in range(days):
        day = now.date() + timedelta(days=offset)
        plan = spec.plan(db, row, day)
        if plan is not None and scheduled_send._aware(plan.at) > now:
            return plan
    return None


def status_of(db: Session, key: str, now: Optional[datetime] = None) -> dict:
    """팀 현황 판 한 줄에 덧붙일 것 — 다음 회차 · 오늘 회차."""
    _load_all()
    now = scheduled_send._aware(now or clock.now())
    row = automation.load(db, key)
    out = {"ready": key in REGISTRY, "next_label": "", "today": None,
           "fields": []}
    spec = REGISTRY.get(key)
    if spec is not None:
        current = values(row, key)
        out["fields"] = [
            {"name": f.name, "label": f.label, "kind": f.kind, "hint": f.hint,
             "low": f.low, "high": f.high,
             "value": ("\n".join(current[f.name]) if f.kind == "lines"
                       else current[f.name])}
            for f in spec.fields]
    if spec is not None and spec.describe is not None:
        try:
            out["describe"] = spec.describe(db, row)
        except Exception:  # noqa: BLE001 - 덧붙이는 한 줄 때문에 판이 죽으면 안 된다
            log.exception("자동화 %s 의 설명 줄을 못 만들었습니다", key)
    if row is None or key not in REGISTRY:
        return out
    plan = next_plan(db, row, now)
    if plan is not None:
        out["next_label"] = scheduled_send.label(plan.at)
    test = automation.is_test(row)
    today = db.execute(
        select(AutoSendRun).where(AutoSendRun.kind == run_kind(key, test),
                                  AutoSendRun.day == now.date().isoformat())
        .order_by(AutoSendRun.id.desc())
    ).scalars().first()
    if today is not None:
        out["today"] = {"status": today.status, "job_id": today.job_id,
                        "error": today.error or ""}
    return out


def today_items(db: Session, user: User, now: Optional[datetime] = None) -> List[dict]:
    """오늘 할 일에 세울 자동화 줄.

    - **못 세운 회차**(0건 · 실패) — 보내는 계정과 관리자에게.
    - **선 회차** — 관리자에게만(보내는 계정에게는 `scheduled_send.standing_for`
      가 같은 회차를 이미 예약으로 세운다. 두 줄이면 같은 일을 두 번 하라는
      것으로 읽힌다).
    - 자동화가 따로 세우는 줄(`Spec.notes`) — 예: 내일 미팅 요청 나갈 곳.
    """
    _load_all()
    now = scheduled_send._aware(now or clock.now())
    admin = user.role == "admin"
    out: List[dict] = []
    for key, spec in REGISTRY.items():
        row = automation.load(db, key)
        if not automation.is_on(row):
            continue
        label = automation.BY_KEY[key].label
        test = automation.is_test(row)
        sender_id = automation.sender_id(db, row)
        mode = " (시험 모드)" if test else ""
        if admin or user.id == sender_id:
            runs = db.execute(
                select(AutoSendRun).where(AutoSendRun.kind == run_kind(key, test),
                                          AutoSendRun.day == now.date().isoformat())
            ).scalars().all()
            for run in runs:
                if run.status in (STATUS_EMPTY, STATUS_FAILED):
                    out.append({"level": "soon" if run.status == STATUS_EMPTY else "urgent",
                                "title": f"자동화 · {label}{mode} — 오늘은 안 나갑니다",
                                "detail": run.error or "", "href": "/team#automations",
                                "count": None})
                elif (run.status == STATUS_READY and admin and run.job_id
                      and user.id != run.user_id):
                    job = db.get(SendJob, run.job_id)
                    if job is not None and job.status == "draft":
                        out.append({"level": "info",
                                    "title": f"자동화 · {label}{mode}",
                                    "detail": scheduled_send.sentence(job, now),
                                    "href": f"/jobs/{job.id}",
                                    "count": scheduled_send.pending_count(job)})
        if spec.notes is not None:
            try:
                out.extend(spec.notes(db, user, row, now))
            except Exception:  # noqa: BLE001 - 오늘 할 일 한 줄 때문에 화면이 죽으면 안 된다
                log.exception("자동화 %s 의 오늘 할 일 줄을 못 만들었습니다", key)
    return out


# ── 실 ──────────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """웹 프로세스 안에서 5분마다 깨어나 본다 — 예약 발송·월간 자동과 같은 얼개.

    켠 자동화가 없으면 깨어나도 곧바로 돌아온다(`run_once` 의 `off`). 실을 안
    띄우는 길을 두지 않는다 — 켠 뒤 다시 배포해야 돈다면 켜 두고 잊는 날이 온다.
    """
    global _SCHEDULER
    if _SCHEDULER is not None and _SCHEDULER.is_alive():
        return
    # 자동화 모듈을 **지금** 읽어 둔다. 읽힐 때 다른 실에 고리를 다는 모듈이
    # 있다(소싱 리마인드 → 메일 확인의 `리마인드 전 회차`). 첫 회차(5분 뒤)까지
    # 미루면 그사이 화면 · 메일 확인이 고리 없는 판을 본다.
    _load_all()

    def loop() -> None:
        while True:
            _time.sleep(CHECK_INTERVAL_SEC)
            db = SessionLocal()
            try:
                run_all(db)
            except Exception:  # noqa: BLE001
                log.exception("자동화를 살피다 실패했습니다")
            finally:
                db.close()

    _SCHEDULER = threading.Thread(target=loop, daemon=True, name="automations")
    _SCHEDULER.start()
