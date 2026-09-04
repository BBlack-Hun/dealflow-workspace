"""주간 업무 — 반복 업무를 표에서 바로 고친다.

시트에는 목록 아래에 규칙이 글로 적혀 있었다("이메일 발송 — 매주 화·목
오전"). 화면으로 옮긴 뒤에도 항목·세부업무·시간대를 고치려면 지우고 다시
만들어야 했다 — 그 자리에서 고칠 수 있어야 한다.
"""
from __future__ import annotations

from .conftest import DEMO_PASSWORD


def _routine_table(body: str) -> str:
    """화면에서 반복 업무 표만 떼어 낸다.

    지운 규칙이 만들어 둔 **주간 업무 항목**은 같은 이름으로 위쪽 표에 그대로
    남는다(그게 지우기 창의 약속이다). 그래서 화면 전체에서 이름을 찾으면
    지워졌는지 알 수 없다.
    """
    head = body.find('id="routine-table"')
    return body[head:body.find("</table>", head)] if head >= 0 else ""



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


# --- 반복 업무 지우기 --------------------------------------------------------
#
# 사용자가 든 증상: "반복업무를 생성 후 삭제를 누를 때 500 Error".
# 만들면 `/todo` 로 돌아오고, 그 화면이 `fill_week` 로 **그 주 항목을 곧바로
# 하나 만든다.** 그 항목이 `weekly_tasks.routine_id` 로 규칙을 가리키는데
# SQLite 는 `PRAGMA foreign_keys=ON` 이라(app/db.py), 규칙을 지우려 하면
#
#     sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError)
#     FOREIGN KEY constraint failed
#     [SQL: DELETE FROM weekly_routines WHERE weekly_routines.id = ?]
#
# 로 튕겼다. 화면에는 500 만 보인다.

def test_deleting_a_routine_after_the_week_was_filled(client, db, users):
    """만들고 → 화면을 열고 → 지운다. 사람이 실제로 하는 순서 그대로."""
    from app.models import WeeklyTask

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"category": "메일", "title": "주간 정리",
                                        "weekdays": "0"})
    from app.models import WeeklyRoutine
    routine_id = db.query(WeeklyRoutine).filter_by(title="주간 정리").one().id

    # 화면을 열면 그 주 항목이 생긴다 — 만들기 뒤의 리다이렉트가 곧 이 화면이다.
    client.get("/todo")
    assert db.query(WeeklyTask).filter_by(routine_id=routine_id).count() == 1

    r = client.post(f"/todo/routines/{routine_id}/delete", follow_redirects=False)
    assert r.status_code == 303, "반복 업무 삭제가 500 입니다"
    assert "주간 정리" not in _routine_table(client.get("/todo").text)


def test_the_rows_it_already_made_survive_the_delete(client, db, users):
    """지우기 창의 약속 — "이미 만들어진 이번 주 항목은 남습니다"."""
    from app.models import WeeklyRoutine, WeeklyTask

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"title": "주간 정리", "weekdays": "0"})
    routine = db.query(WeeklyRoutine).filter_by(title="주간 정리").one()
    client.get("/todo")

    client.post(f"/todo/routines/{routine.id}/delete")
    db.expire_all()
    assert db.query(WeeklyTask).filter_by(title="주간 정리").count() == 1


def test_deleted_routines_do_not_come_back(client, db, users):
    """지운 반복 업무가 새로고침 한 번에 되살아났다.

    `ensure_routines` 는 화면을 열 때마다 도는데, "지금 규칙이 하나도 없는가"
    로 처음 쓰는 사람을 가렸다. 우리 팀이 하지 않는 기본 규칙을 다 지운
    사람에게는 그 조건이 그대로 참이라, 다음 새로고침에 넷이 새 번호로 다시
    섰다 — 그 주 목록에도 항목이 다시 생긴다.
    """
    from app.services import weekly

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.get("/todo")                     # 기본 규칙 넷이 깔린다
    for routine in weekly.active_routines(db, users["u1"]):
        client.post(f"/todo/routines/{routine.id}/delete")

    body = client.get("/todo").text         # 다시 열어 본다
    assert weekly.active_routines(db, users["u1"]) == []
    assert "반복 업무가 없습니다" in body, "지운 반복 업무가 되살아났습니다"


def test_a_deleted_routine_stops_making_new_rows(client, db, users):
    """내려 둔 규칙은 다음 주 목록을 채우지 않는다."""
    from datetime import date, timedelta

    from app.models import WeeklyRoutine, WeeklyTask
    from app.services import weekly

    next_week = weekly.week_start(date.today()) + timedelta(days=7)

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"title": "주간 정리", "weekdays": "0"})
    routine = db.query(WeeklyRoutine).filter_by(title="주간 정리").one()
    client.post(f"/todo/routines/{routine.id}/delete")

    client.get(f"/todo?week={next_week}")
    assert db.query(WeeklyTask).filter_by(week_start=next_week.isoformat(),
                                          routine_id=routine.id).count() == 0


def test_cannot_delete_someone_elses_routine(client, db, users):
    from app.models import WeeklyRoutine

    routine = WeeklyRoutine(user_id=users["u2"].id, category="메일",
                            title="남의 규칙", weekdays="0")
    db.add(routine)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.post(f"/todo/routines/{routine.id}/delete", follow_redirects=False)
    assert r.status_code == 404
    assert db.get(WeeklyRoutine, routine.id) is not None


# --- 고른 요일이 다 저장되는가 -----------------------------------------------

def test_every_checked_weekday_is_saved(client, db, users):
    """화면의 요일칸은 체크박스 다섯 개가 `weekdays` 한 이름을 쓴다.

    월·화·목을 고르면 `weekdays=0&weekdays=1&weekdays=3` 으로 나가는데,
    서버가 문자열 하나로 받던 동안에는 마지막 `3` 만 남고 앞의 둘이 조용히
    버려졌다 — 화면에는 셋을 골랐는데 표에는 `목` 만 적혔다.
    """
    from app.models import WeeklyRoutine

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines",
                data={"title": "여러 요일", "weekdays": ["0", "1", "3"]})
    row = db.query(WeeklyRoutine).filter_by(title="여러 요일").one()
    assert row.weekdays == "0,1,3"


# --- 저장되지 않았는데 저장된 척하지 않는가 ----------------------------------

def test_blank_routine_title_is_refused(client, db, users):
    """주간 업무 쪽(`patch_task`)은 400 을 낸다. 반복 업무만 200 을 냈다 —
    표는 초록 깜빡임을 내고 칸을 비운 채 두는데 DB 에는 옛 이름이 남았다."""
    from app.models import WeeklyRoutine

    routine = WeeklyRoutine(user_id=users["u1"].id, category="메일",
                            title="원래 이름", weekdays="0")
    db.add(routine)
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    r = client.patch(f"/api/todo/routines/{routine.id}", json={"title": "   "})
    assert r.status_code == 400
    db.refresh(routine)
    assert routine.title == "원래 이름"


# --- 지난 주 · 가져오기 ------------------------------------------------------

def test_carry_over_does_not_duplicate_routine_rows(client, db, users):
    """[이번 주로 가져오기] 를 누르면 반복 업무가 두 벌이 됐다.

    지난 주 화면에서 만들어진 반복 항목이 이번 주로 옮겨 오는데, 이번 주에는
    `fill_week` 가 만든 같은 규칙의 줄이 이미 서 있다.
    """
    from datetime import date, timedelta

    from app.models import WeeklyRoutine, WeeklyTask
    from app.services import weekly

    this_week = weekly.week_start(date.today())
    last_week = this_week - timedelta(days=7)

    routine = WeeklyRoutine(user_id=users["u1"].id, category="메일",
                            title="주간 발송", weekdays="0")
    db.add(routine)
    db.commit()
    # 지난 주에 만들어졌지만 끝내지 못한 반복 항목.
    db.add(WeeklyTask(user_id=users["u1"].id, week_start=last_week.isoformat(),
                      category="메일", title="주간 발송", status="todo",
                      routine_id=routine.id))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.get(f"/todo?week={this_week}")          # 이번 주 줄이 생긴다
    client.post("/todo/carry-over", data={"week": this_week.isoformat()})

    db.expire_all()
    rows = db.query(WeeklyTask).filter_by(week_start=this_week.isoformat(),
                                          routine_id=routine.id).all()
    assert len(rows) == 1, "같은 반복 업무가 한 주에 두 줄로 앉았습니다"


def test_opening_a_past_week_does_not_invent_work(client, db, users):
    """[← 지난 주] 를 누르기만 해도 그 주에 반복 업무가 새로 생겼다.

    시킨 적 없는 일이 날짜가 지난 채로 나타나 그 자리에서 '지남' 이 되고,
    이번 주 화면에는 "지난 주에 못 끝낸 일이 N건" 이라는 안내까지 떴다.
    """
    from datetime import date, timedelta

    from app.models import WeeklyRoutine, WeeklyTask
    from app.services import weekly

    last_week = weekly.week_start(date.today()) - timedelta(days=7)
    db.add(WeeklyRoutine(user_id=users["u1"].id, category="메일",
                         title="주간 발송", weekdays="0"))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.get(f"/todo?week={last_week}")

    assert db.query(WeeklyTask).filter_by(
        week_start=last_week.isoformat()).count() == 0
