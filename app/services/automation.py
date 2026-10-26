"""2단계 자동화 — **스위치 · 보내는 계정 · 시험 모드**.

2단계 자동화는 사람 확인 없이 나간다(미팅 후 문의 · 미팅 요청 · 소싱
리마인드 · 채널방 · 스타트업 월간). 이 파일은 그 다섯이 함께 쓰는 세 가지를
한 곳에 둔다.

1. **켜짐/꺼짐** — 팀 현황의 `자동화` 판(관리자). 기본은 꺼짐이다.
2. **누구 카톡에서 나가나** — 팀에 하나인 **자동 발송 계정**(자동화 판의 팀
   공통 칸, 안 골랐으면 스타트업 월간 발송 계정 — `default_sender_id`). 모든
   투자사 방에 들어가 있는 업무용 PC 한 대다. 자동화마다 바꿀 수는 있지만
   다르면 판이 경고한다(`status` 의 `sender_warning`). 회차가 그 계정 것으로
   서므로 **그 계정 PC 의 발송기만** 집어간다 — `routers/agent_api.poll` 은
   회차 주인의 기기 토큰에만 잡을 내준다(사용자 1명 = 기기 1대,
   `AgentDevice.user_id` 가 유일). 다른 팀원의 발송(딜소개 등)은 이 파일을
   지나지 않는다. 팀 공통 칸에는 그 밖에 가능 시간대 · 피할 시간 · 같은 분
   하루 최대 · 자동 회차 사이 간격이 있다(`Team`).
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
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import (TEST_SEND_KIND, Automation, DealBatch, IrCompany, SendItem,
                      SendJob, SourcingContact, User, VcContact)

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
         "미팅 완료 2일 뒤 14:00 그 투자사 방에 미팅 후기 문구, "
         "30일 뒤 14:00 투자 결정 문의(거절이면 안 물음)"),
    Kind(MEETING_REQUEST, "미팅 요청 2회",
         "IR 자료 전달 7일 뒤 14:00 미팅 요청, 답이 없으면 10일 뒤 한 번 더"),
    Kind(SOURCING_REMIND, "소싱 리마인드",
         "매월 3주차 목요일 11:00 — 이번 달 딜을 아직 안 준 심사역"),
    Kind(CHANNEL_TOP, "채널방 TOP·핵심 딜",
         "매주 수요일 13:30 — 오픈채팅방마다 TOP·핵심 딜 3곳"),
    Kind(STARTUP_MONTHLY, "스타트업 월간 발송",
         "매월 26일 11:00 → 30일(없으면 말일) 13:00 → 28일 14:00 순환, "
         "토·일이면 앞 평일 — 스타트업 월간 발송 메뉴의 계정으로"),
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


# ── 팀 공통 설정 (자동 발송 계정 · 시간대 · 피할 시간 · 중복 · 회차 간격) ─────────
#
# 자동 발송은 **한 사람의 업무용 PC**(모든 투자사 방에 들어가 있는 계정)에서
# 나간다. 그래서 자동화마다 따로가 아니라 **팀에 하나**인 값들이 있다:
#
#   · 자동 발송 계정 — 다섯 자동화의 기본 보내는 계정(자동화마다 바꿀 수는 있다)
#   · 자동 발송 가능 시간대 — 이 안에서만 자동 회차가 선다(발송 안전장치
#     09~19시 안쪽만 고른다)
#   · 피할 시간 — 업무용 PC 라 점심 등 비워 둘 때. 그 안에 떨어진 회차는 끝나는
#     분으로 밀린다
#   · 같은 분 하루 최대 자동 발송 수(기본 1) — 다른 자동화끼리도 센다
#   · 자동 회차 사이 최소 간격(분) — 두 자동화 회차가 붙어 나가지 않게
#
# 새 표를 만들지 않고 `automations` 표에 **예약된 열쇠 한 줄**(`TEAM_KEY`)로 둔다
# — 칸 모양(보내는 계정 `user_id` + 값 `params`)이 똑같고, 수정 로그도 같은
# 자리(`edit_log.WATCHED["automations"]`)에 남는다. `KINDS` 에 없는 열쇠라
# 자동화 한 줄로 저장되는 길(`save`)은 이 줄을 못 건드린다.

TEAM_KEY = "_team"

DEFAULT_WINDOW = ("09:00", "19:00")
#: 같은 분(담당자 · 딜 소싱 명단 한 줄)에게 하루에 나가는 자동 발송의 최대 수.
DEFAULT_PER_CONTACT_DAILY = 1
MAX_PER_CONTACT_DAILY = 5
#: 다른 자동화 회차 사이 최소 간격(분). 상한을 예약이 버티는 시간
#: (`scheduled_send.EXPIRE_MINUTES` = 60분)보다 한참 아래에 둔다 — 간격 때문에
#: 기다리는 회차가 그 기다림 때문에 '예약 시각을 놓쳤다' 로 떨어지지 않게
#: (`automation_runner.release_floor` 가 그 기다림만큼 버티는 시간을 늘린다).
DEFAULT_JOB_GAP_MIN = 10
MAX_JOB_GAP_MIN = 30


def _minutes(raw) -> int:
    """`HH:MM` → 그날 0시부터의 분. 못 읽으면 `ValueError`."""
    import re

    found = re.fullmatch(r"(\d{1,2}):(\d{2})", str(raw or "").strip())
    if not found:
        raise ValueError(f"'{raw}' — 09:00 처럼 시각을 적으세요")
    hour, minute = int(found.group(1)), int(found.group(2))
    if minute > 59 or hour > 24 or (hour == 24 and minute):
        raise ValueError(f"'{raw}' — 시각을 읽을 수 없습니다")
    return hour * 60 + minute


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def guard_window() -> tuple:
    """발송 안전장치가 허락하는 폭(분) — 팀 시간대는 이 안이어야 한다.

    폭은 `send_window` 한 곳에서 온다. 테스트 서버에서 껐으면 00:00~24:00 이다.
    """
    from . import send_window

    low, high = send_window.hours()
    return low * 60, high * 60


def time_input(minutes: int) -> str:
    """`<input type="time">` 에 넣을 값. 그 칸은 `24:00` 을 못 담아 `23:59` 로 적는다
    (테스트 서버에서 시간 제한을 껐을 때만 생긴다)."""
    return hhmm(min(minutes, 24 * 60 - 1))


@dataclass(frozen=True)
class Team:
    """팀 공통 설정 한 덩이. 저장값이 없거나 망가졌으면 기본값이다."""

    sender_id: Optional[int] = None
    window_start: str = DEFAULT_WINDOW[0]
    window_end: str = DEFAULT_WINDOW[1]
    avoid_start: str = ""
    avoid_end: str = ""
    per_contact_daily: int = DEFAULT_PER_CONTACT_DAILY
    job_gap_min: int = DEFAULT_JOB_GAP_MIN

    @property
    def window_label(self) -> str:
        return f"{self.window_start}~{self.window_end}"

    @property
    def avoid_label(self) -> str:
        return f"{self.avoid_start}~{self.avoid_end}" if self.avoid_start else ""

    def contains(self, value: str) -> bool:
        """`HH:MM` 이 시간대 안인가(끝 시각은 안 든다)."""
        try:
            at = _minutes(value)
        except ValueError:
            return False
        return _minutes(self.window_start) <= at < _minutes(self.window_end)

    def fit(self, when):
        """이 시각을 **보낼 수 있는 첫 분**으로 옮긴다. 그날 안에 못 넣으면 `None`.

        시간대 시작보다 이르면 시작으로, 피할 시간 안이면 그 끝으로 민다 —
        **앞당기지는 않는다**(정한 시각보다 먼저 나가면 사람이 빼거나 [중단] 할
        틈이 줄어든다). 시간대 끝을 넘으면 그날은 못 나간다.
        """
        from datetime import timedelta

        base = when.replace(second=0, microsecond=0)
        if base < when:
            base += timedelta(minutes=1)
        at = base.hour * 60 + base.minute
        at = max(at, _minutes(self.window_start))
        if self.avoid_start:
            a0, a1 = _minutes(self.avoid_start), _minutes(self.avoid_end)
            if a0 <= at < a1:
                at = a1
        if at >= _minutes(self.window_end):
            return None
        return base.replace(hour=at // 60, minute=at % 60)


def _team_row(db: Session) -> Optional[Automation]:
    return load(db, TEAM_KEY)


def clean_team(values: dict) -> dict:
    """팀 공통 값을 가린다. **못 받을 값이면 `ValueError`** — 까닭이 화면에 간다.

    화면만 막으면 주소로 폼을 흉내 내는 순간 뚫린다 — 저장 자리에서 자른다.
    """
    low, high = guard_window()
    start = _minutes(values.get("window_start") or DEFAULT_WINDOW[0])
    end = _minutes(values.get("window_end") or DEFAULT_WINDOW[1])
    if not (low <= start < end <= high):
        raise ValueError(f"자동 발송 가능 시간대는 {hhmm(low)}~{hhmm(high)} 안에서 "
                         "시작이 끝보다 앞이어야 합니다(발송 안전장치의 보내는 시간)")
    a0_raw = str(values.get("avoid_start") or "").strip()
    a1_raw = str(values.get("avoid_end") or "").strip()
    avoid = ("", "")
    if a0_raw or a1_raw:
        if not (a0_raw and a1_raw):
            raise ValueError("피할 시간은 시작과 끝을 함께 넣으세요(안 쓰면 둘 다 비우세요)")
        a0, a1 = _minutes(a0_raw), _minutes(a1_raw)
        if not (start <= a0 < a1 <= end):
            raise ValueError("피할 시간은 자동 발송 가능 시간대 안에서 시작이 끝보다 앞이어야 합니다")
        if a0 == start and a1 == end:
            raise ValueError("피할 시간이 시간대 전체입니다 — 자동 발송이 하나도 못 나갑니다")
        avoid = (hhmm(a0), hhmm(a1))
    try:
        per = int(str(values.get("per_contact_daily", DEFAULT_PER_CONTACT_DAILY)).strip())
        gap = int(str(values.get("job_gap_min", DEFAULT_JOB_GAP_MIN)).strip())
    except ValueError:
        raise ValueError("숫자 칸에 숫자를 넣으세요") from None
    if not 1 <= per <= MAX_PER_CONTACT_DAILY:
        raise ValueError(f"같은 분 하루 최대 자동 발송은 1~{MAX_PER_CONTACT_DAILY} 사이로 넣으세요")
    if not 0 <= gap <= MAX_JOB_GAP_MIN:
        raise ValueError(f"자동 회차 사이 최소 간격은 0~{MAX_JOB_GAP_MIN}분 사이로 넣으세요")
    return {"window_start": hhmm(start), "window_end": hhmm(end),
            "avoid_start": avoid[0], "avoid_end": avoid[1],
            "per_contact_daily": per, "job_gap_min": gap}


def team(db: Session) -> Team:
    """팀 공통 설정. 저장값이 망가졌으면 **기본값**으로 돈다(화면을 죽이지 않는다)."""
    row = _team_row(db)
    stored = params(row)
    try:
        cleaned = clean_team(stored) if stored else {}
    except ValueError:
        log.warning("자동화 팀 공통 값이 맞지 않아 기본값을 씁니다")
        cleaned = {}
    return Team(sender_id=row.user_id if row is not None and row.user_id else None,
                **cleaned)


def save_team(db: Session, *, user_id: Optional[int], values: dict) -> Team:
    """팀 공통 설정을 저장한다. 못 받을 값이면 `ValueError`. 커밋까지 한다."""
    cleaned = clean_team(values)
    member = db.get(User, user_id) if user_id else None
    if user_id and not may_send(member):
        raise ValueError("자동 발송 계정은 딜소개를 보내는 살아 있는 계정이어야 합니다")
    row = _team_row(db)
    if row is None:
        row = Automation(key=TEAM_KEY, enabled=0, test_mode=1)
        db.add(row)
    row.user_id = member.id if member else None
    set_params(row, cleaned)
    db.commit()
    return team(db)


def startup_sender_id(db: Session) -> Optional[int]:
    """**스타트업 월간 발송을 보내는 그 계정** — 메뉴가 켜져 있을 때만.

    자동 발송 계정을 따로 안 골랐을 때의 기본값이다. 이미 그 한 계정을 고르는
    자리가 있다 — 스타트업 월간 발송(`auto_send_settings` 의 `startup_ir` 줄)이
    **정해진 한 PC 의 카톡**에서만 나가도록 관리자가 고른 계정이다.

    판정은 A5 와 같은 `startup_send.sender_id` 하나다 — 메뉴를 끄면 비어 있다.
    꺼진 메뉴의 계정을 기본으로 계속 쓰면 판의 '메뉴의 계정 따름' 이 거짓이 되고,
    A5(메뉴 꺼짐 ⇒ 꺼짐)와 나머지 자동화가 다른 계정을 본다(PR #315 리뷰). 메뉴가
    꺼졌고 팀 칸도 비었으면 자동화는 보낼 계정이 없다 — 판이 그렇게 적는다(덜
    보내는 쪽).

    옛 미팅 후기 자동 준비 계정(`meeting_review` 줄)은 더 읽지 않는다 — 그 판을
    걷어 화면에서 고칠 수 없는 값이 되었고, 이주(0105)가 스타트업 계정이 없을 때
    그 계정을 팀 공통 자동 발송 계정으로 옮겼다(#31).
    """
    from . import startup_send

    return startup_send.sender_id(db)


def default_sender_id(db: Session) -> Optional[int]:
    """기본 보내는 계정 — 팀 현황 자동화 판의 **자동 발송 계정**.

    자동화는 모든 팀원의 투자사 방에 들어가 있는 계정 하나(업무용 PC)에서
    나간다. 그 계정이 누구인지 코드에 적지 않는다(저장소가 공개다). 자동화
    판에서 고른 계정이 먼저고, 안 골랐으면 **스타트업 월간 발송 계정**(메뉴가
    켜져 있을 때만 — `startup_sender_id`), 그것도 없으면 `None`(화면에서 골라야
    한다).
    """
    row = _team_row(db)
    if row is not None and row.user_id:
        return row.user_id
    return startup_sender_id(db)


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
    자동화 값의 `rooms`) · **보내는 계정 카톡 기준 방 제목**(`sender_rooms` 의
    확정 제목과 후보 — 시험 글이 실제로 가는 곳이 그 계정 카톡이다)."""
    from ..models import SenderRoom

    names = set()
    for column in (VcContact.kakao_room_name, SourcingContact.kakao_room_name,
                   IrCompany.kakao_room_name, SenderRoom.room_name):
        for value in db.execute(select(column).where(column.isnot(None))).scalars():
            text = (value or "").strip()
            if text:
                names.add(text)
    for raw in db.execute(select(SenderRoom.candidates)
                          .where(SenderRoom.candidates.isnot(None))).scalars():
        try:
            picks = json.loads(raw or "[]")
        except ValueError:
            continue
        if isinstance(picks, list):
            names |= {str(r).strip() for r in picks if str(r).strip()}
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
    from .automation_dedup import room_key

    text = clean_room(room)
    if not text:
        return "시험방 이름을 넣으세요 — 시험 모드에서는 모든 글이 그 방으로 갑니다"
    # 견주는 꼴은 중복 막기의 방 견주기와 같다(띄어쓰기 · 대소문자 무시) — 막는
    # 쪽은 넓게 잡는다.
    if room_key(text) in {room_key(name) for name in real_rooms(db)}:
        return (f"'{text}' 은 실제 상대의 카톡방 이름입니다 — 시험방으로 쓸 수 "
                "없습니다(나와의 채팅 등 우리 쪽 방을 넣으세요)")
    return ""


def turn_off(db: Session, key: str) -> bool:
    """**끈다 — 늘 된다.** 다른 칸을 하나도 가리지 않는다. 껐으면(켜져 있었으면) 참.

    끄는 것은 멈추는 길이라 어떤 값 검사에도 걸리면 안 된다 — 시험방 칸이
    잘못됐다는 까닭으로 끄기가 막혀 실제 모드가 켜진 채로 남으면 그것이 사고다.
    커밋까지 한다. 이미 서 있는 회차를 거두는 것은 `automation_runner.stop_jobs`.
    """
    if key not in BY_KEY:
        raise ValueError("그런 자동화는 없습니다")
    row = load(db, key)
    if row is None or not row.enabled:
        return False
    row.enabled = 0
    db.commit()
    return True


def save(db: Session, key: str, *, enabled: bool, user_id: Optional[int],
         test_mode: bool, test_room: Optional[str], commit: bool = True) -> Automation:
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
    if key == STARTUP_MONTHLY:
        user_id = startup_menu_sender(db, user_id, enabled)
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
    if commit:
        db.commit()
    return row


def startup_menu_sender(db: Session, picked: Optional[int], enabled: bool) -> Optional[int]:
    """스타트업 월간 발송(A5)의 보내는 계정 — **메뉴의 계정 그 하나**.

    스타트업 대표방은 메뉴가 고른 그 한 PC 의 카톡에만 있고, 예약을 푸는 자리도
    그 계정만 통과시킨다(`scheduled_send.held_back`). 다른 계정을 고를 수 있으면
    회차는 서는데 아무 PC 도 못 보내는 반쯤 켜진 자동화가 된다 — 그래서 고르게
    두지 않고 메뉴의 계정을 그대로 적는다(사용자 결정 2026-10-17). 다른 계정을
    넘기면 `ValueError`, 메뉴가 꺼진 채로 켜도 `ValueError`.
    """
    from . import startup_send

    menu = startup_send.sender_id(db)
    label = startup_send.LABEL
    if picked and picked != menu:
        raise ValueError(f"{label}은 메뉴의 계정으로만 보냅니다 — 계정을 바꾸려면 "
                         f"'{label} — 메뉴·보내는 계정' 판에서 바꾸세요")
    if enabled and not menu:
        raise ValueError(f"{label} 메뉴가 꺼져 있습니다 — '{label} — 메뉴·보내는 계정' "
                         "판에서 먼저 켜세요(그 계정 PC 에서 나갑니다)")
    return menu


def follow_startup_menu(db: Session) -> Tuple[bool, int, str]:
    """메뉴를 따라 A5 를 맞춘다 — `(A5 를 껐나, 거둔 회차 수, 덧붙일 말)`. 커밋까지 한다.

    - 메뉴의 계정이 바뀌었으면 A5 도 그 계정으로. 옛 계정 PC 로 서 있던 회차는
      거둔다(`automation_runner.stop_jobs`). 거둔 회차가 **풀리기 전 예약**이고 그날
      나갈 시각 전이면 새 계정으로 곧바로 다시 세운다(`automation_runner.rebuild`)
      — 아니면 그 달은 손으로 보내라고 적는다(같은 달 두 번은 `month_job` 이 막는다).
    - **메뉴를 껐으면 A5 도 끈다**(계정은 마지막 것 그대로) — 보낼 계정이 없는데
      켜짐으로 남으면 화면이 '다음: 날짜' 를 약속하고 그날 아무것도 안 나간다.
    """
    from . import automation_runner, scheduled_send, startup_send

    row = load(db, STARTUP_MONTHLY)
    if row is None:
        return False, 0, ""
    menu = startup_send.sender_id(db)
    if not menu:
        return (turn_off(db, STARTUP_MONTHLY),
                automation_runner.stop_jobs(db, STARTUP_MONTHLY), "")
    if row.user_id == menu:
        return False, 0, ""
    row.user_id = menu
    db.commit()
    unreleased = automation_runner.unreleased_jobs(db, STARTUP_MONTHLY)
    stopped = automation_runner.stop_jobs(db, STARTUP_MONTHLY)
    if not stopped:
        return False, 0, ""
    again = automation_runner.rebuild(db, STARTUP_MONTHLY, unreleased)
    if again is not None and again.get("status") == automation_runner.STATUS_READY:
        at = scheduled_send.parse(again["at"][0])
        return False, stopped, f"새 계정으로 다시 세웠습니다 — {scheduled_send.label(at)} 에 나갑니다"
    why = ("이미 풀렸거나 나갈 시각이 지났습니다" if again is None
           else again.get("error") or {"empty": "보낼 곳 0곳"}.get(again["status"],
                                                                  again["status"]))
    return False, stopped, (f"이 달 A5 회차는 새 계정으로 다시 세우지 않았습니다({why}) — "
                            f"{startup_send.LABEL} 화면에서 손으로 보내세요")


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
    #: 이 한 통만 **다른 시각**에 나갈 때(예: 미팅 요청 두 번째의 시각). 비면
    #: 그 회차의 시각(`Plan.at`). 시각이 다른 한 통은 회차가 따로 선다.
    at: Optional[object] = None


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

def agent_state(db: Session, user_id: Optional[int]) -> dict:
    """이 계정 PC 의 발송기가 **자동 회차를 받을 수 있는 판**인가.

    자동 회차는 건 사이 간격(`delay_min_sec`/`delay_max_sec`)을 잡에 실어
    보낸다. 그 칸을 모르는 낡은 발송기는 제 설정(3~7초)으로 몰아 보내므로
    서버가 자동 회차를 **내주지 않는다**(`routers/agent_api.poll`). 판정은
    `version.agent_handles_automation` 한 곳이다.
    """
    from .. import version
    from ..deps import agent_user_id
    from ..models import AgentDevice

    # 보내는 계정이 남의 발송기로 보내면 그 발송기의 판이다(`deps.agent_user_id`).
    device = db.execute(
        select(AgentDevice).where(AgentDevice.user_id == agent_user_id(db, user_id))
    ).scalars().first() if user_id else None
    reported = (device.agent_version or "") if device is not None else ""
    return {"version": reported,
            "ok": version.agent_handles_automation(reported),
            "need": version.AUTOMATION_AGENT_VERSION,
            "connected": bool(device is not None and device.last_poll_at)}


def status(db: Session) -> dict:
    """팀 현황 `자동화` 판이 읽는 한 덩이. **화면은 판정하지 않는다.**"""
    team_ = team(db)
    default_id = default_sender_id(db)
    default_user = db.get(User, default_id) if default_id else None
    startup_id = startup_sender_id(db)
    startup_user = db.get(User, startup_id) if startup_id else None
    rows = []
    for kind in KINDS:
        row = load(db, kind.key)
        who = sender(db, row)
        own = row.user_id if row and row.user_id else 0
        # 자동화마다 계정을 바꿀 수는 있다. 다만 **자동 발송 계정과 다르면**
        # 그 계정 PC 에서 나간다 — 업무용 PC 한 대에서 나가기로 했으니 판이
        # 크게 적는다.
        differs = bool(own and default_id and own != default_id)
        # A5 는 고르지 않는다 — 메뉴의 계정을 보여 준다(`startup_menu_sender`).
        fixed = None
        if kind.key == STARTUP_MONTHLY:
            from . import startup_send

            menu_id = startup_send.sender_id(db)
            menu_user = db.get(User, menu_id) if menu_id else None
            fixed = {"id": menu_id or 0, "name": menu_user.name if menu_user else ""}
        rows.append({
            "key": kind.key,
            "label": kind.label,
            "summary": kind.summary,
            "fixed_sender": fixed,
            "enabled": is_on(row),
            "test_mode": is_test(row),
            "test_room": (row.test_room or "") if row else "",
            "user_id": own,
            "sender": who.name if who else "",
            "sender_differs": differs,
            "sender_warning": (f"자동 발송 계정({default_user.name if default_user else '-'})과 "
                               f"다른 계정({who.name if who else '-'}) PC 에서 나갑니다"
                               if differs else ""),
            "params": params(row),
        })
    agent = agent_state(db, default_id)
    return {"rows": rows,
            "default_sender": default_user.name if default_user else "",
            "default_sender_id": default_id or 0,
            # 자동 발송 계정을 따로 골랐나(0 이면 스타트업 월간 발송 계정을 따른다).
            "team_sender_id": team_.sender_id or 0,
            "startup_sender": startup_user.name if startup_user else "",
            "team": {"window_start": team_.window_start,
                     "window_end": team_.window_end,
                     "avoid_start": team_.avoid_start,
                     "avoid_end": team_.avoid_end,
                     "window_label": team_.window_label,
                     "avoid_label": team_.avoid_label,
                     "per_contact_daily": team_.per_contact_daily,
                     "job_gap_min": team_.job_gap_min,
                     "max_per_contact_daily": MAX_PER_CONTACT_DAILY,
                     "max_job_gap_min": MAX_JOB_GAP_MIN,
                     "guard_start": hhmm(guard_window()[0]),
                     "guard_end": hhmm(guard_window()[1]),
                     # 시간 칸(`<input type="time">`)에 넣는 값 — `24:00` 을
                     # 못 담는다. 운영(09:00~19:00)에서는 위와 같은 글자다.
                     "guard_end_input": time_input(guard_window()[1]),
                     "window_end_input": time_input(_minutes(team_.window_end)),
                     # 분 단위 칸. 운영은 10분(600초) 그대로이고, 테스트 서버에서
                     # 껐을 때만 1분 — `23:59` 를 고를 수 있게.
                     "time_step": 60 if guard_window()[1] >= 24 * 60 else 600},
            "agent": agent}
