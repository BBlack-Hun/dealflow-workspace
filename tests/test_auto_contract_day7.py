"""#9 계약 Day7 우편 발송 + 미수신 문자 3회 — **계약 완료로 바뀐 날**에서 센다.

1. 계약여부가 계약 완료(무료/유료)로 바뀌면 그날이 적히고(IR 화면 · 따라 고치기 · 시트
   어느 길이든 flush 한 자리), 계약 완료가 아니게 되면 빈다. 새 줄 · 무료 ↔ 유료는 안 적는다.
2. 7일 뒤 판의 시각에 계약 담당 팀원의 카톡방으로 한 통 — 같은 날 두 번 돌아도 한 번.
3. 계약서 수신이 O 가 아니면 14 · 21 · 28일 뒤 그 팀원에게 문자(n/3), O 가 되면 멈춘다.
4. 담당자를 못 맞추거나 팀원 카톡방이 비었으면 안 보내고 까닭을 남긴다.
5. 날이 안 적힌 기존 계약 기업 · 꺼진 자동화는 아무것도 안 한다.
6. 시험 모드에서는 문자도 시험방 카톡으로 간다(진짜 문자는 안 나간다).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

TEST_ROOM = "자동화 시험방"
MEMBER_ROOM = "계약 알림 테스트방"
DONE_ON = "2026-10-05"                       # 월 → 7일 10/12 · 14일 10/19 · 21일 10/26 · 28일 11/2


def _at(y, m, d, hh=9, mm=0):
    return datetime(y, m, d, hh, mm).astimezone()


@pytest.fixture()
def company(db, users):
    from app.models import IrCompany

    users["u1"].kakao_room_name = MEMBER_ROOM
    row = IrCompany(name="샘플우편", contract_status="paid", contract_done_at=DONE_ON,
                    assignee_name="윤서아 > 10/1 강민준")       # 지금 담당자는 화살표 뒤
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def texts(monkeypatch):
    """문자 업체 대신 — 보낸 (번호, 글)을 모은다."""
    from app.services import sms

    sent = []
    monkeypatch.setattr(sms, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "load_settings", lambda: None)
    monkeypatch.setattr(sms, "send", lambda to, text, settings=None: sent.append((to, text)) or "m1")
    return sent


def _turn_on(db, users, test=False):
    from app.services import automation

    return automation.save(db, automation.CONTRACT_DAY7, enabled=True,
                           user_id=users["u2"].id, test_mode=test, test_room=TEST_ROOM)


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.CONTRACT_DAY7, now)


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


# ── 1. 계약 완료로 바뀐 날 ───────────────────────────────────────────────────

def test_계약완료로_바뀐_날이_적히고_아니게_되면_빈다(db, users):
    from app import clock
    from app.models import IrCompany

    today = clock.today().isoformat()
    row = IrCompany(name="샘플도장", contract_status="paid")      # 새 줄 — 옛 계약일 수 있다
    db.add(row)
    db.commit()
    assert row.contract_done_at is None
    row.contract_status = "none"
    db.commit()
    row.contract_status = "free"
    db.commit()
    assert row.contract_done_at == today
    row.contract_done_at = "2026-10-01"
    row.contract_status = "paid"                                  # 무료 → 유료 — 날 그대로
    db.commit()
    assert row.contract_done_at == "2026-10-01"
    row.contract_status = "review"
    db.commit()
    assert row.contract_done_at is None


def test_투자컨설턴트에서_따라온_계약도_날이_적힌다(db, users):
    from app import clock
    from app.models import ConsultingCompany, IrCompany
    from app.services import consulting_sheets as cs

    ir = IrCompany(name="샘플따라")
    db.add(ir)
    db.commit()
    sheet = {s.kind: s.label for s in cs.ensure(db)}["startup"]
    meta = ConsultingCompany(user_id=users["u1"].id, sheet=sheet, position=1,
                             company_name="샘플따라")
    db.add(meta)
    db.commit()
    assert meta.ir_company_id == ir.id
    meta.contract_done = "유료계약완료"
    db.commit()
    db.expire_all()
    ir = db.get(IrCompany, ir.id)
    assert ir.contract_status == "paid" and ir.contract_done_at == clock.today().isoformat()


# ── 2. 7일 뒤 카톡 ───────────────────────────────────────────────────────────

def test_7일_뒤_계약_담당_팀원_방으로_한_번(db, users, company):
    from app.services import scheduled_send
    from app.services.automations import contract_day7 as c7

    _turn_on(db, users)
    assert _run(db, _at(2026, 10, 9))["status"] == "empty"        # 아직
    assert _run(db, _at(2026, 10, 12))["status"] == "ready"
    assert _run(db, _at(2026, 10, 12, 9, 30))["status"] == "done"   # 같은 날 또 — 그대로
    items = _items(db)
    assert len(items) == 1
    item = items[0]
    assert item.room_name == MEMBER_ROOM and item.contact_id is None
    assert item.message == ("[계약서 우편 발송] 샘플우편 — 10/5 계약. 계약서를 우편으로 "
                            "보내 주세요. 받으면 IR 기업현황 '계약서 수신'을 O로 바꿔 주세요.")
    job = item.job
    assert job.user_id == users["u2"].id and job.kind == "deal_intro" and job.topic == c7.POST_KIND
    assert scheduled_send.label(scheduled_send.scheduled_at(job)) == "10/12(월) 10:00"
    # 나간 뒤 다음 날(사흘 안쪽) 다시 돌아도 또 안 간다.
    item.status, item.sent_at = "sent", "2026-10-12T10:00:30+09:00"
    db.commit()
    assert _run(db, _at(2026, 10, 13))["status"] == "empty"
    assert len(_items(db)) == 1


def test_풀기_직전에_계약서를_받았으면_뺀다(db, users, company):
    from app.services import automation_runner as runner

    _turn_on(db, users)
    _run(db, _at(2026, 10, 12))
    company.contract_received = "o"
    db.commit()
    job = _items(db)[0].job
    assert runner.prune(db, job, _at(2026, 10, 12, 10, 0)) == 0
    assert "계약서 수신이 O 입니다" in _items(db)[0].error


def test_문구는_문구_화면에서_고친다(db, users, company):
    from app.models import MessageTemplate
    from app.routers.templates_crud import KIND_LABELS
    from app.services.automations import contract_day7 as c7

    assert {c7.POST_KIND, c7.SMS_TEMPLATE_KIND} <= set(KIND_LABELS)
    db.add(MessageTemplate(kind=c7.POST_KIND, name="우편", body="우편 {기업명} {계약일}"))
    db.commit()
    due = c7.Due(company, 0)
    assert c7.message(db, users["u2"], due) == "우편 샘플우편 10/5"
    assert c7.message(db, users["u2"], c7.Due(company, 2)) == (
        "[계약서 수신 확인 2/3] 샘플우편 계약서 받으셨으면 IR 기업현황 '계약서 수신'을 O로 바꿔 주세요.")


# ── 3. 14 · 21 · 28일 문자 ───────────────────────────────────────────────────

def test_14_21_28일_문자_O가_되면_멈춘다(db, users, company, texts):
    from app.models import SmsNotice
    from app.services.automations import contract_day7 as c7

    _turn_on(db, users)
    assert c7.send_sms(db, _at(2026, 10, 19, 9, 30))["status"] == "not_now"   # 판의 시각 전
    assert c7.send_sms(db, _at(2026, 10, 19, 10, 30))["sent"] == 1
    assert c7.send_sms(db, _at(2026, 10, 19, 11, 0))["sent"] == 0             # 같은 날 또
    assert c7.send_sms(db, _at(2026, 10, 20, 10, 30))["sent"] == 0            # 다음 날도
    assert c7.send_sms(db, _at(2026, 10, 26, 10, 30))["sent"] == 1
    assert texts == [
        ("01000000001", "[계약서 수신 확인 1/3] 샘플우편 계약서 받으셨으면 IR 기업현황 "
                        "'계약서 수신'을 O로 바꿔 주세요."),
        ("01000000001", "[계약서 수신 확인 2/3] 샘플우편 계약서 받으셨으면 IR 기업현황 "
                        "'계약서 수신'을 O로 바꿔 주세요.")]
    company.contract_received = "O"
    db.commit()
    assert c7.send_sms(db, _at(2026, 11, 2, 10, 30))["sent"] == 0
    assert len(texts) == 2
    kinds = db.execute(select(SmsNotice.kind, SmsNotice.status)).all()
    assert sorted(kinds) == [(f"contract_receipt:{company.id}:1", "sent"),
                             (f"contract_receipt:{company.id}:2", "sent")]


def test_실제_모드_문자는_카톡_회차에_안_실린다(db, users, company, texts):
    _turn_on(db, users)
    result = _run(db, _at(2026, 10, 19))
    assert result["status"] == "empty" and _items(db) == []


# ── 4. 못 맞추면 안 보내고 까닭을 남긴다 ─────────────────────────────────────

def test_담당자_못_맞춤_방_비었음이면_안_보내고_까닭이_선다(db, users, company, texts, monkeypatch):
    from app import clock
    from app.models import IrCompany
    from app.services import automation_runner as runner
    from app.services.automations import contract_day7 as c7

    users["u1"].kakao_room_name = None
    db.add(IrCompany(name="샘플없는", contract_status="free", contract_done_at=DONE_ON,
                     assignee_name="없는팀원"))
    db.commit()
    _turn_on(db, users)
    result = _run(db, _at(2026, 10, 12))
    assert result["status"] == "empty" and _items(db) == []
    joined = " / ".join(result["skipped"])
    assert "샘플우편 · 카톡 — 강민준 님의 카톡방 이름이 비어 있습니다" in joined
    assert "샘플없는 · 카톡 — 담당자 '없는팀원' 을 팀원 계정에서 못 찾았습니다" in joined
    monkeypatch.setattr(clock, "now", lambda: _at(2026, 10, 12, 9, 5))    # 판을 그날 연다
    state = runner.status_of(db, "contract_day7")
    assert "안 보내는 까닭 2" in state["describe"] and "없는팀원" in state["describe"]
    assert "없는팀원" in state["today"]["error"]
    # 문자는 방이 아니라 번호로 간다 — 못 맞춘 곳만 빠진다.
    assert c7.send_sms(db, _at(2026, 10, 19, 10, 30))["sent"] == 1
    assert [t for _n, t in texts if "샘플없는" in t] == []


# ── 5. 기존 계약 · 꺼짐 ──────────────────────────────────────────────────────

def test_날이_안_적힌_기존_계약_기업은_안_건다(db, users, texts):
    from app.models import IrCompany
    from app.services.automations import contract_day7 as c7

    users["u1"].kakao_room_name = MEMBER_ROOM
    db.add(IrCompany(name="샘플옛계약", contract_status="paid", assignee_name="강민준"))
    db.commit()
    _turn_on(db, users)
    assert _run(db, _at(2026, 10, 12))["status"] == "empty"
    assert c7.send_sms(db, _at(2026, 10, 19, 10, 30))["sent"] == 0
    assert _items(db) == [] and texts == []


def test_꺼져_있으면_아무것도_안_한다(db, users, company, texts):
    from app.models import AutoSendRun, SmsNotice
    from app.services.automations import contract_day7 as c7

    assert _run(db, _at(2026, 10, 12))["status"] == "off"
    assert c7.send_sms(db, _at(2026, 10, 19, 10, 30))["status"] == "off"
    assert _items(db) == [] and texts == []
    assert db.execute(select(AutoSendRun)).first() is None
    assert db.execute(select(SmsNotice)).first() is None


# ── 6. 시험 모드 ─────────────────────────────────────────────────────────────

def test_시험_모드에서는_문자도_시험방_카톡으로(db, users, company, texts):
    from app.services.automations import contract_day7 as c7

    _turn_on(db, users, test=True)
    assert _run(db, _at(2026, 10, 19))["status"] == "ready"
    item = _items(db)[0]
    assert item.room_name == TEST_ROOM and item.job.kind == "test_send"
    assert item.message.startswith("[시험] 원래 받을 방: 문자 → 강민준")
    assert "[계약서 수신 확인 1/3] 샘플우편" in item.message
    assert c7.send_sms(db, _at(2026, 10, 19, 10, 30))["status"] == "off" and texts == []


# ── 팀 현황 — 팀원 카톡방 ────────────────────────────────────────────────────

def test_팀_현황에서_팀원_카톡방을_넣고_실제_상대_방은_막는다(client, db, users):
    from app.models import User, VcContact
    from app.services import auth as auth_svc

    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.add(VcContact(user_id=users["u1"].id, name="홍길동", firm="가나다벤처스",
                     kakao_room_name="가나다벤처스 Deal 공유", source_sheet="내 명단"))
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    r = client.post("/team/member-rooms", data={"room_1": f" {MEMBER_ROOM} ",
                                                "room_2": "가나다벤처스 deal공유"},
                    follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert db.get(User, 1).kakao_room_name == MEMBER_ROOM
    assert db.get(User, 2).kakao_room_name is None
    html = client.get("/team").text
    assert 'name="room_1"' in html and f'value="{MEMBER_ROOM}"' in html


def test_판_이름은_0119_다음_0120이다():
    src = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "0120_contract_day7.py").read_text("utf-8")
    assert 'revision = "0120_contract_day7"' in src
    assert 'down_revision = "0119_ir_success_fee"' in src
