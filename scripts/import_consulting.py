"""투자컨설턴트 현황 시트 가져오기.

원본이 `중요 스타트업` · `경영본부 전달 기업` 으로 나뉘어 있고 관리하는
사람이 다르다. 시트별로 통째로 갈아 끼운다 — 맞춰 넣으면 시트에서 지운
줄이 앱에 남는다.

컬럼 순서가 시트마다 다르다(`경영본부 전달 기업` 은 기업명이 뒤에 있다).
자리가 아니라 **이름으로** 찾는다.

월 컬럼(`8월 마지막주 리마인드 …`)도 시트마다 달라서 시트별로 만든다 —
섞으면 없는 달의 빈 칸이 생긴다.

    python scripts/import_consulting.py 파일.xlsx            # 미리보기
    python scripts/import_consulting.py 파일.xlsx --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ConsultingColumn, ConsultingCompany  # noqa: E402

# 시트 컬럼(포함으로 찾는다) → 모델 칸
FIELDS = [
    ("지역", "region"),
    ("미팅일", "meeting_at"),
    ("기업명", "company_name"),
    ("기업 관리", "management"),
    ("대표자", "ceo_name"),
    ("연락처", "phone"),
    ("이메일", "email"),
]
# 월 컬럼은 이 낱말이 들어간 칸으로 알아본다.
MONTH_MARK = "리마인드"


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    out = str(value).replace("\r", "").strip()
    # 구글 시트가 좁은 칸을 `#####` 로 내보낸다 — 값이 아니라 화면 표시다.
    if out and set(out) == {"#"}:
        return ""
    # `=ROW()-3` 같은 수식은 값이 아니다.
    return "" if out.startswith("=") else out


def header_row(ws) -> int:
    """머리글 행. 시트마다 4~5행이다(위에 제목·요약이 붙어 있다)."""
    for r in range(1, 8):
        labels = [text(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
        if sum(1 for x in labels if x) >= 4 and any("기업" in x for x in labels):
            return r
    return 1


def main() -> None:
    ap = argparse.ArgumentParser(description="투자컨설턴트 현황 가져오기")
    ap.add_argument("path")
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.path)
    db = SessionLocal()
    total = 0

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet = sheet_name.strip()
        hr = header_row(ws)
        head = [(c, text(ws.cell(hr, c).value)) for c in range(1, ws.max_column + 1)]
        if not any("기업" in h for _c, h in head):
            print(f"  건너뜀 (표가 아님): {sheet}")
            continue

        where = {}
        for label, field in FIELDS:
            col = next((c for c, h in head if label in h), None)
            if col is not None:
                where[field] = col
        month_cols = [(c, h) for c, h in head if MONTH_MARK in h]

        # 시트를 통째로 갈아 끼운다 — 맞춰 넣으면 지운 줄이 남는다.
        db.execute(delete(ConsultingCompany).where(ConsultingCompany.sheet == sheet))
        db.execute(delete(ConsultingColumn).where(ConsultingColumn.sheet == sheet))

        cols = []
        for pos, (c, label) in enumerate(month_cols):
            col = ConsultingColumn(sheet=sheet, label=label, position=pos)
            db.add(col)
            cols.append((c, col))
        db.flush()

        n = 0
        for r in range(hr + 1, ws.max_row + 1):
            name = text(ws.cell(r, where["company_name"]).value) if "company_name" in where else ""
            if not name:
                continue
            row = ConsultingCompany(sheet=sheet, position=n + 1, company_name=name)
            for field, c in where.items():
                if field == "company_name":
                    continue
                value = text(ws.cell(r, c).value)
                if value:
                    setattr(row, field, value)
            notes = {}
            for c, col in cols:
                value = text(ws.cell(r, c).value)
                if value:
                    notes[str(col.id)] = value
            row.notes = json.dumps(notes, ensure_ascii=False)
            db.add(row)
            n += 1
        total += n
        print(f"  {sheet:24} {n:3}개사 · 월 컬럼 {len(cols)}개")

    print(f"\n합계 {total}개사")
    if args.apply:
        db.commit()
        print("→ 저장했습니다.")
    else:
        db.rollback()
        print("→ 미리보기입니다. 실제로 넣으려면 --apply 를 붙이세요.")
    db.close()


if __name__ == "__main__":
    main()
