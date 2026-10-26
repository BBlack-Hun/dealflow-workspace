"""**이미 있는 Series A 이상 딜 소싱 줄을 IR 기업에 잇는다** — 미리보기가 기본이다.

기업 동기화 3단계(10/26). 새 줄 · 기업명을 고친 줄 · IR 에 새로 생기거나 이름이 바뀐
기업은 저장할 때 저절로 이어진다(`services/company_sync.py` 머리말 규칙 6). 그 전에
들어와 있던 줄은 이 스크립트가 **한 번** 잇는다 — `/ir-link` Series A 탭의 [후보가 하나인
줄 일괄 연결]과 같은 함수다(`routers/ir_link.bulk_pairs` → `services/ir_link.link(auto=True)`).
잇는 순간 양쪽 빈칸 채우기는 flush 가 한다(`company_sync.before_flush`).

    # ① 미리보기 (기본) — DB 를 읽기 전용으로 열어 **메모리에** 복사본을 뜨고 거기서 돌린다
    python scripts/series_a_ir_link.py

    # ② 실제로 저장 — 운영 반영 뒤 백업을 뜨고 한 번. 수정 로그에 남을 계정을 꼭 준다
    python scripts/series_a_ir_link.py --apply --user-id N

· 이름이 정확히 하나 맞는 줄만 잇는다. 후보가 여럿 · 없는 줄은 `/ir-link` 에서 사람이 고른다.
· 양쪽에 다른 값이 있으면 덮지 않는다 — `/ir-link` 의 `값 다름` 에 남는다(결정 5).

이름 · 번호를 찍지 않는다(공개 저장소 · 실명) — 칸 · 수만 찍는다.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.link_sourcing_rows import memory_copy  # noqa: E402 — 같은 미리보기 방식


def run(db) -> Counter:
    """잇고 센다 — `{single: 이을 줄, done: 이은 줄, linked: 이미 이어진 줄, multi, none,
    'sa:칸' / 'ir:칸': 잇는 순간 채운 빈칸 수, 'left:칸': 남은 값 다름}`. 커밋은 부르는 쪽."""
    from sqlalchemy import select

    from app.models import IrCompany, SeriesACompany
    from app.routers.ir_link import bulk_pairs
    from app.services import company_sync as cs
    from app.services import ir_link

    idx = ir_link.index(db)
    counts: Counter = Counter(ir_link.state(idx, r)
                              for r in db.execute(select(SeriesACompany)).scalars())
    # Series A 탭은 팀 공용이라 계정을 안 읽는다(`routers/ir_link.rows_for`).
    pairs = bulk_pairs(db, None, ir_link.SERIES_A, idx)
    kinds = cs.sheet_kinds(db)
    # 잇기 전 값 — 빈칸 채우기가 몇 칸을 채웠나 센다(한 IR 에 여러 줄이 붙어도 IR 은 한 번).
    before = {}
    for row, company in pairs:
        for field, where in cs._places(row, kinds).items():
            before[(row, where, field)] = cs._value(row, where, field)
            before.setdefault((company, field, field), cs._value(company, field, field))
    for row, company in pairs:
        counts["done"] += ir_link.link(db, row, company, auto=True)
    db.flush()
    for (obj, where, field), was in before.items():
        side = "ir" if isinstance(obj, IrCompany) else "sa"
        counts[f"{side}:{field}"] += cs._value(obj, where, field) != was
    for diffs in cs.differences(db, [r for r, _c in pairs]).values():
        for d in diffs:
            counts["left:" + d["field"]] += 1
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Series A 이상 딜 소싱 줄 → IR 기업 잇기(이름이 하나 맞는 줄)")
    ap.add_argument("--user-id", type=int, default=None, help="수정 로그에 남을 계정(--apply 때 꼭)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="미리보기(기본)")
    mode.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args(argv)

    from app import config
    from app.models import User
    from app.services import company_sync as cs
    from app.services import edit_log

    if args.apply and args.user_id is None:
        print("--apply 에는 --user-id 가 있어야 합니다(수정 로그에 남을 계정).", file=sys.stderr)
        return 2
    if args.apply:
        from app.db import SessionLocal

        db = SessionLocal()
    else:
        prefix = "sqlite:///"
        if not config.DATABASE_URL.startswith(prefix):
            print("미리보기는 SQLite DB 에서만 돕니다(메모리 복사본에서 돌린다).", file=sys.stderr)
            return 2
        db = memory_copy(config.DATABASE_URL[len(prefix):])

    edit_log.install()
    token = None
    try:
        if args.user_id is not None:
            user = db.get(User, args.user_id)
            if user is None:
                print(f"--user-id {args.user_id} 계정이 없습니다.", file=sys.stderr)
                return 2
            token = edit_log.begin(user.id, "SCRIPT", "scripts/series_a_ir_link.py")
        counts = run(db)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        if token is not None:
            edit_log.end(token)
        db.close()

    print("저장했습니다." if args.apply else "미리보기 — DB 에는 쓰지 않았습니다(메모리 복사본에서 돌림)")
    print(f"이을 줄(후보 하나) {counts['single']} → 이은 줄 {counts['done']}"
          f" · 이미 이어진 줄 {counts['linked']}"
          f" · 후보 여럿(사람이 /ir-link 에서 고름) {counts['multi']} · 후보 없음 {counts['none']}")
    for field in cs.FIELDS:
        sa, ir, left = counts["sa:" + field], counts["ir:" + field], counts["left:" + field]
        if sa or ir or left:
            print(f"  {cs.label(field)}: Series A 빈칸 채움 {sa} · IR 빈칸 채움 {ir} · 남은 값 다름 {left}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
