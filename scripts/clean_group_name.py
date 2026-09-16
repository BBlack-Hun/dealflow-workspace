"""그룹 칸(`vc_contacts.group_name`)에 쌓인 문장을 **제자리로 돌려놓는다.**

이 칸의 화면 이름은 오랫동안 `그룹/투자분야/라운드사이즈` 였다. 이름이 시키는
대로 사람들이 투자 단계·규모·분야를 한 칸에 문장으로 적어 왔고, 그 말들은 이미
제 칸이 있다(`round_size` · `sectors`). 사용자가 정했다 — **그룹 칸은 정해 둔
갈래만 담는다. 문장은 안 담는다.** 갈래는 한 글자 여섯(`A`~`F`)과 **뜻이 있는
이름들**(`특정분야` · `Pre IPO` · `Series B 이상` …)이다. 화면 칸은 그 갈래에서
고르는 칸이라, 갈래로 안 읽히는 값은 필터에서 따로 떨어져 나온다(저장은 되는데
같은 갈래로는 안 걸리는 값이 된다).

**사용자가 일부러 넣은 이름은 건드리지 않는다.** 무엇이 갈래인지는 이 파일이
아니라 `app/services/group_name.KNOWN` 이 정한다 — 이름이 하나 늘면 거기에만
적는다. 여기서 또 가리면 그날로 둘이 갈리고, 그때 이 스크립트가 사용자가
적어 둔 이름을 메모로 쓸어 간다.

    # ① 무엇이 어떻게 바뀌는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/clean_group_name.py

    # ② 되돌릴 파일을 떠 두고 실제로 바꾼다
    python scripts/clean_group_name.py --apply --save-baseline /tmp/group.json

    # ③ 바뀐 것이 계획대로인지 맞춘다
    python scripts/clean_group_name.py --baseline /tmp/group.json

    # ④ 되돌린다
    python scripts/clean_group_name.py --restore /tmp/group.json --apply

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/check_month_backfill.py` 가 같은 방식이고, 이 스크립트도 그 뼈대를
따른다(`--dry-run` · `--baseline` · `--save-baseline`).

## 네 갈래로 가른다

판정은 **여기 적지 않는다.** `app/services/group_name.decide()` 하나를 부른다 —
시트를 읽어 넣는 쪽(`services/sheet_import`)이 부르는 바로 그 함수다. 규칙이 두
군데 적히면 한쪽이 낡고, 그러면 여기서 정리해 둔 것을 다음 업로드가 되돌린다.

    그대로   이미 정해 둔 갈래다(`A` · `특정분야` …). 손대지 않는다.
    고침     표기만 다르다. `b그룹` · `a` → `B` · `A`, `series b이상` →
             `Series B 이상`.
    지움     `round_size` 나 `sectors` 에 **이미 있는 말**이다. 그냥 비운다 —
             메모로 옮기면 같은 말이 세 군데가 된다.
    옮김     여기에만 있는 말이다. `memo` 뒤에 `[그룹 칸에서 옮김]` 표시와 함께
             붙이고 그룹 칸을 비운다.

## 이름을 찍지 않는다

이 칸에는 투자사·사람 이야기가 섞여 있다. 그래서 미리보기는 **id 와 값의
모양**(길이 · 어느 갈래인지)만 찍는다. 값 자체를 봐야 할 때만 `--show-values` 를
따로 준다(기본은 끔). 옮길 글이 맞는지 눈으로 확인하는 자리가 필요해서 남겨
두지만, 그대로 로그에 남기면 공개할 수 없는 글이 된다.

## 되돌리기

바꾸기 전의 `(id, group_name, memo)` 를 통째로 파일에 떠 둔다. `--restore` 는 그
파일의 `before` 를 그대로 다시 적는다 — 이 스크립트가 무엇을 했든 그 자리로
돌아간다. 파일에는 바뀐 **뒤**의 값(`after`)도 함께 적어서, `--baseline` 이
"계획대로 바뀌었는가" 를 맞출 수 있게 한다.

**떠 둔 파일에는 값이 그대로 들어 있다**(되돌리려면 그래야 한다). 공개 저장소에
넣지 말고 저장소 밖(`/tmp`)에 두어라.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TABLE = "vc_contacts"

# 갈래마다 화면에 적는 말. `decide()` 가 돌려주는 값을 그대로 열쇠로 쓴다 —
# 여기에 갈래를 새로 적어 두면 판정이 늘 때 한쪽만 늘어난다.
LABELS = {
    "keep": "그대로",
    "fix": "고침",
    "drop": "지움",
    "move": "옮김",
}

# `지움` 안에서 **어느 칸과 겹쳤는가.** 사용자가 실측으로 셋을 갈라 세었고
# (round_size 49 · sectors 15 · 둘 다 30), 같은 결로 나오는지 보아야 한다.
WHERE_ROUND = "라운드 사이즈와 겹침"
WHERE_SECTORS = "선호 투자분야와 겹침"
WHERE_BOTH = "둘 다 겹침"


def open_db(path: Path, write: bool) -> sqlite3.Connection:
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다."""
    if write:
        return sqlite3.connect(str(path))
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def shape(value) -> str:
    """값의 **모양**. 실명이 찍히면 안 되니 길이만 적는다."""
    return f"{len(value or '')}자"


def pad(text: str, width: int, right: bool = False) -> str:
    """표의 칸을 **눈에 보이는 너비**로 맞춘다.

    `f"{text:12}"` 는 글자 수로 센다. 이 표의 말은 거의 한글이라 한 글자가 두
    칸을 먹고, 그러면 줄마다 칸이 어긋나 표를 읽을 수가 없다 — 실제로 그랬다.
    """
    room = max(0, width - sum(
        2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text))
    return (" " * room + text) if right else (text + " " * room)


def read_rows(con: sqlite3.Connection) -> list:
    """그룹 칸에 값이 있는 줄 전부 — `(id, group, round, sectors, memo)`."""
    return list(con.execute(
        f"SELECT id, group_name, round_size, sectors, memo FROM {TABLE} "
        "WHERE group_name IS NOT NULL AND TRIM(group_name) != '' "
        "ORDER BY id"))


def plan(con: sqlite3.Connection) -> list:
    """줄마다 `(id, 판정, 겹친 칸, 전, 후)`. **DB 를 읽기만 한다.**

    `전`·`후` 는 되돌리기 파일에 그대로 들어간다 — 미리보기와 저장이 **같은
    계획 하나**를 지나야 미리 본 것이 실제와 같다(`import_investor_list.py` 의
    `fill_plan` 이 같은 이유로 정하는 일과 얹는 일을 나누었다).
    """
    from app.services import group_name as gn

    out = []
    for row_id, group, round_size, sectors, memo in read_rows(con):
        decision = gn.decide(group, round_size=round_size, sectors=sectors,
                             memo=memo)
        where = ""
        if decision.action == gn.DROP:
            hit_round = gn.overlaps(group, round_size)
            hit_sectors = gn.overlaps(group, sectors)
            where = (WHERE_BOTH if hit_round and hit_sectors
                     else WHERE_ROUND if hit_round else WHERE_SECTORS)
        before = {"group_name": group, "memo": memo}
        after = {"group_name": decision.group,
                 "memo": memo if decision.memo is None else decision.memo}
        out.append((row_id, decision.action, where, before, after))
    return out


def summarize(rows: list) -> Counter:
    """갈래별 줄 수. 사용자가 손으로 센 표와 **같은 결**로 나와야 한다."""
    counts: Counter = Counter()
    for _row_id, action, where, _before, _after in rows:
        counts[action] += 1
        if where:
            counts[where] += 1
    return counts


def print_summary(rows: list) -> None:
    counts = summarize(rows)
    lines = [
        ("그대로 (정해 둔 갈래)", counts["keep"]),
        ("고침   (표기만 다름)", counts["fix"]),
        (f"지움   ({WHERE_ROUND})", counts[WHERE_ROUND]),
        (f"지움   ({WHERE_SECTORS})", counts[WHERE_SECTORS]),
        (f"지움   ({WHERE_BOTH})", counts[WHERE_BOTH]),
        ("옮김   (아무 데도 안 겹침)", counts["move"]),
        ("─ 합계 (그룹 칸에 값이 있는 줄)", len(rows)),
    ]
    print("① 갈래별 줄 수")
    for label, count in lines:
        print(f"   {pad(label, 34)}{count:6}")
    print()


def print_rows(rows: list, limit: int, show_values: bool) -> None:
    """바뀌는 줄만 편다. **값은 안 찍는다** — `--show-values` 일 때만.

    **갈래마다 따로 센 만큼 편다.** 한 덩어리로 id 순서대로 자르면 앞쪽 갈래가
    자리를 다 먹어, 정작 눈으로 봐야 할 `옮김`(메모로 옮기는 줄)이 한 줄도
    안 보인 채 "그 밖 N줄" 로 접힌다.
    """
    changing = [r for r in rows if r[1] != "keep"]
    print(f"② 바뀌는 줄 {len(changing)}개"
          + ("" if show_values else " — 값은 모양(길이)으로만 찍는다"
                                   " (`--show-values` 로 값을 본다)"))
    print("   " + pad("갈래", 7) + pad("id", 7, right=True) + "  "
          + pad("그룹 값" if show_values else "그룹 길이", 22) + "  "
          + pad("겹친 칸", 22) + pad("메모", 7, right=True) + "  결과")
    for action in ("fix", "drop", "move"):
        mine = [r for r in changing if r[1] == action]
        for _row_id, _action, where, before, after in mine[:limit or None]:
            group, memo = before["group_name"], before["memo"]
            grown = ("" if after["memo"] == memo
                     else f" · 메모 +{len(after['memo']) - len(memo or '')}자")
            print("   " + pad(LABELS[action], 7)
                  + pad(str(_row_id), 7, right=True) + "  "
                  + pad(group if show_values else shape(group), 22) + "  "
                  + pad(where, 22) + pad(shape(memo), 7, right=True)
                  + "  → " + (after["group_name"] or "(빔)") + grown)
        if limit and len(mine) > limit:
            print(f"   … {LABELS[action]} {len(mine) - limit}줄 더 "
                  "(`--limit 0` 으로 전부 편다)")
    print()


def apply_plan(con: sqlite3.Connection, rows: list) -> int:
    """계획대로 적는다. 바뀌는 줄만 건드린다."""
    changed = 0
    for row_id, action, _where, _before, after in rows:
        if action == "keep":
            continue
        con.execute(f"UPDATE {TABLE} SET group_name = ?, memo = ? WHERE id = ?",
                    (after["group_name"], after["memo"], row_id))
        changed += 1
    con.commit()
    return changed


def save_baseline(path: Path, rows: list) -> int:
    """되돌리기 파일. 바뀌는 줄의 `전`·`후` 를 그대로 적는다."""
    data = [{"id": row_id, "action": action, "where": where,
             "before": before, "after": after}
            for row_id, action, where, before, after in rows if action != "keep"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(data)


def restore(con: sqlite3.Connection, path: Path) -> int:
    """떠 둔 파일의 `before` 를 그대로 다시 적는다 — **원상 복구**."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data:
        con.execute(f"UPDATE {TABLE} SET group_name = ?, memo = ? WHERE id = ?",
                    (item["before"]["group_name"], item["before"]["memo"],
                     item["id"]))
    con.commit()
    return len(data)


def check_baseline(con: sqlite3.Connection, path: Path) -> int:
    """**계획대로 바뀌었는가.** 떠 둔 `after` 와 지금 DB 를 줄마다 맞춘다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [item["id"] for item in data]
    now = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        for row_id, group, memo in con.execute(
                f"SELECT id, group_name, memo FROM {TABLE} "
                f"WHERE id IN ({marks})", chunk):
            now[row_id] = {"group_name": group, "memo": memo}

    bad = [item["id"] for item in data
           if now.get(item["id"]) != item["after"]]
    print(f"③ 기준과 맞추기 — 떠 둔 {len(data)}줄")
    print(f"   계획대로 {len(data) - len(bad)}줄 · 어긋남 {len(bad)}줄")
    if bad:
        print(f"   어긋난 id: {', '.join(str(i) for i in bad[:20])}"
              + (" …" if len(bad) > 20 else ""))
    print()
    return len(bad)


def default_db() -> Path:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return Path(__file__).resolve().parent.parent / "data" / "dealflow.db"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="그룹 칸을 정해 둔 갈래만 담게 정리한다 (기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    # `--dry-run` 은 **기본값**이라 안 적어도 미리보기다. 그래도 받는다 —
    # 적어 두고 돌린 명령이 "안 적었으니 저장됐나" 로 읽히면 안 된다.
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 DB 에 적는다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--save-baseline", default="",
                    help="바꾸기 전 `(id, group_name, memo)` 를 이 파일로 떠 둔다")
    ap.add_argument("--baseline", default="",
                    help="떠 둔 파일과 지금 DB 를 맞춘다 (바꾼 뒤에 돌린다)")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일로 **원상 복구**한다 (`--apply` 와 함께)")
    ap.add_argument("--show-values", action="store_true",
                    help="값 자체를 찍는다. 기본은 끔 — 실명이 섞여 있다")
    ap.add_argument("--limit", type=int, default=30,
                    help="②에 몇 줄까지 펼까 (0 = 전부)")
    args = ap.parse_args()

    path = Path(args.db) if args.db else default_db()
    if not path.exists():
        print(f"그런 파일이 없다: {path}", file=sys.stderr)
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
        # 되돌릴 파일 없이 바꾸면 되돌릴 길이 없다. 막는다.
        print("`--apply` 에는 `--save-baseline` 이 있어야 한다 "
              "(되돌릴 파일 없이 바꾸지 않는다).", file=sys.stderr)
        return 2

    con = open_db(path, write=args.apply)
    try:
        rows = plan(con)

        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: 그룹 칸은 정해 둔 갈래만 담는다 — 문장은 아니다 "
              "(판정은 `app/services/group_name.decide`)")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()

        print_summary(rows)
        print_rows(rows, args.limit, args.show_values)

        if args.save_baseline:
            saved = save_baseline(Path(args.save_baseline), rows)
            print(f"되돌리기 파일을 떠 두었다: {args.save_baseline} ({saved}줄)")
            print("   ※ 값이 그대로 들어 있다. 저장소 밖에 두어라.")
            print()

        if args.apply:
            changed = apply_plan(con, rows)
            print(f"DB 에 적었다: {changed}줄")
            print(f"   되돌리려면: python {Path(__file__).name} "
                  f"--restore {args.save_baseline} --apply")
            print()

        if args.baseline:
            return 1 if check_baseline(con, Path(args.baseline)) else 0
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
