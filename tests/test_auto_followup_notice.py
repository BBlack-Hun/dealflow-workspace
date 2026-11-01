"""결과 문의 알림 — 옛 결과 문의 문자를 걷고 **팀원 카톡방**으로 하루 한 통(사용자 결정 2026-11-01).

1. 오늘 물어볼 미팅이 있는 팀원마다 그 팀원 카톡방으로 한 통 —
   `[결과 문의] ○○님(투자사) 외 N건` + `/ir#meetings` 링크. 같은 날 또 돌아도 한 번.
2. 다음 날에도 남아 있으면 또 간다(날마다 한 통).
3. 팀원 카톡방이 비면 보내지 않고 까닭을 남긴다.
4. 주말 · 꺼진 자동화는 아무것도 안 한다. 시험 모드면 시험방으로.
5. 풀기 직전에 결과를 다 적었으면 뺀다.
6. 팀 현황 자동화 목록에 이름과 설명이 선다.

이름·회사명은 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from tests.conftest import DEMO_PASSWORD

TEST_ROOM = "자동화 시험방"
U1_ROOM = "결과 알림 테스트방"
LONG_PAST = "2020-01-06"                 # 결과를 물을 날이 오래전에 지났다


def _at(y, m, d, hh=9, mm=0):
    return datetime(y, m, d, hh, mm).astimezone()


MONDAY, TUESDAY, SATURDAY = _at(2026, 11, 2), _at(2026, 11, 3), _at(2026, 11, 7)


@pytest.fixture()
def due(db, users, monkeypatch):
    """u1 에게 결과 문의 3건(방 있음), u2 에게 1건(방 없음)."""
    from app.models import Meeting, VcContact

    monkeypatch.setenv("DEALFLOW_DOMAIN", "deal.example.org")
    users["u1"].kakao_room_name = U1_ROOM
    meetings = []
    for owner, name, firm in [(users["u1"], "가담당", "가나벤처스"),
                              (users["u1"], "나담당", "다라벤처스"),
                              (users["u1"], "다담당", "마바벤처스"),
                              (users["u2"], "라담당", "사아벤처스")]:
        contact = VcContact(user_id=owner.id, name=name, firm=firm,
                            source_sheet="내 명단", connect_stage="connected")
        db.add(contact)
        db.flush()
        meeting = Meeting(user_id=owner.id, contact_id=contact.id, scheduled_at=LONG_PAST,
                          status="done", done_at=LONG_PAST, followup_due=LONG_PAST,
                          followup_done=0, outcome="reviewing")
        db.add(meeting)
        meetings.append(meeting)
    db.commit()
    return meetings


def _turn_on(db, users, test=False):
    from app.services import automation

    return automation.save(db, automation.FOLLOWUP_NOTICE, enabled=True,
                           user_id=users["u2"].id, test_mode=test, test_room=TEST_ROOM)


def _run(db, now):
    from app.services import automation, automation_runner as runner

    return runner.run_once(db, automation.FOLLOWUP_NOTICE, now)


def _items(db):
    from app.models import SendItem

    db.expire_all()
    return db.execute(select(SendItem).order_by(SendItem.id)).scalars().all()


# ── 1 · 2 · 3. 팀원 카톡방으로 하루 한 통 ────────────────────────────────────

def test_팀원_카톡방으로_하루_한_통_방이_비면_까닭이_선다(db, users, due):
    from app.services import scheduled_send

    _turn_on(db, users)
    result = _run(db, MONDAY)
    assert result["status"] == "ready"
    assert _run(db, _at(2026, 11, 2, 9, 30))["status"] == "done"      # 같은 날 또 — 그대로
    [item] = _items(db)
    assert item.room_name == U1_ROOM and item.contact_id is None
    assert item.message == ("[결과 문의] 가담당님(가나벤처스) 외 2건\n"
                            "https://deal.example.org/ir#meetings")
    assert item.job.user_id == users["u2"].id and item.job.kind == "deal_intro"
    assert scheduled_send.label(scheduled_send.scheduled_at(item.job)) == "11/2(월) 10:00"
    assert ("윤서아 님 결과 문의 1건 — 카톡방 이름이 비어 있습니다(팀 현황 › 자동화)"
            in result["skipped"])
    # 다음 날에도 아직 물어볼 것이 남아 있으면 또 간다.
    item.status, item.sent_at = "sent", "2026-11-02T10:00:30+09:00"
    db.commit()
    assert _run(db, TUESDAY)["status"] == "ready"
    assert len(_items(db)) == 2


def test_한_건이면_외_0건을_안_붙이고_주소가_없으면_링크_줄을_뺀다():
    from app.services.automations import followup_notice as fn

    assert fn.compose([{"name": "가담당", "firm": "가나벤처스"}], "") == "[결과 문의] 가담당님(가나벤처스)"
    assert fn.compose([{"name": "가담당", "firm": ""}, {"name": "나담당"}], "https://x/ir#meetings") == (
        "[결과 문의] 가담당님 외 1건\nhttps://x/ir#meetings")


# ── 4. 주말 · 꺼짐 · 시험 모드 ──────────────────────────────────────────────

def test_주말과_꺼진_자동화는_아무것도_안_한다(db, users, due):
    from app.models import AutoSendRun

    assert _run(db, MONDAY)["status"] == "off"
    _turn_on(db, users)
    assert _run(db, SATURDAY)["status"] == "not_today"
    assert _items(db) == [] and db.execute(select(AutoSendRun)).first() is None


def test_시험_모드면_시험방으로(db, users, due):
    _turn_on(db, users, test=True)
    assert _run(db, MONDAY)["status"] == "ready"
    [item] = _items(db)
    assert item.room_name == TEST_ROOM and item.job.kind == "test_send"
    assert item.message.startswith(f"[시험] 원래 받을 방: {U1_ROOM}")
    assert "[결과 문의] 가담당님(가나벤처스) 외 2건" in item.message


# ── 5. 풀기 직전 ─────────────────────────────────────────────────────────────

def test_풀기_직전에_결과를_다_적었으면_뺀다(db, users, due):
    from app.services import automation_runner as runner

    _turn_on(db, users)
    _run(db, MONDAY)
    for meeting in due[:3]:
        meeting.followup_done = 1
    db.commit()
    job = _items(db)[0].job
    assert runner.prune(db, job, _at(2026, 11, 2, 10, 0)) == 0
    assert "물어볼 결과 문의가 남아 있지 않습니다" in _items(db)[0].error


# ── 6. 팀 현황 ───────────────────────────────────────────────────────────────

def test_팀_현황_자동화_목록에_선다(client, db, users):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    client.post("/login", data={"phone": "01000000009", "password": DEMO_PASSWORD})
    html = client.get("/team").text
    assert "결과 문의 알림" in html and "오늘 결과를 물어볼 미팅이 있는 팀원의 카톡방에" in html
    assert "결과 문의 문자 알림" not in html
