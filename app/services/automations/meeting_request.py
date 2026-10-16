"""A2 · **미팅 요청 2회** — IR 자료를 받은 투자사에 7일 · 10일 뒤 미팅을 청한다.

IR 자료를 전달한 날(전달함 처리 또는 IR 자료 전달 발송이 나간 날)에서

  · **7일 뒤 14:00** — 미팅 요청 문구(`closing_meeting`, 발송 화면의 미팅 요청
    탭과 같은 길)
  · 답이 없으면 **10일 뒤 14:00** — 조금 다른 말로 한 번 더
    (`closing_meeting_again`, 딜 제안 문구에서 고친다)

그날이 주말이면 다음 평일이다. 보내는 계정(자동화 판의 그 계정) 카톡에서,
방 제목은 그 계정 카톡 기준(`sender_rooms.room_for`).

## 멈추는 것 — 답이 왔다는 표시

자료를 전달한 뒤에 아래 중 하나가 생기면 그 담당자에게는 더 안 묻는다.

  · **미팅이 기록됐다**(취소 아닌 미팅이 전달일 이후에 잡혔거나 적혔다)
  · **IR 요청이 새로 들어왔다**(전달 뒤에 또 자료를 달라고 했다 — 답이 온 것이다)
  · **[답 옴]** 을 눌렀다(`ContactActivity` 의 `reply` 줄 — 아래 `mark_replied`).
    카톡으로 답이 와도 앱은 모른다 — 사람이 한 번 눌러 알린다. 그래서
    **나가기 전날** 오늘 할 일에 `내일 미팅 요청 나갈 곳 N` 이 그 담당 팀원에게
    선다(`notes`). 답이 온 곳을 거기서 누르면 된다.

첫 번째는 이미 사람이 미팅 요청을 보냈으면(앱 발송 · 손으로 적은 기록 —
`pipeline.meeting_ask_state`) 안 나간다. 두 번째는 **첫 번째가 실제로 나간
경우에만** 나간다(나간 건의 상태를 본다 — 발송기가 꺼져 있어 안 나간 첫
번째 뒤에 "다시 여쭙습니다" 가 가면 거짓말이다).

## 며칠 치를 돌아본다

그날이거나 사흘 안쪽으로 지난 것만 줍는다(A7 과 같은 까닭 — 켜는 날 밀린
것이 한꺼번에 나가지 않게).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ... import clock
from ...models import (Automation, AutomationSend, ContactActivity, IrRequest,
                       Meeting, SendItem, SendJob, User, VcContact)
from .. import automation, cadence, pipeline, sender_rooms, sheet_owner
from .. import automation_runner as runner
from .. import message_composer as mc

#: 사람이 [답 옴] 을 누른 자국 — `ContactActivity.kind`.
REPLY_KIND = "reply"
REPLY_TEXT = "답 옴 — 미팅 요청 자동화를 멈춤"

LOOKBACK_DAYS = 3


def _check(values: dict) -> None:
    if values["second_days"] <= values["first_days"]:
        raise ValueError("두 번째는 첫 번째보다 뒤여야 합니다")


FIELDS = (
    runner.Field("first_days", "첫 번째(며칠 뒤)", "int", 7, low=1, high=30,
                 hint="IR 자료를 전달한 날에서 — 그날이 주말이면 다음 평일"),
    runner.Field("second_days", "두 번째(며칠 뒤)", "int", 10, low=2, high=45,
                 hint="첫 번째에 답이 없을 때 — 조금 다른 말로"),
    runner.Field("time", "첫 번째 보낼 시각", "time", "14:00"),
    runner.Field("second_time", "두 번째 보낼 시각", "time", "14:00",
                 hint="첫 번째와 다른 시각이면 두 번째는 그 시각에 따로 선다"),
    runner.Field("manual_days", "손 발송 뒤 쉬는 날(일)", "int", 7, low=0, high=60,
                 hint="이 날수 안에 사람이 미팅 요청·후기를 보낸 분께는 안 묻는다(0 이면 안 본다)"),
)


@dataclass
class Ask:
    contact: VcContact
    anchor: str          # 자료를 전달한 날(YYYY-MM-DD)
    round: int           # 1 | 2
    due: date

    @property
    def ref(self) -> str:
        return f"ask:{self.contact.id}:{self.anchor}:{self.round}"


# ── 언제부터 세나 ────────────────────────────────────────────────────────────

def anchors(db: Session, since: str) -> Dict[int, str]:
    """담당자마다 **마지막으로 IR 자료를 받은 날** — `since` 이후 것만.

    둘을 본다: IR 요청을 `전달함` 으로 닫은 날(손으로 처리한 것까지)과 IR 자료
    전달 발송이 실제로 나간 날. 팀원 전원의 것이다.
    """
    out: Dict[int, str] = {}

    def note(contact_id, when):
        day = (when or "")[:10]
        if contact_id and day >= since and day > out.get(contact_id, ""):
            out[contact_id] = day

    for contact_id, when in db.execute(
        select(IrRequest.contact_id, func.max(IrRequest.delivered_at))
        .where(IrRequest.status == "delivered", IrRequest.delivered_at.isnot(None))
        .group_by(IrRequest.contact_id)
    ).all():
        note(contact_id, when)
    for contact_id, when in db.execute(
        select(SendItem.contact_id, func.max(SendItem.sent_at))
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.kind == "ir_delivery", SendItem.status == "sent",
               SendItem.contact_id.isnot(None))
        .group_by(SendItem.contact_id)
    ).all():
        note(contact_id, when)
    return out


def _due(anchor: str, days: int) -> Optional[date]:
    try:
        return cadence.next_business_day(date.fromisoformat(anchor) + timedelta(days=days))
    except ValueError:
        return None


# ── 답이 왔나 ────────────────────────────────────────────────────────────────

def replied_since(db: Session, contact_id: int, since: str) -> str:
    """전달일 이후 **답이 왔다는 표시**가 있으면 그 까닭. 없으면 빈 글자."""
    meeting = db.execute(
        select(Meeting.id).where(Meeting.contact_id == contact_id,
                                 Meeting.status != "canceled",
                                 (Meeting.scheduled_at >= since)
                                 | (Meeting.created_at >= since)).limit(1)
    ).first()
    if meeting:
        return "미팅이 기록됐습니다"
    request = db.execute(
        select(IrRequest.id).where(IrRequest.contact_id == contact_id,
                                   IrRequest.requested_at > since).limit(1)
    ).first()
    if request:
        return "IR 요청이 새로 들어왔습니다"
    mark = db.execute(
        select(ContactActivity.id).where(ContactActivity.contact_id == contact_id,
                                         ContactActivity.kind == REPLY_KIND,
                                         ContactActivity.happened_at >= since).limit(1)
    ).first()
    if mark:
        return "답 옴 표시가 있습니다"
    return ""


def mark_replied(db: Session, contact: VcContact, when: Optional[date] = None) -> bool:
    """[답 옴] — 이 담당자에게 미팅 요청 자동화를 멈춘다. 새로 적었으면 참.

    같은 날 두 번 눌러도 한 줄이다. 커밋은 부르는 쪽이.
    """
    day = (when or clock.today()).isoformat()
    exists = db.execute(
        select(ContactActivity.id).where(ContactActivity.contact_id == contact.id,
                                         ContactActivity.kind == REPLY_KIND,
                                         ContactActivity.happened_at == day).limit(1)
    ).first()
    if exists:
        return False
    db.add(ContactActivity(contact_id=contact.id, kind=REPLY_KIND,
                           content=REPLY_TEXT, source="manual",
                           happened_at=day, month=day[:7]))
    return True


def undo_replied(db: Session, contact: VcContact) -> int:
    """잘못 누른 [답 옴] 을 거둔다 — 지우지 않고 되돌린 표시를 단다
    (`ContactActivity.undone_at`, 다른 손 기록과 같은 방식)."""
    rows = db.execute(
        select(ContactActivity).where(ContactActivity.contact_id == contact.id,
                                      ContactActivity.kind == REPLY_KIND)
    ).scalars().all()
    for row in rows:
        row.undone_at = clock.now_iso()
    return len(rows)


# ── 누구에게 ────────────────────────────────────────────────────────────────

def _sendable(db: Session, contact: Optional[VcContact]) -> str:
    if contact is None:
        return "담당자가 없습니다"
    if contact.is_hidden or not sheet_owner.investors(db, [contact]):
        return "투자사 명단에 없는 줄입니다"
    if sheet_owner.is_paused(contact):
        return "검토중단"
    if not sheet_owner.is_connected(contact):
        return "카톡방 연결 전"
    if not (contact.kakao_room_name or "").strip():
        return "방 이름 없음"
    return ""


def _first_sent(db: Session, contact_id: int, anchor: str, test: bool) -> bool:
    """첫 번째가 **실제로 나갔나**(이 모드로)."""
    rec = db.execute(
        select(AutomationSend).where(
            AutomationSend.automation == automation.MEETING_REQUEST,
            AutomationSend.ref == f"ask:{contact_id}:{anchor}:1",
            AutomationSend.test == (1 if test else 0))
    ).scalars().first()
    if rec is None or not rec.item_id:
        return False
    item = db.get(SendItem, rec.item_id)
    return bool(item and item.status == "sent")


def due_on(db: Session, row: Optional[Automation], day: date,
           test: bool) -> tuple:
    """그날 나갈 미팅 요청 `(Ask 목록, 뺀 것 목록)`."""
    values = runner.values(row, automation.MEETING_REQUEST)
    first, second = values["first_days"], values["second_days"]
    since = (day - timedelta(days=second + LOOKBACK_DAYS + 7)).isoformat()
    found = anchors(db, since)
    if not found:
        return [], []
    contacts = {c.id: c for c in db.execute(
        select(VcContact).where(VcContact.id.in_(list(found)))).scalars().all()}
    asked = pipeline.meeting_ask_state(
        db, db.execute(select(IrRequest).where(
            IrRequest.contact_id.in_(list(found)))).scalars().all(), today=day)

    out, skipped = [], []
    for contact_id, anchor in sorted(found.items()):
        contact = contacts.get(contact_id)
        r1, r2 = _due(anchor, first), _due(anchor, second)
        if r1 is None or r2 is None:
            continue
        ask = None
        if r1 <= day < r2 and (day - r1).days <= LOOKBACK_DAYS:
            ask = Ask(contact, anchor, 1, r1)
        elif r2 <= day and (day - r2).days <= LOOKBACK_DAYS:
            ask = Ask(contact, anchor, 2, r2)
        if ask is None:
            continue
        who = f"{contact.name}({contact.firm or '-'})" if contact else f"#{contact_id}"
        why = _sendable(db, contact) or replied_since(db, contact_id, anchor)
        if not why and ask.round == 1:
            state = asked.get(contact_id) or {}
            if state.get("asked") and state.get("asked_at", "") >= anchor:
                why = "미팅 요청을 이미 보냈습니다"
        if not why and ask.round == 2 and not _first_sent(db, contact_id, anchor, test):
            why = "첫 번째 미팅 요청이 나가지 않았습니다"
        if why:
            skipped.append(f"{who} — {why}")
            continue
        out.append(ask)
    return out, skipped


# ── 틀에 다는 것 ─────────────────────────────────────────────────────────────

def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    """평일마다 한 번. 회차의 시각은 두 시각 중 **이른 쪽**이다 — 두 번째가 다른
    시각이면 그 한 통들은 그 시각의 회차로 따로 선다(`automation.Out.at`)."""
    if cadence.next_business_day(day) != day:
        return None
    values = runner.values(row, automation.MEETING_REQUEST)
    first = runner.at_on(day, values["time"])
    second = runner.at_on(day, values["second_time"])
    return runner.Plan(period=runner.day_key(day), at=min(first, second))


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    from ...routers import deals as deals_view

    day = plan_.at.date()
    values = runner.values(row, automation.MEETING_REQUEST)
    times = {1: runner.at_on(day, values["time"]),
             2: runner.at_on(day, values["second_time"])}
    asks, skipped = due_on(db, row, day, automation.is_test(row))
    rooms = sender_rooms.rooms_for(db, sender.id, [a.contact for a in asks])
    batch = runner.Batch(skipped=skipped, note="미팅 요청 나갈 곳이 없습니다")
    for ask in asks:
        batch.outs.append(automation.Out(
            room=rooms.get(ask.contact.id) or ask.contact.kakao_room_name,
            message=deals_view.meeting_ask_message(db, sender, ask.contact,
                                                   again=ask.round == 2),
            contact_id=ask.contact.id, stage=mc.STAGE_MEETING, ref=ask.ref,
            at=times[ask.round]))
    return batch


def manual(db: Session, values: dict, contact_id: Optional[int],
           _sourcing_id: Optional[int], day: date) -> str:
    """사람이 `manual_days` 일 안에 미팅 요청·후기를 보냈으면 안 묻는다
    (`automation_dedup.manual_meeting` — 자동화가 보낸 첫 번째는 안 센다)."""
    from .. import automation_dedup

    days = int(values.get("manual_days") or 0)
    if days <= 0:
        return ""
    return automation_dedup.manual_meeting(db, contact_id, day - timedelta(days=days))


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 [답 옴] · 미팅 · 새 IR 요청이 생겼으면 뺀다."""
    try:
        _, contact_id, anchor, _round = rec.ref.split(":")
        contact_id = int(contact_id)
    except ValueError:
        return ""
    contact = db.get(VcContact, contact_id)
    return _sendable(db, contact) or replied_since(db, contact_id, anchor)


def notes(db: Session, user: User, row: Automation, now: datetime) -> List[dict]:
    """**나가기 전날** — 담당 팀원의 오늘 할 일에 `내일 미팅 요청 나갈 곳 N`.

    답이 온 곳을 앱은 모른다. 사람이 [답 옴] 을 누를 수 있게 하루 앞서
    알린다. 관리자는 팀 전체 수를 본다.
    """
    nxt = cadence.next_business_day(now.date() + timedelta(days=1))
    asks, _ = due_on(db, row, nxt, automation.is_test(row))
    if user.role != "admin":
        asks = [a for a in asks if a.contact.user_id == user.id]
    if not asks:
        return []
    when = "내일" if nxt == now.date() + timedelta(days=1) else f"{nxt.month}/{nxt.day}"
    mode = " (시험 모드)" if automation.is_test(row) else ""
    names = ", ".join(f"{a.contact.name}({a.contact.firm or '-'})" for a in asks[:3])
    return [{"level": "soon",
             "title": f"{when} 미팅 요청 나갈 곳 {len(asks)}{mode}",
             "detail": f"{names}{' 외' if len(asks) > 3 else ''} — 답이 온 곳은 [답 옴] 을 눌러 주세요",
             "href": "/automations/meeting-request", "count": len(asks)}]


runner.register(runner.Spec(
    key=automation.MEETING_REQUEST, kind="deal_intro", plan=plan,
    collect=collect, still_ok=still_ok, notes=notes, fields=FIELDS,
    check=_check, manual=manual))
