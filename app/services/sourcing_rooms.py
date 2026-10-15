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
   못 찾으면 이름(`agent/main.py: process_verify_job`). **회사는 안 보낸다**
   (`search_terms`) — 보내면 발송기가 여럿 나온 결과를 회사 이름이 든 방 하나로
   줄이는데, 회사 이름이 든 방이 곧 그분의 **딜소개 방**이다(방 이름을 짓는
   `build_room_name` 이 회사명을 넣는다). 스타트업 쪽 `_company_search` 가 회사를
   안 보내는 것과 같은 까닭이다(PR #284 리뷰).
2. 찾은 제목은 **후보로만** 담는다(`room_candidates` — 모양은
   `room_match.save_candidates` 그대로). 하나뿐이어도 방 이름에 안 넣는다 — 이름이
   든 방이 꼭 그 분과의 딜 소싱 방인 것은 아니다(딜소개 방일 수도 있다).
   발송기 오류로 끝난 찾기는 **담아 둔 후보를 지우지 않는다** — 오류만 적는다
   (`apply_result`). 지우면 `후보 없음` 으로 서서 사람은 카톡에 방이 없다고 읽는다.
3. **[이 방으로 확정]** — 사람이 후보를 누르면 방 이름이 그 제목이 되고
   `확인됨` 이 된다(`confirm`). 카톡 창에서 읽어 온 글자만 받는다. 후보가
   없으면 카톡에서 복사해 `카톡방 이름` 칸에 직접 적는다(`확인 안 됨`).

스타트업 쪽과 다른 점 — 투자사 방을 통째로 후보에서 **빼지는 않는다.** 소싱
명단의 사람은 투자사 심사역이라 찾는 방이 곧 투자사 사람과의 방이다. 무엇이 딜
소싱 방인지는 사람이 고른다. 다만 **그분의 딜소개 방으로 이미 알려진 제목**
(이어진 투자사 줄 · 번호가 같은 투자사 줄의 `kakao_room_name`)은 딜 소싱 방이
아닌 것이 확실하므로 후보에서 빼고 확정도 막는다(`deal_rooms`) — 확정하면 소싱
리마인드가 남의 딜소개 방으로 간다.

**못 지우게 막지 않는다.** 방 찾기 건(`SendItem`)이 이 줄을 가리키지만 보낸
것이 아니다 — 딜 소싱 [삭제] 의 '보낸 이력' 에서 빼고, 지울 때 함께 치운다
(`forget`).

**아무것도 보내지 않는다.** (열린 PR #277 의 같은 이름 파일에서 옮겨 왔다 —
그쪽은 자동화 보내는 계정으로, 여기는 누른 사람 계정으로 세운다.)
"""
from __future__ import annotations

import json
import re
from typing import Iterable, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from .. import clock
from ..models import (SOURCING_ROOM_TOPIC, SendItem, SendJob, SourcingContact, User,
                      VcContact)
from . import room_match, sourcing_link, sourcing_sync
# 줄의 상태 문구 · 확정 못 하는 까닭은 스타트업 [방 매칭] 과 **한 벌**이다 —
# 두 벌이면 한쪽만 고친 날 두 [방 후보 찾기] 화면이 다른 말을 한다(PR #284 리뷰).
from .startup_room_pick import STATE_LABELS, NotPickable  # noqa: F401 — 라우터가 잡는다


def query_of(contact: SourcingContact) -> str:
    return f"{contact.name or ''} {contact.title or ''}".strip()


def needs_room(db: Session, rows: Iterable[SourcingContact]) -> List[SourcingContact]:
    """보낼 방이 **없는** 줄 — 자기 방 이름도, 이어받을 투자사 방도 없다.

    이어받기 규칙은 `sourcing_link.linked_rooms` 한 곳이다(시리즈 A 갈래는 안
    이어받는다). 발송이 방을 고르는 그 함수를 같이 지나야 '방 없음' 표시와
    실제로 못 보내는 줄이 같다.
    """
    # 불참여인 분은 받을 일이 없다 — `방 없음` 도, 방 찾기 대상도 아니다
    # (발송도 그분을 뺀다 — `routers/deals.py`).
    rows = [r for r in rows
            if not (r.kakao_room_name or "").strip() and (r.name or "").strip()
            and sourcing_sync.takes_part(r)]
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


def forget(db: Session, row_id: int) -> int:
    """지우는 줄을 가리키던 **방 찾기 건**을 치운다. 치운 수를 돌려준다.

    방 찾기는 아무것도 보내지 않는다 — 그 건은 '보낸 이력' 이 아니라서 줄을
    지우는 것을 막지 않는다(`routers/sourcing.delete_row`). 그래도 남겨 두면
    없는 줄을 가리키게 되므로 같이 치우고, 그 회차의 수를 남은 건으로 다시 센다.
    """
    from ..routers.agent_api import VERIFY_KIND   # 잡 종류는 그 라우터가 안다

    items = db.execute(
        select(SendItem).join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.sourcing_contact_id == row_id, SendJob.kind == VERIFY_KIND)
    ).scalars().all()
    jobs = {i.job_id for i in items}
    for item in items:
        db.delete(item)
    db.flush()
    for job_id in jobs:
        job = db.get(SendJob, job_id)
        counted = dict(db.execute(
            select(SendItem.status, func.count(SendItem.id))
            .where(SendItem.job_id == job_id).group_by(SendItem.status)).all())
        job.total = sum(counted.values())
        job.sent = int(counted.get("sent", 0))
        job.failed = int(counted.get("failed", 0))
    return len(items)


def search_terms(contact: SourcingContact) -> dict:
    """발송기에 실어 보내는 검색어(`agent_api._verify_search`).

    **`firm` 을 일부러 안 보낸다**(`agent_api._company_search` 와 같은 까닭).
    발송기는 결과가 둘 이상이면 `firm` 앞 글자로 걸러 하나로 줄이고, 줄여서
    하나가 되면 나머지를 버린 채 보고한다(`agent/main.py: process_verify_job`).
    회사 이름이 든 방은 그분의 **딜소개 방**이다 — 사람이 골라야 할 딜 소싱 방이
    후보에서 빠지고 딜소개 방 하나만 선다(PR #284 리뷰).

    `target` 도 안 붙인다 — 찾는 방이 곧 투자사 사람과의 방이라 발송기가 투자사
    방을 버리면 안 된다.
    """
    return {"query": query_of(contact), "name": (contact.name or "").strip()}


def _room_key(title: Optional[str]) -> str:
    return re.sub(r"\s+", "", title or "").lower()


def deal_rooms(db: Optional[Session], contact: SourcingContact) -> Set[str]:
    """이 분의 **딜소개 방**으로 알려진 제목들(공백 · 대소문자 무시 비교 열쇠).

    투자사 관리 현황의 이어진 줄(`vc_contact_id`)과 번호가 같은 줄
    (`sourcing_link.MIN_DIGITS` 이상)의 `kakao_room_name` 이다. 그 방은 딜 소싱
    방이 아닌 것이 확실하다 — 후보에서 빼고 확정도 막는다(모듈 머리말).
    """
    if db is None:
        return set()
    phone = sourcing_link.digits(contact.phone)
    out: Set[str] = set()
    for cid, raw, room in db.execute(
            select(VcContact.id, VcContact.phone, VcContact.kakao_room_name)
            .where(VcContact.kakao_room_name.isnot(None))).all():
        same = (contact.vc_contact_id and cid == contact.vc_contact_id) or (
            len(phone) >= sourcing_link.MIN_DIGITS
            and sourcing_link.digits(raw) == phone)
        if same and _room_key(room):
            out.add(_room_key(room))
    return out


def _note_failure(contact: SourcingContact, error: str) -> None:
    """찾기가 **오류로** 끝났다 — 담아 둔 후보는 그대로 두고 오류만 적는다."""
    try:
        data = json.loads(contact.room_candidates or "")
    except (TypeError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {"at": "", "query": "", "rooms": [], "dropped": 0, "same": []}
    data["error"] = error
    data["error_at"] = clock.now_iso()
    contact.room_candidates = json.dumps(data, ensure_ascii=False)


def last_error(contact: SourcingContact) -> str:
    """마지막 찾기가 오류로 끝났으면 그 사유. 그 뒤 찾기가 되면 지워진다."""
    try:
        data = json.loads(contact.room_candidates or "")
    except (TypeError, ValueError):
        return ""
    return str(data.get("error") or "") if isinstance(data, dict) else ""


def apply_result(item: SendItem, body) -> None:
    """찾은 제목들을 **후보로만** 담는다. 방 이름 · 확인 표시는 안 건드린다.

    **발송기 오류로 끝난 찾기**(후보 없이 `error` 가 실려 온 결과 — 카톡 창
    오류 등)는 담아 둔 후보를 **덮지 않는다** — 오류만 건과 줄에 적는다. 덮으면
    `후보 없음`(찾아봤는데 없음)으로 서서 사람은 카톡에 방이 없다고 읽는다. 오류
    없이 못 찾은 것은 찾아본 결과라 예전처럼 빈 후보로 담는다.
    """
    contact = item.sourcing_contact
    if contact is None:
        item.status = "failed"
        item.error = "딜 소싱 명단 줄을 찾을 수 없습니다"
        return
    rooms = [str(r).strip() for r in (body.candidates or []) if str(r).strip()]
    found = (body.found_room or "").strip()
    if found and found not in rooms:
        rooms.insert(0, found)
    error = (body.error or "").strip()
    if not rooms and error:
        _note_failure(contact, error)
        item.status = "failed"
        item.sent_at = None
        item.error = error
        return
    # 그분의 딜소개 방은 후보에서 뺀다(모듈 머리말 · `deal_rooms`).
    known = deal_rooms(object_session(contact), contact)
    kept = [r for r in rooms if _room_key(r) not in known]
    room_match.save_candidates(contact, kept, at=clock.now_iso(),
                               query=query_of(contact),
                               dropped=len(rooms) - len(kept))
    rooms = kept
    if rooms:
        item.status = "sent"
        item.sent_at = clock.now_iso()
        # 후보가 여럿이면 고르면 된다 — `카톡에서 방 이름을 고유하게` 같은
        # 안 해도 되는 일을 시키지 않는다(`agent_api._apply_company_candidates`).
        item.error = None
    else:
        item.status = "failed"
        item.sent_at = None
        item.error = error or ("카톡에서 찾은 방이 이 분의 딜소개 방뿐입니다"
                               if found or body.candidates
                               else "카톡에서 이 분의 방을 찾지 못했습니다")


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
            "state_label": STATE_LABELS[state].format(n=len(found["rooms"])),
            # 마지막 찾기가 발송기 오류로 끝났으면 그 사유(후보는 그 전 것 그대로).
            "error": last_error(contact)}


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
    if _room_key(text) in deal_rooms(object_session(contact), contact):
        # 예전에 담긴 후보에 남아 있을 수 있다 — 담을 때 빼는 것과 같은 규칙.
        raise NotPickable("이 분의 투자사 딜소개 방입니다 — 딜 소싱 방이 아니라 "
                          "확정하지 않습니다")
    contact.kakao_room_name = text
    contact.room_verified = "verified"
    return contact
