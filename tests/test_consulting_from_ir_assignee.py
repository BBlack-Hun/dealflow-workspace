"""IR `담당자` 를 투자컨설턴트로 넘기면 그 사람 표에 이어진 줄이 선다(#201).

투자컨설턴트는 IR 기업 현황을 못 연다 — 맡은 기업을 볼 자리가 투자컨설턴트 표뿐이다.
그래서 IR 에서 지금 맡은 사람(넘긴 이력의 마지막 이름)이 **켜져 있는 투자컨설턴트 계정 하나의
표시 이름**으로 바뀌면 그 사람 앞으로 줄을 세우고 기업 번호로 잇는다. 잇는 칸의 빈칸은
커밋할 때 IR 값으로 채워진다(`company_sync`).

안 세우는 자리: 팀원 계정 이름 · 맡은 사람이 그대로인 저장 · 이미 이어진 줄이 있는 기업 ·
기업명이 같은 안 이은 줄이 있는 기업 · 정지한 컨설턴트.

이름은 전부 가상값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD

NAME = "샘플넘김랩"


@pytest.fixture()
def stage(db, users):
    from app.models import IrCompany, User
    from app.services import auth as auth_svc

    consultant = User(name="컨설갑", phone="01000000201", role="consultant",
                      can_view_consulting=1,
                      password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    ir = IrCompany(name=NAME, contact_name="가대표", contact_phone="010-0000-0301",
                   contact_email="ceo@example.com", region="서울")
    db.add_all([consultant, ir])
    db.commit()
    return {"consultant": consultant, "ir": ir}


def _rows(db, ir_id=None):
    from sqlalchemy import select

    from app.models import ConsultingCompany

    db.expire_all()
    stmt = select(ConsultingCompany)
    if ir_id is not None:
        stmt = stmt.where(ConsultingCompany.ir_company_id == ir_id)
    return db.execute(stmt).scalars().all()


def test_컨설턴트로_넘기면_그_사람_표에_이어진_줄이_서고_잇는_칸이_채워진다(logged_in, db, stage):
    from app.models import EditLog
    from app.services import consulting_sheets as cs

    ir, who = stage["ir"], stage["consultant"]
    r = logged_in.patch(f"/api/companies/{ir.id}",
                        json={"assignee_name": "강민준 > 11/09 컨설갑"})
    assert r.status_code == 200, r.text

    rows = _rows(db, ir.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == who.id, "주인은 넘겨받은 컨설턴트다"
    assert row.ir_link_auto == 0, "기업 번호로 이었다(이름 맞추기가 아니다)"
    assert row.sheet == cs.default_label(db), "[기업 추가] 의 기본 탭"
    assert row.company_name == NAME
    assert (row.ceo_name, row.phone, row.email, row.region) == (
        "가대표", "010-0000-0301", "ceo@example.com", "서울"), "잇는 칸이 IR 값으로 안 채워졌다"
    # 누른 사람은 IR 담당자를 고쳤을 뿐이라 줄이 선 것은 수정 로그로 짚는다(새 줄 로그는
    # 번호가 안 실리는 길이라 기업 이름으로 — `test_ir_consulting_edit` 과 같다).
    logs = [(x.action, x.row_label) for x in db.query(EditLog).all()
            if x.table_name == "consulting_companies"]
    assert logs == [("create", NAME)], logs


def test_새_기업을_컨설턴트_담당으로_넣어도_선다(logged_in, db, stage):
    r = logged_in.post("/api/companies", json={"name": "샘플새기업", "assignee_name": "컨설갑"})
    assert r.status_code == 200, r.text
    rows = _rows(db, r.json()["id"])
    assert [x.user_id for x in rows] == [stage["consultant"].id]


def test_팀원_이름이나_맡은_사람이_그대로인_저장에는_안_선다(logged_in, db, users, stage):
    ir = stage["ir"]
    r = logged_in.patch(f"/api/companies/{ir.id}", json={"assignee_name": users["u2"].name})
    assert r.status_code == 200, r.text
    assert _rows(db) == [], "팀원 계정 이름으로는 세우지 않는다"

    # 기능이 생기기 전부터 컨설턴트가 맡던 기업 — 다른 칸을 고친 저장으로는 안 되살린다.
    ir.assignee_name = "컨설갑"
    db.commit()
    r = logged_in.patch(f"/api/companies/{ir.id}",
                        json={"assignee_name": "컨설갑", "region": "부산"})
    assert r.status_code == 200, r.text
    assert _rows(db) == []


def test_이미_이어진_줄이나_같은_이름의_줄이_있으면_또_세우지_않는다(logged_in, db, users, stage):
    from app.models import ConsultingCompany, IrCompany
    from app.services import consulting_sheets as cs

    ir = stage["ir"]
    sheet = cs.default_label(db)
    db.add(ConsultingCompany(user_id=users["u2"].id, sheet=sheet, company_name=NAME,
                             ir_company_id=ir.id))
    db.commit()
    r = logged_in.patch(f"/api/companies/{ir.id}", json={"assignee_name": "컨설갑"})
    assert r.status_code == 200, r.text
    assert len(_rows(db)) == 1, "이어진 줄이 있는데 또 세웠다"

    # 이름이 같은 IR 기업이 둘이라 저절로 안 이어진 줄 — 사람이 `/ir-link` 에서 잇는다.
    other = IrCompany(name="샘플같은이름")
    db.add_all([other, IrCompany(name="(주)샘플같은이름")])
    db.commit()
    loose = ConsultingCompany(user_id=users["u2"].id, sheet=sheet,
                              company_name="샘플같은이름 / 무료")
    db.add(loose)
    db.commit()
    assert loose.ir_company_id is None
    r = logged_in.patch(f"/api/companies/{other.id}", json={"assignee_name": "컨설갑"})
    assert r.status_code == 200, r.text
    assert len(_rows(db)) == 2, "기업명이 같은 줄이 있는데 또 세웠다"


def test_정지한_컨설턴트에게는_안_선다(logged_in, db, stage):
    stage["consultant"].is_active = 0
    db.commit()
    r = logged_in.patch(f"/api/companies/{stage['ir'].id}", json={"assignee_name": "컨설갑"})
    assert r.status_code == 200, r.text
    assert _rows(db) == []


def test_컨설턴트_화면에_그_줄과_탭의_월_칸이_보인다(logged_in, client, db, stage):
    """월 칸은 탭마다 한 벌이라(`ConsultingColumn`) 줄 주인이 컨설턴트여도 머리글이 선다."""
    from app.models import ConsultingColumn
    from app.services import consulting_sheets as cs

    db.add(ConsultingColumn(sheet=cs.default_label(db), label="샘플월 리마인드", position=0))
    db.commit()
    r = logged_in.patch(f"/api/companies/{stage['ir'].id}", json={"assignee_name": "컨설갑"})
    assert r.status_code == 200, r.text

    client.post("/logout")
    client.post("/login", data={"phone": "01000000201", "password": DEMO_PASSWORD})
    html = client.get("/consulting").text
    assert NAME in html and "샘플월 리마인드" in html
