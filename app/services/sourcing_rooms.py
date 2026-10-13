"""딜 소싱 명단의 카톡방 **후보 찾기 · 확정** — 딜 소싱 화면의 [방 후보 찾기].

소싱 명단 줄에는 방 이름이 거의 없다(운영: 시리즈 A 이상 갈래 21명 중 0명).
방이 없으면 소싱 제안도 소싱 리마인드도 못 나간다. 스타트업 명단의 [방 후보
찾기](#264, `services/startup_room_pick.py`)와 **같은 길**을 탄다.

1. **[방 후보 찾기]**(관리자) — 방이 없는 줄을 방 확인 잡 하나에 실어 **소싱
   리마인드를 보내는 계정 것으로** 세운다(`SOURCING_ROOM_TOPIC`). 그 계정
   PC 의 카톡에서 찾으므로 찾은 제목이 곧 그 계정 카톡의 제목이다. 발송기는
   안 고친다 — 검색어는 이름+직함, 못 찾으면 이름, 여럿이면 회사로 좁힌다.
2. 찾은 제목은 **후보로만** 담는다(`room_candidates` — 모양은
   `room_match.save_candidates` 그대로). 하나뿐이어도 방 이름에 안 넣는다.
3. **[이 방으로 확정]** — 사람이 후보를 누르면 방 이름이 그 제목이 되고
   `확인됨` 이 된다(`confirm`). 카톡 창에서 읽어 온 글자만 받는다.

스타트업 쪽과 다른 점 하나 — 투자사 방을 후보에서 **빼지 않는다.** 소싱 명단의
사람은 투자사 심사역이라 찾는 방이 곧 투자사 사람과의 방이다.

**아무것도 보내지 않는다.**
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import SOURCING_ROOM_TOPIC, SendItem, SendJob, SourcingContact, User
from . import room_match, sourcing_link


class NotPickable(ValueError):
    """확정할 수 없는 제목. 까닭이 그대로 화면에 간다."""


def query_of(contact: SourcingContact) -> str:
    return f"{contact.name or ''} {contact.title or ''}".strip()


def targets(db: Session, bucket: str = "") -> List[SourcingContact]:
    """찾을 줄 — 방 이름이 없고, 투자사 명단에서 이어 줄 방도 없는 줄."""
    stmt = select(SourcingContact).order_by(SourcingContact.position,
                                            SourcingContact.id)
    if bucket:
        stmt = stmt.where(SourcingContact.bucket == bucket)
    rows = [r for r in db.execute(stmt).scalars().all()
            if not (r.kakao_room_name or "").strip() and (r.name or "").strip()]
    linked = sourcing_link.linked_rooms(db, rows)
    return [r for r in rows if r.id not in linked]


def queue_search(db: Session, sender: User, bucket: str = "") -> Optional[SendJob]:
    """방 확인 잡 하나를 **보내는 계정 것으로**. 찾을 줄이 없으면 `None`."""
    from ..routers.agent_api import VERIFY_KIND

    rows = targets(db, bucket)
    if not rows:
        return None
    job = SendJob(user_id=sender.id, kind=VERIFY_KIND, status="queued",
                  total=len(rows), sent=0, failed=0, topic=SOURCING_ROOM_TOPIC)
    db.add(job)
    db.flush()
    for row in rows:
        # 문구는 비운다 — 구버전 발송기가 발송으로 오해해도 보낼 내용이 없다.
        db.add(SendItem(job_id=job.id, sourcing_contact_id=row.id,
                        room_name=query_of(row), message="", status="pending"))
    db.commit()
    return job


def search_terms(contact: SourcingContact) -> dict:
    """발송기에 실어 보내는 검색어. `target` 을 안 붙인다 — 찾는 방이 곧 투자사
    사람과의 방이라 발송기가 투자사 방을 버리면 안 된다."""
    return {"query": query_of(contact), "name": (contact.name or "").strip(),
            "firm": contact.firm or ""}


def apply_result(item: SendItem, body, verdict: str) -> None:
    """찾은 제목들을 **후보로만** 담는다. 방 이름 · 확인 표시는 안 건드린다."""
    contact = item.sourcing_contact
    if contact is None:
        item.status = "failed"
        item.error = "소싱 명단 줄을 찾을 수 없습니다"
        return
    rooms = [str(r).strip() for r in (body.candidates or []) if str(r).strip()]
    found = (body.found_room or "").strip()
    if found and found not in rooms:
        rooms.insert(0, found)
    room_match.save_candidates(contact, rooms, at=clock.now_iso(),
                               query=query_of(contact))
    if rooms:
        item.status = "sent"
        item.sent_at = clock.now_iso()
        item.error = None
    else:
        item.status = "failed"
        item.sent_at = None
        item.error = body.error or "카톡에서 이 사람의 방을 찾지 못했습니다"


def picks(contact: SourcingContact) -> dict:
    found = room_match.candidates(contact)
    return {"rooms": found["rooms"], "same": found["same"], "at": found["at"]}


def confirm(contact: SourcingContact, title: str) -> SourcingContact:
    """[이 방으로 확정] — 후보 제목을 방 이름으로, `확인됨` 으로."""
    text = (title or "").strip()
    found = room_match.candidates(contact)
    if not text or text not in found["rooms"]:
        raise NotPickable("카톡에서 찾은 후보가 아닙니다 — 화면을 새로 열어 보세요")
    if text in found["same"]:
        raise NotPickable("카톡에 같은 제목의 방이 여럿입니다 — 카톡에서 방 이름을 "
                          "고유하게 바꾼 뒤 직접 적어 주세요")
    contact.kakao_room_name = text
    contact.room_verified = "verified"
    return contact
