"""딜소개 → 자료 요청으로 이어지는 길이 끊기지 않는가.

투자사가 "2, 4 주세요" 라고 답했을 때, 사람이 하는 일은 세 가지다.
그 셋이 각각 막혀 있었다.

    ① 후속 화면에서 그 사람을 보고 → IR 요청 화면으로 옮겨 담당자를 다시 고른다
    ② 번호가 어느 기업인지 지난 카톡을 뒤진다
    ③ 회차명을 손으로 적는다
"""
from __future__ import annotations

from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def sent_batch(client, db, users):
    """담당자 1명에게 기업 3개를 보낸 상태."""
    from app.models import (DealBatch, DealBatchCompany, IrCompany, SendItem,
                            SendJob, SheetOwner, VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 심사역님")
    companies = [IrCompany(name=n) for n in ("샘플애그", "샘플메디", "샘플로지")]
    batch = DealBatch(user_id=users["u1"].id, title="8월 3주차",
                      sent_date="2026-08-19")
    db.add_all([contact, batch] + companies)
    db.commit()

    for i, company in enumerate(companies, start=1):
        db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id,
                                position=i))
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.commit()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, status="sent",
                    room_name="홍길동 심사역님", message="…",
                    sent_at="2026-08-19T09:00:00+00:00"))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "contact": contact, "companies": companies}


# --- ② 번호로 적기 -----------------------------------------------------------

def test_numbers_become_companies(sent_batch, db):
    """"2, 4" 를 이름으로 읽으면 `2` 라는 기업의 요청이 만들어진다."""
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id, "company_name": "2, 3"})

    rows = db.query(IrRequest).order_by(IrRequest.id).all()
    assert [r.company_name for r in rows] == ["샘플메디", "샘플로지"]
    assert all(r.company_id is not None for r in rows), "기업까지 이어져야 한다"


def test_numbers_and_names_can_mix(sent_batch, db):
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id,
        "company_name": "1, 샘플로지"})
    assert {r.company_name for r in db.query(IrRequest).all()} == {"샘플애그", "샘플로지"}


def test_the_same_company_twice_is_one_request(sent_batch, db):
    """번호로도 이름으로도 적었다 — 요청이 두 개 생기면 두 번 보낸다."""
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id,
        "company_name": "1, 샘플애그"})
    assert db.query(IrRequest).count() == 1


def test_a_number_that_was_never_sent_is_not_silently_kept(sent_batch, db):
    """없는 번호를 이름으로 남기면 `9` 라는 기업이 생긴다."""
    from app.models import IrRequest

    r = sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id, "company_name": "1, 9"})

    assert db.query(IrRequest).count() == 1
    assert "9" in r.headers["location"], "건너뛴 번호를 알려 줘야 한다"


def test_only_numbers_and_none_of_them_valid(sent_batch, db):
    from app.models import IrRequest

    sent_batch["client"].post("/ir/requests", follow_redirects=False, data={
        "contact_id": sent_batch["contact"].id, "company_name": "8, 9"})
    assert db.query(IrRequest).count() == 0


# --- ① 후속에서 바로 넘어가기 -------------------------------------------------

def test_followup_names_link_to_the_request_form(sent_batch, db):
    from app.models import SendSequence

    db.add(SendSequence(user_id=sent_batch["contact"].user_id,
                        contact_id=sent_batch["contact"].id, stage=1,
                        next_stage=2, status="active",
                        next_due_date=(date.today()).isoformat()))
    db.commit()

    body = sent_batch["client"].get("/followups").text
    assert f'/ir?contact={sent_batch["contact"].id}' in body


def test_arriving_with_a_contact_opens_the_form_ready(sent_batch):
    contact_id = sent_batch["contact"].id
    body = sent_batch["client"].get(f"/ir?contact={contact_id}").text
    assert f'value="{contact_id}" selected' in body
    assert '<div class="member-form" id="new-request" >' in body or \
           'id="new-request" >' in body, "폼이 열린 채로 떠야 한다"


# --- ③ 회차명 · 주차 -----------------------------------------------------------

def test_batch_title_is_filled_in(sent_batch):
    import re

    body = sent_batch["client"].get("/deals").text
    m = re.search(r'id="batch-title" value="([^"]*)"', body)
    assert m, "회차명 칸이 없다"
    assert re.fullmatch(r"\d+월 \d주차", m.group(1)), m.group(1)


def test_every_screen_counts_weeks_the_same_way():
    """같은 날이 화면마다 3주차·4주차로 갈리면 안 된다 — 실제로 갈렸다."""
    from app.services import cadence, report, sheet_import

    for iso in ("2026-08-04", "2026-08-13", "2026-08-19", "2026-08-26"):
        day = date.fromisoformat(iso)
        week = sheet_import.week_of_month(iso)
        assert report.week_of_month(day) == week, iso
        assert cadence.batch_title(day) == f"{day.month}월 {week}주차", iso


# --- 발송 이력에 기업명 --------------------------------------------------------

def test_send_history_shows_companies_not_the_room_name(sent_batch, db):
    """`딜소개 발송 성공 · 홍길동 심사역님` 이라 기업 자리에 사람 이름이 찍혔다.
    이력을 훑는 목적은 '언제 어떤 기업을 보냈나' 다."""
    body = sent_batch["client"].get(
        f"/api/contacts/{sent_batch['contact'].id}").json()
    rows = [t for t in body["timeline"] if t["source"] == "system"]
    assert rows, "발송 이력이 없다"

    row = rows[0]
    assert [c["name"] for c in row["companies"]] == ["샘플애그", "샘플메디", "샘플로지"]
    assert row["company_count"] == 3
    assert "홍길동" not in row["content"]
    assert row["week"] == 3 and row["weekday"] == "수"
