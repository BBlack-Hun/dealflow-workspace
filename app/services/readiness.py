"""회차 준비 점검 — 발송일 전에 무엇이 막혀 있는지 한 번에 본다.

발송 당일에 "왜 안 나가지?"를 찾는 것은 늦다. 막히는 자리는 정해져 있다:
발송 프로그램이 안 켜져 있거나, 방 제목이 실제와 다르거나, 보낼 기업이 안
골라져 있다.

각 항목은 **지금 어떤 상태인지**와 **무엇을 하면 되는지**를 함께 준다.
"괜찮음/주의/막힘" 세 단계로만 나눈다 — 더 나누면 무엇을 먼저 할지 흐려진다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import clock, config
from ..models import (SEND_KINDS, AgentDevice, IrCompany, MessageTemplate,
                      SendItem, SendJob, User)
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
        # 경과시간은 **순간**끼리 뺀다 — 저장값의 오프셋이 무엇이든 결과가 같다.
        mins = (clock.now()
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
    """시험방 설정 — **더는 실발송을 막지 않는다.**

    ## 무엇이 바뀌었나

    예전에는 이 항목이 실발송에서 `BLOCK` 이었다. 그럴 만했다 — 시험방이
    켜져 있으면 `create_send_list` 가 **모든 발송**을 그 방으로 돌렸으니,
    끄지 않고 보내면 투자사는 아무것도 못 받았다. 점검의 뜻은 "끄는 것을
    잊지 마라" 였다.

    이제 일반 발송은 시험방을 읽지 않는다(`app/config.py: TEST_ROOM`).
    켜져 있어도 딜 소개는 투자사에게 간다. **막을 사고가 없어졌는데 계속
    막으면**, 사람은 이 화면의 빨강을 "또 그 소리" 로 읽고 다음 빨강도 같이
    지나친다 — 그 값이 이 화면의 전부다.

    그래서 실발송에서는 **알리기만 한다**(`OK`). 지워야 할 값이 아니라
    켜 둬도 되는 값이므로 `WARN` 도 아니다.

    ## 리허설에서는 여전히 켜져 있어야 한다

    리허설은 **담당자 줄의 방 이름을 시험방으로 둔 가짜 담당자**에게 실제
    발송 길을 걸어 보는 일이고(`scripts/rehearsal.py`), 그 담당자를 만들려면
    시험방 제목이 있어야 한다. 값이 없으면 리허설을 시작할 수가 없다.
    """
    room = config.TEST_ROOM
    if rehearsal:
        if room:
            return _check(OK, "시험방",
                          f"'{room}' — 리허설 담당자가 이 방으로 받습니다", "")
        return _check(BLOCK, "시험방", "정해져 있지 않습니다",
                      "리허설 담당자를 만들 수 없습니다 — `.env` 에 넣고 다시 띄우세요")
    if room:
        return _check(OK, "시험방",
                      f"'{room}' — `/setup` 의 시험 단추만 이 방으로 갑니다",
                      "딜 소개·IR 전달·리마인드는 각 담당자 방으로 나갑니다", "/setup")
    return _check(OK, "시험방", "정해져 있지 않습니다 — `/setup` 시험 자리가 닫혀 있습니다",
                  "", "/setup")


def _targets_check(db: Session, user: User) -> List[dict]:
    # **딜 제안 관리와 같은 모집단**이다. 여기가 "발송 대상" 을 말하는 자리라,
    # 발송 화면이 세는 사람과 다르면 회차 직전 점검이 다른 수를 말하게 된다
    # (`sheet_owner.deal_list_contacts` 한 곳에서 나온다).
    contacts = sheet_owner.deal_list_contacts(db, user)
    states = [_room_state(c) for c in contacts]
    # **여기가 "발송 대상" 을 말하는 자리라, 발송 화면과 같은 문을 지나야 한다.**
    # 방만 보고 세던 동안에는 딜 제안 관리가 빼는 사람(연결이 안 끝났거나 딜
    # 소개를 멈춰 둔 사람)이 회차 직전 점검에서는 대상으로 잡혔다 — 두 화면이
    # 다른 수를 말하면 어느 쪽을 믿을지 알 수가 없다. 아래 방 갈래는 그대로
    # 명단 전체를 본다: 방을 고치는 일은 연결이 끝나기 전에도 해야 한다.
    sendable = sum(1 for c in contacts
                   if sheet_owner.can_send_to(c)
                   and _room_state(c) in _SENDABLE_ROOM)
    failed = sum(1 for s in states if s == "failed")
    missing = sum(1 for s in states if s == "missing")
    unverified = sum(1 for s in states if s == "unverified")

    out = []
    if sendable == 0:
        out.append(_check(BLOCK, "발송 대상", "보낼 수 있는 담당자가 없습니다",
                          "카톡방을 연결하세요", "/contacts"))
    else:
        out.append(_check(OK, "발송 대상",
                          f"{sendable}명 · 딜소개 명단 {len(contacts)}명 중", "", "/contacts"))
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
               SendJob.kind.in_(SEND_KINDS),
               func.coalesce(SendItem.sent_at, "") >= cutoff)
    ).scalar() or 0
    if recent:
        return _check(OK, "최근 발송 확인", f"최근 7일 안에 {recent}건 성공", "")
    # **"테스트 모드를 켜고 한 건 보내 보세요" 라고 적던 자리다.** 그 말이
    # 맞던 때는 시험방이 켜져 있으면 발송이 전부 그리로 갔기 때문인데, 이제는
    # 켜도 투자사에게 그대로 나간다 — 그대로 두면 이 화면이 **실발송을 시키는**
    # 안내가 된다. 발송기가 도는지만 보려면 `/setup` 의 시험 단추가 그 자리다
    # (그쪽은 `SEND_KINDS` 밖이라 여기 세어지지는 않는다).
    return _check(WARN, "최근 발송 확인", "최근 7일 안에 성공한 발송이 없습니다",
                  "발송기가 도는지는 `/setup` 의 시험 단추로 먼저 보세요", "/setup")


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
    """회차 준비 상태. `rehearsal` 을 주지 않으면 **실발송 기준**이다.

    예전 기본값은 `bool(config.TEST_ROOM)` 이었다 — 시험방이 켜져 있으면
    그날 나가는 것이 전부 시험방행이었으니 "지금은 리허설" 이 사실이었다.
    이제는 시험방이 켜져 있어도 딜 소개는 투자사에게 간다. 그 추측을 그대로
    두면 **진짜 회차 날 아침에 "리허설 점검" 이라고 적힌 화면**을 보게 되고,
    거기 적힌 "실제 담당자에게는 가지 않습니다" 는 거짓말이다.

    추측할 근거가 없어졌으므로 추측하지 않는다. 리허설로 보려면 화면에서
    그렇게 고른다(`/readiness/detail?mode=rehearsal`).
    """
    today = today or date.today()
    if rehearsal is None:
        rehearsal = False

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
