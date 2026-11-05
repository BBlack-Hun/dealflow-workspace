"""**이미 들어 있는 `투자라운드` 값을 일곱 단계로 맞춘다**(#162) — 미리보기가 기본이다.

    Seed → Pre-A → Bridge → Series A → Series B → Series C → Pre-IPO

새로 적는 값은 저장할 때 저절로 맞춰진다(`services/series_stage.py`). 그 전에 들어와 있던
값은 이 스크립트가 **한 번** 맞춘다 — 머리글이 `투자라운드` 인 세 칸 모두:

    IR 기업 현황 `ir_companies.series` · Series A 이상 딜 소싱 `series_a_companies.series`
    · 스타트업 명단 `vc_contacts.notes["company_kind"]`

    # ① 미리보기(기본) — DB 를 읽기 전용으로 열어 **메모리에** 복사본을 뜨고 거기서 돌린다
    python scripts/series_stage_fill.py

    # ② 실제로 저장 — 백업을 뜬 뒤 한 번. 수정 로그에 남을 계정을 꼭 준다
    python scripts/series_stage_fill.py --apply --user-id N

· 못 읽는 값(`M&A` · `Pre IPO 전단계` …)과 빈칸은 그대로 둔다 — 남은 값과 수를 찍는다.
· 원래 값 — IR · Series A 는 수정 로그에 전→후 값이 남는다(`series` 는 값을 남기는 칸).
  스타트업 명단은 값이 수정 로그에 안 남는 칸(`notes`)이라 같은 줄의 `company_kind_raw`
  에 **처음 한 번** 적어 둔다(다시 돌려도 안 덮는다).
· 기업 동기화는 같은 단계를 같은 값으로 본다(`company_sync.same`) — 맞추기만 한 것은
  이어진 다른 표로 따라가지 않는다.
· ORM 으로 한 줄씩 고친다. 다시 돌리면 더 할 일이 없다.
· 단계 글자와 수만 찍는다 — 기업명 · 번호는 안 찍는다(공개 저장소 · 실명).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.link_sourcing_rows import memory_copy  # noqa: E402 — 같은 미리보기 방식

#: 스타트업 명단 줄의 원래 값 자리(`notes` 열쇠).
RAW_NOTE = "company_kind_raw"
IR, SERIES_A, STARTUP = "IR 기업 현황", "Series A 이상 딜 소싱", "스타트업 명단"


def _shown(text: str) -> str:
    return " ".join(text.split())[:30]


def run(db) -> Dict[str, Counter]:
    """맞추고 센다 — `{changed: (표, 옛 값, 단계), kept: (표, 값), same: 표, blank: 표}`.
    커밋은 부르는 쪽."""
    from sqlalchemy import select

    from app.models import IrCompany, SeriesACompany, VcContact
    from app.services import contact_columns as cc
    from app.services import series_stage

    out = {"changed": Counter(), "kept": Counter(), "same": Counter(), "blank": Counter()}

    def target(table: str, value: Optional[str]) -> Optional[str]:
        """바꿀 단계 — 바꿀 것이 없으면 None(세기는 한다)."""
        text = (value or "").strip()
        if not text:
            out["blank"][table] += 1
            return None
        stage = series_stage.stage_of(text)
        if stage is None:
            out["kept"][(table, _shown(text))] += 1
            return None
        if stage == value:
            out["same"][table] += 1
            return None
        out["changed"][(table, _shown(text), stage)] += 1
        return stage

    for model, table in ((IrCompany, IR), (SeriesACompany, SERIES_A)):
        for row in db.execute(select(model).order_by(model.id)).scalars():
            stage = target(table, row.series)
            if stage is not None:
                row.series = stage
    for row in db.execute(select(VcContact).order_by(VcContact.id)).scalars():
        notes = cc.load_notes(row.notes)
        if "company_kind" not in notes:
            continue
        stage = target(STARTUP, notes["company_kind"])
        if stage is not None:
            notes.setdefault(RAW_NOTE, notes["company_kind"])
            notes["company_kind"] = stage
            row.notes = cc.dump_notes(notes)
    db.flush()
    return out


def report(out: Dict[str, Counter]) -> List[str]:
    lines = []
    for table in (IR, SERIES_A, STARTUP):
        changed = sum(n for (t, _o, _s), n in out["changed"].items() if t == table)
        kept = sum(n for (t, _v), n in out["kept"].items() if t == table)
        lines.append(f"[{table}] 바뀜 {changed} · 이미 단계 {out['same'][table]}"
                     f" · 그대로 둠(못 읽음) {kept} · 빈칸 {out['blank'][table]}")
        for (t, old, stage), n in sorted(out["changed"].items(), key=lambda x: (-x[1], x[0])):
            if t == table:
                lines.append(f"    {n:4d}  {old}  →  {stage}")
        for (t, value), n in sorted(out["kept"].items(), key=lambda x: (-x[1], x[0])):
            if t == table:
                lines.append(f"    {n:4d}  {value}  (그대로)")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="투자라운드 값을 일곱 단계로 맞춘다(#162)")
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
            token = edit_log.begin(user.id, "SCRIPT", "scripts/series_stage_fill.py")
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
