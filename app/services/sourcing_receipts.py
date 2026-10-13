"""딜 소싱 — **이 달 이 사람에게서 딜을 받았나.**

소싱 리마인드(`services/automations/sourcing_remind.py`)는 이 달 딜을 **아직
안 준** 사람에게만 나간다. 받은 사람은 딜 소싱 화면에서 `딜 받음` 을 누른다
(`mark`). 달마다 한 줄이다 — 다음 달이 되면 다시 비어 있다.

## 메일로 저절로 적는 길 — 열어만 두었다

딜은 메일로 온다. 나중에 받은 편지함(IMAP)을 읽어 저절로 적으려면 **보낸
사람 주소 → 소싱 명단 줄**을 찾아 `source="mail"` 로 적으면 된다 — 그 자리가
`record_from_mail` 이다. 편지함을 읽는 쪽은 아직 만들지 않았다(어느 편지함을
어떤 자격으로 읽을지 정해지지 않았다). 만들 때는 그 실이 이 함수 하나만
부르면 되고, 화면 · 리마인드는 고칠 것이 없다.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock
from ..models import SourcingContact, SourcingReceipt

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


def mark(db: Session, contact_id: int, month: str, *, source: str = SOURCE_MANUAL,
         user_id: Optional[int] = None) -> bool:
    """`딜 받음` 을 적는다. 새로 적었으면 참(이미 있으면 그대로). 커밋은 부르는 쪽이."""
    exists = db.execute(
        select(SourcingReceipt.id).where(
            SourcingReceipt.sourcing_contact_id == contact_id,
            SourcingReceipt.month == month)
    ).first()
    if exists:
        return False
    db.add(SourcingReceipt(sourcing_contact_id=contact_id, month=month,
                           source=source, user_id=user_id))
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


def record_from_mail(db: Session, address: str, when: Optional[date] = None) -> List[int]:
    """**메일로 딜이 왔다** — 보낸 주소로 소싱 명단 줄을 찾아 그 달 `딜 받음`.

    받은 편지함을 읽는 쪽(아직 없다)이 부를 자리다. 같은 주소가 여러 갈래에
    있으면 그 줄 전부에 적는다(같은 사람이 갈래마다 한 줄이다). 적은 줄 번호들.
    """
    key = (address or "").strip().lower()
    if not key:
        return []
    month = month_of(when)
    ids = db.execute(
        select(SourcingContact.id).where(func.lower(SourcingContact.email) == key)
    ).scalars().all()
    return [cid for cid in ids if mark(db, cid, month, source=SOURCE_MAIL)]


def delete_for(db: Session, contact_ids: Iterable[int]) -> None:
    """명단 줄을 지울 때 그 줄의 표시도 함께 — 가리킬 곳이 없는 줄을 남기지 않는다."""
    ids = list(contact_ids)
    if ids:
        db.query(SourcingReceipt).filter(
            SourcingReceipt.sourcing_contact_id.in_(ids)).delete(
            synchronize_session=False)
