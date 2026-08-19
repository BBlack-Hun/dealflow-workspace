"""발송 목록 생성 — 미리보기에서 고친 문구가 그대로 나가는지 확인한다.

자동 조합이 늘 맞을 수는 없어서 담당자별로 문장을 손보는 일이 잦다.
고친 문구가 무시되거나(원문 발송), 대상이 아닌 사람에게 붙거나, 빈 문구로
나가는 것은 모두 발송 사고다. 아래 세 가지가 그 경계다.
"""
import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def seed(client, db, users):
    """u1 로 로그인 + 소개 가능한 기업 1개 + 카톡방이 등록된 담당자 1명."""
    from app.models import IrCompany, VcContact

    company = IrCompany(
        name="샘플애그", sector_major="애그테크", series="Seed",
        one_liner="B2B 농산물 선도거래 플랫폼", summary="요약문", summary_status="done",
        revenue_recent=12,
    )
    contact = VcContact(
        user_id=users["u1"].id, name="홍길동", title="심사역", firm="가나벤처스",
        kakao_room_name="홍길동 심사역님 가나벤처스", room_verified="verified",
    )
    db.add_all([company, contact])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"company_id": company.id, "contact_id": contact.id}




def _sent_message(db, job_id: int) -> str:
    """실제로 에이전트가 보낼 문구 = send_items 에 저장된 스냅샷."""
    from app.models import SendItem
    from sqlalchemy import select
    db.expire_all()
    return db.execute(select(SendItem).where(SendItem.job_id == job_id)).scalars().first().message


def test_send_uses_edited_message(client, db, seed):
    """미리보기에서 고친 문구는 그대로 발송된다."""
    edited = "직접 고친 문구입니다.\n이 내용 그대로 나가야 합니다."
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
        "title": "수정본 회차",
        "overrides": [{"contact_id": seed["contact_id"], "message": edited}],
    })
    assert r.status_code == 200, r.text
    assert _sent_message(db, r.json()["job_id"]) == edited


def test_send_rejects_empty_override(client, seed):
    """빈 수정본은 사고다 — 조용히 원문으로 되돌리지 않고 막는다."""
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
        "overrides": [{"contact_id": seed["contact_id"], "message": "   "}],
    })
    assert r.status_code == 400


def test_send_ignores_override_for_untargeted_contact(client, db, seed):
    """대상에서 뺀 담당자의 수정본은 무시된다(엉뚱한 사람에게 나가면 안 된다)."""
    r = client.post("/api/deals/send", json={
        "company_ids": [seed["company_id"]],
        "contact_ids": [seed["contact_id"]],
        "overrides": [{"contact_id": 999999, "message": "대상 아님"}],
    })
    assert r.status_code == 200, r.text
    assert "대상 아님" not in _sent_message(db, r.json()["job_id"])
