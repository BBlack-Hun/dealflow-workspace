"""IR 자료 전달 — 자료가 실제로 따라가는가.

    홍길동 팀장님 안녕하세요.
    1번 기업 (주)샘플애그 IR deck 먼저 전달드리겠습니다.

문구만 나갔다. 앱은 링크를 **알고 있었고** 미리보기 옆에 띄우기까지 했는데,
정작 메시지 본문에는 들어가지 않았다. 받은 쪽은 다시 물어봐야 한다.
자료 전달에서 자료가 빠지는 것보다 나쁜 실패는 없다.
"""
from __future__ import annotations

import pytest

from app.services import message_composer as mc

from .conftest import DEMO_PASSWORD

LINK = "https://drive.google.com/file/d/agri/view"


@pytest.fixture()
def stage(client, db, users):
    from app.models import (DealBatch, DealBatchCompany, IrCompany,
                            MessageTemplate, SendItem, SendJob, SheetOwner,
                            VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="팀장",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 팀장님")
    agri = IrCompany(name="샘플애그", ir_drive_url=LINK)
    medi = IrCompany(name="샘플메디")            # 링크 없음
    batch = DealBatch(user_id=users["u1"].id, title="8월 3주차",
                      sent_date="2026-08-19")
    db.add_all([contact, agri, medi, batch,
                MessageTemplate(user_id=None, kind="ir_delivery", is_active=1,
                                body="{담당자명} {직함} 안녕하세요.\n"
                                     "{기업목록} IR deck 먼저 전달드리겠습니다.\n\n"
                                     "{자료링크}")])
    db.commit()

    db.add_all([DealBatchCompany(batch_id=batch.id, company_id=agri.id, position=1),
                DealBatchCompany(batch_id=batch.id, company_id=medi.id, position=2)])
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.commit()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, status="sent",
                    room_name="홍길동 팀장님", message="…"))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "contact": contact, "agri": agri, "medi": medi}


def _preview(stage, company_ids) -> dict:
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": company_ids})
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]


def test_the_link_is_in_the_message(stage):
    body = _preview(stage, [stage["agri"].id])["message"]
    assert LINK in body, "자료 전달인데 링크가 문구에 없다"
    assert "1번 샘플애그" in body, "지난 회차 번호로 짚어야 어느 기업인지 맞는다"


def test_a_company_without_a_link_is_said_out_loud(stage):
    """조용히 빼면 보낸 쪽도 받은 쪽도 몇 개를 주고받았는지 어긋난다."""
    preview = _preview(stage, [stage["agri"].id, stage["medi"].id])
    assert "샘플메디" in preview["message"]
    assert "자료 준비 중" in preview["message"]
    assert any("샘플메디" in w for w in preview["warnings"])


def test_links_go_out_even_if_the_template_forgot_them(db, stage):
    """템플릿에 {자료링크} 를 안 넣어 뒀어도 자료는 따라가야 한다.

    실제로 그렇게 나갔다 — 문구에는 '전달드리겠습니다' 만 있었다.
    """
    from app.models import MessageTemplate

    row = db.query(MessageTemplate).filter_by(kind="ir_delivery").one()
    row.body = "{담당자명} {직함} 안녕하세요.\n{기업목록} IR deck 전달드립니다."
    db.commit()

    assert LINK in _preview(stage, [stage["agri"].id])["message"]


def test_deal_intro_does_not_carry_links(stage):
    """딜소개에는 링크를 붙이지 않는다 — 자료는 요청이 온 뒤에 보낸다."""
    r = stage["client"].post("/api/deals/preview", json={
        "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    assert LINK not in r.json()["previews"][0]["message"]


def test_composer_appends_only_when_missing():
    """이미 링크가 들어 있으면 두 번 붙이지 않는다."""
    contact = mc.ContactView(name="홍길동", title="팀장", firm="가나벤처스")
    out = mc.compose_message(
        "{담당자명} {직함} 안녕하세요.", "{자료링크}", contact,
        stage=mc.STAGE_REMIND, file_links=f"1번 샘플애그\n{LINK}")
    assert out.text.count(LINK) == 1
