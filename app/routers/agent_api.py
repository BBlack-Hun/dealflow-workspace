"""Agent queue protocol (ROADMAP task 1.6, TECH_SPEC §4).

All endpoints require `Authorization: Bearer <agent_token>`.

    GET  /api/agent/poll               -> one running job (atomically claimed) or 204
    GET  /api/agent/jobs/{id}/state    -> 발송 **직전** 확인 (아직 보내도 되는가)
    POST /api/agent/items/{id}/result  -> {status: sent|failed, error?, screenshot_b64?}
    POST /api/agent/jobs/{id}/status   -> {status, counters}
    POST /api/agent/heartbeat          -> refresh last_poll_at (connection badge)

Job claim is atomic: UPDATE ... WHERE status='queued' (row-count guarded) so a
job is never handed to two agents. Web app and agent never share the DB — HTTP only.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import and_, exists, select, text
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..services import cadence, pipeline
from ..deps import get_agent_device, now_iso
from ..models import AgentDevice, SendItem, SendJob

router = APIRouter(prefix="/api/agent", tags=["agent"])

AGENT_LOG_DIR = config.BASE_DIR / "agent_logs"

# 문구를 실제로 전송하는 잡 종류.
SEND_KINDS = ("deal_intro", "ir_delivery")
# 방 이름만 대조하는 잡 (ROADMAP 2.5). 전송하지 않는다.
VERIFY_KIND = "verify_room"

VERIFY_VERDICTS = ("verified", "not_found", "ambiguous")
VERIFY_ERRORS = {
    "not_found": "카톡에서 같은 이름의 방을 찾지 못했습니다 (방 제목을 확인하세요)",
    "ambiguous": "같은 이름의 방이 여러 개입니다 (카톡에서 방 이름을 고유하게 바꾸세요)",
}


def _requested_kinds(kinds: Optional[str]) -> list:
    """에이전트가 처리할 수 있다고 밝힌 잡 종류.

    기본값에 verify_room 을 넣지 않는 것이 핵심이다. 이미 각자 PC에 깔려 도는
    **구버전 에이전트**는 잡 종류를 보지 않고 무조건 문구를 전송하므로, 확인 잡이
    그쪽으로 흘러가면 안 된다. 새 에이전트만 ?kinds= 로 명시해 받아간다.
    """
    wanted = [k.strip() for k in (kinds or "").split(",") if k.strip()]
    return wanted or list(SEND_KINDS)


def _touch_device(db: Session, device: AgentDevice, hostname: Optional[str] = None,
                  version: Optional[str] = None, sender: Optional[str] = None) -> None:
    device.last_poll_at = now_iso()
    if hostname:
        device.hostname = hostname
    if version:
        device.agent_version = version
    if sender:
        device.sender = sender


def _agent_items(job: SendJob) -> list:
    """발송 프로그램이 **집어갈 수 있는** 대기 건. 만든 순서대로.

    내주는 기준(`poll`)과 "다 끝났는가" 판정 기준(`job_status_update`)이 **반드시
    같아야 한다.** 두 곳에 따로 적으면 한쪽만 어긋나서, 안 나간 사람을 두고
    회차가 완료로 끝나거나(지금 고치는 버그) 반대로 영영 안 끝난다.

    - 메일 건은 서버가 SMTP 로 직접 보낸다(`services/mail_sender.py`). 발송
      프로그램이 집어가면 메일 주소를 방 제목으로 알고 카톡방을 찾다가 실패한다.
      완료 판정에서도 빼야 한다 — 여기서 세면 카톡을 다 보내고도 메일 건이
      대기로 남아 잡을 계속 큐로 되돌리게 된다.
    - IR 자료 전달은 링크가 순서대로 나가야 하는데 관계에서 그냥 꺼내면 순서가
      보장되지 않아 id 로 정렬한다. **매번 같은 순서**여야 여러 번에 나눠 보낼 때
      회분이 앞으로 나아간다(같은 60건을 다시 집어가면 안 된다).
    """
    return sorted((i for i in job.items
                   if i.status == "pending" and i.channel != "email"),
                  key=lambda i: i.id)


@router.get("/poll")
def poll(
    response: Response,
    kinds: Optional[str] = None,
    cap: Optional[int] = None,
    files: int = 0,
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    """Atomically claim the oldest queued job for this agent's user and return it.

    `kinds` (CSV) = 이 에이전트가 처리할 수 있는 잡 종류. 생략하면 발송 잡만 준다.
    `cap` = 이 에이전트가 한 번에 처리할 건수 상한(계정 보호). 아래 참고.
    `files` = 자료 파일을 붙여 보낼 수 있는가. 아래 참고.
    """
    _touch_device(db, device)

    # ★ 자료 파일이 실린 잡은 **파일을 붙일 줄 아는 발송기에만** 내준다.
    #
    # `kinds` 와 **같은 이유·같은 방식**이다. 이 칸을 모르는 구버전 발송기는
    # `files` 를 그냥 무시하고 **문구만 보낸다** — 그러면 "1번 기업 … 자료
    # 전달드리겠습니다" 만 나가고 자료가 없다. 자료 전달에서 그것이 제일 나쁜
    # 결과다(`agent/main.py: send_item` 참고). 버전으로 가리지 않는 이유도
    # `kinds` 와 같다: 버전은 짐작이고, 밝힌 것은 사실이다.
    #
    # 못 내주는 잡은 **큐에 그대로 둔다.** 실패로 닫으면 사람이 다시 만들어야
    # 하는데, 여기서 막힌 이유는 발송기를 갱신하면 사라지는 것이다
    # (`/setup` 에서 다시 내려받으면 그다음 폴링에 그대로 이어 나간다).
    can_attach = bool(files)

    # Find a candidate queued job owned by this agent's user.
    query = (
        select(SendJob.id)
        .where(SendJob.status == "queued", SendJob.user_id == device.user_id,
               SendJob.kind.in_(_requested_kinds(kinds)))
    )
    if not can_attach:
        query = query.where(~exists().where(and_(SendItem.job_id == SendJob.id,
                                                 SendItem.files_json.isnot(None))))
    candidate = db.execute(
        query.order_by(SendJob.id).limit(1)
    ).scalar_one_or_none()

    if candidate is None:
        db.commit()
        return Response(status_code=204)

    # Atomic claim: only succeeds if still queued.
    result = db.execute(
        text("UPDATE send_jobs SET status='running', started_at=:t "
             "WHERE id=:id AND status='queued'"),
        {"t": now_iso(), "id": candidate},
    )
    if result.rowcount == 0:
        # Someone else claimed it between select and update.
        db.commit()
        return Response(status_code=204)

    db.commit()

    job = db.get(SendJob, candidate)
    pending_items = _agent_items(job)

    # ★ 한 번에 내주는 건수의 상한은 **에이전트가 정한다** (`?cap=`).
    #
    # 상한 자체는 계정 보호용이라 필요하다. 문제는 그 숫자가 에이전트에만 있고
    # 서버는 몰랐다는 것이다 — 서버가 97건을 통째로 내주면 에이전트는 앞 60건만
    # 처리하고 **나머지 37건을 버린 채** 잡을 완료로 끝냈다(회차 13에서 실제로
    # 발생). 서버가 60건만 내주면 애초에 버릴 것이 없다.
    #
    # 그렇다고 서버가 자기 상한값을 따로 들고 있으면 두 숫자가 또 어긋난다.
    # 값은 `agent/main.py: DEFAULT_CONFIG["job_cap"]`(사용자는 config.yaml 로
    # 조절) **한 곳**에만 두고, 서버는 에이전트가 말한 값을 지킬 뿐이다.
    #
    # 상한을 말하지 않는 구버전 에이전트에게는 지금까지처럼 전부 내준다. 그쪽은
    # 여전히 앞 60건만 처리하지만, 남은 건은 `job_status_update` 가 다시 큐로
    # 돌려 다음 폴링에 이어 보낸다 — 그래서 **에이전트를 갱신하지 않아도** 사람이
    # 빠지지 않는다.
    if cap and cap > 0:
        pending_items = pending_items[:cap]

    return {
        "job_id": job.id,
        "kind": job.kind,
        "items": [
            {"id": i.id, "room_name": i.room_name, "message": i.message, "stage": i.stage,
             # 여러 통으로 나눠 보낼 때의 순서. 이 칸을 모르는 예전 발송
             # 프로그램은 message(합친 전문)를 한 통으로 보낸다 — 순서는 같다.
             **({"parts": json.loads(i.parts_json)} if i.parts_json else {}),
             # 함께 붙여 보낼 자료의 **파일 이름**(경로가 아니다 — 자료 폴더는
             # PC 마다 다르고 발송기가 조립한다). 차례대로 파일을 먼저 보내고
             # 문구를 마지막에 보낸다.
             #
             # 파일이 실린 잡은 붙일 줄 아는 발송기에만 내준다(위 `can_attach`) —
             # 여기까지 왔다는 것은 그 발송기라는 뜻이다.
             **({"files": json.loads(i.files_json)} if i.files_json else {}),
             # 방 확인 잡에만 검색어(이름+직함)를 함께 준다. message 는 빈 채로 두어
             # 구버전 에이전트가 이 잡을 발송으로 오해해도 보낼 내용이 없게 한다.
             **({"query": f"{i.contact.name} {i.contact.title or ''}".strip(),
                 # 직함이 시트와 실제 방에서 다른 경우가 있어(이직·표기 차이)
                 # 이름만으로 재검색할 수 있게 함께 준다. 동명이인은 회사로 가린다.
                 "name": i.contact.name,
                 "firm": i.contact.firm or ""}
                if job.kind == "verify_room" and i.contact is not None else {})}
            for i in pending_items
        ],
    }


class ItemResult(BaseModel):
    status: str  # sent | failed
    error: Optional[str] = None
    screenshot_b64: Optional[str] = None
    # kind=verify_room 잡에서만: verified | not_found | ambiguous
    verify_result: Optional[str] = None
    # 검색으로 찾아낸 실제 방 제목(단일 후보일 때만). 방 이름은 생성으로 맞출 수
    # 없어서, 확인 잡이 곧 '방 이름 알아내기' 역할을 한다.
    found_room: Optional[str] = None
    candidates: Optional[list] = None


@router.post("/items/{item_id}/result")
def item_result(
    item_id: int,
    body: ItemResult,
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    _touch_device(db, device)
    item = db.get(SendItem, item_id)
    if item is None:
        db.commit()
        return {"ok": False, "detail": "item not found"}

    # Guard: don't overwrite a canceled item (e.g. user hit [중단] mid-flight).
    if item.status == "canceled":
        db.commit()
        return {"ok": True, "detail": "item canceled, result ignored"}

    job = item.job
    if job is not None and job.kind == VERIFY_KIND:
        _apply_verify_result(item, body)
    elif body.status == "sent":
        item.status = "sent"
        item.sent_at = now_iso()
        item.error = None
        # 후속은 **성공한 뒤에만** 잡는다. 발송 목록을 만든 시점에 잡으면
        # 실패한 건까지 예약되어, 받은 적 없는 사람에게 "지난번 공유드린" 이 나간다.
        cadence.start_or_advance(db, item, job)
        if job is not None and job.kind == "ir_delivery":
            # 보내고 나서 다시 화면으로 돌아와 '전달함'을 누르게 하면
            # 바쁠 때 그 한 번을 빼먹는다.
            pipeline.close_requests_for(db, job, item.contact_id)
    else:
        item.status = "failed"
        item.error = body.error or "unknown error"
        if body.screenshot_b64:
            item.screenshot_path = _save_screenshot(item_id, body.screenshot_b64)

    # Recompute job counters from items (source of truth).
    job.sent = sum(1 for i in job.items if i.status == "sent")
    job.failed = sum(1 for i in job.items if i.status == "failed")
    db.commit()
    return {"ok": True}


def _apply_verify_result(item: SendItem, body: ItemResult) -> None:
    """방 연결 확인 결과를 담당자 배지(vc_contacts.room_verified)에 반영한다.

    화면에서는 '성공/실패'로 읽히는 편이 자연스러우므로 verified 만 sent 로 두고
    not_found/ambiguous 는 사유가 보이도록 failed 로 남긴다 — 고쳐야 할 방이
    실패 목록에 그대로 뜬다.
    """
    # 판정을 못 받았으면 '확인됨'으로 올리지 않는다 — 모르면 미확인 쪽이 안전하다.
    verdict = body.verify_result if body.verify_result in VERIFY_VERDICTS else "not_found"

    contact = item.contact
    if contact is not None:
        contact.room_verified = verdict
        # ★ 검색으로 찾아낸 실제 방 제목을 저장한다.
        # 방 이름은 우리가 만들어 맞출 수 없다(접미사·담당자명이 방마다 다름).
        # 확인 잡이 사실상 '방 이름 알아내기'이므로 결과를 반영해야 발송이 된다.
        if verdict == "verified" and body.found_room:
            found = body.found_room.strip()
            if found and found != contact.kakao_room_name:
                item.room_name = found
                contact.kakao_room_name = found
    item.status = "sent" if verdict == "verified" else "failed"
    item.sent_at = now_iso() if verdict == "verified" else None
    item.error = None if verdict == "verified" else (
        body.error or VERIFY_ERRORS.get(verdict, verdict)
    )


def _save_screenshot(item_id: int, b64: str) -> Optional[str]:
    try:
        AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = AGENT_LOG_DIR / f"{item_id}.png"
        path.write_bytes(base64.b64decode(b64))
        return str(path.relative_to(config.BASE_DIR))
    except Exception:  # noqa: BLE001 - screenshot is best-effort
        return None


# 이 상태가 되면 에이전트는 **남은 건을 보내지 않는다**.
#
# canceled 는 물론이고, 이미 끝난 것으로 표시된 잡을 계속 보내면 같은 사람에게
# 두 번 나간다. paused 도 화면에는 '멈춤' 으로 보이므로 계속 보내면 화면과
# 실제가 어긋난다 — 화면에 안 보이는 발송이 제일 위험하다.
STOP_STATUSES = ("canceled", "done", "done_with_errors", "paused")


@router.get("/jobs/{job_id}/state")
def job_state(
    job_id: int,
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    """발송 **직전**에 에이전트가 물어보는 가벼운 경로.

    ## 왜 필요했나

    화면의 [중단]은 서버 DB 만 바꿨다(잡을 canceled 로, 대기 건을 canceled 로).
    그런데 에이전트는 폴링할 때 items 를 통째로 받아 메모리에 들고 끝까지
    돌았다 — 중간에 다시 묻지 않으니 [중단]을 눌러도 카톡은 계속 나갔다.
    `item_result` 가 취소된 건의 결과를 거부하긴 하지만 그때는 이미 나간
    뒤다. 기록만 안 남을 뿐 상대는 받았다. 즉 [중단]이 '발송을 멈추는'
    버튼이 아니라 '기록을 멈추는' 버튼이었다.

    건 사이에 이미 3~7초를 쉬므로(사람 흉내) 여기서 한 번 더 묻는 비용은
    무시할 만하다.

    `POST /jobs/{id}/status` 는 에이전트가 **알리는** 것, 이 `GET
    /jobs/{id}/state` 는 **묻는** 것이다. 이름이 비슷하니 헷갈리지 말 것.

    돌려주는 값::

        {"ok": true, "job_id": 12, "status": "running",
         "canceled": false, "canceled_items": []}

    - ``canceled`` — 이 잡의 발송을 멈춰야 하는가. 에이전트는 **이 값 하나만**
      보면 된다. 판정 기준(``STOP_STATUSES``)이 늘어도 에이전트를 다시
      배포하지 않아도 된다.
    - ``canceled_items`` — 잡은 살아 있는데 **이 건들만** 취소된 경우.
      건 단위로 취소·되돌리는 화면이 생겨도 에이전트를 고치지 않게 함께 준다.

    없는 잡·남의 잡은 ``canceled: true`` 로 답한다. 모르면 보내지 않는 쪽이
    안전하다 — 잘못 물어본 에이전트가 계속 보내는 것보다 멈추는 게 낫다.
    """
    _touch_device(db, device)
    job = db.get(SendJob, job_id)
    if job is None or job.user_id != device.user_id:
        db.commit()
        return {"ok": False, "detail": "job not found", "job_id": job_id,
                "status": "unknown", "canceled": True, "canceled_items": []}

    canceled_items = [i.id for i in job.items if i.status == "canceled"]
    db.commit()
    return {"ok": True, "job_id": job.id, "status": job.status,
            "canceled": job.status in STOP_STATUSES,
            "canceled_items": canceled_items}


class JobStatusUpdate(BaseModel):
    # running            — 아직 돌고 있다
    # done / done_with_errors / queued
    #                    — 이번 회분은 손을 뗐다. **끝났는지는 서버가 다시 판정한다**
    #                      (아래 `_settle`). queued 는 "상한에 걸려 남은 게 있다" 는
    #                      새 에이전트의 보고다.
    # paused             — 물어보지 못해 스스로 멈췄다. 사람이 봐야 한다
    status: str
    sent: Optional[int] = None
    failed: Optional[int] = None


# 에이전트가 "이 회분은 손을 뗐다" 고 알리는 값들. 여기 걸리면 `_settle` 이
# 잡의 실제 상태를 다시 정한다 — 에이전트의 말을 그대로 믿지 않는다.
BATCH_END_STATUSES = ("done", "done_with_errors", "queued")


def _made_progress(job: SendJob) -> bool:
    """이번에 잡을 물고 나서 **한 건이라도 손댔는가**.

    큐로 되돌리는 것을 무한히 반복하지 않기 위한 판정이다. 아무것도 처리하지
    못하는 상태(발송기가 죽어 결과를 못 올린다든지, 에이전트가 제 쪽에서 건들을
    통째로 걸러 버린다든지)에서 계속 되돌리면, 폴링할 때마다 같은 잡을 물고 같은
    자리에서 끝나 영원히 돈다.

    ## 어떻게 판정하나

    잡을 물 때 `started_at` 을 새로 찍는다(위 poll 의 원자적 선점). 그러니
    **대기에서 벗어난 건 중에 그 시각 이후에 바뀐 것**이 하나라도 있으면 이번
    회분이 일을 한 것이다. 결과가 올라오면 그 건의 `updated_at` 이 갱신된다
    (`models.TimestampMixin.onupdate`).

    새 칸을 만들지 않고 이미 있는 두 시각으로 판정한다 — 이 판정 하나 때문에
    스키마를 늘리면 운영 DB 이관이 따라붙는다.

    시각 문자열은 `app/clock.py` 한 곳에서만 적으므로 형식이 같고, 그대로 견줘도
    된다. 다만 초 단위까지만 적어서 **같은 초 안에** 벌어진 일은 '진행 있음' 으로
    읽힌다(`>=`). 그 쪽으로 틀리는 편이 안전하다 — 실제로 보낸 회분을 진행 없음으로
    보면 남은 사람이 또 대기로 묶인다. 그래도 다음 폴링은 다른 초에 일어나므로
    되돌림이 무한히 이어지지는 않는다(막아야 할 것은 반복이지 한 번의 여유가 아니다).
    """
    started = job.started_at or ""
    return any((i.updated_at or "") >= started
               for i in job.items if i.status != "pending")


def _settle(job: SendJob) -> str:
    """회분 보고를 받고 **잡이 실제로 끝났는지** 서버가 판정한다.

    ## 왜 서버가 판정하나

    에이전트는 상한(job_cap)에 걸려 앞 60건만 처리하고도 잡 **전체**를 `done` 으로
    보고했다. 서버가 그 말을 그대로 받아 적어서, 97명 중 60명만 나간 회차가 화면에
    '완료' 로 끝났다 — 대기 37명이 남아 있는데도. 화면이 끝났다고 하니 안 나간 것을
    사람이 알아챌 방법이 없었다.

    각자 PC 의 발송 프로그램은 한동안 구버전이 섞여 돈다. 그러니 **서버에서**
    막아야 에이전트를 갱신하지 않은 사람에게도 이 버그가 사라진다.

    ## 판정

    - 대기 건이 남았고 이번 회분이 일을 했다 → `queued`. 다음 폴링에서 **남은
      건만** 이어 나간다(poll 이 대기 건만 내주므로 받은 사람에게 또 가지 않는다).
    - 대기 건이 남았는데 이번 회분이 아무것도 못 했다 → `paused`. 되돌려 봐야
      같은 자리에서 끝나니 멈추고 사람이 보게 한다. `paused` 는 poll 이 집어가지
      않아(`WHERE status='queued'`) 반복이 여기서 끊긴다.
    - 남은 게 없다 → 이제 진짜 끝. `done`/`done_with_errors` 는 에이전트의 말이
      아니라 **건들을 보고** 정한다. 여러 회분에 나눠 보내면 마지막 회분만
      성공해도 에이전트는 `done` 이라고 하는데, 그러면 앞 회분의 실패가 화면에서
      사라진다([실패 재시도] 버튼이 안 뜬다).

    남은 건을 이어 보내는 판단은 **결과 보고(`item_result`)가 유일한 근거**다.
    보낸 뒤 결과 보고가 통째로 유실되면 그 사람에게 다시 나갈 수 있다. 그래도
    안 보내고 완료로 끝내는 쪽보다 낫다 — 안 나간 것은 아무도 모르지만, 두 번
    나간 것은 상대가 알려 준다.
    """
    if _agent_items(job):
        return "queued" if _made_progress(job) else "paused"
    return "done_with_errors" if any(i.status == "failed" for i in job.items) else "done"


@router.post("/jobs/{job_id}/status")
def job_status_update(
    job_id: int,
    body: JobStatusUpdate,
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    _touch_device(db, device)
    job = db.get(SendJob, job_id)
    if job is None:
        db.commit()
        return {"ok": False, "detail": "job not found"}

    # If the user canceled while the agent was working, keep it canceled.
    if job.status == "canceled":
        db.commit()
        return {"ok": True, "detail": "job canceled"}

    settled = None
    if body.status in BATCH_END_STATUSES:
        settled = _settle(job)
    elif body.status in ("running", "paused"):
        settled = body.status

    if settled:
        job.status = settled
        # 다시 큐로 돌린 잡에 끝난 시각이 남아 있으면 화면에서 끝난 것으로 읽힌다.
        job.finished_at = now_iso() if settled in ("done", "done_with_errors") else None
    job.sent = sum(1 for i in job.items if i.status == "sent")
    job.failed = sum(1 for i in job.items if i.status == "failed")
    db.commit()
    # `pending` 은 왜 안 끝났는지 에이전트 로그에서 바로 보이라고 함께 준다.
    return {"ok": True, "status": job.status, "pending": len(_agent_items(job))}


class Heartbeat(BaseModel):
    hostname: Optional[str] = None
    agent_version: Optional[str] = None
    sender: Optional[str] = None


@router.post("/heartbeat")
def heartbeat(
    body: Heartbeat,
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    _touch_device(db, device, hostname=body.hostname, version=body.agent_version,
                  sender=body.sender)
    db.commit()
    # IR 자료 폴더 자리를 **여기에 실어 내려보낸다.** 발송기가 이미 주기적으로
    # 두드리는 통로라 새로 팔 것이 없고, 화면에서 값을 고치면 다음 박동에
    # 그대로 따라간다(발송기를 다시 켤 필요가 없다).
    return {"ok": True, "server_time": now_iso(),
            "ir_root": device.ir_root or ""}


class Diagnostics(BaseModel):
    """에이전트가 올리는 진단 스냅샷.

    사용자의 Windows PC는 별도 기기라 원격에서 명령을 돌릴 수 없다.
    대신 에이전트가 스스로 상태를 수집해 서버로 보내면, 서버 쪽에서
    원인을 확인할 수 있다(카톡 창 제목 불일치·포커스 실패 진단용).
    """
    kind: Optional[str] = None            # startup | send_failed | manual
    agent_hostname: Optional[str] = None  # 에이전트가 도는 PC 이름
    platform: Optional[str] = None
    sender: Optional[str] = None
    foreground_window: Optional[str] = None
    window_titles: Optional[list] = None  # 열려 있는 창 제목 전체
    target_room: Optional[str] = None     # 보내려던 방
    error: Optional[str] = None
    log_tail: Optional[str] = None        # 최근 로그 몇 줄


@router.post("/diagnostics")
def diagnostics(
    body: Diagnostics,
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    """진단 스냅샷을 파일로 남긴다 (data/agent_reports.log).

    DB 스키마를 늘리지 않고도 서버에서 바로 열어볼 수 있게 로그 파일로 적재한다.
    """
    from .. import config as _config

    line = {
        "at": now_iso(),
        "user_id": device.user_id,
        "hostname": device.hostname,
        **body.model_dump(exclude_none=True),
    }
    try:
        path = Path(_config.DATA_DIR) / "agent_reports.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True}
