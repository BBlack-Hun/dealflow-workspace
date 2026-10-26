"""IR 기업 현황 매출·금액 칸 + 연도 자동 (#75).

팀원 요청: "23·24·25년 매출액 · 누적투자금액 · 투자유치희망금액 · Pre Value 를 IR 기업
현황 소분류 옆에 · 26년 매출액 칸 · 연도가 바뀌면 자동으로 연도가 추가되게".
담당자가 추천안대로 정했다(`services/revenue_years.py` 머리말).

지키는 것
  1. 보이는 해는 **오늘 기준** 지난 세 해 + `최근 매출액(올해)` — 2026 · 2027 로 시계를 민다.
  2. IR 기업 현황 탭 `소분류` 바로 뒤에 그 칸들이 서고, 머리글과 칸이 자리마다 짝이 맞는다.
  3. 해가 바뀌면 `최근 매출액` 을 지난해 칸으로 옮겨 적는다 — 빈 칸만 · 해마다 한 번 · 로그에 남는다.
  4. IR 기업 현황 탭에서 고친 값이 스타트업DB 탭에 보인다(같은 줄 · 같은 API).
  5. 칸을 하나 더 팔 때 적을 곳(`CompanyIn` · companies.js `FIELDS`)이 빠지면 잡힌다.

해는 `revenue_years.this_year`(= `clock.today().year`) 하나로 민다 — `clock.now` 를 밀면
로그인 세션 만료까지 따라 움직인다(tests/test_company_updated_at.py 의 `_rewind` 머리말).
다른 검사들은 2026 에 못 박혀 있다(tests/conftest.py). 값은 전부 지어낸 것이다.
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "app" / "static" / "js" / "companies.js"

Y2026 = date(2026, 10, 26)
Y2027 = date(2027, 1, 4)


@pytest.fixture()
def at(monkeypatch):
    """`at(날짜)` — 연도별 매출 칸이 읽는 올해를 그 날의 해로(기본은 2026 — tests/conftest.py)."""
    from app.services import revenue_years

    def move(day: date) -> None:
        monkeypatch.setattr(revenue_years, "this_year", lambda: day.year)
    return move


def _heads(html: str) -> list:
    head = html.split("</thead>")[0].split("<thead>")[-1]
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m)).strip()
            for m in re.findall(r"<th\b[^>]*>(.*?)</th>", head, re.S)]


def _first_row_fields(html: str) -> list:
    """첫 줄의 칸마다 `data-field` — 없으면 None. 머리글과 자리로 짝짓는다."""
    body = html.split("</thead>")[1]
    row = re.search(r"<tr\b[^>]*data-id[^>]*>(.*?)</tr>", body, re.S).group(1)
    out = []
    for cell in re.finditer(r"<td\b([^>]*)>(.*?)</td>", row, re.S):
        f = re.search(r'data-field="([a-z_0-9]+)"', cell.group(1) + cell.group(2))
        out.append(f.group(1) if f else None)
    return out


def _panel_ids(html: str) -> list:
    return re.findall(r'id="f-([a-z_0-9]+)"', html)


def _script_fields() -> list:
    listed = re.search(r"var FIELDS = \[(.*?)\];", SCRIPT.read_text("utf-8"), re.S)
    return re.findall(r'"([a-z_0-9]+)"', listed.group(1))


@pytest.fixture()
def company(db):
    from app.models import IrCompany

    row = IrCompany(name="샘플가나랩", sector_major="헬스케어", sector_minor="의료AI",
                    series="Seed", revenue_2022="1억", revenue_2023="2억",
                    revenue_2024="3억", revenue_2025="4억", revenue_2026="5억",
                    revenue_recent="6.5", funding_total="10", raise_target="5-10억 사이",
                    pre_value="~")
    db.add(row)
    db.commit()
    return row


# --- 1. 보이는 해 ----------------------------------------------------------------

def test_지난_세_해와_올해_최근_매출액이다():
    from app.services import revenue_years as ry

    assert ry.shown(2026) == [("revenue_2023", "23"), ("revenue_2024", "24"),
                               ("revenue_2025", "25")]
    assert ry.recent_label(2026) == "최근 매출액(26년)"
    assert ry.shown(2027) == [("revenue_2024", "24"), ("revenue_2025", "25"),
                               ("revenue_2026", "26")]
    assert ry.recent_label(2027) == "최근 매출액(27년)"
    # 칸을 안 판 해는 건너뛴다 — 판이 늦어도 화면은 안 죽는다.
    assert [f for f, _ in ry.shown(2033)] == ["revenue_2030"]


@pytest.mark.parametrize("day, years, gone", [
    (Y2026, ("23", "24", "25"), "22"),
    (Y2027, ("24", "25", "26"), "23"),
])
def test_두_탭과_창에_올해_기준_해가_선다(logged_in, company, at, day, years, gone):
    at(day)
    label = f"최근 매출액({day.year % 100}년)"
    db_tab = logged_in.get("/companies?tab=db").text
    heads = _heads(db_tab)
    assert [h for h in heads if h.endswith("년 매출")] == [f"{y}년 매출" for y in years]
    assert label in heads and "최근 매출액" not in heads
    # 숨긴 해는 표에서만 빠진다 — 창에도 안 서고(보내지 않으니 안 지워진다) 값은 남는다.
    status = logged_in.get("/companies").text
    for html in (db_tab, status):
        ids = _panel_ids(html)
        assert [i for i in ids if re.fullmatch(r"revenue_\d{4}", i)] == \
            [f"revenue_20{y}" for y in years]
        assert f"<span>{label}</span>" in html, "창의 이름이 표 머리글과 다릅니다"
        assert f'data-field="revenue_20{gone}"' not in html
    assert logged_in.get(f"/api/companies/{company.id}").json()[f"revenue_20{gone}"]


@pytest.mark.parametrize("day", [Y2026, Y2027])
def test_IR_탭은_소분류_바로_뒤에_매출_금액이_선다(logged_in, company, at, day):
    from app.services import revenue_years as ry

    at(day)
    html = logged_in.get("/companies").text
    heads, fields = _heads(html), _first_row_fields(html)
    assert len(heads) == len(fields), "머리글과 칸 수가 다릅니다 — 뒤 칸이 한 칸씩 밀립니다"
    block = ry.columns(day.year)
    at_minor = heads.index("소분류")
    assert heads[at_minor + 1:at_minor + 1 + len(block)] == [h for _f, h in block]
    assert heads[at_minor + 1 + len(block)] == "투자라운드"
    # 칸도 같은 자리 — 눌러 고치면 그 머리글의 칸이 저장된다.
    assert fields[at_minor] == "sector_minor"
    assert fields[at_minor + 1:at_minor + 1 + len(block)] == [f for f, _h in block]
    if day == Y2026:
        assert [h for _f, h in block] == [
            "23년 매출", "24년 매출", "25년 매출", "최근 매출액(26년)",
            "누적투자금액", "투자유치희망금액", "Pre Value"]


def test_IR_탭에서_고친_값이_스타트업DB_탭에_보인다(logged_in, company, at):
    at(Y2026)
    status = logged_in.get("/companies").text
    assert 'data-field="revenue_2024"' in status and 'data-field="pre_value"' in status
    # 표의 칸을 누르면 inline_edit.js 가 이 PATCH 를 보낸다(`data-inline-url`).
    r = logged_in.patch(f"/api/companies/{company.id}",
                        json={"revenue_2024": "1,224백만원", "pre_value": "120억"})
    assert r.status_code == 200, r.text
    db_tab = logged_in.get("/companies?tab=db").text
    assert "1,224백만원" in db_tab and "120억" in db_tab


def test_화면_그대로_엑셀에도_같은_자리에_선다(logged_in, company, at):
    import openpyxl

    from app.services import revenue_years as ry

    at(Y2027)
    resp = logged_in.get("/api/export/companies-view.xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(resp.content)).active
    head, row = [[c.value for c in r] for r in ws.iter_rows(max_row=2)]
    block = ry.columns(2027)
    at_minor = head.index("소분류")
    assert head[at_minor + 1:at_minor + 1 + len(block)] == [h for _f, h in block]
    # 숫자로만 적힌 글자는 파일에서 수로 선다(`_xlsx` — 엑셀에서 더할 수 있게).
    assert row[at_minor + 1:at_minor + 1 + len(block)] == [
        "3억", "4억", "5억", 6.5, 10, "5-10억 사이", "~"]


def test_한줄_소개는_보이는_세_해만_싣는다(at):
    from types import SimpleNamespace

    from app.services.one_liner import compose_one_liner

    fields = {f: None for f in ("business_desc", "funding_total", "raise_target",
                                "pre_value", "competitiveness")}
    company = SimpleNamespace(**fields, one_liner=None, revenue_2022="1억", revenue_2023="2억",
                              revenue_2024="3억", revenue_2025="4억", revenue_2026="5억")
    at(Y2026)
    assert compose_one_liner(company) == "매출 23년 2억, 24년 3억, 25년 4억"
    at(Y2027)
    assert compose_one_liner(company) == "매출 24년 3억, 25년 4억, 26년 5억"


# --- 3. 해가 바뀌면 ----------------------------------------------------------------

def test_새해_첫_화면이_빈_지난해_칸에만_최근_매출액을_옮겨_적는다(logged_in, db, users, at):
    from app.models import EditLog, IrCompany

    empty = IrCompany(name="샘플빈칸랩", revenue_recent="18.3")
    kept = IrCompany(name="샘플적힌랩", revenue_recent="9", revenue_2026="7억")
    none = IrCompany(name="샘플없음랩")
    loose = IrCompany(name="샘플구간랩", revenue_recent="5-10억 사이", revenue_2026="  ")
    db.add_all([empty, kept, none, loose])
    db.commit()

    at(Y2027)
    assert logged_in.get("/companies").status_code == 200
    db.expire_all()
    # 단위를 붙여 옮긴다 — 연도 칸은 적힌 그대로 읽는 글자라 `18.3` 만 두면 단위가 없다.
    assert empty.revenue_2026 == "18.3억"
    assert loose.revenue_2026 == "5~10억"
    assert kept.revenue_2026 == "7억", "적힌 값을 덮었습니다"
    assert none.revenue_2026 is None
    # `최근 매출액` 은 그대로 — 새 값이 들어올 때까지 가장 최근 값이다.
    assert empty.revenue_recent == "18.3" and kept.revenue_recent == "9"

    # 수정 로그 — 화면을 연 사람 이름으로, 옮긴 줄만.
    logs = db.query(EditLog).filter(EditLog.table_name == "ir_companies").all()
    assert sorted(log.row_label for log in logs) == ["샘플구간랩", "샘플빈칸랩"]
    assert {log.actor_user_id for log in logs} == {users["u1"].id}
    assert all("revenue_2026" in log.changes_json for log in logs)

    # 해마다 **한 번**이다 — 사람이 일부러 비운 칸을 다음 화면이 다시 채우지 않는다.
    assert logged_in.patch(f"/api/companies/{empty.id}",
                           json={"revenue_2026": ""}).status_code == 200
    logged_in.get("/companies")
    db.expire_all()
    assert empty.revenue_2026 is None


def test_2026년에는_옮기지_않는다(logged_in, db, at):
    """`최근 매출액` 은 처음부터 26년 자리였다 — 25년 칸에 옮기면 틀린 해에 적힌다."""
    from app.models import IrCompany

    row = IrCompany(name="샘플올해랩", revenue_recent="18.3")
    db.add(row)
    db.commit()
    at(Y2026)
    logged_in.get("/companies")
    db.expire_all()
    assert row.revenue_2025 is None


def test_옮겨_적기는_직접_불러도_해마다_한_번이다(db, users):
    from app.models import IrCompany
    from app.services import revenue_years as ry

    row = IrCompany(name="샘플두번랩", revenue_recent="3")
    db.add(row)
    db.commit()
    assert ry.roll_over(db, users["u1"].id, 2027) == 1
    row.revenue_2026 = None
    db.commit()
    assert ry.roll_over(db, users["u1"].id, 2027) == 0
    assert ry.roll_over(db, users["u1"].id, 2028) == 1   # 다음 해는 다시
    db.refresh(row)
    assert row.revenue_2027 == "3억" and row.revenue_2026 is None


# --- 5. 칸을 더 팔 때 ---------------------------------------------------------------

def test_파_둔_해는_저장_길과_창_목록에_다_있다():
    """2032년 전에 `revenue_2031` 판을 더할 때 — 여기서 빠진 곳을 잡는다."""
    from app.routers.companies import CompanyIn
    from app.services import revenue_years as ry

    assert ry.FIELDS == [f"revenue_{y}" for y in range(2022, 2031)]
    assert not set(ry.FIELDS) - set(CompanyIn.model_fields), "PATCH 가 그 해를 버립니다"
    assert not set(ry.FIELDS) - set(_script_fields()), "창이 그 해를 저장하지 않습니다"


@pytest.mark.parametrize("day", [Y2026, Y2027])
def test_창에_선_칸은_모두_저장_목록에_있다(logged_in, company, at, day):
    """창은 [저장] 한 번에 `FIELDS` 를 보낸다 — 창에 서고 목록에 없으면 조용히 저장이 안 된다."""
    at(day)
    for url in ("/companies", "/companies?tab=db"):
        missing = set(_panel_ids(logged_in.get(url).text)) - set(_script_fields())
        assert missing <= {"is_top_deal", "desc_backup"}, missing
