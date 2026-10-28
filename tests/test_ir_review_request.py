"""IR 자료 검토 요청(#79) — 전달한 자료 → 검토 요청 → 상태 표시 → 미팅 요청.

10/28 담당자 '추천대로'. 여기서 못 박는 것.

1. 「전달한 자료」 투자사명은 `IR 자료 검토 요청` 탭으로 열고, 미팅 요청은 줄에 따로 선다.
2. [IR 자료 검토 요청 보냄] 은 이제 **검토 요청** 표시다 — 상태가 `IR 자료 검토 요청 완료 ·
   날짜`, 빨간 경보가 걷히고, 전화 요청 단추가 선다. 미팅 요청 손 기록은 [미팅 요청 보냄].
3. 발송 화면 `IR 자료 검토 요청` 탭으로 보내면 회차에 표시(`topic`)가 남고, 나간 뒤
   같은 상태가 선다. 미팅 요청 판정(업무 보고 · 자동화 A2)은 그대로다.

이름·기업명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _delivered(db, users, *, days=30):
    from app.models import IrRequest, SheetOwner, VcContact

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="가담당", title="심사역",
                        firm="가나벤처스", source_sheet="내 명단", channel_kakao=1,
                        connect_stage="connected", kakao_room_name="가담당 심사역님",
                        room_verified="verified")
    db.add(contact)
    db.flush()
    when = (date.today() - timedelta(days=days)).isoformat()
    db.add(IrRequest(user_id=users["u1"].id, contact_id=contact.id, company_name="샘플애그",
                     requested_at=when, status="delivered", delivered_at=when))
    db.commit()
    return contact


def test_투자사명은_검토_요청으로_미팅_요청은_줄에_따로(db, users, logged):
    contact = _delivered(db, users)
    body = logged.get("/ir").text
    assert f'href="/deals?mode=ir_review&contacts={contact.id}"' in body
    assert f'href="/deals?mode=meeting&contacts={contact.id}"' in body
    assert 'class="status-when bad">IR 자료 검토 요청 미완료 · 30일' in body
    assert 'class="overdue-row"' in body
    assert ">IR 자료 검토 요청 보냄</button>" in body
    assert ">미팅 요청 보냄</button>" in body
    # 아직 아무 말도 안 나간 줄에는 전화 요청 단추가 없다(#37).
    assert f'data-call-flag="{contact.id}"' not in body


def test_검토_요청_보냄을_누르면_완료가_서고_경보가_걷힌다(db, users, logged):
    from app.models import ContactActivity
    from app.services import pipeline

    contact = _delivered(db, users)
    res = logged.post(f"/ir/contacts/{contact.id}/review-asked", follow_redirects=False)
    assert res.status_code == 303
    act = db.query(ContactActivity).filter_by(contact_id=contact.id).one()
    assert act.kind == pipeline.IR_REVIEW_KIND

    body = logged.get("/ir").text
    assert f"IR 자료 검토 요청 완료 · {date.today().isoformat()}" in body
    assert "IR 자료 검토 요청 미완료" not in body
    assert 'class="overdue-row"' not in body
    assert ">IR 자료 검토 요청 보냄</button>" not in body
    assert ">미팅 요청 보냄</button>" in body, "미팅 요청은 아직이다"
    assert f'data-call-flag="{contact.id}"' in body, "검토 요청 뒤에도 전화 요청이 선다"
    # 미팅 요청 판정은 그대로 — 업무 보고 · 자동화 A2 는 미팅 요청만 센다.
    from app.models import IrRequest
    st = pipeline.meeting_ask_state(db, db.query(IrRequest).all())[contact.id]
    assert st["reviewed"] and not st["asked"]


def test_미팅_요청_보냄은_미팅_요청으로_적힌다(db, users, logged):
    contact = _delivered(db, users)
    logged.post(f"/ir/contacts/{contact.id}/meeting-asked")
    body = logged.get("/ir").text
    assert f"회의실 미팅 톡 요청 보냄 완료 · {date.today().isoformat()}" in body
    assert "IR 자료 검토 요청 완료" not in body
    assert ">IR 자료 검토 요청 보냄</button>" not in body


def test_검토_요청_탭으로_보내면_회차에_표시가_남고_나간_뒤_완료가_선다(db, users, logged):
    from app.models import IrRequest, SendItem, SendJob
    from app.routers import deals
    from app.services import pipeline

    contact = _delivered(db, users)
    res = logged.post("/api/deals/send", json={
        "mode": deals.MODE_IR_REVIEW, "company_ids": [], "contact_ids": [contact.id]})
    assert res.status_code == 200, res.text
    job = db.get(SendJob, res.json()["job_id"])
    assert job.topic == pipeline.IR_REVIEW_KIND and job.kind == "deal_intro"
    item = db.query(SendItem).filter_by(job_id=job.id).one()
    assert item.stage == 2
    assert "IR 자료는 검토해 보셨을지요" in item.message   # 팀 문구가 없으면 폴백

    item.status, item.sent_at = "sent", f"{date.today().isoformat()}T11:00:00+09:00"
    db.commit()
    st = pipeline.meeting_ask_state(db, db.query(IrRequest).all())[contact.id]
    assert st["reviewed"] and st["reviewed_at"] == date.today().isoformat()
    assert f"IR 자료 검토 요청 완료 · {date.today().isoformat()}" in logged.get("/ir").text


def test_문구_관리와_발송_화면에_검토_요청이_선다(logged):
    from app.routers import templates_crud

    assert "ir_review_request" in templates_crud.KIND_LABELS
    assert 'data-mode="ir_review"' in logged.get("/deals").text
    assert "IR 자료 검토 요청" in logged.get("/templates").text
