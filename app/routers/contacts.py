"""내 투자사 — 담당자 CRUD · 활동 이력 · 방 연결 확인 (ROADMAP 2.2/2.5, FEATURE_SPEC §3).

표에 보이는 '최근 딜소개'와 '반응'은 **저장하지 않고 조회 시 집계**한다(DATA_MODEL §2.4).
수기로 관리하면 실제 발송 이력과 어긋나는 순간 신뢰를 잃기 때문이다. 126행 화면에서
N+1 쿼리가 나지 않도록 담당자 전체를 한 번에 모아 파이썬에서 묶는다.

RBAC: 조회·수정 모두 **자기 담당분**이다(``VcContact.user_id == 현재 사용자``).
관리자만 팀 전체를 보고 고친다 — 그 판정은 ``deps.may_manage_team_contacts`` 한
곳에 있고, 표(`contact_rows`)와 한 줄 고치기(`_owned`)가 같은 것을 읽는다.
두 쪽이 각자 판정하던 동안은 관리자 화면에 뜬 줄을 눌러도 404 가 났다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import can_open, get_current_user, may_manage_team_contacts
from ..models import (ContactActivity, ContactColumn, IrCompany, SendItem,
                      SendJob, User, VcContact)
from ..services import (contact_columns, deal_stage, firm_type, room_name,
                        sheet_import, sheet_owner)
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


# 시트에서 직접 넣지 않고 화면에서 추가한 담당자
MANUAL_SHEET = "직접 추가"


def _sheet_labels(value: Optional[str]) -> List[str]:
    """이 담당자가 어느 명단에서 왔는가.

    한 사람이 여러 명단에 겹쳐 있다(실제로 126명이 딜소개현황과 신규 명단에
    함께 들어 있다). 그래서 하나가 아니라 목록이다.
    """
    labels = [x.strip() for x in (value or "").split(",") if x.strip()]
    return labels or [MANUAL_SHEET]


# 명단별 탭은 `sheet_owner.sheet_rows()` 하나가 만든다.
#
# 여기에도 같은 것을 세는 `sheet_tabs()` 가 있었다. 아무도 부르지 않는데(화면은
# `sheet_rows` 를 쓴다) 남아 있어서, 명단에 조건이 하나 붙을 때마다 "여기도
# 고쳐야 하나" 를 매번 따져야 했다. 같은 것을 두 벌로 세는 코드가 곧 투자사
# 관리 현황 117명 · 대시보드 123명 같은 사고를 부른다 — 지운다.


def contact_rows(db: Session, user: User, team_wide: bool = False,
                 include_hidden: bool = False) -> List[dict]:
    """표 한 행 = 담당자 1명 + 집계값. (FEATURE_SPEC §3 7컬럼)

    `team_wide` 는 관리자 전용이다. 관리자는 직접 보내지 않지만 **누가 어떤
    투자사를 맡고 있는지** 알아야 팀이 굴러간다. 여기 뜨는 줄은 그대로 고칠 수도
    있다 — 누가 열리는지는 `_owned` 와 **같은 판정**(`may_manage_team_contacts`)
    을 읽는다. 발송 대상 고르기는 여전히 본인 담당분만이다 — 남의 담당에 실수로
    나가면 안 된다.

    `include_hidden` 은 **투자사 관리 현황 화면 하나만** 쓴다. 감춘 명단도 그
    탭에서는 그대로 보여야 하기 때문이다(감추기는 지우기가 아니다). 그 외에는
    기본값 그대로 두어야 한다 — 여기서 새는 순간 세는 곳마다 수가 갈린다.
    """
    # 누구를 세는지는 **여기서 정하지 않는다.** 딜 제안 관리가 같은 것을 두고
    # 자기 질의를 따로 들고 있어서 두 화면의 수가 갈렸다 — 이제 둘 다
    # `sheet_owner.managed()` 를 지난다(그쪽은 명단·연결 두 문을 더 얹는다).
    #
    # 방 상태 갈래도 마찬가지다. 대시보드가 `_room_state` 로 세고 그 갈래로
    # 링크를 거는데 표가 다른 갈래를 실으면, 눌러 온 화면의 줄 수가 안 맞는다.
    # (services → routers 는 없는 방향이라 순환이 아니다)
    from ..services import dashboard
    from ..services.dashboard import _room_state as dashboard_room_state

    contacts = sheet_owner.managed(db, user, team_wide=team_wide,
                                   include_hidden=include_hidden)
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

    # 진행 단계는 행마다 묻지 않고 한 번에 구한다 — 300명이면 질의가 1,200번 나간다.
    stages_by_contact = deal_stage.of_many(db, [c.id for c in contacts])

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
        # 표에 세우고 거르는 값은 **발송 준비 관점의 갈래**다
        # (`dashboard._room_state`). 위의 `room_label` 과 갈래가 다르다 —
        # 저쪽은 방 이름을 찾았는지만 보고, 이쪽은 채널이 카톡인지까지 본다
        # (메일 채널·채널 불가 투자사는 방이 없어도 '미등록' 이 아니다).
        # 대시보드가 그 갈래로 세고 그 갈래로 링크를 걸므로, 표도 같은 갈래를
        # 실어야 눌러 왔을 때 수가 맞는다. **말을 여기 다시 적지 않는다.**
        send_state = dashboard_room_state(c)
        send_label, send_class = dashboard.ROOM_LABELS[send_state]

        rows.append({
            "id": c.id,
            "owner": owners.get(c.user_id, ""),
            "is_mine": c.user_id == user.id,
            "connect_stage": c.connect_stage,
            "sheets": _sheet_labels(c.source_sheet),
            "assignee": (c.assignee_name or "").strip(),
            "firm_type": c.firm_type or "unknown",
            "firm_type_label": firm_type.label(c.firm_type),
            "connect_label": sheet_import.CONNECT_LABELS.get(c.connect_stage, c.connect_stage),
            "department": c.department or "",
            "phone": c.phone or "",
            "email": c.email or "",
            "name": c.name,
            "title": c.title or "",
            "firm": c.firm or "",
            "group_name": c.group_name or "",
            "channel_kakao": c.channel_kakao,
            "channel_email": c.channel_email,
            # 대시보드의 '메일 채널 3' · '채널 불가 투자사 6' 에서 눌러 오는 자리다.
            # 세는 것만 보여주고 갈 곳이 없으면, 그 6명이 누구인지 알 수 없다.
            "channel_label": ("카톡" if c.channel_kakao else
                              "메일" if c.channel_email else "미지정"),
            "room_name": c.kakao_room_name or "",
            "room_verified": room_state,
            "room_class": room_class,
            "room_label": room_label,
            # 대시보드의 `방 미등록 6` · `채널 불가 투자사 6` 에서 눌러 오는 자리.
            "send_state": send_state,
            "send_label": send_label,
            "send_class": send_class,
            "invited_status": c.invited_status or "",
            "stages": _split_csv(c.stages),
            "sectors": _split_csv(c.sectors),
            "round_size": c.round_size or "",
            # 시트에 있는데 그동안 화면·엑셀 어디에도 안 나오던 값들.
            "office_phone": c.office_phone or "",
            "office_fax": c.office_fax or "",
            "address": c.address or "",
            "card_registered_at": c.card_registered_at or "",
            "interest_level": c.interest_level or "",
            # 시트에만 있고 앱에는 칸이 없어 버려지던 둘.
            "sourcing_note": c.sourcing_note or "",
            "tips_note": c.tips_note or "",
            "kakao_joined": c.kakao_joined or "",
            # 이 명단에만 있는 칸들(스타트업 명단의 `사업분야 대분류` 등)과
            # 달마다 늘어나는 칸의 값. 화면은 배치가 정해 준 키로 꺼내 쓴다.
            "notes": contact_columns.load_notes(c.notes),
            # 이 줄만 감췄는가. 표에서 빼고, 발송 대상에서도 뺀다.
            "is_hidden": bool(c.is_hidden),
            "last_deal": last_deal,
            "last_deal_label": _date_label(last_deal, last_round),
            "last_deal_note": last_deal_note or "",
            "last_deal_full": (last_round.content if last_round else ""),
            "recency": _recency_bucket(last_deal, today),
            "ir_recent": ir_recent,
            "meet_recent": meet_recent,
            "ir_total": ir_total,
            "meet_total": meet_total,
            # 대시보드의 "반응"과 같은 기준(전체 기간)이어야 눌러 왔을 때 수가 맞는다.
            "reaction_tags": _reaction_tags(ir_total, meet_total),
            "deal_stage": stages_by_contact.get(c.id, deal_stage.NONE),
            "deal_stage_label": deal_stage.label(stages_by_contact.get(c.id, deal_stage.NONE)),
            "deal_stage_cls": deal_stage.CLASSES[stages_by_contact.get(c.id, deal_stage.NONE)],
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


def _reaction_tags(ir_count: int, meet_count: int) -> List[str]:
    """반응이 있었는가. **기간을 자르지 않는다**.

    예전엔 최근 N일만 봤는데, N+1일째가 되면 태그가 조용히 사라졌다.
    화면만 보고는 왜 없어졌는지 알 수 없고, 대시보드에서 눌러 온 목록과도
    수가 어긋난다. 반응은 한 번 오면 없어지는 것이 아니다.
    """
    tags = []
    if ir_count:
        tags.append("IR 있음")
    if meet_count:
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
    """이 사람이 손대도 되는 담당자 줄만 돌려준다.

    **표에 보이는 줄과 같은 판정이다** — 둘 다 `may_manage_team_contacts` 를
    읽는다(`contact_rows` 의 `team_wide`). 여기서만 따로 `user_id != user.id`
    를 보고 있었던 탓에, 관리자 화면에 팀 전체가 떠 있는데 그 줄을 눌러 고치면
    404 가 났다 — 보이는데 못 고치는 상태였다. 관리자에게 왜 여는지는
    `deps.may_manage_team_contacts` 에.
    """
    contact = db.get(VcContact, contact_id)
    if contact is None or not (contact.user_id == user.id
                               or may_manage_team_contacts(user)):
        # 남의 담당자는 '없는 것'으로 답한다(존재 여부도 흘리지 않는다).
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")
    return contact


# ── 스키마 ──────────────────────────────────────────────────────────────────

class ContactIn(BaseModel):
    # 표에서 칸 하나만 눌러 고치는 일이 잦다(메모·카톡방 이름). 그때 이름까지
    # 같이 보내라고 하면 칸 하나 고치는 데 이름이 필요해진다 — 만들 때만 필수다.
    name: Optional[str] = None
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
    # 시트에 있던 값들 — 화면에서도 보고 고칠 수 있어야 한다.
    assignee_name: Optional[str] = None
    department: Optional[str] = None
    office_phone: Optional[str] = None
    office_fax: Optional[str] = None
    address: Optional[str] = None
    card_registered_at: Optional[str] = None
    interest_level: Optional[str] = None
    kakao_joined: Optional[str] = None
    sourcing_note: Optional[str] = None
    tips_note: Optional[str] = None
    # 연결 단계(미착수 → 진행 중 → 연결 완료 / 참여 안 함 / 방 나감).
    #
    # 그동안 이 값은 **어디서도 못 고쳤다** — 임포트와 '방 이름 지우기' 만
    # 바꿨다. 그래서 카톡방을 나가신 분을 `방 나감` 으로 표시할 길이 없었다.
    # 값은 `sheet_import.CONNECT_LABELS` 의 **키**다(라벨이 아니다) — 라벨은
    # 화면 글자라 바뀌면 저장이 조용히 어긋난다.
    connect_stage: Optional[str] = None
    # 이 명단에만 있는 칸 + 달마다 늘어나는 칸. {"칸키": "내용"}
    #
    # 칸 하나마다 스키마·저장 목록·되읽기 응답·화면 네 곳에 이름을 적어 두던
    # 방식을 여기서 끊는다. 그렇게 두면 네 곳 중 하나만 빠져도 증상이 조용하다 —
    # PATCH 는 200 을 주는데 아무것도 안 들어가거나, 저장은 되는데 다시 열면
    # 빈칸이다(실제로 `kakao_joined` 가 그랬다). 묶음으로 받으면 칸이 늘어도
    # 네 곳을 다시 맞출 일이 없다.
    notes: Optional[Dict[str, str]] = None
    # 이 줄만 표에서 감출까(1) 다시 보일까(0).
    is_hidden: Optional[int] = None


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
    # 투자사로 세지 않는 명단·감춘 줄은 방을 확인할 이유가 없다. 확인해 두면
    # `연결 완료` 가 붙고, 그 순간 딜소개 발송 대상 목록에 함께 뜬다.
    contacts = sheet_owner.investors(
        db, db.execute(query.order_by(VcContact.id)).scalars().all())

    # 메일 채널로만 관리하는 담당자는 카톡방이 없는 게 정상이라 확인 대상이 아니다.
    def _is_kakao(c) -> bool:
        return bool((c.kakao_room_name or "").strip()) and not (
            c.channel_email == 1 and c.channel_kakao == 0
        )

    targets = [c for c in contacts if _is_kakao(c)]
    skipped = [c.name for c in contacts if not _is_kakao(c)]

    # 동명이인인데 방 이름에 회사가 없으면 **확인할 수가 없다.** 카톡 검색은
    # 참여자 이름으로도 걸려서 같은 이름의 다른 사람 방이 함께 나온다.
    # 확인을 시켜 봐야 어느 쪽이 맞는지 알 수 없으므로, 보내기 전에 여기서
    # 막고 방 이름을 고치게 한다 — 나가고 나서 알면 이미 남의 방이다.
    #
    # 대상 몇 명만 고른 경우에도 **전체 명단**을 기준으로 견준다. 겹치는
    # 상대가 이번 대상에 없다고 이름이 구별되는 것은 아니다.
    everyone = db.execute(
        select(VcContact).where(VcContact.user_id == user.id)
    ).scalars().all()
    unclear = {c.id for c in room_name.ambiguous_contacts(everyone)}
    conflicts = [c.name for c in targets if c.id in unclear]
    for contact in targets:
        if contact.id in unclear:
            contact.room_verified = "ambiguous"
    targets = [c for c in targets if c.id not in unclear]

    if not targets:
        detail = "확인할 카톡방 이름이 등록된 담당자가 없습니다"
        if conflicts:
            detail = (f"동명이인이라 방 이름만으로 구별되지 않습니다: "
                      f"{', '.join(conflicts[:5])} — 방 이름에 투자사명을 넣어주세요")
        db.commit()
        raise HTTPException(status_code=400, detail=detail)

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
    return {"job_id": job.id, "total": len(targets), "skipped": skipped,
            # 세는 것만 보여주면 왜 빠졌는지 모른다.
            "conflicts": conflicts}


# ── CRUD ────────────────────────────────────────────────────────────────────

def _back(db: Session, label: str) -> str:
    """이 명단을 만진 뒤 **돌아갈 화면 주소**.

    명단마다 사는 화면이 다르다(투자사 관리 현황 · 스타트업). 주소를
    `/contacts` 로 못 박아 두면 스타트업 화면에서 칸 이름을 고친 순간 남의
    화면으로 튀는데, 거기에는 그 탭이 없어서 **방금 고친 것이 사라진 것처럼**
    보인다. 어느 화면인지는 명단에 붙은 배치가 정한다(`sheet_owner.page_href`)
    — 참고 자료가 이미 같은 방식이다(아래 `_ref_back`).
    """
    return sheet_owner.page_href(db, (label or "").strip())


class AssignIn(BaseModel):
    contact_ids: List[int]
    label: str


@router.post("/assign")
def assign_to_my_sheet(body: AssignIn, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """풀에서 고른 담당자를 내 명단으로 할당한다.

    풀에서 빼지 않는다 — 풀은 확보해 둔 전체 명단이고 거기서 뽑아 쓰는 것이다.
    내 명단이 아닌 곳으로는 할당할 수 없다(남의 명단을 불릴 수 없다).
    """
    label = body.label.strip()
    if label not in sheet_owner.my_labels(db, user):
        raise HTTPException(status_code=403, detail="내 명단으로만 할당할 수 있습니다")
    rows = db.execute(
        select(VcContact).where(VcContact.id.in_(body.contact_ids or []))
    ).scalars().all()
    # 투자사로 세지 않기로 한 명단에서는 꺼내 오지 않는다. 여기서 내 명단에
    # 더하는 순간 그 사람들이 투자사 수에 다시 들어오고 발송 대상에도 뜬다 —
    # 방금 빼 둔 것을 되돌리는 길이 열려 있는 셈이다. 화면에서 이미 단추를
    # 감췄지만, 화면만 감추면 id 를 직접 보내는 길이 남는다.
    #
    # 진짜로 옮겨야 하면 먼저 그 명단의 [숨김 해제] 를 누른다.
    blocked = len(rows) - len(sheet_owner.investors(db, rows))
    rows = sheet_owner.investors(db, rows)
    if blocked and not rows:
        raise HTTPException(
            status_code=400,
            detail="투자사로 세지 않는 명단입니다 — 먼저 숨김을 해제하세요")
    moved = sheet_owner.add_to_sheet(db, rows, label, user.id)
    db.commit()
    return {"moved": moved, "label": label}


class TransferIn(BaseModel):
    label: str


@router.post("/{contact_id}/transfer")
def transfer_contact(contact_id: int, body: TransferIn,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """줄 **하나**를 다른 담당자의 명단으로 넘긴다.

    명단을 통째로 옮기는 길(`/sheets/assign` · `scripts/import_new_list.py`)은
    이미 있었다. 없던 것은 **한 사람만** 넘기는 길이다 — 실제로 남의 명단에
    섞여 들어간 몇 곳을 손으로 만든 배정표(CSV)로 옮겨야 했고, 팀원 워크북에는
    `7/21 A -> 8/19 B` 처럼 사람 사이에 넘긴 이력이 적혀 있다. 그 일이 앱 안에서
    돼야 한다.

    **옮기는 규칙은 여기 적지 않는다.** `sheet_owner.move_to` 한 곳에 있고
    스크립트도 같은 것을 부른다 — 두 벌로 적으면 다음에 한쪽만 고쳐지고,
    고쳐지지 않은 쪽으로 옮긴 사람만 조용히 옛 담당자의 발송 대상에 남는다.

    ── 누가 넘길 수 있나 ────────────────────────────────────────────────────

    **관리자, 그리고 지금 그 줄을 맡고 있는 사람.** 판정은 `_owned` 하나이고,
    그것은 표에 보이는 줄을 고르는 판정과 같은 것을 읽는다
    (`deps.may_manage_team_contacts`) — 보이는 줄은 넘길 수 있고, 안 보이는
    줄은 넘길 수 없다. 여기서만 따로 역할을 보면 **보이는데 못 넘기거나 안
    보이는데 넘어가는** 상태가 생긴다(이 저장소가 이미 겪은 404 사고다).

    내 줄을 남에게 **주는** 것은 열고, 남의 줄을 내가 **가져오는** 것은 막는다.
    앞쪽이 요청받은 그 일이고(워크북에 적힌 이력이 전부 그 방향이다), 뒤쪽은
    남의 대시보드와 발송 대상을 본인 모르게 바꾸는 일이다. 가져와야 하면
    관리자가 한다 — 관리자는 이미 명단 담당을 통째로 옮긴다.

    투자컨설턴트는 이 주소가 허용 목록(`deps.CONSULTANT_PATHS`)에 없어 미들웨어
    에서 끊긴다. 새 주소의 기본값이 **막힘**이라 여기 따로 적지 않는다.
    """
    contact = _owned(db, contact_id, user)
    label = (body.label or "").strip()

    # 넘길 수 있는 곳인가. **담당이 정해진 명단만** 받는다 — 풀로 넘기면 넘긴
    # 줄의 담당을 정할 수가 없다. 화면이 이미 그런 곳을 안 보여 주지만, 화면만
    # 감추면 이름을 직접 보내는 길이 남는다(`assign_to_my_sheet` 이 같은 이유로
    # 막는다).
    #
    # 감춘 명단은 **막지 않는다.** 스타트업 화면의 명단은 원래 전부 감춰져 있어
    # (투자사가 아니라서) 막으면 그 화면에서는 이관 자체가 안 된다. 대신 고르는
    # 칸이 `(투자사로 안 셈)` 이라고 적는다 — 이유는 `sheet_owner.transfer_targets`.
    targets = {t["label"]: t for t in sheet_owner.transfer_targets(db)}
    target = targets.get(label)
    if target is None:
        raise HTTPException(
            status_code=400,
            detail="담당이 정해진 명단으로만 넘길 수 있습니다")

    # **화면을 건너뛰지 않는다.** 투자사 줄을 스타트업 명단으로 넘기면 그 줄이
    # 다른 화면으로 사라져, 넘긴 사람은 어디로 갔는지 찾을 수가 없다. 이관은
    # *누가 맡는지*를 바꾸는 일이지 화면을 옮기는 일이 아니다.
    here = {sheet_owner.page_of(db, x)
            for x in sheet_owner.labels_of(contact.source_sheet)}
    if sheet_owner.page_of(db, label) not in here:
        raise HTTPException(
            status_code=400,
            detail="다른 화면의 명단으로는 넘길 수 없습니다")

    moved = sheet_owner.move_to(db, contact, label, target["owner_id"])
    db.commit()
    # **무엇이 어떻게 바뀌었는지 돌려준다.** 되돌리려면 어디서 왔는지 알아야
    # 한다 — 옛 명단 이름이 응답에 없으면 잘못 넘겼을 때 되돌릴 근거가 없다.
    return {"ok": True, "moved": moved, "label": label,
            "owner": target["owner"]}


@router.post("/sheets/assign", include_in_schema=False)
def assign_sheet(
    label: str = Form(...),
    user_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """명단의 담당 팀원을 정한다. 팀 전체 배분이 바뀌므로 관리자만."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="명단 담당은 관리자만 바꿀 수 있습니다")
    target = int(user_id) if user_id.strip().isdigit() else None
    if target is not None and db.get(User, target) is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    sheet_owner.assign(db, label.strip(), target)
    db.commit()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"{_back(db, label.strip())}?sheet={quote(label.strip())}", status_code=303)


@router.post("/sheets/hide", include_in_schema=False)
def toggle_sheet_hidden(
    label: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """명단 하나를 투자사 집계·발송 대상에서 빼거나 되돌린다.

    **지우는 것이 아니다.** 그 명단 탭에서는 그대로 보이고, 투자사로만 세지
    않는다 — 스타트업 리마인드 명단처럼 같은 표에 얹혀 있을 뿐 투자사가 아닌
    줄이 투자사 수를 부풀리고 발송 대상 목록에까지 뜨던 것을 막는다.

    **관리자만.** 명단을 감추면 그 명단을 담당하는 다른 팀원의 대시보드 숫자와
    발송 대상 목록까지 함께 바뀐다. 팀 전체에 영향이 가는 조작은 팀 현황의
    권한 토글과 같은 자리에 둔다.

    되돌리는 길은 화면에 남아 있다 — 탭은 감춰도 그대로 서 있고 같은 단추가
    `숨김 해제` 로 바뀐다. 감춰 놓고 켜는 단추까지 감추면 DB 를 직접 고쳐야 한다.
    """
    from fastapi.responses import RedirectResponse

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="명단 숨김은 관리자만 바꿀 수 있습니다")
    name = (label or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="명단을 찾을 수 없습니다")
    row = sheet_owner.ensure(db, name)
    row.is_hidden = 0 if row.is_hidden else 1
    db.commit()
    return RedirectResponse(f"{_back(db, name)}?sheet={quote(name)}", status_code=303)


@router.post("/sheets/deal-list", include_in_schema=False)
def toggle_sheet_deal_list(
    label: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 명단으로 **딜 소개를 보낼지** 켜고 끈다.

    발송 대상의 모집단이 이 값으로 정해진다(`sheet_owner.is_deal_list`).
    **명단 이름을 코드에 적지 않으려고** 값으로 둔 것이다 — 지금 이름은
    `전체 딜소개현황(125명)` 처럼 괄호 안 인원이 붙어 있어서, 이름으로 맞추면
    사람이 한 명 늘 때 조용히 깨진다.

    **관리자만.** 켜고 끄는 순간 그 명단을 맡은 팀원의 발송 대상이 통째로
    바뀐다 — 실제 카톡방으로 나가는 일이라 되돌릴 수 없다. 명단 숨김과 같은
    자리·같은 권한에 둔다.

    감춘 명단은 켤 수 없다. 투자사로 세지 않기로 한 명단에 딜 소개를 보내면
    투자사에게 보낼 문구가 스타트업에게 나간다 — 두 값이 서로 어긋나면 어느
    쪽을 믿을지 알 수 없으므로 여기서 막는다.
    """
    from fastapi.responses import RedirectResponse

    if user.role != "admin":
        raise HTTPException(status_code=403,
                            detail="딜소개 명단 표시는 관리자만 바꿀 수 있습니다")
    name = (label or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="명단을 찾을 수 없습니다")
    row = sheet_owner.ensure(db, name)
    if row.is_hidden:
        raise HTTPException(
            status_code=400,
            detail="투자사로 세지 않는 명단에는 딜 소개를 보낼 수 없습니다")
    # **지금 화면에 보이는 값의 반대**로 적는다. 지금 값이 기본값(할당 여부)에서
    # 온 것이어도 사람이 누른 순간 그 뜻이 정해지므로 0/1 을 명시해 둔다 —
    # `None` 으로 되돌리면 나중에 담당이 바뀔 때 표시가 저절로 뒤집힌다.
    row.is_deal_list = 0 if sheet_owner.is_deal_list(row) else 1
    db.commit()
    return RedirectResponse(f"{_back(db, name)}?sheet={quote(name)}", status_code=303)


# ── 달마다 늘어나는 칸 ──────────────────────────────────────────────────────
#
# `7월 리마인드 문자 (7/28)` 은 한 달 뒤면 `8월 …` 이 옆에 붙는다. 시트를 다시
# 올리지 않고도 화면에서 칸을 세울 수 있어야 한다 — 투자컨설턴트 현황의
# 열 추가·이름 바꾸기·삭제와 **같은 방식·같은 어휘**다.

def _sheet_or_400(db: Session, label: str) -> str:
    """이미 쓰고 있는 명단 이름만 받는다.

    아무 값이나 받으면 오타 하나로 **없던 탭이 생긴다** — 탭은 줄에 적힌 시트
    이름을 그대로 올리기 때문이다.
    """
    from ..models import SheetOwner

    name = (label or "").strip()
    known = {row.label for row in db.execute(select(SheetOwner)).scalars().all()}
    known |= {lbl for c in db.execute(select(VcContact.source_sheet)).scalars()
              for lbl in sheet_owner.labels_of(c)}
    if name not in known:
        raise HTTPException(status_code=400, detail="없는 명단입니다")
    return name


@router.post("/columns", include_in_schema=False)
def add_column(label: str = Form(...), sheet: str = Form(...),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """달이 바뀌면 칸을 하나 늘린다. 새 칸이 **맨 앞**에 오도록 한다.

    지금 챙겨야 할 달이 먼저 보여야 한다. (시트가 늘 그 순서인 것은 아니다 —
    `services/monthly_columns.py` 참고. 새로 세우는 자리를 정하는 것뿐이다.)
    """
    from fastapi.responses import RedirectResponse

    name = _sheet_or_400(db, sheet)
    text = (label or "").strip()
    if not text:
        return RedirectResponse(f"{_back(db, name)}?sheet={quote(name)}&msg=칸+이름을+입력하세요",
                                status_code=303)
    for col in contact_columns.month_columns(db, name):
        col.position += 1
    db.add(ContactColumn(sheet=name, label=text[:80], position=0))
    db.commit()
    return RedirectResponse(
        f"{_back(db, name)}?sheet={quote(name)}&msg={quote(text)}+칸을+추가했습니다",
        status_code=303)


@router.post("/columns/{column_id}/rename", include_in_schema=False)
def rename_column(column_id: int, label: str = Form(...),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    col = db.get(ContactColumn, column_id)
    if col is None:
        raise HTTPException(status_code=404, detail="칸을 찾을 수 없습니다")
    from fastapi.responses import RedirectResponse

    if (label or "").strip():
        col.label = label.strip()[:80]
        db.commit()
    return RedirectResponse(f"{_back(db, col.sheet)}?sheet={quote(col.sheet)}", status_code=303)


@router.post("/columns/{column_id}/delete", include_in_schema=False)
def delete_column(column_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """칸을 지우면 **그 달의 기록도 함께 사라진다** — 화면에서 한 번 더 묻는다.

    남은 값을 그냥 두면 어느 칸의 것인지 모르는 값이 JSON 에 쌓인다.
    """
    from fastapi.responses import RedirectResponse

    col = db.get(ContactColumn, column_id)
    if col is None:
        raise HTTPException(status_code=404, detail="칸을 찾을 수 없습니다")
    sheet, key = col.sheet, contact_columns.note_key(col.id)
    for contact in db.execute(select(VcContact)).scalars().all():
        values = contact_columns.load_notes(contact.notes)
        if key in values:
            values.pop(key)
            contact.notes = contact_columns.dump_notes(values)
    db.delete(col)
    db.commit()
    return RedirectResponse(f"{_back(db, sheet)}?sheet={quote(sheet)}", status_code=303)


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
    # 발송 이력에도 **그 회차에 보낸 기업**을 붙인다. 없으면 카톡방 이름만 남아
    # 담당자 이름이 기업 자리에 찍힌다 — 시트에서 옮겨 온 줄과 모양이 달라진다.
    batch_names = _batch_company_names(db, {j.batch_id for _i, j in sends if j.batch_id})
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
            # 시트에 있는데 그동안 화면 어디에도 안 보이던 값들.
            "office_phone": contact.office_phone or "",
            "office_fax": contact.office_fax or "",
            "address": contact.address or "",
            "card_registered_at": contact.card_registered_at or "",
            "interest_level": contact.interest_level or "",
            # 저장은 되는데 **다시 열면 비어 있었다** — 여기서 안 돌려주면
            # 창이 채울 값이 없어, 고쳐 놓고도 안 들어간 줄 안다.
            "kakao_joined": contact.kakao_joined or "",
            "sourcing_note": contact.sourcing_note or "",
            "tips_note": contact.tips_note or "",
            "assignee_name": contact.assignee_name or "",
            "department": contact.department or "",
            # 스키마·저장 목록·화면까지 다 맞춰 놓고 **여기만 빠뜨리면** 저장은
            # 되는데 다시 열었을 때 빈칸이다 — 고쳐 놓고도 안 들어간 줄 안다.
            "connect_stage": contact.connect_stage,
            "status": contact.status,
            "memo": contact.memo or "",
            # 이 명단에만 있는 칸들. **여기서 안 돌려주면 창이 채울 값이 없어**
            # 고쳐 놓고도 안 들어간 줄 안다(저장은 됐는데 다시 열면 빈칸).
            "notes": contact_columns.load_notes(contact.notes),
            "is_hidden": 1 if contact.is_hidden else 0,
        },
        # 한 줄기로 모은다: 시트에서 옮겨 온 월별 기록 + 발송 이력 +
        # **이 도구에서 만든 IR 요청·미팅**.
        #
        # 마지막 것이 빠져 있었다 — 미팅을 잡고 완료 처리까지 해도 그 담당자의
        # 활동 이력에는 아무것도 안 남아, 화면에서 한 일이 기록에 없는 것처럼
        # 보였다.
        # **최신순으로 섞어 준다.** 출처별로 뭉쳐 두면 8월 미팅이 6월 기록
        # 아래에 묻혀서, 무슨 일이 언제 있었는지 읽을 수가 없다.
        "timeline": sorted(
            [_activity_view(a, known) for a in acts]
            + [_send_view(item, job, batch_names.get(job.batch_id, []), known)
               for item, job in sends]
            + _pipeline_views(db, contact.id),
            key=lambda row: row.get("date") or "",
            reverse=True,
        ),
    }


def _pipeline_views(db: Session, contact_id: int) -> List[dict]:
    """이 도구에서 만든 IR 요청·미팅을 활동 이력 줄로.

    시트에서 옮겨 온 줄과 **같은 모양**이어야 한 줄기로 읽힌다.
    """
    from ..models import IrRequest, Meeting
    from ..services.pipeline import MEETING_KINDS, OUTCOMES, REQUEST_STATUS

    out: List[dict] = []

    for row in db.execute(
        select(IrRequest).where(IrRequest.contact_id == contact_id)
    ).scalars().all():
        date_ = (row.requested_at or "")[:10]
        out.append({
            "date": date_, "month": None, "kind": "ir_request",
            "content": f"IR 자료 요청 · {REQUEST_STATUS.get(row.status, row.status)}",
            "source": "system",
            "companies": [{"name": row.company_name or "", "known": bool(row.company_id)}]
                         if row.company_name else [],
            "company_count": 1 if row.company_name else None,
            "weekday": sheet_import.weekday_of(date_) if date_ else None,
            "week": sheet_import.week_of_month(date_) if date_ else None,
        })

    for row in db.execute(
        select(Meeting).where(Meeting.contact_id == contact_id)
    ).scalars().all():
        date_ = (row.scheduled_at or "")[:10]
        label = MEETING_KINDS.get(row.kind, row.kind)
        if row.status == "done":
            label += f" 완료 · {OUTCOMES.get(row.outcome or '', '결과 미정')}"
        elif row.status == "canceled":
            label += " 취소"
        else:
            label += " 예정"
        out.append({
            "date": date_, "month": None, "kind": "meeting",
            "content": label, "source": "system",
            "companies": [{"name": row.company_name, "known": False}]
                         if row.company_name else [],
            "company_count": None,
            "weekday": sheet_import.weekday_of(date_) if date_ else None,
            "week": sheet_import.week_of_month(date_) if date_ else None,
        })

    return out


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


def _batch_company_names(db: Session, batch_ids: set) -> Dict[int, List[str]]:
    """회차별 기업 이름을 **번호 순서대로**. 한 번에 모아 온다."""
    from ..models import DealBatchCompany

    ids = [b for b in batch_ids if b]
    if not ids:
        return {}
    rows = db.execute(
        select(DealBatchCompany.batch_id, IrCompany.name)
        .join(IrCompany, IrCompany.id == DealBatchCompany.company_id)
        .where(DealBatchCompany.batch_id.in_(ids))
        .order_by(DealBatchCompany.batch_id, DealBatchCompany.position)
    ).all()
    out: Dict[int, List[str]] = {}
    for batch_id, name in rows:
        out.setdefault(batch_id, []).append(name)
    return out


def _send_view(item: SendItem, job: SendJob, names: List[str],
               known: Dict[str, str]) -> dict:
    """발송 1건 → 화면용. **시트에서 옮겨 온 줄과 같은 모양**이어야 한다.

    예전에는 `딜소개 발송 성공 · {카톡방 이름}` 이라 기업 자리에 담당자 이름이
    찍혔다. 이력을 훑는 목적은 '언제 어떤 기업을 보냈나' 인데 그게 안 보였다.
    """
    date = (item.sent_at or item.created_at or "")[:10]
    return {
        "date": date,
        "month": None,
        "kind": job.kind,
        "content": _send_summary(item, job),
        "source": "system",
        "companies": [
            {"name": name,
             "known": sheet_import.normalize_company_name(name) in known}
            for name in names
        ],
        "company_count": len(names) or None,
        "weekday": sheet_import.weekday_of(date) if date else None,
        "week": sheet_import.week_of_month(date) if date else None,
    }


def _send_summary(item: SendItem, job: SendJob) -> str:
    """실패했을 때만 뜻이 있는 줄. 성공한 건은 기업 목록이 본문이다."""
    label = {"deal_intro": "딜소개", "ir_delivery": "IR 전달"}.get(job.kind, job.kind)
    if item.status == "sent":
        return label
    state = {"failed": "실패", "pending": "대기",
             "canceled": "취소"}.get(item.status, item.status)
    detail = f" — {item.error}" if item.status == "failed" and item.error else ""
    return f"{label} {state}{detail}"


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
    note = _assign(contact, body)
    if contact.kakao_room_name != before_room:
        # 방 이름이 바뀌면 이전 확인 결과는 더 이상 근거가 아니다.
        contact.room_verified = "unverified"
    db.commit()
    # `connect_note` 는 **서버가 저 혼자 바꾼 것**을 화면이 사람에게 전할 자리다.
    # 없으면 응답에 넣지 않는다 — 늘 있는 값이면 화면이 읽지 않게 된다.
    out = {"ok": True, "room_verified": contact.room_verified,
           "connect_stage": contact.connect_stage}
    if note:
        out["connect_note"] = note
    return out


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


def _assign(contact: VcContact, body: ContactIn) -> str:
    """None 은 '변경 없음'. 빈 문자열은 '지움'으로 취급한다(부분 수정 PATCH 의미).

    돌려주는 것은 **화면이 사람에게 보여 줄 한 줄**이다(없으면 빈 문자열).
    서버가 값을 저 혼자 바꿨으면 그렇게 됐다고 말해야 한다 — 아래 참고.
    """
    note = ""
    for field in ("title", "firm", "group_name", "kakao_room_name", "invited_status",
                  "email", "phone", "stages", "sectors", "round_size", "memo", "status",
                  # 시트에 있던 값들 — 화면에서도 고칠 수 있어야 한다.
                  "assignee_name", "department", "office_phone", "office_fax",
                  "address", "card_registered_at", "interest_level",
                  # 스키마(ContactIn)에만 있고 여기 빠져 있어서, 화면에서 고쳐도
                  # 조용히 안 들어갔다 — 요청은 200 으로 끝나는데 값은 그대로다.
                  "kakao_joined", "sourcing_note", "tips_note"):
        value = getattr(body, field)
        if value is not None:
            setattr(contact, field, value.strip() if isinstance(value, str) else value)
    if body.channel_kakao is not None:
        contact.channel_kakao = 1 if body.channel_kakao else 0
    if body.channel_email is not None:
        contact.channel_email = 1 if body.channel_email else 0
    if body.is_hidden is not None:
        contact.is_hidden = 1 if body.is_hidden else 0
    if body.notes is not None:
        # **통째로 덮지 않고 합친다.** 표에서 칸 하나를 고치면 그 칸 하나만
        # 올라온다 — 덮어 버리면 나머지 달의 기록이 그때 사라진다.
        # (`ConsultingCompany` 도 같은 이유로 합친다)
        merged = contact_columns.load_notes(contact.notes)
        merged.update({k: (v or "").strip() for k, v in body.notes.items()})
        contact.notes = contact_columns.dump_notes(merged)

    # ── 연결 단계 ──────────────────────────────────────────────────────────
    #
    # **사람이 고른 값이 언제나 이긴다.** 수정 창에서 고른 단계는 그대로 들어간다.
    # 빈 문자열은 '안 골랐다' 는 뜻이다(담당자 추가 창은 값 없이 열린다) —
    # 여기서만은 빈 값을 '지움' 으로 읽지 않는다. 지울 수 있는 값이 아니다.
    if (body.connect_stage or "").strip():
        stage = body.connect_stage.strip()
        if stage not in sheet_import.CONNECT_LABELS:
            # 모르는 값을 조용히 버리면 화면은 저장된 줄 알고 닫힌다 —
            # 이 저장소가 반복해 당한 부류라 여기서 소리를 낸다.
            raise HTTPException(
                status_code=400,
                detail=f"모르는 연결 상태입니다: {stage}")
        contact.connect_stage = stage

    # 방 이름과 연결 단계가 어긋나면 안 된다. 방 이름을 지웠는데 '연결 완료'로
    # 남으면 발송 대상 목록에는 뜨는데 보낼 방이 없다.
    #
    # **다만 말없이 바꾸지 않는다.** 예전에는 방 이름을 지우기만 하면 코드가
    # 알아서 `진행 중` 으로 되돌렸다. 그래서 카톡방을 나가신 분의 방 이름을
    # 지웠더니 대시보드에 `지금 연결 중 1명` 으로 계속 떴다 — 아무도 연결하고
    # 있지 않은데 화면은 그렇게 말했고, 왜 그렇게 됐는지 어디에도 안 나왔다.
    #
    # 그래서 규칙을 둘로 나눈다.
    #   ① 사람이 단계를 함께 골랐으면 **손대지 않는다.** 수정 창은 늘 고른
    #      값을 함께 보내므로, 화면에서 지우는 길은 언제나 이쪽이다.
    #   ② 단계 없이 방 이름만 지운 요청(스크립트·다른 화면)은 예전처럼
    #      `진행 중` 으로 두되 **그렇게 했다고 응답이 말한다.** 어느 쪽으로
    #      갈지(방 나감인지 다시 연결 중인지)는 코드가 알 수 없어서,
    #      돌이키기 쉬운 쪽(아직 할 일이 남은 쪽)에 둔다.
    if body.kakao_room_name is not None and not (body.connect_stage or "").strip():
        if (contact.kakao_room_name or "").strip():
            contact.connect_stage = sheet_import.STAGE_CONNECTED
        elif contact.connect_stage == sheet_import.STAGE_CONNECTED:
            # 연결됐던 사람이니 미착수로 되돌리지는 않는다.
            contact.connect_stage = sheet_import.STAGE_IN_PROGRESS
            note = ("카톡방 이름을 지워 연결 상태를 "
                    f"'{sheet_import.CONNECT_LABELS[sheet_import.STAGE_IN_PROGRESS]}'"
                    " 으로 바꿨습니다. 방을 나가신 분이면 "
                    f"'{sheet_import.CONNECT_LABELS[sheet_import.STAGE_LEFT_ROOM]}'"
                    " 으로 고쳐 주세요.")
    return note


# --- 참고 시트 --------------------------------------------------------------
#
# 이 라우터는 `/api/contacts` 밑이라 화면 폼이 쓰기엔 주소가 어색하다.
# 참고 시트는 따로 붙인다.

ref_router = APIRouter(tags=["ref-sheets"])


@router.post("/sheets/rename", include_in_schema=False)
def rename_list_sheet(old: str = Form(""), new: str = Form(""),
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """명단(시트) 탭 이름 바꾸기.

    참고 탭은 이름을 바꿀 수 있는데 명단 탭은 못 바꿨다. 원본 시트에서 이름을
    다듬으면 앱만 옛 이름으로 남는다.

    **옮기는 일은 `sheet_owner.rename` 한 곳이 한다.** 이름은 설정 줄뿐 아니라
    사람·달 칸·달 표시에도 문자열로 박혀 있어서, 여기서 따로 적으면 스크립트로
    바꾼 명단과 화면으로 바꾼 명단이 서로 다르게 갈라진다(거기 설명 참고).
    """
    from fastapi.responses import RedirectResponse

    # 자르는 규칙은 **저장하는 쪽**이 가진 것을 그대로 쓴다. 여기서 안 자르면
    # 긴 이름을 넣었을 때 저장된 이름과 되돌아갈 주소가 갈려 없는 탭이 열린다.
    before, after = (old or "").strip(), sheet_owner.normalize_label(new)
    # 이름 없는 탭은 누를 자리가 없어진다.
    if not before or not after or before == after:
        return RedirectResponse(f"{_back(db, before)}?sheet={quote(before)}", status_code=303)

    try:
        sheet_owner.rename(db, before, after)
    except sheet_owner.RenameError as exc:
        # **왜 안 됐는지 화면이 말해야 한다.** 조용히 옛 이름으로 돌아가면
        # 누르는 사람은 저장이 된 줄 알고 창을 닫는다.
        db.rollback()
        return RedirectResponse(
            f"{_back(db, before)}?sheet={quote(before)}&msg={quote(str(exc))}",
            status_code=303)
    db.commit()
    return RedirectResponse(f"{_back(db, after)}?sheet={quote(after)}", status_code=303)


class RefCellIn(BaseModel):
    """표 참고 자료의 칸 하나."""
    row: int
    col: int
    value: str = ""


def _editable_ref(db: Session, sheet_id: int, user: User):
    """고칠 수 있는 참고 자료만 돌려준다.

    이 주소들은 **여러 화면이 같이 쓴다** — 투자사 관리 현황과 투자컨설턴트
    현황이 같은 `/ref-sheets/…` 를 부른다. 화면 접근만 막아 두면 번호만 바꿔
    남의 화면 자료를 지우거나 이름을 바꿀 수 있다.

    `page` 값이 곧 그 자료가 붙은 화면 주소라(`contacts` · `consulting`)
    화면 판정을 그대로 쓴다 — 역할별 규칙을 여기 또 적으면 둘이 어긋난다.
    """
    from ..models import RefSheet

    row = db.get(RefSheet, sheet_id)
    if row is None:
        raise HTTPException(status_code=404, detail="참고 시트를 찾을 수 없습니다")
    if not can_open(user, f"/{row.page or 'contacts'}"):
        raise HTTPException(status_code=403, detail="이 자료를 고칠 권한이 없습니다")
    return row


def _ref_back(row, sheet: str = "") -> str:
    """고치고 나서 돌아갈 화면.

    자료가 붙은 화면으로 돌아가야 한다 — `/contacts` 로 못 박아 두면
    투자컨설턴트 현황에서 스크립트를 고쳤을 때 남의 화면으로 튄다.
    """
    back = f"/{row.page or 'contacts'}?ref={row.id}"
    if sheet:
        back += f"&sheet={quote(sheet)}"
    return back


@ref_router.patch("/api/ref-sheets/{sheet_id}/cell", include_in_schema=False)
def edit_ref_cell(sheet_id: int, body: RefCellIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """표 참고 자료의 칸 고치기.

    보기만 되던 자료다. 스크립트·성격 정리는 쓰면서 다듬는 것이라, 고치려고
    구글 시트를 따로 열어야 하면 화면 안으로 들여온 뜻이 없다.
    """
    import json

    row = _editable_ref(db, sheet_id, user)
    if row.kind != "table":
        raise HTTPException(status_code=404, detail="표 참고 자료가 아닙니다")
    data = json.loads(row.content_json or "{}")
    rows = data.get("rows") or []
    if not (0 <= body.row < len(rows)) or not (0 <= body.col < len(rows[body.row])):
        raise HTTPException(status_code=400, detail="없는 칸입니다")
    rows[body.row][body.col] = body.value.strip()
    data["rows"] = rows
    row.content_json = json.dumps(data, ensure_ascii=False)
    db.commit()
    return {"ok": True}


@ref_router.post("/ref-sheets/{sheet_id}/body", include_in_schema=False)
def edit_ref_body(sheet_id: int, body: str = Form(""), sheet: str = Form(""),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """줄글 참고 자료 고치기.

    줄글은 칸으로 나뉘어 있지 않아 통째로 고친다 — 표로 쪼개면 내용이 칸에
    잘려 사라진다.
    """
    import json

    from fastapi.responses import RedirectResponse

    row = _editable_ref(db, sheet_id, user)
    data = json.loads(row.content_json or "{}")
    data["body"] = body.replace("\r\n", "\n")
    row.content_json = json.dumps(data, ensure_ascii=False)
    db.commit()
    return RedirectResponse(_ref_back(row, sheet), status_code=303)


@ref_router.post("/ref-sheets/{sheet_id}/rename", include_in_schema=False)
def rename_ref_sheet(sheet_id: int, title: str = Form(""), sheet: str = Form(""),
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """참고 탭 이름 바꾸기.

    이름이 원본 시트의 탭 이름 그대로라 길고(`40개사 스타트업 매월 1회
    리마인드 카톡 가이드`) 무엇을 여는 탭인지 한눈에 안 들어온다. 자료는
    그대로 두고 부르는 이름만 바꾼다.
    """
    from fastapi.responses import RedirectResponse

    row = _editable_ref(db, sheet_id, user)
    # 이름 없는 탭은 누를 자리가 없어진다 — 비우려 하면 그냥 두던 이름을 쓴다.
    name = (title or "").strip()
    if name:
        row.title = name[:80]
        db.commit()
    return RedirectResponse(_ref_back(row, sheet), status_code=303)


@ref_router.post("/ref-sheets/{sheet_id}/delete", include_in_schema=False)
def delete_ref_sheet(sheet_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """참고 탭 지우기.

    다 옮겨 놓고 쓰면서 추리는 것이 순서라, 안 쓰는 탭이 남아 있으면 자리만
    차지한다. **지우지 않고 감춘다** — 원본 시트를 다시 받아 오지 않아도
    되돌릴 수 있어야 한다.
    """
    from fastapi.responses import RedirectResponse

    row = _editable_ref(db, sheet_id, user)
    row.is_active = 0
    db.commit()
    # 지운 탭은 다시 열 수 없으니 `?ref=` 없이 그 화면만 연다.
    return RedirectResponse(f"/{row.page or 'contacts'}", status_code=303)
