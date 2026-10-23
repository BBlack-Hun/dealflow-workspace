"""**남은 연락처 · 이메일 `값 다름` 을 한 번에 둘 다 남긴다** — 미리보기가 기본이다.

10/23 결정: "연락처나 이메일인데 각각 다른 내용이 들어간건 둘다 쓰도록 하자". `/ir-link`
의 [둘 다 남기기]와 **같은 함수**(`company_sync.keep_both`)를 이어진 줄마다 돌린다 —
`IR 값, 이 줄 값`(앞이 정 · 메일은 정에만 간다), 꼴만 다른 같은 번호 · 대소문자만 다른
같은 메일은 하나로, 연락처 칸의 메일 주소는 이메일 칸으로 옮겨 잇는다.

    # ① 미리보기 (기본) — DB 를 읽기 전용으로 열어 **메모리에** 복사본을 뜨고 거기서 돌린다
    python scripts/ir_link_keep_both.py

    # ② 실제로 저장 — 수정 로그에 남을 계정을 꼭 준다
    python scripts/ir_link_keep_both.py --apply --user-id N

**모양이 이상한 값이 끼면 건너뛴다**(`keep_both(skip_odd=True)`) — 이메일 칸에 주소가 아닌
글, 연락처 칸에 숫자도 메일도 없는 글. 저절로 잇지 않고 `/ir-link` 의 `값 다름` 에 남겨
사람이 고른다.

이름 · 번호 · 주소를 찍지 않는다(공개 저장소 · 실명) — 표 · 줄 id · 칸 · 수만 찍는다.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.link_sourcing_rows import memory_copy  # noqa: E402 — 같은 미리보기 방식


def run(db) -> tuple:
    """이어진 줄마다 연락처 → 이메일 차례로. `(수 Counter, [(표, 줄 id, 칸, 한 일)])`.

    칸마다 `값 다름` 을 **다시 센다** — 앞 칸(연락처의 메일 옮기기)이나 같은 IR 의 앞 줄이
    이미 맞췄으면 건너뛴다. 커밋은 부르는 쪽.
    """
    from sqlalchemy import select

    from app.models import ConsultingCompany, VcContact
    from app.services import company_sync as cs

    counts: Counter = Counter()
    trace: List[tuple] = []
    for model in (ConsultingCompany, VcContact):
        rows = db.execute(select(model).where(model.ir_company_id.isnot(None))
                          .order_by(model.id)).scalars().all()
        for row in rows:
            for field in cs.BOTH:
                diff = next((d for d in cs.differences(db, [row]).get(row.id, [])
                             if d["field"] == field), None)
                if diff is None:
                    continue
                done = cs.keep_both(db, row, field, skip_odd=True)
                if done["odd"]:
                    counts["odd"] += 1
                    trace.append((model.__tablename__, row.id, field, "건너뜀(모양 이상)"))
                    continue
                db.flush()      # 같은 IR 의 다음 줄이 이 결과를 보게
                counts[field] += 1
                counts["moved"] += done["moved"]
                counts["folded"] += done["folded"]
                trace.append((model.__tablename__, row.id, field,
                              f"둘 다 남김 · 메일 옮김 {done['moved']} · 접음 {done['folded']}"))
        counts["left"] += sum(len(v) for v in cs.differences(db, rows).values())
    return counts, trace


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="남은 연락처 · 이메일 값 다름을 둘 다 남긴다")
    ap.add_argument("--user-id", type=int, default=None, help="수정 로그에 남을 계정(--apply 때 꼭)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="미리보기(기본)")
    mode.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args(argv)

    from app import config
    from app.models import User
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
            token = edit_log.begin(user.id, "SCRIPT", "scripts/ir_link_keep_both.py")
        counts, trace = run(db)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        if token is not None:
            edit_log.end(token)
        db.close()

    print("저장했습니다." if args.apply else "미리보기 — DB 에는 쓰지 않았습니다(메모리 복사본에서 돌림)")
    for table, rid, field, what in trace:
        print(f"  {table}#{rid}  {field}  {what}")
    print(f"둘 다 남긴 값 다름: 연락처 {counts['contact_phone']} · 이메일 {counts['contact_email']}"
          f" | 연락처 칸 → 이메일 칸 옮긴 메일 {counts['moved']}"
          f" | 꼴만 달라 하나로 접은 값 {counts['folded']}"
          f" | 모양이 이상해 건너뜀 {counts['odd']}"
          f" | 끝난 뒤 남은 값 다름 {counts['left']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
