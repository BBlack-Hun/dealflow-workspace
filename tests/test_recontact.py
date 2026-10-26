"""보류한 2차·후속 미팅 — 90일마다 재접촉 시기(개선 과제 #68).

판정은 `services/recontact.due` 한 곳이고, 오늘 할 일 · 매출예상리스트가 같은 목록을 그린다.
여기서 못 박는 것:

1. 보류만 뜬다 — 거절 · 투자 검토는 안 뜨고, 뒤 미팅을 거절로 마쳤으면 빠진다.
2. 미팅 날부터 90 · 180일 주기.
3. 그 뒤 미팅 · 결과 문의 기록 · IR 요청 · IR 전달 이력이 있으면 그날부터 다시 센다
   (같은 투자사 × 같은 기업만 — 다른 기업 일은 안 센다).
4. 1차 미팅은 뜨지 않는다.
5. 담당 범위 — 팀원은 자기 미팅만, 관리자는 매출예상리스트의 범위 고르기를 따른다.

이름 · 회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD

MET = date(2026, 3, 2)


def _vc(db, name, firm="가나벤처스", user_id=1):
    from app.models import VcContact

    row = VcContact(user_id=user_id, source_sheet="시험 명단", name=name, firm=firm)
    db.add(row)
    db.commit()
    return row


def _meet(db, contact, day=MET, kind="second", status="done", outcome="hold",
          company="샘플가나랩", user_id=1):
    from app.models import Meeting

    row = Meeting(user_id=user_id, contact_id=contact.id, company_name=company,
                  scheduled_at=day.isoformat(), kind=kind, status=status, outcome=outcome)
    db.add(row)
    db.commit()
    return row


def _due(db, today, owners=(1,)):
    from app.services import recontact

    return recontact.due(db, owners, today)


# --- 1 · 4. 무엇이 뜨나 ---------------------------------------------------------

def test_보류만_뜨고_거절_투자검토_1차는_안_뜬다(db, users):
    a, b, c, d = (_vc(db, n, firm=f) for n, f in
                  (("심사가", "가나벤처스"), ("심사나", "나다투자"),
                   ("심사다", "다라파트너스"), ("심사라", "라마캐피탈")))
    held = _meet(db, a)
    _meet(db, b, outcome="pass")
    _meet(db, c, outcome="investing")
    _meet(db, d, kind="first")
    etc = _meet(db, _vc(db, "심사마", firm="마바인베스트"), kind="etc")
    found = _due(db, MET + timedelta(days=90))
    assert [r["meeting_id"] for r in found] == [held.id, etc.id]
    assert found[0]["kind_label"] == "2차 미팅" and found[1]["kind_label"] == "기타"


def test_뒤_미팅을_거절로_마쳤으면_빠지고_보류면_그_미팅이_뜬다(db, users):
    vc = _vc(db, "심사가")
    _meet(db, vc)
    later = _meet(db, _vc(db, "심사나"), day=MET + timedelta(days=20), kind="etc",
                  outcome="pass")
    assert _due(db, MET + timedelta(days=200)) == [], "같은 투자사가 그 뒤 거절했다"

    later.outcome = "hold"
    db.commit()
    assert [r["meeting_id"] for r in _due(db, MET + timedelta(days=200))] == [later.id]


# --- 2. 90 · 180일 주기 ---------------------------------------------------------

def test_미팅_날부터_90일_180일마다(db, users):
    _meet(db, _vc(db, "심사가"))
    assert _due(db, MET + timedelta(days=89)) == []
    first = _due(db, MET + timedelta(days=90))[0]
    assert (first["due"], first["days"]) == ((MET + timedelta(days=90)).isoformat(), 90)
    assert first["last_contact"] == MET.isoformat()
    assert _due(db, MET + timedelta(days=179))[0]["due"] == (MET + timedelta(days=90)).isoformat()
    assert _due(db, MET + timedelta(days=185))[0]["due"] == (MET + timedelta(days=180)).isoformat()


# --- 3. 연락이 있으면 그날부터 다시 센다 ----------------------------------------

def test_그_뒤_미팅을_잡았으면_그날부터_다시_센다(db, users):
    _meet(db, _vc(db, "심사가"))
    # 같은 회사의 다른 심사역 · 아직 안 한 미팅
    _meet(db, _vc(db, "심사나"), day=MET + timedelta(days=60), status="scheduled",
          outcome=None)
    assert _due(db, MET + timedelta(days=100)) == []
    assert _due(db, MET + timedelta(days=150))[0]["due"] == \
        (MET + timedelta(days=150)).isoformat()


def test_결과_문의_기록과_IR_요청은_연락으로_센다(db, users):
    from app.models import IrRequest

    vc = _vc(db, "심사가")
    meeting = _meet(db, vc)
    today = MET + timedelta(days=95)
    assert _due(db, today)

    meeting.followup_at = (MET + timedelta(days=10)).isoformat()
    db.commit()
    assert _due(db, today) == [], "결과 문의를 적은 날부터 90일"

    meeting.followup_at = None
    db.add(IrRequest(user_id=1, contact_id=vc.id, company_name="샘플가나랩",
                     requested_at=(MET + timedelta(days=30)).isoformat()))
    db.commit()
    assert _due(db, today) == []
    assert _due(db, MET + timedelta(days=120))[0]["last_contact"] == \
        (MET + timedelta(days=30)).isoformat()


def test_IR_전달_이력은_같은_기업만_센다(db, users):
    from app.models import ContactActivity

    vc = _vc(db, "심사가")
    _meet(db, vc)
    today = MET + timedelta(days=95)

    def deliver(names):
        db.add(ContactActivity(contact_id=vc.id, kind="ir_delivery", content="IR 자료 전달",
                               happened_at=(MET + timedelta(days=40)).isoformat(),
                               company_names=json.dumps(names, ensure_ascii=False)))
        db.commit()

    deliver(["샘플다라소재"])
    assert _due(db, today), "다른 기업 자료는 이 기업 연락이 아니다"
    deliver(["샘플다라소재", "샘플 가나랩"])
    assert _due(db, today) == []


def test_딜_소개는_연락으로_세지_않는다(db, users):
    from app.models import ContactActivity

    vc = _vc(db, "심사가")
    _meet(db, vc)
    db.add(ContactActivity(contact_id=vc.id, kind="deal_intro", content="딜 소개",
                           happened_at=(MET + timedelta(days=40)).isoformat(),
                           company_names=json.dumps(["샘플가나랩"], ensure_ascii=False)))
    db.commit()
    assert _due(db, MET + timedelta(days=95))


# --- 5. 담당 범위 · 화면 --------------------------------------------------------

@pytest.fixture()
def portal(db, users):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=91, name="관리자시험", phone="01000000091", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    app = create_app()

    def sign_in(phone):
        client = TestClient(app)
        client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
        return client

    return {"u1": sign_in("01000000001"), "u2": sign_in("01000000002"),
            "admin": sign_in("01000000091")}


def test_오늘_할_일은_자기_미팅만(db, users):
    from app.services import recontact, today

    _meet(db, _vc(db, "심사가"))
    _meet(db, _vc(db, "심사나", firm="나다투자", user_id=2), company="샘플다라소재", user_id=2)
    day = MET + timedelta(days=90)
    mine = [i for i in today.build(db, users["u1"], day)["items"]
            if i["title"] == recontact.TITLE]
    assert [(i["detail"], i["href"], i["count"]) for i in mine] == \
        [("심사가(가나벤처스 · 샘플가나랩)", "/report/forecast#recontact", 1)]
    other = [i for i in today.build(db, users["u2"], day)["items"]
             if i["title"] == recontact.TITLE]
    assert other[0]["detail"] == "심사나(나다투자 · 샘플다라소재)"


def test_매출예상리스트는_화면_범위를_따르고_주인만_다시_기록한다(portal, db):
    from app.models import Meeting

    long_ago = date.today() - timedelta(days=100)
    mine = _meet(db, _vc(db, "심사가"), day=long_ago)
    _meet(db, _vc(db, "심사나", firm="나다투자", user_id=2), day=long_ago,
          company="샘플다라소재", user_id=2)

    page = portal["u1"].get("/report/forecast").text
    assert "재접촉 시기 — 보류한 2차·후속 미팅" in page
    assert "샘플가나랩" in page and "샘플다라소재" not in page
    assert f"2차 미팅 {long_ago.isoformat()} 보류 · 100일 지남" in page
    assert f'action="/ir/meetings/{mine.id}/followup"' in page

    assert "재접촉 시기" not in portal["admin"].get("/report/forecast").text, "관리자 기본은 내 것"
    team = portal["admin"].get("/report/forecast?scope=team").text
    assert "샘플가나랩" in team and "샘플다라소재" in team
    assert "강민준 담당" in team and 'name="back" value="forecast"' not in team, \
        "남의 미팅은 적지 못한다"
    member = portal["admin"].get("/report/forecast?member=2").text
    assert "샘플다라소재" in member and "샘플가나랩" not in member

    r = portal["u1"].post(f"/ir/meetings/{mine.id}/followup",
                          data={"back": "forecast", "note": "다음 분기에 다시"},
                          follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/report/forecast#recontact"
    db.expire_all()
    assert db.get(Meeting, mine.id).followup_at == date.today().isoformat()
    assert "재접촉 시기" not in portal["u1"].get("/report/forecast").text, "적은 날부터 다시 센다"
