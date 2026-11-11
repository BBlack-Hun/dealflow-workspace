"""스타트업 명단 줄의 카톡방 **후보 찾기 · 확정** — 좌측 [스타트업] → [방 매칭].

## 막혀 있던 것

스타트업 안내 카톡(`services/startup_outreach.py`)은 **카톡에서 확인된 방**에만
나간다. 그런데 운영의 스타트업 명단 줄에는 방 이름이 든 곳이 **하나도
없었다** — 채우는 길이 수정창에 한 곳씩 옮겨 적고 [방 연결 확인] 을 거는
것뿐이었다. 팀원마다 수십 곳이다.

## 무엇을 하나

1. **[방 후보 찾기]** — 내 스타트업 줄 중 방이 아직 확인 안 된 곳을 **회사명으로**
   카톡에서 찾는다. 이미 있는 방 확인 잡(`verify_room`)에 `ROOM_SEARCH_TOPIC`
   을 달아 세운다(`routers/startup_outreach.search_rooms`). **발송기는 안
   고친다** — 발송기는 줄마다 실린 `query`·`target` 만 보고 움직이고, 월간
   발송 쪽 맞추기가 이미 같은 길을 탄다(`room_match` 머리말).
2. 찾은 제목은 **후보로만** 담는다(`VcContact.room_candidates`). 하나뿐이어도
   방 이름에 안 넣는다 — 회사명이 든 방이 꼭 그 대표와의 방인 것은 아니다.
   투자사 방은 담을 때도, 화면에 세울 때도 뺀다(`room_match.drop_investor_rooms`).
3. **[이 방으로 확정]** — 사람이 후보를 누르면 방 이름이 그 제목이 되고
   `확인됨` 이 된다(`confirm`). 카톡 창에서 읽어 온 글자 그대로라 [방 연결
   확인] 을 한 번 더 거칠 까닭이 없다. 확인 값은 `room_joined` 를 지나 적는다
   — `카톡 연결 여부` 가 `O` 로 따라 맞는다.
4. **직접 적기** — 후보가 없으면 카톡에서 복사해 적는다. 사람이 적은 글자라
   `확인 안 됨` 이고 [방 연결 확인] 을 거쳐야 보낸다. 적는 길은 수정창과
   **같은 길**이다(`PATCH /api/contacts/{id}` → `room_joined.after_edit`).

## 단추는 하나다 — [카톡방 찾기·확인] (11/11)

명단 툴바에 [방 연결 확인] · [방 후보 찾기] · [방 매칭] 셋이 나란히 서 있었다.
사용자 말: *"같은 기능 같은데 하나로 통합해 줘."* 셋이 하는 일은 결국 「이 줄의
방을 맞춘다」 하나라서, **한 번 누르면 잡 하나**가 줄마다 할 일을 고른다(`plan`).

  · 방 이름이 **적혀 있고 아직 확인 전**(`확인 안 됨`) — 그 이름 **그대로** 카톡에서
    대조한다([방 연결 확인] 이 하던 일 — 글자까지 같은 제목만 `확인됨`).
  · 방 이름이 **없거나**, 적어 둔 이름으로 이미 못 찾았다(`카톡에서 못 찾음` ·
    `같은 이름이 여럿`) — **회사명으로** 찾아 후보로만 담는다([방 후보 찾기]).
  · 이미 확인된 줄 · 제외 줄은 싣지 않는다.

잡은 지금까지의 후보 찾기 잡 그대로다(`verify_room` + `ROOM_SEARCH_TOPIC`) — 두
갈래를 가르는 것은 **건에 실린 방 이름**이다(`routers/agent_api._company_row`).
발송기는 줄마다 실린 `exact` · `query` · `target` 만 보고 움직이므로 **판을 안
올린다.** 후보를 고르는 자리 · 직접 적기 · 확정은 [방 매칭] 화면 **한 곳**이다.

## 판정을 새로 적지 않는다  ★

  · 내 줄 — `startup_outreach.my_rows` (안내 카톡이 고르는 그 명단)
  · 방을 찾을 줄 — `startup_outreach.group_of` 가 `no_room` 인 줄. 안내 카톡
    화면이 `방 확인 전` 으로 접어 두는 **그 줄들**이다. 갈리면 찾아서 확정한
    줄이 안내 카톡에서 여전히 못 고르는 줄로 남거나, 거기서 접힌 줄을 여기서
    못 찾는다.
  · 검색어 · 투자사 방 거르기 · 후보를 담는 모양 — `room_match`
  · 확인 값 · 참여여부 — `room_joined`

## 투자사 줄은 그대로다

투자사 담당자의 방 확인(`routers/contacts.verify_rooms`)은 이 파일을 지나지
않는다. 그 잡에는 `ROOM_SEARCH_TOPIC` 이 없어서 발송기가 이름+직함으로
대조하고, 결과가 하나면 서버가 그 제목을 방 이름으로 넣는다 — 지금까지와 같다
(`routers/agent_api._apply_verify_result`).
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from ..models import User, VcContact
from . import room_joined, room_match, startup_outreach

#: 줄의 상태 — 화면이 이 말을 그대로 적는다(사용자가 정한 말이다).
CONFIRMED = "confirmed"
PICKS = "picks"
NO_PICKS = "no_picks"
NEVER = "never"

STATE_LABELS = {
    CONFIRMED: "확정됨",
    PICKS: "후보 {n}개",
    NO_PICKS: "후보 없음",
    NEVER: "아직 안 찾아봄",
}


class NotPickable(ValueError):
    """확정할 수 없는 제목. 까닭이 그대로 화면에 간다."""


# ── 누구를 찾나 ─────────────────────────────────────────────────────────────

#: [카톡방 찾기·확인] 이 줄마다 고르는 일 — 적어 둔 이름 그대로 대조 / 회사명으로 찾기.
EXACT = "exact"
SEARCH = "search"


def task_of(contact: VcContact) -> str:
    """[카톡방 찾기·확인] 이 이 줄에서 할 일 — `exact` · `search` · 빈 글자(할 일 없음).

    방이 아직 확인 안 된 줄(안내 카톡의 `방 확인 전`)만 본다. 그중

      · 방 이름이 적혀 있고 **아직 확인 전**이면 그 이름 그대로 대조한다(`exact`).
      · 그 밖(이름이 없다 · 적어 둔 이름으로 못 찾았다 · 여럿이다)은 **회사명으로**
        찾는다(`search`). 회사명이 빈 줄은 무엇으로 찾을지가 없다 — 성함으로 찾으면
        그 이름이 든 다른 방이 걸린다(`room_match.company_name`).

    못 찾은 이름을 한 번 더 대조해도 같은 답이 나온다. 그 줄은 진짜 제목을 알아야
    하므로 찾기로 간다 — 적어 둔 이름은 그대로 둔다(후보만 담는다).
    """
    if startup_outreach.group_of(contact) != startup_outreach.NO_ROOM:
        return ""
    if (contact.kakao_room_name or "").strip() and \
            startup_outreach.room_state(contact) == room_joined.UNVERIFIED:
        return EXACT
    return SEARCH if room_match.search_query(contact) else ""


def searchable(contact: VcContact) -> bool:
    """[카톡방 찾기·확인] 을 걸 줄인가 — 할 일이 있다(`task_of`)."""
    return bool(task_of(contact))


def targets(db: Session, user: User,
            ids: Optional[Iterable[int]] = None) -> List[VcContact]:
    """걸 줄 — **내 스타트업 줄**(`startup_outreach.my_rows`) 중 `searchable`.

    `ids` 를 주면 그 안에서만 고른다(스타트업 화면에 보이는 줄 · 수정창의 한
    줄). 남의 줄 · 감춘 줄 · 투자사 줄 · 이미 확인된 줄은 **id 로 찔러도**
    안 들어간다 — 고르는 판정이 이 함수 하나다.
    """
    rows = [c for c in startup_outreach.my_rows(db, user) if searchable(c)]
    if ids is None:
        return rows
    wanted = set(ids)
    return [c for c in rows if c.id in wanted]


def plan(db: Session, user: User, ids: Optional[Iterable[int]] = None):
    """`(대조할 줄, 회사명으로 찾을 줄, 동명이인이라 못 싣는 줄)` — 잡 하나에 실을 것.

    대조할 줄은 [방 연결 확인] 과 같은 막이를 지난다: 같은 성함의 다른 줄과 방
    이름까지 같으면 글자로는 어느 방인지 못 가른다(`room_name.ambiguous_contacts` —
    `routers/contacts.verify_rooms` 와 같은 판정, 견주는 것도 내 줄 전부).
    """
    from sqlalchemy import select

    from .room_name import ambiguous_contacts

    picked = targets(db, user, ids)
    exact = [c for c in picked if task_of(c) == EXACT]
    search = [c for c in picked if task_of(c) == SEARCH]
    if not exact:
        return exact, search, []
    everyone = db.execute(
        select(VcContact).where(VcContact.user_id == user.id)).scalars().all()
    unclear = {c.id for c in ambiguous_contacts(everyone)}
    return ([c for c in exact if c.id not in unclear], search,
            [c for c in exact if c.id in unclear])


def queue(db: Session, user: User, ids: Optional[Iterable[int]] = None) -> dict:
    """[카톡방 찾기·확인] — 잡 **하나**를 세운다. 커밋까지 한다.

    잡은 후보 찾기 잡 그대로다(`verify_room` + `ROOM_SEARCH_TOPIC`, `queued` —
    아무것도 안 나가고 읽기만 한다). 대조할 건에는 적어 둔 방 이름을 싣고, 찾을
    건은 **빈 글자**다(모르는 값을 지어 넣지 않는다). 그 한 칸이 발송기에 무엇을
    줄지와 결과를 어디에 적을지를 가른다(`routers/agent_api._company_row`).
    문구는 늘 비운다 — 아주 낡은 발송기가 이 잡을 발송으로 오해해도 보낼 것이 없다.

    동명이인이라 못 싣는 줄은 `같은 이름이 여럿` 으로 적는다([방 연결 확인] 과
    같다 — 다음에 누르면 회사명으로 찾는다). 실을 줄이 없으면 `job` 이 `None` 이다.
    """
    from ..models import ROOM_SEARCH_TOPIC, SendItem, SendJob
    from ..routers.agent_api import VERIFY_KIND

    exact, search, unclear = plan(db, user, ids)
    for contact in unclear:
        room_joined.set_verdict(contact, room_joined.AMBIGUOUS)
    out = {"job": None, "exact": len(exact), "search": len(search),
           "conflicts": [startup_outreach.who(c) for c in unclear]}
    if not exact and not search:
        db.commit()
        return out
    job = SendJob(user_id=user.id, kind=VERIFY_KIND, topic=ROOM_SEARCH_TOPIC,
                  status="queued", total=len(exact) + len(search), sent=0, failed=0)
    db.add(job)
    db.flush()
    named = {c.id for c in exact}
    for contact in exact + search:
        db.add(SendItem(job_id=job.id, contact_id=contact.id,
                        room_name=(contact.kakao_room_name or "") if contact.id in named else "",
                        message="", status="pending"))
    db.commit()
    out["job"] = job
    return out


def pick_counts(db: Session, contacts: Iterable[VcContact]) -> dict:
    """`{contact_id: 고를 수 있는 후보 수}` — 화면이 줄마다 `후보 N개 — 고르기` 를 적는다.

    세는 것은 고르는 화면과 **같은 함수**다(`picks` — 투자사 방은 뺀다).
    """
    known = room_match.investor_rooms(db)
    return {c.id: len(picks(c, known)[0]) for c in contacts}


# ── 후보 ────────────────────────────────────────────────────────────────────

def picks(contact: VcContact, known: room_match.InvestorRooms):
    """고를 수 있는 후보 `(제목들, 투자사 방이라 뺀 수)`.

    **담긴 것을 한 번 더 거른다.** 담을 때 이미 거르지만(`agent_api.
    _apply_company_candidates`), 그 뒤에 투자사 명단에 방 이름이 들어오면 그
    방은 지금부터 투자사 방이다. 화면과 확정이 **이 한 함수**를 지난다 —
    화면에 안 선 제목이 주소로 확정되는 일이 없게(`room_match.rows` 와 같은
    규칙).
    """
    found = room_match.candidates(contact)
    shown, hidden = room_match.drop_investor_rooms(
        found["rooms"], room_match.company_name(contact), known)
    return shown, found["dropped"] + len(hidden)


def state_of(contact: VcContact, shown: List[str], searched: bool) -> str:
    """`확정됨` · `후보 N개` · `후보 없음` · `아직 안 찾아봄` 중 하나."""
    if startup_outreach.room_ready(contact):
        return CONFIRMED
    if shown:
        return PICKS
    return NO_PICKS if searched else NEVER


def rows(db: Session, user: User) -> dict:
    """[방 매칭] 화면 — 내 스타트업 줄 전부(제외 줄 빼고)를 한 판에.

    **확정된 줄도 남는다.** 빼면 "방금 확정한 곳이 어디 갔지" 를 화면에서 물을
    수가 없다. `딜소개 불가` · `검토중단` 줄은 표에 세우지 않고 **수만** 적는다
    — 안내 카톡이 언제나 빼는 줄이라 방을 맞춰도 나갈 일이 없다.
    """
    known = room_match.investor_rooms(db)
    out, excluded = [], 0
    for c in startup_outreach.my_rows(db, user):
        if startup_outreach.group_of(c) == startup_outreach.EXCLUDED:
            excluded += 1
            continue
        found = room_match.candidates(c)
        shown, hidden = picks(c, known)
        room = (c.kakao_room_name or "").strip()
        state = state_of(c, shown, bool(found["at"]))
        room_state = startup_outreach.room_state(c)
        out.append({
            "contact": c,
            "id": c.id,
            "firm": startup_outreach.company_name(c),
            "name": (c.name or "").strip(),
            "room": room,
            "room_state": room_state,
            "room_label": startup_outreach.ROOM_LABELS.get(room_state, room_state),
            "state": state,
            "state_label": STATE_LABELS[state].format(n=len(shown)),
            "picks": [{"room": r,
                       # 사용자가 짚어 준 「회사명이 무조건 들어가 있음」 — 고를 때의 근거.
                       "has_name": room_match.has_company_name(r, room_match.company_name(c)),
                       # 지금 방 이름이 이 제목이다(이미 확정했거나 적어 둔 것).
                       "current": r == room,
                       # 같은 제목의 방이 여럿 — 확정할 수 없다(`confirm`).
                       "same": r in found["same"]}
                      for r in shown],
            "searched_at": found["at"],
            "query": room_match.search_query(c),
            "investor_hidden": hidden,
            "searchable": searchable(c),
        })
    return {
        "rows": out,
        "total": len(out),
        "excluded": excluded,
        "confirmed": sum(1 for r in out if r["state"] == CONFIRMED),
        "with_picks": sum(1 for r in out if r["state"] == PICKS),
        "no_picks": sum(1 for r in out if r["state"] == NO_PICKS),
        "never": sum(1 for r in out if r["state"] == NEVER),
        # [카톡방 찾기·확인] 이 실을 줄 수 — 누르면 세우는 잡의 크기와 **같은 함수**다
        # (`task_of` — 대조할 줄 + 회사명으로 찾을 줄).
        "search_count": sum(1 for r in out if r["searchable"]),
    }


# ── 확정 ────────────────────────────────────────────────────────────────────

def mine(db: Session, user: User, contact_id: int) -> Optional[VcContact]:
    """확정할 수 있는 내 줄 — 화면에 서는 줄과 **같은 판정**(`rows`)."""
    for c in startup_outreach.my_rows(db, user):
        if c.id == contact_id:
            if startup_outreach.group_of(c) == startup_outreach.EXCLUDED:
                return None
            return c
    return None


def confirm(db: Session, contact: VcContact, title: str) -> VcContact:
    """[이 방으로 확정] — 방 이름을 그 후보 제목으로 적고 **`확인됨`** 으로 둔다.

    ## 왜 확인을 한 번 더 안 거치나

    후보는 발송기가 **카톡 창에서 읽어 온 제목**이다(`discover_rooms` — 검색
    결과 줄, 또는 열어 본 방의 창 제목). [방 연결 확인] 이 하는 일도 같은
    글자를 카톡에서 찾아보는 것이라, 그 글자를 그대로 적은 지금 다시 돌려도
    같은 답이 나온다. 사람이 고른 것은 **어느 방인가** 이지 글자가 아니다.

    ## 받지 않는 것

      · **후보에 없는 글자** — 확정은 카톡에서 읽어 온 글자에만 `확인됨` 을
        단다. 사람이 적은 글자는 직접 적기(`확인 안 됨`)로 간다.
      · 투자사 방으로 걸러진 제목 — 화면과 같은 함수(`picks`)로 거른다.
      · **같은 제목이 여럿** 걸린 제목(`room_match.save_candidates` 의 `same`) —
        그 글자로는 어느 방인지 가를 수 없다. 방 확인이 `같은 이름이 여럿` 으로
        끝나는 그 경우다.

    ## 적는 자리

    방 이름이 바뀌면 이전 확인은 무효다(`room_joined.after_edit`) — 그 위에
    `확인됨` 을 적는다(`room_joined.set_verdict`). 참여여부가 `O` 로 맞고,
    사람이 `방 나감`·`참여 안 함` 으로 적어 둔 줄이면 `확인됨` 을 달지 않는다
    (그 규칙도 거기 한 곳이다).
    """
    text = (title or "").strip()
    shown, _ = picks(contact, room_match.investor_rooms(db))
    if not text or text not in shown:
        raise NotPickable("카톡에서 찾은 후보가 아닙니다 — 화면을 새로 열어 보세요. "
                          "직접 적은 이름은 [방 연결 확인] 으로 확인합니다")
    if text in room_match.candidates(contact)["same"]:
        raise NotPickable("카톡에 같은 제목의 방이 여럿입니다 — 카톡에서 방 이름을 "
                          "고유하게 바꾼 뒤 직접 적고 [방 연결 확인] 을 눌러 주세요")
    was = room_joined.before(contact)
    contact.kakao_room_name = text
    room_joined.after_edit(contact, was)
    room_joined.set_verdict(contact, room_joined.VERIFIED)
    return contact
