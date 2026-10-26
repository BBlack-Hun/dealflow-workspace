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
  · 옮기기는 관리자만 — 팀원이 올리면 본인 줄만 고친다. 남의 줄은 담당자
    칸이 무엇이든 건너뛰고(사본도 없이) 건너뛴 수만 보인다.
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


def _up(client, keep, dry):
    return client.post(
        "/api/import/contacts",
        files={"file": ("현황.xlsx", _xlsx(_rows()),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dry_run": "true" if dry else "false",
              "keep_other_owner": "true" if keep else "false"})


def test_preview_reports_overlap_before_apply(client, db, held):
    """관리자 — 옮길지 따로 만들지 고르고, 겹친 줄의 지금 담당 이름이 보인다."""
    db.get(User, 2).role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})

    def up(keep, dry):
        return _up(client, keep, dry)

    off = up(False, True).json()
    assert off["overlap_total"] == 1 and off["overlap_moved"] == 1
    on = up(True, True).json()
    assert on["overlap_total"] == 1 and on["overlap_kept"] == 1
    assert on["overlaps"] == [{"name": "홍길동", "firm": "가나다벤처스", "owner": "강민준"}]
    assert len(_copies(db)) == 1          # 미리보기는 안 남긴다
    assert up(True, False).status_code == 200
    assert [r.user_id for r in _copies(db)] == [1, 2]


def test_member_upload_never_moves_and_hides_holder(client, db, held):
    """팀원 — 옮기기를 골라 보내도 남의 줄은 건너뛰고(사본도 없이), 누구 줄인지는 안 싣는다."""
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    res = _up(client, keep=False, dry=True)
    assert res.status_code == 200
    body = res.json()
    assert body["keep_other_owner"] is True
    assert body["overlap_total"] == 0 and body["overlap_moved"] == 0
    assert body["other_skipped"] == 1
    assert any(n.startswith(f"{si.OTHER_HOLDER} 줄 1개는 건너뜀") for n in body["notes"])
    assert "강민준" not in res.text           # 메모 · 요약에도 없다

    assert _up(client, keep=False, dry=False).status_code == 200
    assert [r.user_id for r in _copies(db)] == [1]      # 원래 줄만, 사본 없음


# ── 팀원 업로드는 본인 줄만 고친다 ──────────────────────────────────────────

MONTH_ROW = ["", "", "", "", "", "", "", "", "", "", "", "8월", "", ""]
FULL_HEADER = ["그룹", "담당자", "이름", "직함", "투자사명", "초대", "관심도",
               "카톡방 참여여부", "휴대폰", "메모", "딜 소싱",
               "1차 딜소개", "IR 요청", "미팅"]


def _full(owner, name="홍길동", firm="가나다벤처스"):
    return [MONTH_ROW, FULL_HEADER,
            ["B", owner, name, "대표", firm, "완료", "상", "O", "010-0000-0099",
             "새 메모", "Series A", "8/13(목) 샘플가", "8/19(수) 2번", ""]]


def _post(client, rows, dry=False):
    return client.post(
        "/api/import/contacts",
        files={"file": ("현황.xlsx", _xlsx(rows),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"dry_run": "true" if dry else "false", "year": "2026"})


def _snapshot(db, contact_id):
    from sqlalchemy import inspect

    db.expire_all()
    row = db.get(VcContact, contact_id)
    return {a.key: getattr(row, a.key) for a in inspect(VcContact).column_attrs}


@pytest.fixture()
def third(db, users):
    db.add(User(id=3, name="박지호", phone="01000000003", role="user"))
    db.commit()


@pytest.mark.parametrize("owner", ["", "강민준", "박지호", "없는사람"])
def test_member_upload_leaves_other_rows_alone(client, db, held, third, owner):
    """담당자 칸이 비었든 · 그 줄 주인이든 · 다른 팀원이든 · 계정 없는 이름이든 남의 줄은 그대로."""
    from app.models import ContactActivity, SourcingContact

    before = _snapshot(db, held)
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    res = _post(client, _full(owner))
    assert res.status_code == 200, res.text
    assert res.json()["other_skipped"] == 1
    assert res.json()["created"] == 0 and res.json()["updated"] == 0

    assert _snapshot(db, held) == before
    assert [r.user_id for r in _copies(db)] == [1]
    assert db.query(ContactActivity).filter_by(contact_id=held).count() == 0
    assert db.query(SourcingContact).count() == 0


def test_member_upload_updates_own_rows_and_creates_only_in_own_list(client, db, held, third):
    """본인 줄은 예전처럼 고치고, 새 줄은 담당자 칸에 다른 팀원 이름이 있어도 본인 명단에."""
    from app.models import ContactActivity

    mine = VcContact(user_id=2, name="김서연", title="대표", firm="마바벤처스",
                     status="active")
    db.add(mine)
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})

    rows = _full("박지호", name="김서연", firm="마바벤처스")
    rows.append(_full("박지호", name="이새봄", firm="사아벤처스")[2])
    res = _post(client, rows)
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 1 and res.json()["created"] == 1
    assert res.json()["other_skipped"] == 0

    db.expire_all()
    got = db.get(VcContact, mine.id)
    assert got.user_id == 2
    assert got.invited_status == "완료" and got.interest_level == "상"
    assert got.phone == "010-0000-0099" and got.memo == "새 메모"
    assert db.query(ContactActivity).filter_by(contact_id=mine.id).count() > 0
    new = db.execute(select(VcContact).where(VcContact.name == "이새봄")).scalars().all()
    assert [r.user_id for r in new] == [2]
    assert db.query(VcContact).filter_by(user_id=3).count() == 0


def test_admin_upload_still_updates_found_row(client, db, held):
    """관리자 — 예전 그대로. 담당자 칸이 빈 시트도 찾은 줄을 고친다(소유는 그대로)."""
    db.get(User, 2).role = "admin"
    db.commit()
    client.post("/login", data={"phone": "01000000002", "password": DEMO_PASSWORD})
    res = _post(client, _full(""))
    assert res.status_code == 200, res.text
    assert res.json()["other_skipped"] == 0 and res.json()["updated"] == 1

    db.expire_all()
    got = db.get(VcContact, held)
    assert got.user_id == 1
    assert got.invited_status == "완료" and got.phone == "010-0000-0099"


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
