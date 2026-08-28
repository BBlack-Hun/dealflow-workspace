"""딜 소싱 명단 ↔ 투자사 관리 현황 잇기.

같은 사람이 두 표에 있다. 투자사 관리 현황에서 이미 카톡방까지 연결해 둔
사람이면, 딜 소싱에서 방 이름을 **다시 적을 이유가 없다** — 손으로 옮겨
적으면 한 글자만 달라도 발송이 통째로 skip 된다.

**휴대폰 번호로만 잇는다.** 이름은 안 된다 — 같은 이름이 여럿 있고(한 이름이
셋이었다), 잘못 이으면 남의 방으로 나간다. 번호는 사람마다 하나뿐이라
틀릴 여지가 없다.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import sheet_owner
from ..models import VcContact

#: 휴대폰으로 인정할 최소 자릿수. `010-1234-5678` → 11자리.
#: 짧은 값(내선번호 `1234`)끼리 우연히 맞아 엉뚱한 사람과 이어지는 것을 막는다.
MIN_DIGITS = 10


def digits(phone: Optional[str]) -> str:
    return re.sub(r"\D", "", phone or "")


def _by_phone(contacts: List[VcContact]) -> Dict[str, VcContact]:
    """번호 → 담당자. 번호가 겹치면 **아예 빼 버린다.**

    같은 번호가 둘이면 어느 쪽 방인지 알 수 없다. 하나를 골라 두면 반은 틀린다.
    """
    seen: Dict[str, VcContact] = {}
    clashed = set()
    for c in contacts:
        key = digits(c.phone)
        if len(key) < MIN_DIGITS:
            continue
        if key in seen:
            clashed.add(key)
        seen[key] = c
    for key in clashed:
        seen.pop(key, None)
    return seen


def linked_rooms(db: Session, sourcing) -> Dict[int, dict]:
    """소싱 대상 → 투자사 명단에서 찾은 방.

    `{sourcing_id: {"room": 방 이름, "firm": 투자사, "contact_id": …}}`

    자기 방을 이미 적어 둔 줄은 건드리지 않는다 — 사람이 적은 것이 우선이다.
    """
    # 투자사로 세지 않는 명단은 잇지 않는다 — 스타트업 대표의 번호가 소싱
    # 명단의 심사역과 우연히 맞으면 그 방으로 딜 소싱 제안이 나간다.
    contacts = sheet_owner.investors(
        db, db.execute(select(VcContact)).scalars().all())
    by_phone = _by_phone(contacts)

    out: Dict[int, dict] = {}
    for s in sourcing:
        if (getattr(s, "kakao_room_name", "") or "").strip():
            continue
        # 기본 문구 미리보기의 **가상 대상**에는 번호가 없다. 실제 사람만
        # 이으면 되므로 없는 것은 그냥 건너뛴다 — 없다고 터질 자리가 아니다.
        match = by_phone.get(digits(getattr(s, "phone", None)))
        if match is None or not (match.kakao_room_name or "").strip():
            continue
        out[s.id] = {
            "room": match.kakao_room_name,
            "firm": match.firm or "",
            "contact_id": match.id,
            "verified": match.room_verified,
        }
    return out


def room_for(sourcing_contact, linked: Dict[int, dict]) -> str:
    """이 사람에게 실제로 보낼 방. 자기 것이 먼저, 없으면 이어진 것."""
    own = (getattr(sourcing_contact, "kakao_room_name", "") or "").strip()
    if own:
        return own
    return (linked.get(sourcing_contact.id) or {}).get("room", "")
