"""명단(탭)이 **어떤 표로 보일지**를 바꾼다.

배치는 `SheetOwner.layout` 에 값으로 들어 있다(`app/services/contact_columns.py`).
지금까지 그 값을 정하는 자리는 임포터뿐이었다 — 시트를 다시 올리지 않고는
"이 명단을 저 명단과 같은 모양으로 맞춰 달라" 를 할 수가 없었다. 그래서 배치만
바꾸는 자리를 따로 둔다. 워크북을 읽는 일과 화면을 어떻게 그릴지 정하는 일은
서로 다른 일이고, 섞어 두면 배치를 바꾸려고 시트를 다시 올리게 된다.

## 배치는 **어느 화면에 서는지도** 정한다

`Layout.page` 가 그 값이다. 스타트업 배치인 명단은 좌측 [스타트업 리마인드] 에,
투자사 배치인 명단은 [투자사 관리 현황] 에 선다. 그래서 여기서 배치를 바꾸면
**그 명단이 화면을 옮긴다** — 값을 하나 더 두지 않으려고 그렇게 했다(값이 둘이면
하나를 빠뜨린 명단이 어디에도 안 뜬다). 바꾸기 전에 어느 화면으로 가는지 적는다.

## 달마다 늘어나는 칸이 **어떻게 되는지 먼저 보여 준다**

배치를 바꾸면 그 칸이 표에서 사라지는 수가 있다(투자사 명함 표가 그렇다).
**값은 지워지지 않는다** — 값은 줄의 `notes` 에, 칸은 `ContactColumn` 줄에
따로 있고 배치는 그것을 어디에 그릴지만 정한다. 그래도 화면에서 사라지면
사람은 지워진 줄 알기 때문에, 바꾸기 전에 **몇 칸이 어디로 가는지** 적는다.

    python scripts/set_sheet_layout.py --sheet "명단 이름" --layout investor
    python scripts/set_sheet_layout.py --sheet "명단 이름" --layout investor --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ContactColumn, SheetOwner, VcContact  # noqa: E402
from app.services import contact_columns as cc  # noqa: E402
from app.services import sheet_owner  # noqa: E402


def known_sheets(db) -> set:
    """지금 **쓰고 있는** 명단 이름.

    아무 이름이나 받으면 오타 하나로 없던 명단이 생기고, 그 설정은 아무 줄도
    가리키지 않은 채 남는다. 화면의 [칸 추가] 가 같은 이유로 같은 검사를 한다
    (`routers/contacts.py` 의 `_sheet_or_400`).
    """
    names = {row.label for row in db.execute(select(SheetOwner)).scalars()}
    names |= {label for raw in db.execute(select(VcContact.source_sheet)).scalars()
              for label in sheet_owner.labels_of(raw)}
    return names


def month_report(db, sheet: str, layout: cc.Layout) -> str:
    """이 명단의 달 칸이 바뀐 배치에서 **어디에 서는지** 한 줄로.

    칸 수만 세지 않고 **값이 든 칸 수**까지 센다. 칸은 있는데 값이 없으면
    사라져도 잃을 것이 없고, 값이 있으면 그것이 그 명단의 핵심 내용이다.
    """
    columns = db.execute(
        select(ContactColumn).where(ContactColumn.sheet == sheet)
    ).scalars().all()
    if not columns:
        return "달마다 늘어나는 칸 없음"
    keys = {cc.note_key(col.id) for col in columns}
    filled = 0
    for contact in db.execute(select(VcContact)).scalars():
        if sheet not in sheet_owner.labels_of(contact.source_sheet):
            continue
        filled += sum(1 for k, v in cc.load_notes(contact.notes).items()
                      if k in keys and v)
    where = "표와 수정창" if layout.monthly else "수정창(표에는 안 섭니다)"
    return (f"달 칸 {len(columns)}개 · 값이 든 칸 {filled}개 → {where}에 섭니다"
            f" (값은 지워지지 않습니다)")


def main() -> int:
    ap = argparse.ArgumentParser(description="명단의 표 배치를 바꾼다")
    ap.add_argument("--sheet", action="append", required=True,
                    help="앱의 명단(탭) 이름. 여러 번 적을 수 있다")
    ap.add_argument("--layout", required=True, choices=sorted(cc.LAYOUTS),
                    help=" · ".join(f"{k}={v.label}" for k, v in sorted(cc.LAYOUTS.items())))
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args()

    layout = cc.LAYOUTS[args.layout]
    db = SessionLocal()
    names = known_sheets(db)

    missing = [s for s in args.sheet if s not in names]
    if missing:
        # 만들지 않고 멈춘다 — 오타로 생긴 설정은 아무 줄도 가리키지 않은 채
        # 남고, 정작 바꾸려던 명단은 그대로다.
        print("없는 명단입니다: " + ", ".join(f"`{s}`" for s in missing))
        print("지금 있는 명단:")
        for name in sorted(names):
            print(f"    {name}")
        db.close()
        return 1

    print(f"배치 `{args.layout}` ({layout.label}) 로 바꿉니다")
    changed = []
    for name in args.sheet:
        now = sheet_owner.layout_of(db, name)
        rows = sum(1 for c in db.execute(select(VcContact)).scalars()
                   if name in sheet_owner.labels_of(c.source_sheet))
        mark = "그대로" if now == args.layout else f"{now} → {args.layout}"
        print(f"  {name}  ({rows}줄)  {mark}")
        # **화면이 바뀌는 것을 먼저 말한다.** 배치를 맞추려고 돌렸는데 명단이
        # 통째로 다른 메뉴로 옮겨 가면, 찾을 자리를 모른 채 사라진 것으로 읽는다.
        was, now_page = cc.page_of(now), layout.page
        moves = "" if was == now_page else f"  ⚠ /{was} → /{now_page} 로 옮겨 갑니다"
        print(f"      화면 /{now_page}{moves}")
        print(f"      {month_report(db, name, layout)}")
        if now != args.layout:
            changed.append(name)

    if not args.apply:
        print("\n미리보기입니다. 바꾸려면 --apply 를 붙이세요.")
        db.close()
        return 0

    for name in changed:
        sheet_owner.ensure(db, name).layout = args.layout
    db.commit()
    print(f"\n바꾼 명단 {len(changed)}개")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
