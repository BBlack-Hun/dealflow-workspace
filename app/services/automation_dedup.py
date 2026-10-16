"""2단계 자동화 — **중복 발송 막기**. 같은 분 · 같은 방 · 손으로 보낸 것.

자동화 하나 안에서 같은 대상에게 두 번 안 가는 것은 `automation_sends` 의
`(자동화, ref, 시험)` 가 이미 지킨다. 여기는 그 **바깥**이다.

1. **같은 분에게 하루 N통(기본 1)** — 다른 자동화끼리도 센다. 미팅 후 문의가
   나가는 날 미팅 요청이 같은 분에게 또 가면, 받는 쪽에서는 하루에 두 번 재촉을
   받는다. 분(分)이 아니라 사람이다: 담당자(`VcContact`) · 딜 소싱 명단 줄
   (`SourcingContact`) 한 줄이 한 사람이다. 수는 팀 현황 자동화 판에서 고친다
   (`automation.Team.per_contact_daily`).
2. **같은 방에도 하루 N통** — 한 회차 안에서도, 다른 자동화끼리도(수는 1 과
   같다). 같은 투자사가 두 팀원 명단에 따로 올라 있으면(줄이 둘) 1 로는 못
   막는다 — 보내는 계정 카톡에서 그 둘은 **같은 방**이다. 방 제목은 띄어쓰기 ·
   대소문자를 빼고 견준다(`room_key`).
3. **손으로 보낸 것** — 같은 글을 사람이 먼저 보냈으면 자동으로 또 보내지
   않는다. 미팅 후 문의 · 미팅 요청은 **N일(기본 7일) 안**의 미팅 단계 글,
   소싱 리마인드는 **그 달**의 월간 리마인드(`manual_*`).

## 언제 보나 — 세울 때와 풀 때, 두 번

**세울 때**(아침, `automation_runner.run_once`)는 그날 이미 실린 것(대기 ·
보내는 중 · 보냄)을 모두 센다 — 아침에 먼저 선 회차가 있으면 뒤에 서는 회차는
그 분을 뺀다. **풀 때**(예약 시각, `automation_runner.prune`)는 **이미 풀린
것**(보냄 · 보내는 중 · 큐에 선 회차)만 센다 — 아직 안 풀린 회차끼리는 먼저
풀리는 쪽이 이긴다. 그 사이에 사람이 손으로 보냈으면 풀 때 빠진다.

뺀 것은 **사유와 함께** 남는다 — 세울 때 뺀 것은 회차 자리(`auto_send_runs.error`)
에, 풀 때 뺀 것은 발송 건(`canceled` + `자동 제외 — …`)에. 오늘 할 일과 진행
화면이 그 둘을 읽는다.

## 시험 모드끼리만 센다

시험 모드로 실린 것은 시험 모드끼리, 실제는 실제끼리 센다(`automation_sends.test`).
시험이 실제 발송을 막으면 시험을 끄는 날 아무것도 안 나간다 — 거꾸로, 시험
모드에서도 **실제와 같은 규칙으로** 빠지는 것을 볼 수 있다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Iterable, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import AutomationSend, ContactActivity, SendItem, SendJob

#: 실린 것으로 세는 건 상태 — 실패 · 취소는 받는 쪽에 아무것도 안 갔다.
LIVE_ITEMS = ("pending", "sending", "sent")
#: 이미 나간(또는 나가는 중인) 건.
GONE_ITEMS = ("sending", "sent")
#: 이미 풀린 회차 — 큐에 서 있거나 발송기가 물어 갔다.
RELEASED_JOBS = ("queued", "running")

#: 사유 앞머리. 오늘 할 일 · 진행 화면이 이 말로 중복 막기로 뺀 것을 센다.
PREFIX = "중복 방지"


def room_key(room: Optional[str]) -> str:
    """방 제목을 견주는 꼴 — 띄어쓰기를 다 빼고 대소문자를 접는다.

    발송은 정확히 같은 제목이어야 나가지만(`room_name` 머리말), **막는** 쪽은
    넓게 잡는다. `가나다 벤처스 Deal` 과 `가나다벤처스 deal` 이 같은 방으로 읽혀
    한 통이 빠지는 것은 사고가 아니고, 그 반대가 사고다.
    """
    return re.sub(r"\s+", "", room or "").casefold()


def _day_bounds(day: date) -> tuple:
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


@dataclass
class Ledger:
    """그날 **이미 실린** 자동 발송 — 사람별 수와 방."""

    limit: int = 1
    #: `("vc", id)` · `("sc", id)` → 그날 실린 수.
    people: Dict[tuple, int] = field(default_factory=dict)
    #: 방 열쇠 → 그날 그 방에 실린 수.
    rooms: Dict[str, int] = field(default_factory=dict)
    #: 방 열쇠 → 그 방을 먼저 차지한 자동화 이름(사유에 적는다).
    room_by: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _keys(contact_id: Optional[int], sourcing_contact_id: Optional[int]) -> list:
        keys = []
        if contact_id:
            keys.append(("vc", int(contact_id)))
        if sourcing_contact_id:
            keys.append(("sc", int(sourcing_contact_id)))
        return keys

    def why(self, *, contact_id: Optional[int] = None,
            sourcing_contact_id: Optional[int] = None,
            room: Optional[str] = None) -> str:
        """이 한 통을 **오늘 더 실으면 안 되는** 까닭. 실어도 되면 빈 글자."""
        for key in self._keys(contact_id, sourcing_contact_id):
            if self.people.get(key, 0) >= self.limit:
                return (f"{PREFIX} — 오늘 이 분께 자동 발송이 이미 "
                        f"{self.people[key]}통 실렸습니다(하루 최대 {self.limit})")
        rkey = room_key(room)
        if rkey and self.rooms.get(rkey, 0) >= self.limit:
            return (f"{PREFIX} — 오늘 같은 방에 이미 자동 발송이 있습니다"
                    f"({self.room_by.get(rkey, '자동화')})")
        return ""

    def add(self, *, contact_id: Optional[int] = None,
            sourcing_contact_id: Optional[int] = None,
            room: Optional[str] = None, label: str = "") -> None:
        for key in self._keys(contact_id, sourcing_contact_id):
            self.people[key] = self.people.get(key, 0) + 1
        rkey = room_key(room)
        if rkey:
            self.rooms[rkey] = self.rooms.get(rkey, 0) + 1
            self.room_by.setdefault(rkey, label or "자동화")


def ledger(db: Session, day: date, test: bool, *, limit: int,
           released_only: bool = False,
           exclude_jobs: Iterable[int] = ()) -> Ledger:
    """그날(`day`) 실린 자동 발송으로 장부를 세운다.

    - `released_only=False`(세울 때) — 대기 · 보내는 중 · 보냄을 다 센다.
    - `released_only=True`(풀 때) — 이미 나갔거나 큐에 선 회차의 건만 센다.
    - `exclude_jobs` — 지금 보고 있는 회차 자신은 빼고 센다.
    """
    from . import automation

    start, end = _day_bounds(day)
    query = (
        select(AutomationSend.automation, AutomationSend.item_id,
               AutomationSend.room, AutomationSend.contact_id,
               AutomationSend.sourcing_contact_id)
        .join(SendItem, SendItem.id == AutomationSend.item_id)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(AutomationSend.test == (1 if test else 0),
               SendJob.scheduled_at >= start, SendJob.scheduled_at < end,
               SendItem.status.in_(LIVE_ITEMS))
    )
    if released_only:
        query = query.where(or_(SendItem.status.in_(GONE_ITEMS),
                                SendJob.status.in_(RELEASED_JOBS)))
    skip = [j for j in exclude_jobs if j]
    if skip:
        query = query.where(SendJob.id.notin_(skip))
    book = Ledger(limit=max(1, int(limit or 1)))
    seen = set()
    for key, item_id, room, contact_id, sourcing_id in db.execute(query).all():
        # 채널방은 한 통에 기업마다 줄이 선다 — 한 통은 한 번만 센다.
        if item_id in seen:
            continue
        seen.add(item_id)
        kind = automation.BY_KEY.get(key)
        book.add(contact_id=contact_id, sourcing_contact_id=sourcing_id,
                 room=room, label=kind.label if kind else key)
    return book


# ── 손으로 보낸 것 ───────────────────────────────────────────────────────────

def _auto_items():
    """자동화가 세운 발송 건 — 손 발송을 셀 때 뺀다(그쪽은 `automation_sends` 가 센다)."""
    return select(AutomationSend.item_id).where(AutomationSend.item_id.isnot(None))


def _md(when: Optional[str]) -> str:
    text = (when or "")[:10]
    return f"{int(text[5:7])}/{int(text[8:10])}" if len(text) == 10 else text


def manual_meeting(db: Session, contact_id: Optional[int], since: date) -> str:
    """`since` 이후 사람이 이 담당자에게 **미팅 단계 글**(미팅 요청 · 미팅 후기)을
    보냈으면 그 사유. 없으면 빈 글자.

    둘을 본다: 앱이 내보낸 것(`deal_intro` 잡의 `stage=3`, 실제로 `sent`)과 손으로
    적은 미팅 요청 기록(`ContactActivity` 의 `meeting_ask`, 되돌린 줄은 안 보인다).
    미팅 요청과 미팅 후기는 같은 단계 값을 쓴다(`pipeline.meeting_ask_state` 의
    `아는 흠`) — 둘을 가르지 못하니 **둘 다 센다**. 빠지는 쪽으로 틀리는 것이라
    중복을 막는 자리로는 맞는 쪽이다.
    """
    from . import cadence, pipeline

    if not contact_id:
        return ""
    sent = db.execute(
        select(func.max(SendItem.sent_at))
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.contact_id == contact_id,
               SendItem.stage == cadence.STAGE_MEETING,
               SendItem.status == "sent",
               SendItem.sent_at >= since.isoformat(),
               SendItem.id.notin_(_auto_items()))
    ).scalar()
    if sent:
        return f"{PREFIX} — {_md(sent)} 에 미팅 요청·후기를 손으로 보냈습니다"
    marked = db.execute(
        select(func.max(ContactActivity.happened_at))
        .where(ContactActivity.contact_id == contact_id,
               ContactActivity.kind == pipeline.MEETING_ASK_KIND,
               ContactActivity.happened_at >= since.isoformat())
    ).scalar()
    if marked:
        return f"{PREFIX} — {_md(marked)} 에 미팅 요청을 보냈다고 적혀 있습니다"
    return ""


def manual_sourcing_remind(db: Session, sourcing_contact_id: Optional[int],
                           month: str) -> str:
    """그 달(`YYYY-MM`) 사람이 이 분께 **월간 리마인드**를 보냈으면 그 사유."""
    from . import sourcing_msg

    if not sourcing_contact_id:
        return ""
    start = f"{month}-01"
    year, mon = int(month[:4]), int(month[5:7])
    end = f"{year + (mon == 12):04d}-{(mon % 12) + 1:02d}-01"
    sent = db.execute(
        select(func.max(SendItem.sent_at))
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.sourcing_contact_id == sourcing_contact_id,
               SendJob.kind == "sourcing_intro",
               SendJob.topic == sourcing_msg.REMIND_KIND,
               SendItem.status == "sent",
               SendItem.sent_at >= start, SendItem.sent_at < end,
               SendItem.id.notin_(_auto_items()))
    ).scalar()
    if sent:
        return f"{PREFIX} — {_md(sent)} 에 이 달 월간 리마인드를 손으로 보냈습니다"
    return ""


def count_in(lines: Iterable[str]) -> int:
    """사유 목록에서 중복 막기로 뺀 것의 수."""
    return sum(1 for line in lines if PREFIX in (line or ""))
