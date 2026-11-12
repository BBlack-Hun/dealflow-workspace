"""투자컨설턴트의 **이어진 줄**에서 IR 칸을 고치면 IR 기업 현황이 바뀐다(11/12 사용자).

#83 은 그 칸들을 읽기만 두었다 — 값은 IR 기업 한 곳에 있어야 두 벌로 안 갈린다. 그 한 곳은
그대로이고, 투자컨설턴트 표에서도 그 한 곳을 고친다(`routers/consulting.update_ir`). 못 박는 것.

1. 이은 줄에서 고치면 **IR 기업의 칸**이 바뀌고, 수정 로그에 고친 사람(그 계정)이 남는다.
2. 저장은 IR 기업 현황과 **같은 함수**다 — 금액 `억` 붙이기 · 투자라운드 단계 맞추기가 같다.
3. 고칠 수 있는 사람은 **그 줄을 고칠 수 있는 사람**뿐이다(자기 줄 · 맡긴 담당자 줄 · 관리자).
4. 표에 선 IR 칸만 받는다 — 이 길로 기업명 · 담당자 · IR 자료를 고칠 수 없다.
5. 안 이은 줄은 고칠 IR 기업이 없다 — 안내만 뜨고 IR 기업을 만들지 않는다.

이름 · 기업명 · 금액은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

PHONES = {"consultant_a": "01000000081", "consultant_b": "01000000082",
          "admin": "01000000083"}


@pytest.fixture()
def stage(db, users):
    """컨설턴트 둘 · 팀원 둘(u1 · u2) · 관리자 — IR 기업 하나에 이은 줄과 안 이은 줄."""
    from app.models import ConsultingCompany, IrCompany, User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    users["u1"].can_view_consulting = 1
    users["u2"].can_view_consulting = 1
    people = {"member": users["u1"], "other": users["u2"]}
    for key, role in (("consultant_a", "consultant"), ("consultant_b", "consultant"),
                      ("admin", "admin")):
        people[key] = User(name=f"{key}샘플", phone=PHONES[key], role=role,
                           can_view_consulting=1, password_hash=pw)
        db.add(people[key])
    ir = IrCompany(name="샘플팜", business_desc="스마트팜 설비", series="Seed",
                   revenue_2024="10억", ir_file_name="샘플팜_IR.pdf")
    db.add(ir)
    db.commit()
    linked = ConsultingCompany(user_id=people["consultant_a"].id, company_name="샘플팜",
                               sheet="스타트업", position=1, ir_company_id=ir.id)
    loose = ConsultingCompany(user_id=people["consultant_a"].id, company_name="없는샘플",
                              sheet="스타트업", position=2)
    db.add_all([linked, loose])
    db.commit()
    return {"people": people, "ir": ir, "linked": linked, "loose": loose}


@pytest.fixture()
def sign_in(db, users):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    phones = {"member": "01000000001", "other": "01000000002", **PHONES}

    def _open(who: str):
        c = TestClient(app)
        r = c.post("/login", data={"phone": phones[who], "password": DEMO_PASSWORD},
                   follow_redirects=False)
        assert r.status_code == 303
        return c
    return _open


def _ir(db, ir_id: int):
    from app.models import IrCompany

    db.expire_all()
    return db.get(IrCompany, ir_id)


# ── 1. 이은 줄에서 고치면 IR 기업이 바뀐다 · 로그에 고친 사람 ─────────────────────

def test_이은_줄에서_고치면_IR_기업_현황이_바뀌고_로그에_고친_사람이_남는다(stage, sign_in, db):
    from app.models import EditLog

    who = stage["people"]["consultant_a"]
    r = sign_in("consultant_a").patch(f"/api/consulting/{stage['linked'].id}/ir",
                                      json={"business_desc": "수직 농장 설비"})
    assert r.status_code == 200, r.text
    assert r.json()["ir"]["business_desc"] == "수직 농장 설비", "화면에 다시 적을 IR 글자가 없습니다"
    assert _ir(db, stage["ir"].id).business_desc == "수직 농장 설비"

    logs = db.query(EditLog).filter_by(table_name="ir_companies",
                                       row_id=stage["ir"].id).all()
    assert [g.actor_user_id for g in logs] == [who.id], \
        "IR 칸을 고쳤는데 수정 로그에 고친 컨설턴트가 안 남았습니다"
    assert '"business_desc"' in logs[0].changes_json, logs[0].changes_json


# ── 2. IR 기업 현황과 같은 함수 ─────────────────────────────────────────────

def test_금액과_투자라운드는_IR_기업_현황과_같은_모양으로_담긴다(stage, sign_in, db):
    """같은 글자를 두 화면에서 넣으면 같은 값이 남아야 한다 — 따로 검증하면 갈린다."""
    from app.models import IrCompany

    other = IrCompany(name="견줄샘플")
    db.add(other)
    db.commit()
    sent = {"revenue_2024": "30", "funding_total": "5-10억 사이", "series": "시리즈A"}
    r = sign_in("consultant_a").patch(f"/api/consulting/{stage['linked'].id}/ir", json=sent)
    assert r.status_code == 200, r.text
    r = sign_in("member").patch(f"/api/companies/{other.id}", json=sent)
    assert r.status_code == 200, r.text

    mine, theirs = _ir(db, stage["ir"].id), db.get(IrCompany, other.id)
    for field in sent:
        assert getattr(mine, field) == getattr(theirs, field), field
    assert mine.revenue_2024 == "30억" and mine.series == "Series A"


# ── 3. 그 줄을 고칠 수 있는 사람만 ───────────────────────────────────────────

@pytest.mark.parametrize("who", ["consultant_b", "member", "other"])
def test_그_줄을_못_고치는_사람은_IR_칸도_못_고친다(stage, sign_in, db, who):
    r = sign_in(who).patch(f"/api/consulting/{stage['linked'].id}/ir",
                           json={"business_desc": "남이 고친 소개"})
    assert r.status_code == 404, r.text
    assert _ir(db, stage["ir"].id).business_desc == "스마트팜 설비"


@pytest.mark.parametrize("who", ["member", "admin"])
def test_맡은_팀원과_관리자는_IR_칸을_고친다(stage, sign_in, db, who):
    from app.models import ConsultingRowGrant

    db.add(ConsultingRowGrant(user_id=stage["people"]["consultant_a"].id,
                              editor_user_id=stage["people"]["member"].id))
    db.commit()
    r = sign_in(who).patch(f"/api/consulting/{stage['linked'].id}/ir",
                           json={"business_desc": f"{who} 가 고친 소개"})
    assert r.status_code == 200, r.text
    assert _ir(db, stage["ir"].id).business_desc == f"{who} 가 고친 소개"


# ── 4. 표에 선 IR 칸만 ───────────────────────────────────────────────────

@pytest.mark.parametrize("field,value", [("name", "바뀐기업명"), ("assignee_name", "아무개"),
                                         ("ir_file_name", "다른_IR.pdf"),
                                         ("contract_status", "paid")])
def test_표에_선_IR_칸_말고는_이_길로_못_고친다(stage, sign_in, db, field, value):
    before = getattr(_ir(db, stage["ir"].id), field)
    r = sign_in("consultant_a").patch(f"/api/consulting/{stage['linked'].id}/ir",
                                      json={field: value})
    assert r.status_code == 400, r.text
    assert getattr(_ir(db, stage["ir"].id), field) == before


# ── 5. 안 이은 줄 ────────────────────────────────────────────────────────

def test_안_이은_줄은_IR_기업을_만들지_않고_막는다(stage, sign_in, db):
    from app.models import IrCompany

    n = db.query(IrCompany).count()
    r = sign_in("consultant_a").patch(f"/api/consulting/{stage['loose'].id}/ir",
                                      json={"business_desc": "새 소개"})
    assert r.status_code == 400, r.text
    db.expire_all()
    assert db.query(IrCompany).count() == n


# ── 화면 — 여는 칸과 안 여는 칸 ─────────────────────────────────────────────

def _ir_cells(html: str, row_id: int) -> dict:
    tr = re.search(rf'<tr data-id="{row_id}".*?</tr>', html, re.S)
    assert tr, f"{row_id} 줄을 찾지 못했습니다"
    return {m.group(2): m.group(1) + m.group(3)
            for m in re.finditer(r'<td class="([^"]*)" data-ir="([^"]+)"([^>]*)>', tr.group(0))}


def test_이은_줄의_IR_칸만_눌러_고치는_칸으로_선다(stage, sign_in, db):
    html = sign_in("consultant_a").get("/consulting?sheet=" + quote("스타트업")).text
    linked, loose = _ir_cells(html, stage["linked"].id), _ir_cells(html, stage["loose"].id)

    assert "cell multi" in linked["business_desc"], linked["business_desc"]
    assert "cell" in linked["revenue_2024"].split('"')[0]
    assert 'data-choices="Seed,Pre-A' in linked["series"], "투자라운드를 골라 넣는 보기가 없습니다"
    # IR 자료는 화면 글자(`있음`)로 파일 이름을 고칠 수 없다 — 안 열고, 누르면 까닭이 뜬다.
    assert " cell" not in linked["ir_file_name"] and "data-why=" in linked["ir_file_name"]
    # 안 이은 줄은 하나도 안 연다(누르면 표의 `data-ir-why` 가 뜬다).
    assert all(" cell" not in v for v in loose.values()), loose


def test_남의_줄의_IR_칸은_열리지_않는다(stage, sign_in, db):
    """팀원은 남의 줄을 **보지만** 못 고친다 — IR 칸도 같은 판정(`editable`)을 따른다."""
    html = sign_in("member").get("/consulting?sheet=" + quote("스타트업")).text
    cells = _ir_cells(html, stage["linked"].id)
    assert cells and all(" cell" not in v for v in cells.values()), cells
