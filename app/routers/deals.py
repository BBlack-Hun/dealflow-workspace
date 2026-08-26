"""딜소개 보내기 — preview + send-list creation (ROADMAP task 1.5, FEATURE_SPEC §5 ①~⑥)."""
from __future__ import annotations

import json

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import get_current_user, now_iso
from ..models import (
    SEND_KINDS,
    DealBatch,
    DealBatchCompany,
    IrCompany,
    MessageTemplate,
    SendItem,
    SendJob,
    SourcingContact,
    User,
    VcContact,
)
from ..services import mail_sender, mailer, matcher
from ..services import message_composer as mc
from ..services import sourcing_link, sourcing_msg
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


def _to_contact_view(c) -> mc.ContactView:
    """VcContact 든 SourcingContact 든 문구가 필요로 하는 것은 셋뿐이다."""
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
        exists().where(SendItem.contact_id == contact_id, SendItem.status == "sent",
                       SendItem.job_id.in_(
                           select(SendJob.id).where(SendJob.kind.in_(SEND_KINDS))))
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


# 보내는 방식. 화면의 탭과 1:1로 맞춘다.
MODE_DEAL = "deal"          # 인사말 + 안내문 + 기업 목록
MODE_ASK = "ask"            # 선호 분야 묻기
MODE_REMIND = "remind"      # 리마인드
MODE_MEETING = "meeting"    # 미팅 요청
MODE_IR = "ir"              # IR 자료 전달
MODE_REVIEW = "review"      # 미팅 후기 — 미팅 열흘 뒤 결과 문의
# 딜 소싱 제안 — 받는 사람이 다른 명단(딜 소싱)에 있고, 부탁하는 것도 다르다.
# 우리 딜을 보여 주는 게 아니라 **당신이 뺀 딜을 달라**고 청한다.
MODE_SOURCING = "sourcing"

# 딜소개 말고는 전부 **기업 목록 없이 문구만** 나간다.
# 이미 목록을 받은 사람에게 같은 목록을 다시 밀어 넣는 것은 후속이 아니라 재발송이다.
#
#   방식 → (문구 종류, 템플릿이 없을 때 쓸 문구, 단계)
FOLLOW_UP_MODES = {
    MODE_ASK: ("ask_preference",
               "선호하는 기업분야 말씀해주시면 맞추어 딜 공유해드리겠습니다.",
               mc.STAGE_REMIND),
    MODE_REMIND: ("closing_remind",
                  "지난번 공유드린 기업들 검토 중 궁금하신 점 있으시면 말씀 부탁드립니다.",
                  mc.STAGE_REMIND),
    MODE_MEETING: ("closing_meeting",
                   "다음주 또는 다다음주 20~30분 정도 간단히 미팅 가능하실지요?",
                   mc.STAGE_MEETING),
    # IR 자료 전달은 기업을 고르지만 **목록을 다시 나열하지 않는다**.
    # 이미 목록을 본 사람이 "그 중 몇 번을 달라"고 답한 상황이라,
    # 번호와 이름만 짚어 주면 된다.
    # 인사는 인사말이 맡는다 — 여기에 또 넣으면 인사가 두 번 나간다.
    MODE_IR: ("ir_delivery",
              "{기업목록} IR deck 먼저 전달드리겠습니다.\n\n{자료링크}",
              mc.STAGE_REMIND),
    # 미팅 뒤 열흘쯤 지나 결과를 묻는다. 원본 시트에도 "결과확인전화가 없으면
    # 계약을 잊어버리는 경우가 발생할 수 있습니다" 라고 적혀 있었다.
    MODE_REVIEW: ("meeting_review",
                  "지난번 미팅은 어떻게 보셨는지요? 검토 진행 상황이 궁금합니다.",
                  mc.STAGE_MEETING),
    # 문구는 갈래마다 다르다(호칭·개수·범위). 여기 폴백은 쓰이지 않는다 —
    # `sourcing_msg.body_for()` 가 갈래를 보고 고른다.
    MODE_SOURCING: (sourcing_msg.KIND, "", mc.STAGE_REMIND),
}
#: 발송 화면의 **탭 → 문구 종류**. 한 곳에서 정해 두고 문구 관리 화면이
#: 이것을 읽어 "어느 탭에서 쓰는 문구인지" 를 적는다 — 안 그러면 문구가
#: 열다섯 종류인데 어느 것을 고쳐야 그 탭이 바뀌는지 알 수 없다.
MODE_TEMPLATE_KIND = {
    MODE_DEAL: "closing_day1",
    MODE_IR: "ir_delivery",
    MODE_REMIND: "closing_remind",
    MODE_MEETING: "closing_meeting",
    MODE_REVIEW: "meeting_review",
    MODE_ASK: "ask_preference",
    MODE_SOURCING: sourcing_msg.KIND,
}

MODE_TITLES = {
    MODE_ASK: "선호 분야 묻기",
    MODE_REMIND: "리마인드",
    MODE_MEETING: "미팅 요청",
    MODE_IR: "IR 자료 전달",
    MODE_REVIEW: "미팅 후기",
    MODE_SOURCING: "딜 소싱 제안",
}
MODE_TITLES[MODE_DEAL] = "딜 소개"

# IR 자료 전달은 기업을 고른다(무엇을 보내는지 알아야 한다).
# 나머지 후속 문구는 기업과 무관하다.
MODES_WITH_COMPANIES = {MODE_DEAL, MODE_IR}


def _compose_for_contact(
    db: Session, user: User, contact: VcContact, companies: List[IrCompany],
    opening_template_id: Optional[int] = None,
    closing_template_id: Optional[int] = None,
    mode: str = MODE_DEAL,
    include_opening: Optional[bool] = None,
) -> mc.ComposeResult:
    # 인사말 기본값은 방식마다 다르다. 후속 문구는 이미 대화가 오간 방에 한 줄
    # 덧붙이는 것이라 인사를 다시 붙이지 않는 편이 자연스럽다. 화면에서 켜고 끌 수 있다.
    if include_opening is None:
        # 인사말은 **기본으로 붙인다.** 빼는 것은 선호 분야를 되물을 때뿐이다 —
        # 그건 이미 대화가 오간 방에 한 줄만 덧붙이는 것이라 다시 인사하면
        # 어색하다. 화면 기본값과 같아야 한다(deals.js) — 다르면 미리보기와
        # 실제로 나가는 것이 달라진다.
        include_opening = mode != MODE_ASK

    # 소싱 명단에는 딜소개 이력이 없다(다른 표다) — 늘 '처음 인사' 다.
    has_hist = False if mode == MODE_SOURCING else _has_history(db, contact.id)
    opening_kind = mc.pick_opening_kind(has_hist)
    # 폴백도 실제 운영 스크립트 형식과 동일하게 유지(템플릿 미시드 상황 대비).
    opening_body = _template_body(
        db, user.id, opening_kind,
        "안녕하세요, {담당자명} {직함}\n우리브이씨 ASSET입니다.",
    )
    follow_up = FOLLOW_UP_MODES.get(mode)
    if mode == MODE_SOURCING:
        # 갈래(bucket)가 문구를 정한다 — '대표님/5개사' 를 개인 참여 심사역께
        # 보내면 문구 자체가 어긋난다.
        closing_body = sourcing_msg.body_for(db, user, getattr(contact, "bucket", ""))
    elif follow_up:
        kind, fallback, _stage = follow_up
        closing_body = _template_body(db, user.id, kind, fallback)
    else:
        closing_body = _template_body(
            db, user.id, "closing_day1",
            "핵심 딜 {개수}개사 간단히 공유드립니다.\n관심 가시는 기업 있으시면 IR Deck 공유드리겠습니다.",
        )
    # 화면에서 고른 문구가 있으면 그것을 우선한다.
    opening_body = _template_body_by_id(db, user, opening_template_id) or opening_body
    closing_body = _template_body_by_id(db, user, closing_template_id) or closing_body

    who = _to_contact_view(contact)
    if mode == MODE_SOURCING and not (who.title or "").strip():
        # 직함이 빈 줄이 있다. 그대로 두면 '안녕하세요, 홍길동' 으로 나간다.
        who.title = sourcing_msg.honorific(getattr(contact, "bucket", ""))

    return mc.compose_message(
        opening_body,
        closing_body,
        who,
        [] if follow_up else [_to_company_view(c) for c in companies],
        # STAGE_DAY1 이 아니면 기업 목록을 붙이지 않는다(composer 규칙).
        stage=follow_up[2] if follow_up else mc.STAGE_DAY1,
        include_opening=include_opening,
        company_list=(build_company_list(db, contact, companies)
                      if mode == MODE_IR else None),
        file_links=(build_file_links(db, contact, companies)
                    if mode == MODE_IR else None),
        # 링크를 먼저 한 통씩, 설명은 마지막에 — 카톡에서 읽히는 순서다.
        link_blocks=(build_link_blocks(db, contact, companies)
                     if mode == MODE_IR else None),
    )


def deal_positions(db: Session, contact_id: int) -> dict:
    """이 담당자가 **마지막으로 받은 회차**에서 각 기업이 몇 번이었는지.

    투자사는 "5) 친환경 패키지 …" 처럼 번호로 기억하고 답한다. 자료를 보낼 때
    같은 번호로 짚어 줘야 어느 기업인지 서로 맞는다. 번호를 새로 매기면
    받는 쪽에서는 다른 기업 이야기로 읽힌다.
    """
    batch_id = db.execute(
        select(SendJob.batch_id)
        .join(SendItem, SendItem.job_id == SendJob.id)
        .where(SendItem.contact_id == contact_id, SendItem.status == "sent",
               SendJob.kind.in_(SEND_KINDS),
               SendJob.batch_id.isnot(None))
        .order_by(SendItem.id.desc()).limit(1)
    ).scalar()
    if batch_id is None:
        return {}
    return {
        row.company_id: row.position
        for row in db.execute(
            select(DealBatchCompany).where(DealBatchCompany.batch_id == batch_id)
        ).scalars().all()
    }


def build_company_list(db: Session, contact: VcContact,
                       companies: List[IrCompany]) -> str:
    """'1번 기업 샘플애그' · 여럿이면 '1번 기업 샘플애그, 3번 기업 …'.

    지난 회차에 없던 기업은 번호를 붙이지 않는다 — 없는 번호를 지어내면
    받는 쪽이 자기 목록에서 찾다가 못 찾는다.
    """
    positions = deal_positions(db, contact.id)
    parts = []
    for company in companies:
        no = positions.get(company.id)
        parts.append(f"{no}번 기업 {company.name}" if no else company.name)
    return ", ".join(parts)


def build_file_links(db: Session, contact: VcContact,
                     companies: List[IrCompany]) -> str:
    """자료 전달 문구에 붙는 **링크 묶음**.

        1번 (주)샘플애그
        https://drive.google.com/file/d/…

    이게 없으면 "IR deck 전달드리겠습니다" 만 나가고 정작 자료는 안 간다 —
    실제로 그렇게 나갔다. 받은 쪽은 다시 물어봐야 한다.

    번호는 지난 회차의 번호를 그대로 쓴다(`build_company_list` 와 같은 규칙).
    링크가 없는 기업은 **빼지 않고** 그렇다고 적는다 — 조용히 빠지면 보낸 쪽도
    받은 쪽도 몇 개를 주고받았는지 어긋난다.
    """
    return "\n\n".join(build_link_blocks(db, contact, companies))


def build_link_blocks(db: Session, contact: VcContact,
                      companies: List[IrCompany]) -> List[str]:
    """기업 하나당 한 통. **순서대로** 나간다.

    카톡에서 링크는 각자 미리보기 카드로 떠야 하므로 한 통에 몰아넣지 않는다.
    """
    positions = deal_positions(db, contact.id)
    blocks = []
    for company in companies:
        no = positions.get(company.id)
        head = f"{no}번 {company.name}" if no else company.name
        url = (company.ir_drive_url or "").strip()
        blocks.append(f"{head}\n{url}" if url else f"{head}\n(자료 준비 중)")
    return blocks


def _room_of(contact, linked: dict) -> str:
    """이 사람에게 실제로 보낼 방. 자기 것이 먼저, 없으면 이어진 것."""
    own = (getattr(contact, "kakao_room_name", "") or "").strip()
    return own or (linked.get(getattr(contact, "id", 0)) or {}).get("room", "")


def _apply_test_room(contact, text: str, linked: Optional[dict] = None) -> tuple:
    """테스트 모드면 발송 대상 방을 테스트 방 하나로 바꾼다.

    config.TEST_ROOM 이 설정돼 있으면 실제 담당자 방으로 나가지 않고 전부
    그 방으로만 간다. 실투자사 150명에게 잘못 나가는 사고를 막기 위한 장치.
    누구에게 갈 문구였는지 알 수 있도록 머리말을 붙인다.
    """
    if not config.TEST_ROOM:
        return _room_of(contact, linked or {}), text
    who = f"{contact.name} {contact.title or ''}".strip()
    firm = f" / {contact.firm}" if contact.firm else ""
    banner = (f"[테스트 발송 → {who}{firm}]\n"
              f"원래 방: {_room_of(contact, linked or {})}\n\n")
    return config.TEST_ROOM, banner + text


def _apply_test_room_to_parts(contact, parts: List[str],
                              linked: Optional[dict] = None) -> List[str]:
    """테스트 머리말은 첫 통에만 붙인다.

    통마다 붙이면 테스트 방이 "[테스트 발송 → …]" 로 도배돼 정작 무엇이
    나가는지 안 보인다.
    """
    if not parts or not config.TEST_ROOM:
        return parts
    _room, first = _apply_test_room(contact, parts[0], linked)
    return [first] + parts[1:]


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


class _SampleRecipient:
    """담당자를 고르기 전에 보여 줄 **가상의 받는 사람**.

    문구를 확인하려고 아무나 한 명 체크했다가 그대로 발송을 누르는 일이
    있었다. 고르지 않아도 기본 문구가 보이면 그럴 이유가 없다.

    이름을 `○○○` 로 두는 것은 일부러다 — 진짜 이름이 보이면 그 사람에게
    나갈 문구로 읽힌다.
    """

    id = 0
    name = "○○○"
    title = "심사역"
    firm = "○○벤처스"
    kakao_room_name = ""
    room_verified = "unverified"

    def __init__(self, bucket: str = ""):
        self.bucket = bucket


def _sample_bucket(db: Session) -> str:
    """소싱 기본 문구는 갈래마다 다르다 — 첫 갈래를 보여 준다."""
    row = db.execute(
        select(SourcingContact).order_by(SourcingContact.position,
                                         SourcingContact.id)
    ).scalars().first()
    return row.bucket if row else ""


def _load_recipients(db: Session, user: User, mode: str, ids: List[int]) -> List:
    """이 방식이 보내는 대상. 화면에서 고른 순서를 지킨다.

    딜 소싱만 다른 표(`sourcing_contacts`)에서 온다. 소싱 명단은 스타트업
    관리처럼 **팀 공용**이라 담당자로 거르지 않는다 — 명단 자체가 하나다.
    """
    if mode == MODE_SOURCING:
        rows = db.execute(
            select(SourcingContact).where(SourcingContact.id.in_(ids))
        ).scalars().all()
    else:
        rows = db.execute(
            select(VcContact).where(VcContact.id.in_(ids),
                                    VcContact.user_id == user.id)
        ).scalars().all()
    by_id = {r.id: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


# --- schemas ---------------------------------------------------------------

class PreviewRequest(BaseModel):
    company_ids: List[int] = []
    contact_ids: List[int]
    # 발송 화면에서 고른 문구. 없으면 기존대로 활성 템플릿을 쓴다.
    opening_template_id: Optional[int] = None
    closing_template_id: Optional[int] = None
    # "deal" = 기업 목록까지 · 그 밖에는 문구만 (ask / remind / meeting)
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
    # kakao = 각자 PC의 발송 프로그램 · email = 서버가 SMTP 로 직접
    channel: str = "kakao"
    subject: Optional[str] = None
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
    # 아무도 안 골랐으면 **기본 문구**를 보여 준다. 문구를 확인하려고
    # 아무나 한 명 체크했다가 그대로 발송을 누르는 일이 있었다.
    sample = not req.contact_ids
    if (not sample and req.mode in MODES_WITH_COMPANIES
            and not (1 <= len(req.company_ids) <= MAX_COMPANIES_PER_SEND)):
        raise HTTPException(
            status_code=400,
            detail=f"기업은 1~{MAX_COMPANIES_PER_SEND}개 선택하세요",
        )
    companies = _load_companies(db, req.company_ids) if req.mode in MODES_WITH_COMPANIES else []
    previews = []
    sourcing = req.mode == MODE_SOURCING
    recipients = ([_SampleRecipient(_sample_bucket(db) if sourcing else "")]
                  if sample else _load_recipients(db, user, req.mode, req.contact_ids))
    # 투자사 관리 현황에서 연결해 둔 방이 있으면 미리보기에도 그 방이 떠야 한다 —
    # 화면에는 '방 미등록' 인데 실제로는 나가면, 어디로 갈지 모른 채 누르게 된다.
    linked = sourcing_link.linked_rooms(db, recipients) if sourcing else {}
    for contact in recipients:
        result = _compose_for_contact(db, user, contact, companies,
                                      req.opening_template_id, req.closing_template_id,
                                      mode=req.mode,
                                      include_opening=req.include_opening)
        room = _room_of(contact, linked)
        room_ok = bool(room) and contact.room_verified in ("verified", "unverified")
        if sample:
            room_ok = True          # 가상의 사람에게 방을 물을 것이 없다
        # 투자분야/단계/라운드 규모 적합도 — 성향과 어긋나는 딜은 발송 전 경고(DRAFT_REFERENCE).
        # 소싱 제안은 기업을 붙이지 않아 companies 가 비고, 그러면 견줄 것이
        # 없어 빈 결과가 나온다.
        fit = matcher.evaluate_contact(contact, companies)
        thin = [c.name for c in companies if not c.introducible]  # 문구만 모드면 companies 가 비어 있다
        thin_warnings = (
            [f"내용이 부족한 기업이 포함됐습니다: {', '.join(thin)} — "
             f"IR 기업현황에서 한줄소개·숫자를 채우면 문구가 좋아집니다"]
            if thin and req.mode != MODE_IR else []
        )
        # IR 자료 전달인데 보낼 자료가 없으면 문구만 나가고 자료는 못 보낸다.
        # 발송 목록을 만들기 **전에** 알려야 한다.
        if req.mode == MODE_IR:
            no_file = [c.name for c in companies
                       if not (c.ir_drive_url or "").strip()]
            if no_file:
                thin_warnings.append(
                    f"IR 자료 링크가 없는 기업: {', '.join(no_file)} — "
                    f"IR 기업현황에서 구글드라이브 링크를 넣어주세요"
                )
        previews.append({
            "contact_id": contact.id,
            "name": contact.name,
            "title": contact.title,
            "firm": contact.firm,
            "room_name": room,
            # 이 방이 어디서 왔는지 — 소싱에서 직접 적은 것인지, 투자사 명단에서
            # 이어 온 것인지.
            "room_from": ("투자사 명단"
                          if room and not (contact.kakao_room_name or "").strip()
                          else ""),
            "room_verified": contact.room_verified,
            "room_warning": None if (sample or room) else "카톡방 이름 미등록",
            "message": result.text,
            # 몇 통으로 나가는지 화면에서 보여야 한다 — 링크가 먼저 한 통씩
            # 나가고 설명이 마지막이라는 게 보이지 않으면 확인할 수가 없다.
            "parts": list(result.parts),
            "char_count": result.char_count,
            "too_long": result.too_long,
            "warnings": result.warnings + fit.warnings + thin_warnings,
            # 소싱 대상은 다른 표에 있다 — 같은 번호의 투자사 담당자 이력을
            # 제 것으로 읽으면 안 된다.
            "has_history": False if (sourcing or sample) else _has_history(db, contact.id),
            # 이 문구는 아직 아무에게도 가지 않는다.
            "sample": sample,
            # IR 자료 전달일 때 무엇을 먼저 보내야 하는지 화면에 띄운다.
            "attachments": ([{"name": c.name, "url": c.ir_drive_url or ""}
                             for c in companies] if req.mode == MODE_IR else []),
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
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create deal_batch + send_job(queued) + send_items(pending) with message snapshots.

    FEATURE_SPEC §5 ⑥: 발송 목록 생성 → send_job(queued). The mock/real agent
    then claims it via the queue API.
    """
    if req.mode in MODES_WITH_COMPANIES and not (1 <= len(req.company_ids) <= MAX_COMPANIES_PER_SEND):
        raise HTTPException(
            status_code=400,
            detail=f"기업은 1~{MAX_COMPANIES_PER_SEND}개 선택하세요",
        )
    if not req.contact_ids:
        raise HTTPException(status_code=400, detail="대상 담당자를 1명 이상 선택하세요")

    by_email = req.channel == "email"
    if by_email and not mailer.is_configured():
        raise HTTPException(
            status_code=400,
            detail="메일 서버 설정이 없습니다 — 팀 현황에서 설정을 확인하세요")

    companies = _load_companies(db, req.company_ids) if req.mode in MODES_WITH_COMPANIES else []

    # Resolve + validate target contacts (must be owned, must have a room name).
    sourcing = req.mode == MODE_SOURCING
    contacts = _load_recipients(db, user, req.mode, req.contact_ids)
    # 소싱 대상이 투자사 관리 현황에도 있고 거기서 방을 연결해 뒀다면 그 방을
    # 쓴다 — 같은 사람의 같은 방이라, 다시 적게 하면 오타로 발송이 빠진다.
    linked = sourcing_link.linked_rooms(db, contacts) if sourcing else {}
    missing = set(req.contact_ids) - {c.id for c in contacts}
    if missing:
        raise HTTPException(status_code=404,
                            detail=f"담당자 {sorted(missing)[0]} 없음")
    for contact in contacts:
        if by_email:
            # 주소가 없으면 보낼 방법이 없다. 목록을 만들기 **전에** 막는다 —
            # 만들고 나서 실패로 남기면 보냈다고 착각하기 쉽다.
            problem = mail_sender.address_problem(contact)
            if problem:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{contact.name}' {problem} — 발송 대상에서 제외하세요")
        elif not _room_of(contact, linked):
            raise HTTPException(
                status_code=400,
                detail=f"'{contact.name}' 카톡방 이름 미등록 — 발송 대상에서 제외하세요",
            )

    # Batch + companies
    batch = DealBatch(
        user_id=user.id,
        title=req.title or MODE_TITLES.get(req.mode, "딜소개 회차"),
        sent_date=now_iso()[:10],
        cycle_type="adhoc",
    )
    db.add(batch)
    db.flush()
    for pos, company in enumerate(companies, start=1):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=pos))

    # Job (queued) + items (pending, snapshotted message + room name)
    job = SendJob(
        user_id=user.id,
        # IR 자료 전달은 딜소개와 다른 일이다. 종류를 남겨야 후속을 멈추고
        # 요청을 '전달함'으로 닫을 수 있다.
        kind=("ir_delivery" if req.mode == MODE_IR
              else "sourcing_intro" if sourcing else "deal_intro"),
        batch_id=batch.id,
        status="queued", total=len(contacts), sent=0, failed=0,
    )
    db.add(job)
    db.flush()

    overrides = _override_map(req, {c.id for c in contacts})

    for contact in contacts:
        if contact.id in overrides:
            # 사람이 고친 문구가 최우선. 고친 것은 통째로 한 통이다 —
            # 어디서 끊을지는 고친 사람만 안다.
            text, parts = overrides[contact.id], []
        else:
            composed = _compose_for_contact(db, user, contact, companies,
                                            req.opening_template_id,
                                            req.closing_template_id,
                                            mode=req.mode,
                                            include_opening=req.include_opening)
            text, parts = composed.text, list(composed.parts)
        if by_email:
            # 메일은 테스트 방 치환이 없다 — 주소가 곧 대상이고, 테스트 모드는
            # 카톡방을 하나로 모으는 장치다. 대신 제목에 표시를 남긴다.
            target = (contact.email or "").strip()
            message = text
            subject = (req.subject or "").strip() or (req.title or "딜 소개")
            if config.TEST_ROOM:
                subject = f"[테스트] {subject}"
        else:
            target, message = _apply_test_room(contact, text, linked)
            # 머리말은 **첫 통에만**. 통마다 붙으면 테스트 방이 배너로 도배된다.
            parts = _apply_test_room_to_parts(contact, parts, linked)
            subject = None

        db.add(SendItem(
            job_id=job.id,
            # 소싱 대상은 다른 표에 있다 — 둘 중 하나만 채운다.
            contact_id=None if sourcing else contact.id,
            sourcing_contact_id=contact.id if sourcing else None,
            stage=(FOLLOW_UP_MODES[req.mode][2] if req.mode in FOLLOW_UP_MODES
                   else mc.STAGE_DAY1),
            channel="email" if by_email else "kakao",
            room_name=target,
            subject=subject,
            message=message,
            # 메일은 한 통이다 — 나눠 보낼 곳이 없다.
            parts_json=(json.dumps(parts, ensure_ascii=False)
                        if parts and not by_email else None),
            status="pending",
        ))

    db.commit()

    if by_email:
        # 요청 안에서 다 보내면 110명일 때 몇 분이 걸려 요청이 끊긴다.
        # 목록만 만들고 뒤에서 한 건씩 보낸다 — 진행 화면이 카톡과 똑같이 폴링한다.
        background.add_task(mail_sender.send_job, job.id)

    return {"job_id": job.id, "batch_id": batch.id, "total": len(contacts),
            "status": job.status, "channel": req.channel}
