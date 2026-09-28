"""**이미 있는 팀원의 빠진 개인 탭을 채운다** — 미리보기가 기본이다.

계정을 만드는 세 자리는 이제 탭을 함께 세운다(`sheet_owner.ensure_member_tabs`).
그런데 **그 전에 만들어진 계정**에는 탭이 없다. 운영에는 탭이 하나도 없는
계정이 있고, 한쪽 화면의 탭만 있는 계정도 있다. 그 계정으로 로그인하면 투자사
관리 현황·스타트업이 빈 화면이고 줄을 넣을 자리조차 없다(`may_add_row` 는
명단이 있어야 판정한다).

    # ① 누구에게 어떤 탭이 서는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/fill_member_tabs.py

    # ② 되돌릴 파일을 떠 두고 실제로 만든다
    python scripts/fill_member_tabs.py --apply --save-baseline /tmp/tabs.json

    # ③ 계획대로 섰는지 맞춘다
    python scripts/fill_member_tabs.py --baseline /tmp/tabs.json

    # ④ 되돌린다 (`--member` 가 필요 없다 — 떠 둔 파일이 줄을 지목한다)
    python scripts/fill_member_tabs.py --restore /tmp/tabs.json --apply

    # 한 사람만
    python scripts/fill_member_tabs.py --member 10

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/set_group_from_pref.py` 와 같은 뼈대다.

## 판정은 여기 적지 않는다

누구에게 어떤 탭이 필요한지도, 그 탭을 무엇이라 부를지도
`app/services/sheet_owner.py` 하나가 정한다(`missing_member_tabs`). 계정을
만드는 세 자리와 **같은 계획 하나**를 지난다 — 규칙이 두 군데 적히면 한쪽이
낡는다. 그래서 이 스크립트는 sqlite3 가 아니라 앱의 세션으로 돈다.

무엇을 읽고 어떻게 가르는지는 그 모듈의 「팀원 한 사람의 **개인 탭**」 절에
있다. 요약하면 이렇다.

  · 탭을 세울 화면은 **그 화면을 열 수 있는 계정인가**로 정한다
    (`deps.can_open`). 투자컨설턴트에게는 `/contacts`·`/startup` 이 닫혀 있어
    (`deps.CONSULTANT_PATHS`) 탭을 만들지 않는다 — 만들면 아무도 못 보는 탭이다.
  · **이미 그 화면의 탭을 가진 사람은 넘어간다.** 이름이 아니라 화면으로 센다.
  · 투자사 탭은 숨기지 않고, 스타트업 탭은 숨긴다(`is_hidden`). 거꾸로 달면
    딜 소개 발송 대상이 어긋난다.

## **이미 있는 탭은 건드리지 않는다**

만드는 것만 한다. 이름을 고치지도, 배치를 옮기지도, 담당을 덮지도 않는다
(`sheet_owner.ensure` 가 할당을 안 덮는 그 성질을 그대로 쓴다). 쓰고 있는 명단에
손을 대면 그 명단의 줄·달 칸·달 표시가 함께 어긋날 수 있다 — 이름이 곧 열쇠라
네 곳에 문자열로 박혀 있다(`sheet_owner.py` 의 「명단 이름 바꾸기」).

## 이름을 찍지 않는다

팀원 이름이 탭 이름에 들어간다. 미리보기는 **계정 번호 · 권한 · 화면 · 배치**만
찍는다. 탭 이름은 `--show-values` 일 때만 본다 — 공개 저장소에 붙일 기록에
사람 이름이 실리지 않게.

## 되돌리기

만든 탭의 `(label, layout, is_hidden, user_id)` 를 파일에 떠 둔다. `--restore`
는 **그 파일에 적힌 탭만** 지운다. 그때까지 그 탭에 줄이 하나라도 붙었으면
(`source_sheet` 에 이름이 올랐으면) **지우지 않고 넘어간다** — 지우면 그 줄이
어느 탭에도 안 뜨는 유령이 된다. 떠 둔 파일에는 이름이 그대로 들어 있으니
저장소 밖(`/tmp`)에 두어라.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import config  # noqa: E402
from app.models import SheetOwner, User, VcContact  # noqa: E402
from app.services import sheet_owner  # noqa: E402


def open_session(path: Path, write: bool):
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다.

    `app.db.SessionLocal` 을 쓰지 않는다. 그쪽은 붙을 때마다
    `PRAGMA journal_mode=WAL` 을 적는데, 그것이 **쓰기**라 읽기 전용으로 연 파일
    에서는 그 자리에서 터진다 — 미리보기가 못 도는 것이 아니라 이유가 엉뚱한
    곳에서 난다.
    """
    if write:
        url = f"sqlite:///{path}"
    else:
        url = f"sqlite:///file:{path}?mode=ro&uri=true"
    engine = create_engine(url, future=True,
                           connect_args={"check_same_thread": False})
    return sessionmaker(bind=engine, autoflush=False, future=True)()


def pad(text: str, width: int, right: bool = False) -> str:
    """표의 칸을 **눈에 보이는 너비**로 맞춘다(한글 한 글자가 두 칸을 먹는다)."""
    room = max(0, width - sum(
        2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text))
    return (" " * room + text) if right else (text + " " * room)


def plan(db, member_id: int):
    """계정마다 `(계정, 세울 탭 계획)`. **DB 를 읽기만 한다.**

    계획은 `sheet_owner.missing_member_tabs` 하나가 만든다 — 계정을 만드는 세
    자리가 지나는 그 판정이다. 미리 본 것과 실제로 서는 것이 갈릴 자리가 없다.
    """
    stmt = select(User).order_by(User.id)
    if member_id:
        stmt = stmt.where(User.id == member_id)
    out = []
    for user in db.execute(stmt).scalars().all():
        out.append((user, sheet_owner.missing_member_tabs(db, user)))
    return out


def print_plan(db, rows, show_values: bool) -> None:
    made = [(u, tabs) for u, tabs in rows if tabs]
    total = sum(len(tabs) for _u, tabs in made)
    print(f"① 계정 {len(rows)}개 — 탭을 세울 계정 {len(made)}개 · 세울 탭 {total}개")
    print()
    print("   " + pad("계정", 6, right=True) + "  " + pad("권한", 12)
          + pad("지금 가진 화면", 22) + pad("세울 탭", 30))
    for user, tabs in rows:
        have = ", ".join(sorted(sheet_owner.owned_pages(db, user))) or "-"
        if show_values:
            new = ", ".join(t["label"] for t in tabs) or "-"
        else:
            new = ", ".join(f'{t["page"]}({t["layout"]}'
                            + (", 숨김" if t["is_hidden"] else "") + ")"
                            for t in tabs) or "-"
        print("   " + pad(str(user.id), 6, right=True) + "  "
              + pad(user.role, 12) + pad(have, 22) + pad(new, 30))
    print()
    # 이름을 못 지어 빠진 탭. **빼 버리면 왜 안 만들어졌는지 알 수 없다.**
    stuck = [(u, t) for u, tabs in rows for t in tabs if not t["label"]]
    if stuck:
        print(f"   ⚠ 이름을 못 지어 못 만드는 탭 {len(stuck)}개 — 그 이름을 이미")
        print("     쓰는 명단이 있다. 그 명단의 이름을 화면에서 먼저 고쳐라.")
        for user, tab in stuck:
            print("     " + pad(str(user.id), 6, right=True) + "  " + tab["page"])
        print()


def print_why(rows) -> None:
    """**탭을 안 세우는 계정이 왜 그런지** 적는다. 조용히 빠지면 이유를 모른다."""
    skipped = [u for u, tabs in rows if not tabs]
    if not skipped:
        return
    print(f"② 탭을 안 세우는 계정 {len(skipped)}개 — 이유")
    for user in skipped:
        specs = sheet_owner.tab_specs(user)
        if not specs:
            why = ("그 권한으로는 투자사 관리 현황·스타트업을 못 연다"
                   " (`deps.CONSULTANT_PATHS`) — 탭을 만들면 아무도 못 본다")
        else:
            why = "두 화면의 탭을 이미 갖고 있다"
        print("   " + pad(str(user.id), 6, right=True) + "  "
              + pad(user.role, 12) + why)
    print()


def print_send_check(db) -> None:
    """**새 탭이 딜 소개 발송 대상을 흔드는가.** 세어서 보여 준다.

    흔들지 않는다 — 새 탭에는 줄이 하나도 없고, 발송 대상은 **줄**로 센다
    (`recipients` → `deal_list_contacts` → `managed`). 그래도 세어서 보여
    준다: 이 저장소가 반복해 당한 사고가 "수가 조용히 달라지는 것" 이라,
    미리보기가 전후를 같은 자리에서 찍어 두면 나중에 견줄 수 있다.
    """
    hidden = sheet_owner.hidden_labels(db)
    off = sheet_owner.off_deal_labels(db)
    rows = db.execute(select(VcContact)).scalars().all()
    counted = [c for c in rows if sheet_owner.is_investor(c, hidden)]
    on_list = [c for c in counted if sheet_owner.on_deal_list(c, off)]
    ready = [c for c in on_list if sheet_owner.can_send_to(c)]
    print("③ 지금 수 — 새 탭에는 줄이 하나도 없으니 이 수는 안 움직인다")
    print(f"   전체 줄 {len(rows)}개 · 투자사로 세는 줄 {len(counted)}개"
          f" · 딜 소개 명단 {len(on_list)}개 · 지금 보낼 수 있는 줄 {len(ready)}개")
    print("   (`is_investor` → `on_deal_list` → `can_send_to`. 새 탭은"
          " 스타트업만 숨김이고, 숨김은 그 명단에 이름이 오른 줄에만 먹는다.)")
    print()


def apply_plan(db, rows) -> list:
    """계획대로 만든다. **`ensure_member_tabs` 하나만 부른다.**"""
    made = []
    for user, tabs in rows:
        if not tabs:
            continue
        for row in sheet_owner.ensure_member_tabs(db, user):
            made.append({"id": row.id, "label": row.label,
                         "layout": row.layout, "is_hidden": row.is_hidden,
                         "user_id": row.user_id})
    db.commit()
    return made


def save_baseline(path: Path, made: list) -> int:
    """되돌리기 파일 — **새로 만든 탭만** 적는다(그 밖에는 손댄 것이 없다)."""
    path.write_text(json.dumps(made, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(made)


def restore(db, path: Path) -> tuple:
    """떠 둔 파일에 적힌 탭을 지운다 — `(지운 수, 줄이 붙어 못 지운 수)`.

    **줄이 붙은 탭은 안 지운다.** 그 이름이 `VcContact.source_sheet` 에 올랐으면
    지우는 순간 그 줄이 어느 탭에도 안 뜬다(이름이 곧 열쇠다). 되돌리기가
    자료를 잃는 일이 되면 안 된다.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    gone = kept = 0
    for item in data:
        row = db.execute(
            select(SheetOwner).where(SheetOwner.label == item["label"])
        ).scalars().first()
        if row is None:
            continue
        used = any(item["label"] in sheet_owner.labels_of(c.source_sheet)
                   for c in db.execute(select(VcContact)).scalars())
        if used:
            kept += 1
            continue
        db.delete(row)
        gone += 1
    db.commit()
    return gone, kept


def check_baseline(db, path: Path) -> int:
    """**계획대로 섰는가.** 떠 둔 것과 지금 DB 를 탭마다 맞춘다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    bad = []
    for item in data:
        row = db.execute(
            select(SheetOwner).where(SheetOwner.label == item["label"])
        ).scalars().first()
        if row is None or (row.user_id, row.layout, bool(row.is_hidden)) != (
                item["user_id"], item["layout"], bool(item["is_hidden"])):
            bad.append(item["label"])
    print(f"④ 기준과 맞추기 — 떠 둔 탭 {len(data)}개")
    print(f"   계획대로 {len(data) - len(bad)}개 · 어긋남 {len(bad)}개")
    if bad:
        print(f"   어긋난 탭 {len(bad)}개 (이름은 찍지 않는다 —"
              " `--show-values` 로 본다)")
    print()
    return len(bad)


def default_db() -> Path:
    url = config.DATABASE_URL
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return Path(__file__).resolve().parent.parent / "data" / "dealflow.db"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="이미 있는 팀원의 빠진 개인 탭을 채운다 "
                    "(기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    ap.add_argument("--member", type=int, default=0,
                    help="이 계정 번호만 (기본: 모든 계정)")
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 DB 에 만든다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--save-baseline", default="",
                    help="새로 만든 탭을 이 파일로 떠 둔다")
    ap.add_argument("--baseline", default="",
                    help="떠 둔 파일과 지금 DB 를 맞춘다 (만든 뒤에 돌린다)")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일의 탭을 지운다 (`--apply` 와 함께)")
    ap.add_argument("--show-values", action="store_true",
                    help="탭 이름을 찍는다. 기본은 끔 — 사람 이름이 들어 있다")
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
        db = open_session(path, write=True)
        try:
            gone, kept = restore(db, Path(args.restore))
        finally:
            db.close()
        print(f"되돌렸다: 지운 탭 {gone}개 ← {args.restore}")
        if kept:
            print(f"   줄이 붙어 안 지운 탭 {kept}개 — 지우면 그 줄이 어느 탭에도"
                  " 안 뜬다. 화면에서 보고 정해라.")
        return 0

    if args.apply and not args.save_baseline:
        print("`--apply` 에는 `--save-baseline` 이 있어야 한다 "
              "(되돌릴 파일 없이 만들지 않는다).", file=sys.stderr)
        return 2

    db = open_session(path, write=args.apply)
    try:
        rows = plan(db, args.member)

        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: 이미 있는 팀원의 빠진 개인 탭을 만든다 "
              "(판정은 `app/services/sheet_owner.missing_member_tabs`)")
        print("어디를     : " + (f"계정 {args.member} 만" if args.member
                                else "모든 계정"))
        print("덮는가     : **안 덮는다** — 만드는 것만 한다. 이미 있는 탭은"
              " 이름·배치·담당 어느 것도 건드리지 않는다")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()

        if not rows:
            print(f"그런 계정이 없다: {args.member}")
            return 2

        print_plan(db, rows, args.show_values)
        print_why(rows)
        print_send_check(db)

        if args.apply:
            made = apply_plan(db, rows)
            print(f"DB 에 만들었다: 탭 {len(made)}개")
            if args.save_baseline:
                saved = save_baseline(Path(args.save_baseline), made)
                print(f"되돌리기 파일을 떠 두었다: {args.save_baseline}"
                      f" ({saved}개)")
                print("   ※ 탭 이름이 그대로 들어 있다. 저장소 밖에 두어라.")
                print(f"   되돌리려면: python {Path(__file__).name} "
                      f"--restore {args.save_baseline} --apply")
            print()

        if args.baseline:
            return 1 if check_baseline(db, Path(args.baseline)) else 0
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
