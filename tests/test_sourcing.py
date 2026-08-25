"""딜 소싱 — 우리 딜을 같이 볼 사람 명단.

투자사 관리 현황(딜소개를 **보내는** 명단)과는 성격이 다르다. 여기는
무엇을 찾는지(시리즈 A 이상 · 개인 참여 · M&A · 후속투자)로 갈래가 나뉘고,
같은 사람이 여러 갈래에 들어갈 수 있다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def seeded(client, db, users):
    from app.models import SourcingContact

    db.add_all([
        SourcingContact(bucket="시리즈 A 이상", position=0, name="홍길동",
                        title="심사역", firm="가나벤처스",
                        sectors="AI", round_size="10~30억"),
        SourcingContact(bucket="시리즈 A 이상", position=1, name="김철수",
                        title="팀장", firm="다라인베스트"),
        # 같은 사람이 다른 갈래에도 들어간다
        SourcingContact(bucket="M&A 찾는 투자사", position=1000, name="홍길동",
                        title="심사역", firm="가나벤처스"),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def test_the_menu_and_page_exist(seeded):
    body = seeded.get("/sourcing").text
    assert "딜 소싱" in body


def test_tabs_are_the_buckets_with_counts(seeded):
    body = seeded.get("/sourcing").text
    assert "시리즈 A 이상" in body
    assert "M&amp;A 찾는 투자사" in body or "M&A 찾는 투자사" in body
    # 어디에 사람이 있는지 알아야 한다
    assert ">2<" in body


def test_first_bucket_opens_by_default(seeded):
    """전체를 먼저 보여주면 갈래가 나뉜 뜻이 사라진다."""
    body = seeded.get("/sourcing").text
    assert "홍길동" in body and "김철수" in body


def test_the_same_person_can_be_in_two_buckets(seeded, db):
    from app.models import SourcingContact

    rows = db.query(SourcingContact).filter_by(name="홍길동").all()
    assert len(rows) == 2
    assert {r.bucket for r in rows} == {"시리즈 A 이상", "M&A 찾는 투자사"}


def test_rows_are_editable_in_place(seeded, db):
    from app.models import SourcingContact

    row = db.query(SourcingContact).filter_by(name="김철수").first()
    r = seeded.patch(f"/api/sourcing/{row.id}", json={"memo": "10월 통화 예정"})
    assert r.status_code == 200
    db.refresh(row)
    assert row.memo == "10월 통화 예정"


def test_the_name_cannot_be_emptied(seeded, db):
    """누구인지 모르는 줄이 남으면 안 된다."""
    from app.models import SourcingContact

    row = db.query(SourcingContact).filter_by(name="김철수").first()
    seeded.patch(f"/api/sourcing/{row.id}", json={"name": "  "})
    db.refresh(row)
    assert row.name == "김철수"


def test_sending_is_not_wired_yet(seeded):
    """보내는 길을 먼저 만들면 명단이 맞는지 확인하기 전에 나가 버린다."""
    body = seeded.get("/deals").text
    assert 'data-mode="sourcing" disabled' in body
    assert "준비 중" in body


def test_the_importer_replaces_a_bucket_wholesale(db, users):
    """맞춰 넣으면 시트에서 지운 사람이 앱에 남는다."""
    import pathlib

    src = pathlib.Path("scripts/import_sourcing.py").read_text(encoding="utf-8")
    assert "delete(SourcingContact).where(SourcingContact.bucket == bucket)" in src
