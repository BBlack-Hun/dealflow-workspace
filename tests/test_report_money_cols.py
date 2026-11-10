"""업무 보고 두 표의 매출 · 누적투자금액 칸(#173 팀원 요청).

요청: "업무보고 > 23년 매출, 24년 매출, 25년 매출, 26년 매출, 27년 예상매출액, 누적투자금액
컬럼 추가 > 내용도 자동으로 기입되게" · "그룹웨어 어떤 컬럼에서 넣어도 동일한 컬럼의 단어이면
모두 자동으로 기입되게".

  1. 칸 — IR 기업 현황과 같은 차례 · 같은 이름(`revenue_years.columns` 에서 투자유치희망금액 ·
     Pre Value 를 뺀 것). `소개한 기업` · `소개 후보` 두 표 모두, 투자유치희망금액 바로 뒤
  2. 값 — 따로 적어 두지 않고 IR 줄(없으면 Series A 줄)의 그 칸을 읽는다. Series A 줄은 그 칸을
     받는 자리(`company_sync.slot` — 올해 매출은 `revenue_2026`, 23년은 칸이 없어 빈칸)
  3. 고치기 — 줄의 저장 주소로 그 칸을 보낸다(계약여부와 같은 길). 이어진 줄은 따라 고친다

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

#: 2026년(conftest 가 못 박는다)에 서는 칸 — 요청의 여섯 칸 그대로(27년은 #490 의 `revenue_years.forecast`).
HEADS = ["23년 매출", "24년 매출", "25년 매출", "26년 매출", "27년 예상매출", "누적투자금액"]


@pytest.fixture()
def stage(db, users):
    from app.models import ContactActivity, IrCompany, SeriesACompany, VcContact

    ir = IrCompany(name="샘플보냄", sector_major="AI", raise_target="40",
                   revenue_2023="8.2억", revenue_2024="12", revenue_2025="1,224백만원",
                   revenue_recent="18.3", revenue_2027="25", funding_total="11")
    big = IrCompany(name="샘플큰가", sector_major="AI", raise_target="30", revenue_recent="5")
    db.add_all([ir, big])
    db.flush()
    linked = SeriesACompany(name="샘플 보냄")          # 같은 이름 — 저절로 잇는다
    sa = SeriesACompany(name="샘플에이랩", revenue_2024="3", revenue_2026="4", revenue_2027="7",
                        funding_total="2")
    db.add_all([linked, sa])
    who = VcContact(user_id=users["u1"].id, name="가상갑", firm="가나벤처스")
    db.add(who)
    db.flush()
    db.add(ContactActivity(contact_id=who.id, kind="deal_intro", content="공유",
                           happened_at="2026-08-12", source="manual",
                           company_names=json.dumps(["샘플보냄", "샘플에이랩", "샘플어디에도없음"],
                                                    ensure_ascii=False)))
    db.commit()
    return {"ir": ir, "big": big, "linked": linked, "sa": sa}


def _cells(row):
    return {m["head"]: (m["field"], m["value"]) for m in row["money"]}


# ── 1 · 2. 칸과 값 ───────────────────────────────────────────────────────────

def test_칸은_IR_기업_현황과_같은_차례_같은_이름(stage, db, users):
    from app.services import report, revenue_years

    heads = [h for _f, h in report.money_columns()]
    assert heads == HEADS
    assert heads == [h for f, h in revenue_years.columns() if f not in ("raise_target", "pre_value")]
    assert "투자유치희망금액" not in heads, "투자유치희망금액은 이 표가 따로 세운다(#118)"


def test_값은_IR_줄에서_없으면_Series_A_줄에서_읽는다(stage, db, users):
    from app.services import report

    got = report.intro_companies(db, date(2026, 8, 1), date(2026, 8, 31), users["u1"])
    rows = {c["company"]: _cells(c) for c in got["rows"]}
    ir = rows["샘플보냄"]
    assert [ir[h] for h in HEADS] == [
        ("revenue_2023", "8.2억"), ("revenue_2024", "12"), ("revenue_2025", "1,224백만원"),
        ("revenue_recent", "18.3"), ("revenue_2027", "25"), ("funding_total", "11")], \
        "글자는 IR 표처럼 적힌 그대로"
    sa = rows["샘플에이랩"]
    assert [sa[h] for h in HEADS] == [
        ("", ""), ("revenue_2024", "3"), ("revenue_2025", ""), ("revenue_2026", "4"),
        ("revenue_2027", "7"), ("funding_total", "2")], \
        "Series A 는 23년 칸이 없고, 올해 매출은 revenue_2026 이다"
    assert set(rows["샘플어디에도없음"].values()) == {("", "")}

    left = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 11, 7))["intro_left"]
    assert [(c["company"], _cells(c)["26년 매출"]) for c in left] == \
        [("샘플큰가", ("revenue_recent", "5"))]


# ── 화면 ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def page(stage, client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client.get("/report?month=2026-08").text


def _outer(html, company):
    """`소개한 기업` 표의 바깥 줄 — 기업명 칸 안에 작은 표가 있어 `</tr>` 가 둘이다."""
    at = html.index(f"<summary><b>{company}</b></summary>")
    start = html.rindex("<tr", 0, at)
    end = html.index("</tr>", html.index("</details>", at)) + len("</tr>")
    return html[start:end]


def _candidate(html, company):
    m = re.search(r"<tr\b[^>]*>(?:(?!<tr\b).)*?<b>" + re.escape(company) + r"</b>.*?</tr>",
                  html[html.index('id="intro-left"'):], re.S)
    assert m, f"{company} 후보 줄이 없다"
    return m.group(0)


def _heads(table_html):
    return [re.sub(r"<[^>]+>", "", h).strip()
            for h in re.findall(r"<th\b[^>]*>(.*?)</th>", table_html, re.S)]


def test_두_표_모두_투자유치희망금액_바로_뒤에_칸이_선다(page):
    from app.services import report

    want = [h for _f, h in report.money_columns()]
    intros = page[page.index('id="intros"'):page.index('id="intro-left"')]
    heads = _heads(intros[:intros.index("</thead>")])
    at = heads.index("투자유치희망금액")
    assert heads[at + 1:at + 1 + len(want)] == want
    left = page[page.index('id="intro-left"'):]
    heads = _heads(left[:left.index("</thead>")])
    at = heads.index("투자유치희망금액")
    assert heads[at + 1:at + 1 + len(want)] == want


def test_고칠_곳이_있는_칸만_눌러_고치는_칸이다(page, stage):
    ir = _outer(page, "샘플보냄")
    assert 'data-inline-url="/api/companies"' in ir
    assert '<td class="cell num" data-field="revenue_2023">8.2억</td>' in ir
    assert '<td class="cell num" data-field="funding_total">11</td>' in ir
    assert '<td class="cell num" data-field="revenue_2027">25</td>' in ir

    sa = _outer(page, "샘플에이랩")
    assert 'data-inline-url="/api/series-a-companies"' in sa
    assert '<td class="cell num" data-field="revenue_2026">4</td>' in sa
    assert 'data-field="revenue_2023"' not in sa, "Series A 에 없는 해는 고칠 곳이 없다"

    nowhere = _outer(page, "샘플어디에도없음")
    assert 'class="cell num"' not in nowhere

    assert '<td class="cell num" data-field="revenue_recent">5</td>' in _candidate(page, "샘플큰가")


def test_연간_보기의_소개한_기업_표에도_선다(stage, client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    html = client.get("/report?span=year&year=2026").text
    assert '<td class="cell num" data-field="revenue_2024">12</td>' in _outer(html, "샘플보냄")


# ── 3. 고치기 — 그 줄에 담기고 이어진 줄이 따라온다 ──────────────────────────────

def test_업무_보고에서_고치면_IR_줄에_담기고_이어진_Series_A_가_따라온다(page, stage, client, db):
    from app.models import IrCompany, SeriesACompany

    res = client.patch(f"/api/companies/{stage['ir'].id}", json={"funding_total": "15"})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(IrCompany, stage["ir"].id).funding_total == "15억"   # `억` 이 붙는다(#217)
    assert db.get(SeriesACompany, stage["linked"].id).funding_total == "15억", \
        "같은 기업의 Series A 줄이 안 따라왔다(company_sync)"
    again = client.get("/report?month=2026-08").text
    assert '<td class="cell num" data-field="funding_total">15억</td>' in _outer(again, "샘플보냄")


def test_Series_A_탭에서_고친_값도_다음_화면에_그대로(page, stage, client):
    res = client.patch(f"/api/series-a-companies/{stage['sa'].id}", json={"revenue_2026": "6"})
    assert res.status_code == 200, res.text
    again = client.get("/report?month=2026-08").text
    assert '<td class="cell num" data-field="revenue_2026">6억</td>' in _outer(again, "샘플에이랩")
