"""회차 준비 점검 — 발송일 전에 무엇이 막혀 있는지 한 번에 본다.

발송 당일에 "왜 안 나가지?"를 찾는 것은 늦다. 막히는 자리는 정해져 있다:
발송 프로그램이 안 켜져 있거나, 방 제목이 실제와 다르거나, 테스트 모드가
켜진 채(또는 꺼진 채)이거나, 보낼 기업이 안 골라져 있다.

각 항목은 **지금 어떤 상태인지**와 **무엇을 하면 되는지**를 함께 준다.
"괜찮음/주의/막힘" 세 단계로만 나눈다 — 더 나누면 무엇을 먼저 할지 흐려진다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..models import AgentDevice, IrCompany, MessageTemplate, SendItem, SendJob, User
from . import cadence, pipeline, sheet_owner
from .dashboard import _SENDABLE_ROOM, _room_state

OK = "ok"
WARN = "warn"
BLOCK = "block"

# 발송 프로그램이 이만큼 안 붙어 있으면 꺼진 것으로 본다.
AGENT_STALE_MIN = 5


def _check(level: str, title: str, detail: str, action: str = "",
           href: str = "") -> dict:
    return {"level": level, "title": title, "detail": detail,
            "action": action, "href": href}


def _agent_check(db: Session, user: User) -> dict:
    device = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == user.id)
    ).scalars().first()
    if device is None or not device.last_poll_at:
        return _check(BLOCK, "발송 프로그램", "한 번도 연결된 적이 없습니다",
                      "내 PC에 설치하고 켜 두세요", "/setup")
    try:
        mins = (datetime.now(timezone.utc)
                - datetime.fromisoformat(device.last_poll_at)).total_seconds() / 60
    except ValueError:
        return _check(BLOCK, "발송 프로그램", "연결 상태를 알 수 없습니다",
                      "다시 내려받아 설치하세요", "/setup")
    if mins > AGENT_STALE_MIN:
        return _check(BLOCK, "발송 프로그램",
                      f"{int(mins)}분째 연결이 끊겨 있습니다",
                      "그 PC에서 프로그램 창이 켜져 있는지 확인하세요", "/setup")
    sender = (device.sender or "").strip()
    if sender and sender.startswith("mock"):
        return _check(BLOCK, "발송 프로그램", "연습 모드로 붙어 있습니다",
                      "연습 모드에서는 실제로 보내지 않습니다", "/setup")
    return _check(OK, "발송 프로그램",
                  f"연결됨 · {device.hostname or '이름 없음'}", "", "/setup")


def _test_room_check(rehearsal: bool) -> dict:
    """테스트 방 설정. 리허설과 실발송에서 요구가 정반대다."""
    room = config.TEST_ROOM
    if rehearsal:
        if room:
            return _check(OK, "테스트 모드",
                          f"모든 발송이 '{room}' 방으로만 갑니다", "")
        return _check(BLOCK, "테스트 모드", "꺼져 있습니다",
                      "리허설인데 실제 담당자에게 나갑니다 — 켜고 다시 하세요")
    if room:
        return _check(BLOCK, "테스트 모드",
                      f"켜져 있습니다 — 전부 '{room}' 방으로만 갑니다",
                      "실발송 전에 꺼야 합니다")
    return _check(OK, "테스트 모드", "꺼짐 — 각 담당자 방으로 나갑니다", "")


def _targets_check(db: Session, user: User) -> List[dict]:
    contacts = sheet_owner.my_contacts(db, user)
    states = [_room_state(c) for c in contacts]
    sendable = sum(1 for s in states if s in _SENDABLE_ROOM)
    failed = sum(1 for s in states if s == "failed")
    missing = sum(1 for s in states if s == "missing")
    unverified = sum(1 for s in states if s == "unverified")

    out = []
    if sendable == 0:
        out.append(_check(BLOCK, "발송 대상", "보낼 수 있는 담당자가 없습니다",
                          "카톡방을 연결하세요", "/contacts"))
    else:
        out.append(_check(OK, "발송 대상",
                          f"{sendable}명 · 내 명단 {len(contacts)}명 중", "", "/contacts"))
    if failed or missing:
        out.append(_check(WARN, "방을 못 찾은 담당자",
                          f"{failed + missing}명에게는 나가지 않습니다",
                          "[방 연결 확인]을 돌리거나 방 제목을 고치세요", "/contacts"))
    if unverified:
        out.append(_check(WARN, "방 이름 미확인",
                          f"{unverified}명은 실제 방 제목과 대조하지 않았습니다",
                          "[방 연결 확인]을 돌리면 맞춰집니다", "/contacts"))
    return out


def _companies_check(db: Session) -> dict:
    companies = db.execute(select(IrCompany)).scalars().all()
    ready = [c for c in companies if c.introducible]
    if not ready:
        return _check(BLOCK, "소개할 기업", "소개 문구를 만들 수 있는 기업이 없습니다",
                      "한줄소개와 숫자를 채우세요", "/companies")
    return _check(OK, "소개할 기업", f"{len(ready)}개 · 등록 {len(companies)}개 중",
                  "", "/companies")


def _templates_check(db: Session, user: User) -> dict:
    kinds = {
        row.kind for row in db.execute(
            select(MessageTemplate).where(
                (MessageTemplate.user_id.is_(None))
                | (MessageTemplate.user_id == user.id))
        ).scalars().all()
    }
    need = {"opening_first", "closing_day1"}
    missing = need - kinds
    if missing:
        return _check(BLOCK, "발송 문구", "인사말 또는 안내문이 없습니다",
                      "문구를 만들어 두세요", "/templates")
    return _check(OK, "발송 문구", "인사말·안내문 준비됨", "", "/templates")


def _rehearsal_check(db: Session, user: User, today: date) -> dict:
    """최근에 테스트 방으로 실제 발송을 해 봤는가."""
    cutoff = (today - timedelta(days=7)).isoformat()
    recent = db.execute(
        select(func.count()).select_from(SendItem)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.user_id == user.id, SendItem.status == "sent",
               func.coalesce(SendItem.sent_at, "") >= cutoff)
    ).scalar() or 0
    if recent:
        return _check(OK, "최근 발송 확인", f"최근 7일 안에 {recent}건 성공", "")
    return _check(WARN, "최근 발송 확인", "최근 7일 안에 성공한 발송이 없습니다",
                  "테스트 모드를 켜고 한 건 보내 보세요", "/deals")


def _open_requests_check(db: Session, user: User) -> dict:
    """새 회차를 보내기 전에 지난 회차 요청부터 답해야 한다."""
    items = pipeline.today_items(db, user)
    overdue = items["overdue_requests"]
    if overdue:
        names = ", ".join(f"{r['name']}({r['company_name']})" for r in overdue[:3])
        return _check(WARN, "답 못 한 IR 요청",
                      f"{len(overdue)}건이 사흘 넘게 밀려 있습니다 — {names}",
                      "새 회차를 보내기 전에 먼저 답하세요", "/ir")
    if items["open_requests"]:
        return _check(WARN, "보낼 자료",
                      f"{len(items['open_requests'])}건이 남아 있습니다", "", "/ir")
    return _check(OK, "IR 요청", "밀린 요청이 없습니다", "", "/ir")


def report(db: Session, user: User, today: Optional[date] = None,
           rehearsal: Optional[bool] = None) -> dict:
    """회차 준비 상태. `rehearsal` 을 주지 않으면 테스트 방 설정으로 판단한다."""
    today = today or date.today()
    if rehearsal is None:
        rehearsal = bool(config.TEST_ROOM)

    checks: List[dict] = [
        _agent_check(db, user),
        _test_room_check(rehearsal),
        *_targets_check(db, user),
        _companies_check(db),
        _templates_check(db, user),
        _rehearsal_check(db, user, today),
        _open_requests_check(db, user),
    ]

    upcoming = cadence.upcoming_send_dates(db, today)
    next_send = upcoming[0]
    return {
        "checks": checks,
        "blocked": [c for c in checks if c["level"] == BLOCK],
        "warned": [c for c in checks if c["level"] == WARN],
        "ready": not any(c["level"] == BLOCK for c in checks),
        "rehearsal": rehearsal,
        "next_send": next_send,
        "days_left": (next_send - today).days,
        "upcoming": upcoming,
    }
