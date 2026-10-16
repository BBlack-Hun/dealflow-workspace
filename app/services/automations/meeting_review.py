"""A7 · **미팅 후 검토결과 문의** — 미팅을 마친 투자사에 이틀 뒤 결과를 묻는다.

미팅을 완료로 적으면(`pipeline.complete_meeting`) **기본 2일 뒤 14:00**(그날이
주말이면 다음 평일)에
그 투자사 담당자의 방으로 미팅 후기 문구(`meeting_review`)가 나간다 — 보내는
계정(자동화 판의 그 계정) 카톡에서.

## 팀원 전원의 미팅이다  ★

결과 문의 대기 목록(`services/auto_send.py`)은 **보내는 계정 자신의** 미팅만
골랐다 — 그 길이 `create_send_list` 를 지나 내 명단만 받기 때문이다. 그래서
보내는 계정이 아닌 팀원의 미팅은 아무도 묻지 않았다. 여기서는 팀원 전원의
미팅을 본다. 보내는 계정은 모든 투자사 방에 들어가 있는 계정이고, 방 제목은
그 계정 카톡 기준으로 고른다(`sender_rooms.room_for` — 확인된 제목 → 없으면
담당 팀원의 제목).

## 안 보내는 것

- **결과가 이미 적힌 미팅** — 결말이 `투자 검토` · `보류` · `거절` 이거나,
  결과 문의를 이미 했다고 적었거나(`followup_done` · `followup_note`).
  `검토 중`(또는 빈칸)일 때만 묻는다 — 그 결과를 묻는 문구다.
- **다음 걸음이 잡힌 미팅** — 같은 담당자의 미팅이 그 뒤에 또 잡혀 있다
  (2차 미팅 · 일정 변경). 화면이 결과 문의에서 빼는 규칙(`pipeline.meeting_rows`
  의 `superseded`)과 같다.
- **취소된 미팅** — 완료(`done`)인 미팅만 본다.
- **멈춘 담당자** — 검토중단 · 감춘 줄 · 연결 전 · 방 이름 없음.
- **결과 문의 대기 목록으로 이미 선 미팅**(`auto_send` 의 자리가 있다).

아침에 세운 뒤 14시 전에 결과를 적거나 미팅이 바뀌면, 예약이 풀리는 순간
다시 보고 그 건은 뺀다(`still_ok`).

## 며칠 치를 돌아본다

물어볼 날이 오늘이거나 사흘 안쪽으로 지난 미팅을 줍는다 — 서버가 멈춰 그날
회차를 못 세웠으면 다음 날 회차가 줍는다. 그보다 오래된 것은 줍지 않는다:
켜는 날 밀린 미팅이 한꺼번에 나가면 그것이 사고다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import AutoSendRun, Automation, AutomationSend, Meeting, User, VcContact
from .. import automation, cadence, sender_rooms, sheet_owner
from .. import automation_runner as runner
from .. import message_composer as mc

#: 결과를 아직 모를 때의 결말 — 이때만 묻는다. 빈칸도 같다.
ASKABLE_OUTCOMES = {"", "reviewing"}

#: 물어볼 날이 며칠 지난 것까지 줍나.
LOOKBACK_DAYS = 3

FIELDS = (
    runner.Field("days", "며칠 뒤", "int", 2, low=1, high=14,
                 hint="미팅을 완료로 적은 날에서 며칠 뒤에 묻나 — 그날이 주말이면 다음 평일"),
    runner.Field("time", "보낼 시각", "time", "14:00"),
)


def _due(meeting: Meeting, days: int) -> Optional[date]:
    try:
        done = date.fromisoformat((meeting.done_at or "")[:10])
    except ValueError:
        return None
    return cadence.next_business_day(done + timedelta(days=days))


def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    """평일마다 한 번 — 주말에는 투자사 방이 울리지 않는다."""
    if cadence.next_business_day(day) != day:
        return None
    values = runner.values(row, automation.MEETING_REVIEW)
    return runner.Plan(period=runner.day_key(day),
                       at=runner.at_on(day, values["time"]))


def _later_meetings(db: Session, contact_ids) -> Dict[int, List[Meeting]]:
    rows = db.execute(
        select(Meeting).where(Meeting.contact_id.in_(list(contact_ids)),
                              Meeting.status != "canceled")
    ).scalars().all()
    out: Dict[int, List[Meeting]] = {}
    for row in rows:
        out.setdefault(row.contact_id, []).append(row)
    return out


def why_not(db: Session, meeting: Optional[Meeting], contact: Optional[VcContact],
            others: List[Meeting]) -> str:
    """이 미팅에 지금 물으면 안 되는 까닭. 물어도 되면 빈 글자."""
    if meeting is None:
        return "미팅이 지워졌습니다"
    if meeting.status != "done":
        return "미팅이 완료 상태가 아닙니다(취소·일정 변경)"
    if (meeting.outcome or "") not in ASKABLE_OUTCOMES:
        return "결과가 이미 적혀 있습니다"
    if meeting.followup_done or (meeting.followup_note or "").strip():
        return "결과 문의를 이미 했습니다"
    mine = meeting.scheduled_at or ""
    if any(o.id != meeting.id and (o.scheduled_at or "") > mine for o in others):
        return "그 뒤 미팅이 또 잡혀 있습니다"
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


def _queued_by_old_list(db: Session, meeting_ids) -> set:
    """결과 문의 대기 목록(`auto_send`)으로 이미 선 미팅들."""
    from .. import auto_send

    ids = list(meeting_ids)
    if not ids:
        return set()
    return set(db.execute(
        select(AutoSendRun.ref_id).where(AutoSendRun.kind == auto_send.KIND_REVIEW,
                                         AutoSendRun.ref_id.in_(ids))
    ).scalars().all())


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    from ...routers import deals as deals_view

    values = runner.values(row, automation.MEETING_REVIEW)
    day = plan_.at.date()
    oldest = day - timedelta(days=LOOKBACK_DAYS + values["days"] + 7)
    meetings = db.execute(
        select(Meeting).where(Meeting.status == "done",
                              Meeting.done_at.isnot(None),
                              Meeting.done_at >= oldest.isoformat())
        .order_by(Meeting.done_at, Meeting.id)
    ).scalars().all()
    due = []
    for meeting in meetings:
        when = _due(meeting, values["days"])
        if when is not None and day - timedelta(days=LOOKBACK_DAYS) <= when <= day:
            due.append(meeting)
    if not due:
        return runner.Batch(note="물어볼 미팅이 없습니다")

    contacts = {c.id: c for c in db.execute(
        select(VcContact).where(VcContact.id.in_({m.contact_id for m in due}))
    ).scalars().all()}
    others = _later_meetings(db, contacts)
    old = _queued_by_old_list(db, [m.id for m in due])
    rooms = sender_rooms.rooms_for(db, sender.id, contacts.values())

    batch = runner.Batch(note="물어볼 미팅이 없습니다")
    seen = set()
    for meeting in due:
        contact = contacts.get(meeting.contact_id)
        who = f"{contact.name}({contact.firm or '-'})" if contact else f"#{meeting.id}"
        why = why_not(db, meeting, contact, others.get(meeting.contact_id, []))
        if not why and meeting.id in old:
            why = "결과 문의 대기 목록으로 이미 섰습니다"
        if not why and contact.id in seen:
            # 같은 분과 같은 날 미팅이 둘 — 한 통이면 된다.
            why = "같은 담당자에게 이미 한 통이 실렸습니다"
        if why:
            batch.skipped.append(f"{who} — {why}")
            continue
        seen.add(contact.id)
        batch.outs.append(automation.Out(
            room=rooms.get(contact.id) or contact.kakao_room_name,
            # 발송 화면의 미팅 후기 탭과 **같은 함수**다 — 글자 하나까지 같다.
            message=deals_view.review_message(db, sender, contact),
            contact_id=contact.id, stage=mc.STAGE_MEETING,
            ref=f"meeting:{meeting.id}"))
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """예약이 풀리기 직전 — 그사이 결과를 적었거나 미팅이 바뀌었으면 뺀다."""
    try:
        meeting_id = int(rec.ref.split(":", 1)[1])
    except (IndexError, ValueError):
        return ""
    meeting = db.get(Meeting, meeting_id)
    contact = db.get(VcContact, meeting.contact_id) if meeting else None
    others = _later_meetings(db, [meeting.contact_id]).get(
        meeting.contact_id, []) if meeting else []
    return why_not(db, meeting, contact, others)


runner.register(runner.Spec(
    key=automation.MEETING_REVIEW, kind="deal_intro", plan=plan,
    collect=collect, still_ok=still_ok, fields=FIELDS))
