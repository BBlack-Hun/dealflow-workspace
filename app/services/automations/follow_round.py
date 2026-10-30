"""#94 · #98 **후속라운드 시작 알림** — 팀원에게 카톡 · 문자로 세 번.

두 곳의 `후속라운드 시작`(`YYYY-MM`)을 읽는다.

  · 업무 보고 › 매출예상리스트 `후속라운드 시작 년월`(`RevenueForecast.follow_round_month`
    — 0128). 그 줄의 담당은 줄을 만든 팀원(`user_id`)이다.
  · IR 기업 현황 › Series A 이상 딜 소싱 `후속라운드 시작`(`SeriesACompany.follow_round_month`
    — 0127). 담당은 `담당자` 칸의 지금 담당자(`contract_day7.member_of` 와 같은 규칙)다.

## 언제 — 세 번

`2027-05` 면 **한 달 전 1일(4/1) · 전달 15일(4/15) · 당월 1일(5/1)**, 판의 시각(기본 10:00).
그날이 주말이면 다음 평일이다. 판을 늦게 켜도 밀린 것이 한꺼번에 나가지 않게, 나갈 날에서
사흘 안쪽만 줍는다(`LOOKBACK_DAYS` — 계약 Day7 과 같은 까닭). 값이 바뀌면(달이 다르면)
새 알림이다 — 열쇠에 달이 든다.

## 누구에게 — 판의 '받는 팀원'

한 줄에 하나. `담당 팀원`(그 줄 담당) · `자동 발송 계정`(보내는 계정 주인) · 팀원 이름
(살아 있는 계정과 **정확히** 같은 이름). 기본은 앞의 둘이다. 못 정한 줄은 보내지 않고
까닭을 남긴다(판의 상태 칸 · 그날 회차의 뺀 곳).

## 어떻게 — 카톡과 문자

  · **카톡** — 그 팀원의 카톡방(`User.kakao_room_name`, 팀 현황 › 자동화의 팀원 카톡방)으로
    자동 발송 계정 PC 에서. 방 이름이 비면 카톡만 건너뛴다.
  · **문자** — 서버가 바로 보낸다(`send_sms` — `runner.run_all` 이 실이 깰 때마다 부른다).
    문자 설정(솔라피)이 없거나 번호가 없으면 문자만 건너뛴다. 받는 사람은 팀원뿐이다
    (`followup_sms.assert_team_phone`). 시험 모드에서는 문자도 **시험방 카톡**으로 간다.

## 한 번만

카톡은 틀의 `automation_sends` `(자동화, ref, 시험)` 이 지킨다. 실제 모드 문자는
`sms_notices` 에 **(알림 · 받는 사람)마다** 한 줄을 보내기 전에 넣고, 있으면 날이 달라도
다시 안 보낸다 — 성공이든 실패든(계약 Day7 과 같은 까닭).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ... import clock
from ...models import (Automation, AutomationSend, IrCompany, RevenueForecast,
                       SeriesACompany, SmsNotice, User)
from .. import (automation, cadence, followup_sms, forecast, scheduled_send, send_window,
                sms)
from .. import automation_runner as runner
from .contract_day7 import member_of

log = logging.getLogger(__name__)

KEY = automation.FOLLOW_ROUND
#: 실제 모드 회차의 `SendJob.topic` · `sms_notices.kind` 머리.
TOPIC = "follow_round"
LOOKBACK_DAYS = 3
#: 읽는 곳 — 열쇠 머리.
FORECAST, SERIES_A = "fc", "sa"
#: '받는 팀원' 칸의 두 낱말.
OWNER, SENDER = "담당 팀원", "자동 발송 계정"
#: 원문(#94) "000기업 5월 라운드시작입니다" 에 회차를 붙인다.
TEXT = "{기업명} {월}월 라운드 시작입니다 ({회차}/3)"

FIELDS = (
    runner.Field("time", "보낼 시각", "time", "10:00",
                 hint="한 달 전 1일 · 전달 15일 · 당월 1일 이 시각에 카톡이 서고 문자도 이 시각 뒤에 "
                      "서버가 보냅니다 — 주말이면 다음 평일"),
    runner.Field("recipients", "받는 팀원(한 줄에 하나)", "lines", [OWNER, SENDER],
                 hint=f"'{OWNER}'(그 줄 담당) · '{SENDER}'(보내는 계정 주인) · 팀원 이름"),
)


# ── 무엇을 ──────────────────────────────────────────────────────────────────

@dataclass
class Target:
    src: str
    row_id: int
    company: str
    month: str
    owner: Optional[User]
    owner_why: str


def alert_days(month: str) -> List[date]:
    """`YYYY-MM` → 1/3 한 달 전 1일 · 2/3 전달 15일 · 3/3 당월 1일 — 주말이면 다음 평일."""
    first = date(int(month[:4]), int(month[5:7]), 1)
    prev = (first - timedelta(days=1)).replace(day=1)
    return [cadence.next_business_day(d) for d in (prev, prev.replace(day=15), first)]


def targets(db: Session) -> List[Target]:
    """후속라운드 시작이 적힌 줄 — 매출예상리스트 · Series A 이상 딜 소싱."""
    out = []
    for row in db.execute(select(RevenueForecast).where(
            RevenueForecast.follow_round_month.isnot(None))).scalars():
        name = (row.company_name or "").strip()
        if not name and row.ir_company_id:
            company = db.get(IrCompany, row.ir_company_id)
            name = company.name if company else ""
        owner = db.get(User, row.user_id)
        ok = owner is not None and owner.is_active
        out.append(Target(FORECAST, row.id, name or "(기업명 없음)", row.follow_round_month,
                          owner if ok else None,
                          "" if ok else "매출예상리스트 줄의 담당 계정이 없거나 꺼져 있습니다"))
    for row in db.execute(select(SeriesACompany).where(
            SeriesACompany.follow_round_month.isnot(None))).scalars():
        owner, why = member_of(db, row)
        out.append(Target(SERIES_A, row.id, row.name, row.follow_round_month, owner, why))
    return [t for t in out if forecast.month(t.month or "")]


@dataclass
class Due:
    target: Target
    #: 1~3 — 한 달 전 1일 · 전달 15일 · 당월 1일.
    round: int

    @property
    def key(self) -> str:
        t = self.target
        return f"{t.src}:{t.row_id}:{t.month}:{self.round}"

    @property
    def label(self) -> str:
        return f"{self.target.company} {self.target.month} · {self.round}/3"


def due_on(db: Session, day: date) -> List[Due]:
    """그날 나갈 알림 — 줄마다 **이미 온 마지막 회차** 하나, 사흘 안쪽으로 지난 것까지."""
    out = []
    for target in targets(db):
        days = alert_days(target.month)
        came = [n for n, when in enumerate(days, start=1) if when <= day]
        if came and (day - days[came[-1] - 1]).days <= LOOKBACK_DAYS:
            out.append(Due(target, came[-1]))
    return out


def message(due: Due) -> str:
    return (TEXT.replace("{기업명}", due.target.company)
            .replace("{월}", str(int(due.target.month[5:7])))
            .replace("{회차}", str(due.round)))


# ── 누구에게 ────────────────────────────────────────────────────────────────

def recipients(db: Session, row: Optional[Automation], sender: Optional[User],
               target: Target) -> Tuple[List[User], List[str]]:
    """판의 '받는 팀원' → 계정들과 **못 정한 까닭**들."""
    users: List[User] = []
    whys: List[str] = []
    for line in runner.values(row, KEY)["recipients"]:
        if line == OWNER:
            user, why = target.owner, target.owner_why
        elif line == SENDER:
            user, why = sender, "" if sender else "자동 발송 계정이 정해지지 않았습니다"
        else:
            found = db.execute(select(User).where(User.name == line, User.is_active == 1)
                               ).scalars().all()
            user = found[0] if len(found) == 1 else None
            why = "" if user else (f"받는 팀원 '{line}' 을 계정에서 못 찾았습니다" if not found
                                   else f"받는 팀원 '{line}' 이름의 계정이 {len(found)}개입니다")
        if user is None:
            whys.append(why)
        elif all(u.id != user.id for u in users):
            users.append(user)
    return users, whys


# ── 틀에 다는 것 ─────────────────────────────────────────────────────────────

def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    """평일마다 한 번, 판의 시각."""
    if cadence.next_business_day(day) != day:
        return None
    return runner.Plan(period=runner.day_key(day),
                       at=runner.at_on(day, runner.values(row, KEY)["time"]))


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    """카톡 — 받는 팀원의 카톡방으로. 시험 모드면 문자도 시험방 카톡으로 싣는다.
    실제 모드 문자는 여기서 안 보낸다(`send_sms`)."""
    test = automation.is_test(row)
    batch = runner.Batch(note="오늘 후속라운드 시작을 알릴 곳이 없습니다")
    later = 0
    for due in due_on(db, plan_.at.date()):
        users, whys = recipients(db, row, sender, due.target)
        batch.skipped.extend(f"{due.label} — {why}" for why in whys)
        text = message(due)
        for user in users:
            room = (user.kakao_room_name or "").strip()
            if room:
                batch.outs.append(automation.Out(room=room, message=text,
                                                 ref=f"kakao:{due.key}:{user.id}"))
            else:
                batch.skipped.append(f"{due.label} — {user.name} 님의 카톡방 이름이 비어 있어 "
                                     f"카톡은 건너뜁니다(팀 현황 › 자동화)")
            if not sms.digits(user.phone):
                batch.skipped.append(f"{due.label} — {user.name} 님의 휴대폰 번호가 없어 "
                                     f"문자는 건너뜁니다")
            elif test:
                batch.outs.append(automation.Out(room=f"문자 → {user.name}", message=text,
                                                 ref=f"sms:{due.key}:{user.id}"))
            elif not texted(db, due, user.id):
                later += 1
    if later:
        batch.note += (f" — 문자 {later}건은 {plan_.at:%H:%M} 이후 서버가 보냅니다"
                       if sms.is_configured() else
                       f" — 문자 설정이 없어 문자 {later}건은 건너뜁니다")
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 줄이 지워졌거나 후속라운드 시작이 바뀌었으면 뺀다."""
    try:
        _channel, src, row_id, month = rec.ref.split(":")[:4]
        model = RevenueForecast if src == FORECAST else SeriesACompany
        row = db.get(model, int(row_id))
    except ValueError:
        return ""
    if row is None:
        return "줄이 지워졌습니다"
    return "" if row.follow_round_month == month else "후속라운드 시작이 바뀌었습니다"


def describe(db: Session, row: Optional[Automation]) -> str:
    """판 상태 칸의 한 줄 — 알림 기다리는 곳과 **건너뛰는 까닭**."""
    today = clock.today()
    waiting = [t for t in targets(db)
               if alert_days(t.month)[-1] + timedelta(days=LOOKBACK_DAYS) >= today]
    problems: List[str] = []
    if not sms.is_configured():
        problems.append("문자 설정(솔라피 키 · 발신번호)이 없어 문자는 건너뜁니다")
    sender = automation.sender(db, row)
    for target in waiting:
        users, whys = recipients(db, row, sender, target)
        problems += [f"{target.company} — {why}" for why in whys]
        problems += [f"{u.name} 님 카톡방 이름 없음 — 카톡 건너뜀" for u in users
                     if not (u.kakao_room_name or "").strip()]
    problems = list(dict.fromkeys(problems))
    text = f"후속라운드 알림 기다리는 곳 {len(waiting)}" if waiting else ""
    if problems:
        text += (" · " if text else "") + "건너뛰는 까닭: " + "; ".join(problems[:5])
    return text


# ── 실제 모드 문자 ───────────────────────────────────────────────────────────

def _sms_kind(due: Due) -> str:
    return f"{TOPIC}:{due.key}"


def texted(db: Session, due: Due, user_id: int) -> bool:
    """이 알림을 이 사람에게 문자로 보낸 줄이 있나(성공이든 실패든 — 다시 안 보낸다)."""
    return db.execute(select(SmsNotice.id).where(
        SmsNotice.kind == _sms_kind(due), SmsNotice.user_id == user_id)).first() is not None


def _claim(db: Session, due: Due, user_id: int, day: date) -> Optional[SmsNotice]:
    """이 알림 · 이 사람의 문자 자리를 **보내기 전에** 잡는다. 이미 있으면 `None`."""
    if texted(db, due, user_id):
        return None
    notice = SmsNotice(kind=_sms_kind(due), day=day.isoformat(), user_id=user_id, count=1,
                       status="sending")
    db.add(notice)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return notice


def send_sms(db: Session, now: Optional[datetime] = None) -> dict:
    """문자 — 켜져 있고 **실제 모드**이고 그날 판의 시각이 지났고 보내는 시간
    (`send_window`) 안이고 문자 설정이 있을 때만. 받는 사람은 팀원뿐이다."""
    now = scheduled_send._aware(now or clock.now())
    row = automation.load(db, KEY)
    if not automation.is_on(row) or automation.is_test(row):
        return {"status": "off"}
    plan_ = plan(db, row, now.date())
    if plan_ is None or now < scheduled_send._aware(plan_.at) or not send_window.contains(now):
        return {"status": "not_now"}
    if not sms.is_configured():
        return {"status": "no_sms"}
    settings = sms.load_settings()
    sender = automation.sender(db, row)
    result = {"status": "done", "sent": 0, "failed": 0}
    for due in due_on(db, now.date()):
        users, _whys = recipients(db, row, sender, due.target)
        for user in users:
            notice = _claim(db, due, user.id, now.date()) if sms.digits(user.phone) else None
            if notice is None:
                continue
            try:
                phone = followup_sms.assert_team_phone(db, user.phone)
                sms.send(phone, message(due), settings=settings)
            except Exception as exc:  # noqa: BLE001 - 한 통 실패가 나머지를 막지 않는다
                notice.status, notice.error = "failed", sms.redact(str(exc))[:500]
                db.commit()
                log.warning("후속라운드 문자 실패 열쇠=%s 받는이=%s: %s",
                            due.key, user.id, notice.error)
                result["failed"] += 1
                continue
            notice.status, notice.sent_at, notice.error = "sent", clock.now_iso(), None
            db.commit()
            result["sent"] += 1
    return result


runner.register(runner.Spec(
    key=KEY, kind="deal_intro", topic=TOPIC, plan=plan, collect=collect,
    still_ok=still_ok, describe=describe, fields=FIELDS, direct=send_sms))
