"""`round_size` 에 섞여 적힌 투자 단계를 **`stages` 로 옮겨 적는다.**

`stages`(화면 이름 `선호 투자단계`)는 **넣는 길이 없어서** 운영 274줄이 전부
비어 있었다 — 시트를 읽는 세 갈래 어디에도 이 칸의 매핑이 없었다. 그런데 값은
실제로 있다. 단계를 적을 자리가 화면에 없으니 사람들이 옆 칸(`round_size`)에
함께 적어 왔다(`Series C 이상 6/30` · `Seed단계 위주로 보심`).

`stages` 는 **읽는 곳이 있다** — `matcher.evaluate_company` 가 기업의 `series`
와 견주어 `단계 불일치` 경고를 내고, `llm_brief.INVESTOR_FIELDS` 가 시킬 말에
싣는다. 비어 있는 동안 그 축이 통째로 죽어 있었다.

    # ① 무엇이 어떻게 바뀌는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/fill_stages_from_round.py

    # ② 되돌릴 파일을 떠 두고 실제로 바꾼다
    python scripts/fill_stages_from_round.py --apply --save-baseline /tmp/stages.json

    # ③ 바뀐 것이 계획대로인지 맞춘다
    python scripts/fill_stages_from_round.py --baseline /tmp/stages.json

    # ④ 되돌린다
    python scripts/fill_stages_from_round.py --restore /tmp/stages.json --apply

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/clean_group_name.py` 가 같은 방식이고, 이 스크립트도 그 뼈대를 따른다.

## **베낀다. 옮기지 않는다** — `round_size` 는 한 글자도 안 건드린다

그룹 칸을 정리할 때는 원본을 비웠다(`clean_group_name`). 그 칸은 A~F 만 담는
자리라 문장이 있으면 안 됐기 때문이다. **여기는 다르다.**

  · `round_size` 의 본뜻은 금액이고 `matcher.parse_round_size_eok` 가 그것을
    읽는데, 옮길 23줄 중 **22줄은 원래부터 금액이 없다**(`None`). 단계 말을
    빼도 그 축에서 얻는 것이 **없다.**
  · 반대로 빼면 잃는 것이 크다. 23줄 중 16줄은 빼고 나면 빈 글이거나 `이상` ·
    `단계` 같은 **토막말만** 남고, 5줄은 문장이 부서진다(`또는 상장사 메자닌` ·
    `단계 위주로 보심`). 사람이 적어 둔 원문이 훼손된다.
  · 그룹 칸 때도 **문장 안에서 낱말만 도려낸 적은 없다.** `group_name.decide`
    는 값을 통째로 두거나, 통째로 비우거나, 통째로 옮겼다. 이 저장소에 사람이
    쓴 문장을 부분 삭제한 전례는 없다.

같은 사실이 두 칸에 남는 것은 맞다. 그래도 **읽는 쪽이 갈리지 않는다** —
`matcher` 는 단계를 `stages` 에서만 읽고 금액을 `round_size` 에서만 읽는다.
`round_size` 의 단계 말은 어느 읽는 쪽에도 안 걸리는 죽은 글자다.

## 판정은 여기 적지 않는다

`app/services/invest_stage.decide()` 하나를 부른다 — 시트를 읽어 넣는 쪽
(`services/sheet_import.apply_sheet_a`)이 부르는 바로 그 함수다. 규칙이 두
군데 적히면 한쪽이 낡고, 그러면 여기서 정리해 둔 것을 다음 업로드가 되돌린다.

## 여섯 갈래로 가른다

    넣음     확실한 단계 말이다 (`Series C 이상` → `SeriesC, Pre-IPO`)
    애매     `초기`·`후기`·`얼리스테이지` 뿐이다. **세기만 한다**
    뒤집힘   단계 말은 있는데 뜻이 반대다 (`Seed 단계 검토 어려움`)
    단계없음 금액·분야만 적힌 줄
    이미있음 `stages` 에 값이 있다 — 덮지 않는다
    빈칸     `round_size` 가 비었다

`애매` 와 `뒤집힘` 은 **손대지 않는다.** 틀리게 넣으면 딜 고르기가 엉뚱한
단계로 걸러진다. 특히 `뒤집힘` 은 비어 있는 것보다 나쁘다 — 안 보겠다고 적어
둔 사람에게 `단계 일치` 가 떠서 그 딜이 권해진다.

## 이름을 찍지 않는다

이 칸에는 투자사 이야기가 섞여 있다. 그래서 미리보기는 **id 와 값의 모양**
(길이 · 어느 갈래인지 · 읽어낸 단계)만 찍는다. 값 자체는 `--show-values` 일
때만 본다(기본은 끔).

## 되돌리기

바꾸기 전의 `(id, stages)` 를 통째로 파일에 떠 둔다. `--restore` 는 그 파일의
`before` 를 그대로 다시 적는다. `round_size` 는 애초에 안 건드리므로 떠 둘
것도 없다 — 되돌릴 칸이 하나뿐인 것이 이 갈래(베끼기)를 고른 덤이다.

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

TABLE = "vc_contacts"

# 갈래마다 화면에 적는 말. `decide()` 가 돌려주는 값을 그대로 열쇠로 쓴다 —
# 여기에 갈래를 새로 적어 두면 판정이 늘 때 한쪽만 늘어난다.
LABELS = {
    "fill": "넣음",
    "vague": "애매",
    "negated": "뒤집힘",
    "none": "단계없음",
    "taken": "이미있음",
    "empty": "빈칸",
}


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
    칸을 먹고, 그러면 줄마다 칸이 어긋나 표를 읽을 수가 없다.
    """
    room = max(0, width - sum(
        2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text))
    return (" " * room + text) if right else (text + " " * room)


def read_rows(con: sqlite3.Connection) -> list:
    """`round_size` 에 값이 있는 줄 전부 — `(id, round_size, stages)`."""
    return list(con.execute(
        f"SELECT id, round_size, stages FROM {TABLE} "
        "WHERE round_size IS NOT NULL AND TRIM(round_size) != '' "
        "ORDER BY id"))


def plan(con: sqlite3.Connection) -> list:
    """줄마다 `(id, 판정, 읽어낸 단계, 전, 후)`. **DB 를 읽기만 한다.**

    `전`·`후` 는 되돌리기 파일에 그대로 들어간다 — 미리보기와 저장이 **같은
    계획 하나**를 지나야 미리 본 것이 실제와 같다.
    """
    from app.services import invest_stage as st

    out = []
    for row_id, round_size, stages in read_rows(con):
        decision = st.decide(round_size, stages=stages)
        before = {"stages": stages, "round_size": round_size}
        after = {"stages": decision.stages if decision.changes else stages,
                 # **원문은 안 건드린다.** 떠 두는 것은 맞춰 보기 위해서다 —
                 # 되돌리기가 이 칸을 다시 적지는 않는다.
                 "round_size": round_size}
        out.append((row_id, decision.action, list(decision.found), before, after))
    return out


def summarize(rows: list) -> Counter:
    """갈래별 줄 수. 실측으로 센 표와 **같은 결**로 나와야 한다."""
    counts: Counter = Counter()
    for _row_id, action, _found, _before, _after in rows:
        counts[action] += 1
    return counts


def print_summary(rows: list) -> None:
    counts = summarize(rows)
    print("① 갈래별 줄 수")
    for key in ("fill", "vague", "negated", "none", "taken", "empty"):
        if key == "empty" and not counts[key]:
            continue
        print(f"   {pad(LABELS[key], 12)}{counts[key]:6}")
    print(f"   {pad('─ 합계 (라운드 칸에 값이 있는 줄)', 34)}{len(rows):6}")
    print()
    # **안 건드린 줄을 따로 찍는다.** 이 수가 보이지 않으면 "단계 말이 없는
    # 줄" 과 "있는데 일부러 비워 둔 줄" 이 한 덩어리로 보인다.
    print(f"   ※ 단계 말이 보이는데 **일부러 안 건드린** 줄: "
          f"{counts['vague'] + counts['negated']}줄 "
          f"(애매 {counts['vague']} · 뒤집힘 {counts['negated']})")
    print()


def print_rows(rows: list, limit: int, show_values: bool) -> None:
    """볼 만한 줄만 편다. **값은 안 찍는다** — `--show-values` 일 때만.

    **갈래마다 따로 센 만큼 편다.** 한 덩어리로 id 순서대로 자르면 앞쪽 갈래가
    자리를 다 먹어, 정작 눈으로 봐야 할 `뒤집힘` 이 한 줄도 안 보인다.
    """
    shown = [r for r in rows if r[1] in ("fill", "vague", "negated")]
    print(f"② 눈으로 볼 줄 {len(shown)}개"
          + ("" if show_values else " — 값은 모양(길이)으로만 찍는다"
                                   " (`--show-values` 로 값을 본다)"))
    print("   " + pad("갈래", 9) + pad("id", 6, right=True) + "  "
          + pad("라운드 값" if show_values else "라운드 길이", 46)
          + "  → stages")
    for action in ("fill", "negated", "vague"):
        mine = [r for r in shown if r[1] == action]
        for row_id, _action, found, before, after in mine[:limit or None]:
            raw = before["round_size"]
            result = after["stages"] or "(안 건드림)"
            if action == "negated" and found:
                result = f"(안 건드림 — 뒤집힌 말: {', '.join(found)})"
            print("   " + pad(LABELS[action], 9)
                  + pad(str(row_id), 6, right=True) + "  "
                  + pad((raw if show_values else shape(raw))[:46], 46)
                  + "  → " + result)
        if limit and len(mine) > limit:
            print(f"   … {LABELS[action]} {len(mine) - limit}줄 더 "
                  "(`--limit 0` 으로 전부 편다)")
    print()


def apply_plan(con: sqlite3.Connection, rows: list) -> int:
    """계획대로 적는다. **`stages` 만 적는다** — `round_size` 는 건드리지 않는다."""
    changed = 0
    for row_id, action, _found, _before, after in rows:
        if action != "fill":
            continue
        con.execute(f"UPDATE {TABLE} SET stages = ? WHERE id = ?",
                    (after["stages"], row_id))
        changed += 1
    con.commit()
    return changed


def save_baseline(path: Path, rows: list) -> int:
    """되돌리기 파일. 바뀌는 줄의 `전`·`후` 를 그대로 적는다."""
    data = [{"id": row_id, "action": action, "found": found,
             "before": before, "after": after}
            for row_id, action, found, before, after in rows if action == "fill"]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(data)


def restore(con: sqlite3.Connection, path: Path) -> int:
    """떠 둔 파일의 `before` 를 그대로 다시 적는다 — **원상 복구**."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data:
        con.execute(f"UPDATE {TABLE} SET stages = ? WHERE id = ?",
                    (item["before"]["stages"], item["id"]))
    con.commit()
    return len(data)


def check_baseline(con: sqlite3.Connection, path: Path) -> int:
    """**계획대로 바뀌었는가.** 떠 둔 `after` 와 지금 DB 를 줄마다 맞춘다.

    `round_size` 도 함께 맞춘다 — 이 스크립트가 지키기로 한 것이 "원문을 안
    건드린다" 이므로, 안 건드렸다는 것도 확인해야 한다.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [item["id"] for item in data]
    now = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        for row_id, stages, round_size in con.execute(
                f"SELECT id, stages, round_size FROM {TABLE} "
                f"WHERE id IN ({marks})", chunk):
            now[row_id] = {"stages": stages, "round_size": round_size}

    bad = [item["id"] for item in data if now.get(item["id"]) != item["after"]]
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
        description="라운드 칸에 섞인 투자 단계를 stages 로 베낀다 "
                    "(기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    # `--dry-run` 은 **기본값**이라 안 적어도 미리보기다. 그래도 받는다 —
    # 적어 두고 돌린 명령이 "안 적었으니 저장됐나" 로 읽히면 안 된다.
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 DB 에 적는다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--save-baseline", default="",
                    help="바꾸기 전 `(id, stages)` 를 이 파일로 떠 둔다")
    ap.add_argument("--baseline", default="",
                    help="떠 둔 파일과 지금 DB 를 맞춘다 (바꾼 뒤에 돌린다)")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일로 **원상 복구**한다 (`--apply` 와 함께)")
    ap.add_argument("--show-values", action="store_true",
                    help="값 자체를 찍는다. 기본은 끔 — 투자사 이야기가 섞여 있다")
    ap.add_argument("--limit", type=int, default=30,
                    help="②에 갈래마다 몇 줄까지 펼까 (0 = 전부)")
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
        print("무엇을 하나: 라운드 칸의 단계 말을 stages 로 **베낀다** "
              "(판정은 `app/services/invest_stage.decide`)")
        print("원문       : `round_size` 는 건드리지 않는다")
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
