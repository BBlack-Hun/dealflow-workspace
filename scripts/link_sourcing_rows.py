"""**딜 소싱 대표 · 개인참여 갈래의 이미 있는 줄을 투자사 관리 현황과 잇는다** — 미리보기가 기본이다.

2026-10-22 대표 · 개인참여 갈래도 투자사 관리 현황과 잇기로 했다(`sourcing_sync.BRANCHES`).
그 전에 들어 있던 줄은 잇기를 한 번도 지나지 않았다. 화면의 [저절로 잇기]는 맞는 분만
잇고, [추가]의 '없으면 만든다'는 새로 넣는 줄에만 돈다. 그래서 이미 있는 줄에 [추가]와
**같은 함수**(`sourcing_sync.add_from_sourcing`)를 한 번 돌린다.

    # ① 미리보기 (기본) — 운영 DB 를 읽기 전용으로 열어 **메모리에** 복사본을 뜨고 거기서 돌린다
    python scripts/link_sourcing_rows.py

    # ② 실제로 저장
    python scripts/link_sourcing_rows.py --apply [--user-id N]

## 줄마다 (안 이어진 대표 · 개인참여 줄만)

  · 이름 + 번호가 같은 투자사 줄이 팀 전체에 딱 하나 → 잇는다([저절로 잇기]와 같다)
  · 이름이나 번호가 같은 줄이 있는데 못 이었다 → 아무것도 안 만든다(딜 소싱 화면에 후보로 남는다)
  · `(딜 소개 X)` · `딜 소개 보류` 인 분과 번호가 같거나 이름에 그 표시 → 막힘
  · 아무도 없다 → 담당 계정의 `직접 추가` 명단에 새 투자사 줄을 만들고 잇는다
  · `불참여` 줄 → 잇기만 보고 새로 만들지 않는다(빠진 분을 팀원 명단에 새로 세우지 않는다)

`참여` 칸 · 딜 소싱 담당자 칸 · 카톡방은 건드리지 않는다.

## 새 투자사 줄의 담당 계정 (`owner_for`)

[추가]는 **넣은 사람** 명단에 만든다. 이미 있는 줄에는 넣은 사람이 없다 — 가장 가까운 것이
그 줄의 딜 소싱 `담당자` 칸(그 분을 딜 소싱 방에 둔 팀원)이다. 그래서

  ① 담당자 칸의 지금 맡은 사람(`pipeline.current_assignee` — `가팀 > 홍길동` → 홍길동)과
     이름이 같은 쓰는 계정이 하나면 그 계정
  ② 없으면 그 사람 이름의 투자사 탭(`홍길동 투자사 120명`)을 가진 계정이 하나면 그 계정 —
     계정 이름이 사람 이름이 아닌 계정이 있다(탭 주인을 담당으로 본 10/21 분류와 같은 손)
  ③ 그래도 없으면(팀 이름 · 빈칸 · 둘 이상) `--user-id` 계정, 그것도 없으면 만들지 않는다

## 미리보기는 운영 DB 에 쓰지 않는다

`--apply` 가 없으면 DB 파일을 읽기 전용으로 열어 **메모리에** 복사하고(파일을 만들지
않는다), 거기서 같은 길을 돌린 뒤 버린다 — 미리보기 수와 `--apply` 수가 같다.
`--apply` 는 끝에 한 번 저장한다.

## 이름을 찍지 않는다

줄마다 **딜 소싱 줄 id · 한 일 · 계정 id** 만 찍는다(공개 저장소 · 실명).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: 한 일 → 찍을 이름. 차례가 곧 요약 차례다.
LABELS = {
    "linked": "투자사 줄과 이음",
    "created": "새 투자사 줄 만들어 이음",
    "held": "같은 분일 수 있는 줄 있음 — 안 만듦(후보)",
    "blocked": "막힘(딜 소개 X · 보류)",
    "left": "불참여 — 안 만듦",
    "no_owner": "담당 계정 못 찾음 — 안 만듦",
}


def owner_for(db, row, fallback=None):
    """새 투자사 줄을 둘 계정 — 모듈 머리말 ①②③."""
    from sqlalchemy import select

    from app.models import User, VcContact
    from app.services import sheet_owner
    from app.services.pipeline import current_assignee

    name = current_assignee(row.assignee_name)
    if name:
        same = [u for u in db.execute(select(User)).scalars()
                if u.is_active and sheet_owner.real_name(u) == name]
        if len(same) == 1:
            return same[0]
        owners = {c.user_id for c in db.execute(select(VcContact)).scalars()
                  if any(label.startswith(name + " ")
                         for label in sheet_owner.labels_of(c.source_sheet))}
        if len(owners) == 1:
            user = db.get(User, owners.pop())
            if user is not None and user.is_active:
                return user
    return fallback


def run(db, fallback=None) -> List[tuple]:
    """안 이어진 대표 · 개인참여 줄마다 — `(소싱 줄 id, 한 일, 계정 id)`. 커밋은 부르는 쪽."""
    from sqlalchemy import select

    from app.models import SourcingContact
    from app.services import sourcing_sync

    buckets = (sourcing_sync.CEO_BUCKET, sourcing_sync.SOLO_BUCKET)
    rows = [r for r in db.execute(
        select(SourcingContact).where(SourcingContact.vc_contact_id.is_(None))
        .order_by(SourcingContact.id)).scalars()
        if sourcing_sync.branch_of(r) in buckets]
    out = []
    for row in rows:
        owner = None if sourcing_sync.is_left(row) else owner_for(db, row, fallback)
        if owner is None:
            # 만들 수 없는 줄 — 잇기만([저절로 잇기]와 같은 규칙)
            if sourcing_sync.auto_link(db, row):
                action = "linked"
            elif sourcing_sync.is_left(row):
                action = "left"
            elif sourcing_sync.lookalikes(db, row):
                action = "held"
            else:
                action = "no_owner"
        else:
            try:
                contact, _note = sourcing_sync.add_from_sourcing(db, row, owner)
            except sourcing_sync.SyncError:
                action = "blocked"
            else:
                # 만든 줄은 확정으로 잇는다(`add_from_sourcing` ⑤) · 저절로 이은 줄은 아니다
                action = ("held" if contact is None
                          else "created" if row.vc_link_confirmed else "linked")
        db.flush()      # 다음 줄의 잇기 · 같은 분 찾기가 이 줄의 결과를 보게
        out.append((row.id, action, owner.id if action == "created" else None))
    return out


def memory_copy(path: str):
    """DB 파일을 읽기 전용으로 열어 **메모리에** 뜬 세션 — 파일을 만들지 않는다."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    mem = sqlite3.connect(":memory:", check_same_thread=False)
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        source.backup(mem)
    finally:
        source.close()
    mem.execute("PRAGMA foreign_keys=ON")
    engine = create_engine("sqlite://", creator=lambda: mem, poolclass=StaticPool, future=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="딜 소싱 대표 · 개인참여 갈래의 이미 있는 줄을 투자사 관리 현황과 잇는다")
    ap.add_argument("--user-id", type=int, default=None,
                    help="담당 계정을 못 찾은 줄의 새 투자사 줄 주인 · 수정 로그에 남을 계정")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="미리보기(기본)")
    mode.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args(argv)

    from app import config
    from app.models import User
    from app.services import edit_log

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
        fallback = None
        if args.user_id is not None:
            fallback = db.get(User, args.user_id)
            if fallback is None:
                print(f"--user-id {args.user_id} 계정이 없습니다.", file=sys.stderr)
                return 2
            token = edit_log.begin(fallback.id, "SCRIPT", "scripts/link_sourcing_rows.py")
        results = run(db, fallback)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        if token is not None:
            edit_log.end(token)
        db.close()

    counts = Counter(action for _, action, _ in results)
    owners = Counter(uid for _, action, uid in results if action == "created")
    print("저장했습니다." if args.apply else "미리보기 — DB 에는 쓰지 않았습니다(메모리 복사본에서 돌림)")
    for rid, action, uid in results:
        print(f"  {rid:>6}  {LABELS[action]}" + (f" — 계정 {uid}" if uid else ""))
    print("합계: " + " · ".join(f"{LABELS[k]} {counts.get(k, 0)}" for k in LABELS)
          + f" (모두 {len(results)})")
    if owners:
        print("새 투자사 줄 계정별: " + " · ".join(f"계정 {k} {v}" for k, v in sorted(owners.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
