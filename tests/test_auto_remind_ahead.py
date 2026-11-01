"""#112 다가오는 미팅·후속라운드 미리 알림 — D-10 · D-7 · D-4 · D-1, 담당 팀원 카톡방(사용자 결정 2026-11-01).

1. 회차 날 — 토·일이면 앞 금요일.
2. 그날 걸린 건을 팀원마다 한 통으로 묶는다(예정 미팅 + 매출예상리스트 후속라운드), 같은 날 또 돌아도 한 번.
3. 지난 회차는 건너뛴다 — 늦게 등록된 건은 남은 회차만. 예정이 아닌 미팅은 안 센다.
4. 방 이름이 빈 팀원은 보내지 않고 까닭이 선다(판의 상태 칸에도).
5. 주말 · 꺼진 자동화는 아무것도 안 한다. 시험 모드면 시험방으로.
6. 풀기 직전에 알릴 건이 없어졌으면 뺀다.
7. 문구 화면의 글을 쓴다 — `{목록}` 이 없으면 글 끝에.
8. 같은 팀원 방을 다른 팀원 알림보다 먼저 잡는다(같은 방 하루 1통).
9. 팀 현황 자동화 목록에 이름과 설명이 선다.

이름·회사명·방 이름은 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

TEST_ROOM = "자동화 시험방"
U1_ROOM = "미리 알림 테스트방"
MEETING_DAY = "2026-11-27"          # 금 — 회차 11/17(화) · 11/20(금) · 11/23(월) · 11/26(목)
FOLLOW_MONTH = "2026-12"            # 12/1(화) — 회차 11/20(금, 21일 토에서 당김) · 11/24 · 11/27 · 11/30


def _at(y, m, d, hh=9, mm=0):
    return datetime(y, m, d, hh, mm).astimezone()


@pytest.fixture()
def due(db, users):
    """u1: 11/27 미팅 + 12월 후속라운드(방 있음), u2: 11/27 미팅(방 없음) — 11/20 에 셋 다 걸린다."""
    from app.models import Meeting, RevenueForecast, VcContact

    users["u1"].kakao_room_name = U1_ROOM
    meetings = []
    for owner, firm, company in [(users["u1"], "다라벤처스", "가나바이오"),
                                 (users["u2"], "사아벤처스", "마바로보틱스")]:
        contact = VcContact(user_id=owner.id, name="가담당", firm=firm,
                            source_sheet="내 명단", connect_stage="connected")
        db.add(contact)
        db.flush()
        meeting = Meeting(user_id=owner.id, contact_id=contact.id, company_name=company,
                          scheduled_at=MEETING_DAY, status="scheduled")
        db.add(meeting)
        meetings.append(meeting)
    db.add(RevenueForecast(user_id=users["u1"].id, company_name="샘플후속",
                           follow_round_month=FOLLOW_MONTH))
    db.commit()
    return meetings


def _turn_on(db, users, test=False):
    from app.services import automation

    return automation.save(db, automation.REMIND_AHEAD, enabled=True,
                           user_id=users["u2"].id, test_mode=test, test_room=TEST_ROOM)


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.REMIND_AHEAD, now)


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


# ── 1. 회차 날 ───────────────────────────────────────────────────────────────

def test_회차_날은_10_7_4_1일_전_토일이면_앞_금요일():
    from app.services.automations import remind_ahead as ra

    monday = date(2026, 11, 16)
    assert [ra.send_day(monday, n) for n in ra.DAYS] == [
        date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 12), date(2026, 11, 13)]
    assert ra.send_day(date(2026, 12, 1), 10) == date(2026, 11, 20)


# ── 2 · 4. 팀원마다 한 통 · 빈 방 ──────────────────────────────────────────

def test_그날_걸린_건을_팀원마다_한_통으로_묶고_빈_방은_까닭이_선다(db, users, due, monkeypatch):
    from app import clock
    from app.models import AutomationSend
    from app.services import automation_runner as runner

    _turn_on(db, users)
    result = _run(db, _at(2026, 11, 20))
    assert result["status"] == "ready"
    assert _run(db, _at(2026, 11, 20, 9, 30))["status"] == "done"     # 같은 날 또 — 그대로
    [item] = _items(db)
    assert item.room_name == U1_ROOM and item.contact_id is None
    assert item.message == ("[미리 알림]\n"
                            "11/27(금) 미팅 — 가나바이오 × 다라벤처스 (D-7)\n"
                            "12월 후속라운드 시작 — 샘플후속 (D-11)")
    assert item.job.user_id == users["u2"].id and item.job.kind == "deal_intro"
    assert "윤서아 님 미리 알림 1건 — 카톡방 이름이 비어 있습니다(팀 현황 › 자동화)" in result["skipped"]
    refs = {r for (r,) in db.execute(select(AutomationSend.ref)).all()}
    assert refs == {f"user:{users['u1'].id}:2026-11-20"}
    monkeypatch.setattr(clock, "now", lambda: _at(2026, 11, 20, 9, 5))
    state = runner.status_of(db, "remind_ahead")
    assert "미리 알림 기다리는 건 3" in state["describe"]
    assert "윤서아 님 카톡방 이름 없음" in state["describe"]


# ── 3. 지난 회차 · 예정 아닌 미팅 ────────────────────────────────────────────

def test_지난_회차는_건너뛰고_예정이_아닌_미팅은_안_센다(db, users, due):
    _turn_on(db, users)
    assert _run(db, _at(2026, 11, 18))["status"] == "empty"           # 11/17 회차를 몰아 안 보낸다
    assert _run(db, _at(2026, 11, 23))["status"] == "ready"
    [item] = _items(db)
    assert item.message == "[미리 알림]\n11/27(금) 미팅 — 가나바이오 × 다라벤처스 (D-4)"
    due[0].status = "canceled"
    db.commit()
    assert _run(db, _at(2026, 11, 26))["status"] == "empty"           # D-1 이지만 취소


# ── 5. 주말 · 꺼짐 · 시험 모드 ──────────────────────────────────────────────

def test_주말과_꺼진_자동화는_아무것도_안_한다(db, users, due):
    from app.models import AutoSendRun

    assert _run(db, _at(2026, 11, 20))["status"] == "off"
    _turn_on(db, users)
    assert _run(db, _at(2026, 11, 21))["status"] == "not_today"
    assert _items(db) == [] and db.execute(select(AutoSendRun)).first() is None


def test_시험_모드면_시험방으로(db, users, due):
    _turn_on(db, users, test=True)
    assert _run(db, _at(2026, 11, 20))["status"] == "ready"
    [item] = _items(db)
    assert item.room_name == TEST_ROOM and item.job.kind == "test_send"
    assert item.message.startswith(f"[시험] 원래 받을 방: {U1_ROOM}")


# ── 6. 풀기 직전 ─────────────────────────────────────────────────────────────

def test_풀기_직전에_알릴_건이_없어졌으면_뺀다(db, users, due):
    from app.models import RevenueForecast
    from app.services import automation_runner as runner

    _turn_on(db, users)
    _run(db, _at(2026, 11, 20))
    due[0].scheduled_at = "2026-12-04"                                # 미팅을 옮겼다
    db.query(RevenueForecast).delete()
    db.commit()
    job = _items(db)[0].job
    assert runner.prune(db, job, _at(2026, 11, 20, 10, 0)) == 0
    assert "알릴 미팅 · 후속라운드가 남아 있지 않습니다" in _items(db)[0].error


# ── 7. 문구 화면 ─────────────────────────────────────────────────────────────

def test_문구_화면의_글을_쓰고_목록_자리가_없으면_글_끝에(db, users):
    from app.models import MessageTemplate
    from app.services.automations import remind_ahead as ra

    assert ra.compose(db, users["u2"], ["가", "나"]) == "[미리 알림]\n가\n나"
    db.add(MessageTemplate(kind=ra.TEMPLATE_KIND, name="팀", body="다가오는 일정입니다"))
    db.commit()
    assert ra.compose(db, users["u2"], ["가", "나"]) == "다가오는 일정입니다\n가\n나"


# ── 8. 다른 팀원 알림과 같은 방 ─────────────────────────────────────────────

def test_같은_팀원_방을_결과_문의_알림보다_먼저_잡는다(db, users, due):
    from app.models import Meeting, VcContact
    from app.services import automation, automation_runner as runner

    other = VcContact(user_id=users["u1"].id, name="나담당", firm="자차벤처스",
                      source_sheet="내 명단", connect_stage="connected")
    db.add(other)
    db.flush()
    db.add(Meeting(user_id=users["u1"].id, contact_id=other.id, scheduled_at="2020-01-06",
                   status="done", done_at="2020-01-06", followup_due="2020-01-06",
                   followup_done=0, outcome="reviewing"))
    db.commit()
    _turn_on(db, users)
    automation.save(db, automation.FOLLOWUP_NOTICE, enabled=True, user_id=users["u2"].id,
                    test_mode=False, test_room=TEST_ROOM)
    out = runner.run_all(db, _at(2026, 11, 20))
    assert out["remind_ahead"]["status"] == "ready"
    assert out["followup_notice"]["status"] == "empty"
    assert any("중복 방지" in s for s in out["followup_notice"]["skipped"])
    [item] = _items(db)
    assert item.message.startswith("[미리 알림]")


# ── 9. 팀 현황 ───────────────────────────────────────────────────────────────

def test_팀_현황_자동화_목록에_선다(client, db, users):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    html = client.get("/team").text
    assert "다가오는 미팅·후속라운드 미리 알림" in html
    assert "10·7·4·1일 전" in html
