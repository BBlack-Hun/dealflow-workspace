"""카카오톡 채팅방 이름 생성/정규화.

운영 중인 실제 방 이름 규칙:

    이서준 이사님 다라인베스트먼트 Deal 공유 우리브이씨 Asset
    └이름┘└직함─┘└──── 투자사 ────┘└──── 고정 접미사 ─────┘

즉 시트의 `이름`(=이름+직함)과 `투자사명` 만 있으면 방 이름을 **자동 생성**할 수 있다.
이는 Sprint 2 임포트에서 126명 × 7명분의 방 이름을 수기 입력하지 않아도 되게 해준다.

★ 방 이름은 발송 시 창 제목과 **정확히 일치**해야만 전송되므로(오발송 방지),
  공백 정규화 외의 임의 보정은 하지 않는다. 실제와 다르면 발송이 skip 될 뿐 오발송은 없다.
"""
from __future__ import annotations

import os
import re
from typing import Optional

# 조직 고정 접미사.
# 카톡방 이름 끝에 늘 붙는 문구. 회사마다 다르므로 환경변수로 뺀다.
# 저장소 기본값은 가상 이름이다(공개 저장소에 실제 상호를 두지 않는다).
# 실제 값은 .env 의 DEALFLOW_ROOM_SUFFIX 로 준다.
DEFAULT_SUFFIX = os.environ.get("DEALFLOW_ROOM_SUFFIX", "Deal 공유 우리브이씨 Asset")


def normalize_space(text: str) -> str:
    """연속 공백을 하나로 줄이고 앞뒤 공백 제거 (방 제목 비교용)."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def build_room_name(
    name: Optional[str],
    title: Optional[str],
    firm: Optional[str],
    suffix: str = DEFAULT_SUFFIX,
) -> str:
    """이름/직함/투자사 → 카톡 방 이름.

    >>> build_room_name("이서준", "이사님", "다라인베스트먼트")
    '이서준 이사님 다라인베스트먼트 Deal 공유 우리브이씨 Asset'

    직함에 '님'이 없으면 붙인다('심사역' → '심사역님') — 방 제목도 존칭 표기를 따른다.
    비어 있는 요소는 건너뛴다(공백이 겹치지 않게).
    """
    from .message_composer import honorific_title

    parts = []
    if name and name.strip():
        parts.append(name.strip())
    if title and title.strip():
        parts.append(honorific_title(title))
    if firm and firm.strip():
        parts.append(firm.strip())
    if suffix and suffix.strip():
        parts.append(suffix.strip())
    return normalize_space(" ".join(parts))


def _key(text: Optional[str]) -> str:
    """공백·괄호 차이를 무시하고 견주기 위한 형태.

    같은 회사를 `TKG VENTURES` 와 `TKG VENTURES CO., LTD.` 처럼 다르게 적는다.
    띄어쓰기만 다른 경우(`한국투자캐피탈` / `한국투자 캐피탈`)도 흔하다.
    """
    return re.sub(r"[\s(),.·\-]", "", (text or "")).lower()


def tells_people_apart(room: Optional[str], firm: Optional[str]) -> bool:
    """이 방 이름만 보고 **어느 회사 사람인지** 알 수 있는가.

    동명이인이 있을 때 방 이름에 회사가 없으면 누구의 방인지 알 수 없다.
    실제로 `김형준 이사님 Deal 공유 …` 처럼 회사가 빠진 방이 있었고, 같은
    이름의 다른 사람이 둘 더 있었다. 그대로 보내면 남의 방으로 갈 수 있다.
    """
    if not (room or "").strip():
        return False
    if not (firm or "").strip():
        return False          # 회사를 모르면 견줄 것이 없다
    return _key(firm) in _key(room)


def ambiguous_contacts(contacts) -> list:
    """이름이 겹치는데 방 이름으로 구별되지 않는 담당자.

    발송 전에 걸러야 한다 — 나가고 나서 알면 이미 남의 방이다.
    """
    by_name: dict = {}
    for c in contacts:
        by_name.setdefault(normalize_space(c.name), []).append(c)

    out = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        for c in group:
            if not tells_people_apart(c.kakao_room_name, c.firm):
                out.append(c)
    return out


def split_name_title(raw: Optional[str]) -> tuple:
    """시트의 `이름` 셀('이서준 이사님')을 (이름, 직함)으로 분리.

    시트에는 이름과 직함이 한 칸에 합쳐져 있다(SHEET_FINDINGS §2).
    마지막 토큰이 알려진 직함이면 직함으로 떼어낸다. 아니면 전체를 이름으로 둔다
    (근거 없는 추측 분리로 잘못된 방 이름을 만들지 않기 위함).
    """
    text = normalize_space(raw or "")
    if not text:
        return ("", None)
    tokens = text.split(" ")
    if len(tokens) == 1:
        return (tokens[0], None)

    last = tokens[-1]
    # '…님'으로 끝나거나 알려진 직함 어휘면 직함으로 인정.
    if last.endswith("님") or _is_known_title(last):
        return (" ".join(tokens[:-1]), last)
    return (text, None)


_TITLE_WORDS = (
    "대표", "이사", "상무", "전무", "부사장", "사장", "회장",
    "팀장", "부장", "차장", "과장", "센터장", "본부장", "실장",
    "심사역", "수석심사역", "책임심사역", "선임심사역",
    "파트너", "매니저", "위원", "연구원", "부대표",
)


def _is_known_title(token: str) -> bool:
    t = token.rstrip("님")
    return t in _TITLE_WORDS
