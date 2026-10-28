"""**이미 이어진 줄의 2단계 칸을 처음 맞춘다** — 양쪽 빈칸만 채운다. 미리보기가 기본이다.

기업 동기화 2단계(#59 · 10/23): 계약여부 · 계약서 수신 여부 · 미팅제공일자 · 성공보수율을
IR 기업 현황 ↔ 투자컨설턴트 ↔ 스타트업 명단이 따라 고친다(`services/company_sync.py`). 그런데
지금 이어진 줄은 이 칸들이 잇는 칸이 되기 **전에** 이어져, 잇는 순간 빈칸 채우기를 못 지났다.
이 스크립트가 그 일을 한 번 한다 — `company_sync.fill_blanks`(잇는 순간과 같은 함수).

10/28(0125) — `Series A 이상 딜 소싱` 줄에도 계약여부 · 계약서 수신 여부 칸이 생겼다. 이미
이어진 Series A 줄도 같은 까닭으로 한 번 채운다(같은 함수 · 같은 규칙 — Series A 에 칸이
없는 미팅제공일자 · 성공보수율은 건너뛴다).

    # ① 미리보기 (기본) — DB 를 읽기 전용으로 열어 **메모리에** 복사본을 뜨고 거기서 돌린다
    python scripts/company_sync_fill.py

    # ② 실제로 저장 — 수정 로그에 남을 계정을 꼭 준다
    python scripts/company_sync_fill.py --apply --user-id N

· 양쪽에 다른 값이 있으면 덮지 않는다 — `/ir-link` 의 `값 다름` 에 남아 사람이 고른다(결정 5).
· **`딜소개 불가` 는 적지도 지우지도 않는다** — IR 이 그 값이 되면 그 기업이 딜 발송에서
  빠진다. `값 다름` 에 `딜소개 불가` 딱지로 남는다. 끝에 그 수를 따로 찍는다.

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

#: 2단계 칸.
FIELDS = ("contract_status", "contract_received", "meeting_offered_at", "success_fee")


def run(db, fields=FIELDS) -> Counter:
    """빈칸을 채우고 센다 — `{칸: 채운 칸 수, 'ir:칸': 그중 IR, 'left:칸': 남은 값 다름,
    'blocked': 딜소개 불가가 낀 값 다름, 'a5_in' / 'a5_out': 월간 IR 문서 받는 기업 증감}`.
    커밋은 부르는 쪽."""
    from sqlalchemy import select

    from app.models import ConsultingCompany, IrCompany, SeriesACompany, VcContact
    from app.routers.companies import contract_key
    from app.services import company_sync as cs
    from app.services.ir_monthly import CONTRACTED

    fields = [f for f in fields if f in cs.FIELDS]
    rows = [r for model in (ConsultingCompany, VcContact, SeriesACompany)
            for r in db.execute(select(model).where(model.ir_company_id.isnot(None))
                                .order_by(model.id)).scalars()]
    companies = db.execute(select(IrCompany)).scalars().all()
    before = {c.id: {f: cs._value(c, f, f) for f in fields} for c in companies}

    counts: Counter = Counter()
    with cs.fill_only(db):
        for field in fields:
            counts[field] = cs.fill_blanks(db, rows, [field])
        db.flush()
    for c in companies:
        for f in fields:
            counts["ir:" + f] += cs._value(c, f, f) != before[c.id][f]
        if "contract_status" in fields:
            was = contract_key(before[c.id]["contract_status"] or cs.NONE)
            now = contract_key(c.contract_status)
            counts["blocked_changed"] += (was == cs.BLOCKED) != (now == cs.BLOCKED)
            counts["a5_in"] += was not in CONTRACTED and now in CONTRACTED
            counts["a5_out"] += was in CONTRACTED and now not in CONTRACTED
    for diffs in cs.differences(db, rows).values():
        for d in diffs:
            if d["field"] in fields:
                counts["left:" + d["field"]] += 1
                counts["blocked"] += d["blocked"]
                counts["stuck:" + d["field"]] += not d["movable"]
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="이어진 줄의 2단계 칸(계약 · 미팅 · 보수율) 빈칸 채우기")
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
            token = edit_log.begin(user.id, "SCRIPT", "scripts/company_sync_fill.py")
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
    for f in FIELDS:
        print(f"  {cs.LABELS[f]}: 채운 칸 {counts[f]}(그중 IR {counts['ir:' + f]})"
              f" · 남은 값 다름 {counts['left:' + f]}(그중 줄 값을 못 옮김 {counts['stuck:' + f]})")
    print(f"딜소개 불가가 낀 값 다름 {counts['blocked']} — 사람이 /ir-link 에서 고른다"
          f" | 딜소개 불가로 바뀌거나 풀린 IR {counts['blocked_changed']}(늘 0이어야 한다)"
          f" | 월간 IR 문서(A5) 새로 받는 기업 {counts['a5_in']} · 빠지는 기업 {counts['a5_out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
