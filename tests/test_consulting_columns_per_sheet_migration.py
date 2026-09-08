"""0066 — 투자컨설턴트 월 칸을 **사람마다**에서 **탭마다**로.

이 판이 하는 일은 스키마 한 칸을 떼는 것이 아니라 **자료를 합치는 것**이다.
운영에는 이미 사람이 적어 둔 기록이 `notes` 에 `{"칸 id": "내용"}` 으로 들어
있는데, 칸을 합치면서 없어지는 칸의 id 를 다시 적지 않으면 **그 기록이 화면
에서 통째로 사라진다** — 값은 JSON 에 그대로 있는데 그 열쇠에 해당하는 칸이
없어 아무 데도 안 붙는다. 0039 가 고쳐야 했던 유형이 정확히 그것이다.

그래서 여기서는 스키마가 아니라 **줄에 적힌 글자**를 본다.
`tests/test_migrations.py` 가 스키마와 올림/내림/다시 올림을 이미 지키므로,
이 파일은 겹치지 않게 자료만 본다.

기업명은 전부 지어낸 값이다 — 이 저장소는 공개다.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BEFORE = "0065_consulting_quote_contract_invoice"
AFTER = "0066_consulting_columns_per_sheet"


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    """따로 뜬 프로세스로 `alembic` 을 돌린다(`tests/test_migrations.py` 와 같다).

    `alembic/env.py` 는 import 시점에 굳은 `app.config.DATABASE_URL` 을 읽는데,
    테스트 프로세스에서 그것은 이미 conftest 의 테스트 DB 다.
    """
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db}",
           "DEALFLOW_DATA_DIR": str(db.parent)}
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


@pytest.fixture()
def old_db(tmp_path) -> Path:
    """0065 까지만 올린 DB — 아직 `consulting_columns.user_id` 가 있다."""
    db = tmp_path / "before.db"
    done = _alembic(db, "upgrade", BEFORE)
    assert done.returncode == 0, done.stdout + done.stderr
    with sqlite3.connect(db) as con:
        have = {r[1] for r in con.execute("PRAGMA table_info(consulting_columns)")}
    assert "user_id" in have, "0065 자리인데 담당 칸이 없다 — 검사가 헛돈다"
    return db


def _seed(db: Path, columns, companies) -> None:
    """`columns` = [(id, user_id, sheet, label, position)],
    `companies` = [(id, user_id, sheet, name, notes dict)]"""
    # `created_at`·`updated_at` 은 모델이 채우는 칸이라 raw SQL 로는 손수 넣는다.
    stamp = "2026-08-01 00:00:00"
    con = sqlite3.connect(db)
    try:
        for cid, uid, sheet, label, pos in columns:
            con.execute(
                "INSERT INTO consulting_columns "
                "(id, user_id, sheet, label, position, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (cid, uid, sheet, label, pos, stamp, stamp))
        for rid, uid, sheet, name, notes in companies:
            con.execute(
                "INSERT INTO consulting_companies "
                "(id, user_id, sheet, company_name, notes, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (rid, uid, sheet, name, json.dumps(notes, ensure_ascii=False),
                 stamp, stamp))
        con.commit()
    finally:
        con.close()


def _read(db: Path):
    con = sqlite3.connect(db)
    try:
        cols = con.execute("SELECT id, sheet, label FROM consulting_columns "
                           "ORDER BY position, id").fetchall()
        rows = {r[0]: json.loads(r[1] or "{}") for r in con.execute(
            "SELECT id, notes FROM consulting_companies")}
        return cols, rows
    finally:
        con.close()


SHEET = "스타트업"
OTHER = "경영본부 전달 기업"
AUG = "8월 마지막주 리마인드 톡 or TEL"


def test_같은_탭의_같은_이름_칸이_하나로_합쳐진다(old_db):
    """두 사람이 각자 올린 시트라 같은 달 칸이 두 벌 서 있다. `담당: 전체`
    에서 머리글이 겹쳐 서던 그것이다."""
    _seed(old_db,
          [(1, 1, SHEET, AUG, 0), (2, 7, SHEET, AUG, 0)],
          [(11, 1, SHEET, "샘플가", {"1": "통화함"}),
           (12, 7, SHEET, "샘플나", {"2": "부재중"})])
    done = _alembic(old_db, "upgrade", AFTER)
    assert done.returncode == 0, done.stdout + done.stderr

    cols, rows = _read(old_db)
    assert [(c[1], c[2]) for c in cols] == [(SHEET, AUG)], cols
    kept = cols[0][0]
    # **두 사람의 기록이 다 남는다.** 없어진 칸을 가리키던 열쇠를 다시 적지
    # 않으면 그 줄만 빈칸이 된다 — 값은 있는데 붙을 칸이 없다.
    assert rows[11] == {str(kept): "통화함"}
    assert rows[12] == {str(kept): "부재중"}


def test_이름이_다르면_합치지_않는다(old_db):
    """`8월 마지막주 리마인드 톡 or TEL` 과 `8월 리마인드` 는 같은 달이지만
    같은 칸이 아니다 — 시트가 그렇게 부르고 있고, 이 저장소는 적힌 것을
    고쳐 쓰지 않는다."""
    _seed(old_db,
          [(1, 1, SHEET, AUG, 0), (2, 7, SHEET, "8월 리마인드", 1)],
          [(11, 1, SHEET, "샘플가", {"1": "통화함", "2": "따로 적은 것"})])
    assert _alembic(old_db, "upgrade", AFTER).returncode == 0

    cols, rows = _read(old_db)
    assert sorted(c[2] for c in cols) == sorted([AUG, "8월 리마인드"])
    assert rows[11] == {"1": "통화함", "2": "따로 적은 것"}


def test_탭이_다르면_합치지_않는다(old_db):
    """칸은 탭마다 한 벌이다 — 옆 탭의 같은 달과 섞으면 없는 달의 빈 칸이 생긴다."""
    _seed(old_db,
          [(1, 1, SHEET, AUG, 0), (2, 1, OTHER, AUG, 0)],
          [(11, 1, SHEET, "샘플가", {"1": "통화함"}),
           (12, 1, OTHER, "샘플나", {"2": "전달함"})])
    assert _alembic(old_db, "upgrade", AFTER).returncode == 0

    cols, rows = _read(old_db)
    assert {(c[1], c[2]) for c in cols} == {(SHEET, AUG), (OTHER, AUG)}
    assert rows[11] == {"1": "통화함"} and rows[12] == {"2": "전달함"}


def test_두_칸에_다_적혀_있으면_둘_다_남긴다(old_db):
    """하나를 버리면 사람이 적어 둔 글이 조용히 사라진다 — 어느 쪽이 맞는지
    아무도 모른다. 사람이 보고 정리할 일이다."""
    _seed(old_db,
          [(1, 1, SHEET, AUG, 0), (2, 7, SHEET, AUG, 1)],
          [(11, 1, SHEET, "샘플가", {"1": "통화함", "2": "부재중"})])
    assert _alembic(old_db, "upgrade", AFTER).returncode == 0

    _cols, rows = _read(old_db)
    left = rows[11]["1"]
    assert "통화함" in left and "부재중" in left, left


def test_자동_생성_기록의_열쇠도_같이_옮긴다(old_db):
    """`monthly_column_runs.scope` 가 `"{user_id}:{탭}"` 이었다.

    그대로 두면 새 열쇠(`"{탭}"`)로는 그 달을 아무도 안 맡은 것이 되어,
    **사람이 지운 이번 달 칸이 다음 요청에 되살아난다.**
    """
    _seed(old_db, [(1, 1, SHEET, AUG, 0)], [])
    con = sqlite3.connect(old_db)
    try:
        for i, uid in enumerate((1, 7), start=1):
            con.execute(
                "INSERT INTO monthly_column_runs "
                "(id, target, scope, month, labels, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (i, "consulting", f"{uid}:{SHEET}", "2026-08", "[]",
                 "2026-08-01 00:00:00", "2026-08-01 00:00:00"))
        con.execute(
            "INSERT INTO monthly_column_runs "
            "(id, target, scope, month, labels, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (9, "contact", "샘플 명단", "2026-08", "[]",
             "2026-08-01 00:00:00", "2026-08-01 00:00:00"))
        con.commit()
    finally:
        con.close()

    assert _alembic(old_db, "upgrade", AFTER).returncode == 0

    con = sqlite3.connect(old_db)
    try:
        got = sorted(con.execute(
            "SELECT target, scope, month FROM monthly_column_runs").fetchall())
    finally:
        con.close()
    # 같은 (탭, 달) 이 둘이었다 — 하나만 남는다. 옆 표는 손대지 않는다.
    assert got == [("consulting", SHEET, "2026-08"),
                   ("contact", "샘플 명단", "2026-08")]


def test_내렸다_다시_올려도_기록이_그대로다(old_db):
    """되돌리기는 담당 칸을 **비운 채로** 세운다 — 누구 것이었는지는 합치면서
    사라졌고, 지어내면 남의 표에 없던 칸이 생긴다. 칸에 적힌 기록은 `notes` 에
    그대로 남아, 다시 올리면 같은 자리로 돌아온다."""
    _seed(old_db,
          [(1, 1, SHEET, AUG, 0), (2, 7, SHEET, AUG, 1)],
          [(11, 1, SHEET, "샘플가", {"1": "통화함"}),
           (12, 7, SHEET, "샘플나", {"2": "부재중"})])
    assert _alembic(old_db, "upgrade", AFTER).returncode == 0
    after_up, notes_up = _read(old_db)

    down = _alembic(old_db, "downgrade", BEFORE)
    assert down.returncode == 0, down.stdout + down.stderr
    with sqlite3.connect(old_db) as con:
        have = {r[1] for r in con.execute("PRAGMA table_info(consulting_columns)")}
    assert "user_id" in have
    assert _read(old_db)[1] == notes_up, "내리면서 기록이 바뀌었다"

    again = _alembic(old_db, "upgrade", AFTER)
    assert again.returncode == 0, again.stdout + again.stderr
    assert _read(old_db) == (after_up, notes_up), "다시 올렸더니 달라졌다"
