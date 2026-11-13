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
- **방 이름이 적힌 줄**(1 에서 못 찾은 줄) — 이름으로 찾은 결과 중 **적어 둔 이름과
  글자까지 같은 제목**이 하나면 그대로 확인됨(1 에서 결과가 늦게 읽혀 놓친 경우). 같은
  제목이 없고 찾은 방이 **빈 줄과 같은 막이(`_pick`)를 지나면 그 제목으로 방 이름을
  바꾸고** 확인됨(사용자 11/13: "찾아진 방이 있으면 그 방이름으로 카톡방이름 대체해줘").
  적어 둔 이름으로도(1) 이름+직급 · 이름으로도(2 · 3) 그 제목이 안 나왔다 = 카톡에 그
  이름의 방이 없다(방 이름을 카톡에서 바꿨거나 잘못 적었다). 막이를 못 지나면(여럿 ·
  이름만 · 동명이인인데 회사명 없음) 바꾸지 않고 `방 없음` 그대로 찾은 제목을 사유에
  적는다. 이렇게 바꾸는 자리는 **여기 한 곳**이다 — 1 의 대조(`agent_api.
  _apply_verify_result` 의 ★ 11/05)는 여전히 적어 둔 이름을 안 바꾼다(그때 사고는 대조
  결과로 덮은 것이다). 바꾼 것은 건의 사유 칸에 `방 이름을 찾은 제목으로 바꿈 (전: …)`
  으로(성공 건이라 실패로 안 센다), 수정 로그에 전→후로 남는다(`_confirm`).
  바꾸지 않는 줄: 방 나감 · 참여 안 함(`CONNECT_DONE`), 찾는 사이 사람이 방 이름을
  고친 줄(`fall_back` 이 떠 둔 이름과 다르다 — 고친 이름은 아직 대조도 안 했다).
- **확인됨을 달면 보낼 수 있는 줄로**(`_connect`) — 연결 단계를 `연결 완료` 로,
  카톡이 꺼져 있으면 켠다. 방 이름 칸만 채우면 단계가 `미착수` 그대로라 딜 소개
  대상에 안 뜬다. 수정 창의 「방 이름만 넣으면 연결 완료」와 같은 규칙이고, 방 나감 ·
  참여 안 함 줄은 그대로 둔다. 확정 못 한 줄은 단계 · 채널 모두 그대로다.
- **발송기 오류**(카톡 창을 못 잡음 등) — 줄은 건드리지 않고 오류만 건에 적는다.

## 확정 못 한 후보는 사람이 눌러 고른다 (11/13)

사용자: "자동으로 연결 안 해 줄 거면 그걸 클릭해서 카톡방에 입력 후 해당 투자사만
재검사". 찾은 제목은 사유 글에 **잘려**(셋까지 · 60자 — `_shown`) 적힌다. 그 글을 쪼개
읽지 않는다 — 발송기가 올린 제목을 건의 `room_candidates` 에 그대로 담고(`save_rooms`),
진행 화면이 확정 못 한(`failed`) 건의 사유 아래에 제목마다 단추를 세운다(`pick_view`).
누르면 그 줄 방 이름을 그 제목으로 고치고(수정 창과 같은 길 — `routers/contacts.
update_contact`) 그 한 줄만 새 [방 연결 확인] 회차로 다시 본다(`routers/jobs.pick_room`).
다시 보는 회차는 적어 둔 이름 그대로 대조한다(1) — 맞으면 확인됨이다.

  · 같은 제목이 둘 이상 걸린 제목은 단추를 안 세운다 — 넣어도 어느 방인지 못 가른다.
  · 찾을 때의 방 이름(`was`)과 지금 방 이름이 다르면 덮지 않는다 — 사람이 고쳤다.
  · 이 칸 전에 끝난 건은 후보를 모른다 — 단추가 안 선다(사유 글은 그대로다).

## 누가 찾나 — 그 계정 발송기

잡은 누른 계정(팀원 화면으로 보는 중이면 그 팀원) 것으로 서고, 그 계정의 발송기가
집어간다 — 팀 현황에서 `○○ 발송기로` 를 골라 두었으면 그 발송기다
(`deps.agent_user_id` · `users.send_via_user_id`). 찾은 제목은 그 발송기 카톡의 제목이다.
"""
from __future__ import annotations

import json
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
    # 대조했던 이름을 떠 둔다 — 결과를 받을 때 그 사이 사람이 방 이름을 고쳤는지 본다
    # (`apply_result`). 메일 제목 칸이지만 방 확인 건(카톡)에는 쓰이지 않는다.
    item.subject = item.room_name
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
    """방 이름 칸에 **저절로 넣을 제목**과, 못 넣으면 그 까닭 — 빈 줄을 채울 때도, 적어 둔
    이름을 바꿀 때도(11/13) 같은 막이다.

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
    # 사유 글에는 잘려 적히는 제목을 자르지 않고 건에 담는다 — 확정 못 하면 진행 화면이
    # 제목마다 단추를 세운다(`pick_view`). 확정한 건(`sent`)에는 안 선다.
    save_rooms(item, rooms)
    error = (body.error or "").strip()
    written = (contact.kakao_room_name or "").strip()
    if written:
        # 방 이름 칸에 적힌 이름 그대로 건에 되돌린다 — 진행 화면에 그 이름이 서고,
        # [실패 재시도] 는 다시 그 이름 대조부터 한다.
        item.room_name = written

    def done(error_text: Optional[str], note: Optional[str] = None) -> None:
        # `note` — 성공 건에 남기는 한 줄. 진행 화면의 `사유 / 시각` 칸이 그린다.
        item.status = "failed" if error_text else "sent"
        item.sent_at = None if error_text else clock.now_iso()
        item.error = error_text or note

    if not rooms and error:
        done(error)                     # 발송기 오류 — 줄은 그대로
        return
    if written:
        hits = sum(1 for r in rooms if room_name.same_title(r, written))
        if hits == 1:
            _confirm(db, item, contact)
            done(None)
            return
        lead = before or "카톡에서 적어 둔 방 이름과 같은 제목을 찾지 못했습니다"
        if not rooms:
            done(f"{lead} · 이름+직급 → 이름으로도 찾지 못했습니다")
            return
        if hits > 1:
            room_joined.set_verdict(contact, room_joined.AMBIGUOUS)
            title, why = None, "적어 둔 이름과 같은 제목의 방이 여럿입니다"
        elif (contact.connect_stage or "") in CONNECT_DONE:
            title, why = None, "방 나감 · 참여 안 함 줄이라 방 이름을 바꾸지 않습니다"
        elif not room_name.same_title(item.subject, written):
            # 찾는 사이 사람이 방 이름을 고쳤다(빈 줄이면 채웠다) — 그 이름은 아직 대조도
            # 안 했다. 옛 이름으로 찾은 결과로 덮지 않는다.
            title, why = None, "찾는 사이 방 이름이 바뀌어 바꾸지 않았습니다 — 다시 확인하세요"
        else:
            title, why = _pick(db, contact, rooms)
        if title is not None:
            _confirm(db, item, contact, title)
            done(None, f"방 이름을 찾은 제목으로 바꿈 (전: {_clip(written)})")
            return
        done(f"{lead} · 이름+직급 → 이름으로 찾은 방: {_shown(rooms)} — {why} (맞는 방이면 "
             "그 제목을 방 이름 칸에 넣고 다시 확인하세요)")
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


# ── 확정 못 한 후보 — 건에 담아 두고 진행 화면에서 골라 다시 확인 (11/13) ──────────

#: 건에 담는 찾은 방 제목 수의 상한(같은 제목을 하나로 친 뒤). 제목은 자르지 않는다.
ROOMS_MAX = 10


def save_rooms(item: SendItem, rooms: List[str]) -> None:
    """발송기가 올린 제목들을 건에 담는다 — `{"rooms", "same", "was"}`. 없으면 비운다.

    · `rooms` — 같은 제목(`title_key`)을 하나로 친 제목, 올라온 차례 그대로 · 자르지 않음.
    · `same` — 둘 이상 걸린 제목. 넣어도 어느 방인지 못 가른다(`_pick` 의 「같은 제목의
      방이 여럿」 · 다시 확인하면 `ambiguous`) — 단추를 안 세운다.
    · `was` — **찾기 시작할 때의 방 이름**. 적어 둔 이름으로 못 찾아 되돌아온 건이면 그
      이름(`fall_back` 이 `subject` 에 떠 둔 것), 처음부터 빈 줄이면 빈 글자. 누를 때
      지금 방 이름과 견줘 사람이 그 사이 고쳤으면 덮지 않는다(`routers/jobs.pick_room`).
    """
    keys: dict = {}
    same: List[str] = []
    for room in rooms:
        key = room_name.title_key(room)
        if not key:
            continue
        if key in keys:
            if keys[key] not in same:
                same.append(keys[key])
            continue
        keys[key] = room
    if not keys:
        item.room_candidates = None
        return
    item.room_candidates = json.dumps(
        {"rooms": list(keys.values())[:ROOMS_MAX], "same": same,
         "was": (item.subject or "").strip()}, ensure_ascii=False)


def _saved(item: SendItem) -> dict:
    """담아 둔 후보 — 글자가 깨졌거나 없으면 빈 묶음(진행 화면이 터지지 않게)."""
    try:
        data = json.loads(item.room_candidates or "")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def pick_view(job: Optional[SendJob], item: SendItem) -> Optional[dict]:
    """진행 화면 사유 칸 아래에 세울 후보 — 없으면 `None`.

    `{"rooms": [누를 제목], "picked": 고른 제목, "job_id": 다시 확인 회차, "note": 한 줄}`.
    투자사 [방 연결 확인](주제 없음)의 담당자 줄 건 중 **확정 못 한(`failed`)** 건만이다 —
    확인됨 건 · 대기 건 · 이 칸 전에 끝난 건(후보를 모른다)에는 안 선다. 이미 골랐으면
    단추 대신 고른 제목과 다시 확인 회차를 싣는다(`mark_picked` — 한 번에 한 후보만).
    """
    from ..routers.agent_api import VERIFY_KIND   # 순환 import 를 피해 늦게 부른다

    if (job is None or job.kind != VERIFY_KIND or job.topic is not None
            or item.contact_id is None or item.ir_company_id is not None
            or item.status != "failed" or not item.room_candidates):
        return None
    data = _saved(item)
    picked = str(data.get("picked") or "")
    if picked:
        return {"rooms": [], "picked": picked, "job_id": data.get("job_id"),
                "note": str(data.get("note") or "")}
    same = {room_name.title_key(r) for r in data.get("same") or []}
    rooms = [str(r) for r in data.get("rooms") or []
             if str(r).strip() and room_name.title_key(str(r)) not in same]
    if not rooms:
        return None
    return {"rooms": rooms, "picked": "", "job_id": None, "note": ""}


def pickable(item: SendItem) -> List[str]:
    """누를 수 있는 제목들(`pick_view` 의 `rooms`) — 고른 뒤 · 확정한 건이면 빈 목록."""
    view = pick_view(item.job, item)
    return view["rooms"] if view else []


def started_from(item: SendItem) -> str:
    """찾기 시작할 때의 방 이름(`save_rooms` 의 `was`)."""
    return str(_saved(item).get("was") or "")


def mark_picked(item: SendItem, title: str, job_id: Optional[int], note: str = "") -> None:
    """고른 제목과 다시 확인 회차를 건에 적는다 — 그 뒤로는 단추 대신 그 회차 링크가 선다."""
    data = _saved(item)
    data.update({"picked": title, "job_id": job_id, "note": note})
    item.room_candidates = json.dumps(data, ensure_ascii=False)


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
    제목을 방 이름으로 넣는다(빈 줄은 채우고, 적힌 줄은 바꾼다). 수정 로그는 **찾기를 건
    계정** 이름으로 — 적어 둔 이름을 바꿀 때는 자기 줄이라도 전→후를 남긴다
    (`edit_log.always`). 사람이 적은 값을 기계가 덮은 것이라 나중에 물을 곳이 있어야 한다.

    이 길에는 요청 문맥이 없다(발송기가 부른다). 딜 소싱의 저절로 확정과 같은 방식이다
    (`sourcing_rooms._confirm_single`). 확인 값 · 참여여부는 한 자리를 지난다
    (`room_joined.set_verdict`).
    """
    db.flush()          # 건 상태는 로그 밖에서 먼저 내보낸다
    token = edit_log.begin(item.job.user_id, "POST", f"/agent/items/{item.id}/result")
    try:
        if title is not None:
            if (contact.kakao_room_name or "").strip():
                edit_log.always(contact)
            contact.kakao_room_name = title
        room_joined.set_verdict(contact, room_joined.VERIFIED)
        _connect(contact)
        db.flush()
    finally:
        edit_log.end(token)
    if title is not None:
        item.room_name = title
