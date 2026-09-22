"""**선호로 그룹을 다시 매긴다** — 한 딜 소개 명단만, 미리보기가 기본이다.

한 명단의 그룹 칸이 `A` 69 · `B` 1 · 빈칸 46 이었는데 그 `A` 가 **무슨 뜻인지
앱 자료 어디에도 남아 있지 않았다**(A 69줄 중 선호 투자분야가 적힌 줄 3 ·
라운드 사이즈 3 · 투자 단계 0). 사용자가 정했다 — 선호 투자분야와 라운드
사이즈로 다시 묶고, **특이사항이 없는 분들은 `공통` 한 갈래로** 모은다.

    # ① 무엇이 어떻게 바뀌는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/set_group_from_pref.py --sheet "전체 딜소개현황-○○○"

    # ② 되돌릴 파일을 떠 두고 실제로 바꾼다
    python scripts/set_group_from_pref.py --sheet "전체 딜소개현황-○○○" \
        --apply --save-baseline /tmp/g.json

    # ③ 바뀐 것이 계획대로인지 맞춘다
    python scripts/set_group_from_pref.py --sheet "전체 딜소개현황-○○○" \
        --baseline /tmp/g.json

    # ④ 되돌린다 (`--sheet` 가 필요 없다 — 떠 둔 파일이 줄을 지목한다)
    python scripts/set_group_from_pref.py --restore /tmp/g.json --apply

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/clean_group_name.py` · `scripts/fill_stages_from_round.py` 가 같은
방식이고, 이 스크립트도 그 뼈대를 따른다.

## 판정은 여기 적지 않는다

`app/services/pref_group.decide()` 하나를 부른다. 규칙이 두 군데 적히면 한쪽이
낡는다 — 이 저장소가 반복해 당한 사고다. 무엇을 읽고 어떤 차례로 가르는지는
그 모듈 설명에 있다.

## **한 명단만 건드린다** — 그리고 **기본값을 두지 않는다**

`--sheet` 에 적힌 명단에 속한 줄만 본다. `source_sheet` 는 쉼표로 이어 붙으므로
**부분 일치**로 본다 — 앱이 명단을 가리는 자와 같다(`sheet_owner.labels_of` ·
`is_mine`).

**반드시 적어야 한다.** 기본값을 안 두는 이유가 둘이다. 명단 이름에는 담당자
이름이 들어 있어 **공개 저장소에 적을 수 없고**, 이 스크립트는 값을 덮으므로
어느 명단인지 손으로 적게 하는 편이 안전하다 — 기본값이 있으면 `--sheet` 를
깜빡한 명령이 조용히 남의 명단을 덮는다.

다른 담당자의 명단은 그 사람이 쓰는 갈래가 따로 있다(`E그룹` · `C그룹`).
여기서 함께 건드리면 남의 갈래가 말없이 바뀐다.

## **감춘 줄은 건드리지 않는다**

`VcContact.is_hidden` 인 줄은 화면에도 안 뜨고 딜 소개 대상도 아니다
(`sheet_owner.is_investor` 가 걸러 내고 `recipients` 가 그것을 지난다). 그룹은
**보낼 사람을 묶는 값**이라(`deal_queue.targets`) 안 보낼 줄에 매길 이유가 없다.

조용히 바꾸는 것이 더 나쁘기도 하다 — 나중에 감춤을 풀었을 때 화면에 안 보이던
사이에 값이 바뀌어 있으면 누가 언제 바꾼 것인지 알 길이 없다. 감춤을 풀고 이
스크립트를 다시 돌리면 그때 함께 매겨진다. **몇 번을 돌려도 같은 자리에 선다.**

정말로 함께 바꿔야 하면 `--include-hidden` 을 준다. 기본은 끔이고, 미리보기가
몇 줄이 그렇게 빠졌는지 늘 찍는다 — 조용히 빠지면 수가 안 맞는 이유를 모른다.

## **덮어쓴다** — 그래서 되돌릴 파일을 요구한다

이 칸에는 이미 값이 있다(`A` · `B`). 빈 칸에만 얹으면 69줄이 `A` 인 채로
남아 아무것도 안 한 것이 된다. 그러므로 `_fill_if_empty` 가 아니라 **덮어쓴다.**

덮는 일이라 `--apply` 는 `--save-baseline` 을 **요구한다**(없으면 종료코드 2).
되돌릴 파일 없이 117줄을 건드리게 두지 않는다.

**다음 시트 업로드가 되돌리지 않는다.** `sheet_import.apply_sheet_a` 는 그룹을
`_fill_if_empty` 로만 넣으므로, 값이 있는 칸은 시트가 `A` 라고 해도 안 밀어낸다.
다만 **시트와 앱이 다른 말을 하게 된다** — 시트 쪽 `그룹` 열은 사람이 손봐야 한다.

## **`딜 소개 보류` 는 이름일 뿐 발송을 막지 않는다**

갈래 중 하나가 `딜 소개 보류` 다(`pref_group.HOLD`). 그런데 **그룹 이름은 앱의
어느 발송 판정도 지나지 않는다.** 실제로 막는 값은 `VcContact.status` 의
`검토중단` 하나다(`sheet_owner.is_paused` → `can_send_to` → `recipients`).

그래서 미리보기가 **그 그룹인데 아직 `검토중단` 이 아닌 줄이 몇인지** 늘 찍는다
(②번 칸). 세어서 보여 줄 뿐 **상태를 바꾸지는 않는다** — 사용자가 시킨 것은
갈래를 세우는 데까지고, 상태를 대신 바꾸면 그 줄이 화면 목록에서 통째로 사라진다.

## 이름을 찍지 않는다

이 칸에는 투자사 이야기가 섞여 있다. 미리보기는 **id 와 값의 모양**(길이 ·
어느 갈래인지 · 읽어낸 낱말)만 찍는다. 값 자체는 `--show-values` 일 때만 본다.

## 되돌리기

바꾸기 전의 `(id, group_name)` 을 통째로 파일에 떠 둔다. `--restore` 는 그
파일의 `before` 를 그대로 다시 적는다. **떠 둔 파일에는 값이 그대로 들어
있다.** 공개 저장소에 넣지 말고 저장소 밖(`/tmp`)에 두어라.
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

#: 읽어 오는 칸. `decide()` 가 보는 것(`pref_group.PREF_FIELDS` + `memo`)에
#: 그룹과 id 를 더한 것이다.
#:
#: **`status` 는 판정이 안 쓴다.** 미리보기가 `딜 소개 보류` 로 간 줄이 실제로
#: 발송에서 빠지는지(`검토중단` 인지) 세어 보여 주려고 함께 읽는다 —
#: 아래 `print_hold` 참고.
COLUMNS = ("id", "group_name", "sectors", "round_size", "stages", "memo",
           "status")


class Row:
    """`pref_group.decide()` 에 넘길 줄 하나.

    판정은 `getattr` 로만 읽으므로 모델을 불러올 필요가 없다 — 스크립트가
    SQLAlchemy 를 띄우지 않고 sqlite3 로만 도는 것이 이 저장소의 다른 정리
    스크립트와 같은 꼴이다.
    """

    def __init__(self, values):
        for name, value in zip(COLUMNS, values):
            setattr(self, name, value)


class Item:
    """계획 한 줄. **미리보기와 저장이 이 한 벌을 같이 지난다.**

    `note` 는 예전 그룹 칸에서 옮겨 온 글이다(`pref_group.moved_text`).
    판정에는 이미 쓰였고, 여기 들고 다니는 것은 **아무것도 안 읽힌 줄을
    눈으로 보여 주려고**서다(`print_watch`).
    """

    def __init__(self, row_id, decision, before, after, note, status=None):
        self.id = row_id
        self.decision = decision
        self.before = before
        self.after = after
        self.note = note
        # 판정에는 안 쓴다 — `print_hold` 가 발송이 실제로 막히는지 볼 때만.
        self.status = status

    @property
    def changes(self) -> bool:
        """이 줄을 실제로 건드리는가 — 지금 값과 매긴 값이 다른가."""
        return ((self.before["group_name"] or "").strip()
                != self.after["group_name"])


def open_db(path: Path, write: bool) -> sqlite3.Connection:
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다."""
    if write:
        return sqlite3.connect(str(path))
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def pad(text: str, width: int, right: bool = False) -> str:
    """표의 칸을 **눈에 보이는 너비**로 맞춘다.

    `f"{text:12}"` 는 글자 수로 센다. 이 표의 말은 거의 한글이라 한 글자가 두
    칸을 먹고, 그러면 줄마다 칸이 어긋나 표를 읽을 수가 없다.
    """
    room = max(0, width - sum(
        2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text))
    return (" " * room + text) if right else (text + " " * room)


def read_rows(con: sqlite3.Connection, sheet: str, include_hidden: bool):
    """이 명단의 줄 — `(전부, 감춰서 뺀 줄 수)`.

    명단은 **부분 일치**로 가린다(`source_sheet` 가 쉼표로 이어 붙는다).
    """
    cols = ", ".join(COLUMNS)
    everything = list(con.execute(
        f"SELECT {cols}, is_hidden FROM {TABLE} "
        "WHERE source_sheet LIKE ? ORDER BY id", (f"%{sheet}%",)))
    if include_hidden:
        return [Row(r[:-1]) for r in everything], 0
    kept = [Row(r[:-1]) for r in everything if not r[-1]]
    return kept, len(everything) - len(kept)


def plan(con: sqlite3.Connection, sheet: str, include_hidden: bool):
    """줄마다 `(id, 판정, 전, 후)` 와 감춰서 뺀 줄 수. **DB 를 읽기만 한다.**

    `전`·`후` 는 되돌리기 파일에 그대로 들어간다 — 미리보기와 저장이 **같은
    계획 하나**를 지나야 미리 본 것이 실제와 같다.
    """
    from app.services import pref_group as pg

    rows, hidden = read_rows(con, sheet, include_hidden)
    out = []
    for row in rows:
        decision = pg.decide(row)
        out.append(Item(row.id, decision,
                        {"group_name": row.group_name},
                        {"group_name": decision.group},
                        pg.moved_text(row.memo), row.status))
    return out, hidden


def print_summary(rows, hidden: int, sheet: str) -> None:
    from app.services import pref_group as pg

    print(f"① 명단 `{sheet}` — 손볼 줄 {len(rows)}개"
          + (f" (감춰서 뺀 줄 {hidden}개)" if hidden else ""))
    print()

    before = Counter((it.before["group_name"] or "").strip() or "(빈값)"
                     for it in rows)
    after = Counter(it.after["group_name"] for it in rows)
    print("   그룹별 인원 — 지금 / 매긴 뒤")
    names = sorted(set(before) | set(after),
                   key=lambda n: (-after.get(n, 0), -before.get(n, 0), n))
    for name in names:
        print("     " + pad(name, 22)
              + pad(str(before.get(name, 0)), 6, right=True)
              + pad("→", 4, right=True)
              + pad(str(after.get(name, 0)), 6, right=True))
    print("     " + pad("─ 합계", 22)
          + pad(str(sum(before.values())), 6, right=True)
          + pad("→", 4, right=True)
          + pad(str(sum(after.values())), 6, right=True))
    print()

    moved = [it for it in rows if it.changes]
    print(f"   바뀌는 줄 {len(moved)}개 · 그대로 {len(rows) - len(moved)}개")
    print()

    why = Counter(it.decision.why for it in rows)
    print("   무엇을 보고 매겼나")
    for key, label in ((pg.BY_SECTOR, "선호 투자분야를 읽음"),
                       (pg.BY_ROUND, "라운드·투자단계를 읽음"),
                       (pg.BY_LABEL, "사람이 달아 둔 딱지를 그대로 읽음"),
                       (pg.BY_NONE, f"아무것도 안 읽힘 → `{pg.COMMON}`")):
        print("     " + pad(label, 34) + pad(str(why.get(key, 0)), 6, right=True))
    print()

    # `특정분야` 안을 갈래별로 센다. **이것이 안 보이면 이름을 줄 때를 모른다** —
    # 어느 갈래가 자랐는지가 덩어리 안에 숨는다(`pref_group` 설명 참고).
    small = Counter(it.decision.sector for it in rows
                    if it.after["group_name"] == pg.SMALL and it.decision.sector)
    if small:
        print(f"   `{pg.SMALL}` {sum(small.values())}명 안을 갈래별로")
        for name, count in small.most_common():
            print("     " + pad(name, 22) + pad(str(count), 6, right=True))
        print("     ※ 한 갈래가 자라면 `group_name.NAMED` 에 이름을 더하고")
        print("        `pref_group.NAMED_SECTORS` 로 옮긴다.")
        print()


def print_hold(rows) -> None:
    """**`딜 소개 보류` 로 간 줄이 정말 안 나가는가.**

    안 나간다 — 라고 말할 수 없다. 그룹 이름은 앱의 어느 판정도 지나지 않는다.
    딜 소개가 나가는 길이 둘인데 **둘 다 그룹으로 막지 않는다**:

      · 예약(`deal_queue.targets`)은 그룹으로 거르지만, 그것은 **사람이 그
        그룹을 골랐을 때만** 그 그룹으로 간다는 뜻이다. 고르지 않으면 안 가는
        것이지 코드가 막는 것이 아니다.
      · 직접 고르기(`routers/deals._load_recipients`)는 화면에서 체크한 id 만
        본다. 그룹 거르개를 안 걸고 [전체선택]을 누르면 **이 그룹도 함께
        체크된다.**

    앱에서 실제로 막는 값은 `VcContact.status` 의 `검토중단` 하나다
    (`sheet_owner.is_paused` → `can_send_to` → `recipients`). 그래서 이
    그룹으로 가는데 아직 `검토중단` 이 아닌 줄을 **세어서 보여 준다.**

    **여기서 상태를 바꾸지 않는다.** 사용자가 시킨 것은 갈래를 세우는 데까지고,
    상태를 대신 바꾸면 그 줄이 화면 목록에서 통째로 사라진다 — 사람이 보고
    정할 일이다.
    """
    from app.services import pref_group as pg

    PAUSED = "paused"       # `sheet_owner.STATUS_PAUSED` 와 같은 값
    hold = [it for it in rows if it.after["group_name"] == pg.HOLD]
    if not hold:
        return
    open_rows = [it for it in hold if (it.status or "") != PAUSED]
    print(f"② `{pg.HOLD}` {len(hold)}개 — **이름만으로는 발송이 안 막힌다**")
    print("   앱에서 막는 값은 상태 칸의 `검토중단` 하나다"
          " (`sheet_owner.is_paused` → `can_send_to`).")
    print(f"   그런데 이 {len(hold)}개 중 아직 `검토중단` 이 아닌 줄이 "
          f"**{len(open_rows)}개**다 — 지금 그대로면 딜 소개가 나간다.")
    if open_rows:
        print("   " + pad("id", 6, right=True) + "  상태")
        for it in open_rows:
            print("   " + pad(str(it.id), 6, right=True) + "  "
                  + (it.status or "(빈값)"))
    print("   ※ 상태를 바꾸는 것은 이 스크립트가 하지 않는다. 사람이 정할 일이다.")
    print()


def print_watch(rows, show_values: bool) -> None:
    """**눈으로 봐야 하는 줄** — 예전 그룹 칸에 적어 둔 글이 있는데 아무것도
    안 읽혀 `공통` 으로 가는 줄.

    사람이 무언가를 적어 두었다는 것은 **특이사항이 있다는 뜻**인데, 규칙이
    그것을 못 읽었다는 말이다. 그대로 `공통` 에 섞이면 왜 섞였는지 아무도
    모른다.

    한때 여기에 `보류` · `대형` · `지역 한정` 이 들어 있었고, 사용자가 그
    셋을 보고 **따로 갈래를 세우기로 정했다**(`pref_group.HOLD_LABELS` ·
    `AXIS_LABELS`). 이 칸이 하는 일이 바로 그것이다 — 매기지 않고 세어서
    보여 주면 사람이 보고 정한다. 조용히 섞어 두면 정할 기회 자체가 없다.

    그래서 이 칸은 **비어 가는 것이 정상**이다. 새로 뜨는 줄이 있으면 그것이
    다음에 갈래를 하나 더 세울 자리다.
    """
    from app.services import pref_group as pg

    watch = [it for it in rows
             if it.decision.why == pg.BY_NONE and it.note]
    print(f"③ 눈으로 볼 줄 {len(watch)}개 — 그룹 칸에 적어 둔 글은 있는데 "
          f"분야·라운드가 안 읽혀 `{pg.COMMON}` 으로 가는 줄")
    if not watch:
        print("   없다.")
        print()
        return
    print("   이 줄들은 **특이사항이 없는 것이 아니다.** 어떻게 할지는 사람이")
    print(f"   정할 일이라 여기서는 매기지 않고 세어서 보여 준다 — 지금 규칙은")
    print(f"   `{pg.COMMON}` 으로 보낸다.")
    print("   " + pad("id", 6, right=True) + "  "
          + ("적어 둔 글" if show_values else "적어 둔 글 길이"))
    for it in watch:
        print("   " + pad(str(it.id), 6, right=True) + "  "
              + (it.note if show_values else f"{len(it.note)}자"))
    print()


def print_rows(rows, limit: int, show_values: bool) -> None:
    """바뀌는 줄을 편다. **값은 안 찍는다** — `--show-values` 일 때만.

    **갈래마다 따로 센 만큼 편다.** 한 덩어리로 id 차례대로 자르면 큰 갈래가
    자리를 다 먹어, 정작 눈으로 봐야 할 작은 갈래가 한 줄도 안 보인다.
    """
    moved = [it for it in rows if it.changes]
    print(f"④ 바뀌는 줄 {len(moved)}개"
          + ("" if show_values else " — 읽은 글은 모양(길이)으로만 찍는다"
                                   " (`--show-values` 로 값을 본다)"))
    print("   " + pad("id", 6, right=True) + "  " + pad("지금", 14)
          + pad("→ 매긴 값", 24) + pad("근거", 8)
          + ("읽은 글" if show_values else "읽은 글 길이"))
    groups = sorted({it.after["group_name"] for it in moved})
    for group in groups:
        mine = [it for it in moved if it.after["group_name"] == group]
        for it in mine[:limit or None]:
            word = ", ".join(it.decision.found) or "-"
            print("   " + pad(str(it.id), 6, right=True) + "  "
                  + pad((it.before["group_name"] or "(빈값)"), 14)
                  + pad("→ " + it.after["group_name"], 24)
                  + pad(it.decision.why, 8)
                  + (word if show_values else f"{len(word)}자"))
        if limit and len(mine) > limit:
            print(f"   … `{group}` {len(mine) - limit}줄 더 "
                  "(`--limit 0` 으로 전부 편다)")
    print()


def apply_plan(con: sqlite3.Connection, rows) -> int:
    """계획대로 적는다. **`group_name` 만 적는다** — 다른 칸은 안 건드린다."""
    count = 0
    for it in rows:
        if not it.changes:
            continue
        con.execute(f"UPDATE {TABLE} SET group_name = ? WHERE id = ?",
                    (it.after["group_name"], it.id))
        count += 1
    con.commit()
    return count


def save_baseline(path: Path, rows) -> int:
    """되돌리기 파일. 바뀌는 줄의 `전`·`후` 를 그대로 적는다."""
    data = [{"id": it.id, "why": it.decision.why,
             "found": list(it.decision.found), "sector": it.decision.sector,
             "before": it.before, "after": it.after}
            for it in rows if it.changes]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(data)


def restore(con: sqlite3.Connection, path: Path) -> int:
    """떠 둔 파일의 `before` 를 그대로 다시 적는다 — **원상 복구**."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data:
        con.execute(f"UPDATE {TABLE} SET group_name = ? WHERE id = ?",
                    (item["before"]["group_name"], item["id"]))
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
        for row_id, group in con.execute(
                f"SELECT id, group_name FROM {TABLE} "
                f"WHERE id IN ({marks})", chunk):
            now[row_id] = {"group_name": group}

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
        description="선호 투자분야·라운드 사이즈로 그룹을 다시 매긴다 "
                    "(기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    # **기본값이 없다.** 위 설명 참고 — 깜빡한 명령이 남의 명단을 덮으면 안 되고,
    # 명단 이름에는 담당자 이름이 들어 있어 저장소에 적을 수도 없다.
    ap.add_argument("--sheet", default="",
                    help="손볼 명단 이름 (부분 일치). `--restore` 말고는 꼭 줘야 한다")
    # `--dry-run` 은 **기본값**이라 안 적어도 미리보기다. 그래도 받는다 —
    # 적어 두고 돌린 명령이 "안 적었으니 저장됐나" 로 읽히면 안 된다.
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 DB 에 적는다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--include-hidden", action="store_true",
                    help="감춘 줄도 함께 매긴다 (기본은 끔 — 안 보낼 줄이다)")
    ap.add_argument("--save-baseline", default="",
                    help="바꾸기 전 `(id, group_name)` 을 이 파일로 떠 둔다")
    ap.add_argument("--baseline", default="",
                    help="떠 둔 파일과 지금 DB 를 맞춘다 (바꾼 뒤에 돌린다)")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일로 **원상 복구**한다 (`--apply` 와 함께)")
    ap.add_argument("--show-values", action="store_true",
                    help="읽은 글을 찍는다. 기본은 끔 — 투자사 이야기가 섞여 있다")
    ap.add_argument("--limit", type=int, default=20,
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

    if not args.sheet:
        print("어느 명단을 손볼지 `--sheet` 로 적어라 "
              "(기본값을 두지 않는다 — 깜빡하면 남의 명단을 덮는다).",
              file=sys.stderr)
        return 2

    if args.apply and not args.save_baseline:
        # 되돌릴 파일 없이 덮으면 되돌릴 길이 없다. 막는다.
        print("`--apply` 에는 `--save-baseline` 이 있어야 한다 "
              "(되돌릴 파일 없이 덮지 않는다).", file=sys.stderr)
        return 2

    con = open_db(path, write=args.apply)
    try:
        rows, hidden = plan(con, args.sheet, args.include_hidden)

        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: 선호 투자분야·라운드 사이즈로 그룹을 다시 매긴다 "
              "(판정은 `app/services/pref_group.decide`)")
        print(f"어디를     : 명단 `{args.sheet}` 만"
              + ("" if args.include_hidden else " · 감춘 줄은 건드리지 않는다"))
        print("덮는가     : **덮는다** — 이 칸에는 이미 값이 있다")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()

        if not rows:
            print(f"그 명단에 해당하는 줄이 없다: `{args.sheet}`")
            return 2

        print_summary(rows, hidden, args.sheet)
        print_hold(rows)
        print_watch(rows, args.show_values)
        print_rows(rows, args.limit, args.show_values)

        if args.save_baseline:
            saved = save_baseline(Path(args.save_baseline), rows)
            print(f"되돌리기 파일을 떠 두었다: {args.save_baseline} ({saved}줄)")
            print("   ※ 값이 그대로 들어 있다. 저장소 밖에 두어라.")
            print()

        if args.apply:
            count = apply_plan(con, rows)
            print(f"DB 에 적었다: {count}줄")
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
