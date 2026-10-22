"""카톡방을 **나간** 분(`방 나감`)은 카톡으로 보내지 않는다.

10/22 리마인드 107명에 방을 나간 분 2명이 섞였다. 방 이름이 그대로 남아
있어서 발송 목록을 만드는 자리의 방 이름 검사로는 안 걸렸다.

지키는 것.

1. **오늘 보낼 리마인드** 판의 [보내기] 묶음에서 빠지고, 접힌 줄로 이름이
   남는다. 리마인드 줄은 **건드리지 않는다** — 단계를 되돌리면 다시 선다.
2. **발송 목록 만들기**가 카톡이면 빼고, 뺀 분과 이유를 돌려준다.
3. 미리보기가 몇 명 빠지는지 먼저 말한다.
4. 다른 단계 · 메일 · 시험 발송 · 그룹 예약 발송은 그대로다.

이름·회사명은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

DUE = "2026-01-05"   # 지난 날 — 시계와 상관없이 `오늘 보낼` 판에 선다


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _contact(db, users, name, stage="connected", **extra):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name=name, title="심사역",
                    firm="가나벤처스", kakao_room_name=f"{name} 심사역님",
                    room_verified="verified", channel_kakao=1,
                    connect_stage=stage, **extra)
    db.add(row)
    db.flush()
    return row


def _due_reminder(db, users, contact):
    """딜소개가 나가고 **리마인드 날이 지난** 줄 하나 — `cadence` 를 그대로 태운다."""
    from app.models import DealBatch, SendItem, SendJob
    from app.services import cadence

    batch = DealBatch(user_id=users["u1"].id, title="1회차", sent_date="2026-01-01")
    db.add(batch)
    db.flush()
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, contact_id=contact.id, stage=1, room_name="방",
                    message="문구", status="sent", sent_at="2026-01-01T09:00:00+09:00")
    db.add(item)
    db.flush()
    seq = cadence.start_or_advance(db, item, job)
    seq.next_due_date = DUE
    db.commit()
    return seq


@pytest.fixture()
def board(db, users):
    stay = _contact(db, users, "가담당")
    left = _contact(db, users, "나담당", stage="left_room")
    return {"stay": stay, "left": left,
            "stay_seq": _due_reminder(db, users, stay),
            "left_seq": _due_reminder(db, users, left)}


def _remind_section(html: str) -> str:
    start = html.index('<div id="remind">')
    return html[start:html.index('class="dash-grid"', start)]


# --- 1. 오늘 보낼 리마인드 판 ---------------------------------------------------

def test_the_board_leaves_out_who_left_the_room(logged, db, users, board):
    from app.routers import followups

    ctx = followups.remind_context(db, users["u1"], date(2026, 1, 10))
    sent_ids = [r["contact_id"] for g in ctx["due_groups"] for r in g["rows"]]
    assert sent_ids == [board["stay"].id]
    assert [r["contact_id"] for r in ctx["due_left_room"]] == [board["left"].id]
    assert ctx["remind_counts"]["due"] == 1

    section = _remind_section(logged.get("/ir").text)
    # [보내기] 링크에 그 분 번호가 없다 — 눌러도 발송 화면에서 안 켜진다.
    send_link = section[section.index("/deals?mode="):].split('"')[0]
    assert str(board["left"].id) not in send_link.split("contacts=")[1].split(",")
    assert "방 나감 1명 — 보내지 않음" in section
    assert "나담당" in section


def test_the_reminder_row_is_not_touched_and_comes_back(logged, db, users, board):
    """줄을 멈추거나 닫지 않는다 — 단계를 되돌리면 다음 화면부터 다시 선다."""
    from app.models import SendSequence
    from app.routers import followups

    logged.get("/ir")
    db.expire_all()
    seq = db.get(SendSequence, board["left_seq"].id)
    assert seq.status == "active" and seq.next_due_date == DUE

    board["left"].connect_stage = "connected"
    db.commit()
    ctx = followups.remind_context(db, users["u1"], date(2026, 1, 10))
    sent_ids = {r["contact_id"] for g in ctx["due_groups"] for r in g["rows"]}
    assert sent_ids == {board["stay"].id, board["left"].id}
    assert ctx["due_left_room"] == []


def test_the_jump_bar_count_matches_the_board(db, users, board):
    from app.services import flow

    assert flow.counts(db, users["u1"], date(2026, 1, 10))["due"] == 1


@pytest.mark.parametrize("stage", ["in_progress", "declined", "not_started"])
def test_other_stages_stay_on_the_board(db, users, stage):
    """`방 나감` 만 빠진다 — 다른 단계는 지금까지 그대로다."""
    from app.routers import followups

    row = _contact(db, users, "다담당", stage=stage)
    _due_reminder(db, users, row)
    ctx = followups.remind_context(db, users["u1"], date(2026, 1, 10))
    assert [r["contact_id"] for g in ctx["due_groups"] for r in g["rows"]] == [row.id]
    assert ctx["due_left_room"] == []


# --- 2. 발송 목록 만들기 ---------------------------------------------------------

def _send(client, ids, **extra):
    body = {"contact_ids": ids, "mode": "remind", "title": "리마인드"}
    body.update(extra)
    return client.post("/api/deals/send", json=body)


def test_the_send_list_skips_who_left_the_room(logged, db, users):
    from app.models import SendItem

    stay = _contact(db, users, "가담당")
    left = _contact(db, users, "나담당", stage="left_room")
    db.commit()

    r = _send(logged, [stay.id, left.id])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert [s["contact_id"] for s in body["skipped"]] == [left.id]
    assert "방 나감" in body["skipped"][0]["reason"]
    items = db.query(SendItem).filter_by(job_id=body["job_id"]).all()
    assert [i.contact_id for i in items] == [stay.id]


def test_only_people_who_left_the_room_is_refused(logged, db, users):
    from app.models import SendJob

    left = _contact(db, users, "나담당", stage="left_room")
    db.commit()
    r = _send(logged, [left.id])
    assert r.status_code == 400
    assert "나담당" in r.json()["detail"] and "방 나감" in r.json()["detail"]
    assert db.query(SendJob).count() == 0


def test_other_stages_are_not_skipped(logged, db, users):
    """연결 단계로 막는 것은 `방 나감` 하나다 — 나머지는 지금까지 그대로."""
    ids = [_contact(db, users, f"{n}담당", stage=s).id
           for n, s in (("가", "connected"), ("나", "in_progress"),
                        ("다", "declined"), ("라", "not_started"))]
    db.commit()
    r = _send(logged, ids)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 4 and r.json()["skipped"] == []


def test_mail_is_not_blocked_by_leaving_the_room(logged, db, users, monkeypatch):
    """방을 나간 것이 메일을 거절한 것은 아니다 — 메일은 그대로 나간다."""
    from app.services import mail_sender

    monkeypatch.setenv("DEALFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PORT", "465")
    monkeypatch.setenv("DEALFLOW_SMTP_USER", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_FROM", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PASSWORD", "secret")
    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)

    left = _contact(db, users, "나담당", stage="left_room", channel_email=1,
                    email="na@example.com")
    db.commit()
    r = _send(logged, [left.id], channel="email")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1 and r.json()["skipped"] == []


# --- 3. 미리보기 -----------------------------------------------------------------

def test_the_preview_says_how_many_are_left_out(logged, db, users):
    stay = _contact(db, users, "가담당")
    left = _contact(db, users, "나담당", stage="left_room")
    db.commit()

    body = logged.post("/api/deals/preview", json={
        "contact_ids": [stay.id, left.id], "mode": "remind"}).json()
    assert body["left_room"] == 1
    assert any(w.startswith("방 나감 1명 제외") and "나담당" in w
               for w in body["warnings"]), body["warnings"]

    mail = logged.post("/api/deals/preview", json={
        "contact_ids": [stay.id, left.id], "mode": "remind",
        "channel": "email"}).json()
    assert mail["left_room"] == 0
    assert not any("방 나감" in w for w in mail["warnings"])


# --- 4. 시험 발송 · 그룹 예약 발송은 그대로 ----------------------------------------

def test_the_test_send_still_goes_to_the_test_room(logged, db, users, monkeypatch):
    """시험 발송은 담당자 방이 아니라 시험방으로 간다 — 단계와 상관없다."""
    from app import config
    from app.models import Meeting, SendItem

    monkeypatch.setattr(config, "TEST_ROOM", "나와의 채팅")
    left = _contact(db, users, "나담당", stage="left_room")
    meeting = Meeting(user_id=users["u1"].id, contact_id=left.id,
                      scheduled_at="2026-01-01", kind="first", status="done",
                      done_at="2026-01-01", outcome="reviewing",
                      followup_due="2026-01-11", followup_done=0)
    db.add(meeting)
    db.commit()

    r = logged.post("/setup/test/meeting-review", data={"meeting_id": meeting.id},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/jobs/")
    job_id = int(r.headers["location"].rsplit("/", 1)[1])
    item = db.query(SendItem).filter_by(job_id=job_id).one()
    assert item.room_name == "나와의 채팅"


def test_group_sends_are_unchanged(logged, db, users):
    """그룹 예약 발송은 원래 `연결 완료` 만 센다 — 뺄 사람이 처음부터 없다."""
    from app.models import IrCompany

    company = IrCompany(name="가나애그", one_liner="B2B 농산물", summary="요약문",
                        summary_status="done", revenue_recent=12)
    db.add(company)
    stay = _contact(db, users, "가담당", group_name="1군", source_sheet="가 명단")
    _contact(db, users, "나담당", stage="left_room", group_name="1군",
             source_sheet="가 명단")
    db.commit()

    made = logged.post("/api/deals/queue", json={
        "group_name": "1군", "company_ids": [company.id], "title": "회차"}).json()
    assert made["target_count"] == 1
    r = logged.post(f"/api/deals/queue/{made['item_id']}/start",
                    json={"shown": 1, "confirmed": False})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1 and r.json()["skipped"] == []
    from app.models import SendItem
    assert [i.contact_id for i in db.query(SendItem).filter_by(
        job_id=r.json()["job_id"])] == [stay.id]
