"""스타트업 월간 발송 — 딜 제안 관리 **안**의 자리.

## 왜 스타트업 메뉴가 아니라 여기인가

스타트업 메뉴는 **명단과 자료를 보는 화면**이고
(`/startup`, `/startup/ir-report*` 는 그대로 있다), 딜 제안 관리는 **보내는
화면**이다 — 회차를 만들고, 누구에게 어느 방으로 가는지 보고, 진행을 지켜본다.
보내는 일이 명단 화면에 섞여 있으면 명단을 보러 온 사람 앞에 발송 단추가 선다.

## 자리가 둘이다 — 보내는 표와 **맞추는 표**

`/deals/startup-ir` 은 보내는 표다. `/deals/startup-ir/rooms` 는 **방 제목을
맞추는 표**이고, 왜 갈라 두었는지는 그 라우트에 적어 두었다.

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
from ..models import IrCompany, SendItem, SendJob, User
from ..services import cadence, ir_monthly, room_match, startup_send
from ..ui import base_ctx
# 방 확인 잡의 종류는 **한 곳에만 적는다**(`agent_api.VERIFY_KIND`). 여기에
# 글자를 한 벌 더 두면 잡은 서는데 발송기가 집어가지 않는 날이 온다 —
# `services/startup_send.KIND` 머리말이 같은 사고를 적어 두었다.
from .agent_api import VERIFY_KIND

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
    return value if ir_monthly.is_month(value) else startup_send.default_month()


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


# ── 대표 카톡방 맞추기 ──────────────────────────────────────────────────────
#
# 왜 보내는 표 **안**이 아니라 따로인가
#
#   · 보내는 표는 **달마다 보는 표**다(`선택한 달 말까지 몇 줄`). 방 제목은
#     달과 상관이 없다 — 한 번 맞추면 다음 달에도 그 방이다. 한 표에 섞으면
#     달을 바꿀 때마다 맞추던 자리가 다시 그려진다.
#   · 보내는 표는 **누르기 전에 보는 표**다(그 파일 머리말). 그 표에 고치는
#     칸과 [카톡에서 방 찾기] 단추가 서면, 보낼지 보고 있던 사람 앞에 고치는
#     일이 끼어든다.
#   · 보내는 표는 **못 보내는 줄도 남긴다.** 맞추는 표도 같은 규칙이지만
#     남기는 까닭이 다르다(여기서는 `후보 없음`·`이미 맞춰짐`이다).
#
# 길은 보내는 표의 `방 이름 없음` 안내에서 이어진다 — 지금까지 그 안내가
# 가리키던 `IR 기업 현황` 의 [수정] 창이 **기업마다 한 번씩 여는 자리**라서
# 수십 곳을 채울 수가 없었다. 이 표는 **계약 기업 전부가 한 판에** 선다.


@router.get("/deals/startup-ir/rooms", response_class=HTMLResponse)
def rooms_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    msg: str = "",
):
    """[대표 카톡방 맞추기] — 계약 기업 **전부**가 한 판에 서는 표.

    줄마다 셋이 선다: **카톡에서 찾아온 후보**(눌러서 넣는다) · **규칙으로
    지어 본 초안**(초안이라고 적혀 있다) · **직접 적는 칸**. 셋 다 같은 칸
    하나로 모이고, [저장] 한 번에 바뀐 줄만 들어간다.

    **고르는 것은 사람이다.** 서버는 후보를 세워 주기만 한다 — 왜 하나뿐인
    후보도 서버가 집어넣지 않는지는 `services/room_match.py` 머리말에 있다.
    """
    _guard(db, user)
    ctx = base_ctx(request, db, user, ACTIVE)
    ctx.update(room_match.rows(db))
    ctx.update({
        "label": startup_send.LABEL,
        "msg": msg,
        "no_room_label": startup_send.NO_ROOM,
    })
    return templates.TemplateResponse("startup_room.html", ctx)


@router.post("/deals/startup-ir/rooms", include_in_schema=False)
def save_rooms(
    company_ids: List[int] = Form(default=[]),
    rooms: List[str] = Form(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[저장] — 줄마다 적힌 방 제목을 **바뀐 것만** 넣는다.

    ## 왜 폼 하나로 받나

    수십 곳을 한 판에 다루는 것이 이 화면의 전부다. 줄마다 따로 저장하면(칸을
    눌러 고치는 다른 표들처럼) 수십 번 눌러야 하고, 어디까지 했는지를 사람이
    세게 된다. 한 번에 받고 **몇 줄이 들어갔는지 되돌려 적는다.**

    ## 왜 짝지은 두 목록인가

    `company_ids[i]` 와 `rooms[i]` 가 한 줄이다. 칸 이름에 기업 번호를 섞어
    (`room_12`) 받는 길도 있지만, 그러면 칸 이름을 만드는 규칙이 화면과 여기
    **두 벌**이 되고 한쪽만 고쳐지는 날 저장 단추가 아무 일도 안 한다.
    짝이 어긋나면 **한 줄도 넣지 않는다** — 어긋난 채로 넣으면 A 기업 칸의
    글자가 B 기업 방 이름이 되고, 그것이 곧 오발송이다.

    ## 적는 자리는 여기가 아니다

    `services/room_match.set_room` 하나다 — `IR 기업 현황` 의 [수정] 창도 그
    함수를 지난다. 확인 표시를 되돌리는 규칙이 거기 있고, 여기 한 줄 더 적으면
    이 화면으로 고친 기업만 `확인됨` 배지를 그대로 달고 있게 된다.

    ## 모르는 기업 번호는 **조용히 넘기지 않는다**

    화면에 선 줄과 여기서 받는 줄이 **같은 함수**로 갈린다
    (`room_match.company_ids`). 갈리면 화면에 없는 기업이 주소로는 들어간다 —
    `startup_send.sendable_ids` 가 보내는 쪽에서 하는 일과 같은 짝이다.
    """
    _guard(db, user)
    if len(company_ids) != len(rooms):
        return _back_rooms("보낸 줄이 어긋났습니다 — 화면을 새로 열고 다시 저장하세요")
    if not company_ids:
        return _back_rooms("저장할 줄이 없습니다")

    allowed = set(room_match.company_ids(db))
    changed, unknown = 0, 0
    for company_id, value in zip(company_ids, rooms):
        if company_id not in allowed:
            unknown += 1
            continue
        company = db.get(IrCompany, company_id)
        if company is not None and room_match.set_room(company, value):
            changed += 1
    db.commit()

    parts = [f"{changed}곳의 방 제목을 넣었습니다" if changed else "바뀐 줄이 없습니다"]
    if unknown:
        parts.append(f"계약 기업이 아닌 {unknown}줄은 넣지 않았습니다")
    return _back_rooms(" · ".join(parts))


@router.post("/deals/startup-ir/rooms/search", include_in_schema=False)
def search_rooms(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[카톡에서 방 찾기] — **회사명으로 카톡을 뒤져 후보를 모아 온다.**

    ## 새 잡 종류를 만들지 않는다  ★★

    이미 있는 **방 확인 잡**(`verify_room`)을 그대로 세운다. 그 잡은 발송기가
    카톡을 검색해 **방 제목 목록**을 올리는 잡이고(`agent/main.py:
    process_verify_job` → `sender.discover_rooms`), 그 목록이 곧 후보다.

    새 종류를 만들면 **그 종류를 모르는 발송기가 잡을 집어가지 않아 큐에 그대로
    선다** — 팀원 PC 에 깔린 발송기를 전부 다시 받게 해야 비로소 돌기 시작한다
    (`app/version.py` 의 0.9.0 · 0.10.0 설명이 그 일을 두 번 적어 두었다).
    `routers/setup.py` 의 시험용 방 확인 자리에 같은 판단이 이미 적혀 있다.
    그래서 **발송기를 한 줄도 안 고치고, 판도 안 올린다.**

    ## 한 통도 나가지 않는다

    `verify_room` 잡에서 발송기는 방을 열지도, 문구를 보내지도 않는다. 그래도
    `message=""` 로 둔다 — 혹시 아주 낡은 발송기가 이 잡을 발송으로 오해해도
    **보낼 내용이 없어** 실패로 끝난다(`routers/contacts.verify_rooms` 가 같은
    이유로 같은 값을 넣는다).

    ## `queued` 로 세운다

    대기 목록 만들기(`draft`)와 다르다. 저쪽은 **사람에게 카톡이 나가는** 일이라
    한 번 더 누르게 한다. 이쪽은 아무것도 나가지 않고 **읽기만** 하므로, 한 번
    더 누르게 할 까닭이 없다.
    """
    _guard(db, user)

    # 이미 맞춰 둔 기업도 **뺀다**. 맞춰 둔 이름이 있는데 검색 결과를 덮어쓰면,
    # 사람이 카톡에서 옮겨 적은 글자가 기계가 찾아온 후보에 묻힌다. 다시 찾을
    # 일이 있으면 방 제목을 비우고 누르면 된다.
    targets = [r["company"] for r in room_match.rows(db)["rows"]
               if not r["room"] and r["query"]]
    if not targets:
        return _back_rooms("찾을 기업이 없습니다 — 방 제목이 비어 있는 계약 기업만 찾습니다")

    job = SendJob(user_id=user.id, kind=VERIFY_KIND, status="queued",
                  total=len(targets), sent=0, failed=0)
    db.add(job)
    db.flush()
    for company in targets:
        db.add(SendItem(
            job_id=job.id,
            ir_company_id=company.id,
            # 아직 모르는 값이다. **지어 넣지 않는다** — 초안을 넣어 두면
            # 발송기가 후보를 못 찾았을 때 그 초안으로 방을 열어 보고
            # (`verify_room` 의 뒷길), 없는 방 이름이 `확인함` 쪽으로 기울 수
            # 있다. 빈 글자면 발송기가 그 자리에서 `not_found` 로 끝낸다.
            room_name="",
            message="",
            status="pending",
        ))
    db.commit()
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


def _back_rooms(why: str) -> RedirectResponse:
    """맞추는 표로 되돌리며 **무엇이 됐는지 적는다.** 조용히 돌아가면 저장이
    된 것인지 알 수 없다."""
    return RedirectResponse(f"/deals/startup-ir/rooms?msg={quote(why)}",
                            status_code=303)
