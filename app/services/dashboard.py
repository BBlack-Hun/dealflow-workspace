"""대시보드 집계 — 화면에 쓸 숫자를 한곳에서 만든다.

두 가지 화면이 있고 보는 목적이 다르다.

- **사용자 대시보드**: "다음 발송까지 내가 뭘 고쳐야 하나."
  방이 없는 담당자, 소개 문구가 없는 기업처럼 **막힌 것**을 먼저 보여준다.
  발송은 매월 첫째·셋째 수요일이라 그날까지 남은 날이 곧 마감이다.
- **관리자 대시보드**: "팀이 굴러가고 있나."
  팀원별 담당 규모·발송량·방 확인율을 나란히 놓아 어디가 막혔는지 본다.

집계는 SQL 한 번씩으로 끝낸다. 담당자 126명 · 활동 1,000여 건 규모라
파이썬에서 세도 되지만, 팀이 커지면 화면이 먼저 느려지는 자리다.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import cadence, mailer, pipeline, sheet_owner
from ..models import (
    AgentDevice,
    IrRequest,
    Meeting,
    ContactActivity,
    DealBatch,
    IrCompany,
    SendItem,
    SendJob,
    User,
    VcContact,
)

# 반응을 '최근'으로 볼 기간. 내 투자사 화면과 같은 기준을 쓴다.
REACTION_WINDOW_DAYS = 60

# 발송 주기는 `schedule_rules` 가 정한다 — cadence.upcoming_send_dates 를 직접 쓴다.
# 예전엔 여기에 "매월 첫째·셋째 수요일" 이 박혀 있었는데, 주기는 운영하며 바뀐다.


# --- 공통 집계 --------------------------------------------------------------

# 방 확인 결과를 **명시적으로** 나눈다. 예전에는 모르는 값을 전부 '미확인'으로
# 떨어뜨렸는데, 그래서 '방 없음(not_found)' 으로 확인된 사람까지 발송 가능으로
# 세어졌다(투자사 DB 117명 · 대시보드 123명으로 어긋난 원인).
_SENDABLE_ROOM = {"verified", "unverified"}
_ROOM_ALIAS = {
    "verified": "verified",
    "unverified": "unverified",
    "failed": "failed",
    "not_found": "failed",       # 방이 없다고 확인된 것 — 보낼 수 없다
    "ambiguous": "failed",       # 어느 방인지 모른다 — 보내면 안 된다
}


def _room_state(c: VcContact) -> str:
    """발송 준비 관점에서 본 방 상태."""
    if not c.channel_kakao:
        # 카톡 채널이 아니면 방 이름이 있어도 카톡 발송 대상이 아니다.
        return "email" if c.channel_email else "no_channel"
    if not (c.kakao_room_name or "").strip():
        return "missing"
    # 처음 보는 값은 '확인 안 됨'이 아니라 **보낼 수 없음**으로 본다.
    # 모르는 상태를 낙관적으로 해석하면 못 가는 곳에 갈 수 있다고 세게 된다.
    return _ROOM_ALIAS.get(c.room_verified or "", "failed")


ROOM_LABELS = {
    "verified": ("확인됨", "ok"),
    "unverified": ("미확인", "warn"),
    "failed": ("방 없음 · 실패", "bad"),
    "missing": ("방 미등록", "bad"),
    "email": ("메일 채널", "muted"),
    "no_channel": ("채널 미지정", "muted"),
}


def _recent_activity_counts(db: Session, contact_ids: List[int],
                            cutoff: str) -> Dict[str, int]:
    """최근 N일 안의 활동을 종류별로 센다(투자사 목록의 '반응' 태그용)."""
    if not contact_ids:
        return {}
    rows = db.execute(
        select(ContactActivity.kind, func.count())
        .where(ContactActivity.contact_id.in_(contact_ids),
               func.coalesce(ContactActivity.happened_at, "") >= cutoff)
        .group_by(ContactActivity.kind)
    ).all()
    return {kind: n for kind, n in rows}


def _reaction_summary(db: Session, contact_ids: List[int]) -> dict:
    """반응 요약 — **기간을 자르지 않는다**.

    예전엔 '최근 60일'이었는데, 61일째가 되면 숫자가 갑자기 줄어드는 것을
    화면만 보고는 알 수 없었다. 반응은 한 번 오면 없어지는 것이 아니므로
    전체 기간으로 센다.

    세는 단위도 나눈다. IR 요청·미팅은 **투자사(담당자) 몇 곳**이 반응했는지가
    궁금하고(같은 곳이 세 번 요청해도 한 곳이다), 요청받은 **기업 수**는
    따로 봐야 한다.
    """
    if not contact_ids:
        return {"ir_contacts": 0, "meeting_contacts": 0, "requested_companies": 0}

    rows = db.execute(
        select(ContactActivity.kind, ContactActivity.contact_id,
               ContactActivity.company_names)
        .where(ContactActivity.contact_id.in_(contact_ids),
               ContactActivity.kind.in_(("ir_request", "meeting")))
    ).all()

    ir_contacts, meeting_contacts, companies = set(), set(), set()
    for kind, contact_id, names in rows:
        if kind == "ir_request":
            ir_contacts.add(contact_id)
            for name in _company_names(names):
                companies.add(name)
        else:
            meeting_contacts.add(contact_id)

    # 이 시스템으로 받은 요청도 함께 센다(시트 이력만 보면 최근 것이 빠진다).
    for contact_id, company_name in db.execute(
        select(IrRequest.contact_id, IrRequest.company_name)
        .where(IrRequest.contact_id.in_(contact_ids))
    ).all():
        ir_contacts.add(contact_id)
        if company_name:
            companies.add(company_name.strip())
    for (contact_id,) in db.execute(
        select(Meeting.contact_id).where(Meeting.contact_id.in_(contact_ids))
    ).all():
        meeting_contacts.add(contact_id)

    return {
        "ir_contacts": len(ir_contacts),
        "meeting_contacts": len(meeting_contacts),
        "requested_companies": len(companies),
    }


def _company_names(raw: Optional[str]) -> List[str]:
    import json

    try:
        return [str(n).strip() for n in json.loads(raw or "[]") if str(n).strip()]
    except (TypeError, ValueError):
        return []


def _split_csv(value: Optional[str]) -> List[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _distribution(values: List[str], top: int = 6) -> List[dict]:
    """막대그래프용 분포. 합계 대비 비율까지 계산해 템플릿을 단순하게 둔다."""
    counted = Counter(values)
    total = sum(counted.values()) or 1
    rows = [{"label": label, "count": n, "percent": round(n * 100 / total)}
            for label, n in counted.most_common(top)]
    return rows


# --- 사용자 대시보드 --------------------------------------------------------

def user_dashboard(db: Session, user: User, today: Optional[date] = None) -> dict:
    today = today or date.today()
    cutoff = (today - timedelta(days=REACTION_WINDOW_DAYS)).isoformat()

    # 담당은 **명단(시트) 단위**로 정해진다 — "내 이름으로 된 탭만 내 담당".
    # 이렇게 하지 않으면 시트를 올린 사람에게 팀 전체가 붙는다.
    contacts = sheet_owner.my_contacts(db, user)
    waiting = [c for c in contacts if c.connect_stage != "connected"]
    ids = [c.id for c in contacts]

    rooms = Counter(_room_state(c) for c in contacts)
    sendable = sum(rooms[state] for state in _SENDABLE_ROOM)

    companies = db.execute(select(IrCompany)).scalars().all()
    introducible = [c for c in companies if c.introducible]

    acts = _recent_activity_counts(db, ids, cutoff)

    # 이번 달 발송 = 성공한 건수. '보냈다'는 시도가 아니라 도착을 뜻해야 한다.
    month_prefix = today.strftime("%Y-%m")
    sent_this_month = db.execute(
        select(func.count()).select_from(SendItem)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.user_id == user.id, SendItem.status == "sent",
               func.coalesce(SendItem.sent_at, "").startswith(month_prefix))
    ).scalar() or 0

    # 막힌 것 — 발송 전에 손봐야 할 목록
    blockers = []
    if rooms["missing"]:
        blockers.append({
            "count": rooms["missing"], "label": "카톡방이 등록되지 않은 담당자",
            "hint": "이름·직함·투자사로 방을 찾아 연결하세요",
            "href": "/contacts", "level": "bad",
        })
    if rooms["failed"]:
        blockers.append({
            "count": rooms["failed"], "label": "방을 찾지 못한 담당자",
            "hint": "실제 카톡방이 없거나 제목이 다릅니다 — 이 사람에게는 나가지 않습니다",
            "href": "/contacts", "level": "bad",
        })
    if rooms["unverified"]:
        blockers.append({
            "count": rooms["unverified"], "label": "방 이름을 확인하지 않은 담당자",
            "hint": "[방 연결 확인]을 돌리면 실제 방 제목으로 맞춥니다",
            "href": "/contacts", "level": "warn",
        })
    not_introducible = len(companies) - len(introducible)
    if not_introducible:
        blockers.append({
            "count": not_introducible, "label": "소개 문구를 만들 수 없는 기업",
            "hint": "한줄소개 또는 숫자(매출·투자금)가 비어 있습니다",
            "href": "/companies", "level": "warn",
        })

    device = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == user.id)
    ).scalars().first()
    if device is None or not device.last_poll_at:
        blockers.append({
            "count": 1, "label": "발송 프로그램이 아직 연결되지 않음",
            "hint": "내 PC에 설치하고 켜 두어야 카톡으로 나갑니다",
            "href": "/setup", "level": "bad",
        })

    # 오늘 보낼 후속 — 딜소개 회차보다 먼저 챙겨야 할 때가 많다.
    cadence.sweep_reactions(db, user.id)
    due_rows = cadence.sequence_rows(db, user.id, today)
    due_today = [r for r in due_rows if r["status"] == "active" and r["due"]
                 and r["due"] <= today.isoformat()]

    upcoming = cadence.upcoming_send_dates(db, today)
    next_send = upcoming[0]

    return {
        "kpis": [
            # 이름만 보고 무엇을 세는지 알 수 있어야 한다.
            # '카톡 발송 가능'·'소개 가능 기업'은 무엇이 가능하다는 건지 모호했다.
            {"key": "contacts", "label": "내 담당 투자사", "value": len(contacts),
             "sub": "내 명단에 있는 사람", "href": "/contacts"},
            {"key": "sendable", "label": "카톡방 연결된 투자사", "value": sendable,
             "sub": f"지금 바로 보낼 수 있음 · 전체 {len(contacts)}명 중",
             "href": "/contacts"},
            {"key": "companies", "label": "소개 문구 준비된 기업",
             "value": len(introducible),
             "sub": f"발송 목록에 뜸 · 등록 {len(companies)}개 중",
             "href": "/companies"},
            {"key": "sent", "label": "이번 달 보낸 건수", "value": sent_this_month,
             "sub": "카톡·메일 도착 성공", "href": "/deals"},
        ],
        "next_send": next_send,
        "days_left": (next_send - today).days,
        "upcoming": upcoming,
        "rooms": [
            {"state": s, "label": ROOM_LABELS[s][0], "level": ROOM_LABELS[s][1],
             "count": rooms.get(s, 0),
             "percent": round(rooms.get(s, 0) * 100 / (len(contacts) or 1))}
            for s in ("verified", "unverified", "failed", "missing",
                      "email", "no_channel")
            if rooms.get(s, 0)
        ],
        "blockers": blockers,
        # 연결 작업은 발송과 다른 일이라 따로 보여준다.
        "pipeline": _pipeline_view(waiting),
        "pipeline_items": pipeline.today_items(db, user, today),
        "followups": {
            "due": len(due_today),
            "overdue": sum(1 for r in due_today if r["overdue"]),
            "rows": due_today[:5],
        },
        "reactions": _reaction_summary(db, ids),
        "stages": _distribution([s for c in contacts for s in _split_csv(c.stages)]),
        "sectors": _distribution([s for c in contacts for s in _split_csv(c.sectors)]),
        "recent_batches": recent_batches(db, user_id=user.id),
    }


def _pipeline_view(rows: List[VcContact]) -> dict:
    """아직 연결되지 않은 명단. 누가 맡고 있는지까지 보여준다."""
    stages = Counter(c.connect_stage for c in rows)
    owners = Counter((c.assignee_name or "미지정").strip() for c in rows)
    return {
        "total": len(rows),
        "in_progress": stages.get("in_progress", 0),
        "not_started": stages.get("not_started", 0),
        "declined": stages.get("declined", 0),
        "owners": [{"name": name, "count": n} for name, n in owners.most_common(4)],
    }


def recent_batches(db: Session, user_id: Optional[int] = None, limit: int = 5) -> List[dict]:
    """최근 발송 회차. 관리자 화면에서는 user_id 없이 팀 전체를 본다."""
    stmt = select(SendJob).where(SendJob.kind == "deal_intro")
    if user_id is not None:
        stmt = stmt.where(SendJob.user_id == user_id)
    jobs = db.execute(stmt.order_by(SendJob.id.desc()).limit(limit)).scalars().all()
    if not jobs:
        return []

    batches = {
        b.id: b for b in db.execute(
            select(DealBatch).where(
                DealBatch.id.in_([j.batch_id for j in jobs if j.batch_id] or [0]))
        ).scalars().all()
    }
    owners = {
        u.id: u for u in db.execute(
            select(User).where(User.id.in_([j.user_id for j in jobs]))
        ).scalars().all()
    }
    out = []
    for job in jobs:
        batch = batches.get(job.batch_id)
        owner = owners.get(job.user_id)
        out.append({
            "job_id": job.id,
            "title": batch.title if batch else "딜소개 회차",
            "date": (batch.sent_date if batch else None) or (job.started_at or "")[:10],
            "owner": owner.name if owner else "",
            "status": job.status,
            "total": job.total, "sent": job.sent, "failed": job.failed,
        })
    return out


# --- 관리자 대시보드 --------------------------------------------------------

def admin_dashboard(db: Session, today: Optional[date] = None) -> dict:
    today = today or date.today()
    cutoff = (today - timedelta(days=REACTION_WINDOW_DAYS)).isoformat()
    month_prefix = today.strftime("%Y-%m")

    users = db.execute(select(User).order_by(User.id)).scalars().all()
    contacts = db.execute(select(VcContact)).scalars().all()
    by_user: Dict[int, List[VcContact]] = {}
    for c in contacts:
        by_user.setdefault(c.user_id, []).append(c)

    devices = {
        d.user_id: d for d in db.execute(select(AgentDevice)).scalars().all()
    }

    # 이번 달 사용자별 성공 발송 수
    sent_rows = db.execute(
        select(SendJob.user_id, func.count())
        .select_from(SendItem).join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.status == "sent",
               func.coalesce(SendItem.sent_at, "").startswith(month_prefix))
        .group_by(SendJob.user_id)
    ).all()
    sent_by_user = {uid: n for uid, n in sent_rows}

    rows = []
    for u in users:
        mine = by_user.get(u.id, [])
        states = Counter(_room_state(c) for c in mine)
        ready = sum(states[state] for state in _SENDABLE_ROOM)
        acts = _recent_activity_counts(db, [c.id for c in mine], cutoff)
        device = devices.get(u.id)
        rows.append({
            "id": u.id,
            "name": u.name or "-",
            "phone": u.phone,
            "role": u.role,
            "contacts": len(mine),
            "ready": ready,
            "ready_percent": round(ready * 100 / (len(mine) or 1)),
            "missing": states["missing"] + states["failed"],
            "sent_month": sent_by_user.get(u.id, 0),
            "ir": acts.get("ir_request", 0),
            "meeting": acts.get("meeting", 0),
            "agent": _agent_label(device),
            "agent_ok": bool(device and device.last_poll_at),
            "password_pending": bool(u.must_change_password),
            "consulting": bool(u.can_view_consulting) or u.role == "admin",
            "last_login": (u.last_login_at or "")[:10],
        })

    companies = db.execute(select(IrCompany)).scalars().all()
    introducible = [c for c in companies if c.introducible]

    unassigned = len([c for c in contacts
                      if c.user_id not in {u.id for u in users}])

    return {
        "kpis": [
            {"key": "users", "label": "팀원", "value": len(users), "sub": "명", "href": "/team"},
            {"key": "contacts", "label": "전체 투자사", "value": len(contacts),
             "sub": "명", "href": "/contacts"},
            {"key": "companies", "label": "소개 가능 기업", "value": len(introducible),
             "sub": f"등록 {len(companies)}개 중", "href": "/companies"},
            {"key": "sent", "label": "이번 달 발송", "value": sum(sent_by_user.values()),
             "sub": "건 성공", "href": "/team"},
        ],
        "members": rows,
        "next_send": cadence.upcoming_send_dates(db, today)[0],
        "upcoming": cadence.upcoming_send_dates(db, today),
        "companies": {
            "total": len(companies),
            "introducible": len(introducible),
            "blocked": len(companies) - len(introducible),
            "top_deal": len([c for c in companies if c.is_top_deal]),
            "contracted": len([c for c in companies if c.contract_status == "yes"]),
        },
        "sectors": _distribution([c.sector_major for c in companies if c.sector_major], top=8),
        "mail": mailer.status(),
        "warnings": _admin_warnings(rows, unassigned),
        "recent_batches": recent_batches(db, limit=8),
    }


def _agent_label(device: Optional[AgentDevice]) -> str:
    if device is None:
        return "미발급"
    if not device.last_poll_at:
        return "미연결"
    try:
        ts = datetime.fromisoformat(device.last_poll_at)
        mins = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    except ValueError:
        return "확인 불가"
    if mins < 2:
        return f"연결됨 · {device.hostname or '이름 없음'}"
    if mins < 60:
        return f"{int(mins)}분 전"
    return f"{int(mins // 60)}시간 전"


def _admin_warnings(rows: List[dict], unassigned: int) -> List[dict]:
    """팀 단위로 손봐야 할 것. 사람 이름을 세워 누가 막혔는지 바로 보이게 한다."""
    out = []
    no_agent = [r["name"] for r in rows if not r["agent_ok"]]
    if no_agent:
        out.append({"level": "bad", "label": "발송 프로그램 미연결",
                    "detail": ", ".join(no_agent),
                    "hint": "그 PC에서 [발송 프로그램 설치]를 해야 발송이 나갑니다"})
    pending = [r["name"] for r in rows if r["password_pending"]]
    if pending:
        out.append({"level": "warn", "label": "초기 비밀번호를 아직 안 바꾼 계정",
                    "detail": ", ".join(pending),
                    "hint": "첫 로그인 시 변경 화면으로 유도됩니다"})
    blocked = [f"{r['name']}({r['missing']}명)" for r in rows if r["missing"]]
    if blocked:
        out.append({"level": "warn", "label": "카톡방이 없거나 연결 실패한 담당자",
                    "detail": ", ".join(blocked),
                    "hint": "그 담당자에게는 발송이 나가지 않습니다"})
    empty = [r["name"] for r in rows if r["contacts"] == 0 and r["role"] != "admin"]
    if empty:
        out.append({"level": "muted", "label": "담당 투자사가 없는 계정",
                    "detail": ", ".join(empty),
                    "hint": "현황 시트를 업로드하면 채워집니다"})
    if unassigned:
        out.append({"level": "bad", "label": "주인이 없는 담당자",
                    "detail": f"{unassigned}명",
                    "hint": "계정이 지워졌는데 담당자가 남아 있습니다"})
    return out
