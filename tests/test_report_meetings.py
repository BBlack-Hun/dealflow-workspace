"""업무 보고 › `IR 미팅진행 리스트`(#120) — `/report/meetings`.

못 박는 것.

1. 앱 미팅 한 줄 = 한 건. 취소 · 다른 달은 빠지고, 예정이 다가오는 차례로 위 · 완료는
   최근 차례로 아래. 투자유치희망금액은 이어 둔 IR 기업의 `raise_target` 을 `amount.phrase` 로.
2. `지난 기록` — 명단 월별 `미팅` 칸 글을 원문 그대로. `IR 요청` 칸 · 숨긴 칸 · 다른 달은 안 싣는다.
3. 범위 — 팀원은 제 것만(`member` 를 붙여 와도), 관리자는 팀 전체가 기본, 팀원 화면으로
   보는 중이면 그 팀원. 오른쪽 팀원 고르개는 없다. 투자컨설턴트는 못 연다.
4. 탭 차례 `업무 보고 | IR 미팅진행 리스트 | 매출예상리스트` · 빈 상태 안내.

이름 · 회사는 전부 지어낸 것이다(공개 저장소).
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD

SHEET = "투자사 시험 탭"
TODAY = date(2026, 11, 1)


@pytest.fixture()
def data(db, users):
    from app.models import ContactColumn, IrCompany, Meeting, SheetOwner, VcContact
    from app.services import contact_columns as cc

    company = IrCompany(name="샘플애그", raise_target="5-10억 사이")
    mine = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역", firm="가나다벤처스",
                     source_sheet=SHEET)
    theirs = VcContact(user_id=users["u2"].id, name="김철수", firm="라마바파트너스",
                       source_sheet="남의 탭")
    db.add_all([company, mine, theirs,
                SheetOwner(label=SHEET, user_id=users["u1"].id, layout=cc.INVESTOR_MONTHLY),
                SheetOwner(label="남의 탭", user_id=users["u2"].id, layout=cc.INVESTOR_MONTHLY)])
    db.flush()
    cols = {label: ContactColumn(sheet=sheet, label=label, position=pos, month=month,
                                 is_hidden=int(label.endswith("옛 칸")))
            for pos, (sheet, label, month) in enumerate((
                (SHEET, "10월 IR 요청", "2026-10"),
                (SHEET, "10월 미팅", "2026-10"),
                (SHEET, "10월 미팅 옛 칸", "2026-10"),
                (SHEET, "9월 미팅", "2026-09"),
                ("남의 탭", "10월 미팅완료 투자사", "2026-10")))}
    db.add_all(cols.values())
    db.flush()

    def memo(person, values):
        person.notes = json.dumps({cc.note_key(cols[k].id): v for k, v in values.items()},
                                  ensure_ascii=False)

    memo(mine, {"10월 IR 요청": "10/5 샘플가 전달", "10월 미팅": "10/8 샘플가 1차 미팅\n→ 검토중",
                "10월 미팅 옛 칸": "숨긴 칸 글", "9월 미팅": "9/3 샘플나 미팅"})
    memo(theirs, {"10월 미팅완료 투자사": "10/20 샘플다 미팅완료"})
    db.add_all([
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_id=company.id,
                company_name="샘플애그", scheduled_at="2026-10-07", scheduled_time="14:00",
                status="done", outcome="reviewing", meet_mode="video", kind="first"),
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="완료늦은기업",
                scheduled_at="2026-10-14", status="done", kind="second"),
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="예정뒤기업",
                scheduled_at="2026-10-28", status="scheduled"),
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="예정앞기업",
                scheduled_at="2026-10-21", status="scheduled", meet_mode="in_person"),
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="취소된기업",
                scheduled_at="2026-10-09", status="canceled"),
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="십일월기업",
                scheduled_at="2026-11-03", status="scheduled"),
        Meeting(user_id=users["u2"].id, contact_id=theirs.id, company_name="남의기업",
                scheduled_at="2026-10-15", status="scheduled"),
    ])
    db.commit()


def _login(client, phone="01000000001"):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})
    return client


# --- 1. 앱 미팅 -------------------------------------------------------------

def test_listing_one_row_per_meeting(db, users, data):
    from app.services import meeting_calendar

    rows = meeting_calendar.listing(db, users["u1"].id, 2026, 10)
    assert [r["company"] for r in rows] == ["예정앞기업", "예정뒤기업", "완료늦은기업", "샘플애그"]
    first = rows[-1]
    assert (first["date"], first["time"], first["owner"]) == ("2026-10-07", "14:00", "강민준")
    assert (first["who"], first["firm"]) == ("홍길동 심사역", "가나다벤처스")
    assert first["raise_target"] == "5~10억"
    assert (first["kind"], first["mode"], first["status"], first["outcome"]) == (
        "1차 미팅", "화상", "완료", "검토 중")
    # IR 기업에 안 이은 미팅은 금액이 빈칸 — 이름으로 짐작하지 않는다.
    assert rows[0]["raise_target"] == "" and rows[0]["status"] == "예정"
    assert len(meeting_calendar.listing(db, None, 2026, 10)) == 5


# --- 2. 지난 기록 -----------------------------------------------------------

def test_memo_rows_are_verbatim_meeting_cells(db, users, data):
    from app.services import meeting_calendar

    rows = meeting_calendar.memo_rows(db, users["u1"].id, 2026, 10, TODAY)
    assert rows == [{"owner": "강민준", "sheet": SHEET, "column": "10월 미팅",
                     "firm": "가나다벤처스", "name": "홍길동",
                     "text": "10/8 샘플가 1차 미팅\n→ 검토중"}]
    assert [r["text"] for r in meeting_calendar.memo_rows(db, None, 2026, 10, TODAY)] == [
        "10/20 샘플다 미팅완료", "10/8 샘플가 1차 미팅\n→ 검토중"]
    assert [r["text"] for r in meeting_calendar.memo_rows(db, users["u1"].id, 2026, 9, TODAY)] == [
        "9/3 샘플나 미팅"]


# --- 3. 범위 ----------------------------------------------------------------

def test_member_sees_only_their_own(client, data, users):
    c = _login(client)
    html = c.get("/report/meetings?month=2026-10").text
    assert "샘플애그" in html and "5~10억" in html and "10/8 샘플가 1차 미팅" in html
    assert "남의기업" not in html and "샘플다" not in html
    assert "취소된기업" not in html and "십일월기업" not in html and "숨긴 칸 글" not in html
    html = c.get(f"/report/meetings?month=2026-10&member={users['u2'].id}").text
    assert "남의기업" not in html and "샘플애그" in html
    assert "팀 전체" not in html


def test_admin_sees_the_team_without_a_right_picker(client, db, data, users):
    users["u1"].role = "admin"
    db.commit()
    c = _login(client)
    html = c.get("/report/meetings?month=2026-10").text
    assert "샘플애그" in html and "남의기업" in html and "샘플다 미팅완료" in html
    assert "팀원 선택" not in html                                  # 고르개는 왼쪽 한 곳
    html = c.get("/report/meetings?month=2026-10&member=1").text   # [내 것]
    assert "샘플애그" in html and "남의기업" not in html
    assert "/report/meetings?month=2026-09&amp;member=1" in html  # 달을 바꿔도 범위를 지킨다


def test_view_as_defaults_to_the_viewed_member(client, db, data, users):
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=9, name="관리자", phone="01000000009", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()
    c = _login(client, "01000000009")
    c.post("/account/view-as", data={"member_id": users["u2"].id, "next": "/"})
    html = c.get("/report/meetings?month=2026-10").text
    assert "남의기업" in html and "샘플애그" not in html
    html = c.get("/report/meetings?month=2026-10&member=0").text    # [팀 전체]
    assert "남의기업" in html and "샘플애그" in html


def test_consultant_cannot_open(client, db, users):
    users["u2"].role = "consultant"
    db.commit()
    res = _login(client, "01000000002").get("/report/meetings", follow_redirects=False)
    assert res.status_code == 303


# --- 4. 탭 · 빈 상태 ----------------------------------------------------------

def test_tab_order_and_empty_state(client, data):
    c = _login(client)
    html = c.get("/report").text
    assert re.search(r'href="/report">업무 보고</a>\s*<a[^>]*href="/report/meetings">IR 미팅진행 리스트'
                     r'</a>\s*<a[^>]*href="/report/forecast">매출예상리스트', html)
    html = c.get("/report/meetings?month=2026-08").text
    assert re.search(r'class="sheet-tab active" href="/report/meetings"', html)
    assert "앱에 잡힌 미팅이 없습니다." in html
    res = c.get("/report/meetings?month=2026-13")                  # 손으로 고친 주소도 500 이 아니다
    assert res.status_code == 200
