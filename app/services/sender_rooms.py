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

**아무것도 보내지 않는다.** 확인 잡은 방 제목만 읽는다.
"""
from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import (SENDER_ROOM_TOPIC, SendItem, SendJob, SenderRoom, User,
                      VcContact)
from . import sheet_owner

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

def row_of(db: Session, sender_id: int, contact_id: int) -> Optional[SenderRoom]:
    return db.execute(
        select(SenderRoom).where(SenderRoom.sender_user_id == sender_id,
                                 SenderRoom.contact_id == contact_id)
    ).scalars().first()


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


def queue_check(db: Session, sender: User) -> Optional[SendJob]:
    """[보내는 계정 PC 로 전체 방 확인] — 방 확인 잡 하나를 **보내는 계정 것으로**.

    `None` 이면 확인할 사람이 없다. 문구는 비운다(`contacts.verify_rooms` 와
    같은 까닭: 구버전 발송기가 이 잡을 발송으로 오해해도 보낼 내용이 없다).
    """
    from ..routers.agent_api import VERIFY_KIND

    people = targets(db, sender)
    if not people:
        return None
    job = SendJob(user_id=sender.id, kind=VERIFY_KIND, status="queued",
                  total=len(people), sent=0, failed=0, topic=SENDER_ROOM_TOPIC)
    db.add(job)
    db.flush()
    for contact in people:
        db.add(SendItem(job_id=job.id, contact_id=contact.id,
                        room_name=contact.kakao_room_name.strip(), message="",
                        status="pending"))
    db.commit()
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


# ── 결과 받기 ────────────────────────────────────────────────────────────────

def apply_result(db: Session, item: SendItem, body, verdict: str) -> None:
    """방 확인 결과를 **이 표에만** 담는다. 담당 팀원의 줄은 안 건드린다.

    - 찾은 제목들 중 주인의 제목과 **똑같은 것이 정확히 하나** → 확인됨.
    - 하나도 못 찾았는데 판정이 `verified` → 발송기가 주인의 제목 그대로 방을
      열어 본 것이다(검색 기능이 없는 발송기의 `verify_room`) — 확인됨.
    - 그 밖(제목이 다르다 · 같은 제목이 여럿) → 후보만, 사람이 고른다.
    """
    contact = item.contact
    job = item.job
    if contact is None or job is None:
        item.status = "failed"
        item.error = "담당자를 찾을 수 없습니다"
        return
    own = (contact.kakao_room_name or "").strip()
    rooms = [str(r).strip() for r in (body.candidates or []) if str(r).strip()]
    found = (body.found_room or "").strip()
    if found and found not in rooms:
        rooms.insert(0, found)
    if verdict == "verified" and not rooms:
        rooms = [own]

    row = row_of(db, job.user_id, contact.id)
    if row is None:
        row = SenderRoom(sender_user_id=job.user_id, contact_id=contact.id,
                         verified=0)
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
    row.verified = 0
    row.room_name = None
    item.status = "failed"
    item.sent_at = None
    if rooms:
        item.error = (f"보내는 계정 카톡의 제목이 다릅니다 — 후보 {len(rooms)}개, "
                      "팀 현황 → 보내는 계정 방 제목에서 고르세요")
    else:
        item.error = "보내는 계정 카톡에서 이 방을 찾지 못했습니다"


def confirm(db: Session, sender_id: int, contact_id: int, title: str) -> SenderRoom:
    """[이 방으로 확정] — 후보 중 하나를 그 계정 카톡의 제목으로 적는다.

    **후보에 없는 글자는 받지 않는다** — 카톡 창에서 읽어 온 글자만 확인됨이
    된다. 같은 제목이 후보에 여럿이면 어느 방인지 가를 수 없어 받지 않는다.
    """
    row = row_of(db, sender_id, contact_id)
    text = (title or "").strip()
    picks = candidates(row)
    if row is None or not text or text not in picks:
        raise NotPickable("카톡에서 찾은 후보가 아닙니다 — 화면을 새로 열어 보세요")
    if picks.count(text) > 1:
        raise NotPickable("같은 제목의 방이 여럿입니다 — 카톡에서 방 이름을 고유하게 "
                          "바꾼 뒤 다시 확인하세요")
    row.room_name = text
    row.verified = 1
    db.commit()
    return row


def clear(db: Session, sender_id: int, contact_id: int) -> None:
    """확정을 거둔다 — 다시 주인의 제목으로 보낸다."""
    row = row_of(db, sender_id, contact_id)
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
    """`/team/sender-rooms` 가 읽는 한 판 — 고를 것이 있는 줄이 위로."""
    people = targets(db, sender)
    rows = {r.contact_id: r for r in db.execute(
        select(SenderRoom).where(SenderRoom.sender_user_id == sender.id)
    ).scalars().all()}
    owners = {u.id: u.name for u in db.execute(select(User)).scalars().all()}
    out = []
    for contact in people:
        row = rows.get(contact.id)
        state = state_of(row)
        picks = candidates(row)
        out.append({
            "contact_id": contact.id,
            "owner": owners.get(contact.user_id, ""),
            "name": contact.name,
            "firm": contact.firm or "",
            "own_room": (contact.kakao_room_name or "").strip(),
            "room": (row.room_name or "") if row else "",
            "state": state,
            "state_label": STATE_LABELS[state].format(n=len(picks)),
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
