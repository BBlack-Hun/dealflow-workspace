"""A5 · **스타트업 월간 발송 순환** — 날짜·시각과 문구를 달마다 돌린다.

스타트업 월간 발송은 **이 자동화 하나**다(#31 — 옛 30일 자동
`services/startup_monthly` 의 실은 걷었다). 같은 대표가 매달 같은 날 같은 시각에
글자 하나 안 다른 글을 받으면 자동으로 찍어 보내는 것으로 읽힌다. 이 자동화는

  · **날짜·시각을 달마다 돌린다** — 기본 `26일 11:00 → 30일 13:00 → 28일 14:00`
    (자동화 판에서 고친다, 한 줄에 `일 시각`). 몇 번째를 쓰는지는 **달의 번호**
    로 정한다(연·월로 센 수를 목록 길이로 나눈 나머지) — 서버가 멈췄다 켜져도
    차례가 밀리지 않는다. 그 달에 없는 날이면 말일, **토·일이면 앞 평일**이다
    (`slot_for`). 글이 `{달} 말 기준` 현황이라 날짜를 월말에 둔다(사용자 결정
    2026-10-17).
  · **문구를 최대 셋 중에서 돌린다** — 1번은 지금의 `startup_sms` ·
    `startup_sms_tail`, 2·3번은 새 초안(`ir_kakao.VARIANT_KINDS`). 자료(요약 ·
    요청 투자사 목록)와 모양은 같고 인사·맺음 문장만 다르다.

글을 짓는 것은 스타트업 화면과 **같은 함수**다(`ir_kakao.for_company`).
보낼 기업도 화면의 [N곳 대기 목록 만들기] 와 같은 규칙이다
(`startup_send.sendable_ids`).

## 한 달에 한 번

그 달 스타트업 월간 회차(취소되지 않은 것 — 취소됐어도 나간 곳이 있는 것)가
이미 있으면 세우지 않는다(`startup_monthly.month_job` — 사람이 먼저 세웠거나
옛 30일 자동이 세운 것도 센다). 회차명에 `YYYY-MM` 을 적어 그 판정이 이 회차를
알아본다. 사람이 이 회차를 [중단] 해도 그 달 자리는 이미 잡혀 있어 다시 서지
않는다(`auto_send_runs` — 회차 하나는 한 번).

## 누가 보내나

스타트업 월간 발송은 **정해진 한 계정만** 보낸다(`startup_send.may_send`). 이
자동화의 보내는 계정은 **스타트업 월간 발송 메뉴의 계정 그 하나**다 — 다른
계정은 저장 자리에서 받지 않고(`automation.save`), 메뉴의 계정을 바꾸면 따라
바뀐다(`automation.follow_startup_menu`). 예약을 푸는 자리도 같은 판정으로
막는다(`scheduled_send.held_back`).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from ...models import STARTUP_SEND_KIND, Automation, IrCompany, User
from .. import automation
from .. import automation_runner as runner

DEFAULT_SLOTS = ["26 11:00", "30 13:00", "28 14:00"]

_SLOT = re.compile(r"(\d{1,2})\s+(\d{1,2}:\d{2})")


def parse_slots(lines) -> List[Tuple[int, str]]:
    """`26 11:00` 줄들 → `[(26, "11:00"), …]`. 못 읽으면 `ValueError`."""
    out = []
    for line in lines:
        found = _SLOT.fullmatch(str(line).strip())
        if not found:
            raise ValueError(f"'{line}' — '26 11:00' 처럼 일과 시각을 넣으세요")
        day = int(found.group(1))
        if not 1 <= day <= 31:
            raise ValueError(f"'{line}' — 날짜는 1~31")
        out.append((day, runner.parse_time(found.group(2))))
    if not out:
        raise ValueError("날짜·시각을 한 줄 이상 넣으세요")
    return out


def _check(values: dict) -> None:
    parse_slots(values["slots"])


FIELDS = (
    runner.Field("slots", "날짜·시각 순환(한 줄에 '일 시각')", "lines", DEFAULT_SLOTS,
                 hint="달마다 차례로 — 그 달에 없는 날이면 말일, 토·일이면 앞 평일"),
    runner.Field("variants", "문구 순환 개수", "int", 3, low=1, high=3,
                 hint="1 이면 지금 문구만, 2·3 이면 순환 초안까지 달마다 돌린다"),
)


def month_index(day: date) -> int:
    return day.year * 12 + (day.month - 1)


def _weekday_in_month(day: date) -> date:
    """토·일이면 **앞** 평일로 — 대표방이 주말에 울리지 않게(사용자 결정 2026-10-17).

    앞으로 당기는 것은 글이 `{달} 말 기준` 이라 **다음 달로 넘어가면 안 되기**
    때문이다. 앞 평일이 지난달이면(1일이 토·일) 그 달 첫 평일로 민다 — 어느 쪽이든
    그 달 안이다.
    """
    back = day
    while back.weekday() >= 5:         # 5=토 6=일
        back -= timedelta(days=1)
    if back.month == day.month:
        return back
    from .. import cadence

    return cadence.next_business_day(day)


def slot_for(values: dict, year: int, month: int) -> Tuple[date, str]:
    """그 달에 나가는 날·시각 — 순환 차례, 없는 날이면 말일, 주말이면 앞 평일."""
    slots = parse_slots(values["slots"])
    day, hhmm = slots[month_index(date(year, month, 1)) % len(slots)]
    last = calendar.monthrange(year, month)[1]
    return _weekday_in_month(date(year, month, min(day, last))), hhmm


def variant_for(values: dict, day: date) -> int:
    return month_index(day) % max(1, min(3, values["variants"])) + 1


def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    values = runner.values(row, automation.STARTUP_MONTHLY)
    try:
        when, hhmm = slot_for(values, day.year, day.month)
    except ValueError:
        return None
    if when != day:
        return None
    return runner.Plan(period=day.year * 100 + day.month,
                       at=runner.at_on(day, hhmm))


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    from .. import ir_kakao, startup_monthly, startup_send

    values = runner.values(row, automation.STARTUP_MONTHLY)
    day = plan_.at.date()
    month = f"{day.year:04d}-{day.month:02d}"
    label = startup_send.LABEL
    if not startup_send.may_send(db, sender):
        return runner.Batch(note=f"보내는 계정이 {label}을 보낼 수 있는 계정이 아닙니다 "
                                 f"— 팀 현황의 '{label} — 메뉴·보내는 계정' 판을 확인하세요")
    if not automation.is_test(row):
        existing = startup_monthly.month_job(db, month)
        if existing is not None:
            return runner.Batch(note=f"이 달 회차가 이미 있습니다(#{existing.id}) — 한 달에 한 번")
    variant = variant_for(values, day)
    batch = runner.Batch(note="보낼 수 있는 곳이 0곳입니다 — 대표 카톡방 이름·요청을 확인하세요",
                         title=f"{label} {month} 자동 · 문구 {variant}")
    for company_id in startup_send.sendable_ids(db, month):
        company = db.get(IrCompany, company_id)
        composed = ir_kakao.for_company(db, sender, company_id, month, variant=variant)
        if company is None or composed is None:
            continue
        batch.outs.append(automation.Out(
            room=(company.kakao_room_name or "").strip(), message=composed.text,
            parts=list(composed.parts), ir_company_id=company.id,
            ref=f"month:{month}:{company.id}"))
    return batch


def describe(db: Session, row: Optional[Automation]) -> str:
    """판에 덧붙이는 한 줄 — 앞으로 석 달의 날짜·시각과 문구 번호."""
    from ... import clock

    values = runner.values(row, automation.STARTUP_MONTHLY)
    today = clock.today()
    bits, cursor = [], date(today.year, today.month, 1)
    try:
        for _ in range(3):
            when, hhmm = slot_for(values, cursor.year, cursor.month)
            bits.append(f"{when.month}/{when.day} {hhmm}·문구{variant_for(values, when)}")
            cursor = _next_month(cursor)
    except ValueError:
        return ""
    return "순환: " + " → ".join(bits)


def _next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def header(db: Session, now=None) -> dict:
    """`/deals/startup-ir` 와 메뉴 판 머리 한 줄 — **다음 자동 발송은 언제**, 꺼져
    있으면 꺼짐. 화면은 판정하지 않고 이 값을 읽는다.

    다음 날짜의 달에 이미 회차가 있으면(사람이 먼저 세웠거나 옛 30일 자동이 세운
    것 — `month_job`) 그 달은 안 선다 — 그 사실(`skip`)과 **그 다음 달** 날짜를
    준다. 시험 모드는 회차가 있어도 시험방으로 선다(`collect` 와 같은 판정).
    """
    from datetime import datetime

    from ... import clock
    from .. import scheduled_send, startup_monthly, startup_send

    row = automation.load(db, automation.STARTUP_MONTHLY)
    out = {"on": automation.is_on(row), "test": automation.is_test(row),
           "next_label": "", "next_count": 0, "skip": None}
    if not out["on"]:
        return out
    cursor = scheduled_send._aware(now or clock.now())
    for _ in range(2):
        plan_ = runner.next_plan(db, row, cursor)
        if plan_ is None:
            break
        month = f"{plan_.at.year:04d}-{plan_.at.month:02d}"
        done = None if out["test"] else startup_monthly.month_job(db, month)
        if done is None:
            out["next_label"] = scheduled_send.label(plan_.at)
            out["next_count"] = len(startup_send.sendable_ids(db, month))
            break
        out["skip"] = {"month": month, "job_id": done.id}
        first = _next_month(plan_.at.date())
        cursor = datetime(first.year, first.month, 1).astimezone()
    return out


def times(values: dict) -> List[str]:
    """보낼 시각들 — 순환 줄마다의 시각(팀 시간대 안인지 저장 자리에서 본다)."""
    return [hhmm for _day, hhmm in parse_slots(values["slots"])]


runner.register(runner.Spec(
    key=automation.STARTUP_MONTHLY, kind=STARTUP_SEND_KIND, plan=plan,
    collect=collect, fields=FIELDS, check=_check, describe=describe,
    times=times))
