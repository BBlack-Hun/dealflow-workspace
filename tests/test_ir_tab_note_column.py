"""#103 "기업현황 > 컬럼 메모노출되게" — IR 기업 현황 탭에 `메모`(`note`) 칸.

[수정] 창에만 있던 칸이다(시트 `비고` 를 옮겨 온 칸 · 10/27 TIPS 조사 메모도 여기).
`IR 자료` 바로 앞 — `IR 자료` 는 맨 끝 그대로다(관리자가 붙인 칸 `TIPS` 등은 그 오른쪽).
표에서 눌러 고치고, 고친 값은 검색에도 걸린다. 스타트업DB 탭은 그대로다.
값은 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import pytest

from tests.conftest import DEMO_PASSWORD
from tests.test_company_tab_order import _head_names


@pytest.fixture()
def logged(client, users, db):
    from app.models import IrCompany

    row = IrCompany(name="샘플가온헬스", received_at="2026-09-01",
                    note="TIPS 가능\n누적 투자 12억")
    db.add(row)
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.company_id = row.id
    return client


def test_IR_탭에만_IR_자료_앞에_메모가_선다(logged):
    html = logged.get("/companies").text
    names = _head_names(html)
    assert names[names.index("IR 자료") - 1] == "메모", names
    body = html.split("<tbody>", 1)[1]
    assert 'data-field="note" data-type="long">TIPS 가능\n누적 투자 12억</div>' in body
    assert "메모" not in _head_names(logged.get("/companies?tab=db").text)


def test_표에서_고치면_저장되고_검색에_걸린다(logged, db):
    from app.models import IrCompany

    res = logged.patch(f"/api/companies/{logged.company_id}", json={"note": " 후속 검토 "})
    assert res.status_code == 200, res.text
    assert "후속 검토" in res.json()["search"]
    db.expire_all()
    assert db.get(IrCompany, logged.company_id).note == "후속 검토"
