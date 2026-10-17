"""A7 · **미팅 후 검토결과 문의** — 미팅을 마친 투자사에 이틀 뒤 결과를 묻고,
한 달 뒤 투자 결정을 한 번 더 묻는다.

미팅을 완료로 적으면(`pipeline.complete_meeting`) 그 투자사 담당자의 방으로 —
보내는 계정(자동화 판의 그 계정) 카톡에서 —

  · **첫 번째 · 기본 2일 뒤 14:00** — 미팅 후기 문구(`meeting_review`, 발송
    화면의 미팅 후기 탭과 같은 글)
  · **두 번째 · 기본 30일 뒤 14:00** — 투자 결정 문의(`meeting_review_decision`,
    문구 화면에서 고친다). 같은 틀(인사말 + 본문, 단계 3)에 본문만 다르고,
    본문의 `{미팅 기업}` 에 그 미팅의 기업 이름이 들어간다
    (`routers/deals.meeting_decision_message`).

그날이 주말이면 다음 평일이다. 두 번째는 판에서 날수를 `0` 으로 두면 안 묻고,
시각이 첫 번째와 다르면 그 시각의 회차로 따로 선다(A2 미팅 요청의 두 번째와
같은 얼개 — `automation.Out.at`).

## 팀원 전원의 미팅이다  ★

결과 문의 대기 목록(`services/auto_send.py`)은 **보내는 계정 자신의** 미팅만
골랐다 — 그 길이 `create_send_list` 를 지나 내 명단만 받기 때문이다. 그래서
보내는 계정이 아닌 팀원의 미팅은 아무도 묻지 않았다. 여기서는 팀원 전원의
미팅을 본다. 보내는 계정은 모든 투자사 방에 들어가 있는 계정이고, 방 제목은
그 계정 카톡 기준으로 고른다(`sender_rooms.room_for` — 확인된 제목 → 없으면
담당 팀원의 제목).

## 안 보내는 것 — 첫 번째(`why_not`)

- **결과가 이미 적힌 미팅** — 결말이 `투자 검토` · `보류` · `거절` 이거나,
  결과 문의를 이미 했다고 적었거나(`followup_done` · `followup_note`).
  `검토 중`(또는 빈칸)일 때만 묻는다 — 그 결과를 묻는 문구다.
- **다음 걸음이 잡힌 미팅** — 같은 담당자의 미팅이 그 뒤에 또 잡혀 있다
  (2차 미팅 · 일정 변경). 화면이 결과 문의에서 빼는 규칙(`pipeline.meeting_rows`
  의 `superseded`)과 같다.
- **취소된 미팅** — 완료(`done`)인 미팅만 본다.
- **멈춘 담당자** — 검토중단 · 감춘 줄 · 연결 전 · 방 이름 없음.
- **결과 문의 대기 목록으로 이미 선 미팅**(`auto_send` 의 자리가 있다).
- **손 발송** — 미팅을 마친 뒤 `manual_days`(기본 7일) 안에 사람이 미팅
  요청·후기를 보냈다(`manual`).

## 안 보내는 것 — 두 번째(`why_not_decision`)

두 번째는 결과가 **적혀 있어도** 묻는다 — `검토 중` · `투자 검토` · `보류` ·
빈칸 모두. 묻는 것이 한 달 뒤의 투자 결정이라, 이틀 뒤에 들은 결말은 그사이
바뀌었을 수 있다. 빼는 것은:

- **거절로 끝난 미팅** — 거절한 곳에 결정을 다시 묻는 것은 실례다. 결과 문의
  날을 안 잡는 결말과 같은 묶음이다(`pipeline.NO_FOLLOWUP_OUTCOMES`).
- **같은 기업 건으로 다음 걸음이 잡힌 미팅** — 같은 담당자와 **같은 기업** 건
  미팅이 그 뒤에 또 있다(`_same_company`). 다른 기업 건 미팅은 이 기업의 결정을
  묻는 데 걸리지 않는다 — 사용자가 정했다(2026-10-17). 첫 번째는 그대로 담당자
  단위다(화면의 결과 문의 목록과 같은 규칙).
- **미팅을 마친 뒤 사람이 미팅 단계 글을 보냈다** — 미팅을 마친 날부터 지금까지
  **전부**를 본다(`manual_days` 와 상관없이). 이미 사람이 묻고 답을 듣고 있는
  곳에 한 달 뒤 자동 문의가 끼어들면 안 된다. 자동화가 보낸 첫 번째는 세지
  않는다(`automation_dedup.manual_meeting` 이 자동 발송 건을 뺀다). 뒤 미팅과
  달리 **기업으로 좁히지 않는다** — 손으로 보낸 미팅 요청 · 후기에는 기업이
  실리지 않아(`routers/deals.MODES_WITH_COMPANIES` · `pipeline.record_meeting_ask`)
  어느 기업 건인지 모른다. 모르는 글은 센다(덜 보내는 쪽 — PR #311 리뷰).
- 취소된 미팅 · 멈춘 담당자 — 첫 번째와 같다.

결과 문의를 했다는 표시(`followup_done` · `followup_note`)는 **보지 않는다** —
그것은 첫 번째 단계(이틀~열흘 뒤)의 문의를 적은 것이고, 두 번째는 그 뒤의 일이다.

아침에 세운 뒤 보낼 시각 전에 결과를 적거나 미팅이 바뀌면, 예약이 풀리는 순간
다시 보고 그 건은 뺀다(`still_ok` — 회차마다 제 규칙으로). 그사이 판에서 두
번째를 껐으면(날수 0) 서 있던 두 번째도 그때 빠진다.

## 같은 날 둘이 겹치면

같은 분께 첫 번째와 두 번째가 같은 날 서면 **한 통만** 나간다 — 같은 분 하루
N통(`automation_dedup` 장부, 기본 1)이 막고, 첫 번째가 먼저 실린다. 같은 분의
미팅 둘이 같은 날 같은 회차로 서면(첫 번째끼리 · 두 번째끼리) 여기서 한 통으로
줄인다.

## 열쇠(`automation_sends.ref`)

첫 번째는 `meeting:<미팅 번호>` — 운영에 이미 이 모양으로 쌓여 있어 바꾸지
않는다. 두 번째는 `meeting30:<미팅 번호>`(30 은 기본값에서 온 이름이다 — 날수를
바꿔도 열쇠는 같아, 한 미팅에 두 번째는 한 번뿐이다). 풀기 직전 판정(`still_ok`)
과 손 발송 판정(`manual`)이 열쇠 머리로 회차를 가른다(`_parse_ref`).

## 며칠 치를 돌아본다

물어볼 날이 오늘이거나 사흘 안쪽으로 지난 미팅을 줍는다 — 서버가 멈춰 그날
회차를 못 세웠으면 다음 날 회차가 줍는다. 그보다 오래된 것은 줍지 않는다:
켜는 날 밀린 미팅이 한꺼번에 나가면 그것이 사고다. 두 번째도 같다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import AutoSendRun, Automation, AutomationSend, Meeting, User, VcContact
from .. import automation, cadence, pipeline, sender_rooms, sheet_owner
from .. import automation_runner as runner
from .. import message_composer as mc

#: 결과를 아직 모를 때의 결말 — 첫 번째는 이때만 묻는다. 빈칸도 같다.
ASKABLE_OUTCOMES = {"", "reviewing"}

#: 물어볼 날이 며칠 지난 것까지 줍나.
LOOKBACK_DAYS = 3

#: 회차마다의 열쇠 머리. 첫 번째는 운영에 쌓인 모양 그대로다.
REVIEW_REF = "meeting"
DECISION_REF = "meeting30"
#: 두 번째 회차의 이름 — 뺀 곳 사유 줄에 붙여 어느 회차였는지 보인다.
DECISION_LABEL = "투자 결정 문의"


def _check(values: dict) -> None:
    if values["decision_days"] and values["decision_days"] <= values["days"]:
        raise ValueError("두 번째(투자 결정 문의)는 첫 번째보다 뒤여야 합니다 "
                         "— 안 물으려면 0 을 넣으세요")


FIELDS = (
    runner.Field("days", "첫 번째(며칠 뒤)", "int", 2, low=1, high=14,
                 hint="미팅을 완료로 적은 날에서 며칠 뒤에 결과를 묻나 — 그날이 주말이면 다음 평일"),
    runner.Field("time", "첫 번째 보낼 시각", "time", "14:00"),
    # 30 은 판에 처음 세울 때 · 새로 저장할 때의 값이다. 두 번째가 생기기 전에 저장된
    # A7 줄(이 칸이 없다)은 **0 — 안 묻는다**(`absent`) — 배포하는 날 켜 둔 A7 에 두
    # 번째가 저절로 붙지 않게(PR #311 리뷰). 판에는 0 으로 서고, 사람이 날수를 넣어야 켜진다.
    runner.Field("decision_days", "두 번째 — 투자 결정 문의(며칠 뒤)", "int", 30,
                 low=0, high=90, absent=0,
                 hint="미팅을 완료로 적은 날에서 — 그날이 주말이면 다음 평일. "
                      "0 이면 두 번째는 안 묻는다(거절로 끝난 미팅에는 안 묻는다)"),
    runner.Field("decision_time", "두 번째 보낼 시각", "time", "14:00",
                 hint="첫 번째와 다른 시각이면 두 번째는 그 시각에 따로 선다"),
    runner.Field("manual_days", "손 발송 뒤 쉬는 날(일)", "int", 7, low=0, high=60,
                 hint="이 날수 안에 사람이 미팅 요청·후기를 보낸 분께는 첫 번째를 안 묻는다"
                      "(0 이면 안 본다) — 두 번째는 미팅을 마친 뒤 보낸 것을 전부 본다"),
)


def _due(meeting: Meeting, days: int) -> Optional[date]:
    try:
        done = date.fromisoformat((meeting.done_at or "")[:10])
    except ValueError:
        return None
    return cadence.next_business_day(done + timedelta(days=days))


def _rounds(values: dict, day: date) -> List[Tuple[str, int, object]]:
    """그날 볼 회차들 `(열쇠 머리, 며칠 뒤, 나갈 시각)` — 첫 번째가 앞이다
    (같은 분께 둘이 겹치면 장부가 앞의 것을 싣는다)."""
    out = [(REVIEW_REF, values["days"], runner.at_on(day, values["time"]))]
    if values["decision_days"]:
        out.append((DECISION_REF, values["decision_days"],
                    runner.at_on(day, values["decision_time"])))
    return out


def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    """평일마다 한 번 — 주말에는 투자사 방이 울리지 않는다. 회차의 시각은
    첫 번째 · 두 번째 중 **이른 쪽**이다(두 번째를 안 물으면 첫 번째 시각)."""
    if cadence.next_business_day(day) != day:
        return None
    values = runner.values(row, automation.MEETING_REVIEW)
    return runner.Plan(period=runner.day_key(day),
                       at=min(at for _head, _days, at in _rounds(values, day)))


def _due_meetings(db: Session, day: date, days: int) -> List[Meeting]:
    """물어볼 날(완료일 + `days`, 주말이면 다음 평일)이 오늘이거나 사흘 안쪽으로
    지난 완료 미팅들."""
    oldest = day - timedelta(days=LOOKBACK_DAYS + days + 7)
    meetings = db.execute(
        select(Meeting).where(Meeting.status == "done",
                              Meeting.done_at.isnot(None),
                              Meeting.done_at >= oldest.isoformat())
        .order_by(Meeting.done_at, Meeting.id)
    ).scalars().all()
    out = []
    for meeting in meetings:
        when = _due(meeting, days)
        if when is not None and day - timedelta(days=LOOKBACK_DAYS) <= when <= day:
            out.append(meeting)
    return out


def _later_meetings(db: Session, contact_ids) -> Dict[int, List[Meeting]]:
    rows = db.execute(
        select(Meeting).where(Meeting.contact_id.in_(list(contact_ids)),
                              Meeting.status != "canceled")
    ).scalars().all()
    out: Dict[int, List[Meeting]] = {}
    for row in rows:
        out.setdefault(row.contact_id, []).append(row)
    return out


def _superseded(meeting: Meeting, others: List[Meeting]) -> bool:
    """같은 담당자의 (취소 아닌) 미팅이 이 미팅 **뒤에** 또 잡혀 있나."""
    mine = meeting.scheduled_at or ""
    return any(o.id != meeting.id and (o.scheduled_at or "") > mine for o in others)


def _same_company(a: Meeting, b: Meeting) -> bool:
    """두 미팅이 같은 기업 건인가 — 둘 다 기업 번호가 있으면 번호로, 아니면 이름
    (`pipeline._key` — 띄어쓰기 · 대소문자 무시)으로. 한쪽이라도 기업을 모르면 같은
    건으로 본다 — 모르는 채 결정을 묻는 쪽이 사고다."""
    if a.company_id and b.company_id:
        return a.company_id == b.company_id
    mine, theirs = pipeline._key(a.company_name), pipeline._key(b.company_name)
    return not mine or not theirs or mine == theirs


def _contact_problem(db: Session, contact: Optional[VcContact]) -> str:
    """이 담당자에게 지금 보내면 안 되는 까닭 — 두 회차가 같은 규칙이다."""
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


def why_not(db: Session, meeting: Optional[Meeting], contact: Optional[VcContact],
            others: List[Meeting]) -> str:
    """첫 번째 — 이 미팅에 지금 물으면 안 되는 까닭. 물어도 되면 빈 글자."""
    if meeting is None:
        return "미팅이 지워졌습니다"
    if meeting.status != "done":
        return "미팅이 완료 상태가 아닙니다(취소·일정 변경)"
    if (meeting.outcome or "") not in ASKABLE_OUTCOMES:
        return "결과가 이미 적혀 있습니다"
    if meeting.followup_done or (meeting.followup_note or "").strip():
        return "결과 문의를 이미 했습니다"
    if _superseded(meeting, others):
        return "그 뒤 미팅이 또 잡혀 있습니다"
    return _contact_problem(db, contact)


def why_not_decision(db: Session, meeting: Optional[Meeting],
                     contact: Optional[VcContact], others: List[Meeting]) -> str:
    """두 번째(투자 결정 문의) — 이 미팅에 지금 물으면 안 되는 까닭.

    결과 문의를 했다는 표시(`followup_done` · `followup_note`)와 거절 아닌 결말은
    보지 않는다(머리말 `안 보내는 것 — 두 번째`).
    """
    if meeting is None:
        return "미팅이 지워졌습니다"
    if meeting.status != "done":
        return "미팅이 완료 상태가 아닙니다(취소·일정 변경)"
    if (meeting.outcome or "") in pipeline.NO_FOLLOWUP_OUTCOMES:
        return "결과가 거절로 적혀 있습니다"
    if _superseded(meeting, [o for o in others if _same_company(o, meeting)]):
        return "그 뒤 미팅이 또 잡혀 있습니다"
    return _contact_problem(db, contact)


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
    rounds = [(head, at, _due_meetings(db, day, days))
              for head, days, at in _rounds(values, day)]
    due = [m for _head, _at, meetings in rounds for m in meetings]
    if not due:
        return runner.Batch(note="물어볼 미팅이 없습니다")

    contacts = {c.id: c for c in db.execute(
        select(VcContact).where(VcContact.id.in_({m.contact_id for m in due}))
    ).scalars().all()}
    others = _later_meetings(db, contacts)
    old = _queued_by_old_list(db, [m.id for head, _at, meetings in rounds
                                   if head == REVIEW_REF for m in meetings])
    rooms = sender_rooms.rooms_for(db, sender.id, contacts.values())

    batch = runner.Batch(note="물어볼 미팅이 없습니다")
    for head, at, meetings in rounds:
        decision = head == DECISION_REF
        seen = set()
        for meeting in meetings:
            contact = contacts.get(meeting.contact_id)
            who = f"{contact.name}({contact.firm or '-'})" if contact else f"#{meeting.id}"
            if decision:
                who += f" · {DECISION_LABEL}"
            judge = why_not_decision if decision else why_not
            why = judge(db, meeting, contact, others.get(meeting.contact_id, []))
            if not why and not decision and meeting.id in old:
                why = "결과 문의 대기 목록으로 이미 섰습니다"
            if not why and contact.id in seen:
                # 같은 분과 같은 날 미팅이 둘 — 한 통이면 된다. 첫 번째와 두 번째가
                # 겹치는 것은 장부(같은 분 하루 N통)가 막는다.
                why = "같은 담당자에게 이미 한 통이 실렸습니다"
            if why:
                batch.skipped.append(f"{who} — {why}")
                continue
            seen.add(contact.id)
            batch.outs.append(automation.Out(
                room=rooms.get(contact.id) or contact.kakao_room_name,
                # 첫 번째는 발송 화면의 미팅 후기 탭과 **같은 함수**다 — 글자 하나까지
                # 같다. 두 번째는 같은 틀에 본문만 투자 결정 문의다.
                message=(deals_view.meeting_decision_message(db, sender, contact, meeting)
                         if decision else deals_view.review_message(db, sender, contact)),
                contact_id=contact.id, stage=mc.STAGE_MEETING,
                ref=f"{head}:{meeting.id}", at=at))
    return batch


def _parse_ref(ref) -> Tuple[str, Optional[int]]:
    """`meeting:12` → `("meeting", 12)`, `meeting30:12` → `("meeting30", 12)`.
    못 읽으면 번호가 `None`."""
    head, _, raw = str(ref or "").partition(":")
    try:
        return head, int(raw)
    except ValueError:
        return head, None


def still_ok(db: Session, rec: AutomationSend) -> str:
    """예약이 풀리기 직전 — 그사이 결과를 적었거나 미팅이 바뀌었으면 뺀다.
    두 번째는 두 번째의 규칙(`why_not_decision`)으로 다시 보고, 그사이 판에서
    두 번째를 껐으면(날수 0) 뺀다."""
    head, meeting_id = _parse_ref(rec.ref)
    if meeting_id is None:
        return ""
    if head == DECISION_REF and not runner.values(
            automation.load(db, automation.MEETING_REVIEW),
            automation.MEETING_REVIEW)["decision_days"]:
        return "두 번째(투자 결정 문의)를 껐습니다"
    meeting = db.get(Meeting, meeting_id)
    contact = db.get(VcContact, meeting.contact_id) if meeting else None
    others = _later_meetings(db, [meeting.contact_id]).get(
        meeting.contact_id, []) if meeting else []
    judge = why_not_decision if head == DECISION_REF else why_not
    return judge(db, meeting, contact, others)


def manual(db: Session, values: dict, target, day: date) -> str:
    """사람이 미팅 요청·후기를 보냈으면 안 묻는다(`automation_dedup.manual_meeting`
    — 자동화가 보낸 것은 안 센다).

    - 첫 번째 — **그 미팅을 마친 뒤** `manual_days` 일 안. 미팅을 마치기 **전**에
      보낸 글은 세지 않는다 — 그 미팅을 잡게 한 미팅 요청이 대개 일주일 안쪽이라,
      세면 문의가 거의 늘 빠진다.
    - 두 번째 — 그 미팅을 마친 뒤 **전부**(`manual_days` 와 상관없이). 미팅 뒤
      사람이 이미 물었으면 한 달 뒤 자동 문의는 끼어들지 않는다.
    """
    from .. import automation_dedup

    head, meeting_id = _parse_ref(getattr(target, "ref", ""))
    meeting = db.get(Meeting, meeting_id) if meeting_id is not None else None
    after = (meeting.done_at or "") if meeting is not None else ""
    if head == DECISION_REF:
        try:
            since = date.fromisoformat(after[:10])
        except ValueError:
            return ""
        return automation_dedup.manual_meeting(db, target.contact_id, since,
                                               after=after)
    days = int(values.get("manual_days") or 0)
    if days <= 0:
        return ""
    return automation_dedup.manual_meeting(db, target.contact_id,
                                           day - timedelta(days=days),
                                           after=after or None)


def summary(values: dict) -> str:
    """판 첫 칸의 한 줄 — **저장된 날수 · 시각으로** 적는다. 두 번째 날수가 0 이면
    `두 번째 문의 꺼짐`(기본값 글 '30일 뒤 … 투자 결정 문의' 는 꺼 둔 줄에서 거짓말이다
    — 화면 점검 10/17)."""
    first = (f"미팅 완료 {values['days']}일 뒤 {values['time']} 그 투자사 방에 "
             "미팅 후기 문구")
    if not values["decision_days"]:
        return f"{first} · 두 번째 문의 꺼짐"
    return (f"{first}, {values['decision_days']}일 뒤 {values['decision_time']} "
            "투자 결정 문의(거절이면 안 물음)")


runner.register(runner.Spec(
    key=automation.MEETING_REVIEW, kind="deal_intro", plan=plan,
    collect=collect, still_ok=still_ok, fields=FIELDS, check=_check, manual=manual,
    summary=summary))
