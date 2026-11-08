"""#196 · **딜 소싱 참여 제안** — 검토가능 중 `제안 대기중` 분께 참여 안내(처음)를 한 번.

딜 소싱 명단의 정한 갈래(기본 시리즈 A — 화면 이름 `Series A 이상 딜 검토 가능 심사역`)
에서 `참여` 칸이 **`딜 소싱 참여 제안 대기중`** 인 분께, 기본 **3주차 화요일 10:00** 에
참여 안내(처음) 문구가 나간다. 보내는 계정은 자동화 판의 그 계정(비우면 팀의 자동 발송
계정 — 업무용 PC 한 대)이다.

**손으로 보내는 참여 안내(딜 소싱 제안 › [보낼 문구 › 참여 안내(처음)])를 그대로 자동으로
돌린 것이다.** 글(`deals._compose_for_contact` — 인사말 + 갈래 문구) · 방 · 잡 모양
(`sourcing_intro` + 빈 문구)이 그 길과 같다. 그래서 나간 뒤 일도 같다 — 발송기가 성공을
보고하면 그 줄이 저절로 `참여 의사를 물어보는 중` 이 된다(`sourcing_sync.mark_invited`).

## 같은 분께 두 번 안 간다 — 셋이 겹쳐 막는다

  · **`제안 대기중` 만** — 검토가능 칩은 `물어보는 중` 도 세지만, 그분은 이미 제안을
    받고 답을 기다리는 중이라 뺀다(다시 청하는 것은 사람이 손으로 — 손 길은 여전히
    `물어보는 중` 에게 보낼 수 있다). `불참여`(거절) · `참여`(이미 들어옴) · 사람이 적은
    문구도 안 간다.
  · **자동화 안에서 한 분께 한 번** — `ref` 가 `invite:<줄 번호>` 로 달이 없다
    (`automation_sends` 의 `(자동화, ref, 시험)`). 그 뒤 누가 칸을 다시 `제안 대기중`
    으로 돌려도 자동으로는 다시 안 간다.
  · **손으로 보낸 참여 안내가 있으면** — 기간 없이 뺀다(`automation_dedup.
    manual_sourcing_invite` — 큐에 서 있거나 보내는 중인 것 포함).

그 밖은 다른 자동화와 같다 — 같은 분 · 같은 방 하루 N통, 시험 모드끼리만 센다.

## 담당 칸은 보지 않는다

딜 소싱 `담당` 칸은 표기일 뿐이다. 글은 보내는 계정 PC 의 카톡에서 그 줄의 **방 이름**
으로 나간다 — 방은 그 계정 카톡 기준으로 [방 후보 찾기]에서 확정해 둔 것이어야 한다.
방이 없는 줄은 뺀다(투자사 방을 이어받지 않는다 — `sourcing_link.linked_rooms`).

## 알림 (`Spec.alert`)

보내는 계정(과 그 계정이 맡긴 발송기 주인)으로 웹에 로그인하면 전날 · 당일 아침 ·
다 나간 뒤 화면에 알림 창이 뜬다(`automation_runner.alert_for`).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Automation, AutomationSend, SourcingContact, User
from .. import automation, sourcing_buckets, sourcing_link, sourcing_msg, sourcing_sync
from .. import automation_runner as runner
from .. import message_composer as mc
# 칸 모양(갈래 · 주차 · 요일 · 시각)이 소싱 리마인드와 같다 — 읽고 가리는 손도 같은 것.
from .sourcing_remind import _check, _weeks, week_of_month

KEY = automation.SOURCING_INVITE

FIELDS = (
    runner.Field("groups", "갈래(한 줄에 하나)", "lines", [sourcing_sync.SYNC_BUCKET],
                 hint="딜 소싱 화면의 갈래 탭 이름 그대로"),
    runner.Field("weeks", "주차", "text", "3", hint="1~7일이 1주차 — 쉼표로 여럿"),
    runner.Field("weekday", "요일", "text", "화"),
    runner.Field("time", "보낼 시각", "time", "10:00"),
)


def plan(db: Session, row: Automation, day: date) -> Optional[runner.Plan]:
    values = runner.values(row, KEY)
    try:
        weekday, weeks = runner.parse_weekday(values["weekday"]), _weeks(values["weeks"])
    except ValueError:
        return None
    nth = week_of_month(day)
    if day.weekday() != weekday or nth not in weeks:
        return None
    return runner.Plan(period=(day.year * 100 + day.month) * 10 + nth,
                       at=runner.at_on(day, values["time"]))


def message(db: Session, sender: User, contact: SourcingContact) -> str:
    """참여 안내 전문 — 손으로 보내는 참여 안내(처음)와 **같은 길**."""
    from ...routers import deals as deals_view

    return deals_view._compose_for_contact(
        db, sender, contact, [], mode=deals_view.MODE_SOURCING,
        topic=sourcing_msg.KIND).text


def collect(db: Session, row: Automation, sender: User,
            plan_: runner.Plan) -> runner.Batch:
    values = runner.values(row, KEY)
    people = db.execute(
        select(SourcingContact).where(SourcingContact.bucket.in_(
            sourcing_buckets.variants(db, *values["groups"])))
        .order_by(SourcingContact.position, SourcingContact.id)
    ).scalars().all()
    linked = sourcing_link.linked_rooms(db, people)
    batch = runner.Batch(note="참여 제안을 보낼 분이 없습니다"
                              "(제안 대기중인 분이 없거나 모두 방이 없음)")
    for person in people:
        value = sourcing_sync.participation_of(person)
        if value != sourcing_sync.OFFER_PENDING:
            # 검토가능 중 `물어보는 중` 만 까닭을 남긴다 — 참여 · 불참여 · 문구는
            # 애초에 이 글의 대상이 아니다.
            if value == sourcing_sync.ASKING:
                batch.skipped.append(f"{person.name}({person.firm or '-'}) — {value}"
                                     "(이미 제안함 — 다시 보내려면 손으로)")
            continue
        room = sourcing_link.room_for(person, linked)
        if not room:
            batch.skipped.append(f"{person.name}({person.firm or '-'}) — 방 이름 없음")
            continue
        batch.outs.append(automation.Out(
            room=room, message=message(db, sender, person),
            sourcing_contact_id=person.id, stage=mc.STAGE_DAY1,
            ref=f"invite:{person.id}"))
    return batch


def still_ok(db: Session, rec: AutomationSend) -> str:
    """풀리기 직전 — 그사이 칸이 `제안 대기중` 이 아니게 됐거나(손으로 보냄 · 사람이
    바꿈) 줄이 지워졌으면 뺀다."""
    person = db.get(SourcingContact, rec.sourcing_contact_id) if rec.sourcing_contact_id else None
    if person is None:
        return "딜 소싱 명단에서 지워짐"
    value = sourcing_sync.participation_of(person)
    return "" if value == sourcing_sync.OFFER_PENDING else value


def manual(db: Session, _values: dict, target, _day: date) -> str:
    from .. import automation_dedup

    return automation_dedup.manual_sourcing_invite(db, target.sourcing_contact_id)


runner.register(runner.Spec(
    key=KEY, kind=sourcing_sync.INVITE_JOB_KIND, topic=None, plan=plan,
    collect=collect, still_ok=still_ok, fields=FIELDS, check=_check,
    manual=manual, alert=True))
