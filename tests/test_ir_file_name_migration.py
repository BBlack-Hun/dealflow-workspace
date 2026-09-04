"""자료 칸의 이름이 바뀌는 판(0056) — **값을 잃지 않고** 오르내리는가.

`tests/test_migrations.py` 는 빈 DB 로 오르내리며 **표와 칸**을 본다. 그 길에서는
`0001` 이 이미 새 이름으로 표를 만들어 두어서, 이름을 바꾸는 코드가 아예 돌지
않는다 — 즉 **운영 DB 가 지나는 그 길은 거기서 한 번도 안 밟힌다.**

여기서는 운영과 같은 모양을 세워 놓고 그 길을 밟는다: 칸 이름이 `ir_drive_url`
이고, 그 칸에 폐기된 드라이브 링크가 남아 있는 DB.

**실측**(이 판을 쓰기 직전 운영 DB): 344곳 중 값이 있는 칸 3곳, 전부
`https://drive.google.com/…`, 파일명 꼴 0곳.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from .test_migrations import _alembic

BEFORE = "0055_agent_ir_root"
LINK = "https://drive.google.com/file/d/sample/view"
MARK = "옛 IR 자료 링크(구글 드라이브): "


def _columns(db) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute('PRAGMA table_info("ir_companies")')}
    finally:
        con.close()


def _rows(db) -> list:
    con = sqlite3.connect(db)
    try:
        col = "ir_file_name" if "ir_file_name" in _columns(db) else "ir_drive_url"
        return con.execute(
            f"SELECT name, {col}, note FROM ir_companies ORDER BY name").fetchall()
    finally:
        con.close()


@pytest.fixture()
def old_db(tmp_path):
    """운영과 **같은 모양**: 칸 이름이 옛 이름이고, 그 칸에 링크가 들어 있다.

    빈 DB 를 `0055` 까지 올린 뒤 칸 이름을 손으로 되돌린다 — 0056 이전에 세워진
    DB 가 실제로 그 모양이다(그때의 `0001` 은 옛 이름으로 표를 만들었다).
    """
    db = tmp_path / "old.db"
    done = _alembic(db, "upgrade", BEFORE)
    assert done.returncode == 0, done.stdout + done.stderr

    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE ir_companies "
                    "RENAME COLUMN ir_file_name TO ir_drive_url")
        # 실제 표에는 NOT NULL 인 칸이 몇 개 더 있다 — 여기서 보는 값은 아니라
        # 그럴듯한 기본값으로 채운다.
        add = ("INSERT INTO ir_companies (name, ir_drive_url, note, "
               "contract_status, summary_status, is_top_deal, "
               "created_at, updated_at) "
               "VALUES (?, ?, ?, 'no', 'todo', 0, "
               "'2026-09-04T00:00:00+09:00', '2026-09-04T00:00:00+09:00')")
        con.execute(add, ("샘플애그", LINK, "이미 적혀 있던 비고"))
        con.execute(add, ("샘플메디", LINK, None))
        con.execute(add, ("샘플페이", None, None))
        con.commit()
    finally:
        con.close()
    return db


def test_the_column_takes_the_name_of_what_it_holds(old_db):
    assert "ir_drive_url" in _columns(old_db), "준비가 틀렸다"

    up = _alembic(old_db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr

    cols = _columns(old_db)
    assert "ir_file_name" in cols
    assert "ir_drive_url" not in cols, "옛 이름이 남으면 어느 쪽이 정본인지 갈린다"


def test_the_old_links_leave_the_file_name_column(old_db):
    """주소는 파일명이 아니다 — 남겨 두면 발송기가 거부할 값이 그대로 쌓인다."""
    _alembic(old_db, "upgrade", "head")

    values = {name: value for name, value, _note in _rows(old_db)}
    assert values == {"샘플애그": None, "샘플메디": None, "샘플페이": None}


def test_the_links_are_not_destroyed(old_db):
    """그 3곳의 자료는 **그 링크에만 있다.** 지우면 파일을 어디서 내려받는지
    아무도 모른다 — 자료를 잃는 것과 같다. 비고로 옮겨 둔다."""
    _alembic(old_db, "upgrade", "head")

    notes = {name: note for name, _value, note in _rows(old_db)}
    assert notes["샘플애그"] == f"이미 적혀 있던 비고\n{MARK}{LINK}", \
        "원래 적혀 있던 비고를 덮어쓰면 안 된다"
    assert notes["샘플메디"] == f"{MARK}{LINK}"
    assert notes["샘플페이"] is None, "값이 없던 줄에는 아무것도 적지 않는다"


def test_coming_back_down_puts_the_links_back(old_db):
    """올린 자리를 그대로 되짚는다 — 되돌린 DB 는 올리기 전과 같아야 한다."""
    before = _rows(old_db)

    assert _alembic(old_db, "upgrade", "head").returncode == 0
    down = _alembic(old_db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr

    assert "ir_drive_url" in _columns(old_db)
    assert _rows(old_db) == before, "내렸는데 올리기 전과 다르다"


def test_it_can_go_up_again_after_coming_down(old_db):
    """내렸다 올리는 길이 한 번만 되는 것과 계속 되는 것은 다르다."""
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    after_first = _rows(old_db)

    assert _alembic(old_db, "downgrade", BEFORE).returncode == 0
    again = _alembic(old_db, "upgrade", "head")
    assert again.returncode == 0, again.stdout + again.stderr

    assert _rows(old_db) == after_first, "다시 올렸더니 값이 달라졌다"
    # 표식이 두 벌 쌓이면 되돌리기가 어느 것이 마지막인지 헷갈린다.
    notes = {name: (note or "") for name, _value, note in _rows(old_db)}
    assert notes["샘플메디"].count(MARK) == 1


def test_a_person_who_typed_a_file_name_keeps_it(old_db, tmp_path):
    """되돌릴 때 **사람이 적은 값을 덮지 않는다**(0051 과 같은 규칙).

    올린 뒤에 파일명을 넣어 둔 줄은, 내려간다고 그 자리에 옛 링크가 들어오면
    안 된다 — 덮어쓴 값은 되찾을 수 없고, 링크는 비고에 그대로 남아 있다.
    """
    assert _alembic(old_db, "upgrade", "head").returncode == 0

    con = sqlite3.connect(old_db)
    try:
        con.execute("UPDATE ir_companies SET ir_file_name = ? WHERE name = ?",
                    ("샘플메디_IR.pdf", "샘플메디"))
        con.commit()
    finally:
        con.close()

    assert _alembic(old_db, "downgrade", BEFORE).returncode == 0

    values = {name: value for name, value, _note in _rows(old_db)}
    notes = {name: (note or "") for name, _value, note in _rows(old_db)}
    assert values["샘플메디"] == "샘플메디_IR.pdf", "사람이 적은 값이 지워졌다"
    assert MARK + LINK in notes["샘플메디"], "그러면 링크는 비고에 남아 있어야 한다"
    # 손대지 않은 줄은 그대로 되돌아간다.
    assert values["샘플애그"] == LINK


def test_the_send_item_files_column_comes_and_goes(tmp_path):
    """0057 — 파일명을 싣는 칸이 오르내린다.

    내려간 상태에서도 위험하지 않아야 한다: 칸이 없으면 파일이 실리지 않고,
    그러면 **문구만 나가고 사람이 손으로 첨부하는** 예전 동작으로 돌아간다.
    """
    db = tmp_path / "files.db"
    assert _alembic(db, "upgrade", "head").returncode == 0

    def columns():
        con = sqlite3.connect(db)
        try:
            return {r[1] for r in con.execute('PRAGMA table_info("send_items")')}
        finally:
            con.close()

    assert "files_json" in columns()

    down = _alembic(db, "downgrade", "0056_ir_file_name")
    assert down.returncode == 0, down.stdout + down.stderr
    assert "files_json" not in columns()

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert "files_json" in columns()


def test_running_the_rename_twice_changes_nothing(old_db, tmp_path):
    """운영에서는 배포할 때마다 `upgrade head` 를 돈다."""
    assert _alembic(old_db, "upgrade", "head").returncode == 0
    once = _rows(old_db)

    twice = _alembic(old_db, "upgrade", "head")
    assert twice.returncode == 0, twice.stdout + twice.stderr
    assert "Running upgrade" not in twice.stdout + twice.stderr
    assert _rows(old_db) == once


def test_a_fresh_db_never_needs_the_rename(tmp_path):
    """빈 DB 는 `0001` 이 이미 새 이름으로 만든다 — 거기서 또 바꾸면 부팅이 죽는다."""
    db = tmp_path / "fresh.db"
    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert "ir_file_name" in _columns(db)
    assert "ir_drive_url" not in _columns(db)

    shutil.copy(db, tmp_path / "copy.db")   # 아래 되돌리기가 원본을 건드리지 않게
    down = _alembic(tmp_path / "copy.db", "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
