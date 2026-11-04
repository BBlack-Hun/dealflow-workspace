"""업무 보고 — 계약여부를 골라서 바로 고친다(#147 팀원 요청).

요청: "업무보고 > 컬럼 계약여부 단어 선택해서 기입할수 있게 , 다른 컬럼의 계약여부도 마찬가지".
업무 보고(`/report`)의 두 표 — `소개한 기업` 과 맨 아래 `소개 후보` — 의 계약여부 칸.

  1. 칸 — IR 표와 같은 고르기 칸(`data-type="pick"`) · 같은 여덟 말(`CONTRACT_LABELS`)
  2. 저장 자리 — 값을 읽어 온 줄 한 곳: IR 줄이면 `/api/companies`, Series A 줄이면
     `/api/series-a-companies`(줄의 `data-inline-url`). 이름으로 짝을 못 찾은 줄은 글자 그대로
  3. 같은 PATCH 길 — 계약년월 · 계약 완료일 · 따라 고치기(`company_sync`)가 IR 표와 같이 돈다

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def stage(db, users):
    from app.models import ContactActivity, IrCompany, SeriesACompany, VcContact

    ir_sent = IrCompany(name="샘플보냄", raise_target="40", sector_major="AI",
                        contract_status="none")
    big = IrCompany(name="샘플큰가", raise_target="30", sector_major="AI",
                    series="Series A (누적 10억 이상)", contract_status="review")
    db.add_all([ir_sent, big])
    db.flush()
    # IR 에 이어진 Series A 줄(같은 이름 — 저절로 잇는다) · IR 에 없는 Series A 줄.
    linked = SeriesACompany(name="샘플 보냄")
    sa_only = SeriesACompany(name="샘플에이랩", contract_status="free")
    db.add_all([linked, sa_only])
    who = VcContact(user_id=users["u1"].id, name="가상갑", firm="가나벤처스")
    db.add(who)
    db.flush()
    db.add(ContactActivity(contact_id=who.id, kind="deal_intro", content="공유",
                           happened_at="2026-08-12", source="manual",
                           company_names=json.dumps(["샘플보냄", "샘플에이랩", "샘플어디에도없음"],
                                                    ensure_ascii=False)))
    db.commit()
    return {"ir": ir_sent, "big": big, "linked": linked, "sa": sa_only}


@pytest.fixture()
def page(stage, client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client.get("/report?month=2026-08").text


def _row(html: str, company: str) -> str:
    """그 기업 이름이 든 `<tr …>…</tr>` 한 줄(펼침 속 작은 표가 아니라 바깥 줄)."""
    for m in re.finditer(r"<tr\b[^>]*>(?:(?!<tr\b).)*?<b>" + re.escape(company) + r"</b>.*?</tr>",
                         html, re.S):
        return m.group(0)
    raise AssertionError(f"{company} 줄이 화면에 없다")


def _outer(html: str, company: str) -> str:
    """`소개한 기업` 표의 바깥 줄 — 기업명 칸 안에 작은 표가 있어 `</tr>` 가 둘이다."""
    at = html.index(f"<summary><b>{company}</b></summary>")
    start = html.rindex("<tr", 0, at)
    end = html.index("</details>", at)
    end = html.index("</tr>", end) + len("</tr>")
    return html[start:end]


def _contract_td(row: str) -> str:
    found = re.search(r'<td[^>]*data-field="contract_status"[^>]*>[^<]*</td>', row)
    assert found, "계약여부가 고르기 칸이 아니다:\n" + row
    return found.group(0)


# ── 1. 데이터 — 줄마다 고칠 곳 ────────────────────────────────────────────────

def test_줄마다_읽어_온_곳의_번호와_표를_싣는다(stage, db, users):
    from app.services import report

    got = report.intro_companies(db, date(2026, 8, 1), date(2026, 8, 31), users["u1"])
    rows = {c["company"]: (c["company_id"], c["company_kind"]) for c in got["rows"]}
    assert rows == {"샘플보냄": (stage["ir"].id, "ir"),          # IR 이 있으면 IR(이어진 Series A 줄이 아니라)
                    "샘플에이랩": (stage["sa"].id, "series_a"),
                    "샘플어디에도없음": (None, "")}
    left = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 11, 1))["intro_left"]
    assert [(c["company"], c["company_id"], c["company_kind"]) for c in left] == \
        [("샘플큰가", stage["big"].id, "ir")]


# ── 2. 화면 — 고르기 칸 · 저장 주소 ───────────────────────────────────────────

def test_두_표의_계약여부가_IR_표와_같은_고르기_칸이다(page):
    from app.routers.companies import CONTRACT_LABELS

    assert "js/inline_edit.js" in page, "업무 보고가 칸 고치기 부품을 안 싣는다"
    assert page.count('<table class="grid-table compact" data-inline-url="/api/companies">') == 2
    for row in (_outer(page, "샘플보냄"), _outer(page, "샘플에이랩"), _row(page, "샘플큰가")):
        td = _contract_td(row)
        assert 'class="cell"' in td and 'data-type="pick"' in td, td
        choices = re.search(r'data-choices="([^"]*)"', td).group(1)
        assert [v.strip() for v in choices.split(",")] == list(CONTRACT_LABELS.values()), \
            "보기가 IR 표의 여덟 말과 다르다 — 새 목록을 만들면 안 된다"


def test_IR_줄은_IR_로_Series_A_줄은_Series_A_로_저장한다(page, stage):
    ir = _outer(page, "샘플보냄")
    assert f'data-id="{stage["ir"].id}"' in ir and 'data-inline-url="/api/companies"' in ir
    assert ">미계약</td>" in _contract_td(ir)

    sa = _outer(page, "샘플에이랩")
    assert f'data-id="{stage["sa"].id}"' in sa
    assert 'data-inline-url="/api/series-a-companies"' in sa
    assert ">무료계약완료</td>" in _contract_td(sa)

    big = _row(page, "샘플큰가")
    assert f'data-id="{stage["big"].id}"' in big and 'data-inline-url="/api/companies"' in big
    assert ">계약검토중</td>" in _contract_td(big)


def test_짝을_못_찾은_줄은_고칠_곳이_없어_글자로_남는다(page):
    row = _outer(page, "샘플어디에도없음")
    head = row[:row.index(">") + 1]
    assert "data-id" not in head and "data-inline-url" not in head, head
    assert 'data-field="contract_status"' not in row and 'class="cell"' not in row, row


def test_연간_보기의_소개한_기업_표도_고르기_칸이다(stage, client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    html = client.get("/report?span=year&year=2026").text
    assert "js/inline_edit.js" in html
    assert 'data-inline-url="/api/series-a-companies"' in _outer(html, "샘플에이랩")
    _contract_td(_outer(html, "샘플보냄"))


# ── 3. 같은 PATCH 길 — 계약년월 · 계약 완료일 · 따라 고치기 ─────────────────────

def test_IR_줄을_고르면_계약년월_완료일이_적히고_이어진_Series_A_가_따라온다(page, stage, client, db):
    """칸은 보이는 말을 그대로 보낸다(`inline_edit.js`) — 라우터가 열쇠로 맞춘다."""
    from app import clock
    from app.models import IrCompany, SeriesACompany

    url = re.search(r'data-inline-url="([^"]+)"', _outer(page, "샘플보냄")).group(1)
    res = client.patch(f"{url}/{stage['ir'].id}", json={"contract_status": "유료계약완료"})
    assert res.status_code == 200, res.text
    assert res.json()["contract_label"] == "유료계약완료"

    db.expire_all()
    ir = db.get(IrCompany, stage["ir"].id)
    today = clock.today().isoformat()
    assert (ir.contract_status, ir.contract_ym, ir.contract_done_at) == ("paid", today[:7], today)
    linked = db.get(SeriesACompany, stage["linked"].id)
    assert linked.ir_company_id == ir.id
    assert linked.contract_status == "paid", "이어진 Series A 줄이 안 따라왔다(company_sync)"

    again = client.get("/report?month=2026-08").text
    assert ">유료계약완료</td>" in _contract_td(_outer(again, "샘플보냄"))


def test_Series_A_줄을_고르면_그_줄만_바뀌고_계약년월이_적힌다(page, stage, client, db):
    from app import clock
    from app.models import IrCompany, SeriesACompany

    url = re.search(r'data-inline-url="([^"]+)"', _outer(page, "샘플에이랩")).group(1)
    res = client.patch(f"{url}/{stage['sa'].id}", json={"contract_status": "유료계약완료"})
    assert res.status_code == 200, res.text

    db.expire_all()
    sa = db.get(SeriesACompany, stage["sa"].id)
    assert (sa.contract_status, sa.contract_ym) == ("paid", None), \
        "무료 → 유료는 계약 완료끼리라 계약년월을 안 적는다(IR 과 같은 규칙)"
    assert [c.contract_status for c in db.query(IrCompany).order_by(IrCompany.id)] == \
        ["none", "review"], "IR 에 없는 기업인데 IR 줄이 바뀌었다"

    client.patch(f"{url}/{stage['sa'].id}", json={"contract_status": "미계약"})
    client.patch(f"{url}/{stage['sa'].id}", json={"contract_status": "무료계약완료"})
    db.expire_all()
    assert db.get(SeriesACompany, stage["sa"].id).contract_ym == clock.today().isoformat()[:7]


def test_모르는_말은_IR_표처럼_막는다(page, stage, client, db):
    from app.models import IrCompany

    bad = client.patch(f"/api/companies/{stage['ir'].id}", json={"contract_status": "아마도 계약"})
    assert bad.status_code == 400 and "모르는 계약여부" in bad.json()["detail"]
    db.expire_all()
    assert db.get(IrCompany, stage["ir"].id).contract_status == "none"
