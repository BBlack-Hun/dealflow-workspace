"""이미 들어와 있는 미팅 이력(`contact_activities.kind = 'meeting'`)을 **다시 가른다.**

시트 머리글에 `미팅` 글자만 있으면 전부 한 칸(`meeting`)으로 눌렸다. 그래서
**미팅을 청하기만 한 줄**과 **실제로 만난 줄**이 같은 값이 되고, 읽는 쪽은
둘을 가릴 수 없어 전부 "미팅했다" 로 읽었다 — 고객사가 "그분들은 실제로
미팅하신 상태가 아닙니다" 라고 짚은 자리다.

앞으로 들어오는 줄은 고쳤다(`app/services/sheet_import`). **이미 들어와 있는
줄은 그대로**라 이 스크립트가 같은 규칙으로 다시 가른다.

    # ① 무엇이 어디로 가는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/resplit_meeting_kind.py

    # ② 되돌릴 파일을 떠 두고 실제로 바꾼다
    python scripts/resplit_meeting_kind.py --apply --save-baseline /tmp/meet.json

    # ③ 바뀐 것이 계획대로인지 맞춘다
    python scripts/resplit_meeting_kind.py --baseline /tmp/meet.json

    # ④ 되돌린다
    python scripts/resplit_meeting_kind.py --restore /tmp/meet.json --apply

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/resplit_deal_companies.py` 의 뼈대를 그대로 따른다(`--dry-run` ·
`--baseline` · `--save-baseline` · `--restore` · `--show-values` · `--limit`).

## 판정은 **여기 적지 않는다**

`app/services/meeting_kind` 의 `of_content()` 하나를 부른다 — 시트를 읽어
넣는 쪽(`services/sheet_import`)이 부르는 바로 그 모듈이다. 규칙이 두 군데
적히면 **앞으로 들어오는 것과 이미 들어와 있는 것이 다르게 갈린다.**

## 다섯 갈래로 가른다

    요청   `meeting_request`  청했을 뿐 안 만났다
    확정   `meeting_set`      날짜가 잡혔다. 그래도 아직 안 만났다
    완료   `meeting_done`     실제로 만났다
    그대로 **미팅 말이 없다** — 내용에 미팅 이야기가 아예 없는 줄(`검토 중`
           같은 잡담). 머리글이 무엇이었는지는 이 표에 안 남아 있으므로
           (`contact_activities` 에는 칸 이름이 없다) 옮기면 **추측**이 된다.
    그대로 **가릴 수 없다** — 미팅 말은 있는데 어느 갈래인지 못 정한 줄
           (`미팅 취소`·`미팅 미진행` 처럼 안 했다는 말이 섞인 줄 포함).

뒤의 둘은 **옮기지 않고 센다.** 옛 값 `meeting` 은 가르기 전까지 지금 뜻
그대로라(`services/meeting_kind` 모듈 설명), 손대지 않으면 그 줄들은 지금과
똑같이 보인다. 사람이 `--show-values` 로 읽어 보고 화면에서 고치면 된다.

## 이름을 찍지 않는다

내용에 실명·투자사명이 섞여 있다. 미리보기는 **모양(길이)** 만 찍고, 값 자체는
`--show-values` 를 따로 줄 때만 찍는다(기본은 끔).

## 되돌리기

바꾸기 전의 줄 전체를 파일에 떠 둔다. `--restore` 는 그 파일의 `before` 를
그대로 다시 적는다. 줄을 새로 만들지도 지우지도 않으므로(칸 하나만 바꾼다)
되돌리면 값이 한 글자도 안 달라진다.

**떠 둔 파일에는 값이 그대로 들어 있다.** 공개 저장소에 넣지 말고 저장소
밖(`/tmp`)에 두어라.
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

TABLE = "contact_activities"

#: 가를 대상 = **아직 안 가른 옛 값 하나뿐**이다. 이미 갈린 줄은 안 건드린다
#: (두 번 돌려도 같은 결과다).
KIND = "meeting"

#: 줄을 이루는 칸. 되돌리기 파일에 이 칸들을 통째로 떠 둔다.
COLUMNS = ("contact_id", "month", "kind", "content", "happened_at", "source",
           "created_at", "updated_at", "weekday", "company_names",
           "company_count", "raw_text", "batch_key", "undone_at")

#: 옮기지 않는 두 갈래의 이름. 갈래 이름 자리에 쓰므로 실제 `kind` 값과
#: 겹치지 않는 글자로 둔다.
NO_WORD = "그대로(미팅 말 없음)"
UNSURE = "그대로(가릴 수 없음)"


def open_db(path: Path, write: bool) -> sqlite3.Connection:
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다."""
    if write:
        return sqlite3.connect(str(path))
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def pad(text: str, width: int, right: bool = False) -> str:
    """표의 칸을 **눈에 보이는 너비**로 맞춘다(한글 한 글자 = 두 칸)."""
    room = max(0, width - sum(
        2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text))
    return (" " * room + text) if right else (text + " " * room)


def shape(text: str) -> str:
    """값의 **모양**. 실명이 찍히면 안 되니 길이만 적는다."""
    text = (text or "").strip()
    return f"{len(text)}자" if text else "빈칸"


def read_rows(con: sqlite3.Connection) -> list:
    """가를 후보 줄 — 아직 안 가른 미팅, 되돌리지 않은 것."""
    cols = ", ".join(("id",) + COLUMNS)
    return [dict(zip(("id",) + COLUMNS, row)) for row in con.execute(
        f"SELECT {cols} FROM {TABLE} WHERE kind = ? AND undone_at IS NULL "
        "ORDER BY id", (KIND,))]


def plan(con: sqlite3.Connection) -> list:
    """줄마다 `(갈래, before, after)`. **DB 를 읽기만 한다.**

    미리보기와 저장이 **같은 계획 하나**를 지나야 미리 본 것이 실제와 같다.
    """
    from app.services import meeting_kind as mk

    out = []
    for row in read_rows(con):
        # 내용과 원문을 함께 본다 — 회차를 쪼개며 `content` 에서 날짜가 떨어져
        # 나간 줄이 있고, 갈래를 가리는 말은 그 뒤에 남아 있다.
        text = " ".join(t for t in (row["content"], row["raw_text"]) if t)
        if not mk.mentions_meeting(text):
            out.append({"id": row["id"], "bucket": NO_WORD, "row": row,
                        "kind": None})
            continue
        kind = mk.of_content(text)
        out.append({"id": row["id"], "bucket": kind or UNSURE, "row": row,
                    "kind": kind})
    return out


def moved(rows: list) -> list:
    """실제로 칸이 바뀌는 줄만."""
    return [r for r in rows if r["kind"]]


# ── 세어 보기 ───────────────────────────────────────────────────────────────

def people_counts(con: sqlite3.Connection, rows: list) -> dict:
    """**사람 수가 어떻게 바뀌나.** 줄 수보다 이쪽이 화면에 보이는 것이다.

    세는 잣대는 `meeting_kind.MET` — 화면·엑셀의 `미팅(누적)` 이 세는 바로 그
    갈래다(`routers/contacts.contact_rows`). 여기서 다시 정하지 않는다.

    **이 표(`contact_activities`)만 본다.** 이 앱에서 잡은 미팅(`meetings` 표)은
    이 스크립트가 건드리지 않으므로 전후가 같다 — 섞어 세면 안 바뀐 것까지
    바뀐 것처럼 보인다.
    """
    from app.services import meeting_kind as mk

    plan_by_id = {r["id"]: r for r in rows}

    before, after, done_after, asked_after = set(), set(), set(), set()
    cols = "id, contact_id, kind"
    for row_id, contact_id, kind in con.execute(
            f"SELECT {cols} FROM {TABLE} WHERE undone_at IS NULL"):
        if kind not in mk.ALL:
            continue
        if kind in mk.MET:
            before.add(contact_id)
        item = plan_by_id.get(row_id)
        now = (item["kind"] or kind) if item else kind
        if now in mk.MET:
            after.add(contact_id)
        if now == mk.DONE:
            done_after.add(contact_id)
        if now == mk.REQUEST:
            asked_after.add(contact_id)
    return {"before": len(before), "after": len(after),
            "done": len(done_after), "asked": len(asked_after),
            "dropped": len(before - after), "kept": len(before & after)}


def summarize(rows: list) -> Counter:
    counts: Counter = Counter()
    for item in rows:
        counts[item["bucket"]] += 1
    return counts


def print_summary(rows: list, people: dict, counts_all: int) -> None:
    from app.services import meeting_kind as mk

    counts = summarize(rows)
    print("① 갈래별 줄 수")
    order = [(mk.REQUEST, f"{mk.LABELS[mk.REQUEST]}   ← 청했을 뿐 안 만났다"),
             (mk.SET, f"{mk.LABELS[mk.SET]}   ← 날짜는 잡혔다"),
             (mk.DONE, f"{mk.LABELS[mk.DONE]}   ← 실제로 만났다"),
             (NO_WORD, f"{NO_WORD}   ← 안 옮긴다"),
             (UNSURE, f"{UNSURE}   ← 안 옮긴다")]
    for key, label in order:
        print(f"   {pad(label, 40)}{counts[key]:6}")
    print(f"   {pad('─ 옮기는 줄 합계', 40)}{len(moved(rows)):6}")
    print(f"   {pad('─ 아직 안 가른 미팅 줄 전체', 40)}{counts_all:6}")
    print()
    print("② 화면에 **미팅으로 서는 사람** 수 (`meeting_kind.MET` — 엑셀의 "
          "`미팅(누적)` 과 같은 잣대)")
    for label, value in (
        ("미팅으로 서는 사람 (전 → 후)", f"{people['before']} → {people['after']}"),
        ("└ 그대로 남는 사람", f"{people['kept']}"),
        ("└ 미팅에서 내려오는 사람", f"{people['dropped']}"),
        ("그중 `미팅 완료` 로 서는 사람", f"{people['done']}"),
        ("`미팅 요청` 으로 내려가는 사람", f"{people['asked']}"),
    ):
        print(f"   {pad(label, 40)}{value:>10}")
    print("   ※ 이 앱에서 잡은 미팅(`meetings` 표)은 안 건드린다 — 그쪽 근거로")
    print("     서 있는 사람은 위 수와 무관하게 그대로 미팅이다.")
    print()


def print_rows(rows: list, limit: int, show_values: bool) -> None:
    """옮기는 줄과 **안 옮기는 줄**을 함께 편다.

    안 옮기는 줄을 감추면 사람이 볼 길이 없다 — 그 줄들이 바로 손으로
    가려야 하는 줄이다.
    """
    from app.services import meeting_kind as mk

    print(f"③ 줄별 판정 — 값은 "
          + ("그대로 찍는다" if show_values
             else "모양(길이)으로만 찍는다 (`--show-values` 로 값을 본다)"))
    print("   " + pad("갈래", 18) + pad("id", 7, right=True) + "  "
          + pad("달", 9) + pad("내용", 40))
    for key in (mk.REQUEST, mk.SET, mk.DONE, NO_WORD, UNSURE):
        mine = [r for r in rows if r["bucket"] == key]
        label = mk.LABELS.get(key, key)
        for item in mine[:limit or None]:
            row = item["row"]
            text = (row["content"] or "").strip()
            print("   " + pad(label, 18)
                  + pad(str(item["id"]), 7, right=True) + "  "
                  + pad(row["month"] or "-", 9)
                  + pad(text[:40] if show_values else shape(text), 40))
        if limit and len(mine) > limit:
            print(f"   … {label} {len(mine) - limit}줄 더 "
                  "(`--limit 0` 으로 전부 편다)")
    print()


def apply_plan(con: sqlite3.Connection, rows: list) -> int:
    """계획대로 적는다. **바꾸는 칸은 `kind` 하나**다."""
    changed = 0
    for item in moved(rows):
        con.execute(f"UPDATE {TABLE} SET kind = ? WHERE id = ?",
                    (item["kind"], item["id"]))
        changed += 1
    con.commit()
    return changed


def save_baseline(path: Path, rows: list) -> int:
    """되돌리기 파일. **옮기는 줄만** 전·후를 그대로 적는다."""
    data = [{"id": item["id"], "bucket": item["bucket"],
             "before": {c: item["row"][c] for c in COLUMNS},
             "after": dict({c: item["row"][c] for c in COLUMNS},
                           kind=item["kind"])}
            for item in moved(rows)]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(data)


def restore(con: sqlite3.Connection, path: Path) -> int:
    """떠 둔 파일의 `before` 를 다시 적는다 — 원상 복구."""
    data = json.loads(path.read_text(encoding="utf-8"))
    sets = ", ".join(f"{c} = ?" for c in COLUMNS)
    for item in data:
        con.execute(f"UPDATE {TABLE} SET {sets} WHERE id = ?",
                    [item["before"][c] for c in COLUMNS] + [item["id"]])
    con.commit()
    return len(data)


def check_baseline(con: sqlite3.Connection, path: Path) -> int:
    """**계획대로 바뀌었는가.** 떠 둔 `후` 와 지금 DB 를 줄마다 맞춘다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cols = ", ".join(COLUMNS)
    bad = []
    for item in data:
        got = con.execute(f"SELECT {cols} FROM {TABLE} WHERE id = ?",
                          (item["id"],)).fetchone()
        if got is None or list(got) != [item["after"][c] for c in COLUMNS]:
            bad.append(item["id"])
    print(f"④ 기준과 맞추기 — 떠 둔 {len(data)}줄")
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
        description="이미 들어온 미팅 이력을 요청·확정·완료로 다시 가른다 "
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
                    help="내용을 그대로 찍는다. 기본은 끔 — 실명이 섞여 있다")
    ap.add_argument("--limit", type=int, default=20,
                    help="③에 갈래마다 몇 줄까지 펼까 (0 = 전부)")
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
            back = restore(con, Path(args.restore))
        finally:
            con.close()
        print(f"되돌렸다: 되살린 줄 {back} ← {args.restore}")
        return 0

    if args.apply and not args.save_baseline:
        # 되돌릴 파일 없이 바꾸면 되돌릴 길이 없다. 막는다.
        print("`--apply` 에는 `--save-baseline` 이 있어야 한다 "
              "(되돌릴 파일 없이 바꾸지 않는다).", file=sys.stderr)
        return 2

    con = open_db(path, write=args.apply)
    try:
        rows = plan(con)
        people = people_counts(con, rows)
        all_rows = con.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE kind = ?", (KIND,)).fetchone()[0]

        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: 눌려 있던 `meeting` 을 요청·확정·완료로 가른다 "
              "(판정은 `app/services/meeting_kind.of_content`)")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()

        print_summary(rows, people, all_rows)
        print_rows(rows, args.limit, args.show_values)

        if args.save_baseline:
            # **바꾸기 전에** 떠 둔다. 적는 중에 멈춰도 되돌릴 파일은 남는다.
            saved = save_baseline(Path(args.save_baseline), rows)
            print(f"되돌리기 파일을 떠 두었다: {args.save_baseline} ({saved}줄)")
            print("   ※ 값이 그대로 들어 있다. 저장소 밖에 두어라.")
            print()

        if args.apply:
            changed = apply_plan(con, rows)
            print(f"DB 에 적었다: 갈래를 바꾼 줄 {changed}")
            if args.save_baseline:
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
