"""미팅 결과를 물어볼 때가 되면 **담당 팀원에게 문자로** 알린다.

## 왜 문자인가

화면은 열어야 보인다. 결과 문의는 화면을 안 연 날 그대로 지나가는데, 그 열흘은
`pipeline` 이 대신 세어 주고 있으니 **알려 주기만 하면 되는 일**이다.

카톡은 각자 PC 의 발송 프로그램이 켜져 있어야 나가서 아침에 저절로 보낼 수
없다. 문자는 메일처럼 **서버가 바로** 보낸다. 그래서 문자다.

**받는 사람은 우리 팀원뿐이다.** 투자사에게 이 길로 보내지 않는다 — 번호를
`users.phone` 밖에서 받지 않는 것으로 그 선을 지킨다(`recipients`), 그리고
보내기 직전에 한 번 더 확인한다(`assert_team_phone`).

## 무엇을 보고 판단하나

**새로 세지 않는다.** 오늘 물어볼 미팅은 `pipeline.today_items` 의
`due_followups` 가 이미 뽑아 둔 것이고, 화면(`/ir`)이 보여 주는 것도 그것이다.
같은 판단을 두 군데에 적으면 한쪽이 낡는다 — 이 저장소가 되풀이해 당한 사고다.

## 언제 보내나

`services/backup.py` 의 일일 백업과 **같은 방식**이다. 이미지 안 데몬 실이
30분마다 깨어나 "오늘 것이 나갔나" 만 보고, 안 나갔으면 보낸다. 정해진 시각에
거는 방식은 그 시각에 컨테이너가 안 떠 있으면 그날을 조용히 건너뛴다 —
배포·재부팅이 겹치면 그렇게 된다.

다만 백업과 다른 것이 둘 있다.

- **울리는 시각을 가린다**(`SEND_FROM_HOUR`~`SEND_UNTIL_HOUR`). 백업은 새벽 3시에
  떠도 아무도 모르지만 문자는 그 시각에 폰을 울린다.
- **주말에는 안 보낸다.** 결과 문의는 평일에 하는 일이라 토요일 알림은 할 수
  없는 일을 알리는 것이다. 주말 사이에 사라지지도 않는다 — `followup_due_now`
  는 `물어볼 날 <= 오늘` 이라 월요일 아침에 그대로 있다.

## 같은 건으로 두 번 보내지 않기

30분마다 깨어나므로 그냥 보내면 **하루에 스무 통이 간다.** 그래서 보냈다는
사실을 `sms_notices` 에 남기고 `(kind, day, user_id)` 유일 색인으로 그날 자리를
하나만 잡는다. 자세한 것은 그 표의 설명(`models.SmsNotice`)에 있다. 핵심은
**보내기 전에 줄을 넣는다**는 것 — 성공한 뒤에 남기면 업체가 받아 놓고 응답만
실패했을 때 30분 뒤에 또 보낸다.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock, config
from ..db import SessionLocal
from ..models import SmsNotice, User
from . import cadence, pipeline, sms

log = logging.getLogger(__name__)

#: `sms_notices.kind`. 알림 종류가 늘면 여기 옆에 하나 더 선다.
KIND = "meeting_followup"

#: 문자가 데려갈 화면. 결과 문의 목록이 있는 그 자리다(`templates/ir.html` 의
#: `id="meetings"` — 대시보드의 `결과 문의` 도 같은 곳으로 간다). 앵커까지
#: 붙이는 이유는 폰에서 열면 위쪽 IR 요청 목록이 먼저 나와서, 스크롤을 내려야
#: 문자가 말한 그 목록이 보이기 때문이다.
LINK_PATH = "/ir#meetings"

#: 몇 시부터 몇 시까지 보내는가. 아침에 붙어야 그날 안에 전화를 돌린다.
#: 저녁 8시를 넘기면 그날은 보내지 않는다 — 밤에 울려서 얻는 것이 없고,
#: 다음 날 아침에 그대로 간다(결과 문의는 물어보기 전까지 사라지지 않는다).
SEND_FROM_HOUR = 9
SEND_UNTIL_HOUR = 20

#: 얼마나 자주 깨어나 볼 것인가. 일일 백업과 같은 30분이다 — 아침 9시에서
#: 최대 30분 늦게 간다는 뜻이고, 아침 알림에는 그 정도면 된다.
CHECK_INTERVAL_SEC = 30 * 60

#: 알림 실은 프로세스당 하나. `create_app()` 이 여러 번 불려도(검사) 겹쳐
#: 뜨지 않게 한다.
_SCHEDULER: Optional[threading.Thread] = None


class NotTeamPhone(RuntimeError):
    """팀원 번호가 아니다. **이 길로는 투자사에게 갈 수 없다.**"""


# --- 어디로 데려갈 것인가 ----------------------------------------------------

def link_url() -> str:
    """문자에 넣을 주소. 서비스 주소가 없으면 빈 문자열.

    주소는 `DEALFLOW_DOMAIN` 하나에서 온다(`config.base_url`) — Caddy 가
    인증서를 받는 그 이름이다. 코드에 박으면 도메인을 옮기는 날 문자에 적힌
    주소만 옛것으로 남는다.
    """
    base = config.base_url()
    return f"{base}{LINK_PATH}" if base else ""


# --- 문구 -------------------------------------------------------------------

def compose(rows: List[dict], link: str) -> str:
    """`[결과 문의] 홍길동님(가나벤처스) 외 2건` + 링크.

    **짧게 쓴다.** 단문 90바이트(한글 45자)를 넘으면 장문으로 넘어가 값이 뛴다.
    링크만 40바이트 안팎이라 남는 자리가 많지 않아서, 넘칠 때 버릴 순서를
    정해 둔다: 회사명 → 이름. 링크와 건수는 끝까지 남는다 — 그 둘이 없으면
    문자를 받고도 무엇을 해야 하는지 알 수 없다.

    맨 앞 이름은 **화면 맨 위에 뜨는 그 사람**이다(`due_followups` 순서 그대로).
    문자를 보고 화면을 열었을 때 같은 이름이 먼저 보여야 헷갈리지 않는다.

    건수가 하나면 `외 0건` 을 붙이지 않는다.
    """
    if not rows:
        return ""
    head = rows[0]
    name = (head.get("name") or "").strip() or "담당자"
    firm = (head.get("firm") or "").strip()
    more = len(rows) - 1
    tail = f" 외 {more}건" if more > 0 else ""

    full = _line(f"{name}님({firm}){tail}" if firm else f"{name}님{tail}", link)
    if sms.byte_len(full) <= sms.SMS_MAX_BYTES:
        return full
    # 회사명을 버린다 — 이름이 있으면 누구인지는 안다.
    without_firm = _line(f"{name}님{tail}", link)
    if sms.byte_len(without_firm) <= sms.SMS_MAX_BYTES:
        return without_firm
    # 이름까지 버린다. 여기까지 오면 이름이 아주 길거나 주소가 아주 긴 것이다.
    return _line(f"미팅 {len(rows)}건", link)


def _line(body: str, link: str) -> str:
    return f"[결과 문의] {body}\n{link}"


# --- 누구에게 -----------------------------------------------------------------

def team_phones(db: Session) -> set:
    """지금 문자를 받을 수 있는 **팀원 번호 전부**(숫자만).

    이 앱은 로그인 ID 가 곧 휴대폰번호라 `users.phone` 이 그대로 번호다.
    쉬는 계정(`is_active=0`)은 뺀다 — 나간 사람에게 계속 보내지 않는다.
    """
    rows = db.execute(select(User.phone).where(User.is_active == 1)).scalars().all()
    return {p for p in (sms.digits(raw) for raw in rows) if p}


def assert_team_phone(db: Session, phone: str) -> str:
    """**투자사에게 갈 길을 막는 마지막 문**.

    번호는 `recipients` 가 `users.phone` 에서만 꺼내므로 여기까지 남의 번호가
    올 일이 없다. 그래도 한 번 더 본다 — 이 길이 실수로 투자사에게 열리는 것이
    이 기능에서 제일 나쁜 사고이고, 나중에 다른 곳에서 이 함수를 부를 때
    (예: 관리자 화면의 시험 발송) 그 자리에서 다시 판단하지 않아도 되게 한다.
    """
    number = sms.digits(phone)
    if not number or number not in team_phones(db):
        raise NotTeamPhone(
            "팀원 번호가 아닙니다 — 이 알림은 팀원에게만 갑니다")
    return number


def recipients(db: Session) -> List[Tuple[User, List[dict]]]:
    """오늘 알릴 사람과 그 사람의 결과 문의 목록.

    **조건을 다시 적지 않는다.** 무엇이 '오늘 물어볼 미팅' 인지는
    `pipeline.today_items` 가 정하고, 화면도 같은 값을 읽는다.

    번호가 없는 팀원은 건너뛴다. 계정은 있는데 `phone` 이 비어 있는 경우가
    있다(관리자가 이름만 먼저 만들어 둔 계정). 보낼 곳이 없는 것은 고장이
    아니므로 조용히 넘어가되, 팀 현황 화면이 그 수를 보여 준다.
    """
    users = db.execute(
        select(User).where(User.is_active == 1).order_by(User.id)
    ).scalars().all()

    out = []
    for user in users:
        rows = pipeline.today_items(db, user)["due_followups"]
        if rows:
            out.append((user, rows))
    return out


# --- 하루 한 번 --------------------------------------------------------------

def within_window(now: datetime) -> bool:
    """지금 보내도 되는 때인가 — 평일 09~20시.

    주말과 밤을 여기 한 곳에서 가린다. 주말 판정은 회차일을 미는 규칙과
    **같은 자리**에서 온다(`cadence.next_business_day`).
    """
    day = now.date()
    if cadence.next_business_day(day) != day:
        return False
    return SEND_FROM_HOUR <= now.hour < SEND_UNTIL_HOUR


def run_once(db: Session, *, now: Optional[datetime] = None) -> dict:
    """지금 보낼 것이 있으면 보낸다. 실이 깰 때마다 이것을 부른다.

    아무것도 안 하고 돌아오는 길이 여럿이다(설정 없음·시간대 아님·보낼 것
    없음·오늘 이미 보냄). **그것이 정상 동작이다** — 왜 안 갔는지는 돌려주는
    `skipped` 에 담아 두어 화면과 검사가 읽는다.
    """
    now = now or clock.now()
    result = {"sent": 0, "failed": 0, "skipped": ""}

    if not sms.is_configured() or not link_url():
        # 설정이 없으면 **조용히 아무것도 하지 않는다**(메일과 같다).
        result["skipped"] = "설정 없음"
        return result
    if not within_window(now):
        result["skipped"] = "보내는 시간대가 아님"
        return result

    day = now.date().isoformat()
    settings = sms.load_settings()
    for user, rows in recipients(db):
        outcome = _notify(db, user, rows, day, settings)
        if outcome == "sent":
            result["sent"] += 1
        elif outcome == "failed":
            result["failed"] += 1
    return result


def _notify(db: Session, user: User, rows: List[dict], day: str,
            settings: sms.SmsSettings) -> str:
    """한 사람에게 한 통. 돌려주는 값: sent | failed | skipped."""
    phone = sms.digits(user.phone)
    if not phone:
        return "skipped"          # 번호가 없는 팀원 — 고장이 아니다

    notice = _claim(db, user.id, day, len(rows))
    if notice is None:
        return "skipped"          # 오늘 것은 이미 나갔다

    try:
        assert_team_phone(db, phone)
        sms.send(phone, compose(rows, link_url()), settings=settings)
    except Exception as exc:      # noqa: BLE001 - 한 사람 실패가 나머지를 막지 않는다
        notice.status = "failed"
        notice.error = sms.redact(str(exc))[:500]
        db.commit()
        # 번호도 문구도 로그에 남기지 않는다 — 누구에게(계정 번호가 아닌 id)
        # 몇 건을 보내려다 실패했는지만 남긴다.
        log.warning("결과 문의 문자 실패 user=%s 건수=%s: %s",
                    user.id, len(rows), notice.error)
        return "failed"

    notice.status = "sent"
    notice.sent_at = clock.now_iso()
    notice.error = None
    db.commit()
    return "sent"


def _claim(db: Session, user_id: int, day: str, count: int) -> Optional[SmsNotice]:
    """오늘 이 사람 자리를 잡는다. 이미 잡혀 있으면 `None`.

    **보내기 전에** 넣는다(왜 그런지는 `models.SmsNotice`). 유일 색인이 있어
    두 프로세스가 동시에 넣으면 하나만 성공하고, 나머지는 `IntegrityError` 로
    조용히 물러난다 — `monthly_column_runs` 가 쓰는 방식과 같다.
    """
    exists = db.execute(
        select(SmsNotice).where(SmsNotice.kind == KIND,
                                SmsNotice.day == day,
                                SmsNotice.user_id == user_id)
    ).scalars().first()
    if exists is not None:
        return None

    notice = SmsNotice(kind=KIND, day=day, user_id=user_id, count=count,
                       status="sending")
    db.add(notice)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return notice


# --- 화면에 보여줄 것 ---------------------------------------------------------

def status(db: Optional[Session] = None,
           today: Optional[date] = None) -> dict:
    """켜졌는가 / 무엇이 없는가 / 오늘 어떻게 됐는가.

    메일 설정과 **나란히** 팀 현황에 선다. 비밀값은 있음/없음만 나간다
    (`sms.status`).
    """
    out = dict(sms.status())
    link = link_url()
    missing = list(out["missing"])
    if not link:
        # 링크 없는 문자는 화면으로 갈 길이 없다. 켜진 것으로 치지 않는다.
        missing.append("서비스 주소(DEALFLOW_DOMAIN)")
    out["missing"] = missing
    out["link"] = link
    out["configured"] = out["configured"] and bool(link)
    out["window"] = f"평일 {SEND_FROM_HOUR:02d}:00~{SEND_UNTIL_HOUR:02d}:00"
    out["today"] = _today_rows(db, today) if db is not None else []
    return out


def _today_rows(db: Session, today: Optional[date]) -> List[dict]:
    """오늘 나간 알림. **실패한 것을 사람이 볼 수 있어야 한다.**"""
    day = (today or clock.today()).isoformat()
    rows = db.execute(
        select(SmsNotice, User)
        .join(User, User.id == SmsNotice.user_id)
        .where(SmsNotice.kind == KIND, SmsNotice.day == day)
        .order_by(SmsNotice.id)
    ).all()
    return [{"name": user.name, "count": notice.count,
             "status": notice.status, "error": notice.error or "",
             "sent_at": (notice.sent_at or "")[11:16]}
            for notice, user in rows]


# --- 스케줄러 ---------------------------------------------------------------

def start_scheduler() -> Optional[threading.Thread]:
    """알림 실 하나를 띄운다. 이미 떠 있으면 그대로 둔다.

    **설정이 없으면 아예 뜨지 않는다.** 안 켠 사람에게는 아무 일도 일어나지
    않아야 하고, 검사도 이 실을 띄우지 않는다(설정을 비워 두므로).

    별도 프로세스·크론이 아니라 웹과 같은 프로세스의 실이다 — 이유는 일일
    백업과 같다(`services/backup.py` 머리말). 호스트 크론에 걸어 둔 것은
    서버를 다시 세울 때 같이 사라졌고, 사라진 것을 아무도 몰랐다.
    """
    global _SCHEDULER

    if not sms.is_configured() or not link_url():
        return None
    if _SCHEDULER is not None and _SCHEDULER.is_alive():
        return _SCHEDULER

    def loop() -> None:
        while True:
            db = SessionLocal()
            try:
                run_once(db)
            except Exception:  # noqa: BLE001 - 알림 실이 죽으면 조용해진다
                log.exception("결과 문의 문자 실이 넘어졌습니다")
            finally:
                db.close()
            time.sleep(CHECK_INTERVAL_SEC)

    _SCHEDULER = threading.Thread(target=loop, name="followup-sms", daemon=True)
    _SCHEDULER.start()
    return _SCHEDULER
