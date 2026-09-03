"""빈 DB 로 시작해도 `alembic upgrade head` 가 끝까지 가는가.

## 왜 이 검사가 있나

`0001_initial` 은 `Base.metadata.create_all()` 로 **지금 모델 전체**를 만든다
(모델과 마이그레이션이 갈라지지 않게 하려는 것 — 0001 의 설명 참고). 그래서
새 DB 는 처음부터 최신 칸을 다 갖고 시작하고, 뒤따르는 판들이 그 칸을 또
붙이려 들면 `duplicate column name` 으로 **부팅 자체가 죽는다.**

이미 올라와 있는 운영 DB 는 아무렇지도 않아서, 이 고장은 오직 **처음 세울 때**
드러난다 — 재해 복구·새 서버 이전·백업에서 복원, 그리고 개발자가 빈 볼륨으로
로컬을 띄울 때. 하필 제일 급한 날에만 보이는 고장이라, 사람이 알아채기를
기다리지 않고 여기서 잡는다. 실제로 0017 부터 이 규칙이 잊혔고 34개 판이
쌓이는 동안 아무도 몰랐다.

## 무엇을 지키나

1. 빈 DB → `head` 가 끝까지 간다
2. 그렇게 만든 스키마가 **모델과 표·칸 단위로 같다** (한쪽만 고치면 새 서버와
   지금 서버가 다른 앱이 된다)
3. 마이그레이션이 만드는 **인덱스가 빠지지 않는다** — 표를 만드는 `if` 안에
   인덱스를 같이 넣어 두면 빈 DB 길에서 통째로 건너뛴다. 실제로 그렇게 12개가
   빠져 있었고, 표·칸만 봐서는 보이지 않았다
4. 이미 `head` 인 DB 에서 한 번 더 돌려도 **아무 일도 안 일어난다**
5. `downgrade` 로 내려갔다가 다시 올라온다 (`downgrade` 가 아예 없는 판이 하나
   섞여 있으면 그 판을 지나는 되돌리기 전체가 계획 단계에서 멎는다 — 0012 가
   그랬다)

느리지 않다(전체 1~2초). 도커도 필요 없다 — CI 가 그대로 돌린다.
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _alembic(db: Path, *args: str) -> subprocess.CompletedProcess:
    """저장소 뿌리에서 `alembic <args>` 를 돌린다.

    **따로 뜬 프로세스로 돌린다.** `alembic/env.py` 는 import 시점에 굳은
    `app.config.DATABASE_URL` 을 읽는데, 테스트 프로세스에서는 그것이 이미
    conftest 의 테스트 DB 다. 컨테이너가 실제로 하는 것과 같은 방식이기도 하다
    (`scripts/entrypoint.sh`).
    """
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db}",
           "DEALFLOW_DATA_DIR": str(db.parent)}
    return subprocess.run([sys.executable, "-m", "alembic", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def _schema(db: Path) -> tuple[dict, set]:
    """(표·칸, 인덱스) — 표·칸 단위로 대조하려고 읽어 둔다."""
    con = sqlite3.connect(db)
    try:
        cur = con.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        columns = {t: {c[1] for c in cur.execute(f'PRAGMA table_info("{t}")')}
                   for t in tables}
        indexes = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%'").fetchall()}
        return columns, indexes
    finally:
        con.close()


@pytest.fixture(scope="module")
def fresh_db(tmp_path_factory) -> Path:
    """빈 파일에서 `head` 까지 올린 DB. 이 파일의 검사들이 나눠 쓴다."""
    db = tmp_path_factory.mktemp("migrations") / "fresh.db"
    done = _alembic(db, "upgrade", "head")
    assert done.returncode == 0, (
        "빈 DB 에서 head 까지 못 갔다 — 이 상태면 빈 볼륨으로 띄운 컨테이너가 "
        "부팅에서 죽는다.\n"
        "새 판을 더할 때는 `ADD COLUMN`·`CREATE TABLE`·`CREATE INDEX` 앞에 "
        "이미 있는지 보는 `if` 를 두어야 한다(0002·0005·0018 참고).\n\n"
        + done.stdout + done.stderr)
    return db


def test_an_empty_db_climbs_all_the_way_to_head(fresh_db):
    """1. 끝까지 올라갔고, 그 자리가 정말 head 인가."""
    where = _alembic(fresh_db, "current")
    assert "(head)" in where.stdout + where.stderr, where.stdout + where.stderr


def test_the_fresh_schema_matches_the_models(fresh_db):
    """2. 빈 DB 로 만든 스키마 == 모델. 표도 칸도 남거나 모자라면 안 된다.

    한쪽만 고치는 날 여기서 걸린다 — 마이그레이션에는 칸을 붙였는데 모델에는
    안 붙였다면(또는 그 반대라면), 새로 세운 서버와 지금 서버가 서로 다른 표를
    갖게 된다.
    """
    import app.models  # noqa: F401  (Base.metadata 에 모델 등록)
    from app.db import Base

    want = {t.name: {c.name for c in t.columns} for t in Base.metadata.tables.values()}
    got, _ = _schema(fresh_db)
    # 알렘빅이 제 판 번호를 적어 두는 표. 모델에 있을 것이 아니다.
    got.pop("alembic_version", None)

    assert set(got) == set(want), (
        f"모델에만 있는 표: {sorted(set(want) - set(got))} · "
        f"DB 에만 있는 표: {sorted(set(got) - set(want))}")
    for table in sorted(want):
        assert got[table] == want[table], (
            f"{table}: 모델에만 있는 칸 {sorted(want[table] - got[table])} · "
            f"DB 에만 있는 칸 {sorted(got[table] - want[table])}")


def test_no_index_is_lost_on_the_empty_db_path(fresh_db):
    """3. 마이그레이션이 이름 붙여 만드는 인덱스가 빈 DB 에도 다 있는가.

    표·칸만 대조하면 이 고장이 안 보인다. 인덱스를 `if <표가 없으면>` 안에
    같이 넣어 두면, 0001 이 표를 이미 만들어 둔 빈 DB 길에서는 인덱스까지
    통째로 건너뛴다 — 새 서버만 인덱스 없이 돌게 된다(느려질 뿐 안 죽어서
    더 늦게 발견된다). 실제로 12개가 그렇게 빠져 있었다.

    이름으로 찾는다. 이 저장소의 인덱스는 전부 `ix_`/`uq_` 로 시작한다.
    `op.create_index(INDEX, ...)` 처럼 이름을 상수에 담아 부르는 판이 있어서,
    호출을 따라가지 않고 **파일에 적힌 이름**을 그대로 줍는다.
    """
    named = re.compile(r'"((?:ix|uq)_[a-z0-9_]+)"')
    # `UniqueConstraint(..., name="uq_…")` 로만 쓰인 이름은 뺀다. SQLite 는
    # 표 안의 UNIQUE 제약을 `sqlite_autoindex_…` 로 만들어서, 그 이름은
    # 어느 길로 만들든 DB 에 남지 않는다(찾으면 늘 없다고 나온다).
    constraint = re.compile(r'name="((?:ix|uq)_[a-z0-9_]+)"')
    wanted: set[str] = set()
    only_constraint: set[str] = set()
    for path in sorted((ROOT / "alembic" / "versions").glob("0*.py")):
        text = path.read_text(encoding="utf-8")
        wanted |= set(named.findall(text))
        only_constraint |= set(constraint.findall(text))
    wanted -= only_constraint
    assert wanted, "마이그레이션에서 인덱스 이름을 하나도 못 찾았다 — 검사가 헛돈다"

    _, have = _schema(fresh_db)
    missing = sorted(wanted - have)
    assert not missing, (
        f"마이그레이션이 만드는데 빈 DB 에는 없는 인덱스: {missing}\n"
        "표를 만드는 `if` 밖으로 꺼내 인덱스만 따로 보게 하라(0005 참고).")


def test_running_it_again_does_nothing(fresh_db, tmp_path):
    """4. 이미 head 인 DB 에서 한 번 더 — 운영에서 배포할 때마다 하는 일이다."""
    before = _schema(fresh_db)
    again = _alembic(fresh_db, "upgrade", "head")
    assert again.returncode == 0, again.stdout + again.stderr
    # 한 판도 돌지 않아야 한다.
    assert "Running upgrade" not in again.stdout + again.stderr
    assert _schema(fresh_db) == before


def test_it_comes_back_down_and_up_again(tmp_path):
    """5. 내려갔다 올라온다.

    `downgrade` 가 없는 판이 하나만 섞여 있어도 알렘빅은 되돌릴 길을 **짜지도
    못한다**(`AttributeError`) — 0012 가 그랬고, 그래서 0013 이후를 한 칸
    내리는 것조차 되지 않았다.
    """
    db = tmp_path / "roundtrip.db"
    assert _alembic(db, "upgrade", "head").returncode == 0
    top = _schema(db)

    down = _alembic(db, "downgrade", "base")
    assert down.returncode == 0, down.stdout + down.stderr

    up = _alembic(db, "upgrade", "head")
    assert up.returncode == 0, up.stdout + up.stderr
    assert _schema(db) == top, "내렸다 올렸더니 스키마가 달라졌다"
