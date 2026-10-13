"""A1 · **소싱 리마인드** — 이 달 딜을 아직 안 준 심사역에게 한 달에 두 번.

딜 소싱 명단(좌측 [딜 소싱])의 정한 갈래(기본 `시리즈 A 이상 딜 소싱 참여
심사역`) 사람 중 **이 달 `딜 받음` 이 안 눌린** 사람에게, 기본 **2주차 ·
3주차 수요일 11:00** 에 리마인드 문구(`sourcing_remind` — 딜 제안 문구에서
고친다)가 나간다. 보내는 계정(자동화 판의 그 계정) 카톡에서.

## 무엇을 보고 고르나

  · 갈래 — 자동화 판에서 고친다(여러 줄이면 여러 갈래).
  · `딜 받음` — 딜 소싱 화면의 줄마다 그 달 표시(`sourcing_receipts`). 지금은
    사람이 누른다. 메일로 저절로 적는 길은 열어만 두었다
    (`sourcing_receipts.record_from_mail`).
  · 방 — 그 줄의 방 이름, 없으면 투자사 명단에서 휴대폰 번호로 이어진 방
    (`sourcing_link` — 그 방은 보내는 계정 카톡 기준 제목으로 고른다).
    방이 없는 줄은 뺀다 — 딜 소싱 화면의 [방 후보 찾기] 로 채운다.

## 주차

`1~7일이 1주차` — 이 저장소가 주차를 세는 규칙 하나(`sheet_import.week_of_month`).
`2주차 수요일` 은 8~14일 사이의 수요일이다.

## 아침에 세운 뒤 `딜 받음` 을 누르면

11시에 풀리는 순간 그 사람은 빠진다(`still_ok`).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Automation, AutomationSend, SourcingContact, User, VcContact
from .. import automation, sender_rooms, sourcing_link, sourcing_receipts
from .. import automation_runner as runner
from .. import message_composer as mc

#: 문구 종류 — 딜 제안 문구 화면에서 고친다(`routers/templates_crud.KINDS`).
KIND = "sourcing_remind"

#: 문구틀이 없을 때 나가는 글. **글자까지 `scripts/bootstrap.py` 의 시드와 같다.**
#: 딜 소싱 제안(`sourcing_msg.default_body`)과 같은 결 — 무엇을 왜 달라는지,
#: 어떻게 쓰이는지, 이미 보냈으면 넘겨도 된다는 말.
DEFAULT_BODY = "\n".join([
    "Deal Sourcing 네트워크 관련하여 이번 달 딜 공유 요청드립니다.",
    "",
    "이번 달 검토하신 딜 중 투자 방향이나 Fit 차이로 제외된 딜이 있으시면",
    "편하실 때 전달 부탁드립니다.",
    "",
    " . 전달 주신 딜은 취합하여 월초 통합 공유드립니다",
    " . 클로즈드 방식으로 운영되고 있습니다",
    "",
    "이미 전달 주셨다면 이 메시지는 넘겨 주셔도 됩니다.",
    "감사합니다.",
])

#: 기본 갈래 — 운영의 갈래 이름(시트 탭 이름) 그대로.
DEFAULT_GROUPS = ["시리즈 A 이상 딜 소싱 참여 심사역"]

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


def message(db: Session, sender: User, contact) -> str:
    """리마인드 전문 — 딜 소싱 제안과 **같은 틀**(인사말 + 안내문, 호칭은 갈래로)
    에 안내문만 리마인드 문구로 바꾼다(`deals._compose_for_contact`)."""
    from ...routers import deals as deals_view
    from .. import template_pick

    picked = template_pick.pick(db, sender.id, KIND)
    body = picked.body if picked else DEFAULT_BODY
    return deals_view._compose_for_contact(
        db, sender, contact, [], mode=deals_view.MODE_SOURCING,
        closing_override=body).text


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
    month = sourcing_receipts.month_of(plan_.at.date())
    nth = plan_.period % 10
    people = db.execute(
        select(SourcingContact).where(SourcingContact.bucket.in_(values["groups"]))
        .order_by(SourcingContact.position, SourcingContact.id)
    ).scalars().all()
    got = sourcing_receipts.received_ids(db, month)
    linked = sourcing_link.linked_rooms(db, people)
    batch = runner.Batch(note="리마인드 보낼 심사역이 없습니다(모두 딜 받음이거나 방이 없음)")
    for person in people:
        who = f"{person.name}({person.firm or '-'})"
        if person.id in got:
            batch.skipped.append(f"{who} — 이번 달 딜 받음")
            continue
        room = _room(db, sender, person, linked)
        if not room:
            batch.skipped.append(f"{who} — 방 이름 없음")
            continue
        batch.outs.append(automation.Out(
            room=room, message=message(db, sender, person),
            sourcing_contact_id=person.id, stage=mc.STAGE_REMIND,
            ref=f"remind:{person.id}:{month}:{nth}"))
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 `딜 받음` 을 눌렀으면 뺀다."""
    try:
        _, contact_id, month, _nth = rec.ref.split(":")
    except ValueError:
        return ""
    if sourcing_receipts.is_received(db, int(contact_id), month):
        return "이번 달 딜 받음"
    return ""


runner.register(runner.Spec(
    key=automation.SOURCING_REMIND, kind="sourcing_intro", plan=plan,
    collect=collect, still_ok=still_ok, fields=FIELDS, check=_check))
