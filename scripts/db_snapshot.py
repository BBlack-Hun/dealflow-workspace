"""SQLite 를 **옮길 수 있는 한 덩어리**로 뽑는다.

`dealflow.db` 파일만 복사하면 안 된다. WAL 모드라 최근에 쓴 것이 아직 본체가
아니라 `dealflow.db-wal` 에 있고, 그 파일이 본체보다 클 때도 있다. 파일 하나만
들고 가면 그만큼이 통째로 사라진다. 세 파일(`-wal`, `-shm` 포함)을 같이
복사하는 것도 답이 아니다 — 복사하는 동안에도 쓰기가 일어나면 셋의 시점이
어긋나 열리지 않는 파일이 된다.

`sqlite3` 의 백업 API 는 **돌아가는 중에도** 일관된 한 덩어리를 만들어 준다.
멈출 필요가 없다.

    # 뽑기 (서버 안에서)
    python scripts/db_snapshot.py /app/data/dealflow.db /app/data/snapshot.db

    # 옮긴 뒤 확인 (받은 쪽에서)
    python scripts/db_snapshot.py --verify snapshot.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# 옮기고 나서 "다 왔는지" 세어 볼 표. 사람이 눈으로 비교한다.
COUNTED = [
    "users", "vc_contacts", "ir_companies", "sourcing_contacts",
    "message_templates", "send_jobs", "send_items", "contact_activities",
    "ir_requests", "meetings", "consulting_companies", "ref_sheets",
]


def counts(conn: sqlite3.Connection) -> dict:
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    out = {}
    for table in COUNTED:
        if table in have:
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return out


def report(conn: sqlite3.Connection) -> int:
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"  무결성: {integrity}")
    rows = counts(conn)
    for table, n in rows.items():
        print(f"    {table:22} {n:6}")
    print(f"  합계 {sum(rows.values())}행 / {len(rows)}개 표")
    try:
        version = conn.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        print(f"  스키마 버전: {version}")
    except sqlite3.Error:
        print("  스키마 버전: (없음 — alembic 이 아직 안 돈 DB)")
    return 0 if integrity == "ok" else 1


def verify(path: Path) -> int:
    if not path.exists():
        print(f"파일이 없습니다: {path}")
        return 1
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        print(f"■ {path} ({path.stat().st_size:,} bytes)")
        return report(conn)
    finally:
        conn.close()


def snapshot(src: Path, dst: Path) -> int:
    if not src.exists():
        print(f"원본이 없습니다: {src}")
        return 1
    if dst.exists():
        print(f"받을 자리에 이미 파일이 있습니다: {dst}")
        return 1

    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(dst)
    try:
        # 돌아가는 중에도 일관된 한 덩어리를 만든다(WAL 이 접혀 들어간다).
        source.backup(target)
    finally:
        target.close()
        source.close()

    print(f"■ 원본 {src}")
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    before = counts(src_conn)
    src_conn.close()
    for table, n in before.items():
        print(f"    {table:22} {n:6}")

    print(f"\n■ 스냅샷 {dst} ({dst.stat().st_size:,} bytes)")
    conn = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
    try:
        code = report(conn)
        after = counts(conn)
    finally:
        conn.close()

    # 뽑는 사이에 쓰기가 있었으면 숫자가 다를 수 있다. 조용히 넘기지 않는다.
    moved = {t: (before[t], after.get(t)) for t in before
             if before[t] != after.get(t)}
    if moved:
        print("\n⚠ 뽑는 동안 값이 바뀐 표가 있습니다(사용 중이면 정상):")
        for table, (b, a) in moved.items():
            print(f"    {table}: {b} → {a}")
    print(f"\n다음: 이 파일을 옮긴 뒤 `--verify` 로 같은 숫자인지 확인하세요.")
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="SQLite 스냅샷 뽑기 / 확인")
    ap.add_argument("src", help="원본 .db (또는 --verify 일 때 확인할 파일)")
    ap.add_argument("dst", nargs="?", help="만들 스냅샷 경로")
    ap.add_argument("--verify", action="store_true", help="세어 보기만 한다")
    args = ap.parse_args()

    if args.verify:
        return verify(Path(args.src))
    if not args.dst:
        ap.error("스냅샷을 만들려면 받을 경로가 필요합니다 (또는 --verify)")
    return snapshot(Path(args.src), Path(args.dst))


if __name__ == "__main__":
    sys.exit(main())
