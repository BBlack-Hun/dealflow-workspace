"""업무 보고 — `소개한 기업`(#92 팀원 요청: 월별·연별로 기업별로 묶어 보기).

세는 기준은 딜 제안 관리의 `내 투자사 N/M` 과 같다(`deal_history.scan`).
여기서 못 박는 것:

1. 기간 — 받은 날이 그 달·그 해에 든 것만.
2. 사람 — 내 것은 내 것만(시트·손 기록은 지금 담당, 앱 발송은 누른 계정), 팀 전체는 모두.
3. 안 나간 앱 발송(실패·취소)은 안 센다.
4. 세 출처(시트 · 손으로 적음 · 앱 발송)를 모두 센다.
5. 엑셀에 `소개한 기업` · `소개 상세` 두 장이 붙는다.
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import pytest

from .conftest import DEMO_PASSWORD
from .test_deal_history import _mine_history

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _rows(got):
    return {c["company"]: c for c in got["rows"]}


def test_year_counts_every_source_but_not_failed_sends(db, users):
    from app.services import report

    _mine_history(db, users)
    got = report.intro_companies(db, date(2026, 1, 1), date(2026, 12, 31),
                                 users["u1"])
    rows = _rows(got)
    # 샘플메디는 남의 명단이 받았고(시트) 내 앱 발송은 실패·취소라 내 표에 없다.
    assert list(rows) == ["샘플애그"]
    agg = rows["샘플애그"]
    assert (agg["times"], agg["investors"], agg["first"], agg["last"]) == \
        (3, 3, "2026-08-10", "2026-09-01")
    assert [d["day"] for d in agg["rows"]] == ["2026-09-01", "2026-08-15", "2026-08-10"]
    assert [d["source"] for d in agg["rows"]] == ["앱 발송", "손으로 적음", "시트"]
    assert got["details"] == 3


def test_month_cuts_by_received_day(db, users):
    from app.services import report

    _mine_history(db, users)
    aug = report.monthly(db, 2026, 8, users["u1"], today=date(2026, 10, 29))
    assert [(c["company"], c["times"]) for c in aug["intro_companies"]["rows"]] == \
        [("샘플애그", 2)]
    sep = report.monthly(db, 2026, 9, users["u1"], today=date(2026, 10, 29))
    assert [(c["company"], c["times"], c["first"]) for c in
            sep["intro_companies"]["rows"]] == [("샘플애그", 1, "2026-09-01")]
    oct_ = report.monthly(db, 2026, 10, users["u1"], today=date(2026, 10, 29))
    assert oct_["intro_companies"] == {"rows": [], "details": 0}


def test_team_takes_everyone_and_sorts_by_last_day(db, users):
    from app.services import report

    _mine_history(db, users)
    team = report.yearly(db, 2026, None, date(2026, 10, 29))["intro_companies"]
    # 마지막 날 최신순. 샘플메디의 09-05 앱 발송은 실패라 마지막 날이 08-20 이다.
    assert [(c["company"], c["last"]) for c in team["rows"]] == \
        [("샘플애그", "2026-09-01"), ("샘플메디", "2026-08-20")]
    # 남의 명단도 팀 전체에는 든다 — 그 사람 것으로.
    other = report.intro_companies(db, date(2026, 1, 1), date(2026, 12, 31),
                                   users["u2"])
    assert [c["company"] for c in other["rows"]] == ["샘플메디"]


def test_app_send_belongs_to_who_pressed(db, users):
    """앱 발송은 **누른 계정** 것이다 — 받은 투자사의 담당이 누구든."""
    from app.models import (DealBatch, DealBatchCompany, IrCompany, SendItem,
                            SendJob, VcContact)
    from app.services import report

    company = IrCompany(name="샘플바이오")
    contact = VcContact(user_id=users["u1"].id, name="가상갑", firm="가나벤처스")
    batch = DealBatch(user_id=users["u2"].id, title="회차", sent_date="2026-10-07")
    db.add_all([company, contact, batch])
    db.flush()
    db.add(DealBatchCompany(batch_id=batch.id, company_id=company.id, position=1))
    job = SendJob(user_id=users["u2"].id, kind="deal_intro", batch_id=batch.id)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=contact.id, room_name="방",
                    message="본문", status="sent"))
    db.commit()

    start, end = date(2026, 10, 1), date(2026, 10, 31)
    assert report.intro_companies(db, start, end, users["u1"])["rows"] == []
    assert [c["company"] for c in
            report.intro_companies(db, start, end, users["u2"])["rows"]] == ["샘플바이오"]


def test_report_page_shows_the_table(logged, db, users):
    _mine_history(db, users)

    page = logged.get("/report?month=2026-08")
    assert page.status_code == 200
    assert "8월 딜소개 한 기업" in page.text and "샘플애그" in page.text
    # 팀원은 `팀 전체` 를 달아도 제 것만 본다 — 남의 명단이 받은 샘플메디가 `소개한 기업` 에 없다
    # (내가 안 보낸 기업이라 아래 `소개 후보` 에는 선다 — #174).
    assert "<summary><b>샘플메디</b></summary>" not in \
        logged.get("/report?month=2026-08&scope=team").text

    assert "이 기간에 소개한 기업이 없습니다" in logged.get("/report?month=2026-10").text

    year = logged.get("/report?span=year&year=2026")
    assert year.status_code == 200
    assert "2026년 딜소개 한 기업" in year.text


def _grid(ws):
    return [[("" if c is None else c) for c in row]
            for row in ws.iter_rows(values_only=True)]


def test_excel_gets_two_intro_sheets(logged, db, users):
    _mine_history(db, users)

    r = logged.get("/api/export/report.xlsx?span=year&year=2026")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[-2:] == ["2026 딜소개 한 기업", "2026 소개 상세"]

    summary = _grid(wb["2026 딜소개 한 기업"])
    # 기업명 바로 오른쪽 소개한 횟수(#165 — 본인 보기라 `본인 소개 횟수`) · 그 옆
    # `투자유치희망금액`(#118) · 계약여부 · 계약서 수신 여부(#122) —
    # 샘플애그는 금액 · 계약서 수신을 안 적어 빈칸이고 계약여부는 기본 `미계약` 이다.
    assert ["기업명", "본인 소개 횟수", "투자유치희망금액", "계약여부", "계약서 수신 여부",
            "받은 투자사 수", "처음 날짜", "마지막 날짜"] in summary
    assert ["샘플애그", 3, "", "미계약", "", 3, "2026-08-10", "2026-09-01"] in summary

    detail = _grid(wb["2026 소개 상세"])
    assert ["날짜", "기업", "투자사 회사", "투자사 이름", "출처"] in detail
    lines = [row for row in detail if row[1] == "샘플애그"]
    assert sorted(row[4] for row in lines) == ["손으로 적음", "시트", "앱 발송"]

    month = openpyxl.load_workbook(io.BytesIO(
        logged.get("/api/export/report.xlsx?month=2026-10").content))
    assert month.sheetnames[-2:] == ["2026-10 딜소개 한 기업", "2026-10 소개 상세"]
    flat = [str(c) for row in _grid(month["2026-10 딜소개 한 기업"]) for c in row]
    assert "이 기간에 소개한 기업이 없습니다." in flat


# --- 펼친 투자사 표가 기업명 칸에서 안 잘린다(11/05) ------------------------------
#
# 기업명 칸만 폭이 없어 나머지 칸을 뺀 자투리를 받는다. 1280px 화면에서 190px 남짓 —
# 그 칸 안에서 펼친 투자사 표(NO·날짜·출처 고정폭)가 넘쳐 `td { overflow: hidden }` 에
# 잘렸다. 표에 `min-width` 를 못 박아 모자라면 `.table-wrap` 이 가로로 굴리게 했다.

_ROOT = Path(__file__).resolve().parents[1]
_INTROS_HTML = _ROOT / "app/templates/_report_intros.html"
_CSS = _ROOT / "app/static/css/app.css"
_SEL = r"#intros\s*>\s*\.table-wrap\s*>\s*\.grid-table"   # app.css 가 이 표를 잡는 선택자
_NO_COL = 36        # 줄 앞 `NO` 칸(`tr::before`) — 바깥 표에도 안쪽 표에도 선다
_TD_PAD = 16        # `.grid-table.compact td` 좌우 여백 8px × 2
_INVESTOR_MIN = 80  # 안쪽 표의 `투자사`(이름 + 회사) 칸이 이만큼은 남아야 읽힌다


def _th_widths(html: str) -> list:
    return [int(w) if w else 0 for w in
            re.findall(r"<th\b[^>]*?(?:width:\s*(\d+)px[^>]*)?>", html)]


def _intro_heads():
    """(바깥 표 머리글 폭들, 펼친 안쪽 표 머리글 폭들)."""
    html = _INTROS_HTML.read_text(encoding="utf-8")
    start = html.index("<table", html.index('id="intros"'))
    outer_head = html[start:html.index("</thead>", start)]
    inner_at = html.index("<details>", start)
    inner_head = html[inner_at:html.index("</thead>", inner_at)]
    return _th_widths(outer_head), _th_widths(inner_head)


def test_펼친_투자사_표가_기업명_칸에_들어간다():
    outer, inner = _intro_heads()
    assert outer[0] == 0, "기업명 칸은 폭 없이 남는 자리를 받는 칸이다"
    css = re.sub(r"/\*.*?\*/", "", _CSS.read_text(encoding="utf-8"), flags=re.S)
    hit = re.search(_SEL + r"\s*\{[^}]*min-width:\s*(\d+)px", css)
    assert hit, "소개한 기업 표에 min-width 가 없다 — 좁은 화면에서 기업명 칸이 0px 로 눌린다"
    company_col = int(hit.group(1)) - sum(outer) - _NO_COL
    investor_col = company_col - _TD_PAD - sum(inner) - _NO_COL
    assert investor_col >= _INVESTOR_MIN, (
        f"min-width {hit.group(1)}px — 펼친 표의 투자사 칸이 {investor_col}px 뿐이다")
    # 안쪽 표도 `.table-wrap` 안이라 폰 규칙(760px)을 받는다 — 빼 주지 않으면 칸 밖으로 잘린다.
    assert re.search(_SEL + r"\s+\.grid-table\s*\{[^}]*min-width:\s*0", css), \
        "펼친 안쪽 표가 폰 규칙의 min-width 760px 를 그대로 받는다"


def test_폭_규칙이_잡는_자리에_펼치는_표가_있다(logged, db, users):
    """CSS 가 `#intros > .table-wrap > .grid-table` 로 잡는다 — 화면의 짜임이 달라지면
    규칙은 소리 없이 논다. 그 자리에 기업명을 펼치는 표가 서는지 본다."""
    _mine_history(db, users)
    page = logged.get("/report?month=2026-08").text
    m = re.search(r'id="intros">.*?</h2>\s*<div class="table-wrap">\s*'
                  r'<table class="grid-table\b(.*?)</section>', page, re.S)
    assert m, "소개한 기업 표가 `#intros > .table-wrap >` 바로 아래에 없다"
    assert "<details>" in m.group(1) and "샘플애그" in m.group(1)
