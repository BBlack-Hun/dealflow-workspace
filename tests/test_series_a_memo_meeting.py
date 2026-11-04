"""`Series A 이상 딜 소싱` 탭 — #142 메모 · 수정한 팀원 · 수정한 날짜, #143 IR 투자컨설팅 미팅일시(0131).

#142: "기업명 컬럼 오른쪽에 메모 컬럼 삽입, 수정담당자명, 수정일 컬럼 넣어서 수정일은 자동으로".
수정한 날짜는 `updated_at`, 수정한 팀원은 수정 로그(IR 기업 현황의 같은 두 칸과 같은 셈).
#143: "후속라운드 시작 컬럼 오른쪽에 IR 투자컨설팅 미팅일시간 기입할 수 있게" — `YYYY-MM-DD HH:MM`.
값은 전부 지어낸 것이다 — 저장소가 공개다.
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


def _page(client):
    html = client.get("/companies?tab=series-a").text
    thead = re.search(r'id="sa-table".*?</thead>', html, re.S).group(0)
    labels = [re.sub(r"<[^>]+>", "", t).strip()
              for t in re.findall(r"<th\b[^>]*>(.*?)</th>", thead, re.S)]
    return labels, re.search(r"<tr data-id=.*?</tr>", html, re.S).group(0)


def test_칸이_요청한_자리에_선다(logged_in, deal):
    labels, row = _page(logged_in)
    at = labels.index("기업명")
    assert labels[at + 1:at + 4] == ["메모", "수정한 팀원", "수정한 날짜"], labels
    assert labels[labels.index("후속라운드 시작") + 1] == "IR 투자컨설팅 미팅일시", labels
    fields = re.findall(r'class="cell[^"]*" data-field="([^"]+)"', row)
    assert fields[fields.index("name") + 1] == "memo", fields
    assert fields[fields.index("follow_round_month") + 1] == "consulting_meeting_at", fields
    # 수정한 팀원 · 날짜는 앱이 적는 칸 — 눌러 열리는 `.cell` 이 아니다.
    assert re.search(r'<td class="updated-by[^"]*">', row)
    assert re.search(r'<td class="updated-at[^"]*"', row)


def test_메모를_저장하면_수정한_날짜와_팀원이_채워진다(logged_in, deal, users, db):
    from app.models import SeriesACompany

    _labels, row = _page(logged_in)
    # 아무도 안 고친 줄 — 팀원은 빈칸(`기록 없음` 을 안 쓴다), 날짜는 만든 시각을 옅게.
    assert re.search(r'<td class="updated-by muted"></td>', row), row
    assert 'class="updated-at muted"' in row

    res = logged_in.patch(f"/api/series-a-companies/{deal.id}",
                          json={"memo": " 11/3 대표 통화 — 다음 주 자료 \n받기로 "})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["memo"] == "11/3 대표 통화 — 다음 주 자료 \n받기로"
    assert data["updated_by"] == users["u1"].name
    db.expire_all()
    saved = db.get(SeriesACompany, deal.id)
    assert data["updated_at"] == saved.updated_at[:16].replace("T", " ")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", data["updated_at"])
    assert "다음 주 자료" in data["search"]

    _labels, row = _page(logged_in)
    # 옅은 글씨(`만든 뒤로 안 고침`)는 분까지 견준다 — 만든 그 분에 고친 이 시험에서는 남을 수 있다.
    assert re.search(rf'<td class="updated-by[^"]*">{users["u1"].name}</td>', row), row
    assert f">{data['updated_at']}</td>" in row


def test_사람_손_없이_줄이_바뀐_것이_마지막이면_자동이다(logged_in, deal, db):
    from sqlalchemy import text as sql

    from app.models import SeriesACompany
    from app.routers.companies import AUTO_EDITOR, last_editors

    assert logged_in.patch(f"/api/series-a-companies/{deal.id}",
                           json={"memo": "샘플 메모"}).status_code == 200
    db.execute(sql("UPDATE series_a_companies SET updated_at = '2099-01-01T00:00:00+09:00' "
                   "WHERE id = :i"), {"i": deal.id})
    db.commit()
    db.expire_all()
    table = SeriesACompany.__tablename__
    assert last_editors(db, [db.get(SeriesACompany, deal.id)], table) == {deal.id: AUTO_EDITOR}
    # IR 기업 현황의 로그와 섞이지 않는다 — 같은 번호라도 표가 다르면 안 읽는다.
    assert last_editors(db, [db.get(SeriesACompany, deal.id)]) == {}


@pytest.mark.parametrize("sent, saved", [
    ("2026.11.5 14:00", "2026-11-05 14:00"),
    ("2026-11-05T09:30", "2026-11-05 09:30"),     # <input type="datetime-local"> 꼴
    ("2026/11/05 9:05:00", "2026-11-05 09:05"),
    ("2026-11-05", "2026-11-05"),                 # 시각을 모르면 날짜만
])
def test_미팅일시를_한_꼴로_맞춰_저장한다(logged_in, deal, sent, saved):
    data = logged_in.patch(f"/api/series-a-companies/{deal.id}",
                           json={"consulting_meeting_at": sent}).json()
    assert data["consulting_meeting_at"] == saved
    assert saved in data["search"]


@pytest.mark.parametrize("sent", ["다음 주 화요일", "2026-11-05 25:00", "2026-13-01 10:00",
                                  "2026-11-05 오후 2시"])
def test_못_읽는_미팅일시는_400이고_값을_안_바꾼다(logged_in, deal, db, sent):
    from app.models import SeriesACompany

    url = f"/api/series-a-companies/{deal.id}"
    first = logged_in.patch(url, json={"consulting_meeting_at": "2026-11-05 14:00"})
    assert first.status_code == 200
    bad =logged_in.patch(url, json={"consulting_meeting_at": sent})
    assert bad.status_code == 400 and "YYYY-MM-DD HH:MM" in bad.json()["detail"]
    db.expire_all()
    assert db.get(SeriesACompany, deal.id).consulting_meeting_at == "2026-11-05 14:00"
    # 비우기는 늘 된다.
    assert logged_in.patch(url, json={"consulting_meeting_at": " "}).json()[
        "consulting_meeting_at"] == ""


def test_IR_기업에_이어진_줄이라도_두_칸은_IR로_안_간다(logged_in, db):
    """메모 · 미팅일시는 받은 딜 한 건의 기록이다 — `company_sync.FIELDS` 에 넣지 않았다."""
    from app.models import IrCompany, SeriesACompany

    ir = IrCompany(name="샘플가람", note="IR 쪽 메모")
    db.add(ir)
    db.commit()
    row = SeriesACompany(name="샘플가람", received_at="2026-07-01", ir_company_id=ir.id)
    db.add(row)
    db.commit()
    res = logged_in.patch(f"/api/series-a-companies/{row.id}",
                          json={"memo": "딜 쪽 메모", "consulting_meeting_at": "2026-11-05 14:00"})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(IrCompany, ir.id).note == "IR 쪽 메모"


def test_수정_로그에_미팅일시가_이름과_값으로_남는다():
    from app.services import edit_log

    assert edit_log.field_label("consulting_meeting_at") == "IR 투자컨설팅 미팅일시"
    assert "consulting_meeting_at" in edit_log.VALUE_FIELDS
    assert "memo" not in edit_log.VALUE_FIELDS     # 메모는 `바뀜` 만 — 긴 글은 값을 안 싣는다


def _cols(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("series_a_companies")')}
    finally:
        con.close()


def test_0131_은_두_칸을_붙이고_되돌리면_뗀다(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", "0130_channel_sms").returncode == 0
    # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
    con = sqlite3.connect(db)
    try:
        for name in ("memo", "consulting_meeting_at"):
            con.execute(f"ALTER TABLE series_a_companies DROP COLUMN {name}")
        con.commit()
    finally:
        con.close()
    assert not {"memo", "consulting_meeting_at"} & _cols(db)

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert {"memo", "consulting_meeting_at"} <= _cols(db)

    down = _alembic(db, "downgrade", "0130_channel_sms")
    assert down.returncode == 0, down.stdout + down.stderr
    assert not {"memo", "consulting_meeting_at"} & _cols(db)
