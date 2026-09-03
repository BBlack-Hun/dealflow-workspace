"""일일 백업과 관리자 되돌리기.

## 왜 이 검사가 있나

되돌리기 기능만 만들고 **백업이 없으면 돌아갈 지점이 없다.** 서버가 실제로 그
상태였다 — `deploy/README.md` 는 크론을 걸라고 적어 두었는데 어느 크론탭에도
없었고, 남아 있는 백업은 배포할 때마다 뜨는 `predeploy-*` 뿐이라 **배포가 없는
주에는 하루도 안 떴다.** 아무도 그것을 몰랐다는 것이 진짜 문제다.

그래서 여기서 지키는 것은 셋이다.

1. **하루 한 번 뜬다** — 그리고 오래된 것만 지운다. 성격이 다른 백업
   (`predeploy-*` · `before-restore-*`)은 건드리지 않는다.
2. **멈추면 화면이 안다** — 낡은 백업은 `stale` 로 뜬다.
3. **되돌리면 진짜로 돌아온다** — 그리고 되돌리기 전 상태가 남는다.

날짜는 전부 `today=` 로 못박는다. 자정에 결과가 바뀌는 검사를 만들지 않는다.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pytest

from .conftest import DEMO_PASSWORD

# 검사가 기준으로 삼는 날. 실제 오늘이 언제든 결과가 같아야 한다.
TODAY = date(2026, 9, 3)


@pytest.fixture()
def backups(db):
    """백업 폴더를 비우고 시작한다.

    conftest 의 임시 폴더는 **검사 전체가 같이 쓴다.** 앞 검사가 남긴
    `daily-*.db` 가 그대로 있으면 뒤 검사의 개수가 어긋난다.
    """
    from app.services import backup

    live = backup.db_path()
    for path in backup.backup_dir().glob("*.db"):
        if path.name != live.name:
            path.unlink()
    backup._LAST_ERROR = None
    return backup


def _stamp(path, revision: str) -> None:
    """그 파일이 어느 알렘빅 판인지 적어 둔다.

    검사용 DB 는 `Base.metadata.create_all()` 로 만들어서 `alembic_version` 이
    없다(conftest). 실제 백업에는 늘 들어 있는 값이라, 없는 채로 두면 검사만
    현실과 다른 길을 걷는다.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS alembic_version "
                     "(version_num VARCHAR(32) NOT NULL)")
        conn.execute("DELETE FROM alembic_version")
        conn.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        conn.commit()
    finally:
        conn.close()


def _head() -> str:
    from app.services import backup

    return backup.known_revisions()[1]


# --- 1. 하루 한 번 뜬다 -------------------------------------------------------

def test_the_daily_backup_is_made_once_a_day(backups):
    made = backups.run_daily(TODAY)
    assert made is not None
    assert made.name == "daily-20260903.db"
    assert made.exists()

    # 같은 날 또 불러도 새로 뜨지 않는다 — 30분마다 깨어나 보기 때문이다.
    again = backups.run_daily(TODAY)
    assert again is None
    assert len(list(backups.backup_dir().glob("daily-*.db"))) == 1


def test_the_backup_is_a_real_openable_database(backups):
    """파일만 생기고 열리지 않으면 백업이 아니다."""
    made = backups.run_daily(TODAY)
    conn = sqlite3.connect(f"file:{made}?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # 표가 실려 있는가 (conftest 가 만든 스키마)
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "users" in names
    finally:
        conn.close()


def test_a_missing_day_is_still_backed_up_when_the_app_comes_back(backups):
    """정해진 시각에 거는 방식이면 그날을 조용히 건너뛴다.

    어제 것만 있고 오늘 것이 없으면, 몇 시에 깨어나든 오늘 것을 뜬다.
    """
    backups.run_daily(TODAY - timedelta(days=1))
    assert backups.run_daily(TODAY) is not None
    assert (backups.backup_dir() / "daily-20260903.db").exists()


# --- 2. 오래된 것만 지운다 ----------------------------------------------------

def test_only_the_last_week_is_kept(backups):
    """사용자가 '1주일이면 충분하다' 고 했다 — 7일치가 남는다.

    12일치가 쌓여 있는 상태에서 **오늘 백업이 돌면** 오래된 것이 정리된다.
    (정리는 그날 백업이 돌 때 같이 일어난다 — 따로 도는 것이 아니다.)
    """
    for back in reversed(range(0, 12)):
        backups.run_daily(TODAY - timedelta(days=back))

    left = sorted(p.name for p in backups.backup_dir().glob("daily-*.db"))
    assert left == [
        "daily-20260828.db", "daily-20260829.db", "daily-20260830.db",
        "daily-20260831.db", "daily-20260901.db", "daily-20260902.db",
        "daily-20260903.db",
    ]


def test_other_kinds_of_backup_are_never_deleted(backups):
    """`predeploy-*` 는 성격이 다른 백업이다 — 정리 대상이 아니다.

    되돌리기 직전 백업(`before-restore-*`)은 더더욱 그렇다. 7일 규칙에 걸려
    사라지면 **잘못 되돌렸을 때 돌아올 곳**이 없어진다.
    """
    d = backups.backup_dir()
    keep = [d / "predeploy-20250101-000000.db",
            d / "before-restore-20250101-000000.db",
            d / "손으로뜬것.db"]
    for path in keep:
        path.write_bytes(b"")

    for back in reversed(range(0, 30)):
        backups.run_daily(TODAY - timedelta(days=back))

    for path in keep:
        assert path.exists(), f"{path.name} 이 지워졌다"
    # 일일 백업만 7개로 줄었다.
    assert len(list(d.glob("daily-*.db"))) == 7


# --- 3. 멈추면 화면이 안다 ----------------------------------------------------

def test_a_fresh_backup_looks_healthy(backups):
    backups.run_daily(TODAY)
    health = backups.health()
    assert not health.stale
    assert health.latest == "daily-20260903.db"
    assert health.count == 1


def test_no_backup_at_all_is_reported_as_stale(backups):
    """이것이 지금 서버의 상태다 — 화면이 조용하면 안 된다."""
    health = backups.health()
    assert health.stale
    assert health.latest is None
    assert "하나도 없습니다" in health.detail


def test_a_backup_that_stopped_days_ago_is_reported_as_stale(backups):
    """배포가 없는 주에는 하루도 안 뜨던 상태를 화면이 잡아내야 한다."""
    made = backups.run_daily(TODAY)
    # 파일을 사흘 낡게 만든다(mtime 이 증거다).
    old = (datetime.now() - timedelta(days=3)).timestamp()
    import os

    os.utime(made, (old, old))

    health = backups.health()
    assert health.stale
    assert "멈춘 것 같습니다" in health.detail


# --- 4. 알렘빅 판을 본다 ------------------------------------------------------

def test_a_backup_from_the_future_is_refused(backups):
    """백업이 코드보다 **앞서** 있으면 되돌리면 안 된다.

    코드가 모르는 판이라는 것은 그 백업이 더 새 스키마라는 뜻이다. 되돌리면
    지금 코드가 읽을 줄 모르는 표를 마주한다.
    """
    known, head = backups.known_revisions()
    verdict, note = backups.verdict_for("9999_from_the_future", known, head)
    assert verdict == "ahead"
    assert verdict not in backups.SAFE_VERDICTS
    assert "되돌리면 안 됩니다" in note


def test_a_backup_with_no_schema_version_is_refused(backups):
    known, head = backups.known_revisions()
    verdict, _ = backups.verdict_for(None, known, head)
    assert verdict == "unknown"
    assert verdict not in backups.SAFE_VERDICTS


def test_the_current_and_older_versions_are_allowed(backups):
    known, head = backups.known_revisions()
    assert backups.verdict_for(head, known, head)[0] == "same"
    # 첫 판은 코드가 아는 옛 판이다 — 되돌린 뒤 올리면 된다.
    assert backups.verdict_for("0001_initial", known, head)[0] == "behind"


def test_the_list_marks_unsafe_points_but_still_shows_them(backups):
    """숨기지 않는다 — 있는데 안 보이면 왜 못 돌아가는지 알 수 없다."""
    backups.run_daily(TODAY)
    _stamp(backups.backup_dir() / "daily-20260903.db", "9999_from_the_future")

    points = backups.restore_points()
    assert [p.name for p in points] == ["daily-20260903.db"]
    assert points[0].safe is False
    assert points[0].verdict == "ahead"


def test_the_live_database_is_not_offered_as_a_restore_point(backups):
    backups.run_daily(TODAY)
    names = [p.name for p in backups.restore_points()]
    assert backups.db_path().name not in names


# --- 5. 되돌리면 진짜로 돌아온다 ----------------------------------------------

def _company_names(session) -> set:
    from sqlalchemy import select

    from app.models import IrCompany

    return {c.name for c in session.execute(select(IrCompany)).scalars().all()}


def test_restoring_brings_the_data_back(backups, db, users):
    """이 검사가 이 기능의 전부다 — 바꾸고, 되돌리고, 원래대로 오는가."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import IrCompany

    db.add(IrCompany(name="되돌리기전에있던회사"))
    db.commit()

    # 지금 상태를 지점으로 만든다(= 일일 백업이 하는 일과 같다).
    made = backups.run_daily(TODAY)
    _stamp(made, _head())

    # 그 뒤에 데이터가 바뀐다.
    db.add(IrCompany(name="백업뒤에들어온회사"))
    gone = db.execute(select(IrCompany)
                      .where(IrCompany.name == "되돌리기전에있던회사")).scalar_one()
    db.delete(gone)
    db.commit()

    check = SessionLocal()
    assert _company_names(check) == {"백업뒤에들어온회사"}
    check.close()

    point = backups.find_point(made.name)
    assert point.safe, point.note

    # 우리 연결을 놓고 되돌린다(라우터가 하는 것과 같은 순서).
    db.close()
    result = backups.restore(point, now=datetime(2026, 9, 3, 14, 30))

    after = SessionLocal()
    try:
        assert _company_names(after) == {"되돌리기전에있던회사"}
    finally:
        after.close()

    # 되돌리기 직전 상태가 남아 있다 — 잘못 되돌렸을 때 돌아올 곳.
    safety = backups.backup_dir() / result["safety"]
    assert safety.exists()
    assert result["safety"] == "before-restore-20260903-143000.db"

    conn = sqlite3.connect(f"file:{safety}?mode=ro", uri=True)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM ir_companies")}
        assert names == {"백업뒤에들어온회사"}, "되돌리기 직전 상태가 안 남았다"
    finally:
        conn.close()


def test_the_app_keeps_working_after_a_restore(backups, db, users):
    """되돌린 뒤 화면이 열려야 한다 — 앱을 세우지 않는 방식이라 더 중요하다."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import IrCompany

    db.add(IrCompany(name="복구확인용회사"))
    db.commit()
    made = backups.run_daily(TODAY)
    _stamp(made, _head())

    db.close()
    backups.restore(backups.find_point(made.name))

    with TestClient(create_app()) as client:
        assert client.get("/health").json()["status"] == "ok"
        r = client.post("/login", data={"phone": "01000000001",
                                        "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303, "되돌린 뒤 로그인이 안 된다"


def test_a_point_the_code_cannot_read_is_never_restored(backups, db):
    """판정이 화면에만 있으면 주소를 직접 두드려 지나갈 수 있다."""
    made = backups.run_daily(TODAY)
    _stamp(made, "9999_from_the_future")
    point = backups.find_point(made.name)

    with pytest.raises(backups.BackupError):
        backups.restore(point)


# --- 6. 무엇이 바뀌는지 먼저 보여준다 -----------------------------------------

def test_the_preview_counts_what_will_change(backups, db, users):
    """날짜만 보고 누르게 하면 안 된다."""
    from app.models import IrCompany

    made = backups.run_daily(TODAY)
    _stamp(made, _head())
    db.add_all([IrCompany(name=f"백업뒤회사{i}") for i in range(3)])
    db.commit()

    rows = {r["table"]: r for r in backups.diff(backups.find_point(made.name))}
    # 되돌리면 3곳이 사라진다.
    assert rows["ir_companies"]["now"] == 3
    assert rows["ir_companies"]["then"] == 0
    assert rows["ir_companies"]["delta"] == -3
    # 사람이 읽을 이름이 붙는다 — `ir_companies` 로는 무엇이 사라지는지 모른다.
    assert rows["ir_companies"]["label"] == "IR 기업"


def test_the_preview_warns_when_you_could_lock_yourself_out(backups, db, users):
    """백업에 내 계정이 없으면 되돌린 뒤 **다시 들어올 수 없다.**

    로그인 세션이 DB 안에 있어서 되돌리면 어차피 로그아웃되는데, 계정 자체가
    그 백업에 없으면 그것으로 끝이다.
    """
    from app.models import User
    from app.services import auth as auth_svc

    made = backups.run_daily(TODAY)          # 이 시점에는 관리자가 없다
    _stamp(made, _head())
    db.add(User(id=91, name="나중에만든관리자", phone="01000000091", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()

    point = backups.find_point(made.name)
    risk = backups.login_risk(point, "01000000091")
    assert risk.me is False
    assert risk.admins == 0
    assert "관리자 계정이 하나도 없습니다" in risk.warning


# --- 7. 발송 중에는 되돌리지 않는다 -------------------------------------------

@pytest.mark.parametrize("status", ["queued", "running"])
def test_a_send_in_flight_blocks_the_restore(backups, db, users, status):
    """회차 중간에 되돌리면 이미 받은 투자사에게 **또 나간다.**"""
    from app.models import SendJob

    db.add(SendJob(user_id=1, status=status, total=10, sent=4))
    db.commit()
    assert [j.status for j in backups.sending_now(db)] == [status]


@pytest.mark.parametrize("status", ["draft", "paused", "done",
                                    "done_with_errors", "canceled"])
def test_a_finished_or_stopped_send_does_not_block(backups, db, users, status):
    """멈춘 회차까지 막으면 취소된 회차 하나 때문에 영영 못 되돌린다."""
    from app.models import SendJob

    db.add(SendJob(user_id=1, status=status, total=10, sent=4))
    db.commit()
    assert backups.sending_now(db) == []


# --- 8. 관리자만 -------------------------------------------------------------
#
# **팀원도 막는다.** 되돌리기는 팀 전체의 데이터를 한 번에 옛 것으로 바꾸는
# 조작이라, 딜소개를 보내는 팀원이 실수로라도 닿으면 안 된다. 판정은
# `deps.admin_only` 하나를 쓴다 — 라우터마다 `role != "admin"` 을 적으면 화면과
# 조작의 응답 규칙이 갈린다(그래서 팀 현황이 주소창에 날것의 JSON 을 뿌렸다).

@pytest.fixture()
def portal(db, users):
    """역할별로 따로 로그인한 클라이언트.

    한 클라이언트로 로그인을 갈아타면 쿠키가 덮여, 어느 사람으로 부른 것인지
    알 수 없게 된다(`tests/test_admin_guard.py` 와 같은 방식).
    """
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    pw = auth_svc.hash_password(DEMO_PASSWORD)
    db.add_all([
        User(id=81, name="관리자시험", phone="01000000081", role="admin",
             password_hash=pw),
        User(id=82, name="컨설턴트시험", phone="01000000082", role="consultant",
             password_hash=pw),
    ])
    db.commit()

    app = create_app()

    def sign_in(phone: str):
        client = TestClient(app)
        r = client.post("/login", data={"phone": phone, "password": DEMO_PASSWORD},
                        follow_redirects=False)
        assert r.status_code == 303
        return client

    return {"member": sign_in("01000000001"),      # 일반 팀원
            "admin": sign_in("01000000081"),
            "consultant": sign_in("01000000082")}


def test_a_member_cannot_open_the_restore_screen(portal):
    """팀원에게는 권한 안내가 뜬다 — 되돌리기 화면이 아니라.

    안내는 `deps.admin_block_response` 가 그리는 화면이다(날것의 JSON 이
    아니다). 좌측 메뉴에 없는 주소라 이름 대신 '이 화면' 으로 부른다.
    """
    resp = portal["member"].get("/team/restore")
    assert "관리자만 볼 수 있습니다" in resp.text
    assert "guard-modal" in resp.text
    # 막혔는데 내용이 비치면 막은 것이 아니다.
    assert "되돌릴 수 있는 지점" not in resp.text
    assert "일일 백업 상태" not in resp.text


def test_a_member_cannot_actually_restore(portal, backups, db, users):
    """화면만 막고 조작이 열려 있으면 주소를 직접 두드려 지나갈 수 있다."""
    from sqlalchemy import select

    from app.models import IrCompany

    made = backups.run_daily(TODAY)
    _stamp(made, _head())
    db.add(IrCompany(name="팀원이지우면안되는회사"))
    db.commit()

    resp = portal["member"].post("/team/restore/apply", data={"name": made.name},
                                 follow_redirects=False)
    assert resp.status_code == 403, "팀원이 데이터를 통째로 되돌릴 수 있다"

    # 상태 코드만 맞고 실제로는 되돌아갔을 수 있다 — 데이터가 그대로인지 본다.
    db.rollback()
    assert db.execute(select(IrCompany)
                      .where(IrCompany.name == "팀원이지우면안되는회사")
                      ).scalar_one_or_none() is not None
    # 되돌리기 직전 백업도 안 생겼다(시작조차 안 했다는 뜻).
    assert not list(backups.backup_dir().glob("before-restore-*.db"))


def test_a_consultant_is_sent_to_their_own_screen(portal):
    """컨설턴트 차단이 먼저다 — 남의 화면 이름을 보게 두지 않는다."""
    resp = portal["consultant"].get("/team/restore", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/consulting"


def test_the_admin_sees_the_real_screen(portal, backups):
    backups.run_daily(TODAY)
    body = portal["admin"].get("/team/restore").text
    assert "되돌릴 수 있는 지점" in body
    assert "일일 백업 상태" in body


def test_the_restore_screen_works_without_javascript(portal, backups):
    """되돌리기는 하필 **무언가 잘못됐을 때** 쓴다.

    그날 스크립트 하나가 어긋나 있으면 되돌릴 방법이 통째로 사라진다 — 고르는
    것도 확인하는 것도 평범한 링크와 폼이어야 한다.
    """
    made = backups.run_daily(TODAY)
    _stamp(made, _head())
    body = portal["admin"].get(f"/team/restore?pick={made.name}").text
    block = body[body.index('<main class="content">'):body.index("</main>")]
    assert "<script" not in block
    assert "onclick" not in block
    assert f'<form method="post" action="/team/restore/apply"' in block


def test_the_team_screen_shows_whether_backups_are_running(portal, backups):
    """되돌리기 화면 안에만 두면, 되돌릴 일이 생기고 나서야 백업이 없다는 것을 안다."""
    body = portal["admin"].get("/team").text
    assert "데이터 백업" in body
    assert "일일 백업이 하나도 없습니다" in body      # 지금은 하나도 없다
    assert 'href="/team/restore"' in body


def test_the_admin_stays_logged_in_after_a_restore(backups, db, users):
    """되돌린 사람이 결과를 볼 수 있어야 한다.

    로그인 세션은 **DB 안에 있다**(`sessions` 표). 되돌리면 그 시점 세션으로
    바뀌므로, 백업이 로그인보다 앞선 보통의 경우 누른 사람은 결과 알림도 못
    보고 로그인 화면으로 튕긴다 — 되돌아갔는지 아닌지조차 알 수 없다.
    계정이 그 시점에도 있다면 세션을 다시 붙여 준다.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.models import User
    from app.services import auth as auth_svc

    db.add(User(id=83, name="관리자시험", phone="01000000083", role="admin",
                password_hash=auth_svc.hash_password(DEMO_PASSWORD)))
    db.commit()

    # **아직 아무도 로그인하지 않은** 시점을 뜬다.
    made = backups.run_daily(TODAY)
    _stamp(made, _head())

    client = TestClient(create_app())
    assert client.post("/login", data={"phone": "01000000083",
                                       "password": DEMO_PASSWORD},
                       follow_redirects=False).status_code == 303

    db.close()
    done = client.post("/team/restore/apply", data={"name": made.name},
                       follow_redirects=False)
    assert done.status_code == 303

    landed = client.get(done.headers["location"])
    assert landed.status_code == 200
    assert "/login" not in str(landed.url), "되돌린 사람이 로그인 화면으로 튕겼다"
    assert "지점으로 되돌렸습니다" in landed.text
    assert "되돌리기 직전 상태는" in landed.text


def test_pruning_leaves_no_orphan_wal_files(backups):
    """스냅샷은 원본의 WAL 모드를 물려받아 **읽기만 해도** 곁딸린 파일이 생긴다.

    본체만 지우면 주인 없는 `-wal`·`-shm` 이 폴더에 영영 쌓인다 — 목록에는
    안 뜨므로(`*.db` 만 훑는다) 아무도 모른 채 늘어난다.
    """
    old = backups.run_daily(TODAY - timedelta(days=30))
    for tail in ("-wal", "-shm"):
        old.with_name(old.name + tail).write_bytes(b"")

    backups.run_daily(TODAY)

    assert not old.exists()
    leftovers = sorted(p.name for p in backups.backup_dir().iterdir()
                       if p.name.startswith(old.name))
    assert leftovers == [], f"주인 없는 부스러기가 남았다: {leftovers}"
