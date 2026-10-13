"""딜 소싱 — **이 달 이 사람에게서 딜을 받았나.**

딜 소싱 화면의 줄마다 그 달 `딜 받음` 표시(`mark`). 달마다 한 줄이다 — 다음
달이 되면 다시 비어 있다. 소싱 리마인드 자동화(#277, 아직 안 들어옴)는 이
표를 보고 이 달 딜을 **아직 안 준** 사람에게만 보낸다.

## 메일로 저절로 적는 길

딜은 대개 메일로 온다. 회사 받은 편지함(POP3)의 머리글을 읽어
(`services/sourcing_mail.py`) **보낸 사람 주소 → 소싱 명단 줄**을 찾아
`source="mail"` 로 적는다 — 그 자리가 `record_from_mail` 하나다. 화면 ·
리마인드는 이 표만 본다.

  · 주소는 `email` 칸과 **`firm` 칸 둘 다**에서 줍는다 — 시트에서 옮길 때
    주소가 회사 칸에 들어간 줄이 있다(`addresses_of`).
  · 사람이 누른 표시는 그대로 둔다. 메일은 **세우기만** 하고 거두지 않는다.
  · 같은 메일(Message-ID)로는 한 번만 — 사람이 거둔 표시를 같은 메일이 다시
    세우지 않는다(`models.SourcingMailSeen`).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import SourcingContact, SourcingMailSeen, SourcingReceipt

SOURCE_MANUAL = "manual"
SOURCE_MAIL = "mail"


def month_of(day: Optional[date] = None) -> str:
    day = day or clock.today()
    return f"{day.year:04d}-{day.month:02d}"


def received_ids(db: Session, month: str) -> Set[int]:
    """그 달 `딜 받음` 인 사람들."""
    return set(db.execute(
        select(SourcingReceipt.sourcing_contact_id)
        .where(SourcingReceipt.month == month)
    ).scalars().all())


def is_received(db: Session, contact_id: int, month: str) -> bool:
    return contact_id in received_ids(db, month) if contact_id else False


def receipts(db: Session, month: str) -> Dict[int, SourcingReceipt]:
    """그 달 `딜 받음` 줄들 — 사람 번호 → 줄. 화면이 `메일 10/15` 를 적을 때."""
    rows = db.execute(
        select(SourcingReceipt).where(SourcingReceipt.month == month)
    ).scalars().all()
    return {row.sourcing_contact_id: row for row in rows}


def mark(db: Session, contact_id: int, month: str, *, source: str = SOURCE_MANUAL,
         user_id: Optional[int] = None, mail_at: Optional[str] = None,
         mail_subject: Optional[str] = None,
         mail_message_id: Optional[str] = None) -> bool:
    """`딜 받음` 을 적는다. 새로 적었으면 참(이미 있으면 그대로). 커밋은 부르는 쪽이.

    이미 있으면 **아무것도 바꾸지 않는다** — 사람이 누른 줄을 메일이 덮어
    `메일` 로 바꾸지 않는다.
    """
    exists = db.execute(
        select(SourcingReceipt.id).where(
            SourcingReceipt.sourcing_contact_id == contact_id,
            SourcingReceipt.month == month)
    ).first()
    if exists:
        return False
    db.add(SourcingReceipt(sourcing_contact_id=contact_id, month=month,
                           source=source, user_id=user_id, mail_at=mail_at,
                           mail_subject=mail_subject,
                           mail_message_id=mail_message_id))
    db.flush()
    return True


def unmark(db: Session, contact_id: int, month: str) -> int:
    """`딜 받음` 을 거둔다. 커밋은 부르는 쪽이."""
    rows = db.execute(
        select(SourcingReceipt).where(
            SourcingReceipt.sourcing_contact_id == contact_id,
            SourcingReceipt.month == month)
    ).scalars().all()
    for row in rows:
        db.delete(row)
    return len(rows)


# 주소 한 개. 칸에 이름·괄호·여러 주소가 섞여 있어도 주소만 줍는다.
# 전각 골뱅이(＠)는 먼저 반각으로 바꾼다 — 손으로 옮겨 적은 칸에 섞여 있다.
_ADDRESS = re.compile(r"[A-Za-z0-9._%+'\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")


def addresses_in(text: Optional[str]) -> List[str]:
    """글자 속 메일 주소들(소문자, 나온 차례, 겹친 것은 한 번)."""
    found: List[str] = []
    for hit in _ADDRESS.findall((text or "").replace("＠", "@")):
        key = hit.strip(".").lower()
        if key and key not in found:
            found.append(key)
    return found


def addresses_of(row: SourcingContact) -> List[str]:
    """이 줄의 메일 주소 — `email` 칸, 그리고 **`firm` 칸에 잘못 들어간 주소**도."""
    out = addresses_in(row.email)
    for key in addresses_in(row.firm):
        if key not in out:
            out.append(key)
    return out


def address_book(db: Session) -> Dict[str, List[int]]:
    """주소 → 그 주소를 가진 명단 줄들. 같은 사람이 갈래마다 한 줄이라 여럿일 수 있다."""
    book: Dict[str, List[int]] = {}
    rows = db.execute(
        select(SourcingContact).order_by(SourcingContact.id)
    ).scalars().all()
    for row in rows:
        for key in addresses_of(row):
            book.setdefault(key, []).append(row.id)
    return book


def without_address(db: Session) -> int:
    """메일 주소가 한 칸에도 없는 줄 수 — 메일 확인이 찾을 수 없는 사람."""
    rows = db.execute(select(SourcingContact)).scalars().all()
    return sum(1 for row in rows if not addresses_of(row))


def mail_count(db: Session, month: str) -> int:
    """그 달 메일로 `딜 받음` 이 선 줄 수."""
    return sum(1 for row in receipts(db, month).values()
               if row.source == SOURCE_MAIL)


def record_from_mail(db: Session, address: str, when: Optional[date] = None, *,
                     subject: str = "", message_id: str = "",
                     mail_at: Optional[str] = None,
                     book: Optional[Dict[str, List[int]]] = None) -> List[int]:
    """**메일로 딜이 왔다** — 보낸 주소로 소싱 명단 줄을 찾아 그 달 `딜 받음`.

    받은 편지함을 읽는 쪽(`services/sourcing_mail.py`)이 부른다. 같은 주소가
    여러 갈래에 있으면 그 줄 전부에 적는다(같은 사람이 갈래마다 한 줄이다).
    **새로** 적은 줄 번호들. 커밋은 부르는 쪽이.

    `message_id` 가 있으면 **그 메일로는 한 번만** 본다 — 이미 본 메일이면
    (사람이 그 뒤 표시를 거뒀어도) 다시 세우지 않는다. 주소 장부(`book`)는
    여러 통을 한꺼번에 볼 때 한 번만 만들려고 받는다.
    """
    key = (address or "").strip().lower()
    if not key:
        return []
    month = month_of(when)
    ids = (book if book is not None else address_book(db)).get(key, [])
    out: List[int] = []
    for cid in ids:
        if message_id:
            seen = db.execute(
                select(SourcingMailSeen.id).where(
                    SourcingMailSeen.message_id == message_id,
                    SourcingMailSeen.sourcing_contact_id == cid)
            ).first()
            if seen:
                continue
            db.add(SourcingMailSeen(message_id=message_id, sourcing_contact_id=cid,
                                    month=month, mail_at=mail_at))
            db.flush()
        if mark(db, cid, month, source=SOURCE_MAIL, mail_at=mail_at,
                mail_subject=subject or None, mail_message_id=message_id or None):
            out.append(cid)
    return out


def delete_for(db: Session, contact_ids: Iterable[int]) -> None:
    """명단 줄을 지울 때 그 줄의 표시도 함께 — 가리킬 곳이 없는 줄을 남기지 않는다."""
    ids = list(contact_ids)
    if ids:
        db.query(SourcingReceipt).filter(
            SourcingReceipt.sourcing_contact_id.in_(ids)).delete(
            synchronize_session=False)
        db.query(SourcingMailSeen).filter(
            SourcingMailSeen.sourcing_contact_id.in_(ids)).delete(
            synchronize_session=False)
