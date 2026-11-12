"""업무 보고 › 이 달의 반응 › `IR 요청 투자사` 표의 상태 칸 — `IR 자료 전달 완료` 오른쪽에
**전달한 날짜·시각**이 저절로 붙는다.

팀 요청(11/12): "업무보고 > 상태 컬럼에 IR 전달 완료 우측에 년월일시 자동으로 들어가게".

날짜(`ir_requests.delivered_at`)는 전부터 적혀 있었고 시각은 어디에도 없었다. 시각은
0137 부터 `delivered_time`(`HH:MM`)에 적는다 — 미팅의 `scheduled_at` · `scheduled_time`
과 같은 짝이다. 그 전에 전달된 줄은 시각을 모르므로 **날짜만** 보인다(지어내지 않는다).

  1. 판(0137) 오르내리기 — 옛 줄은 빈 칸
  2. 전달하는 순간 시각이 적힌다(단추 · 발송기 보고가 함께 지나는 `pipeline.deliver`)
     — 지난 날짜를 넘겨받은 길은 그날 몇 시였는지 모르므로 비운다
  3. 화면: `IR 자료 전달 완료 · 2026-…-… 14:05` · 옛 줄은 날짜만 · 다른 상태는 그대로
  4. 엑셀 `이 달의 반응` 시트도 같은 글자

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import io
import re
import sqlite3
from datetime import date, datetime, time, timedelta

import pytest

from .conftest import DEMO_PASSWORD
from .test_migrations import _alembic

LABEL = "IR 자료 전달 완료"


@pytest.fixture()
def logged(client, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _contact(db, users, name):
    from app.models import SheetOwner, VcContact

    if db.query(SheetOwner).filter_by(label="내 명단").first() is None:
        db.add(SheetOwner(label="내 명단", user_id=users["u1"].id))
    row = VcContact(user_id=users["u1"].id, name=name, title="심사역", firm="가나벤처스",
                    source_sheet="내 명단", channel_kakao=1, connect_stage="connected",
                    kakao_room_name=f"{name} 심사역님")
    db.add(row)
    db.commit()
    return row


def _request(db, users, contact, company, *, when, status="delivered", at=None):
    from app.models import IrRequest

    row = IrRequest(user_id=users["u1"].id, contact_id=contact.id, company_name=company,
                    requested_at=when.isoformat(), status=status,
                    delivered_at=when.isoformat() if status in ("delivered", "lost") else None,
                    delivered_time=at)
    db.add(row)
    db.commit()
    return row


def _month() -> date:
    """확실히 지난 달의 어느 날 — 그 달 보고를 연다."""
    return date.today().replace(day=1) - timedelta(days=45)


def _ir_rows(html: str) -> list:
    """`이 달의 반응` › `IR 요청 투자사` 갈래의 `<tr>` 들."""
    hit = re.search(r'bucket-head"[^>]*>\s*IR 요청 투자사', html)
    assert hit, "갈래를 못 찾았다"
    chunk = html[hit.end():]
    chunk = chunk[:chunk.find("bucket-head")] if "bucket-head" in chunk else chunk
    body = chunk[chunk.index("<tbody>"):chunk.index("</tbody>")]
    return [re.sub(r"\s+", " ", r) for r in re.findall(r"<tr[^>]*>.*?</tr>", body, flags=re.S)]


def _report(logged, when) -> str:
    return logged.get(f"/report?month={when.year}-{when.month:02d}").text


def _sheet_cells(logged, when) -> list:
    import openpyxl

    resp = logged.get(f"/api/export/report.xlsx?month={when.year}-{when.month:02d}")
    assert resp.status_code == 200, resp.status_code
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb[[s for s in wb.sheetnames if "반응" in s][0]]
    return [str(c.value) for row in ws.iter_rows() for c in row if c.value]


# ── 1) 판 ───────────────────────────────────────────────────────────────────

def _cols(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("ir_requests")')}
    finally:
        con.close()


def test_0137_은_빈_칸을_붙이고_되돌리면_뗀다(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", "0136_no_reaction_cleared").returncode == 0
    # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE ir_requests DROP COLUMN delivered_time")
        con.execute("INSERT INTO ir_requests (user_id, contact_id, company_name, requested_at,"
                    " status, delivered_at, created_at, updated_at)"
                    " VALUES (1, 1, '샘플가', '2026-10-01', 'delivered', '2026-10-02', 'x', 'x')")
        con.commit()
    finally:
        con.close()

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    con = sqlite3.connect(db)
    try:
        # 옛 줄은 시각을 모른다 — 비운 채로 둔다.
        assert con.execute("SELECT delivered_at, delivered_time FROM ir_requests").fetchall() \
            == [("2026-10-02", None)]
    finally:
        con.close()

    down = _alembic(db, "downgrade", "0136_no_reaction_cleared")
    assert down.returncode == 0, down.stdout + down.stderr
    assert "delivered_time" not in _cols(db)


# ── 2) 전달하는 순간 시각이 적힌다 ────────────────────────────────────────────

def test_지금_전달하면_날짜와_시각이_함께_적힌다(db, users, monkeypatch):
    from app import clock
    from app.services import pipeline

    today = date.today()
    monkeypatch.setattr(clock, "now",
                        lambda: datetime.combine(today, time(14, 5, 41)).astimezone())
    row = _request(db, users, _contact(db, users, "가담당"), "샘플애그",
                   when=today, status="open")
    pipeline.deliver(db, row)
    assert (row.status, row.delivered_at, row.delivered_time) == \
        ("delivered", today.isoformat(), "14:05")


def test_지난_날짜를_넘겨받으면_시각은_비운다(db, users):
    """그날 몇 시였는지 모른다 — `00:00` 이나 지금 시각을 붙이면 지어낸 값이 된다."""
    from app.services import pipeline

    past = date.today() - timedelta(days=3)
    row = _request(db, users, _contact(db, users, "가담당"), "샘플애그",
                   when=past, status="open")
    pipeline.deliver(db, row, past)
    assert (row.delivered_at, row.delivered_time) == (past.isoformat(), None)


def test_단추로_전달하면_업무_보고에_시각까지_붙는다(db, users, logged):
    """[IR 자료 전달 완료] 단추 → 같은 달 업무 보고의 상태 칸."""
    today = date.today()
    row = _request(db, users, _contact(db, users, "가담당"), "샘플애그",
                   when=today, status="open")
    resp = logged.post(f"/ir/requests/{row.id}/deliver", follow_redirects=False)
    assert resp.status_code == 303, resp.status_code
    db.refresh(row)
    assert re.fullmatch(r"\d\d:\d\d", row.delivered_time or ""), row.delivered_time

    rows = _ir_rows(_report(logged, today))
    assert f"{LABEL} · {today.isoformat()} {row.delivered_time}" in rows[0], rows[0]


# ── 3) 화면 ─────────────────────────────────────────────────────────────────

def test_상태_칸_전달_완료_오른쪽에_날짜와_시각이_붙는다(db, users, logged):
    when = _month()
    _request(db, users, _contact(db, users, "가담당"), "샘플애그", when=when, at="14:05")
    rows = _ir_rows(_report(logged, when))
    assert len(rows) == 1, rows
    assert f"{LABEL} · {when.isoformat()} 14:05" in rows[0], rows[0]


def test_시각이_없는_옛_줄은_날짜만_붙는다(db, users, logged):
    when = _month()
    _request(db, users, _contact(db, users, "가담당"), "샘플애그", when=when)
    rows = _ir_rows(_report(logged, when))
    assert f"{LABEL} · {when.isoformat()}" in rows[0], rows[0]
    assert not re.search(re.escape(f"{LABEL} · {when.isoformat()}") + r" \d\d:\d\d", rows[0])


def test_전달_완료가_아닌_줄은_그대로다(db, users):
    from app.services import report as report_svc

    when = _month()
    _request(db, users, _contact(db, users, "가담당"), "샘플애그", when=when, status="open")
    _request(db, users, _contact(db, users, "나담당"), "샘플메디", when=when,
             status="lost", at="10:00")
    data = report_svc.monthly(db, when.year, when.month, users["u1"])
    notes = sorted(r["note"] for b in data["buckets"] if b["key"] == "ir" for r in b["rows"])
    assert notes == ["IR 자료 요청 받음", "드랍"], notes


# ── 4) 엑셀 ─────────────────────────────────────────────────────────────────

def test_엑셀_상태_칸에도_같은_글자가_실린다(db, users, logged):
    from app.services import report as report_svc

    when = _month()
    _request(db, users, _contact(db, users, "가담당"), "샘플애그", when=when, at="09:30")
    _request(db, users, _contact(db, users, "나담당"), "샘플메디", when=when)

    data = report_svc.monthly(db, when.year, when.month, users["u1"])
    said = [r["note"] for b in data["buckets"] if b["key"] == "ir" for r in b["rows"]]
    assert f"{LABEL} · {when.isoformat()} 09:30" in said
    assert f"{LABEL} · {when.isoformat()}" in said

    cells = _sheet_cells(logged, when)
    html = _report(logged, when)
    for text in said:
        # 엑셀은 상태 아래에 미팅 요청 한 줄을 더 잇는다 — 첫 줄이 화면 글자와 같다.
        assert any(c.split("\n")[0] == text for c in cells), (text, cells)
        assert text in html, text
