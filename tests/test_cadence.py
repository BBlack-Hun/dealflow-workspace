"""후속 캐던스 — 딜소개 뒤에 무엇을 언제 보낼지.

여기서 지키려는 경계.

1. **성공한 뒤에만 시작한다.** 발송 목록을 만든 시점에 시작하면 실패한 건까지
   후속이 예약되어, 받은 적 없는 사람에게 "지난번 공유드린" 이 나간다.
2. **답이 오면 멈춘다.** IR 요청·미팅이 잡혔는데도 리마인드가 계속 나가는 것이
   이 기능에서 가장 나쁜 실패다.
3. **주말에는 보내지 않는다.**
4. **주기는 DB 가 정한다.** 코드에 박아 두면 바뀔 때마다 배포해야 한다
   (실제로 '매주'에서 '월 2회'로 한 번 바뀌었다).
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def seed(db, users):
    from app.models import IrCompany, VcContact

    company = IrCompany(name="샘플애그", one_liner="B2B 농산물 선도거래",
                        revenue_recent=12, summary_status="done")
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", kakao_room_name="홍길동 심사역님 가나벤처스",
                        room_verified="verified", channel_kakao=1)
    db.add_all([company, contact])
    db.commit()
    return {"company_id": company.id, "contact_id": contact.id,
            "user_id": users["u1"].id}


def _send(db, contact_id, user_id, stage=1, status="sent", kind="deal_intro",
          sent_on=None):
    """발송 한 건을 만들고 결과까지 기록한다."""
    from app.models import DealBatch, SendItem, SendJob

    when = (sent_on or date.today()).isoformat() + "T09:00:00+00:00"
    batch = DealBatch(user_id=user_id, title="회차", sent_date=when[:10])
    db.add(batch)
    db.flush()
    job = SendJob(user_id=user_id, kind=kind, batch_id=batch.id, status="done")
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, contact_id=contact_id, stage=stage,
                    room_name="방", message="문구", status=status,
                    sent_at=when if status == "sent" else None)
    db.add(item)
    db.flush()
    return item, job


# --- 주기 규칙 --------------------------------------------------------------

def test_rules_come_from_the_database(db):
    """주기를 바꾸면 다음 회차일이 따라 바뀐다."""
    from app.models import ScheduleRule
    from app.services import cadence

    db.add(ScheduleRule(key="deal_cycle", label="딜소개 회차",
                        kind="monthly_weekday", weekday=0, nth_weeks="2",
                        skip_weekend=1))
    db.commit()
    # 2026-09 의 두 번째 월요일 = 9/14
    assert cadence.upcoming_send_dates(db, date(2026, 9, 1), count=1) == [date(2026, 9, 14)]


def test_weekend_is_pushed_to_monday(db):
    from app.services import cadence

    saturday = date(2026, 9, 5)
    assert cadence.next_business_day(saturday) == date(2026, 9, 7)
    assert cadence.next_business_day(date(2026, 9, 7)) == date(2026, 9, 7)


def test_follow_up_lands_inside_the_window(db):
    """리마인드는 6~7일 뒤. 매번 같은 날이 아니라 범위 안에서 흩어진다."""
    from app.services import cadence

    sent = date(2026, 9, 2)          # 수요일
    seen = set()
    for s in range(30):
        day = cadence.follow_up_date(db, sent, cadence.STAGE_REMIND,
                                     random.Random(s))
        assert day.weekday() < 5                      # 주말에는 안 보낸다
        assert 6 <= (day - sent).days <= 9            # 6~7일 + 주말 보정
        seen.add(day)
    assert len(seen) > 1, "모두 같은 날이면 한 번에 몰린 발송으로 보인다"


# --- 시퀀스 시작 ------------------------------------------------------------

def test_sequence_starts_only_after_a_successful_send(db, seed):
    from app.models import SendSequence
    from app.services import cadence

    item, job = _send(db, seed["contact_id"], seed["user_id"], status="failed")
    assert cadence.start_or_advance(db, item, job) is None
    assert db.query(SendSequence).count() == 0


def test_day1_success_schedules_the_remind(db, seed):
    from app.services import cadence

    sent_on = date(2026, 9, 2)
    item, job = _send(db, seed["contact_id"], seed["user_id"], sent_on=sent_on)
    seq = cadence.start_or_advance(db, item, job, random.Random(1))
    db.commit()

    assert seq.stage == cadence.STAGE_DAY1
    assert seq.next_stage == cadence.STAGE_REMIND
    assert seq.status == "active"
    assert 6 <= (date.fromisoformat(seq.next_due_date) - sent_on).days <= 9


def test_remind_success_schedules_the_meeting_from_day1(db, seed):
    """미팅 요청은 딜소개일 기준이다 — 리마인드가 늦어도 회차 간격이 안 엉킨다."""
    from app.services import cadence

    day1 = date(2026, 9, 2)
    item, job = _send(db, seed["contact_id"], seed["user_id"], sent_on=day1)
    seq = cadence.start_or_advance(db, item, job, random.Random(1))
    db.commit()

    late = day1 + timedelta(days=9)      # 리마인드가 늦게 나갔다
    item2, job2 = _send(db, seed["contact_id"], seed["user_id"], stage=2, sent_on=late)
    seq = cadence.start_or_advance(db, item2, job2, random.Random(1))
    db.commit()

    assert seq.next_stage == cadence.STAGE_MEETING
    gap = (date.fromisoformat(seq.next_due_date) - day1).days
    assert 11 <= gap <= 16              # 딜소개일 + 11~14 (+ 주말 보정)


def test_meeting_success_finishes_the_sequence(db, seed):
    from app.services import cadence

    item, job = _send(db, seed["contact_id"], seed["user_id"])
    cadence.start_or_advance(db, item, job)
    item2, job2 = _send(db, seed["contact_id"], seed["user_id"], stage=2)
    cadence.start_or_advance(db, item2, job2)
    item3, job3 = _send(db, seed["contact_id"], seed["user_id"], stage=3)
    seq = cadence.start_or_advance(db, item3, job3)
    db.commit()

    assert seq.status == "done"
    assert seq.next_due_date is None


# --- 멈추기 -----------------------------------------------------------------

def test_ir_delivery_stops_the_sequence(db, seed):
    """자료를 보냈다는 것은 상대가 달라고 했다는 뜻이다."""
    from app.services import cadence

    item, job = _send(db, seed["contact_id"], seed["user_id"])
    cadence.start_or_advance(db, item, job)
    db.commit()

    item2, job2 = _send(db, seed["contact_id"], seed["user_id"], kind="ir_delivery")
    seq = cadence.start_or_advance(db, item2, job2)
    db.commit()
    assert seq.status == "responded"
    assert seq.next_due_date is None


def test_reaction_sweep_stops_the_sequence(db, seed):
    """IR 요청 기록이 생기면 리마인드를 멈춘다."""
    from app.models import ContactActivity, SendSequence
    from app.services import cadence

    day1 = date.today() - timedelta(days=3)
    item, job = _send(db, seed["contact_id"], seed["user_id"], sent_on=day1)
    cadence.start_or_advance(db, item, job)
    db.commit()

    db.add(ContactActivity(contact_id=seed["contact_id"], kind="ir_request",
                           content="IR 요청", happened_at=date.today().isoformat()))
    db.commit()

    assert cadence.sweep_reactions(db, seed["user_id"]) == 1
    db.expire_all()
    seq = db.query(SendSequence).first()
    assert seq.status == "responded"


def test_reaction_before_day1_does_not_stop_it(db, seed):
    """딜소개 **이전**의 IR 요청은 이번 회차에 대한 답이 아니다."""
    from app.models import ContactActivity, SendSequence
    from app.services import cadence

    old = date.today() - timedelta(days=30)
    db.add(ContactActivity(contact_id=seed["contact_id"], kind="ir_request",
                           content="옛날 요청", happened_at=old.isoformat()))
    db.commit()

    item, job = _send(db, seed["contact_id"], seed["user_id"])
    cadence.start_or_advance(db, item, job)
    db.commit()

    assert cadence.sweep_reactions(db, seed["user_id"]) == 0
    db.expire_all()
    assert db.query(SendSequence).first().status == "active"


# --- 화면 -------------------------------------------------------------------

def test_due_list_includes_overdue(db, seed, logged):
    """놓친 건이 목록에서 사라지면 영영 안 보낸다."""
    from app.models import SendSequence
    from app.services import cadence

    item, job = _send(db, seed["contact_id"], seed["user_id"])
    seq = cadence.start_or_advance(db, item, job)
    seq.next_due_date = (date.today() - timedelta(days=5)).isoformat()
    db.commit()

    rows = cadence.due_sequences(db, seed["user_id"])
    assert len(rows) == 1

    body = logged.get("/followups").text
    assert "5일 지남" in body


def test_followups_page_opens(logged):
    r = logged.get("/followups")
    assert r.status_code == 200
    assert "오늘 보낼 후속" in r.text


def test_mark_responded_stops_it(db, seed, logged):
    from app.models import SendSequence
    from app.services import cadence

    item, job = _send(db, seed["contact_id"], seed["user_id"])
    seq = cadence.start_or_advance(db, item, job)
    db.commit()
    seq_id = seq.id

    logged.post(f"/followups/{seq_id}/responded", follow_redirects=False)
    db.expire_all()
    assert db.get(SendSequence, seq_id).status == "responded"


def test_cannot_touch_another_users_sequence(db, seed, client, users):
    from app.services import cadence

    item, job = _send(db, seed["contact_id"], seed["user_id"])
    seq = cadence.start_or_advance(db, item, job)
    db.commit()
    seq_id = seq.id

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert client.post(f"/followups/{seq_id}/responded").status_code == 404


def test_rule_change_is_admin_only(logged, db, seed):
    assert logged.post("/followups/rules/remind",
                       data={"offset_min_days": 3, "offset_max_days": 4}).status_code == 403


def test_backfill_picks_up_past_sends(db, seed, logged):
    """이 기능을 켜기 전에 나간 회차에도 후속을 잡아 준다."""
    from app.models import SendSequence

    _send(db, seed["contact_id"], seed["user_id"])
    db.commit()
    assert db.query(SendSequence).count() == 0

    logged.post("/followups/backfill", follow_redirects=False)
    db.expire_all()
    assert db.query(SendSequence).count() == 1
