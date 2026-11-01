"""기업명 옆 `투자유치희망금액` 칸(#118) — 딜 진행 관리 4표 · 업무 보고 3표 · 엑셀.

값은 저장하지 않고 열 때마다 읽는다: 이어진 IR 기업 번호 → IR 기업명 → Series A 같은
이름(`pipeline.company_finder`). 표기는 `amount.phrase`(`18.3억` · `5~10억`), 없으면 빈칸.

기업·사람 이름은 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import io
import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD
from .test_deal_history import _mine_history

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture()
def stage(client, db, users):
    from app.models import IrCompany, IrRequest, Meeting, SeriesACompany, VcContact

    agg = IrCompany(name="샘플애그", raise_target="18.3")
    medi = IrCompany(name="샘플메디", raise_target="5-10억 사이")
    who = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역", firm="가나벤처스")
    db.add_all([agg, medi, who,
                SeriesACompany(name="샘플에이랩", raise_target="30"),
                # IR 기업 현황에도 있는 기업 — IR 값이 먼저다.
                SeriesACompany(name="(주)샘플 애그", raise_target="99")])
    db.flush()
    u1 = users["u1"].id
    db.add_all([
        IrRequest(user_id=u1, contact_id=who.id, company_name="샘플애그", company_id=agg.id,
                  requested_at="2026-08-03", status="open"),
        IrRequest(user_id=u1, contact_id=who.id, company_name="샘플에이랩",
                  requested_at="2026-08-04", status="delivered", delivered_at="2026-08-05"),
        Meeting(user_id=u1, contact_id=who.id, company_name="샘플애그", company_id=agg.id,
                kind="first", scheduled_at="2026-08-20", status="scheduled"),
        Meeting(user_id=u1, contact_id=who.id, company_name="샘플메디", kind="first",
                scheduled_at="2026-08-10", status="done", outcome="review"),
    ])
    db.commit()
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return {"client": client, "agg": agg, "medi": medi}


def test_번호_이름_Series_A_차례로_읽는다(stage, db):
    from app.services import pipeline

    find = pipeline.company_finder(db)

    def show(company_id, name):
        return pipeline.raise_target(find(company_id, name))

    assert show(stage["medi"].id, "엉뚱한 이름") == "5~10억", "이어진 번호가 이름보다 먼저"
    assert show(None, "샘플 애그") == "18.3억", "이름이 같으면 IR 값 — Series A 값이 아니다"
    assert show(None, "샘플에이랩") == "30억", "IR 에 없으면 Series A 탭의 같은 칸"
    assert show(None, "샘플없음") == "" and show(None, "") == ""


def _table(html: str, marker: str) -> str:
    start = html.index(marker)
    return html[start:html.index("</table>", start)]


def test_딜_진행_관리_네_표에_선다(stage):
    html = stage["client"].get("/ir").text

    assert "IR 전달기업" in html and "전달한 자료" not in re.sub(r"\{#.*?#\}", "", html, flags=re.S)
    # 열린 요청 · 미팅 스케줄(번호로 이어진 샘플애그) — 두 줄.
    assert html.count('<td class="num">18.3억</td>') == 2
    assert '<td class="num">30억</td>' in _table(html, 'id="delivered-table"')
    assert '<td class="num">5~10억</td>' in _table(html, 'id="review-table"')


def test_업무_보고_화면과_엑셀에_선다(stage):
    client = stage["client"]
    page = client.get("/report?month=2026-08").text
    # 미팅 표 둘(샘플애그 · 샘플메디) + 반응 표(IR 요청 둘 · 미팅 요청 · 미팅완료 · 리마인드 TEL).
    assert page.count('<td class="num">18.3억</td>') == 3
    assert page.count('<td class="num">30억</td>') == 1
    assert page.count('<td class="num">5~10억</td>') >= 2

    wb = openpyxl.load_workbook(io.BytesIO(
        client.get("/api/export/report.xlsx?month=2026-08").content))
    for sheet, value in (("2026-08 미팅", "18.3억"), ("2026-08 반응", "30억")):
        rows = [list(r) for r in wb[sheet].iter_rows(values_only=True)]
        head = next(r for r in rows if "기업명" in r)
        at = head.index("기업명")
        assert head[at + 1] == "투자유치희망금액", f"{sheet}: 기업명 바로 오른쪽이어야 한다"
        assert any(r[at + 1] == value for r in rows), f"{sheet}: {value} 가 없다"


def test_소개한_기업에도_선다(db, users):
    from app.models import IrCompany
    from app.services import report

    _mine_history(db, users)
    db.query(IrCompany).filter_by(name="샘플애그").one().raise_target = "12"
    db.commit()
    got = report.intro_companies(db, date(2026, 1, 1), date(2026, 12, 31), users["u1"])
    assert [(c["company"], c["raise_target"]) for c in got["rows"]] == [("샘플애그", "12억")]
