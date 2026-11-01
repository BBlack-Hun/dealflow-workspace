"""**결과 문의 알림** — 오늘 결과를 물어볼 미팅이 있는 팀원에게, 그 팀원의 카톡방으로 하루 한 통.

옛 결과 문의 **문자**(`followup_sms`, 솔라피)를 걷고 그 자리에 섰다(사용자 결정
2026-11-01 — 문자 발송 폐지). 뜻은 같다: 미팅을 마치고 결과를 물어볼 때가 됐는데
화면을 안 열면 그대로 지나가니, 담당 팀원에게 알려 주기만 한다.

## 무엇을 — 새로 세지 않는다

오늘 물어볼 미팅은 `pipeline.today_items` 의 `due_followups` 다 — `/ir` 결과 문의
목록 · 대시보드 · 오늘 할 일이 읽는 그 목록이다(A7 이 이미 물은 미팅은 빠진다).
글은 `[결과 문의] 홍길동님(가나벤처스) 외 2건` + 결과 문의 화면 링크(`/ir#meetings`).
맨 앞 이름은 화면 맨 위에 뜨는 그 사람이다(목록 차례 그대로).

## 언제 · 어디로

평일 판의 시각(기본 10:00) 한 번. 받는 방은 팀 현황 › 자동화의 **팀원 카톡방**
(`User.kakao_room_name`) — 계약 Day7 · 후속라운드와 같은 방이다. 방 이름이 비면
보내지 않고 까닭을 남긴다. 시험 모드면 틀이 시험방으로 바꾼다.

## 한 번만

회차는 날마다 하나(`auto_send_runs`), 한 통은 `automation_sends` 의
`user:<계정>:<날>` 하나다 — 같은 날 두 번 안 가고, 다음 날 아직 남아 있으면 또 간다.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import clock, config
from ...models import Automation, AutomationSend, User
from .. import automation, cadence, pipeline
from .. import automation_runner as runner

KEY = automation.FOLLOWUP_NOTICE
#: 결과 문의 목록이 있는 자리(`templates/ir.html` 의 `id="meetings"`).
LINK_PATH = "/ir#meetings"

FIELDS = (
    runner.Field("time", "보낼 시각", "time", "10:00",
                 hint="평일 이 시각에 팀원 카톡방으로 섭니다 — 주말에는 안 보냅니다"),
)


def link_url() -> str:
    """글에 넣을 주소. 서비스 주소(`DEALFLOW_DOMAIN`)가 없으면 빈 글자 — 링크 줄을 뺀다."""
    base = config.base_url()
    return f"{base}{LINK_PATH}" if base else ""


def compose(rows: List[dict], link: str) -> str:
    """`[결과 문의] 홍길동님(가나벤처스) 외 2건` + 링크. 하나면 `외 0건` 을 안 붙인다."""
    head = rows[0]
    name = (head.get("name") or "").strip() or "담당자"
    firm = (head.get("firm") or "").strip()
    more = len(rows) - 1
    text = f"[결과 문의] {name}님" + (f"({firm})" if firm else "") + (f" 외 {more}건" if more > 0 else "")
    return f"{text}\n{link}" if link else text


def due_rows(db: Session, user: User, day: date) -> List[dict]:
    return pipeline.today_items(db, user, day)["due_followups"]


def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    """평일마다 한 번, 판의 시각."""
    if cadence.next_business_day(day) != day:
        return None
    return runner.Plan(period=runner.day_key(day),
                       at=runner.at_on(day, runner.values(row, KEY)["time"]))


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    """오늘 물어볼 미팅이 있는 팀원마다 한 통 — 그 팀원 카톡방으로."""
    day = plan_.at.date()
    link = link_url()
    batch = runner.Batch(note="오늘 결과 문의를 알릴 팀원이 없습니다")
    users = db.execute(select(User).where(User.is_active == 1).order_by(User.id)).scalars()
    for user in users:
        rows = due_rows(db, user, day)
        if not rows:
            continue
        room = (user.kakao_room_name or "").strip()
        if not room:
            batch.skipped.append(f"{user.name} 님 결과 문의 {len(rows)}건 — 카톡방 이름이 "
                                 f"비어 있습니다(팀 현황 › 자동화)")
            continue
        batch.outs.append(automation.Out(room=room, message=compose(rows, link),
                                         ref=f"user:{user.id}:{day.isoformat()}"))
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 결과를 다 적었거나 계정이 꺼졌으면 뺀다."""
    try:
        user = db.get(User, int(rec.ref.split(":")[1]))
    except (IndexError, ValueError):
        return ""
    if user is None or not user.is_active:
        return "계정이 없거나 꺼져 있습니다"
    return "" if due_rows(db, user, clock.today()) else "물어볼 결과 문의가 남아 있지 않습니다"


runner.register(runner.Spec(
    key=KEY, kind="deal_intro", topic=KEY, plan=plan, collect=collect,
    still_ok=still_ok, fields=FIELDS))
