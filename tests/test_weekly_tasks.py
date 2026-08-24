"""주간 업무 — 반복 업무를 표에서 바로 고친다.

시트에는 목록 아래에 규칙이 글로 적혀 있었다("이메일 발송 — 매주 화·목
오전"). 화면으로 옮긴 뒤에도 항목·세부업무·시간대를 고치려면 지우고 다시
만들어야 했다 — 그 자리에서 고칠 수 있어야 한다.
"""
from __future__ import annotations

from .conftest import DEMO_PASSWORD



# --- 반복 업무 인라인 수정 + 오전/오후 ------------------------------------------

def test_routine_row_is_inline_editable(client, db, users):
    from app.models import WeeklyRoutine

    routine = WeeklyRoutine(user_id=users["u1"].id, category="메일",
                            title="홍보 메일 발송", weekdays="0,2")
    db.add(routine)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.patch(f"/api/todo/routines/{routine.id}",
                     json={"title": "홍보 메일 발송 · 수신거부 정리"})
    assert r.status_code == 200
    db.refresh(routine)
    assert routine.title == "홍보 메일 발송 · 수신거부 정리"


def test_time_of_day_can_be_set_and_cleared(client, db, users):
    from app.models import WeeklyRoutine

    routine = WeeklyRoutine(user_id=users["u1"].id, category="메일",
                            title="발송", weekdays="0")
    db.add(routine)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.patch(f"/api/todo/routines/{routine.id}", json={"time_of_day": "am"})
    db.refresh(routine)
    assert routine.time_of_day == "am"

    client.patch(f"/api/todo/routines/{routine.id}", json={"time_of_day": ""})
    db.refresh(routine)
    assert routine.time_of_day is None


def test_cannot_edit_someone_elses_routine(client, db, users):
    from app.models import WeeklyRoutine

    routine = WeeklyRoutine(user_id=users["u2"].id, category="메일",
                            title="발송", weekdays="0")
    db.add(routine)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    assert client.patch(f"/api/todo/routines/{routine.id}",
                        json={"title": "가로채기"}).status_code == 404


def test_the_table_is_wired_and_new_routines_can_set_time(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/todo").text
    assert 'data-inline-url="/api/todo/routines"' in body
    assert 'name="time_of_day"' in body

    client.post("/todo/routines", data={"category": "메일", "title": "발송",
                                        "weekdays": "0", "time_of_day": "pm"})
    from app.models import WeeklyRoutine
    row = db.query(WeeklyRoutine).filter_by(title="발송").one()
    assert row.time_of_day == "pm"
