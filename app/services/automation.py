"""2단계 자동화 — **스위치 · 보내는 계정 · 시험 모드**.

2단계 자동화는 사람 확인 없이 나간다(미팅 후 문의 · 미팅 요청 · 소싱
리마인드 · 채널방 · 스타트업 월간). 이 파일은 그 다섯이 함께 쓰는 세 가지를
한 곳에 둔다.

1. **켜짐/꺼짐** — 팀 현황의 `자동화` 판(관리자). 기본은 꺼짐이다.
2. **누구 카톡에서 나가나** — 자동화마다 보내는 계정 하나. 비워 두면 기본
   보내는 계정(`default_sender_id`)이다. 회차가 그 계정 것으로 서므로 **그
   계정 PC 의 발송기만** 집어간다 — `routers/agent_api.poll` 은 회차 주인의
   기기 토큰에만 잡을 내준다(사용자 1명 = 기기 1대, `AgentDevice.user_id` 가
   유일). 다른 팀원의 발송(딜소개 등)은 이 파일을 지나지 않는다.
3. **시험 모드** — 기본은 켜짐. 켜져 있으면 자동화가 보낼 모든 한 통이 원래
   방 대신 **시험방**으로 간다(`route`).

## 시험 모드는 새 장치가 아니다  ★

시험방으로 가는 발송은 이미 있다 — `/setup` 의 시험 단추가 만드는
`test_send` 회차(`models.TEST_SEND_KIND`). 그 종류는 일부러 `SEND_KINDS` 밖에
있어서 **실적 · 후속(캐던스) · 담당자 이력 어디에도 안 잡힌다.** 여기서도 그
종류로 세운다(`build_job`). 그래서 시험 회차는

  · 방이 시험방 하나이고(`route` 가 바꾼다)
  · 글 맨 앞에 `[시험] 원래 받을 방: …` 이 붙고 — 시험하는 사람이 **어디로
    갈 뻔했는지**를 본다
  · 받는 줄(담당자 · 소싱 명단 · 기업)을 **가리키지 않는다** — 가리키면 그
    줄의 발송 이력에 시험이 섞인다. 무엇을 위한 한 통이었는지는 자동화가
    따로 적는다.

`/setup` 시험 단추의 시험방(`config.TEST_ROOM`)과 다른 점은 하나 — 방 이름을
**화면에서** 정한다. 시험은 보내는 계정(예: 한 사람의 Windows PC) 카톡에 있는
방 하나로 해야 하는데, `.env` 값은 서버 전체에 하나뿐이고 바꾸려면 배포가
필요하다. 대신 **진짜 상대의 방 이름은 시험방으로 받지 않는다**
(`test_room_problem`) — 오타 하나로 시험 글이 투자사 방에 가는 길을 막는다.

## 왜 회차를 여기서 짓나 (`build_job`)

딜소개 화면의 `routers/deals.py: create_send_list` 는 **내 명단만** 받고
(`VcContact.user_id == user.id`), 시험방을 읽지 않는다. 자동화는 그 둘을
넘어야 한다 — 팀 전원의 미팅에 보내는 계정 하나가 묻고, 시험 모드에서는
시험방으로 간다. 그래서 회차 짓기를 여기 한 곳에 둔다. 문구는 짓지 않는다 —
문구는 각 자동화가 **발송 화면과 같은 함수**로 지어 넘긴다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import (TEST_SEND_KIND, AutoSendSetting, Automation, DealBatch,
                      IrCompany, SendItem, SendJob, SourcingContact, User,
                      VcContact)

log = logging.getLogger(__name__)


# ── 어떤 자동화가 있나 ──────────────────────────────────────────────────────

MEETING_REVIEW = "meeting_review"
MEETING_REQUEST = "meeting_request"
SOURCING_REMIND = "sourcing_remind"
CHANNEL_TOP = "channel_top"
STARTUP_MONTHLY = "startup_monthly"


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    #: 화면 한 줄 — 언제 누구에게 무엇이 나가나(기본값 기준).
    summary: str


#: 팀 현황 판에 서는 차례. **여기 없는 열쇠는 저장하지 않는다.**
KINDS: List[Kind] = [
    Kind(MEETING_REVIEW, "미팅 후 검토결과 문의",
         "미팅 완료 2일 뒤 14:00 — 그 투자사 방에 미팅 후기 문구"),
    Kind(MEETING_REQUEST, "미팅 요청 2회",
         "IR 자료 전달 7일 뒤 14:00 미팅 요청, 답이 없으면 10일 뒤 한 번 더"),
    Kind(SOURCING_REMIND, "소싱 리마인드",
         "매월 2·3주차 수요일 11:00 — 이번 달 딜을 아직 안 준 심사역"),
    Kind(CHANNEL_TOP, "채널방 TOP·핵심 딜",
         "매주 수요일 13:30 — 오픈채팅방마다 TOP·핵심 딜 3곳"),
    Kind(STARTUP_MONTHLY, "스타트업 월간 발송",
         "매월 15일 11:00 → 20일 13:00 → 16일 14:00 순환"),
]
BY_KEY: Dict[str, Kind] = {k.key: k for k in KINDS}

#: 시험 글 맨 앞 한 줄. **원래 받을 방**을 그대로 적는다 — 시험하는 사람이
#: 대상이 맞게 잡혔는지 본다.
TEST_PREFIX = "[시험] 원래 받을 방: {room}"
#: 방 이름이 없는 대상(이런 줄은 자동화가 미리 거르지만, 거르기 전 단계의
#: 미리보기에서 빈칸으로 찍히지 않게).
NO_ROOM = "(방 이름 없음)"

#: 시험방 이름 길이 상한. 카톡방 제목이 이보다 길 일은 없다.
MAX_ROOM = 120


# ── 설정 ────────────────────────────────────────────────────────────────────

def load(db: Session, key: str) -> Optional[Automation]:
    """이 자동화의 줄. **없으면 `None` — 그것이 꺼짐이다.**"""
    return db.execute(
        select(Automation).where(Automation.key == key)
    ).scalars().first()


def params(row: Optional[Automation]) -> dict:
    """자동화마다 다른 값. 망가진 JSON 이어도 화면을 죽이지 않는다."""
    if row is None or not row.params:
        return {}
    try:
        value = json.loads(row.params)
    except ValueError:
        log.warning("자동화 %s 의 값이 망가져 있습니다 — 기본값을 씁니다", row.key)
        return {}
    return value if isinstance(value, dict) else {}


def set_params(row: Automation, values: dict) -> None:
    row.params = json.dumps(values, ensure_ascii=False, sort_keys=True)


def is_on(row: Optional[Automation]) -> bool:
    return bool(row and row.enabled)


def is_test(row: Optional[Automation]) -> bool:
    """시험 모드인가. **줄이 없으면 시험 모드다** — 기본이 켜짐이다."""
    return True if row is None else bool(row.test_mode)


def default_sender_id(db: Session) -> Optional[int]:
    """기본 보내는 계정 — **스타트업 월간 발송을 보내는 그 계정.**

    자동화는 모든 팀원의 투자사 방에 들어가 있는 계정 하나에서 나간다. 그
    계정이 누구인지 코드에 적지 않는다(저장소가 공개다). 이미 그 한 계정을
    고르는 자리가 있다 — 스타트업 월간 발송(`auto_send_settings` 의 `startup_ir`
    줄)이 **정해진 한 PC 의 카톡**에서만 나가도록 관리자가 고른 계정이다.
    거기가 비면 미팅 후기 자동 준비 계정, 그것도 없으면 `None`(화면에서 골라야
    한다).
    """
    for kind in ("startup_ir", "meeting_review"):
        row = db.execute(
            select(AutoSendSetting).where(AutoSendSetting.kind == kind)
        ).scalars().first()
        if row is not None and row.user_id:
            return row.user_id
    return None


def sender_id(db: Session, row: Optional[Automation]) -> Optional[int]:
    """이 자동화가 보내는 계정 번호 — 고른 계정, 없으면 기본."""
    if row is not None and row.user_id:
        return row.user_id
    return default_sender_id(db)


def may_send(user: Optional[User]) -> bool:
    """보내는 계정이 될 수 있는가 — 살아 있고 딜소개를 보내는 계정.

    투자컨설턴트는 발송기가 붙은 PC 가 없다(`deps.sends_deals`). 정지된
    계정을 그대로 두면 회차가 서기만 하고 아무도 안 집어간다.
    """
    from .. import deps

    return bool(user is not None and user.is_active and deps.sends_deals(user))


def sender(db: Session, row: Optional[Automation]) -> Optional[User]:
    """이 자동화가 보내는 계정. 쓸 수 없는 계정이면 `None`."""
    uid = sender_id(db, row)
    user = db.get(User, uid) if uid else None
    return user if may_send(user) else None


def clean_room(raw: Optional[str]) -> str:
    return (raw or "").strip()[:MAX_ROOM]


def real_rooms(db: Session) -> set:
    """**진짜 상대**의 방 이름들 — 투자사 명단 · 딜 소싱 명단 · 기업 대표방 ·
    자동화가 보내는 방 목록(채널방처럼 받는 줄 없이 방 이름만 적어 둔 것 —
    자동화 값의 `rooms`)."""
    names = set()
    for column in (VcContact.kakao_room_name, SourcingContact.kakao_room_name,
                   IrCompany.kakao_room_name):
        for value in db.execute(select(column).where(column.isnot(None))).scalars():
            text = (value or "").strip()
            if text:
                names.add(text)
    for row in db.execute(select(Automation)).scalars().all():
        rooms = params(row).get("rooms")
        if isinstance(rooms, list):
            names |= {str(r).strip() for r in rooms if str(r).strip()}
    return names


def test_room_problem(db: Session, room: Optional[str]) -> str:
    """이 이름을 시험방으로 쓸 수 없는 까닭. 쓸 수 있으면 빈 글자.

    **진짜 상대의 방 이름은 받지 않는다.** 시험방 칸에 투자사 방 이름이
    들어가면 시험 글(`[시험] 원래 받을 방: …`)이 그 투자사에게 간다 — 시험
    모드가 막으려던 바로 그 사고다. 복사해 붙이다 한 줄 어긋나는 것으로 충분히
    생긴다.
    """
    text = clean_room(room)
    if not text:
        return "시험방 이름을 넣으세요 — 시험 모드에서는 모든 글이 그 방으로 갑니다"
    if text in real_rooms(db):
        return (f"'{text}' 은 실제 상대의 카톡방 이름입니다 — 시험방으로 쓸 수 "
                "없습니다(나와의 채팅 등 우리 쪽 방을 넣으세요)")
    return ""


def save(db: Session, key: str, *, enabled: bool, user_id: Optional[int],
         test_mode: bool, test_room: Optional[str]) -> Automation:
    """설정을 저장한다. **값은 여기서 한 번만 가린다** — 못 받을 값이면
    `ValueError`(까닭이 그대로 화면에 간다).

    - 시험방은 진짜 상대의 방이면 안 된다(`test_room_problem`). 비워 둘 수는
      있다 — 그러면 시험 모드인 동안 **아무것도 안 나간다**(켜 둘 수 없게
      막는다: 켜짐이라고 적혀 있는데 아무 일도 없으면 그것이 제일 나쁘다).
    - 보내는 계정은 살아 있고 딜소개를 보내는 계정이어야 한다.
    """
    if key not in BY_KEY:
        raise ValueError("그런 자동화는 없습니다")
    room = clean_room(test_room)
    if room:
        problem = test_room_problem(db, room)
        if problem:
            raise ValueError(problem)
    member = db.get(User, user_id) if user_id else None
    if user_id and not may_send(member):
        raise ValueError("보내는 계정은 딜소개를 보내는 살아 있는 계정이어야 합니다")

    row = load(db, key)
    if row is None:
        row = Automation(key=key, enabled=0, test_mode=1)
        db.add(row)
    row.user_id = member.id if member else None
    row.test_mode = 1 if test_mode else 0
    row.test_room = room or None

    if enabled:
        if sender(db, row) is None:
            raise ValueError("보내는 계정을 고르세요 — 기본 보내는 계정이 정해져 있지 않습니다")
        if row.test_mode and not room:
            raise ValueError("시험 모드로 켜려면 시험방 이름을 넣으세요")
    row.enabled = 1 if enabled else 0
    db.commit()
    return row


# ── 시험방으로 돌리기 ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Routed:
    room: str
    message: str
    test: bool
    #: 시험 모드에서 나눠 보내는 글이면 머리줄이 첫 통이다.
    parts: tuple = ()


def route(room: str, message: str, *, test_room: Optional[str] = None,
          parts: Sequence[str] = ()) -> Routed:
    """한 통이 **어디로 무엇으로** 가나 — 시험 모드면 시험방으로, 머리줄을 붙여.

    `test_room` 이 비어 있으면 실제 모드다: 받은 그대로 돌려준다. 시험 모드의
    머리줄은 **원래 받을 방**을 적는다 — 시험하는 사람이 대상이 맞게 잡혔는지를
    그 한 줄로 본다.
    """
    target = (room or "").strip()
    if not test_room:
        return Routed(room=target, message=message, test=False,
                      parts=tuple(parts))
    head = TEST_PREFIX.format(room=target or NO_ROOM)
    return Routed(room=test_room, message=f"{head}\n\n{message}", test=True,
                  parts=((head,) + tuple(parts)) if parts else ())


# ── 회차 짓기 ────────────────────────────────────────────────────────────────

@dataclass
class Out:
    """자동화가 보낼 한 통. 받는 줄은 **셋 중 하나만** 찬다(`SendItem` 과 같다)
    — 채널방처럼 받는 줄이 없는 방도 있다."""

    room: str
    message: str
    contact_id: Optional[int] = None
    sourcing_contact_id: Optional[int] = None
    ir_company_id: Optional[int] = None
    stage: Optional[int] = None
    parts: List[str] = field(default_factory=list)
    #: 자동화 안에서 이 한 통을 가리키는 열쇠(예: `meeting:12`). 두 번 안
    #: 보내는 판정에 쓴다 — 회차는 그것을 모른다.
    ref: str = ""
    #: 이 한 통에 실린 기업들(채널방). 기업마다 '보냈다' 줄이 선다.
    company_ids: List[int] = field(default_factory=list)
    #: 세운 뒤 채워진다 — 이 한 통이 된 발송 건.
    item_id: Optional[int] = None


def build_job(db: Session, *, sender: User, kind: str, title: str,
              outs: Sequence[Out], scheduled_at: Optional[str] = None,
              test_room: Optional[str] = None, status: str = "draft",
              topic: Optional[str] = None) -> SendJob:
    """자동화 회차 하나를 **보내는 계정 것으로** 세운다. 커밋은 부르는 쪽이.

    - 주인은 `sender` — 그 계정 기기만 집어간다(`agent_api.poll`).
    - `test_room` 이 있으면 **시험 회차**다: 종류가 `test_send` 이고, 모든 한
      통이 시험방으로 가며(`route`), 받는 줄을 가리키지 않는다.
    - 기본은 `draft` 로 서서 `scheduled_at` 을 기다린다 — 예약을 푸는 것은
      `services/scheduled_send.py` 하나다(발송 경로를 새로 만들지 않는다).
    """
    test = bool(test_room)
    batch = DealBatch(user_id=sender.id, title=title,
                      sent_date=clock.today().isoformat(), cycle_type="auto")
    db.add(batch)
    db.flush()
    job = SendJob(user_id=sender.id, kind=TEST_SEND_KIND if test else kind,
                  batch_id=batch.id, status=status, total=len(outs), sent=0,
                  failed=0, scheduled_at=scheduled_at,
                  topic=None if test else topic)
    db.add(job)
    db.flush()
    for out in outs:
        routed = route(out.room, out.message, test_room=test_room,
                       parts=out.parts)
        item = SendItem(
            job_id=job.id,
            contact_id=None if test else out.contact_id,
            sourcing_contact_id=None if test else out.sourcing_contact_id,
            ir_company_id=None if test else out.ir_company_id,
            stage=None if test else out.stage,
            channel="kakao",
            room_name=routed.room,
            message=routed.message,
            parts_json=(json.dumps(list(routed.parts), ensure_ascii=False)
                        if routed.parts else None),
            status="pending",
        )
        db.add(item)
        db.flush()
        out.item_id = item.id
    return job


#: [시험방 확인] 이 보내는 한 통.
CHECK_MESSAGE = ("[시험] 자동화 '{label}' 시험방 확인입니다 — 이 글이 보이면 "
                 "시험방이 맞게 잡힌 것입니다. 실제 발송이 아닙니다.")


def queue_check(db: Session, key: str) -> SendJob:
    """[시험방 확인] — 보내는 계정 PC 로 **시험방에 한 통**. 못 하면 `ValueError`.

    자동화를 시험 모드로 켜기 전에 두 가지를 먼저 본다: 시험방 이름이 그 계정
    카톡에서 정말 열리는가, 그 계정 PC 의 발송기가 집어가는가. 바로 나간다
    (`queued`) — 시험 종류라 보내는 시간 관문도 하루 상한도 안 걸린다
    (`send_guard` 머리말: 가는 곳이 우리 방 하나뿐이다).
    """
    kind = BY_KEY.get(key)
    if kind is None:
        raise ValueError("그런 자동화는 없습니다")
    row = load(db, key)
    room = clean_room(row.test_room if row else "")
    problem = test_room_problem(db, room)
    if problem:
        raise ValueError(problem)
    who = sender(db, row)
    if who is None:
        raise ValueError("보내는 계정이 없습니다 — 먼저 계정을 고르세요")
    # 확인 한 통은 머리줄 없이 그대로 — 원래 받을 방이 따로 없다. 종류를
    # 처음부터 시험 종류로 주면 `build_job` 이 방을 바꾸지 않는다.
    job = build_job(db, sender=who, kind=TEST_SEND_KIND,
                    title=f"{kind.label} 시험방 확인", status="queued",
                    outs=[Out(room=room, message=CHECK_MESSAGE.format(
                        label=kind.label))])
    db.commit()
    return job


# ── 화면 ────────────────────────────────────────────────────────────────────

def status(db: Session) -> dict:
    """팀 현황 `자동화` 판이 읽는 한 덩이. **화면은 판정하지 않는다.**"""
    default_id = default_sender_id(db)
    default_user = db.get(User, default_id) if default_id else None
    rows = []
    for kind in KINDS:
        row = load(db, kind.key)
        who = sender(db, row)
        rows.append({
            "key": kind.key,
            "label": kind.label,
            "summary": kind.summary,
            "enabled": is_on(row),
            "test_mode": is_test(row),
            "test_room": (row.test_room or "") if row else "",
            "user_id": row.user_id if row and row.user_id else 0,
            "sender": who.name if who else "",
            "params": params(row),
        })
    return {"rows": rows,
            "default_sender": default_user.name if default_user else "",
            "default_sender_id": default_id or 0}
