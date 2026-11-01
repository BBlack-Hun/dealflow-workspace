"""#112 **다가오는 미팅·후속라운드 미리 알림** — 날짜 앞에 담당 팀원 카톡방으로 네 번.

원 요청(11/01): "리마인드해야 할 카톡 … 10일 전부터 3일 간격으로". 사용자 결정(11/01):
받는 사람은 이번엔 **팀원만**(스타트업 · 투자사에 앱이 직접 보내는 것은 나중에 정한다).

## 무엇을 — 두 날짜

  · 딜 진행 관리의 **예정 미팅**(`Meeting.status == "scheduled"`)의 미팅 날짜 —
    담당은 미팅 주인(`Meeting.user_id`).
  · 매출예상리스트 `후속라운드 시작 년월`(`RevenueForecast.follow_round_month` — 0128)
    — 년월뿐이라 **그달 1일**을 날짜로 본다. 담당은 줄을 만든 팀원(`user_id`).
    전에는 `follow_round` 가 1일 · 15일 · 1일로 알렸는데 이 방식으로 바꿨다(사용자 결정
    11/01). Series A 이상 딜 소싱 쪽은 `follow_round` 에 그대로 남았다.

## 언제 — D-10 · D-7 · D-4 · D-1

판의 시각(기본 10:00). 그날이 토·일이면 **앞 금요일**이다(공휴일 표는 앱에 없어 주말만).
**바로 그날**만 줍는다 — 늦게 등록된 건은 남은 회차만 나가고, 지난 회차를 한꺼번에 몰아
보내지 않는다. 날짜가 바뀌면(미팅을 옮기면) 바뀐 날짜로 다시 센다.

## 누구에게 · 어떻게 — 팀원마다 하루 한 통

그날 걸린 건을 **팀원마다 한 통으로 묶는다**. 건마다 따로 보내면 같은 방 하루 1통
(`automation_dedup`)에 걸려 둘째부터 빠진다. 받는 방은 팀 현황 › 자동화의 **팀원 카톡방**
(`User.kakao_room_name`) — 계약 Day7 · 후속라운드 · 결과 문의와 같은 방이고, 자동 발송
계정 PC 에서 나간다. 방 이름이 비면 보내지 않고 까닭을 남긴다. 시험 모드면 틀이 시험방으로.

글은 문구 화면 `remind_ahead`(보내는 계정이 고른 것), 비어 있으면 `TEXT`. `{목록}` 자리에
`11/12(목) 미팅 — 가나바이오 × 다라벤처스 (D-4)` 가 한 줄씩 들어간다. 괄호 안은 **그날부터
남은 날수**다(금요일로 당긴 D-1 은 D-3 으로 적힌다 — 날짜와 어긋나지 않게).

## 한 번만

회차는 날마다 하나(`auto_send_runs`), 한 통은 `automation_sends` 의 `user:<계정>:<날>`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import clock
from ...models import (Automation, AutomationSend, IrCompany, Meeting, RevenueForecast,
                       User, VcContact)
from .. import automation, cadence, forecast, template_pick
from .. import automation_runner as runner
from ..weekly import WEEKDAYS

KEY = automation.REMIND_AHEAD
#: 며칠 전에 알리나.
DAYS = (10, 7, 4, 1)
#: 문구 화면의 종류(`routers/templates_crud.KINDS`).
TEMPLATE_KIND = "remind_ahead"
LIST_TOKEN = "{목록}"
#: 샘플 — 문구 화면에서 고치면 그것이 나간다.
TEXT = "[미리 알림]\n" + LIST_TOKEN

FIELDS = (
    runner.Field("time", "보낼 시각", "time", "10:00",
                 hint="미팅 날짜 · 후속라운드 시작(그달 1일) 10·7·4·1일 전 이 시각에 담당 팀원 "
                      "카톡방으로 섭니다 — 토·일이면 앞 금요일"),
)


def send_day(when: date, n: int) -> date:
    """`when` 의 n일 전 — 토·일이면 앞 금요일."""
    day = when - timedelta(days=n)
    while day.weekday() >= 5:          # 5=토 6=일
        day -= timedelta(days=1)
    return day


# ── 무엇을 ──────────────────────────────────────────────────────────────────

@dataclass
class Target:
    when: date
    #: `11/12(목) 미팅 — 가나바이오 × 다라벤처스` — 글 한 줄 · 까닭 줄의 앞머리.
    what: str
    owner: Optional[User]
    owner_why: str


def _owner(db: Session, user_id: Optional[int], where: str) -> Tuple[Optional[User], str]:
    user = db.get(User, user_id) if user_id else None
    if user is not None and user.is_active:
        return user, ""
    return None, f"{where} 담당 계정이 없거나 꺼져 있습니다"


def targets(db: Session, after: date) -> List[Target]:
    """`after` 보다 뒤 날짜의 예정 미팅 · 매출예상리스트 후속라운드 — 날짜 차례."""
    out = []
    for m in db.execute(select(Meeting).where(
            Meeting.status == "scheduled", Meeting.scheduled_at > after.isoformat())
            .order_by(Meeting.id)).scalars():
        try:
            when = date.fromisoformat((m.scheduled_at or "")[:10])
        except ValueError:
            continue
        if when <= after:
            continue
        contact = db.get(VcContact, m.contact_id)
        firm = ((contact.firm or "").strip() or (contact.name or "").strip()) if contact else ""
        names = " × ".join(x for x in ((m.company_name or "").strip(), firm) if x)
        out.append(Target(when, f"{when.month}/{when.day}({WEEKDAYS[when.weekday()]}) 미팅 — "
                          f"{names or '(이름 없음)'}",
                          *_owner(db, m.user_id, "미팅")))
    for row in db.execute(select(RevenueForecast).where(
            RevenueForecast.follow_round_month.isnot(None)).order_by(RevenueForecast.id)).scalars():
        month = forecast.month(row.follow_round_month or "")
        when = date(int(month[:4]), int(month[5:7]), 1) if month else None
        if when is None or when <= after:
            continue
        name = (row.company_name or "").strip()
        if not name and row.ir_company_id:
            company = db.get(IrCompany, row.ir_company_id)
            name = company.name if company else ""
        out.append(Target(when, f"{when.month}월 후속라운드 시작 — {name or '(기업명 없음)'}",
                          *_owner(db, row.user_id, "매출예상리스트 줄의")))
    return sorted(out, key=lambda t: t.when)


def due_on(db: Session, day: date) -> List[Target]:
    """그날 알릴 건 — D-10·7·4·1 중 하나가 **바로 그날**인 것. 지난 회차는 건너뛴다."""
    return [t for t in targets(db, day) if any(send_day(t.when, n) == day for n in DAYS)]


def compose(db: Session, sender: Optional[User], lines: List[str]) -> str:
    """문구 화면의 글(보내는 계정이 고른 것), 없으면 샘플. `{목록}` 이 없으면 글 끝에."""
    found = template_pick.pick(db, sender.id, TEMPLATE_KIND) if sender is not None else None
    body = ((found.body if found else "") or "").strip() or TEXT
    listing = "\n".join(lines)
    return body.replace(LIST_TOKEN, listing) if LIST_TOKEN in body else f"{body}\n{listing}"


# ── 틀에 다는 것 ─────────────────────────────────────────────────────────────

def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    """평일마다 한 번, 판의 시각."""
    if cadence.next_business_day(day) != day:
        return None
    return runner.Plan(period=runner.day_key(day),
                       at=runner.at_on(day, runner.values(row, KEY)["time"]))


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    """그날 걸린 건을 팀원마다 한 통으로 — 그 팀원 카톡방으로."""
    day = plan_.at.date()
    batch = runner.Batch(note="오늘 미리 알릴 미팅 · 후속라운드가 없습니다")
    by_user: Dict[int, Tuple[User, List[str]]] = {}
    for t in due_on(db, day):
        if t.owner is None:
            batch.skipped.append(f"{t.what} — {t.owner_why}")
            continue
        by_user.setdefault(t.owner.id, (t.owner, []))[1].append(
            f"{t.what} (D-{(t.when - day).days})")
    for user, lines in by_user.values():
        room = (user.kakao_room_name or "").strip()
        if not room:
            batch.skipped.append(f"{user.name} 님 미리 알림 {len(lines)}건 — 카톡방 이름이 "
                                 f"비어 있습니다(팀 현황 › 자동화)")
            continue
        batch.outs.append(automation.Out(room=room, message=compose(db, sender, lines),
                                         ref=f"user:{user.id}:{day.isoformat()}"))
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 알릴 건이 다 없어졌거나(취소 · 날짜 바뀜) 계정이 꺼졌으면 뺀다."""
    try:
        _head, user_id, day = rec.ref.split(":")
        user, day = db.get(User, int(user_id)), date.fromisoformat(day)
    except ValueError:
        return ""
    if user is None or not user.is_active:
        return "계정이 없거나 꺼져 있습니다"
    if any(t.owner is not None and t.owner.id == user.id for t in due_on(db, day)):
        return ""
    return "알릴 미팅 · 후속라운드가 남아 있지 않습니다"


def describe(db: Session, row: Optional[Automation]) -> str:
    """판 상태 칸의 한 줄 — 미리 알림 기다리는 건과 **건너뛰는 까닭**."""
    waiting = targets(db, clock.today())
    if not waiting:
        return ""
    problems = [f"{t.what} — {t.owner_why}" for t in waiting if t.owner is None]
    problems += [f"{t.owner.name} 님 카톡방 이름 없음 — 카톡 건너뜀" for t in waiting
                 if t.owner is not None and not (t.owner.kakao_room_name or "").strip()]
    problems = list(dict.fromkeys(problems))
    text = f"미리 알림 기다리는 건 {len(waiting)}"
    if problems:
        text += " · 건너뛰는 까닭: " + "; ".join(problems[:5])
    return text


runner.register(runner.Spec(
    key=KEY, kind="deal_intro", topic=KEY, plan=plan, collect=collect,
    still_ok=still_ok, describe=describe, fields=FIELDS))
