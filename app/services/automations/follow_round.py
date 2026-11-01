"""#94 · #98 **후속라운드 시작 알림** — 팀원에게 카톡으로 세 번.

IR 기업 현황 › Series A 이상 딜 소싱 `후속라운드 시작`(`SeriesACompany.follow_round_month`
— 0127, `YYYY-MM`)을 읽는다. 담당은 `담당자` 칸의 지금 담당자(`contract_day7.member_of` 와
같은 규칙)다. 매출예상리스트 `후속라운드 시작 년월`(0128)도 여기서 읽었는데, D-10·7·4·1 의
미리 알림(`remind_ahead`)으로 옮겼다(사용자 결정 2026-11-01 — Series A 쪽은 그대로).

## 언제 — 세 번

`2027-05` 면 **한 달 전 1일(4/1) · 전달 15일(4/15) · 당월 1일(5/1)**, 판의 시각(기본 10:00).
그날이 주말이면 다음 평일이다. 판을 늦게 켜도 밀린 것이 한꺼번에 나가지 않게, 나갈 날에서
사흘 안쪽만 줍는다(`LOOKBACK_DAYS` — 계약 Day7 과 같은 까닭). 값이 바뀌면(달이 다르면)
새 알림이다 — 열쇠에 달이 든다.

## 누구에게 — 판의 '받는 팀원'

한 줄에 하나. `담당 팀원`(그 줄 담당) · `자동 발송 계정`(보내는 계정 주인) · 팀원 이름
(살아 있는 계정과 **정확히** 같은 이름). 기본은 앞의 둘이다. 못 정한 줄은 보내지 않고
까닭을 남긴다(판의 상태 칸 · 그날 회차의 뺀 곳).

## 어떻게 — 카톡

그 팀원의 카톡방(`User.kakao_room_name`, 팀 현황 › 자동화의 팀원 카톡방)으로 자동 발송
계정 PC 에서. 방 이름이 비면 건너뛰고 까닭을 남긴다. 문자도 같이 나갔는데 문자 발송을
앱에서 걷으며 뺐다(사용자 결정 2026-11-01).

## 한 번만

틀의 `automation_sends` `(자동화, ref, 시험)` 이 지킨다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import clock
from ...models import Automation, AutomationSend, SeriesACompany, User
from .. import automation, cadence, forecast
from .. import automation_runner as runner
from .contract_day7 import member_of

KEY = automation.FOLLOW_ROUND
#: 실제 모드 회차의 `SendJob.topic`.
TOPIC = "follow_round"
LOOKBACK_DAYS = 3
#: 읽는 곳 — 열쇠 머리. 매출예상리스트(`fc`)는 `remind_ahead` 로 옮겼다.
SERIES_A = "sa"
#: '받는 팀원' 칸의 두 낱말.
OWNER, SENDER = "담당 팀원", "자동 발송 계정"
#: 원문(#94) "000기업 5월 라운드시작입니다" 에 회차를 붙인다.
TEXT = "{기업명} {월}월 라운드 시작입니다 ({회차}/3)"

FIELDS = (
    runner.Field("time", "보낼 시각", "time", "10:00",
                 hint="한 달 전 1일 · 전달 15일 · 당월 1일 이 시각에 카톡이 섭니다 "
                      "— 주말이면 다음 평일"),
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
    """후속라운드 시작이 적힌 줄 — Series A 이상 딜 소싱."""
    out = []
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
    """카톡 — 받는 팀원의 카톡방으로(시험 모드면 틀이 시험방으로 바꾼다)."""
    batch = runner.Batch(note="오늘 후속라운드 시작을 알릴 곳이 없습니다")
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
                                     f"건너뜁니다(팀 현황 › 자동화)")
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 줄이 지워졌거나 후속라운드 시작이 바뀌었으면 뺀다."""
    try:
        _channel, src, row_id, month = rec.ref.split(":")[:4]
        row = db.get(SeriesACompany, int(row_id))
    except ValueError:
        return ""
    if src != SERIES_A:          # 옮기기 전에 선 매출예상리스트 회차
        return "매출예상리스트 후속라운드는 미리 알림 자동화로 옮겼습니다"
    if row is None:
        return "줄이 지워졌습니다"
    return "" if row.follow_round_month == month else "후속라운드 시작이 바뀌었습니다"


def describe(db: Session, row: Optional[Automation]) -> str:
    """판 상태 칸의 한 줄 — 알림 기다리는 곳과 **건너뛰는 까닭**."""
    today = clock.today()
    waiting = [t for t in targets(db)
               if alert_days(t.month)[-1] + timedelta(days=LOOKBACK_DAYS) >= today]
    problems: List[str] = []
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


runner.register(runner.Spec(
    key=KEY, kind="deal_intro", topic=TOPIC, plan=plan, collect=collect,
    still_ok=still_ok, describe=describe, fields=FIELDS))
