"""기업 소개 이력 · IR 링크 일괄 입력.

매 회차 같은 기업을 또 보내면 받는 쪽에서는 이쪽이 지난번을 기억 못 한다고 읽는다.
그래서 고를 때 최근에 보낸 것이 눈에 띄어야 한다.

이력은 두 곳에 있다 — 이 시스템으로 보낸 회차와, 시트에서 옮겨 온 지난 기록
(문구 안에 기업명이 적혀 있다). 둘을 합쳐 **가장 최근 날짜**를 쓴다.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _company(db, name, **kw):
    from app.models import IrCompany

    row = IrCompany(name=name, one_liner="소개", revenue_recent=10, **kw)
    db.add(row)
    db.commit()
    return row


# --- 이력 ------------------------------------------------------------------

def test_history_comes_from_imported_activities(db, users):
    """시트에서 옮겨 온 지난 발송 기록에서 기업명을 읽는다."""
    from app.models import ContactActivity, VcContact
    from app.services import deal_history

    company = _company(db, "샘플애그")
    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add(ContactActivity(
        contact_id=contact.id, kind="deal_intro", content="8개사 공유",
        happened_at="2026-08-10",
        company_names=json.dumps(["샘플애그", "샘플메디"], ensure_ascii=False)))
    db.commit()

    sent = deal_history.last_sent_map(db)
    info = deal_history.annotate([company], sent, today=date(2026, 8, 20))
    assert info[company.id]["last_sent"] == "2026-08-10"
    assert info[company.id]["days_ago"] == 10
    assert info[company.id]["recent"] is True


def test_history_comes_from_our_own_batches(db, users):
    from app.models import DealBatch, DealBatchCompany
    from app.services import deal_history

    company = _company(db, "샘플애그")
    batch = DealBatch(user_id=users["u1"].id, title="회차", sent_date="2026-08-12")
    db.add(batch)
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    db.commit()

    sent = deal_history.last_sent_map(db)
    info = deal_history.annotate([company], sent, today=date(2026, 8, 20))
    assert info[company.id]["last_sent"] == "2026-08-12"


def test_the_latest_date_wins(db, users):
    """두 곳에 기록이 있으면 더 최근 것을 쓴다."""
    from app.models import ContactActivity, DealBatch, DealBatchCompany, VcContact
    from app.services import deal_history

    company = _company(db, "샘플애그")
    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    batch = DealBatch(user_id=users["u1"].id, title="회차", sent_date="2026-07-01")
    db.add_all([contact, batch])
    db.flush()
    db.add_all([
        DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1),
        ContactActivity(contact_id=contact.id, kind="deal_intro", content="공유",
                        happened_at="2026-08-15",
                        company_names=json.dumps(["샘플애그"], ensure_ascii=False)),
    ])
    db.commit()

    assert deal_history.last_sent_map(db)[
        deal_history._key("샘플애그")] == "2026-08-15"


def test_company_name_variants_match(db, users):
    """'(주)' 와 띄어쓰기 차이로 다른 기업이 되면 안 된다."""
    from app.models import ContactActivity, VcContact
    from app.services import deal_history

    company = _company(db, "(주)샘플애그")
    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.flush()
    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro", content="공유",
                           happened_at="2026-08-10",
                           company_names=json.dumps(["샘플애그"], ensure_ascii=False)))
    db.commit()

    info = deal_history.annotate([company], deal_history.last_sent_map(db),
                                 today=date(2026, 8, 20))
    assert info[company.id]["last_sent"] == "2026-08-10"


def test_old_send_is_not_recent(db, users):
    from app.models import ContactActivity, VcContact
    from app.services import deal_history

    company = _company(db, "샘플애그")
    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.flush()
    long_ago = (date(2026, 8, 20) - timedelta(days=90)).isoformat()
    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro", content="공유",
                           happened_at=long_ago,
                           company_names=json.dumps(["샘플애그"], ensure_ascii=False)))
    db.commit()

    info = deal_history.annotate([company], deal_history.last_sent_map(db),
                                 today=date(2026, 8, 20))
    assert info[company.id]["recent"] is False


def test_deals_page_marks_recent_companies(logged, db, users):
    from app.models import ContactActivity, VcContact
    from app.services import deal_history

    _company(db, "샘플애그")
    contact = VcContact(user_id=users["u1"].id, name="홍길동", firm="가나벤처스")
    db.add(contact)
    db.flush()
    recent = (date.today() - timedelta(days=3)).isoformat()
    db.add(ContactActivity(contact_id=contact.id, kind="deal_intro", content="공유",
                           happened_at=recent,
                           company_names=json.dumps(["샘플애그"], ensure_ascii=False)))
    db.commit()

    body = logged.get("/deals").text
    assert 'data-recent="1"' in body
    assert "일 전 소개" in body


# --- IR 링크 일괄 입력 ------------------------------------------------------

def test_bulk_links_apply(logged, db):
    from app.models import IrCompany

    a = _company(db, "샘플애그")
    b = _company(db, "샘플메디")
    logged.post("/companies/ir-links", follow_redirects=False, data={
        "pasted": "샘플애그\thttps://drive.google.com/file/d/aaa/view\n"
                  "샘플메디,https://drive.google.com/file/d/bbb/view",
    })
    db.expire_all()
    assert db.get(IrCompany, a.id).ir_drive_url.endswith("aaa/view")
    assert db.get(IrCompany, b.id).ir_drive_url.endswith("bbb/view")


def test_bulk_links_report_unmatched(logged, db):
    """넣은 줄 알았는데 안 들어간 것이 제일 나쁘다 — 몇 건인지 알려 준다."""
    _company(db, "샘플애그")
    r = logged.post("/companies/ir-links", follow_redirects=False, data={
        "pasted": "샘플애그\thttps://drive.google.com/a\n"
                  "없는기업\thttps://drive.google.com/b",
    })
    from urllib.parse import unquote

    assert "못 찾은 기업 1건" in unquote(r.headers["location"])
    assert "없는기업" in unquote(r.headers["location"])


def test_bulk_links_ignore_lines_without_a_url(logged, db):
    from app.models import IrCompany

    a = _company(db, "샘플애그")
    logged.post("/companies/ir-links", follow_redirects=False, data={
        "pasted": "샘플애그\t미정\n샘플애그\thttps://drive.google.com/ok",
    })
    db.expire_all()
    assert db.get(IrCompany, a.id).ir_drive_url.endswith("/ok")


def test_bulk_links_match_name_variants(logged, db):
    from app.models import IrCompany

    a = _company(db, "(주)샘플애그")
    logged.post("/companies/ir-links", follow_redirects=False, data={
        "pasted": "샘플 애그\thttps://drive.google.com/x",
    })
    db.expire_all()
    assert db.get(IrCompany, a.id).ir_drive_url.endswith("/x")
