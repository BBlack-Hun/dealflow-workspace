"""이어진 IR 기업의 칸을 **읽기만** — 투자컨설턴트(#83) · 스타트업 명단(#85).

10/28 담당자 '추천대로': 값을 그 표에 한 벌 더 적지 않고, 줄에 이어 둔 IR 기업의 값을
그대로 보여 준다(`services/ir_readonly.py`). 여기서 못 박는 것.

1. 스타트업 표 — `이메일` 오른쪽(바로 오른쪽은 `미팅제공일자` 자리라 그 뒤)에 IR 칸이
   서고, 이은 줄은 IR 값, 안 이은 줄은 빈칸이다. 눌러 고치는 칸이 아니다.
2. 스타트업 표 `기업명` 을 IR 기업 이름으로 고치면 그 기업에 이어지고, 응답에 IR 값이
   실려 그 자리에서 다시 그린다(후보창에서 고르는 길).
3. 투자컨설턴트 — 스타트업 탭 `이메일` 오른쪽에 같은 묶음, 계약 탭에는 없다.

이름·기업명·금액은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

LIST = "샘플 스타트업(85)"


def _heads(html: str) -> list:
    m = re.search(r"<thead>(.*?)</thead>", html, re.S)
    assert m, "표 머리글을 찾지 못했습니다"
    return [(" ".join(re.sub(r"<[^>]+>", " ", cell).split()), "ir-ro" in attrs)
            for attrs, cell in re.findall(r"<th\b([^>]*)>(.*?)</th>", m.group(1), re.S)]


@pytest.fixture()
def ir(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플팜", revenue_recent="12", funding_total="30",
                    raise_target="50", pre_value="200", competitiveness="특허 3건",
                    founded_year="2021", region="판교", guarantee="기보 5억",
                    business_desc="스마트팜 설비", series="Pre-A",
                    ir_file_name="샘플팜_IR.pdf")
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def startup(client, db, users, ir):
    from app.models import SheetOwner, VcContact
    from app.services import contact_columns as cc

    db.add(SheetOwner(label=LIST, user_id=users["u1"].id, layout=cc.STARTUP, is_hidden=0))
    db.commit()     # 명단이 먼저 있어야 새 줄이 스타트업 줄로 읽혀 저절로 이어진다
    linked = VcContact(user_id=users["u1"].id, source_sheet=LIST, name="김샘플",
                       firm="샘플팜", phone="01000000851")
    loose = VcContact(user_id=users["u1"].id, source_sheet=LIST, name="이샘플",
                      firm="없는기업", phone="01000000852")
    db.add_all([linked, loose])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "linked": linked, "loose": loose}


def _startup_url() -> str:
    from app.services import contact_columns as cc

    return f"/{cc.page_of(cc.STARTUP)}?sheet={quote(LIST)}"


def test_스타트업_표_이메일_오른쪽에_IR_칸이_읽기_전용으로_선다(startup, db):
    from app.services import ir_readonly

    assert startup["linked"].ir_company_id, "이름이 하나 맞는 새 줄은 저절로 이어진다"
    html = startup["client"].get(_startup_url()).text
    heads = _heads(html)
    names = [n for n, _ in heads]
    want = [c.label for c in ir_readonly.startup_columns()]
    at = names.index("미팅제공일자")
    assert names[at - 1] == "이메일"
    assert names[at + 1:at + 1 + len(want)] == want, names
    assert all(ro for _, ro in heads[at + 1:at + 1 + len(want)])
    assert want[0].endswith("년 매출")     # 해마다 이름이 바뀐다(`revenue_years.columns`)
    assert {"특이사항 (장점)", "설립년도", "지역", "정책자금", "Pre Value"} <= set(want)

    rows = re.findall(r'<tr class="data-row[^"]*" data-id="(\d+)"[^>]*>(.*?)</tr>', html, re.S)
    cells = {int(i): dict(re.findall(r'data-ir="(\w+)" title="([^"]*)"', body))
             for i, body in rows}
    got = cells[startup["linked"].id]
    assert got["revenue_recent"] == "12" and got["guarantee"] == "기보 5억"
    assert got["founded_year"] == "2021" and got["competitiveness"] == "특허 3건"
    assert set(cells[startup["loose"].id].values()) == {""}, "안 이은 줄은 빈칸이다"
    # 눌러 고치는 칸이 아니다 — `data-field` 로 IR 칸 이름이 실리지 않는다.
    assert 'data-field="guarantee"' not in html
    # `기업명` 칸에 IR 기업 후보를 띄운다(#85).
    assert "data-ir-hint" in html and 'id="opts-ir-company"' in html


def test_기업명을_IR_기업_이름으로_고치면_이어지고_값이_실려_온다(startup, db, ir):
    from app.models import VcContact

    loose = startup["loose"]
    assert loose.ir_company_id is None
    res = startup["client"].patch(f"/api/contacts/{loose.id}", json={"firm": "샘플팜"})
    assert res.status_code == 200, res.text
    assert res.json()["ir_values"]["pre_value"] == "200"
    db.expire_all()
    row = db.get(VcContact, loose.id)
    assert row.ir_company_id == ir.id and row.ir_link_auto == 1


def test_사람이_고른_연결은_기업명을_고쳐도_그대로다(startup, db, ir):
    from app.models import IrCompany, VcContact

    other = IrCompany(name="샘플랩")
    db.add(other)
    db.commit()
    row = db.get(VcContact, startup["linked"].id)
    row.ir_link_auto = 0           # 사람이 /ir-link 에서 고른 연결
    db.commit()
    res = startup["client"].patch(f"/api/contacts/{row.id}", json={"firm": "샘플랩"})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(VcContact, row.id).ir_company_id == ir.id


def test_투자컨설턴트_스타트업_탭에만_IR_칸이_선다(client, db, users, ir):
    from app.models import ConsultingCompany
    from app.services import ir_readonly

    users["u1"].can_view_consulting = 1
    db.add(ConsultingCompany(user_id=users["u1"].id, company_name="샘플팜",
                             ir_company_id=ir.id))
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})

    html = client.get("/consulting?sheet=" + quote("스타트업")).text
    names = [n for n, _ in _heads(html)]
    want = [c.label for c in ir_readonly.consulting_columns()]
    at = names.index("이메일")
    assert names[at + 1:at + 1 + len(want)] == want, names
    assert "수신일" not in want and "성공보수율" not in want and "담당자" not in want
    assert 'data-ir="business_desc" title="스마트팜 설비"' in html
    assert 'data-ir="ir_file_name" title="있음"' in html

    contract = client.get("/consulting?sheet=" + quote("월간 계약 업무현황표")).text
    assert "ir-ro" not in contract
