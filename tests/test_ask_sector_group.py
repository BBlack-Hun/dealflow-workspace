"""리마인드 구역 — **선호 투자분야가 빈 분** 묶음과 [선호 분야 묻기 보내기](#101).

1. 대상은 발송 화면 목록(`sheet_owner.recipients`) 중 선호 투자분야가 빈 분이다 —
   방 나감 · 검토중단 · 숨김 · 분야 있음은 안 선다.
2. 선호 분야 묻기 회차에 표시(`SendJob.topic`)가 남고, 최근 30일 안에 물은 분은
   묶음에서 빠진다. 30일이 지났거나 실패한 묻기는 다시 선다.
3. /ir 리마인드 구역의 단추가 지금 발송 화면(`/deals?mode=ask&contacts=…`)을 연다.

이름·회사명은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

from datetime import date, timedelta

from .conftest import DEMO_PASSWORD


def _contact(db, users, name, stage="connected", **extra):
    from app.models import VcContact

    row = VcContact(user_id=users["u1"].id, name=name, title="심사역",
                    firm="가나벤처스", kakao_room_name=f"{name} 심사역님",
                    room_verified="verified", channel_kakao=1,
                    connect_stage=stage, **extra)
    db.add(row)
    db.flush()
    return row


def _asked(db, users, contact, when, status="sent"):
    """`when` 날짜에 나간 선호 분야 묻기 한 건(회차 표시가 있는)."""
    from app.models import SendItem, SendJob
    from app.routers.deals import ASK_TOPIC

    job = SendJob(user_id=users["u1"].id, kind="deal_intro", status="done",
                  topic=ASK_TOPIC)
    db.add(job)
    db.flush()
    stamp = f"{when.isoformat()}T10:00:00+09:00"
    db.add(SendItem(job_id=job.id, contact_id=contact.id, stage=2, room_name="방",
                    message="문구", status=status, sent_at=stamp, created_at=stamp))


def test_group_is_empty_sector_recipients_not_asked_lately(client, db, users):
    from app.routers import followups

    today = date(2026, 10, 30)
    empty = _contact(db, users, "가담당")
    blank = _contact(db, users, "나담당", sectors="  ")
    _contact(db, users, "다담당", sectors="AI")
    _contact(db, users, "라담당", stage="left_room")
    _contact(db, users, "마담당", status="paused")
    _contact(db, users, "바담당", is_hidden=1)
    recent = _contact(db, users, "사담당")
    _asked(db, users, recent, today - timedelta(days=29))
    old = _contact(db, users, "아담당")
    _asked(db, users, old, today - timedelta(days=31))
    failed = _contact(db, users, "자담당")
    _asked(db, users, failed, today - timedelta(days=1), status="failed")
    db.commit()

    got = [c.id for c in followups.no_sector_rows(db, users["u1"], today)]
    assert sorted(got) == sorted([empty.id, blank.id, old.id, failed.id])


def test_ask_send_is_marked_and_drops_out_of_the_group(client, db, users):
    from app.models import SendJob
    from app.routers import followups
    from app.routers.deals import ASK_TOPIC

    first = _contact(db, users, "가담당")
    second = _contact(db, users, "나담당")
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    html = client.get("/ir").text
    section = html[html.index('id="ask-sector"'):]
    link = section[section.index("/deals?mode=ask&contacts="):].split('"')[0]
    assert sorted(link.split("contacts=")[1].split(",")) == sorted(
        [str(first.id), str(second.id)])

    r = client.post("/api/deals/send", json={"mode": "ask", "contact_ids": [first.id],
                                             "title": "선호 분야 묻기"})
    assert r.status_code == 200, r.text
    assert db.get(SendJob, r.json()["job_id"]).topic == ASK_TOPIC
    # 아직 대기 중이어도 뺀다 — 돌아와 또 누르면 두 번 묻는다.
    left = followups.no_sector_rows(db, users["u1"], date.today())
    assert [c.id for c in left] == [second.id]
