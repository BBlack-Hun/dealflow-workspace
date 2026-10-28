"""리마인드 — **선호 투자분야가 빈 분께만** 글 끝에 되묻는 말을 붙인다(10/28).

1. 선호분야가 비었거나 공백뿐이면 글 끝에 빈 줄 하나 두고 세 줄이 붙는다.
2. 선호분야가 있으면 그대로다.
3. 미리보기 글 = 발송 목록에 실린 글(사람마다).
4. 다른 방식(미팅 요청 · 선호 분야 묻기)과 기본 문구(가상의 받는 사람)는 그대로다.
5. 관리자가 문구 화면에서 고친 팀 문구가 나간다 · 시드 = 코드 폴백.

이름·회사명은 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

TAIL = "\n\n선호하는 기업분야 말씀주시면\n맞추어\n딜 공유 드리겠습니다.\n"


@pytest.fixture()
def people(client, db, users):
    from app.models import VcContact

    rows = {}
    for key, sectors in (("has", "AI, 헬스케어"), ("empty", None), ("blank", "  \n ")):
        row = VcContact(user_id=users["u1"].id, name=f"{key}담당", title="심사역",
                        firm="가나벤처스", kakao_room_name=f"{key}담당 심사역님",
                        room_verified="verified", channel_kakao=1,
                        connect_stage="connected", sectors=sectors)
        db.add(row)
        rows[key] = row
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return rows


def _preview(client, ids, mode="remind"):
    r = client.post("/api/deals/preview", json={"mode": mode, "contact_ids": ids})
    assert r.status_code == 200, r.text
    return [p["message"] for p in r.json()["previews"]]


def test_tail_only_for_empty_sectors_and_preview_is_what_goes(client, db, people):
    from app.models import SendItem

    ids = [people[k].id for k in ("has", "empty", "blank")]
    has, empty, blank = _preview(client, ids)
    assert not has.endswith(TAIL) and "선호하는 기업분야" not in has
    assert empty.endswith(TAIL) and blank.endswith(TAIL)
    # 붙는 말 앞은 선호분야 있는 분 글과 같다(이름 줄만 다르다)
    assert empty[: -len(TAIL)].replace("empty", "has") == has.rstrip("\n")

    r = client.post("/api/deals/send", json={"mode": "remind", "contact_ids": ids,
                                             "title": "리마인드"})
    assert r.status_code == 200, r.text
    sent = {i.contact_id: i.message for i in db.query(SendItem).filter_by(
        job_id=r.json()["job_id"])}
    assert [sent[i] for i in ids] == [has, empty, blank]


@pytest.mark.parametrize("mode", ["meeting", "ask"])
def test_other_modes_are_untouched(client, people, mode):
    [text] = _preview(client, [people["empty"].id], mode=mode)
    assert "말씀주시면\n맞추어" not in text


def test_sample_message_has_no_tail(db, users):
    from app.routers import deals

    text = deals.sample_message(db, users["u1"], deals.MODE_REMIND)
    assert "말씀주시면\n맞추어" not in text


def test_admin_text_is_used_and_seed_matches_fallback(client, db, people):
    from app.models import MessageTemplate
    from app.routers import deals, templates_crud
    from scripts import bootstrap

    assert dict(bootstrap.TEAM_TEMPLATES)[deals.REMIND_NO_SECTOR_KIND] == \
        deals.REMIND_NO_SECTOR_FALLBACK
    assert deals.REMIND_NO_SECTOR_KIND in templates_crud.KIND_LABELS
    db.add(MessageTemplate(user_id=None, kind=deals.REMIND_NO_SECTOR_KIND,
                           is_active=1, body="관심 분야 알려 주시면 맞춰 드리겠습니다."))
    db.commit()
    [text] = _preview(client, [people["empty"].id])
    assert text.endswith("\n\n관심 분야 알려 주시면 맞춰 드리겠습니다.\n")
