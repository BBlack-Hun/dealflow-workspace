"""IR 자료 전달 — 자료는 **사람이 PC 카톡에서 첨부한다**.

지금까지는 구글 드라이브 링크를 문구에 실어 보냈다. 기업 하나당 한 통씩
링크를 먼저 던지고 설명이 마지막이었다.

    1번 (주)샘플애그
    https://drive.google.com/file/d/…       ← 이 통들이 없어졌다

    홍길동 팀장님 안녕하세요.
    1번 기업 (주)샘플애그 IR deck 먼저 전달드리겠습니다.

그 방식을 폐기했다. 링크는 더 이상 문구에 실리지 않고, 앱은 **안내 문구만**
보낸다. 자료 파일은 사람이 PC 카카오톡에서 직접 첨부한다.

이 파일이 지키는 것은 셋이다.
- 링크가 **정말로 안 나간다**(옛 문구에 남은 `{자료링크}` 토큰까지 포함해서).
- 그래도 **어느 기업 자료인지는 문구에 남는다** — 번호와 이름.
- [자료 보내기] 를 누른 것이 **활동 이력에 남고**, 눌렀다는 이유만으로
  요청이 '전달함' 으로 닫히지는 않는다.
"""
from __future__ import annotations

import pathlib

import pytest

from app.services import message_composer as mc

from .conftest import DEMO_PASSWORD

LINK = "https://drive.google.com/file/d/agri/view"


@pytest.fixture()
def stage(client, db, users):
    from app.models import (DealBatch, DealBatchCompany, IrCompany, IrRequest,
                            MessageTemplate, SendItem, SendJob, SheetOwner,
                            VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="팀장",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 팀장님")
    agri = IrCompany(name="샘플애그", ir_drive_url=LINK)
    medi = IrCompany(name="샘플메디")            # 자료 없음
    batch = DealBatch(user_id=users["u1"].id, title="8월 3주차",
                      sent_date="2026-08-19")
    db.add_all([contact, agri, medi, batch,
                # 인사는 인사말이 맡는다 — 여기에 또 넣으면 두 번 나간다
                MessageTemplate(user_id=None, kind="ir_delivery", is_active=1,
                                body="{기업목록} IR deck 먼저 전달드리겠습니다.")])
    db.commit()

    db.add_all([DealBatchCompany(batch_id=batch.id, company_id=agri.id, position=1),
                DealBatchCompany(batch_id=batch.id, company_id=medi.id, position=2)])
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id,
                  status="done")
    db.add(job)
    db.commit()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, status="sent",
                    room_name="홍길동 팀장님", message="…"))
    # 투자사가 "1번, 2번 주세요" 라고 답한 상태 — [자료 보내기] 가 눌리는 자리.
    db.add_all([
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_id=agri.id, company_name="샘플애그",
                  requested_at="2026-08-20"),
        IrRequest(user_id=users["u1"].id, contact_id=contact.id,
                  company_id=medi.id, company_name="샘플메디",
                  requested_at="2026-08-20"),
    ])
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "contact": contact, "agri": agri, "medi": medi}


def _preview(stage, company_ids) -> dict:
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": company_ids})
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]


# --- 링크는 나가지 않는다 -----------------------------------------------------

def test_the_link_is_not_in_the_message(stage):
    """폐기한 것은 **보내는 방식**이다 — 링크가 문구에 실리지 않는다."""
    body = _preview(stage, [stage["agri"].id])["message"]
    assert LINK not in body, "구글 드라이브 링크 방식은 폐기했다"
    assert "drive.google.com" not in body


def test_the_company_is_still_pointed_at_by_number(stage):
    """자료는 안 실려도 **어느 기업 자료인지**는 남아야 한다.

    투자사는 지난 회차의 번호로 기억하고 답한다("2번 주세요").
    """
    body = _preview(stage, [stage["agri"].id])["message"]
    assert "1번 기업 샘플애그" in body


def test_it_goes_as_one_message(stage):
    """링크를 한 통씩 먼저 던지던 것이 없어졌으니 나눌 것도 없다."""
    preview = _preview(stage, [stage["agri"].id, stage["medi"].id])
    assert preview["parts"] == []
    assert "1번 기업 샘플애그" in preview["message"]
    assert "2번 기업 샘플메디" in preview["message"]


def test_an_old_template_token_does_not_leak(db, stage):
    """손으로 고쳐 둔 문구에 `{자료링크}` 가 남아 있어도 **글자 그대로 나가면 안 된다**.

    모르는 `{…}` 는 그대로 두는 것이 치환 규칙이라(오타를 눈에 띄게 하려고),
    치환 목록에서 빼 버리면 토큰이 투자사 카톡방에 그대로 나간다.
    """
    from app.models import MessageTemplate

    row = db.query(MessageTemplate).filter_by(kind="ir_delivery").one()
    row.body = "{기업목록} IR deck 전달드립니다.\n\n{자료링크}"
    db.commit()

    body = _preview(stage, [stage["agri"].id])["message"]
    assert "{자료링크}" not in body
    assert LINK not in body


def test_composer_no_longer_fills_the_token():
    contact = mc.ContactView(name="홍길동", title="팀장", firm="가나벤처스")
    out = mc.compose_message("{담당자명} {직함} 안녕하세요.", "{자료링크}", contact,
                             stage=mc.STAGE_REMIND)
    assert "{자료링크}" not in out.text


def test_the_send_stores_no_parts(stage, db):
    """한 통이면 순서를 저장할 것이 없다."""
    from app.models import SendItem

    r = stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id, stage["medi"].id]})
    assert r.status_code == 200, r.text

    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.parts_json is None
    assert LINK not in item.message


def test_the_agent_gets_one_message(stage, db):
    from app.models import AgentDevice

    stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    device = db.query(AgentDevice).filter_by(
        user_id=stage["contact"].user_id).first()

    payload = stage["client"].get(
        "/api/agent/poll",
        headers={"Authorization": f"Bearer {device.token}"}).json()
    item = payload["items"][0]
    assert item.get("parts") in (None, [])
    assert LINK not in item["message"]


# --- 자료가 없으면 첨부할 것이 없다 --------------------------------------------

def test_a_company_without_material_is_still_warned(stage):
    """링크는 안 나가지만, **첨부할 파일을 내려받을 곳**은 있어야 한다."""
    preview = _preview(stage, [stage["agri"].id, stage["medi"].id])
    assert any("샘플메디" in w and "첨부할 IR 자료가 없는 기업" in w
               for w in preview["warnings"])


def test_the_attachment_list_still_carries_the_link(stage):
    """화면에서 **열어 내려받는** 자리는 남는다 — `ir_drive_url` 칸을 지운 게 아니다."""
    preview = _preview(stage, [stage["agri"].id])
    assert preview["attachments"][0]["url"] == LINK


# --- [자료 보내기] — 활동 이력과 안내창 ----------------------------------------

def _press_deliver(stage, follow=False):
    return stage["client"].post(
        "/ir/deliver-guide",
        data={"contact_id": stage["contact"].id,
              "company_ids": f"{stage['agri'].id},{stage['medi'].id}"},
        follow_redirects=follow)


def test_pressing_it_leaves_a_line_in_the_history(stage, db):
    """자료를 앱이 안 보내므로, 여기 안 적으면 손으로 한 일이 아무 데도 안 남는다."""
    from app.models import ContactActivity

    _press_deliver(stage)

    rows = db.query(ContactActivity).filter_by(
        contact_id=stage["contact"].id, kind="ir_delivery").all()
    assert len(rows) == 1
    assert "PC 에서 직접 첨부" in rows[0].content
    assert rows[0].source == "system"
    assert sorted(rows[0].companies) == ["샘플메디", "샘플애그"]


def test_pressing_it_twice_does_not_pile_up(stage, db):
    """두 번 눌렀다고 같은 줄이 두 번 쌓이면 이력이 아니라 소음이다."""
    from app.models import ContactActivity

    _press_deliver(stage)
    _press_deliver(stage)

    assert db.query(ContactActivity).filter_by(
        contact_id=stage["contact"].id, kind="ir_delivery").count() == 1


def test_pressing_it_does_not_close_the_request(stage, db):
    """아직 아무것도 안 나갔다. 여기서 닫으면 첨부를 잊어도 '보낼 자료' 에서 사라진다."""
    from app.models import IrRequest

    _press_deliver(stage)

    rows = db.query(IrRequest).filter_by(contact_id=stage["contact"].id).all()
    assert [r.status for r in rows] == ["open", "open"]


def test_it_lands_on_the_send_screen_with_everything_picked(stage):
    r = _press_deliver(stage)
    assert r.status_code == 303
    where = r.headers["location"]
    assert where.startswith("/deals?")
    assert "mode=ir" in where
    assert f"contacts={stage['contact'].id}" in where
    assert f"companies={stage['agri'].id},{stage['medi'].id}" in where
    assert "attach=1" in where


def test_the_send_screen_says_to_attach_on_the_pc(stage):
    import re

    html = _press_deliver(stage, follow=True).text
    assert "PC 에서 IR 자료를 첨부해주시기 바랍니다" in html
    # 닫는 길은 **평범한 링크**다 — 스크립트 예외 하나로 발송 화면이 통째로
    # 가려지면 안 된다(`admin_only.html` 과 같은 조심). 닫으면 안내창만 빠지고
    # 골라 둔 담당자·기업은 그대로다.
    close = re.search(r'guard-go" href="([^"]+)"', html)
    assert close, "안내창을 닫을 링크가 없다"
    assert close.group(1).startswith("/deals?")
    assert "attach" not in close.group(1)
    assert "mode=ir" in close.group(1)
    assert f"contacts={stage['contact'].id}" in close.group(1)


def test_the_notice_is_not_shown_on_a_plain_visit(stage):
    """평소에 발송 화면을 열 때는 안내창이 뜨지 않는다."""
    html = stage["client"].get("/deals").text
    assert "PC 에서 IR 자료를 첨부해주시기 바랍니다" not in html


def test_another_persons_contact_is_refused(client, db, users, stage):
    """남의 담당자로 이력을 남길 수 없다."""
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    r = client.post("/ir/deliver-guide",
                    data={"contact_id": stage["contact"].id, "company_ids": ""})
    assert r.status_code == 404


# --- 인사말 --------------------------------------------------------------------

def test_the_greeting_appears_exactly_once(stage):
    """인사말은 모든 방식에서 기본으로 붙는다. 자료 전달 문구가 자체적으로
    인사로 시작하면 **두 번** 나가므로, 그 문구는 본문만 담는다."""
    body = _preview(stage, [stage["agri"].id])["message"]
    assert body.count("안녕하세요") == 1, body


def test_the_greeting_is_on_by_default_except_when_asking(stage):
    """빼는 것은 선호 분야를 되물을 때뿐이다 — 그건 이미 대화가 오간 방에
    한 줄만 덧붙이는 것이라 다시 인사하면 어색하다."""
    js = pathlib.Path("app/static/js/deals.js").read_text(encoding="utf-8")
    assert 'greet.checked = (mode !== "ask")' in js


def test_it_can_still_be_turned_off(stage):
    """켜고 끄는 것은 사람이 정한다 — 기본값만 정해 둔 것이다."""
    r = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id], "include_opening": False})
    assert "안녕하세요" not in r.json()["previews"][0]["message"]


def test_deal_intro_still_greets(stage):
    """딜소개는 처음 여는 말이 필요하다."""
    r = stage["client"].post("/api/deals/preview", json={
        "contact_ids": [stage["contact"].id], "company_ids": [stage["agri"].id]})
    assert "안녕하세요" in r.json()["previews"][0]["message"]


def test_deal_intro_never_carried_links(stage):
    """딜소개에는 애초에 링크를 붙이지 않았다 — 그대로다."""
    r = stage["client"].post("/api/deals/preview", json={
        "contact_ids": [stage["contact"].id],
        "company_ids": [stage["agri"].id]})
    assert LINK not in r.json()["previews"][0]["message"]
