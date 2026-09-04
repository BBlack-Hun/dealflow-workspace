"""자동 첨부 칸이 생기는 판(0059) — **이미 쓰고 있던 사람이 잃지 않는가.**

`tests/test_migrations.py` 는 빈 DB 로 오르내리며 표와 칸을 본다. 그 길에는
**계정이 한 줄도 없어서** 이 판의 데이터 부분이 한 번도 밟히지 않는다 — 그런데
사고가 나는 곳은 정확히 거기다.

새 칸의 기본값은 `0` 이다. 그대로 배포하면 지금 자료 폴더를 넣어 두고 발송기에게
자료를 맡기고 있는 계정이 **배포하는 그 순간 자동 첨부를 잃는다.** 아무도 끄지
않았는데. 그 사람은 다음 회차에 문구만 나간 것을 받는 쪽에서 알게 된다.

그래서 운영과 같은 모양을 세워 놓고 그 길을 밟는다: 폴더를 넣어 둔 계정 ·
공백만 넣어 둔 계정 · 넣지 않은 계정 · 정지된 계정.
"""
from __future__ import annotations

import sqlite3

import pytest

from .test_migrations import _alembic

BEFORE = "0058_startup_db_one_liner"
FOLDER = "/Users/tester/Share/자료폴더"
NOW = "2026-09-04T00:00:00+09:00"


def _columns(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("users")')}
    finally:
        con.close()


def _flags(db) -> dict:
    """이름 → 자동 첨부 칸. 칸이 없으면 빈 표(내려간 상태)."""
    if "can_auto_attach_ir" not in _columns(db):
        return {}
    con = sqlite3.connect(db)
    try:
        return dict(con.execute(
            "SELECT name, can_auto_attach_ir FROM users ORDER BY name"))
    finally:
        con.close()


@pytest.fixture()
def old_db(tmp_path):
    """운영과 **같은 모양**: 0058 까지 올라와 있고, 계정마다 폴더 사정이 다르다.

    빈 DB 를 0058 까지 올린 뒤 새 칸을 **손으로 지운다.** `0001` 은
    `Base.metadata.create_all()` 로 지금 모델 전체를 만들기 때문에 그 길에서는
    0058 자리에서도 이 칸이 이미 있는데, 실제 운영 DB 는 처음 세워질 때의 모델로
    만들어져 이 칸이 없다 — 여기서 보려는 것이 바로 **그 DB 가 지나는 길**이다.
    (`0056` 검사가 칸 이름을 손으로 되돌리는 것과 같은 자리다.)
    """
    db = tmp_path / "old.db"
    done = _alembic(db, "upgrade", BEFORE)
    assert done.returncode == 0, done.stdout + done.stderr

    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE users DROP COLUMN can_auto_attach_ir")
        add_user = ("INSERT INTO users (id, name, phone, role, weekly_goal_sends, "
                    "is_active, must_change_password, can_view_consulting, "
                    "created_at, updated_at) "
                    f"VALUES (?, ?, ?, ?, 30, ?, 0, 0, '{NOW}', '{NOW}')")
        add_device = ("INSERT INTO agent_devices (user_id, token, ir_root, "
                      f"created_at, updated_at) VALUES (?, ?, ?, '{NOW}', '{NOW}')")
        # ① 폴더를 넣어 두고 쓰고 있던 사람 — 이 판이 켜 주어야 한다.
        con.execute(add_user, (1, "쓰던사람", "01000000001", "user", 1))
        con.execute(add_device, (1, "agt_1", FOLDER))
        # ② 기기는 붙었는데 폴더는 안 넣은 사람.
        con.execute(add_user, (2, "안쓰던사람", "01000000002", "user", 1))
        con.execute(add_device, (2, "agt_2", None))
        # ③ 공백만 들어 있는 사람 — 옮기기 전 판정이 **빈 것으로 보았다.**
        con.execute(add_user, (3, "공백사람", "01000000003", "user", 1))
        con.execute(add_device, (3, "agt_3", "   "))
        # ④ 기기 줄이 아예 없는 사람(발송기를 한 번도 안 켰다).
        con.execute(add_user, (4, "기기없음", "01000000004", "user", 1))
        # ⑤ 폴더를 넣어 뒀는데 정지된 계정 — 되살렸을 때 예전과 같아야 한다.
        con.execute(add_user, (5, "정지된사람", "01000000005", "user", 0))
        con.execute(add_device, (5, "agt_5", FOLDER))
        con.commit()
    finally:
        con.close()
    return db


def test_the_column_arrives(old_db):
    assert "can_auto_attach_ir" not in _columns(old_db), "준비가 틀렸다"

    up = _alembic(old_db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert "can_auto_attach_ir" in _columns(old_db)


def test_whoever_had_a_folder_keeps_working(old_db):
    """★ 배포 그 순간 아무도 기능을 잃지 않는다.

    무엇이 "지금 켜져 있는 계정" 인가는 **옮기기 전 코드의 판정 그대로**다 —
    `ir_root` 가 비어 있지 않은 계정. 공백만 든 값은 그 판정이 빈 것으로
    보았으므로 여기서도 그렇게 본다.
    """
    assert _alembic(old_db, "upgrade", "head").returncode == 0

    assert _flags(old_db) == {
        "쓰던사람": 1,       # 폴더가 있었다 → 켜 둔다
        "정지된사람": 1,     # 정지돼 있어도 켜 둔다 — 되살렸을 때 예전과 같아야
        "안쓰던사람": 0,
        "공백사람": 0,       # 공백은 폴더가 아니다
        "기기없음": 0,
    }


def test_the_folder_itself_is_untouched(old_db):
    """이 판은 **권한만** 옮긴다 — 경로는 그 PC 앞에 앉은 사람의 값이다."""
    assert _alembic(old_db, "upgrade", "head").returncode == 0

    con = sqlite3.connect(old_db)
    try:
        roots = dict(con.execute(
            "SELECT user_id, ir_root FROM agent_devices ORDER BY user_id"))
    finally:
        con.close()
    assert roots == {1: FOLDER, 2: None, 3: "   ", 5: FOLDER}


def test_coming_back_down_takes_the_column_away(old_db):
    """되돌리면 코드도 함께 돌아가 판정이 다시 `폴더가 찼는가` 하나가 된다 —
    그 코드는 이 칸을 아예 읽지 않으므로 되짚어 둘 값이 없다."""
    assert _alembic(old_db, "upgrade", "head").returncode == 0

    down = _alembic(old_db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
    assert "can_auto_attach_ir" not in _columns(old_db)


def test_it_can_go_up_again_after_coming_down(old_db):
    """내렸다 올리는 길이 한 번만 되는 것과 계속 되는 것은 다르다."""
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    after_first = _flags(old_db)

    assert _alembic(old_db, "downgrade", BEFORE).returncode == 0
    again = _alembic(old_db, "upgrade", "head")
    assert again.returncode == 0, again.stdout + again.stderr
    assert _flags(old_db) == after_first, "다시 올렸더니 값이 달라졌다"


def test_running_it_twice_changes_nothing(old_db):
    """운영에서는 배포할 때마다 `upgrade head` 를 돈다."""
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    once = _flags(old_db)

    twice = _alembic(old_db, "upgrade", "head")
    assert twice.returncode == 0, twice.stdout + twice.stderr
    assert _flags(old_db) == once


def test_a_hand_switched_account_survives_the_next_deploy(old_db):
    """★ 사람이 켜고 끈 값을 **다음 배포가 덮지 않는다.**

    이 판은 한 번 돌고 끝나야 한다. 매번 도는 자리였다면 관리자가 끈 계정이
    (폴더는 남아 있으니) 배포할 때마다 되살아난다 — 껐는데 다시 켜지는 것을
    아무도 못 알아챈다.
    """
    assert _alembic(old_db, "upgrade", "head").returncode == 0

    con = sqlite3.connect(old_db)
    try:
        con.execute("UPDATE users SET can_auto_attach_ir = 0 WHERE name = ?",
                    ("쓰던사람",))
        con.commit()
    finally:
        con.close()

    assert _alembic(old_db, "upgrade", "head").returncode == 0
    assert _flags(old_db)["쓰던사람"] == 0, "관리자가 끈 것이 배포로 되살아났다"


def test_a_fresh_db_gets_the_column_from_the_start(tmp_path):
    """빈 DB 는 `0001` 이 모델 전체를 만든다 — 거기서 또 붙이면 부팅이 죽는다."""
    db = tmp_path / "fresh.db"
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert "can_auto_attach_ir" in _columns(db)

    down = _alembic(db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
