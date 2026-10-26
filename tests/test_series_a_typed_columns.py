"""`Series A 이상 딜 소싱` 탭 — 직접 적는 칸(개선 과제 #24 · 0112).

사용자 요청: "대표자명 · 핸드폰 · 이메일 · 24~27년 매출 · 누적투자금액 ·
투자유치희망금액 · 프리밸류 · 딜소개문구 컬럼 추가". 결정: **이 탭에서 사람이 적는다.**
`딜소개 문구` 는 이미 있는 칸이다. 10/26 부터 IR 기업에 이어진 줄은 그 기업의 같은
칸과 따라 고친다(기업 동기화 3단계 — tests/test_series_a_ir_sync.py).

값은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from .test_migrations import _alembic

ROOT = Path(__file__).resolve().parent.parent

# 이름은 스타트업DB 의 같은 칸 그대로다(#63 — 처음 요청은 `핸드폰` · `프리밸류`).
LABELS = ["대표자명", "연락처", "이메일", "24년 매출", "25년 매출", "26년 매출",
          "27년 매출", "누적투자금액", "투자유치희망금액", "Pre Value"]


@pytest.fixture()
def deal(db):
    from app.models import SeriesACompany

    row = SeriesACompany(name="샘플애그", received_at="2026-07-01",
                         series="Series A", detail="스마트팜 관제")
    db.add(row)
    db.commit()
    return row


def _head(html: str) -> list:
    thead = re.search(r'id="sa-table".*?</thead>', html, re.S).group(0)
    return [(attrs, re.sub(r"<[^>]+>", "", text).strip())
            for attrs, text in re.findall(r"<th\b([^>]*)>(.*?)</th>", thead, re.S)]


def test_칸이_투자라운드_뒤_상세_내용_앞에_요청_차례로_선다(logged_in, deal):
    from app.routers.series_a import TYPED

    html = logged_in.get("/companies?tab=series-a").text
    labels = [label for _a, label in _head(html)]
    at = labels.index("투자라운드")
    assert labels[at + 1:at + 1 + len(LABELS)] == LABELS, labels
    assert labels[at + 1 + len(LABELS)] == "상세 내용"
    # 줄마다 눌러 고치는 칸이 같은 차례로 선다(`inline_edit.js` 의 `.cell`).
    row = re.search(r"<tr data-id=.*?</tr>", html, re.S).group(0)
    fields = re.findall(r'class="cell[^"]*" data-field="([^"]+)"', row)
    at = fields.index("series")
    assert fields[at + 1:at + 1 + len(TYPED)] == list(TYPED), fields


def test_표_폭이_칸_폭_합보다_넓다(logged_in, deal):
    """`table-layout: fixed` 에서 폭 합이 표 폭을 넘으면 폭을 안 준 `상세 내용` 이
    0 으로 짜부라진다(`app.css` 머리말). 칸을 더한 만큼 `#sa-table` 을 올렸는지."""
    html = logged_in.get("/companies?tab=series-a").text
    total = sum(int(w) for attrs, _l in _head(html)
                for w in re.findall(r"width:(\d+)px", attrs))
    css = (ROOT / "app" / "static" / "css" / "app.css").read_text("utf-8")
    table = int(re.search(r"#sa-table \{ min-width: (\d+)px; \}", css).group(1))
    # 남는 자리(`상세 내용`)가 공통 값(2,030px)일 때 만큼은 된다.
    assert table - total >= 2030 - 1582, (table, total)


def test_적은_그대로_저장되고_응답과_검색에_실린다(logged_in, deal, db):
    from app.models import SeriesACompany

    sent = {"ceo_name": " 홍길동 ", "ceo_phone": "010-1000-0001",
            "ceo_email": "ceo@example.com", "revenue_2024": "8.2",
            "revenue_2025": "12억", "revenue_2026": "5-10억", "revenue_2027": "~",
            "funding_total": "18.3", "raise_target": "30", "pre_value": "150억 ~ 200억"}
    res = logged_in.patch(f"/api/series-a-companies/{deal.id}", json=sent)
    assert res.status_code == 200, res.text
    data = res.json()
    for field, value in sent.items():
        assert data[field] == value.strip(), field
    assert "홍길동" in data["search"] and "010-1000-0001" in data["search"]

    db.expire_all()
    row = db.get(SeriesACompany, deal.id)
    assert (row.ceo_name, row.revenue_2026, row.pre_value) == ("홍길동", "5-10억", "150억 ~ 200억")
    html = logged_in.get("/companies?tab=series-a").text
    assert 'data-field="ceo_email" title="ceo@example.com">ceo@example.com</td>' in html

    # 비우면 지운다.
    assert logged_in.patch(f"/api/series-a-companies/{deal.id}",
                           json={"ceo_phone": "  "}).json()["ceo_phone"] == ""
    db.expire_all()
    assert db.get(SeriesACompany, deal.id).ceo_phone is None


def test_안_이어진_줄은_IR에서_옮겨_오지_않고_시트_가져오기도_안_건드린다(logged_in, deal, db):
    """이 칸은 사람이 적는다. IR 기업에 **안 이어진** 줄(사람이 [연결 풀기]한 줄)은 같은
    이름의 IR 기업이 있어도 비어 있고, 시트를 덮어쓰기로 다시 가져와도 적은 값이 남는다.
    이어진 줄의 따라 고치기는 tests/test_series_a_ir_sync.py."""
    from app.models import IrCompany, SeriesACompany
    from app.services import series_a_import as svc

    db.add(IrCompany(name="샘플애그", contact_name="김가나", contact_phone="010-1000-0002",
                     revenue_2024="9", pre_value="100"))
    db.commit()
    # 같은 이름의 IR 기업이 생기면 저절로 이어진다(3단계) — 사람이 푼 줄을 흉내 낸다.
    table = SeriesACompany.__table__
    db.execute(table.update().where(table.c.id == deal.id).values(
        ir_company_id=None, ir_link_auto=0, ceo_name=None, ceo_phone=None,
        revenue_2024=None, pre_value=None))
    db.commit()
    data = logged_in.patch(f"/api/series-a-companies/{deal.id}", json={"detail": "x"}).json()
    assert data["ir_name"] == "샘플애그"
    assert (data["ceo_name"], data["ceo_phone"], data["revenue_2024"], data["pre_value"]) \
        == ("", "", "", "")

    from app.routers.series_a import TYPED
    assert not set(TYPED) & set(svc.HEADERS), "시트 가져오기가 직접 적는 칸을 읽습니다"
    logged_in.patch(f"/api/series-a-companies/{deal.id}", json={"ceo_phone": "010-1000-0003"})
    sheet = [["수신 일자", "공유 심사역", "기업명", "상세 내용"],
             ["2026-07-01", "", "샘플애그", "시트 내용"]]
    svc.upsert(db, svc.parse(sheet).records, overwrite=True)
    db.commit()
    db.expire_all()
    row = db.get(SeriesACompany, deal.id)
    assert row.detail == "시트 내용", "시트 줄이 이 줄에 안 맞았습니다 — 아래 단정이 무의미해집니다"
    assert row.ceo_phone == "010-1000-0003"


def test_추가_칸_자리_목록에도_선다():
    """관리자가 추가 칸을 이 칸들 뒤에 둘 수 있다(`custom_columns._HAND_ANCHORS`)."""
    from app.services import custom_columns as svc

    tab = svc.anchor_groups("companies")["Series A 이상 딜 소싱"]
    at = tab.index("투자라운드")
    assert list(tab[at + 1:at + 1 + len(LABELS)]) == LABELS


# ── 판(0112) ────────────────────────────────────────────────────────────────

def _columns(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("series_a_companies")')}
    finally:
        con.close()


def test_판은_0111_뒤에_칸을_더하고_되돌리면_그_칸만_뺀다(tmp_path):
    from app.routers.series_a import TYPED

    db = tmp_path / "m.db"
    done = _alembic(db, "upgrade", "0111_forecast_fee")
    assert done.returncode == 0, done.stdout + done.stderr
    con = sqlite3.connect(db)
    try:
        # 운영 DB 는 이 칸이 없는 표에서 출발한다(0001 의 create_all 은 이미 칸이 있다).
        keep = ", ".join(c for c in _columns(db) if c not in TYPED)
        con.execute(f"CREATE TABLE sa_old AS SELECT {keep} FROM series_a_companies")
        con.execute("DROP TABLE series_a_companies")
        con.execute("ALTER TABLE sa_old RENAME TO series_a_companies")
        con.commit()
    finally:
        con.close()
    assert not set(TYPED) & _columns(db)

    done = _alembic(db, "upgrade", "0112_series_a_fields")
    assert done.returncode == 0, done.stdout + done.stderr
    assert set(TYPED) <= _columns(db)

    done = _alembic(db, "downgrade", "0111_forecast_fee")
    assert done.returncode == 0, done.stdout + done.stderr
    cols = _columns(db)
    assert not set(TYPED) & cols and {"deal_pitch", "import_key"} <= cols
