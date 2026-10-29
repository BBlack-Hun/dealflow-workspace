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
from datetime import date

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
    assert "8월 소개한 기업" in page.text and "샘플애그" in page.text
    # 팀원은 `팀 전체` 를 달아도 제 것만 본다 — 남의 명단이 받은 샘플메디가 없다.
    assert "샘플메디" not in logged.get("/report?month=2026-08&scope=team").text

    assert "이 기간에 소개한 기업이 없습니다" in logged.get("/report?month=2026-10").text

    year = logged.get("/report?span=year&year=2026")
    assert year.status_code == 200
    assert "2026년 소개한 기업" in year.text


def _grid(ws):
    return [[("" if c is None else c) for c in row]
            for row in ws.iter_rows(values_only=True)]


def test_excel_gets_two_intro_sheets(logged, db, users):
    _mine_history(db, users)

    r = logged.get("/api/export/report.xlsx?span=year&year=2026")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[-2:] == ["2026 소개한 기업", "2026 소개 상세"]

    summary = _grid(wb["2026 소개한 기업"])
    assert ["기업명", "소개한 횟수", "받은 투자사 수", "처음 날짜", "마지막 날짜"] in summary
    assert ["샘플애그", 3, 3, "2026-08-10", "2026-09-01"] in summary

    detail = _grid(wb["2026 소개 상세"])
    assert ["날짜", "기업", "투자사 회사", "투자사 이름", "출처"] in detail
    lines = [row for row in detail if row[1] == "샘플애그"]
    assert sorted(row[4] for row in lines) == ["손으로 적음", "시트", "앱 발송"]

    month = openpyxl.load_workbook(io.BytesIO(
        logged.get("/api/export/report.xlsx?month=2026-10").content))
    assert month.sheetnames[-2:] == ["2026-10 소개한 기업", "2026-10 소개 상세"]
    flat = [str(c) for row in _grid(month["2026-10 소개한 기업"]) for c in row]
    assert "이 기간에 소개한 기업이 없습니다." in flat
