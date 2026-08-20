"""딜소개 보내기 — preview + send-list creation (ROADMAP task 1.5, FEATURE_SPEC §5 ①~⑥)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import config
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


def _template_body_by_id(db: Session, user: User, template_id: Optional[int]) -> Optional[str]:
    """발송 화면에서 고른 문구. 남의 개인 문구는 쓸 수 없다."""
    if not template_id:
        return None
    t = db.get(MessageTemplate, template_id)
    if t is None:
        return None
    if t.user_id is not None and t.user_id != user.id:
        return None
    return t.body


# 보내는 방식. 화면의 두 탭과 1:1로 맞춘다.
MODE_DEAL = "deal"      # 인사말 + 안내문 + 기업 목록
MODE_ASK = "ask"        # 인사말 + 문구 한 줄 (기업 목록 없음)

# 문구만 보낼 때 쓰는 기본값. 딜소개를 보냈는데 답이 없을 때, 목록을 또 밀어 넣기보다
# 무엇을 보고 싶은지 되묻는 편이 답이 온다.
ASK_FALLBACK = "선호하는 기업분야 말씀해주시면 맞추어 딜 공유해드리겠습니다."


def _compose_for_contact(
    db: Session, user: User, contact: VcContact, companies: List[IrCompany],
    opening_template_id: Optional[int] = None,
    closing_template_id: Optional[int] = None,
    mode: str = MODE_DEAL,
    include_opening: Optional[bool] = None,
) -> mc.ComposeResult:
    # 인사말 기본값은 방식마다 다르다. 문구만 보낼 때는 이미 대화가 오간 방이라
    # 인사를 다시 붙이지 않는 편이 자연스럽다. 화면에서 켜고 끌 수 있다.
    if include_opening is None:
        include_opening = mode != MODE_ASK

    has_hist = _has_history(db, contact.id)
    opening_kind = mc.pick_opening_kind(has_hist)
    # 폴백도 실제 운영 스크립트 형식과 동일하게 유지(템플릿 미시드 상황 대비).
    opening_body = _template_body(
        db, user.id, opening_kind,
        "안녕하세요, {담당자명} {직함}\n우리브이씨 ASSET입니다.",
    )
    if mode == MODE_ASK:
        closing_body = _template_body(db, user.id, "ask_preference", ASK_FALLBACK)
    else:
        closing_body = _template_body(
            db, user.id, "closing_day1",
            "핵심 딜 {개수}개사 간단히 공유드립니다.\n관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다.",
        )
    # 화면에서 고른 문구가 있으면 그것을 우선한다.
    opening_body = _template_body_by_id(db, user, opening_template_id) or opening_body
    closing_body = _template_body_by_id(db, user, closing_template_id) or closing_body

    return mc.compose_message(
        opening_body,
        closing_body,
        _to_contact_view(contact),
        [] if mode == MODE_ASK else [_to_company_view(c) for c in companies],
        # STAGE_DAY1 이 아니면 기업 목록을 붙이지 않는다(composer 규칙).
        stage=mc.STAGE_REMIND if mode == MODE_ASK else mc.STAGE_DAY1,
        include_opening=include_opening,
    )


def _apply_test_room(contact: VcContact, text: str) -> tuple:
    """테스트 모드면 발송 대상 방을 테스트 방 하나로 바꾼다.

    config.TEST_ROOM 이 설정돼 있으면 실제 담당자 방으로 나가지 않고 전부
    그 방으로만 간다. 실투자사 150명에게 잘못 나가는 사고를 막기 위한 장치.
    누구에게 갈 문구였는지 알 수 있도록 머리말을 붙인다.
    """
    if not config.TEST_ROOM:
        return contact.kakao_room_name, text
    who = f"{contact.name} {contact.title or ''}".strip()
    firm = f" / {contact.firm}" if contact.firm else ""
    banner = f"[테스트 발송 → {who}{firm}]\n원래 방: {contact.kakao_room_name}\n\n"
    return config.TEST_ROOM, banner + text


def _load_companies(db: Session, company_ids: List[int]) -> List[IrCompany]:
    companies = []
    for cid in company_ids:
        c = db.get(IrCompany, cid)
        if c is None:
            raise HTTPException(status_code=404, detail=f"기업 {cid} 없음")
        # 내용이 부족해도 막지 않는다. 화면에서 '내용 부족'으로 표시해 두고
        # 사람이 알고 고른 것이라면 그 판단을 존중한다(막으면 이유도 모른 채 못 보낸다).
        # 대신 미리보기 경고에 남긴다.
        companies.append(c)
    return companies


# --- schemas ---------------------------------------------------------------

class PreviewRequest(BaseModel):
    company_ids: List[int] = []
    contact_ids: List[int]
    # 발송 화면에서 고른 문구. 없으면 기존대로 활성 템플릿을 쓴다.
    opening_template_id: Optional[int] = None
    closing_template_id: Optional[int] = None
    # "deal" = 기업 목록까지 · "ask" = 문구만
    mode: str = MODE_DEAL
    # 인사말을 붙일지. None 이면 방식별 기본값(딜소개 O · 문구만 X)을 쓴다.
    include_opening: Optional[bool] = None


class MessageOverride(BaseModel):
    """미리보기에서 사람이 직접 고친 문구."""
    contact_id: int
    message: str


class SendRequest(BaseModel):
    company_ids: List[int] = []
    contact_ids: List[int]
    title: Optional[str] = None
    mode: str = MODE_DEAL
    include_opening: Optional[bool] = None
    opening_template_id: Optional[int] = None
    closing_template_id: Optional[int] = None
    # 담당자별 수정본. 없는 담당자는 서버가 다시 조합한다.
    overrides: List[MessageOverride] = []


def _override_map(req: SendRequest, contact_ids: set) -> dict:
    """수정본을 {contact_id: message} 로 정리한다.

    발송 대상이 아닌 담당자의 수정본은 무시한다(화면에서 대상을 뺐는데
    수정본만 남아 엉뚱한 사람에게 나가는 일을 막는다).
    빈 문구는 사고이므로 조용히 넘기지 않고 막는다.
    """
    out = {}
    for ov in req.overrides:
        if ov.contact_id not in contact_ids:
            continue
        text = ov.message.strip()
        if not text:
            raise HTTPException(status_code=400,
                                detail="수정한 문구가 비어 있습니다 — 내용을 확인하세요")
        if len(text) > mc.MESSAGE_WARN_CHARS * 2:
            raise HTTPException(status_code=400, detail="수정한 문구가 너무 깁니다")
        out[ov.contact_id] = text
    return out


# --- endpoints -------------------------------------------------------------

@router.post("/preview")
def preview(
    req: PreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Per-contact composed message previews (FEATURE_SPEC §5 ⑤)."""
    if req.mode != MODE_ASK and not (1 <= len(req.company_ids) <= MAX_COMPANIES_PER_SEND):
        raise HTTPException(
            status_code=400,
            detail=f"기업은 1~{MAX_COMPANIES_PER_SEND}개 선택하세요",
        )
    companies = [] if req.mode == MODE_ASK else _load_companies(db, req.company_ids)
    previews = []
    for contact_id in req.contact_ids:
        contact = db.get(VcContact, contact_id)
        if contact is None or contact.user_id != user.id:
            continue
        result = _compose_for_contact(db, user, contact, companies,
                                      req.opening_template_id, req.closing_template_id,
                                      mode=req.mode,
                                      include_opening=req.include_opening)
        room_ok = bool(contact.kakao_room_name) and contact.room_verified in ("verified", "unverified")
        # 투자분야/단계/라운드 규모 적합도 — 성향과 어긋나는 딜은 발송 전 경고(DRAFT_REFERENCE).
        fit = matcher.evaluate_contact(contact, companies)
        thin = [c.name for c in companies if not c.introducible]  # 문구만 모드면 companies 가 비어 있다
        thin_warnings = (
            [f"내용이 부족한 기업이 포함됐습니다: {', '.join(thin)} — "
             f"딜 기업 DB에서 한줄소개·숫자를 채우면 문구가 좋아집니다"]
            if thin else []
        )
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
            "warnings": result.warnings + fit.warnings + thin_warnings,
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
    if req.mode != MODE_ASK and not (1 <= len(req.company_ids) <= MAX_COMPANIES_PER_SEND):
        raise HTTPException(
            status_code=400,
            detail=f"기업은 1~{MAX_COMPANIES_PER_SEND}개 선택하세요",
        )
    if not req.contact_ids:
        raise HTTPException(status_code=400, detail="대상 담당자를 1명 이상 선택하세요")

    companies = [] if req.mode == MODE_ASK else _load_companies(db, req.company_ids)

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
        title=req.title or ("선호 분야 묻기" if req.mode == MODE_ASK else "딜소개 회차"),
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

    overrides = _override_map(req, {c.id for c in contacts})

    for contact in contacts:
        if contact.id in overrides:
            text = overrides[contact.id]      # 사람이 고친 문구가 최우선
        else:
            text = _compose_for_contact(db, user, contact, companies,
                                        req.opening_template_id,
                                        req.closing_template_id,
                                        mode=req.mode,
                                        include_opening=req.include_opening).text
        room_name, message = _apply_test_room(contact, text)
        db.add(SendItem(
            job_id=job.id,
            contact_id=contact.id,
            stage=mc.STAGE_REMIND if req.mode == MODE_ASK else mc.STAGE_DAY1,
            room_name=room_name,
            message=message,
            status="pending",
        ))

    db.commit()
    return {"job_id": job.id, "batch_id": batch.id, "total": len(contacts), "status": job.status}
