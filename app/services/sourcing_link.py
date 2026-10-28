"""딜 소싱 명단 ↔ 투자사 관리 현황 — **카톡방은 이어받지 않는다**(모든 갈래).

딜 소싱 줄의 방은 **보내는 사람 카톡의 딜 소싱 방**이다. 휴대폰 번호로 찾은
투자사 줄의 방은 그 줄을 맡은 팀원의 **딜소개 방**이라, 이어받으면 딜 소싱
제안 · 리마인드가 남의 딜소개 방(또는 보내는 사람 카톡에 없는 제목)으로 간다
(사용자 원문: "딜소싱에 있다는건 다른 사람 담당자라도 카톡방에 초대 되어있다는
뜻"). 자기 방 이름이 없는 줄은 **방 없음** 이고, 딜 소싱 화면의 [방 후보 찾기]로
보내는 사람 카톡에서 찾아 확정한다(`services/sourcing_rooms.py`).

처음엔 시리즈 A 갈래만 막았다(PR #284). M&A · 구주·후속 · 대표 · 개인참여도
같은 규칙으로 막는다 — 사용자 결정 2026-10-28.

번호 비교(`digits` · `MIN_DIGITS`)는 투자사 줄과 **잇는** 일(`sourcing_sync`)과
딜소개 방 알아보기(`sourcing_rooms.deal_rooms`)가 쓴다.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

from sqlalchemy.orm import Session

#: 휴대폰으로 인정할 최소 자릿수. `010-1234-5678` → 11자리.
#: 짧은 값(내선번호 `1234`)끼리 우연히 맞아 엉뚱한 사람과 이어지는 것을 막는다.
MIN_DIGITS = 10


def digits(phone: Optional[str]) -> str:
    return re.sub(r"\D", "", phone or "")


def linked_rooms(db: Session, sourcing) -> Dict[int, dict]:
    """소싱 대상 → 투자사 명단에서 이어받을 방. **늘 비어 있다** — 어느 갈래도
    이어받지 않는다(모듈 머리말).

    발송 · 미리보기 · 리마인드 · `방 없음` 표시가 모두 이 함수를 지나므로, 이어받기
    규칙은 여기 한 곳이다.
    """
    # shortcut: 부르는 쪽의 '이어받은 방' 갈래(🔗 투자사 명단 · room_from)는 이제 안 탄다, 되돌릴 일이 없으면 걷어낸다
    return {}


def room_for(sourcing_contact, linked: Dict[int, dict]) -> str:
    """이 사람에게 실제로 보낼 방. 자기 것이 먼저, 없으면 이어진 것."""
    own = (getattr(sourcing_contact, "kakao_room_name", "") or "").strip()
    if own:
        return own
    return (linked.get(sourcing_contact.id) or {}).get("room", "")
