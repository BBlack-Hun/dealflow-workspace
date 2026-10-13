"""A5 · **스타트업 월간 발송 순환** — 날짜·시각과 문구를 달마다 돌린다.

지금까지 스타트업 월간 발송은 매월 **30일 17:00** 에 섰다
(`services/startup_monthly.py`). 같은 대표가 매달 같은 날 같은 시각에 글자
하나 안 다른 글을 받으면 자동으로 찍어 보내는 것으로 읽힌다. 이 자동화는

  · **날짜·시각을 달마다 돌린다** — 기본 `15일 11:00 → 20일 13:00 → 16일 14:00`
    (자동화 판에서 고친다, 한 줄에 `일 시각`). 몇 번째를 쓰는지는 **달의 번호**
    로 정한다(연·월로 센 수를 목록 길이로 나눈 나머지) — 서버가 멈췄다 켜져도
    차례가 밀리지 않는다.
  · **문구를 최대 셋 중에서 돌린다** — 1번은 지금의 `startup_sms` ·
    `startup_sms_tail`, 2·3번은 새 초안(`ir_kakao.VARIANT_KINDS`). 자료(요약 ·
    요청 투자사 목록)와 모양은 같고 인사·맺음 문장만 다르다.

글을 짓는 것은 스타트업 화면과 **같은 함수**다(`ir_kakao.for_company`).
보낼 기업도 화면의 [N곳 대기 목록 만들기] 와 같은 규칙이다
(`startup_send.sendable_ids`).

## 한 달에 한 번

그 달 스타트업 월간 회차(취소되지 않은 것)가 이미 있으면 세우지 않는다
(`startup_monthly.month_job` — 사람이 먼저 세웠거나 30일 자동이 세운 것).
회차명에 `YYYY-MM` 을 적어 그 판정이 이 회차를 알아본다.

## 30일 자동과의 관계

이 자동화가 **실제 모드로** 켜지면 옛 30일 자동(`startup_monthly.run_once`)은
물러난다. 시험 모드인 동안에는 옛 30일 자동이 그대로 돈다 — 시험이 운영의
월간 발송을 멈추면 안 된다.

## 누가 보내나

스타트업 월간 발송은 **정해진 한 계정만** 보낸다(`startup_send.may_send`).
보내는 계정이 그 계정이 아니면 세우지 않는다(예약을 푸는 자리도 같은 판정으로
막는다 — `scheduled_send.held_back`).
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from ...models import STARTUP_SEND_KIND, Automation, IrCompany, User
from .. import automation
from .. import automation_runner as runner

DEFAULT_SLOTS = ["15 11:00", "20 13:00", "16 14:00"]

_SLOT = re.compile(r"(\d{1,2})\s+(\d{1,2}:\d{2})")


def parse_slots(lines) -> List[Tuple[int, str]]:
    """`15 11:00` 줄들 → `[(15, "11:00"), …]`. 못 읽으면 `ValueError`."""
    out = []
    for line in lines:
        found = _SLOT.fullmatch(str(line).strip())
        if not found:
            raise ValueError(f"'{line}' — '15 11:00' 처럼 일과 시각을 넣으세요")
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
                 hint="달마다 차례로 — 그 달에 없는 날이면 말일"),
    runner.Field("variants", "문구 순환 개수", "int", 3, low=1, high=3,
                 hint="1 이면 지금 문구만, 2·3 이면 순환 초안까지 달마다 돌린다"),
)


def month_index(day: date) -> int:
    return day.year * 12 + (day.month - 1)


def slot_for(values: dict, year: int, month: int) -> Tuple[date, str]:
    slots = parse_slots(values["slots"])
    day, hhmm = slots[month_index(date(year, month, 1)) % len(slots)]
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last)), hhmm


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
                                 "— 팀 현황의 스타트업 월간 발송 판과 같은 계정으로 고르세요")
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
    from datetime import timedelta

    from ... import clock

    values = runner.values(row, automation.STARTUP_MONTHLY)
    today = clock.today()
    bits, cursor = [], date(today.year, today.month, 1)
    try:
        for _ in range(3):
            when, hhmm = slot_for(values, cursor.year, cursor.month)
            bits.append(f"{when.month}/{when.day} {hhmm}·문구{variant_for(values, when)}")
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    except ValueError:
        return ""
    return "순환: " + " → ".join(bits)


def owns_monthly(db: Session) -> bool:
    """이 자동화가 **실제 모드로** 켜져 있어 옛 30일 자동이 물러나야 하는가."""
    row = automation.load(db, automation.STARTUP_MONTHLY)
    return automation.is_on(row) and not automation.is_test(row)


runner.register(runner.Spec(
    key=automation.STARTUP_MONTHLY, kind=STARTUP_SEND_KIND, plan=plan,
    collect=collect, fields=FIELDS, check=_check, describe=describe))
