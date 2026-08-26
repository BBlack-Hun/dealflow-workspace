"""`스타트업(16)` 시트 가져오기 — 투자사 명단과 같은 표로.

이 시트만 성격이 다르다. 다른 탭은 **딜을 받을 투자사**인데 여기는 **우리가
챙기는 스타트업**이고, 사람(성함)과 회사(기업명)가 따로 적혀 있다. 모양은
같아서 같은 표에 탭 하나로 들어간다.

**연결 단계는 미착수로 둔다.** 딜 제안 관리는 `connected` 인 사람만 대상으로
고르는데, 스타트업이 그 목록에 섞이면 투자사에게 보낼 문구가 스타트업에게
나간다.

    python scripts/import_startup_sheet.py 파일.xlsx            # 미리보기
    python scripts/import_startup_sheet.py 파일.xlsx --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User, VcContact  # noqa: E402

SHEET = "스타트업(16)"
# 시트 컬럼(포함으로 찾는다) → 모델 칸
FIELDS = [
    ("기업명", "firm"),
    ("성함", "name"),
    ("연락처", "phone"),
    ("이메일", "email"),
    ("메모", "memo"),
    ("카톡 연결", "kakao_joined"),
    ("사업분야", "sectors"),
]


def _has_row_no(value) -> bool:
    """시트의 `NO` 칸에 번호가 있는가.

    표 아래에 운영 가이드가 줄글로 붙어 있어서, 기업명 칸에 그 문장이 들어오면
    담당자가 되어 버린다(실제로 38줄이 그렇게 들어갔다).

    글자 길이나 문장부호로 가르려 했더니 양쪽으로 틀렸다 — 멀쩡한 담당자
    `허승욱 Senior Analyst님(메일)` 을 길다고 지우고, 정작 `안녕하세요 대표님`
    은 짧아서 통과시켰다.

    **번호가 붙은 줄만 표의 줄이다.** 짐작이 아니라 시트가 직접 말해 주는
    사실이라 양쪽 다 틀리지 않는다(번호 있는 32줄 / 없는 38줄로 정확히 갈린다).
    """
    try:
        return float(str(value).strip()) > 0
    except (TypeError, ValueError):
        return False


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).replace("\r", "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ws = openpyxl.load_workbook(args.path)[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    header = [text(c) for c in rows[0]]
    where = {}
    for label, field in FIELDS:
        col = next((i for i, h in enumerate(header) if label in h), None)
        if col is not None:
            where[field] = col

    db = SessionLocal()
    owner = db.execute(select(User).where(User.role == "user")).scalars().first()
    if owner is None:
        print("담당 계정을 찾지 못했습니다.")
        return 1

    # 이 시트만 통째로 갈아 끼운다 — 맞춰 넣으면 시트에서 지운 줄이 남는다.
    existing = db.execute(
        select(VcContact).where(VcContact.source_sheet == SHEET)
    ).scalars().all()

    made, skipped = [], []
    for r in rows[1:]:
        firm = text(r[where["firm"]]) if "firm" in where else ""
        name = text(r[where["name"]]) if "name" in where else ""
        if not firm and not name:
            continue
        # 번호가 없는 줄은 표의 줄이 아니다 — 표 아래에 붙은 운영 가이드다.
        if not _has_row_no(r[0] if r else None):
            skipped.append(firm or name)
            continue
        item = {f: text(r[c]) for f, c in where.items() if c < len(r)}
        # 사람 이름이 비면 기업명으로 세운다 — 누구인지 모르는 줄을 만들지 않는다.
        item["name"] = item.get("name") or firm
        made.append(item)

    print(f"시트 {len(made)}줄 · 앱에 이미 있는 같은 시트 줄 {len(existing)}개")
    if skipped:
        # 조용히 버리면 몇 줄이 왜 빠졌는지 알 수 없다.
        print(f"  건너뜀 {len(skipped)}줄 (표 아래 줄글):")
        for v in skipped[:3]:
            print(f"     {v[:44]}…")
    for item in made[:5]:
        print(f"   {item.get('name','')} / {item.get('firm','')} / {item.get('phone','')}")
    if not args.apply:
        print("\n미리보기입니다. 넣으려면 --apply 를 붙이세요.")
        return 0

    for row in existing:
        db.delete(row)
    db.flush()
    for item in made:
        db.add(VcContact(
            user_id=owner.id, source_sheet=SHEET,
            # 딜 제안 관리는 connected 만 대상으로 고른다. 스타트업이 그
            # 목록에 섞이면 투자사에게 보낼 문구가 스타트업에게 나간다.
            connect_stage="not_started",
            channel_kakao=1, channel_email=1, status="active",
            **{k: v for k, v in item.items() if v}))
    db.commit()
    print(f"\n{len(made)}줄 넣었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
