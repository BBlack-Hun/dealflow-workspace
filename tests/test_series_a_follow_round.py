"""#98 `Series A 이상 딜 소싱` 탭 — `수신일` 오른쪽 `후속라운드 시작`(0127).

요청: "수신일 오른쪽에 후속라운드시작 컬럼 추가". 꼴은 매출예상리스트 `예상 시기` 와
같은 `YYYY-MM` 이다(`forecast.month` — `2027.3` 도 받아 맞춘다). 값은 지어낸 것이다.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from .test_migrations import _alembic


@pytest.fixture()
def deal(db):
    from app.models import SeriesACompany

    row = SeriesACompany(name="샘플애그", received_at="2026-07-01")
    db.add(row)
    db.commit()
    return row


def test_수신일_바로_오른쪽에_선다(logged_in, deal):
    html = logged_in.get("/companies?tab=series-a").text
    thead = re.search(r'id="sa-table".*?</thead>', html, re.S).group(0)
    labels = [re.sub(r"<[^>]+>", "", t).strip()
              for t in re.findall(r"<th\b[^>]*>(.*?)</th>", thead, re.S)]
    assert labels[labels.index("수신일") + 1] == "후속라운드 시작", labels
    row = re.search(r"<tr data-id=.*?</tr>", html, re.S).group(0)
    fields = re.findall(r'data-field="([^"]+)"', row)
    assert fields[fields.index("received_at") + 1] == "follow_round_month", fields


def test_YYYY_MM_으로_맞춰_저장하고_못_읽으면_400(logged_in, deal, db):
    from app.models import SeriesACompany

    url = f"/api/series-a-companies/{deal.id}"
    data = logged_in.patch(url, json={"follow_round_month": "2027.3"}).json()
    assert data["follow_round_month"] == "2027-03"
    assert "2027-03" in data["search"]

    bad = logged_in.patch(url, json={"follow_round_month": "내년 상반기"})
    assert bad.status_code == 400 and "YYYY-MM" in bad.json()["detail"]
    db.expire_all()
    assert db.get(SeriesACompany, deal.id).follow_round_month == "2027-03"

    assert logged_in.patch(url, json={"follow_round_month": " "}).json()["follow_round_month"] == ""
    db.expire_all()
    assert db.get(SeriesACompany, deal.id).follow_round_month is None


def _cols(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("series_a_companies")')}
    finally:
        con.close()


def test_0127_은_칸을_붙이고_되돌리면_뗀다(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", "0126_startup_send_day_wording").returncode == 0
    # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE series_a_companies DROP COLUMN follow_round_month")
        con.commit()
    finally:
        con.close()
    assert "follow_round_month" not in _cols(db)

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert "follow_round_month" in _cols(db)

    down = _alembic(db, "downgrade", "0126_startup_send_day_wording")
    assert down.returncode == 0, down.stdout + down.stderr
    assert "follow_round_month" not in _cols(db)
