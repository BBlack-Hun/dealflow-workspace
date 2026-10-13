"""2단계 자동화 공통 틀 — **아침에 세우고, 정한 시각에, 한 번만.**

가짜 자동화 하나를 틀에 달아(`Spec`) 틀이 지키는 것을 본다.

1. 꺼져 있으면 아무 일도 없다.
2. 그날이 아니면 · 08시 전이면 · 나갈 시각이 지났으면 세우지 않는다.
3. 세우면 **보내는 계정 것**의 `draft` 회차가 그 시각 예약으로 선다.
   시험 모드면 `test_send` 이고 시험방으로 간다.
4. 같은 회차는 두 번 서지 않고(`auto_send_runs`), 같은 대상은 두 번 안 간다
   (`automation_sends`). 시험으로 보낸 것은 실제 발송을 막지 않는다.
5. 0건이면 세우지 않고 그날 다시 본다 — 사유는 오늘 할 일에 선다.
6. 띄워 보내기(`spacing`) — 한 통마다 회차를 따로, 분 단위로 띄워 세운다.
7. 예약이 풀리기 직전 `still_ok` 로 다시 보고 더는 보낼 까닭이 없는 건을 뺀다.
8. 풀린 회차는 보내는 계정의 발송기만 집어간다.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_TOKEN, OTHER_TOKEN, auth

# 2026-10-14 는 수요일.
WED_9AM = datetime(2026, 10, 14, 9, 0)
WED_7AM = datetime(2026, 10, 14, 7, 0)
WED_3PM = datetime(2026, 10, 14, 15, 0)
THU_9AM = datetime(2026, 10, 15, 9, 0)
TEST_ROOM = "자동화 시험방"


def _aware(when):
    return when.astimezone()


@pytest.fixture()
def fake(db, users):
    """가짜 자동화 — 매일 14:00, 대상은 `state["targets"]` 그대로."""
    from app.models import VcContact
    from app.services import automation, automation_runner as runner

    runner._load_all()
    saved = dict(runner.REGISTRY)

    contacts = []
    for index, firm in enumerate(["가나다벤처스", "라마바벤처스"]):
        row = VcContact(user_id=users["u1"].id, name=f"홍길동{index}", firm=firm,
                        title="심사역", kakao_room_name=f"{firm} Deal 공유",
                        connect_stage="connected", source_sheet="내 명단")
        db.add(row)
        contacts.append(row)
    db.commit()

    state = {"targets": list(contacts), "spacing": None, "veto": set(),
             "contacts": contacts}

    def plan(db, row, day):
        return runner.Plan(period=day.year * 10000 + day.month * 100 + day.day,
                           at=datetime(day.year, day.month, day.day, 14, 0).astimezone())

    def collect(db, row, sender, plan):
        outs = [automation.Out(room=c.kakao_room_name, message=f"{c.name} 님께",
                               contact_id=c.id, stage=3, ref=f"contact:{c.id}")
                for c in state["targets"]]
        return runner.Batch(outs=outs, spacing=state["spacing"],
                            note="가짜 대상이 없습니다")

    def still_ok(db, rec):
        return "결과를 적었습니다" if rec.contact_id in state["veto"] else ""

    runner.REGISTRY.clear()
    runner.register(runner.Spec(key=automation.MEETING_REVIEW, kind="deal_intro",
                                plan=plan, collect=collect, still_ok=still_ok))
    try:
        yield state
    finally:
        runner.REGISTRY.clear()
        runner.REGISTRY.update(saved)


def _turn_on(db, users, *, test=True):
    from app.services import automation

    return automation.save(db, automation.MEETING_REVIEW, enabled=True,
                           user_id=users["u2"].id, test_mode=test,
                           test_room=TEST_ROOM)


def _jobs(db):
    from app.models import SendJob

    db.expire_all()
    return db.execute(select(SendJob).order_by(SendJob.id)).scalars().all()


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.MEETING_REVIEW, _aware(now))


# ── 1·2. 세우지 않는 때 ──────────────────────────────────────────────────────

def test_off_does_nothing(db, fake):
    assert _run(db, WED_9AM)["status"] == "off"
    assert _jobs(db) == []


def test_not_before_eight_and_not_after_the_hour(db, users, fake):
    _turn_on(db, users)
    assert _run(db, WED_7AM)["status"] == "too_early"
    assert _run(db, WED_3PM)["status"] == "too_late"
    assert _jobs(db) == []


def test_no_sender_means_nothing(db, users, fake):
    _turn_on(db, users)
    users["u2"].is_active = 0
    db.commit()
    assert _run(db, WED_9AM)["status"] == "no_sender"


# ── 3. 세운다 ────────────────────────────────────────────────────────────────

def test_test_mode_builds_a_scheduled_test_job_on_the_sender(db, users, fake):
    from app.models import TEST_SEND_KIND, AutoSendRun
    from app.services import scheduled_send

    _turn_on(db, users, test=True)
    result = _run(db, WED_9AM)
    assert result["status"] == "ready" and result["test"] is True

    [job] = _jobs(db)
    assert job.kind == TEST_SEND_KIND
    assert job.user_id == users["u2"].id      # 보내는 계정 것
    assert job.status == "draft"
    assert scheduled_send.scheduled_at(job).strftime("%H:%M") == "14:00"
    assert [i.room_name for i in job.items] == [TEST_ROOM, TEST_ROOM]
    assert job.items[0].message.startswith("[시험] 원래 받을 방: 가나다벤처스 Deal 공유")
    assert all(i.contact_id is None for i in job.items)

    run = db.execute(select(AutoSendRun)).scalars().one()
    assert (run.kind, run.ref_id, run.status, run.job_id) == (
        "auto:meeting_review:test", 20261014, "ready", job.id)


def test_real_mode_points_at_the_contacts(db, users, fake):
    _turn_on(db, users, test=False)
    _run(db, WED_9AM)
    [job] = _jobs(db)
    assert job.kind == "deal_intro"
    assert [i.contact_id for i in job.items] == [c.id for c in fake["contacts"]]
    assert [i.room_name for i in job.items] == ["가나다벤처스 Deal 공유",
                                                "라마바벤처스 Deal 공유"]


# ── 4. 한 번만 ───────────────────────────────────────────────────────────────

def test_same_day_twice_is_one_job(db, users, fake):
    _turn_on(db, users)
    _run(db, WED_9AM)
    assert _run(db, datetime(2026, 10, 14, 9, 30))["status"] == "done"
    assert len(_jobs(db)) == 1


def test_a_target_is_sent_once_across_days(db, users, fake):
    _turn_on(db, users)
    _run(db, WED_9AM)
    result = _run(db, THU_9AM)
    assert result["status"] == "empty"
    assert len(_jobs(db)) == 1


def test_test_sends_do_not_block_real_ones(db, users, fake):
    _turn_on(db, users, test=True)
    _run(db, WED_9AM)
    _turn_on(db, users, test=False)
    assert _run(db, datetime(2026, 10, 14, 10, 0))["status"] == "ready"
    jobs = _jobs(db)
    assert [j.kind for j in jobs] == ["test_send", "deal_intro"]


# ── 5. 0건 ───────────────────────────────────────────────────────────────────

def test_empty_is_retried_the_same_day_and_shows_on_today(db, users, fake):
    from app.models import User
    from app.services import automation_runner as runner

    _turn_on(db, users)
    targets = fake["targets"]
    fake["targets"] = []
    assert _run(db, WED_9AM)["status"] == "empty"

    sender_lines = runner.today_items(db, users["u2"], _aware(WED_9AM))
    assert any("오늘은 안 나갑니다" in line["title"] for line in sender_lines)
    assert runner.today_items(db, users["u1"], _aware(WED_9AM)) == []

    fake["targets"] = targets
    assert _run(db, datetime(2026, 10, 14, 11, 0))["status"] == "ready"
    assert len(_jobs(db)) == 1
    assert db.get(User, users["u2"].id) is not None


def test_admin_sees_a_job_set_up_on_someone_else(db, users, fake):
    from app.services import automation_runner as runner

    _turn_on(db, users)
    _run(db, WED_9AM)
    users["u1"].role = "admin"
    db.commit()
    lines = runner.today_items(db, users["u1"], _aware(datetime(2026, 10, 14, 10, 0)))
    assert len(lines) == 1
    assert "자동화 · 미팅 후 검토결과 문의 (시험 모드)" == lines[0]["title"]
    assert lines[0]["href"].startswith("/jobs/")
    # 보내는 계정 본인에게는 같은 회차가 예약 줄로 이미 선다 — 두 번 안 적는다.
    assert runner.today_items(db, users["u2"], _aware(datetime(2026, 10, 14, 10, 0))) == []


# ── 6. 띄워 보내기 ───────────────────────────────────────────────────────────

def test_spacing_splits_jobs_minutes_apart(db, users, fake):
    from app.services import scheduled_send, send_guard

    fake["spacing"] = (2, 5)
    _turn_on(db, users)
    _run(db, WED_9AM)
    jobs = _jobs(db)
    assert len(jobs) == 2
    first, second = (scheduled_send.scheduled_at(j) for j in jobs)
    gap = (second - first).total_seconds() / 60
    assert first.strftime("%H:%M") == "14:00"
    assert 2 <= gap <= 5
    # 둘 다 **자동 회차**다 — 실패 알림이 둘 모두에 걸린다.
    assert send_guard.auto_job_ids(db, [j.id for j in jobs]) == {j.id for j in jobs}


# ── 7·8. 풀리는 순간 ─────────────────────────────────────────────────────────

def test_release_prunes_and_only_the_sender_device_gets_it(client, db, users, fake):
    from app.services import scheduled_send

    _turn_on(db, users)
    _run(db, WED_9AM)
    fake["veto"] = {fake["contacts"][0].id}
    released = scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    assert released["count"] == 1

    [job] = _jobs(db)
    assert job.status == "queued"
    statuses = [(i.status, i.error or "") for i in job.items]
    assert statuses[0][0] == "canceled" and "결과를 적었습니다" in statuses[0][1]
    assert statuses[1][0] == "pending"

    kinds = {"kinds": "deal_intro,ir_delivery,sourcing_intro,test_send"}
    assert client.get("/api/agent/poll", params=kinds,
                      headers=auth(DEMO_TOKEN)).status_code == 204
    got = client.get("/api/agent/poll", params=kinds, headers=auth(OTHER_TOKEN))
    assert got.status_code == 200
    assert [i["room_name"] for i in got.json()["items"]] == [TEST_ROOM]


def test_everything_pruned_closes_the_job(db, users, fake):
    from app.services import scheduled_send

    _turn_on(db, users)
    _run(db, WED_9AM)
    fake["veto"] = {c.id for c in fake["contacts"]}
    released = scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    assert released["count"] == 0
    [job] = _jobs(db)
    assert job.status == "canceled"
    assert {i.status for i in job.items} == {"canceled"}


def test_status_of_names_the_next_run(db, users, fake):
    from app.services import automation_runner as runner

    _turn_on(db, users)
    state = runner.status_of(db, "meeting_review", _aware(WED_9AM))
    assert state["ready"] is True
    assert state["next_label"] == "10/14(수) 14:00"
    _run(db, WED_9AM)
    state = runner.status_of(db, "meeting_review", _aware(datetime(2026, 10, 14, 10, 0)))
    assert state["today"]["status"] == "ready"


def test_cancel_before_send_stops_it(client, db, users, fake):
    """오늘 할 일에서 들어가 [중단] — 예약 시각이 와도 나가지 않는다."""
    from app.services import scheduled_send
    from tests.conftest import DEMO_PASSWORD

    _turn_on(db, users)
    _run(db, WED_9AM)
    [job] = _jobs(db)
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 200
    released = scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    assert released["count"] == 0
    assert _jobs(db)[0].status == "canceled"
