"""명단(시트) 이름 고치기.

시트 이름이 곧 화면의 탭 이름이다. 원본에서 이름을 다듬었는데 앱에 옛 이름이
남아 있으면, 쓰던 사람이 같은 명단을 못 알아본다.

## 바꿀 이름을 **코드에 적어 두지 않는다**

예전에는 옛 이름 → 새 이름을 이 파일 안의 표에 적어 두고 `--apply` 로 돌렸다.
그 표는 한 번 돌리고 나면 **이미 지난 일**인데 파일에는 그대로 남아서, 다음에
다른 명단을 고치러 온 사람이 그 표를 고쳐야 했다 — 고치다 지우는 것을 잊으면
지난번 이름이 한 번 더 돈다. 이름은 그때그때 다르므로 **부르는 사람이 준다.**

    python scripts/rename_sheets.py --from "옛 이름" --to "새 이름"          # 미리보기
    python scripts/rename_sheets.py --from "옛 이름" --to "새 이름" --apply
    # 여러 개를 한 번에 — 적은 순서대로 짝을 짓는다
    python scripts/rename_sheets.py --from "가" --to "나" --from "다" --to "라"

## 옮기는 일은 **앱과 같은 함수**가 한다

이름은 설정 줄(`SheetOwner.label`)뿐 아니라 사람(`VcContact.source_sheet`) ·
달 칸(`ContactColumn.sheet`) · 달 표시(`MonthlyColumnRun.scope`)에도 문자열로
박혀 있다. 여기서 따로 적으면 화면의 [이름 저장]으로 바꾼 명단과 이 명령으로
바꾼 명단이 서로 다르게 갈라진다 — `app/services/sheet_owner.rename` 하나만
부른다(왜 그렇게 두는지는 그쪽 설명에 있다).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ContactColumn, MonthlyColumnRun, SheetOwner, VcContact  # noqa: E402
from app.services import sheet_owner  # noqa: E402
from app.services.monthly_columns import CONTACT  # noqa: E402


def counts(db, label: str) -> dict:
    """이 이름을 담고 있는 것이 몇이나 되는가. **바꾸기 전에** 세어 둔다.

    바꾸고 나서 세면 늘 0이라(이미 새 이름이다) 무엇이 따라갔는지 알 수 없다.
    """
    return {
        "명단": len(db.execute(select(SheetOwner)
                              .where(SheetOwner.label == label)).scalars().all()),
        "사람": sum(1 for c in db.execute(select(VcContact)).scalars()
                  if label in sheet_owner.labels_of(c.source_sheet)),
        "달 칸": len(db.execute(select(ContactColumn)
                              .where(ContactColumn.sheet == label)).scalars().all()),
        "달 표시": len(db.execute(
            select(MonthlyColumnRun).where(MonthlyColumnRun.target == CONTACT,
                                           MonthlyColumnRun.scope == label)
        ).scalars().all()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="명단(탭) 이름 고치기")
    # 짝으로 받는다. 하나의 인자에 두 이름을 구분기호로 이어 붙이면 이름 안에
    # 그 기호가 든 날 조용히 엉뚱하게 갈린다 — 시트 이름에는 괄호·슬래시·
    # 가운뎃점이 실제로 들어 있다.
    ap.add_argument("--from", dest="old", action="append", default=[],
                    help="지금 이름")
    ap.add_argument("--to", dest="new", action="append", default=[],
                    help="바꿀 이름 (--from 과 같은 순서로 짝을 짓는다)")
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args()

    if not args.old:
        print("바꿀 이름을 주세요:  --from '옛 이름' --to '새 이름'")
        return 1
    if len(args.old) != len(args.new):
        # 짝이 안 맞으면 **아무것도 하지 않는다.** 앞에서부터 짝지어 돌리면
        # 마지막 하나만 빠지는 것이 아니라 그 뒤가 통째로 밀린다.
        print(f"--from {len(args.old)}개 · --to {len(args.new)}개 — 짝이 안 맞습니다.")
        return 1

    db = SessionLocal()
    failed = False
    for before, after in zip(args.old, args.new):
        before, after = before.strip(), after.strip()
        found = counts(db, before)
        try:
            sheet_owner.rename(db, before, after)
        except sheet_owner.RenameError as exc:
            print(f"  ✗ {before!r}\n      {exc}")
            failed = True
            continue
        print(f"  {before!r}\n    → {after!r}")
        print("      " + " · ".join(f"{k} {v}" for k, v in found.items()))
        if not found["명단"]:
            # 설정 줄이 없으면 담당·배치·딜소개 표시가 딸려 있지 않다는 뜻이다.
            # 줄만 옮겨 두고 담당이 안 붙으면 그 탭은 아무의 것도 아니게 된다.
            print("      ⚠ 그 이름의 명단 설정이 없습니다 — 이름이 맞는지 확인하세요")

    if failed:
        # 하나라도 거절당하면 **아무것도 저장하지 않는다.** 절반만 바뀌면
        # 어디까지 갔는지 화면으로는 알 수 없다.
        db.rollback()
        print("\n→ 바꿀 수 없는 이름이 있어 아무것도 저장하지 않았습니다.")
        db.close()
        return 1
    if args.apply:
        db.commit()
        print("\n→ 저장했습니다.")
    else:
        db.rollback()
        print("\n→ 미리보기입니다. 실제로 넣으려면 --apply 를 붙이세요.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
