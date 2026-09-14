"""0075 이전이 **값을 건드리지 않았는지** 재고, 백필 결과를 사람이 읽게 편다.

0075 는 `contact_columns` · `consulting_columns` 의 이름에만 있던 `달`·`종류` 를
값으로 올린다. 칸 행도 줄마다의 값도 옮기지 않는 설계라, **안 움직였다는 것을
단정적으로** 잴 수 있다 — 그 단정을 여기서 건다.

    # ① 이전 전에 기준을 뜬다 (아직 칸이 없어도 돈다)
    python scripts/check_month_backfill.py --dry-run --save-baseline /tmp/before.json

    # ② 이전 뒤에 같은 자리를 다시 재고 기준과 맞춘다
    python scripts/check_month_backfill.py --baseline /tmp/before.json

**DB 에 한 글자도 쓰지 않는다.** 읽기 전용(`mode=ro`)으로 연다.

`--dry-run` 은 표에 적힌 `month`·`kind` 를 안 보고 **이름에서 다시 셈한다.**
이전을 하기 전에도 결과를 미리 볼 수 있어야 하기 때문이다(운영에서는 이것을
먼저 돌려 본다). 셈은 마이그레이션과 **같은 함수**를 부른다
(`app/services/monthly_columns.py`) — 두 벌이면 여기서 맞다고 한 것이 실제와
다를 수 있다.

## 다섯 가지를 낸다

  ① 두 표의 **행 수** — 이전 전 == 이전 후여야 한다
  ② `notes` **열쇠 집합 해시** — 반드시 같다. 다르면 이전이 값을 건드린 것이다
  ③ 달을 못 읽어 `NULL` 로 남은 칸 — 사람이 읽고 판단할 목록
  ④ `(표, 달, 종류)` 가 겹치는 칸 — 0건이 바람직하다
  ⑤ `(표, 종류)` 별 달 목록 — **연도가 튀는 줄**이 여기서 보인다

## 이름은 가리고 찍는다

명단·탭 이름에 사람 이름이 섞여 있다. 그렇다고 통째로 가리면 어느 표 이야기인지
알 수 없어 판단을 못 하므로, **앞 두 글자 + 이름마다 다른 꼬리표**로 줄인다
(`스타트업 · 홍길동` → `스타…#a1`). 서로 다른 표는 꼬리표가 달라 끝까지 갈리고,
같은 표는 어느 줄에서나 같은 글자로 나온다. 칸 이름(`9월 리마인드 문자`)은
가리지 않는다 — ③·⑤ 는 그 글자를 읽어야 판단이 된다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (칸 표, 값이 담긴 표, 열쇠 앞글자, MonthlyColumnRun.target)
#
# 열쇠 모양이 표마다 다르다 — 투자사 쪽은 `c12`, 투자컨설턴트 쪽은 `12` 다.
# 0075 는 이 열쇠를 **다시 적지 않는다**(그래서 ② 가 반드시 같아야 한다).
TABLES = (
    ("contact_columns", "vc_contacts", "c", "contact"),
    ("consulting_columns", "consulting_companies", "", "consulting"),
)


def mask(name: str) -> str:
    """`스타트업 · 홍길동` → `스타…#a1`. 위 모듈 설명의 그 규칙."""
    name = name or ""
    tail = hashlib.sha256(name.encode("utf-8")).hexdigest()[:2]
    return f"{name[:2]}…#{tail}" if len(name) > 2 else f"{name}#{tail}"


def open_ro(path: Path) -> sqlite3.Connection:
    """읽기 전용으로 연다 — 이 스크립트가 자료를 바꿀 길을 아예 막는다."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}


def notes_fingerprint(con: sqlite3.Connection, table: str) -> str:
    """줄마다 `sorted(notes.keys())` 를 이어 붙인 sha256.

    **값이 아니라 열쇠**를 센다. 0075 가 건드릴 수 있었던 것이 열쇠이기 때문이다
    (0039·0067 이 실제로 열쇠를 다시 적었고, 한 줄만 어긋나도 그 줄의 기록이
    화면에서 통째로 사라진다). 값까지 넣으면 사람이 그 사이에 한 글자만 고쳐도
    해시가 달라져, 이전 탓인지 사람 탓인지 갈리지 않는다.
    """
    digest = hashlib.sha256()
    for row_id, notes in con.execute(
            f"SELECT id, notes FROM {table} ORDER BY id"):
        try:
            values = json.loads(notes or "{}")
        except (TypeError, ValueError):
            values = None
        keys = sorted(values.keys()) if isinstance(values, dict) else []
        digest.update(f"{row_id}:{','.join(keys)}\n".encode("utf-8"))
    return digest.hexdigest()


def value_counts(con: sqlite3.Connection, table: str, prefix: str) -> dict:
    """칸마다 **적혀 있는 값이 몇 건**인가. 빈 값은 세지 않는다."""
    out: dict = defaultdict(int)
    for (notes,) in con.execute(
            f"SELECT notes FROM {table} WHERE notes IS NOT NULL AND notes != ''"):
        try:
            values = json.loads(notes)
        except (TypeError, ValueError):
            continue
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if value in (None, ""):
                continue
            if prefix and not str(key).startswith(prefix):
                continue
            rest = str(key)[len(prefix):]
            if rest.isdigit():
                out[int(rest)] += 1
    return out


def as_date(raw) -> date | None:
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def runs_index(con: sqlite3.Connection, target: str) -> dict:
    """`{표: {이름: [달, …]}}` — 앱이 그 칸을 세우며 적어 둔 기록."""
    out: dict = {}
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "monthly_column_runs" not in tables:
        return out
    for scope, month, labels in con.execute(
            "SELECT scope, month, labels FROM monthly_column_runs "
            "WHERE target = ? ORDER BY id", (target,)):
        try:
            names = json.loads(labels or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(names, list):
            continue
        per_sheet = out.setdefault(scope or "", {})
        for name in names:
            if isinstance(name, str):
                per_sheet.setdefault(name, []).append(month)
    return out


def read_columns(con: sqlite3.Connection, table: str, target: str,
                 computed: bool) -> list:
    """칸마다 `(id, 표, 이름, 달, 종류)`.

    `computed` 면 표에 적힌 값을 안 보고 **이름에서 다시 셈한다** — 마이그레이션이
    부르는 그 함수를 그대로 부르므로, 이전 전에 돌려도 이전 뒤와 같은 답이 나온다.
    """
    from app.services import monthly_columns as mc

    stored = has_column(con, table, "month") and has_column(con, table, "kind")
    runs = runs_index(con, target) if computed or not stored else {}
    picked = ("SELECT id, sheet, label, created_at, month, kind"
              if stored and not computed else
              "SELECT id, sheet, label, created_at")
    rows = []
    for row in con.execute(f"{picked} FROM {table} ORDER BY id"):
        col_id, sheet, label, created = row[0], row[1] or "", row[2] or "", row[3]
        if stored and not computed:
            month, kind = row[4], row[5]
        else:
            month = mc.month_key_of(label, as_date(created),
                                    runs.get(sheet, {}))
            kind = mc.kind_of(label) if month is not None else None
        rows.append((col_id, sheet, label, month, kind))
    return rows


def snapshot(con: sqlite3.Connection) -> dict:
    """① · ② 가 대조하는 값. 이전 전후로 한 번씩 뜬다."""
    out: dict = {"rows": {}, "notes": {}}
    for columns, values, _prefix, _target in TABLES:
        out["rows"][columns] = con.execute(
            f"SELECT COUNT(*) FROM {columns}").fetchone()[0]
        out["rows"][values] = con.execute(
            f"SELECT COUNT(*) FROM {values}").fetchone()[0]
        out["notes"][values] = notes_fingerprint(con, values)
    return out


def _verdict(ok: bool) -> str:
    return "합격" if ok else "**불합격**"


def report(path: Path, computed: bool, baseline: dict | None) -> int:
    con = open_ro(path)
    try:
        now = snapshot(con)
        failed = False

        print(f"자료      : {path}  (읽기 전용)")
        print("읽는 곳   : " + ("이름에서 셈한 값 (--dry-run)"
                                if computed else "표에 적힌 month·kind"))
        print("이름 가리기: 앞 두 글자 + 이름마다 다른 꼬리표(`스타…#a1`). "
              "칸 이름은 가리지 않는다.")
        print()

        print("① 행 수 — 이전 전 == 이전 후")
        for table, count in now["rows"].items():
            was = (baseline or {}).get("rows", {}).get(table)
            if was is None:
                print(f"   {table:22} {count:6}   (기준 없음)")
            else:
                same = was == count
                failed |= not same
                print(f"   {table:22} {count:6}   기준 {was:6}  {_verdict(same)}")
        print()

        print("② notes 열쇠 집합 해시 — **반드시 같다**")
        for table, digest in now["notes"].items():
            was = (baseline or {}).get("notes", {}).get(table)
            print(f"   {table:22} {digest}")
            if was is None:
                print(f"   {'':22} (기준 없음)")
            else:
                same = was == digest
                failed |= not same
                print(f"   {'':22} 기준 {was}  {_verdict(same)}")
                if not same:
                    print(f"   {'':22} → 이전이 `notes` 의 열쇠를 건드렸다. "
                          "0075 는 값을 옮기지 않는 설계이므로 이것은 고장이다.")
        print()

        columns = {}
        for table, values, prefix, target in TABLES:
            columns[table] = (read_columns(con, table, target, computed),
                              value_counts(con, values, prefix))

        print("③ 달을 못 읽어 `NULL` 로 남은 칸 — 사람이 읽고 판단한다")
        nulls = 0
        for table, (rows, counts) in columns.items():
            for col_id, sheet, label, month, _kind in rows:
                if month:
                    continue
                nulls += 1
                print(f"   {table:20} {mask(sheet):12} id={col_id:<4} "
                      f"값 {counts.get(col_id, 0):3}건  {label}")
        print(f"   합계 {nulls}칸")
        print()

        print("④ `(표, 달, 종류)` 가 둘 이상인 칸 — 0건이 바람직")
        dup_total = 0
        for table, (rows, counts) in columns.items():
            groups: dict = defaultdict(list)
            for col_id, sheet, label, month, kind in rows:
                if month:
                    groups[(sheet, month, kind)].append((col_id, label))
            for (sheet, month, kind), members in sorted(
                    groups.items(), key=lambda kv: str(kv[0])):
                if len(members) < 2:
                    continue
                dup_total += 1
                print(f"   {table:20} {mask(sheet):12} {month} {kind!r}")
                for col_id, label in members:
                    print(f"      id={col_id:<4} 값 {counts.get(col_id, 0):3}건  {label}")
        print(f"   합계 {dup_total}건")
        print()

        print("⑤ `(표, 종류)` 별 달 목록 — 연도가 튀는 줄을 찾는다")
        for table, (rows, _counts) in columns.items():
            groups: dict = defaultdict(list)
            for _col_id, sheet, _label, month, kind in rows:
                if month:
                    groups[(sheet, kind)].append(month)
            for (sheet, kind), months in sorted(
                    groups.items(), key=lambda kv: str(kv[0])):
                years = sorted({m[:4] for m in months})
                flag = "  ← 해가 둘 이상이다" if len(years) > 1 else ""
                print(f"   {table:20} {mask(sheet):12} {kind!r}")
                print(f"      {', '.join(sorted(months))}{flag}")
        print()

        if baseline is None:
            print("판정: 기준이 없어 ①·② 는 재지 못했다 "
                  "(--save-baseline 으로 이전 전에 떠 두고, 이전 뒤 --baseline 으로 준다)")
            return 0
        print(f"판정: {_verdict(not failed)}")
        return 1 if failed else 0
    finally:
        con.close()


def default_db() -> Path:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return Path(__file__).resolve().parent.parent / "data" / "dealflow.db"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="0075 백필 확인 (DB 에 쓰지 않는다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true",
                    help="표에 적힌 값을 안 보고 이름에서 다시 셈한다 "
                         "(이전 전에도 돈다)")
    ap.add_argument("--baseline", default="",
                    help="이전 전에 떠 둔 기준 파일 — ①·② 를 이것과 맞춘다")
    ap.add_argument("--save-baseline", default="",
                    help="지금 값을 기준 파일로 떠 둔다")
    args = ap.parse_args()

    path = Path(args.db) if args.db else default_db()
    if not path.exists():
        print(f"그런 파일이 없다: {path}", file=sys.stderr)
        return 2

    if args.save_baseline:
        con = open_ro(path)
        try:
            Path(args.save_baseline).write_text(
                json.dumps(snapshot(con), ensure_ascii=False, indent=2),
                encoding="utf-8")
        finally:
            con.close()
        print(f"기준을 떠 두었다: {args.save_baseline}")

    baseline = None
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    return report(path, args.dry_run, baseline)


if __name__ == "__main__":
    raise SystemExit(main())
