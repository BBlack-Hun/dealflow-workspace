"""보내는 계정 카톡 기준 **방 제목** — 확인하고, 고르고, 자동화가 읽는다.

## 왜 따로 있나

카톡 단톡방 제목은 **사람마다 따로 바꿀 수 있다.** 담당 팀원이 적어 둔 방
이름(`VcContact.kakao_room_name`)은 그 팀원 카톡에서의 제목이다. 자동화는
**모든 방에 들어가 있는 한 계정**(보내는 계정)의 카톡에서 나가므로, 그 계정
카톡에서는 같은 방이 다른 제목일 수 있다. 발송기는 제목으로 방을 찾는다 —
제목이 다르면 그 한 통은 `방을 찾지 못했습니다` 로 끝난다.

## 무엇을 하나

1. **[보내는 계정 PC 로 전체 방 확인]**(관리자) — 팀원 전원의 보낼 수 있는
   투자사 담당자를 방 확인 잡 하나에 실어 **보내는 계정 것으로** 세운다
   (`queue_check`). 이미 있는 방 확인 잡(`verify_room`)에 `SENDER_ROOM_TOPIC`
   을 단다 — **발송기는 안 고친다**(줄마다 실린 `query`·`name`·`firm` 만 보고
   움직인다). 보내는 계정 본인의 담당자는 빠진다 — 그 제목이 곧 기준이다.
2. 찾은 제목은 **이 표에만** 담는다(`apply_result`). 담당 팀원의 방 이름도
   확인 표시도 `카톡방 참여여부` 도 **건드리지 않는다** — 그 팀원 카톡에서는
   그 이름이 맞다.
   - 찾은 제목 중 **주인의 제목과 똑같은 것이 정확히 하나**면 저절로 넣는다.
   - 다르거나(이름을 바꾼 방) 여럿이면 **후보만** 담고 사람이 고른다
     (`/team/sender-rooms` → `confirm`).
3. **자동화가 방을 고를 때**(`room_for`): 그 계정 카톡에서 확인된 제목이
   있으면 그것, 없으면 주인의 제목.

## 딜 소싱 명단도 같은 길이다(0135)

딜 소싱 방 이름(`SourcingContact.kakao_room_name`)은 [방 후보 찾기]를 누른
팀원 카톡의 제목이다(`services/sourcing_rooms.py`). 딜 소싱 참여 제안 · 소싱
리마인드 자동화는 보내는 계정 카톡에서 나가므로 그 계정 기준 제목이 따로
있어야 한다. 그래서

- [전체 방 확인]에 **불참여가 아닌 딜 소싱 분**도 함께 싣는다(`sourcing_targets`).
  방 이름이 있으면 그 제목으로, 없으면 이름+직함으로 찾는다.
- **보내는 계정이 딜 소싱 화면에서 [방 후보 찾기]를 눌러도** 찾은 제목은 이 표에만
  담는다(`queue_sourcing` — `routers/sourcing.search_rooms`). 딜 소싱 명단의 방
  이름 · 후보 · 확인 표시는 그대로다 — 그 칸은 손으로 보내는 팀원 카톡의 제목이다.
- 딜 소싱 분은 **찾은 방(같은 제목을 하나로 친)이 하나뿐이면 그 방으로 확정한다**
  (사용자 결정 2026-11-10 — `sourcing_rooms` 머리말). 사람이 [이 방으로 확정] 을
  누른 것과 같은 길(`confirm`)이다. 둘 이상일 때만 사람이 고른다. 투자사 담당자
  줄은 그대로다(제목이 다르면 하나뿐이어도 후보만).
- 그 계정이 딜 소싱 분께 보낼 때(자동화 · 손으로 보내는 딜 소싱 제안) 확인된
  제목이 먼저, 없으면 명단의 방 이름(`sourcing_rooms_for`).

**누가 보내는 계정인가는 코드에 적지 않는다** — 팀 현황 자동화 판의 자동 발송
계정과 자동화마다 고른 계정이다(`senders`).

**아무것도 보내지 않는다.** 확인 잡은 방 제목만 읽는다.
"""
from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import (SENDER_ROOM_TOPIC, SendItem, SendJob, SenderRoom,
                      SourcingContact, User, VcContact)
from . import edit_log, sheet_owner

#: 줄의 상태 — 화면이 이 말을 그대로 적는다.
CONFIRMED = "confirmed"
PICKS = "picks"
NOT_FOUND = "not_found"
NEVER = "never"
STATE_LABELS = {
    CONFIRMED: "확인됨",
    PICKS: "후보 {n}개 — 골라 주세요",
    NOT_FOUND: "못 찾음",
    NEVER: "아직 안 찾아봄",
}


class NotPickable(ValueError):
    """확정할 수 없는 제목. 까닭이 그대로 화면에 간다."""


# ── 읽기 ────────────────────────────────────────────────────────────────────

def row_of(db: Session, sender_id: int, contact_id: int,
           sourcing: bool = False) -> Optional[SenderRoom]:
    """(보내는 계정, 줄) 의 한 줄. `sourcing` 이면 `contact_id` 는 딜 소싱 줄 번호다."""
    column = SenderRoom.sourcing_contact_id if sourcing else SenderRoom.contact_id
    return db.execute(
        select(SenderRoom).where(SenderRoom.sender_user_id == sender_id,
                                 column == contact_id)
    ).scalars().first()


def senders(db: Session) -> List[User]:
    """**보내는 계정들** — 팀 현황 자동화 판의 자동 발송 계정과 자동화마다 고른 계정.

    `/team/sender-rooms` 가 고르는 계정이고, 딜 소싱 화면의 [방 후보 찾기]를 이
    표로 돌리는 판정(`is_sender`)도 같은 목록을 읽는다.
    """
    from . import automation

    seen, out = set(), []
    ids = [automation.default_sender_id(db)] + [
        automation.sender_id(db, automation.load(db, k.key)) for k in automation.KINDS]
    for uid in ids:
        member = db.get(User, uid) if uid else None
        if member is not None and automation.may_send(member) and member.id not in seen:
            seen.add(member.id)
            out.append(member)
    return out


def is_sender(db: Session, user: Optional[User]) -> bool:
    return user is not None and any(s.id == user.id for s in senders(db))


def candidates(row: Optional[SenderRoom]) -> List[str]:
    if row is None or not row.candidates:
        return []
    try:
        value = json.loads(row.candidates)
    except ValueError:
        return []
    return [str(v) for v in value if str(v).strip()] if isinstance(value, list) else []


def room_for(db: Session, sender_id: int, contact: VcContact) -> str:
    """**이 계정이 이 담당자에게 보낼 때의 방 제목.**

    그 계정 카톡에서 확인된 제목 → 없으면 주인의 제목. 보내는 계정 본인의
    담당자면 주인의 제목이 곧 그 계정 카톡의 제목이다.
    """
    own = (contact.kakao_room_name or "").strip()
    if contact.user_id == sender_id:
        return own
    row = row_of(db, sender_id, contact.id)
    if row is not None and row.verified and (row.room_name or "").strip():
        return row.room_name.strip()
    return own


def rooms_for(db: Session, sender_id: int,
              contacts: Iterable[VcContact]) -> Dict[int, str]:
    """`room_for` 를 여럿 한 번에 — 줄마다 조회하지 않는다."""
    contacts = list(contacts)
    ids = [c.id for c in contacts if c.user_id != sender_id]
    rows = {}
    if ids:
        rows = {r.contact_id: r for r in db.execute(
            select(SenderRoom).where(SenderRoom.sender_user_id == sender_id,
                                     SenderRoom.contact_id.in_(ids))
        ).scalars().all()}
    out = {}
    for contact in contacts:
        own = (contact.kakao_room_name or "").strip()
        row = rows.get(contact.id)
        if (contact.user_id != sender_id and row is not None and row.verified
                and (row.room_name or "").strip()):
            out[contact.id] = row.room_name.strip()
        else:
            out[contact.id] = own
    return out


def sourcing_rooms_for(db: Session, sender_id: int,
                       people: Iterable[SourcingContact]) -> Dict[int, str]:
    """딜 소싱 분들 중 **이 계정 카톡에서 확인된 제목**이 있는 분만 — {줄 번호: 제목}.

    없는 분은 들어 있지 않다 — 부르는 쪽이 명단의 방 이름으로 이어 간다
    (`sourcing_link.room_for`). 딜 소싱 줄에는 주인이 없어서 투자사 쪽처럼
    "본인 줄이면 주인의 제목" 갈래가 없다.
    """
    ids = [p.id for p in people]
    if not ids:
        return {}
    rows = db.execute(
        select(SenderRoom).where(SenderRoom.sender_user_id == sender_id,
                                 SenderRoom.sourcing_contact_id.in_(ids),
                                 SenderRoom.verified == 1)
    ).scalars().all()
    return {r.sourcing_contact_id: r.room_name.strip() for r in rows
            if (r.room_name or "").strip()}


# ── 누구를 확인하나 ──────────────────────────────────────────────────────────

def targets(db: Session, sender: User) -> List[VcContact]:
    """확인할 담당자 — **팀원 전원의 보낼 수 있는 투자사 담당자**(보내는 계정 본인 것 빼고).

    - 투자사로 세는 명단(`sheet_owner.investors`), 감춘 줄 아님.
    - 지금 보낼 수 있는 사람(`sheet_owner.can_send_to` — 연결 끝 · 검토중단 아님).
    - 방 이름이 적혀 있고 메일 전용이 아니다(찾을 제목이 있어야 한다).
    - 살아 있는 팀원의 줄.
    """
    active = {u.id for u in db.execute(
        select(User).where(User.is_active == 1)).scalars().all()}
    rows = db.execute(
        select(VcContact).where(VcContact.user_id != sender.id,
                                VcContact.is_hidden == 0)
        .order_by(VcContact.user_id, VcContact.id)
    ).scalars().all()
    out = []
    for contact in sheet_owner.investors(db, rows):
        if contact.user_id not in active:
            continue
        if not sheet_owner.can_send_to(contact):
            continue
        if not (contact.kakao_room_name or "").strip():
            continue
        if contact.channel_email == 1 and contact.channel_kakao == 0:
            continue
        out.append(contact)
    return out


def sourcing_targets(db: Session) -> List[SourcingContact]:
    """확인할 딜 소싱 분 — **불참여가 아닌 분 전부**(방 이름이 없어도).

    방 이름이 없는 분은 이름+직함으로 찾고, 찾은 제목은 후보로만 담긴다. 같은 분이
    여러 갈래에 있으면 줄마다 따로다 — 딜 소싱 화면과 같다.
    """
    from . import sourcing_sync

    rows = db.execute(
        select(SourcingContact).order_by(SourcingContact.bucket,
                                         SourcingContact.position, SourcingContact.id)
    ).scalars().all()
    return [r for r in rows if (r.name or "").strip() and not sourcing_sync.is_left(r)]


def _sourcing_item(job: SendJob, person: SourcingContact) -> SendItem:
    from .sourcing_rooms import query_of

    return SendItem(job_id=job.id, sourcing_contact_id=person.id,
                    room_name=(person.kakao_room_name or "").strip() or query_of(person),
                    message="", status="pending")


def _new_job(db: Session, sender: User, total: int) -> SendJob:
    from ..routers.agent_api import VERIFY_KIND

    job = SendJob(user_id=sender.id, kind=VERIFY_KIND, status="queued",
                  total=total, sent=0, failed=0, topic=SENDER_ROOM_TOPIC)
    db.add(job)
    db.flush()
    return job


def queue_check(db: Session, sender: User) -> Optional[SendJob]:
    """[보내는 계정 PC 로 전체 방 확인] — 방 확인 잡 하나를 **보내는 계정 것으로**.

    투자사 담당자(`targets`)와 딜 소싱 분(`sourcing_targets`)을 한 잡에 싣는다.
    `None` 이면 확인할 사람이 없다. 문구는 비운다(`contacts.verify_rooms` 와
    같은 까닭: 구버전 발송기가 이 잡을 발송으로 오해해도 보낼 내용이 없다).
    """
    people = targets(db, sender)
    sourcing = sourcing_targets(db)
    if not people and not sourcing:
        return None
    job = _new_job(db, sender, len(people) + len(sourcing))
    for contact in people:
        db.add(SendItem(job_id=job.id, contact_id=contact.id,
                        room_name=contact.kakao_room_name.strip(), message="",
                        status="pending"))
    for person in sourcing:
        db.add(_sourcing_item(job, person))
    db.commit()
    return job


def queue_sourcing(db: Session, sender: User,
                   rows: List[SourcingContact]) -> Optional[SendJob]:
    """딜 소싱 화면의 [방 후보 찾기]를 **보내는 계정**이 눌렀을 때 — 같은 확인 잡으로.

    찾은 제목은 이 표에만 담긴다(`apply_result`). 딜 소싱 명단의 후보 · 방 이름 ·
    확인 표시는 그대로다. `db.commit()` 은 부르는 쪽이 한다(`sourcing_rooms.queue_search`
    와 같다).
    """
    if not rows:
        return None
    job = _new_job(db, sender, len(rows))
    for person in rows:
        db.add(_sourcing_item(job, person))
    return job


def search_terms(contact: VcContact) -> dict:
    """발송기에 실어 보내는 검색어 — **주인의 방 제목**으로 먼저, 없으면 이름으로.

    제목을 안 바꾼 방이면 첫 검색에 그대로 걸린다. 바꾼 방이면 첫 검색이
    비고, 발송기가 `name` 으로 한 번 더 찾는다(`agent/main.py:
    process_verify_job`). 여럿이 걸리면 `firm` 으로 좁힌다 — 좁혀도 남는
    후보는 사람이 고른다.
    """
    return {"query": (contact.kakao_room_name or "").strip(),
            "name": (contact.name or "").strip(),
            "firm": contact.firm or ""}


def sourcing_search_terms(person: SourcingContact) -> dict:
    """딜 소싱 분의 검색어 — 명단의 방 이름, 없으면 이름+직함. 못 찾으면 이름으로.

    `firm` 은 **안 보낸다** — 발송기가 여럿 나온 결과를 회사 이름이 든 방 하나로
    줄이는데, 그 방은 그분의 딜소개 방이다(`sourcing_rooms.search_terms` 와 같은 까닭).
    """
    from .sourcing_rooms import query_of

    return {"query": (person.kakao_room_name or "").strip() or query_of(person),
            "name": (person.name or "").strip()}


# ── 결과 받기 ────────────────────────────────────────────────────────────────

def apply_result(db: Session, item: SendItem, body, verdict: str) -> None:
    """방 확인 결과를 **이 표에만** 담는다. 담당 팀원의 줄은 안 건드린다.

    - 찾은 제목들 중 주인의 제목과 **똑같은 것이 정확히 하나** → 확인됨.
    - 하나도 못 찾았는데 판정이 `verified` → 발송기가 주인의 제목 그대로 방을
      열어 본 것이다(검색 기능이 없는 발송기의 `verify_room`) — 확인됨.
    - 딜 소싱 분인데 찾은 제목이 **하나뿐**(같은 제목을 하나로 쳐서) → 그 방으로
      확정(`confirm` — 사용자 결정 2026-11-10). 같은 제목의 방이 여럿이면 거기서
      막혀 아래로 간다. 확정해 둔 제목이 이번에 안 걸리고 다른 하나가 걸려도 그
      하나로 바꾼다 — 예전에도 확정해 둔 제목이 안 걸리면 확정을 거뒀다.
    - 그 밖(제목이 다르다 · 같은 제목이 여럿) → 후보만, 사람이 고른다.
    """
    person = item.sourcing_contact
    contact = item.contact or person
    job = item.job
    if contact is None or job is None:
        item.status = "failed"
        item.error = "담당자를 찾을 수 없습니다"
        return
    sourcing = person is not None and item.contact is None
    own = (contact.kakao_room_name or "").strip()
    rooms = [str(r).strip() for r in (body.candidates or []) if str(r).strip()]
    found = (body.found_room or "").strip()
    if found and found not in rooms:
        rooms.insert(0, found)
    if verdict == "verified" and not rooms and own:
        rooms = [own]

    row = row_of(db, job.user_id, contact.id, sourcing)
    if row is None:
        row = SenderRoom(sender_user_id=job.user_id, verified=0,
                         contact_id=None if sourcing else contact.id,
                         sourcing_contact_id=contact.id if sourcing else None)
        db.add(row)
    row.candidates = json.dumps(rooms, ensure_ascii=False) if rooms else None
    row.checked_at = clock.now_iso()

    if own and rooms.count(own) == 1:
        row.room_name = own
        row.verified = 1
        item.status = "sent"
        item.sent_at = clock.now_iso()
        item.error = None
        return
    # 이미 사람이 확정해 둔 제목이 이번에도 걸렸으면 그대로 둔다.
    if row.verified and row.room_name and rooms.count(row.room_name) == 1:
        item.status = "sent"
        item.sent_at = clock.now_iso()
        item.error = None
        return
    if sourcing and len(set(rooms)) == 1 and _confirm_single(db, item, contact, rooms[0]):
        item.status = "sent"
        item.sent_at = clock.now_iso()
        item.error = None
        return
    row.verified = 0
    row.room_name = None
    item.status = "failed"
    item.sent_at = None
    if rooms:
        item.error = (f"보내는 계정 카톡의 제목이 다릅니다 — 후보 {len(rooms)}개, "
                      "팀 현황 → 보내는 계정 방 제목에서 고르세요")
    else:
        item.error = "보내는 계정 카톡에서 이 방을 찾지 못했습니다"


def _confirm_single(db: Session, item: SendItem, person: SourcingContact,
                    title: str) -> bool:
    """딜 소싱 분의 하나뿐인 후보를 **사람이 고른 것과 같은 길**(`confirm`)로 확정한다.

    이 길에는 요청 문맥이 없어서 수정 로그는 **찾기를 건 계정** 이름으로 남긴다
    (`sourcing_sync.mark_invited` 와 같은 방식). 확정 못 하는 제목이면 `False`.
    """
    sender_id = item.job.user_id
    db.flush()       # 새 줄 · 후보 · 건 상태는 로그 밖에서 먼저 내보낸다
    token = edit_log.begin(sender_id, "POST", f"/agent/items/{item.id}/result")
    try:
        confirm(db, sender_id, person.id, title, sourcing=True, commit=False)
        db.flush()
        return True
    except NotPickable:
        return False
    finally:
        edit_log.end(token)


def confirm(db: Session, sender_id: int, contact_id: int, title: str,
            sourcing: bool = False, commit: bool = True) -> SenderRoom:
    """[이 방으로 확정] — 후보 중 하나를 그 계정 카톡의 제목으로 적는다.

    **후보에 없는 글자는 받지 않는다** — 카톡 창에서 읽어 온 글자만 확인됨이
    된다. 같은 제목이 후보에 여럿이면 어느 방인지 가를 수 없어 받지 않는다.
    `sourcing` 이면 `contact_id` 는 딜 소싱 줄 번호다. 딜 소싱 분의 후보가
    하나뿐이면 찾기 결과를 받을 때 이 함수로 저절로 확정된다(`_confirm_single`
    — 그때는 결과 받는 쪽이 저장하므로 `commit=False`).
    """
    row = row_of(db, sender_id, contact_id, sourcing)
    text = (title or "").strip()
    picks = candidates(row)
    if row is None or not text or text not in picks:
        raise NotPickable("카톡에서 찾은 후보가 아닙니다 — 화면을 새로 열어 보세요")
    if picks.count(text) > 1:
        raise NotPickable("같은 제목의 방이 여럿입니다 — 카톡에서 방 이름을 고유하게 "
                          "바꾼 뒤 다시 확인하세요")
    row.room_name = text
    row.verified = 1
    if commit:
        db.commit()
    return row


def clear(db: Session, sender_id: int, contact_id: int,
          sourcing: bool = False) -> None:
    """확정을 거둔다 — 다시 주인의 제목으로 보낸다."""
    row = row_of(db, sender_id, contact_id, sourcing)
    if row is not None:
        row.verified = 0
        row.room_name = None
        db.commit()


# ── 화면 ────────────────────────────────────────────────────────────────────

def state_of(row: Optional[SenderRoom]) -> str:
    if row is None or not row.checked_at:
        return CONFIRMED if (row and row.verified) else NEVER
    if row.verified and row.room_name:
        return CONFIRMED
    return PICKS if candidates(row) else NOT_FOUND


def board(db: Session, sender: User) -> dict:
    """`/team/sender-rooms` 가 읽는 한 판 — 고를 것이 있는 줄이 위로.

    투자사 담당자 줄 다음에 딜 소싱 분 줄(`kind` = `sourcing`)이 함께 선다.
    """
    mine = db.execute(
        select(SenderRoom).where(SenderRoom.sender_user_id == sender.id)
    ).scalars().all()
    rows = {r.contact_id: r for r in mine if r.contact_id is not None}
    by_sourcing = {r.sourcing_contact_id: r for r in mine
                   if r.sourcing_contact_id is not None}
    owners = {u.id: u.name for u in db.execute(select(User)).scalars().all()}
    lines = ([("vc", c, rows.get(c.id), owners.get(c.user_id, ""))
              for c in targets(db, sender)]
             + [("sourcing", p, by_sourcing.get(p.id), f"딜 소싱 · {p.bucket or '-'}")
                for p in sourcing_targets(db)])
    out = []
    for kind, contact, row, owner in lines:
        state = state_of(row)
        picks = candidates(row)
        # 딜 소싱 분은 **둘 이상일 때만 고른다** — 하나뿐이면 찾을 때 확정된다
        # (`apply_result`). 하나뿐인데 확정 안 된 줄(같은 제목이 여럿 · 확정을 거둠 ·
        # 이 결정 전에 담긴 후보)에는 고르는 단추 · `골라 주세요` 를 안 세운다.
        choose = kind == "vc" or len(set(picks)) > 1
        label = STATE_LABELS[state].format(n=len(picks))
        if state == PICKS and not choose:
            label = ("같은 제목의 방이 여럿 — 확정 불가" if len(picks) > 1
                     else "후보 1개 — 다시 확인하면 확정됩니다")
        out.append({
            "kind": kind,
            "contact_id": contact.id,
            "owner": owner,
            "name": contact.name,
            "firm": contact.firm or "",
            "own_room": (contact.kakao_room_name or "").strip(),
            "room": (row.room_name or "") if row else "",
            "state": state,
            "state_label": label,
            "choose": choose,
            "picks": [{"room": p, "same": picks.count(p) > 1,
                       "current": bool(row and row.verified and row.room_name == p)}
                      for p in dict.fromkeys(picks)],
            "checked_at": (row.checked_at or "")[:16].replace("T", " ") if row else "",
        })
    order = {PICKS: 0, NOT_FOUND: 1, NEVER: 2, CONFIRMED: 3}
    out.sort(key=lambda r: (order[r["state"]], r["owner"], r["name"]))
    counts = {key: sum(1 for r in out if r["state"] == key)
              for key in (CONFIRMED, PICKS, NOT_FOUND, NEVER)}
    return {"rows": out, "total": len(out), "counts": counts,
            "sender": sender.name, "sender_id": sender.id}
