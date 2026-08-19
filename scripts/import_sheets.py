"""구글시트 CSV 임포트 CLI (ROADMAP 2.1, DATA_MODEL §6).

구글시트는 API 연동 없이 **CSV로 내려받아** 넣는다(시트별로 파일 → 다운로드 →
쉼표로 구분된 값). 스프레드시트에는 투자사 명단 시트가 여러 장이고 컬럼 구성이
조금씩 다르지만, 파서가 헤더 이름으로 찾으므로 **같은 명령으로 전부** 넣을 수 있다.

담당자(소유자)는 시트의 **담당자 컬럼**이 정한다 — 한 시트에 여러 팀원의 담당분이
섞여 있다. `--user-id` 는 담당자 칸이 비었거나 계정이 없을 때 쓰는 **폴백**이다
(임포트에서 사람을 잃지 않기 위해 스킵하지 않는다).

    # 미리보기(DB 변경 없음) — 먼저 이걸로 스킵/미매칭 리포트를 확인할 것
    python scripts/import_sheets.py --sheet-a a.csv --user-id 1 --dry-run

    # 명단 시트 여러 장을 차례로 (같은 사람은 이름+투자사로 병합된다)
    python scripts/import_sheets.py --sheet-a deal_status.csv --user-id 1
    python scripts/import_sheets.py --sheet-a list_150.csv   --user-id 1
    python scripts/import_sheets.py --sheet-b ir_companies.csv

    # 도커
    docker exec -i dealflow-public-web-1 python scripts/import_sheets.py \
        --sheet-a /tmp/a.csv --user-id 1

멱등 기준: 담당자=(이름, 투자사) · 기업=기업명 · 활동=(담당자, 월, 종류, 내용).
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services import sheet_import as si  # noqa: E402
from app.services.room_name import DEFAULT_SUFFIX  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="구글시트 CSV → dealflow 임포트")
    p.add_argument("--sheet-a", help="투자사 명단 시트 CSV 경로")
    p.add_argument("--sheet-a-url", help="투자사 명단 시트 탭 URL (CSV 자동 다운로드)")
    p.add_argument("--sheet-b", help="기업 명단 시트(IR 기업현황 / 스타트업) CSV 경로")
    p.add_argument("--sheet-b-url", help="기업 명단 시트 탭 URL (CSV 자동 다운로드)")
    p.add_argument("--financials-url", help="기업 재무 시트(스타트업DB) 탭 URL")
    p.add_argument("--user-id", type=int,
                   help="담당자 칸이 비었거나 계정이 없을 때 쓸 폴백 user_id (시트 A 임포트 시 필수)")
    p.add_argument("--label", help="이 시트의 이름표 (기본: 파일명). vc_contacts.source_sheet 에 기록")
    p.add_argument("--year", type=int, default=date.today().year,
                   help="월 컬럼(6월/7월…)에 붙일 연도 (기본: 올해)")
    p.add_argument("--room-suffix", default=DEFAULT_SUFFIX,
                   help=f"카톡방 이름 고정 접미사 (기본: {DEFAULT_SUFFIX!r})")
    p.add_argument("--encoding", default="utf-8-sig", help="CSV 인코딩 (기본 utf-8-sig)")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 결과만 출력")
    return p


SHEET_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")
GID_RE = re.compile(r"[?#&]gid=(\d+)")


def fetch_sheet(url: str, out_dir: str = "") -> str:
    """구글시트 탭 URL → CSV 파일로 내려받고 경로를 돌려준다.

    시트를 손으로 CSV 내보내는 단계를 없애기 위한 것. 탭이 12개나 되고 갱신도
    잦아서, 링크만으로 최신 데이터를 가져올 수 있어야 실사용에 쓸 만하다.
    (공유 설정이 '링크가 있는 사람'이어야 받아진다)
    """
    m = SHEET_RE.search(url)
    if not m:
        raise SystemExit(f"구글시트 URL 이 아닙니다: {url}")
    doc_id = m.group(1)
    gid = (GID_RE.search(url) or [None, "0"])[1]
    export = f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}"

    dest = Path(out_dir or tempfile.gettempdir()) / f"sheet_{doc_id[:8]}_{gid}.csv"
    with urllib.request.urlopen(export, timeout=60) as resp:
        data = resp.read()
    if data[:15].lstrip().lower().startswith(b"<!doctype html"):
        raise SystemExit(
            "시트를 CSV 로 받지 못했습니다(HTML 응답). 공유 설정을 "
            "'링크가 있는 모든 사용자'로 바꾼 뒤 다시 시도하세요."
        )
    dest.write_bytes(data)
    return str(dest)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # URL 이 주어지면 먼저 내려받아 경로로 바꾼다.
    if getattr(args, "sheet_a_url", None):
        args.sheet_a = fetch_sheet(args.sheet_a_url)
        print(f"[다운로드] 시트 A → {args.sheet_a}")
    if getattr(args, "sheet_b_url", None):
        args.sheet_b = fetch_sheet(args.sheet_b_url)
        print(f"[다운로드] 시트 B → {args.sheet_b}")

    if not args.sheet_a and not args.sheet_b and not getattr(args, 'financials_url', None):
        print("--sheet-a 또는 --sheet-b 중 하나는 필요합니다", file=sys.stderr)
        return 2
    if args.sheet_a and args.user_id is None:
        # 담당자 칸이 비어 있거나 계정이 없는 행이 반드시 나온다. 그 사람들을 버리지 않으려면
        # 붙일 곳이 필요하다 → 폴백 사용자를 반드시 지정하게 한다.
        print("--sheet-a 를 넣을 때는 --user-id(폴백 담당자)가 필수입니다", file=sys.stderr)
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
            label = args.label or Path(args.sheet_a).stem
            print(f"[투자사 명단: {label}] 헤더 {(parsed.header_row or 0) + 1}행 인식 · "
                  f"담당자 {len(parsed.contacts)}명 · "
                  f"활동 컬럼 {len(parsed.activity_columns)}개")
            report = si.apply_sheet_a(db, parsed, user_id=args.user_id,
                                      room_suffix=args.room_suffix, dry_run=args.dry_run,
                                      source_label=label)
            print(report.as_text(f"투자사 명단 (폴백 담당자: {user.name}/id={user.id})"))

        if args.sheet_b:
            rows = si.read_csv(args.sheet_b, encoding=args.encoding)
            parsed_b = si.parse_sheet_b(rows, year=args.year)
            print(f"[기업 명단: {args.label or Path(args.sheet_b).stem}] "
                  f"헤더 {(parsed_b.header_row or 0) + 1}행 인식 · 기업 {len(parsed_b.companies)}개")
            report_b = si.apply_sheet_b(db, parsed_b, dry_run=args.dry_run)
            print(report_b.as_text("기업 명단 → 딜 기업 DB"))

        if getattr(args, "financials_url", None):
            path = fetch_sheet(args.financials_url)
            print(f"[다운로드] 재무 시트 → {path}")
            rows = si.read_csv(path, encoding=args.encoding)
            rep = si.apply_company_financials(db, rows, dry_run=args.dry_run)
            print(rep.as_text("기업 재무 → 딜 기업 DB"))

        if args.dry_run:
            print("\n※ --dry-run: DB에 아무것도 쓰지 않았습니다.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
