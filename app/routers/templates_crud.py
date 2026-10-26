"""문구 템플릿 관리 — 팀이 만들어 둔 문구 중에서 **각자 하나를 고른다**.

딜소개 문구는 매번 같지 않다(첫 연락/재연락, 리마인드, 미팅 요청, 연말 인사 …).
그래서 같은 종류(kind)라도 문구를 여러 개 둔다.

여러 개 중 무엇을 쓸지는 **이 화면에서 한 번** 고른다. 회차마다 고르게 하면
다음 회차에 또 골라야 하고, 한 번이라도 잊으면 아무거나 나간다.

팀 기본 템플릿(user_id=NULL)은 모두에게 보이고, 본인이 만든 것은 본인에게만 보인다.
**고치는 것과 고르는 것은 다른 권한이다** — 팀 기본은 관리자만 고치지만,
고르는 것은 각자 한다(관리자도 제 선택을 가진다).

한 가지 예외가 관리자의 [모든 팀원에게 적용] 이다 — 모두가 같은 말로 나가야
할 때 관리자가 팀 문구 하나로 각자의 선택을 한 번에 덮는다(되돌릴 수 있다).
무엇을 덮고 어떻게 되돌리는지는 `services/template_apply.py` 한 곳에 있다.
"""
from __future__ import annotations

from typing import List, Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import admin_only, get_current_user, templates as jinja
from ..models import MessageTemplate, TemplateApplyBackup, User
from ..services import startup_outreach, template_apply, template_pick
from ..ui import base_ctx
# 합쳐진 문구는 발송 화면이 쓰는 그 길로 만든다 — 여기서 다시 합치면 두 벌이
# 되고, 두 벌은 반드시 어긋난다.
from . import deals as deals_view

router = APIRouter(tags=["templates"])

# 화면에 보여줄 종류와 설명. 문구가 어디에 쓰이는지 알아야 제대로 쓴다.
KINDS = [
    ("opening_first", "인사말 — 첫 연락", "처음 딜소개를 보내는 담당자에게"),
    ("opening_re", "인사말 — 재연락", "이미 보낸 적 있는 담당자에게"),
    ("closing_day1", "안내문 — 딜소개", "기업 목록 위에 오는 안내 문구"),
    ("closing_remind", "안내문 — 리마인드", "딜소개 발송 6~7일 뒤에 보냅니다"),
    ("closing_meeting", "안내문 — 미팅 요청", "딜소개 발송 11~14일 뒤에 보냅니다"),
    # 미팅 요청 자동화의 **두 번째**(`services/automations/meeting_request.py`).
    ("closing_meeting_again", "안내문 — 미팅 요청 (두 번째)",
     "IR 자료 전달 7일 뒤 미팅 요청에 답이 없으면 10일 뒤 자동으로 — 첫 번째와 조금 다른 말로"),
    # 미팅 후기 · 투자 결정 문의의 설명 끝에는 **며칠 뒤 나가는지**를 판의 값으로
    # 붙인다(`_desc`) — 여기 날수를 적어 두면 판에서 고친 뒤에도 옛 말이 남는다.
    ("meeting_review", "문구만 — 미팅 후기",
     "미팅 뒤 결과를 물을 때 — 미팅 후 검토결과 문의 자동화의 첫 번째"),
    # 미팅 후 검토결과 문의 자동화의 **두 번째**(`services/automations/meeting_review.py`).
    # 미팅 후기와 같은 틀(인사말 + 본문)에 본문만 이것이다.
    ("meeting_review_decision", "문구만 — 미팅 30일 뒤 투자 결정 문의",
     "미팅 후 검토결과 문의 자동화의 두 번째 — 인사말 아래에 붙습니다 · "
     "거절로 끝난 미팅에는 안 나갑니다 · {미팅 기업} 은 그 미팅의 기업 이름으로 채워집니다"),
    ("ask_preference", "문구만 — 선호 분야 묻기", "반응이 없는 담당자에게 기업 목록 없이 이 문구만"),
    # 계약 Day7 우편 발송 자동화(#9 · `services/automations/contract_day7.py`) — 받는 쪽이
    # **우리 팀원**이다. 비어 있으면 그 파일의 샘플 문구가 나간다.
    ("contract_post", "팀원 알림 — 계약서 우편 발송 (카톡)",
     "계약 완료 7일 뒤 계약 담당 팀원의 카톡방으로 자동으로 — "
     "{기업명} · {계약일} 은 앱이 채웁니다"),
    ("contract_receipt_sms", "팀원 알림 — 계약서 수신 확인 (문자)",
     "계약서 수신이 O 가 아니면 계약 14·21·28일 뒤 계약 담당 팀원에게 문자로 — "
     "{기업명} · {회차}(1/3 …) 는 앱이 채웁니다"),
    ("ir_delivery", "IR 자료 전달", "PC 에서 자료를 첨부해 보낸 뒤 뒤따라 보내는 문구"),
    # 자료 파일명이 없는 기업은 이번엔 빼고 보내고 글 끝에 이 한 줄(#53, `deals.IR_LATER_KIND`).
    ("ir_delivery_later", "IR 자료 전달 — 추후 발송 안내",
     "IR 자료를 보낼 때 파일이 없는 기업이 있으면 글 끝에 붙는 한 줄 — "
     "{기업목록} 에 못 보낸 기업이 번호와 함께 들어갑니다"),
    # 갈래마다 하나씩이다 — 호칭·전달 개수·찾는 범위가 다르다.
    # 문구 이름에 갈래를 적어 두면 그 갈래에 쓰인다(`sourcing_msg.body_for`).
    ("sourcing_intro", "딜 소싱 제안", "갈래(시리즈 A 이상 · 투자사 대표 · 개인 참여 …)마다 하나씩"),
    # 이미 참여한 분께 이 달 딜을 청하는 글 — 딜 소싱 제안 탭의 [보낼 문구 ›
    # 월간 리마인드]. 처음 안내처럼 갈래마다 하나씩(이름 = 갈래), 인사말 아래에
    # 붙는다. 종류 이름은 자동 리마인드(#277)와 같다 — 같은 저장 문구를 읽는다.
    ("sourcing_remind", "딜 소싱 리마인드",
     "딜 소싱 제안 탭에서 [월간 리마인드]를 고르면 나가는 글 — 갈래마다 하나씩, "
     "인사말 아래에 붙습니다 · {월} 은 이 달 숫자로 채워집니다"),
    # 시리즈 A 갈래 심사역께 `Series A 이상 딜 소싱` 탭의 받은 딜을 소개하는 글 —
    # 딜 소싱 제안 탭의 [보낼 문구 › Series A 딜 공유]. 갈래마다 하나(이름 =
    # 갈래)이고 인사말 아래에 붙는다. `{기업 목록}` 자리에 고른 기업이 들어간다
    # (`services/series_a_share.py`).
    ("sourcing_deal_share", "Series A 딜 공유",
     "딜 소싱 제안 탭에서 [Series A 딜 공유]를 고르면 나가는 글 — 시리즈 A 이상 "
     "딜 소싱 참여 심사역 갈래에만, 인사말 아래에 붙습니다 · {기업 목록} 자리에 "
     "고른 기업이 기업마다 한 덩어리(기업명 · 분야 · 투자라운드 · 소개)로 들어갑니다 "
     "— 자리가 없으면 첫 문단 뒤에 들어갑니다"),
    ("connect_call", "연결 — 전화 응대", "카톡방 연결 전 첫 통화"),
    ("connect_sms", "연결 — 부재중 문자", "전화를 못 받으셨을 때 보내는 문자"),
    ("connect_reinvite", "연결 — 방 나가신 분", "카톡방을 나간 담당자에게 다시 연락할 때"),
    ("startup_info", "기업 — 정보 기재 요청",
     "스타트업에 회사명·매출·투자금 등을 적어 달라고 할 때"),
    # 이 문구 둘은 **목록 위(머리말)와 아래(맺음말)**다 — 그 사이의 요청 투자사
    # 목록과 요약 숫자는 코드가 붙인다(`services/ir_kakao.py`). 목록까지 여기서
    # 적게 하지 않는 까닭은 그 파일 머리말에 있다(짧게: 목록은 자료이고, 가리는
    # 일이 문구틀 밖에 있어야 한다). 비워 두면 코드에 적힌 문장으로 나간다.
    #
    # **둘로 나눈 까닭**: 맺음말이 목록 아래에 온다. 한 덩어리로 두면 문구틀에
    # `{목록}` 같은 자리를 내줘야 하는데, 그러면 같은 문구에 **안 가려진** 자리도
    # 쓸 수 있게 된다 — 가리는 일이 문구를 고치는 사람 손에 넘어간다.
    ("startup_sms", "기업 리마인드 — 문자",
     "IR 자료를 요청한 투자사가 있다고 스타트업에 알리는 문구 — "
     "여기는 제목과 머리말만 적고, 요청 투자사 목록은 앱이 붙입니다 "
     "({연월}·{달}·{기업들} 은 앱이 채웁니다)"),
    ("startup_sms_tail", "기업 리마인드 — 맺음말",
     "위 문구의 **목록 아래**에 붙는 한 줄 — 요약 숫자와 목록은 앱이 짓습니다"),
    # 스타트업 월간 자동화가 **달마다 돌려 쓰는** 머리말·맺음말 2·3번
    # (`services/ir_kakao.VARIANT_KINDS`). 1번은 바로 위 둘이다. 자료(요약 ·
    # 목록)와 모양은 같고 인사·맺음 문장만 다르다 — **초안**이다.
    ("startup_sms_v2", "기업 리마인드 — 문자 (순환 2 · 초안)",
     "스타트업 월간 자동화가 달마다 돌려 쓰는 두 번째 머리말 — 인사만 다르고 자료는 같습니다"),
    ("startup_sms_tail_v2", "기업 리마인드 — 맺음말 (순환 2 · 초안)",
     "두 번째 머리말과 짝이 되는 맺음말"),
    ("startup_sms_v3", "기업 리마인드 — 문자 (순환 3 · 초안)",
     "스타트업 월간 자동화가 달마다 돌려 쓰는 세 번째 머리말 — 인사만 다르고 자료는 같습니다"),
    ("startup_sms_tail_v3", "기업 리마인드 — 맺음말 (순환 3 · 초안)",
     "세 번째 머리말과 짝이 되는 맺음말"),
    ("startup_call", "기업 리마인드 — 전화", "문자 뒤 통화할 때"),
    ("mail_subject", "홍보메일 제목", "메일 발송에 쓸 제목 후보"),
    # 스타트업 안내 카톡 셋 — 종류·이름은 `startup_outreach.TOPICS` 한 곳에서
    # 온다(발송 화면이 고르는 목록과 같은 목록이다).
    *[(t.key, f"스타트업 안내 — {t.label}",
       "좌측 [스타트업] → [안내 카톡 보내기] 에서 고르는 문구 — "
       + " · ".join(token for token, _ in startup_outreach.PLACEHOLDERS)
       + " 은 앱이 채웁니다(성함이 비면 그 자리를 빼고 보냅니다)")
      for t in startup_outreach.TOPICS],
]
KIND_LABELS = {k: label for k, label, _ in KINDS}
KIND_DESCS = {k: desc for k, _, desc in KINDS}

#: 미팅 후 검토결과 문의 자동화(A7)가 쓰는 문구 → 며칠 뒤인지 적힌 판의 칸.
A7_DAYS = {"meeting_review": "days", "meeting_review_decision": "decision_days"}


def _desc(db: Session, kind: str) -> str:
    """종류의 설명. A7 이 쓰는 두 문구는 **팀 현황 › 자동화 판의 날수**를 읽어
    붙인다 — 미팅 후기에 `열흘쯤` 이 박혀 있어 첫 번째(기본 2일)와 어긋났다."""
    desc = KIND_DESCS.get(kind, "")
    if kind not in A7_DAYS:
        return desc
    from ..services import automation, automation_runner as runner

    days = runner.values(automation.load(db, automation.MEETING_REVIEW),
                         automation.MEETING_REVIEW)[A7_DAYS[kind]]
    when = f"미팅 완료 {days}일 뒤 자동으로 나갑니다" if days else "지금은 날수가 0 이라 안 나갑니다"
    return f"{desc} · {when}(팀 현황 › 자동화에서 고침)"

# 문구에 쓸 수 있는 치환 변수 (화면 안내용)
VARIABLES = [
    ("{기업목록}", "[기업1] 샘플애그 (IR 자료 전달에서만)"),
    ("{담당자명}", "김영주"),
    ("{직함}", "심사역님 (없으면 자동으로 '님')"),
    ("{투자사}", "가나벤처스"),
    ("{개수}", "선택한 기업 수"),
    ("{월}", "10 — 이 달 숫자 (딜 소싱 리마인드에서만)"),
    ("{기업 목록}", "[기업1] 샘플바이오 · 분야 · 투자라운드 · 소개 — 고른 기업마다 한 "
                  "덩어리 (Series A 딜 공유에서만)"),
    ("{미팅 기업}", "샘플바이오 — 그 미팅의 기업 이름, 비었으면 '기업' "
                  "(미팅 30일 뒤 투자 결정 문의에서만)"),
    ("{기업명}", "샘플바이오 (팀원 알림 — 계약서 우편 발송 · 수신 확인에서만)"),
    ("{계약일}", "10/26 — 계약 완료로 바뀐 날 (계약서 우편 발송에서만)"),
    ("{회차}", "1/3 — 문자 몇 번째인가 (계약서 수신 확인에서만)"),
]


def _visible(db: Session, user: User) -> List[MessageTemplate]:
    """내가 쓸 수 있는 템플릿 = 팀 기본 + 내 것."""
    return db.execute(
        select(MessageTemplate)
        .where(or_(MessageTemplate.user_id.is_(None),
                   MessageTemplate.user_id == user.id))
        .order_by(MessageTemplate.kind, MessageTemplate.id)
    ).scalars().all()


def _editable(t: MessageTemplate, user: User) -> bool:
    """팀 기본(user_id=NULL)은 관리자만, 개인 것은 주인만 고칠 수 있다."""
    if t.user_id is None:
        return user.role == "admin"
    return t.user_id == user.id


def _snippet(body: str, limit: int = 40) -> str:
    """고를 때 보여줄 첫 줄. 이름이 비슷하면 이름만으로는 구별이 안 된다."""
    head = (body or "").strip().splitlines()
    first = head[0].strip() if head else ""
    return first if len(first) <= limit else first[:limit] + "…"


def _slots(kind: str, of_kind: List[MessageTemplate]) -> List[str]:
    """이 종류 안에서 문구들이 서 있는 **자리** 목록.

    보통은 자리가 하나다 — 그 종류의 문구가 전부 한 자리를 놓고 겨룬다.
    딜 소싱만 갈래마다 자리가 갈린다(갈래가 다르면 아예 다른 문구다).
    화면에 뜨는 순서를 문구 목록 순서와 맞춘다 — 순서가 어긋나면 어느
    선택기가 어느 문구를 가리키는지 눈으로 못 따라간다.
    """
    if kind not in template_pick.NAME_IS_A_BUCKET:
        return [""]
    # 문구가 하나도 없어도 자리 하나는 남긴다 — 그래야 "지금은 무엇이
    # 나가는가"(코드에 적힌 뼈대)를 볼 수 있고, 새로 만들 자리도 생긴다.
    # 띄어쓰기만 다른 갈래 이름은 **한 자리**다(`template_pick.same_slot`) — 처음
    # 나온 이름으로 부른다.
    slots: List[str] = []
    for t in of_kind:
        variant = template_pick.variant_of(kind, t.name)
        if not any(template_pick.same_slot(kind, variant, seen) for seen in slots):
            slots.append(variant)
    return slots or [""]


def _apply_view(db: Session, user: User, t: MessageTemplate) -> Optional[dict]:
    """[모든 팀원에게 적용] 단추의 재료 — 관리자에게, 정해 둔 종류의 켜진 팀 문구에만.

    확인창의 숫자는 실제 적용과 **같은 함수**(`template_apply.plan`)로 센다.
    화면이 따로 세면 "7명이 바뀝니다" 라고 물어 놓고 9명을 바꾸는 날이 온다.
    """
    if user.role != "admin" or not template_apply.eligible(t):
        return None
    plan = template_apply.plan(db, t)
    members, personal = len(plan.previous), len(plan.turn_off)
    if plan.empty:
        return {"empty": True, "members": 0, "personal": 0, "confirm": "", "hint": ""}
    # 0 인 쪽은 말하지 않는다 — "개인 문구 0개가 꺼집니다" 는 읽는 사람이 무엇이
    # 꺼지는지 다시 찾게 만든다.
    if members and personal:
        what = (f"팀원 {members}명의 선택이 이 문구로 바뀌고, "
                f"개인 문구 {personal}개가 꺼집니다")
        hint = f"팀원 {members}명의 선택 · 개인 문구 {personal}개가 바뀝니다"
    elif members:
        what = f"팀원 {members}명의 선택이 이 문구로 바뀝니다"
        hint = f"팀원 {members}명의 선택이 바뀝니다"
    else:
        what = ("팀원의 선택은 이미 모두 이 문구이고, "
                f"개인 문구 {personal}개가 꺼집니다")
        hint = f"개인 문구 {personal}개가 꺼집니다"
    return {"empty": False, "members": members, "personal": personal,
            "hint": f"저장한 문구로 — {hint}",
            "confirm": (f"{what}(되돌릴 수 있게 먼저 백업합니다).\n"
                        "관리자 계정의 선택도 함께 바뀝니다. 적용할까요?")}


def _last_apply(db: Session, user: User, kind: str, variant: str) -> Optional[dict]:
    """이 자리에서 아직 되돌리지 않은 마지막 [모든 팀원에게 적용] — 관리자에게만.

    언제 · 누가 · 어느 문구로 덮었는지를 단추 옆에 적는다. 그것이 안 보이면
    [되돌리기] 가 무엇을 되돌리는지 모르고 누르게 된다.
    """
    if user.role != "admin" or kind not in template_apply.KINDS:
        return None
    backup = template_apply.latest(db, kind, variant)
    if backup is None:
        return None
    who = db.get(User, backup.user_id) if backup.user_id else None
    applied = db.get(MessageTemplate, backup.template_id)
    members, personal = template_apply.counts(backup)
    return {
        "id": backup.id,
        "at": (backup.created_at or "")[:16].replace("T", " "),
        "who": who.name if who else "알 수 없는 사람",
        "name": ((applied.name or "이름 없는 문구") if applied else "지워진 문구"),
        "members": members, "personal": personal,
    }


def _slot_view(db: Session, user: User, kind: str, variant: str,
               of_slot: List[MessageTemplate], mode: str, topic: str = "") -> dict:
    """한 자리의 화면 재료 — 고를 것들 · 지금 고른 것 · 합쳐진 미리보기.

    고를 것이 하나뿐이면 선택기를 만들지 않는다. 고를 것이 없는데 라디오
    버튼만 늘어서면 무엇을 해야 하는 화면인지 흐려진다. 대신 그때는 "기본
    문구를 복사해 내 문구 만들기" 를 띄운다 — 빈 칸에서 처음부터 쓰라고 하면
    아무도 쓰지 않는다.
    """
    options = template_pick.candidates(db, user.id, kind, variant)
    picked = template_pick.chosen_id(db, user.id, kind, variant)
    mine = [o for o in options if o.user_id == user.id]
    team = [o for o in options if o.user_id is None]
    return {
        "variant": variant,
        "chosen_id": picked,
        # 팀 기본이 여럿인데 아직 아무것도 고르지 않으면 코드에 적힌 기본
        # 문구가 나간다. 그 사실이 화면에 보여야 고를 이유가 생긴다.
        "undecided": template_pick.pick(db, user.id, kind, variant) is None,
        "options": [{
            "id": o.id,
            "name": o.name or "이름 없는 문구",
            # 사용자가 실제로 고르는 것은 이 둘 중 하나다 — 팀이 정해 둔
            # 문구를 쓸 것인가, 내가 손본 문구를 쓸 것인가.
            "owner": "내 문구" if o.user_id == user.id else "기본 문구",
            "snippet": _snippet(o.body),
            "selected": o.id == picked,
        } for o in options],
        # 내 문구가 아직 없을 때만 복사를 권한다. 두 벌을 만들어 두면 어느
        # 것이 나가는지 또 헷갈린다.
        "copy_from": team[0].id if (team and not mine) else None,
        "rows": [{"t": t, "editable": _editable(t, user),
                  "chosen": t.id == picked,
                  "apply": _apply_view(db, user, t)} for t in of_slot],
        # 이 자리에 관리자가 [모든 팀원에게 적용] 한 것 중 아직 안 되돌린 마지막 것.
        "last_apply": _last_apply(db, user, kind, variant),
        # 실제로 나가는 문구 — 인사말과 본문을 합친 전문.
        "preview": (deals_view.sample_message(db, user, mode, bucket=variant,
                                              topic=topic)
                    if mode else ""),
        # 인사말이 붙는지는 발송 쪽 판단을 그대로 쓴다. 여기서 따로 정하면
        # 보여 준 문구와 나가는 문구가 인사말 한 덩어리만큼 어긋난다.
        "with_opening": bool(mode) and deals_view.opening_is_included(mode),
        # 기업을 고르는 방식은 미리보기에 '0개사' 가 뜬다 — 아직 아무 기업도
        # 고르지 않았기 때문이다. 그렇다고 가짜 기업을 지어 넣으면 그 숫자가
        # 진짜인 줄 안다. 무엇이 채워지는지 한 줄로 적어 둔다.
        "with_companies": mode in deals_view.MODES_WITH_COMPANIES,
    }


def _section(db: Session, user: User, rows: List[MessageTemplate],
             kind: str, title: str, tab: str, mode: str, topic: str = "") -> dict:
    """화면의 한 구간. 딜 제안 관리의 탭 하나 또는 '그 밖의 문구' 한 종류."""
    label, desc = KIND_LABELS.get(kind, kind), _desc(db, kind)
    # 키 이름을 'items' 로 두면 Jinja 에서 dict.items 메서드가 잡힌다(실제로 500 발생).
    of_kind = [t for t in rows if t.kind == kind]
    slots = [_slot_view(db, user, kind, variant,
                        [t for t in of_kind
                         if template_pick.same_slot(kind, t.name, variant)],
                        mode, topic)
             for variant in _slots(kind, of_kind)]
    return {"kind": kind, "title": title, "tab": tab, "mode": mode,
            "label": label, "desc": desc, "slots": slots,
            # 갈래가 있는 종류만 자리 이름을 적는다(딜 소싱). 나머지는 자리가
            # 하나라 이름을 붙이면 없는 구분을 있는 것처럼 보이게 한다.
            "has_buckets": kind in template_pick.NAME_IS_A_BUCKET}


@router.get("/templates", response_class=HTMLResponse, include_in_schema=False)
def templates_page(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user), msg: str = ""):
    # 지워졌거나 꺼진 문구를 가리키는 선택을 여기서 치운다. 화면에는 "고름"
    # 인데 실제로는 다른 문구가 나가는 상태로 남으면 안 된다.
    if template_pick.prune(db, user.id):
        db.commit()

    rows = _visible(db, user)
    # 구간은 **딜 제안 관리의 탭**을 따른다. 문구가 열다섯 종류로 나열돼 있으면
    # 어느 것을 고쳐야 그 탭이 바뀌는지 알 수 없었다. 탭 순서도 발송 화면과
    # 같아야 한다 — 두 화면의 순서가 다르면 같은 것을 찾는 데 매번 헤맨다.
    from .deals import (MODE_TEMPLATE_KIND, MODE_TITLES,  # noqa: PLC0415
                        MODE_TOPIC_KINDS)

    tabs = []
    for mode, kind in MODE_TEMPLATE_KIND.items():
        tab = MODE_TITLES.get(mode, "")
        tabs.append(_section(db, user, rows, kind, tab, tab, mode))
        # 한 탭 안에서 [보낼 문구]로 고르는 또 하나의 글(딜 소싱 제안의 월간
        # 리마인드) — 그 탭 바로 아래에 선다. 미리보기도 그 글로 짓는다.
        for topic_kind, label in MODE_TOPIC_KINDS.get(mode, ()):
            tabs.append(_section(db, user, rows, topic_kind, f"{tab} — {label}",
                                 tab, mode, topic=topic_kind))

    # 탭에 걸리지 않은 종류들 — 인사말·연결·기업 리마인드·메일 제목. 발송
    # 화면의 탭에서 직접 고르는 것은 아니지만 쓰이는 곳이 있다.
    tabbed = set(MODE_TEMPLATE_KIND.values()) | {
        k for pairs in MODE_TOPIC_KINDS.values() for k, _label in pairs}
    others = [_section(db, user, rows, kind, label, "", "")
              for kind, label, _desc in KINDS if kind not in tabbed]

    ctx = base_ctx(request, db, user, active="templates")
    ctx.update({"tabs": tabs, "others": others, "variables": VARIABLES, "msg": msg})
    return jinja.TemplateResponse(request, "templates.html", ctx)


@router.post("/templates/choose", include_in_schema=False)
def choose_template(
    kind: str = Form(""),
    template_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 종류에 내가 쓸 문구를 정한다 — 회차마다가 아니라 여기서 한 번.

    고치는 권한과는 상관이 없다. 팀 기본은 관리자만 고치지만 **고르는 것은
    각자** 한다 — 그래야 한 문구를 두고 사람마다 다른 것을 쓸 수 있다.
    """
    if kind not in KIND_LABELS:
        raise HTTPException(status_code=400, detail="알 수 없는 문구 종류입니다")
    t = db.get(MessageTemplate, template_id)
    # 남의 개인 문구는 고를 수 없다. 그 사람이 고칠 때마다 내 발송이 따라
    # 바뀌고, 그 사람이 지우면 내 선택이 사라진다.
    if (t is None or t.kind != kind or t.is_active != 1
            or t.user_id not in (None, user.id)):
        raise HTTPException(status_code=400, detail="고를 수 없는 문구입니다")
    # 자리는 화면이 보낸 값이 아니라 **문구 자신**에서 읽는다 — 화면 값을
    # 믿으면 '대표님·5개사' 문구가 다른 갈래의 자리에 꽂힐 수 있다.
    template_pick.set_choice(db, user.id, kind, t.id,
                             variant=template_pick.variant_of(kind, t.name))
    db.commit()
    return RedirectResponse(f"/templates?msg={quote('이 문구를 쓰기로 했습니다')}#{kind}",
                            status_code=303)


@router.post("/templates/copy", include_in_schema=False)
def copy_template(
    template_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """기본 문구를 그대로 베껴 **내 문구**를 만들고, 곧바로 그것을 고른다.

    빈 칸을 주고 처음부터 쓰라고 하면 아무도 쓰지 않는다. 지금 나가는 문구가
    이미 들어 있어야 한 줄만 고쳐서 제 것으로 만든다.

    만들자마자 고른 상태로 두는 이유: 만들어 놓고 고르지 않으면 왜 내 문구가
    안 나가는지 알 수 없다.
    """
    src = db.get(MessageTemplate, template_id)
    if src is None or src.user_id is not None:
        # 베낄 것은 팀 기본뿐이다. 내 문구를 또 베끼면 두 벌이 되고, 그때부터는
        # 어느 것이 나가는지 다시 헷갈린다.
        raise HTTPException(status_code=400, detail="복사할 수 있는 문구가 아닙니다")
    variant = template_pick.variant_of(src.kind, src.name)
    if any(t.user_id == user.id
           for t in template_pick.candidates(db, user.id, src.kind, variant)):
        return RedirectResponse(
            f"/templates?msg={quote('이미 내 문구가 있습니다')}#{src.kind}",
            status_code=303)
    # 딜 소싱은 이름이 곧 갈래라 이름을 바꾸면 그 갈래에서 쓰이지 않는다.
    # 나머지 종류의 이름은 사람이 알아보라고 붙인 딱지일 뿐이다.
    name = src.name if src.kind in template_pick.NAME_IS_A_BUCKET else "내 문구"
    mine = MessageTemplate(user_id=user.id, kind=src.kind, name=name,
                           body=src.body, is_active=1)
    db.add(mine)
    db.flush()
    template_pick.set_choice(db, user.id, src.kind, mine.id, variant=variant)
    db.commit()
    return RedirectResponse(
        f"/templates?msg={quote('기본 문구를 복사했습니다 — 이제 고쳐 쓰세요')}#{src.kind}",
        status_code=303)


def _clean_body(body: str) -> str:
    """저장할 문구 — 줄바꿈을 `\n` 하나로 맞추고 앞뒤 공백을 뗀다.

    브라우저는 여러 줄 칸(`textarea`)을 `\r\n` 으로 보낸다. 그대로 두면 빈 줄로
    문단을 찾는 자리(Series A 딜 공유의 `series_a_share.slot`)가 문단을 못 찾고,
    카톡에도 `\r` 이 실린다. 문구 종류와 상관없이 저장할 때 한 번 맞춘다.
    """
    return (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()


@router.post("/templates/new", include_in_schema=False)
def create_template(
    kind: str = Form(""),
    name: str = Form(""),
    body: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if kind not in KIND_LABELS:
        raise HTTPException(status_code=400, detail="알 수 없는 문구 종류입니다")
    if not body.strip():
        return RedirectResponse("/templates?msg=내용을+입력하세요", status_code=303)
    db.add(MessageTemplate(user_id=user.id, kind=kind,
                           name=(name.strip() or None), body=_clean_body(body), is_active=1))
    db.commit()
    return RedirectResponse("/templates?msg=문구를+추가했습니다", status_code=303)


@router.post("/templates/{template_id}/edit", include_in_schema=False)
def edit_template(
    template_id: int,
    name: str = Form(""),
    body: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(MessageTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문구를 찾을 수 없습니다")
    if not _editable(t, user):
        raise HTTPException(status_code=403, detail="이 문구를 수정할 권한이 없습니다")
    t.name = name.strip() or None
    t.body = _clean_body(body)
    db.commit()
    return RedirectResponse("/templates?msg=문구를+수정했습니다", status_code=303)


@router.post("/templates/{template_id}/delete", include_in_schema=False)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    t = db.get(MessageTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문구를 찾을 수 없습니다")
    if not _editable(t, user):
        raise HTTPException(status_code=403, detail="이 문구를 삭제할 권한이 없습니다")
    # 이 문구를 골라 둔 사람들의 선택을 먼저 거둔다. 남겨 두면 없는 문구를
    # 가리킨 채로 남아 "골라 뒀는데 다른 것이 나간다" 가 되고, 외래키가 켜져
    # 있으면 삭제 자체가 막힌다.
    template_pick.forget_template(db, t.id)
    db.delete(t)
    db.commit()
    return RedirectResponse("/templates?msg=문구를+삭제했습니다", status_code=303)


@router.post("/templates/{template_id}/apply-all", include_in_schema=False)
def apply_template_to_all(
    template_id: int,
    name: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[모든 팀원에게 적용] — 이 팀 문구로 모두의 선택을 덮고 그 자리의 개인 문구를 끈다.

    관리자만. 무엇을 덮고 어떻게 되돌리는지는 `services/template_apply.py` 에 있다.

    단추가 [저장] 과 같은 폼 안에 있어 칸의 값이 함께 온다. **고친 채로 누르면
    적용하지 않는다** — 적용되는 것은 저장된 문구인데, 화면에는 고친 글이 떠
    있어 무엇이 나갔는지 어긋난다(딜 소싱은 이름이 곧 갈래라 자리까지 바뀐다).
    """
    admin_only(user)
    t = db.get(MessageTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문구를 찾을 수 없습니다")
    if not template_apply.eligible(t):
        raise HTTPException(status_code=400,
                            detail="모든 팀원에게 적용할 수 있는 문구가 아닙니다")
    if body is not None and (
            _clean_body(body) != _clean_body(t.body)
            or (name or "").strip() != (t.name or "").strip()):
        return RedirectResponse(
            f"/templates?msg={quote('고친 내용을 먼저 [저장]한 뒤 적용하세요')}#{t.kind}",
            status_code=303)

    plan, backup = template_apply.apply(db, t, user)
    if backup is None:
        return RedirectResponse(
            f"/templates?msg={quote('바뀔 것이 없습니다 — 모두 이미 이 문구를 씁니다')}#{t.kind}",
            status_code=303)
    db.commit()
    done = (f"모든 팀원에게 적용했습니다 — 선택 {len(plan.previous)}명 · "
            f"개인 문구 {len(plan.turn_off)}개 꺼짐 (잘못 눌렀으면 [되돌리기])")
    return RedirectResponse(f"/templates?msg={quote(done)}#{t.kind}", status_code=303)


@router.post("/templates/apply-all/{backup_id}/undo", include_in_schema=False)
def undo_apply_to_all(
    backup_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[되돌리기] — 이 자리의 **마지막** 적용을 그 전으로. 한 번만 된다.

    그 사이 사람이 다시 고른 선택 · 주인이 고치거나 지운 문구는 건드리지 않고
    몇 건인지 알린다(`template_apply.restore`).
    """
    admin_only(user)
    backup = db.get(TemplateApplyBackup, backup_id)
    if backup is None:
        raise HTTPException(status_code=404, detail="되돌릴 적용을 찾을 수 없습니다")
    if backup.restored_at:
        return RedirectResponse(
            f"/templates?msg={quote('이미 되돌린 적용입니다')}#{backup.kind}",
            status_code=303)
    last = template_apply.latest(db, backup.kind, backup.variant)
    if last is None or last.id != backup.id:
        return RedirectResponse(
            f"/templates?msg={quote('이 자리에 더 나중에 적용한 것이 있습니다 — 그것부터 되돌려 주세요')}"
            f"#{backup.kind}", status_code=303)

    done = template_apply.restore(db, backup)
    db.commit()
    msg = f"되돌렸습니다 — 선택 {done.choices}명 · 개인 문구 {done.templates}개"
    if done.skipped:
        msg += f" (그 사이 바뀐 {done.skipped}건은 그대로 두었습니다)"
    return RedirectResponse(f"/templates?msg={quote(msg)}#{backup.kind}", status_code=303)


@router.get("/api/templates")
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """발송 화면의 문구 선택기용."""
    rows = _visible(db, user)
    return {
        "templates": [
            {"id": t.id, "kind": t.kind,
             "name": t.name or ("팀 기본" if t.user_id is None else "내 문구"),
             "body": t.body, "mine": t.user_id == user.id}
            for t in rows
        ],
        "kinds": [{"kind": k, "label": label} for k, label, _ in KINDS],
    }
