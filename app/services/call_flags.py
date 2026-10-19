"""리마인드 뒤 **답 없음 · 전화 필요** — 표시와 메모 (10/17 회의 #37).

리마인드 카톡을 보낸 뒤 팀원·담당자가 확인해서 답이 없으면 `답 없음 · 전화
필요` 를 켜고, 들은 것·할 것을 메모로 남긴다. 켜 둔 동안은 그 투자사를 맡은
팀원의 오늘 할 일에 `전화 필요` 로 서고, 끄면 빠진다.

## 딜 진행 관리에서 리마인드 카톡이 나가는 흐름 (코드 기준)

  1. **딜소개 후속 사다리**(`services/cadence.py`) — 딜소개 6~7일 뒤 리마인드
     (`closing_remind` · 선호 분야 묻기도 같은 단계), 11~14일 뒤 미팅 요청
     (`closing_meeting`), 그 사흘 뒤 전화 요청(사람이 건다). `SendSequence.stage`
     가 2 이상이면 리마인드가 나간 것이다.
  2. **IR 자료 전달 뒤 미팅 요청**(화면 말 `회의실 미팅 톡 요청`) — 자동화 A2
     (`automations/meeting_request.py`: 7일 뒤 · 답이 없으면 10일 뒤 다시) 또는
     사람이 보낸 것(발송 화면 `미팅 요청` 탭 · [IR 자료 검토 요청 보냄] 표시).
     판정은 `pipeline.meeting_ask_state`.
  3. **미팅 뒤 결과 문의** — 자동화 A7(`automations/meeting_review.py`). 사람이
     보낸 미팅 후기 탭 발송도 같은 단계(stage 3)로 남는다.

  (딜 소싱 월간 리마인드는 딜 소싱 메뉴의 일이라 여기 넣지 않았다.)

## 무엇에 붙나 — **사람 하나에 한 줄**

표시는 투자사 담당자(`VcContact`) 하나에 한 줄이다(`models.DealFollowup` 머리말).
위 세 흐름의 줄이 서는 자리마다 같은 배지가 붙는다.

## 리마인드가 아직 안 나간 사람에게는

화면은 단추를 안 세우고(`ir.html` 의 `call_flag` 매크로가 줄마다 판정을 받는다),
서버도 **켜는 것**을 막는다(`reminded`). 끄기와 메모 지우기는 막지 않는다 —
남아 있는 표시를 치울 길은 늘 있어야 한다.

## 누가 고치나

그 투자사를 맡은 팀원(`VcContact.user_id`), 그 사람의 리마인드·IR 요청·미팅
줄을 가진 팀원, 관리자(`deps.may_manage_team_contacts` — 관리자가 팀 전체의
담당자를 보고 고치는 그 판정). 그 밖의 계정에는 **없는 사람**으로 답한다(404) —
`routers/ir._owned_contact` 와 같은 말이다.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..deps import doer, may_manage_team_contacts
from ..models import (ContactActivity, DealFollowup, IrRequest, Meeting,
                      SendItem, SendSequence, User, VcContact)

#: 배지 글자. 화면 · 오늘 할 일이 같은 말을 쓴다.
LABEL = "답 없음 · 전화 필요"
#: 메모 길이 상한 — 한 줄 메모 칸이다. 넘는 것은 자른다(통째로 버리지 않는다).
MEMO_MAX = 500


def reminded_contacts(db: Session, contact_ids: Iterable[int]) -> Set[int]:
    """이 사람들 가운데 **리마인드 카톡이 한 번이라도 나간** 사람.

    위 머리말의 세 흐름을 그 흐름이 남기는 자국으로 본다.

      · 후속 사다리가 리마인드 단계를 지났다 — `SendSequence.stage >= 2`
      · 미팅 요청 · 미팅 후기가 실제로 나갔다 — `SendItem.stage == 3` · `sent`
        (A2 · A7 자동화도 이 단계로 남는다)
      · 사람이 카톡으로 직접 보내고 표시했다 — `ContactActivity` 의 `meeting_ask`

    IR 자료 전달 발송은 `stage` 가 2 로 적히지만(`deals.FOLLOW_UP_MODES`) 리마인드가
    아니라서 `SendItem.stage == 2` 는 **안 본다** — 시퀀스 단계로만 본다(자료
    전달은 시퀀스를 올리지 않고 멈춘다 — `cadence.advance`).
    """
    from .cadence import STAGE_MEETING, STAGE_REMIND
    from .pipeline import MEETING_ASK_KIND

    ids = sorted({int(i) for i in contact_ids if i})
    if not ids:
        return set()
    out: Set[int] = set()
    out |= set(db.execute(
        select(SendSequence.contact_id)
        .where(SendSequence.contact_id.in_(ids),
               SendSequence.stage >= STAGE_REMIND)).scalars().all())
    out |= set(db.execute(
        select(SendItem.contact_id)
        .where(SendItem.contact_id.in_(ids), SendItem.stage == STAGE_MEETING,
               SendItem.status == "sent")).scalars().all())
    out |= set(db.execute(
        select(ContactActivity.contact_id)
        .where(ContactActivity.contact_id.in_(ids),
               ContactActivity.kind == MEETING_ASK_KIND)).scalars().all())
    return {i for i in out if i}


def reminded(db: Session, contact_id: int) -> bool:
    return contact_id in reminded_contacts(db, [contact_id])


def may_edit(db: Session, user: User, contact: VcContact) -> bool:
    """이 사람의 표시·메모를 **이 계정이** 고칠 수 있는가 — 머리말의 `누가 고치나`."""
    if may_manage_team_contacts(user) or contact.user_id == user.id:
        return True
    for model in (SendSequence, IrRequest, Meeting):
        hit = db.execute(
            select(model.id).where(model.contact_id == contact.id,
                                   model.user_id == user.id).limit(1)).first()
        if hit:
            return True
    return False


def _row(db: Session, contact_id: int) -> DealFollowup:
    row = db.execute(
        select(DealFollowup).where(DealFollowup.contact_id == contact_id)
    ).scalars().first()
    if row is None:
        row = DealFollowup(contact_id=contact_id, call_needed=0)
        db.add(row)
    return row


def set_call(db: Session, contact_id: int, on: bool, user: User) -> DealFollowup:
    """켜거나 끈다. 누가 언제 했는지 함께 적는다. 커밋은 부르는 쪽이 한다."""
    row = _row(db, contact_id)
    row.call_needed = 1 if on else 0
    row.call_by = doer(user).id
    row.call_at = clock.now_iso()
    db.flush()
    return row


def set_memo(db: Session, contact_id: int, memo: str, user: User) -> DealFollowup:
    """메모를 적는다(비우면 지운다). 누가 언제 적었는지 함께. 커밋은 부르는 쪽이."""
    row = _row(db, contact_id)
    text = (memo or "").strip()[:MEMO_MAX]
    row.memo = text or None
    row.memo_by = doer(user).id
    row.memo_at = clock.now_iso()
    db.flush()
    return row


def _names(db: Session, ids: Iterable[Optional[int]]) -> Dict[int, str]:
    want = {i for i in ids if i}
    if not want:
        return {}
    return {u.id: u.name or f"#{u.id}" for u in db.execute(
        select(User).where(User.id.in_(want))).scalars().all()}


def views(db: Session, contact_ids: Optional[Iterable[int]] = None) -> Dict[int, dict]:
    """사람 → 화면이 그릴 값. **켜졌거나 메모가 있는 줄만** 든다.

        on        `답 없음 · 전화 필요` 가 켜져 있나
        by · at   마지막으로 켜거나 끈 사람 · 때(`YYYY-MM-DD HH:MM`)
        memo      메모(없으면 빈 글자)
        memo_by · memo_at   메모를 마지막으로 적은 사람 · 때

    끈 데다 메모도 없는 줄은 화면에 그릴 것이 없어 뺀다 — 템플릿이 `get()` 한
    번으로 "아무것도 없다" 를 알 수 있다.
    """
    stmt = select(DealFollowup)
    if contact_ids is not None:
        ids = sorted({int(i) for i in contact_ids if i})
        if not ids:
            return {}
        stmt = stmt.where(DealFollowup.contact_id.in_(ids))
    rows = [r for r in db.execute(stmt).scalars().all()
            if r.call_needed or (r.memo or "").strip()]
    names = _names(db, [r.call_by for r in rows] + [r.memo_by for r in rows])
    return {
        r.contact_id: {
            "on": bool(r.call_needed),
            "by": names.get(r.call_by or 0, ""),
            "at": clock.stamp_text(r.call_at) if r.call_at else "",
            "memo": r.memo or "",
            "memo_by": names.get(r.memo_by or 0, ""),
            "memo_at": clock.stamp_text(r.memo_at) if r.memo_at else "",
        }
        for r in rows
    }


def needed_for(db: Session, user: User) -> List[dict]:
    """**이 팀원이 걸어야 할 전화** — 켜져 있고, 그 투자사를 이 사람이 맡았다.

    `오늘 할 일` 과 딜 진행 관리의 `전화 요청` 구역이 이 한 벌을 읽는다. 끄면
    여기서 빠진다. 맡은 사람은 **지금의** `VcContact.user_id` 다 — 담당을 넘기면
    표시도 새 담당의 할 일로 따라간다.

    차례는 **오래 켜져 있던 것부터**다(가장 오래 기다린 사람이 먼저).
    """
    rows = db.execute(
        select(DealFollowup, VcContact)
        .join(VcContact, VcContact.id == DealFollowup.contact_id)
        .where(DealFollowup.call_needed == 1, VcContact.user_id == user.id)
        .order_by(DealFollowup.call_at, DealFollowup.id)
    ).all()
    flags = views(db, [f.contact_id for f, _c in rows])
    return [{
        "contact_id": c.id,
        "name": c.name or "-",
        "title": c.title or "",
        "firm": c.firm or "",
        **flags.get(c.id, {}),
    } for _f, c in rows]
