"""관리자의 [탭 삭제] — 투자사 관리 현황의 명단(탭) 하나를 지운다.

탭을 지우면서 **그 탭에만 있는 투자사도 함께 지운다.** 다른 탭에도 있는
사람은 남고 이 탭 표시만 빠진다. 잠가야 하는 것.

1. **관리자만.** 팀원은 자기 탭이라도 못 지운다 — 서버가 403 으로 막고, 화면에
   단추도 없다.
2. **확인 없이는 안 지워진다.** `confirm` 없이 부르면 세기만 한다 — 이 탭에만
   있는 사람 · 남는 사람 · 함께 사라지는 활동 이력.
3. **이 탭에만 있는 사람은 지워지고, 다른 탭에도 있는 사람은 남는다**(이 탭
   이름만 빠진다). 이름이 비슷한 다른 탭(`… 2`)은 건드리지 않는다.
4. **이 탭에만 있는 사람은 이력째 지운다**(사용자 결정 — 한 줄 지우기와
   다르다). 활동 이력 · 발송 기록 · 후속 발송 · IR 요청 · 미팅이 남김없이
   사라지고 고아가 남지 않는다. 다만 **지금 나가는 중인 회차**에 실린 사람이
   있으면 막고 그 회차를 말한다.
4-1. **지우기 직전에 DB 를 뜬다.** 못 뜨면 지우지 않는다.
5. **탭이 다시 서지 않는다.** 설정 줄 · 달 칸 · 달 표시까지 치운다.
6. **수정 로그에 누가 · 어느 탭 · 몇 명이 남는다.**

이름 · 회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from .conftest import DEMO_PASSWORD

TAB = "가나다벤처스 시험 탭"
OTHER = "투자사 풀 시험"
LOOKALIKE = "가나다벤처스 시험 탭 2"


@pytest.fixture(autouse=True)
def snap_dir(tmp_path, monkeypatch):
    """지우기 직전 백업이 떨어질 자리 — 검사마다 빈 폴더."""
    from app.services import backup

    where = tmp_path / "snaps"
    where.mkdir()
    monkeypatch.setattr(backup, "backup_dir", lambda: where)
    return where


@pytest.fixture()
def admin(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=91, name="관리자시험", phone="01000000091", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def rows(db, users, admin):
    """TAB 에만 둘(하나는 감춘 줄) · TAB+OTHER 하나 · OTHER 하나 · 비슷한 이름 하나."""
    from app.models import (ContactActivity, ContactColumn, MonthlyColumnRun,
                            SheetOwner, VcContact)
    from app.services import contact_columns as cc
    from app.services.monthly_columns import CONTACT

    u1 = users["u1"]
    db.add_all([
        SheetOwner(label=TAB, user_id=u1.id, layout=cc.INVESTOR),
        SheetOwner(label=OTHER, user_id=None, layout=cc.INVESTOR),
        SheetOwner(label=LOOKALIKE, user_id=u1.id, layout=cc.INVESTOR),
    ])
    made = {}
    for name, sheet, hidden in (("가담당", TAB, 0),
                                ("나담당", TAB, 1),
                                ("다담당", f"{TAB},{OTHER}", 0),
                                ("라담당", OTHER, 0),
                                ("마담당", LOOKALIKE, 0)):
        row = VcContact(user_id=u1.id, source_sheet=sheet, name=name,
                        firm="가나다벤처스", is_hidden=hidden)
        db.add(row)
        made[name] = row
    db.flush()
    db.add_all([
        ContactActivity(contact_id=made["가담당"].id, month="2026-08",
                        kind="deal_intro", content="1회차"),
        ContactActivity(contact_id=made["나담당"].id, month="2026-08",
                        kind="deal_intro", content="1회차"),
        ContactActivity(contact_id=made["다담당"].id, month="2026-08",
                        kind="deal_intro", content="1회차"),
        ContactColumn(sheet=TAB, label="8월 리마인드", position=0),
        ContactColumn(sheet=OTHER, label="8월 리마인드", position=0),
        MonthlyColumnRun(target=CONTACT, scope=TAB, month="2026-08"),
    ])
    db.commit()
    return made


def _sign_in(phone: str):
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())
    c.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return c


@pytest.fixture()
def boss(rows):
    return _sign_in("01000000091")


@pytest.fixture()
def member(rows):
    """TAB 의 주인인 팀원(u1) — 자기 탭이라도 못 지운다."""
    return _sign_in("01000000001")


def _delete(client, label=TAB, confirm=None):
    body = {"label": label}
    if confirm is not None:
        body["confirm"] = confirm
    return client.post("/api/contacts/sheets/delete", json=body)


def _names(db):
    from app.models import VcContact

    db.expire_all()
    return sorted(r.name for r in db.query(VcContact).all())


# ═══════════════════════════════════════════════════════════════════════════
# 1. 관리자만
# ═══════════════════════════════════════════════════════════════════════════

def test_팀원은_자기_탭이라도_못_지운다(member, db, rows):
    for confirm in (None, True):
        r = _delete(member, confirm=confirm)
        assert r.status_code == 403, f"팀원이 탭을 지웠습니다: {r.status_code}"
    assert len(_names(db)) == 5, "403 인데 사람이 사라졌습니다"


def test_단추는_관리자_화면에만_선다(member, boss, rows):
    url = f"/contacts?sheet={quote(TAB)}"
    assert 'id="tab-delete-btn"' in boss.get(url).text, "관리자 화면에 [탭 삭제] 가 없습니다"
    assert 'id="tab-delete-btn"' not in member.get(url).text, (
        "팀원 화면에 [탭 삭제] 가 서 있습니다")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 확인 없이는 세기만 한다
# ═══════════════════════════════════════════════════════════════════════════

def test_확인_없이_부르면_세기만_한다(boss, db, rows):
    r = _delete(boss)
    assert r.status_code == 200
    out = r.json()
    assert out["confirmed"] is False
    plan = out["plan"]
    assert plan["only"] == 2, "이 탭에만 있는 사람 수가 틀립니다(감춘 줄도 셉니다)"
    assert plan["shared"] == 1, "다른 탭에도 있는 사람 수가 틀립니다"
    assert plan["activities"] == 2, (
        "함께 사라지는 활동 이력은 이 탭에만 있는 사람 것만 셉니다")
    assert plan["blocked"] == []
    assert len(_names(db)) == 5, "세기만 했는데 사람이 사라졌습니다"


def test_없는_탭과_직접_추가는_못_지운다(boss, db, rows):
    assert _delete(boss, label="없는 탭", confirm=True).status_code == 400
    from app.models import VcContact

    db.add(VcContact(user_id=1, source_sheet="", name="바담당", firm="가나다벤처스"))
    db.commit()
    from app.services.sheet_owner import MANUAL_SHEET

    assert _delete(boss, label=MANUAL_SHEET, confirm=True).status_code == 400
    assert "바담당" in _names(db)


# ═══════════════════════════════════════════════════════════════════════════
# 3·4·5. 지운다
# ═══════════════════════════════════════════════════════════════════════════

def test_이_탭에만_있는_사람은_지우고_겹친_사람은_탭_표시만_뺀다(boss, db, rows):
    from app.models import (ContactActivity, ContactColumn, MonthlyColumnRun,
                            SheetOwner, VcContact)

    keep_id = rows["다담당"].id
    gone_ids = [rows["가담당"].id, rows["나담당"].id]

    r = _delete(boss, confirm=True)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["deleted"], out["kept"]) == (2, 1)
    assert out["back"] == "/contacts"

    assert _names(db) == ["다담당", "라담당", "마담당"]
    kept = db.get(VcContact, keep_id)
    assert kept.source_sheet == OTHER, (
        f"겹친 사람에게서 이 탭 이름만 빠져야 합니다: {kept.source_sheet!r}")
    assert db.query(VcContact).filter(
        VcContact.name == "마담당").one().source_sheet == LOOKALIKE, (
        "이름이 비슷한 다른 탭까지 건드렸습니다")

    # 활동 이력 — 지운 사람 것은 사라지고(고아 없음) 남은 사람 것은 그대로.
    assert db.query(ContactActivity).filter(
        ContactActivity.contact_id.in_(gone_ids)).count() == 0, "고아 활동 이력이 남았습니다"
    assert db.query(ContactActivity).filter(
        ContactActivity.contact_id == keep_id).count() == 1, "남은 사람의 이력까지 지웠습니다"

    # 탭이 다시 서지 않게 — 설정 줄 · 달 칸 · 달 표시.
    labels = {s.label for s in db.query(SheetOwner).all()}
    assert labels == {OTHER, LOOKALIKE}, f"설정 줄이 남았거나 엉뚱한 것을 지웠습니다: {labels}"
    assert db.query(ContactColumn).filter(ContactColumn.sheet == TAB).count() == 0
    assert db.query(ContactColumn).filter(ContactColumn.sheet == OTHER).count() == 1
    assert db.query(MonthlyColumnRun).filter(MonthlyColumnRun.scope == TAB).count() == 0

    html = boss.get("/contacts?sheet=all").text
    assert TAB + "<" not in html and f'data-label="{TAB}"' not in html, (
        "지운 탭이 화면에 다시 섰습니다")


def _history(db, rows, job_status="done", item_status="sent"):
    """가담당 · 나담당(이 탭에만)과 라담당(다른 탭)에 이력을 하나씩 건다.

    한 회차에 가담당 건과 라담당 건이 함께 실린다 — 회차는 남고 수만 줄어야 한다.
    """
    from app.models import IrRequest, Meeting, SendItem, SendJob, SendSequence

    job = SendJob(user_id=1, kind="deal_intro", status=job_status, total=2, sent=2)
    db.add(job)
    db.flush()
    db.add_all([
        SendItem(job_id=job.id, contact_id=rows["가담당"].id,
                 room_name="가담당 방", message="", status=item_status),
        SendItem(job_id=job.id, contact_id=rows["라담당"].id,
                 room_name="라담당 방", message="", status="sent"),
        SendSequence(user_id=1, contact_id=rows["가담당"].id),
        IrRequest(user_id=1, contact_id=rows["가담당"].id,
                  company_name="시험기업", requested_at="2026-08-20"),
        IrRequest(user_id=1, contact_id=rows["나담당"].id,
                  company_name="시험기업", requested_at="2026-08-21"),
        Meeting(user_id=1, contact_id=rows["나담당"].id,
                scheduled_at="2026-08-28"),
        Meeting(user_id=1, contact_id=rows["라담당"].id,
                scheduled_at="2026-08-29"),
    ])
    db.commit()
    return job


#: 담당자 줄을 가리키는 표 전부 — 하나라도 빠지면 고아를 못 잡는다.
LINKED_TABLES = ("contact_activities", "send_items", "send_sequences",
                 "ir_requests", "meetings")


def test_가리키는_표를_빠짐없이_지운다():
    """`vc_contacts` 를 가리키는 표가 늘면 탭 지우기 목록에도 들어가야 한다."""
    from app.db import Base
    from app.routers.contacts import TAB_PURGE_LINKS

    pointing = {t.name for t in Base.metadata.sorted_tables
                for fk in t.foreign_keys if fk.column.table.name == "vc_contacts"}
    purged = {model.__tablename__ for _k, model, _l in TAB_PURGE_LINKS}
    assert pointing == purged == set(LINKED_TABLES), (
        f"탭 지우기가 안 지우는 표가 있습니다: {pointing - purged}")


def test_이력이_걸린_사람도_이력째_지우고_고아를_남기지_않는다(boss, db, rows):
    from sqlalchemy import text

    from app.models import SendJob

    job = _history(db, rows)

    plan = _delete(boss).json()["plan"]
    assert plan["blocked"] == [] and plan["live_jobs"] == [], "이력 때문에 막았습니다"
    assert (plan["only"], plan["shared"]) == (2, 1)
    assert (plan["activities"], plan["sends"], plan["sequences"],
            plan["ir_requests"], plan["meetings"]) == (2, 1, 1, 2, 1), plan

    r = _delete(boss, confirm=True)
    assert r.status_code == 200, r.text
    assert _names(db) == ["다담당", "라담당", "마담당"]

    # 고아가 없다 — 가리키는 표마다 없는 사람을 가리키는 줄이 0.
    for table in LINKED_TABLES:
        n = db.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE contact_id IS NOT NULL "
            "AND contact_id NOT IN (SELECT id FROM vc_contacts)")).scalar()
        assert n == 0, f"{table} 에 고아 {n}줄이 남았습니다"
    assert db.execute(text("PRAGMA foreign_key_check")).all() == []

    # 남은 사람 것은 그대로.
    keep = rows["라담당"].id
    for table, want in (("send_items", 1), ("meetings", 1)):
        n = db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE contact_id=:c"),
                       {"c": keep}).scalar()
        assert n == want, f"남은 사람의 {table} 까지 지웠습니다"

    # 회차는 남고 수만 남은 건으로 맞춘다.
    db.expire_all()
    left = db.get(SendJob, job.id)
    assert left is not None and left.status == "done"
    assert (left.total, left.sent, left.failed) == (1, 1, 0)


def test_비어_버린_대기_회차는_취소로_둔다(boss, db, rows):
    from app.models import SendItem, SendJob

    job = SendJob(user_id=1, kind="deal_intro", status="draft", total=1,
                  scheduled_at="2026-12-01T09:00:00+09:00")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=rows["가담당"].id,
                    room_name="가담당 방", message="", status="pending"))
    db.commit()

    r = _delete(boss, confirm=True)
    assert r.status_code == 200, r.text
    assert r.json()["canceled_jobs"] == 1
    db.expire_all()
    left = db.get(SendJob, job.id)
    assert (left.status, left.total) == ("canceled", 0), (
        "빈 예약 회차가 그대로 남아 예약 시각에 풀립니다")


@pytest.mark.parametrize("job_status,item_status", [
    ("queued", "pending"), ("running", "pending"), ("paused", "pending"),
    ("done", "sending"),
])
def test_나가는_중인_회차에_실린_사람이_있으면_막는다(boss, db, rows, snap_dir,
                                         job_status, item_status):
    from app.models import SheetOwner

    job = _history(db, rows, job_status=job_status, item_status=item_status)

    live = _delete(boss).json()["plan"]["live_jobs"]
    assert [j["job_id"] for j in live] == [job.id]

    r = _delete(boss, confirm=True)
    assert r.status_code == 409, "나가는 중인 회차의 사람을 지웠습니다"
    assert f"#{job.id}" in r.json()["detail"], "어느 회차인지 말하지 않습니다"
    assert len(_names(db)) == 5, "막았는데 일부가 지워졌습니다"
    assert db.query(SheetOwner).filter(SheetOwner.label == TAB).count() == 1
    assert list(snap_dir.iterdir()) == [], "막았는데 백업을 떴습니다"


def test_지우기_직전에_백업을_뜨고_이름을_알려_준다(boss, db, rows, snap_dir):
    import sqlite3

    _history(db, rows)
    r = _delete(boss, confirm=True)
    assert r.status_code == 200, r.text
    name = r.json()["snapshot"]
    assert name.startswith("snapshot-before-tab-delete-") and name.endswith(".db")
    files = [p.name for p in snap_dir.iterdir()]
    assert files == [name], files

    # 지우기 **전** 상태가 담겨 있다 — 다섯 사람 · 지운 이력까지.
    conn = sqlite3.connect(snap_dir / name)
    try:
        assert conn.execute("SELECT COUNT(*) FROM vc_contacts").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM ir_requests").fetchone()[0] == 2
    finally:
        conn.close()

    from app.services import backup

    assert backup._kind_of(name) == "탭 삭제 직전"


def test_백업을_못_뜨면_지우지_않는다(boss, db, rows, monkeypatch):
    from app.models import SheetOwner
    from app.services import backup

    _history(db, rows)

    def broken(dst, src=None, timeout=30.0):
        raise backup.BackupError("디스크가 가득 찼습니다")

    monkeypatch.setattr(backup, "snapshot", broken)
    r = _delete(boss, confirm=True)
    assert r.status_code == 500
    assert "백업" in r.json()["detail"]
    assert len(_names(db)) == 5, "백업 없이 지웠습니다"
    assert db.query(SheetOwner).filter(SheetOwner.label == TAB).count() == 1


def test_다른_탭에도_있는_사람의_이력은_그대로_둔다(boss, db, rows):
    """겹친 사람은 지우지 않으므로 그 사람의 이력도 세지 않고 지우지 않는다."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=1, kind="deal_intro", status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=rows["다담당"].id,
                    room_name="다담당 방", message="", status="sent"))
    db.commit()

    assert _delete(boss).json()["plan"]["sends"] == 0, (
        "남는 사람의 발송 기록까지 지울 것으로 셉니다")
    assert _delete(boss, confirm=True).status_code == 200
    assert "다담당" in _names(db)
    assert db.query(SendItem).count() == 1, "남는 사람의 발송 기록을 지웠습니다"


# ═══════════════════════════════════════════════════════════════════════════
# 6. 수정 로그
# ═══════════════════════════════════════════════════════════════════════════

def test_수정_로그에_누가_어느_탭_몇_명이_남는다(boss, db, rows, admin):
    from app.models import EditLog

    _history(db, rows)
    r = _delete(boss, confirm=True)
    assert r.status_code == 200
    db.expire_all()
    logs = db.query(EditLog).filter(EditLog.table_name == "sheet_owners").all()
    assert len(logs) == 1, f"탭 지우기가 한 줄로 남지 않았습니다: {len(logs)}"
    log = logs[0]
    assert log.actor_user_id == admin.id
    assert log.action == "delete"
    assert log.row_label == TAB
    got = {c["field"]: c["before"] for c in json.loads(log.changes_json)}
    assert got["label"] == TAB
    assert got["tab_deleted_contacts"] == 2
    assert got["tab_kept_contacts"] == 1
    assert got["tab_deleted_activities"] == 2
    assert got["tab_deleted_columns"] == 1
    assert got["tab_deleted_sends"] == 1
    assert got["tab_deleted_sequences"] == 1
    assert got["tab_deleted_ir_requests"] == 2
    assert got["tab_deleted_meetings"] == 1
    assert got["tab_snapshot"] == r.json()["snapshot"]

    # 사람은 줄마다 따로 남는다(담당자 줄 지우기와 같다).
    gone = db.query(EditLog).filter(EditLog.table_name == "vc_contacts",
                                    EditLog.action == "delete").count()
    assert gone == 2
