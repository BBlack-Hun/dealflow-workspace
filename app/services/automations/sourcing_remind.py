"""A1 · **소싱 리마인드** — 이 달 딜을 아직 안 준 심사역에게 한 달에 두 번.

딜 소싱 명단(좌측 [딜 소싱])의 정한 갈래(기본 `시리즈 A 이상 딜 소싱 참여
심사역`) 사람 중 **이 달 `딜 받음` 이 아닌** 사람에게, 기본 **2주차 ·
3주차 수요일 11:00** 에 월간 리마인드가 나간다. 보내는 계정(자동화 판의 그
계정) 카톡에서.

**손으로 보내는 월간 리마인드(딜 소싱 제안 › [보낼 문구 › 월간 리마인드])를
그대로 자동으로 돌린 것이다.** 고르는 사람 · 빼는 사람 · 글 · 방이 그 길과
같은 부품을 지난다 — 둘이 다른 규칙을 들면 같은 심사역이 손으로 받을 때와
자동으로 받을 때 다른 글을 받는다.

## 무엇을 보고 고르나

  · 갈래 — 자동화 판에서 고친다(여러 줄이면 여러 갈래).
  · `불참여` — 뺀다(`sourcing_sync.takes_part` — 손으로 보낼 때와 같은 판정).
  · `딜 받음` — 그 달 표시(`sourcing_receipts`). 사람이 누르거나, 회사 받은
    편지함(POP3) 확인이 저절로 세운다(`services/sourcing_mail.py`). 리마인드가
    나가는 날에는 **30분 전에 메일을 한 번 더 본다** — 아래 `remind_at` 을
    메일 확인의 고리(`sourcing_mail.register_remind_source`)에 단다.
  · 방 — 그 줄의 방 이름, 없으면 투자사 명단에서 휴대폰 번호로 이어진 방
    (`sourcing_link.linked_rooms` — **시리즈 A 갈래는 이어받지 않는다**, 그
    갈래는 자기 방이 없으면 방 없음). 이어진 방은 보내는 계정 카톡 기준
    제목으로 고른다(`sender_rooms.room_for`). 방이 없는 줄은 뺀다 — 딜 소싱
    화면의 [방 후보 찾기](`services/sourcing_rooms.py`)로 채운다.

## 글

손으로 보낼 때와 같은 글이다 — 딜 소싱 제안과 같은 틀(인사말 + 안내문, 빈
직함은 갈래 호칭)에 안내문이 **월간 리마인드** 문구(`sourcing_remind`, 딜
제안 문구에서 고친다 · 갈래 문구 > 갈래 없는 문구 > 코드 뼈대 —
`sourcing_msg.remind_body_for`). `{월}` 은 **보내는 날의 달**로 채운다.

회차는 `topic=sourcing_remind` 로 선다 — 손으로 보낸 리마인드와 같은 이름
(`딜 소싱 리마인드`)으로 발송 기록에 남는다.

## 주차

`1~7일이 1주차` — 이 저장소가 주차를 세는 규칙 하나(`sheet_import.week_of_month`).
`2주차 수요일` 은 8~14일 사이의 수요일이다.

## 아침에 세운 뒤 `딜 받음` 이 서면

11시에 풀리는 순간 그 사람은 빠진다(`still_ok`). 그사이 `불참여` 가 됐거나
줄이 지워졌어도 빠진다.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Automation, AutomationSend, SourcingContact, User, VcContact
from .. import (automation, sender_rooms, sourcing_link, sourcing_mail,
                sourcing_msg, sourcing_receipts, sourcing_sync)
from .. import automation_runner as runner
from .. import message_composer as mc

#: 문구 종류 — 손으로 보내는 월간 리마인드와 **같은 종류**다(딜 제안 문구에서 고친다).
KIND = sourcing_msg.REMIND_KIND

#: 기본 갈래 — 투자사 관리 현황과 잇는 그 갈래(운영의 시트 탭 이름 그대로).
DEFAULT_GROUPS = [sourcing_sync.SYNC_BUCKET]

_WEEKDAYS = "월화수목금토일"


def _weekday(raw: str) -> int:
    text = (raw or "").strip()
    if len(text) == 1 and text in _WEEKDAYS:
        return _WEEKDAYS.index(text)
    raise ValueError("요일은 월~일 중 한 글자로 넣으세요")


def _weeks(raw: str) -> List[int]:
    try:
        weeks = sorted({int(p) for p in str(raw).replace(" ", "").split(",") if p})
    except ValueError:
        raise ValueError("주차는 2,3 처럼 쉼표로 넣으세요") from None
    if not weeks or any(w < 1 or w > 5 for w in weeks):
        raise ValueError("주차는 1~5 사이로 넣으세요")
    return weeks


def _check(values: dict) -> None:
    _weekday(values["weekday"])
    _weeks(values["weeks"])
    if not values["groups"]:
        raise ValueError("보낼 갈래를 하나 이상 넣으세요")


FIELDS = (
    runner.Field("groups", "갈래(한 줄에 하나)", "lines", DEFAULT_GROUPS,
                 hint="딜 소싱 화면의 갈래 탭 이름 그대로"),
    runner.Field("weeks", "주차", "text", "2,3", hint="1~7일이 1주차 — 쉼표로 여럿"),
    runner.Field("weekday", "요일", "text", "수"),
    runner.Field("time", "보낼 시각", "time", "11:00"),
)


def week_of_month(day: date) -> int:
    from ..sheet_import import week_of_month as rule

    return rule(day.isoformat()) or 0


def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    values = runner.values(row, automation.SOURCING_REMIND)
    try:
        weekday, weeks = _weekday(values["weekday"]), _weeks(values["weeks"])
    except ValueError:
        return None
    nth = week_of_month(day)
    if day.weekday() != weekday or nth not in weeks:
        return None
    return runner.Plan(period=(day.year * 100 + day.month) * 10 + nth,
                       at=runner.at_on(day, values["time"]))


def remind_at(db: Session, day: date) -> Optional[datetime]:
    """그날 리마인드가 나갈 시각 — **켜 둔 날만.** 메일 확인이 이 시각 30분
    전에 한 번 더 받은 편지함을 본다(`sourcing_mail.slots_on`). 그 확인이
    실패해도 리마인드는 그대로 나간다(그쪽 머리말 — fail-open)."""
    row = automation.load(db, automation.SOURCING_REMIND)
    if not automation.is_on(row):
        return None
    planned = plan(db, row, day)
    return planned.at if planned is not None else None


sourcing_mail.register_remind_source(remind_at)


def message(db: Session, sender: User, contact: SourcingContact,
            day: Optional[date] = None) -> str:
    """리마인드 전문 — 손으로 보내는 월간 리마인드와 **같은 길**
    (`deals._compose_for_contact`, `topic=sourcing_remind`). `{월}` 만 보내는
    날의 달로 채워 넣는다(아침에 세운 글이 그날 나간다 — 달이 갈릴 일은 없지만
    시계를 두 번 읽지 않는다)."""
    from ...routers import deals as deals_view

    body = sourcing_msg.remind_body_for(db, sender, getattr(contact, "bucket", ""),
                                        day)
    return deals_view._compose_for_contact(
        db, sender, contact, [], mode=deals_view.MODE_SOURCING,
        topic=KIND, closing_override=body).text


def _room(db: Session, sender: User, contact: SourcingContact, linked: dict) -> str:
    own = (contact.kakao_room_name or "").strip()
    if own:
        return own
    link = linked.get(contact.id)
    if not link:
        return ""
    vc = db.get(VcContact, link["contact_id"])
    return sender_rooms.room_for(db, sender.id, vc) if vc else link["room"]


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    values = runner.values(row, automation.SOURCING_REMIND)
    day = plan_.at.date()
    month = sourcing_receipts.month_of(day)
    nth = plan_.period % 10
    people = db.execute(
        select(SourcingContact).where(SourcingContact.bucket.in_(values["groups"]))
        .order_by(SourcingContact.position, SourcingContact.id)
    ).scalars().all()
    got = sourcing_receipts.received_ids(db, month)
    linked = sourcing_link.linked_rooms(db, people)
    batch = runner.Batch(note="리마인드 보낼 심사역이 없습니다"
                              "(모두 딜 받음 · 불참여이거나 방이 없음)")
    for person in people:
        who = f"{person.name}({person.firm or '-'})"
        if not sourcing_sync.takes_part(person):
            batch.skipped.append(f"{who} — {sourcing_sync.LEFT}")
            continue
        if person.id in got:
            batch.skipped.append(f"{who} — 이번 달 딜 받음")
            continue
        room = _room(db, sender, person, linked)
        if not room:
            batch.skipped.append(f"{who} — 방 이름 없음")
            continue
        batch.outs.append(automation.Out(
            room=room, message=message(db, sender, person, day),
            sourcing_contact_id=person.id, stage=mc.STAGE_DAY1,
            ref=f"remind:{person.id}:{month}:{nth}"))
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 `딜 받음` 이 섰거나(메일 확인 · 사람) `불참여` 가
    됐거나 줄이 지워졌으면 뺀다."""
    try:
        _, contact_id, month, _nth = rec.ref.split(":")
        contact_id = int(contact_id)
    except ValueError:
        return ""
    if sourcing_receipts.is_received(db, contact_id, month):
        return "이번 달 딜 받음"
    person = db.get(SourcingContact, contact_id)
    if person is None:
        return "딜 소싱 명단에서 지워짐"
    if not sourcing_sync.takes_part(person):
        return sourcing_sync.LEFT
    return ""


runner.register(runner.Spec(
    key=automation.SOURCING_REMIND, kind="sourcing_intro", topic=KIND, plan=plan,
    collect=collect, still_ok=still_ok, fields=FIELDS, check=_check))
