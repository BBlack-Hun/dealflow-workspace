"""시트의 **선호 메모 두 칸**을 `llm_brief` 가 읽는 칸으로 옮긴다.

`심사역 리스트(공통양식)` 탭의 `기타` 와 `대화내역 메모` 는 사람이 손으로
적어 온 글인데 지금은 **시트에만 있다.** 딜 고르기(`llm_brief`)가 읽는 메모는
`memo` · `sourcing_note` · `tips_note` 셋뿐이고, 저 두 칸은 거기 안 닿는다
(`기타` 는 `notes["etc"]` 로 가거나 아예 안 읽히고, `대화내역 메모` 는 넣는
길이 하나뿐이면서 덮어쓴다). 어디로 보내고 왜인지는 `app/services/pref_notes`
모듈 설명에 적어 두었다 — **판정은 거기 하나**에 있고 여기서는 부르기만 한다.

    # ① 무엇이 어떻게 바뀌는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/import_pref_notes.py --xlsx /tmp/pref.xlsx

    # ② 되돌릴 파일을 떠 두고 실제로 바꾼다
    python scripts/import_pref_notes.py --xlsx /tmp/pref.xlsx \
        --apply --save-baseline /tmp/pref.json

    # ③ 바뀐 것이 계획대로인지 맞춘다
    python scripts/import_pref_notes.py --xlsx /tmp/pref.xlsx --baseline /tmp/pref.json

    # ④ 되돌린다
    python scripts/import_pref_notes.py --restore /tmp/pref.json --apply

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/clean_group_name.py` 의 뼈대를 그대로 따른다.

## 시트는 저장소 밖에서 받는다

이 저장소는 공개고 시트에는 실명·투자사명이 들어 있다. **`--xlsx` 로 받기만
한다** — 시트도, 시트에서 뽑은 값도 저장소에 넣지 않는다. 검사는 지어낸 값으로
만든 작은 xlsx 를 코드에서 만들어 쓴다(`tests/test_pref_notes.py`).

같은 이유로 미리보기는 **id 와 값의 모양(길이)** 만 찍는다. 값 자체는
`--show-values` 를 따로 줬을 때만 나온다(기본은 끔).

## 애매한 줄은 **건드리지 않는다**

시트 한 줄이 앱의 **여러 줄**에 맞으면 어느 쪽이 그 사람인지 여기서 못 가린다.
아무 데도 안 맞으면 붙일 자리가 없다. 둘 다 **세기만 하고 건너뛴다** — 틀리게
붙이면 남의 선호가 엉뚱한 투자사에 들어가고, 그 말을 다음 주 딜 고르기가 그대로
믿는다.

## 되돌리기

바꾸기 전의 `(id, memo, sourcing_note)` 를 통째로 파일에 떠 둔다. `--restore` 는
그 파일의 `before` 를 그대로 다시 적는다. 파일에는 바뀐 **뒤**의 값(`after`)도
함께 적어서 `--baseline` 이 "계획대로 바뀌었는가" 를 맞출 수 있다.

**떠 둔 파일에는 값이 그대로 들어 있다**(되돌리려면 그래야 한다). 저장소 밖
(`/tmp`)에 두어라.
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

# 기본 탭. 이 이름이 아닌 워크북을 받으면 `--tab` 으로 준다.
DEFAULT_TAB = "심사역 리스트(공통양식)"

# 머리글을 **찾는** 말. 줄 번호로 박지 않는다 — 지금은 2행이지만 사람이 위에
# 줄을 하나 끼워 넣으면 바로 밀린다(`sheet_import.detect_header_row` 와 같은 뜻).
HEADER_TOKENS = ("이름", "투자사명", "기타")

# 갈래마다 화면에 적는 말. `pref_notes` 가 돌려주는 값을 그대로 열쇠로 쓴다.
LABELS = {
    "add": "붙임",
    "same": "이미 있음",
    "shell": "껍데기",
    "empty": "빈 칸",
}

# 시트 줄을 앱 줄에 못 대는 두 경우. **세기만 한다.**
SKIP_MANY = "여러 줄에 맞음"
SKIP_NONE = "한 줄도 안 맞음"
SKIP_NOKEY = "이름이 없어 이을 수 없음"


def open_db(path: Path, write: bool) -> sqlite3.Connection:
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다."""
    if write:
        return sqlite3.connect(str(path))
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def shape(value) -> str:
    """값의 **모양**. 실명이 찍히면 안 되니 길이만 적는다."""
    return f"{len(value or '')}자"


def cells(text: str) -> int:
    """이 글이 화면에서 **몇 칸**을 먹나. 한글 한 자가 두 칸이다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in text)


def pad(text: str, width: int, right: bool = False) -> str:
    """표의 칸을 **눈에 보이는 너비**로 맞춘다.

    `f"{text:12}"` 는 글자 수로 센다. 이 표의 말은 거의 한글이라 한 글자가 두
    칸을 먹고, 그러면 줄마다 칸이 어긋나 표를 읽을 수가 없다.
    """
    room = max(0, width - cells(text))
    return (" " * room + text) if right else (text + " " * room)


def one_line(value: str, width: int) -> str:
    """`--show-values` 로 값을 찍을 때. 줄바꿈을 펴고 너무 길면 자른다.

    자르는 자도 **칸 수**다(글자 수가 아니다) — 글자 수로 자르면 한글이 섞인
    줄만 두 배로 길어져 옆 칸을 밀어낸다.
    """
    text = " ⏎ ".join(part.strip() for part in (value or "").splitlines()
                      if part.strip())
    if cells(text) <= width:
        return text
    out = ""
    for ch in text:
        if cells(out) + cells(ch) > width - 1:
            break
        out += ch
    return out + "…"


# ── 시트 읽기 ───────────────────────────────────────────────────────────────

def read_sheet(xlsx: Path, tab: str) -> list:
    """시트 → `[(이름, 투자사명, {칸 이름: 글})]`. **줄바꿈을 살려서** 읽는다.

    `기타` 는 두세 줄짜리가 흔하고(`6/18 전화 완료` 다음 줄에 `6/26부터 문자로
    딜 소개`), 줄바꿈을 공백으로 펴면 사람이 적어 둔 시간 순서가 뭉개진다.

    **6~27열(달마다의 딜소개·IR요청·미팅)은 읽지 않는다.** 앱이 이미
    `ContactActivity` 행으로 갖고 있어서, 가져오면 같은 이력이 메모에 또 쌓인다.
    """
    from app.services import pref_notes, sheet_import, spreadsheet

    rows = spreadsheet.read_rows(xlsx.name, xlsx.read_bytes(), tab)
    head = sheet_import.detect_header_row(rows, HEADER_TOKENS)
    if head is None:
        raise SystemExit(
            f"`{tab}` 에서 머리글을 못 찾았다 ({' · '.join(HEADER_TOKENS)} 가 "
            "한 줄에 다 있어야 한다).")
    header = [sheet_import.norm(c) for c in rows[head]]

    where = {}
    at_name = sheet_import.find_column(header, ["이름"])
    at_firm = sheet_import.find_column(header, ["투자사명"])
    for source in pref_notes.SOURCES:
        # **완전히 일치**할 때만 건다. `기타` 는 두 글자뿐이라 포함으로 찾으면
        # 다른 머리글에 걸리고, `메모` 로 넓게 찾으면 `대화내역 메모` 말고 다른
        # 메모 칸이 있는 워크북에서 엉뚱한 열을 읽는다.
        found = next((i for i, h in enumerate(header) if h == source.label), None)
        if found is None:
            raise SystemExit(f"`{tab}` 에 `{source.label}` 칸이 없다.")
        where[source.label] = found
    if at_name is None:
        raise SystemExit(f"`{tab}` 에 `이름` 칸이 없다.")

    out = []
    for row in rows[head + 1:]:
        name = sheet_import.norm(sheet_import._cell(row, at_name))
        firm = sheet_import.norm(sheet_import._cell(row, at_firm))
        texts = {label: sheet_import._raw_cell(row, i)
                 for label, i in where.items()}
        if not name and not any(texts.values()):
            continue
        out.append((name, firm, texts))
    return out


# ── 앱 줄 찾기 ─────────────────────────────────────────────────────────────

def match_index(con: sqlite3.Connection) -> dict:
    """`(투자사명, 이름)` → `[id…]`. **여러 개면 여러 개인 채로 둔다.**

    여기서 하나를 고르면(먼저 만든 줄 · id 가 작은 줄) 그 고르는 규칙이 코드
    어디에도 근거가 없는 채로 남의 선호를 옮겨 붙인다. 고르지 않고 세어서
    알리고, 사람이 시트를 고친 뒤 다시 돌리는 자리다.
    """
    from app.services import pref_notes

    index: dict = {}
    for row_id, name, firm in con.execute(
            f"SELECT id, name, firm FROM {TABLE} ORDER BY id"):
        key = pref_notes.match_key(name, firm)
        if key is not None:
            index.setdefault(key, []).append(row_id)
    return index


def current_values(con: sqlite3.Connection) -> dict:
    """`id` → `{칸: 지금 값}`. 손대는 칸만 읽는다."""
    from app.services import pref_notes

    cols = ", ".join(pref_notes.FIELDS)
    return {row[0]: dict(zip(pref_notes.FIELDS, row[1:]))
            for row in con.execute(f"SELECT id, {cols} FROM {TABLE}")}


def plan(con: sqlite3.Connection, sheet: list) -> tuple:
    """`(줄 계획, 갈래별 수)`. **DB 를 읽기만 한다.**

    미리보기와 저장이 **같은 계획 하나**를 지나야 미리 본 것이 실제와 같다
    (`clean_group_name.plan` 이 같은 이유로 정하는 일과 얹는 일을 나누었다).

    줄 계획은 **앱 줄 하나당 하나**다(`id`, `{칸: 갈래}`, `before`, `after`).
    시트 한 줄이 두 칸을 함께 나르므로, 칸마다 따로 적으면 같은 id 가 두 번
    나와 되돌리기 파일에서 뒤엣것이 앞엣것의 `before` 를 덮는다.
    """
    from app.services import pref_notes

    index = match_index(con)
    now = current_values(con)
    counts: Counter = Counter()
    by_id: dict = {}
    order: list = []

    for name, firm, texts in sheet:
        key = pref_notes.match_key(name, firm)
        hits = index.get(key, []) if key is not None else []
        if key is None:
            counts[SKIP_NOKEY] += 1
            continue
        if not hits:
            counts[SKIP_NONE] += 1
            continue
        if len(hits) > 1:
            # **건드리지 않는다.** 위 `match_index` 설명 참고.
            counts[SKIP_MANY] += 1
            continue
        row_id = hits[0]
        counts["맞은 시트 줄"] += 1
        if row_id not in by_id:
            before = {f: now[row_id][f] for f in pref_notes.FIELDS}
            by_id[row_id] = {"actions": {}, "before": before,
                             "after": dict(before)}
            order.append(row_id)
        entry = by_id[row_id]
        for source in pref_notes.SOURCES:
            decision = pref_notes.decide(texts.get(source.label),
                                         entry["after"][source.field],
                                         source.mark)
            counts[f"{source.label}:{decision.action}"] += 1
            entry["actions"][source.label] = decision.action
            if decision.changes:
                entry["after"][source.field] = decision.value

    rows = [(row_id, by_id[row_id]["actions"], by_id[row_id]["before"],
             by_id[row_id]["after"]) for row_id in order]
    counts["맞은 앱 줄"] = len(rows)
    counts["바뀌는 줄"] = sum(1 for r in rows if r[2] != r[3])
    return rows, counts


# ── 화면 ───────────────────────────────────────────────────────────────────

def print_summary(sheet: list, counts: Counter) -> None:
    from app.services import pref_notes

    print("① 시트 줄을 앱 줄에 대 본 결과 — 열쇠는 **투자사명 + 이름**")
    lines = [
        ("읽은 시트 줄", len(sheet)),
        ("  정확히 한 줄에 맞음", counts["맞은 시트 줄"]),
        (f"  {SKIP_MANY} (건드리지 않음)", counts[SKIP_MANY]),
        (f"  {SKIP_NONE} (건드리지 않음)", counts[SKIP_NONE]),
        (f"  {SKIP_NOKEY}", counts[SKIP_NOKEY]),
    ]
    for label, count in lines:
        print(f"   {pad(label, 34)}{count:6}")
    doubled = counts["맞은 시트 줄"] - counts["맞은 앱 줄"]
    if doubled:
        # 시트에 같은 사람이 두 줄로 적혀 있는 경우다. 앱 줄 하나에 두 줄이
        # 차례로 얹히고, 두 번째 줄의 같은 말은 `이미 있음` 으로 걸러진다.
        print(f"   {pad('  ↳ 앱 줄로는', 34)}{counts['맞은 앱 줄']:6}"
              f"   (시트에 같은 사람이 {doubled}줄 겹쳐 적혀 있다)")
    print()

    print("② 칸마다 몇 줄을 가져오나 (맞은 줄 안에서)")
    print("   " + pad("시트 칸", 16) + pad("→ 앱 칸", 16)
          + "".join(pad(LABELS[a], 11, right=True)
                    for a in ("add", "same", "shell", "empty")))
    for source in pref_notes.SOURCES:
        print("   " + pad(source.label, 16) + pad(f"→ {source.field}", 16)
              + "".join(pad(str(counts[f"{source.label}:{a}"]), 11, right=True)
                        for a in ("add", "same", "shell", "empty")))
    print(f"   {pad('─ 실제로 바뀌는 줄', 32)}{counts['바뀌는 줄']:6}")
    print()


def print_rows(rows: list, limit: int, show_values: bool) -> None:
    """바뀌는 줄만 편다. **값은 안 찍는다** — `--show-values` 일 때만."""
    from app.services import pref_notes

    changing = [r for r in rows if r[2] != r[3]]
    print(f"③ 바뀌는 줄 {len(changing)}개"
          + ("" if show_values else " — 값은 모양(길이)으로만 찍는다"
                                   " (`--show-values` 로 값을 본다)"))
    print("   " + pad("id", 7, right=True) + "  "
          + "".join(pad(f"{s.label} → {s.field}", 34) for s in pref_notes.SOURCES))
    for row_id, actions, before, after in changing[:limit or None]:
        drawn = []
        for source in pref_notes.SOURCES:
            action = actions.get(source.label, "empty")
            was, now = before[source.field], after[source.field]
            if action != "add":
                drawn.append(pad(LABELS[action], 34))
            elif show_values:
                # **붙인 글만** 보여 준다. 앞의 글은 안 건드렸으니 다시 찍을
                # 것이 없고, 표시(`mark`)는 줄마다 같아서 자리만 먹는다.
                added = now[len(was or ""):].lstrip("\n")
                if added.startswith(source.mark):
                    added = added[len(source.mark):].lstrip()
                drawn.append(pad(one_line(added, 32), 34))
            else:
                drawn.append(pad(f"{shape(was)} → {shape(now)} "
                                 f"(+{len(now) - len(was or '')}자)", 34))
        print("   " + pad(str(row_id), 7, right=True) + "  " + "".join(drawn))
    if limit and len(changing) > limit:
        print(f"   … {len(changing) - limit}줄 더 (`--limit 0` 으로 전부 편다)")
    print()


# ── 쓰기 · 되돌리기 ────────────────────────────────────────────────────────

def apply_plan(con: sqlite3.Connection, rows: list) -> int:
    """계획대로 적는다. **바뀌는 줄만** 건드린다."""
    from app.services import pref_notes

    sets = ", ".join(f"{f} = ?" for f in pref_notes.FIELDS)
    changed = 0
    for row_id, _actions, before, after in rows:
        if before == after:
            continue
        con.execute(f"UPDATE {TABLE} SET {sets} WHERE id = ?",
                    [after[f] for f in pref_notes.FIELDS] + [row_id])
        changed += 1
    con.commit()
    return changed


def save_baseline(path: Path, rows: list) -> int:
    """되돌리기 파일. **바뀌는 줄**의 `전`·`후` 를 그대로 적는다."""
    data = [{"id": row_id, "actions": actions,
             "before": before, "after": after}
            for row_id, actions, before, after in rows if before != after]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(data)


def restore(con: sqlite3.Connection, path: Path) -> int:
    """떠 둔 파일의 `before` 를 그대로 다시 적는다 — **원상 복구**."""
    from app.services import pref_notes

    sets = ", ".join(f"{f} = ?" for f in pref_notes.FIELDS)
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data:
        con.execute(f"UPDATE {TABLE} SET {sets} WHERE id = ?",
                    [item["before"][f] for f in pref_notes.FIELDS] + [item["id"]])
    con.commit()
    return len(data)


def check_baseline(con: sqlite3.Connection, path: Path) -> int:
    """**계획대로 바뀌었는가.** 떠 둔 `after` 와 지금 DB 를 줄마다 맞춘다."""
    from app.services import pref_notes

    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [item["id"] for item in data]
    cols = ", ".join(pref_notes.FIELDS)
    now = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        for row in con.execute(
                f"SELECT id, {cols} FROM {TABLE} WHERE id IN ({marks})", chunk):
            now[row[0]] = dict(zip(pref_notes.FIELDS, row[1:]))

    bad = [item["id"] for item in data if now.get(item["id"]) != item["after"]]
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
        description="시트의 `기타`·`대화내역 메모` 를 투자사 줄의 메모 칸으로 "
                    "옮긴다 (기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--xlsx", default="",
                    help="시트 파일 (**저장소 밖에서 받는다** — 커밋하지 않는다)")
    ap.add_argument("--tab", default=DEFAULT_TAB, help="워크북 안의 탭 이름")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    # `--dry-run` 은 **기본값**이라 안 적어도 미리보기다. 그래도 받는다 —
    # 적어 두고 돌린 명령이 "안 적었으니 저장됐나" 로 읽히면 안 된다.
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 DB 에 적는다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--save-baseline", default="",
                    help="바꾸기 전 `(id, memo, sourcing_note)` 를 이 파일로 떠 둔다")
    ap.add_argument("--baseline", default="",
                    help="떠 둔 파일과 지금 DB 를 맞춘다 (바꾼 뒤에 돌린다)")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일로 **원상 복구**한다 (`--apply` 와 함께)")
    ap.add_argument("--show-values", action="store_true",
                    help="값 자체를 찍는다. 기본은 끔 — 실명이 섞여 있다")
    ap.add_argument("--limit", type=int, default=30,
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

    if not args.xlsx:
        print("`--xlsx` 로 시트 파일을 줘라 (저장소에는 없다).", file=sys.stderr)
        return 2
    xlsx = Path(args.xlsx)
    if not xlsx.exists():
        print(f"그런 시트가 없다: {xlsx}", file=sys.stderr)
        return 2

    from app.services import pref_notes

    sheet = read_sheet(xlsx, args.tab)
    con = open_db(path, write=args.apply)
    try:
        rows, counts = plan(con, sheet)

        print(f"시트      : {xlsx}  [{args.tab}]")
        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: " + " · ".join(
            f"`{s.label}` → `{s.field}`" for s in pref_notes.SOURCES)
            + "  (덮지 않고 줄바꿈으로 잇는다)")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()

        print_summary(sheet, counts)
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
