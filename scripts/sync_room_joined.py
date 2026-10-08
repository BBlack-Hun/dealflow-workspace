"""이미 쌓인 줄의 `확인됨` ↔ `카톡방 참여여부` 를 **한 번** 맞춘다.

앞으로는 방 확인이 `확인됨` 으로 끝날 때 참여여부가 함께 `O` 가 된다
(`app/services/room_joined` 의 규칙 1). 그 규칙이 생기기 전에 확인된 줄은
`확인됨` 인데 참여여부가 비어 있다 — 이 스크립트가 그 줄을 채운다.

    # ① 무엇이 몇 줄인지 본다 (**기본이 미리보기다** — DB 를 읽기 전용으로 연다)
    python scripts/sync_room_joined.py

    # ② 되돌릴 파일을 떠 두고 실제로 채운다
    python scripts/sync_room_joined.py --apply --save-baseline /tmp/room_joined.json

    # ③ 되돌린다 (채운 `O` 를 다시 비운다 — 그 사이 사람이 고친 줄은 안 건드린다)
    python scripts/sync_room_joined.py --restore /tmp/room_joined.json --apply

## 채우는 것과 세기만 하는 것

판정은 **여기 적지 않는다.** 살아 있는 길과 같은 함수를 부른다
(`room_joined.joined_after_verified` · `sheet_import.joined_state`). 규칙을 두
군데 적으면 스크립트가 채운 줄과 앞으로 채워질 줄이 다른 규칙을 탄다.

    채움       `확인됨` + 참여여부 빈칸 → `O`. **이것만 쓴다.**
    어긋남     `확인됨` + `X`. 세기만 한다 — 방을 나가신 분일 수도, `X` 가
               틀린 것일 수도 있다. 어느 쪽인지는 사람이 보고 정한다.
    나간 단계  `확인됨` + 빈칸인데 연결 단계가 `방 나감`·`참여 안 함`. 세기만
               한다(같은 이유다 — 살아 있는 길도 이런 줄에는 `O` 를 안 적는다).
    그대로     `확인됨` + 이미 참여 표시(`O`·`○`·`●`·`○, DAY` …).
    다른 말    `확인됨` + 사람이 적은 다른 말. 앱이 뜻을 정하지 않는다.

`확인됨` 이 아닌 줄은 건드리지 않는다. 참여여부가 `O` 인데 방 확인이 안 된 줄은
규칙 3 그대로다 — 방이 있다는 것은 PC 발송기만 확인할 수 있다.

## 찍는 것

**수만 찍는다.** 이 표에는 실명이 있다. 어느 줄인지 봐야 하면 `--ids` 로 줄
번호만 찍는다(번호로 화면에서 찾는다).

`--apply` 없이는 DB 를 읽기 전용(`mode=ro`)으로 연다 — 미리보기가 쓸 길 자체를
막는다(`scripts/clean_group_name.py` 와 같은 뼈대다).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TABLE = "vc_contacts"

FILL = "fill"
CONFLICT = "conflict"
STAGE_OUT = "stage_out"
OK = "ok"
OTHER = "other"

LABELS = {
    FILL: "채움 (빈칸 → O)",
    CONFLICT: "어긋남 (확인됨 + X) — 안 바꿈",
    STAGE_OUT: "나간 단계 + 빈칸 (방 나감·참여 안 함) — 안 바꿈",
    OK: "그대로 (이미 참여 표시)",
    OTHER: "다른 말 — 안 바꿈",
}
ORDER = (FILL, CONFLICT, STAGE_OUT, OK, OTHER)


def open_db(path: Path, write: bool) -> sqlite3.Connection:
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다."""
    if write:
        return sqlite3.connect(str(path))
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def classify(joined, stage) -> str:
    """`확인됨` 인 줄 하나가 어느 갈래인가. 판정은 살아 있는 길의 함수다."""
    from app.services import room_joined, sheet_import

    state = sheet_import.joined_state(joined)
    if state == sheet_import.JOINED_NO:
        return CONFLICT          # 단계가 무엇이든 — 단계는 요약에 따로 찍는다
    if state == sheet_import.JOINED_YES:
        return OK
    if state == sheet_import.JOINED_OTHER:
        return OTHER
    # 빈칸 — 살아 있는 길이 이 줄에 무엇을 적었을지 **그 함수에게 묻는다.**
    # `None` 이면 연결 단계가 `방 나감`·`참여 안 함` 인 줄이다.
    if room_joined.joined_after_verified(joined, stage):
        return FILL
    return STAGE_OUT


def plan(con: sqlite3.Connection) -> list:
    """`확인됨` 인 줄마다 `(id, 갈래, 연결 단계, 감춤, 참여여부)`. 읽기만 한다."""
    from app.services import room_joined

    out = []
    for row_id, joined, stage, hidden in con.execute(
            f"SELECT id, kakao_joined, connect_stage, COALESCE(is_hidden, 0) "
            f"FROM {TABLE} WHERE room_verified = ? ORDER BY id",
            (room_joined.VERIFIED,)):
        out.append((row_id, classify(joined, stage), stage or "", int(hidden or 0),
                    joined))
    return out


def summarize(rows: list) -> Counter:
    counts: Counter = Counter()
    for _row_id, kind, stage, hidden, _joined in rows:
        counts[kind] += 1
        counts[(kind, "hidden" if hidden else "shown")] += 1
        counts[(kind, stage)] += 1
    return counts


def print_summary(rows: list, show_ids: bool) -> None:
    counts = summarize(rows)
    print(f"`확인됨` 인 줄 {len(rows)}줄")
    for kind in ORDER:
        if not counts[kind]:
            continue
        stages = sorted({stage for _i, k, stage, _h, _j in rows if k == kind})
        by_stage = " · ".join(f"{s or '(없음)'} {counts[(kind, s)]}" for s in stages)
        print(f"   {LABELS[kind]:<40} {counts[kind]:>4}줄  "
              f"(보이는 줄 {counts[(kind, 'shown')]} · 감춘 줄 {counts[(kind, 'hidden')]}"
              f" | 단계: {by_stage})")
        if show_ids and kind != OK:
            ids = [str(i) for i, k, _s, _h, _j in rows if k == kind]
            print(f"      id: {', '.join(ids)}")
    print()


def apply_plan(con: sqlite3.Connection, rows: list) -> int:
    """`채움` 줄만 적는다. **빈칸인 줄에만** — 그 사이 누가 적었으면 안 덮는다."""
    from app.services import room_joined

    changed = 0
    for row_id, kind, _stage, _hidden, _joined in rows:
        if kind != FILL:
            continue
        cur = con.execute(
            f"UPDATE {TABLE} SET kakao_joined = ? WHERE id = ? "
            "AND room_verified = ? AND TRIM(COALESCE(kakao_joined, '')) = ''",
            (room_joined.JOINED_MARK, row_id, room_joined.VERIFIED))
        changed += cur.rowcount
    con.commit()
    return changed


def save_baseline(path: Path, rows: list) -> int:
    """되돌리기 파일. 채우는 줄의 번호와 **채우기 전 값**만 적는다(이름은 없다)."""
    data = [{"id": row_id, "before": joined}
            for row_id, kind, _s, _h, joined in rows if kind == FILL]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(data)


def restore(con: sqlite3.Connection, path: Path) -> int:
    """채운 `O` 를 원래 값으로 되돌린다 — **아직 `O` 인 줄만.**

    그 사이 사람이 다른 값으로 고친 줄을 옛 빈칸으로 되돌리면, 되돌리기가
    사람이 한 일을 지운다.
    """
    from app.services import room_joined

    data = json.loads(path.read_text(encoding="utf-8"))
    done = 0
    for item in data:
        cur = con.execute(
            f"UPDATE {TABLE} SET kakao_joined = ? WHERE id = ? AND kakao_joined = ?",
            (item["before"], item["id"], room_joined.JOINED_MARK))
        done += cur.rowcount
    con.commit()
    return done


def default_db() -> Path:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return Path(__file__).resolve().parent.parent / "data" / "dealflow.db"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="`확인됨` 인데 참여여부가 빈 줄을 `O` 로 채운다 "
                    "(기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 적는다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--save-baseline", default="",
                    help="채우기 전 `(id, 값)` 을 이 파일로 떠 둔다")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일로 **원상 복구**한다 (`--apply` 와 함께)")
    ap.add_argument("--ids", action="store_true",
                    help="갈래마다 줄 번호를 찍는다 (이름은 안 찍는다)")
    args = ap.parse_args(argv)

    path = Path(args.db) if args.db else default_db()
    if not path.exists():
        print(f"그런 파일이 없다: {path}", file=sys.stderr)
        return 2
    if args.apply and args.dry_run:
        print("`--apply` 와 `--dry-run` 을 함께 줄 수 없다.", file=sys.stderr)
        return 2

    if args.restore:
        if not args.apply:
            print("되돌리기도 DB 에 쓰는 일이다. `--apply` 를 함께 줘라.",
                  file=sys.stderr)
            return 2
        con = open_db(path, write=True)
        try:
            count = restore(con, Path(args.restore))
        finally:
            con.close()
        print(f"되돌렸다: {count}줄 ← {args.restore}")
        return 0

    if args.apply and not args.save_baseline:
        print("`--apply` 에는 `--save-baseline` 이 있어야 한다 "
              "(되돌릴 파일 없이 바꾸지 않는다).", file=sys.stderr)
        return 2

    con = open_db(path, write=args.apply)
    try:
        rows = plan(con)
        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: `확인됨` 인데 참여여부가 빈 줄을 `O` 로 채운다 "
              "(판정은 `app/services/room_joined`)")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()
        print_summary(rows, args.ids)

        if args.save_baseline:
            saved = save_baseline(Path(args.save_baseline), rows)
            print(f"되돌리기 파일을 떠 두었다: {args.save_baseline} ({saved}줄)")
            print()
        if args.apply:
            changed = apply_plan(con, rows)
            print(f"DB 에 적었다: {changed}줄")
            print(f"   되돌리려면: python scripts/{Path(__file__).name} "
                  f"--restore {args.save_baseline} --apply")
            print()
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
