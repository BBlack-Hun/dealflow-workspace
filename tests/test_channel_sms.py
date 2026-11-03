"""연락 채널 `문자` — `vc_contacts.channel_sms`(0130).

요청: "팀원 중에 문자로도 딜 소개를 하는 경우가 있음. 연락 채널에 카톡, 메일이 있는데,
문자도 추가!" 앱의 문자 발송은 11/01 에 걷었다 — 이 칸은 팀원이 휴대폰으로 **직접**
보낸다는 표시다.

  1. 판(0130) 오르내리기
  2. 저장 · 라벨 · 내보내기
  3. 문자만 켠 줄은 자동 발송 목록에서 빠지고, 빠진 사유로 이름이 선다
  4. 카톡방 상태 `sms` — `채널 불가 투자사` 와 다른 갈래, 보낼 수 있는 갈래가 아니다
  5. 카톡 · 메일이 하나라도 켜져 있으면 문자 칸은 아무 일도 안 한다(회귀)

이름은 전부 지어낸 것이다 — 저장소가 공개다.
"""
from __future__ import annotations

import sqlite3

import pytest

from .test_migrations import _alembic

SHEET = "가 명단"


@pytest.fixture()
def rows(db, users):
    from app.models import SheetOwner, VcContact

    db.add(SheetOwner(label=SHEET, user_id=users["u1"].id))

    def contact(name, **kw):
        base = dict(user_id=users["u1"].id, name=name, firm="가나벤처스",
                    source_sheet=SHEET, connect_stage="connected", status="active",
                    kakao_room_name=f"{name} 방", room_verified="verified")
        base.update(kw)
        return VcContact(**base)

    made = [
        contact("가카톡", channel_kakao=1),
        contact("나메일", channel_email=1),
        contact("다문자", channel_sms=1),                         # ★ 문자만
        contact("라카톡문자", channel_kakao=1, channel_sms=1),
        contact("마메일문자", channel_email=1, channel_sms=1),
        contact("바없음"),                                        # 채널 불가 — 그대로
        contact("사문자연결전", channel_sms=1, connect_stage="not_started"),
    ]
    db.add_all(made)
    db.commit()
    return {c.name: c for c in made}


# ── 1) 판 ───────────────────────────────────────────────────────────────────

def _cols(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("vc_contacts")')}
    finally:
        con.close()


def test_0130_은_칸을_0으로_붙이고_되돌리면_뗀다(tmp_path):
    db = tmp_path / "old.db"
    assert _alembic(db, "upgrade", "0129_contract_ym").returncode == 0
    # 운영 DB 의 모양 — 0001 의 `create_all()` 은 지금 모델이라 칸이 이미 있다.
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE vc_contacts DROP COLUMN channel_sms")
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
        assert con.execute("SELECT channel_sms FROM vc_contacts").fetchall() == [(0,)]
    finally:
        con.close()

    down = _alembic(db, "downgrade", "0129_contract_ym")
    assert down.returncode == 0, down.stdout + down.stderr
    assert "channel_sms" not in _cols(db)


# ── 2) 저장 · 라벨 ──────────────────────────────────────────────────────────

def test_문자_칸을_켜고_끄면_저장되고_라벨이_선다(logged_in, db, users, rows):
    from app.routers.contacts import contact_rows
    from app.routers.data_io import _contact_row

    row = rows["가카톡"]
    r = logged_in.patch(f"/api/contacts/{row.id}",
                        json={"channel_kakao": 0, "channel_sms": 1})
    assert r.status_code == 200, r.text
    db.refresh(row)
    assert (row.channel_kakao, row.channel_sms) == (0, 1)
    assert logged_in.get(f"/api/contacts/{row.id}").json()["contact"]["channel_sms"] == 1

    by_name = {x["name"]: x for x in contact_rows(db, users["u1"])}
    assert by_name["가카톡"]["channel_label"] == "문자"
    assert by_name["가카톡"]["channel_tags"] == ["문자"]
    assert by_name["라카톡문자"]["channel_label"] == "카톡"       # 카톡이 먼저다
    assert by_name["라카톡문자"]["channel_tags"] == ["카톡", "문자"]
    assert by_name["바없음"]["channel_label"] == "미지정"
    # 엑셀 `채널` 칸(9번째)
    assert _contact_row(by_name["라카톡문자"])[8] == "카톡/문자"

    r = logged_in.patch(f"/api/contacts/{row.id}", json={"channel_sms": 0})
    db.refresh(row)
    assert row.channel_sms == 0


def test_편집_창에_문자_체크가_있다(logged_in, rows):
    html = logged_in.get("/contacts").text
    assert 'id="f-channel_sms"' in html


# ── 3) 자동 발송에서 빠진다 ─────────────────────────────────────────────────

def test_문자만_켠_분은_발송_대상이_아니고_사유로_이름이_선다(logged_in, db, users, rows):
    from app.services import sheet_owner

    names = {c.name for c in sheet_owner.recipients(db, users["u1"])}
    assert "다문자" not in names
    # 회귀 — 카톡 · 메일 · 채널 불가는 지금과 같다(채널 불가도 원래 목록에 있었다).
    assert {"가카톡", "나메일", "라카톡문자", "마메일문자", "바없음"} <= names

    counts = sheet_owner.recipient_counts(db, users["u1"])
    sms = counts["sms"]
    assert sms["label"] == sheet_owner.SMS_LABEL
    assert [p["name"] for p in sms["people"]] == ["다문자"]
    # 연결 전 문자 분은 연결 단계 쪽에 한 번만 선다 — 사유를 겹쳐 세지 않는다.
    assert (counts["paused"]["count"] + sms["count"]
            + sum(s["count"] for s in counts["blocked_by_stage"])) == counts["blocked"]

    html = logged_in.get("/deals").text
    assert 'data-name="다문자"' not in html
    block = html[html.index('id="sms-contacts"'):]
    assert "다문자" in block and sheet_owner.SMS_LABEL in block


def test_문자만_켠_분은_오래된_탭에서_눌러도_안_나간다(logged_in, db, rows):
    from app.models import IrCompany
    from app.services import sheet_owner

    company = IrCompany(name="샘플애그", sector_major="애그테크", series="Seed",
                        one_liner="B2B 농산물 선도거래 플랫폼", summary="요약문",
                        summary_status="done", revenue_recent=12)
    db.add(company)
    db.commit()
    r = logged_in.post("/api/deals/send", json={
        "company_ids": [company.id], "contact_ids": [rows["다문자"].id]})
    assert r.status_code == 400, r.text
    assert sheet_owner.SMS_LABEL in r.json()["detail"]
    # 회귀 — 채널 불가(아무것도 안 켬)는 지금처럼 나간다.
    ok = logged_in.post("/api/deals/send", json={
        "company_ids": [company.id], "contact_ids": [rows["바없음"].id]})
    assert ok.status_code == 200, ok.text


def test_미팅_자동화도_문자만_켠_분은_건너뛴다(db, rows):
    from app.services import sheet_owner
    from app.services.automations import meeting_request, meeting_review

    for check in (meeting_request._sendable, meeting_review._contact_problem):
        assert check(db, rows["다문자"]) == sheet_owner.SMS_LABEL
        assert check(db, rows["라카톡문자"]) == ""
        assert check(db, rows["바없음"]) == ""


# ── 4) 카톡방 상태 ──────────────────────────────────────────────────────────

def test_문자만_켠_분은_채널_불가와_다른_카톡방_상태다(db, users, rows):
    from app.services import dashboard
    from app.services.dashboard import _SENDABLE_ROOM, ROOM_LABELS, _room_state

    assert _room_state(rows["다문자"]) == "sms"
    assert ROOM_LABELS["sms"] == ("문자(직접 발송)", "muted")
    assert "sms" not in _SENDABLE_ROOM
    assert _room_state(rows["바없음"]) == "no_channel"

    summary = dashboard.user_dashboard(db, users["u1"])
    rooms = {r["state"]: r for r in summary["rooms"]}
    assert rooms["sms"]["count"] == 2           # 연결 전 분도 방 갈래로는 센다
    assert rooms["sms"]["label"] == "문자(직접 발송)"
    stuck = {r["state"]: r for r in summary["pipeline"]["rooms"]}
    assert [p["name"] for p in stuck["sms"]["people"]] == ["다문자"]


# ── 5) 회귀 — 카톡 · 메일이 켜져 있으면 문자 칸은 아무 일도 안 한다 ───────────

def test_카톡이나_메일이_켜져_있으면_문자_칸은_판정을_안_바꾼다(db, rows):
    from app.services import sheet_owner
    from app.services.dashboard import _room_state

    assert _room_state(rows["라카톡문자"]) == _room_state(rows["가카톡"]) == "verified"
    assert _room_state(rows["마메일문자"]) == _room_state(rows["나메일"]) == "email"
    for name in ("가카톡", "나메일", "라카톡문자", "마메일문자", "바없음"):
        assert not sheet_owner.sms_only(rows[name])
        assert sheet_owner.can_send_to(rows[name])
    assert sheet_owner.sms_only(rows["다문자"])
    assert not sheet_owner.can_send_to(rows["다문자"])
