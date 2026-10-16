"""릴리스 PR 리뷰에서 찾은 자동화 결함들 — **멈춤은 늘 되고, 덜 보내는 쪽으로.**

각 검사 이름 앞의 번호는 리뷰 지적 번호다(PR 댓글의 표와 같다).

 1. 끄거나 시험 ↔ 실제를 바꾸면 아침에 세운 회차도 나가지 않는다(저장 · 풀 때 ·
    내줄 때 · 사람이 다시 낼 때 모두).
 3. 안 나간 대상(시각을 놓침 · 실패)은 다시 실리고, 받은 대상은 절대 다시 안 간다
    (→ `test_automation_runner.py`).
 4. 끄기는 다른 칸이 틀려도 늘 된다.
 5. 간격 때문에 기다린 회차는 그 기다림 때문에 '시각을 놓쳤다' 로 떨어지지 않고,
    큰 회차 뒤에는 그 길이만큼 띄운다.
 6. 미팅 후 문의는 그 미팅을 **마친 뒤** 사람이 보낸 글만 센다.
 8. 풀기 직전 확인이 넘어져도 회차가 멈춰 서지 않고, 다른 회차는 그대로 풀린다.
 9. 채널방처럼 띄워 보내는 회차는 밀려도 제 폭을 지킨다.
10. 시험방은 보내는 계정 카톡의 방 제목(확정 · 후보)일 수 없다.
12. 저장은 다 가린 뒤 한 번에 — 반쪽 저장이 없다.
13. 미팅 요청 두 번째가 첫 번째와 같은 날에 겹치지 않는다.
14. 진행 화면 · 오늘 할 일의 판정은 한 번만 센다.
15. 요일 읽기는 한 곳이다.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from tests.conftest import DEMO_PASSWORD, OTHER_TOKEN, auth
from tests.test_automation_guards import (  # noqa: F401 - 픽스처를 함께 쓴다
    KINDS, TEST_ROOM, WED_9AM, _hhmm, _jobs, _on, _release_at, _run, world)


def _aware(when):
    return when.astimezone()


def _admin(db, users, client):
    users["u2"].role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    return client


# ── 1. 끄면 멈춘다 ───────────────────────────────────────────────────────────

def test_01_turning_off_cancels_the_mornings_job(client, db, users, world):
    from app.services import automation_runner as runner
    from app.services import scheduled_send

    world["A"] = [world["people"]["c1"], world["people"]["c2"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    [job] = _jobs(db)
    assert job.status == "draft"

    _admin(db, users, client)
    r = client.post("/team/automations/meeting_review",
                    data={"enabled": "", "test_mode_shown": "1"}, follow_redirects=False)
    from urllib.parse import unquote

    assert "거뒀습니다" in unquote(r.headers["location"])
    db.expire_all()
    job = _jobs(db)[0]
    assert job.status == "canceled"
    assert all(i.status == "canceled" and i.error.startswith("자동화 중지 — 자동화를 꺼서")
               for i in job.items)
    # 예약 시각이 와도 아무것도 안 나간다.
    assert scheduled_send.run_once(
        db, _aware(datetime(2026, 10, 14, 14, 0, 20)))["count"] == 0
    # 오늘 할 일에 거둔 사실이 선다(꺼진 자동화라도).
    lines = runner.today_items(db, users["u2"], _aware(datetime(2026, 10, 14, 10, 0)))
    assert any("거뒀습니다" in line["title"] for line in lines)


def test_01_release_checks_the_switch_even_if_it_was_flipped_elsewhere(db, users, world):
    """끄는 화면을 지나지 않고 꺼졌어도(예: DB 를 손으로) 풀 때 다시 본다."""
    from app.services import automation, scheduled_send

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    automation.load(db, "meeting_review").enabled = 0
    db.commit()
    assert scheduled_send.run_once(
        db, _aware(datetime(2026, 10, 14, 14, 0, 20)))["count"] == 0
    [job] = _jobs(db)
    assert job.status == "canceled"
    assert "자동화를 꺼서" in job.items[0].error


def test_01_switching_mode_cancels_the_other_modes_job(db, users, world):
    from app.services import automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review", test=False)
    _run(db, "meeting_review")
    _row, stopped = runner.save_settings(db, "meeting_review", None, enabled=True,
                                         user_id=None, test_mode=True,
                                         test_room=TEST_ROOM)
    assert stopped == 1
    [job] = _jobs(db)
    assert job.status == "canceled" and "시험 모드가 바뀌어" in job.items[0].error


def test_01_changing_the_auto_send_account_cancels_the_old_pcs_job(db, users, world):
    from app.services import automation, automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    automation.save_team(db, user_id=users["u1"].id, values={})
    assert runner.stop_jobs(db, "meeting_review") == 1
    assert "보내는 계정이 바뀌어" in _jobs(db)[0].items[0].error


def test_01_a_queued_job_of_a_switched_off_automation_is_never_handed_out(
        client, db, users, world, monkeypatch):
    from app.services import automation, automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    _release_at(db, monkeypatch, 14, 0)
    assert _jobs(db)[0].status == "queued"
    automation.load(db, "meeting_review").enabled = 0       # 저장 화면을 안 지남
    db.commit()
    assert client.get("/api/agent/poll", params=KINDS,
                      headers=auth(OTHER_TOKEN)).status_code == 204
    # 오늘 할 일이 서 있는 회차를 크게 알린다.
    lines = runner.today_items(db, users["u2"], _aware(datetime(2026, 10, 14, 14, 1)))
    assert any(line["level"] == "urgent" and "서 있습니다" in line["title"]
               for line in lines)


def test_01_a_stopped_job_cannot_be_resent_by_hand(client, db, users, world):
    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    _admin(db, users, client)
    client.post("/team/automations/meeting_review",
                data={"enabled": "", "test_mode_shown": "1"}, follow_redirects=False)
    job = _jobs(db)[0]
    r = client.post(f"/api/jobs/{job.id}/resend-canceled")
    assert r.status_code == 400 and "자동화 회차" in r.json()["detail"]
    db.expire_all()
    assert _jobs(db)[0].status == "canceled"


def test_03_a_retaken_targets_old_item_cannot_be_resent_by_hand(client, db, users, world):
    """예약 시각을 놓쳐 다음 날 다시 실린 대상 — 옛 회차의 옛 건을 사람이
    [취소분 재발송] 으로 되살려 두 번 보내지 못한다."""
    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    old = _jobs(db)[0]
    assert _run(db, "meeting_review", datetime(2026, 10, 15, 9, 0))["count"] == 1
    db.expire_all()
    assert "다시 실림" in _jobs(db)[0].items[0].error
    _admin(db, users, client)
    r = client.post(f"/api/jobs/{old.id}/resend-canceled")
    assert r.status_code == 400 and "다시 실림" in r.json()["detail"]


# ── 결정 1. 발송기 손에 안 간 대상만 다시 싣는다 ─────────────────────────────

def test_d1_a_failed_target_is_not_retried_but_a_person_can(client, db, users, world):
    """발송기가 실패로 보고한 대상은 자동으로 다시 안 보낸다. 사람의 [실패 재시도]
    는 그대로 된다(그때도 끔 · 중복 판정은 지난다)."""
    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    job = _jobs(db)[0]
    job.items[0].status, job.items[0].error = "failed", "room_mismatch"
    job.status = "done_with_errors"
    db.commit()
    assert _run(db, "meeting_review", datetime(2026, 10, 15, 9, 0))["status"] == "empty"
    _admin(db, users, client)
    page = client.get(f"/jobs/{job.id}").text
    assert 'data-testid="automation-failed-note"' in page and "[실패 재시도]" in page
    r = client.post(f"/api/jobs/{job.id}/retry")
    assert r.status_code == 200 and r.json()["requeued"] == 1


def test_d1_targets_stopped_by_turning_off_are_not_requeued_when_back_on(
        client, db, users, world):
    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    _admin(db, users, client)
    client.post("/team/automations/meeting_review",
                data={"enabled": "", "test_mode_shown": "1"}, follow_redirects=False)
    _on(db, "meeting_review")                     # 다음 날 다시 켬
    result = _run(db, "meeting_review", datetime(2026, 10, 15, 9, 0))
    assert result["status"] == "empty"
    assert len(_jobs(db)) == 1


def test_d1_targets_a_person_stopped_are_not_requeued(client, db, users, world):
    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    job = _jobs(db)[0]
    _admin(db, users, client)
    assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 200
    assert _run(db, "meeting_review", datetime(2026, 10, 15, 9, 0))["status"] == "empty"


def test_d1_a_temporary_dedupe_drop_is_retried_the_next_day(db, users, world):
    """풀 때 중복 방지로 빠진 대상(발송기 손에 안 감)은 다음 날 다시 실린다."""
    from app.models import AutomationSend, DealBatch, SendItem, SendJob
    from app.services import scheduled_send

    c1 = world["people"]["c1"]
    world["A"] = [c1]
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
    scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    assert _jobs(db)[0].items[0].error.startswith("자동 제외 — 중복 방지")
    result = _run(db, "meeting_review", datetime(2026, 10, 15, 9, 0))
    assert result["status"] == "ready" and result["count"] == 1


# ── 4 · 12. 끄기는 늘 되고, 저장은 한 번에 ───────────────────────────────────

def test_04_turning_off_sticks_even_when_other_fields_are_wrong(client, db, users, world):
    from app.services import automation, automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review", test=False)
    before = runner.values(automation.load(db, "meeting_review"), "meeting_review")
    _admin(db, users, client)
    r = client.post("/team/automations/meeting_review", data={
        "enabled": "", "test_mode_shown": "1",
        # 진짜 상대의 방을 시험방에 · 보내는 시간 밖의 시각 — 둘 다 못 받을 값.
        "test_room": world["people"]["c1"].kakao_room_name,
        "p_item_gap_min": "90", "p_item_gap_max": "30"}, follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    row = automation.load(db, "meeting_review")
    assert row.enabled == 0, "다른 칸이 틀려 끄기가 막혔습니다"
    assert runner.values(row, "meeting_review") == before
    from urllib.parse import unquote

    assert "껐습니다" in unquote(r.headers["location"])


def test_12_a_rejected_save_changes_nothing(client, db, users, world):
    from app.services import automation, automation_runner as runner

    _on(db, "meeting_review", test=True)
    before = runner.values(automation.load(db, "meeting_review"), "meeting_review")
    _admin(db, users, client)
    client.post("/team/automations/meeting_review", data={
        "enabled": "on", "test_mode_shown": "1", "test_mode": "on",
        "test_room": world["people"]["c1"].kakao_room_name,   # 못 받을 시험방
        "p_item_gap_min": "40", "p_item_gap_max": "80"}, follow_redirects=False)
    db.expire_all()
    row = automation.load(db, "meeting_review")
    assert runner.values(row, "meeting_review") == before, "값만 먼저 저장됐습니다"
    assert row.test_room == TEST_ROOM


# ── 5. 간격 때문에 기다린 회차 ───────────────────────────────────────────────

def test_05_the_gap_is_capped_well_below_the_expiry(db, users):
    from app.services import automation, scheduled_send

    assert automation.MAX_JOB_GAP_MIN * 2 <= scheduled_send.EXPIRE_MINUTES
    with pytest.raises(ValueError):
        automation.save_team(db, user_id=None,
                             values={"job_gap_min": str(automation.MAX_JOB_GAP_MIN + 1)})


def test_05_a_job_held_by_the_gap_does_not_expire_because_of_it(
        client, db, users, world, monkeypatch):
    from app import clock
    from app.services import scheduled_send

    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c2"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    _run(db, "meeting_request")
    first, second = _jobs(db)
    _release_at(db, monkeypatch, 14, 0)
    assert client.get("/api/agent/poll", params=KINDS,
                      headers=auth(OTHER_TOKEN)).json()["job_id"] == first.id
    _release_at(db, monkeypatch, 14, 11)
    # 앞 회차가 아주 길게 갔다 — 15:20 에 끝났다(두 번째의 원래 마감 15:11 이 지남).
    first = _jobs(db)[0]
    first.status = "done"
    first.finished_at = _aware(datetime(2026, 10, 14, 15, 20)).isoformat(timespec="seconds")
    db.commit()
    for minute in (21, 25):
        monkeypatch.setattr(clock, "now",
                            lambda m=minute: _aware(datetime(2026, 10, 14, 15, m, 0)))
        assert client.get("/api/agent/poll", params=KINDS,
                          headers=auth(OTHER_TOKEN)).status_code == 204
        db.expire_all()
        assert _jobs(db)[1].status == "queued", "간격 때문에 기다리다 시각을 놓쳤다고 떨어졌다"
    monkeypatch.setattr(clock, "now", lambda: _aware(datetime(2026, 10, 14, 15, 30, 30)))
    got = client.get("/api/agent/poll", params=KINDS, headers=auth(OTHER_TOKEN))
    assert got.status_code == 200 and got.json()["job_id"] == second.id
    # 기다림이 끝난 뒤로도 60분이 지나면 그때는 놓친 것이다(덜 보내는 쪽).
    assert scheduled_send.EXPIRE_MINUTES == 60


def test_05_a_long_job_pushes_the_next_one_by_its_length(db, users, world):
    from app.models import VcContact

    many = []
    for n in range(30):
        row = VcContact(user_id=users["u1"].id, name=f"이름{n}", firm=f"회사{n}",
                        title="심사역", kakao_room_name=f"방 {n}",
                        connect_stage="connected", source_sheet="내 명단")
        db.add(row)
        many.append(row)
    db.commit()
    world["A"] = many
    world["B"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    _run(db, "meeting_request")
    first, second = _jobs(db)
    # 30통 × 20초 + 29 × 평균 40초 ≈ 30분 → 14:30 끝 + 간격 10분.
    assert _hhmm(first) == "14:00"
    assert _hhmm(second) >= "14:39"


# ── 6. 미팅 후 문의는 미팅 뒤의 손 발송만 ────────────────────────────────────

def _a7_world(db, users):
    from app.models import AutoSendSetting, Meeting, VcContact

    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    who = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나다벤처스",
                    title="심사역", kakao_room_name="홍길동 가나다벤처스 Deal 공유",
                    connect_stage="connected", source_sheet="내 명단")
    db.add(who)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=who.id, scheduled_at="2026-10-12",
                   status="done", done_at="2026-10-12", outcome="reviewing"))
    db.commit()
    return who


def _hand_sent(db, users, who, when):
    from app.models import DealBatch, SendItem, SendJob

    batch = DealBatch(user_id=users["u1"].id, title="미팅", sent_date=when[:10],
                      cycle_type="adhoc")
    db.add(batch)
    db.flush()
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done", total=1, sent=1, failed=0)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=who.id, stage=3, channel="kakao",
                    room_name=who.kakao_room_name, message="미팅", status="sent",
                    sent_at=when))
    db.commit()


def test_06_the_meeting_request_before_the_meeting_does_not_suppress_the_review(db, users):
    from app.services import automation, automation_runner as runner

    who = _a7_world(db, users)
    _hand_sent(db, users, who, "2026-10-09T15:00:00+09:00")    # 미팅 전의 미팅 요청
    automation.save(db, "meeting_review", enabled=True, user_id=None, test_mode=False,
                    test_room=TEST_ROOM)
    assert runner.run_once(db, "meeting_review", _aware(WED_9AM))["status"] == "ready"


def test_06_a_review_sent_by_hand_after_the_meeting_suppresses_it(db, users):
    from app.services import automation, automation_runner as runner

    who = _a7_world(db, users)
    _hand_sent(db, users, who, "2026-10-13T15:00:00+09:00")    # 미팅 뒤 손으로
    automation.save(db, "meeting_review", enabled=True, user_id=None, test_mode=False,
                    test_room=TEST_ROOM)
    result = runner.run_once(db, "meeting_review", _aware(WED_9AM))
    assert result["status"] == "empty"
    assert any("손으로" in line for line in result["skipped"])


# ── 8. 풀기 직전 확인이 넘어져도 ─────────────────────────────────────────────

def test_08_a_crash_in_the_check_closes_the_job_without_sending(db, users, world,
                                                               monkeypatch):
    from app.services import automation_runner as runner
    from app.services import scheduled_send, send_guard

    world["A"] = [world["people"]["c1"]]
    world["B"] = [world["people"]["c2"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    automation_send_gap_zero(db)
    _run(db, "meeting_review")
    _run(db, "meeting_request")
    first, second = _jobs(db)
    alerts = []
    monkeypatch.setattr(send_guard, "_dispatch", lambda func, *a: alerts.append(a))
    real = runner.prune

    def boom(db_, job, now=None):
        if job.id == first.id:
            raise RuntimeError("확인 중 고장")
        return real(db_, job, now)

    monkeypatch.setattr(runner, "prune", boom)
    released = scheduled_send.run_once(db, _aware(datetime(2026, 10, 14, 14, 0, 20)))
    assert released["released"] == [second.id], "고장 난 회차 때문에 나머지가 안 풀렸다"
    db.expire_all()
    first = _jobs(db)[0]
    assert first.status == "done_with_errors"
    assert first.items[0].status == "failed" and "오류" in first.items[0].error
    assert scheduled_send.state(first) != scheduled_send.STATE_DUE
    assert alerts, "관리자에게 알리지 않았다"


def automation_send_gap_zero(db):
    from app.services import automation

    automation.save_team(db, user_id=None, values={"job_gap_min": "0"})


# ── 9. 띄워 보내는 회차는 밀려도 제 폭을 ─────────────────────────────────────

def test_09_spaced_jobs_keep_their_spacing_after_a_shift(db, users, world):
    from app.services import automation, automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")                       # 14:00 에 다른 자동 회차 하나
    team = automation.team(db)
    outs = [automation.Out(room=f"채널 {n}", message="딜", ref=f"r{n}") for n in range(4)]
    batch = runner.Batch(outs=outs, spacing=(2, 5))
    plan = runner.Plan(period=202642, at=_aware(datetime(2026, 10, 14, 14, 0)))
    placed = runner._place_all(db, batch, plan, "channel_top", team, users["u2"].id,
                               date(2026, 10, 14), outs, [])
    times = [when for _group, when in placed]
    assert times[0] >= _aware(datetime(2026, 10, 14, 14, 11))
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
    assert all(2 <= g <= 5 for g in gaps), gaps


# ── 10. 시험방은 보내는 계정 카톡의 방 제목일 수 없다 ────────────────────────

def test_10_the_senders_own_room_titles_are_real_rooms(db, users, world):
    import json

    from app.models import SenderRoom
    from app.services import automation

    c1 = world["people"]["c1"]
    db.add(SenderRoom(sender_user_id=users["u2"].id, contact_id=c1.id,
                      room_name="홍길동 이사님 가나다 Deal",
                      candidates=json.dumps(["김철수 수석 라마바 Deal"], ensure_ascii=False)))
    db.commit()
    for room in ("홍길동 이사님 가나다 Deal", "홍길동이사님가나다 deal",
                 "김철수 수석  라마바 DEAL"):
        assert automation.test_room_problem(db, room), room
    assert automation.test_room_problem(db, "나와의 채팅 시험방") == ""


# ── 13. 미팅 요청 두 번째가 첫 번째와 겹치지 않는다 ──────────────────────────

def test_13_the_second_ask_never_lands_on_the_first_asks_day():
    from app.services.automations import meeting_request as a2

    # 10/3(토) 에 전달 — +7 = 10/10(토) → 10/12(월), +8 = 10/11(일) → 10/12(월).
    r1, r2 = a2.rounds("2026-10-03", 7, 8)
    assert r1 == date(2026, 10, 12)
    assert r2 == date(2026, 10, 13)


def test_13_the_first_ask_goes_out_when_the_days_collide(db, users):
    from app.models import AutoSendSetting, IrRequest, VcContact
    from app.services import automation, automation_runner as runner

    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u2"].id))
    who = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나다벤처스",
                    title="심사역", kakao_room_name="홍길동 가나다벤처스 Deal 공유",
                    connect_stage="connected", source_sheet="내 명단")
    db.add(who)
    db.flush()
    db.add(IrRequest(user_id=users["u1"].id, contact_id=who.id, company_name="기업",
                     requested_at="2026-10-01", status="delivered",
                     delivered_at="2026-10-03"))
    db.commit()
    runner.save_params(db, "meeting_request", {"first_days": "7", "second_days": "8"})
    automation.save(db, "meeting_request", enabled=True, user_id=None, test_mode=False,
                    test_room=TEST_ROOM)
    result = runner.run_once(db, "meeting_request", _aware(datetime(2026, 10, 12, 9, 0)))
    assert result["status"] == "ready" and result["count"] == 1


# ── 14. 한 번만 센다 ─────────────────────────────────────────────────────────

def test_14_the_job_screen_counts_the_hold_once(client, db, users, world, monkeypatch):
    from app.services import automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _run(db, "meeting_review")
    _release_at(db, monkeypatch, 14, 0)
    calls = []
    real = runner.held_jobs
    monkeypatch.setattr(runner, "held_jobs",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    _admin(db, users, client)
    job = _jobs(db)[0]
    assert client.get(f"/api/jobs/{job.id}").status_code == 200
    assert len(calls) == 1


def test_14_today_items_reads_the_switches_once(db, users, world, monkeypatch):
    from app.services import automation, automation_runner as runner

    world["A"] = [world["people"]["c1"]]
    _on(db, "meeting_review")
    _on(db, "meeting_request")
    _run(db, "meeting_review")
    calls = []
    real = automation.load
    monkeypatch.setattr(automation, "load",
                        lambda *a, **k: calls.append(a[1]) or real(*a, **k))
    runner.today_items(db, users["u2"], _aware(datetime(2026, 10, 14, 10, 0)))
    # 자동화 줄은 한 번에 읽어 쓴다 — 하나씩 다시 읽는 것은 팀 공통 줄 한 번뿐.
    assert [c for c in calls if c != automation.TEAM_KEY] == [], calls
    assert calls.count(automation.TEAM_KEY) <= 1, calls


# ── 15. 요일 읽기는 한 곳 ────────────────────────────────────────────────────

def test_15_weekday_parsing_is_one_function():
    from app.services import automation_runner as runner
    from app.services.automations import channel_top, sourcing_remind

    assert channel_top._weekday is runner.parse_weekday
    assert sourcing_remind._weekday is runner.parse_weekday
    assert runner.parse_weekday("수") == 2
    with pytest.raises(ValueError):
        runner.parse_weekday("수요일")
