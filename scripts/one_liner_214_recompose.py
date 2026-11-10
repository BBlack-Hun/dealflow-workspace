"""**과제 214 전 규칙으로 만든 자동 딜 소개 문구를 새 규칙으로 한 번 다시 조합한다** — 미리보기가 기본이다.

과제 214 가 조합 규칙을 바꿨다(`services/one_liner.py`).
  · 기업 한줄 소개에 `매출 13억` 토막이 따로 적혀 있으면 칸의 여러 해를 건너뛰던 것 →
    그 자리에 칸의 여러 해(`매출 24년 2억, 25년 3억`)가 선다
  · 예상 칸 값의 `(예상)` 이 `27년(예상) 30억(예상)` 으로 두 번 찍히던 것 → 한 번

그 전 규칙으로 만든 자동 문구도 앱이 자동으로 알아본다(`one_liner._auto_texts`) — 그래서 재료를
고치면 그때 새 규칙으로 따라온다. 이 스크립트는 **재료를 고치지 않아도** 그 줄들을 지금 한 번
새 규칙으로 맞춘다. 배포 뒤 한 번 돌린다.

    # ① 미리보기(기본) — DB 를 읽기 전용으로 열어 **메모리에** 복사본을 뜨고 거기서 센다
    python scripts/one_liner_214_recompose.py

    # ② 실제로 저장 — 백업을 뜬 뒤 한 번. 수정 로그에 남을 계정을 꼭 준다
    python scripts/one_liner_214_recompose.py --apply --user-id N

· 바꾸는 줄은 **지금 문구가 214 전 규칙의 조합값 그대로**이고 새 규칙의 조합값과 다른 줄뿐이다.
  사람이 쓴 문구(어느 규칙의 조합값과도 다른 글)는 **절대 안 바꾼다.** 빈 문구 · 기업 한줄
  소개가 없는 줄도 안 건드린다(빈 문구는 다음 저장에서 앱이 채운다 — `one_liner._FILL_EMPTY`).
· 바꾸기 전 값은 `one_liner_backups` 에 **한 묶음**으로 남는다 — IR 기업 현황의 [전체 자동조합] 창
  [되돌리기] 가 이 묶음을 되돌린다(그 뒤에 사람이 또 고친 줄은 안 건드린다). 수정 로그에도 전→후
  값이 남는다.
· 다시 돌리면 할 일이 없다. IR 기업 현황만 본다(Series A 문구는 되돌릴 버퍼가 없어 재료를 고칠 때
  앱이 따라 고친다).
· 수와 기업 번호(id)만 찍는다 — 기업명 · 문구는 안 찍는다(공개 저장소 · 실명).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.link_sourcing_rows import memory_copy  # noqa: E402 — 같은 미리보기 방식

KEYS = (("recompose", "다시 조합"), ("manual", "사람 문구 그대로"), ("same", "이미 새 규칙"),
        ("other", "다른 자동 모양(안 건드림)"), ("empty", "빈 문구"), ("no_head", "한줄 소개 없음"))


def plan(db) -> Tuple[List[Tuple[object, str]], Counter]:
    """다시 조합할 줄 `[(기업, 새 문구)]` 과 줄 수 — **읽기만 한다.**"""
    from sqlalchemy import select

    from app.models import IrCompany
    from app.services import one_liner as ol

    todo: List[Tuple[object, str]] = []
    count: Counter = Counter()
    for company in db.execute(select(IrCompany).order_by(IrCompany.id)).scalars():
        text = ol._text(company.one_liner)
        if not text:
            count["empty"] += 1
            continue
        if not ol._clean(company.business_desc):
            count["no_head"] += 1      # 앱도 이 줄은 저절로 안 만든다(`one_liner._HEAD`)
            continue
        layouts = ol._layouts(company)
        now = ol.compose_one_liner(company, layouts[0])
        if text == now:
            count["same"] += 1
            continue
        pairs = [(ol.compose_one_liner(company, r, before_214=True), ol.compose_one_liner(company, r))
                 for r in layouts]
        # 214 전 규칙의 조합값 그대로이고, 그 모양이 214 로 **달라진** 줄만 — 규칙과 상관없는
        # 지난해 · 예전 칸 모양의 자동 문구는 앱이 재료를 고칠 때 따라 고친다.
        if now and any(text == old != new for old, new in pairs):
            todo.append((company, now))
            count["recompose"] += 1
        elif any(text in pair for pair in pairs):
            count["other"] += 1
        else:
            count["manual"] += 1
    return todo, count


def apply(db, todo: List[Tuple[object, str]], user_id: int) -> Optional[int]:
    """새 문구를 넣고 바꾸기 전 값을 한 묶음으로 남긴다 — 묶음 번호. 커밋은 부르는 쪽."""
    from sqlalchemy import select

    from app.models import OneLinerBackup

    if not todo:
        return None
    batch = (db.execute(select(OneLinerBackup.batch)
                        .order_by(OneLinerBackup.batch.desc()).limit(1)).scalar() or 0) + 1
    for company, text in todo:
        db.add(OneLinerBackup(batch=batch, company_id=company.id,
                              previous=company.one_liner or None, applied=text,
                              user_id=user_id))
        company.one_liner = text
    db.flush()
    return batch


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="과제 214 전 규칙의 자동 딜 소개 문구를 새 규칙으로 다시 조합한다")
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
    batch = None
    try:
        if args.user_id is not None:
            user = db.get(User, args.user_id)
            if user is None:
                print(f"--user-id {args.user_id} 계정이 없습니다.", file=sys.stderr)
                return 2
            token = edit_log.begin(user.id, "SCRIPT", "scripts/one_liner_214_recompose.py")
        todo, count = plan(db)
        ids = [company.id for company, _ in todo]
        if args.apply:
            batch = apply(db, todo, args.user_id)
            db.commit()
        else:
            db.rollback()
    finally:
        if token is not None:
            edit_log.end(token)
        db.close()

    print("저장했습니다." if args.apply else "미리보기 — DB 에는 쓰지 않았습니다(메모리 복사본에서 돌림)")
    print("[IR 기업 현황] " + " · ".join(f"{label} {count[key]}" for key, label in KEYS))
    if ids:
        print("다시 조합할 기업 id: " + ", ".join(map(str, ids)))
    if batch is not None:
        print(f"되돌리기: IR 기업 현황 [전체 자동조합] 창의 [되돌리기] (묶음 {batch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
