"""관리자의 [탭 삭제] — 투자사 관리 현황의 명단(탭) 하나를 지운다.

탭을 지우면서 **그 탭에만 있는 투자사도 함께 지운다.** 다른 탭에도 있는
사람은 남고 이 탭 표시만 빠진다. 잠가야 하는 것.

1. **관리자만.** 팀원은 자기 탭이라도 못 지운다 — 서버가 403 으로 막고, 화면에
   단추도 없다.
2. **확인 없이는 안 지워진다.** `confirm` 없이 부르면 세기만 한다 — 이 탭에만
   있는 사람 · 남는 사람 · 함께 사라지는 활동 이력.
3. **이 탭에만 있는 사람은 지워지고, 다른 탭에도 있는 사람은 남는다**(이 탭
   이름만 빠진다). 이름이 비슷한 다른 탭(`… 2`)은 건드리지 않는다.
4. **딸린 것이 담당자 줄 지우기와 같이 된다.** 활동 이력은 함께 사라지고,
   발송 기록 등이 걸린 사람이 이 탭에만 있으면 통째로 막는다.
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


def test_이력이_걸린_사람이_이_탭에만_있으면_통째로_막는다(boss, db, rows):
    from app.models import SendItem, SendJob, SheetOwner

    job = SendJob(user_id=1, kind="deal_intro", status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=rows["가담당"].id,
                    room_name="가담당 방", message="", status="sent"))
    db.commit()

    plan = _delete(boss).json()["plan"]
    assert [b["name"] for b in plan["blocked"]] == ["가담당"]
    assert "발송 기록 1건" in plan["blocked"][0]["why"]

    r = _delete(boss, confirm=True)
    assert r.status_code == 409, "발송 이력이 걸린 사람을 지웠습니다"
    assert len(_names(db)) == 5, "막았는데 일부가 지워졌습니다"
    assert db.query(SheetOwner).filter(SheetOwner.label == TAB).count() == 1


def test_다른_탭에도_있는_사람의_이력은_막지_않는다(boss, db, rows):
    """겹친 사람은 지우지 않으므로 그 사람의 이력은 탭 지우기를 막지 않는다."""
    from app.models import SendItem, SendJob

    job = SendJob(user_id=1, kind="deal_intro", status="done")
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=rows["다담당"].id,
                    room_name="다담당 방", message="", status="sent"))
    db.commit()

    assert _delete(boss).json()["plan"]["blocked"] == []
    assert _delete(boss, confirm=True).status_code == 200
    assert "다담당" in _names(db)


# ═══════════════════════════════════════════════════════════════════════════
# 6. 수정 로그
# ═══════════════════════════════════════════════════════════════════════════

def test_수정_로그에_누가_어느_탭_몇_명이_남는다(boss, db, rows, admin):
    from app.models import EditLog

    assert _delete(boss, confirm=True).status_code == 200
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

    # 사람은 줄마다 따로 남는다(담당자 줄 지우기와 같다).
    gone = db.query(EditLog).filter(EditLog.table_name == "vc_contacts",
                                    EditLog.action == "delete").count()
    assert gone == 2
