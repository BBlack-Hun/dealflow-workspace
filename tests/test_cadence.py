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


def test_one_off_date_does_not_hide_a_nearer_cycle_day(db):
    """일회성 회차일이 있어도 **더 이른 회차일**을 건너뛰지 않는다.

    일회성 날짜를 개수에 함께 세는 바람에, 하나만 물으면(`count=1`) 규칙에서
    나온 더 이른 날을 찾기도 전에 멈추고 뒤엣 날을 답했다.
    """
    from app.models import ScheduleRule
    from app.services import cadence

    db.add(ScheduleRule(key="deal_cycle", label="딜소개 회차",
                        kind="monthly_weekday", weekday=2, nth_weeks="1,3",
                        skip_weekend=1, extra_dates="2026-08-26"))
    db.commit()
    # 8/10 에서 보면 8월 셋째 수요일(8/19)이 8/26 보다 먼저다.
    assert cadence.upcoming_send_dates(db, date(2026, 8, 10), count=1) == \
        [date(2026, 8, 19)]
    assert cadence.upcoming_send_dates(db, date(2026, 8, 10), count=3) == \
        [date(2026, 8, 19), date(2026, 8, 26), date(2026, 9, 2)]
    # 일회성 날짜는 여전히 목록에 든다.
    assert date(2026, 8, 26) in cadence.upcoming_send_dates(db, date(2026, 8, 20), count=2)


# --- 회차를 가르는 것은 주 ---------------------------------------------------
#
# 회차일에 다 못 보내고 다음 날 이어 보내는 일이 실제로 있다. 그때 회차가
# 넘어가면 한 번 보낸 것이 두 회차로 갈라져 남는다.
#
# 날짜는 전부 못박는다 — 오늘이 언제냐에 따라 통과했다 실패했다 하면 안 된다.
# 기본 규칙(수요일 · 1,3번째)으로만 재려고 `db=None` 을 쓴다.

def test_cycle_does_not_move_the_day_after(db):
    """**회차일 다음 날에도 같은 회차다.** 이것이 사용자가 본 증상이다.

    고치기 전에는 8/19(수) 다음 날인 8/20(목)에 화면을 열면 회차명이
    `08/26` 으로, 8/26(수) 다음 날에는 `09/02` 로 넘어갔다.
    """
    from app.services import cadence

    wednesday = date(2026, 8, 19)          # 8월 셋째 수요일 = 회차일
    thursday = date(2026, 8, 20)
    assert cadence.cycle_anchor(None, wednesday) == wednesday
    assert cadence.cycle_anchor(None, thursday) == wednesday
    # 회차명까지 같아야 한 회차로 남는다.
    assert (cadence.batch_title(cadence.cycle_anchor(None, thursday))
            == cadence.batch_title(wednesday) == "08/19 (8월 3주차)")


def test_cycle_holds_all_week(db):
    """월~일 한 주는 통째로 한 회차다 — 회차일 앞이든 뒤든."""
    from app.services import cadence

    wednesday = date(2026, 9, 2)           # 9월 첫째 수요일
    monday = date(2026, 8, 31)             # 그 주 월요일
    sunday = date(2026, 9, 6)              # 그 주 일요일
    for day in (monday, date(2026, 9, 1), wednesday,
                date(2026, 9, 3), date(2026, 9, 4), sunday):
        assert cadence.cycle_anchor(None, day) == wednesday, day


def test_next_week_is_the_next_cycle(db):
    """주가 넘어가면 회차도 넘어간다 — 붙잡아 두지는 않는다."""
    from app.services import cadence

    assert cadence.cycle_anchor(None, date(2026, 9, 6)) == date(2026, 9, 2)
    # 하루 뒤 = 다음 주 월요일
    assert cadence.cycle_anchor(None, date(2026, 9, 7)) == date(2026, 9, 16)


def test_week_without_a_cycle_day_points_at_the_next_one(db):
    """회차일이 없는 주는 그대로 다음 회차일을 가리킨다(전과 같다)."""
    from app.services import cadence

    off_week = date(2026, 9, 9)            # 9/7~9/13 에는 회차일이 없다
    assert cadence.cycle_anchor(None, off_week) == date(2026, 9, 16)
    assert (cadence.cycle_anchor(None, off_week)
            == cadence.upcoming_send_dates(None, off_week, count=1)[0])


def test_week_boundary_is_the_weekly_one(db):
    """주 경계는 주간 업무와 **같은 것**을 쓴다 — 두 벌로 정의하지 않는다."""
    from app.services import cadence, weekly

    for day in (date(2026, 8, 20), date(2026, 9, 3), date(2026, 10, 8)):
        anchor = cadence.cycle_anchor(None, day)
        # 회차 기준일은 늘 그 날과 같은 주 안에 있거나(그 주에 회차일이 있을 때),
        # 아직 오지 않은 다음 회차일이다.
        assert (weekly.week_start(anchor) == weekly.week_start(day)
                or anchor > day)


def test_wednesday_cycle_never_straddles_a_week(db):
    """딜 주기(수요일)는 월~일 주 안에 온전히 들어간다 — 주 경계가 회차일을 가르지 않는다.

    주 경계를 일요일 시작으로 두거나 주기가 토·일로 옮겨가면 한 회차가 두 주에
    걸쳐 갈라진다. 그 어긋남을 여기서 막는다.
    """
    from app.services import cadence, weekly

    for day in cadence.upcoming_send_dates(None, date(2026, 1, 1), count=24):
        assert day.weekday() <= 4, day          # 주말에 회차일을 두지 않는다
        # 그 회차일이 속한 주의 어느 날에서 물어도 같은 회차가 나온다.
        start = weekly.week_start(day)
        for i in range(7):
            assert cadence.cycle_anchor(None, start + timedelta(days=i)) == day


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


# --- 회차명 앞 날짜는 오늘 -----------------------------------------------------
#
# 회차명은 `09/02 (9월 1주차)` 꼴이고, 앞의 날짜는 **회차 기준일**이었다.
# 그래서 9/2 회차 주의 9/3 에 화면을 열면 `09/02` 가 채워졌다 — 그날 만든
# 회차인데 이름에는 어제가 적힌다. 나중에 "몇 월 며칠에 뭘 보냈지" 를 찾는
# 기준은 결국 **보낸 날**이라, 앞 날짜는 오늘이어야 한다.
#
# **회차일이 아직 오지 않았으면 회차 기준일 그대로다.** 그때는 보낸 날이
# 없다 — 다음 회차를 미리 준비하는 중이다. 오늘을 그냥 쓰면 8/31(월)에
# 준비한 9/2 회차가 `08/31 (8월 5주차)` 로 남아 9월 회차가 8월 이름을 달고,
# 9/10 에는 `09/10 (9월 2주차)` 가 되어 9/16(3주차) 회차가 2주차로 적힌다.
#
# 가르는 것은 **오늘이 회차 기준일보다 앞이냐** 하나다 — 요일로 재지 않는다.
# 지금은 딜 주기가 첫째·셋째 수요일이라 월·화가 그 앞이지만, 주기는
# `ScheduleRule` 이 정하고 실제로 한 번 바뀌었다.
#
# 날짜는 전부 인자로 넣는다 — 오늘이 언제냐에 따라 통과했다 실패했다 하면 안 된다.

# 9월 첫째 수요일 = 9/2 회차. 그 주는 8/31(월)~9/6(일) 이라 **달을 넘어간다.**
CYCLE_DAY = date(2026, 9, 2)


@pytest.mark.parametrize("today, expected", [
    (date(2026, 8, 31), "09/02 (9월 1주차)"),   # 이틀 전 · 월 — **지난달이다**
    (date(2026, 9, 1),  "09/02 (9월 1주차)"),   # 하루 전 · 화
    (date(2026, 9, 2),  "09/02 (9월 1주차)"),   # 당일 · 수
    (date(2026, 9, 3),  "09/03 (9월 1주차)"),   # 다음 날 · 목 — 사용자가 본 그날
    (date(2026, 9, 4),  "09/04 (9월 1주차)"),   # 이틀 뒤 · 금
    (date(2026, 9, 6),  "09/06 (9월 1주차)"),   # 회차 주 끝 · 일
])
def test_title_date_around_the_cycle_day(db, today, expected):
    """회차일 **앞이면 회차 기준일 · 당일부터는 오늘 날짜.**"""
    from app.services import cadence

    assert cadence.cycle_anchor(None, today) == CYCLE_DAY, today   # 다 같은 회차다
    assert cadence.default_batch_title(None, today) == expected


def test_september_cycle_never_carries_an_august_name(db):
    """**달을 넘어가는 자리** — 8/31(월)에 준비하는 것은 9/2 회차다.

    오늘 날짜를 그대로 쓰면 `08/31 (8월 5주차)` 가 되어 9월 회차가 8월 이름으로
    남는다. 발송 이력을 달로 훑을 때 9월 회차가 8월에 가 있으면 못 찾는다.
    """
    from app.services import cadence

    monday = date(2026, 8, 31)
    assert cadence.cycle_anchor(None, monday) == CYCLE_DAY      # 같은 주 · 같은 회차
    assert monday < CYCLE_DAY                                   # 아직 회차일 전이다
    title = cadence.default_batch_title(None, monday)
    assert title == "09/02 (9월 1주차)"
    assert "8월" not in title and title != cadence.batch_title(monday)


# 괄호 안 주차는 **회차의 이름**이다 — 사람들은 "첫째주 회차 / 셋째주 회차" 라고
# 부르고 시트 머리글도 그렇다. 주차 칸은 1~7일씩 끊으므로(`week_of_month`) 회차일이
# **7·14·21일**이면 그 다음 날은 다음 칸으로 넘어간다. 앞 날짜에서 주차를 다시 세면
# 같은 회차가 `02/07 (2월 1주차)` 와 `02/08 (2월 2주차)` 두 이름으로 남아, 이력을
# 주차로 찾을 때 갈라진다.
#
# 2024년 2월이 그 자리다 — 2/1 이 목요일이라 첫째 수요일이 **2/7**, 셋째가 **2/21**.

@pytest.mark.parametrize("anchor, week", [
    (date(2024, 2, 7), 1),                 # 1주차 칸의 마지막 날(1~7일)
    (date(2024, 2, 21), 3),                # 3주차 칸의 마지막 날(15~21일)
])
def test_week_label_stays_with_the_cycle(db, anchor, week):
    """회차일이 7·21일이어도 **그 다음 날 주차가 넘어가지 않는다.**"""
    from app.services import cadence, sheet_import

    assert cadence.cycle_anchor(None, anchor) == anchor
    assert sheet_import.week_of_month(anchor.isoformat()) == week

    for i in range(5):                     # 회차 당일 ~ 그 주 일요일
        day = anchor + timedelta(days=i)
        assert cadence.cycle_anchor(None, day) == anchor, day
        title = cadence.default_batch_title(None, day)
        # 앞 날짜는 보낸 날, 괄호 안 주차는 회차 그대로.
        assert title == f"{day.month:02d}/{day.day:02d} (2월 {week}주차)", day

    # 앞 날짜에서 다시 셌다면 그 다음 날부터 한 칸 넘어갔을 것이다.
    next_day = anchor + timedelta(days=1)
    assert sheet_import.week_of_month(next_day.isoformat()) == week + 1
    assert cadence.default_batch_title(None, next_day) != cadence.batch_title(next_day)


def test_title_date_is_the_cycle_day_outside_its_week(db):
    """회차 주 **밖**이면 회차 기준일이다 — 주차가 어긋나지 않게."""
    from app.services import cadence

    off_week = date(2026, 9, 10)           # 9/7~9/13 에는 회차일이 없다
    assert cadence.cycle_anchor(None, off_week) == date(2026, 9, 16)
    assert cadence.default_batch_title(None, off_week) == "09/16 (9월 3주차)"
    # 오늘을 그냥 썼다면 3주차 회차가 2주차로 적혔을 것이다.
    assert cadence.default_batch_title(None, off_week) != cadence.batch_title(off_week)


def test_title_date_never_runs_ahead_of_the_cycle_day(db):
    """어느 날에 열어도 앞 날짜는 **회차 기준일 아니면 오늘**이다.

    오늘을 쓰는 것은 회차일이 **왔을 때뿐**이다 — 아직 안 왔는데 오늘을 쓰면
    보낸 적 없는 회차가 지난 이름을 단다.
    주차는 `sheet_import.week_of_month` **하나로만** 센다 — 같은 날이 화면마다
    3주차·4주차로 갈리면 안 된다. 괄호 안은 늘 **앞 날짜**를 설명한다.
    """
    import re

    from app.services import cadence, sheet_import

    start = date(2026, 8, 24)              # 회차가 없는 주부터 넉넉히 훑는다
    for i in range(60):
        day = start + timedelta(days=i)
        anchor = cadence.cycle_anchor(None, day)
        title = cadence.default_batch_title(None, day)
        m = re.fullmatch(r"(\d{2})/(\d{2}) \((\d+)월 (\d)주차\)", title)
        assert m, (day, title)

        shown = (int(m.group(1)), int(m.group(2)))
        assert shown in {(anchor.month, anchor.day), (day.month, day.day)}, (day, title)
        if shown == (day.month, day.day) and day != anchor:
            assert day > anchor, (day, anchor, title)      # 회차일이 온 뒤에만 오늘
        # 괄호 안 달·주차는 **회차 기준일**의 것이다 — 앞 날짜에서 다시 세지 않는다.
        assert int(m.group(3)) == anchor.month, (day, title)
        assert int(m.group(4)) == sheet_import.week_of_month(anchor.isoformat()), (day, title)


def test_the_cycle_name_in_parens_never_drifts(db):
    """괄호 안은 **늘 회차 기준일의 달·주차**다 — 어느 날에 열어도 같은 이름.

    같은 회차가 두 이름으로 남으면 이력을 주차로 찾을 때 갈라진다.
    2년치를 하루도 빼지 않고 훑는다.
    """
    from app.services import cadence, sheet_import

    day = date(2026, 1, 1)
    while day < date(2028, 1, 1):
        anchor = cadence.cycle_anchor(None, day)
        week = sheet_import.week_of_month(anchor.isoformat())
        title = cadence.default_batch_title(None, day)
        assert title.endswith(f"({anchor.month}월 {week}주차)"), (day, anchor, title)
        # 앞 날짜의 달도 회차 기준일의 달이다(9월 회차가 8월 이름을 달지 않는다).
        assert title.startswith(f"{anchor.month:02d}/"), (day, anchor, title)
        day += timedelta(days=1)


def test_saved_titles_are_not_renamed(db):
    """**이미 저장된 회차 이름은 건드리지 않는다.**

    바뀌는 것은 새 회차를 만들 때 화면에 채워 주는 기본값뿐이다. 지난 회차
    이름이 오늘에 따라 달라지면 발송 이력이 갈라진다 — `batch_title(day)` 는
    받은 날짜만으로 정해지는 그대로여야 한다.
    """
    from app.services import cadence

    day = date(2026, 8, 19)
    assert cadence.batch_title(day) == "08/19 (8월 3주차)"
    # 오늘이 언제든 같은 값이다(인자를 받는 순수 함수).
    for today in (date(2026, 8, 20), date(2026, 9, 3), date(2027, 1, 5)):
        assert cadence.batch_title(day) == "08/19 (8월 3주차)", today
    # 한 인자로 부르면 괄호 안도 **그 날짜**에서 나온다 — 예전 이름이 그렇게 만들어졌다.
    assert cadence.batch_title(date(2024, 2, 8)) == "02/08 (2월 2주차)"


@pytest.mark.parametrize("today, expected", [
    (date(2026, 9, 1), "09/02 (9월 1주차)"),    # 회차일 전 — 회차 기준일
    (date(2026, 9, 3), "09/03 (9월 1주차)"),    # 회차일 뒤 — 오늘
])
def test_deal_screen_fills_in_the_title(logged, db, monkeypatch, today, expected):
    """화면 기본값이 실제로 그 값이다 — 서비스만 고치고 화면은 옛것일 수 있다."""
    import re

    from app import clock

    monkeypatch.setattr(clock, "today", lambda: today)
    body = logged.get("/deals").text
    m = re.search(r'id="batch-title" value="([^"]*)"', body)
    assert m, "회차명 칸이 없다"
    assert m.group(1) == expected
