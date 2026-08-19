"""구글시트 CSV 임포트 CLI (ROADMAP 2.1, DATA_MODEL §6).

구글시트는 API 연동 없이 **CSV로 내려받아** 넣는다(파일 → 다운로드 → 쉼표로 구분된 값).
시트 1개 = 사용자 1명이므로 시트 A에는 `--user-id` 가 **필수**다(SHEET_FINDINGS §1).

    # 미리보기(DB 변경 없음) — 먼저 이걸로 스킵 리포트를 확인할 것
    python scripts/import_sheets.py --sheet-a a.csv --user-id 1 --dry-run

    # 실제 반영 (재실행해도 중복이 생기지 않는 멱등 upsert)
    python scripts/import_sheets.py --sheet-a a.csv --sheet-b b.csv --user-id 1

    # 도커
    docker exec -i dealflow-public-web-1 python scripts/import_sheets.py \
        --sheet-a /tmp/a.csv --user-id 1

멱등 기준: 담당자=(user_id, 이름, 투자사) · 기업=기업명 · 활동=(담당자, 월, 종류, 내용).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services import sheet_import as si  # noqa: E402
from app.services.room_name import DEFAULT_SUFFIX  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="구글시트 CSV → dealflow 임포트")
    p.add_argument("--sheet-a", help="시트 A(투자사 관리) CSV 경로")
    p.add_argument("--sheet-b", help="시트 B(IR 기업현황) CSV 경로")
    p.add_argument("--user-id", type=int,
                   help="시트 A 담당자들의 소유자 user_id (시트 A 임포트 시 필수)")
    p.add_argument("--year", type=int, default=date.today().year,
                   help="월 컬럼(6월/7월…)에 붙일 연도 (기본: 올해)")
    p.add_argument("--room-suffix", default=DEFAULT_SUFFIX,
                   help=f"카톡방 이름 고정 접미사 (기본: {DEFAULT_SUFFIX!r})")
    p.add_argument("--encoding", default="utf-8-sig", help="CSV 인코딩 (기본 utf-8-sig)")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 결과만 출력")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.sheet_a and not args.sheet_b:
        print("--sheet-a 또는 --sheet-b 중 하나는 필요합니다", file=sys.stderr)
        return 2
    if args.sheet_a and args.user_id is None:
        # 시트마다 소유자가 다르다. 잘못된 사용자에게 126명이 붙으면 되돌리기 번거롭다.
        print("--sheet-a 를 넣을 때는 --user-id 가 필수입니다 (시트 1개 = 사용자 1명)",
              file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        if args.sheet_a:
            user = db.get(User, args.user_id)
            if user is None:
                print(f"user_id={args.user_id} 사용자가 없습니다", file=sys.stderr)
                return 2
            rows = si.read_csv(args.sheet_a, encoding=args.encoding)
            parsed = si.parse_sheet_a(rows, year=args.year)
            print(f"[시트 A] 헤더 {(parsed.header_row or 0) + 1}행 인식 · "
                  f"담당자 {len(parsed.contacts)}명 · "
                  f"활동 컬럼 {len(parsed.activity_columns)}개")
            report = si.apply_sheet_a(db, parsed, user_id=args.user_id,
                                      room_suffix=args.room_suffix, dry_run=args.dry_run)
            print(report.as_text(f"시트 A → {user.name}(id={user.id})"))

        if args.sheet_b:
            rows = si.read_csv(args.sheet_b, encoding=args.encoding)
            parsed_b = si.parse_sheet_b(rows, year=args.year)
            print(f"[시트 B] 헤더 {(parsed_b.header_row or 0) + 1}행 인식 · "
                  f"기업 {len(parsed_b.companies)}개")
            report_b = si.apply_sheet_b(db, parsed_b, dry_run=args.dry_run)
            print(report_b.as_text("시트 B → 딜 기업 DB"))

        if args.dry_run:
            print("\n※ --dry-run: DB에 아무것도 쓰지 않았습니다.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
