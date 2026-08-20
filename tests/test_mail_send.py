"""메일 발송 — 서버가 직접 보낸다.

카톡과 **나가는 길이 다르다**. 카톡은 각자 PC 의 발송 프로그램이, 메일은 서버가
SMTP 로 바로 보낸다. 여기서 지키려는 것.

1. **발송 프로그램이 메일 건을 집어가면 안 된다.** 집어가면 방을 찾다가 실패한다.
2. **주소가 없으면 목록을 만들기 전에 막는다.** 만들고 나서 실패로 남기면
   보냈다고 착각하기 쉽다.
3. **한 건 실패가 나머지를 막지 않는다.** 주소가 틀린 한 사람 때문에
   나머지가 못 받는 것이 가장 나쁘다.
"""
from __future__ import annotations

import smtplib

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


@pytest.fixture()
def mail_on(monkeypatch):
    monkeypatch.setenv("DEALFLOW_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PORT", "465")
    monkeypatch.setenv("DEALFLOW_SMTP_USER", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_FROM", "deal@example.com")
    monkeypatch.setenv("DEALFLOW_SMTP_PASSWORD", "secret")


@pytest.fixture()
def seed(db, users):
    from app.models import IrCompany, SheetOwner, VcContact

    db.add_all([
        SheetOwner(label="내 명단", user_id=users["u1"].id),
        VcContact(user_id=users["u1"].id, name="메일받는분", firm="가나벤처스",
                  source_sheet="내 명단", channel_email=1, channel_kakao=0,
                  email="hong@example.com", connect_stage="connected"),
        VcContact(user_id=users["u1"].id, name="주소없는분", firm="마바벤처스",
                  source_sheet="내 명단", channel_email=1, channel_kakao=0,
                  connect_stage="connected"),
        IrCompany(name="샘플애그", one_liner="B2B 농산물", revenue_recent=12),
    ])
    db.commit()
    return {
        "ok": db.query(VcContact).filter_by(name="메일받는분").first().id,
        "no_addr": db.query(VcContact).filter_by(name="주소없는분").first().id,
        "company": db.query(IrCompany).filter_by(name="샘플애그").first().id,
    }


def _send(client, seed, contact_ids, **extra):
    body = {"company_ids": [seed["company"]], "contact_ids": contact_ids,
            "channel": "email", "title": "메일 회차"}
    body.update(extra)
    return client.post("/api/deals/send", json=body)


# --- 보내기 전 막는 것 ------------------------------------------------------

def test_mail_send_needs_configuration(logged, seed):
    """설정이 없으면 목록조차 만들지 않는다."""
    r = _send(logged, seed, [seed["ok"]])
    assert r.status_code == 400
    assert "메일 서버 설정" in r.json()["detail"]


def test_contact_without_address_is_blocked(logged, seed, mail_on):
    """만들고 나서 실패로 남기면 보냈다고 착각하기 쉽다."""
    from app.models import SendJob

    r = _send(logged, seed, [seed["ok"], seed["no_addr"]])
    assert r.status_code == 400
    assert "주소없는분" in r.json()["detail"]


def test_bad_address_shape_is_blocked(logged, db, seed, mail_on):
    from app.models import VcContact

    row = db.get(VcContact, seed["no_addr"])
    row.email = "주소아님"
    db.commit()
    r = _send(logged, seed, [seed["no_addr"]])
    assert r.status_code == 400
    assert "형식" in r.json()["detail"]


# --- 나가는 길 -------------------------------------------------------------

def test_items_are_marked_as_email(logged, db, seed, mail_on, monkeypatch):
    from app.models import SendItem
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    r = _send(logged, seed, [seed["ok"]], subject="딜 소개 안내")
    assert r.status_code == 200, r.text

    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.channel == "email"
    assert item.room_name == "hong@example.com"     # 주소가 곧 대상이다
    assert item.subject == "딜 소개 안내"


def test_agent_does_not_pick_up_mail(logged, db, seed, mail_on, monkeypatch):
    """발송 프로그램이 메일 건을 집어가면 방을 찾다가 실패한다."""
    from app.models import AgentDevice
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    _send(logged, seed, [seed["ok"]])

    token = db.query(AgentDevice).filter_by(user_id=1).first().token
    r = logged.get("/api/agent/poll?kinds=deal_intro,ir_delivery",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert not r.json().get("items"), "발송 프로그램이 메일 건을 가져갔다"


# --- 실제 발송 -------------------------------------------------------------

def test_sending_marks_each_item(logged, db, seed, mail_on, monkeypatch):
    from app.models import SendItem, SendJob
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    job_id = _send(logged, seed, [seed["ok"]]).json()["job_id"]

    sent = []
    monkeypatch.setattr("app.services.mailer.send_mail",
                        lambda to, subject, body, settings=None: sent.append(to))
    mail_sender._run(db, job_id, gap_sec=0)
    db.expire_all()

    assert sent == ["hong@example.com"]
    assert db.query(SendItem).filter_by(job_id=job_id).one().status == "sent"
    assert db.get(SendJob, job_id).status == "done"


def test_one_failure_does_not_stop_the_rest(logged, db, seed, mail_on, monkeypatch):
    """주소가 틀린 한 사람 때문에 나머지가 못 받는 것이 가장 나쁘다."""
    from app.models import SendItem, VcContact
    from app.services import mail_sender

    db.add(VcContact(user_id=1, name="또다른분", firm="사아파트너스",
                     source_sheet="내 명단", channel_email=1,
                     email="kim@example.com", connect_stage="connected"))
    db.commit()
    other = db.query(VcContact).filter_by(name="또다른분").first().id

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    job_id = _send(logged, seed, [seed["ok"], other]).json()["job_id"]

    def flaky(to, subject, body, settings=None):
        if to == "hong@example.com":
            raise smtplib.SMTPRecipientsRefused({to: (550, b"no such user")})

    monkeypatch.setattr("app.services.mailer.send_mail", flaky)
    result = mail_sender._run(db, job_id, gap_sec=0)
    db.expire_all()

    assert result == {"sent": 1, "failed": 1, "detail": "1건 발송 · 1건 실패"}
    rows = {i.room_name: i for i in db.query(SendItem).filter_by(job_id=job_id).all()}
    assert rows["kim@example.com"].status == "sent"
    assert rows["hong@example.com"].status == "failed"
    assert "거부" in rows["hong@example.com"].error


def test_failure_reason_is_kept(logged, db, seed, mail_on, monkeypatch):
    """무엇을 고쳐야 하는지 알아야 한다 — 사유를 삼키지 않는다."""
    from app.models import SendItem
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    job_id = _send(logged, seed, [seed["ok"]]).json()["job_id"]

    def boom(*_a, **_kw):
        raise smtplib.SMTPAuthenticationError(535, b"bad password")

    monkeypatch.setattr("app.services.mailer.send_mail", boom)
    mail_sender._run(db, job_id, gap_sec=0)
    db.expire_all()
    assert "비밀번호" in db.query(SendItem).filter_by(job_id=job_id).one().error


def test_test_mode_marks_the_subject(logged, db, seed, mail_on, monkeypatch):
    """메일은 방을 하나로 모을 수 없다 — 대신 제목에 표시를 남긴다."""
    from app import config
    from app.models import SendItem
    from app.routers import deals
    from app.services import mail_sender

    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    monkeypatch.setattr(deals.config, "TEST_ROOM", "나와의 채팅")
    job_id = _send(logged, seed, [seed["ok"]], subject="딜 소개").json()["job_id"]
    assert db.query(SendItem).filter_by(job_id=job_id).one().subject == "[테스트] 딜 소개"
