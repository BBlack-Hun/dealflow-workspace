"""딜소개 보내기 — preview + send-list creation (ROADMAP task 1.5, FEATURE_SPEC §5 ①~⑥)."""
from __future__ import annotations

import json

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import clock
from ..db import get_db
from ..deps import get_current_user, now_iso
from ..models import (
    SEND_KINDS,
    STARTUP_SEND_KIND,
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
from ..services import (deal_numbers, deal_queue, ir_attach, ir_kakao,
                        ir_monthly, manual_send, scheduled_send, sheet_owner,
                        sourcing_link, sourcing_msg, startup_send,
                        template_pick)
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
# 스타트업 월간 발송 — 받는 사람이 **투자사가 아니라 스타트업 대표**다.
#
# 앞의 것들과 다른 점이 셋이다.
#   · 받는 줄이 `ir_companies` 다(사람 표가 아니라 기업 표).
#   · 문구를 여기서 짓지 않는다 — `services/ir_kakao.py` 하나가 짓는다.
#     그래서 `FOLLOW_UP_MODES` 에도 `MODE_TEMPLATE_KIND` 에도 줄이 없다
#     (머리말 문구틀은 `ir_kakao.KIND` 가 안다).
#   · **정해진 한 계정만** 쓸 수 있다(`services/startup_send.may_send`).
MODE_STARTUP = "startup"

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
    MODE_STARTUP: "스타트업 월간 발송",
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
        # 자료 전달의 "[기업2] …" — 번호를 새로 매기지 않고 **딜 소개에서
        # 붙인 번호**를 되읽는다(`deal_numbers`). 모양도 딜 소개와 같다.
        company_list=(deal_numbers.company_list(db, contact.id, companies)
                      if mode == MODE_IR else None),
        # `file_links` · `link_blocks` 를 넘기지 않는다 — 자료 전달은 이제
        # **한 통**이다. 링크가 빠졌으니 먼저 던질 것도 없다.
    )


def _mail_subject(req, contact, companies: List[IrCompany]) -> str:
    """메일 한 통의 제목 — **적은 제목 → 회차명 → "딜 소개"** 그대로다.

    ## 비었을 때의 차례는 손대지 않는다

    제목을 안 적으면 예전과 똑같이 회차명이 나가고, 회차명도 없으면
    `"딜 소개"` 다. 화면의 제목 문구 고르개는 **칸을 채울 뿐**이라
    (`deals.js` 의 `applySubject`), 골라도 서버에는 여느 제목과 똑같이
    글자 하나로 들어온다 — 그래서 여기에 갈래가 늘지 않는다.

    ## 적은 제목만 치환을 지난다

    제목 문구는 문구 화면(`/templates` 의 `mail_subject`)에서 만드는데,
    그 화면은 `{담당자명}`·`{직함}`·`{투자사}`·`{개수}` 를 쓸 수 있다고
    적어 두고 있다. 제목만 그것을 안 지나면 **`{담당자명}` 이 글자 그대로
    투자사 메일함에 꽂힌다** — 이 저장소가 이미 겪은 고장이라
    (`services/ir_kakao.py` 의 같은 자리), 문구가 쓰는 그 손을 그대로 쓴다.
    새 치환 자리는 만들지 않는다(`{회차}`·`{날짜}` 같은 것은 문구에도 없다).

    회차명으로 떨어진 제목은 **치환을 안 지난다.** 회차명은 문구가 아니라
    사람이 그 회차에 붙인 이름이고, 이미 그 이름 그대로 나가고 있는 메일이
    있다 — 여기에 손질을 끼우면 그 제목이 달라진다.

    `{개수}` 가 세는 수는 본문과 같아야 한다. 본문은 딜 소개일 때만 기업을
    세고 후속 문구는 0 이다(`message_composer.compose_message` 의 `count`).
    제목만 다른 수를 말하면 열어 보기 전에 이미 어긋난다.
    """
    typed = (req.subject or "").strip()
    if not typed:
        return req.title or "딜 소개"
    count = 0 if req.mode in FOLLOW_UP_MODES else len(companies)
    return mc.render_template(typed, _to_contact_view(contact),
                              company_count=count)


# 자료 전달이 짚는 번호(`[기업2] …`)를 만들던 자리가 여기였다
# (`deal_positions` · `build_company_list`). **`services/deal_numbers.py` 로
# 옮겼다** — 번호를 정하는 곳과 되읽는 곳이 떨어져 있어서 서로 다른 번호를
# 냈다. 딜 소개는 고른 차례로 `[기업1] [기업2] [기업3]` 을 붙이는데, 자료
# 전달은 "마지막으로 나간 회차" 를 봐서 자료를 한 번 보내고 나면 1 부터 다시
# 셌고 리마인드를 한 통 보내면 번호가 사라졌다. 이제 양쪽이 그 한 모듈을 함께
# 쓴다.


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


# ── 시험방은 **`/setup` 의 시험 단추만** 쓴다  ★ ─────────────────────────────
#
# 예전에는 `config.TEST_ROOM` 이 비어 있지 않으면 **여기를 지나는 모든 발송**의
# 방 이름을 그 한 방으로 바꿔 치웠다(`_apply_test_room`). 딜 소개도 IR 전달도
# 리마인드도 소싱도 스타트업 월간도 전부. 그 장치의 전제는 "운영에는 시험방이
# 없다" 였는데, 전제가 깨지는 순간 **딜 소개가 투자사 대신 시험방으로 갔다** —
# 아무도 못 받았다는 것을 며칠 뒤에나 안다.
#
# 이제 가르는 것은 **잡 종류**다(`models.TEST_SEND_KIND`). 시험 발송은 만드는
# 자리 자체가 다르고(`routers/setup.py: _queue_test_job`) 거기서만 방 이름이
# 시험방으로 굳는다. 이 함수가 만드는 잡은 종류가 무엇이든 `TEST_SEND_KIND` 가
# 아니므로, **여기서는 시험방을 아예 읽지 않는다.**
#
# 그래서 이 자리에 `config.TEST_ROOM` 이 다시 등장하면 안 된다. 되살아나는 것을
# 막는 것은 `tests/test_test_room_scope.py` 다 — 갈래마다 한 줄씩 못박아 둔다.
#
# **리허설은 어떻게 하나.** 담당자 줄의 방 이름 자체를 시험방으로 두면 된다
# (`scripts/rehearsal.py` 가 그렇게 만든다). 방을 바꿔 치우는 장치가 아니라
# 받는 사람이 나인 것이고, 그 편이 화면에 보이는 것과 나가는 것이 같다.


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


def review_message(db: Session, user: User, contact) -> str:
    """미팅을 마친 **그 투자사 담당자**에게 나갈 미팅 후기 문구 전문.

    ## 왜 여기인가 — 짓는 자리를 두 벌로 두지 않는다

    미팅 후기 문구(`meeting_review`)는 이미 이 파일이 짓는다. 발송 화면의
    **미팅 후기** 탭이 그것이고, `FOLLOW_UP_MODES[MODE_REVIEW]` 가 문구 종류와
    폴백과 단계를 정해 둔 그대로 나간다. 그래서 밖에서 이 문구가 필요할 때
    새로 짓지 않고 **이 한 줄을 부른다** — 조립 규칙을 다시 적으면 두 벌이 되고,
    두 벌은 반드시 어긋난다(문구 화면이 `sample_message` 를 부르는 것과 같은
    자리, 같은 이유).

    스타트업 기업 리마인드는 그 값을 치른 자리다 — #133 이 `services/startup_msg.py`
    를 새로 냈는데, 같은 뜻의 문구를 짓는 자리가 이미 있었다(`services/ir_kakao.py`).
    한동안 두 벌이었고, 나중에 하나로 모으면서 그 파일을 지웠다. 여기는 있으니
    만들지 않는다.

    ## 무엇이 들어오나

    받는 사람은 **투자사 담당자**(`VcContact`)다. 스타트업이 아니다 — 미팅을
    한 쪽에게 "그 뒤 어떻게 되셨는지" 를 묻는 문구다.

    미팅 자체는 **문구에 들어가지 않는다.** 이 함수가 받는 것이 미팅이 아니라
    담당자인 까닭이 그것이다 — 문구가 쓰는 값은 이름·직함·투자사 셋뿐이고
    (`_to_contact_view`), 언제 만났는지·무엇을 이야기했는지는 어느 자리에도
    안 꽂힌다. 미팅은 **누구에게 물을지**를 가리키는 데까지만 쓰인다.

    ## 인사말이 붙는다

    `opening_is_included(MODE_REVIEW)` 가 참이라 인사말 + 본문 두 덩이가 나간다.
    발송 화면과 같은 판단을 지나므로 여기서 따로 정하지 않는다 — 정하면 화면이
    보여 준 것과 실제로 나가는 것이 인사말 한 덩어리만큼 어긋난다.
    """
    return _compose_for_contact(db, user, contact, [], mode=MODE_REVIEW).text


def _load_recipients(db: Session, user: User, mode: str, ids: List[int]) -> List:
    """이 방식이 보내는 대상. 화면에서 고른 순서를 지킨다.

    딜 소싱만 다른 표(`sourcing_contacts`)에서 온다. 소싱 명단은 스타트업
    관리처럼 **팀 공용**이라 담당자로 거르지 않는다 — 명단 자체가 하나다.
    """
    if mode == MODE_STARTUP:
        # 받는 줄이 **기업**이다. 고를 수 있는 기업을 정하는 자리는
        # `ir_monthly.contracted` 하나다 — 문서·보고·카톡 세 화면이 이미 그
        # 함수를 지난다. 여기서 조건을 다시 적으면 화면에는 안 뜨는 기업에게
        # 발송만 나가는 날이 온다.
        rows = [c for c in ir_monthly.contracted(db) if c.id in set(ids)]
    elif mode == MODE_SOURCING:
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
    # **만들어만 두고 아직 내보내지 않는다.** 참이면 회차가 `draft` 로 서서
    # 발송 프로그램이 집어가지 않는다(`agent_api.poll` 은 `queued` 만 고른다).
    # 사람이 진행 화면에서 [발송 시작] 을 눌러야 `queued` 가 된다.
    #
    # 어느 달치인가 — `2026-09`. **스타트업 월간 발송에서만 쓴다.**
    #
    # 다른 방식은 달을 모른다(딜소개는 오늘 고른 기업이 전부다). 이 발송만
    # 글의 내용이 달로 정해진다 — `7월 말까지 … 요청한투자사 리스트` 의 그
    # 달이다. 화면이 고른 달을 그대로 실어 보내지 않으면, 화면에서 8월을 보고
    # 눌렀는데 9월치가 나가는 일이 생긴다.
    month: str = ""
    # 발송 화면에서는 오지 않는 값이다(기본 거짓 — 지금까지 그대로 바로 나간다).
    # 쓰는 곳은 결과 문의 대기 목록을 **미리 세워 두는** 자리다
    # (`services/auto_send.py`). 거기서 만들고 나서 상태를 고치는 방법도 있지만,
    # 만드는 것과 고치는 것 사이에 발송기가 폴링하면 **사람이 누르기 전에
    # 나간다.** 세울 때 정해야 그 틈이 없다.
    draft: bool = False
    # **언제 내보낼까** — 비어 있으면 지금까지와 같다(만들면서 바로 나간다).
    # 값이 있으면 회차가 `draft` 로 서서 그 시각을 기다린다
    # (`services/scheduled_send.py`). 화면의 `datetime-local` 값 그대로다.
    #
    # 여기서 함께 받는 이유: 목록을 만들고 나서 시각을 다는 두 걸음으로 나누면,
    # 그 사이에 회차가 `queued` 로 서 있는 순간이 생기거나(발송기가 집어간다)
    # 시각이 안 되는 값이었을 때 **아무도 안 볼 회차**만 남는다. 만들 때
    # 정해야 그 틈이 없다(`draft` 가 같은 이유로 여기 있다).
    scheduled_at: str = ""


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
    # 스타트업 월간 발송은 **여기서 미리 보지 않는다.** 그 글을 짓는 자리는
    # `ir_kakao` 하나이고, 보여 주는 화면도 따로 있다(`/deals/startup-ir`).
    # 이 길로 들여보내면 `_compose_for_contact` 가 기업 id 를 투자사 담당자 id 로
    # 알고 딜소개 문구를 지어 내놓는다 — 실제로 나갈 글과 아무 상관이 없는
    # 미리보기라, 그것을 보고 [발송] 을 누르는 쪽이 훨씬 위험하다.
    if req.mode == MODE_STARTUP:
        if not startup_send.may_send(db, user):
            raise HTTPException(status_code=404, detail="없는 자리입니다")
        raise HTTPException(status_code=400,
                            detail=f"{startup_send.LABEL} 화면에서 보세요")
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
            # IR 자료 전달에 딸려 갈 자료. **번호와 파일 이름**이 함께 간다.
            #
            # **번호**(#112) — 자료를 붙이는 차례다. 그 번호는 담당자마다 다르고
            # (딜 소개에서 붙은 번호를 되읽는다 — `deal_numbers`) 화면이 고른
            # 차례를 세면 목록은 `1`, 문구는 `[기업2] …` 가 되어 어느 쪽이
            # 맞는지 알 수 없다. 그래서 **문구를 만든 그 함수**가 목록의 번호도
            # 함께 낸다(`numbered_companies`). 딜 소개에 없던 기업은 `no` 가
            # `null` 이다 — 지어내지 않는다. 문구도 그 기업만 이름으로 나간다.
            #
            # **적히는 글자(`label`)도 서버가 짓는다** — `[기업2]` 라는 모양을
            # 화면이 따로 적으면 문구의 모양을 바꿀 때 목록만 옛 모양으로
            # 남는다(`2번`). 번호가 없으면 빈 글자다 — 화면이 그때만 다르게
            # 적는다("번호 없음").
            #
            # **파일 이름**(0056) — 링크가 아니다. 자동 첨부를 켰으면 발송기가
            # 이 이름으로 파일을 찾아 붙이고, 켜지 않았으면 사람이 이 이름을
            # 보고 PC 카톡에서 붙인다. 어느 쪽이든 **번호 차례대로** 간다.
            "attachments": ([{"company_id": c.id, "name": c.name,
                              "file": c.ir_file_name or "", "no": no,
                              "label": deal_numbers.label(no) if no else ""}
                             for no, c in deal_numbers.numbered_companies(
                                 db, contact.id, companies)]
                            if req.mode == MODE_IR else []),
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

    # ── 스타트업 월간 발송은 **정해진 한 계정만** ──────────────────────────
    #
    # 화면을 안 보여 주는 것만으로는 부족하다 — 주소로 이 함수까지 곧장 찌를 수
    # 있고, 그 한 번이 스타트업 대표 카톡방을 여는 요청이다. 막는 판정은 메뉴를
    # 그리는 자리와 **같은 함수**를 읽는다(`startup_send.may_send`).
    #
    # 없는 것처럼 답한다(404). 403 은 "그런 자리가 있는데 너는 안 된다" 라
    # 이 계정으로 쓸 수 없는 기능의 존재를 알려 준다.
    if req.mode == MODE_STARTUP:
        if not startup_send.may_send(db, user):
            raise HTTPException(status_code=404, detail="없는 자리입니다")
        # 달을 짐작하지 않는다. 못 읽는 값이면 **이번 달로 대신 보내지 않는다** —
        # 글에 `7월 말까지` 라고 적혀 나가는 자리라, 짐작이 틀리면 그 거짓말이
        # 그대로 대표에게 간다.
        if not ir_monthly.is_month(req.month):
            raise HTTPException(status_code=400,
                                detail="어느 달치인지가 없습니다 — 달을 고르세요")
        # 메일로는 나가지 않는다. 받는 곳이 **카톡방**이고, 앱이 대표 메일
        # 주소를 이 발송의 상대로 확인해 준 적이 없다(`ir_kakao.contact_of`).
        if req.channel == "email":
            raise HTTPException(status_code=400,
                                detail="스타트업 월간 발송은 카톡으로만 나갑니다")

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
    # 실을지 말지만 여기서 가린다. **무엇을 어떤 차례로** 실을지는 담당자마다
    # 다르므로(번호가 담당자마다 다르다) 아래 담당자 고리에서 정한다.
    attach_on = False
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
        attach_on = True

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
    # 멈춤 표시는 **투자사 명단의 칸**이다(`sheet_owner`). 소싱 명단에도
    # 스타트업 기업 줄에도 그 칸이 없다 — 없는 칸을 물으면 늘 거짓이라
    # 아무것도 막지 못하면서 판정만 하나 늘어난다.
    if req.mode not in (MODE_SOURCING, MODE_STARTUP):
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

    # ── 언제 내보낼까 ──────────────────────────────────────────────────────
    #
    # **아무것도 만들기 전에 본다.** 시각이 안 되는 값인데 회차부터 세우면,
    # 사람은 오류만 보고 화면을 떠나고 아무도 안 볼 `draft` 회차가 남는다.
    # 되는 값인지 가리는 자리는 한 곳이다(`scheduled_send.check`) — 화면이
    # 고르개를 좁혀 두어도 주소로 폼을 흉내 내면 무엇이든 들어온다.
    scheduled = None
    if (req.scheduled_at or "").strip():
        try:
            scheduled = scheduled_send.check(scheduled_send.parse(req.scheduled_at))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    # 예약을 걸었으면 **세워만 둔다** — `draft` 와 같은 뜻이다.
    standing = req.draft or scheduled is not None

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
    # 자료 전달이 나중에 이 번호를 되읽어 "[기업2] …" 라고 짚는다.
    for pos, company in deal_numbers.numbered(companies):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=pos))

    # Job (queued) + items (pending, snapshotted message + room name)
    job = SendJob(
        user_id=user.id,
        # IR 자료 전달은 딜소개와 다른 일이다. 종류를 남겨야 후속을 멈추고
        # 요청을 '전달함'으로 닫을 수 있다.
        # 스타트업 월간 발송은 **`SEND_KINDS` 밖의 종류**다 — 받는 쪽이
        # 투자사가 아니라 스타트업 대표라, 딜소개 실적에 섞이면 안 된다
        # (까닭은 `models.STARTUP_SEND_KIND`).
        kind=(STARTUP_SEND_KIND if req.mode == MODE_STARTUP
              else "ir_delivery" if req.mode == MODE_IR
              else "sourcing_intro" if sourcing else "deal_intro"),
        batch_id=batch.id,
        # `draft` 면 발송기가 집어가지 않는다 — 사람이 누를 때까지, 또는
        # **정해 둔 시각까지** 기다린다.
        status=("draft" if standing else "queued"),
        total=len(contacts), sent=0, failed=0,
        # 예약을 걸었으면 그 시각이 회차에 붙는다. 푸는 것은
        # `services/scheduled_send.py` 이고, 푸는 길은 [발송 시작] 과 같다.
        scheduled_at=(scheduled.isoformat(timespec="seconds") if scheduled
                      else None),
    )
    db.add(job)
    db.flush()

    overrides = _override_map(req, {c.id for c in contacts})

    for contact in contacts:
        # **번호순으로 늘어선 이 담당자의 기업들.** 화면의 [보낼 자료] 목록과
        # 나가는 문구가 이 차례이므로(`deal_numbers.numbered_companies`),
        # 발송기가 붙이는 파일도 같은 차례여야 한다 — 화면은 `[기업1] · [기업3]`
        # 인데 파일이 고른 차례로 나가면 사람이 본 것과 받는 것이 갈린다.
        #
        # 번호는 담당자마다 다르므로 **담당자마다 다시 잡는다.**
        ir_order = ([c for _no, c in deal_numbers.numbered_companies(
            db, contact.id, companies)] if req.mode == MODE_IR else companies)
        attach_files = ir_attach.file_names(ir_order) if attach_on else []
        if contact.id in overrides:
            # 사람이 고친 문구가 최우선. 고친 것은 통째로 한 통이다 —
            # 어디서 끊을지는 고친 사람만 안다.
            text, parts = overrides[contact.id], []
        elif req.mode == MODE_STARTUP:
            # ── 글을 짓는 자리는 `ir_kakao` **하나다** ★ ──────────────────
            #
            # 스타트업 화면(`/startup/ir-kakao/{id}`)도 `/setup` 의 시험 자리도
            # 같은 함수를 지난다. 여기서 한 줄이라도 이어 붙이면 사람이 화면에서
            # 보고 고른 글과 대표가 받는 글이 갈리고, 그 차이는 나간 뒤에야
            # 드러난다. 가리기(`ir_mask`)와 세기(`ir_monthly`)도 그 함수 안에서
            # 지난다 — 여기에 이름이 지나가는 자리 자체가 없다.
            #
            # `user` 는 머리말 문구틀을 고르는 데 쓴다(고른 것 > 내 것 > 팀 것).
            composed = ir_kakao.for_company(db, user, contact.id, req.month)
            if composed is None:
                # **조용히 건너뛰지 않는다.** 빈 목록을 보내면 대표는 우리가
                # 아무것도 안 한 줄로 읽고, 소리 없이 빠지면 몇 곳에 나갔는지
                # 아무도 모른다 — 방 이름이 없을 때와 같은 자리에서 같은
                # 방식으로 막는다: 말하고 멈춘다.
                raise HTTPException(
                    status_code=400,
                    detail=(f"'{contact.name}' {req.month} 말까지 요청한 투자사가 "
                            "없습니다 — 발송 대상에서 제외하세요"))
            text, parts = composed.text, list(composed.parts)
        else:
            composed = _compose_for_contact(db, user, contact, companies,
                                            req.opening_template_id,
                                            req.closing_template_id,
                                            mode=req.mode,
                                            include_opening=req.include_opening)
            text, parts = composed.text, list(composed.parts)
        if by_email:
            # **제목에 `[테스트]` 를 붙이지 않는다.** 붙이던 까닭은 카톡이 전부
            # 시험방으로 모이는 동안 메일만 진짜로 나가서, 그 차이를 제목으로나마
            # 알리자는 것이었다. 이제 카톡도 제 갈 곳으로 가므로 그 차이 자체가
            # 없다 — 남겨 두면 **투자사 메일함에 `[테스트]` 가 꽂힌다.**
            target = (contact.email or "").strip()
            message = text
            subject = _mail_subject(req, contact, companies)
        else:
            # 담당자의 방 그대로. 시험방은 이 길을 지나지 않는다(위 머리말).
            target = _room_of(contact, linked)
            message = text
            subject = None

        startup = req.mode == MODE_STARTUP
        db.add(SendItem(
            job_id=job.id,
            # 받는 줄이 세 표에 나뉜다 — **셋 중 하나만** 채운다.
            # 투자사 담당자 / 딜 소싱 명단 / 스타트업 기업.
            contact_id=None if (sourcing or startup) else contact.id,
            sourcing_contact_id=contact.id if sourcing else None,
            ir_company_id=contact.id if startup else None,
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
        # ── 자료 전달은 **담당자 이력에도 한 줄** ────────────────────────
        #
        # 자료 전달은 나중에 "이 사람에게 언제 어느 기업 자료를 보냈나" 로
        # 되짚는 일이라 담당자 이력에 남아야 한다. 예전에는 IR 진행 관리의
        # [자료 보내기] 를 **누른 순간** 그 화면이 적었는데, 그러면 (ㄱ) 보내지
        # 않고 닫아도 남고 (ㄴ) 딜 제안 관리에서 바로 보내면 아무 줄도 안 남았다.
        #
        # 두 화면이 함께 지나는 곳은 여기 하나뿐이라 여기서 적는다 — 어디서
        # 보내도 같은 줄이 남고, 안 보낸 것은 안 남는다. 두 번 눌러도 한 줄인
        # 것은 그대로다(`record_delivery` 가 같은 날·같은 묶음을 막는다).
        #
        # 기업 차례는 **나간 차례 그대로**(번호순)이고, `attach_files` 가 곧
        # 발송기가 파일을 실었는가다 — 그 판단을 여기서 다시 하지 않는다.
        if req.mode == MODE_IR:
            ir_attach.record_delivery(db, contact.id,
                                      [c.name for c in ir_order],
                                      by_sender=bool(attach_files))

    db.commit()

    if by_email and not standing:
        # 요청 안에서 다 보내면 110명일 때 몇 분이 걸려 요청이 끊긴다.
        # 목록만 만들고 뒤에서 한 건씩 보낸다 — 진행 화면이 카톡과 똑같이 폴링한다.
        #
        # `draft` 면 **보내지 않는다.** 카톡은 발송기가 `queued` 만 집어가서
        # 저절로 기다리지만, 메일은 서버가 바로 보내므로 여기서 막지 않으면
        # 사람이 누르기 전에 나간다.
        background.add_task(mail_sender.send_job, job.id)

    return {"job_id": job.id, "batch_id": batch.id, "total": len(contacts),
            "status": job.status, "channel": req.channel,
            # 예약을 걸었으면 **언제 몇 명에게 나가는지** 한 줄로 돌려준다.
            # 문장을 서버가 만든다 — 화면이 따로 지으면 두 벌이 된다.
            "scheduled": scheduled_send.describe(job)}


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


# ─────────────────────────────────────────────────────────────────────────────
# 손으로 보낸 것 적기
#
# 왜 이 화면인가
# --------------
# 여기는 이미 **기업을 고르고 사람을 고르는** 자리다. 손으로 보낸 것을 적는
# 일도 고르는 것이 똑같다 — `이번 주 딜소개는 8개 기업`, 대상 80명. 따로 화면을
# 세우면 고르는 목록이 두 벌이 되고, 둘 중 한쪽만 `발송 대상` 규칙을 따라가는
# 날이 온다(`sheet_owner.recipients` · 멈춰 둔 사람 빼기 · 방 연결).
#
# 무엇을 지키나 — `bulk-delete` 의 결 그대로
# ------------------------------------------
#   · 확인 없이 부르면 **세기만** 한다(`confirm=False`). 한 줄도 안 쓴다.
#   · **부분 적용을 안 한다.** 남의 담당자가 섞이면 `_owned` 가 그 자리에서
#     404 를 내고, 그때까지 아무 것도 안 적혔다.
#   · 권한 판정을 여기서 새로 짓지 않는다 — 한 줄 고치기와 **같은 `_owned`** 다.
#
# 엑셀 되올리기로 적는 길은 만들지 않는다(`routers/data_io.py` 에 까닭이 있다 —
# 내보낸 표를 되올려 활동 635건이 뻥튀기된 적이 있다).
# ─────────────────────────────────────────────────────────────────────────────


class ManualSendIn(BaseModel):
    contact_ids: List[int] = []
    #: `deal_intro` · `ir_delivery` · `meeting_ask`(`manual_send.KIND_LABELS`).
    kind: str = manual_send.DEAL_INTRO
    #: 보낸 날 `YYYY-MM-DD`. **비어 있으면 오늘이 아니라 400 이다** —
    #: 오늘로 짐작하면 리마인드가 서는 쪽으로 기울고, 그건 되돌리기 번거롭다.
    day: str = ""
    #: 그 판에 실은 기업. **판 하나에 한 번만 고른다** — 80명에게 같은 8개사를
    #: 보낸 것이 보통이라 줄마다 고르게 하면 80번 고르는 일이 된다.
    company_ids: List[int] = []
    #: 이름 없이 **개수만** 적힌 판(`핵심 딜 8개사`). 시트에 그렇게만 적힌
    #: 경우가 실제로 있어서 길을 열어 둔다.
    company_count: Optional[int] = None
    #: **확인 없이는 한 줄도 안 적는다.** 화면은 이 값 없이 한 번 불러
    #: 무엇이 몇 줄인지 보여 주고, 사람이 [확인] 을 누른 뒤에야 참으로 보낸다.
    confirm: bool = False


def _manual_targets(db: Session, user: User, ids: List[int]) -> List[VcContact]:
    """적을 담당자 줄. **남의 줄이 섞이면 한 줄도 안 적는다.**

    판정은 투자사 관리 현황의 한 줄 고치기와 **같은 `_owned`** 다 — 여기서 새로
    지으면 화면에 뜬 줄을 눌러도 서버가 막는, 이 저장소가 반복해 당한 어긋남이
    또 난다(팀원은 자기 담당분만, 관리자는 팀 전체).
    """
    from .contacts import _owned

    clean = list(dict.fromkeys(int(i) for i in (ids or [])))
    if not clean:
        raise HTTPException(status_code=400, detail="적을 담당자를 고르지 않았습니다")
    if len(clean) > manual_send.MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"한 번에 {manual_send.MAX_ROWS}줄까지 적을 수 있습니다")
    # **한 줄이라도 남의 것이면 여기서 끝난다** — 아직 아무 것도 안 적혔다.
    return [_owned(db, cid, user) for cid in clean]


def _manual_names(db: Session, kind: str, company_ids: List[int]) -> List[str]:
    """고른 기업의 **이름**. 없는 번호가 섞이면 말하고 멈춘다.

    이력에 남는 것은 번호가 아니라 이름이다(`ContactActivity.company_names`).
    `llm_brief.sent_history` 와 `deal_history.last_sent_map` 이 그 이름으로
    **이미 보낸 기업**을 만든다 — 기업 없이 줄만 적으면 다음 회차에 LLM 이 같은
    기업을 또 추천한다.
    """
    if kind not in manual_send.KINDS_WITH_COMPANIES or not company_ids:
        return []
    # 차례를 지키고 없는 번호를 가려 주는 자리가 이미 있다.
    companies = _load_companies(db, company_ids)
    return [c.name for c in companies]


@router.get("/manual-sends")
def manual_send_batches(db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """내가 되돌릴 수 있는 판들. **되돌린 것까지** 보여 준다.

    되돌린 판이 목록에서 사라지면 사람은 자기가 되돌렸는지 애초에 안 적었는지를
    알 수 없다(`manual_send.batches`).

    보이는 범위는 **손대도 되는 범위와 같다** — 내 담당자(관리자는 팀 전체)의
    줄만 본다. 되돌릴 수 없는 판이 목록에 떠 있으면 눌러 보고서야 안 된다는 것을
    알게 된다.
    """
    from ..deps import may_manage_team_contacts

    stmt = select(VcContact.id)
    if not may_manage_team_contacts(user):
        stmt = stmt.where(VcContact.user_id == user.id)
    ids = list(db.execute(stmt).scalars().all())
    return {"batches": manual_send.batches(db, ids),
            "remind_note": manual_send.REMIND_NOTE}


@router.post("/manual-sends")
def create_manual_send(body: ManualSendIn, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """손으로 보낸 것을 **한 판으로** 적는다.

    `confirm` 없이 부르면 아무 것도 적지 않고 무엇이 몇 줄인지만 돌려준다.
    """
    if body.kind not in manual_send.KIND_LABELS:
        raise HTTPException(status_code=400, detail="적을 수 없는 갈래입니다")
    if not manual_send.is_day(body.day):
        raise HTTPException(status_code=400,
                            detail="보낸 날짜를 골라 주세요 (YYYY-MM-DD)")
    # **앞날로는 못 적는다.** 아직 안 한 일을 적는 길이 열려 있으면 보고가
    # 미래를 세고, 오늘 것만 리마인드를 세우는 규칙도 뜻을 잃는다.
    if body.day > clock.today().isoformat():
        raise HTTPException(status_code=400,
                            detail="앞날로는 적을 수 없습니다 — 이미 보낸 것만 적습니다")

    contacts = _manual_targets(db, user, body.contact_ids)
    names = _manual_names(db, body.kind, body.company_ids)

    plan = manual_send.plan(db, contacts, body.kind, body.day,
                            company_names=names,
                            company_count=body.company_count)
    if not body.confirm:
        return {"ok": False, "confirmed": False, "added": 0, "plan": plan}

    result = manual_send.record(db, contacts, body.kind, body.day,
                                company_names=names,
                                company_count=body.company_count)
    db.commit()
    return {"ok": True, "confirmed": True, "added": result.added,
            "plan": plan, **result.as_dict()}


class ManualUndoIn(BaseModel):
    confirm: bool = False


@router.post("/manual-sends/{batch_key}/undo")
def undo_manual_send(batch_key: str, body: ManualUndoIn,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """잘못 적은 판을 **묶음째** 되돌린다. 지우지 않고 숨긴다.

    숨긴 줄은 읽는 자리 어디에서도 안 읽힌다(`models._hide_undone_activities`).

    권한은 적을 때와 **같은 `_owned`** 다 — 남의 담당자 줄이 한 줄이라도
    섞여 있으면 한 줄도 안 숨긴다. 관리자가 팀원을 대신 적어 준 판을 그
    팀원이 되돌리지 못하는 것은 맞다: 되돌리는 것도 적는 것과 같은 무게다.
    """
    rows = manual_send.rows_of(db, batch_key)
    if not rows:
        raise HTTPException(status_code=404, detail="그 판을 찾을 수 없습니다")
    # 한 줄이라도 남의 것이면 여기서 끝난다 — 아직 아무 것도 안 숨겼다.
    _manual_targets(db, user, [row.contact_id for row in rows])

    plan = {"rows": len(rows),
            "kind": rows[0].kind,
            "kind_label": manual_send.KIND_LABELS.get(rows[0].kind, rows[0].kind),
            "day": rows[0].happened_at or ""}
    if not body.confirm:
        return {"ok": False, "confirmed": False, "undone": 0, "plan": plan}

    n = manual_send.undo(db, rows)
    db.commit()
    return {"ok": True, "confirmed": True, "undone": n, "plan": plan}
