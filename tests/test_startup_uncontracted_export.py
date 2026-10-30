"""스타트업 월간 발송 › 「계약 안 한 기업 — 보내지 않음」 엑셀 내려받기 (#93 리뷰).

화면 구역과 **같은 줄**이 나가고, 화면을 못 여는 계정에는 없는 자리(404)다.
이름은 전부 지어낸 값이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io

import openpyxl

from tests.test_startup_monthly_send import FIRM, PERSON, _login, _month, _turn_on


def test_계약_안_한_기업_구역을_엑셀로_내려받는다(db, users, client):
    from app.models import IrCompany, IrRequest, VcContact

    month = _month()
    made = {}
    for name, status in (("샘플디", "none"), ("샘플이", "review"),
                         ("샘플에프", "blocked"), ("샘플에이", "paid")):
        made[name] = IrCompany(name=name, contract_status=status,
                               kakao_room_name=f" {name} 대표님 ")
    db.add_all(made.values())
    contact = VcContact(user_id=1, name=PERSON, firm=FIRM)
    db.add(contact)
    db.flush()
    for c in made.values():
        db.add(IrRequest(user_id=1, contact_id=contact.id, company_id=c.id,
                         company_name=c.name, requested_at=f"{month}-05"))
    db.commit()
    _turn_on(db, user_id=1)

    page = _login(client).get(f"/deals/startup-ir?month={month}").text
    box = page.split('data-testid="startup-uncontracted"', 1)[1].split("</section>", 1)[0]
    assert f"/api/export/startup-uncontracted.xlsx?month={month}" in box

    got = client.get(f"/api/export/startup-uncontracted.xlsx?month={month}")
    assert got.status_code == 200
    rows = list(openpyxl.load_workbook(io.BytesIO(got.content)).active.values)
    assert rows[0][0] == "기업명" and rows[0][3] == f"{month} 말까지 요청한 투자사(곳)"
    # 화면 구역과 같은 줄 — 계약 기업(보내는 표)과 딜소개 불가는 없다.
    assert sorted(r[:3] for r in rows[1:]) == [
        ("샘플디", "미계약", "샘플디 대표님"), ("샘플이", "계약검토중", "샘플이 대표님")]
    assert all(r[3:] == (1, 1) for r in rows[1:])

    # 화면을 못 여는 계정에는 내려받기도 없는 자리다.
    other = _login(client, phone="01000000002")
    assert other.get(f"/api/export/startup-uncontracted.xlsx?month={month}").status_code == 404
