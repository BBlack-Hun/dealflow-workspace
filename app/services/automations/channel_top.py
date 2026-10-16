"""A3 · **채널방 TOP·핵심 딜** — 매주 수요일 13:30, 오픈채팅방마다 같은 3곳.

자동화 판에 적어 둔 **오픈채팅방 제목들**(보내는 계정 카톡 기준, 10곳 안팎)에
매주 기본 **수요일 13:30** 부터 TOP·핵심 딜 3곳을 소개한다. 받는 줄(담당자)이
없는 방이라 방 이름 목록이 곧 대상이다.

## 어느 기업을

IR 기업 현황에서 **TOP·핵심**(`is_top_deal`)인 기업 중

  · `딜소개 불가` 는 뺀다(발송 화면이 아예 안 보여 주는 기업 — `pages.deals_page`).
  · 문구를 만들 수 없는 기업(`introducible` 아님)은 뺀다 — 빈 소개가 채널에
    나가면 안 된다.
  · **90일 안에 채널로 나간 기업은 뺀다.**
  · 차례: 채널로 **한 번도 안 나간 기업** 먼저(수신일 최신순), 그다음 **마지막
    채널 발송이 오래된** 기업.

3곳이 안 되면 있는 만큼(1곳도 보낸다). 0곳이면 그 주는 건너뛰고 오늘 할 일에
그 사유가 선다(공통 틀의 `0건`).

## 방마다

그 주에는 **모든 방에 같은 기업**이 간다. 다만

  · 방마다 회차를 따로 세워 **2~5분씩 띄운다**(공통 틀의 `spacing`) — 여러 방에
    같은 글이 한꺼번에 몰리면 스팸으로 읽힌다.
  · 첫 줄 · 안내 줄 · 맺음 줄을 방마다 조금씩 바꾼다(`HEADERS` · `INTROS` ·
    `FOOTERS`). 기업 소개 덩어리는 딜 소개와 **같은 모양**이다
    (`message_composer.compose_message` — `[기업1] 한 줄 소개 …`).

## 채널 발송 기록

기업마다 `automation_sends` 줄(`company_id`)이 남고, 그 건이 실제로 `sent` 인
것만 기록으로 센다(`last_sent`). 시험 모드의 기록은 시험 모드에서만 센다 —
시험을 여러 번 돌리면 차례가 실제처럼 돌아간다.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Automation, AutomationSend, IrCompany, SendItem, User
from .. import automation
from .. import automation_runner as runner
from .. import message_composer as mc

#: 방마다 돌려 쓰는 첫 줄 · 안내 줄 · 맺음 줄. `{개수}` 는 기업 수.
HEADERS = [
    "이번 주 TOP · 핵심 딜 소개드립니다.",
    "이번 주 주목할 TOP · 핵심 딜 공유드립니다.",
    "금주 TOP · 핵심 딜 간단히 소개드립니다.",
]
INTROS = [
    "핵심 딜 {개수}개사 간단히 공유드립니다.",
    "{개수}개사 요약 공유드립니다.",
    "핵심 딜 {개수}개사 요약입니다.",
]
FOOTERS = [
    "관심 가시는 기업 있으시면 편하게 말씀 부탁드립니다. IR Deck 공유드리겠습니다.",
    "검토 원하시는 기업은 말씀 주시면 IR Deck 전달드리겠습니다.",
    "관심 있으신 기업은 연락 주시면 자료 바로 공유드리겠습니다.",
]

#: 요일 한 글자 → 0(월)~6(일). 읽는 자리는 공통 틀 하나다(`runner.parse_weekday`).
_weekday = runner.parse_weekday


def _check(values: dict) -> None:
    _weekday(values["weekday"])
    if values["gap_max"] < values["gap_min"]:
        raise ValueError("방 사이 간격 — 최대가 최소보다 작습니다")


FIELDS = (
    runner.Field("rooms", "채널방(한 줄에 하나)", "lines", [],
                 hint="보내는 계정 카톡의 오픈채팅방 제목 그대로"),
    runner.Field("weekday", "요일", "text", "수"),
    runner.Field("time", "첫 방 시각", "time", "13:30"),
    runner.Field("count", "기업 수", "int", 3, low=1, high=10),
    runner.Field("exclude_days", "다시 보내기까지(일)", "int", 90, low=0, high=365),
    runner.Field("gap_min", "방 사이 최소(분)", "int", 2, low=0, high=30),
    runner.Field("gap_max", "방 사이 최대(분)", "int", 5, low=0, high=30),
)


def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    values = runner.values(row, automation.CHANNEL_TOP)
    try:
        weekday = _weekday(values["weekday"])
    except ValueError:
        return None
    if day.weekday() != weekday:
        return None
    year, week, _ = day.isocalendar()
    return runner.Plan(period=year * 100 + week, at=runner.at_on(day, values["time"]))


# ── 기록 ─────────────────────────────────────────────────────────────────────

def last_sent(db: Session, test: bool) -> Dict[int, str]:
    """기업마다 **마지막으로 채널에 실제로 나간 날**(`YYYY-MM-DD`)."""
    rows = db.execute(
        select(AutomationSend.company_id, func.max(SendItem.sent_at))
        .join(SendItem, SendItem.id == AutomationSend.item_id)
        .where(AutomationSend.automation == automation.CHANNEL_TOP,
               AutomationSend.test == (1 if test else 0),
               AutomationSend.company_id.isnot(None),
               SendItem.status == "sent")
        .group_by(AutomationSend.company_id)
    ).all()
    return {cid: (when or "")[:10] for cid, when in rows if cid}


def pick(db: Session, day: date, count: int, exclude_days: int,
         test: bool) -> tuple:
    """이번 주 기업들 `(고른 것, 뺀 사유)`."""
    from ...routers.companies import BLOCKED_CONTRACT

    history = last_sent(db, test)
    cutoff = (day - timedelta(days=exclude_days)).isoformat()
    rows = db.execute(
        select(IrCompany).where(IrCompany.is_top_deal == 1)
        .where(func.coalesce(IrCompany.contract_status, "") != BLOCKED_CONTRACT)
        .order_by(IrCompany.id)
    ).scalars().all()
    fresh, again, skipped = [], [], []
    for company in rows:
        if not company.introducible:
            skipped.append(f"{company.name} — 소개 문구를 만들 수 없음(내용 부족)")
            continue
        when = history.get(company.id)
        if when is None:
            fresh.append(company)
        elif exclude_days and when > cutoff:
            skipped.append(f"{company.name} — {when} 에 채널로 나감({exclude_days}일 안)")
        else:
            again.append((when, company))
    fresh.sort(key=lambda c: (c.received_at or ""), reverse=True)
    again.sort(key=lambda pair: pair[0])
    ordered = fresh + [c for _when, c in again]
    return ordered[:count], skipped


def message(companies: List[IrCompany], index: int, period: int) -> str:
    """한 방에 갈 글 — 기업 덩어리는 딜 소개와 같은 모양, 앞뒤 줄만 방마다 다르다."""
    from ...routers import deals as deals_view

    header = HEADERS[(index + period) % len(HEADERS)]
    intro = INTROS[(index * 2 + period) % len(INTROS)]
    footer = FOOTERS[(index + period * 3) % len(FOOTERS)]
    nobody = mc.ContactView(name="", title=None, firm=None)
    body = mc.compose_message(header, intro, nobody,
                              [deals_view._to_company_view(c) for c in companies],
                              stage=mc.STAGE_DAY1).text.strip()
    return f"{body}\n\n{footer}\n"


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    values = runner.values(row, automation.CHANNEL_TOP)
    rooms = [r for r in dict.fromkeys(values["rooms"]) if r]
    if not rooms:
        return runner.Batch(note="채널방 목록이 비어 있습니다 — 자동화 판에서 방 제목을 넣으세요")
    companies, skipped = pick(db, plan_.at.date(), values["count"],
                              values["exclude_days"], automation.is_test(row))
    batch = runner.Batch(skipped=skipped,
                         note="보낼 TOP·핵심 딜이 0곳입니다 — 이번 주는 건너뜁니다",
                         spacing=(values["gap_min"], values["gap_max"]))
    if not companies:
        return batch
    for index, room in enumerate(rooms):
        batch.outs.append(automation.Out(
            room=room, message=message(companies, index, plan_.period),
            company_ids=[c.id for c in companies],
            ref=f"week:{plan_.period}:{room}"))
    return batch


def describe(db: Session, row: Optional[Automation]) -> str:
    """판에 덧붙이는 한 줄 — 최근 채널 발송."""
    history = last_sent(db, automation.is_test(row))
    if not history:
        return ""
    names = {c.id: c.name for c in db.execute(
        select(IrCompany).where(IrCompany.id.in_(list(history)))).scalars().all()}
    recent = sorted(history.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return "최근 채널 발송: " + ", ".join(
        f"{names.get(cid, cid)}({when[5:].replace('-', '/')})" for cid, when in recent)


runner.register(runner.Spec(
    key=automation.CHANNEL_TOP, kind="deal_intro", plan=plan, collect=collect,
    fields=FIELDS, check=_check, describe=describe))
