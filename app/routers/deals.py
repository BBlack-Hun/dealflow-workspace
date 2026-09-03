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
from ..services import (deal_numbers, deal_queue, ir_attach, sheet_owner,
                        sourcing_link, sourcing_msg, template_pick)
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
    """이 사람이 이 종류에 쓸 문구. 없으면 코드에 적힌 폴백.

    고르는 규칙은 `template_pick.pick()` 한 곳에 있다 — 딜소개와 딜 소싱이
    서로 다른 규칙으로 고르면 같은 사람이 화면마다 다른 문구를 받는다.

    폴백은 팀 기본이 여럿인데 아직 아무것도 고르지 않았을 때도 쓰인다.
    코드에 적힌 한 문장이라 누구에게나 같다 — 문구가 비어 나가는 것보다는
    같은 문장이 나가는 편이 낫고, 그동안 문구 화면에는 "골라 주세요" 가 뜬다.
    """
    t = template_pick.pick(db, user_id, kind)
    return t.body if t else fallback


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
    #
    # **{자료링크} 를 뺐다.** 구글 드라이브 링크를 문구에 실어 보내는 방식은
    # 폐기했다 — 자료는 이제 사람이 PC 카톡에서 파일로 직접 첨부한다.
    MODE_IR: ("ir_delivery",
              "{기업목록} IR deck 먼저 전달드리겠습니다.",
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


def opening_is_included(mode: str) -> bool:
    """이 방식이 인사말을 붙이는가.

    인사말은 **기본으로 붙인다.** 빼는 것은 선호 분야를 되물을 때뿐이다 —
    그건 이미 대화가 오간 방에 한 줄만 덧붙이는 것이라 다시 인사하면
    어색하다. 화면 기본값과 같아야 한다(deals.js) — 다르면 미리보기와
    실제로 나가는 것이 달라진다.

    문구 화면도 이 판단을 그대로 쓴다. 두 곳에서 따로 정하면 "합쳐 보여 준
    문구"와 "실제로 나가는 문구"가 인사말 한 덩어리만큼 어긋난다.
    """
    return mode != MODE_ASK


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
        include_opening = opening_is_included(mode)

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
        # 자료 전달의 "2번 기업 …" — 번호를 새로 매기지 않고 **딜 소개에서
        # 붙인 번호**를 되읽는다(`deal_numbers`).
        company_list=(deal_numbers.company_list(db, contact.id, companies)
                      if mode == MODE_IR else None),
        # `file_links` · `link_blocks` 를 넘기지 않는다 — 자료 전달은 이제
        # **한 통**이다. 링크가 빠졌으니 먼저 던질 것도 없다.
    )


# 자료 전달이 짚는 번호(`2번 기업 …`)를 만들던 자리가 여기였다
# (`deal_positions` · `build_company_list`). **`services/deal_numbers.py` 로
# 옮겼다** — 번호를 정하는 곳과 되읽는 곳이 떨어져 있어서 서로 다른 번호를
# 냈다. 딜 소개는 고른 차례로 `1) 2) 3)` 을 붙이는데, 자료 전달은 "마지막으로
# 나간 회차" 를 봐서 자료를 한 번 보내고 나면 1 부터 다시 셌고 리마인드를 한
# 통 보내면 번호가 사라졌다. 이제 양쪽이 그 한 모듈을 함께 쓴다.


# 자료 전달 문구에 **구글 드라이브 링크를 실어 보내던 자리**가 여기였다
# (`build_file_links` · `build_link_blocks`). 링크를 한 통씩 먼저 던지고
# 설명을 마지막에 붙였는데, 그 방식 자체를 폐기했다 — 자료는 이제 사람이
# PC 카톡에서 **파일로 직접 첨부**한다.
#
# **자료 칸은 그대로 쓴다.** 나가는 문구에서만 뗀 것이지, 어느 자료를 보낼지는
# 여전히 그 칸으로 안다 — 다만 담기는 값이 링크에서 **파일명**으로 바뀌었다
# (`ir_companies.ir_file_name`, 0056).
#
# 그 파일명이 이제 **발송 건에 함께 실린다**(`SendItem.files_json`) — 자동
# 첨부를 켠 계정에 한해서다(`services/ir_attach.py`). 켜지 않은 계정은 지금까지
# 그대로: 문구만 나가고 사람이 PC 카톡에서 파일을 붙인다.


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


def sample_message(db: Session, user: User, mode: str, bucket: str = "") -> str:
    """받는 사람을 고르기 전, 이 방식으로 나갈 문구 전문(인사말 + 본문).

    문구 화면이 조각(인사말 / 안내문)만 보여 줘서 **정작 무엇이 나가는지**
    알 수 없었다. 합치는 규칙을 화면 쪽에 다시 적으면 두 벌이 되고, 두 벌은
    반드시 어긋난다 — 그래서 발송 화면의 기본 미리보기가 지나는 길을
    그대로 지난다.

    인사말은 **첫 연락 기준**이다. 가상의 받는 사람에게는 발송 이력이 없어
    `pick_opening_kind` 가 늘 '첫 연락'을 고른다. 화면에도 그렇게 적는다.
    """
    who = _SampleRecipient(bucket if mode == MODE_SOURCING else "")
    return _compose_for_contact(db, user, who, [], mode=mode).text


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
        # 목록에 안 뜨는 사람은 **보내지도 않는다.** 화면에서 걸러 두었어도
        # 여기서 한 번 더 본다 — 오래된 탭에 남아 있던 체크박스나 손으로 만든
        # 요청으로도 id 는 들어올 수 있고, 그때는 되돌릴 수가 없다.
        rows = sheet_owner.investors(db, db.execute(
            select(VcContact).where(VcContact.id.in_(ids),
                                    VcContact.user_id == user.id)
        ).scalars().all())
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
    # 딜 소싱에서 **화면이 고른 갈래**. 갈래마다 문구가 다른데(`sourcing_msg`),
    # 아직 아무도 안 골랐을 때는 어느 갈래를 보여 줄지 화면만 안다 —
    # 이 값이 없으면 늘 첫 갈래가 떠서, M&A 를 눌러도 시리즈 A 문구가 보였다.
    # 사람을 고른 뒤에는 그 사람의 갈래가 이기므로 여기서만 쓰인다.
    bucket: str = ""


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
    # 자료를 **발송기가 붙이는가**. 미리보기와 발송 목록 만들기가 같은 판단을
    # 읽어야 한다 — 화면은 "손으로 붙이세요" 인데 파일이 함께 나가면(또는 그
    # 반대면) 사람은 자료를 두 번 보내거나 한 번도 안 보낸다.
    attach_on = req.mode == MODE_IR and ir_attach.auto_attach_enabled(db, user)
    # 화면이 고른 갈래를 먼저 쓴다. 없을 때만 첫 갈래로 돌아간다.
    sample_bucket = (req.bucket or "").strip() or _sample_bucket(db)
    recipients = ([_SampleRecipient(sample_bucket if sourcing else "")]
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
             f"IR 기업 현황에서 한줄소개·숫자를 채우면 문구가 좋아집니다"]
            if thin and req.mode != MODE_IR else []
        )
        # 파일명이 비어 있으면 **붙일 것을 못 찾는다.** 발송기가 붙이든 사람이
        # 붙이든 마찬가지다. 발송 목록을 만들기 **전에** 알려야 한다.
        #
        # 자동 첨부를 켠 계정에서는 경고로 끝나지 않는다 — 목록을 만드는 자리가
        # 아예 막는다(`create_send_list`). 자료 없이 "보내드렸습니다" 만 나가는
        # 것이 제일 나쁘기 때문이다.
        if req.mode == MODE_IR:
            no_file = ir_attach.missing_files(companies)
            if no_file:
                thin_warnings.append(
                    f"첨부할 IR 자료가 없는 기업: {', '.join(no_file)} — "
                    + ("IR 기업 현황에 자료 파일명을 등록해야 발송할 수 있습니다"
                       if attach_on else
                       "IR 기업 현황에 자료 파일명을 등록하세요")
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
            # 몇 통으로 나가는지 화면에서 보여야 한다. 자료 전달은 링크 방식을
            # 폐기한 뒤로 한 통이라 여기가 비지만, 나눠 보내는 길 자체는 남는다.
            "parts": list(result.parts),
            "char_count": result.char_count,
            "too_long": result.too_long,
            "warnings": result.warnings + fit.warnings + thin_warnings,
            # 소싱 대상은 다른 표에 있다 — 같은 번호의 투자사 담당자 이력을
            # 제 것으로 읽으면 안 된다.
            "has_history": False if (sourcing or sample) else _has_history(db, contact.id),
            # 이 문구는 아직 아무에게도 가지 않는다.
            "sample": sample,
            # IR 자료 전달에 딸려 갈 자료. **링크가 아니라 파일 이름**이다(0056).
            # 자동 첨부를 켰으면 발송기가 이 이름으로 파일을 찾아 붙이고,
            # 켜지 않았으면 사람이 이 이름을 보고 PC 카톡에서 붙인다.
            "attachments": ([{"name": c.name, "file": c.ir_file_name or ""}
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
    # 자료를 발송기가 붙이는지 **화면도 알아야 한다** — [보낼 자료] 목록의
    # 말이 달라지고(붙여 보냅니다 / 손으로 붙이세요), 안내창도 그 판단을 따른다.
    return {"previews": previews, "auto_attach": attach_on}


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

    # ── 자료를 발송기가 붙이는가 ────────────────────────────────────────────
    #
    # 켠 계정만 이 길을 탄다(`services/ir_attach.py` 에 왜 그 칸으로 가르는지
    # 적어 두었다). 켜지 않은 계정은 지금까지 그대로 — 문구만 나가고 사람이
    # PC 카톡에서 파일을 붙인다.
    #
    # 메일에는 붙이지 않는다. 파일은 **각자 PC** 에 있고 메일은 서버가 보낸다 —
    # 서버에는 그 파일이 없다(`services/mail_sender.py`).
    attach_files: list = []
    if req.mode == MODE_IR and not by_email and ir_attach.auto_attach_enabled(db, user):
        # 파일명이 빈 기업이 하나라도 있으면 **목록을 만들지 않는다.**
        #
        # 만들어 두면 발송기가 그 건에서 실패하고, 실패한 건은 문구도 안 나가서
        # 그 사람만 아무것도 못 받는다 — 그것을 회차가 끝난 뒤에 알게 된다.
        # 방 이름이 없을 때와 같은 자리에서 같은 방식으로 막는다: **말하고 멈춘다.**
        blank = ir_attach.missing_files(companies)
        if blank:
            raise HTTPException(
                status_code=400,
                detail=(f"'{blank[0]}' IR 자료 파일명 미등록 — IR 기업 현황에서 "
                        f"파일명을 넣거나 발송 대상에서 제외하세요"))
        attach_files = ir_attach.file_names(companies)

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
    # 화면에서 뺀 사람은 **보내지도 않는다.** 오래된 탭에 남아 있던 체크나 손으로
    # 만든 요청으로도 id 는 들어올 수 있고, 나간 뒤에는 되돌릴 수가 없다.
    #
    # 연결 단계까지 여기서 막지는 않는다 — 그쪽은 **보낼 방이 없다**는 뜻이고,
    # 방이 없는 것은 바로 아래에서 이미 막는다. 멈춰 둔 것은 다르다: 방이
    # 멀쩡히 있어도 **사람이 보내지 말라고 정해 둔 것**이라, 여기서 막지 않으면
    # 화면에서 뺀 사람에게 그대로 나간다.
    #
    # 조용히 빼지 않고 **말하고 멈춘다.** 골라 둔 사람이 소리 없이 사라지면
    # 몇 명에게 나갔는지 아무도 모른다(빈 문구를 막는 것과 같은 이유).
    if not sourcing:
        held = [c for c in contacts if sheet_owner.is_paused(c)]
        if held:
            raise HTTPException(
                status_code=400,
                detail=(f"'{held[0].name}' "
                        f"{sheet_owner.STATUS_LABELS[sheet_owner.STATUS_PAUSED]}"
                        " — 발송 대상에서 제외하세요"))
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
    # 회차에 남기는 번호 = 문구에 붙는 번호. 같은 자리에서 가져온다 —
    # 자료 전달이 나중에 이 번호를 되읽어 "2번 기업 …" 이라고 짚는다.
    for pos, company in deal_numbers.numbered(companies):
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
            # 함께 붙여 보낼 자료. **고른 차례 그대로** — 발송기가 이 차례로
            # 파일을 먼저 보내고 문구를 마지막에 보낸다.
            files_json=(json.dumps(attach_files, ensure_ascii=False)
                        if attach_files else None),
            status="pending",
        ))

    db.commit()

    if by_email:
        # 요청 안에서 다 보내면 110명일 때 몇 분이 걸려 요청이 끊긴다.
        # 목록만 만들고 뒤에서 한 건씩 보낸다 — 진행 화면이 카톡과 똑같이 폴링한다.
        background.add_task(mail_sender.send_job, job.id)

    return {"job_id": job.id, "batch_id": batch.id, "total": len(contacts),
            "status": job.status, "channel": req.channel}


# ── 예약 큐 ─────────────────────────────────────────────────────────────────
#
# 그룹마다 붙일 기업이 달라진다고 해서 만든 자리다. 줄 하나가 **그룹 + 기업
# 묶음 + 문구**이고, 사람이 [시작] 을 눌러야 발송 목록이 생긴다.
#
# **여기서 발송 경로를 새로 만들지 않는다.** [시작] 은 위 `create_send_list`
# 를 그대로 부른다 — 방 이름 확인·`검토중단` 막이·테스트 방 치환·문구 스냅숏
# 이 전부 그 함수 안에 있다. 여기에 한 벌 더 적으면 그중 하나가 빠진 채로
# 실투자사 카톡방에 나간다.

class QueueAddRequest(BaseModel):
    """예약 한 줄. **받는 사람이 없다** — 그룹 이름만 담는다.

    대상을 굳혀 두면 예약해 둔 사이에 카톡방을 나갔거나 `검토중단` 이 된 분께
    그대로 나간다. [시작] 이 그때의 명단을 다시 계산한다.
    """

    # 빈 문자열이 `(그룹 없음)` 이다 — 그룹을 안 정해 둔 분들에게 보내는 줄.
    group_name: str = ""
    company_ids: List[int] = []
    title: Optional[str] = None
    opening_template_id: Optional[int] = None
    closing_template_id: Optional[int] = None


class QueueStartRequest(BaseModel):
    """[시작]. `shown` 은 **화면에 적혀 있던 수**다.

    서버가 지금 세어 본 수와 다르면 그냥 보내지 않고 그 차이를 말해 준다
    (`deal_queue.difference_note`). 조용히 다른 수로 나가면, 몇 명에게 나갔는지
    아무도 모르는 채로 되돌릴 수 없는 일이 끝나 있다.
    """

    shown: Optional[int] = None
    # 차이를 읽고 사람이 그래도 진행하겠다고 한 뒤의 두 번째 요청.
    confirmed: bool = False


def _queue_item(db: Session, item_id: int, user: User):
    """내 예약 줄만. 남의 줄은 **없는 것으로 답한다** — 번호만 바꿔 가며
    남이 무엇을 예약해 두었는지 알아낼 수 있으면 안 된다."""
    from ..models import DealQueueItem

    item = db.get(DealQueueItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다")
    return item


@router.post("/queue")
def add_queue_item(
    req: QueueAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """예약을 한 줄 세운다. **아무것도 보내지 않는다.**"""
    from ..models import DealQueueCompany, DealQueueItem

    if not (1 <= len(req.company_ids) <= MAX_COMPANIES_PER_SEND):
        raise HTTPException(
            status_code=400,
            detail=f"기업은 1~{MAX_COMPANIES_PER_SEND}개 선택하세요")
    # 없는 기업을 예약해 두면 [시작] 을 누르는 순간에야 죽는다 — 지금 막는다.
    _load_companies(db, req.company_ids)

    item = DealQueueItem(
        user_id=user.id,
        # 앞뒤 공백을 여기서 턴다. `group_of` 가 돌려주는 값과 글자가 달라지면
        # 대상을 고를 때 아무도 안 걸린다.
        group_name=(req.group_name or "").strip(),
        title=(req.title or "").strip() or MODE_TITLES[MODE_DEAL],
        opening_template_id=req.opening_template_id,
        closing_template_id=req.closing_template_id,
        status=deal_queue.STATUS_WAITING,
    )
    db.add(item)
    db.flush()
    for pos, cid in enumerate(req.company_ids, start=1):
        db.add(DealQueueCompany(item_id=item.id, company_id=cid, position=pos))
    db.commit()
    # 지금 몇 명인지 함께 돌려준다 — 줄이 생기자마자 대상 수가 보여야
    # 그룹을 잘못 고른 것을 바로 안다.
    return {"item_id": item.id,
            "target_count": len(deal_queue.targets(db, user, item.group_name))}


@router.post("/queue/{item_id}/start")
def start_queue_item(
    item_id: int,
    req: QueueStartRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """예약을 발송 목록으로 만든다 — **대상은 지금 다시 센다.**

    화면에 적혀 있던 수(`shown`)와 지금 수가 다르면 먼저 그 차이를 돌려준다.
    사람이 읽고 `confirmed` 로 다시 부르면 그때 보낸다.
    """
    item = _queue_item(db, item_id, user)
    if item.status != deal_queue.STATUS_WAITING:
        # 두 번 눌러 두 번 나가는 일을 막는다. 창을 두 개 열어 두면 실제로 그렇다.
        raise HTTPException(
            status_code=400,
            detail=f"이미 {deal_queue.STATUS_LABELS.get(item.status, item.status)} 인 예약입니다")

    people = deal_queue.targets(db, user, item.group_name)
    if not people:
        raise HTTPException(
            status_code=400,
            detail=(f"[{deal_queue.group_label(item.group_name)}] 지금 보낼 수 있는 "
                    "분이 없습니다 — 투자사 관리 현황에서 연결·상태를 확인하세요"))
    if req.shown is not None and req.shown != len(people) and not req.confirmed:
        # **조용히 다른 수로 보내지 않는다.** 200 으로 돌려주는 것은 실패가
        # 아니기 때문이다 — 화면은 이 말을 확인창에 그대로 띄우고, 사람이
        # 예라고 하면 `confirmed` 로 한 번 더 부른다.
        return {"ok": False, "needs_confirm": True,
                "shown": req.shown, "now": len(people),
                "message": deal_queue.difference_note(
                    req.shown, len(people), item.group_name)}

    result = create_send_list(
        SendRequest(
            company_ids=deal_queue.company_ids(item),
            contact_ids=[c.id for c in people],
            title=item.title,
            mode=MODE_DEAL,
            channel="kakao",
            opening_template_id=item.opening_template_id,
            closing_template_id=item.closing_template_id,
        ),
        background, db, user,
    )
    item.status = deal_queue.STATUS_STARTED
    item.job_id = result["job_id"]
    item.started_at = now_iso()
    db.commit()
    return {"ok": True, "job_id": result["job_id"], "total": result["total"],
            "status": item.status}


@router.post("/queue/{item_id}/cancel")
def cancel_queue_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """예약을 접는다. **지우지 않는다** — 무엇을 세워 뒀다가 접었는지가
    화면에 남아야, 안 나간 이유를 나중에 찾을 수 있다."""
    item = _queue_item(db, item_id, user)
    if item.status != deal_queue.STATUS_WAITING:
        raise HTTPException(
            status_code=400,
            detail=f"이미 {deal_queue.STATUS_LABELS.get(item.status, item.status)} 인 예약입니다")
    item.status = deal_queue.STATUS_CANCELED
    db.commit()
    return {"ok": True, "status": item.status}
