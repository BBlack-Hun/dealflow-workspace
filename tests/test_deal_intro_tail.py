"""딜 소개 **뒤에 따로 나가는 한 통**(문구 종류 `after_day1`, 선택).

1. 그 종류의 문구가 없으면(또는 비었으면) 지금까지와 같은 글 · 한 통이다.
2. 있으면 카톡은 두 통(`parts` = [본문, 뒤 문구])이고 `message` 는 둘을 빈 줄로 이은 글.
3. 미리보기 글 · 통 = 발송 목록에 실린 글 · 통 = 발송기가 받는 통.
4. 메일은 한 통이라 본문 맨 끝에 이어 붙는다.
5. 리마인드 · 미팅 · 자료 전달 · 딜 소싱 등 다른 방식은 그대로다.
6. 팀 기본 문구를 심지 않고, 발송 준비의 필수 문구도 아니다.

이름·회사명·문구는 전부 가상이다(공개 저장소).
"""
from __future__ import annotations

import json

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN, auth

AFTER = "{담당자명} {직함}, 보시고 궁금하신 점은 편하게 말씀 부탁드립니다."
RENDERED = "홍길동 심사역님, 보시고 궁금하신 점은 편하게 말씀 부탁드립니다."


@pytest.fixture()
def seed(client, db, users):
    from app.models import IrCompany, VcContact

    company = IrCompany(name="샘플애그", sector_major="애그테크", series="Seed",
                        one_liner="B2B 농산물 선도거래 플랫폼", summary="요약문",
                        summary_status="done", revenue_recent=12)
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                        firm="가나벤처스", kakao_room_name="홍길동 심사역님 가나벤처스",
                        room_verified="verified", email="hong@example.com")
    db.add_all([company, contact])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"company_ids": [company.id], "contact_ids": [contact.id]}


def _after(db, user_id, body=AFTER):
    from app.models import MessageTemplate
    from app.routers.deals import AFTER_DAY1_KIND

    db.add(MessageTemplate(user_id=user_id, kind=AFTER_DAY1_KIND, body=body, is_active=1))
    db.commit()


def _preview(client, seed, **extra):
    r = client.post("/api/deals/preview", json={**seed, **extra})
    assert r.status_code == 200, r.text
    return r.json()["previews"][0]


def _send(client, db, seed, **extra):
    from app.models import SendItem

    r = client.post("/api/deals/send", json={**seed, "title": "회차", **extra})
    assert r.status_code == 200, r.text
    db.expire_all()
    return db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()


def test_without_the_template_nothing_changes(client, db, seed, users):
    before = _preview(client, seed)
    assert before["parts"] == []
    assert _send(client, db, seed).parts_json is None

    # 빈 문구 · 남의 개인 문구는 없는 것과 같다
    _after(db, users["u1"].id, body="")
    _after(db, users["u2"].id)
    again = _preview(client, seed)
    assert (again["message"], again["parts"]) == (before["message"], [])
    item = _send(client, db, seed)
    assert (item.message, item.parts_json) == (before["message"], None)


def test_the_template_goes_as_a_second_bubble_and_preview_is_what_goes(
        client, db, seed, users):
    body = _preview(client, seed)["message"].strip()
    _after(db, users["u1"].id)

    shown = _preview(client, seed)
    assert shown["parts"] == [body, RENDERED]
    assert shown["message"] == f"{body}\n\n{RENDERED}\n"

    item = _send(client, db, seed)
    assert item.message == shown["message"]
    assert json.loads(item.parts_json) == shown["parts"]
    got = client.get("/api/agent/poll", headers=auth(DEMO_TOKEN)).json()["items"][0]
    assert got["parts"] == shown["parts"]


def test_mail_is_one_message_with_the_text_at_the_end(client, db, seed, users,
                                                      monkeypatch):
    from app.services import mail_sender

    for name, value in (("HOST", "smtp.example.com"), ("PORT", "465"),
                        ("USER", "deal@example.com"), ("FROM", "deal@example.com"),
                        ("PASSWORD", "secret")):
        monkeypatch.setenv(f"DEALFLOW_SMTP_{name}", value)
    monkeypatch.setattr(mail_sender, "send_job", lambda *a, **k: None)
    _after(db, users["u1"].id)

    shown = _preview(client, seed, channel="email")
    assert shown["parts"] == []
    assert shown["message"].endswith(f"\n\n{RENDERED}\n")
    item = _send(client, db, seed, channel="email")
    assert (item.channel, item.message, item.parts_json) == (
        "email", shown["message"], None)


def test_other_modes_are_untouched(client, db, seed, users):
    from app.routers import deals

    modes = [m for m in deals.MODE_TEMPLATE_KIND if m != deals.MODE_DEAL]
    before = {m: deals.sample_message(db, users["u1"], m) for m in modes}
    _after(db, users["u1"].id)
    assert {m: deals.sample_message(db, users["u1"], m) for m in modes} == before

    for mode in ("remind", "meeting", "ask", "ir"):
        shown = _preview(client, seed, mode=mode)
        assert shown["parts"] == [] and "궁금하신 점은 편하게" not in shown["message"]


def test_the_kind_is_made_and_deleted_on_the_template_screen(client, db, seed, users):
    """문구 화면에서 만들면 붙고 지우면 떨어진다. 심어 두지 않고 필수도 아니다."""
    from app.models import MessageTemplate
    from app.routers import deals, templates_crud
    from app.services import readiness
    from scripts import bootstrap

    assert deals.AFTER_DAY1_KIND not in dict(bootstrap.TEAM_TEMPLATES)
    assert templates_crud.KIND_LABELS[deals.AFTER_DAY1_KIND] in client.get("/templates").text

    client.post("/templates/new", data={"kind": deals.AFTER_DAY1_KIND, "body": AFTER})
    row = db.query(MessageTemplate).filter_by(kind=deals.AFTER_DAY1_KIND).one()
    assert row.user_id == users["u1"].id
    assert _preview(client, seed)["parts"][1:] == [RENDERED]
    # 이 문구만 있어서는 '발송 문구 준비됨' 이 되지 않는다(필수는 인사말 · 안내문)
    assert readiness._templates_check(db, users["u1"])["level"] == readiness.BLOCK

    client.post(f"/templates/{row.id}/delete")
    assert _preview(client, seed)["parts"] == []


def test_compose_message_keeps_one_bubble_without_after_body():
    from app.services import message_composer as mc

    who = mc.ContactView(name="홍길동", title="심사역", firm="가나벤처스")
    plain = mc.compose_message("안녕하세요, {담당자명} {직함}", "안내문", who)
    blank = mc.compose_message("안녕하세요, {담당자명} {직함}", "안내문", who,
                               after_body="  \n")
    assert (blank.text, blank.parts) == (plain.text, [])

    two = mc.compose_message("안녕하세요, {담당자명} {직함}", "안내문", who,
                             after_body="{투자사} 담당 {담당자명} {직함}께 한 통 더")
    assert two.parts == [plain.text.strip(), "가나벤처스 담당 홍길동 심사역님께 한 통 더"]
    assert two.text == "\n\n".join(two.parts) + "\n"
    assert two.char_count == len(two.text)
