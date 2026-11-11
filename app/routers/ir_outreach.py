"""IR 기업 현황 › IR 기업현황 탭 — 고른 기업에 **안내 카톡** · **카톡방 찾기·확인** (11/11).

무엇을 왜 그렇게 하는지(받는 줄 · 보내는 계정 · 누가 [발송 시작] 을 누르나 · 막는 규칙)는
`services/ir_outreach.py` 머리말에 있다. 여기는 화면이 부르는 자리 셋이다.

  · `POST /api/ir-msg/preview` — 고른 기업마다 나갈 글 또는 빠지는 까닭.
  · `POST /api/ir-msg/send`    — 고른 것으로 **대기 목록을 세운다**(`draft`). 한 통도
    안 나간다 — 세운 사람이 진행 화면에서 [발송 시작] 을 누르거나 보낼 시각을 고른다.
  · `POST /api/ir-rooms/check` — [카톡방 찾기·확인]. 방 확인 잡 하나(아무것도 안 나간다).

## 발송 경로를 새로 만들지 않는다

[대기 목록 만들기] 는 `routers/deals.create_send_list` 를 그대로 부른다
(`MODE_STARTUP_MSG_IR`). 방 이름 확인 · 문구 스냅숏 · 예약 · `draft` 가 전부 그 함수
안에 있다. 글을 채우는 자리도 `startup_outreach.render` 하나다 — 미리보기와 같은 함수.

## 판정하는 자리는 하나다 (#522 리뷰)

미리보기와 목록 만들기가 둘 다 `ir_outreach.rows` 를 지나는데, 목록 쪽 판정은 **세우는
함수 안**(`deals.build_send_list`)에만 있다 — 여기서 한 벌 더 거르지 않는다. 미리보기 뒤에
방이 풀렸거나 다른 사람이 같은 문구를 보냈으면 그 함수가 **통째로 거절하고 까닭을
말한다** — 조용히 빼고 나머지만 세우면 몇 곳에 나가는지 아무도 모른다. 공용 주소
`/api/deals/send` 는 이 모드를 안 받는다(거기로 찌르면 판정을 건너뛰고 곧장 나갔다).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, no_send_as_member, sends_deals
from ..models import IrCompany, User
from ..services import cadence, ir_outreach, send_window, startup_outreach
from ..version import VERSION

router = APIRouter(tags=["ir-outreach"])


def screen(db: Session, user: User) -> Optional[dict]:
    """IR 기업현황 탭이 그리는 **안내 카톡 · 카톡방 찾기·확인** 칸. 못 쓰는 계정이면 `None`.

    투자컨설턴트는 발송이 없다(`deps.sends_deals`) — 고르는 칸도 안 선다. 보내는 계정이
    안 정해졌으면 칸은 서되 그 까닭을 적는다(누르면 아무 일이 없는 단추를 세우지 않는다).

    문구 셋의 글 · 회차명은 **처음부터 다 싣는다** — 스타트업 화면은 문구를 바꿀 때 화면을
    다시 받지만, 이 표는 수백 줄이라 다시 받으면 고른 체크가 다 풀린다. 고르는 규칙은
    스타트업 화면과 같다(`startup_outreach.template_body` · `cadence`).
    """
    if not sends_deals(user):
        return None
    owner = ir_outreach.sender(db)
    return {
        "sender": owner.name if owner else "",
        "no_sender": ir_outreach.NO_SENDER,
        "label": ir_outreach.LABEL,
        "topics": [{"key": t.key, "label": t.label,
                    "body": startup_outreach.template_body(db, user, t),
                    "title": cadence.default_batch_title(
                        db, label=f"{ir_outreach.LABEL} · {t.label}")}
                   for t in startup_outreach.TOPICS],
        "placeholders": ir_outreach.PLACEHOLDERS,
        "days": startup_outreach.DEFAULT_DAYS,
        "send_earliest_hour": send_window.earliest(),
        "send_latest_hour": send_window.latest(),
        "agent_needs": VERSION,
        "rooms_href": ir_outreach.ROOMS_HREF,
        # 내가 세운 **아직 안 나간** 회차(보내는 계정 것이라 내 다른 목록에는 안 선다).
        "my_drafts": ir_outreach.drafts_by(db, user),
    }


def _topic(value: str) -> startup_outreach.Topic:
    """고른 문구. 모르면 **짐작하지 않고** 멈춘다(다른 문구로 보내지 않는다)."""
    topic = startup_outreach.topic_of(value)
    if topic is None:
        raise HTTPException(status_code=400, detail="보낼 문구를 고르세요")
    return topic


def _sender_name(db: Session) -> str:
    owner = ir_outreach.sender(db)
    return owner.name if owner else ""


class PreviewIn(BaseModel):
    topic: str = ""
    body: str = ""
    company_ids: List[int] = []
    days: int = startup_outreach.DEFAULT_DAYS


@router.post("/api/ir-msg/preview")
def preview(body: PreviewIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """고른 기업마다 **나갈 글**(보낼 수 있는 곳)과 **빠지는 까닭**(나머지).

    아무 곳도 안 골랐으면 지어낸 줄 하나로 글만 보여 준다 — 문구를 보려고 아무 기업이나
    골랐다가 그대로 목록을 만드는 일을 막는다(스타트업 화면과 같은 이유).

    `ready_ids` 가 [대기 목록 만들기] 가 보낼 기업이다 — 화면은 이 값을 그대로 싣는다.
    """
    topic = _topic(body.topic)
    text = (body.body or "").strip() or startup_outreach.template_body(db, user, topic)
    if len(text) > startup_outreach.MAX_CHARS:
        raise HTTPException(status_code=400, detail="문구가 너무 깁니다")
    companies = ir_outreach.load(db, body.company_ids)
    sender = _sender_name(db)
    if not companies:
        # 저장하지 않는 줄이다 — 세션에 넣지 않는다.
        sample = IrCompany(id=0, name="○○기업", contact_name="○○○")
        return {"sample": True, "sender": sender, "ready_ids": [], "skipped": [],
                "previews": [{"company_id": 0, "firm": "○○기업", "name": "○○○", "room": "",
                              "last_date": "",
                              "message": startup_outreach.render(text, sample, user)}]}
    view = ir_outreach.rows(db, companies, topic, startup_outreach.clamp_days(body.days))
    return {
        "sample": False,
        "sender": sender,
        "ready_ids": view["ready_ids"],
        "counts": view["counts"],
        "previews": [{"company_id": r["id"], "firm": r["firm"], "name": r["name"],
                      "room": r["room"], "last_date": r["last_date"],
                      "message": startup_outreach.render(text, r["company"], user)}
                     for r in view["rows"] if r["sendable"]],
        # **조용히 빼지 않는다** — 빠지는 곳마다 까닭을 적는다.
        "skipped": [{"company_id": r["id"], "firm": r["firm"], "group": r["group"],
                     "reason": r["reason"], "last_date": r["last_date"]}
                    for r in view["rows"] if not r["sendable"]],
    }


class SendIn(BaseModel):
    topic: str = ""
    body: str = ""
    company_ids: List[int] = []
    days: int = startup_outreach.DEFAULT_DAYS
    title: str = ""
    scheduled_at: str = ""


@router.post("/api/ir-msg/send", dependencies=[Depends(no_send_as_member)])
def make_draft(body: SendIn, background: BackgroundTasks,
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """[대기 목록 만들기] — **세우기만 한다. 한 통도 나가지 않는다.**

    회차는 **보내는 계정 것**으로, 묶음은 누른 사람 것으로 선다(`create_send_list` 의
    `MODE_STARTUP_MSG_IR`). 누른 사람이 진행 화면에서 [발송 시작] 을 누르거나 고른
    시각이 되어야 그 계정 PC 에서 나간다. 보낼 수 있는지는 세우는 함수가 판정한다.
    """
    from .deals import MODE_STARTUP_MSG_IR, SendRequest, build_send_list

    topic = _topic(body.topic)
    ids = list(dict.fromkeys(body.company_ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="보낼 기업을 하나 이상 고르세요")
    owner = ir_outreach.sender(db)
    if owner is None:
        raise HTTPException(status_code=400, detail=ir_outreach.NO_SENDER)
    if len(ir_outreach.load(db, ids)) != len(ids):
        raise HTTPException(status_code=404,
                            detail="없는 기업이 섞였습니다 — 화면을 새로 여세요")
    made = build_send_list(
        SendRequest(contact_ids=ids, mode=MODE_STARTUP_MSG_IR, draft=True,
                    topic=topic.key, body=body.body or "", days=body.days,
                    title=(body.title or "").strip() or None,
                    scheduled_at=(body.scheduled_at or "").strip()),
        background, db=db, user=user)
    return {**made, "href": f"/jobs/{made['job_id']}", "sender": owner.name}


class RoomCheckIn(BaseModel):
    company_ids: List[int] = []


@router.post("/api/ir-rooms/check", dependencies=[Depends(no_send_as_member)])
def check_rooms(body: RoomCheckIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """[카톡방 찾기·확인] — 고른 기업의 대표 카톡방을 **보내는 계정 PC 카톡**에서.

    적어 둔 방 이름이 확인 전이면 그 이름 그대로 대조하고, 없거나 못 찾은 곳은 회사명으로
    찾아 후보로만 담는다(`ir_outreach.room_task`). `queued` 로 선다 — 읽기만 한다.

    진행 화면은 회차 주인(보내는 계정)과 관리자가 본다. 그 밖의 사람은 [대표 카톡방
    맞추기] 로 보낸다(`rooms_href` — 거기서 찾은 시각 · 후보 · 상태가 줄마다 선다).
    """
    ids = list(dict.fromkeys(body.company_ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="찾을 기업을 하나 이상 고르세요")
    owner = ir_outreach.sender(db)
    if owner is None:
        raise HTTPException(status_code=400, detail=ir_outreach.NO_SENDER)
    companies = ir_outreach.load(db, ids)
    try:
        made = ir_outreach.queue_rooms(db, owner, companies)
    except ir_outreach.RoomCheckRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = made["job"]
    rooms_href = f"{ir_outreach.ROOMS_HREF}?ids={','.join(str(c.id) for c in companies)}"
    if job is None:
        detail = ("찾을 곳이 없습니다 — 고른 기업이 모두 카톡방이 확인됐거나, 딜소개 불가 · "
                  "폐업이거나, 회사명이 비어 있습니다")
        if made["conflicts"]:
            detail = (f"같은 방 제목을 가진 기업이 둘 이상이라 대조하지 않았습니다: "
                      f"{', '.join(made['conflicts'][:5])} — 카톡에서 방 이름을 서로 다르게 "
                      "바꾼 뒤 적어 주세요(다음에 누르면 회사명으로 찾습니다)")
        raise HTTPException(status_code=400, detail=detail)
    viewable = job.user_id == user.id or user.role == "admin"
    return {"job_id": job.id, "total": job.total,
            "exact": made["exact"], "search": made["search"],
            "conflicts": made["conflicts"],
            "skipped": len(ids) - job.total, "sender": owner.name,
            "href": f"/jobs/{job.id}" if viewable else "",
            "rooms_href": rooms_href}
