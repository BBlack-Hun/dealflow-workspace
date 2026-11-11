"""딜 제안 관리 `반응 없음` 에서 **손으로 빼기**(11/11) — `vc_contacts.no_reaction_cleared_at`.

요청: "반응 없는 담당자 사용자가 체크해서 뺄 수 있게". 전화 · 다른 길로 반응이 있었던
분은 앱에 기록이 없어 판정(`services/no_reaction`)이 그대로 `반응 없음` 이라고 했다.

  1. 판(0136) 오르내리기
  2. 뺀 분은 `listed` 에서 빠진다 — 딱지 · 단추 수 · 대시보드 수가 함께 따라온다
  3. 빼고 되돌리는 길 — 맡은 사람 · 관리자만, 남의 줄은 `없는 것`, 수정 로그
  4. 뺀 것은 다른 곳의 반응이 아니다(반응 칸 · 리마인드 · `상태` · 그룹)

화면 쪽(카드의 단추 · 되돌리기)은 `tests/js/deals_noreact_clear_test.js`.
이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD
from .test_migrations import _alembic

SHEET = "가 명단"


@pytest.fixture()
def people(db, users):
    """u1 명단 — 딜소개를 받은 분 셋(둘은 반응 없음 · 하나는 IR 요청), 받기 전 하나."""
    from app.models import ContactActivity, IrRequest, SheetOwner, VcContact

    u1 = users["u1"]
    db.add(SheetOwner(label=SHEET, user_id=u1.id))
    today = date.today().isoformat()

    def person(name, intro=True, **kw):
        c = VcContact(user_id=u1.id, name=name, firm="가나벤처스", source_sheet=SHEET,
                      connect_stage="connected", kakao_room_name=f"{name} 방",
                      channel_kakao=1, **kw)
        db.add(c)
        db.flush()
        if intro:
            db.add(ContactActivity(contact_id=c.id, kind="deal_intro", content="딜소개",
                                   happened_at=today, month=today[:7]))
        return c

    made = {
        "전화반응": person("전화반응", group_name="1군", status="no_response"),
        "무반응": person("무반응"),
        "요청함": person("요청함"),
        "딜소개전": person("딜소개전", intro=False),
    }
    db.add(IrRequest(user_id=u1.id, contact_id=made["요청함"].id, company_name="샘플가",
                     requested_at=today))
    db.commit()
    return made


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


# ── 1) 판 ───────────────────────────────────────────────────────────────────

def _cols(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("vc_contacts")')}
    finally:
        con.close()


def test_0136_은_빈_칸을_붙이고_되돌리면_뗀다(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", "0135_sender_room_sourcing").returncode == 0
    # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE vc_contacts DROP COLUMN no_reaction_cleared_at")
        con.execute("INSERT INTO vc_contacts (user_id, name, channel_kakao, channel_email,"
                    " room_verified, status, connect_stage, is_hidden, created_at, updated_at)"
                    " VALUES (1, '옛줄', 1, 0, 'verified', 'active', 'connected', 0, 'x', 'x')")
        con.commit()
    finally:
        con.close()

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT no_reaction_cleared_at FROM vc_contacts").fetchall() == [(None,)]
    finally:
        con.close()

    down = _alembic(db, "downgrade", "0135_sender_room_sourcing")
    assert down.returncode == 0, down.stdout + down.stderr
    assert "no_reaction_cleared_at" not in _cols(db)


# ── 2) 판정 · 화면 · 대시보드 ────────────────────────────────────────────────

def test_뺀_분은_반응_없음_한_벌에서_빠지고_되돌릴_자리에_선다(db, users, people):
    from app.models import IrRequest
    from app.services import no_reaction

    u1 = users["u1"]
    quiet, done = people["전화반응"], people["무반응"]
    assert no_reaction.listed(db, u1) == {quiet.id, done.id}

    quiet.no_reaction_cleared_at = "2026-11-11T10:00:00+09:00"
    db.commit()
    assert no_reaction.listed(db, u1) == {done.id}
    assert no_reaction.judged(db, u1) == ({done.id}, {quiet.id})

    # 뺀 뒤 반응이 실제로 적히면 판정이 그분을 뺀다 — 되돌릴 것도 없다.
    db.add(IrRequest(user_id=u1.id, contact_id=quiet.id, company_name="샘플나",
                     requested_at=date.today().isoformat()))
    db.commit()
    assert no_reaction.judged(db, u1) == ({done.id}, set())


def test_빼면_딜제안관리_딱지_단추_수와_대시보드_수가_함께_준다(logged_in, db, people):
    def counts():
        deals = logged_in.get("/deals").text
        button = re.search(r'id="select-noreact"[^>]*>반응 없는 담당자만 · (\d+)명<', deals)
        dash = logged_in.get("/dashboard").text
        link = re.search(r'<a[^>]*href="/deals\?noreact=1"[^>]*>.*?<b>(\d+)</b>', dash, re.S)
        return (int(button.group(1)), deals.count('data-noreact="1"'),
                int(link.group(1)) if link else 0, deals)

    assert counts()[:3] == (2, 2, 2)

    quiet = people["전화반응"]
    r = logged_in.post(f"/api/contacts/{quiet.id}/no-reaction", json={"cleared": True})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "cleared": True}
    button, tagged, dash, html = counts()
    assert (button, tagged, dash) == (1, 1, 1)
    # 뺀 분 카드에는 [되돌리기] 모양이 보이고 `반응 없음` 딱지는 숨는다.
    card = re.search(r'value="%d"[^>]*data-noreact="0">.*?</label>' % quiet.id, html, re.S)
    assert card, "뺀 분 카드가 `data-noreact=\"0\"` 으로 안 섰다"
    assert re.search(r'class="noreact-mark" data-cleared="1"', card.group(0))
    assert re.search(r'<span class="noreact-on" hidden>', card.group(0))
    assert re.search(r'<span class="noreact-off">.*?되돌리기</button>', card.group(0), re.S)
    # 남은 분은 [반응 없음에서 빼기] 가 보인다(카드 체크와 다른 단추다).
    other = re.search(r'value="%d"[^>]*data-noreact="1">.*?</label>' % people["무반응"].id,
                      html, re.S)
    assert re.search(r'<span class="noreact-on">.*?<button type="button" '
                     r'class="linkbtn noreact-toggle"', other.group(0), re.S)
    assert re.search(r'<span class="noreact-off" hidden>', other.group(0))
    # 반응 있는 분 · 딜소개 전인 분에게는 아무 것도 안 선다.
    assert html.count('class="noreact-mark"') == 2

    r = logged_in.post(f"/api/contacts/{quiet.id}/no-reaction", json={"cleared": False})
    assert r.json() == {"ok": True, "cleared": False}
    assert counts()[:3] == (2, 2, 2)


# ── 3) 누가 · 수정 로그 ──────────────────────────────────────────────────────

def test_맡은_사람은_빼고_되돌리고_남의_줄은_없는_것이다(client, db, users, people):
    from app.models import EditLog, VcContact

    quiet = people["전화반응"]
    url = f"/api/contacts/{quiet.id}/no-reaction"

    _login(client, "01000000002")                      # u2 — 팀원, 남의 줄
    r = client.post(url, json={"cleared": True})
    assert r.status_code == 404, r.text
    db.expire_all()
    assert db.get(VcContact, quiet.id).no_reaction_cleared_at is None

    _login(client, "01000000001")                      # u1 — 맡은 사람
    assert client.post(url, json={"cleared": True}).status_code == 200
    db.expire_all()
    first = db.get(VcContact, quiet.id).no_reaction_cleared_at
    assert first and re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$", first), first
    # 또 빼도 처음 뺀 시각 그대로다.
    assert client.post(url, json={"cleared": True}).json()["cleared"] is True
    db.expire_all()
    assert db.get(VcContact, quiet.id).no_reaction_cleared_at == first
    # 자기 줄을 고친 것은 수정 로그에 안 남는다(`edit_log` 머리말).
    assert db.query(EditLog).filter(EditLog.table_name == "vc_contacts").count() == 0

    users["u2"].role = "admin"                         # 관리자는 팀 전체를 고친다
    db.commit()
    _login(client, "01000000002")
    r = client.post(url, json={"cleared": False})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(VcContact, quiet.id).no_reaction_cleared_at is None
    log = db.query(EditLog).filter(EditLog.table_name == "vc_contacts",
                                   EditLog.row_id == quiet.id).one()
    assert log.actor_user_id == users["u2"].id and log.path == url
    assert '"no_reaction_cleared_at"' in log.changes_json and first in log.changes_json


# ── 4) 다른 곳의 반응이 아니다 ───────────────────────────────────────────────

def test_뺀_것은_반응_칸_리마인드_상태_그룹을_안_바꾼다(logged_in, db, users, people):
    from app.models import SendSequence, VcContact
    from app.services import dashboard, no_reaction

    quiet = people["전화반응"]
    seq = SendSequence(user_id=users["u1"].id, contact_id=quiet.id, stage=2, status="active")
    db.add(seq)
    db.commit()

    r = logged_in.post(f"/api/contacts/{quiet.id}/no-reaction", json={"cleared": True})
    assert r.status_code == 200, r.text
    db.expire_all()

    assert quiet.id not in no_reaction.reacted_ids(db, [quiet.id])
    hits = dashboard.reaction_hits(db, [quiet.id])
    assert not any(h.contact_id == quiet.id for rows in hits.values() for h in rows), (
        "반응 없음에서 뺀 것이 대시보드 반응 칸에 들어갔다")
    assert db.get(SendSequence, seq.id).status == "active", "리마인드가 멈췄다"
    row = db.get(VcContact, quiet.id)
    assert row.status == "no_response", "`상태` 의 반응없음이 풀렸다"
    assert row.group_name == "1군"
