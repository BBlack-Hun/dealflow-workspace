"""스타트업 월간 발송 — 딜 제안 관리 **안**의 자리.

## 왜 스타트업 메뉴가 아니라 여기인가

스타트업 메뉴는 **명단과 자료를 보는 화면**이고
(`/startup`, `/startup/ir-report*` 는 그대로 있다), 딜 제안 관리는 **보내는
화면**이다 — 회차를 만들고, 누구에게 어느 방으로 가는지 보고, 진행을 지켜본다.
보내는 일이 명단 화면에 섞여 있으면 명단을 보러 온 사람 앞에 발송 단추가 선다.

## 이 화면이 하는 일은 둘뿐이다

1. **그 달에 누구에게 무엇이 나가는지 보여 준다** — 기업마다 카톡방 이름과
   실릴 줄 수. 못 보내는 줄도 **남긴다**(까닭을 적어서).
2. 고른 것으로 **대기 목록을 세운다.** 여기서는 한 통도 나가지 않는다.

## 나가는 것은 사람이 누른 뒤다  ★

회차를 `draft` 로 세운다. 발송 프로그램은 `queued` 인 회차만 집어가므로
(`routers/agent_api.py: poll`), 세워 두는 것만으로는 집어갈 것이 없다. 그
계정이 진행 화면(`/jobs/{id}`)에서 [발송 시작] 을 눌러야 `queued` 가 되고 그때
나간다. 미팅 후기 대기 목록이 낸 길을 그대로 탄다(`services/auto_send.py`).

**누르기 전에 무엇을 보게 되는가** 가 이 판의 알맹이다. 이 화면이 몇 곳에 ·
어느 방으로 가는지를 줄마다 적고, 진행 화면이 같은 것을 한 번 더 적는다.

## 발송 경로를 새로 만들지 않는다

[대기 목록 만들기] 는 `routers/deals.create_send_list` 를 그대로 부른다 —
방 이름 확인 · **시험방 치환** · 문구 스냅숏이 전부 그 함수 안에 있다. 여기에
한 벌 더 적으면 그중 하나가 빠진 채로 실제 대표 카톡방에 나간다(예약 큐와
미팅 후기 대기 목록이 같은 이유로 그 함수를 그대로 부른다).

**글을 짓는 자리도 여기가 아니다** — `services/ir_kakao.py` 하나다.

## 정해진 한 계정만

판정은 `services/startup_send.may_send` 한 곳이고, **메뉴를 그리는 자리와 이
라우터가 같은 함수를 읽는다.** 지정되지 않은 계정에는 메뉴가 아예 안 보이고,
주소를 직접 쳐도 **없는 자리**다(404). 403 이 아닌 까닭은, 403 이 "그런 자리가
있는데 너는 안 된다" 라서 이 계정으로는 쓸 수 없는 기능의 존재를 알려 주기
때문이다.
"""
from __future__ import annotations

from typing import List
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, templates
from ..models import User
from ..services import cadence, ir_monthly, startup_send
from ..ui import base_ctx

router = APIRouter(tags=["startup-send"])

#: 좌측 메뉴에서 켜져 보일 자리. 이 화면은 **딜 제안 관리 안**이다.
ACTIVE = "deal"


def _guard(db: Session, user: User) -> None:
    """정해진 계정이 아니면 **없는 자리**다. 화면도 보내는 자리도 이 한 줄을
    지난다 — 둘로 나누면 한쪽만 고쳐지는 날 메뉴는 안 보이는데 주소로는 열린다."""
    if not startup_send.may_send(db, user):
        raise HTTPException(status_code=404, detail="없는 자리입니다")


def _month(value: str) -> str:
    """고른 달. 모양이 아니면 이번 달이다 — 스타트업 화면과 **같은 판정**이다.

    화면을 여는 데까지만 이렇게 한다. **보낼 때는 짐작하지 않는다**
    (`create_send_list` 가 달이 없으면 거절한다) — 글에 `7월 말까지` 라고
    적혀 나가는 자리라, 짐작이 틀리면 그 거짓말이 그대로 대표에게 간다.
    """
    return value if ir_monthly.is_month(value) else ir_monthly.this_month()


@router.get("/deals/startup-ir", response_class=HTMLResponse)
def startup_ir_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    month: str = "",
    msg: str = "",
):
    """그 달에 **누구에게 무엇이 나가는지** — 누르기 전에 보는 표.

    못 보내는 줄도 **남는다**(방 이름 없음 · 요청 없음). 빼 버리면 계약 기업인데
    왜 안 보이는지 화면에서 물을 수가 없고, 매달 같은 기업만 조용히 빠져도
    아무도 모른다(`services/startup_send.rows`).
    """
    _guard(db, user)
    selected = _month(month)
    months = startup_send.months(db)
    if selected not in months:
        months = sorted(set(months) | {selected}, reverse=True)
    ctx = base_ctx(request, db, user, ACTIVE)
    ctx.update(startup_send.rows(db, selected))
    ctx.update({
        "months": months,
        "selected": selected,
        "label": startup_send.LABEL,
        "no_room_label": startup_send.NO_ROOM,
        "msg": msg,
        # 회차명은 **보내는 날에서 만든다.** 손으로 적으면 이력이 갈라진다 —
        # 딜 제안 관리 화면과 같은 자리에서 가져온다(`cadence`).
        "default_title": cadence.default_batch_title(
            db, label=f"{startup_send.LABEL} {selected}"),
    })
    return templates.TemplateResponse("startup_send.html", ctx)


@router.post("/deals/startup-ir/send", include_in_schema=False)
def make_draft(
    background: BackgroundTasks,
    company_ids: List[int] = Form(default=[]),
    month: str = Form(""),
    title: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[대기 목록 만들기] — **세우기만 한다. 한 통도 나가지 않는다.**

    `draft` 로 서고, 그 계정이 진행 화면에서 [발송 시작] 을 눌러야 나간다.
    만들고 나서 상태를 고치는 방법도 있지만, 만드는 것과 고치는 것 사이에
    발송기가 폴링하면 **사람이 누르기 전에 나간다** — 세울 때 정해야 그 틈이
    없어서 `draft=True` 를 넘긴다(`deals.SendRequest.draft`).

    ## 거절은 조용하지 않다

    방 이름이 없거나 그 달에 실을 줄이 없는 기업이 섞이면 `create_send_list` 가
    **목록 전체를 거절한다.** 그 사유를 그대로 화면에 되돌려 준다 — 조용히 빼고
    나머지만 보내면 몇 곳에 나갔는지 아무도 모른다.
    """
    _guard(db, user)
    from .deals import MODE_STARTUP, SendRequest, create_send_list

    if not ir_monthly.is_month(month):
        return _back(month, "달을 고르세요")
    if not company_ids:
        return _back(month, "보낼 기업을 하나 이상 고르세요")

    # 화면이 거른 것과 여기서 거르는 것이 **같은 함수**를 지난다. 갈리면 화면에서
    # 못 고르는 줄이 주소로는 들어간다.
    allowed = set(startup_send.sendable_ids(db, month))
    unknown = [cid for cid in company_ids if cid not in allowed]
    if unknown:
        return _back(month, "보낼 수 없는 기업이 섞였습니다 — 목록을 다시 보세요")

    try:
        made = create_send_list(
            SendRequest(contact_ids=company_ids, mode=MODE_STARTUP,
                        month=month, draft=True,
                        title=(title or "").strip() or None),
            background, db=db, user=user)
    except HTTPException as exc:
        # `create_send_list` 가 말하고 멈춘 사유를 그대로 옮긴다. 여기서 다시
        # 지어내면 화면의 말과 실제로 막힌 까닭이 갈린다.
        return _back(month, str(exc.detail))

    # 진행 화면이 곧 대기 목록이다 — 누구에게 어느 방으로 가는지가 줄마다 있고,
    # [발송 시작] 이 거기 있다.
    return RedirectResponse(f"/jobs/{made['job_id']}", status_code=303)


def _back(month: str, why: str) -> RedirectResponse:
    """목록으로 되돌리며 **까닭을 적는다.**"""
    return RedirectResponse(
        f"/deals/startup-ir?month={quote(month or '')}&msg={quote(why)}",
        status_code=303)
