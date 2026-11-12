"""IR 기업 현황 › IR 기업현황 탭의 **안내 카톡** · **카톡방 찾기·확인** (11/11).

## 무엇인가

사용자 요청: *"스타트업에 있는 안내 카톡 기능을 IR 기업 현황 메뉴의 IR 기업현황
탭에도 동일하게 있어야 함. 방 매칭도."*

좌측 [스타트업] 의 안내 카톡(`services/startup_outreach.py`)과 **같은 문구 셋 · 같은
채움 · 같은 발송 목록 길**이다. 다른 것은 받는 줄과 보내는 PC 둘이다.

  · 받는 줄 — IR 기업 현황의 기업(`IrCompany`). 방은 그 기업의 `대표 카톡방`
    (`IrCompany.kakao_room_name`) — 스타트업 월간 발송이 보내는 그 칸이다.
  · 보내는 PC — **스타트업 월간 발송의 보내는 계정**(`startup_send.sender_id`).
    그 칸의 방 제목은 그 계정 카톡의 제목이다(맞추기 화면 · 월간 IR 이 그 계정 PC 에서
    찾고 보냈다 — `room_match.verify_picked` · `verify_sent`). 카톡방 제목은 사람마다
    따로 바꿀 수 있어서(`services/sender_rooms.py` 머리말) 누른 팀원 PC 로 보내면 그
    제목의 방이 없을 수 있다. 그래서 회차는 **그 계정 것**으로 서고 그 계정 PC 의
    발송기가 집어간다(`routers/agent_api.poll`). 누가 그 계정인가는 코드에 적지 않는다
    — 팀 현황의 `스타트업 월간 발송 — 메뉴·보내는 계정` 판이 정한다.

## 누가 세우고, 누가 [발송 시작] 을 누르나

투자컨설턴트가 아니면 누구나 고르고 대기 목록을 세운다(그 계정은 이 화면에 못 온다 —
`deps.CONSULTANT_PATHS`). 회차(`SendJob.user_id`)는 보내는 계정 것이고, 회차 묶음
(`DealBatch.user_id`)은 **세운 사람** 것이다. 세운 사람이 진행 화면에서 [발송 시작] ·
예약 · [중단] 을 누른다(`may_operate` — `routers/jobs._job_or_404`). 스타트업 화면에서
각자 세우고 각자 누르는 것과 같은 흐름이다. 다루는 사람은 **세운 사람 + 관리자**다 —
회차 주인인 보내는 계정도 남이 세운 회차는 보기만 한다(#522 리뷰: 그 계정 화면에서
남의 대기 목록을 모르고 누르면 세운 사람이 본 적 없는 때에 나간다). 대기 목록은
늘 `draft` 로 선다 — 공용 발송 주소(`/api/deals/send`)는 이 모드를 안 받는다.

`{보내는사람}` 은 **세운 사람의 이름**이다 — 대표가 답을 주고받을 사람이다. 보내는
계정의 이름은 대개 사람 이름이 아니다(`sheet_owner.real_name`).

## 누구에게 보낼 수 있는가 — 스타트업 안내 카톡의 규칙을 기업 줄로 옮긴다

  · `딜소개 불가` — 계약여부든 기업명 꼬리표든 언제나 뺀다(`companies.deal_blocked`).
  · **폐업** — 이름에 `폐업` 이 든 기업(`ir_monthly.is_closed` — 월간 발송과 같은
    판정. 팀은 폐업을 계약여부가 아니라 이름 뒤 표시로 적는다).
  · 이어 둔 스타트업 명단 줄이 `검토중단` — 그 줄 주인이 멈춰 둔 대표다
    (`VcContact.ir_company_id` — 사람이 [IR 기업 연결] 로 이은 줄). 기업 줄에는 멈춤
    칸이 없어서, 스타트업 쪽 `검토중단` 에 해당하는 것이 이것이다.
  · 방이 없거나 카톡에서 **확인 전** — 확인된 방에만 보낸다(스타트업 안내 카톡과
    같다 — 대표 이름이 든 다른 방이 같은 글자로 걸릴 수 있다). [카톡방 찾기·확인] 으로
    고친다.
  · 이 문구를 N일 안에 받았거나 아직 안 나간 회차에 들어 있다 — 사람이 풀 수 있는
    거르기(`startup_outreach.recent_reason`). 이어 둔 스타트업 줄이 받은 것도 센다
    (같은 대표다 — 거꾸로도 센다, `startup_outreach.last_sent`).

  · 방 제목이 **투자사 방**으로 보인다(`room_match.investor_reason` — 후보를 거르는 그
    판정). 확인 값이 붙어 있어도 막는다 — 그리로 나가면 투자사가 대표 안내를 받는다.

**조용히 빼지 않는다.** 미리보기가 고른 곳마다 나갈 글 또는 빠지는 까닭을 적고,
목록을 만드는 자리(`deals.build_send_list` — 판정은 거기 한 곳)는 섞인 줄이 있으면
통째로 거절한다. [발송 시작] · 예약이 풀리는 순간에도 막는 규칙과 방 이름을 다시
본다(`recheck` — `routers/jobs._requeue`).

## 발송 목록을 만드는 것은 여기가 아니다

`routers/deals.create_send_list` 를 그대로 지난다(`MODE_STARTUP_MSG_IR`) — 방 이름 확인 ·
문구 스냅숏 · 예약 · `draft` 가 전부 그 함수 안에 있다. 글을 채우는 자리도
`startup_outreach.render` 하나다(기업 줄도 받는다). 잡 종류도 같다(`startup_msg` —
발송기 판을 안 올린다).

## 카톡방 찾기·확인 — 기업 줄 (`room_task` · `queue_rooms`)

스타트업 명단 쪽(`startup_room_pick.task_of`)과 같은 판정을 기업 줄에 건다 — 적어 둔
대표 카톡방이 확인 전이면 그 이름 그대로 대조하고, 없거나 못 찾았으면 회사명으로 찾아
**후보로만** 담는다(`IrCompany.room_candidates` — 서버는 고르지 않는다,
`room_match` 머리말). 잡은 방 확인 잡(`verify_room`), **보내는 계정 것**이다(제목이 그
계정 카톡의 것이라). 스타트업 쪽과 같은 막이를 둔다: 같은 방 제목을 가진 기업이 둘이면
대조하지 않고 `같은 이름이 여럿` 으로 적고, 대조한 이름이 투자사 방이면 확인됨으로 안
올린다(`agent_api._startup_investor_room`). 찾는 중인 기업은 또 싣지 않고, 한 번에
`MAX_ROOM_CHECK` 곳까지다. 결과는 기업 줄의 방 칸에만 적힌다 — 이어 둔 스타트업 명단 줄의
방 이름 · 확인 표시는 그 팀원 카톡 기준이라 건드리지 않는다. 고르기 · 직접 적기는
「대표 카톡방 맞추기」(`/deals/startup-ir/rooms`) 한 곳이다.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from collections import Counter

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import (STARTUP_MSG_KIND, DealBatch, IrCompany, SendItem, SendJob,
                      User, VcContact)
from . import (ir_monthly, room_joined, room_match, room_name, sheet_owner, startup_outreach,
               startup_send, twin_send)

#: 화면에 적는 이름 — 스타트업 화면과 **같은 일**이라 같은 이름이다.
LABEL = startup_outreach.LABEL

#: 후보를 고르는 화면 — 「대표 카톡방 맞추기」(`routers/startup_send.rooms_page`).
ROOMS_HREF = "/deals/startup-ir/rooms"

#: [카톡방 찾기·확인] 한 번에 싣는 기업 수. 발송기가 한 번에 집는 수(`agent/main.py:
#: DEFAULT_CONFIG["job_cap"]`)와 같은 크기다 — 그보다 크면 그 PC 의 카톡을 몇 분씩 붙잡는다.
MAX_ROOM_CHECK = 60


class RoomCheckRefused(ValueError):
    """[카톡방 찾기·확인] 을 세우지 않는 까닭. 그대로 화면에 간다."""


#: 보내는 계정이 없을 때의 말 — 화면 · 라우터가 같은 말을 쓴다.
NO_SENDER = (f"{startup_send.LABEL}의 보내는 계정이 정해지지 않았습니다 — 팀 현황의 "
             f"'{startup_send.LABEL} — 메뉴·보내는 계정' 판에서 정하세요(그 계정 PC 에서 나갑니다)")

#: 문구 화면이 적어 주는 채움말 안내 — 무엇이 어디서 채워지는지(기업 줄 기준).
PLACEHOLDERS = [
    (startup_outreach.CEO, "기업의 대표자명 (비어 있으면 그 자리를 빼고 '대표님' 으로 읽힙니다)"),
    (startup_outreach.COMPANY, "기업명 (대괄호 메모는 뺍니다)"),
    (startup_outreach.SENDER, "목록을 세우는 사람(나)의 계정 이름"),
]


# ── 누가 보내나 ─────────────────────────────────────────────────────────────

def sender(db: Session) -> Optional[User]:
    """이 발송이 나가는 계정 — 스타트업 월간 발송의 그 계정. 없거나 정지면 `None`.

    판정은 월간 발송 한 곳이다(`startup_send.sender_id` — 메뉴가 꺼져 있으면 없다).
    정지된 계정으로 세우면 회차는 서는데 아무 PC 도 안 집어간다.
    """
    uid = startup_send.sender_id(db)
    user = db.get(User, uid) if uid else None
    return user if user is not None and user.is_active else None


def made_by(db: Session, job: Optional[SendJob], user: Optional[User]) -> bool:
    """이 사람이 **세운** 안내 카톡 회차인가 — 회차 주인이 아니어도 다룰 수 있다.

    IR 기업현황 탭의 안내 카톡은 회차가 보내는 계정 것이고 묶음이 세운 사람 것이다
    (머리말). 안내 카톡 종류만 본다 — 다른 회차는 묶음 주인과 회차 주인이 늘 같다.
    """
    if job is None or user is None or job.kind != STARTUP_MSG_KIND or not job.batch_id:
        return False
    batch = db.get(DealBatch, job.batch_id)
    return batch is not None and batch.user_id == user.id


def is_ir_job(db: Session, job: Optional[SendJob]) -> bool:
    """IR 기업현황 탭에서 세운 안내 카톡 회차인가 — 기업 줄로 나가는 `startup_msg`."""
    if job is None or job.kind != STARTUP_MSG_KIND:
        return False
    return db.execute(select(SendItem.id).where(
        SendItem.job_id == job.id, SendItem.ir_company_id.isnot(None)).limit(1)).first() is not None


def may_operate(db: Session, job: Optional[SendJob], user: Optional[User]) -> bool:
    """이 사람이 이 회차를 **다룰 수** 있나 — [발송 시작] · 예약 · [중단] · 재시도.

    보통은 회차 주인뿐이다(지금까지 그대로). IR 기업현황 탭의 안내 카톡만 **세운 사람 +
    관리자**다 — 회차 주인(보내는 계정)은 보기만 한다(머리말). 보기는 따로다
    (`routers/jobs._viewable_job_or_404`).
    """
    if job is None or user is None:
        return False
    if is_ir_job(db, job):
        return made_by(db, job, user) or user.role == "admin"
    return job.user_id == user.id


def drafts_by(db: Session, user: User) -> List[dict]:
    """이 사람이 세운 **아직 안 나간** 안내 카톡 회차 — 탭이 링크로 세운다(잊지 않게)."""
    jobs = db.execute(
        select(SendJob).join(DealBatch, DealBatch.id == SendJob.batch_id)
        .where(SendJob.kind == STARTUP_MSG_KIND, SendJob.status == "draft",
               DealBatch.user_id == user.id, SendJob.user_id != user.id)
        .order_by(SendJob.id)).scalars().all()
    return [{"id": j.id, "total": j.total, "topic": startup_outreach.topic_of(j.topic),
             "scheduled": bool(j.scheduled_at)} for j in jobs if is_ir_job(db, j)]

# ── 고른 기업 ───────────────────────────────────────────────────────────────

def load(db: Session, ids: Iterable[int]) -> List[IrCompany]:
    """고른 id 중 있는 기업만, **고른 순서대로**(같은 id 는 한 번)."""
    wanted = list(dict.fromkeys(int(i) for i in ids or []))
    if not wanted:
        return []
    by_id = {c.id: c for c in db.execute(
        select(IrCompany).where(IrCompany.id.in_(wanted))).scalars()}
    return [by_id[i] for i in wanted if i in by_id]


def is_blocked(company: IrCompany) -> bool:
    """`딜소개 불가` 기업 — 계약여부 또는 기업명 꼬리표(`companies.deal_blocked` 그대로)."""
    from ..routers.companies import deal_blocked

    return deal_blocked(company)


def paused_links(db: Session, ids: Iterable[int]) -> Dict[int, str]:
    """`{기업 id: 팀원 이름}` — 이어 둔 스타트업 명단 줄이 `검토중단` 인 기업."""
    ids = list(ids)
    if not ids:
        return {}
    out: Dict[int, str] = {}
    for row in db.execute(select(VcContact).where(VcContact.ir_company_id.in_(ids))).scalars():
        if sheet_owner.is_paused(row) and row.ir_company_id not in out:
            owner = db.get(User, row.user_id)
            out[row.ir_company_id] = getattr(owner, "name", "") or "다른 팀원"
    return out


def room_state(company: IrCompany) -> str:
    """보낼 방의 상태 — `missing` 이거나 방 확인 결과 넷 중 하나(스타트업과 같은 말)."""
    if not (company.kakao_room_name or "").strip():
        return startup_outreach.ROOM_MISSING
    return company.room_verified or room_joined.UNVERIFIED


def _verdict(company: IrCompany, paused: Dict[int, str], known: room_match.InvestorRooms):
    """`(갈래, 까닭)` — 보낼 수 있으면 `("", "")`. 판정은 여기 하나다.

    `known` 은 투자사 방 열쇠(`room_match.investor_rooms` — 한 번 읽어 여러 기업에 쓴다).
    """
    if is_blocked(company):
        return startup_outreach.EXCLUDED, "딜소개 불가"
    if ir_monthly.is_closed(company):
        return startup_outreach.EXCLUDED, "폐업"
    if company.id in paused:
        return (startup_outreach.EXCLUDED,
                f"{paused[company.id]} 님 스타트업 명단에서 {sheet_owner.paused_label()}")
    state = room_state(company)
    if state != room_joined.VERIFIED:
        return startup_outreach.NO_ROOM, startup_outreach.ROOM_LABELS.get(state, state)
    # ★ 마지막 막이 — **투자사 방**으로 보이는 제목에는 확인 값이 있어도 안 보낸다
    #   (#522 리뷰: 대조가 투자사 방을 확인됨으로 올린 적이 있다 — 그 길은 이제 막았지만,
    #   이미 붙은 확인 값은 여기서 막는다).
    why = room_match.investor_reason(company.kakao_room_name, company.name, known)
    if why:
        return startup_outreach.NO_ROOM, f"투자사 방으로 보임({why})"
    return "", ""


def refusal(db: Session, company: IrCompany) -> str:
    """이 기업에 **보내면 안 되는** 까닭. 보낼 수 있으면 빈 글자.

    미리보기 · 목록(`rows`)과 나가는 순간(`recheck`)이 같은 `_verdict` 를 지난다.
    """
    return _verdict(company, paused_links(db, [company.id]),
                    room_match.investor_rooms(db))[1]


def recheck(db: Session, item: SendItem) -> str:
    """**나가는 순간** 이 건을 빼야 하는 까닭 — 안내 카톡 회차의 대기 건. 없으면 빈 글자.

    회차를 세운 뒤 [발송 시작] · 예약까지 사이에 막는 규칙이 걸렸거나(딜소개 불가 ·
    검토중단 · 확인이 풀림 …) **방 이름이 바뀌었으면**(건에 굳힌 방이 지금의 방이
    아니다) 뺀다 — 딜 소싱 · 월간 발송이 나가는 순간 다시 보는 것과 같은 자리
    (`routers/jobs._requeue`). 스타트업 명단 줄(`VcContact`)은 `startup_outreach.refusal`.
    """
    row = item.ir_company if item.ir_company_id else item.contact
    if row is None:
        return "줄이 없어짐"
    why = (refusal(db, row) if isinstance(row, IrCompany)
           else startup_outreach.refusal(row))
    if why:
        return why
    if not room_name.same_title(row.kakao_room_name, item.room_name):
        return "목록을 세운 뒤 방 이름이 바뀜"
    return ""


# ── 이 문구를 언제 받았나 ───────────────────────────────────────────────────

def last_sent(db: Session, companies: List[IrCompany],
              topic: startup_outreach.Topic) -> Dict[int, dict]:
    """`{기업 id: {...}}` — `startup_outreach.last_sent` 와 같은 모양.

    이 기업에 나간 안내 카톡(IR 기업현황 탭) + **이어 둔 스타트업 명단 줄**에 나간 것
    (같은 대표다 — 그 줄 주인 이름이 `by_twin` 에 든다).
    """
    ids = [c.id for c in companies]
    if not ids:
        return {}
    company_of, owner_of = {}, {}

    def keep(row, company_id):
        company_of[row.id] = company_id
        owner = db.get(User, row.user_id)
        owner_of[row.id] = getattr(owner, "name", "") or "다른 팀원"

    for row in db.execute(select(VcContact).where(VcContact.ir_company_id.in_(ids))).scalars():
        keep(row, row.ir_company_id)
        # 다른 팀원 명단의 같은 기업 줄도 같은 대표다(`twin_send.twins` — 스타트업 화면과 같다).
        for twin in twin_send.twins(db, row):
            if twin.id not in company_of:
                keep(twin, row.ir_company_id)
    query = startup_outreach._live(topic).add_columns(SendItem.ir_company_id).where(
        or_(SendItem.ir_company_id.in_(ids), SendItem.contact_id.in_(list(company_of))))
    grouped: Dict[int, list] = {}
    for h in db.execute(query).all():
        if h.ir_company_id:
            grouped.setdefault(h.ir_company_id, []).append((h, ""))
        else:
            grouped.setdefault(company_of[h.contact_id], []).append(
                (h, owner_of[h.contact_id]))
    return {cid: startup_outreach._summary(hits) for cid, hits in grouped.items()}


# ── 미리보기 · 목록이 읽는 것 ───────────────────────────────────────────────

def rows(db: Session, companies: List[IrCompany], topic: startup_outreach.Topic,
         days: int) -> dict:
    """고른 기업마다 **보낼 수 있는가와 그 까닭** — 스타트업 화면의 `rows` 와 같은 갈래.

      · `ready`    지금 보낼 수 있다
      · `recent`   이 문구를 N일 안에 받았거나 대기 중(N 을 0 으로 두면 보낼 수 있다)
      · `no_room`  방이 없거나 확인 전 — [카톡방 찾기·확인] 으로 고친다
      · `excluded` 딜소개 불가 · 폐업 · 이어 둔 스타트업 줄이 검토중단
    """
    history = last_sent(db, companies, topic)
    paused = paused_links(db, [c.id for c in companies])
    known = room_match.investor_rooms(db)
    out = []
    for c in companies:
        info = history.get(c.id)
        group, hard = _verdict(c, paused, known)
        recent = "" if hard else startup_outreach.recent_reason(info, days)
        if not group:
            group = "recent" if recent else "ready"
        out.append({
            "company": c,
            "id": c.id,
            "firm": startup_outreach.company_name(c),
            "name": startup_outreach.ceo_name(c),
            "room": (c.kakao_room_name or "").strip(),
            "room_state": room_state(c),
            "last_date": (info or {}).get("date", ""),
            "reason": hard or recent,
            "group": group,
            "sendable": group == "ready",
        })
    return {
        "rows": out,
        "ready_ids": [r["id"] for r in out if r["sendable"]],
        "counts": {g: sum(1 for r in out if r["group"] == g)
                   for g in ("ready", "recent", startup_outreach.NO_ROOM,
                             startup_outreach.EXCLUDED)},
    }


# ── 카톡방 찾기·확인 — 기업 줄 ──────────────────────────────────────────────

def room_task(company: IrCompany) -> str:
    """[카톡방 찾기·확인] 이 이 기업에서 할 일 — `exact` · `search` · 빈 글자.

    스타트업 명단 쪽과 같은 판정이다(`startup_room_pick.task_of`). `딜소개 불가` ·
    폐업 기업은 싣지 않는다 — 어느 발송도 그 방으로 안 나간다.
    """
    from .startup_room_pick import EXACT, SEARCH

    if is_blocked(company) or ir_monthly.is_closed(company):
        return ""
    state = room_state(company)
    if state == room_joined.VERIFIED:
        return ""
    if state == room_joined.UNVERIFIED:
        return EXACT
    return SEARCH if room_match.search_query(company) else ""


def queue_rooms(db: Session, owner: User, companies: Iterable[IrCompany]) -> dict:
    """[카톡방 찾기·확인] — **보내는 계정 것**으로 방 확인 잡 하나. 커밋까지 한다.

    대조할 건에는 적어 둔 대표 카톡방 이름을, 찾을 건에는 빈 글자를 싣는다 — 그 한
    칸이 발송기에 무엇을 줄지와 결과를 어디에 적을지를 가른다(`agent_api._company_row`
    — 찾은 제목은 `room_candidates` 에 후보로만, 대조 결과는 `room_verified` ·
    `카톡 연결 여부` 에). 문구는 늘 비운다. 실을 곳이 없으면 `job` 이 `None` 이다.
    """
    from ..routers.agent_api import VERIFY_KIND
    from .startup_room_pick import EXACT

    picked = [(c, room_task(c)) for c in companies]
    picked = [(c, t) for c, t in picked if t]
    if len(picked) > MAX_ROOM_CHECK:
        raise RoomCheckRefused(
            f"한 번에 {MAX_ROOM_CHECK}곳까지 찾고 확인합니다 — 지금 {len(picked)}곳입니다. "
            "나눠서 고르세요(그동안 그 PC 의 카톡을 붙잡습니다)")
    busy = _in_flight(db, [c.id for c, _t in picked])
    if busy:
        names = ", ".join(startup_outreach.company_name(c) for c, _t in picked
                          if c.id in busy)
        raise RoomCheckRefused(
            f"이미 찾고 있는 회차에 들어 있습니다: {names} — 그 회차가 끝난 뒤 다시 누르세요"
            f"(회차 #{', #'.join(str(j) for j in sorted(set(busy.values())))})")
    # 같은 방 제목을 가진 기업이 둘 이상이면 그 글자로는 어느 기업 방인지 못 가른다 —
    # 대조하지 않고 `같은 이름이 여럿` 으로 적는다(스타트업 쪽 `room_name.ambiguous_contacts`
    # 와 같은 막이. 견주는 것은 IR 기업 전부다).
    same = Counter(room_name.title_key(r) for r in db.execute(
        select(IrCompany.kakao_room_name).where(IrCompany.kakao_room_name.isnot(None))).scalars()
        if room_name.title_key(r))
    unclear = [c for c, t in picked
               if t == EXACT and same[room_name.title_key(c.kakao_room_name)] > 1]
    for company in unclear:
        room_joined.set_verdict(company, room_joined.AMBIGUOUS)
    picked = [(c, t) for c, t in picked if c not in unclear]
    exact = sum(1 for _c, t in picked if t == EXACT)
    out = {"job": None, "exact": exact, "search": len(picked) - exact,
           "conflicts": [startup_outreach.company_name(c) for c in unclear]}
    if not picked:
        db.commit()
        return out
    job = SendJob(user_id=owner.id, kind=VERIFY_KIND, status="queued",
                  total=len(picked), sent=0, failed=0)
    db.add(job)
    db.flush()
    for company, task in picked:
        db.add(SendItem(job_id=job.id, ir_company_id=company.id,
                        room_name=(company.kakao_room_name or "") if task == EXACT else "",
                        message="", status="pending"))
    db.commit()
    out["job"] = job
    return out


#: 아직 안 끝난 방 확인 회차의 상태 · 건 상태 — 이 건이 곧 발송기에 갈 수 있다.
_OPEN_JOBS = ("draft", "queued", "running", "paused")
_OPEN_ITEMS = ("pending", "sending")


def _in_flight(db: Session, company_ids: List[int]) -> Dict[int, int]:
    """`{기업 id: 회차 id}` — 아직 안 끝난 방 확인 회차에 이미 실린 기업."""
    from ..routers.agent_api import VERIFY_KIND

    if not company_ids:
        return {}
    rows = db.execute(
        select(SendItem.ir_company_id, SendItem.job_id)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.kind == VERIFY_KIND, SendJob.status.in_(_OPEN_JOBS),
               SendItem.status.in_(_OPEN_ITEMS),
               SendItem.ir_company_id.in_(company_ids))).all()
    return {r.ir_company_id: r.job_id for r in rows}
