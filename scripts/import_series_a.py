"""`Series A 이상 기업` 시트를 IR 기업 현황 메뉴의 같은 이름 탭으로 옮긴다.

시트 주소는 받지 않는다 — **내려받은 파일**(CSV 또는 xlsx)의 경로를 받는다.
구글 시트에서 그 탭을 `파일 → 다운로드 → CSV` 로 받거나, 워크북을 xlsx 로 받아
`--sheet` 로 탭을 고른다(탭을 안 고르면 이 시트로 보이는 탭이 하나일 때만 쓴다).

무엇을 열쇠로 맞추는지 · 몇 번 돌려도 같은 결과인 까닭은
`app/services/series_a_import.py` 머리말에 있다. 짧게:

  · `(기업명, 수신 일자)` 로 한 줄을 알아본다 — 기업명은 (주)·띄어쓰기를 다듬어 견준다.
  · 새 줄은 만들고, 있던 줄은 **앱에서 빈 칸만** 채운다(`--overwrite` 로만 덮는다).
  · 시트의 빈 칸 · 시트에서 사라진 줄은 앱에서 아무것도 지우지 않는다.

    python scripts/import_series_a.py 받은파일.csv --dry-run   # 미리보기(저장 안 함)
    python scripts/import_series_a.py 받은파일.csv             # 저장
    python scripts/import_series_a.py 워크북.xlsx --sheet "Series A 이상 기업"

**운영에서 돌리기 전에는 DB 를 먼저 떠 둔다**(`scripts/db_snapshot.py` 또는 팀
현황의 백업). 넣은 줄을 하나씩 되돌리는 길은 없다 — 되돌리기는 DB 를 통째로
그 시점으로 돌린다.

출력은 **수만** 적는다 — 기업명 · 사람 이름을 화면에 늘어놓지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.services import series_a_import as svc  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Series A 이상 기업 시트 가져오기")
    ap.add_argument("path", help="내려받은 시트 파일(.csv · .xlsx)")
    ap.add_argument("--sheet", help="xlsx 일 때 읽을 탭 이름")
    ap.add_argument("--dry-run", action="store_true",
                    help="세어 보기만 하고 저장하지 않는다")
    ap.add_argument("--overwrite", action="store_true",
                    help="앱 값과 다른 칸도 시트 값으로 덮는다(기본은 빈 칸만 채움)")
    args = ap.parse_args(argv)

    try:
        rows = svc.read_rows(Path(args.path), args.sheet)
        parsed = svc.parse(rows)
    except (OSError, ValueError) as err:
        print(f"읽지 못했습니다: {err}")
        return 2

    print(f"시트 줄 {len(parsed.records)}개"
          + (f" · 기업명이 빈 줄 {parsed.no_name}개(건너뜀)" if parsed.no_name else ""))
    if parsed.missing:
        print("시트에 없는 칸(안 들어옵니다): " + ", ".join(parsed.missing))

    db = SessionLocal()
    try:
        result = svc.upsert(db, parsed.records, overwrite=args.overwrite)
        print(f"새 줄 {result.created} · 고친 줄 {result.updated} "
              f"(빈 칸 채움 {result.filled} · 덮음 {result.overwritten}) · "
              f"그대로 {result.unchanged}")
        if result.kept:
            print(f"앱 값과 달라 그대로 둔 칸 {result.kept}개 — 덮으려면 --overwrite")
        if result.duplicates:
            print(f"시트 안에서 (기업명, 수신 일자)가 겹친 줄 {result.duplicates}개 — "
                  "앞 줄만 썼습니다")
        if args.dry_run:
            db.rollback()
            print("→ 미리보기입니다(저장 안 함). 넣으려면 --dry-run 을 빼세요.")
        else:
            db.commit()
            print("→ 저장했습니다.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
