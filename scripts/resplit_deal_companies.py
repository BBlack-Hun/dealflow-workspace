"""딜 소개 이력(`contact_activities.kind = 'deal_intro'`)을 **다시 쪼갠다.**

시트에서 옮겨 올 때 쓰던 옛 규칙은 **대괄호 씌운 날짜**(`[8/5]`)를 날짜로 못
읽었다. 그래서 그 줄이 앞 회차에 통째로 이어 붙고, 쉼표로만 갈라서
`앞기업 [8/12] 뒷기업` 같은 **덩어리 하나**가 기업 이름 자리에 남았다. 이름이
뭉치면 `deal_history._key` 가 맞출 수 없으니 앱은 그 기업들을 **"소개한 적
없음"** 으로 본다 — 딜을 고를 때 이미 보낸 기업이 다시 올라온다.

파서는 고쳤지만(`app/services/company_names`) **이미 들어와 있는 줄은 그대로**다.
이 스크립트가 그 줄들을 같은 규칙으로 다시 쪼갠다.

    # ① 무엇이 어떻게 바뀌는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/resplit_deal_companies.py

    # ② 되돌릴 파일을 떠 두고 실제로 바꾼다
    python scripts/resplit_deal_companies.py --apply --save-baseline /tmp/deal.json

    # ③ 바뀐 것이 계획대로인지 맞춘다
    python scripts/resplit_deal_companies.py --baseline /tmp/deal.json

    # ④ 되돌린다
    python scripts/resplit_deal_companies.py --restore /tmp/deal.json --apply

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/clean_group_name.py` 가 같은 방식이고, 이 스크립트는 그 뼈대를 그대로
따른다(`--dry-run` · `--baseline` · `--save-baseline` · `--restore` ·
`--show-values` · `--limit`).

## 판정은 **여기 적지 않는다**

`app/services/company_names` 의 `rounds()` · `split()` 하나를 부른다 — 시트를
읽어 넣는 쪽(`services/sheet_import`)이 부르는 바로 그 함수다. 규칙이 두 군데
적히면 **앞으로 들어오는 것과 이미 들어와 있는 것이 다르게 쪼개진다.**

## 세 갈래로 가른다

    그대로   다시 쪼개도 같다. 손대지 않는다.
    고침     이름이 뭉쳐 있었다. `company_names` · `company_count` ·
             (비어 있던) `happened_at` · `weekday` · `content` 를 고친다.
    나눔     한 줄에 **회차가 둘 이상** 뭉쳐 있었다. 앞 회차는 그 줄에 두고,
             뒤 회차는 **줄을 새로 만들어** 제 날짜와 함께 옮긴다.

`나눔` 이 필요한 이유: 뒤 회차를 앞 줄에 얹어 두면 기업은 맞아도 **날짜가 앞
회차 날짜로** 잡힌다(실자료에서 중앙값 8일, 최대 16일 어긋난다). `마지막으로
소개한 날` 과 `최근 45일 내 소개함` 이 그 값을 읽는다.

새로 만드는 줄은 임포트가 중복을 가리는 그 열쇠
`(contact_id, kind, content, month)` 로 먼저 살펴보고, 이미 있으면 안 만든다 —
그래서 **두 번 돌려도 줄이 늘지 않는다.** 고친 줄의 `content` 도 고친 파서가
내놓는 모양과 같게 맞춘다(날짜를 뗀 그 회차의 글). 그래야 다음 시트 업로드가
그 열쇠로 **이미 있는 줄을 알아보고** 같은 회차를 또 만들지 않는다.

## 손대지 않는 줄

- `source = 'manual'` — 사람이 화면에서 직접 고른 기업이다. 글에서 다시
  읽어 내면 사람이 고른 것을 기계 추측으로 덮는다.
- `undone_at` 이 찍힌 줄 — 되돌린 줄이다. 어디서도 안 읽히므로 건드리지 않는다.

## 이름을 찍지 않는다

기업 이름은 실명이다. 미리보기는 **모양(길이·개수)** 만 찍는다. 값 자체는
`--show-values` 를 따로 줄 때만 찍는다(기본은 끔).

## 되돌리기

바꾸기 전의 줄 전체를 파일에 떠 둔다. `--restore` 는 그 파일의 `before` 를 그대로
다시 적고, **새로 만든 줄은 지운다.** 되돌리면 값이 한 글자도 안 달라져야 한다.

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
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TABLE = "contact_activities"
KIND = "deal_intro"

#: 손대지 않는 출처. 사람이 화면에서 고른 기업을 글에서 다시 읽어 내지 않는다.
SKIP_SOURCE = "manual"

#: 줄을 이루는 칸. 되돌리기 파일에 이 칸들을 통째로 떠 둔다.
COLUMNS = ("contact_id", "month", "kind", "content", "happened_at", "source",
           "created_at", "updated_at", "weekday", "company_names",
           "company_count", "raw_text", "batch_key", "undone_at")

KEEP, FIX, SPLIT = "keep", "fix", "split"
LABELS = {KEEP: "그대로", FIX: "고침", SPLIT: "나눔"}


def open_db(path: Path, write: bool) -> sqlite3.Connection:
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다."""
    if write:
        return sqlite3.connect(str(path))
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def shape(names) -> str:
    """값의 **모양**. 실명이 찍히면 안 되니 개수와 길이만 적는다."""
    if not names:
        return "없음"
    return f"{len(names)}개 " + "·".join(f"{len(n)}자" for n in names[:6]) + (
        " …" if len(names) > 6 else "")


def pad(text: str, width: int, right: bool = False) -> str:
    """표의 칸을 **눈에 보이는 너비**로 맞춘다(한글 한 글자 = 두 칸)."""
    room = max(0, width - sum(
        2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text))
    return (" " * room + text) if right else (text + " " * room)


def names_of(raw) -> list:
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def read_rows(con: sqlite3.Connection) -> list:
    """다시 쪼갤 후보 줄 — 딜 소개, 시트·앱에서 온 것, 되돌리지 않은 것."""
    cols = ", ".join(("id",) + COLUMNS)
    return [dict(zip(("id",) + COLUMNS, row)) for row in con.execute(
        f"SELECT {cols} FROM {TABLE} WHERE kind = ? AND undone_at IS NULL "
        "AND IFNULL(source, '') != ? ORDER BY id", (KIND, SKIP_SOURCE))]


def _year_of(row: dict) -> Optional[int]:
    """이 줄의 연도. 달 칸(`2026-08`)이 있으면 그것, 없으면 원래 날짜에서."""
    month = row.get("month") or ""
    if len(month) >= 4 and month[:4].isdigit():
        return int(month[:4])
    happened = row.get("happened_at") or ""
    if len(happened) >= 4 and happened[:4].isdigit():
        return int(happened[:4])
    return None


def _iso(year, month, day) -> Optional[str]:
    if year is None or not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def plan(con: sqlite3.Connection) -> list:
    """줄마다 `(판정, before, after, 새 줄들)`. **DB 를 읽기만 한다.**

    미리보기와 저장이 **같은 계획 하나**를 지나야 미리 본 것이 실제와 같다
    (`clean_group_name.plan` 이 같은 이유로 정하는 일과 얹는 일을 나눴다).
    """
    from app.services import company_names as cnames
    from app.services.sheet_import import weekday_of

    # 임포트가 중복을 가리는 그 열쇠. 새 줄이 이미 있는 줄과 겹치지 않게 본다.
    taken = {(cid, kind, content, month) for cid, kind, content, month
             in con.execute(f"SELECT contact_id, kind, content, month FROM {TABLE}")}

    out = []
    for row in read_rows(con):
        chunks = cnames.rounds(row["raw_text"] or row["content"] or "")
        if not chunks:
            continue
        year = _year_of(row)

        head = chunks[0]
        first = cnames.split(head.content)
        after = dict(row)
        after["content"] = head.content or row["content"]
        after["raw_text"] = head.raw or row["raw_text"]
        after["company_names"] = (json.dumps(first.names, ensure_ascii=False)
                                  if first.names else None)
        after["company_count"] = first.count
        # **날짜는 버리지 않는다.** 비어 있을 때만 채운다 — 이미 들어 있는 값은
        # 사람이 고쳤을 수 있고, 시트 글자보다 그쪽이 맞다.
        if not row["happened_at"]:
            when = (_iso(year, head.month, head.day) if head.dated
                    else _iso(year, *first.dates[0]) if first.dates else None)
            if when:
                after["happened_at"] = when
        if not row["weekday"]:
            after["weekday"] = head.weekday or (
                weekday_of(after["happened_at"]) if after["happened_at"] else None)

        fresh = []
        for chunk in chunks[1:]:
            part = cnames.split(chunk.content)
            if not part.names and not part.count:
                continue
            new = {c: row[c] for c in COLUMNS}
            new["content"] = chunk.content or chunk.raw
            new["raw_text"] = chunk.raw
            new["company_names"] = (json.dumps(part.names, ensure_ascii=False)
                                    if part.names else None)
            new["company_count"] = part.count
            when = (_iso(year, chunk.month, chunk.day) if chunk.dated
                    else _iso(year, *part.dates[0]) if part.dates else None)
            new["happened_at"] = when
            new["weekday"] = chunk.weekday or (weekday_of(when) if when else None)
            key = (new["contact_id"], new["kind"], new["content"], new["month"])
            if key in taken:
                continue          # 이미 있는 줄이다. 두 번 돌려도 안 늘어난다.
            taken.add(key)
            fresh.append(new)

        changed = any(after[c] != row[c] for c in COLUMNS)
        action = SPLIT if fresh else (FIX if changed else KEEP)
        if action == KEEP:
            continue
        out.append({"id": row["id"], "action": action,
                    "before": {c: row[c] for c in COLUMNS},
                    "after": after, "fresh": fresh})
    return out


# ── 세어 보기 ───────────────────────────────────────────────────────────────

def match_counts(con: sqlite3.Connection, rows: list) -> dict:
    """**맞출 수 있는 이름인가** — 고치기 전/후를 같은 잣대로 센다.

    잣대는 `deal_history._key` 다. 여기서 또 적지 않는다 — 화면의
    `최근에 소개함` 과 `llm_brief.sent_before` 가 그 함수를 쓴다.
    """
    from app.services.deal_history import _key

    known = {_key(n) for (n,) in con.execute("SELECT name FROM ir_companies")}
    known.discard("")

    def tally(items):
        hit, miss = Counter(), Counter()
        for name in items:
            key = _key(name)
            if not key:
                continue
            (hit if key in known else miss)[key] += 1
        return hit, miss

    before, after = [], []
    for item in rows:
        before += names_of(item["before"]["company_names"])
        after += names_of(item["after"]["company_names"])
        for new in item["fresh"]:
            after += names_of(new["company_names"])
    hit_b, miss_b = tally(before)
    hit_a, miss_a = tally(after)
    return {
        "before_hit": len(hit_b), "before_miss": len(miss_b),
        "before_miss_rows": sum(miss_b.values()),
        "after_hit": len(hit_a), "after_miss": len(miss_a),
        "after_miss_rows": sum(miss_a.values()),
        "new_companies": len(set(hit_a) - set(hit_b)),
    }


def summarize(rows: list) -> Counter:
    counts: Counter = Counter()
    for item in rows:
        counts[item["action"]] += 1
        counts["fresh"] += len(item["fresh"])
        if item["action"] != KEEP and not item["before"]["happened_at"] \
                and item["after"]["happened_at"]:
            counts["date_filled"] += 1
    return counts


def print_summary(rows: list, totals: dict, counts_all: int) -> None:
    counts = summarize(rows)
    print("① 갈래별 줄 수")
    for label, count in (
        (f"{LABELS[FIX]}   (이름이 뭉쳐 있던 줄)", counts[FIX]),
        (f"{LABELS[SPLIT]}   (회차가 둘 이상 뭉쳐 있던 줄)", counts[SPLIT]),
        ("└ 새로 만드는 줄", counts["fresh"]),
        ("빈 날짜를 채우는 줄", counts["date_filled"]),
        ("─ 손대는 줄 합계", len(rows)),
        ("─ 딜 소개 줄 전체", counts_all),
    ):
        print(f"   {pad(label, 38)}{count:6}")
    print()
    print("② 기업 목록과 맞춰 보기 (`deal_history._key` 로 센다)")
    for label, count in (
        ("맞는 기업 (전 → 후)",
         f"{totals['before_hit']} → {totals['after_hit']}"),
        ("새로 잡히는 기업",  f"+{totals['new_companies']}"),
        ("못 맞춘 이름 가지 (전 → 후)",
         f"{totals['before_miss']} → {totals['after_miss']}"),
        ("못 맞춘 이름 건수 (전 → 후)",
         f"{totals['before_miss_rows']} → {totals['after_miss_rows']}"),
    ):
        print(f"   {pad(label, 38)}{count:>12}")
    print("   ※ 쪼갠 뒤에도 남는 `못 맞춘 이름` 은 지우지 않는다 — 지금 기업")
    print("     목록에 없는 기업일 뿐이고, 지우면 그 기록이 사라진다.")
    print()


def print_rows(rows: list, limit: int, show_values: bool) -> None:
    """바뀌는 줄만 편다. **값은 안 찍는다** — `--show-values` 일 때만."""
    print(f"③ 바뀌는 줄 {len(rows)}개"
          + ("" if show_values else " — 값은 모양(개수·길이)으로만 찍는다"
                                   " (`--show-values` 로 값을 본다)"))
    print("   " + pad("갈래", 7) + pad("id", 7, right=True) + "  "
          + pad("전", 30) + "  " + pad("후", 30) + "  새 줄")
    for action in (FIX, SPLIT):
        mine = [r for r in rows if r["action"] == action]
        for item in mine[:limit or None]:
            before = names_of(item["before"]["company_names"])
            after = names_of(item["after"]["company_names"])
            fresh = sum(len(names_of(n["company_names"])) for n in item["fresh"])
            show = (lambda ns: ", ".join(ns) if ns else "없음") if show_values else shape
            print("   " + pad(LABELS[action], 7)
                  + pad(str(item["id"]), 7, right=True) + "  "
                  + pad(show(before), 30) + "  " + pad(show(after), 30)
                  + "  " + (f"{len(item['fresh'])}줄 · 이름 {fresh}개"
                            if item["fresh"] else ""))
        if limit and len(mine) > limit:
            print(f"   … {LABELS[action]} {len(mine) - limit}줄 더 "
                  "(`--limit 0` 으로 전부 편다)")
    print()


def apply_plan(con: sqlite3.Connection, rows: list) -> tuple:
    """계획대로 적는다. 바뀌는 줄만 건드리고, 뒤 회차는 줄을 새로 만든다."""
    sets = ", ".join(f"{c} = ?" for c in COLUMNS)
    cols = ", ".join(COLUMNS)
    marks = ", ".join("?" * len(COLUMNS))
    changed = added = 0
    for item in rows:
        con.execute(f"UPDATE {TABLE} SET {sets} WHERE id = ?",
                    [item["after"][c] for c in COLUMNS] + [item["id"]])
        changed += 1
        for new in item["fresh"]:
            cur = con.execute(f"INSERT INTO {TABLE} ({cols}) VALUES ({marks})",
                              [new[c] for c in COLUMNS])
            new["id"] = cur.lastrowid
            added += 1
    con.commit()
    return changed, added


def save_baseline(path: Path, rows: list) -> int:
    """되돌리기 파일. 바뀌는 줄의 `전`·`후` 와 새로 만든 줄을 그대로 적는다."""
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(rows)


def restore(con: sqlite3.Connection, path: Path) -> tuple:
    """떠 둔 파일의 `before` 를 다시 적고, **새로 만든 줄은 지운다** — 원상 복구."""
    data = json.loads(path.read_text(encoding="utf-8"))
    sets = ", ".join(f"{c} = ?" for c in COLUMNS)
    back = gone = 0
    for item in data:
        for new in item.get("fresh", []):
            if new.get("id"):
                con.execute(f"DELETE FROM {TABLE} WHERE id = ?", (new["id"],))
            else:
                # id 를 못 적어 둔 파일(적기 전에 멈춘 경우) — 임포트가 쓰는
                # 그 열쇠로 찾아 지운다. 그 열쇠로는 줄이 하나뿐이다.
                con.execute(
                    f"DELETE FROM {TABLE} WHERE contact_id = ? AND kind = ? "
                    "AND content = ? AND IFNULL(month, '') = IFNULL(?, '')",
                    (new["contact_id"], new["kind"], new["content"],
                     new["month"]))
            gone += 1
        con.execute(f"UPDATE {TABLE} SET {sets} WHERE id = ?",
                    [item["before"][c] for c in COLUMNS] + [item["id"]])
        back += 1
    con.commit()
    return back, gone


def check_baseline(con: sqlite3.Connection, path: Path) -> int:
    """**계획대로 바뀌었는가.** 떠 둔 `후` 와 지금 DB 를 줄마다 맞춘다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cols = ", ".join(COLUMNS)
    bad = []
    rows = 0
    for item in data:
        wanted = [(item["id"], item["after"])]
        wanted += [(n.get("id"), n) for n in item.get("fresh", [])]
        for row_id, want in wanted:
            rows += 1
            if row_id is None:
                bad.append(item["id"])
                continue
            got = con.execute(f"SELECT {cols} FROM {TABLE} WHERE id = ?",
                              (row_id,)).fetchone()
            if got is None or list(got) != [want[c] for c in COLUMNS]:
                bad.append(row_id)
    print(f"④ 기준과 맞추기 — 떠 둔 {rows}줄")
    print(f"   계획대로 {rows - len(bad)}줄 · 어긋남 {len(bad)}줄")
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
        description="딜 소개 이력의 뭉친 기업 이름을 다시 쪼갠다 "
                    "(기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    # `--dry-run` 은 **기본값**이라 안 적어도 미리보기다. 그래도 받는다 —
    # 적어 두고 돌린 명령이 "안 적었으니 저장됐나" 로 읽히면 안 된다.
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 DB 에 적는다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--save-baseline", default="",
                    help="바꾸기 전 줄 전체를 이 파일로 떠 둔다")
    ap.add_argument("--baseline", default="",
                    help="떠 둔 파일과 지금 DB 를 맞춘다 (바꾼 뒤에 돌린다)")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일로 **원상 복구**한다 (`--apply` 와 함께)")
    ap.add_argument("--show-values", action="store_true",
                    help="값 자체를 찍는다. 기본은 끔 — 실명이 섞여 있다")
    ap.add_argument("--limit", type=int, default=20,
                    help="③에 몇 줄까지 펼까 (0 = 전부)")
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
            back, gone = restore(con, Path(args.restore))
        finally:
            con.close()
        print(f"되돌렸다: 되살린 줄 {back} · 지운 줄 {gone} ← {args.restore}")
        return 0

    if args.apply and not args.save_baseline:
        # 되돌릴 파일 없이 바꾸면 되돌릴 길이 없다. 막는다.
        print("`--apply` 에는 `--save-baseline` 이 있어야 한다 "
              "(되돌릴 파일 없이 바꾸지 않는다).", file=sys.stderr)
        return 2

    con = open_db(path, write=args.apply)
    try:
        rows = plan(con)
        totals = match_counts(con, rows)
        all_rows = con.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE kind = ?", (KIND,)).fetchone()[0]

        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: 뭉친 기업 이름을 다시 쪼갠다 — 회차가 둘이면 줄도 "
              "나눈다 (판정은 `app/services/company_names.split`)")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()

        print_summary(rows, totals, all_rows)
        print_rows(rows, args.limit, args.show_values)

        if args.save_baseline:
            # **바꾸기 전에** 떠 둔다. 적는 중에 멈춰도 되돌릴 파일은 남는다.
            saved = save_baseline(Path(args.save_baseline), rows)
            print(f"되돌리기 파일을 떠 두었다: {args.save_baseline} ({saved}줄)")
            print("   ※ 값이 그대로 들어 있다. 저장소 밖에 두어라.")
            print()

        if args.apply:
            changed, added = apply_plan(con, rows)
            print(f"DB 에 적었다: 고친 줄 {changed} · 새로 만든 줄 {added}")
            if args.save_baseline:
                # 새로 만든 줄의 id 까지 적어 다시 떠 둔다 — 되돌릴 때 그 줄을
                # 정확히 지우기 위해서다.
                save_baseline(Path(args.save_baseline), rows)
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
