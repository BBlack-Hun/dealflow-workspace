"""2단계 자동화의 **업무용 PC 약속** — 누가 · 언제 · 겹치지 않게 · 띄워서.

자동 발송은 한 사람(자동 발송 계정)의 업무용 PC 에서 나간다. 그래서 지킨다:

1. **자동 발송 계정** — 팀 공통 칸 하나(안 골랐으면 스타트업 월간 발송 계정).
   회차가 그 계정 것으로 서서 그 계정 기기만 집어간다. 자동화마다 바꾸면
   판이 경고한다.
2. **시각** — 자동화 다섯 모두 보낼 시각을 고친다. 팀의 가능 시간대(발송
   안전장치 09~19시 안) 밖은 받지 않고, 피할 시간에 떨어진 회차는 끝나는 분으로
   밀린다. 다른 자동화 회차와는 `자동 회차 사이 최소 간격` 을 둔다.
3. **중복 막기** — 같은 분 하루 N통(기본 1, 자동화끼리도) · 같은 방(띄어쓰기 ·
   대소문자 무시) · 손으로 먼저 보낸 것. 세울 때와 **풀 때** 두 번 본다. 뺀 곳과
   까닭은 오늘 할 일 · 회차 화면에 남는다.
4. **건 사이 간격** — 자동 회차를 내줄 때 잡에 `delay_min_sec`/`delay_max_sec`
   를 싣고, 발송기(0.11.8~)는 그 잡에서만 그 폭으로 쉰다. 낡은 발송기에는 자동
   회차를 안 내준다. 앞 자동 회차가 끝난 뒤 간격이 지나야 다음 자동 회차가
   내려간다.
"""
from __future__ import annotations

import importlib
from datetime import datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

# 2026-10-14 는 수요일.
WED_9AM = datetime(2026, 10, 14, 9, 0)
TEST_ROOM = "자동화 시험방"
KINDS = {"kinds": "deal_intro,ir_delivery,sourcing_intro,test_send"}


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def world(db, users):
    """가짜 자동화 둘(A = 미팅 후 문의 자리, B = 미팅 요청 자리) — 매일, 정한 시각.

    보내는 계정은 u2(스타트업 월간 발송 계정) — 두 기기 모두 지금 판이다.
    """
    from app import version
    from app.models import AgentDevice, AutoSendSetting, VcContact
    from app.services import automation, automation_runner as runner

    runner._load_all()
    saved = dict(runner.REGISTRY)
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    for device in db.query(AgentDevice).all():
        device.agent_version = version.VERSION

    def contact(owner, name, firm, room):
        row = VcContact(user_id=owner.id, name=name, firm=firm, title="심사역",
                        kakao_room_name=room, connect_stage="connected",
                        source_sheet="내 명단")
        db.add(row)
        db.flush()
        return row

    people = {
        "c1": contact(users["u1"], "홍길동", "가나다벤처스", "홍길동 가나다벤처스 Deal 공유"),
        "c2": contact(users["u1"], "김철수", "라마바벤처스", "김철수 라마바벤처스 Deal 공유"),
        # 같은 투자사가 다른 팀원 명단에 또 — 보내는 계정 카톡에서는 같은 방이다.
        "c1dup": contact(users["u2"], "홍길동", "가나다벤처스", "홍길동  가나다벤처스 deal 공유"),
    }
    db.commit()
    state = {"A": [], "B": [], "at": {"A": "14:00", "B": "14:00"}, "manual": {},
             "people": people}

    def make(key, name):
        def plan(db, row, day):
            hour, minute = (int(p) for p in state["at"][name].split(":"))
            return runner.Plan(period=runner.day_key(day),
                               at=datetime(day.year, day.month, day.day,
                                           hour, minute).astimezone())

        def collect(db, row, sender, plan_):
            return runner.Batch(note=f"{name} 대상 없음", outs=[
                automation.Out(room=c.kakao_room_name, message=f"{name} — {c.name} 님께",
                               contact_id=c.id, stage=3, ref=f"{name}:{c.id}")
                for c in state[name]])

        def manual(db, values, contact_id, sourcing_id, day):
            return state["manual"].get(contact_id, "")

        return runner.Spec(key=key, kind="deal_intro", plan=plan, collect=collect,
                           manual=manual)

    runner.REGISTRY.clear()
    runner.register(make(automation.MEETING_REVIEW, "A"))
    runner.register(make(automation.MEETING_REQUEST, "B"))
    try:
        yield state
    finally:
        runner.REGISTRY.clear()
        runner.REGISTRY.update(saved)


def _on(db, key, *, test=False):
    from app.services import automation

    return automation.save(db, key, enabled=True, user_id=None, test_mode=test,
                           test_room=TEST_ROOM)


def _run(db, key, now=WED_9AM):
    from app.services import automation_runner as runner

    return runner.run_once(db, key, _aware(now))


def _jobs(db):
    from app.models import SendJob

    db.expire_all()
    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


def _hhmm(job):
    from app.services import scheduled_send

    return scheduled_send.scheduled_at(job).strftime("%H:%M")


# ── 1. 자동 발송 계정 ────────────────────────────────────────────────────────

def test_team_defaults(db, users):
    from app.services import automation

    team = automation.team(db)
    assert (team.window_start, team.window_end, team.avoid_start, team.avoid_end,
            team.per_contact_daily, team.job_gap_min) == ("09:00", "19:00", "", "", 1, 10)


def test_the_team_auto_send_account_is_the_default_sender(client, db, users, world,
                                                          monkeypatch):
    from app import clock
    from app.services import automation

    # 안 골랐으면 스타트업 월간 발송 계정(u2).
    assert automation.default_sender_id(db) == users["u2"].id
    automation.save_team(db, user_id=users["u1"].id, values={})
    assert automation.default_sender_id(db) == users["u1"].id
    # 자동화마다 따로 안 골랐으면 그 계정에서 나간다 — 회차도 그 계정 것.
    world["A"] = [world["people"]["c2"]]
    _on(db, "meeting_review")
    assert automation.sender(db, automation.load(db, "meeting_review")).id == users["u1"].id
    _run(db, "meeting_review")
    [job] = _jobs(db)
    assert job.user_id == users["u1"].id
    # 풀린 뒤 — 그 계정 기기만 받는다. 다른 팀원 기기는 아무것도 못 받는다.
    _release_at(db, monkeypatch, 14, 0)
    assert client.get("/api/agent/poll", params=KINDS,
                      headers=auth(OTHER_TOKEN)).status_code == 204
    got = client.get("/api/agent/poll", params=KINDS, headers=auth(DEMO_TOKEN))
    assert got.status_code == 200 and got.json()["job_id"] == job.id


def test_a_per_automation_sender_that_differs_is_flagged(db, users, world):
    from app.services import automation

    automation.save(db, "meeting_review", enabled=False, user_id=users["u1"].id,
                    test_mode=True, test_room=TEST_ROOM)
    rows = {r["key"]: r for r in automation.status(db)["rows"]}
    assert rows["meeting_review"]["sender_differs"] is True
    assert "다른 계정" in rows["meeting_review"]["sender_warning"]
    assert rows["meeting_request"]["sender_differs"] is False


@pytest.mark.parametrize("values, why", [
    ({"window_start": "08:00", "window_end": "19:00"}, "09:00~19:00"),
    ({"window_start": "15:00", "window_end": "11:00"}, "09:00~19:00"),
    ({"window_end": "19:30"}, "09:00~19:00"),
    ({"avoid_start": "12:00"}, "함께"),
    ({"avoid_start": "08:00", "avoid_end": "09:30"}, "시간대 안"),
    ({"window_start": "10:00", "window_end": "12:00", "avoid_start": "10:00",
      "avoid_end": "12:00"}, "전체"),
    ({"per_contact_daily": "0"}, "1~"),
    ({"job_gap_min": "500"}, "0~"),
])
def test_team_values_are_checked_where_they_are_saved(db, users, values, why):
    from app.services import automation

    with pytest.raises(ValueError) as caught:
        automation.save_team(db, user_id=None, values=values)
    assert why in str(caught.value)


def test_the_team_form_is_admin_only_and_saves(client, db, users):
    from app.services import automation

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.post("/team/automation-team", data={"window_start": "10:00"},
                       follow_redirects=False).status_code in (303, 403)
    assert automation.team(db).window_start == "09:00"

    users["u1"].role = "admin"
    db.commit()
    page = client.get("/team").text
    assert 'data-testid="automation-team-form"' in page
    client.post("/team/automation-team", data={
        "user_id": str(users["u2"].id), "window_start": "10:00", "window_end": "18:00",
        "avoid_start": "12:00", "avoid_end": "13:00", "per_contact_daily": "1",
        "job_gap_min": "15"}, follow_redirects=False)
    db.expire_all()
    team = automation.team(db)
    assert (team.sender_id, team.window_label, team.avoid_label, team.job_gap_min) == (
        users["u2"].id, "10:00~18:00", "12:00~13:00", 15)


# ── 2. 시각 ──────────────────────────────────────────────────────────────────

def test_fit_moves_forward_only():
    from app.services.automation import Team

    team = Team(avoid_start="12:00", avoid_end="13:00")
    at = lambda h, m, s=0: _aware(datetime(2026, 10, 14, h, m, s))  # noqa: E731
    assert team.fit(at(14, 0)) == at(14, 0)
    assert team.fit(at(12, 30)) == at(13, 0)
    assert team.fit(at(8, 0)) == at(9, 0)
    assert team.fit(at(18, 59, 30)) is None
    assert Team(window_end="17:00").fit(at(17, 0)) is None


def test_every_automation_has_an_editable_time_and_item_gap(db, users):
    """다섯 모두 — 보낼 시각(과 날 규칙)을 판에서 고치고, 건 사이 간격도 고친다."""
    from app.services import automation, automation_runner as runner

    runner._load_all()
    for kind in automation.KINDS:
        state = runner.status_of(db, kind.key)
        names = {f["name"] for f in state["fields"]}
        assert {"item_gap_min", "item_gap_max"} <= names, kind.key
        assert runner.times_of(kind.key, runner.values(None, kind.key)), kind.key
    # 미팅 요청은 첫 번째 · 두 번째 시각을 따로 고친다.
    names = {f["name"] for f in runner.status_of(db, "meeting_request")["fields"]}
    assert {"time", "second_time", "first_days", "second_days"} <= names


def test_times_outside_the_team_window_are_refused(db, users):
    from app.services import automation, automation_runner as runner

    automation.save_team(db, user_id=None, values={"window_start": "10:00",
                                                    "window_end": "17:00"})
    with pytest.raises(ValueError, match="시간대"):
        runner.save_params(db, "meeting_review", {"time": "09:30"})
    with pytest.raises(ValueError, match="시간대"):
        runner.save_params(db, "startup_monthly", {"slots": "15 11:00\n20 17:30"})
    with pytest.raises(ValueError, match="시간대"):
        runner.save_params(db, "meeting_request", {"time": "14:00", "second_time": "17:00"})
    runner.save_params(db, "meeting_review", {"time": "12:00"})
    with pytest.raises(ValueError, match="09:00~19:00"):
        runner.save_params(db, "channel_top", {"time": "20:00"})
    with pytest.raises(ValueError, match="건 사이"):
        runner.save_params(db, "channel_top", {"item_gap_min": "90", "item_gap_max": "30"})


def test_a_job_in_the_avoided_slot_moves_to_its_end(db, users, world):
    from app.services import automation

    automation.save_team(db, user_id=None, values={"avoid_start": "13:30",
                                                    "avoid_end": "14:30"})
    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    assert _run(db, "meeting_review")["status"] == "ready"
    [job] = _jobs(db)
    assert _hhmm(job) == "14:30"


def test_a_second_automation_keeps_the_gap(db, users, world):
    from app.services import automation

    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c2"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    _run(db, "meeting_request")
    first, second = _jobs(db)
    assert (_hhmm(first), _hhmm(second)) == ("14:00", "14:10")


def test_no_gap_when_the_team_sets_zero(db, users, world):
    from app.services import automation

    automation.save_team(db, user_id=None, values={"job_gap_min": "0"})
    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c2"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    _run(db, "meeting_request")
    assert [_hhmm(j) for j in _jobs(db)] == ["14:00", "14:00"]


def test_a_job_pushed_past_the_window_is_not_sent_that_day(db, users, world):
    from app.services import automation

    automation.save_team(db, user_id=None, values={"window_end": "14:05"})
    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c2"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    result = _run(db, "meeting_request")
    assert result["status"] == "empty"
    assert "시간대" in "; ".join(result["skipped"])


# ── 3. 중복 막기 ─────────────────────────────────────────────────────────────

def test_one_automated_message_per_person_per_day_across_automations(db, users, world):
    from app.models import AutoSendRun
    from app.services import automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c1"], world["people"]["c2"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    result = _run(db, "meeting_request")
    assert result["count"] == 1
    _first, second = _jobs(db)
    assert [i.contact_id for i in second.items] == [world["people"]["c2"].id]
    assert any("중복 방지" in line for line in result["skipped"])

    run = db.execute(select(AutoSendRun).where(
        AutoSendRun.kind == "auto:meeting_request")).scalars().one()
    assert "뺀 곳 1(중복 방지 1)" in run.error
    # 보내는 계정의 오늘 할 일과 회차 화면에 남는다.
    lines = runner.today_items(db, users["u2"], _aware(datetime(2026, 10, 14, 10, 0)))
    assert any("뺀 곳 1(중복 방지 1)" in line["title"] for line in lines)
    notes = runner.job_notes(db, second)
    assert notes["count"] == 1 and notes["dup"] == 1 and notes["gap"] == "20~60초"


def test_the_limit_is_a_team_setting(db, users, world):
    from app.services import automation

    automation.save_team(db, user_id=None, values={"per_contact_daily": "2"})
    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    assert _run(db, "meeting_request")["count"] == 1


def test_the_same_room_under_two_owners_gets_one_message(db, users, world):
    world["A"] = [world["people"]["c1"], world["people"]["c1dup"], world["people"]["c2"]]
    _on(db, "meeting_review")
    result = _run(db, "meeting_review")
    assert result["count"] == 2
    assert any("같은 방" in line for line in result["skipped"])


def test_test_mode_counts_only_test_mode(db, users, world):
    """시험으로 실린 것은 실제 발송을 막지 않는다 — 시험끼리만 센다."""
    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c1"]]
    _on(db, "meeting_review", test=True)
    _on(db, "meeting_request", test=False)
    _run(db, "meeting_review")
    assert _run(db, "meeting_request")["count"] == 1


def test_a_manual_send_skips_it(db, users, world):
    world["A"] = [world["people"]["c1"], world["people"]["c2"]]
    world["manual"][world["people"]["c1"].id] = "중복 방지 — 손으로 보냈습니다"
    _on(db, "meeting_review")
    result = _run(db, "meeting_review")
    assert result["count"] == 1
    assert any("손으로" in line for line in result["skipped"])


def test_release_checks_again_against_released_automation_jobs(db, users, world):
    """세운 뒤 다른 자동 회차가 먼저 풀려 같은 분께 나갔으면, 풀 때 뺀다."""
    from app.models import AutomationSend, DealBatch, SendItem, SendJob
    from app.services import scheduled_send

    c1 = world["people"]["c1"]
    world["A"] = [c1, world["people"]["c2"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")

    batch = DealBatch(user_id=users["u2"].id, title="다른 자동화", sent_date="2026-10-14",
                      cycle_type="auto")
    db.add(batch)
    db.flush()
    other = SendJob(user_id=users["u2"].id, kind="deal_intro", batch_id=batch.id,
                    status="done", total=1, sent=1, failed=0,
                    scheduled_at="2026-10-14T11:00:00+09:00")
    db.add(other)
    db.flush()
    item = SendItem(job_id=other.id, contact_id=c1.id, channel="kakao",
                    room_name=c1.kakao_room_name, message="먼저", status="sent",
                    sent_at="2026-10-14T11:00:05+09:00")
    db.add(item)
    db.flush()
    db.add(AutomationSend(automation="meeting_request", ref="other:1", test=0,
                          job_id=other.id, item_id=item.id, room=c1.kakao_room_name,
                          contact_id=c1.id))
    db.commit()

    released = scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    assert released["count"] == 1
    job = _jobs(db)[0]
    by_contact = {i.contact_id: i for i in job.items}
    assert by_contact[c1.id].status == "canceled"
    assert by_contact[c1.id].error.startswith("자동 제외 — 중복 방지")
    assert by_contact[world["people"]["c2"].id].status == "pending"


def test_release_checks_manual_sends_again(db, users, world):
    from app.services import scheduled_send

    c1 = world["people"]["c1"]
    world["A"] = [c1]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    world["manual"][c1.id] = "중복 방지 — 14시 전에 손으로 보냈습니다"
    assert scheduled_send.run_once(
        db, _aware(datetime(2026, 10, 14, 14, 0, 20)))["count"] == 0
    [job] = _jobs(db)
    assert job.status == "canceled"
    assert "손으로" in job.items[0].error


def test_real_meeting_review_skips_a_meeting_message_sent_by_hand(db, users):
    """A7 — 7일 안에 사람이 미팅 단계 글을 보낸 분께는 안 묻는다."""
    from app.models import (AutoSendSetting, DealBatch, Meeting, SendItem, SendJob,
                            VcContact)
    from app.services import automation, automation_runner as runner

    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    who = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나다벤처스",
                    title="심사역", kakao_room_name="홍길동 가나다벤처스 Deal 공유",
                    connect_stage="connected", source_sheet="내 명단")
    db.add(who)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=who.id, scheduled_at="2026-10-12",
                   status="done", done_at="2026-10-12", outcome="reviewing"))
    batch = DealBatch(user_id=users["u1"].id, title="미팅 후기", sent_date="2026-10-13",
                      cycle_type="adhoc")
    db.add(batch)
    db.flush()
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done", total=1, sent=1, failed=0)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=who.id, stage=3, channel="kakao",
                    room_name=who.kakao_room_name, message="어떻게 보셨는지요",
                    status="sent", sent_at="2026-10-13T15:00:00+09:00"))
    db.commit()

    automation.save(db, "meeting_review", enabled=True, user_id=None, test_mode=False,
                    test_room=TEST_ROOM)
    result = runner.run_once(db, "meeting_review", _aware(WED_9AM))
    assert result["status"] == "empty"
    assert any("손으로" in line for line in result["skipped"])

    # 쉬는 날을 0 으로 두면 안 본다.
    runner.save_params(db, "meeting_review", {"manual_days": "0"})
    from app.models import AutoSendRun

    db.execute(AutoSendRun.__table__.delete())
    db.commit()
    assert runner.run_once(db, "meeting_review", _aware(WED_9AM))["status"] == "ready"


# ── 4. 건 사이 간격 · 발송기 판 · 회차 사이 간격 ─────────────────────────────

def _release_at(db, monkeypatch, hh, mm):
    from app import clock
    from app.services import scheduled_send

    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, hh, mm, 20)))
    monkeypatch.setattr(clock, "now",
                        lambda: _aware(datetime(2026, 10, 14, hh, mm, 30)))


def test_poll_carries_the_item_gap_and_needs_a_new_agent(client, db, users, world,
                                                         monkeypatch):
    from app.models import AgentDevice, DealBatch, SendItem, SendJob
    from app.services import automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    runner.save_params(db, "meeting_review", {"item_gap_min": "30", "item_gap_max": "90"})
    _run(db, "meeting_review")
    _release_at(db, monkeypatch, 14, 0)
    [auto_job] = _jobs(db)
    assert auto_job.status == "queued"

    # 사람이 누른 회차 하나(같은 계정).
    batch = DealBatch(user_id=users["u2"].id, title="딜 소개", sent_date="2026-10-14",
                      cycle_type="adhoc")
    db.add(batch)
    db.flush()
    manual = SendJob(user_id=users["u2"].id, kind="deal_intro", batch_id=batch.id,
                     status="queued", total=1, sent=0, failed=0)
    db.add(manual)
    db.flush()
    db.add(SendItem(job_id=manual.id, contact_id=world["people"]["c2"].id,
                    channel="kakao", room_name="김철수 라마바벤처스 Deal 공유",
                    message="딜 소개", status="pending"))
    device = db.query(AgentDevice).filter_by(user_id=users["u2"].id).first()
    device.agent_version = "0.11.7"
    db.commit()

    # 낡은 발송기 — 자동 회차는 안 받고, 사람이 누른 회차는 그대로 받는다(간격 칸 없이).
    got = client.get("/api/agent/poll", params=KINDS, headers=auth(OTHER_TOKEN))
    assert got.status_code == 200 and got.json()["job_id"] == manual.id
    assert "delay_min_sec" not in got.json()
    assert client.get("/api/agent/poll", params=KINDS,
                      headers=auth(OTHER_TOKEN)).status_code == 204
    # 회차 화면이 왜 안 내려가는지 말한다.
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    guard = client.get(f"/api/jobs/{auto_job.id}").json()["guard"]
    assert guard["held"] is True and "0.11.8" in guard["sentence"]

    # 새 판이 폴링 때 판 번호를 밝히면 받는다 — 간격이 실려 온다.
    got = client.get("/api/agent/poll", params={**KINDS, "version": "0.11.8"},
                     headers=auth(OTHER_TOKEN))
    assert got.status_code == 200 and got.json()["job_id"] == auto_job.id
    assert (got.json()["delay_min_sec"], got.json()["delay_max_sec"]) == (30, 90)


def test_the_next_automation_job_waits_for_the_gap_after_the_last_one(
        client, db, users, world, monkeypatch):
    from app import clock

    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c2"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    _run(db, "meeting_request")
    first, second = _jobs(db)
    assert (_hhmm(first), _hhmm(second)) == ("14:00", "14:10")

    _release_at(db, monkeypatch, 14, 0)
    got = client.get("/api/agent/poll", params=KINDS, headers=auth(OTHER_TOKEN))
    assert got.json()["job_id"] == first.id
    # 앞 회차가 길게 가서 14:08 에 끝났다 — 14:10 에 풀린 다음 회차는 14:18 까지 선다.
    first = _jobs(db)[0]
    first.status = "done"
    first.finished_at = _aware(datetime(2026, 10, 14, 14, 8)).isoformat(timespec="seconds")
    db.commit()
    _release_at(db, monkeypatch, 14, 10)
    assert client.get("/api/agent/poll", params=KINDS,
                      headers=auth(OTHER_TOKEN)).status_code == 204
    monkeypatch.setattr(clock, "now", lambda: _aware(datetime(2026, 10, 14, 14, 18, 30)))
    got = client.get("/api/agent/poll", params=KINDS, headers=auth(OTHER_TOKEN))
    assert got.status_code == 200 and got.json()["job_id"] == second.id


# ── 발송기 ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def agent_main():
    return importlib.import_module("agent.main")


CFG = {"delay_min_sec": 3, "delay_max_sec": 7, "part_gap_sec": 0, "job_cap": 60,
       "cancel_check_retries": 1, "cancel_check_backoff_sec": 0}


def test_the_agent_uses_the_jobs_gap_only_when_it_is_sane(agent_main):
    assert agent_main.job_delay({"job_id": 1}, CFG) == (3.0, 7.0)
    assert agent_main.job_delay({"delay_min_sec": 20, "delay_max_sec": 60}, CFG) == (20.0, 60.0)
    assert agent_main.job_delay({"delay_min_sec": 0, "delay_max_sec": 0}, CFG) == (3.0, 7.0)
    assert agent_main.job_delay({"delay_min_sec": 60, "delay_max_sec": 20}, CFG) == (3.0, 7.0)
    assert agent_main.job_delay({"delay_min_sec": "x", "delay_max_sec": 2}, CFG) == (3.0, 7.0)


def test_the_agent_rests_the_jobs_gap_between_items(agent_main, monkeypatch):
    rests = []

    class Result:
        ok, error, screenshot_b64 = True, None, None

    class Sender:
        name = "test"

        def send_text(self, room, text):
            return Result()

    class Client:
        def job_state(self, _job_id):
            return {"ok": True, "status": "running", "canceled": False,
                    "canceled_items": []}

        def report_item(self, *_a, **_k):
            pass

        def report_job(self, *_a, **_k):
            pass

        def report_diagnostics(self, *_a, **_k):
            pass

    monkeypatch.setattr(agent_main.random, "uniform", lambda low, high: (low, high))
    monkeypatch.setattr(agent_main.time, "sleep", lambda value: rests.append(value))
    job = {"job_id": 7, "kind": "deal_intro", "delay_min_sec": 20, "delay_max_sec": 60,
           "items": [{"id": n, "room_name": f"방{n}", "message": "안녕하세요"}
                     for n in (1, 2, 3)]}
    agent_main.process_job(Client(), Sender(), job, CFG)
    assert rests == [(20.0, 60.0), (20.0, 60.0)]

    rests.clear()
    job.pop("delay_min_sec")
    job.pop("delay_max_sec")
    agent_main.process_job(Client(), Sender(), job, CFG)
    assert rests == [(3.0, 7.0), (3.0, 7.0)]


def test_the_agent_tells_its_version_when_it_polls():
    from pathlib import Path

    text = Path("agent/main.py").read_text(encoding="utf-8")
    assert '"version": self.version' in text


def test_the_automation_agent_version_is_this_release():
    from app import version

    assert version.AUTOMATION_AGENT_VERSION == version.VERSION
    assert version.agent_handles_automation(version.VERSION)
    assert not version.agent_handles_automation("0.11.7")
    assert not version.agent_handles_automation(None)
