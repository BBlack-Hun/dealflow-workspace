"""IR 기업 현황 `카톡 연결 여부` 자동 O (i130 · 11/02 사용자 결정 A+B · X 자동 안 함 · X→O).

대표 카톡방이 `확인됨` 이 되는 길은 둘이다(`room_match.verify_picked` · `verify_sent`).

1. 맞추기 화면에서 **카톡 후보 제목을 골라** 저장했다.
2. 월간 IR 이 **그 방 이름 그대로** 나갔다.

둘 다 `room_joined.set_verdict` 를 지나 `카톡 연결 여부` 가 빈칸 · `X` 면 `O` 가
되고, 이어진 스타트업 줄로는 `company_sync` 가 옮긴다. 사람이 직접 적은 방
이름 · 실패한 발송 · 시험방으로 바꿔 보낸 건은 아무것도 안 바꾼다.

이름 · 회사명은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

from tests.conftest import DEMO_PASSWORD, DEMO_TOKEN

COMPANY = "샘플카톡"
ROOM = "가나다 대표 샘플카톡 , 라마바 팀장"
OTHER = "가나다 대표 샘플카톡 단체방"
LIST = "샘플 스타트업 명단"


def _company(db, *, joined=None, rooms=(ROOM, OTHER), room=None):
    from app.models import IrCompany
    from app.services import room_match, startup_send

    startup_send.save(db, enabled=True, user_id=1)
    company = IrCompany(name=COMPANY, contract_status="paid", contact_name="가나다",
                        kakao_joined=joined, kakao_room_name=room)
    room_match.save_candidates(company, list(rooms), at="2026-11-01T10:00:00+09:00",
                               query=COMPANY)
    db.add(company)
    db.commit()
    return company


def _save(client, company_id, room):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client.post("/deals/startup-ir/rooms", follow_redirects=False,
                       data={"company_ids": [company_id], "rooms": [room]})


def _state(db, company):
    db.expire_all()
    return company.room_verified, company.kakao_joined


# ── 1. 카톡 후보를 골라 저장 ────────────────────────────────────────────────

def test_후보를_골라_저장하면_확인됨_O(db, users, client):
    company = _company(db)
    assert _save(client, company.id, ROOM).status_code == 303
    assert _state(db, company) == ("verified", "O")


def test_X_였던_곳도_O_가_된다(db, users, client):
    company = _company(db, joined="X")
    _save(client, company.id, ROOM)
    assert _state(db, company) == ("verified", "O")


def test_사람이_적은_방_이름만으론_안_바뀐다(db, users, client):
    company = _company(db, joined="X")
    _save(client, company.id, "가나다 대표 샘플카톡 직접 적음")
    assert _state(db, company) == ("unverified", "X")


def test_같은_제목이_여럿인_후보는_근거가_안_된다(db, users, client):
    company = _company(db, rooms=(ROOM, ROOM, OTHER))
    _save(client, company.id, ROOM)
    assert _state(db, company) == ("unverified", None)


def test_이어진_스타트업_줄도_O_로_따라간다(db, users, client):
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=LIST, user_id=1, layout=cc.STARTUP, is_hidden=1))
    company = _company(db)
    su = VcContact(user_id=1, source_sheet=LIST, name="가나다", firm=COMPANY,
                   ir_company_id=company.id, kakao_joined="X")
    db.add(su)
    db.commit()

    _save(client, company.id, ROOM)
    db.expire_all()
    assert (company.kakao_joined, su.kakao_joined) == ("O", "O")


# ── 2. 월간 IR 발송 결과 ────────────────────────────────────────────────────

def _sent_item(db, company, *, room=None):
    from app.models import STARTUP_SEND_KIND, SendItem, SendJob

    job = SendJob(user_id=1, kind=STARTUP_SEND_KIND, status="running", total=1)
    db.add(job)
    db.flush()
    item = SendItem(job_id=job.id, ir_company_id=company.id, status="sending",
                    room_name=room or company.kakao_room_name, message="월간")
    db.add(item)
    db.commit()
    return item


def _report(client, item_id, status):
    return client.post(f"/api/agent/items/{item_id}/result",
                       headers={"Authorization": f"Bearer {DEMO_TOKEN}"},
                       json={"status": status, "error": None if status == "sent" else "x"})


def test_월간_발송이_그_방으로_나가면_확인됨_O(db, users, client):
    company = _company(db, joined="X", rooms=(), room="가나다 대표 샘플카톡 직접 적음")
    item = _sent_item(db, company)
    assert _report(client, item.id, "sent").status_code == 200
    assert _state(db, company) == ("verified", "O")


def test_월간_발송이_실패하면_그대로다(db, users, client):
    company = _company(db, rooms=(), room=ROOM)
    item = _sent_item(db, company)
    assert _report(client, item.id, "failed").status_code == 200
    assert _state(db, company) == ("unverified", None)


def test_시험방으로_바꿔_보낸_건은_근거가_안_된다(db, users, client):
    company = _company(db, rooms=(), room=ROOM)
    item = _sent_item(db, company, room="시험방")
    assert _report(client, item.id, "sent").status_code == 200
    assert _state(db, company) == ("unverified", None)
