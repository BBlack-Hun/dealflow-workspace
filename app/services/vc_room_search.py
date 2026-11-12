"""투자사 담당자 [방 연결 확인]의 **이름으로 찾기** — 적어 둔 방 이름 → 이름+직급 → 이름.

## 왜 필요했나

[방 연결 확인]은 **적어 둔 카톡방 이름**만 대조했다(`routers/agent_api._exact_verdict`,
11/05). 방 이름이 빈 줄은 잡에 싣지도 않았다 — 명단 전체가 방 이름이 없는 계정
(운영: 팀원 계정 46줄 중 0줄)은 누를 때마다 `확인할 카톡방 이름이 등록된 담당자가
없습니다` 로 끝나고 잡이 서지 않았다. 사용자(11/12): "카톡방 이름(제일 우선) >>>
이름 직급 >>> 이름 이런 식으로 체크를 해야 할 거 같음".

## 순서

1. **적어 둔 카톡방 이름** — 지금까지와 같다. 글자까지 같은 제목만 확인됨.
2. **이름+직급** — 1 이 `방 없음` 이거나 방 이름이 빈 줄.
3. **이름** — 2 로 하나도 못 찾았을 때.

2 → 3 은 발송기가 이미 하는 일이다(`agent/main.py: process_verify_job` — `query` 로
못 찾으면 `name` 으로 한 번 더). 딜 소싱 [방 후보 찾기]가 같은 길을 탄다
(`sourcing_rooms.search_terms` · `query_of`). 그래서 **발송기는 안 고친다** — 건에
실을 검색어만 서버가 고른다(`search_terms`).

1 → 2 는 발송기가 못 잇는다(`exact` 건은 이름으로 다시 찾지 않는다 — 그래야 앞 건의
결과를 이 건 것으로 읽지 않는다). 그래서 **서버가 같은 건을 한 번 더 내준다**
(`fall_back`): 적어 둔 이름으로 못 찾았다는 결과가 오면 그 건을 대기로 되돌리며 방
이름 칸을 비운다 — 빈 방 이름이 곧 「이름으로 찾는 건」이라는 표시다
(`is_search`, 스타트업 · IR 기업 줄의 찾기 건과 같은 약속). 발송기가 회분을 끝내면
남은 대기 건 때문에 회차가 큐로 돌아가고(`agent_api._settle`) 다음 폴링에 그 건만
이름으로 찾는다.

## 찾은 방을 어떻게 받나

- **방 이름이 빈 줄** — 찾은 방(같은 제목을 하나로 친)이 **하나뿐이고 이 분 방이
  분명하면** 그 제목을 방 이름으로 넣고 확인됨(`_pick`). 딜 소싱 [방 후보 찾기]의
  「하나뿐이면 확정」(사용자 결정 2026-11-10)과 같고, 투자사 줄이라 막이를 더 건다:
    · 제목에 **이름+직급**이 들었거나 **회사명**이 들었다 — 이름만 든 방은 같은
      성함의 다른 분 방일 수 있다(이름으로만 찾은 결과가 여기 걸린다).
    · 팀 명단에 **같은 성함의 다른 회사 분**이 있으면 회사명이 든 제목만.
    · 같은 제목의 방이 여럿이면 어느 방인지 못 가른다.
  둘 이상이거나 분명하지 않으면 **넣지 않고** 찾은 제목을 사유에 적는다 — 맞는 방이면
  그 제목을 방 이름 칸에 넣고 다시 확인하면 된다(1 에서 확인됨).
- **방 이름이 적힌 줄**(1 에서 못 찾은 줄) — 적어 둔 이름은 **바꾸지 않는다**
  (`agent_api._apply_verify_result` 의 ★ 11/05 — 사람이 카톡에서 복사해 넣은 이름이
  남의 방 이름으로 바뀐 사고). 이름으로 찾은 결과 중 **적어 둔 이름과 글자까지 같은
  제목**이 하나면 확인됨(1 에서 결과가 늦게 읽혀 놓친 경우), 아니면 `방 없음` 그대로
  두고 찾은 제목을 사유에 적는다.
- **확인됨을 달면 보낼 수 있는 줄로**(`_connect`) — 연결 단계를 `연결 완료` 로,
  카톡이 꺼져 있으면 켠다. 방 이름 칸만 채우면 단계가 `미착수` 그대로라 딜 소개
  대상에 안 뜬다. 수정 창의 「방 이름만 넣으면 연결 완료」와 같은 규칙이고, 방 나감 ·
  참여 안 함 줄은 그대로 둔다. 확정 못 한 줄은 단계 · 채널 모두 그대로다.
- **발송기 오류**(카톡 창을 못 잡음 등) — 줄은 건드리지 않고 오류만 건에 적는다.

## 누가 찾나 — 그 계정 발송기

잡은 누른 계정(팀원 화면으로 보는 중이면 그 팀원) 것으로 서고, 그 계정의 발송기가
집어간다 — 팀 현황에서 `○○ 발송기로` 를 골라 두었으면 그 발송기다
(`deps.agent_user_id` · `users.send_via_user_id`). 찾은 제목은 그 발송기 카톡의 제목이다.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .. import clock
from ..models import SendItem, SendJob, VcContact
from . import edit_log, room_joined, room_name, sheet_owner
from .sheet_import import CONNECT_DONE, STAGE_CONNECTED


def _squash(text: Optional[str]) -> str:
    """공백을 다 떼고 한글 조합 형태를 맞춘 글자 — 제목 속에 이름 · 직급이 들었나 견줄 때."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text or ""))


# ── 누구를 찾나 ─────────────────────────────────────────────────────────────

def _kakao_or_unset(contact: VcContact) -> bool:
    """카톡으로 받는 줄이거나, 받는 길을 **아직 안 정한** 줄(채널 칸이 하나도 안 켜짐).

    시트 가져오기는 `초대 완료` 줄에만 카톡을 켠다(`sheet_import`) — 그래서 방 이름 ·
    채널이 다 빈 명단이 생긴다(운영: 팀원 계정 46줄 중 31줄). 그 줄도 찾는다. 메일로만 ·
    문자로만(`sheet_owner.sms_only`) 받는다고 정해 둔 줄은 카톡방이 없는 게 정상이다.
    """
    return bool(contact.channel_kakao) or not (contact.channel_email or contact.channel_sms)


def searchable(contact: VcContact, hidden: Set[str]) -> bool:
    """이름으로 찾을 줄인가 — **카톡으로 받는(또는 아직 안 정한) 투자사 담당자**, 이름이 있다.

    스타트업 명단 줄은 아니다 — 그쪽은 회사명으로 찾는다(`startup_room_pick`). 방을
    나갔다 · 참여 안 함 으로 적힌 줄도 아니다 — 방을 찾아도 확인됨을 달지 않는다
    (`room_joined` 규칙 2). 메일로만 · 문자로만 받는 줄도 아니다(`_kakao_or_unset`).
    """
    return (bool((contact.name or "").strip())
            and _kakao_or_unset(contact)
            and (contact.connect_stage or "") not in CONNECT_DONE
            and sheet_owner.is_investor(contact, hidden))


def is_search(job: Optional[SendJob], item: SendItem) -> bool:
    """이 방 확인 건이 **투자사 담당자를 이름으로 찾는** 건인가.

    [방 연결 확인] 잡(주제 없음)의 담당자 줄 건 중 **방 이름이 빈** 건이다 — 대조할
    이름이 실린 건은 지금까지처럼 그 이름 그대로 대조한다(`_exact_verdict`). 다른
    주제의 잡(스타트업 찾기 · 딜 소싱 · 보내는 계정)은 저마다의 길이 있다.
    """
    return (job is not None and job.topic is None and item.contact is not None
            and item.ir_company_id is None and not (item.room_name or "").strip())


def search_terms(contact: VcContact) -> dict:
    """발송기에 실을 검색어 — 이름+직급, 못 찾으면 이름. 여럿이면 회사로 좁힌다.

    검색어 짓기는 딜 소싱 [방 후보 찾기]와 **같은 함수**다(`sourcing_rooms.query_of`).
    다른 점 하나 — `firm` 을 **싣는다.** 딜 소싱은 회사 이름이 든 방(= 딜소개 방)을
    피하려고 안 싣지만, 여기서 찾는 방이 바로 그 딜소개 방이다. 발송기는 여럿이 걸리면
    회사명 앞 글자가 든 방 하나로 줄인다(`agent/main.py: process_verify_job`).
    """
    from .sourcing_rooms import query_of   # 그쪽이 VcContact 도 같은 칸으로 읽는다

    return {"query": query_of(contact), "name": (contact.name or "").strip(),
            "firm": contact.firm or ""}


# ── 적어 둔 이름으로 못 찾았다 → 같은 건을 이름으로 한 번 더 ─────────────────────

#: 이름으로 다시 찾는 동안 건에 서는 말 — 진행 화면이 대기 건에도 사유 칸을 그린다.
#: 뒤에 적어 둔 이름으로 못 찾은 까닭을 붙여 두었다가 결과를 받을 때 떼어 쓴다.
SEARCHING = "적어 둔 방 이름으로 못 찾아 이름+직급 → 이름으로 다시 찾는 중 · "


def fall_back(item: SendItem) -> bool:
    """적어 둔 방 이름으로 **못 찾은** 건을 이름으로 찾는 건으로 되돌린다. 되돌렸으면 `True`.

    부르는 쪽(`agent_api._apply_verify_result`)이 판정 · 사유를 다 적은 **뒤**에
    부른다 — 그 사유는 남겨 두었다가 이름으로도 못 찾으면 앞에 붙인다(`apply_result`).
    한 건은 한 번만 되돌아간다(되돌린 건은 방 이름이 비어 `is_search` 쪽으로 간다).
    """
    job = item.job
    contact = item.contact
    if job is None or job.topic is not None or contact is None or item.ir_company_id:
        return False
    db = object_session(item)
    if not searchable(contact, sheet_owner.hidden_labels(db)):
        return False
    item.room_name = ""
    item.status = "pending"
    item.sent_at = None
    item.error = SEARCHING + (item.error or "")
    return True


# ── 결과 받기 ────────────────────────────────────────────────────────────────

def _clip(title: str) -> str:
    title = " ".join(title.split())
    return title if len(title) <= 60 else title[:60] + "…"


def _shown(rooms: List[str]) -> str:
    distinct = list(dict.fromkeys(rooms))
    out = ", ".join(f"'{_clip(r)}'" for r in distinct[:3])
    return out + (f" 외 {len(distinct) - 3}개" if len(distinct) > 3 else "")


def _namesake(db: Session, contact: VcContact) -> bool:
    """팀 명단에 **같은 성함의 다른 회사 분**이 있는가(회사를 모르는 줄도 다른 분으로 본다)."""
    name = room_name.normalize_space(contact.name or "")
    mine = room_name._key(contact.firm)
    rows = db.execute(
        select(VcContact.name, VcContact.firm).where(VcContact.id != contact.id,
                                                     VcContact.name.contains(name))
    ).all()
    return any(room_name.normalize_space(n or "") == name
               and (not mine or room_name._key(f) != mine) for n, f in rows)


def _pick(db: Session, contact: VcContact, rooms: List[str]) -> Tuple[Optional[str], str]:
    """방 이름이 빈 줄에 **저절로 넣을 제목**과, 못 넣으면 그 까닭.

    모듈 머리말 「찾은 방을 어떻게 받나」의 막이 그대로다. `(제목, "")` 또는 `(None, 까닭)`.
    """
    if len({room_name.title_key(r) for r in rooms}) > 1:
        return None, "찾은 방이 여럿입니다"
    if len(rooms) > 1:
        return None, "같은 제목의 방이 여럿입니다"
    title = rooms[0]
    name = _squash(contact.name)
    if not name or name not in _squash(title):
        return None, "제목에 이 분 이름이 없습니다"
    by_firm = room_name.tells_people_apart(title, contact.firm)
    if _namesake(db, contact):
        return ((title, "") if by_firm else
                (None, "같은 성함의 다른 회사 분이 있어 회사명이 든 제목만 넣습니다"))
    rank = (contact.title or "").strip()
    by_rank = bool(rank) and _squash(f"{contact.name}{rank}") in _squash(title)
    return ((title, "") if (by_rank or by_firm) else
            (None, "이름만 든 제목이라(이름+직급 · 회사명 없음) 이 분 방인지 분명하지 않습니다"))


def apply_result(item: SendItem, body) -> None:
    """이름으로 찾은 결과(`is_search` 건) — 모듈 머리말 「찾은 방을 어떻게 받나」."""
    contact = item.contact
    db = object_session(item)
    # 적어 둔 이름으로 못 찾은 까닭(`fall_back`) — 방 이름이 빈 줄의 건에는 없다.
    before = (item.error or "").removeprefix(SEARCHING).strip()
    # 발송기가 올린 그대로다 — 같은 제목이 두 번이면 같은 제목의 방이 둘이다.
    rooms = [str(r).strip() for r in (body.candidates or []) if str(r).strip()]
    found = (body.found_room or "").strip()
    if found and not any(room_name.same_title(found, r) for r in rooms):
        rooms.insert(0, found)
    error = (body.error or "").strip()
    written = (contact.kakao_room_name or "").strip()
    if written:
        # 방 이름 칸에 적힌 이름 그대로 건에 되돌린다 — 진행 화면에 그 이름이 서고,
        # [실패 재시도] 는 다시 그 이름 대조부터 한다.
        item.room_name = written

    def done(error_text: Optional[str]) -> None:
        item.status = "failed" if error_text else "sent"
        item.sent_at = None if error_text else clock.now_iso()
        item.error = error_text

    if not rooms and error:
        done(error)                     # 발송기 오류 — 줄은 그대로
        return
    if written:
        hits = sum(1 for r in rooms if room_name.same_title(r, written))
        if hits == 1:
            _confirm(db, item, contact)
            done(None)
            return
        if hits > 1:
            room_joined.set_verdict(contact, room_joined.AMBIGUOUS)
        lead = before or "카톡에서 적어 둔 방 이름과 같은 제목을 찾지 못했습니다"
        done(f"{lead} · 이름+직급 → 이름으로 찾은 방: {_shown(rooms)} — 맞는 방이면 그 "
             "제목을 방 이름 칸에 넣고 다시 확인하세요" if rooms
             else f"{lead} · 이름+직급 → 이름으로도 찾지 못했습니다")
        return
    if not rooms:
        done("카톡에서 이 분의 방을 찾지 못했습니다 (이름+직급 → 이름으로 찾음)")
        return
    title, why = _pick(db, contact, rooms)
    if title is None:
        done(f"{why} — 찾은 방: {_shown(rooms)} (맞는 방이면 그 제목을 방 이름 칸에 넣고 "
             "다시 확인하세요)")
        return
    _confirm(db, item, contact, title)
    done(None)


def _connect(contact: VcContact) -> None:
    """찾기로 방을 확정한 줄을 **보낼 수 있는 줄**로 — 연결 단계 `연결 완료` · 카톡 켬.

    방 이름만 넣고 확인됨을 달면 단계는 `미착수`(또는 진행 중) 그대로라
    `sheet_owner.can_send_to` 가 거짓 — 딜 소개 대상에 안 뜬다(운영: 팀원 계정 46줄이
    전부 방 이름 빈칸 · 미착수). 수정 창이 「단계를 고르지 않고 방 이름만 넣으면
    `연결 완료`」로 두는 것(`routers/contacts` 의 연결 단계 맞추기)과 같은 규칙이다.

    방 나감 · 참여 안 함 줄은 그대로 둔다 — `room_joined.set_verdict` 가 그 줄에
    확인됨을 달지 않는 것과 같은 판정이다. 방을 찾았다 = 카톡으로 받는다 — 카톡이
    꺼져 있으면 켠다(채널을 아직 안 정한 줄, `_kakao_or_unset`).
    """
    stage = contact.connect_stage or ""
    if stage in CONNECT_DONE:
        return
    if stage != STAGE_CONNECTED:
        contact.connect_stage = STAGE_CONNECTED
    if not contact.channel_kakao:
        contact.channel_kakao = 1


def _confirm(db: Session, item: SendItem, contact: VcContact,
             title: Optional[str] = None) -> None:
    """찾기로 이 분 방을 확정 — 확인됨 · 연결 완료(`_connect`). `title` 이 있으면 그
    제목을 방 이름으로 넣는다(방 이름이 빈 줄). 수정 로그는 **찾기를 건 계정** 이름으로.

    이 길에는 요청 문맥이 없다(발송기가 부른다). 딜 소싱의 저절로 확정과 같은 방식이다
    (`sourcing_rooms._confirm_single`). 확인 값 · 참여여부는 한 자리를 지난다
    (`room_joined.set_verdict`).
    """
    db.flush()          # 건 상태는 로그 밖에서 먼저 내보낸다
    token = edit_log.begin(item.job.user_id, "POST", f"/agent/items/{item.id}/result")
    try:
        if title is not None:
            contact.kakao_room_name = title
        room_joined.set_verdict(contact, room_joined.VERIFIED)
        _connect(contact)
        db.flush()
    finally:
        edit_log.end(token)
    if title is not None:
        item.room_name = title
