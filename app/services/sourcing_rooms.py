"""딜 소싱 명단의 카톡방 **후보 찾기 · 확정** — 딜 소싱 화면의 [방 후보 찾기].

## 왜 필요한가

딜 소싱 명단에 든 분은 **보내는 사람의 카톡 딜 소싱 방에 이미 초대돼 있는**
분이다 — 투자사 관리 현황에서 다른 팀원이 맡은 분이어도 그렇다(사용자 원문:
"딜소싱에 있다는건 다른 사람 담당자라도 카톡방에 초대 되어있다는 뜻"). 그래서
그 방은 투자사 줄의 딜소개 방이 아니라 **보내는 사람 카톡에서 찾아야** 한다.

운영에서는 그 방 이름이 든 줄이 하나도 없었다(46줄 중 0줄, 2026-10-14). 시리즈
A 갈래는 투자사 방을 이어받지 않으므로(`sourcing_link.linked_rooms`) 방 이름을
채우기 전에는 소싱 제안 · 리마인드가 그 갈래로 못 나간다.

## 무엇을 하나 — 스타트업 [방 후보 찾기](#264)와 같은 길

1. **[방 후보 찾기]** — 방 이름이 없는 줄을 방 확인 잡(`verify_room`) 하나에 실어
   **누른 사람 계정**에 세운다(`SOURCING_ROOM_TOPIC`). 그 사람 PC 의 발송기가
   그 사람 카톡에서 찾으므로, 찾은 제목이 곧 **그 사람 카톡의 제목**이다 — 그
   사람이 나중에 같은 PC 로 보낸다. **발송기는 안 고친다** — 검색어는 이름+직함,
   못 찾으면 이름, 여럿이면 회사로 좁힌다(`agent/main.py: process_verify_job`).
2. 찾은 제목은 **후보로만** 담는다(`room_candidates` — 모양은
   `room_match.save_candidates` 그대로). 하나뿐이어도 방 이름에 안 넣는다 — 이름이
   든 방이 꼭 그 분과의 딜 소싱 방인 것은 아니다(딜소개 방일 수도 있다).
3. **[이 방으로 확정]** — 사람이 후보를 누르면 방 이름이 그 제목이 되고
   `확인됨` 이 된다(`confirm`). 카톡 창에서 읽어 온 글자만 받는다. 후보가
   없으면 카톡에서 복사해 `카톡방 이름` 칸에 직접 적는다(`확인 안 됨`).

스타트업 쪽과 다른 점 하나 — 투자사 방을 후보에서 **빼지 않는다.** 소싱 명단의
사람은 투자사 심사역이라 찾는 방이 곧 투자사 사람과의 방이다. 무엇이 딜 소싱
방인지는 사람이 고른다.

**아무것도 보내지 않는다.** (열린 PR #277 의 같은 이름 파일에서 옮겨 왔다 —
그쪽은 자동화 보내는 계정으로, 여기는 누른 사람 계정으로 세운다.)
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import SOURCING_ROOM_TOPIC, SendItem, SendJob, SourcingContact, User
from . import room_match, sourcing_link

#: 줄의 상태 — 스타트업 [방 매칭] 과 같은 말이다(`startup_room_pick.STATE_LABELS`).
STATE_LABELS = {
    "confirmed": "확정됨",
    "picks": "후보 {n}개",
    "no_picks": "후보 없음",
    "never": "아직 안 찾아봄",
}


class NotPickable(ValueError):
    """확정할 수 없는 제목. 까닭이 그대로 화면에 간다."""


def query_of(contact: SourcingContact) -> str:
    return f"{contact.name or ''} {contact.title or ''}".strip()


def needs_room(db: Session, rows: Iterable[SourcingContact]) -> List[SourcingContact]:
    """보낼 방이 **없는** 줄 — 자기 방 이름도, 이어받을 투자사 방도 없다.

    이어받기 규칙은 `sourcing_link.linked_rooms` 한 곳이다(시리즈 A 갈래는 안
    이어받는다). 발송이 방을 고르는 그 함수를 같이 지나야 '방 없음' 표시와
    실제로 못 보내는 줄이 같다.
    """
    rows = [r for r in rows
            if not (r.kakao_room_name or "").strip() and (r.name or "").strip()]
    linked = sourcing_link.linked_rooms(db, rows)
    return [r for r in rows if r.id not in linked]


def targets(db: Session, bucket: str = "",
            ids: Optional[Iterable[int]] = None) -> List[SourcingContact]:
    """[방 후보 찾기] 가 찾을 줄 — 그 갈래(빈 값이면 전체)에서 방이 없는 줄."""
    stmt = select(SourcingContact).order_by(SourcingContact.position,
                                            SourcingContact.id)
    if bucket:
        stmt = stmt.where(SourcingContact.bucket == bucket)
    rows = needs_room(db, db.execute(stmt).scalars().all())
    if ids is None:
        return rows
    wanted = set(ids)
    return [r for r in rows if r.id in wanted]


def queue_search(db: Session, user: User, rows: List[SourcingContact]
                 ) -> Optional[SendJob]:
    """방 확인 잡 하나를 **누른 사람 계정**에. 찾을 줄이 없으면 `None`.

    `db.commit()` 은 부르는 쪽이 한다.
    """
    from ..routers.agent_api import VERIFY_KIND   # 잡 종류는 그 라우터가 안다

    if not rows:
        return None
    job = SendJob(user_id=user.id, kind=VERIFY_KIND, status="queued",
                  total=len(rows), sent=0, failed=0, topic=SOURCING_ROOM_TOPIC)
    db.add(job)
    db.flush()
    for row in rows:
        # 문구는 비운다 — 낡은 발송기가 발송으로 오해해도 보낼 내용이 없다.
        db.add(SendItem(job_id=job.id, sourcing_contact_id=row.id,
                        room_name=query_of(row), message="", status="pending"))
    return job


def search_terms(contact: SourcingContact) -> dict:
    """발송기에 실어 보내는 검색어(`agent_api._verify_search`).

    `target` 을 안 붙인다 — 찾는 방이 곧 투자사 사람과의 방이라 발송기가 투자사
    방을 버리면 안 된다.
    """
    return {"query": query_of(contact), "name": (contact.name or "").strip(),
            "firm": contact.firm or ""}


def apply_result(item: SendItem, body) -> None:
    """찾은 제목들을 **후보로만** 담는다. 방 이름 · 확인 표시는 안 건드린다."""
    contact = item.sourcing_contact
    if contact is None:
        item.status = "failed"
        item.error = "딜 소싱 명단 줄을 찾을 수 없습니다"
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
        # 후보가 여럿이면 고르면 된다 — `카톡에서 방 이름을 고유하게` 같은
        # 안 해도 되는 일을 시키지 않는다(`agent_api._apply_company_candidates`).
        item.error = None
    else:
        item.status = "failed"
        item.sent_at = None
        item.error = (body.error or "") or "카톡에서 이 분의 방을 찾지 못했습니다"


def picks(contact: SourcingContact) -> dict:
    """화면에 세울 후보 · 상태."""
    found = room_match.candidates(contact)
    room = (contact.kakao_room_name or "").strip()
    if room and contact.room_verified == "verified":
        state = "confirmed"
    elif found["rooms"]:
        state = "picks"
    else:
        state = "no_picks" if found["at"] else "never"
    return {"rooms": [{"room": r, "same": r in found["same"], "current": r == room}
                      for r in found["rooms"]],
            "at": found["at"], "query": found["query"], "state": state,
            "state_label": STATE_LABELS[state].format(n=len(found["rooms"]))}


def confirm(contact: SourcingContact, title: str) -> SourcingContact:
    """[이 방으로 확정] — 후보 제목을 방 이름으로, `확인됨` 으로.

    받지 않는 것: 후보에 없는 글자(직접 적기는 `카톡방 이름` 칸 — 확인 안 됨),
    같은 제목이 여럿 걸린 제목(그 글자로는 어느 방인지 가를 수 없다).
    """
    text = (title or "").strip()
    found = room_match.candidates(contact)
    if not text or text not in found["rooms"]:
        raise NotPickable("카톡에서 찾은 후보가 아닙니다 — 화면을 새로 열어 보세요")
    if text in found["same"]:
        raise NotPickable("카톡에 같은 제목의 방이 여럿입니다 — 카톡에서 방 이름을 "
                          "고유하게 바꾼 뒤 `카톡방 이름` 칸에 직접 적어 주세요")
    contact.kakao_room_name = text
    contact.room_verified = "verified"
    return contact
