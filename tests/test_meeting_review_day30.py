"""A7 미팅 후 검토결과 문의 — **두 번째: 미팅 완료 30일 뒤 투자 결정 문의.**

1. 미팅을 완료로 적은 날 + 30일(주말이면 다음 평일) 14:00 에 그 투자사 방으로
   투자 결정 문의가 보내는 계정 것으로 예약된다 — 사흘 안쪽으로 지난 것까지만 줍는다.
2. 글은 미팅 후기와 같은 틀(인사말 + 본문, 단계 3)에 본문만 투자 결정 문의다.
   `{미팅 기업}` 은 그 미팅의 기업 이름(비었으면 `기업`)으로 채워지고, 글자 그대로
   나가는 일이 없다.
3. 거절로 끝난 미팅만 뺀다 — 검토 중 · 투자 검토 · 보류 · 빈칸은 묻는다. 결과
   문의를 했다는 표시(`followup_done` · `followup_note`)는 두 번째를 막지 않는다.
4. 같은 분 · **같은 기업**의 다음 미팅이 잡혀 있으면 뺀다 — 다른 기업 건 미팅은 이
   기업의 투자 결정 문의를 막지 않는다(사용자 결정 2026-10-17). 미팅을 마친 뒤 사람이
   미팅 단계 글을 보냈으면 뺀다(쉬는 날 수와 상관없이 그 뒤 전부) — 자동으로 나간
   첫 번째는 안 센다.
5. 풀리기 직전에도 두 번째의 규칙으로 다시 본다. 첫 번째의 판정은 그대로다.
6. 판에서 날수(0 이면 안 묻는다) · 시각을 따로 고친다. 두 번째는 첫 번째보다 뒤.
7. 같은 분께 첫 번째 · 두 번째가 같은 날 서면 한 통만.
8. 문구는 문구 화면에서 고치고, 새로 깐 서버에는 같은 글이 기본으로 심긴다.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

TEST_ROOM = "자동화 시험방"
# 2026-09-14 월 → +30 = 10/14(수). 2026-10-12 월 → +2 = 10/14(수).
WED_9AM = datetime(2026, 10, 14, 9, 0)
DONE30 = "2026-09-14"
DONE2 = "2026-10-12"

#: 사용자가 정해 준 기본 글 — 줄바꿈까지 그대로.
DEFAULT_TEXT = (
    "지난번 미팅하셨던 {미팅 기업} 관련하여 다시 연락드립니다.\n"
    "미팅 후 한 달가량 지났는데, 혹시 투자 검토 결과가 나오셨는지 여쭙고 싶습니다.\n"
    "검토에 필요한 추가 자료가 있으시거나 한 번 더 미팅이 필요하시면 편하게 말씀 "
    "부탁드립니다. 바로 준비하겠습니다.")


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def world(db, users):
    from app.models import AutoSendSetting

    users["u2"].role = "admin"   # 보내는 계정
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    db.commit()
    return {"owner": users["u1"], "sender": users["u2"]}


def _contact(db, world, name, firm, **kw):
    from app.models import VcContact

    row = VcContact(user_id=world["owner"].id, name=name, firm=firm, title="심사역",
                    kakao_room_name=kw.pop("room", f"{name} {firm} Deal 공유"),
                    connect_stage="connected", source_sheet="내 명단", **kw)
    db.add(row)
    db.commit()
    return row


def _meeting(db, world, who, done=DONE30, **kw):
    from app.models import Meeting

    row = Meeting(user_id=world["owner"].id, contact_id=who.id,
                  scheduled_at=kw.pop("scheduled_at", done),
                  status=kw.pop("status", "done"), done_at=done,
                  outcome=kw.pop("outcome", "reviewing"),
                  company_name=kw.pop("company_name", "샘플바이오"), **kw)
    db.add(row)
    db.commit()
    return row


def _hand_send(db, world, who, sent_at):
    """사람이 발송 화면에서 미팅 단계 글을 보낸 것처럼(자동화 줄 없이)."""
    from app.models import DealBatch, SendItem, SendJob

    owner = world["owner"]
    batch = DealBatch(user_id=owner.id, title="미팅 후기", sent_date=sent_at[:10],
                      cycle_type="adhoc")
    db.add(batch)
    db.flush()
    job = SendJob(user_id=owner.id, kind="deal_intro", batch_id=batch.id,
                  status="done", total=1, sent=1, failed=0)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=who.id, stage=3, channel="kakao",
                    room_name=who.kakao_room_name, message="어떻게 보셨는지요",
                    status="sent", sent_at=sent_at))
    db.commit()


def _turn_on(db, *, test=False, **params):
    from app.services import automation, automation_runner as runner

    if params:
        runner.save_params(db, automation.MEETING_REVIEW, params)
    return automation.save(db, automation.MEETING_REVIEW, enabled=True,
                           user_id=None, test_mode=test, test_room=TEST_ROOM)


def _run(db, now=WED_9AM):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.MEETING_REVIEW, _aware(now))


def _items(db):
    """이 자동화가 세운 발송 건 — 손으로 보낸 건은 빼고."""
    from app.models import AutomationSend, SendItem

    db.expire_all()
    return db.execute(
        select(SendItem).where(SendItem.id.in_(select(AutomationSend.item_id)))
        .order_by(SendItem.id)).scalars().all()


def _refs(db):
    from app.models import AutomationSend

    db.expire_all()
    return sorted(db.execute(
        select(AutomationSend.ref).where(AutomationSend.automation == "meeting_review")
    ).scalars().all())


def _when(job):
    from app.services import scheduled_send

    return scheduled_send.label(scheduled_send.scheduled_at(job))


# ── 1. 언제 ──────────────────────────────────────────────────────────────────

def test_thirty_days_after_the_meeting_at_two_pm(db, users, world):
    from app.routers import deals

    who = _contact(db, world, "홍길동", "가나다벤처스")
    meeting = _meeting(db, world, who)
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "ready", result
    [item] = _items(db)
    assert item.contact_id == who.id and item.stage == 3
    assert item.job.user_id == world["sender"].id and item.job.kind == "deal_intro"
    assert _when(item.job) == "10/14(수) 14:00"
    assert item.message == deals.meeting_decision_message(db, world["sender"], who, meeting)
    # 두 번째는 제 열쇠를 쓴다 — 첫 번째(`meeting:`)와 섞이지 않는다.
    assert _refs(db) == [f"meeting30:{meeting.id}"]


def test_a_weekend_due_day_moves_to_monday(db, users, world):
    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who, done="2026-09-17")      # 목 → +30 = 10/17(토)
    _turn_on(db)
    assert _run(db, datetime(2026, 10, 16, 9, 0))["status"] == "empty"      # 금: 아직
    assert _run(db, datetime(2026, 10, 17, 9, 0))["status"] == "not_today"  # 토
    assert _run(db, datetime(2026, 10, 19, 9, 0))["status"] == "ready"      # 월
    [item] = _items(db)
    assert _when(item.job) == "10/19(월) 14:00"


def test_picks_up_three_days_back_but_never_older(db, users, world):
    recent = _contact(db, world, "홍길동", "가나다벤처스")
    stale = _contact(db, world, "김철수", "라마바벤처스")
    early = _contact(db, world, "이른날", "사아자벤처스")
    _meeting(db, world, recent, done="2026-09-11")   # 금 → 10/11(일) → 10/12(월): 이틀 전
    _meeting(db, world, stale, done="2026-09-09")    # 수 → 10/09(금): 닷새 전
    _meeting(db, world, early, done="2026-09-15")    # 화 → 10/15(목): 내일
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "ready"
    assert {i.contact_id for i in _items(db)} == {recent.id}
    # 너무 오래된 것 · 아직 안 온 것은 아예 안 줍는다(뺀 곳에도 안 선다).
    joined = " / ".join(result["skipped"])
    assert "김철수" not in joined and "이른날" not in joined


# ── 2. 누구에게 ─────────────────────────────────────────────────────────────

def test_only_a_pass_is_left_out(db, users, world):
    people = {}
    for outcome, name in (("reviewing", "검토중"), ("investing", "투자검토"),
                          ("hold", "보류중"), (None, "빈칸"), ("pass", "거절함")):
        people[outcome] = _contact(db, world, name, f"{name}벤처스")
        _meeting(db, world, people[outcome], outcome=outcome)
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "ready"
    sent = {i.contact_id for i in _items(db)}
    assert sent == {people[o].id for o in ("reviewing", "investing", "hold", None)}
    assert any("거절함" in line and "결과가 거절로 적혀 있습니다" in line
               and "투자 결정 문의" in line for line in result["skipped"])


def test_an_earlier_result_inquiry_does_not_block_the_second(db, users, world):
    """`followup_done` · `followup_note` 는 첫 번째 단계의 문의를 적은 것이다."""
    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who, followup_done=1, followup_note="10일 뒤 통화 — 검토 중")
    _turn_on(db)
    assert _run(db)["status"] == "ready"
    assert [i.contact_id for i in _items(db)] == [who.id]


def test_only_a_later_meeting_about_the_same_company_skips_it(db, users, world):
    """같은 분과 **같은 기업** 건으로 뒤 미팅이 있으면 뺀다. 다른 기업 건 미팅은 이
    기업의 결정을 묻는 데 걸리지 않는다. 기업 이름은 띄어쓰기를 빼고 맞추고, 뒤
    미팅의 기업을 모르면 같은 건일 수 있어 뺀다."""
    same = _contact(db, world, "홍길동", "가나다벤처스")
    spaced = _contact(db, world, "이띄움", "다라벤처스")
    unknown = _contact(db, world, "정모름", "마사벤처스")
    other = _contact(db, world, "김철수", "라마바벤처스")
    gone = _contact(db, world, "박취소", "바사벤처스")
    for who, company in ((same, "샘플바이오"), (spaced, "샘플 바이오"), (unknown, None),
                         (other, "샘플애그")):
        _meeting(db, world, who)
        _meeting(db, world, who, done=None, status="scheduled", scheduled_at="2026-10-20",
                 company_name=company)
    _meeting(db, world, gone)
    # 취소된 뒤 미팅은 다음 걸음이 아니다.
    _meeting(db, world, gone, done=None, status="canceled", scheduled_at="2026-10-20")
    _turn_on(db)
    result = _run(db)
    assert {i.contact_id for i in _items(db)} == {other.id, gone.id}
    for name in ("홍길동", "이띄움", "정모름"):
        assert any(name in line and "그 뒤 미팅이 또 잡혀 있습니다" in line
                   for line in result["skipped"]), name


def test_the_first_round_still_skips_any_later_meeting(db, users, world):
    """첫 번째(이틀 뒤)의 규칙은 그대로 — 같은 분의 뒤 미팅이면 기업이 달라도 뺀다
    (화면의 결과 문의 목록 `pipeline.meeting_rows` 의 `superseded` 와 같다)."""
    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who, done=DONE2)
    _meeting(db, world, who, done=None, status="scheduled", scheduled_at="2026-10-20",
             company_name="샘플애그")
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "empty"
    assert any("홍길동" in line and "그 뒤 미팅이 또 잡혀 있습니다" in line
               for line in result["skipped"])


def test_stopped_contacts_are_left_out(db, users, world):
    paused = _contact(db, world, "정멈춤", "가가벤처스", status="paused")
    noroom = _contact(db, world, "강빈방", "나나벤처스", room="")
    _meeting(db, world, paused)
    _meeting(db, world, noroom)
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "empty"
    joined = " / ".join(result["skipped"])
    assert "검토중단" in joined and "방 이름 없음" in joined


# ── 손 발송 ──────────────────────────────────────────────────────────────────

def test_a_hand_sent_meeting_message_after_the_meeting_skips_it(db, users, world):
    """미팅 뒤 사람이 보냈으면 — 쉬는 날(7일)보다 오래전이어도 — 안 묻는다."""
    asked = _contact(db, world, "홍길동", "가나다벤처스")
    before = _contact(db, world, "김철수", "라마바벤처스")
    _meeting(db, world, asked)
    _meeting(db, world, before)
    _hand_send(db, world, asked, "2026-09-20T15:00:00+09:00")    # 미팅 뒤 24일 전
    _hand_send(db, world, before, "2026-09-10T15:00:00+09:00")   # 미팅 **전**
    _turn_on(db)
    result = _run(db)
    assert {i.contact_id for i in _items(db)} == {before.id}
    assert any("홍길동" in line and "손으로" in line for line in result["skipped"])


def test_the_hand_send_rule_ignores_manual_days(db, users, world):
    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who)
    _hand_send(db, world, who, "2026-09-20T15:00:00+09:00")
    _turn_on(db, manual_days="0")
    assert _run(db)["status"] == "empty"


def test_a_meeting_ask_mark_after_the_meeting_skips_it(db, users, world):
    from app.models import ContactActivity
    from app.services import pipeline

    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who)
    db.add(ContactActivity(contact_id=who.id, kind=pipeline.MEETING_ASK_KIND,
                           content="미팅 요청", source="manual",
                           happened_at="2026-09-25", month="2026-09"))
    db.commit()
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "empty"
    assert any("적혀 있습니다" in line for line in result["skipped"])


def test_the_automatic_first_inquiry_does_not_block_the_second(db, users, world):
    """첫 번째(이틀 뒤)가 자동으로 나갔어도 두 번째는 나간다."""
    from app.routers import deals

    who = _contact(db, world, "홍길동", "가나다벤처스")
    meeting = _meeting(db, world, who)
    _turn_on(db)
    assert _run(db, datetime(2026, 9, 16, 9, 0))["status"] == "ready"   # 수: 첫 번째
    [first] = _items(db)
    assert first.message == deals.review_message(db, world["sender"], who)
    first.status, first.sent_at = "sent", "2026-09-16T14:00:30+09:00"
    db.commit()

    assert _run(db)["status"] == "ready"                                # 10/14: 두 번째
    second = [i for i in _items(db) if i.id != first.id]
    assert [i.contact_id for i in second] == [who.id]
    assert second[0].message == deals.meeting_decision_message(
        db, world["sender"], who, meeting)
    assert _refs(db) == [f"meeting30:{meeting.id}", f"meeting:{meeting.id}"]


def test_manual_reads_both_ref_shapes(db, users, world):
    from app.services import automation_runner as runner
    from app.services.automations import meeting_review as a7

    who = _contact(db, world, "홍길동", "가나다벤처스")
    meeting = _meeting(db, world, who)
    _hand_send(db, world, who, "2026-09-20T15:00:00+09:00")
    values = runner.values(None, "meeting_review")
    day = date(2026, 10, 14)

    def target(ref):
        return SimpleNamespace(ref=ref, contact_id=who.id)

    # 첫 번째는 쉬는 날(7일) 안만 본다 — 24일 전 것은 안 센다.
    assert a7.manual(db, values, target(f"meeting:{meeting.id}"), day) == ""
    assert "손으로" in a7.manual(db, values, target(f"meeting30:{meeting.id}"), day)
    assert a7.manual(db, values, target("meeting30:없음"), day) == ""


# ── 풀기 직전 ────────────────────────────────────────────────────────────────

def test_still_ok_reads_each_round_by_its_own_rules(db, users, world):
    from app.models import AutomationSend
    from app.services.automations import meeting_review as a7

    who = _contact(db, world, "홍길동", "가나다벤처스")
    meeting = _meeting(db, world, who, outcome="hold", followup_done=1)
    first = AutomationSend(automation="meeting_review", ref=f"meeting:{meeting.id}", test=0)
    second = AutomationSend(automation="meeting_review", ref=f"meeting30:{meeting.id}",
                            test=0)
    # 첫 번째의 판정은 그대로다.
    assert a7.still_ok(db, first) == "결과가 이미 적혀 있습니다"
    assert a7.still_ok(db, second) == ""
    meeting.outcome = None
    assert a7.still_ok(db, first) == "결과 문의를 이미 했습니다"
    assert a7.still_ok(db, second) == ""
    meeting.outcome = "pass"
    assert a7.still_ok(db, second) == "결과가 거절로 적혀 있습니다"
    meeting.outcome = "reviewing"
    meeting.followup_done = 0
    assert a7.still_ok(db, first) == "" and a7.still_ok(db, second) == ""
    # 다른 기업 건 뒤 미팅 — 첫 번째만 빠진다.
    _meeting(db, world, who, done=None, status="scheduled", scheduled_at="2026-10-20",
             company_name="샘플애그")
    assert a7.still_ok(db, first) == "그 뒤 미팅이 또 잡혀 있습니다"
    assert a7.still_ok(db, second) == ""
    _meeting(db, world, who, done=None, status="scheduled", scheduled_at="2026-10-20")
    assert a7.still_ok(db, first) == a7.still_ok(db, second) == "그 뒤 미팅이 또 잡혀 있습니다"
    assert a7.still_ok(db, AutomationSend(ref="meeting30:x")) == ""


def test_turning_the_second_off_drops_what_stands(db, users, world):
    """아침에 선 두 번째도 판에서 날수를 0 으로 두면 풀릴 때 빠진다 — 첫 번째는 그대로."""
    from app.services import automation_runner as runner, scheduled_send

    first = _contact(db, world, "홍길동", "가나다벤처스")
    second = _contact(db, world, "김철수", "라마바벤처스")
    _meeting(db, world, first, done=DONE2)
    _meeting(db, world, second)
    _turn_on(db)
    assert _run(db)["count"] == 2
    runner.save_params(db, "meeting_review", {"decision_days": "0"})
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    items = {i.contact_id: i for i in _items(db)}
    assert items[second.id].status == "canceled"
    assert "두 번째(투자 결정 문의)를 껐습니다" in items[second.id].error
    assert items[first.id].status == "pending" and items[first.id].job.status == "queued"


def test_a_pass_or_a_new_meeting_before_release_drops_it(db, users, world):
    from app.services import scheduled_send

    refused = _contact(db, world, "홍길동", "가나다벤처스")
    moved = _contact(db, world, "김철수", "라마바벤처스")
    held = _contact(db, world, "박보류", "차카타벤처스")
    first = _contact(db, world, "최첫번", "파하벤처스")
    m_refused = _meeting(db, world, refused)
    _meeting(db, world, moved)
    m_held = _meeting(db, world, held)
    m_first = _meeting(db, world, first, done=DONE2)
    _turn_on(db)
    assert _run(db)["count"] == 4

    m_refused.outcome = "pass"
    _meeting(db, world, moved, done=None, status="scheduled", scheduled_at="2026-10-21")
    m_held.outcome = "hold"      # 두 번째는 보류여도 묻는다
    m_first.outcome = "hold"     # 첫 번째는 결과가 적히면 빠진다(그대로)
    db.commit()
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    items = {i.contact_id: i for i in _items(db)}
    assert items[refused.id].status == "canceled"
    assert "거절" in items[refused.id].error
    assert items[moved.id].status == "canceled"
    assert "그 뒤 미팅" in items[moved.id].error
    assert items[first.id].status == "canceled"
    assert "결과가 이미 적혀" in items[first.id].error
    assert items[held.id].status == "pending"
    assert items[held.id].job.status == "queued"


# ── 3. 판의 값 ───────────────────────────────────────────────────────────────

def test_zero_days_turns_off_only_the_second(db, users, world):
    first = _contact(db, world, "홍길동", "가나다벤처스")
    second = _contact(db, world, "김철수", "라마바벤처스")
    _meeting(db, world, first, done=DONE2)
    _meeting(db, world, second)
    _turn_on(db, decision_days="0")
    assert _run(db)["status"] == "ready"
    assert {i.contact_id for i in _items(db)} == {first.id}


def test_the_round_time_is_the_earlier_of_the_two_times(db, users, world):
    from app.services import automation, automation_runner as runner
    from app.services.automations import meeting_review as a7

    day = date(2026, 10, 14)
    runner.save_params(db, "meeting_review", {"time": "15:00", "decision_time": "10:00"})
    row = automation.load(db, "meeting_review")
    assert a7.plan(db, row, day).at.strftime("%H:%M") == "10:00"
    # 두 번째를 안 물으면 그 시각은 회차를 앞당기지 않는다.
    runner.save_params(db, "meeting_review", {"time": "15:00", "decision_time": "10:00",
                                              "decision_days": "0"})
    assert a7.plan(db, automation.load(db, "meeting_review"), day).at.strftime(
        "%H:%M") == "15:00"


def test_second_must_come_after_first(db, users):
    from app.services import automation, automation_runner as runner

    for bad in ({"days": "5", "decision_days": "5"}, {"days": "5", "decision_days": "3"},
                {"decision_days": "91"}, {"decision_days": "-1"}):
        with pytest.raises(ValueError):
            runner.save_params(db, "meeting_review", bad)
    runner.save_params(db, "meeting_review", {"days": "5", "decision_days": "0"})
    runner.save_params(db, "meeting_review", {"days": "5", "decision_days": "6"})
    # 기본은 그대로 꺼짐 · 시험 모드다.
    row = automation.load(db, "meeting_review")
    assert (row.enabled, row.test_mode) == (0, 1)


def test_a_separate_second_time_gets_its_own_round(db, users, world):
    first = _contact(db, world, "홍길동", "가나다벤처스")
    second = _contact(db, world, "김철수", "라마바벤처스")
    _meeting(db, world, first, done=DONE2)
    _meeting(db, world, second)
    _turn_on(db, decision_time="10:30")
    result = _run(db)
    assert result["status"] == "ready" and len(result["job_ids"]) == 2
    jobs = {i.contact_id: i.job for i in _items(db)}
    assert _when(jobs[second.id]) == "10/14(수) 10:30"
    assert _when(jobs[first.id]) == "10/14(수) 14:00"


def test_both_times_must_be_inside_the_team_window(db, users):
    from app.services import automation, automation_runner as runner

    vals = runner.values(None, "meeting_review")
    vals["decision_time"] = "16:00"
    assert runner.times_of("meeting_review", vals) == ["14:00", "16:00"]
    automation.save_team(db, user_id=None, values={"window_start": "10:00",
                                                    "window_end": "15:00"})
    with pytest.raises(ValueError, match="시간대"):
        runner.save_params(db, "meeting_review", {"decision_time": "16:00"})
    runner.save_params(db, "meeting_review", {"decision_time": "11:00"})


def test_panel_shows_and_saves_the_second_round(client, db, users, world):
    from app.services import automation, automation_runner as runner

    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    page = client.get("/team").text
    assert 'name="p_decision_days"' in page and 'name="p_decision_time"' in page
    assert "두 번째 — 투자 결정 문의(며칠 뒤)" in page
    client.post("/team/automations/meeting_review", data={
        "enabled": "", "test_mode": "on", "test_mode_shown": "1",
        "test_room": TEST_ROOM, "p_days": "2", "p_time": "14:00",
        "p_decision_days": "45", "p_decision_time": "15:30"},
        follow_redirects=False)
    db.expire_all()
    vals = runner.values(automation.load(db, "meeting_review"), "meeting_review")
    assert (vals["decision_days"], vals["decision_time"]) == (45, "15:30")


# ── 같은 날 겹치면 ───────────────────────────────────────────────────────────

def test_first_and_second_for_one_contact_on_one_day_is_one_message(db, users, world):
    """한 분의 미팅 둘이 같은 날로 적혔는데 하나는 그날, 하나는 한 달 늦게 완료로
    적혔다 — 그 분께 첫 번째와 두 번째가 같은 날 선다. 날짜가 같아 '그 뒤 미팅'
    규칙에는 안 걸린다."""
    from app.routers import deals

    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who, outcome="investing")                         # 두 번째
    _meeting(db, world, who, done=DONE2, scheduled_at=DONE30,
             company_name="샘플애그")                                       # 첫 번째
    _turn_on(db)
    result = _run(db)
    assert result["status"] == "ready"
    [item] = _items(db)
    assert item.message == deals.review_message(db, world["sender"], who)   # 첫 번째가 앞
    assert any("중복 방지" in line for line in result["skipped"])


def test_two_second_rounds_for_one_contact_on_one_day_is_one_message(db, users, world):
    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who, company_name="샘플바이오")
    _meeting(db, world, who, company_name="샘플애그")
    _turn_on(db)
    result = _run(db)
    assert len(_items(db)) == 1
    assert any("같은 담당자에게 이미 한 통이 실렸습니다" in line for line in result["skipped"])


# ── 시험 모드 ────────────────────────────────────────────────────────────────

def test_test_mode_goes_to_the_test_room(db, users, world):
    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who)
    _turn_on(db, test=True)
    assert _run(db)["status"] == "ready"
    [item] = _items(db)
    assert item.room_name == TEST_ROOM and item.contact_id is None
    assert "원래 받을 방: 홍길동 가나다벤처스 Deal 공유" in item.message
    assert "샘플바이오 관련하여" in item.message


# ── 4. 글 ────────────────────────────────────────────────────────────────────

def test_the_message_is_the_greeting_plus_the_decision_text(db, users, world):
    from app.routers import deals

    who = _contact(db, world, "홍길동", "가나다벤처스")
    meeting = _meeting(db, world, who, company_name="  샘플바이오 ")
    _turn_on(db)
    _run(db)
    [item] = _items(db)
    assert item.message == (
        "안녕하세요, 홍길동 심사역님\n우리브이씨 ASSET입니다.\n\n"
        + DEFAULT_TEXT.replace("{미팅 기업}", "샘플바이오") + "\n")
    assert item.message == deals.meeting_decision_message(db, world["sender"], who, meeting)
    # 첫 번째(미팅 후기)와는 다른 글이다.
    assert item.message != deals.review_message(db, world["sender"], who)


def test_a_blank_company_still_reads(db, users, world):
    from app.routers import deals

    who = _contact(db, world, "홍길동", "가나다벤처스")
    meeting = _meeting(db, world, who, company_name="  ")
    text = deals.meeting_decision_message(db, world["sender"], who, meeting)
    assert "지난번 미팅하셨던 기업 관련하여 다시 연락드립니다." in text
    assert "{" not in text


def test_the_placeholder_never_goes_out_as_is(db, users, world):
    """팀이 고친 문구 · 인사말에 적힌 자리 · 띄어쓰기 없이 적은 자리도 채운다."""
    from app.models import MessageTemplate

    db.add(MessageTemplate(user_id=None, kind="meeting_review_decision",
                           body="{미팅기업} 건 투자 결정이 나셨을까요?", is_active=1))
    db.add(MessageTemplate(user_id=None, kind="opening_first",
                           body="안녕하세요, {담당자명} {직함}\n{미팅 기업} 미팅 감사했습니다.",
                           is_active=1))
    db.commit()
    who = _contact(db, world, "홍길동", "가나다벤처스")
    _meeting(db, world, who, company_name="샘플애그")
    _turn_on(db)
    _run(db)
    [item] = _items(db)
    assert "{미팅" not in item.message
    assert "샘플애그 미팅 감사했습니다." in item.message
    assert "샘플애그 건 투자 결정이 나셨을까요?" in item.message


def test_the_seed_is_the_code_fallback(db, users):
    """둘이 갈리면 문구틀을 지운 사람만 다른 글을 받는다."""
    from app.models import MessageTemplate
    from app.routers import deals
    from scripts import bootstrap

    seeds = dict(bootstrap.TEAM_TEMPLATES)
    assert deals.MEETING_DECISION_FALLBACK == DEFAULT_TEXT
    assert seeds[deals.MEETING_DECISION_KIND] == deals.MEETING_DECISION_FALLBACK
    # 미팅 요청 두 번째도 같은 약속이다.
    assert seeds[deals.MEETING_ASK_AGAIN_KIND] == deals.MEETING_ASK_AGAIN_FALLBACK

    bootstrap.bootstrap(db)
    db.commit()
    row = db.execute(select(MessageTemplate).where(
        MessageTemplate.kind == deals.MEETING_DECISION_KIND)).scalars().one()
    assert (row.user_id, row.body, row.is_active) == (None, DEFAULT_TEXT, 1)


def test_the_kind_is_on_the_templates_page(client, db, users):
    from app.models import MessageTemplate
    from app.routers.templates_crud import KIND_LABELS, VARIABLES
    from scripts import bootstrap

    assert KIND_LABELS["meeting_review_decision"] == "문구만 — 미팅 30일 뒤 투자 결정 문의"
    assert "미팅 30일 뒤 투자 결정 문의에서만" in dict(VARIABLES)["{미팅 기업}"]
    bootstrap.bootstrap(db)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    page = client.get("/templates")
    assert page.status_code == 200
    assert 'id="meeting_review_decision"' in page.text
    assert "문구만 — 미팅 30일 뒤 투자 결정 문의" in page.text
    assert "{미팅 기업}" in page.text

    # 각자 고쳐 쓸 수 있다.
    r = client.post("/templates/new", data={"kind": "meeting_review_decision",
                                            "name": "내 문구",
                                            "body": "{미팅 기업} 건 여쭙습니다."},
                    follow_redirects=False)
    assert r.status_code == 303
    mine = db.execute(select(MessageTemplate).where(
        MessageTemplate.kind == "meeting_review_decision",
        MessageTemplate.user_id == users["u1"].id)).scalars().one()
    assert mine.body == "{미팅 기업} 건 여쭙습니다."
    assert client.get("/templates").status_code == 200


def _panel(page: str, kind: str) -> str:
    """문구 화면에서 한 종류의 구간(`<div class="panel" id="종류">` 부터 다음 구간 전까지)."""
    start = page.index(f'<div class="panel" id="{kind}">')
    end = page.find('<div class="panel"', start + 1)
    return page[start:end if end != -1 else len(page)]


def test_the_templates_page_says_the_days_set_on_the_panel(client, db, users):
    """미팅 후기 · 투자 결정 문의의 설명은 팀 현황 › 자동화의 A7 날수를 읽는다 —
    '열흘쯤' 처럼 글에 박힌 날수가 판(첫 번째 2일)과 어긋나지 않게."""
    import re
    from pathlib import Path

    from app.services import automation_runner as runner
    from scripts import bootstrap

    bootstrap.bootstrap(db)
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    page = client.get("/templates").text
    review, decision = _panel(page, "meeting_review"), _panel(page, "meeting_review_decision")
    assert "열흘" not in review
    assert "미팅 완료 2일 뒤" in review
    assert "미팅 완료 30일 뒤" in decision

    runner.save_params(db, "meeting_review", {"days": "3", "decision_days": "45"})
    db.commit()
    page = client.get("/templates").text
    assert "미팅 완료 3일 뒤" in _panel(page, "meeting_review")
    assert "미팅 완료 45일 뒤" in _panel(page, "meeting_review_decision")

    runner.save_params(db, "meeting_review", {"days": "3", "decision_days": "0"})
    db.commit()
    decision = _panel(client.get("/templates").text, "meeting_review_decision")
    assert "날수가 0 이라 안 나갑니다" in decision and "미팅 완료" not in decision

    # 제목은 한 줄 — 오른쪽 설명이 길면 설명 쪽이 접힌다(제목이 `… 결정 문 / 의` 로
    # 갈리던 것).
    assert 'class="panel-title tpl-kind-title"' in page
    css = (Path(__file__).resolve().parent.parent / "app" / "static" / "css"
           / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\.tpl-kind-title \.hint\s*\{[^}]*flex:\s*1 1 0", css)
