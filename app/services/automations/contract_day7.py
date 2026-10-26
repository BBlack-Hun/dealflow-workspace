"""#9 · **계약 Day7 우편 발송** — 계약을 맺은 기업의 계약서를 우편으로 보내라고 계약
담당 팀원에게 알리고, 계약서가 안 왔으면 문자로 세 번 묻는다.

IR 기업 현황의 계약여부가 **계약 완료(무료/유료)로 바뀐 날**(`IrCompany.contract_done_at`
— 아래 `before_flush` 가 적는다)에서

  · **7일 뒤 · 판의 시각(기본 10:00)** — 계약 담당 팀원의 카톡방으로 `계약서 우편 발송`
    (자동 발송 계정 카톡에서 — 다른 자동화와 같은 PC)
  · **14 · 21 · 28일 뒤** — 계약서 수신이 `O` 가 아니면 그 팀원에게 **문자**로
    `계약서 수신으로 바꿔 달라`(n/3). 서버가 바로 보낸다(`send_sms` — `runner.run_all`
    이 실이 깰 때마다 부른다). 시험 모드에서는 문자도 **시험방 카톡**으로 간다 —
    시험 모드에서는 아무것도 실제 상대에게 가지 않는다(`automation` 머리말).

그날이 주말이면 다음 평일이다. 계약서 수신이 `O` 가 되면(또는 계약 완료가 아니게
되면) 그 기업은 멈춘다 — 세울 때도, 예약이 풀리기 직전에도(`still_ok`) 다시 본다.

## 누구에게 — 계약 담당 팀원

IR 기업 현황 `담당자` 칸(`assignee_name`)의 **지금 담당자**(`pipeline.current_assignee`
— 이관 이력 `A > 7/22 B` 이면 B)를 살아 있는 계정 이름과 **정확히** 맞춘다. 못 맞추거나
(없음 · 둘 이상) 그 팀원의 카톡방(`User.kakao_room_name`)이 비어 있으면 **보내지 않고**
까닭을 남긴다(`why_not`) — 그날 회차의 뺀 곳(오늘 할 일 · 판의 ⓘ)과 판의 상태 칸
(`describe`)에 선다. 문자는 방 대신 번호(`users.phone`)가 있어야 한다.

## 기존 계약 기업은 안 건다

날짜 칸을 채워 넣지 않았다(0120). 이 칸이 생기기 전에 계약 완료였던 기업은 비어 있어
대상이 아니다. 판을 늦게 켜도 밀린 것이 한꺼번에 나가지 않게, 나갈 날에서 사흘 안쪽만
줍는다(`LOOKBACK_DAYS` — 다른 자동화와 같은 까닭). 그보다 지난 회차는 건너뛴다.

## 한 번만

카톡은 틀의 `automation_sends` `(자동화, ref, 시험)` 이 지킨다(`post:<기업>`). 실제
모드 문자는 `sms_notices` 에 기업 · 회차마다 한 줄(`kind=contract_receipt:<기업>:<n>`)을
**보내기 전에** 넣고, 같은 줄이 있으면 날이 달라도 다시 안 보낸다 — 성공이든 실패든
(`followup_sms` 와 같은 까닭: 업체가 받아 놓고 응답만 실패하면 또 간다). 같은 날 두
프로세스는 그 표의 `(kind, day, user_id)` 유일 색인이 막는다.

## 문구 — 샘플

정식 문구는 담당자가 나중에 준다. 딜 제안 문구 화면의 두 종류(`contract_post` ·
`contract_receipt_sms`)에서 고치고, 비어 있으면 아래 샘플이 나간다. `{기업명}` ·
`{계약일}` · `{회차}` 는 앱이 채운다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from ... import clock
from ...models import Automation, AutomationSend, IrCompany, SmsNotice, User
from .. import (automation, cadence, followup_sms, pipeline, scheduled_send,
                send_window, sms, template_pick)
from .. import automation_runner as runner

log = logging.getLogger(__name__)

KEY = automation.CONTRACT_DAY7
#: 계약 완료 — 무료 · 유료(`routers/companies.CONTRACT_LABELS`).
DONE = ("free", "paid")
#: 계약 완료로 바뀐 날에서 — 카톡(0번째) · 문자 1~3번째.
DAYS = (7, 14, 21, 28)
LOOKBACK_DAYS = 3
#: `sms_notices.kind` 머리 — 뒤에 `:<기업 번호>:<회차>`.
SMS_KIND = "contract_receipt"

POST_KIND = "contract_post"
SMS_TEMPLATE_KIND = "contract_receipt_sms"
#: 샘플 문구 — 문구 화면에서 고치면 그것이 나간다.
POST_TEXT = ("[계약서 우편 발송] {기업명} — {계약일} 계약. 계약서를 우편으로 보내 주세요. "
             "받으면 IR 기업현황 '계약서 수신'을 O로 바꿔 주세요.")
SMS_TEXT = ("[계약서 수신 확인 {회차}] {기업명} 계약서 받으셨으면 IR 기업현황 "
            "'계약서 수신'을 O로 바꿔 주세요.")

FIELDS = (
    runner.Field("time", "보낼 시각", "time", "10:00",
                 hint="7일 뒤 카톡이 이 시각에 서고, 14·21·28일 뒤 문자도 이 시각 뒤에 "
                      "서버가 보냅니다 — 주말이면 다음 평일"),
)


def _key(value) -> str:
    from ...routers.companies import contract_key   # 순환 import 를 피해 늦게 부른다

    return contract_key(value)


def received(company: IrCompany) -> bool:
    return (company.contract_received or "").strip().upper() == "O"


def done_on(company: IrCompany) -> Optional[date]:
    try:
        return date.fromisoformat((company.contract_done_at or "")[:10])
    except ValueError:
        return None


# ── 계약 완료로 바뀐 날 (`models._stamp_contract_done`) ─────────────────────────

def before_flush(session: Session) -> None:
    """IR 기업 계약여부가 **계약 완료로 바뀌면 오늘**을, 계약 완료가 아니게 되면 빈칸을.

    무료 ↔ 유료는 계약 완료끼리라 날을 안 바꾼다. 새 줄(옛 값이 없다)은 안 적는다 —
    시트 · 엑셀로 들어오는 옛 계약과 가를 수 없다(`models.IrCompany.contract_done_at`).
    """
    for company in session.dirty:
        if not isinstance(company, IrCompany) or company in session.deleted:
            continue
        history = get_history(company, "contract_status")
        if not history.added or not history.deleted:
            continue
        was = _key(history.deleted[0]) in DONE
        now = _key(history.added[0]) in DONE
        if now and not was:
            company.contract_done_at = clock.today().isoformat()
        elif was and not now:
            company.contract_done_at = None


# ── 누구에게 ────────────────────────────────────────────────────────────────

def member_of(db: Session, company: IrCompany) -> Tuple[Optional[User], str]:
    """계약 담당 팀원 — `담당자` 칸의 지금 담당자와 이름이 **정확히** 같은 살아 있는 계정."""
    name = pipeline.current_assignee(company.assignee_name)
    if not name:
        return None, ("IR 기업현황 담당자 칸이 비어 있습니다" if not company.assignee_name
                      else f"담당자 칸 '{company.assignee_name}' 에서 지금 담당자를 못 읽었습니다")
    found = db.execute(
        select(User).where(User.name == name, User.is_active == 1)
    ).scalars().all()
    if len(found) != 1:
        return None, (f"담당자 '{name}' 을 팀원 계정에서 못 찾았습니다" if not found
                      else f"담당자 '{name}' 이름의 계정이 {len(found)}개라 못 정했습니다")
    return found[0], ""


def why_not(db: Session, company: IrCompany, round_: int) -> Tuple[Optional[User], str]:
    """이 기업 이 회차를 **안 보내는 까닭**(빈 글자면 보낸다)과 받을 팀원."""
    member, why = member_of(db, company)
    if why:
        return None, why
    if round_ == 0 and not (member.kakao_room_name or "").strip():
        return member, f"{member.name} 님의 카톡방 이름이 비어 있습니다(팀 현황 › 자동화)"
    if round_ > 0 and not sms.digits(member.phone):
        return member, f"{member.name} 님의 휴대폰 번호가 없습니다"
    return member, ""


# ── 언제 ────────────────────────────────────────────────────────────────────

@dataclass
class Due:
    company: IrCompany
    #: 0 = 카톡(7일 뒤) · 1~3 = 문자(14 · 21 · 28일 뒤).
    round: int

    @property
    def ref(self) -> str:
        return f"post:{self.company.id}" if self.round == 0 else f"sms:{self.company.id}:{self.round}"

    @property
    def label(self) -> str:
        return f"{self.company.name} · {'카톡' if self.round == 0 else f'문자 {self.round}/3'}"


def waiting(db: Session, day: date) -> List[IrCompany]:
    """계약서를 기다리는 기업 — 계약 완료로 바뀐 날이 적혀 있고(이 기능 뒤의 계약뿐)
    마지막 문자 날을 갓 지났을 때까지, 계약서 수신이 `O` 가 아닌 곳."""
    since = (day - timedelta(days=DAYS[-1] + LOOKBACK_DAYS + 7)).isoformat()
    rows = db.execute(
        select(IrCompany).where(IrCompany.contract_done_at >= since)
        .order_by(IrCompany.contract_done_at, IrCompany.id)
    ).scalars().all()
    return [c for c in rows if _key(c.contract_status) in DONE and not received(c)]


def due_on(db: Session, day: date) -> List[Due]:
    """그날 나갈 회차 — 기업마다 **이미 온 마지막 회차** 하나, 사흘 안쪽으로 지난 것까지."""
    out = []
    for company in waiting(db, day):
        start = done_on(company)
        if start is None:
            continue
        days = [cadence.next_business_day(start + timedelta(days=n)) for n in DAYS]
        came = [n for n, when in enumerate(days) if when <= day]
        if came and (day - days[came[-1]]).days <= LOOKBACK_DAYS:
            out.append(Due(company, came[-1]))
    return out


# ── 글 ──────────────────────────────────────────────────────────────────────

def _text(db: Session, user: Optional[User], kind: str, fallback: str, values: dict) -> str:
    """문구 화면의 글(보내는 계정이 고른 것 — `template_pick`), 없으면 샘플."""
    found = template_pick.pick(db, user.id, kind) if user is not None else None
    body = ((found.body if found else "") or "").strip() or fallback
    for token, value in values.items():
        body = body.replace("{" + token + "}", value)
    return body


def message(db: Session, sender: Optional[User], due: Due) -> str:
    if due.round == 0:
        start = done_on(due.company)
        return _text(db, sender, POST_KIND, POST_TEXT,
                     {"기업명": due.company.name, "계약일": f"{start.month}/{start.day}"})
    return _text(db, sender, SMS_TEMPLATE_KIND, SMS_TEXT,
                 {"기업명": due.company.name, "회차": f"{due.round}/3"})


# ── 틀에 다는 것 ─────────────────────────────────────────────────────────────

def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    """평일마다 한 번, 판의 시각."""
    if cadence.next_business_day(day) != day:
        return None
    return runner.Plan(period=runner.day_key(day),
                       at=runner.at_on(day, runner.values(row, KEY)["time"]))


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    """카톡(7일 뒤) — 팀원 카톡방으로. 시험 모드면 문자 회차도 시험방 카톡으로 싣는다.
    실제 모드 문자는 여기서 안 보낸다(`send_sms`) — 안 보내는 까닭만 함께 남긴다."""
    test = automation.is_test(row)
    batch = runner.Batch(note="오늘 계약서 우편 발송을 알릴 곳이 없습니다")
    later = 0
    for due in due_on(db, plan_.at.date()):
        member, why = why_not(db, due.company, due.round)
        if why:
            batch.skipped.append(f"{due.label} — {why}")
        elif due.round == 0:
            batch.outs.append(automation.Out(
                room=member.kakao_room_name.strip(), message=message(db, sender, due),
                ref=due.ref))
        elif test:
            batch.outs.append(automation.Out(
                room=f"문자 → {member.name}", message=message(db, sender, due), ref=due.ref))
        elif not texted(db, due):
            later += 1
    if later:
        batch.note += f" — 문자 {later}건은 {plan_.at:%H:%M} 이후 서버가 보냅니다"
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 계약서를 받았거나 계약 완료가 아니게 됐으면 뺀다."""
    try:
        company = db.get(IrCompany, int(rec.ref.split(":")[1]))
    except (IndexError, ValueError):
        return ""
    if company is None:
        return "기업이 지워졌습니다"
    if _key(company.contract_status) not in DONE:
        return "계약 완료가 아닙니다"
    return "계약서 수신이 O 입니다" if received(company) else ""


def describe(db: Session, row: Optional[Automation]) -> str:
    """판 상태 칸의 한 줄 — 계약서를 기다리는 곳과 그중 **안 보내는 까닭**이 있는 곳."""
    today = clock.today()
    rows = waiting(db, today)
    if not rows:
        return ""
    problems = []
    for company in rows:
        # 카톡 날(+사흘)이 지난 곳은 문자 조건(번호)으로 본다 — 방이 비어도 막힌 것이 없다.
        start = done_on(company) or today
        post_until = (cadence.next_business_day(start + timedelta(days=DAYS[0]))
                      + timedelta(days=LOOKBACK_DAYS))
        _member, why = why_not(db, company, 0 if today <= post_until else 1)
        if why:
            problems.append(f"{company.name} — {why}")
    text = f"계약서 기다리는 곳 {len(rows)}"
    if problems:
        text += f" · 안 보내는 까닭 {len(problems)}: " + "; ".join(problems[:5])
    return text


# ── 실제 모드 문자 ───────────────────────────────────────────────────────────

def _sms_kind(due: Due) -> str:
    return f"{SMS_KIND}:{due.company.id}:{due.round}"


def texted(db: Session, due: Due) -> bool:
    """이 기업 이 회차의 문자 줄이 이미 있나(성공이든 실패든 — 다시 안 보낸다)."""
    return db.execute(select(SmsNotice.id).where(SmsNotice.kind == _sms_kind(due))).first() is not None


def _claim(db: Session, due: Due, user_id: int, day: date) -> Optional[SmsNotice]:
    """이 기업 이 회차의 문자 자리를 **보내기 전에** 잡는다. 이미 있으면(날이 달라도) `None`."""
    if texted(db, due):
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
    """14 · 21 · 28일 뒤 문자 — 켜져 있고 **실제 모드**이고 그날 판의 시각이 지났고
    보내는 시간(`send_window`) 안일 때만. 받는 사람은 팀원뿐이다(`assert_team_phone`)."""
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
        if due.round == 0:
            continue
        member, why = why_not(db, due.company, due.round)
        notice = None if why else _claim(db, due, member.id, now.date())
        if notice is None:
            continue
        try:
            phone = followup_sms.assert_team_phone(db, member.phone)
            sms.send(phone, message(db, sender, due), settings=settings)
        except Exception as exc:  # noqa: BLE001 - 한 통 실패가 나머지를 막지 않는다
            notice.status, notice.error = "failed", sms.redact(str(exc))[:500]
            db.commit()
            log.warning("계약서 수신 문자 실패 기업=%s 회차=%s: %s",
                        due.company.id, due.round, notice.error)
            result["failed"] += 1
            continue
        notice.status, notice.sent_at, notice.error = "sent", clock.now_iso(), None
        db.commit()
        result["sent"] += 1
    return result


runner.register(runner.Spec(
    key=KEY, kind="deal_intro", topic=POST_KIND, plan=plan, collect=collect,
    still_ok=still_ok, describe=describe, fields=FIELDS, direct=send_sms))
