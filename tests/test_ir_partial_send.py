"""IR 자료 — **있는 것만 보내고, 없는 기업은 추후 발송 안내** (#53).

자료를 청한 기업 중 일부만 파일명(`ir_companies.ir_file_name`)이 있을 때:

1. 파일은 있는 기업 것만 붙는다(자동 첨부 계정)
2. 같은 글 끝에 "추후 보내 드리겠습니다" 한 줄이 붙는다(문구 `ir_delivery_later`)
3. 회차와 활동 이력에는 **보낸 기업만** 적힌다 — 그래서 보낸 뒤
   `pipeline.close_requests_for` 가 보낸 기업 요청만 닫고 못 보낸 것은 열린 채로 남는다

손으로 붙이는 계정도 같다. 하나도 없으면 지금처럼 400 으로 막는다.
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN

AGRI_FILE = "샘플애그_IR_2026.pdf"
LATER = "자료는 준비되는 대로 추후 보내 드리겠습니다."
NOTHING = "보낼 자료가 하나도 없습니다 — 요청은 그대로 남습니다"


@pytest.fixture()
def stage(client, db, users):
    """자료를 청한 투자사 한 명 — 파일이 있는 기업 하나, 없는 기업 하나."""
    from app.models import IrCompany, IrRequest, SheetOwner, VcContact

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="팀장",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 팀장님")
    agri = IrCompany(name="샘플애그", ir_file_name=AGRI_FILE)
    bare = IrCompany(name="샘플페이")            # 자료 파일명이 없다
    db.add_all([contact, agri, bare])
    db.flush()
    db.add_all([IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                          company_id=c.id, company_name=c.name,
                          requested_at="2026-10-15") for c in (agri, bare)])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "db": db, "user": users["u1"], "contact": contact,
            "agri": agri, "bare": bare}


def _turn_on(stage):
    from app.models import AgentDevice

    stage["db"].query(AgentDevice).filter_by(
        user_id=stage["user"].id).one().ir_root = "/Users/somebody/IR자료"
    stage["user"].can_auto_attach_ir = 1
    stage["db"].commit()


def _send(stage, ids):
    return stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id], "company_ids": ids})


def _deliver(stage):
    """발송기가 집어 가서 보냈다고 답한다 — 요청을 닫는 것은 이 자리다."""
    auth = {"Authorization": f"Bearer {DEMO_TOKEN}"}
    item = stage["client"].get("/api/agent/poll?files=1", headers=auth).json()["items"][0]
    stage["client"].post(f"/api/agent/items/{item['id']}/result",
                         json={"status": "sent"}, headers=auth)
    return item


@pytest.mark.parametrize("auto", [True, False], ids=["auto-attach", "by-hand"])
def test_only_companies_with_a_file_go_and_the_rest_wait(stage, auto):
    from app.models import ContactActivity, DealBatchCompany, IrRequest, SendItem

    if auto:
        _turn_on(stage)
    r = _send(stage, [stage["agri"].id, stage["bare"].id])
    assert r.status_code == 200, r.text
    db = stage["db"]

    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    # 1. 파일은 있는 기업 것만(손 첨부 계정은 잡에 파일이 안 실린다 — 그대로)
    assert (json.loads(item.files_json) if item.files_json else []) == (
        [AGRI_FILE] if auto else [])
    # 2. 글 끝에 못 보낸 기업의 추후 안내 한 줄
    lines = item.message.strip().splitlines()
    assert lines[-1] == f"샘플페이 {LATER}", item.message
    assert "샘플애그 IR deck" in item.message
    assert "샘플페이 IR deck" not in item.message
    # 3. 회차와 활동 이력에는 보낸 기업만
    batch_ids = {row.company_id for row in db.query(DealBatchCompany).filter_by(
        batch_id=r.json()["batch_id"])}
    assert batch_ids == {stage["agri"].id}
    act = db.query(ContactActivity).filter_by(kind="ir_delivery").one()
    assert json.loads(act.company_names) == ["샘플애그"]

    # 보낸 뒤 — 보낸 기업 요청만 닫히고 못 보낸 것은 '요청 받음' 으로 남는다
    _deliver(stage)
    db.expire_all()
    status = {row.company_name: row.status for row in db.query(IrRequest)}
    assert status == {"샘플애그": "delivered", "샘플페이": "open"}


@pytest.mark.parametrize("auto", [True, False], ids=["auto-attach", "by-hand"])
def test_nothing_to_send_is_still_stopped(stage, auto):
    from app.models import SendJob

    if auto:
        _turn_on(stage)
    r = _send(stage, [stage["bare"].id])
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == NOTHING
    assert stage["db"].query(SendJob).count() == 0


def test_the_later_template_is_used_when_there_is_one(stage):
    from app.models import MessageTemplate, SendItem
    from app.routers import templates_crud

    assert "ir_delivery_later" in templates_crud.KIND_LABELS
    stage["db"].add(MessageTemplate(user_id=None, kind="ir_delivery_later",
                                    is_active=1,
                                    body="{기업목록} 자료는 다음 주에 드리겠습니다."))
    stage["db"].commit()

    r = _send(stage, [stage["agri"].id, stage["bare"].id])
    item = stage["db"].query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.message.strip().endswith("샘플페이 자료는 다음 주에 드리겠습니다.")


def test_the_preview_says_what_waits(stage):
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id, stage["bare"].id]})
    preview = r.json()["previews"][0]
    assert preview["message"].strip().endswith(f"샘플페이 {LATER}")
    assert any("샘플페이" in w and "추후 발송" in w for w in preview["warnings"])
    later = {a["name"]: a["later"] for a in preview["attachments"]}
    assert later == {"샘플애그": False, "샘플페이": True}


def test_the_preview_says_nothing_goes_when_no_file_at_all(stage):
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["bare"].id]})
    preview = r.json()["previews"][0]
    assert NOTHING in preview["warnings"]
    # 나가지 않으니 '추후 발송' 이라고 하지 않는다
    assert [a["later"] for a in preview["attachments"]] == [False]
    assert LATER not in preview["message"]
