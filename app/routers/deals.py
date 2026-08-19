"""딜소개 보내기 — preview + send-list creation (ROADMAP task 1.5, FEATURE_SPEC §5 ①~⑥)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, now_iso
from ..models import (
    DealBatch,
    DealBatchCompany,
    IrCompany,
    MessageTemplate,
    SendItem,
    SendJob,
    User,
    VcContact,
)
from ..services import matcher
from ..services import message_composer as mc
from ..services.message_composer import MAX_COMPANIES_PER_SEND

router = APIRouter(prefix="/api/deals", tags=["deals"])


# --- helpers ---------------------------------------------------------------

def _to_company_view(c: IrCompany) -> mc.CompanyView:
    return mc.CompanyView(
        name=c.name,
        sector_major=c.sector_major,
        sector_minor=c.sector_minor,
        one_liner=c.one_liner,
        revenue_recent=c.revenue_recent,
        funding_total=c.funding_total,
        raise_target=c.raise_target,
        pre_value=c.pre_value,
        competitiveness=c.competitiveness,
        summary=c.summary,
    )


def _to_contact_view(c: VcContact) -> mc.ContactView:
    return mc.ContactView(name=c.name, title=c.title, firm=c.firm)


def _template_body(db: Session, user_id: int, kind: str, fallback: str) -> str:
    """User-owned active template of `kind` if present, else team default, else fallback."""
    own = db.execute(
        select(MessageTemplate)
        .where(MessageTemplate.user_id == user_id,
               MessageTemplate.kind == kind,
               MessageTemplate.is_active == 1)
    ).scalars().first()
    if own:
        return own.body
    team = db.execute(
        select(MessageTemplate)
        .where(MessageTemplate.user_id.is_(None),
               MessageTemplate.kind == kind,
               MessageTemplate.is_active == 1)
    ).scalars().first()
    return team.body if team else fallback


def _has_history(db: Session, contact_id: int) -> bool:
    return db.query(
        exists().where(SendItem.contact_id == contact_id, SendItem.status == "sent")
    ).scalar()


def _compose_for_contact(
    db: Session, user: User, contact: VcContact, companies: List[IrCompany]
) -> mc.ComposeResult:
    has_hist = _has_history(db, contact.id)
    opening_kind = mc.pick_opening_kind(has_hist)
    # 폴백도 실제 운영 스크립트 형식과 동일하게 유지(템플릿 미시드 상황 대비).
    opening_body = _template_body(
        db, user.id, opening_kind,
        "안녕하세요, {담당자명} {직함}\n우리브이씨 ASSET입니다.",
    )
    closing_body = _template_body(
        db, user.id, "closing_day1",
        "핵심 딜 {개수}개사 간단히 공유드립니다.\n관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다.",
    )
    return mc.compose_message(
        opening_body,
        closing_body,
        _to_contact_view(contact),
        [_to_company_view(c) for c in companies],
        stage=mc.STAGE_DAY1,
    )


def _load_companies(db: Session, company_ids: List[int]) -> List[IrCompany]:
    companies = []
    for cid in company_ids:
        c = db.get(IrCompany, cid)
        if c is None:
            raise HTTPException(status_code=404, detail=f"기업 {cid} 없음")
        if not c.introducible:
            raise HTTPException(status_code=400, detail=f"'{c.name}'은(는) 요약문 미작성 — 발송 불가")
        companies.append(c)
    return companies


# --- schemas ---------------------------------------------------------------

class PreviewRequest(BaseModel):
    company_ids: List[int]
    contact_ids: List[int]


class SendRequest(BaseModel):
    company_ids: List[int]
    contact_ids: List[int]
    title: Optional[str] = None


# --- endpoints -------------------------------------------------------------

@router.post("/preview")
def preview(
    req: PreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Per-contact composed message previews (FEATURE_SPEC §5 ⑤)."""
    if not (1 <= len(req.company_ids) <= MAX_COMPANIES_PER_SEND):
        raise HTTPException(
            status_code=400,
            detail=f"기업은 1~{MAX_COMPANIES_PER_SEND}개 선택하세요",
        )
    companies = _load_companies(db, req.company_ids)
    previews = []
    for contact_id in req.contact_ids:
        contact = db.get(VcContact, contact_id)
        if contact is None or contact.user_id != user.id:
            continue
        result = _compose_for_contact(db, user, contact, companies)
        room_ok = bool(contact.kakao_room_name) and contact.room_verified in ("verified", "unverified")
        # 투자분야/단계/라운드 규모 적합도 — 성향과 어긋나는 딜은 발송 전 경고(DRAFT_REFERENCE).
        fit = matcher.evaluate_contact(contact, companies)
        previews.append({
            "contact_id": contact.id,
            "name": contact.name,
            "title": contact.title,
            "firm": contact.firm,
            "room_name": contact.kakao_room_name,
            "room_verified": contact.room_verified,
            "room_warning": None if contact.kakao_room_name else "카톡방 이름 미등록",
            "message": result.text,
            "char_count": result.char_count,
            "too_long": result.too_long,
            "warnings": result.warnings + fit.warnings,
            "has_history": _has_history(db, contact.id),
            "fit": {
                "fit_count": fit.fit_count,
                "mismatch_count": fit.mismatch_count,
                "companies": [
                    {"company_id": f.company_id, "name": f.company_name,
                     "verdict": f.verdict, "reasons": f.reasons}
                    for f in fit.fits
                ],
            },
        })
    return {"previews": previews}


@router.post("/send")
def create_send_list(
    req: SendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create deal_batch + send_job(queued) + send_items(pending) with message snapshots.

    FEATURE_SPEC §5 ⑥: 발송 목록 생성 → send_job(queued). The mock/real agent
    then claims it via the queue API.
    """
    if not (1 <= len(req.company_ids) <= MAX_COMPANIES_PER_SEND):
        raise HTTPException(
            status_code=400,
            detail=f"기업은 1~{MAX_COMPANIES_PER_SEND}개 선택하세요",
        )
    if not req.contact_ids:
        raise HTTPException(status_code=400, detail="대상 담당자를 1명 이상 선택하세요")

    companies = _load_companies(db, req.company_ids)

    # Resolve + validate target contacts (must be owned, must have a room name).
    contacts: List[VcContact] = []
    for contact_id in req.contact_ids:
        contact = db.get(VcContact, contact_id)
        if contact is None or contact.user_id != user.id:
            raise HTTPException(status_code=404, detail=f"담당자 {contact_id} 없음")
        if not contact.kakao_room_name:
            raise HTTPException(
                status_code=400,
                detail=f"'{contact.name}' 카톡방 이름 미등록 — 발송 대상에서 제외하세요",
            )
        contacts.append(contact)

    # Batch + companies
    batch = DealBatch(
        user_id=user.id,
        title=req.title or "딜소개 회차",
        sent_date=now_iso()[:10],
        cycle_type="adhoc",
    )
    db.add(batch)
    db.flush()
    for pos, company in enumerate(companies, start=1):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=pos))

    # Job (queued) + items (pending, snapshotted message + room name)
    job = SendJob(
        user_id=user.id, kind="deal_intro", batch_id=batch.id,
        status="queued", total=len(contacts), sent=0, failed=0,
    )
    db.add(job)
    db.flush()

    for contact in contacts:
        result = _compose_for_contact(db, user, contact, companies)
        db.add(SendItem(
            job_id=job.id,
            contact_id=contact.id,
            stage=mc.STAGE_DAY1,
            room_name=contact.kakao_room_name,
            message=result.text,
            status="pending",
        ))

    db.commit()
    return {"job_id": job.id, "batch_id": batch.id, "total": len(contacts), "status": job.status}
