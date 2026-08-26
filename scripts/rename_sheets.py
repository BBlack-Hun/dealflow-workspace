"""명단(시트) 이름 고치기.

시트 이름이 곧 화면의 탭 이름이다. 원본에서 이름을 다듬었는데 앱에 옛 이름이
남아 있으면, 쓰던 사람이 같은 명단을 못 알아본다.

`source_sheet` 는 쉼표로 이어 붙인 목록이라(한 사람이 여러 명단에 겹친다)
통째로 바꾸지 않고 **조각 단위**로 바꾼다.

    python scripts/rename_sheets.py                 # 미리보기
    python scripts/rename_sheets.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import SheetOwner, VcContact  # noqa: E402

# 옛 이름 → 원본 시트의 지금 이름.
#
# **원본이 정답이다.** 앱에서 이름을 다듬어 두면 시트를 쓰던 사람이 같은
# 명단을 못 알아본다 — 시트에는 `150(71명연결)` 인데 앱에는 `투자사 150(71명
# 연결)` 이면 눈으로 대조할 때마다 한 번씩 멈춘다.
# 기준은 `1MB_CGU…` 워크북이다. 같은 자료의 사본이 여럿 도는데 사본마다
# 탭 이름이 조금씩 다르다(`150(71명연결)` vs `투자사 150(71명 연결)`).
# **기준을 하나로 정해 두지 않으면** 사본을 볼 때마다 이름이 뒤집힌다.
RENAMES = {
    # 담당자 이름이 붙어 있었다 — 원본은 사람 이름 없이 전체 현황이다.
    "김정훈 딜소개현황": "전체 딜소개현황(128명)",
}


def main() -> None:
    ap = argparse.ArgumentParser(description="명단 이름 고치기")
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args()

    db = SessionLocal()
    touched = 0

    for contact in db.execute(select(VcContact)).scalars().all():
        parts = [p.strip() for p in (contact.source_sheet or "").split(",") if p.strip()]
        renamed = [RENAMES.get(p, p) for p in parts]
        if renamed != parts:
            contact.source_sheet = ",".join(renamed)
            touched += 1

    sheets = 0
    for owner in db.execute(select(SheetOwner)).scalars().all():
        if owner.label in RENAMES:
            owner.label = RENAMES[owner.label]
            sheets += 1

    for old, new in RENAMES.items():
        print(f"  {old!r}\n    → {new!r}")
    print(f"\n담당자 {touched}명 · 명단 {sheets}개")

    if args.apply:
        db.commit()
        print("→ 저장했습니다.")
    else:
        db.rollback()
        print("→ 미리보기입니다. 실제로 넣으려면 --apply 를 붙이세요.")
    db.close()


if __name__ == "__main__":
    main()
