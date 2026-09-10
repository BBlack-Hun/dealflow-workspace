"""주간 업무 — 반복 업무를 표에서 바로 고친다.

시트에는 목록 아래에 규칙이 글로 적혀 있었다("이메일 발송 — 매주 화·목
오전"). 화면으로 옮긴 뒤에도 항목·세부업무·시간대를 고치려면 지우고 다시
만들어야 했다 — 그 자리에서 고칠 수 있어야 한다.
"""
from __future__ import annotations

from .conftest import DEMO_PASSWORD


def _task_table(body: str) -> str:
    """화면에서 주간 업무 표만 떼어 낸다.

    반복 업무 표에도 같은 이름이 서 있어서(규칙 이름이 곧 항목 이름이다),
    화면 전체에서 찾으면 지워졌는지 알 수 없다 — `_routine_table` 의 반대편이다.
    """
    head = body.find('id="task-table"')
    return body[head:body.find("</table>", head)] if head >= 0 else ""


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


# --- 주간 업무 항목 지우기 ---------------------------------------------------
#
# 사용자가 든 증상: "반복업무로 생성된 일정은 지워지지 않음. 삭제가 될 수 있어야 함".
# 되물으니 "반복 업무에 대해 주간업무로 만들어 지는거잖아. 주간업무쪽에서는
# 지울 수 있게 해주는게 맞는거 같아".
#
# 지우는 길은 이미 있었다(`POST /todo/tasks/{id}/delete`, 모든 줄에 단추도 있다).
# 지운 뒤 `/todo` 로 돌아오면 `fill_week` 가 **다시 만들었다** — "이 규칙 줄이
# 이번 주에 있나" 를 지금 남아 있는 `WeeklyTask.routine_id` 로만 봤기 때문이다.
# 지우면 그 자취까지 사라져 없는 것이 되고, 곧바로 다시 생긴다.


def test_a_deleted_routine_row_stays_deleted(client, db, users):
    """**이 검사가 제일 중요하다.** 지우고 화면을 다시 열어도 안 돌아와야 한다.

    지우기 → `/todo` 로 리다이렉트 → 그 화면이 `fill_week` 를 돌린다. 사람이
    실제로 하는 순서 그대로다.
    """
    from app.models import WeeklyRoutine, WeeklyTask

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"category": "메일", "title": "주간 정리",
                                        "weekdays": "0"})
    routine = db.query(WeeklyRoutine).filter_by(title="주간 정리").one()

    client.get("/todo")                     # 그 주 항목이 생긴다
    task = db.query(WeeklyTask).filter_by(routine_id=routine.id).one()

    client.post(f"/todo/tasks/{task.id}/delete")
    body = client.get("/todo").text         # 다시 열어 본다

    db.expire_all()
    assert db.query(WeeklyTask).filter_by(routine_id=routine.id).count() == 0, (
        "지운 반복 업무 항목이 화면을 다시 여니 되살아났습니다")
    assert "주간 정리" not in _task_table(body)


def test_a_hand_written_row_can_be_deleted(client, db, users):
    """반복이 아닌 항목 — 사람이 직접 적은 줄도 그대로 지워져야 한다.

    되살아나는 것은 반복 업무 쪽 일이지만, 고치면서 이쪽이 함께 깨지면
    아무도 눈치채지 못한다(이 줄에는 되살리는 코드가 애초에 없다).
    """
    from app.models import WeeklyTask

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/tasks", data={"category": "메일", "title": "손으로 적은 일"})
    task = db.query(WeeklyTask).filter_by(title="손으로 적은 일").one()
    assert task.routine_id is None

    client.post(f"/todo/tasks/{task.id}/delete")
    body = client.get("/todo").text

    db.expire_all()
    assert db.query(WeeklyTask).filter_by(title="손으로 적은 일").count() == 0
    assert "손으로 적은 일" not in _task_table(body)


def test_deleting_one_row_does_not_stop_the_next_week(client, db, users):
    """이번 주 줄을 지운 것이 **다음 주까지 끄지는 않는다.**

    만들었다는 표시는 (사람·주·규칙)으로 남는다. 주가 다르면 다른 표시라,
    다음 주를 열면 그 주 몫은 그대로 선다 — 한 번 지운 것이 그 규칙을 영영
    내리는 뜻이 되면, 지우기와 반복 업무 [삭제] 가 같은 것이 되어 버린다.
    """
    from datetime import date, timedelta

    from app.models import WeeklyRoutine, WeeklyTask
    from app.services import weekly

    next_week = weekly.week_start(date.today()) + timedelta(days=7)

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"title": "주간 정리", "weekdays": "0"})
    routine = db.query(WeeklyRoutine).filter_by(title="주간 정리").one()

    client.get("/todo")
    task = db.query(WeeklyTask).filter_by(routine_id=routine.id).one()
    client.post(f"/todo/tasks/{task.id}/delete")

    client.get(f"/todo?week={next_week}")
    db.expire_all()
    assert db.query(WeeklyTask).filter_by(week_start=next_week.isoformat(),
                                          routine_id=routine.id).count() == 1


def test_a_past_week_is_never_filled(client, db, users):
    """지난 주는 `fill_week` 가 애초에 채우지 않는다(`start < week_start(today)`).

    그래서 지난 주 화면에서 지운 줄은 되살아날 길 자체가 없다. 되살아나지
    않는 이유가 **두 가지**(안 채운다 · 표시가 남는다)라는 것을 적어 둔다 —
    한쪽만 보고 다른 쪽을 지우는 날이 온다.
    """
    from datetime import date, timedelta

    from app.models import WeeklyRoutine, WeeklyTask
    from app.services import weekly

    last_week = weekly.week_start(date.today()) - timedelta(days=7)

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"title": "주간 정리", "weekdays": "0"})
    routine = db.query(WeeklyRoutine).filter_by(title="주간 정리").one()

    # 지난 주에 서 있던 줄(그때 만들어진 것). 손으로 세워 둔다 — 지난 주 화면은
    # 그 주를 채우지 않으므로 화면을 열어서는 만들 수 없다.
    db.add(WeeklyTask(user_id=users["u1"].id, week_start=last_week.isoformat(),
                      category="메일", title="주간 정리", routine_id=routine.id))
    db.commit()
    task_id = db.query(WeeklyTask).filter_by(
        week_start=last_week.isoformat()).one().id

    client.post(f"/todo/tasks/{task_id}/delete", data={"week": last_week.isoformat()})
    client.get(f"/todo?week={last_week}")

    db.expire_all()
    assert db.query(WeeklyTask).filter_by(
        week_start=last_week.isoformat()).count() == 0


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


# --- 반복 업무의 주차(격주) --------------------------------------------------
#
# 사용자 원문: "지금 업무가 격주로 진행되고 있는데, 반복업무 셋팅할때 주차도
# 셋팅할 수 있게". 되물어 확정한 격주의 뜻은 **1주차, 3주차**다 — 달 기준이고,
# 딜 회차가 매월 첫째·셋째 수요일인 것과 같은 셈법이다.
#
# **날짜를 박지 않는다.** 예전에 박아 둔 검사가 그날이 되자 깨졌다. 오늘에서
# 앞으로 세어 조건에 맞는 주를 찾아 쓴다 — `fill_week` 는 지난 주를 채우지
# 않으므로(`start < week_start(today)`) 앞으로 세는 것이 조건이기도 하다.


def _week_where(nth: int, weekday: int = 0):
    """오늘 이후로, 그 요일이 `nth`주차에 드는 첫 주의 월요일."""
    from datetime import date, timedelta

    from app.services import weekly

    start = weekly.week_start(date.today())
    for _ in range(60):
        if weekly.week_of_month(start + timedelta(days=weekday)) == nth:
            return start
        start += timedelta(days=7)
    raise AssertionError(f"{nth}주차인 주를 못 찾았다 — 주차 셈법이 바뀌었나")


def test_the_week_rule_is_the_one_the_whole_repo_uses():
    """주차 규칙은 `sheet_import.week_of_month` **하나뿐**이어야 한다.

    예전에 같은 날이 화면마다 3주차·4주차로 갈린 적이 있다. 여기서 따로 세면
    반복 업무만 다른 달력을 쓰게 된다 — `tests/test_cadence.py` 가 회차일에
    대고 지키는 것과 같은 규칙이다.
    """
    from datetime import date, timedelta

    from app.services import sheet_import, weekly

    day = date.today()
    for _ in range(400):
        assert weekly.week_of_month(day) == sheet_import.week_of_month(day.isoformat()), day
        day += timedelta(days=1)


def test_a_biweekly_routine_only_shows_up_on_its_weeks(client, db, users):
    """`1,3` 규칙은 1·3주차에만 생기고 2·4주차에는 안 생긴다."""
    from app.models import WeeklyRoutine, WeeklyTask

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"title": "격주 정리", "weekdays": "0",
                                        "nth_weeks": ["1", "3"]})
    routine = db.query(WeeklyRoutine).filter_by(title="격주 정리").one()
    assert routine.nth_weeks == "1,3"

    def rows_in(start):
        client.get(f"/todo?week={start}")
        db.expire_all()
        return db.query(WeeklyTask).filter_by(week_start=start.isoformat(),
                                              routine_id=routine.id).count()

    for nth in (1, 3):
        assert rows_in(_week_where(nth)) == 1, f"{nth}주차인데 안 생겼습니다"
    for nth in (2, 4):
        assert rows_in(_week_where(nth)) == 0, f"{nth}주차인데 생겼습니다"


def test_an_empty_week_setting_means_every_week(client, db, users):
    """주차를 비우면 **매주**다. 이 칸이 생기기 전의 규칙 수백 개가 그 상태다."""
    from app.models import WeeklyRoutine, WeeklyTask

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    client.post("/todo/routines", data={"title": "매주 정리", "weekdays": "0"})
    routine = db.query(WeeklyRoutine).filter_by(title="매주 정리").one()
    # 빈 글자가 아니라 **빈칸**이어야 한다 — 같은 뜻을 두 글자로 적어 두면
    # 나중에 어느 한쪽만 보는 코드가 생긴다.
    assert routine.nth_weeks is None

    for nth in (1, 2, 3, 4):
        start = _week_where(nth)
        client.get(f"/todo?week={start}")
        db.expire_all()
        assert db.query(WeeklyTask).filter_by(week_start=start.isoformat(),
                                              routine_id=routine.id).count() == 1, (
            f"{nth}주차에 매주 규칙이 안 생겼습니다")


def test_routines_made_before_this_column_still_run_every_week(client, db, users):
    """칸이 생기기 전에 만들어진 규칙(값이 NULL)은 그대로 매주여야 한다.

    이주가 기본값을 채워 넣었다면 여기서 걸린다 — 매주 나가던 홍보 메일이
    말없이 두 주에 한 번이 된다.
    """
    from app.models import WeeklyRoutine, WeeklyTask

    routine = WeeklyRoutine(user_id=users["u1"].id, category="메일",
                            title="옛날 규칙", weekdays="0")
    db.add(routine)
    db.commit()
    assert routine.nth_weeks is None

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    for nth in (1, 2, 3, 4):
        start = _week_where(nth)
        client.get(f"/todo?week={start}")
        db.expire_all()
        assert db.query(WeeklyTask).filter_by(week_start=start.isoformat(),
                                              routine_id=routine.id).count() == 1


def test_the_form_offers_the_weeks_and_shows_them_back(client, db, users):
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/todo").text
    assert 'name="nth_weeks"' in body, "반복 업무 폼에 주차를 고를 자리가 없습니다"

    client.post("/todo/routines", data={"title": "격주 정리", "weekdays": "0",
                                        "nth_weeks": ["1", "3"]})
    table = _routine_table(client.get("/todo").text)
    assert "1·3주차" in table
    # 매주 도는 규칙은 `매주` 라고 적힌다 — 빈칸이 그 뜻이다.
    assert "매주" in _routine_table(client.get("/todo").text)


def test_junk_weeks_are_dropped(client, db, users):
    """한 달은 1~7일부터 29~31일까지 다섯 토막이다. 그 밖의 값은 버린다."""
    from app.services import weekly

    assert weekly.parse_nth_weeks("1,3") == [1, 3]
    assert weekly.parse_nth_weeks("3,1,3") == [1, 3]
    assert weekly.parse_nth_weeks("0,6,x,,-1") == []
    assert weekly.parse_nth_weeks(None) == []
    assert weekly.nth_label(None) == "매주"
    assert weekly.nth_label("3,1") == "1·3주차"


# --- 주간 업무 표 정렬 -------------------------------------------------------
#
# 사용자 원문: "주간 업무 정렬이 추가되어야함 기준은 항목, 일시, 상태를 기준으로
# 오름 및 내림차순". 되물으니 "정렬은 머리글을 눌러서".
#
# 세우는 일은 브라우저가 한다(60줄 안팎이라 왕복할 이유가 없다,
# `app/static/js/table_sort.js`). 여기서는 **화면이 세울 값을 내주는가**를 본다 —
# 값이 안 실리면 정렬은 조용히 아무것도 안 한다.


def test_the_task_table_hands_the_browser_what_it_needs_to_sort(client, db, users):
    from app.models import WeeklyTask
    from app.services import weekly

    # 일시는 **적어 둔 날짜 그대로** 실려야 한다. 어느 날이든 같아야 하는
    # 성질이라 오늘에서 떼어 만든다 — 날짜를 박으면 그날이 왔을 때 깨진다.
    start = weekly.week_start()
    db.add(WeeklyTask(user_id=users["u1"].id, week_start=start.isoformat(),
                      category="메일", title="정렬용 줄", status="doing",
                      due_date=start.isoformat()))
    db.commit()

    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/todo").text
    table = _task_table(body)

    # 머리글 세 칸이 정렬 대상이라고 선언되어 있는가.
    for key in ("category", "due", "status"):
        assert f'data-sort="{key}"' in table, f"{key} 머리글에 정렬이 안 걸렸습니다"
    # 줄에 세울 값이 실려 있는가. **일시는 화면 글자(`8/7(금)`)가 아니라 원래
    # 날짜**여야 한다 — 글자로 세우면 8/7 이 12/1 보다 뒤로 간다.
    assert f'data-s-due="{start.isoformat()}"' in table
    assert 'data-s-category="메일"' in table
    # 상태는 **가나다가 아니라** `진행중 → 예정 → 완료` 차례다. 서버가 그 차례를
    # 숫자로 적어 준다(`STATUS_ORDER`) — 화면이 다시 매기면 두 벌이 된다.
    assert f'data-s-status="{weekly.STATUS_ORDER["doing"]}"' in table
    assert "js/table_sort.js" in body


def test_moving_weeks_keeps_the_sort(client, db, users):
    """주를 옮기는 링크가 정렬을 실어 갈 수 있게 표시돼 있는가.

    [← 지난 주] 는 **링크**라 한 번 새로 그려진다. 표시가 없으면 세워 둔
    차례가 그 한 번에 풀린다(주소를 실어 주는 일은 table_sort.js 가 한다).
    """
    client.post("/login", data={"phone": "01000000001", "password": DEMO_PASSWORD})
    body = client.get("/todo").text
    assert body.count("data-sort-keep") >= 2, "주 이동 링크에 정렬 표시가 없습니다"


# --- 끝난 일의 겉모습 --------------------------------------------------------
#
# 완료로 바꾸면 줄에 **취소선**이 그어졌다. 읽기 힘들다고 해서 뺐다.
# 다만 뺄 것은 취소선뿐이다 — 흐린 색(`--muted`)까지 같이 지우면 끝난 일과
# 안 끝난 일이 겉으로 구분되지 않는다. 그래서 **둘 다** 잠근다.

def _task_done_rules() -> str:
    """app.css 에서 `.task-done` 이 대상인 규칙만 모아 온다."""
    import pathlib
    import re

    css = pathlib.Path("app/static/css/app.css").read_text(encoding="utf-8")
    out = []
    for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [s.strip() for s in block.group(1).split(",")]
        if any("task-done" in s for s in selectors):
            out.append(block.group(2))
    return "\n".join(out)


def test_a_finished_row_is_not_struck_through():
    rules = _task_done_rules()
    assert rules, ".task-done 규칙이 사라졌습니다"
    assert "line-through" not in rules, (
        "끝난 일에 취소선이 돌아왔습니다 — 읽기 힘들다고 해서 뺀 것입니다."
    )


def test_a_finished_row_still_looks_different():
    """취소선을 뺀 자리를 흐린 색이 대신한다 — 이것까지 빼면 구분이 사라진다."""
    rules = _task_done_rules()
    assert "var(--muted)" in rules, (
        "끝난 일의 흐린 색이 사라졌습니다. 취소선을 뺀 뒤로 끝난 일과 안 끝난 "
        "일을 구분해 주는 것은 이 색뿐입니다 — 바꾸려면 사용자에게 먼저 물으세요."
    )


def test_nothing_strikes_the_row_from_the_page_or_the_script():
    """CSS 만 고치고 마는 일을 막는다 — 화면·스크립트가 직접 그으면 그대로 남는다."""
    import pathlib

    watched = [pathlib.Path("app/templates/todo.html"),
               pathlib.Path("app/static/js/weekly_tasks.js")]
    for path in watched:
        text = path.read_text(encoding="utf-8")
        assert "line-through" not in text, f"{path} 가 직접 취소선을 긋고 있습니다"
        assert "textDecoration" not in text, f"{path} 가 직접 취소선을 긋고 있습니다"
