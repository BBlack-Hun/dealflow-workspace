"""계정 이름 바꾸기(`/account/name` · `services/account_rename`).

같은 사람의 표시 이름을 바꾸면 그 이름이 든 탭 · 담당자 칸이 같이 옮겨 간다. 여기서
못 박는 것.

1. 미리보기가 먼저다 — 지문(`expect`) 없이 바로 바뀌지 않는다.
2. 계정 · 그 계정의 탭 · 담당자 칸 다섯이 같이 바뀌고, 탭의 주인 연결이 남는다.
   관리자 시트 올리기도 새 이름으로 그 계정에 붙는다.
3. 메모 · 카톡방 이름 · 다른 낱말 속 같은 글자 · 남의 탭은 안 바뀐다.
4. 다른 계정과 같은 이름(대소문자 · 띄어쓰기 무시) · 예약어 · 빈 이름 · 긴 이름은 막힌다.
5. 팀원은 남의 이름을 못 바꾼다. 팀원 화면으로 보는 중에는 바꾸지 않는다.
6. 발송 중이면 막힌다.
7. 수정 기록이 **한 줄**로 남는다(누른 사람 · 몇 줄).

이름은 모두 지어낸 값이다(공개 저장소).
"""
from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import select

from .conftest import DEMO_PASSWORD

OLD = "가람"
NEW = "새벽"


@pytest.fixture()
def people(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    users["u1"].name = OLD
    admin = User(id=91, name="관리시험", phone="01000000091", role="admin",
                 password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(admin)
    db.commit()
    return {"admin": admin, "member": users["u1"], "other": users["u2"]}


@pytest.fixture()
def stage(db, people):
    """이름이 든 자리 — 바뀔 것과 안 바뀔 것을 섞어 둔다."""
    from app.models import (IrCompany, SeriesACompany, SheetOwner, SourcingContact,
                            VcContact)

    me, other = people["member"].id, people["other"].id
    tabs = {
        "own": SheetOwner(label=f"투자사 관리 현황 · {OLD}", user_id=me, assignee_name=OLD),
        "count": SheetOwner(label=f"{OLD} 12명", user_id=me),
        "inside": SheetOwner(label=f"나{OLD} 투자사", user_id=me),     # 다른 낱말 속
        "others": SheetOwner(label=f"{OLD} 넘겨받은 명단", user_id=other),  # 남의 탭
    }
    db.add_all(tabs.values())
    rows = {
        "a": VcContact(user_id=me, name="가상심사역", firm="가상벤처스",
                       source_sheet=tabs["own"].label, assignee_name=OLD,
                       memo=f"{OLD} 님이 통화함", kakao_room_name=f"{OLD} 방"),
        "b": VcContact(user_id=me, name="나중심사역", firm="나중파트너스",
                       source_sheet=f"{tabs['count'].label},{tabs['others'].label}",
                       assignee_name=OLD),
        "c": VcContact(user_id=me, name="안바뀜", firm="그대로캐피탈",
                       source_sheet=tabs["inside"].label, assignee_name=f"나{OLD}"),
    }
    db.add_all(rows.values())
    sourcing = [SourcingContact(bucket="가상갈래", name="소싱하나", assignee_name=OLD),
                SourcingContact(bucket="가상갈래", name="소싱둘",
                                assignee_name=f"보람 > {OLD}")]
    ir = [IrCompany(name="가상기업하나", assignee_name=f"보람 > 10/01 {OLD}"),
          IrCompany(name="가상기업둘", assignee_name=OLD),
          IrCompany(name="가상기업셋", assignee_name=f"나{OLD}")]
    series = [SeriesACompany(name="가상딜", assignee_name=OLD)]
    db.add_all(sourcing + ir + series)
    db.commit()
    return {"tabs": tabs, "rows": rows, "sourcing": sourcing, "ir": ir, "series": series}


@pytest.fixture()
def portal(db, users, people):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {"admin": sign_in("01000000091"), "member": sign_in("01000000001"),
            "other": sign_in("01000000002")}


def _expect(client, to: str, member: int = 0) -> str:
    q = f"/account/name?to={to}" + (f"&member={member}" if member else "")
    body = client.get(q).text
    found = re.search(r'name="expect" value="([0-9a-f]+)"', body)
    assert found, body[:2000]
    return found.group(1)


def _rename(client, to: str, member: int = 0):
    expect = _expect(client, to, member)
    return client.post("/account/name", data={"member": member, "name": to, "expect": expect},
                       follow_redirects=False)


# ── 1. 미리보기가 먼저다 ─────────────────────────────────────────────────────

def test_미리보기는_세기만_하고_바꾸지_않는다(db, portal, people, stage):
    from app.services import account_rename

    plan = account_rename.plan(db, people["member"], NEW)
    assert plan.tabs == [(f"투자사 관리 현황 · {OLD}", f"투자사 관리 현황 · {NEW}"),
                         (f"{OLD} 12명", f"{NEW} 12명")]
    assert plan.other_tabs == [f"{OLD} 넘겨받은 명단"]
    counts = {c["table"]: (c["equal"], c["history"]) for c in plan.columns}
    assert counts == {"vc_contacts": (2, 0), "sourcing_contacts": (1, 1),
                      "ir_companies": (1, 1), "series_a_companies": (1, 0),
                      "sheet_owners": (1, 0)}
    assert plan.total == 8 and not plan.problem

    body = portal["member"].get(f"/account/name?to={NEW}").text
    assert "탭 2개 · 담당자 칸 8줄" in body
    assert f"{OLD} 넘겨받은 명단" in body          # 남의 탭은 '안 바뀌는 것' 에 선다
    db.expire_all()
    assert people["member"].name == OLD


def test_지문_없이는_바뀌지_않는다(db, portal, people, stage):
    r = portal["member"].post("/account/name", data={"name": NEW}, follow_redirects=False)
    assert r.status_code == 303 and "msg=" in r.headers["location"]
    db.expire_all()
    assert people["member"].name == OLD


def test_미리_본_뒤_바뀐_것이_있으면_다시_묻는다(db, portal, people, stage):
    from app.models import VcContact

    expect = _expect(portal["member"], NEW)
    db.add(VcContact(user_id=people["member"].id, name="늦게온분", firm="늦은벤처스",
                     assignee_name=OLD))
    db.commit()
    r = portal["member"].post("/account/name", data={"name": NEW, "expect": expect},
                              follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert people["member"].name == OLD


# ── 2 · 3. 같이 바뀌는 것 / 안 바뀌는 것 ─────────────────────────────────────

def test_계정_탭_담당자_칸이_같이_바뀐다(db, portal, people, stage):
    from app.models import SheetOwner
    from app.services import sheet_owner

    r = _rename(portal["member"], NEW)
    assert r.status_code == 303, r.text
    db.expire_all()
    me = people["member"]
    assert me.name == NEW
    labels = {t.label: t.user_id for t in db.execute(select(SheetOwner)).scalars()}
    assert labels == {f"투자사 관리 현황 · {NEW}": me.id, f"{NEW} 12명": me.id,
                      f"나{OLD} 투자사": me.id, f"{OLD} 넘겨받은 명단": people["other"].id}
    rows = stage["rows"]
    assert rows["a"].source_sheet == f"투자사 관리 현황 · {NEW}"
    # 쉼표 목록은 조각 단위로 — 남의 탭 이름은 그대로다.
    assert rows["b"].source_sheet == f"{NEW} 12명,{OLD} 넘겨받은 명단"
    assert rows["a"].assignee_name == NEW and rows["b"].assignee_name == NEW
    assert [s.assignee_name for s in stage["sourcing"]] == [NEW, f"보람 > {NEW}"]
    assert [c.assignee_name for c in stage["ir"]] == [f"보람 > 10/01 {NEW}", NEW, f"나{OLD}"]
    assert stage["series"][0].assignee_name == NEW
    assert stage["tabs"]["own"].assignee_name == NEW
    # 탭의 주인 연결이 남는다 — 그 계정 명단이 그대로 그 계정 것이다.
    assert {c.id for c in sheet_owner.my_contacts(db, me)} >= {rows["a"].id, rows["b"].id}


def test_메모_카톡방_다른_낱말_속_글자는_안_바뀐다(db, portal, people, stage):
    _rename(portal["member"], NEW)
    db.expire_all()
    rows = stage["rows"]
    assert rows["a"].memo == f"{OLD} 님이 통화함"
    assert rows["a"].kakao_room_name == f"{OLD} 방"
    assert rows["c"].assignee_name == f"나{OLD}"
    assert rows["c"].source_sheet == f"나{OLD} 투자사"
    assert stage["ir"][2].assignee_name == f"나{OLD}"


def test_따라_바뀐_줄의_수정한_날짜는_그대로다(db, portal, people, stage):
    # 같은 초 안에 만들고 바꾸면 새로 찍혀도 같은 글자다 — 옛 날짜로 못 박고 본다.
    stamp = "2026-01-02T03:04:05+09:00"
    for row in (stage["ir"][0], stage["rows"]["a"], stage["tabs"]["own"]):
        row.updated_at = stamp
    db.commit()
    _rename(portal["member"], NEW)
    db.expire_all()
    assert stage["ir"][0].assignee_name == f"보람 > 10/01 {NEW}"
    assert stage["ir"][0].updated_at == stamp
    assert stage["rows"]["a"].updated_at == stamp
    assert stage["tabs"]["own"].label.endswith(NEW) and stage["tabs"]["own"].updated_at == stamp


def test_이어진_IR_칸을_통째로_옮겨_적지_않는다(db, portal, people, stage):
    """Series A 줄에만 이름이 든 경우 — 이름 토막만 바뀌고, 이어진 IR 칸은 그대로다.

    따라 고치기(`company_sync`)가 돌면 Series A 의 새 값이 IR 칸에 통째로 옮겨 적힌다.
    """
    from app.models import IrCompany, SeriesACompany

    ir = IrCompany(name="가상이음기업", assignee_name="다른담당")
    db.add(ir)
    db.flush()
    linked = SeriesACompany(name="가상이음기업", ir_company_id=ir.id,
                            assignee_name=f"{OLD} -> 다른담당")
    db.add(linked)
    db.commit()
    _rename(portal["member"], NEW)
    db.expire_all()
    assert linked.assignee_name == f"{NEW} -> 다른담당"
    assert ir.assignee_name == "다른담당"


def test_시트_올리기가_새_이름으로_그_계정에_붙는다(db, portal, people, stage):
    from app.models import VcContact
    from app.services import sheet_import as si

    _rename(portal["member"], NEW)
    parsed = si.parse_sheet_a([["번호", "그룹", "이름", "투자사명", "담당자"],
                               ["1", "", "새로온분", "새로운벤처스", NEW]], 2026)
    si.apply_sheet_a(db, parsed, user_id=people["admin"].id)
    db.commit()
    made = db.execute(select(VcContact).where(VcContact.name == "새로온분")).scalar_one()
    assert made.user_id == people["member"].id


# ── 4. 막히는 이름 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad, why", [
    ("", "새 이름을 적어 주세요"),
    ("가" * 21, "20자까지"),
    ("윤 서아", "다른 계정이 이미 쓰는 이름"),     # 띄어쓰기만 다른 남의 이름
    ("관리시험", "다른 계정이 이미 쓰는 이름"),
    ("관리자", "따로 쓰는 말"),
    ("010-1234-5678", "숫자만"),
    ("가,나", "쉼표"),
    (OLD, "지금 이름과 같습니다"),
])
def test_안_되는_이름은_막힌다(db, people, bad, why):
    from app.services import account_rename

    with pytest.raises(account_rename.RenameRefused) as exc:
        account_rename.check_name(db, people["member"], bad)
    assert why in str(exc.value)


def test_대소문자만_다른_남의_이름도_막힌다(db, people):
    from app.services import account_rename

    people["other"].name = "ALPHA"
    db.commit()
    with pytest.raises(account_rename.RenameRefused):
        account_rename.check_name(db, people["member"], "alpha")


def test_탭_이름이_겹치면_바꾸지_않는다(db, portal, people, stage):
    from app.models import SheetOwner
    from app.services import account_rename

    db.add(SheetOwner(label=f"{NEW} 12명", user_id=people["other"].id))
    db.commit()
    plan = account_rename.plan(db, people["member"], NEW)
    assert "같은 이름의 탭" in plan.problem
    body = portal["member"].get(f"/account/name?to={NEW}").text
    assert 'name="expect"' not in body


# ── 5. 권한 ──────────────────────────────────────────────────────────────────

def test_팀원은_남의_이름을_못_바꾼다(db, portal, people, stage):
    other = people["other"].id
    # 주소창이 여는 화면은 관리자 전용 안내창으로 답한다(`deps.admin_block_response`).
    body = portal["member"].get(f"/account/name?member={other}&to={NEW}").text
    assert "guard-modal" in body and 'name="expect"' not in body
    r = portal["member"].post("/account/name", data={"member": other, "name": NEW,
                                                     "expect": "x"}, follow_redirects=False)
    assert r.status_code == 403
    db.expire_all()
    assert people["other"].name == "윤서아"


def test_관리자는_남의_이름을_바꾸고_팀_현황으로_돌아간다(db, portal, people, stage):
    r = _rename(portal["admin"], NEW, member=people["member"].id)
    assert r.status_code == 303 and r.headers["location"].startswith("/team?msg=")
    db.expire_all()
    assert people["member"].name == NEW
    # 팀 현황 줄마다 이 화면으로 오는 길이 있다.
    assert f'/account/name?member={people["other"].id}' in portal["admin"].get("/team").text


def test_팀원_화면으로_보는_중에는_바꾸지_않는다(db, portal, people, stage):
    admin = portal["admin"]
    r = admin.post("/account/view-as", data={"member_id": people["member"].id},
                   follow_redirects=False)
    assert r.status_code == 303
    body = admin.get(f"/account/name?member={people['member'].id}&to={NEW}").text
    assert 'name="expect"' not in body
    r = admin.post("/account/name", data={"member": people["member"].id, "name": NEW,
                                          "expect": "x"}, follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    assert people["member"].name == OLD


# ── 6. 발송 중 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("job_status, item_status", [("running", "pending"),
                                                     ("queued", "pending"),
                                                     ("done", "sending")])
def test_발송_중이면_막힌다(db, portal, people, stage, job_status, item_status):
    from app.models import SendItem, SendJob
    from app.services import account_rename

    job = SendJob(user_id=people["other"].id, status=job_status)
    db.add(job)
    db.flush()
    db.add(SendItem(job_id=job.id, contact_id=stage["rows"]["a"].id, room_name="가상방",
                    message="가상 문구", status=item_status))
    db.commit()
    plan = account_rename.plan(db, people["member"], NEW)
    assert "발송 중" in plan.problem
    with pytest.raises(account_rename.RenameRefused):
        account_rename.apply(db, people["member"], NEW, actor_user_id=people["member"].id,
                             expect=plan.fingerprint)
    db.rollback()
    assert 'name="expect"' not in portal["member"].get(f"/account/name?to={NEW}").text


# ── 7. 수정 기록 ─────────────────────────────────────────────────────────────

def test_수정_기록이_한_줄로_남는다(db, portal, people, stage):
    from app.models import EditLog

    _rename(portal["admin"], NEW, member=people["member"].id)
    logs = db.execute(select(EditLog)).scalars().all()
    assert len(logs) == 1, [(r.table_name, r.row_label) for r in logs]
    log = logs[0]
    assert (log.actor_user_id, log.target_user_id) == (people["admin"].id, people["member"].id)
    assert log.table_name == "users" and log.scope == "others"
    changes = {c["field"]: c for c in json.loads(log.changes_json)}
    assert changes["name"]["before"] == OLD and changes["name"]["after"] == NEW
    assert changes["rename_ir_companies"]["after"] == f"{NEW} · 2줄"
    body = portal["admin"].get("/team/edit-log").text
    assert "같이 바꾼 탭" in body and "담당자 칸 · IR 기업 현황" in body


def test_자기_이름을_바꿔도_남는다(db, portal, people, stage):
    from app.models import EditLog

    _rename(portal["member"], NEW)
    log = db.execute(select(EditLog)).scalar_one()
    assert (log.actor_user_id, log.target_user_id, log.scope) == (
        people["member"].id, people["member"].id, "mine")
