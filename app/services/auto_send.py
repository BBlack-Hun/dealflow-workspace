"""**무인 자동 발송** — 때가 된 건을 사람 없이 발송 목록으로 세운다.

지금 서 있는 것은 **미팅 후기** 하나다. 미팅이 끝나고 열흘 뒤 그 투자사에게
"그 뒤 어떻게 보셨는지" 를 묻는 카톡이 저절로 나간다.

## ⚠ 먼저 알아야 할 것 — 이것은 저장소 문서를 넘어선 결정이다

`docs/TECH_SPEC.md` §8 은 오래 이렇게 적어 두었다.

> 카카오 운영정책은 자동화 프로그램을 통한 서비스 이용을 금지 → **계정 이용
> 제한(제재) 가능성. 본 도구의 최대 리스크**
> 대응: 사람 유사 패턴(건당 랜덤 3~7초), 1회 발송 상한 60건,
> **수동 트리거만(무인 스케줄 발송 금지)**

**사용자가 그 리스크를 알고 자동 발송을 하기로 정했다.** 이 파일이 그 결정이고,
문서도 같이 고쳤다(같은 절 · `docs/FEATURE_SPEC.md` §후속). 지우기 전에 그
판단부터 확인할 것 — "왜 문서와 다르지" 로 읽고 되돌리면 사용자가 정한 것을
코드가 되돌리는 셈이 된다.

문서에서 지킨 것은 **그대로 지킨다**: 건당 랜덤 지연도, 발송 상한도 그대로다
(상한은 아래 `HARD_MAX_PER_DAY`). 바뀐 것은 **누가 방아쇠를 당기는가** 하나뿐이다.

## 위험을 좁히는 것들 — 이 파일의 절반이 이것이다

무인으로 실투자사에게 카톡이 나간다. 되돌릴 수 없다. 그래서:

- **기본은 꺼짐.** 설정 줄이 없으면 아무 일도 없고, 실도 뜨지 않는다
  (메일·문자가 그렇다).
- **한 계정에서만 나간다.** 설정이 고른 그 계정 것으로 잡이 서고, 잡은 그
  계정의 기기 토큰으로만 내려간다.
- **같은 건은 두 번 안 간다.** 보내기 **전에** 자리를 잡는다(`models.AutoSendRun`).
- **시각을 가린다.** 평일, 그리고 설정한 시각의 창 안에서만. 창을 아무 데나
  둘 수는 없다(`EARLIEST_HOUR`~`LATEST_HOUR`) — 받는 쪽이 투자사다.
- **하루 상한.** 문서의 `1회 상한 60건` 을 넘지 못한다.
- **끄는 길이 한 곳.** 팀 현황에서 단추 하나로 멈춘다.
- **나간 것이 남는다.** 잡은 평범한 발송 잡이라 `/jobs/{id}` 와 팀 현황의
  `최근 발송 회차` 에 그대로 뜬다. 어느 잡이 되었는지는 `AutoSendRun.job_id`.

## 새로 짓지 않는다 — 이미 있는 길만 잇는다

- **언제 물어볼지**: `pipeline.today_items(...)["due_followups"]`. 화면(`/ir`)과
  결과 문의 문자가 읽는 바로 그것이다.
- **문구**: `routers/deals.py: review_message`. 발송 화면의 미팅 후기 탭이 지나는
  그 길이다 — 여기서 다시 조립하면 화면과 자동 발송이 다른 글을 낸다.
- **잡**: `routers/deals.py: create_send_list`. 방 이름 확인 · `검토중단` 막이 ·
  **시험방 치환** · 문구 스냅숏이 전부 그 함수 안에 있다. 여기에 한 벌 더 적으면
  그중 하나가 빠진 채로 실투자사 카톡방에 나간다(예약 큐가 같은 이유로 그 함수를
  그대로 부른다).
- **하루 한 번 도는 얼개**: `services/backup.py` · `services/followup_sms.py` 와
  같은 방식 — 웹 프로세스 안 데몬 실이 30분마다 깨어난다.

## 다음 종류를 붙일 자리 — 월말 기업 리마인드

이번은 미팅 후기 하나만이다. 월말 리마인드도 곧 같은 방식으로 나갈 예정이라
얼개를 함께 쓸 수 있게 세워 두었다. 그때 더할 것은 셋뿐이다.

1. `KIND_*` 상수 하나와 `KINDS` 에 줄 하나(`Spec(라벨, 대상 고르기, 잡 만들기)`).
2. 대상을 고르는 함수 — 무엇이 `ref_id` 인가만 정하면 된다(미팅 후기는
   `meetings.id`).
3. 팀 현황 화면에 설정 칸 하나(`team.html` 의 자동 발송 판을 종류마다 그린다).

**표도 실도 안전선도 그대로다.** 설정 줄과 표시 줄이 종류마다 서므로 서로를
밟지 않는다.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..db import SessionLocal
from ..models import AutoSendRun, AutoSendSetting, User, VcContact
from . import cadence, pipeline, sheet_owner

log = logging.getLogger(__name__)

#: 미팅 후기 — 미팅 열흘 뒤 그 투자사에게 결과를 묻는다.
#: 값은 문구 종류(`routers/deals.py: MODE_TEMPLATE_KIND[MODE_REVIEW]`)와 같은
#: 글자다. 같은 것을 가리키므로 다른 글자를 쓸 이유가 없다.
KIND_REVIEW = "meeting_review"

#: **고를 수 있는 시각의 폭.** 설정이 아무 시각이나 담지 못하게 코드가 먼저
#: 좁힌다 — 받는 쪽이 팀원이 아니라 **투자사**다. 새벽 3시에 카톡이 가면
#: 그것만으로 관계가 상한다.
#:
#: 결과 문의 **문자**는 09~20시다(`followup_sms`). 그쪽은 받는 사람이 우리
#: 팀원이라 아침 일찍·저녁 늦게도 괜찮지만, 여기는 양쪽을 한 시간씩 좁혔다:
#: 9시는 출근 직후라 아직 자리에 앉기 전이고, 19시 이후는 퇴근한 사람의 폰이다.
EARLIEST_HOUR = 9
LATEST_HOUR = 19

#: 설정을 처음 켤 때의 값. 오전 10시~오후 5시는 어느 회사든 자리에 있는 시간이다.
DEFAULT_FROM_HOUR = 10
DEFAULT_UNTIL_HOUR = 17

#: **하루에 몇 건까지.** 기본 10건, 최대 60건.
#:
#: 60 은 지어낸 수가 아니라 `docs/TECH_SPEC.md` 의 `1회 발송 상한 60건` 이다.
#: 자동이 되었다고 그 선을 넘으면 문서가 막아 둔 이유(계정 제재)가 그대로
#: 돌아온다. 발송기 쪽에도 같은 상한이 있다(`agent`, 1잡 60건).
DEFAULT_MAX_PER_DAY = 10
HARD_MAX_PER_DAY = 60

#: 얼마나 자주 깨어나 볼 것인가. 백업·결과 문의 문자와 같은 30분이다.
CHECK_INTERVAL_SEC = 30 * 60

_SCHEDULER: Optional[threading.Thread] = None


# --- 종류마다 다른 것 --------------------------------------------------------

@dataclass(frozen=True)
class Target:
    """자동으로 보낼 한 건. `ref_id` 가 **두 번 안 보내게 하는 열쇠**다."""

    ref_id: int
    contact: VcContact


@dataclass(frozen=True)
class Spec:
    """종류 하나가 아는 것. 나머지(설정·시각·상한·표시)는 전부 공용이다."""

    label: str
    #: 이 계정이 지금 자동으로 보낼 건들. 이미 나간 것은 여기서 거르지 않는다
    #: (그 판단은 공용이다 — `_unclaimed`).
    collect: Callable[[Session, User], List[Target]]


# --- 설정 -------------------------------------------------------------------

def load(db: Session, kind: str = KIND_REVIEW) -> Optional[AutoSendSetting]:
    """이 종류의 설정. **없으면 `None` — 그것이 꺼짐이다.**"""
    return db.execute(
        select(AutoSendSetting).where(AutoSendSetting.kind == kind)
    ).scalars().first()


def is_on(setting: Optional[AutoSendSetting]) -> bool:
    """켜져 있는가. **보내는 계정이 없으면 켜진 것이 아니다** — 보낼 사람이
    없는 자동 발송은 돌 수 없고, 반쯤 켜진 상태를 만들면 화면이 `켜짐` 이라고
    적어 두고 아무 일도 일어나지 않는다."""
    return bool(setting and setting.enabled and setting.user_id)


def save(db: Session, kind: str, *, enabled: bool, user_id: Optional[int],
         from_hour: int, until_hour: int, max_per_day: int) -> AutoSendSetting:
    """설정을 저장한다. **값은 여기서 한 번만 다듬는다.**

    화면이 고르개로 좁혀 두었어도 여기서 다시 자른다 — 주소로 폼을 흉내 내면
    무엇이든 들어올 수 있고, 그 한 번이 새벽 3시에 투자사 카톡방을 여는 값이다.
    화면과 라우터가 각각 자르면 언젠가 한쪽만 고쳐진다.
    """
    row = load(db, kind)
    if row is None:
        row = AutoSendSetting(kind=kind)
        db.add(row)
    row.enabled = 1 if enabled else 0
    row.user_id = user_id or None
    row.from_hour, row.until_hour = clamp_hours(from_hour, until_hour)
    row.max_per_day = clamp_cap(max_per_day)
    db.commit()
    return row


def clamp_hours(from_hour: int, until_hour: int) -> tuple:
    """고를 수 있는 폭 안으로 자른다. 뒤집혀 들어오면 한 시간짜리 창으로 만든다.

    `from >= until` 인 창은 **아무 때도 아니다**(`within_window` 가 늘 거짓).
    그대로 두면 화면에는 켜짐이라고 떠 있는데 영영 아무것도 안 나가고, 왜인지
    적힌 곳이 없다. 조용히 안 도는 것보다 좁은 창이 낫다.
    """
    start = max(EARLIEST_HOUR, min(int(from_hour or 0), LATEST_HOUR - 1))
    end = max(start + 1, min(int(until_hour or 0), LATEST_HOUR))
    return start, end


def clamp_cap(value: int) -> int:
    """하루 상한. 1 미만은 1, 문서가 정한 60 을 넘지 못한다."""
    return max(1, min(int(value or 0), HARD_MAX_PER_DAY))


# --- 언제 보내는가 -----------------------------------------------------------

def within_window(setting: AutoSendSetting, now: datetime) -> bool:
    """지금 내보내도 되는 때인가 — **평일**, 그리고 설정한 시각의 창 안.

    주말 판정은 회차일을 미는 규칙과 **같은 자리**에서 온다
    (`cadence.next_business_day`) — 결과 문의 문자가 그 결을 먼저 냈다.
    토요일 아침에 투자사 카톡방이 울리면 그것만으로 사고다.

    창을 지나쳐도 **잃는 것은 없다.** 결과 문의는 물어보기 전까지 사라지지
    않으므로(`followup_due_now` 는 `물어볼 날 <= 오늘`) 다음 평일 아침에 그대로
    나간다.
    """
    day = now.date()
    if cadence.next_business_day(day) != day:
        return False
    start, end = clamp_hours(setting.from_hour, setting.until_hour)
    return start <= now.hour < end


def window_label(setting: Optional[AutoSendSetting]) -> str:
    """화면에 적는 `평일 10:00~17:00`. 설정이 없으면 기본값으로 적는다."""
    start, end = clamp_hours(
        setting.from_hour if setting else DEFAULT_FROM_HOUR,
        setting.until_hour if setting else DEFAULT_UNTIL_HOUR)
    return f"평일 {start:02d}:00~{end:02d}:00"


# --- 무엇을 보내는가 (미팅 후기) ---------------------------------------------

def _review_targets(db: Session, sender: User) -> List[Target]:
    """이 계정이 지금 물어볼 미팅들. **새로 세지 않는다.**

    무엇이 '오늘 물어볼 미팅' 인지는 `pipeline.today_items` 가 정하고, 화면
    (`/ir` 의 결과 문의)과 결과 문의 문자가 읽는 것도 그것이다. 같은 판단을 두
    군데에 적으면 한쪽이 낡는다 — 이 저장소가 되풀이해 당한 사고다.

    ## 왜 **그 계정의 미팅만** 인가

    고르는 것이 아니라 **구조가 그렇다.** 잡은 그 계정 것으로 서고
    (`create_send_list` 는 `VcContact.user_id == user.id` 인 담당자만 받는다),
    남의 담당 투자사에게 이 사람 카톡으로 "지난번 미팅은…" 이 나가면 받는 쪽에는
    만난 적 없는 사람의 안부다. 사용자가 정한 **`다른 팀원 x`** 도 이것과 같은
    뜻이다 — 다른 팀원의 결과 문의는 지금처럼 문자로 알리고 손으로 보낸다.

    ## 여기서 미리 거르는 것

    `create_send_list` 는 방 이름이 없거나 `검토중단` 인 사람이 섞이면 **목록
    전체를 거절한다**(사람이 화면에서 그 사람을 빼도록). 자동에는 뺄 사람이
    없으므로 여기서 미리 걸러 낸다 — 한 사람 때문에 그날 자동 발송이 통째로
    멈추면, 멈춘 것을 아무도 모른다.

    **거른 건은 자리를 잡지 않는다.** 방 이름을 채워 넣으면 다음 회차에 그대로
    나간다.
    """
    rows = pipeline.today_items(db, sender)["due_followups"]
    if not rows:
        return []

    contacts = {
        c.id: c for c in sheet_owner.investors(db, db.execute(
            select(VcContact).where(
                VcContact.id.in_([r["contact_id"] for r in rows]),
                VcContact.user_id == sender.id)
        ).scalars().all())
    }

    out = []
    for row in rows:
        contact = contacts.get(row["contact_id"])
        if contact is None or sheet_owner.is_paused(contact):
            continue
        if not (contact.kakao_room_name or "").strip():
            continue
        out.append(Target(ref_id=row["id"], contact=contact))
    return out


#: 종류 → 그 종류가 아는 것. **월말 기업 리마인드는 여기 줄 하나로 선다.**
KINDS = {
    KIND_REVIEW: Spec(label="미팅 후기", collect=_review_targets),
}


# --- 하루 한 번 --------------------------------------------------------------

def run_once(db: Session, *, kind: str = KIND_REVIEW,
             now: Optional[datetime] = None) -> dict:
    """지금 내보낼 것이 있으면 발송 목록을 세운다. 실이 깰 때마다 이것을 부른다.

    아무것도 안 하고 돌아오는 길이 여럿이다(꺼짐·시간대 아님·보낼 것 없음·오늘
    상한). **그것이 정상 동작이다** — 왜 안 갔는지는 돌려주는 `skipped` 에 담아
    화면과 검사가 읽는다.

    ## 상한을 **하루**로 잡은 이유

    실은 30분마다 깨어난다. 회당 상한만 두면 하루에 그 열 배가 나간다 — 처음
    켜는 날이 특히 그렇다. 밀려 있던 결과 문의가 쉰 건이면, 회당 10건 상한으로도
    그날 안에 쉰 건이 전부 나간다. 그래서 **그날 자리를 잡은 수**를 세어 상한과
    견준다(`AutoSendRun.day`). 남은 것은 다음 영업일에 이어 나간다.
    """
    now = now or clock.now()
    result = {"kind": kind, "created": 0, "skipped": "", "job_id": None}

    setting = load(db, kind)
    if not is_on(setting):
        # 안 켜면 아무 일도 없다 — 메일·문자와 같다.
        result["skipped"] = "꺼짐"
        return result

    sender = db.get(User, setting.user_id)
    if sender is None or not sender.is_active:
        # 보내기로 한 계정이 정지됐다. 다른 사람 것으로 대신 보내지 않는다 —
        # 누구 카톡에서 나가는지가 이 기능의 알맹이다.
        result["skipped"] = "보내는 계정 없음"
        return result

    if not within_window(setting, now):
        result["skipped"] = "보내는 시간대가 아님"
        return result

    day = now.date().isoformat()
    left = remaining_today(db, kind, day, setting)
    if left <= 0:
        result["skipped"] = "오늘 상한"
        return result

    targets = _unclaimed(db, kind, KINDS[kind].collect(db, sender))
    if not targets:
        result["skipped"] = "보낼 것 없음"
        return result

    picked = targets[:left]
    claims = [c for c in (_claim(db, kind, t, sender, day) for t in picked)
              if c is not None]
    if not claims:
        # 다른 프로세스가 방금 같은 것을 집어갔다. 조용히 물러난다.
        result["skipped"] = "보낼 것 없음"
        return result

    by_ref = {t.ref_id: t for t in picked}
    result["job_id"] = _queue(db, kind, sender,
                              [by_ref[c.ref_id].contact for c in claims], claims)
    result["created"] = len(claims) if result["job_id"] else 0
    return result


def remaining_today(db: Session, kind: str, day: str,
                    setting: AutoSendSetting) -> int:
    """오늘 더 보낼 수 있는 건수. **실패한 줄도 센다.**

    자리를 잡았다는 것은 그 건을 오늘 처리했다는 뜻이다. 실패를 빼고 세면 잡을
    못 만드는 상태에서 실이 깰 때마다 다음 건으로 넘어가, 하루 상한이 아무것도
    막지 못한다.
    """
    used = db.execute(
        select(func.count()).select_from(AutoSendRun)
        .where(AutoSendRun.kind == kind, AutoSendRun.day == day)
    ).scalar_one()
    return clamp_cap(setting.max_per_day) - int(used)


def _unclaimed(db: Session, kind: str, targets: List[Target]) -> List[Target]:
    """이미 나간 건을 뺀다. **날짜를 보지 않는다** — 한 건은 평생 한 번이다."""
    if not targets:
        return []
    done = set(db.execute(
        select(AutoSendRun.ref_id).where(
            AutoSendRun.kind == kind,
            AutoSendRun.ref_id.in_([t.ref_id for t in targets]))
    ).scalars().all())
    return [t for t in targets if t.ref_id not in done]


def _claim(db: Session, kind: str, target: Target, sender: User,
           day: str) -> Optional[AutoSendRun]:
    """이 건의 자리를 잡는다. 이미 잡혀 있으면 `None`.

    **보내기 전에** 넣는다(왜 그런지는 `models.AutoSendRun`). 유일 색인이 있어
    두 프로세스가 동시에 넣으면 하나만 성공하고, 나머지는 `IntegrityError` 로
    조용히 물러난다 — `sms_notices` · `monthly_column_runs` 와 같은 방식이다.
    """
    row = AutoSendRun(kind=kind, ref_id=target.ref_id, user_id=sender.id,
                      day=day, status="claimed")
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return row


def _queue(db: Session, kind: str, sender: User, contacts: List[VcContact],
           claims: List[AutoSendRun]) -> Optional[int]:
    """발송 목록을 세운다 — **발송 화면과 같은 함수를 지난다.**

    ## 왜 여기서 잡을 조립하지 않나

    `create_send_list` 안에 방 이름 확인 · `검토중단` 막이 · **시험방 치환** ·
    문구 스냅숏이 전부 들어 있다. 한 벌 더 적으면 그중 하나가 빠진 채로
    실투자사 카톡방에 나간다 — 예약 큐(`start_queue_item`)가 같은 이유로 그
    함수를 그대로 부른다. 문구도 그 안에서 `MODE_REVIEW` 로 지어져, 발송 화면의
    미팅 후기 탭·`/setup` 의 시험 발송과 **글자 하나까지 같다.**

    라우터 함수를 부르는 것이 낯설 수 있는데, 이 함수는 `Depends` 기본값을 쓰는
    평범한 파이썬 함수라 `db`·`user` 를 그대로 넘기면 된다. 실제로 같은 파일의
    예약 큐가 그렇게 부른다.

    ## 여기서 import 하는 이유

    `routers/deals.py` 가 `services/*` 를 여럿 읽으므로 이 모듈이 그것을 맨
    위에서 읽으면 고리가 생긴다. 부를 때 읽는다 — 이 저장소가 `models` 를
    함수 안에서 읽는 자리들과 같은 방식이다.

    ## 실패하면

    자리를 잡은 줄을 `failed` 로 바꾸고 사유를 남긴다. **다시 시도하지 않는다** —
    자동이 조용히 되풀이하는 것보다, 사람이 팀 현황에서 사유를 보고 손으로 보내는
    편이 안전하다(그 건은 결과 문의 목록에 그대로 남아 있다).
    """
    from fastapi import BackgroundTasks

    from ..routers import deals as deals_view

    try:
        made = deals_view.create_send_list(
            deals_view.SendRequest(
                contact_ids=[c.id for c in contacts],
                mode=deals_view.MODE_REVIEW,
                # 회차 제목은 발송 화면과 같은 것에 **자동이라는 표시**만 더한다.
                # 팀 현황의 `최근 발송 회차` 에서 사람이 보낸 것과 구분돼야,
                # 잘못 나간 것을 보고 어디를 꺼야 하는지 바로 안다.
                title=f"{KINDS[kind].label} (자동)",
            ),
            BackgroundTasks(),
            db=db, user=sender)
    except Exception as exc:  # noqa: BLE001 - 실이 죽으면 조용해진다
        detail = getattr(exc, "detail", None) or str(exc)
        # 반쯤 만들다 만 것을 되돌린다. 자리를 잡은 줄은 이미 커밋돼 있어
        # 함께 사라지지 않는다 — **그래야 두 번 가지 않는다.**
        db.rollback()
        for claim in claims:
            claim.status = "failed"
            claim.error = str(detail)[:500]
        db.commit()
        log.warning("%s 자동 발송 목록을 못 만들었습니다 user=%s 건수=%s: %s",
                    KINDS[kind].label, sender.id, len(claims), detail)
        return None

    for claim in claims:
        claim.status = "queued"
        claim.job_id = made["job_id"]
    db.commit()
    return made["job_id"]


# --- 화면에 보여줄 것 ---------------------------------------------------------

def status(db: Session, kind: str = KIND_REVIEW,
           today: Optional[date] = None) -> dict:
    """켜졌는가 / 누가 보내는가 / 언제 · 몇 건까지 / 오늘 무엇이 나갔는가.

    메일·문자 설정과 **나란히** 팀 현황에 선다. 화면은 판정하지 않고 이 값을
    읽는다 — 같은 판단이 두 곳에 적히면 표에는 켜짐이라고 떠 있는데 아무것도
    안 나가는 상태가 생긴다(이 저장소가 여러 번 겪었다).
    """
    setting = load(db, kind)
    sender = db.get(User, setting.user_id) if setting and setting.user_id else None
    day = (today or clock.today()).isoformat()
    return {
        "kind": kind,
        "label": KINDS[kind].label,
        "on": is_on(setting),
        "enabled": bool(setting and setting.enabled),
        "sender_id": setting.user_id if setting else None,
        "sender": sender.name if sender else "",
        "from_hour": setting.from_hour if setting else DEFAULT_FROM_HOUR,
        "until_hour": setting.until_hour if setting else DEFAULT_UNTIL_HOUR,
        "max_per_day": (clamp_cap(setting.max_per_day) if setting
                        else DEFAULT_MAX_PER_DAY),
        "window": window_label(setting),
        "hours": list(range(EARLIEST_HOUR, LATEST_HOUR + 1)),
        "earliest": EARLIEST_HOUR,
        "latest": LATEST_HOUR,
        "hard_max": HARD_MAX_PER_DAY,
        "today": _today_rows(db, kind, day),
    }


def _today_rows(db: Session, kind: str, day: str) -> List[dict]:
    """오늘 자동으로 나간 것. **실패한 것도 보여 준다.**

    자동이라 아무도 안 보면 잘못 나간 것을 영영 모른다. 잡 번호를 함께 주어
    화면이 `/jobs/{id}` 로 데려간다 — 거기에 누구 방으로 무슨 글자가 갔는지가
    그대로 있다.
    """
    from ..models import Meeting

    rows = db.execute(
        select(AutoSendRun).where(AutoSendRun.kind == kind,
                                  AutoSendRun.day == day)
        .order_by(AutoSendRun.id)
    ).scalars().all()

    names = {}
    if kind == KIND_REVIEW and rows:
        # 누구에게 갔는지 이름으로 보여 준다. 미팅 → 담당자 두 걸음이라
        # 여기서 한 번에 읽는다(줄마다 조회하면 화면 여는 것이 느려진다).
        meetings = db.execute(
            select(Meeting).where(Meeting.id.in_([r.ref_id for r in rows]))
        ).scalars().all()
        contacts = {
            c.id: c for c in db.execute(
                select(VcContact).where(
                    VcContact.id.in_([m.contact_id for m in meetings]))
            ).scalars().all()
        }
        for meeting in meetings:
            contact = contacts.get(meeting.contact_id)
            if contact is not None:
                names[meeting.id] = f"{contact.name}({contact.firm or '-'})"

    return [{"ref_id": row.ref_id, "name": names.get(row.ref_id, f"#{row.ref_id}"),
             "status": row.status, "job_id": row.job_id,
             "error": row.error or "",
             "at": (row.created_at or "")[11:16]}
            for row in rows]


# --- 스케줄러 ---------------------------------------------------------------

def start_scheduler() -> Optional[threading.Thread]:
    """자동 발송 실 하나를 띄운다. 이미 떠 있으면 그대로 둔다.

    **켜져 있는 종류가 하나도 없으면 아예 뜨지 않는다.** 안 켠 사람의 서버에서
    도는 것이 없어야 하고, 검사도 이 실을 띄우지 않는다(설정 줄이 없으므로).

    별도 프로세스·크론이 아니라 웹과 같은 프로세스의 실이다 — 이유는 일일
    백업·결과 문의 문자와 같다. 호스트 크론에 걸어 둔 것은 서버를 다시 세울 때
    같이 사라졌고, 사라진 것을 아무도 몰랐다.

    ## 켠 뒤에는 한 번 다시 세워야 한다

    설정을 켜는 순간 실이 뜨지는 않는다(이 함수는 앱이 뜰 때만 불린다). 팀
    현황이 그 사실을 적어 둔다 — 조용히 안 도는 것이 제일 나쁘다. 배포마다
    컨테이너가 새로 뜨므로 실제로는 다음 배포에 저절로 붙는다.
    """
    global _SCHEDULER

    db = SessionLocal()
    try:
        if not any(is_on(load(db, kind)) for kind in KINDS):
            return None
    except Exception:  # noqa: BLE001
        # 앱을 만드는 시점이라 표가 아직 없을 수 있다(빈 볼륨으로 처음 띄울 때,
        # 검사가 앱을 수십 번 만들었다 버릴 때). **뜨지 않는 쪽으로 넘어간다** —
        # 부팅을 죽이면 화면 전체를 못 연다. 실제 배포는 이주가 끝난 뒤 웹이
        # 뜨므로(`scripts/entrypoint.sh`) 여기서 걸릴 일이 없고, 걸렸다면 그
        # 자체가 로그에 남아야 한다.
        log.warning("자동 발송 설정을 읽지 못해 실을 띄우지 않습니다", exc_info=True)
        return None
    finally:
        db.close()

    if _SCHEDULER is not None and _SCHEDULER.is_alive():
        return _SCHEDULER

    def loop() -> None:
        while True:
            db = SessionLocal()
            try:
                for kind in KINDS:
                    run_once(db, kind=kind)
            except Exception:  # noqa: BLE001 - 실이 죽으면 조용해진다
                log.exception("자동 발송 실이 넘어졌습니다")
            finally:
                db.close()
            time.sleep(CHECK_INTERVAL_SEC)

    _SCHEDULER = threading.Thread(target=loop, name="auto-send", daemon=True)
    _SCHEDULER.start()
    return _SCHEDULER
