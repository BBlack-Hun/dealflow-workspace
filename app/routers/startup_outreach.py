"""스타트업 안내 카톡 — 좌측 [스타트업] 안의 자리(`/startup/msg`).

## 왜 [스타트업] 안인가

받는 줄이 그 화면의 명단이다 — 각자 맡은 스타트업이 그 화면에 탭으로 서 있고
(`sheet_owner.member_tabs`), 보내는 사람도 그 명단의 주인이다. 딜 제안 관리의
월간 발송(`/deals/startup-ir`)과는 받는 표도 보내는 사람도 다르다
(`services/startup_outreach.py` 머리말).

[스타트업] 화면 자체(`/startup`)에 체크상자를 끼우지 않고 자리를 따로 둔 까닭:
그 표는 달마다 칸이 세 개씩 붙고 왼쪽 칸이 고정되는 넓은 표라(`contacts.html`
의 `startup-table`), 고르는 칸을 하나 더 끼우면 고정 칸 계산이 전부 바뀐다.
여기서는 **고르는 데 필요한 칸만** 선다 — 기업명 · 성함 · 계약여부 · 카톡방 ·
이 문구를 마지막으로 받은 날. 그 화면의 툴바에서 [안내 카톡 보내기] 로 온다.

## 이 화면이 하는 일

1. 문구 하나를 고르고(셋 중) 그 자리에서 고쳐 본다 — 저장된 문구틀은 문구
   관리에서 고친다(딜 제안 문구와 같은 자리 · 같은 규칙).
2. 보낼 곳을 고르고 줄마다 나갈 글을 미리 본다.
3. 고른 것으로 **대기 목록을 세운다**(`draft`). 여기서는 한 통도 나가지 않는다 —
   진행 화면에서 [발송 시작] 을 누르거나 보낼 시각(09~19시)을 고른다.

## 발송 경로를 새로 만들지 않는다

[대기 목록 만들기] 는 `routers/deals.create_send_list` 를 그대로 부른다
(`MODE_STARTUP_MSG`). 방 이름 확인 · 문구 스냅숏 · 예약 · `draft` 가 전부 그
함수 안에 있다 — 여기에 한 벌 더 적으면 그중 하나가 빠진 채로 대표 카톡방에
나간다. **글을 채우는 자리도 여기가 아니다** — `startup_outreach.render` 하나다.

## 누가 쓰나

딜소개처럼 **각자**다. 화면이 세우는 줄도, 목록을 만드는 자리가 받는 줄도
`startup_outreach.my_rows`(내 줄만) 하나를 지난다. 관리자도 자기 줄만이다 —
회차는 그 사람의 것으로 서고 그 사람 PC 의 발송기만 집어간다.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import User, VcContact
from ..services import cadence, scheduled_send, startup_outreach
from ..ui import base_ctx
from ..version import VERSION
from .pages import STARTUP_PAGE

router = APIRouter(tags=["startup-outreach"])

#: 좌측 메뉴에서 켜져 보일 자리 — [스타트업] 안이다.
ACTIVE = STARTUP_PAGE.key

#: 이 화면의 주소 — [스타트업] 화면의 단추가 가리키는 **그 값**이다
#: (`ListPage.msg_href`). 두 곳에 적으면 단추가 없는 자리로 데려간다.
HREF = STARTUP_PAGE.msg_href


def _topic(value: str) -> startup_outreach.Topic:
    """고른 문구. 모르는 값이면 **첫 문구로 화면만 연다** — 보낼 때는 짐작하지
    않는다(`create_send_list` 가 모르는 문구를 거절한다)."""
    return startup_outreach.topic_of(value) or startup_outreach.TOPICS[0]


@router.get(HREF, response_class=HTMLResponse)
def outreach_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    topic: str = "",
    days: str = "",
    msg: str = "",
):
    """[스타트업 안내 카톡] — 문구 하나를 골라 내 스타트업에 보낼 대기 목록을 세운다."""
    chosen = _topic(topic)
    # 비었거나 숫자가 아니면 기본값(30일)이다(`clamp_days`).
    n_days = startup_outreach.clamp_days(days)
    ctx = base_ctx(request, db, user, ACTIVE)
    ctx.update(startup_outreach.rows(db, user, chosen, n_days))
    ctx.update({
        "label": startup_outreach.LABEL,
        "topics": startup_outreach.TOPICS,
        "topic": chosen,
        "days": n_days,
        "body": startup_outreach.template_body(db, user, chosen),
        "placeholders": startup_outreach.PLACEHOLDERS,
        "msg": msg,
        "href": HREF,
        # 회차명은 **보내는 날에서 만든다**(`cadence`) — 딜 제안 관리·월간
        # 발송과 같은 자리다.
        "default_title": cadence.default_batch_title(
            db, label=f"{startup_outreach.LABEL} · {chosen.label}"),
        # 보낼 시각을 고를 수 있는 폭(09~19시) — **예약이 정한 그 값이다.**
        "send_earliest_hour": scheduled_send.EARLIEST_HOUR,
        "send_latest_hour": scheduled_send.LATEST_HOUR,
        # 이 회차를 집어가는 발송기 판. 낡은 발송기는 이 종류를 모른다고
        # 밝혀 잡이 큐에 서서 기다린다(`agent/main.py: STARTUP_MSG_KIND`).
        "agent_needs": VERSION,
        "startup_href": STARTUP_PAGE.href,
    })
    return templates.TemplateResponse("startup_msg.html", ctx)


class PreviewIn(BaseModel):
    topic: str = ""
    body: str = ""
    contact_ids: List[int] = []


@router.post("/api/startup-msg/preview")
def preview(body: PreviewIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """줄마다 나갈 글. **목록을 만들 때와 같은 함수**(`startup_outreach.render`)
    를 지난다 — 화면이 채움말을 따로 채우면 미리보기와 나가는 글이 갈린다.

    아무 줄도 안 골랐으면 **지어낸 줄 하나**로 보여 준다. 문구를 보려고 아무
    기업이나 골랐다가 그대로 목록을 만드는 일을 막는다(딜 제안 관리의 기본
    미리보기와 같은 이유).
    """
    topic = startup_outreach.topic_of(body.topic)
    if topic is None:
        raise HTTPException(status_code=400, detail="보낼 문구를 고르세요")
    text = (body.body or "").strip() or startup_outreach.template_body(db, user, topic)
    if len(text) > startup_outreach.MAX_CHARS:
        raise HTTPException(status_code=400, detail="문구가 너무 깁니다")
    rows = startup_outreach.load(db, user, body.contact_ids)
    sample = not rows
    if sample:
        # 저장하지 않는 줄이다 — 세션에 넣지 않는다.
        rows = [VcContact(id=0, name="○○○", firm="○○기업", kakao_room_name="")]
    return {
        "sample": sample,
        "previews": [{
            "contact_id": c.id,
            "firm": startup_outreach.company_name(c),
            "name": (c.name or "").strip(),
            "room": (c.kakao_room_name or "").strip(),
            "message": startup_outreach.render(text, c, user),
        } for c in rows],
    }


class SendIn(BaseModel):
    topic: str = ""
    body: str = ""
    contact_ids: List[int] = []
    days: int = startup_outreach.DEFAULT_DAYS
    title: str = ""
    scheduled_at: str = ""


@router.post("/api/startup-msg/send")
def make_draft(body: SendIn, background: BackgroundTasks,
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """[대기 목록 만들기] — **세우기만 한다. 한 통도 나가지 않는다.**

    `draft` 로 서고, 진행 화면에서 [발송 시작] 을 눌러야(또는 고른 시각이
    되어야) 나간다 — 미팅 후기 대기 목록·월간 발송이 낸 길 그대로다.

    ## 화면이 거른 것과 여기서 거르는 것이 **같은 함수**다

    `startup_outreach.rows` — 화면이 `N일 안에 받은 곳 빼기` 를 어떤 값으로
    보고 있었는지(`days`)까지 받아 같은 판정을 다시 한다. 갈리면 화면에서
    못 고르는 줄이 주소로는 들어간다. 확인 안 된 방 · `딜소개 불가` 는 그 값과
    상관없이 `create_send_list` 가 한 번 더 막는다(`startup_outreach.refusal`).

    ## 거절은 조용하지 않다

    섞인 줄이 있으면 **목록 전체를 거절하고** 그 까닭을 그대로 돌려준다 —
    조용히 빼고 나머지만 세우면 몇 곳에 나가는지 아무도 모른다.
    """
    from .deals import MODE_STARTUP_MSG, SendRequest, create_send_list

    topic = startup_outreach.topic_of(body.topic)
    if topic is None:
        raise HTTPException(status_code=400, detail="보낼 문구를 고르세요")
    ids = list(dict.fromkeys(body.contact_ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="보낼 곳을 하나 이상 고르세요")

    days = startup_outreach.clamp_days(body.days)
    view = startup_outreach.rows(db, user, topic, days)
    allowed = {r["id"] for r in view["ready_rows"]}
    blocked = [r for r in view["rows"] if r["id"] in ids and r["id"] not in allowed]
    unknown = [i for i in ids if i not in {r["id"] for r in view["rows"]}]
    if unknown:
        # 내 스타트업 줄이 아니다(남의 줄 · 지운 줄 · 감춘 줄). 있는지도 흘리지 않는다.
        raise HTTPException(status_code=404, detail="보낼 수 없는 줄이 섞였습니다 — 화면을 새로 여세요")
    if blocked:
        first = blocked[0]
        raise HTTPException(
            status_code=400,
            detail=(f"'{first['firm'] or first['name']}' {first['reason']} — "
                    "목록에서 빼거나 화면을 새로 여세요"))

    made = create_send_list(
        SendRequest(contact_ids=ids, mode=MODE_STARTUP_MSG, draft=True,
                    topic=topic.key, body=body.body or "",
                    title=(body.title or "").strip() or None,
                    scheduled_at=(body.scheduled_at or "").strip()),
        background, db=db, user=user)
    return {**made, "href": f"/jobs/{made['job_id']}"}

