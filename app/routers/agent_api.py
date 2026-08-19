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
    db: Session = Depends(get_db),
    device: AgentDevice = Depends(get_agent_device),
):
    """Atomically claim the oldest queued job for this agent's user and return it."""
    _touch_device(db, device)

    # Find a candidate queued job owned by this agent's user.
    candidate = db.execute(
        select(SendJob.id)
        .where(SendJob.status == "queued", SendJob.user_id == device.user_id)
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
            {"id": i.id, "room_name": i.room_name, "message": i.message, "stage": i.stage}
            for i in pending_items
        ],
    }


class ItemResult(BaseModel):
    status: str  # sent | failed
    error: Optional[str] = None
    screenshot_b64: Optional[str] = None


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

    if body.status == "sent":
        item.status = "sent"
        item.sent_at = now_iso()
        item.error = None
    else:
        item.status = "failed"
        item.error = body.error or "unknown error"
        if body.screenshot_b64:
            item.screenshot_path = _save_screenshot(item_id, body.screenshot_b64)

    # Recompute job counters from items (source of truth).
    job = item.job
    job.sent = sum(1 for i in job.items if i.status == "sent")
    job.failed = sum(1 for i in job.items if i.status == "failed")
    db.commit()
    return {"ok": True}


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
