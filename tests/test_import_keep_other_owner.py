"""다른 팀원 명단에 이미 있는 분 — 옮길까, 이 담당자 몫으로 따로 만들까.

업로드(`/api/import/contacts`)는 이름+투자사로 사람을 찾는다. 예전에는 찾은
줄의 소유를 시트의 담당자에게 **옮겼다** — 새 팀원 시트를 넣을 때 그 동작에
기대 왔다. 같은 분을 두 팀원이 각자 맡는 경우(이관받은 명단)를 위해
`keep_other_owner` 를 켜면 **안 옮기고 따로 만든다.**

지키는 것:
  · 꺼 두면 예전 그대로 옮긴다.
  · 켜면 사본이 생기고 원래 줄은 한 칸도 안 바뀐다.
  · 같은 파일을 다시 올려도 사본이 늘지 않는다.
  · 미리보기가 겹친 수와 어떻게 할지를 [반영] 전에 말한다.
  · 같은 분께 두 팀원 몫으로 같은 딜이 이번 주 두 번 나가지 않는다.
"""
from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from app.models import User, VcContact
from app.services import sheet_import as si

from .conftest import DEMO_PASSWORD

openpyxl = pytest.importorskip("openpyxl")

HEADER = ["그룹", "담당자", "이름", "직함", "투자사명", "카톡방 참여여부", "메모"]


def _rows(owner="윤서아"):
    return [
        HEADER,
        ["A", owner, "홍길동", "심사역", "가나다벤처스", "O", "새 메모"],
        ["A", owner, "김서연", "대표", "마바벤처스", "O", ""],
    ]


def _xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def held(db, users):
    """u1(강민준) 이 이미 맡은 분 — 방까지 확인된 줄."""
    c = VcContact(user_id=1, name="홍길동", title="심사역", firm="가나다벤처스",
                  kakao_room_name="홍길동 심사역님 가나다벤처스 (원래방)",
                  room_verified="verified", connect_stage="connected",
                  memo="원래 메모", source_sheet="원래명단", status="active")
    db.add(c)
    db.commit()
    return c.id


def _apply(db, keep, dry_run=False):
    parsed = si.parse_sheet_a(_rows(), year=2026)
    return si.apply_sheet_a(db, parsed, user_id=2, dry_run=dry_run,
                            source_label="업로드", keep_other_owner=keep)


def _copies(db):
    db.expire_all()
    return db.execute(select(VcContact).where(VcContact.name == "홍길동")
                      .order_by(VcContact.id)).scalars().all()


def test_option_off_moves_like_before(db, held):
    report = _apply(db, keep=False)
    rows = _copies(db)
    assert len(rows) == 1 and rows[0].user_id == 2
    assert report.overlap_moved == 1 and report.overlap_kept == 0
    assert any("옮김" in n for n in report.notes)


def test_option_on_makes_own_copy_and_leaves_original(db, held):
    report = _apply(db, keep=True)
    rows = _copies(db)
    assert [r.user_id for r in rows] == [1, 2]
    orig, mine = rows
    assert orig.id == held
    assert orig.kakao_room_name == "홍길동 심사역님 가나다벤처스 (원래방)"
    assert orig.memo == "원래 메모" and orig.source_sheet == "원래명단"
    assert orig.room_verified == "verified" and orig.connect_stage == "connected"
    # 사본은 시트에서 채운다 — 원래 주인의 방을 베끼지 않는다.
    assert mine.memo == "새 메모" and mine.source_sheet == "업로드"
    assert mine.kakao_room_name and "원래방" not in mine.kakao_room_name
    assert report.created == 2 and report.overlap_kept == 1
    assert report.overlaps == [("홍길동", "가나다벤처스", "강민준")]


def test_option_on_reupload_is_idempotent(db, held):
    _apply(db, keep=True)
    again = _apply(db, keep=True)
    assert len(_copies(db)) == 2
    assert again.created == 0 and again.updated == 2
    # 이미 내 몫이 있으면 겹침이 아니다 — 남의 줄을 다시 건드리지 않는다.
    assert again.overlaps == []
    # 옵션을 꺼도 내 몫을 먼저 찾으므로 남의 줄을 옮기지 않는다.
    off = _apply(db, keep=False)
    assert [r.user_id for r in _copies(db)] == [1, 2]
    assert off.overlap_moved == 0


def test_preview_reports_overlap_before_apply(client, db, held):
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})

    def up(keep, dry):
        return client.post(
            "/api/import/contacts",
            files={"file": ("현황.xlsx", _xlsx(_rows()),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"dry_run": "true" if dry else "false",
                  "keep_other_owner": "true" if keep else "false"})

    off = up(False, True).json()
    assert off["overlap_total"] == 1 and off["overlap_moved"] == 1
    on = up(True, True).json()
    assert on["overlap_total"] == 1 and on["overlap_kept"] == 1
    assert on["overlaps"] == [{"name": "홍길동", "firm": "가나다벤처스", "owner": "강민준"}]
    assert len(_copies(db)) == 1          # 미리보기는 안 남긴다
    assert up(True, False).status_code == 200
    assert [r.user_id for r in _copies(db)] == [1, 2]


# ── 같은 분께 두 번 나가지 않게 ──────────────────────────────────────────────

@pytest.fixture()
def twins(db, users):
    from app.models import IrCompany
    company = IrCompany(name="샘플애그", sector_major="애그테크", series="Seed",
                        one_liner="한줄", summary="요약", summary_status="done",
                        revenue_recent=1)
    other = IrCompany(name="샘플메디", sector_major="헬스케어", series="Seed",
                      one_liner="한줄", summary="요약", summary_status="done",
                      revenue_recent=1)
    room = "홍길동 심사역님 가나다벤처스"
    a = VcContact(user_id=1, name="홍길동", title="심사역", firm="가나다벤처스",
                  kakao_room_name=room, room_verified="verified", status="active")
    b = VcContact(user_id=2, name="홍길동", title="심사역", firm="가나다벤처스",
                  kakao_room_name=room, room_verified="verified", status="active")
    c = VcContact(user_id=2, name="김서연", title="대표", firm="마바벤처스",
                  kakao_room_name="김서연 대표님 마바벤처스",
                  room_verified="verified", status="active")
    db.add_all([company, other, a, b, c])
    db.commit()
    return {"company": company.id, "other": other.id, "a": a.id, "b": b.id, "c": c.id}


def _login(client, phone):
    client.cookies.clear()
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def _send(client, company, ids):
    return client.post("/api/deals/send", json={
        "company_ids": [company], "contact_ids": ids, "title": "회차"})


def test_twin_gets_same_deal_only_once(client, db, twins):
    _login(client, "01000000001")
    assert _send(client, twins["company"], [twins["a"]]).status_code == 200

    _login(client, "01000000002")
    # 미리보기가 먼저 말한다.
    pv = client.post("/api/deals/preview", json={
        "company_ids": [twins["company"]], "contact_ids": [twins["b"], twins["c"]]}).json()
    warn = {p["contact_id"]: " ".join(p["warnings"]) for p in pv["previews"]}
    assert "강민준" in warn[twins["b"]] and "샘플애그" in warn[twins["b"]]
    assert "강민준" not in warn[twins["c"]]

    r = _send(client, twins["company"], [twins["b"], twins["c"]])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert [s["contact_id"] for s in body["skipped"]] == [twins["b"]]

    from app.models import SendItem
    db.expire_all()
    rooms = [i.contact_id for i in db.execute(
        select(SendItem).where(SendItem.job_id == body["job_id"])).scalars()]
    assert rooms == [twins["c"]]


def test_twin_only_target_is_refused_with_reason(client, twins):
    _login(client, "01000000001")
    _send(client, twins["company"], [twins["a"]])
    _login(client, "01000000002")
    r = _send(client, twins["company"], [twins["b"]])
    assert r.status_code == 400
    assert "강민준" in r.json()["detail"]


def test_twin_with_other_company_still_goes(client, twins):
    """다른 기업이면 두 번이 아니다 — 막지 않는다."""
    _login(client, "01000000001")
    _send(client, twins["company"], [twins["a"]])
    _login(client, "01000000002")
    r = _send(client, twins["other"], [twins["b"]])
    assert r.status_code == 200 and r.json()["skipped"] == []


def test_canceled_twin_send_does_not_block(client, db, twins):
    from app.models import SendJob
    _login(client, "01000000001")
    job_id = _send(client, twins["company"], [twins["a"]]).json()["job_id"]
    db.get(SendJob, job_id).status = "canceled"
    db.commit()
    _login(client, "01000000002")
    r = _send(client, twins["company"], [twins["b"]])
    assert r.status_code == 200 and r.json()["skipped"] == []


def test_sourcing_link_keeps_room_for_twin_copies(db, users):
    """같은 분의 두 팀원 몫(번호·방 같음)은 번호 겹침으로 치지 않는다."""
    from app.services import sourcing_link
    room = "홍길동 심사역님 가나다벤처스"
    rows = [VcContact(user_id=u, name="홍길동", firm="가나다벤처스",
                      phone="010-0000-0000", kakao_room_name=room)
            for u in (1, 2)]
    assert sourcing_link._by_phone(rows)["01000000000"].kakao_room_name == room
    rows[1].kakao_room_name = "다른 방"
    assert "01000000000" not in sourcing_link._by_phone(rows)
