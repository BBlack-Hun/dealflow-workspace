"""IR 요청 · 미팅 — 딜소개 뒤에 오는 일.

딜소개를 보내면 답이 온다. "이 기업 자료 주세요"(IR 요청), "한번 뵙죠"(미팅).
받은 것을 놓치면 그 회차에서 가장 뜨거운 반응을 흘려보내는 셈이다.

여기서 정하는 것은 세 가지다.
- **열린 것이 먼저 보인다.** 요청받고 안 보낸 건, 오늘 미팅, 결과를 물을 때가 된 건.
- **미팅이 끝나면 열흘 뒤 결과를 묻는다.** 그 열흘을 사람이 기억하지 않아도 되게.
- **답이 왔으면 후속(리마인드)을 멈춘다.** IR 요청이 왔는데 "지난번 공유드린
  기업들 검토 중…"이 또 나가면 상대는 이쪽이 자기 답을 못 봤다고 생각한다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IrCompany, IrRequest, Meeting, User, VcContact
from . import cadence
from .sheet_import import normalize_company_name

# 미팅이 끝나고 결과를 물어보기까지. 운영에서 쓰던 간격 그대로다.
MEETING_FOLLOWUP_DAYS = 10

REQUEST_STATUS = {
    "open": "요청받음",
    "delivered": "전달함",
    "dropped": "보내지 않음",
}
MEETING_STATUS = {
    "scheduled": "예정",
    "done": "완료",
    "canceled": "취소",
}
MEETING_KINDS = {"first": "1차 미팅", "second": "2차 미팅", "etc": "기타"}
OUTCOMES = {
    "reviewing": "검토 중",
    "investing": "투자 검토",
    "hold": "보류",
    "pass": "거절",
}


def _key(name: Optional[str]) -> str:
    return normalize_company_name(name or "").replace(" ", "").lower()


def match_company(db: Session, name: str) -> Optional[IrCompany]:
    """이름으로 우리 DB 의 기업을 찾는다. 못 찾아도 요청은 남긴다.

    투자사가 다른 이름으로 부르거나 아직 등록 안 된 기업일 수 있다.
    못 찾았다고 기록을 버리면 요청을 놓친다.
    """
    key = _key(name)
    if not key:
        return None
    for company in db.execute(select(IrCompany)).scalars().all():
        if _key(company.name) == key:
            return company
    return None


def followup_date(done_on: date) -> date:
    """미팅 결과를 물어볼 날. 주말이면 다음 영업일로 민다."""
    return cadence.next_business_day(done_on + timedelta(days=MEETING_FOLLOWUP_DAYS))


# --- 조회 -------------------------------------------------------------------

def _contact_map(db: Session, ids: List[int]) -> Dict[int, VcContact]:
    if not ids:
        return {}
    return {
        c.id: c for c in db.execute(
            select(VcContact).where(VcContact.id.in_(ids))
        ).scalars().all()
    }


def request_rows(db: Session, user: User) -> List[dict]:
    rows = db.execute(
        select(IrRequest).where(IrRequest.user_id == user.id)
        .order_by(IrRequest.status != "open", IrRequest.requested_at.desc())
    ).scalars().all()
    contacts = _contact_map(db, [r.contact_id for r in rows])
    today = date.today()

    out = []
    for row in rows:
        contact = contacts.get(row.contact_id)
        waited = None
        try:
            waited = (today - date.fromisoformat(row.requested_at)).days
        except (TypeError, ValueError):
            pass
        out.append({
            "id": row.id,
            "contact_id": row.contact_id,
            "name": contact.name if contact else "-",
            "title": (contact.title or "") if contact else "",
            "firm": (contact.firm or "") if contact else "",
            "company_name": row.company_name,
            "company_id": row.company_id,
            "ir_url": "",
            "requested_at": row.requested_at,
            "waited": waited,
            # 사흘 넘게 안 보냈으면 눈에 띄어야 한다.
            "overdue": bool(row.status == "open" and waited is not None and waited >= 3),
            "status": row.status,
            "status_label": REQUEST_STATUS.get(row.status, row.status),
            "delivered_at": row.delivered_at or "",
            "note": row.note or "",
        })

    # 자료 링크를 함께 준다 — 요청 화면에서 바로 열어 보낼 수 있게.
    ids = [r["company_id"] for r in out if r["company_id"]]
    if ids:
        urls = {
            c.id: (c.ir_drive_url or "") for c in db.execute(
                select(IrCompany).where(IrCompany.id.in_(ids))
            ).scalars().all()
        }
        for row in out:
            row["ir_url"] = urls.get(row["company_id"], "")
    return out


def meeting_rows(db: Session, user: User) -> List[dict]:
    rows = db.execute(
        select(Meeting).where(Meeting.user_id == user.id)
        .order_by(Meeting.status != "scheduled", Meeting.scheduled_at.desc())
    ).scalars().all()
    contacts = _contact_map(db, [r.contact_id for r in rows])
    today = date.today()

    out = []
    for row in rows:
        contact = contacts.get(row.contact_id)
        when = _as_date(row.scheduled_at)
        due = _as_date(row.followup_due)
        out.append({
            "id": row.id,
            "contact_id": row.contact_id,
            "name": contact.name if contact else "-",
            "title": (contact.title or "") if contact else "",
            "firm": (contact.firm or "") if contact else "",
            "company_name": row.company_name or "",
            "scheduled_at": row.scheduled_at,
            "days_left": (when - today).days if when else None,
            "kind": row.kind,
            "kind_label": MEETING_KINDS.get(row.kind, row.kind),
            "status": row.status,
            "status_label": MEETING_STATUS.get(row.status, row.status),
            "outcome": row.outcome or "",
            "outcome_label": OUTCOMES.get(row.outcome or "", ""),
            "followup_due": row.followup_due or "",
            "followup_done": bool(row.followup_done),
            # 결과를 물어볼 날이 지났는데 아직 안 물어봤다
            "followup_due_now": bool(
                row.status == "done" and not row.followup_done
                and due is not None and due <= today),
            "note": row.note or "",
        })
    return out


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def last_batch_items(db: Session, contact_id: int) -> dict:
    """이 담당자가 **마지막으로 받은 회차**의 번호와 기업.

    투자사는 "4번, 6번 주세요" 라고 답한다. 그 번호가 어느 기업인지 사람이
    지난 카톡을 뒤져 맞추고 있었다. 회차에 번호가 그대로 남아 있으므로
    여기서 꺼내 보여준다.
    """
    from ..models import DealBatch, DealBatchCompany, SendItem, SendJob

    row = db.execute(
        select(SendJob.batch_id, DealBatch.title, DealBatch.sent_date)
        .join(SendItem, SendItem.job_id == SendJob.id)
        .join(DealBatch, DealBatch.id == SendJob.batch_id)
        .where(SendItem.contact_id == contact_id, SendItem.status == "sent",
               SendJob.kind == "deal_intro", SendJob.batch_id.isnot(None))
        .order_by(SendItem.id.desc()).limit(1)
    ).first()
    if row is None:
        return {"batch_id": None, "title": "", "sent_date": "", "items": []}

    batch_id, title, sent_date = row
    links = db.execute(
        select(DealBatchCompany, IrCompany)
        .join(IrCompany, IrCompany.id == DealBatchCompany.company_id)
        .where(DealBatchCompany.batch_id == batch_id)
        .order_by(DealBatchCompany.position)
    ).all()
    return {
        "batch_id": batch_id,
        "title": title or "지난 회차",
        "sent_date": sent_date or "",
        "items": [{"position": link.position, "company_id": company.id,
                   "name": company.name,
                   "has_link": bool((company.ir_drive_url or "").strip())}
                  for link, company in links],
    }


def resolve_request_names(db: Session, contact_id: int,
                          raw: str) -> tuple:
    """적어 넣은 것을 기업으로 푼다. **번호도 이름처럼 받는다.**

    투자사는 "2, 4 주세요" 라고 답한다. 지금까지는 그 번호를 기업명으로 읽어서
    `2` 라는 이름의 요청이 그대로 만들어졌다 — 어느 기업인지 아무도 모르는
    기록이 남고, 자료 전달 문구도 만들 수 없었다.

    번호는 **그 담당자에게 마지막으로 보낸 회차**의 자리 번호로 읽는다.
    이름과 섞여 있어도 된다("2, 샘플애그, 4").

    돌려주는 것: (풀린 목록, 못 찾은 번호 목록)
    """
    tokens = [t.strip() for t in raw.replace(",", "\n").splitlines() if t.strip()]
    if not tokens:
        return [], []

    numbered = {}
    if any(t.isdigit() for t in tokens):
        batch = last_batch_items(db, contact_id)
        numbered = {str(item["position"]): item for item in batch["items"]}

    resolved, unknown = [], []
    for token in tokens:
        if token.isdigit():
            item = numbered.get(token)
            if item is None:
                # 없는 번호를 조용히 이름으로 남기면 '3' 이라는 기업이 생긴다.
                unknown.append(token)
                continue
            resolved.append({"name": item["name"], "company_id": item["company_id"]})
            continue
        company = match_company(db, token)
        resolved.append({"name": token,
                         "company_id": company.id if company else None})

    # 같은 기업을 번호와 이름으로 둘 다 적었을 수 있다.
    seen, unique = set(), []
    for row in resolved:
        key = row["company_id"] or row["name"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique, unknown


def group_by_contact(requests: List[dict]) -> List[dict]:
    """담당자별로 묶는다. 한 사람이 여러 기업을 한꺼번에 요청하는 일이 잦아,
    한 번에 보내야 대화가 자연스럽다."""
    grouped: Dict[int, dict] = {}
    for row in requests:
        item = grouped.setdefault(row["contact_id"], {
            "contact_id": row["contact_id"], "name": row["name"],
            "title": row["title"], "firm": row["firm"],
            "rows": [], "company_ids": [], "missing": [], "no_link": [],
        })
        item["rows"].append(row)
        if row["company_id"]:
            item["company_ids"].append(row["company_id"])
            if not row["ir_url"]:
                item["no_link"].append(row["company_name"])
        else:
            item["missing"].append(row["company_name"])
    return sorted(grouped.values(), key=lambda g: -len(g["rows"]))


def today_items(db: Session, user: User, today: Optional[date] = None) -> dict:
    """지금 손대야 할 것만. 대시보드와 '오늘 할 일'이 같은 값을 쓴다."""
    today = today or date.today()
    requests = [r for r in request_rows(db, user) if r["status"] == "open"]
    meetings = meeting_rows(db, user)
    return {
        "open_requests": requests,
        "overdue_requests": [r for r in requests if r["overdue"]],
        "today_meetings": [m for m in meetings
                           if m["status"] == "scheduled"
                           and m["scheduled_at"] == today.isoformat()],
        "upcoming_meetings": [m for m in meetings
                              if m["status"] == "scheduled"
                              and m["scheduled_at"] > today.isoformat()],
        "due_followups": [m for m in meetings if m["followup_due_now"]],
    }


# --- 상태 바꾸기 ------------------------------------------------------------

def deliver(db: Session, request: IrRequest, when: Optional[date] = None) -> IrRequest:
    request.status = "delivered"
    request.delivered_at = (when or date.today()).isoformat()
    db.flush()
    return request


def close_requests_for(db: Session, job, contact_id: int,
                       when: Optional[date] = None) -> int:
    """IR 자료를 보냈으면 그 요청을 '전달함'으로 닫는다.

    보내고 나서 다시 화면으로 돌아와 버튼을 누르게 하면, 바쁠 때 그 한 번을
    빼먹는다. 그러면 이미 보낸 요청이 계속 '보낼 자료'에 남는다.

    회차에 담긴 기업과 이름이 맞는 열린 요청만 닫는다 — 같은 담당자의
    다른 기업 요청까지 함께 닫으면 안 보낸 것을 보냈다고 적는 셈이다.
    """
    from ..models import DealBatchCompany

    if job.batch_id is None:
        return 0
    sent_ids = {
        row.company_id for row in db.execute(
            select(DealBatchCompany).where(DealBatchCompany.batch_id == job.batch_id)
        ).scalars().all()
    }
    if not sent_ids:
        return 0
    sent_keys = {
        _key(c.name) for c in db.execute(
            select(IrCompany).where(IrCompany.id.in_(sent_ids))
        ).scalars().all()
    }

    closed = 0
    for row in db.execute(
        select(IrRequest).where(IrRequest.contact_id == contact_id,
                                IrRequest.status == "open")
    ).scalars().all():
        matched = row.company_id in sent_ids or _key(row.company_name) in sent_keys
        if matched:
            deliver(db, row, when)
            closed += 1
    return closed


def complete_meeting(db: Session, meeting: Meeting, outcome: str = "",
                     when: Optional[date] = None) -> Meeting:
    """미팅 완료. **열흘 뒤 결과를 물을 날을 함께 잡는다.**"""
    done_on = when or date.today()
    meeting.status = "done"
    meeting.done_at = done_on.isoformat()
    if outcome in OUTCOMES:
        meeting.outcome = outcome
    meeting.followup_due = followup_date(done_on).isoformat()
    meeting.followup_done = 0
    db.flush()
    return meeting
