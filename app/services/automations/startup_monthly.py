"""A5 · **스타트업 월간 발송 순환** — 날짜·시각과 문구를 달마다 돌린다.

스타트업 월간 발송은 **이 자동화 하나**다(#31 — 옛 30일 자동
`services/startup_monthly` 의 실은 걷었다). 같은 대표가 매달 같은 날 같은 시각에
글자 하나 안 다른 글을 받으면 자동으로 찍어 보내는 것으로 읽힌다. 이 자동화는

  · **날짜·시각을 달마다 돌린다** — 기본 `3주 목 11:00 / 4주 수 11:00`, 곧
    **홀수 달 셋째 목요일 · 짝수 달 넷째 수요일 11:00**(#73, 사용자 결정
    2026-10-28 — 10/17 의 월말 순환 `26 11:00 → 30 13:00 → 28 14:00` 을 대신한다).
    자동화 판에서 고친다 — 한 줄에 `일 시각`(`26 11:00`) 또는 `N주 요일 시각`
    (`3주 목 11:00`, 1~7일이 1주차라 곧 N번째 그 요일). 몇 번째 줄을 쓰는지는
    **달의 번호**로 정한다(연·월로 센 수를 목록 길이로 나눈 나머지 — 두 줄이면
    홀수 달이 첫 줄) — 서버가 멈췄다 켜져도 차례가 밀리지 않는다. 그 달에 없는
    날이면 말일(N주가 없으면 마지막 그 요일), **토·일이면 앞 평일**이다
    (`slot_for`). 달 중간에 나가므로 글은 `{날짜} 기준`(보내는 날)이다.
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
import logging
import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from ...models import STARTUP_SEND_KIND, Automation, IrCompany, SendJob, User
from .. import automation
from .. import automation_runner as runner

log = logging.getLogger(__name__)

DEFAULT_SLOTS = ["3주 목 11:00", "4주 수 11:00"]

#: A5 가 꺼져(시험 모드여도) 있을 때 이 달 날짜를 며칠 앞부터 알리나.
REMIND_DAYS = 10

_SLOT = re.compile(r"(\d{1,2})\s+(\d{1,2}:\d{2})")
_WEEK_SLOT = re.compile(r"(\d)\s*주(?:차)?\s*(\S)(?:요일)?\s+(\d{1,2}:\d{2})")


def parse_slots(lines) -> List[Tuple[object, str]]:
    """`26 11:00` · `3주 목 11:00` 줄들 → `[(26, "11:00"), ((3, 3), "11:00"), …]`
    — 날은 일(int) 또는 (주차, 요일 0=월). 못 읽으면 `ValueError`."""
    out = []
    for line in lines:
        text = str(line).strip()
        week = _WEEK_SLOT.fullmatch(text)
        found = week or _SLOT.fullmatch(text)
        if not found:
            raise ValueError(f"'{line}' — '26 11:00'(일 시각) 또는 "
                             "'3주 목 11:00'(주차 요일 시각)처럼 넣으세요")
        if week:
            nth = int(week.group(1))
            if not 1 <= nth <= 5:
                raise ValueError(f"'{line}' — 주차는 1~5")
            out.append(((nth, runner.parse_weekday(week.group(2))),
                        runner.parse_time(week.group(3))))
            continue
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
    runner.Field("slots", "날짜·시각 순환(한 줄에 '3주 목 11:00' 또는 '26 11:00')",
                 "lines", DEFAULT_SLOTS,
                 hint="달마다 차례로 — 두 줄이면 홀수 달 첫 줄 · 짝수 달 둘째 줄. "
                      "'3주 목' 은 셋째 목요일(1~7일이 1주차, 없으면 마지막 그 요일), "
                      "'26' 은 26일(없으면 말일) · 토·일이면 앞 평일"),
    runner.Field("variants", "문구 순환 개수", "int", 3, low=1, high=3,
                 hint="1 이면 지금 문구만, 2·3 이면 순환 초안까지 달마다 돌린다"),
)


def month_index(day: date) -> int:
    return day.year * 12 + (day.month - 1)


def _weekday_in_month(day: date) -> date:
    """토·일이면 **앞** 평일로 — 대표방이 주말에 울리지 않게(사용자 결정 2026-10-17).

    앞으로 당기는 것은 그 달 회차가 **다음 달로 넘어가면 안 되기** 때문이다(한 달에
    한 번 판정이 달로 센다). 앞 평일이 지난달이면(1일이 토·일) 그 달 첫 평일로
    민다 — 어느 쪽이든 그 달 안이다.
    """
    back = day
    while back.weekday() >= 5:         # 5=토 6=일
        back -= timedelta(days=1)
    if back.month == day.month:
        return back
    from .. import cadence

    return cadence.next_business_day(day)


def slot_for(values: dict, year: int, month: int) -> Tuple[date, str]:
    """그 달에 나가는 날·시각 — 순환 차례, 없는 날이면 말일(없는 N주면 마지막 그
    요일), 주말이면 앞 평일."""
    from .. import cadence

    slots = parse_slots(values["slots"])
    day, hhmm = slots[month_index(date(year, month, 1)) % len(slots)]
    if isinstance(day, tuple):
        when = cadence.nth_weekday(year, month, day[1], day[0])
        if when.month != month:
            when -= timedelta(days=7)
        return _weekday_in_month(when), hhmm
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
    준다. 그 회차가 **A5 가 오늘 아침 세운 제 회차**(아직 안 나감)면 건너뛰는 것이
    아니다 — `booked`('오늘 HH:MM 나갑니다(예약)'). 시험 모드는 회차가 있어도
    시험방으로 선다(`collect` 와 같은 판정). 이 달 날짜가 지났는데 나간 회차가
    없으면 `missed`.
    """
    from ... import clock
    from .. import scheduled_send, startup_monthly

    row = automation.load(db, automation.STARTUP_MONTHLY)
    out = {"on": automation.is_on(row), "test": automation.is_test(row),
           "next_label": "", "next_count": 0, "skip": None, "booked": None,
           "missed": None}
    if not out["on"]:
        return out
    cursor = scheduled_send._aware(now or clock.now())
    out["missed"] = missed(db, row, cursor)
    for _ in range(2):
        plan_ = runner.next_plan(db, row, cursor)
        if plan_ is None:
            break
        month = f"{plan_.at.year:04d}-{plan_.at.month:02d}"
        done = None if out["test"] else startup_monthly.month_job(db, month)
        if done is not None and _own_booking(db, plan_, done):
            at = scheduled_send.scheduled_at(done) or plan_.at
            out["booked"] = {
                "label": (f"오늘 {at:%H:%M}" if at.date() == cursor.date()
                          else scheduled_send.label(at)),
                "job_id": done.id, "count": scheduled_send.pending_count(done)}
            break
        if done is None:
            out["next_label"] = scheduled_send.label(plan_.at)
            out["next_count"] = _sendable_count(db, month)
            break
        out["skip"] = {"month": month, "job_id": done.id}
        first = _next_month(plan_.at.date())
        cursor = datetime(first.year, first.month, 1).astimezone()
    return out


def _own_booking(db: Session, plan_: runner.Plan, job: SendJob) -> bool:
    """이 회차가 **그 회차 자리에 A5 가 세운 제 것**이고 아직 안 끝났나."""
    run = runner.run_row(db, automation.STARTUP_MONTHLY, False, plan_.period)
    return (run is not None and run.job_id == job.id
            and job.status in runner.OPEN_JOBS)


def _sendable_count(db: Session, month: str) -> int:
    from .. import startup_send

    try:
        return len(startup_send.sendable_ids(db, month))
    except Exception:  # noqa: BLE001 - 세는 데 실패해도 팀 현황 · 발송 화면은 떠야 한다
        log.exception("스타트업 월간 발송(A5) — 곳 수를 세지 못했습니다")
        return 0


def missed(db: Session, row: Optional[Automation], now: datetime) -> Optional[dict]:
    """**이 달 A5 날짜가 지났는데 나간 스타트업 회차가 없다** — 그 달이 끝나거나
    한 곳이라도 나갈 때까지 `{month, month_num, slot, error}`. 실제 모드로 켜진
    A5 만 본다(꺼짐 · 시험 모드는 `off_reminder`).

    A5 는 그날 시각이 지나면 다시 세우지 않는다(늦게 조용히 나가지 않게). 그날의
    오늘 할 일 줄(`automation_runner.today_items`)은 그날만 서서, 옛 30일 자동이
    한 달 내내 띄우던 경고가 사라졌다(PR #315 리뷰). 나가는 중이거나 예약 시각을
    기다리는 회차가 있으면 아직 아니다. 사람이 세우고 안 누른 목록 · 다 실패한
    회차는 나간 것이 아니다.
    """
    from .. import scheduled_send, startup_monthly

    if not automation.is_on(row) or automation.is_test(row):
        return None
    try:
        day, hhmm = slot_for(runner.values(row, automation.STARTUP_MONTHLY),
                             now.year, now.month)
    except ValueError:
        return None
    at = runner.at_on(day, hhmm)
    if now < at:
        return None
    month = f"{now.year:04d}-{now.month:02d}"
    waiting = (scheduled_send.STATE_WAITING, scheduled_send.STATE_DUE)
    for job in startup_monthly.month_jobs(db, month):
        if any(item.status in ("sent", "sending") for item in job.items):
            return None
        if (job.status in ("queued", "running", "paused")
                or scheduled_send.state(job, now) in waiting):
            return None
    run = runner.run_row(db, automation.STARTUP_MONTHLY, False,
                         now.year * 100 + now.month)
    error = (run.error or "") if run is not None and run.status in (
        runner.STATUS_EMPTY, runner.STATUS_FAILED) else ""
    return {"month": month, "month_num": now.month,
            "slot": scheduled_send.label(at), "error": error}


def off_reminder(db: Session, row: Optional[Automation], now: datetime) -> Optional[dict]:
    """**A5 가 꺼져(또는 시험 모드라) 이 달 발송이 안 나간다** — 메뉴가 켜져 있고,
    회차가 아직 없는 달의 A5 날짜가 `REMIND_DAYS` 일 안이거나 이미 지났을 때.

    이주(0105)가 옛 30일 자동을 내리고 A5 를 꺼진 채 세웠다 — 켜는 것은 사람인데
    아무도 그 사실을 떠올려 주지 않으면 그 달이 조용히 빠진다(PR #315 리뷰). 그 달
    회차가 이미 있으면(사람이 먼저 보냈다 등) 다음 달을 본다.
    """
    from .. import scheduled_send, startup_monthly, startup_send

    if automation.is_on(row) and not automation.is_test(row):
        return None
    if not startup_send.sender_id(db):
        return None
    values = runner.values(row, automation.STARTUP_MONTHLY)
    cursor = date(now.year, now.month, 1)
    for _ in range(2):
        if startup_monthly.month_job(db, f"{cursor.year:04d}-{cursor.month:02d}") is None:
            try:
                day, hhmm = slot_for(values, cursor.year, cursor.month)
            except ValueError:
                return None
            at = runner.at_on(day, hhmm)
            if at > now and (day - now.date()).days > REMIND_DAYS:
                return None
            return {"month_num": cursor.month, "this_month": cursor == date(now.year, now.month, 1),
                    "slot": scheduled_send.label(at), "passed": at <= now,
                    "test": automation.is_on(row)}
        cursor = _next_month(cursor)
    return None


def today_lines(db: Session, user: User, now: datetime) -> List[dict]:
    """오늘 할 일 — **이 달 스타트업 월간 발송이 안 나갔다 · 안 나간다**(관리자 ·
    메뉴의 계정에게). 그날만 서는 자동화 줄(`automation_runner.today_items`)과 달리
    그 달이 끝나거나 나갈 때까지 선다. A5 가 꺼져 있어도 서야 해서 `Spec.notes`
    (켜진 자동화만 부른다)가 아니라 오늘 할 일이 직접 부른다."""
    from .. import startup_send

    menu = startup_send.sender_id(db)
    if user.role != "admin" and user.id != menu:
        return []
    row = automation.load(db, automation.STARTUP_MONTHLY)
    out = []
    gone = missed(db, row, now)
    if gone is not None:
        out.append({
            "level": "urgent",
            "title": f"스타트업 월간 발송 — {gone['month_num']}월분이 아직 안 나갔습니다",
            "detail": (f"이 달 A5 날짜({gone['slot']})가 지났는데 나간 회차가 없습니다"
                       + (f" — {gone['error']}" if gone["error"] else "")
                       + ". A5 는 그날이 지나면 다시 세우지 않습니다 — 달이 끝나기 전에 "
                       "스타트업 월간 발송 화면에서 손으로 보내세요(같은 달 두 번은 막힙니다)"),
            "href": "/deals/startup-ir" if user.id == menu else "/team#automations",
            "count": None})
    off = off_reminder(db, row, now)
    if off is not None:
        when = "이번 달" if off["this_month"] else f"{off['month_num']}월"
        title = (f"스타트업 월간 발송(A5)이 시험 모드라 {when} 발송이 실제로는 안 나갑니다 "
                 "— 팀 현황 › 자동화에서 실제 발송으로 바꾸세요" if off["test"] else
                 f"스타트업 월간 발송(A5)이 꺼져 있어 {when} 발송이 안 나갑니다 "
                 "— 팀 현황 › 자동화에서 켜세요")
        detail = (f"이 달 날짜({off['slot']})가 지났습니다 — 이 달은 스타트업 월간 발송 "
                  "화면에서 손으로 보내세요" if off["passed"] else
                  f"A5 날짜 {off['slot']} — 켜 두면 그날 아침 회차가 서고 그 시각에 나갑니다")
        out.append({"level": "urgent" if off["passed"] else "soon", "title": title,
                    "detail": detail, "href": "/team#automations", "count": None})
    return out


def times(values: dict) -> List[str]:
    """보낼 시각들 — 순환 줄마다의 시각(팀 시간대 안인지 저장 자리에서 본다)."""
    return [hhmm for _day, hhmm in parse_slots(values["slots"])]


runner.register(runner.Spec(
    key=automation.STARTUP_MONTHLY, kind=STARTUP_SEND_KIND, plan=plan,
    collect=collect, fields=FIELDS, check=_check, describe=describe,
    times=times))
