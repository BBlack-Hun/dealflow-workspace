"""**이미 들어 있는 금액 칸의 맨숫자에 `억` 을 붙인다**(#217) — 미리보기가 기본이다.

새로 적는 값은 저장할 때 저절로 붙는다(`amount.with_unit` · `routers/companies.typed_amount`).
그 전에 들어와 있던 값은 이 스크립트가 **한 번** 맞춘다 — IR 기업 현황 · Series A 이상 딜
소싱 두 표의 금액 칸 모두(연도 매출 · 26년 매출 · 누적투자금액 · 투자유치희망금액 · Pre Value):

    # ① 미리보기(기본) — DB 를 읽기 전용으로 열어 **메모리에** 복사본을 뜨고 거기서 돌린다
    python scripts/amount_unit_fill.py

    # ② 실제로 저장 — 백업을 뜬 뒤 한 번. 수정 로그에 남을 계정을 꼭 준다
    python scripts/amount_unit_fill.py --apply --user-id N

· 맨숫자(`30` · `2.5`)만 바뀐다. 단위 · 구간 · 글 · `0` · 1만 이상(만원 · 원일 수 있다)은 그대로.
· 뜻은 안 바뀐다(맨숫자는 원래 억으로 읽혔다). 기업 동기화도 같은 값으로 본다
  (`company_sync.norm`) — 맞추기만 한 것은 이어진 다른 표로 따라가지 않는다.
· 금액 칸은 수정 로그에 값이 아니라 `바뀜` 으로만 남는다 — 원래 값이 필요하면 백업에서 본다.
· ORM 으로 한 줄씩 고친다. 다시 돌리면 더 할 일이 없다.
· 칸 이름과 수만 찍는다 — 기업명 · 번호 · 값은 안 찍는다(공개 저장소 · 실명).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.link_sourcing_rows import memory_copy  # noqa: E402 — 같은 미리보기 방식

IR, SERIES_A = "IR 기업 현황", "Series A 이상 딜 소싱"


def run(db) -> Dict[str, Counter]:
    """맞추고 센다 — `{표: Counter(칸 → 바뀐 수)}`. 커밋은 부르는 쪽.

    **먼저 다 읽고 나서 적는다** — 한 표를 고친 flush 가 이어진 다른 표를 먼저 건드려
    세는 수가 갈리지 않게.
    """
    from sqlalchemy import select

    from app.models import IrCompany, SeriesACompany
    from app.services import amount

    out = {IR: Counter(), SERIES_A: Counter()}
    todo = []
    with db.no_autoflush:
        for model, table in ((IrCompany, IR), (SeriesACompany, SERIES_A)):
            fields = [c.key for c in model.__table__.columns if amount.FIELD_RE.fullmatch(c.key)]
            for row in db.execute(select(model).order_by(model.id)).scalars():
                for field in fields:
                    before = amount.text(getattr(row, field))
                    after = amount.with_unit(before)
                    if after != before:
                        todo.append((row, field, after))
                        out[table][field] += 1
    for row, field, after in todo:
        setattr(row, field, after)
    db.flush()
    return out


def report(out: Dict[str, Counter]) -> List[str]:
    return [f"[{table}] 바뀜 {sum(c.values())}"
            + "".join(f" · {field} {n}" for field, n in sorted(c.items()))
            for table, c in out.items()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="금액 칸의 맨숫자에 `억` 을 붙인다(#217)")
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
            token = edit_log.begin(user.id, "SCRIPT", "scripts/amount_unit_fill.py")
        out = run(db)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        if token is not None:
            edit_log.end(token)
        db.close()

    print("저장했습니다." if args.apply else "미리보기 — DB 에는 쓰지 않았습니다(메모리 복사본에서 돌림)")
    for line in report(out):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
