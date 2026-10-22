"""딜 진행 관리에서 **Series A 이상 딜 소싱** 기업도 찾아 IR 요청·전달을 적는다.

사용자 요청(10/22): "딜 진행관리에서는 딜소싱에서의 IR 전달도 되야하므로, 기업
범위가 Series A 이상 딜 소싱 에 있는 회사도 검색이 되었음 좋겠어"

못 박는 것.

1. 「요청받은 기업」 후보에 Series A 기업이 **따로 실린다**(`data-series-a`) —
   화면이 `Series A` 딱지를 붙인다. IR 기업 현황에 같은 기업(이름 규칙
   `pipeline._key` = `deal_history._key`)이 있으면 IR 쪽 하나로만 뜨고,
   그 IR 기업이 딜소개 불가면 **둘 다** 안 뜬다.
2. 고르면 **IR 기업 현황에 줄이 안 생긴다** — `company_id` 없이 이름으로
   적힌다(IR 기업 현황에 없는 기업을 적어 온 그 길). 그래서 IR 기업 현황 ·
   딜 소개 목록(`/deals`) · [자료 보내기] 에 섞이지 않는다.
3. 그 줄은 화면에서 `Series A` 딱지로 Series A 탭에 잇고, `우리 DB 에 없는
   기업`(IR 기업 현황에 등록하라는 안내)에 안 든다.
4. IR 월간 현황 · IR 요청 후 미팅 없음이 그 이름을 **부분 일치로 IR 기업에
   붙이지 않는다** — 붙이면 남의 기업 문서에 그 투자사가 실린다.

기업·사람 이름은 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def stage(client, db, users):
    from app.models import IrCompany, SeriesACompany, SheetOwner, VcContact

    db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    who = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                    firm="가나벤처스", source_sheet="내 명단",
                    channel_kakao=1, connect_stage="connected")
    db.add_all([
        who,
        IrCompany(name="샘플애그"),
        IrCompany(name="샘플막힘", contract_status="blocked"),
        # 받은 딜 — 같은 기업을 두 번 받기도 한다(한 줄이 받은 딜 한 건).
        SeriesACompany(name="샘플에이랩", received_at="2026-10-01"),
        SeriesACompany(name="샘플에이랩", received_at="2026-10-15"),
        # IR 기업 현황에도 있는 기업 — 띄어쓰기·(주)만 다르다.
        SeriesACompany(name="(주)샘플 애그", received_at="2026-10-02"),
        # IR 쪽에서 딜소개 불가인 기업.
        SeriesACompany(name="샘플막힘", received_at="2026-10-03"),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "db": db, "who": who}


def _carrier(html: str) -> tuple:
    found = re.search(r"<div id=\"opts-ir-company\" hidden data-names='([^']*)'"
                      r" data-series-a='([^']*)'", html)
    assert found, "후보를 싣는 칸에 Series A 목록이 없습니다"
    return json.loads(found.group(1)), json.loads(found.group(2))


def test_Series_A_기업이_후보에_따로_실린다(stage):
    ir, sa = _carrier(stage["client"].get("/ir").text)

    assert sa == ["샘플에이랩"], f"Series A 후보가 다릅니다: {sa}"
    assert "샘플에이랩" not in ir, "Series A 기업이 IR 후보에 섞였습니다"
    assert "샘플애그" in ir and "(주)샘플 애그" not in sa, (
        "IR 기업 현황에도 있는 기업이 두 번 뜹니다 — IR 쪽 하나로 서야 합니다")
    assert "샘플막힘" not in ir + sa, (
        "딜소개 불가 기업이 Series A 쪽으로 다시 떴습니다")


def test_고르면_이름으로_적히고_IR_기업현황에_안_섞인다(stage):
    from app.models import IrCompany, IrRequest

    before = stage["db"].query(IrCompany).count()
    res = stage["client"].post("/ir/requests", follow_redirects=False,
                               data={"contact_id": stage["who"].id,
                                     "company_name": "샘플에이랩"})
    assert res.status_code == 303

    row = stage["db"].query(IrRequest).one()
    assert (row.company_id, row.company_name) == (None, "샘플에이랩")
    assert stage["db"].query(IrCompany).count() == before, (
        "IR 기업 현황에 줄이 생겼습니다 — 딜 소개 목록에 받기만 한 기업이 뜹니다")

    html = stage["client"].get("/ir").text
    assert f'href="/companies?tab=series-a&q={quote("샘플에이랩")}"' in html, (
        "Series A 줄로 돌아가는 링크가 없습니다")
    assert not re.search(r"우리 DB 에 없는 기업: [^<]*샘플에이랩", html), (
        "Series A 기업을 IR 기업 현황에 등록하라고 안내합니다")
    # [자료 보내기] 에는 안 실린다 — 붙일 IR 파일이 없는 기업이다.
    assert 'name="company_ids" value=""' not in html
    assert "자료 보내기</button>" not in html


def test_전달_완료_뒤에도_Series_A_로_잇는다(stage):
    from app.models import IrRequest

    stage["client"].post("/ir/requests", follow_redirects=False,
                         data={"contact_id": stage["who"].id,
                               "company_name": "샘플에이랩"})
    req = stage["db"].query(IrRequest).one()
    stage["client"].post(f"/ir/requests/{req.id}/deliver", follow_redirects=False)

    html = stage["client"].get("/ir").text
    done = html[html.index('id="delivered"'):]
    assert "/companies?tab=series-a&q=" in done, (
        "전달한 자료 줄에서 Series A 로 못 돌아갑니다")


def test_IR_기업에_부분일치로_안_붙는다(db, users):
    """`샘플에이랩` 요청이 `샘플에이랩스`(IR) 문서·표에 실리면 안 된다."""
    from app.models import IrCompany, IrRequest, SeriesACompany, VcContact
    from app.services import ir_monthly, ir_no_meeting

    who = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역",
                    firm="가나벤처스")
    near = IrCompany(name="샘플에이랩스")
    db.add_all([who, near, SeriesACompany(name="샘플에이랩")])
    db.flush()
    db.add(IrRequest(user_id=users["u1"].id, contact_id=who.id, company_id=None,
                     company_name="샘플에이랩", requested_at="2026-10-10"))
    db.commit()

    got = ir_monthly.monthly_requests(db, "2026-10")
    assert near.id not in got.by_company, (
        "Series A 기업 요청이 이름이 비슷한 IR 기업 월간 현황에 실렸습니다")
    assert got.skipped_count == 1

    rows, _ = ir_no_meeting.rows(db, None, date(2026, 10, 22))
    assert [r["company"] for r in rows] == ["샘플에이랩"], (
        "IR 요청 후 미팅 없음이 Series A 기업을 IR 기업 이름으로 바꿔 적었습니다")
