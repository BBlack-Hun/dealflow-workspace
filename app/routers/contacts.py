"""내 투자사 — 담당자 CRUD · 활동 이력 · 방 연결 확인 (ROADMAP 2.2/2.5, FEATURE_SPEC §3).

표에 보이는 '최근 딜소개'와 '반응'은 **저장하지 않고 조회 시 집계**한다(DATA_MODEL §2.4).
수기로 관리하면 실제 발송 이력과 어긋나는 순간 신뢰를 잃기 때문이다. 126행 화면에서
N+1 쿼리가 나지 않도록 담당자 전체를 한 번에 모아 파이썬에서 묶는다.

RBAC: 모든 조회·수정은 ``VcContact.user_id == 현재 사용자`` 로 좁힌다. 정식 로그인은
다음 스프린트(휴대폰번호 + 비밀번호)라 현재 사용자는 얇은 의존성 하나로 결정된다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import ContactActivity, IrCompany, SendItem, SendJob, User, VcContact
from ..services import sheet_import
from ..services.room_name import DEFAULT_SUFFIX, build_room_name

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

# 반응(IR 요청·미팅) 집계 창 — FEATURE_SPEC §3 표 정의.
REACTION_WINDOW_DAYS = 90

ROOM_BADGES = {
    "verified": ("ok", "● 확인됨"),
    "unverified": ("wait", "○ 미확인"),
    "not_found": ("warn", "⚠ 방 없음"),
    "ambiguous": ("warn", "⚠ 복수 매칭"),
}
STATUS_LABELS = {"active": "활발", "no_response": "반응없음", "paused": "검토중단"}


# ── 조회 모델 (SSR 표 + 상세 패널 공용) ─────────────────────────────────────

def _split_csv(value: Optional[str]) -> List[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _activity_date(act: ContactActivity) -> Optional[str]:
    """활동의 대표 날짜. 날짜가 없으면 월의 1일로 근사한다(정렬·창 계산용)."""
    if act.happened_at:
        return act.happened_at
    if act.month:
        return f"{act.month}-01"
    return None


def _recency_bucket(last: Optional[str], today: date) -> str:
    if not last:
        return "없음"
    try:
        days = (today - date.fromisoformat(last[:10])).days
    except ValueError:
        return "없음"
    if days <= 7:
        return "7일 내"
    if days <= 30:
        return "30일 내"
    return "30일 초과"


def contact_rows(db: Session, user: User, team_wide: bool = False) -> List[dict]:
    """표 한 행 = 담당자 1명 + 집계값. (FEATURE_SPEC §3 7컬럼)

    `team_wide` 는 관리자 전용이다. 관리자는 직접 보내지 않지만 **누가 어떤
    투자사를 맡고 있는지** 알아야 팀이 굴러간다. 발송 대상 고르기는 여전히
    본인 담당분만이다 — 남의 담당에 실수로 나가면 안 된다.
    """
    stmt = select(VcContact).order_by(VcContact.group_name, VcContact.name)
    if not (team_wide and user.role == "admin"):
        stmt = stmt.where(VcContact.user_id == user.id)
    contacts = db.execute(stmt).scalars().all()
    if not contacts:
        return []
    ids = [c.id for c in contacts]

    # 발송 이력(성공 건)에서 담당자별 마지막 딜소개 시각.
    sent_map: Dict[int, str] = {}
    for contact_id, last_at in db.execute(
        select(SendItem.contact_id, func.max(SendItem.sent_at))
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendJob.kind == "deal_intro", SendItem.status == "sent",
               SendItem.contact_id.in_(ids))
        .group_by(SendItem.contact_id)
    ).all():
        if last_at:
            sent_map[contact_id] = last_at[:10]

    acts_map: Dict[int, List[ContactActivity]] = {cid: [] for cid in ids}
    for act in db.execute(
        select(ContactActivity).where(ContactActivity.contact_id.in_(ids))
    ).scalars().all():
        acts_map[act.contact_id].append(act)

    today = date.today()
    cutoff = (today - timedelta(days=REACTION_WINDOW_DAYS)).isoformat()

    owners = {
        u.id: u.name for u in db.execute(
            select(User).where(User.id.in_({c.user_id for c in contacts}))
        ).scalars().all()
    }

    rows = []
    for c in contacts:
        acts = acts_map.get(c.id, [])
        deal_dates = [d for d in (_activity_date(a) for a in acts
                                  if a.kind == "deal_intro") if d]
        if c.id in sent_map:
            deal_dates.append(sent_map[c.id])
        last_deal = max(deal_dates) if deal_dates else None
        last_round = next(
            (a for a in acts
             if a.kind == "deal_intro" and _activity_date(a) == last_deal), None
        )
        last_deal_note = _round_label(last_round) if last_round else ""

        ir_recent = sum(1 for a in acts if a.kind == "ir_request"
                        and (_activity_date(a) or "") >= cutoff)
        meet_recent = sum(1 for a in acts if a.kind == "meeting"
                          and (_activity_date(a) or "") >= cutoff)
        ir_total = sum(1 for a in acts if a.kind == "ir_request")
        meet_total = sum(1 for a in acts if a.kind == "meeting")

        room_state = c.room_verified if c.kakao_room_name else "not_found"
        room_class, room_label = ROOM_BADGES.get(room_state, ROOM_BADGES["unverified"])
        if not c.kakao_room_name:
            room_class, room_label = "warn", "⚠ 미등록"

        rows.append({
            "id": c.id,
            "owner": owners.get(c.user_id, ""),
            "is_mine": c.user_id == user.id,
            "connect_stage": c.connect_stage,
            "connect_label": sheet_import.CONNECT_LABELS.get(c.connect_stage, c.connect_stage),
            "department": c.department or "",
            "name": c.name,
            "title": c.title or "",
            "firm": c.firm or "",
            "group_name": c.group_name or "",
            "channel_kakao": c.channel_kakao,
            "channel_email": c.channel_email,
            "room_name": c.kakao_room_name or "",
            "room_verified": room_state,
            "room_class": room_class,
            "room_label": room_label,
            "invited_status": c.invited_status or "",
            "stages": _split_csv(c.stages),
            "sectors": _split_csv(c.sectors),
            "round_size": c.round_size or "",
            "last_deal": last_deal,
            "last_deal_label": _date_label(last_deal, last_round),
            "last_deal_note": last_deal_note or "",
            "last_deal_full": (last_round.content if last_round else ""),
            "recency": _recency_bucket(last_deal, today),
            "ir_recent": ir_recent,
            "meet_recent": meet_recent,
            "ir_total": ir_total,
            "meet_total": meet_total,
            "reaction_tags": _reaction_tags(ir_recent, meet_recent),
            "status": c.status,
            "status_label": STATUS_LABELS.get(c.status, c.status),
            "memo": c.memo or "",
            "channel_tags": _channel_tags(c),
        })
    return rows


def _date_label(last_deal: Optional[str], round_: Optional[ContactActivity]) -> str:
    """`08.19(수)` — 요일까지 보여야 '셋째주 수요일' 운영 리듬과 대조된다."""
    if not last_deal:
        return "-"
    weekday = (round_.weekday if round_ else None) or sheet_import.weekday_of(last_deal)
    return f"{last_deal[5:7]}.{last_deal[8:10]}" + (f"({weekday})" if weekday else "")


def _round_label(act: ContactActivity) -> str:
    """`7개사 · 샘플애그, 샘플메디 …` — 몇 개사를 보냈는지가 먼저 보여야 한다."""
    names = act.companies
    count = act.company_count or len(names) or None
    head = f"{count}개사" if count else ""
    if names:
        shown = ", ".join(names[:3]) + (f" 외 {len(names) - 3}" if len(names) > 3 else "")
        return f"{head} · {shown}" if head else shown
    return head or act.content


def _reaction_tags(ir_recent: int, meet_recent: int) -> List[str]:
    tags = []
    if ir_recent:
        tags.append("IR 있음")
    if meet_recent:
        tags.append("미팅 있음")
    return tags or ["반응 없음"]


def _channel_tags(c: VcContact) -> List[str]:
    tags = []
    if c.channel_kakao:
        tags.append("카톡")
    if c.channel_email:
        tags.append("메일")
    return tags


def _owned(db: Session, contact_id: int, user: User) -> VcContact:
    contact = db.get(VcContact, contact_id)
    if contact is None or contact.user_id != user.id:
        # 남의 담당자는 '없는 것'으로 답한다(존재 여부도 흘리지 않는다).
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")
    return contact


# ── 스키마 ──────────────────────────────────────────────────────────────────

class ContactIn(BaseModel):
    name: str
    title: Optional[str] = None
    firm: Optional[str] = None
    group_name: Optional[str] = None
    kakao_room_name: Optional[str] = None
    invited_status: Optional[str] = None
    channel_kakao: Optional[int] = None
    channel_email: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    stages: Optional[str] = None
    sectors: Optional[str] = None
    round_size: Optional[str] = None
    status: Optional[str] = None
    memo: Optional[str] = None


class VerifyRequest(BaseModel):
    contact_ids: Optional[List[int]] = None


# ── 방 연결 확인 (ROADMAP 2.5) ──────────────────────────────────────────────
# 라우트 순서 주의: "/verify-rooms" 가 "/{contact_id}"(int) 보다 먼저 등록돼야 한다.

@router.post("/verify-rooms")
def verify_rooms(
    req: VerifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[방 연결 확인] — 방 이름 대조 잡을 큐에 넣는다.

    카톡방 제목이 실제와 한 글자라도 다르면 발송이 통째로 skip 되므로, 실운영 전
    126명을 한 번에 대조해야 한다. 확인은 **발송과 같은 큐**를 타되 잡 종류로 갈린다
    (kind=verify_room) — 에이전트는 이 잡에서 방을 열지도, 문구를 보내지도 않는다.
    """
    query = select(VcContact).where(VcContact.user_id == user.id)
    if req.contact_ids:
        query = query.where(VcContact.id.in_(req.contact_ids))
    contacts = db.execute(query.order_by(VcContact.id)).scalars().all()

    # 메일 채널로만 관리하는 담당자는 카톡방이 없는 게 정상이라 확인 대상이 아니다.
    def _is_kakao(c) -> bool:
        return bool((c.kakao_room_name or "").strip()) and not (
            c.channel_email == 1 and c.channel_kakao == 0
        )

    targets = [c for c in contacts if _is_kakao(c)]
    skipped = [c.name for c in contacts if not _is_kakao(c)]
    if not targets:
        raise HTTPException(status_code=400, detail="확인할 카톡방 이름이 등록된 담당자가 없습니다")

    job = SendJob(user_id=user.id, kind="verify_room", status="queued",
                  total=len(targets), sent=0, failed=0)
    db.add(job)
    db.flush()
    for contact in targets:
        db.add(SendItem(
            job_id=job.id,
            contact_id=contact.id,
            room_name=contact.kakao_room_name,
            # 확인 잡에는 보낼 문구가 없다. 빈 문자열이어야 혹시 구버전 에이전트가
            # 이 잡을 발송으로 오해해도 보낼 내용이 없어 실패로 끝난다(오발송 방지).
            message="",
            status="pending",
        ))
    db.commit()
    return {"job_id": job.id, "total": len(targets), "skipped": skipped}


# ── CRUD ────────────────────────────────────────────────────────────────────

@router.get("")
def list_contacts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"contacts": contact_rows(db, user)}


@router.post("")
def create_contact(
    body: ContactIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="담당자명을 입력하세요")
    contact = VcContact(user_id=user.id, name=name, status=body.status or "active")
    _assign(contact, body)
    if not contact.kakao_room_name and contact.firm:
        # 이름·직함·투자사만으로 실제 방 제목 규칙을 재현할 수 있다(room_name.py).
        contact.kakao_room_name = build_room_name(contact.name, contact.title,
                                                  contact.firm, suffix=DEFAULT_SUFFIX)
    db.add(contact)
    db.commit()
    return {"id": contact.id, "kakao_room_name": contact.kakao_room_name}


@router.get("/{contact_id}")
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contact = _owned(db, contact_id, user)
    acts = db.execute(
        select(ContactActivity).where(ContactActivity.contact_id == contact.id)
    ).scalars().all()
    acts.sort(key=lambda a: (_activity_date(a) or "", a.id), reverse=True)

    sends = db.execute(
        select(SendItem, SendJob)
        .join(SendJob, SendJob.id == SendItem.job_id)
        .where(SendItem.contact_id == contact.id, SendJob.kind != "verify_room")
        .order_by(SendItem.id.desc()).limit(20)
    ).all()

    known = _known_company_names(db)
    return {
        "contact": {
            "id": contact.id,
            "name": contact.name,
            "title": contact.title or "",
            "firm": contact.firm or "",
            "group_name": contact.group_name or "",
            "kakao_room_name": contact.kakao_room_name or "",
            "room_verified": contact.room_verified,
            "invited_status": contact.invited_status or "",
            "channel_kakao": contact.channel_kakao,
            "channel_email": contact.channel_email,
            "email": contact.email or "",
            "phone": contact.phone or "",
            "stages": contact.stages or "",
            "sectors": contact.sectors or "",
            "round_size": contact.round_size or "",
            "status": contact.status,
            "memo": contact.memo or "",
        },
        # 임포트된 월별 기록 + 서비스가 자동으로 쌓는 발송 이력을 한 줄기로 보여준다.
        "timeline": [_activity_view(a, known) for a in acts] + [
            {"date": (item.sent_at or item.created_at or "")[:10], "month": None,
             "kind": job.kind, "content": _send_summary(item, job), "source": "system",
             "companies": [], "company_count": None, "weekday": None, "week": None}
            for item, job in sends
        ],
    }


def _activity_view(act: ContactActivity, known: Dict[str, str]) -> dict:
    """활동 1건 → 화면용. 회차마다 '몇째 주 · 무슨 요일 · 몇 개사 · 어떤 기업'이 보여야 한다.

    기업명은 시트 원문 그대로 두고, 딜 기업 DB에 있는 이름만 표시(matched)만 남긴다
    (DB에 없는 기업이 훨씬 많아 매칭 실패를 오류로 다루지 않는다).
    """
    date = _activity_date(act)
    companies = act.companies
    return {
        "date": date,
        "month": act.month or (date[:7] if date else None),
        "kind": act.kind,
        "content": act.content,
        "source": act.source,
        "weekday": act.weekday or (sheet_import.weekday_of(date) if date else None),
        "week": sheet_import.week_of_month(date) if date else None,
        "company_count": act.company_count or (len(companies) or None),
        "companies": [
            {"name": name, "known": sheet_import.normalize_company_name(name) in known}
            for name in companies
        ],
        "raw_text": act.raw_text,
    }


def _known_company_names(db: Session) -> Dict[str, str]:
    """딜 기업 DB의 기업명(법인 표기 제거) → 원래 이름."""
    rows = db.execute(select(IrCompany.name)).scalars().all()
    return {sheet_import.normalize_company_name(n): n for n in rows if n}


def _send_summary(item: SendItem, job: SendJob) -> str:
    label = {"deal_intro": "딜소개 발송", "ir_delivery": "IR 전달"}.get(job.kind, job.kind)
    state = {"sent": "성공", "failed": "실패", "pending": "대기",
             "canceled": "취소"}.get(item.status, item.status)
    return f"{label} {state} · {item.room_name}"


@router.patch("/{contact_id}")
def update_contact(
    contact_id: int,
    body: ContactIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contact = _owned(db, contact_id, user)
    before_room = contact.kakao_room_name
    if (body.name or "").strip():
        contact.name = body.name.strip()
    _assign(contact, body)
    if contact.kakao_room_name != before_room:
        # 방 이름이 바뀌면 이전 확인 결과는 더 이상 근거가 아니다.
        contact.room_verified = "unverified"
    db.commit()
    return {"ok": True, "room_verified": contact.room_verified}


@router.delete("/{contact_id}")
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contact = _owned(db, contact_id, user)
    db.query(ContactActivity).filter(ContactActivity.contact_id == contact.id).delete()
    db.delete(contact)
    db.commit()
    return {"ok": True}


def _assign(contact: VcContact, body: ContactIn) -> None:
    """None 은 '변경 없음'. 빈 문자열은 '지움'으로 취급한다(부분 수정 PATCH 의미)."""
    for field in ("title", "firm", "group_name", "kakao_room_name", "invited_status",
                  "email", "phone", "stages", "sectors", "round_size", "memo", "status"):
        value = getattr(body, field)
        if value is not None:
            setattr(contact, field, value.strip() if isinstance(value, str) else value)
    if body.channel_kakao is not None:
        contact.channel_kakao = 1 if body.channel_kakao else 0
    if body.channel_email is not None:
        contact.channel_email = 1 if body.channel_email else 0
