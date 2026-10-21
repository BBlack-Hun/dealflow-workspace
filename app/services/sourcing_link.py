"""딜 소싱 명단 ↔ 투자사 관리 현황 잇기 — **카톡방 이어받기**.

**`시리즈 A 이상 딜 소싱 참여 심사역` 갈래는 이어받지 않는다**(`linked_rooms`
안의 ★ 주석). 그 갈래의 방은 보내는 사람 카톡의 딜 소싱 방이라, 자기 방 이름이
없으면 딜 소싱 화면의 [방 후보 찾기]로 채운다(`services/sourcing_rooms.py`).
아래는 나머지 갈래의 이야기다.

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

    같은 분이 **두 팀원 몫으로** 한 줄씩 있는 것은 겹침이 아니다(투자사 관리 현황
    업로드의 `따로 만들기` — `sheet_import.apply_sheet_a`). 그때는 이어 줄 방이
    갈리지 않으면(한쪽만 방이 있거나 두 방 이름이 같으면) 방이 있는 줄을 쓴다.
    방 이름이 서로 다르면 여전히 어느 쪽인지 모르므로 뺀다.
    """
    seen: Dict[str, VcContact] = {}
    clashed = set()
    for c in contacts:
        key = digits(c.phone)
        if len(key) < MIN_DIGITS:
            continue
        if key in seen:
            prev = seen[key]
            if _same_room(prev, c):
                # 방이 있는 쪽을 남긴다 — 이어 주는 것이 방이다.
                if not (prev.kakao_room_name or "").strip():
                    seen[key] = c
                continue
            clashed.add(key)
        seen[key] = c
    for key in clashed:
        seen.pop(key, None)
    return seen


def _key(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _same_room(a: VcContact, b: VcContact) -> bool:
    """같은 분의 두 팀원 몫인데 이어 줄 방이 갈리지 않는가."""
    if a.user_id == b.user_id:
        return False      # 한 팀원 명단 안의 겹침은 예전처럼 겹침이다
    if (_key(a.name), _key(a.firm)) != (_key(b.name), _key(b.firm)):
        return False
    ra, rb = _key(a.kakao_room_name), _key(b.kakao_room_name)
    return not ra or not rb or ra == rb


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
    # 이어받지 않는 갈래 — 아래 ★ 주석.
    from .sourcing_sync import is_series_a  # noqa: PLC0415 — 그쪽이 이 파일을 부른다

    out: Dict[int, dict] = {}
    for s in sourcing:
        if (getattr(s, "kakao_room_name", "") or "").strip():
            continue
        # ★ **시리즈 A 갈래는 투자사 방을 이어받지 않는다.**
        #
        # 사용자가 짚었다 — "딜소싱에 있다는건 다른 사람 담당자라도 카톡방에
        # 초대 되어있다는 뜻". 그 갈래 사람의 방은 **보내는 사람 카톡의 딜 소싱
        # 방**이고, 번호로 찾은 투자사 줄의 방은 그 줄을 맡은 팀원의 **딜소개
        # 방**이다. 이어받으면 소싱 리마인드가 남의 딜소개 방(또는 보내는 사람
        # 카톡에 없는 제목)으로 간다. 그 갈래는 자기 방 이름이 없으면 **방 없음**
        # 이고, 딜 소싱 화면의 [방 후보 찾기]로 채운다(`services/sourcing_rooms.py`).
        #
        # 다른 갈래는 **예전 그대로 둔다** — 사용자가 짚은 갈래가 아니고, 그
        # 갈래들은 지금(운영) 자기 방이 한 줄도 없어 이어받기가 유일한 길이다.
        # 같은 이유로 막을지는 사용자가 정할 일이다(PR #284 본문).
        # (투자사 관리 현황과 잇는 갈래가 셋이 된 뒤에도 — M&A · 구주·후속은 예전처럼
        # 자기 방이 없으면 투자사 방을 이어받는다. 사용자 결정 2026-10-21.)
        if is_series_a(s):
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
