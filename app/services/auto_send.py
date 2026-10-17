"""**옛 결과 문의 대기 목록** — 엔진은 걷었고, 설정 줄을 다루는 손잡이만 남았다.

## 걷은 것 (#31)

여기는 미팅이 끝나고 열흘 뒤가 되면 그 미팅을 한 투자사에게 "그 뒤 어떻게
보셨는지" 를 묻는 **발송 목록**을 `draft` 로 세워 두던 30분 실이었다 — 보내는 것은
그 계정이 진행 화면에서 [발송 시작] 을 누른 뒤였고, 보내는 계정 **자신의**
미팅만 골랐다(`create_send_list` 가 내 명단만 받는다).

같은 일을 2단계 자동화 A7(`services/automations/meeting_review.py`)이 팀원 전원의
미팅에 대해, 이틀 뒤 14:00 에 사람 확인 없이 묻는다. 아침 08시에 회차가 서고
14시 전에 사람이 [중단] 할 수 있어 그 자리가 옛 '발송 준비' 몫을 한다. 둘이
나란히 서 있으면 같은 투자사에 두 번 갈 길이 생겨, 사용자 결정(2026-10-17)으로
결과 문의는 A7 하나다 — 실도 팀 현황 판도 `/team/auto-send` 도 걷었다.

**표와 이력은 남는다.** `auto_send_settings` 의 `meeting_review` 줄(이주 0105 가 그
계정을 팀 공통 자동 발송 계정으로 옮겼다)과 `auto_send_runs` 의 옛 줄 —
A7 은 그 줄로 이미 목록에 섰던 미팅을 다시 묻지 않는다
(`meeting_review._queued_by_old_list`).

## 남은 것

- **설정 줄 손잡이**(`load` · `is_on` · `save` · `clamp_*`) — 스타트업 월간 발송의
  메뉴 설정이 같은 표의 `startup_ir` 줄이라 그대로 쓴다(`services/startup_send.py`).
- **보내는 시간의 폭**(`EARLIEST_HOUR` · `LATEST_HOUR`) — 예약이 이 값을 읽는다
  (`scheduled_send`). 숫자는 `send_window` 한 곳이다.
- **남아 있던 옛 목록**(`waiting_jobs` · `waiting_for`) — 걷는 날 아직 아무도 안 누른
  `미팅 후기 자동` 회차. 예약 시각이 없는 `draft` 라 **저절로 나가지 않는다** —
  오늘 할 일에 서서 사람이 [발송 시작] 하거나 [취소] 한다(사용자 결정 8).
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AutoSendRun, AutoSendSetting, User
from . import send_window

#: 미팅 후기 — 옛 대기 목록이 `auto_send_runs.kind` · 설정 줄에 쓰던 글자. A7 이
#: 이 글자로 옛 목록에 섰던 미팅을 알아본다(`meeting_review._queued_by_old_list`).
KIND_REVIEW = "meeting_review"

#: `auto_send_runs.status` — **한 건이 어디까지 갔나.**
#:   claimed : 자리를 잡았다(목록을 세우기 전에 먼저 남긴다)
#:   ready   : 대기 목록에 섰다. **아직 안 나갔다** — 그 계정이 [발송 시작] 을
#:             누르면 그때 나가고, 어디까지 갔는지는 회차 화면이 말한다
#:   failed  : 목록을 못 세웠다(사유는 같은 줄의 `error`)
#:
#: 보냈다고 적지 않는다. 이 표는 **두 번 세우지 않으려고** 있는 것이고, 실제로
#: 나갔는지는 `send_items` 가 안다 — 여기에 `sent` 를 두면 발송기가 꺼져 있어
#: 한 통도 안 나간 회차를 화면이 `보냄` 이라고 말한다(`deal_queue` 가 같은
#: 이유로 `시작함` 이라고만 적는다).
STATUS_CLAIMED = "claimed"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

#: **고를 수 있는 시각의 폭.** 설정이 아무 시각이나 담지 못하게 코드가 먼저
#: 좁힌다 — 받는 쪽이 팀원이 아니라 **투자사**다. 새벽 3시에 카톡이 가면
#: 그것만으로 관계가 상한다.
#:
#: 결과 문의 **문자**는 09~20시다(`followup_sms`). 그쪽은 받는 사람이 우리
#: 팀원이라 아침 일찍·저녁 늦게도 괜찮지만, 여기는 양쪽을 한 시간씩 좁혔다:
#: 9시는 출근 직후라 아직 자리에 앉기 전이고, 19시 이후는 퇴근한 사람의 폰이다.
#:
#: 숫자는 `send_window` 한 곳에 있다. **판정은 이 상수가 아니라
#: `send_window.hours()` 를 읽는다** — 테스트 서버에서 그 폭을 끄는 스위치가
#: 있어서다(`DEALFLOW_TEST_SERVER_NO_SEND_WINDOW`). 상수는 운영의 폭을 적어 둔 것이다.
EARLIEST_HOUR = send_window.EARLIEST_HOUR
LATEST_HOUR = send_window.LATEST_HOUR

#: 설정을 처음 켤 때의 값. 오전 10시~오후 5시는 어느 회사든 자리에 있는 시간이다.
DEFAULT_FROM_HOUR = 10
DEFAULT_UNTIL_HOUR = 17

#: **하루에 몇 건까지.** 기본 10건, 최대 60건.
#:
#: 60 은 지어낸 수가 아니라 이 도구가 처음부터 지켜 온 **1회 발송 상한**이다
#: (`docs/TECH_SPEC.md` §5.5 · 발송기 쪽에도 같은 상한이 있다 — 1잡 60건).
#: 목록을 세우는 쪽이 그보다 크게 만들면, 사람이 눌러도 발송기가 앞의 60건만
#: 처리하고 나머지는 대기로 남는다.
DEFAULT_MAX_PER_DAY = 10
HARD_MAX_PER_DAY = 60

# --- 설정 -------------------------------------------------------------------

def load(db: Session, kind: str = KIND_REVIEW) -> Optional[AutoSendSetting]:
    """이 종류의 설정. **없으면 `None` — 그것이 꺼짐이다.**"""
    return db.execute(
        select(AutoSendSetting).where(AutoSendSetting.kind == kind)
    ).scalars().first()


def is_on(setting: Optional[AutoSendSetting]) -> bool:
    """켜져 있는가. **보내는 계정이 없으면 켜진 것이 아니다** — 보낼 사람이
    없으면 목록을 세울 수 없고, 반쯤 켜진 상태를 만들면 화면이 `켜짐` 이라고
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
    low, high = send_window.hours()
    start = max(low, min(int(from_hour or 0), high - 1))
    end = max(start + 1, min(int(until_hour or 0), high))
    return start, end


def clamp_cap(value: int) -> int:
    """하루 상한. 1 미만은 1, 문서가 정한 60 을 넘지 못한다."""
    return max(1, min(int(value or 0), HARD_MAX_PER_DAY))


# --- 남아 있던 옛 목록 -------------------------------------------------------

def waiting_jobs(db: Session, *, user_id: Optional[int] = None) -> List[dict]:
    """걷는 날 남아 있던 옛 `미팅 후기 자동` 회차 중 **아직 아무도 안 누른 것**.

    예약 시각 없이 `draft` 로 섰던 회차라 발송기도 예약을 푸는 실도 집어가지 않는다
    — 그대로 두면 서 있는 줄 모른 채 잊힌다. 그래서 오늘 할 일에 세운다
    (`services/today.py`). 누르거나 [취소] 하면 `draft` 가 아니게 되어 사라진다.

    **회차 단위로 묶는다.** 회차 하나에 여러 건이 담기므로 건마다 세면 화면이
    같은 회차를 몇 번씩 말한다. 몇 명인지는 회차가 안다(`send_jobs.total`).

    옛 엔진의 줄(`kind = meeting_review`)만 본다 — 같은 표에 2단계 자동화의 회차
    자리(`auto:…`)도 서는데, 그쪽은 예약으로 서서 예약 줄이 따로 말한다.
    """
    from ..models import SendJob

    job_ids = set(db.execute(
        select(AutoSendRun.job_id).where(AutoSendRun.kind == KIND_REVIEW,
                                         AutoSendRun.status == STATUS_READY,
                                         AutoSendRun.job_id.isnot(None))
    ).scalars().all())
    if not job_ids:
        return []
    query = select(SendJob).where(SendJob.id.in_(job_ids), SendJob.status == "draft")
    if user_id is not None:
        query = query.where(SendJob.user_id == user_id)
    return [{"job_id": job.id, "count": job.total, "user_id": job.user_id}
            for job in db.execute(query.order_by(SendJob.id)).scalars().all()]


def waiting_for(db: Session, user: User) -> List[dict]:
    """오늘 할 일에 세울 옛 목록 — 주인은 제 것, 관리자는 팀 전체.

    누르고 취소하는 것은 **주인만** 된다(`routers/jobs._job_or_404`). 관리자에게는
    걷는 날 누구 계정에 무엇이 남았는지 보이게만 한다(회차 화면은 관리자도 연다).
    """
    return waiting_jobs(db, user_id=None if user.role == "admin" else user.id)
