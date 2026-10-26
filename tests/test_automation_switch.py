"""2단계 자동화 스위치 · 시험 모드 — **시험이 실제 상대에게 새지 않는다.**

1. 줄이 없으면 꺼짐이고 **시험 모드**다.
2. 기본 보내는 계정은 스타트업 월간 발송 계정이다(이름을 코드에 적지 않는다).
3. 시험 모드로 켜려면 시험방이 있어야 하고, **진짜 상대의 방 이름은 시험방이
   될 수 없다.**
4. 시험 회차는 `test_send` 종류로 서고, 모든 한 통이 시험방으로 가며 글 맨 앞에
   `[시험] 원래 받을 방: …` 이 붙고, 받는 줄(담당자)을 가리키지 않는다.
5. 회차는 **보내는 계정 것**이라 그 계정의 발송기만 집어간다 — 다른 팀원의
   기기는 아무것도 못 받는다.
6. 팀 현황 판 — 관리자만 고친다. 시험 모드 칸이 빠진 요청은 시험 모드를 켠
   채로 둔다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN, OTHER_TOKEN, auth

TEST_ROOM = "자동화 시험방"


@pytest.fixture()
def admin(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=9, name="관리자", phone="01000000009", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


def _contact(db, user, room="가나다벤처스 Deal 공유"):
    from app.models import VcContact

    row = VcContact(user_id=user.id, name="홍길동", firm="가나다벤처스",
                    title="심사역", kakao_room_name=room,
                    connect_stage="connected", source_sheet="내 명단")
    db.add(row)
    db.commit()
    return row


def _startup_sender(db, user):
    """스타트업 월간 발송 계정 — 자동화의 기본 보내는 계정이 된다."""
    from app.models import AutoSendSetting

    db.add(AutoSendSetting(kind="startup_ir", enabled=1, user_id=user.id))
    db.commit()


# ── 1·2. 기본값 ─────────────────────────────────────────────────────────────

def test_no_row_means_off_and_test_mode(db, users):
    from app.services import automation

    state = automation.status(db)
    assert [r["key"] for r in state["rows"]] == [k.key for k in automation.KINDS]
    assert len(state["rows"]) == 6
    for row in state["rows"]:
        assert row["enabled"] is False
        assert row["test_mode"] is True
        assert row["test_room"] == ""


def test_default_sender_is_the_startup_monthly_sender(db, users):
    from app.services import automation

    assert automation.default_sender_id(db) is None
    _startup_sender(db, users["u2"])
    assert automation.default_sender_id(db) == users["u2"].id
    row = automation.load(db, automation.MEETING_REVIEW)
    assert automation.sender(db, row).id == users["u2"].id
    assert automation.status(db)["default_sender"] == users["u2"].name


# ── 3. 저장 ─────────────────────────────────────────────────────────────────

def test_test_mode_needs_a_test_room(db, users):
    from app.services import automation

    _startup_sender(db, users["u1"])
    with pytest.raises(ValueError, match="시험방"):
        automation.save(db, automation.MEETING_REVIEW, enabled=True,
                        user_id=None, test_mode=True, test_room="")
    db.rollback()
    row = automation.save(db, automation.MEETING_REVIEW, enabled=True,
                          user_id=None, test_mode=True, test_room=TEST_ROOM)
    assert row.enabled == 1 and row.test_mode == 1 and row.test_room == TEST_ROOM


def test_a_real_room_cannot_be_the_test_room(db, users):
    from app.services import automation

    _startup_sender(db, users["u1"])
    _contact(db, users["u2"], room="가나다벤처스 Deal 공유")
    with pytest.raises(ValueError, match="실제 상대"):
        automation.save(db, automation.CHANNEL_TOP, enabled=False, user_id=None,
                        test_mode=True, test_room="가나다벤처스 Deal 공유")


def test_enabling_needs_a_sender(db, users):
    from app.services import automation

    with pytest.raises(ValueError, match="보내는 계정"):
        automation.save(db, automation.SOURCING_REMIND, enabled=True,
                        user_id=None, test_mode=True, test_room=TEST_ROOM)


def test_a_consultant_cannot_be_the_sender(db, users):
    from app.models import User
    from app.services import automation

    users["u2"].role = "consultant"
    db.commit()
    with pytest.raises(ValueError, match="딜소개를 보내는"):
        automation.save(db, automation.SOURCING_REMIND, enabled=False,
                        user_id=users["u2"].id, test_mode=True,
                        test_room=TEST_ROOM)
    assert db.get(User, users["u2"].id).role == "consultant"


# ── 4. 시험방으로 돌리기 ──────────────────────────────────────────────────────

def test_route_puts_the_real_room_on_top():
    from app.services import automation

    real = automation.route("가나다벤처스 Deal 공유", "본문")
    assert (real.room, real.message, real.test) == ("가나다벤처스 Deal 공유", "본문", False)

    test = automation.route("가나다벤처스 Deal 공유", "본문", test_room=TEST_ROOM)
    assert test.room == TEST_ROOM
    assert test.test is True
    assert test.message.splitlines()[0] == "[시험] 원래 받을 방: 가나다벤처스 Deal 공유"
    assert test.message.endswith("본문")


def test_test_job_is_a_test_send_that_points_at_nobody(db, users):
    from app.models import TEST_SEND_KIND
    from app.services import automation

    contact = _contact(db, users["u2"])
    job = automation.build_job(
        db, sender=users["u1"], kind="deal_intro", title="시험",
        outs=[automation.Out(room=contact.kakao_room_name, message="본문",
                             contact_id=contact.id, stage=3)],
        test_room=TEST_ROOM)
    db.commit()

    assert job.kind == TEST_SEND_KIND
    assert job.user_id == users["u1"].id
    assert job.status == "draft"
    item = job.items[0]
    assert item.room_name == TEST_ROOM
    assert item.message.startswith("[시험] 원래 받을 방: 가나다벤처스 Deal 공유")
    # 담당자 이력 · 후속 · 실적에 안 잡히도록 **아무도 가리키지 않는다**.
    assert item.contact_id is None and item.stage is None


def test_real_job_keeps_kind_room_and_recipient(db, users):
    from app.services import automation

    contact = _contact(db, users["u2"])
    job = automation.build_job(
        db, sender=users["u1"], kind="deal_intro", title="실제",
        outs=[automation.Out(room=contact.kakao_room_name, message="본문",
                             contact_id=contact.id, stage=3)])
    db.commit()
    item = job.items[0]
    assert job.kind == "deal_intro"
    assert (item.room_name, item.message, item.contact_id, item.stage) == (
        "가나다벤처스 Deal 공유", "본문", contact.id, 3)


# ── 5. 보내는 계정의 기기만 집어간다 ──────────────────────────────────────────

def test_only_the_sender_device_picks_up_the_job(client, db, users):
    from app.services import automation

    contact = _contact(db, users["u1"])
    job = automation.build_job(
        db, sender=users["u2"], kind="deal_intro", title="실제",
        status="queued",
        outs=[automation.Out(room=contact.kakao_room_name, message="본문",
                             contact_id=contact.id)])
    db.commit()

    kinds = {"kinds": "deal_intro,ir_delivery,sourcing_intro,test_send"}
    # 담당자의 주인(u1)의 기기는 받지 못한다 — 회차 주인은 보내는 계정(u2)이다.
    mine = client.get("/api/agent/poll", params=kinds, headers=auth(DEMO_TOKEN))
    assert mine.status_code == 204
    theirs = client.get("/api/agent/poll", params=kinds, headers=auth(OTHER_TOKEN))
    assert theirs.status_code == 200
    assert theirs.json()["job_id"] == job.id


def test_check_message_goes_to_the_test_room_from_the_sender(client, db, users):
    from app.models import TEST_SEND_KIND
    from app.services import automation

    _startup_sender(db, users["u2"])
    automation.save(db, automation.CHANNEL_TOP, enabled=False, user_id=None,
                    test_mode=True, test_room=TEST_ROOM)
    job = automation.queue_check(db, automation.CHANNEL_TOP)
    assert job.kind == TEST_SEND_KIND and job.status == "queued"
    assert job.user_id == users["u2"].id
    assert [i.room_name for i in job.items] == [TEST_ROOM]

    got = client.get("/api/agent/poll", params={"kinds": "test_send"},
                     headers=auth(OTHER_TOKEN))
    assert got.status_code == 200
    assert got.json()["items"][0]["room_name"] == TEST_ROOM
    assert client.get("/api/agent/poll", params={"kinds": "test_send"},
                      headers=auth(DEMO_TOKEN)).status_code == 204



def test_test_mode_does_not_lean_on_the_setup_test_tools(db, users, monkeypatch):
    """운영에서 `/setup` 시험 자리가 닫혀도(`test_tools_on`) 자동화 시험 모드는 돈다 —
    시험방이 `.env`(`DEALFLOW_TEST_ROOM`)가 아니라 자동화 줄(`Automation.test_room`)에 있다."""
    from app import config
    from app.models import TEST_SEND_KIND
    from app.routers.setup import test_tools_on
    from app.services import automation

    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "TEST_ROOM", "")
    assert not test_tools_on()
    _startup_sender(db, users["u2"])
    automation.save(db, automation.CHANNEL_TOP, enabled=False, user_id=None,
                    test_mode=True, test_room=TEST_ROOM)
    job = automation.queue_check(db, automation.CHANNEL_TOP)
    assert job.kind == TEST_SEND_KIND
    assert [i.room_name for i in job.items] == [TEST_ROOM]

# ── 6. 팀 현황 ──────────────────────────────────────────────────────────────

def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def test_panel_is_on_the_team_page(client, db, admin):
    _login(client, admin.phone)
    page = client.get("/team")
    assert page.status_code == 200
    assert 'data-testid="automation-panel"' in page.text
    for label in ("미팅 후 검토결과 문의", "미팅 요청 2회", "소싱 리마인드",
                  "채널방 TOP·핵심 딜", "스타트업 월간 발송"):
        assert label in page.text


def test_admin_saves_a_row(client, db, admin, users):
    from app.services import automation

    _login(client, admin.phone)
    answer = client.post("/team/automations/meeting_review", data={
        "enabled": "on", "user_id": users["u1"].id, "test_mode": "on",
        "test_mode_shown": "1", "test_room": TEST_ROOM},
        follow_redirects=False)
    assert answer.status_code == 303
    db.expire_all()
    row = automation.load(db, automation.MEETING_REVIEW)
    assert (row.enabled, row.user_id, row.test_mode, row.test_room) == (
        1, users["u1"].id, 1, TEST_ROOM)


def test_missing_checkbox_field_keeps_test_mode_on(client, db, admin, users):
    """체크 상자를 모르는 요청이 시험 모드를 **꺼 버리지** 않는다."""
    from app.services import automation

    _login(client, admin.phone)
    client.post("/team/automations/meeting_review", data={
        "enabled": "", "user_id": users["u1"].id, "test_room": TEST_ROOM},
        follow_redirects=False)
    db.expire_all()
    assert automation.load(db, automation.MEETING_REVIEW).test_mode == 1

    # 화면 폼에서 체크를 끄면(칸이 안 오고 `shown` 만 온다) 그때 꺼진다.
    client.post("/team/automations/meeting_review", data={
        "enabled": "", "user_id": users["u1"].id, "test_room": TEST_ROOM,
        "test_mode_shown": "1"}, follow_redirects=False)
    db.expire_all()
    assert automation.load(db, automation.MEETING_REVIEW).test_mode == 0


def test_non_admin_cannot_save(client, db, users):
    from app.services import automation

    _login(client, "01000000001")
    client.post("/team/automations/meeting_review", data={
        "enabled": "on", "user_id": users["u1"].id, "test_mode": "on",
        "test_mode_shown": "1", "test_room": TEST_ROOM},
        follow_redirects=False)
    db.expire_all()
    assert automation.load(db, automation.MEETING_REVIEW) is None


def test_unknown_automation_is_404(client, db, admin):
    _login(client, admin.phone)
    answer = client.post("/team/automations/nope", data={},
                         follow_redirects=False)
    assert answer.status_code == 404


def test_bad_test_room_comes_back_as_a_message(client, db, admin, users):
    from app.services import automation

    _contact(db, users["u2"], room="가나다벤처스 Deal 공유")
    _login(client, admin.phone)
    answer = client.post("/team/automations/channel_top", data={
        "enabled": "", "test_mode": "on", "test_mode_shown": "1",
        "test_room": "가나다벤처스 Deal 공유"}, follow_redirects=False)
    assert answer.status_code == 303
    assert "msg=" in answer.headers["location"]
    db.expire_all()
    assert automation.load(db, automation.CHANNEL_TOP) is None


def test_other_users_jobs_are_untouched(db, users):
    """자동화 회차는 보내는 계정의 회차일 뿐 — 다른 팀원의 회차 수는 그대로다."""
    from app.models import SendJob
    from app.services import automation

    contact = _contact(db, users["u1"])
    automation.build_job(db, sender=users["u2"], kind="deal_intro", title="실제",
                         outs=[automation.Out(room=contact.kakao_room_name,
                                              message="본문",
                                              contact_id=contact.id)])
    db.commit()
    owners = db.execute(select(SendJob.user_id)).scalars().all()
    assert owners == [users["u2"].id]
