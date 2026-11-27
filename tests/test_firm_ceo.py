"""투자사 대표님 표시(0139 · `vc_contacts.is_firm_ceo`).

요청: "딜소개 드리는 분들중에서 투자사 대표님은 그룹웨어에 별도로 기입 … 표시가 좀
눈에 띄어야 함". 투자사 관리 현황 표의 `투자사 대표` 칸(O/X)을 고르면 이름 옆에 [대표]
배지가 서고, 그 칸의 필터로 대표님만 본다. 시트를 다시 올려도 값이 남아야 한다.
"""
from __future__ import annotations

import re
import sqlite3

from app.models import VcContact

from .test_data_io import SAMPLE, _sheet, _upload
from .test_migrations import _alembic


def _uploaded(client, db):
    r = _upload(client, _sheet(SAMPLE), dry_run="false")
    assert r.status_code == 200, r.text
    db.expire_all()
    return {c.name: c for c in db.query(VcContact).filter(
        VcContact.name.in_(["홍길동", "김서연"]))}


def _row_html(html: str, row_id: int) -> str:
    m = re.search(r'<tr class="data-row[^"]*" data-id="%d".*?</tr>' % row_id, html, re.S)
    assert m, f"줄 {row_id} 이 표에 없다"
    return m.group(0)


def test_the_cell_takes_o_and_x_and_answers_the_stored_value(logged_in, db):
    rows = _uploaded(logged_in, db)
    cid = rows["김서연"].id

    r = logged_in.patch(f"/api/contacts/{cid}", json={"is_firm_ceo": "O"})
    assert r.status_code == 200, r.text
    assert r.json()["is_firm_ceo"] == "O"
    db.expire_all()
    assert db.get(VcContact, cid).is_firm_ceo == 1

    # `X` 는 저장값이 빈칸이다 — 화면이 이 값으로 칸 · 배지를 다시 그린다.
    r = logged_in.patch(f"/api/contacts/{cid}", json={"is_firm_ceo": "x"})
    assert r.status_code == 200, r.text
    assert r.json()["is_firm_ceo"] == ""
    db.expire_all()
    assert db.get(VcContact, cid).is_firm_ceo == 0

    # 다른 칸만 고친 저장은 이 값을 건드리지 않는다.
    logged_in.patch(f"/api/contacts/{cid}", json={"is_firm_ceo": 1})
    logged_in.patch(f"/api/contacts/{cid}", json={"memo": "메모만"})
    db.expire_all()
    assert db.get(VcContact, cid).is_firm_ceo == 1

    assert logged_in.patch(f"/api/contacts/{cid}",
                           json={"is_firm_ceo": "대표"}).status_code == 422


def test_the_table_shows_the_badge_and_filters_on_it(logged_in, db):
    rows = _uploaded(logged_in, db)
    ceo, other = rows["김서연"], rows["홍길동"]
    ceo.is_firm_ceo = 1
    db.commit()

    html = logged_in.get("/contacts?sheet=all").text
    assert 'data-filters="ceo:투자사 대표"' in html
    mine = _row_html(html, ceo.id)
    assert 'data-f-ceo="O"' in mine
    assert 'class="tag ceo-badge">대표</span>' in mine
    assert 'data-field="is_firm_ceo"' in mine
    theirs = _row_html(html, other.id)
    assert 'data-f-ceo=""' in theirs
    assert 'class="tag ceo-badge" hidden>대표</span>' in theirs


def test_reuploading_the_sheet_keeps_the_mark(logged_in, db):
    rows = _uploaded(logged_in, db)
    cid = rows["김서연"].id
    logged_in.patch(f"/api/contacts/{cid}", json={"is_firm_ceo": "O"})

    _uploaded(logged_in, db)
    assert db.get(VcContact, cid).is_firm_ceo == 1


def _contact_columns(path) -> set:
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("vc_contacts")')}
    finally:
        con.close()


def test_migration_adds_and_drops_the_column(tmp_path):
    db = tmp_path / "old.db"
    done = _alembic(db, "upgrade", "0138_send_item_room_candidates")
    assert done.returncode == 0, done.stdout + done.stderr
    # 0001 은 지금 모델로 표를 만든다 — 운영 DB 처럼 칸이 없는 모양으로 되돌린다.
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE vc_contacts DROP COLUMN is_firm_ceo")
    con.commit()
    con.close()
    assert "is_firm_ceo" not in _contact_columns(db)

    done = _alembic(db, "upgrade", "head")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "is_firm_ceo" in _contact_columns(db)
    # 있던 줄은 0(대표 아님)으로 선다 — 비어 있으면 배지 판정이 줄마다 갈린다.
    con = sqlite3.connect(db)
    col = next(r for r in con.execute('PRAGMA table_info("vc_contacts")') if r[1] == "is_firm_ceo")
    con.close()
    assert col[3] == 1 and col[4] in ("0", "'0'")
    done = _alembic(db, "downgrade", "0138_send_item_room_candidates")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "is_firm_ceo" not in _contact_columns(db)
