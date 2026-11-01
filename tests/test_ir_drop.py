"""#116 2차 — IR 전달 뒤 피드백 없음 · 드랍 추적(B안, 11/01 결정).

못 박는 것.

1. 드랍 의심 — 전달 완료 뒤 21일 · 같은 투자사에 완료 · 예정(지난 예정 포함) 미팅 없음.
   미팅 요청을 보냈으면 `어레인지중` 이고 그날부터 다시 21일.
2. 드랍(`lost`) — 미팅 없음 · 드랍 의심에서 빠지고 칩으로 본다. 드랍 뒤 새 요청이 오면 다시 산다.
   보낸 것이라 업무 보고 전달 수 · 명단 기록 겹침은 그대로 센다.
3. [드랍 확정] · [드랍 취소] — 팀원은 제 것만, 관리자는 팀 전체. 돌아갈 곳은 그 화면만.
4. 명단 기록 — 명단 칸에만 적힌 `…전달` 이 줄로 선다(앱 기록과 겹치면 안 선다).
   [앱 기록으로] 가 앱 요청으로 옮긴다 — 서버가 칸을 다시 읽어 있을 때만.
5. 업무 보고 IR 판에 `전달 후 21일 미팅 없음 N건` 링크.

이름 · 회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from .conftest import DEMO_PASSWORD

TODAY = date.today()


def _ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


@pytest.fixture()
def seed(db, users):
    from app.models import ContactActivity, IrCompany, IrRequest, Meeting, VcContact

    u1, u2 = users["u1"].id, users["u2"].id
    hong = VcContact(user_id=u1, name="홍길동", title="심사역", firm="가나다벤처스")
    lee = VcContact(user_id=u1, name="이몽룡", title="이사", firm="라마바파트너스")
    lim = VcContact(user_id=u1, name="임꺽정", title="심사역", firm="라마바파트너스")
    park = VcContact(user_id=u2, name="성춘향", title="팀장", firm="사아자캐피탈")
    cos = {n: IrCompany(name=n) for n in ("샘플애그", "테스트랩", "보기팜", "예시바이오", "견본솔루션")}
    db.add_all([hong, lee, lim, park, *cos.values()])
    db.flush()

    def req(user, contact, company, req_days, deliv_days=None, status=None):
        row = IrRequest(user_id=user, contact_id=contact.id, company_id=cos[company].id,
                        company_name=company, requested_at=_ago(req_days),
                        status=status or ("delivered" if deliv_days is not None else "open"),
                        delivered_at=_ago(deliv_days) if deliv_days is not None else None)
        db.add(row)
        return row

    def meet(contact, company, days, status):
        db.add(Meeting(user_id=u1, contact_id=contact.id, company_id=cos[company].id,
                       company_name=company, scheduled_at=_ago(days), status=status))

    rows = {
        # 25일 전 전달 · 미팅 없음 → 의심
        "quiet": req(u1, hong, "샘플애그", 27, 25),
        # 10일 전 전달 → 아직
        "fresh": req(u1, hong, "테스트랩", 11, 10),
        # 30일 전 전달 · 같은 투자사 다른 심사역(임꺽정)이 미팅 예정 → 아니다
        "firm": req(u1, lee, "보기팜", 31, 30),
        # 40일 전 전달 · 예정일 지난 미팅(완료 처리 안 됨) → 아니다
        "overdue": req(u1, hong, "예시바이오", 41, 40),
        # 남의 줄 — 30일 전 전달 → 의심(관리자만 본다)
        "other": req(u2, park, "샘플애그", 31, 30),
    }
    meet(lim, "보기팜", -5, "scheduled")
    meet(hong, "예시바이오", 20, "scheduled")
    db.commit()
    return {"rows": rows, "contacts": {"hong": hong, "lee": lee, "park": park},
            "companies": cos, "req": req, "act": ContactActivity}


def _rows(db, user_id=None, today=TODAY):
    from app.services import ir_no_meeting

    return {(r["contact_name"], r["company"]): r
            for r in ir_no_meeting.rows(db, user_id, today)[0]}


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


# --- 1. 드랍 의심 ------------------------------------------------------------

def test_suspect_definition(db, users, seed):
    got = _rows(db)
    assert got[("홍길동", "샘플애그")]["suspect"] is True
    assert got[("홍길동", "샘플애그")]["quiet_days"] == 25
    assert got[("홍길동", "테스트랩")]["suspect"] is False         # 10일
    assert got[("이몽룡", "보기팜")]["suspect"] is False           # 같은 투자사 미팅 예정
    assert got[("홍길동", "예시바이오")]["suspect"] is False       # 지난 예정 미팅이 있다
    assert got[("성춘향", "샘플애그")]["suspect"] is True
    assert ("성춘향", "샘플애그") not in _rows(db, users["u1"].id)   # 팀원은 제 것만


def test_meeting_ask_means_arranging_and_restarts_the_clock(db, users, seed):
    from app.models import ContactActivity, VcContact
    from app.services import ir_no_meeting, pipeline

    # 미팅 요청은 담당자당 한 통 — 그 담당자의 **마지막** 전달 뒤에 나가야 보낸 것이다
    # (`meeting_ask_state`). 전달이 한 건뿐인 사람으로 본다.
    kim = VcContact(user_id=users["u1"].id, name="김선달", title="심사역", firm="차카타벤처스")
    db.add(kim)
    db.flush()
    seed["req"](users["u1"].id, kim, "샘플애그", 27, 25)
    db.add(ContactActivity(contact_id=kim.id, kind=pipeline.MEETING_ASK_KIND,
                           content="미팅 요청", happened_at=_ago(15)))
    db.commit()
    row = _rows(db)[("김선달", "샘플애그")]
    assert row["status_label"] == ir_no_meeting.LABEL_ARRANGING
    assert row["asked_at"] == _ago(15)
    # 전달(25일)이 아니라 미팅 요청(15일)부터 — 아직 의심이 아니다
    assert (row["quiet_days"], row["suspect"]) == (15, False)
    later = _rows(db, today=TODAY + timedelta(days=6))[("김선달", "샘플애그")]
    assert (later["quiet_days"], later["suspect"]) == (21, True)


# --- 2. 드랍 상태 ------------------------------------------------------------

def test_lost_leaves_the_lists_and_comes_back_on_a_new_request(db, users, seed):
    row = seed["rows"]["quiet"]
    row.status = "lost"
    db.commit()
    got = _rows(db)[("홍길동", "샘플애그")]
    assert (got["state"], got["status_label"], got["suspect"]) == ("lost", "드랍", False)
    assert got["lost_ids"] == [row.id] and got["delivered_at"] == _ago(25)

    # 드랍 뒤에 다시 자료를 달라고 했다 → 다시 산다
    seed["req"](users["u1"].id, seed["contacts"]["hong"], "샘플애그", 2)
    db.commit()
    assert _rows(db)[("홍길동", "샘플애그")]["state"] == "open"


def test_lost_still_counts_as_sent(db, users, seed):
    from app.services import memo_delivered, report

    month = _ago(27)[:7]

    def delivered():
        return report.monthly(db, int(month[:4]), int(month[5:]), users["u1"],
                              today=TODAY)["ir_delivered"]

    before = delivered()
    seed["rows"]["quiet"].status = "lost"
    db.commit()
    assert delivered() == before                     # 드랍도 보낸 것으로 센다
    # 명단 기록 겹침도 드랍한 앱 기록을 본다 — 안 그러면 명단 쪽이 다시 세어진다
    assert any("샘플애그" in keys and person[1] == "홍길동"
               for (person, _), keys in memo_delivered.app_delivered(db).items())


# --- 3. 화면 · 단추 -----------------------------------------------------------

def test_drop_view_and_confirm_then_undo(client, db, users, seed):
    c = _login(client)
    html = c.get("/ir/no-meeting?view=drop").text
    assert "드랍 의심 1" in html and "드랍 확정" in html
    body = html.split('id="irnm-table"', 1)[1]
    assert "샘플애그" in body and "테스트랩" not in body and "성춘향" not in body

    rid = seed["rows"]["quiet"].id
    res = c.post("/ir/no-meeting/status", data={"ids": str(rid), "to": "lost",
                                                "back": "/ir/no-meeting?view=drop"},
                 follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/ir/no-meeting?view=drop"
    db.refresh(seed["rows"]["quiet"])
    assert seed["rows"]["quiet"].status == "lost"
    assert "드랍 의심 0" in c.get("/ir/no-meeting").text
    assert "샘플애그" not in c.get("/ir/no-meeting").text.split('id="irnm-table"', 1)[-1]

    shown = c.get("/ir/no-meeting?drop=show").text
    assert "드랍 취소" in shown
    c.post("/ir/no-meeting/status", data={"ids": str(rid), "to": "delivered"})
    db.refresh(seed["rows"]["quiet"])
    assert seed["rows"]["quiet"].status == "delivered"


def test_confirm_rules(client, db, users, seed):
    c = _login(client)
    other = seed["rows"]["other"].id
    # 팀원은 남의 요청을 못 고친다
    assert c.post("/ir/no-meeting/status", data={"ids": str(other), "to": "lost"}).status_code == 404
    assert c.post("/ir/no-meeting/status",
                  data={"ids": str(seed["rows"]["quiet"].id), "to": "open"}).status_code == 400
    # 열린 요청은 드랍으로 안 간다(전달 완료만)
    fresh = seed["req"](users["u1"].id, seed["contacts"]["hong"], "견본솔루션", 3)
    db.commit()
    c.post("/ir/no-meeting/status", data={"ids": str(fresh.id), "to": "lost"})
    db.refresh(fresh)
    assert fresh.status == "open"
    # 돌아갈 곳은 그 화면만
    res = c.post("/ir/no-meeting/status", data={"ids": "", "to": "lost",
                                                "back": "https://example.com/"},
                 follow_redirects=False)
    assert res.headers["location"] == "/ir/no-meeting"

    # 관리자는 팀 전체
    users["u1"].role = "admin"
    db.commit()
    assert c.post("/ir/no-meeting/status", data={"ids": str(other), "to": "lost"}).status_code == 200
    db.refresh(seed["rows"]["other"])
    assert seed["rows"]["other"].status == "lost"
    # 남의 요청을 고친 일은 수정 로그에 남는다
    from app.models import EditLog
    log = db.query(EditLog).filter_by(table_name="ir_requests", row_id=other).one()
    assert (log.actor_user_id, log.path) == (users["u1"].id, "/ir/no-meeting/status")
    assert "lost" in log.changes_json


# --- 4. 명단 기록 ------------------------------------------------------------

@pytest.fixture()
def memo(db, users, seed):
    """u1 명단 — 40일 전 달의 `IR 요청` 칸에 `견본솔루션 전달` · `샘플애그 전달`(앱과 겹침)."""
    from app.models import ContactColumn, SheetOwner
    from app.services import contact_columns as cc

    sheet = "투자사 시험 탭"
    day = TODAY - timedelta(days=40)
    col = ContactColumn(sheet=sheet, label=f"{day.month}월 IR 요청", position=0,
                        month=day.strftime("%Y-%m"))
    db.add_all([SheetOwner(label=sheet, user_id=users["u1"].id, layout=cc.INVESTOR_MONTHLY), col])
    hong = seed["contacts"]["hong"]
    hong.source_sheet = sheet
    db.flush()
    hong.notes = json.dumps({cc.note_key(col.id): f"{day.month}/{day.day} 견본솔루션 전달"},
                            ensure_ascii=False)
    db.commit()
    return {"day": day.isoformat(), "month": day.strftime("%Y-%m")}


def test_memo_rows_are_read_and_can_be_adopted(client, db, users, seed, memo):
    from app.models import IrRequest

    row = _rows(db)[("홍길동", "견본솔루션")]
    assert (row["src"], row["src_label"], row["state"]) == ("memo", "명단 기록", "delivered")
    assert row["suspect"] is True and row["sent_ids"] == [] and row["quiet_days"] == 40
    assert row["memos"] == [{"contact_id": seed["contacts"]["hong"].id, "month": memo["month"],
                             "company": "견본솔루션"}]

    c = _login(client)
    html = c.get("/ir/no-meeting?view=drop").text
    assert "앱 기록으로" in html and "명단 기록" in html
    assert c.get("/ir/no-meeting?src=memo").text.count("<tr data-pair>") == 1

    # 칸에 없는 기업은 못 옮긴다
    bad = {"contact_id": seed["contacts"]["hong"].id, "month": memo["month"], "company": "없는기업"}
    assert c.post("/ir/no-meeting/adopt", data=bad).status_code == 404
    c.post("/ir/no-meeting/adopt", data={**bad, "company": "견본솔루션"})
    c.post("/ir/no-meeting/adopt", data={**bad, "company": "견본솔루션"})   # 두 번 눌러도 한 건
    made = db.query(IrRequest).filter_by(company_name="견본솔루션").all()
    assert len(made) == 1
    assert (made[0].status, made[0].delivered_at, made[0].user_id) == (
        "delivered", memo["day"], users["u1"].id)
    row = _rows(db)[("홍길동", "견본솔루션")]
    assert row["src"] == "app" and row["sent_ids"] == [made[0].id]   # 이제 [드랍 확정]


def test_memo_overlapping_app_is_not_shown_twice(db, users, seed, memo):
    from app.models import IrRequest

    db.add(IrRequest(user_id=users["u1"].id, contact_id=seed["contacts"]["hong"].id,
                     company_name="견본솔루션", requested_at=memo["day"],
                     status="lost", delivered_at=memo["day"]))
    db.commit()
    row = _rows(db)[("홍길동", "견본솔루션")]
    assert row["src"] == "app" and row["state"] == "lost"   # 드랍한 앱 기록과 겹친다


def test_other_member_cannot_adopt(client, db, users, seed, memo):
    c = _login(client, "01000000002")
    res = c.post("/ir/no-meeting/adopt", data={"contact_id": seed["contacts"]["hong"].id,
                                                "month": memo["month"], "company": "견본솔루션"})
    assert res.status_code == 404


# --- 5. 업무 보고 링크 ----------------------------------------------------------

def test_report_links_to_drop_suspects(client, db, users, seed):
    html = _login(client).get("/report").text
    assert "전달 후 21일 미팅 없음" in html
    assert f'href="/ir/no-meeting?view=drop&amp;member={users["u1"].id}">1건' in html
    users["u1"].role = "admin"
    db.commit()
    html = client.get("/report?scope=team").text
    assert 'href="/ir/no-meeting?view=drop&amp;member=0">2건' in html
    assert "전달 후 21일 미팅 없음" not in client.get("/report?span=year").text
