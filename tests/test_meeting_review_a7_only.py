"""#31 미팅 후기 결과 문의는 **A7 하나**다 — 옛 '발송 준비'(대기 목록)를 걷었다.

사용자 결정(2026-10-17, "추천대로"):

1. 옛 대기 목록 엔진(`services/auto_send` 의 30분 실 · 열흘 뒤 `draft` 목록)과
   팀 현황의 `미팅 후기 발송 준비` 판 · `/team/auto-send` 를 걷는다. 표와 이력
   (`auto_send_settings` · `auto_send_runs`)은 남긴다.
3. 결과 문의는 A7(`automations/meeting_review.py`) 하나 — 08~14시 사이 사람이
   [중단] 할 수 있는 자리가 옛 '발송 준비' 몫을 한다.
8. 걷는 날 남아 있던 옛 `미팅 후기 자동` 목록(`draft`)은 **저절로 안 나간다** —
   오늘 할 일에 서서 사람이 보내거나 취소한다.

기본 보내는 계정은 이제 옛 미팅 후기 설정을 읽지 않는다 — 이주(0105)가 그 계정을
팀 공통 자동 발송 계정으로 옮겼다.

이름·회사명은 전부 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import threading

from tests.conftest import DEMO_PASSWORD


def _admin(db, users):
    users["u1"].role = "admin"
    db.commit()
    return users["u1"]


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


def _old_draft(db, user, *, count=2, ref_id=501):
    """걷기 전 옛 엔진이 세워 둔 `미팅 후기 자동` 목록 하나 — 아직 아무도 안 눌렀다."""
    from app.models import AutoSendRun, DealBatch, SendItem, SendJob

    batch = DealBatch(user_id=user.id, title="10/14 (미팅 후기 자동)",
                      sent_date="2026-10-14")
    db.add(batch)
    db.flush()
    job = SendJob(user_id=user.id, kind="deal_intro", batch_id=batch.id,
                  status="draft", total=count, sent=0, failed=0)
    db.add(job)
    db.flush()
    for index in range(count):
        db.add(SendItem(job_id=job.id, channel="kakao", room_name=f"가나벤처스 {index}",
                        message="미팅 후기", status="pending"))
        db.add(AutoSendRun(kind="meeting_review", ref_id=ref_id + index,
                           user_id=user.id, day="2026-10-14", status="ready",
                           job_id=job.id))
    db.commit()
    return job


# ── 1. 옛 엔진 · 판 · 길이 없다 ─────────────────────────────────────────────

def test_the_old_list_engine_is_gone(db, users, client):
    """옛 설정이 켜진 채 남아 있어도 실이 뜨지 않는다."""
    from app.models import AutoSendSetting
    from app.services import auto_send

    db.add(AutoSendSetting(kind="meeting_review", enabled=1, user_id=1))
    db.commit()
    for gone in ("run_once", "start_scheduler", "KINDS", "status"):
        assert not hasattr(auto_send, gone), gone
    assert "auto-send" not in {t.name for t in threading.enumerate()}


def test_the_old_panel_and_route_are_gone(db, users, client):
    _admin(db, users)
    page = _login(client).get("/team").text
    assert "미팅 후기 발송 준비" not in page
    assert 'action="/team/auto-send"' not in page
    assert 'data-automation="meeting_review"' in page        # A7 줄은 그대로
    answer = client.post("/team/auto-send", data={"kind": "meeting_review",
                                                  "enabled": "on", "user_id": 1},
                         follow_redirects=False)
    assert answer.status_code in (404, 405)


def test_the_default_sender_no_longer_reads_the_old_review_setting(db, users):
    from app.models import AutoSendSetting
    from app.services import automation

    db.add(AutoSendSetting(kind="meeting_review", enabled=1, user_id=users["u2"].id))
    db.commit()
    assert automation.default_sender_id(db) is None
    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=users["u1"].id))
    db.commit()
    assert automation.default_sender_id(db) == users["u1"].id


# ── 8. 남아 있던 옛 목록 ────────────────────────────────────────────────────

def test_a_leftover_old_list_shows_in_today_for_a_person_to_handle(db, users):
    from app.services import today

    job = _old_draft(db, users["u1"])
    mine = [i for i in today.build(db, users["u1"])["items"]
            if i["href"] == f"/jobs/{job.id}"]
    assert len(mine) == 1
    assert "옛" in mine[0]["title"] and "미팅 후기" in mine[0]["title"]
    assert "저절로 나가지 않습니다" in mine[0]["detail"]
    assert "[발송 시작]" in mine[0]["detail"] and "[취소]" in mine[0]["detail"]
    assert mine[0]["count"] == 2
    # 다른 팀원에게는 안 선다(누를 수 있는 것은 주인뿐이다).
    assert not [i for i in today.build(db, users["u2"])["items"]
                if i["href"] == f"/jobs/{job.id}"]


def test_the_admin_sees_another_members_leftover_list_too(db, users):
    from app.models import User
    from app.services import auth as auth_svc, today

    admin = User(id=9, name="관리자", phone="01000000009", role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.commit()
    job = _old_draft(db, users["u2"])
    lines = [i for i in today.build(db, admin)["items"] if i["href"] == f"/jobs/{job.id}"]
    assert len(lines) == 1
    assert users["u2"].name in lines[0]["detail"]


def test_a_leftover_list_is_never_released_on_its_own(db, users):
    """예약 시각이 없는 `draft` 라 예약을 푸는 실도 손대지 않는다 — 사람이 눌러야 나간다."""
    from app.services import scheduled_send

    job = _old_draft(db, users["u1"])
    scheduled_send.run_once(db)
    db.refresh(job)
    assert job.status == "draft"
    assert {i.status for i in job.items} == {"pending"}


def test_the_line_goes_away_once_started_or_canceled(db, users, client):
    from app.services import today

    job = _old_draft(db, users["u1"])
    answer = _login(client).post(f"/api/jobs/{job.id}/cancel")
    assert answer.status_code == 200, answer.text
    db.expire_all()
    assert not [i for i in today.build(db, users["u1"])["items"]
                if i["href"] == f"/jobs/{job.id}"]
