"""IR 미팅 달력(#5) — 딜 진행 관리에 잡힌 미팅을 달·해 단위로 본다.

못 박는 것.

1. 월간: 미팅이 **그날 칸**에 `기업 ↔ 투자사` 로 서고, 완료·예정이 갈린다.
   취소한 미팅 · 다른 달 미팅은 안 선다.
2. 연간: 달마다 완료·예정 수.
3. 팀원은 **제 미팅만** 본다(`member` 를 붙여 와도). 관리자는 팀 전체가
   기본이고 한 사람을 고를 수 있다.
4. 주소를 손으로 고쳐도 500 이 안 난다 · 12월 ↔ 1월 이동이 해를 넘는다.
5. 딜 진행 관리에서 탭으로 들어간다.
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def meetings(db, users):
    from app.models import Meeting, VcContact

    mine = VcContact(user_id=users["u1"].id, name="홍길동", title="심사역", firm="가나다벤처스")
    theirs = VcContact(user_id=users["u2"].id, name="김철수", title="이사", firm="라마바파트너스")
    db.add_all([mine, theirs])
    db.flush()
    db.add_all([
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="샘플애그",
                scheduled_at="2026-10-07", scheduled_time="14:00", status="done",
                outcome="reviewing"),
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="테스트랩",
                scheduled_at="2026-10-21", status="scheduled"),
        # 취소 — 없던 일이다
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="취소된기업",
                scheduled_at="2026-10-09", status="canceled"),
        # 다른 달
        Meeting(user_id=users["u1"].id, contact_id=mine.id, company_name="십일월기업",
                scheduled_at="2026-11-03", status="scheduled"),
        # 다른 팀원
        Meeting(user_id=users["u2"].id, contact_id=theirs.id, company_name="남의기업",
                scheduled_at="2026-10-15", status="scheduled"),
    ])
    db.commit()
    return {"mine": mine, "theirs": theirs}


def _login(client):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    return client


def _cell(html: str, day: int) -> str:
    """그 달 `day` 일 칸의 속 — 달 밖 칸(`cal-out`)은 건너뛴다."""
    for m in re.finditer(r'<td class="([^"]*)">(.*?)</td>', html, re.S):
        if "cal-out" in m.group(1):
            continue
        if re.search(rf'<span class="cal-day">{day}</span>', m.group(2)):
            return m.group(2)
    raise AssertionError(f"{day}일 칸이 없다")


# --- 1. 월간 ---------------------------------------------------------------

def test_month_puts_each_meeting_on_its_day(client, meetings):
    html = _login(client).get("/ir/calendar?view=month&ym=2026-10").text

    done = _cell(html, 7)
    assert "샘플애그 ↔ 가나다벤처스" in done
    assert 'class="cal-chip done"' in done and "✓" in done
    assert "14:00" in done
    # 제 미팅은 딜 진행 관리의 그 구역으로 이어진다
    assert 'href="/ir#reviews"' in done

    planned = _cell(html, 21)
    assert "테스트랩 ↔ 가나다벤처스" in planned
    assert 'class="cal-chip plan"' in planned
    assert 'href="/ir#meetings"' in planned

    assert "취소된기업" not in html
    assert "십일월기업" not in html


def test_month_counts_done_and_planned(db, users, meetings):
    from app.services import meeting_calendar

    got = meeting_calendar.month(db, users["u1"].id, 2026, 10, date(2026, 10, 19))
    assert (got["done"], got["planned"]) == (1, 1)
    # 주는 일요일부터 일곱 날, 오늘 칸이 하나 표시된다
    assert all(len(w) == 7 for w in got["weeks"])
    assert got["weeks"][0][0]["date"].weekday() == 6
    today = [d for w in got["weeks"] for d in w if d["today"]]
    assert [d["date"] for d in today] == [date(2026, 10, 19)]


# --- 2. 연간 ---------------------------------------------------------------

def test_year_counts_per_month(db, users, meetings):
    from app.services import meeting_calendar

    months = meeting_calendar.year(db, users["u1"].id, 2026)
    assert len(months) == 12
    assert (months[9]["done"], months[9]["planned"]) == (1, 1)   # 10월 — 취소는 안 센다
    assert (months[10]["done"], months[10]["planned"]) == (0, 1)  # 11월
    assert sum(m["done"] + m["planned"] for m in months) == 3


def test_year_view_links_each_month_to_its_calendar(client, meetings):
    html = _login(client).get("/ir/calendar?view=year&y=2026").text
    assert "/ir/calendar?view=month&ym=2026-10" in html
    assert "/ir/calendar?view=month&ym=2026-11" in html
    assert "완료 1 · 예정 2" in html


# --- 3. 누가 무엇을 보나 ----------------------------------------------------

def test_member_sees_only_their_own(client, meetings, users):
    c = _login(client)
    html = c.get("/ir/calendar?ym=2026-10").text
    assert "남의기업" not in html
    # `member` 를 붙여 와도 제 것만 — 고르개도 안 선다
    html = c.get(f"/ir/calendar?ym=2026-10&member={users['u2'].id}").text
    assert "남의기업" not in html and "샘플애그" in html
    assert "팀원 선택" not in html


def test_admin_sees_the_team_and_can_pick_one(client, db, meetings, users):
    users["u1"].role = "admin"
    db.commit()
    c = _login(client)

    html = c.get("/ir/calendar?ym=2026-10").text
    assert "샘플애그" in html and "남의기업" in html
    # 팀 전체일 때는 누구 미팅인지 적는다 · 남의 미팅은 /ir 에 안 보이므로 잇지 않는다
    other = _cell(html, 15)
    assert "윤서아" in other and "<a " not in other
    assert "팀원 선택" in html

    html = c.get(f"/ir/calendar?ym=2026-10&member={users['u2'].id}").text
    assert "남의기업" in html and "샘플애그" not in html
    # 앞뒤 이동이 고른 팀원을 놓치지 않는다
    assert f"ym=2026-11&amp;member={users['u2'].id}" in html   # 속성 안이라 `&` 가 `&amp;`


# --- 4. 주소 ------------------------------------------------------------------

@pytest.mark.parametrize("ym", ["", "abc", "2026-13", "2026", "1999-05", "2026-10-05"])
def test_bad_month_falls_back_to_this_month(client, meetings, ym):
    res = _login(client).get(f"/ir/calendar?ym={ym}")
    assert res.status_code == 200
    today = date.today()
    assert f"{today.year}년 {today.month}월" in res.text


def test_prev_and_next_cross_the_year(client, meetings):
    c = _login(client)
    html = c.get("/ir/calendar?ym=2026-12").text
    assert "ym=2026-11" in html and "ym=2027-01" in html
    html = c.get("/ir/calendar?ym=2026-01").text
    assert "ym=2025-12" in html and "ym=2026-02" in html
    html = c.get("/ir/calendar?view=year&y=2026").text
    assert "y=2025" in html and "y=2027" in html


# --- 5. 탭 ------------------------------------------------------------------

def test_deal_progress_page_has_the_calendar_tab(client, meetings):
    html = _login(client).get("/ir").text
    assert 'href="/ir/calendar"' in html
    assert re.search(r'class="sheet-tab active" href="/ir">딜 진행 관리', html)
