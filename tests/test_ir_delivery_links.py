"""IR 자료 전달 — 자료가 실제로 따라가는가.

    홍길동 팀장님 안녕하세요.
    1번 기업 (주)샘플애그 IR deck 먼저 전달드리겠습니다.

문구만 나갔다. 앱은 링크를 **알고 있었고** 미리보기 옆에 띄우기까지 했는데,
정작 메시지 본문에는 들어가지 않았다. 받은 쪽은 다시 물어봐야 한다.
자료 전달에서 자료가 빠지는 것보다 나쁜 실패는 없다.
"""
from __future__ import annotations

import pathlib

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


# --- 나가는 순서 -------------------------------------------------------------
#
# 링크가 먼저 한 통씩, 설명이 마지막. 카톡에서 링크는 각자 미리보기 카드로
# 떠야 하고 그게 먼저 와야 한다 — 설명이 먼저 가면 "전달드리겠습니다" 만
# 떠 있고 자료가 안 보이는 시간이 생긴다.

def test_links_go_first_then_the_message(stage):
    preview = _preview(stage, [stage["agri"].id])
    parts = preview["parts"]

    assert len(parts) == 2, parts
    assert parts[0].startswith("1번 샘플애그") and LINK in parts[0]
    assert "안녕하세요" in parts[1]
    assert LINK not in parts[1], "링크가 두 번 나가면 안 된다"


def test_several_links_keep_their_order(stage):
    parts = _preview(stage, [stage["agri"].id, stage["medi"].id])["parts"]

    assert len(parts) == 3
    assert parts[0].startswith("1번 샘플애그")
    assert parts[1].startswith("2번 샘플메디")
    assert "안녕하세요" in parts[2]


def test_the_whole_text_is_the_parts_joined(stage):
    """`parts` 를 모르는 예전 발송 프로그램도 순서가 맞는 한 통을 보낸다."""
    preview = _preview(stage, [stage["agri"].id, stage["medi"].id])
    assert preview["message"].strip() == "\n\n".join(preview["parts"]).strip()


def test_deal_intro_is_still_one_message(stage):
    r = stage["client"].post("/api/deals/preview", json={
        "contact_ids": [stage["contact"].id], "company_ids": [stage["agri"].id]})
    assert r.json()["previews"][0]["parts"] == []


def test_the_send_stores_the_order(stage, db):
    """보낼 때 순서가 저장돼야 발송 프로그램이 그대로 보낸다."""
    import json

    from app.models import SendItem

    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id, stage["medi"].id]})
    assert r.status_code == 200, r.text

    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    parts = json.loads(item.parts_json)
    assert len(parts) == 3 and LINK in parts[0] and "안녕하세요" in parts[2]
    # 사람이 세는 것은 '몇 통' 이 아니라 '몇 명' 이다
    assert db.query(SendItem).filter_by(job_id=r.json()["job_id"]).count() == 1


def test_an_edited_message_goes_as_one(stage, db):
    """어디서 끊을지는 고친 사람만 안다."""
    from app.models import SendItem

    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id],
        "overrides": [{"contact_id": stage["contact"].id,
                       "message": "제가 직접 쓴 문구입니다"}]})
    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.parts_json is None
    assert item.message == "제가 직접 쓴 문구입니다"


def test_the_agent_is_given_the_order(stage, db):
    import json

    from app.models import AgentDevice, SendItem

    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    device = db.query(AgentDevice).filter_by(
        user_id=stage["contact"].user_id).first()

    payload = stage["client"].get(
        "/api/agent/poll",
        headers={"Authorization": f"Bearer {device.token}"}).json()
    item = payload["items"][0]
    assert item["parts"][0].startswith("1번 샘플애그")
    assert len(item["parts"]) == 2
    # 합친 전문도 함께 준다 — 이 칸을 모르는 예전 프로그램을 위해
    assert item["message"].strip() == "\n\n".join(item["parts"]).strip()
    assert json.loads(db.query(SendItem).filter_by(
        job_id=r.json()["job_id"]).one().parts_json) == item["parts"]


# --- 인사말 --------------------------------------------------------------------

def test_no_greeting_by_default(stage):
    """자료 전달은 **자료를 달라고 한 답장에 이어** 보내는 것이다.

    "안녕하세요" 로 다시 시작하면 처음 연락하는 것처럼 읽히고, 자료 전달 문구가
    이미 `{담당자명} {직함} 안녕하세요.` 로 시작하므로 **인사가 두 번** 나간다.
    """
    body = _preview(stage, [stage["agri"].id])["message"]
    assert body.count("안녕하세요") == 1, body


def test_the_screen_starts_with_the_box_unchecked(stage):
    """서버 기본값이 맞아도, 화면 체크박스가 켜져 있으면 그 값을 덮어쓴다 —
    실제로 그래서 인사가 두 번 나갔다."""
    js = pathlib.Path("app/static/js/deals.js").read_text(encoding="utf-8")
    assert 'greet.checked = !askMode && mode !== "ir"' in js


def test_it_can_still_be_turned_on(stage):
    """켜고 끄는 것은 사람이 정한다 — 기본값만 바꾼 것이다."""
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id], "include_opening": True})
    assert r.json()["previews"][0]["message"].count("안녕하세요") == 2


def test_deal_intro_still_greets(stage):
    """딜소개는 처음 여는 말이 필요하다."""
    r = stage["client"].post("/api/deals/preview", json={
        "contact_ids": [stage["contact"].id], "company_ids": [stage["agri"].id]})
    assert "안녕하세요" in r.json()["previews"][0]["message"]
