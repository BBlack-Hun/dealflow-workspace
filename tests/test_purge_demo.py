"""데모 계정을 지울 때 **주간 업무가 붙들지 않는가**.

`weekly_routines` · `weekly_tasks` · `weekly_routine_runs` 는 셋 다 `users.id` 를
가리키고 SQLite 는 `PRAGMA foreign_keys=ON` 으로 돈다(`app/db.py`). 그래서 딸린
줄이 하나라도 남아 있으면 계정 삭제가

    sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError)
    FOREIGN KEY constraint failed
    [SQL: DELETE FROM users WHERE users.id IN (?, ?)]

로 튕긴다. 그리고 **가상 계정은 거의 다 그 상태가 된다** — `/todo` 를 한 번만
열어도 그 주 목록이 채워지기 때문이다(`services/weekly.py` 의 `fill_week`).
데모를 써 보고 지우려는 사람이 딱 그때 이 벽을 만난다.
"""
from __future__ import annotations


def _demo_user(db, at: int = 0):
    """부트스트랩이 만드는 가상 계정 하나 — **번호로 판정한다.**

    지울 것을 이름이 아니라 부트스트랩 목록으로 가리는 스크립트라
    (`scripts/purge_demo.py` 머리말), 검사도 그 목록에서 번호를 가져와야 한다.
    이미 그 번호가 있으면 그것을 쓴다 — `users` 픽스처가 같은 번호를 하나 쓴다.
    """
    from app.models import User
    from app.services import auth as auth_svc
    from scripts.bootstrap import DEMO_USERS

    row = DEMO_USERS[at]
    user = db.query(User).filter_by(phone=row["phone"]).one_or_none()
    if user is None:
        user = User(name=row["name"], phone=row["phone"], role=row["role"],
                    password_hash=auth_svc.hash_password("dealflow123"))
        db.add(user)
        db.commit()
    return user


def test_a_demo_account_with_weekly_work_can_still_be_purged(db):
    from app.models import User, WeeklyRoutine, WeeklyRoutineRun, WeeklyTask
    from app.services import weekly
    from scripts.purge_demo import purge

    user = _demo_user(db)

    # 화면을 한 번 여는 것과 같은 상태를 만든다 — 규칙이 깔리고 그 주가 채워지고
    # 만들었다는 표시가 남는다.
    weekly.ensure_routines(db, user)
    made = weekly.fill_week(db, user, weekly.week_start())
    assert made, "그 주가 안 채워졌다 — 이 검사가 헛돈다"
    assert db.query(WeeklyRoutineRun).filter_by(user_id=user.id).count() == made

    purge(db, apply=True)

    assert db.query(User).filter_by(phone=user.phone).count() == 0, (
        "주간 업무가 붙들어 가상 계정이 안 지워졌습니다")
    for model in (WeeklyRoutineRun, WeeklyTask, WeeklyRoutine):
        assert db.query(model).filter_by(user_id=user.id).count() == 0, (
            f"{model.__tablename__} 에 지운 계정의 줄이 남았습니다")


def test_purging_leaves_other_peoples_weekly_work_alone(db, users):
    """지우는 것은 **가상 계정 몫**뿐이다. 같은 표에 있는 남의 줄은 그대로."""
    from app.models import WeeklyTask
    from app.services import weekly
    from scripts.purge_demo import purge

    # `users` 픽스처의 u2 가 가상 계정 첫 번째와 **같은 번호**를 쓴다. 그 사람은
    # 이 검사에서 지워질 쪽이므로, 남아야 할 줄은 u1 에 둔다.
    demo = _demo_user(db, at=1)
    weekly.ensure_routines(db, demo)
    weekly.fill_week(db, demo, weekly.week_start())

    mine = WeeklyTask(user_id=users["u1"].id, week_start=weekly.week_start().isoformat(),
                      category="메일", title="내 일")
    db.add(mine)
    db.commit()

    purge(db, apply=True)

    assert db.query(WeeklyTask).filter_by(user_id=users["u1"].id).count() == 1
