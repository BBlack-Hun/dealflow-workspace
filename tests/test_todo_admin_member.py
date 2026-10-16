"""관리자가 팀원의 주간업무를 **보고 대신 고친다** (`/todo?member=<id>`).

## 지키는 것

1. 관리자는 팀원 한 사람을 골라 그 사람의 주간업무 표와 반복 업무를 본다.
   화면 머리에 **"○○ 님의 주간업무를 보는 중 (관리자)"** 가 선다.
2. 그 자리에서 추가 · 수정 · 완료 · 삭제 · 가져오기 · 반복 업무 추가/수정/삭제가
   **그 팀원의 표에** 들어간다. 고친 뒤에는 그 팀원 화면으로 돌아온다.
3. 누가 고쳤는지는 수정 로그에 **관리자 이름으로** 남는다. 자기 할 일을 고치는
   것은 남지 않는다(지운 것도) — 개인 메모라 남기면 로그가 덮인다.
4. 관리자가 아니면 남의 것은 **403**. 주소에 번호를 넣어도, 폼에 실어 보내도.
5. 남의 화면을 보는 동안 **그 사람의 발송 쪽은 건드리지 않는다** — 시스템이
   챙기는 일 · 회차 준비 점검을 그리지 않고, 그 둘을 짓는 함수도 부르지 않는다.
"""
from __future__ import annotations

import pytest

from .conftest import DEMO_PASSWORD


@pytest.fixture()
def admin(db, users):
    from app.models import User
    from app.services import auth as auth_svc

    row = User(id=9, name="관리자", phone="01000000009", role="admin",
               password_hash=auth_svc.hash_password(DEMO_PASSWORD))
    db.add(row)
    db.commit()
    return row


def _login(client, phone):
    client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD})


def _task(db, user_id, title="홍길동 미팅 준비", category="미팅"):
    from datetime import date

    from app.models import WeeklyTask
    from app.services import weekly

    row = WeeklyTask(user_id=user_id,
                     week_start=weekly.week_start(date.today()).isoformat(),
                     category=category, title=title)
    db.add(row)
    db.commit()
    return row


def _logs(db, table):
    from sqlalchemy import select

    from app.models import EditLog

    db.expire_all()
    return db.execute(select(EditLog).where(EditLog.table_name == table)
                      .order_by(EditLog.id)).scalars().all()


# ── 1. 본다 ──────────────────────────────────────────────────────────────────

def test_admin_sees_the_members_week_with_a_banner(client, db, users, admin):
    _task(db, users["u1"].id, title="가나다벤처스 자료 정리")
    _task(db, admin.id, title="관리자 본인 할 일")
    _login(client, "01000000009")

    page = client.get(f"/todo?member={users['u1'].id}")
    assert page.status_code == 200
    body = page.text
    assert 'data-testid="todo-viewing-other"' in body
    assert "강민준 님의 주간업무를 보는 중 (관리자)" in body
    assert "가나다벤처스 자료 정리" in body
    assert "관리자 본인 할 일" not in body
    # 폼이 그 팀원 번호를 실어 보낸다.
    assert f'name="member" value="{users["u1"].id}"' in body
    # 주를 옮겨도 그 팀원 화면에 머문다.
    assert f"&member={users['u1'].id}" in body


def test_admin_has_a_member_picker_and_members_do_not(client, db, users, admin):
    _login(client, "01000000009")
    body = client.get("/todo").text
    assert 'id="todo-member-pick"' in body
    assert 'data-testid="todo-viewing-other"' not in body

    _login(client, "01000000001")
    assert 'id="todo-member-pick"' not in client.get("/todo").text


def test_member_cannot_open_someone_elses_week(client, db, users):
    _task(db, users["u2"].id, title="남의 할 일")
    _login(client, "01000000001")
    r = client.get(f"/todo?member={users['u2'].id}")
    assert r.status_code == 403
    assert "남의 할 일" not in r.text
    # 자기 번호를 넣는 것은 그냥 내 화면이다.
    mine = client.get(f"/todo?member={users['u1'].id}")
    assert mine.status_code == 200
    assert 'data-testid="todo-viewing-other"' not in mine.text


def test_unknown_member_is_404(client, db, users, admin):
    _login(client, "01000000009")
    assert client.get("/todo?member=999").status_code == 404


def test_viewing_someone_else_does_not_touch_their_sending_side(
        client, db, users, admin, monkeypatch):
    """시스템이 챙기는 일 · 회차 준비 점검은 그 사람의 발송·리마인드를 읽는 자리다.
    여는 것만으로 리마인드 정리가 도는 길이라, 남의 화면에서는 부르지도 않는다."""
    from app.services import readiness, today

    called = []
    monkeypatch.setattr(today, "build", lambda db, user, *a, **k: called.append(
        ("today", user.id)) or {"items": []})
    real_report = readiness.report
    monkeypatch.setattr(readiness, "report", lambda db, user, *a, **k: (
        called.append(("ready", user.id)), real_report(db, user, *a, **k))[1])
    _login(client, "01000000009")

    body = client.get(f"/todo?member={users['u1'].id}").text
    assert called == []
    assert 'id="readiness"' not in body

    client.get("/todo")
    assert ("today", admin.id) in called and ("ready", admin.id) in called


# ── 2. 대신 고친다 ────────────────────────────────────────────────────────────

def test_admin_adds_a_task_to_the_members_week(client, db, users, admin):
    from sqlalchemy import select

    from app.models import WeeklyTask

    _login(client, "01000000009")
    r = client.post("/todo/tasks", data={"category": "메일\n후속", "title": "홍보 메일",
                                          "member": str(users["u1"].id)},
                    follow_redirects=False)
    assert r.status_code == 303
    assert f"member={users['u1'].id}" in r.headers["location"]
    rows = db.execute(select(WeeklyTask).where(WeeklyTask.title == "홍보 메일")).scalars().all()
    assert [row.user_id for row in rows] == [users["u1"].id]

    log = _logs(db, "weekly_tasks")
    assert len(log) == 1
    assert (log[0].actor_user_id, log[0].target_user_id) == (admin.id, users["u1"].id)
    assert log[0].action == "create" and log[0].scope == "others"


def test_admin_edits_completes_and_deletes_the_members_task(client, db, users, admin):
    from app.models import WeeklyTask

    task = _task(db, users["u1"].id)
    task_id = task.id
    _login(client, "01000000009")

    assert client.patch(f"/api/todo/tasks/{task.id}",
                        json={"title": "홍길동 미팅 준비 (자료 포함)"}).status_code == 200
    assert client.patch(f"/api/todo/tasks/{task.id}",
                        json={"status": "done"}).status_code == 200
    db.expire_all()
    row = db.get(WeeklyTask, task.id)
    assert row.status == "done" and row.title == "홍길동 미팅 준비 (자료 포함)"
    assert row.user_id == users["u1"].id   # 주인은 그대로다

    r = client.post(f"/todo/tasks/{task.id}/delete", data={"week": ""},
                    follow_redirects=False)
    assert r.status_code == 303 and f"member={users['u1'].id}" in r.headers["location"]
    db.expire_all()
    assert db.get(WeeklyTask, task_id) is None

    actions = [(l.action, l.actor_user_id, l.target_user_id) for l in _logs(db, "weekly_tasks")]
    assert actions == [("update", admin.id, users["u1"].id),
                       ("update", admin.id, users["u1"].id),
                       ("delete", admin.id, users["u1"].id)]


def test_own_todo_edits_leave_no_log(client, db, users):
    """자기 할 일을 적고 고치고 지우는 것은 남기지 않는다 — 지운 것도."""
    task = _task(db, users["u1"].id)
    _login(client, "01000000001")
    client.patch(f"/api/todo/tasks/{task.id}", json={"status": "done"})
    client.post(f"/todo/tasks/{task.id}/delete", data={"week": ""})
    client.post("/todo/tasks", data={"title": "새 할 일"})
    assert _logs(db, "weekly_tasks") == []


def test_member_cannot_write_into_someone_elses_week(client, db, users):
    from sqlalchemy import select

    from app.models import WeeklyRoutine, WeeklyTask

    other = _task(db, users["u2"].id)
    _login(client, "01000000001")

    assert client.post("/todo/tasks", data={"title": "끼워 넣기",
                                             "member": str(users["u2"].id)},
                       follow_redirects=False).status_code == 403
    assert client.post("/todo/routines", data={"title": "끼워 넣기",
                                                "member": str(users["u2"].id)},
                       follow_redirects=False).status_code == 403
    assert client.post("/todo/carry-over", data={"member": str(users["u2"].id)},
                       follow_redirects=False).status_code == 403
    assert client.patch(f"/api/todo/tasks/{other.id}",
                        json={"title": "가로채기"}).status_code == 404
    assert client.post(f"/todo/tasks/{other.id}/delete",
                       follow_redirects=False).status_code == 404
    db.expire_all()
    assert not db.execute(select(WeeklyTask).where(WeeklyTask.title == "끼워 넣기")).first()
    assert not db.execute(select(WeeklyRoutine).where(WeeklyRoutine.title == "끼워 넣기")).first()
    assert db.get(WeeklyTask, other.id).title == "홍길동 미팅 준비"


def test_admin_manages_the_members_routines(client, db, users, admin):
    from sqlalchemy import select

    from app.models import WeeklyRoutine

    _login(client, "01000000009")
    r = client.post("/todo/routines", data={"category": "메일", "title": "주간 보고 정리",
                                             "weekdays": ["0", "3"],
                                             "member": str(users["u1"].id)},
                    follow_redirects=False)
    assert f"member={users['u1'].id}" in r.headers["location"]
    routine = db.execute(select(WeeklyRoutine).where(
        WeeklyRoutine.title == "주간 보고 정리")).scalars().one()
    assert routine.user_id == users["u1"].id and routine.weekdays == "0,3"

    assert client.patch(f"/api/todo/routines/{routine.id}",
                        json={"time_of_day": "am"}).status_code == 200
    r = client.post(f"/todo/routines/{routine.id}/delete", data={"week": ""},
                    follow_redirects=False)
    assert f"member={users['u1'].id}" in r.headers["location"]
    db.expire_all()
    assert db.get(WeeklyRoutine, routine.id).is_active == 0

    logs = _logs(db, "weekly_routines")
    assert logs and all(l.actor_user_id == admin.id
                        and l.target_user_id == users["u1"].id for l in logs)


def test_admin_carries_over_the_members_unfinished_work(client, db, users, admin):
    from datetime import date, timedelta

    from sqlalchemy import select

    from app.models import WeeklyTask
    from app.services import weekly

    this_week = weekly.week_start(date.today())
    last_week = this_week - timedelta(days=7)
    db.add(WeeklyTask(user_id=users["u1"].id, week_start=last_week.isoformat(),
                      category="메일", title="못 끝낸 일", status="todo"))
    db.commit()
    _login(client, "01000000009")

    r = client.post("/todo/carry-over", data={"week": this_week.isoformat(),
                                               "member": str(users["u1"].id)},
                    follow_redirects=False)
    assert r.status_code == 303 and f"member={users['u1'].id}" in r.headers["location"]
    moved = db.execute(select(WeeklyTask).where(
        WeeklyTask.title == "못 끝낸 일",
        WeeklyTask.week_start == this_week.isoformat())).scalars().all()
    assert [m.user_id for m in moved] == [users["u1"].id]


def test_todo_has_no_send_controls(client, db, users, admin):
    """주간업무 화면에는 발송을 시작하는 자리가 없다 — 남의 화면에서도."""
    _login(client, "01000000009")
    body = client.get(f"/todo?member={users['u1'].id}").text
    for needle in ("/api/jobs/", "/api/deals/send", "/api/deals/manual-sends", "발송 시작"):
        assert needle not in body
