"""Series A 이상 딜 소싱 기업도 **IR 자료를 등록**하고 [자료 보내기]로 붙여 보낸다(0118).

사용자 요청(10/22): "Sereis A 이상 딜 소싱에 있는 기업도 IR 자료가 있어서 등록 가능하게
해줘". #365 로 딜 진행 관리에서 그 기업의 IR 요청은 적을 수 있었지만 IR 파일 칸이 없어
[자료 보내기]가 안 됐다.

못 박는 것.

1. **등록** — 그 탭의 `IR 자료` 칸. IR 기업 현황의 `IR 자료 파일명` 과 같은 규칙(파일
   이름 하나 — 경로 · 주소는 받지 않는다). IR 기업 현황에 같은 이름 기업이 있으면 **받지
   않고**(그 요청은 IR 줄로 이어져 IR 쪽 자료가 나간다) IR 쪽 파일 이름을 보여만 준다.
2. **보내기** — IR 기업과 같은 길(`/api/deals/send` · mode `ir`)로 `series_a_ids` 를 받아
   파일을 붙이고(자동 첨부 계정), 문구에는 번호 없이 이름으로, 활동 이력에 남기고, 보낸
   뒤 그 요청을 `IR 자료 전달 완료` 로 닫는다. 자료가 없으면 `/ir` 의 안내 그대로다.
3. **섞이지 않는다** — IR 기업 현황(`ir_companies`) · 딜 소개 회차의 기업 칸
   (`deal_batch_companies`)에 줄이 안 생기고, 번호(`deal_numbers`)를 빌려 쓰지 않는다.

기업 · 사람 이름은 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD, DEMO_TOKEN
from .test_migrations import _alembic

AGRI_FILE = "샘플애그_IR_2026.pdf"
SA_FILE = "샘플에이랩 IR deck.pdf"


@pytest.fixture()
def stage(client, db, users):
    """투자사 한 명이 IR 기업 하나 · Series A 기업 하나의 자료를 청했다."""
    from app.models import (IrCompany, IrRequest, MessageTemplate, SeriesACompany,
                            SheetOwner, VcContact)

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    contact = VcContact(user_id=users["u1"].id, name="홍길동", title="팀장",
                        firm="가나벤처스", source_sheet="내 명단",
                        channel_kakao=1, connect_stage="connected",
                        kakao_room_name="홍길동 팀장님")
    agri = IrCompany(name="샘플애그", ir_file_name=AGRI_FILE)
    # 같은 기업을 두 번 받은 딜 — 자료는 뒤 줄에만 적었다.
    sa_old = SeriesACompany(name="샘플에이랩", received_at="2026-10-01")
    sa = SeriesACompany(name="샘플에이랩", received_at="2026-10-15", ir_file_name=SA_FILE)
    bare = SeriesACompany(name="샘플비랩", received_at="2026-10-16")   # 자료 없음
    twin = SeriesACompany(name="(주)샘플 애그", received_at="2026-10-02")  # IR 에도 있음
    db.add_all([contact, agri, sa_old, sa, bare, twin,
                MessageTemplate(user_id=None, kind="ir_delivery", is_active=1,
                                body="{기업목록} IR deck 먼저 전달드리겠습니다.")])
    db.flush()
    db.add_all([
        IrRequest(user_id=users["u1"].id, contact_id=contact.id, company_id=agri.id,
                  company_name="샘플애그", requested_at="2026-10-20"),
        # Series A 기업은 #365 그대로 — 기업 번호 없이 이름으로 적힌다.
        IrRequest(user_id=users["u1"].id, contact_id=contact.id, company_id=None,
                  company_name="샘플에이랩", requested_at="2026-10-20"),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "db": db, "user": users["u1"], "contact": contact,
            "agri": agri, "sa": sa, "sa_old": sa_old, "bare": bare, "twin": twin}


def _turn_on(stage):
    """자동 첨부 — 관리자가 켜 주고(`can_auto_attach_ir`) 본인이 폴더를 정했다."""
    from app.models import AgentDevice

    stage["db"].query(AgentDevice).filter_by(
        user_id=stage["user"].id).one().ir_root = "/Users/somebody/IR자료"
    stage["user"].can_auto_attach_ir = 1
    stage["db"].commit()


def _send(stage, company_ids, series_a_ids):
    return stage["client"].post("/api/deals/send", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": company_ids, "series_a_ids": series_a_ids})


def _deliver(stage):
    """발송기가 집어 가서 보냈다고 답한다 — 요청을 닫는 것은 이 자리다."""
    auth = {"Authorization": f"Bearer {DEMO_TOKEN}"}
    item = stage["client"].get("/api/agent/poll?files=1", headers=auth).json()["items"][0]
    stage["client"].post(f"/api/agent/items/{item['id']}/result",
                         json={"status": "sent"}, headers=auth)


# ── 1. 등록 ──────────────────────────────────────────────────────────────────

def test_탭에서_IR_자료_파일_이름을_적는다(stage):
    c, bare = stage["client"], stage["bare"]

    res = c.patch(f"/api/series-a-companies/{bare.id}",
                  json={"ir_file_name": " 샘플비랩_IR.pdf "})
    assert res.status_code == 200, res.text
    assert res.json()["ir_file_name"] == "샘플비랩_IR.pdf"
    stage["db"].refresh(bare)
    assert bare.ir_file_name == "샘플비랩_IR.pdf"

    html = c.get("/companies?tab=series-a").text
    heads = re.findall(r"<th\b[^>]*>(.*?)</th>",
                       re.search(r'id="sa-table".*?</thead>', html, re.S).group(0), re.S)
    assert "IR 자료" in [re.sub(r"<[^>]+>", "", h).strip() for h in heads]
    row = re.search(rf'<tr data-id="{bare.id}".*?</tr>', html, re.S).group(0)
    assert 'data-field="ir_file_name"' in row and "샘플비랩_IR.pdf" in row


@pytest.mark.parametrize("bad", ["/Users/someone/IR/a.pdf", "C:\\IR\\a.pdf",
                                 "https://drive.google.com/x", ".hidden.pdf"])
def test_경로나_주소는_받지_않는다(stage, bad):
    """IR 기업 현황과 **같은 판정**(`_looks_like_a_file_name`) — 발송기가 거부할 값."""
    res = stage["client"].patch(f"/api/series-a-companies/{stage['bare'].id}",
                                json={"ir_file_name": bad})
    assert res.status_code == 400, res.text
    stage["db"].refresh(stage["bare"])
    assert stage["bare"].ir_file_name is None


def test_IR_기업현황에도_있는_기업은_IR_쪽_자료를_쓴다(stage):
    """중복 등록 막기 — 그 이름의 요청은 IR 줄로 이어져 IR 쪽 자료가 나간다."""
    from app.routers.series_a import IR_TWIN_FILE

    c, twin = stage["client"], stage["twin"]
    res = c.patch(f"/api/series-a-companies/{twin.id}", json={"ir_file_name": "다른.pdf"})
    assert res.status_code == 400 and res.json()["detail"] == IR_TWIN_FILE
    # 비우기는 된다(예전에 적힌 값이 있었을 수 있다).
    assert c.patch(f"/api/series-a-companies/{twin.id}",
                   json={"ir_file_name": ""}).status_code == 200

    row = re.search(rf'<tr data-id="{twin.id}".*?</tr>',
                    c.get("/companies?tab=series-a").text, re.S).group(0)
    assert 'data-field="ir_file_name"' not in row, "IR 기업 현황에도 있는 기업 칸이 고쳐진다"
    assert f"📎 {AGRI_FILE}" in row, "IR 쪽 자료 파일 이름을 안 보여 준다"


# ── 2. 보내기 ────────────────────────────────────────────────────────────────

def test_ir_화면에서_자료_보내기에_실린다(stage):
    html = stage["client"].get("/ir").text
    assert f'name="series_a_ids" value="{stage["sa"].id}"' in html, (
        "[자료 보내기]에 Series A 기업(자료를 적은 줄)이 안 실렸다")
    assert f"📎 {SA_FILE}" in html
    assert "IR 자료 파일명이 없어" not in html, "자료가 있는데 직접 보내라고 안내한다"


def test_자료가_없으면_지금_안내_그대로(stage):
    """자료 없는 Series A 기업은 [자료 보내기]에 안 실리고 직접 보내라는 안내가 선다."""
    from app.models import IrRequest

    db = stage["db"]
    db.add(IrRequest(user_id=stage["user"].id, contact_id=stage["contact"].id,
                     company_id=None, company_name="샘플비랩", requested_at="2026-10-21"))
    db.commit()
    html = stage["client"].get("/ir").text
    assert re.search(r"Series A 이상 딜 소싱 기업: 샘플비랩 — IR 자료 파일명이 없어", html)
    assert f'name="series_a_ids" value="{stage["sa"].id}"' in html, "자료 있는 쪽까지 빠졌다"
    assert f'value="{stage["bare"].id}"' not in html


@pytest.mark.parametrize("auto", [True, False], ids=["auto-attach", "by-hand"])
def test_IR_기업처럼_보내고_요청을_닫는다(stage, auto):
    from app.models import (ContactActivity, DealBatch, DealBatchCompany, IrCompany,
                            IrRequest, SendItem)

    if auto:
        _turn_on(stage)
    db = stage["db"]
    companies_before = db.query(IrCompany).count()
    r = _send(stage, [stage["agri"].id], [stage["sa"].id])
    assert r.status_code == 200, r.text

    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    # 파일 — 자동 첨부 계정만, IR 기업 뒤에 Series A 기업.
    assert (json.loads(item.files_json) if item.files_json else []) == (
        [AGRI_FILE, SA_FILE] if auto else [])
    # 문구 — Series A 기업은 딜 소개 번호가 없으니 이름으로만.
    assert "샘플애그, 샘플에이랩 IR deck" in item.message, item.message
    # 회차 — IR 기업 칸에는 IR 기업만, Series A 는 이름으로.
    batch = db.get(DealBatch, r.json()["batch_id"])
    assert {row.company_id for row in db.query(DealBatchCompany).filter_by(
        batch_id=batch.id)} == {stage["agri"].id}
    assert json.loads(batch.series_a_names) == ["샘플에이랩"]
    assert db.query(IrCompany).count() == companies_before, "IR 기업 현황에 줄이 생겼다"
    # 활동 이력 — 누구에게 어느 기업 자료를 보냈나.
    act = db.query(ContactActivity).filter_by(kind="ir_delivery").one()
    assert json.loads(act.company_names) == ["샘플애그", "샘플에이랩"]

    _deliver(stage)
    db.expire_all()
    assert {row.company_name: row.status for row in db.query(IrRequest)} == {
        "샘플애그": "delivered", "샘플에이랩": "delivered"}


def test_Series_A_기업만_보내도_된다(stage):
    from app.models import IrRequest

    _turn_on(stage)
    r = _send(stage, [], [stage["sa"].id])
    assert r.status_code == 200, r.text
    _deliver(stage)
    stage["db"].expire_all()
    assert {row.company_name: row.status for row in stage["db"].query(IrRequest)} == {
        "샘플애그": "open", "샘플에이랩": "delivered"}, "안 보낸 IR 기업 요청까지 닫혔다"
    # 담당자 이력의 그 발송 줄에도 보낸 기업이 선다(`contacts._batch_company_names`).
    timeline = stage["client"].get(f"/api/contacts/{stage['contact'].id}").json()["timeline"]
    # 발송 건의 줄은 본문이 `IR 전달` 이다(활동 이력 줄 `IR 자료 전달 — …` 과 다른 줄).
    sent = [t for t in timeline if t["kind"] == "ir_delivery" and t["content"] == "IR 전달"]
    assert [[c["name"] for c in t["companies"]] for t in sent] == [["샘플에이랩"]], timeline


def test_자료_없는_Series_A_기업은_추후_안내로_빠지고_요청이_남는다(stage):
    """딜 제안 관리에서 손으로 골랐을 때 — IR 기업의 #53 규칙 그대로."""
    from app.models import DealBatch, IrRequest, SendItem

    db = stage["db"]
    db.add(IrRequest(user_id=stage["user"].id, contact_id=stage["contact"].id,
                     company_id=None, company_name="샘플비랩", requested_at="2026-10-21"))
    db.commit()
    r = _send(stage, [stage["agri"].id], [stage["bare"].id])
    assert r.status_code == 200, r.text
    item = db.query(SendItem).filter_by(job_id=r.json()["job_id"]).one()
    assert item.message.strip().splitlines()[-1].startswith("샘플비랩 자료는"), item.message
    assert db.get(DealBatch, r.json()["batch_id"]).series_a_names is None
    _deliver(stage)
    db.expire_all()
    assert db.query(IrRequest).filter_by(company_name="샘플비랩").one().status == "open"


def test_Series_A_만이고_자료가_없으면_막는다(stage):
    r = _send(stage, [], [stage["bare"].id])
    assert r.status_code == 400
    assert r.json()["detail"] == "보낼 자료가 하나도 없습니다 — 요청은 그대로 남습니다"


def test_IR_기업현황에도_있는_기업은_Series_A_로_못_싣는다(stage):
    r = _send(stage, [], [stage["twin"].id])
    assert r.status_code == 400
    assert "IR 기업 현황에도 있는 기업" in r.json()["detail"]


def test_같은_번호의_IR_기업_딜소개_번호를_빌리지_않는다(stage, users):
    """`deal_batch_companies` 의 번호는 IR 기업 번호로 남는다 — Series A 줄 번호가 우연히
    같아도 그 번호(`[기업N]`)를 붙이면 투자사가 남의 기업 자료로 읽는다."""
    from app.models import (DealBatch, DealBatchCompany, IrCompany, SendItem, SendJob)
    from app.services import message_composer as mc

    db = stage["db"]
    # Series A 줄 번호와 같은 번호의 IR 기업이 지난 딜 소개에서 [기업2] 였다.
    same = db.get(IrCompany, stage["sa"].id) or IrCompany(id=stage["sa"].id, name="샘플다른")
    db.add(same)
    batch = DealBatch(user_id=users["u1"].id, title="지난 회차", sent_date="2026-10-01")
    db.add(batch)
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=same.id, position=2))
    job = SendJob(user_id=users["u1"].id, kind="deal_intro", batch_id=batch.id, status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=stage["contact"].id, status="sent",
                    stage=mc.STAGE_DAY1, room_name="홍길동 팀장님", message="…"))
    db.commit()

    res = stage["client"].post("/api/deals/preview", json={
        "mode": "ir", "contact_ids": [stage["contact"].id],
        "company_ids": [], "series_a_ids": [stage["sa"].id]})
    assert res.status_code == 200, res.text
    p = res.json()["previews"][0]
    assert [(a["name"], a["no"], a["file"]) for a in p["attachments"]] == [
        ("샘플에이랩", None, SA_FILE)]
    assert "[기업2]" not in p["message"], p["message"]


def test_스크립트_없는_길도_Series_A_기업을_넘긴다(stage):
    """`/ir/deliver-guide` — 이 담당자가 이름으로 열어 둔 요청의 그 줄만 넘긴다."""
    res = stage["client"].post("/ir/deliver-guide", follow_redirects=False, data={
        "contact_id": stage["contact"].id, "company_ids": str(stage["agri"].id),
        # 요청받지 않은 기업 번호가 섞여 들어와도 발송 화면에는 요청받은 것만.
        "series_a_ids": f"{stage['sa'].id},{stage['bare'].id}"})
    assert res.status_code == 303
    loc = res.headers["location"]
    assert f"companies={stage['agri'].id}" in loc
    assert loc.endswith(f"&series_a={stage['sa'].id}"), loc


# ── 3. 섞이지 않는다 ─────────────────────────────────────────────────────────

def test_딜_소개_목록에는_Series_A_기업이_IR_기업으로_안_선다(stage):
    html = stage["client"].get("/deals").text
    company_list = re.search(r'id="company-list".*?id="company-filter-note"', html, re.S).group(0)
    assert "샘플에이랩" not in company_list


# ── 판(0118) ────────────────────────────────────────────────────────────────

def _columns(db: Path, table: str) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
    finally:
        con.close()


def test_판은_0117_뒤에_칸_둘을_더하고_되돌리면_그_칸만_뺀다(tmp_path):
    db = tmp_path / "m.db"
    done = _alembic(db, "upgrade", "0117_ir_link_auto")
    assert done.returncode == 0, done.stdout + done.stderr
    con = sqlite3.connect(db)
    try:
        # 운영 DB 는 이 칸이 없는 표에서 출발한다(0001 의 create_all 은 이미 칸이 있다).
        for table, column in (("series_a_companies", "ir_file_name"),
                              ("deal_batches", "series_a_names")):
            con.execute(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')
        con.commit()
    finally:
        con.close()

    done = _alembic(db, "upgrade", "0118_series_a_ir_file")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "ir_file_name" in _columns(db, "series_a_companies")
    assert "series_a_names" in _columns(db, "deal_batches")

    done = _alembic(db, "downgrade", "0117_ir_link_auto")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "ir_file_name" not in _columns(db, "series_a_companies")
    assert {"series_a_names"}.isdisjoint(_columns(db, "deal_batches"))
    assert "import_key" in _columns(db, "series_a_companies")
