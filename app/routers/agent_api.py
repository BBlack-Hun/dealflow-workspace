"""Agent queue protocol (ROADMAP task 1.6, TECH_SPEC §4).

All endpoints require `Authorization: Bearer <agent_token>`.

    GET  /api/agent/poll               -> one running job (atomically claimed) or 204
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
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
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


@router.get("/poll")
def poll(
    response: Response,
    kinds: Optional[str] = None,
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    """Atomically claim the oldest queued job for this agent's user and return it.

    `kinds` (CSV) = 이 에이전트가 처리할 수 있는 잡 종류. 생략하면 발송 잡만 준다.
    """
    _touch_device(db, device)

    # Find a candidate queued job owned by this agent's user.
    candidate = db.execute(
        select(SendJob.id)
        .where(SendJob.status == "queued", SendJob.user_id == device.user_id,
               SendJob.kind.in_(_requested_kinds(kinds)))
        .order_by(SendJob.id)
        .limit(1)
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
    pending_items = [i for i in job.items if i.status == "pending"]
    return {
        "job_id": job.id,
        "kind": job.kind,
        "items": [
            {"id": i.id, "room_name": i.room_name, "message": i.message, "stage": i.stage,
             # 방 확인 잡에만 검색어(이름+직함)를 함께 준다. message 는 빈 채로 두어
             # 구버전 에이전트가 이 잡을 발송으로 오해해도 보낼 내용이 없게 한다.
             **({"query": f"{i.contact.name} {i.contact.title or ''}".strip()}
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


class JobStatusUpdate(BaseModel):
    status: str  # running | done | done_with_errors | paused
    sent: Optional[int] = None
    failed: Optional[int] = None


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

    if body.status in ("done", "done_with_errors", "running", "paused"):
        job.status = body.status
        if body.status in ("done", "done_with_errors"):
            job.finished_at = now_iso()
    job.sent = sum(1 for i in job.items if i.status == "sent")
    job.failed = sum(1 for i in job.items if i.status == "failed")
    db.commit()
    return {"ok": True, "status": job.status}


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
    return {"ok": True, "server_time": now_iso()}


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
