"""투자컨설턴트 현황 시트 가져오기 — **한 담당자 몫씩.**

원본이 `IR 스타트업` · `경영본부 전달기업` · `월간 계약 업무현황표` 로 나뉘어
있고, 같은 탭을 컨설턴트 여럿이 각자의 시트로 들고 있다. 그래서 이 스크립트가
지우고 넣는 범위는 **탭 하나가 아니라 (탭, 담당자) 하나**다.

    python scripts/import_consulting.py 파일.xlsx --owner 7            # 미리보기
    python scripts/import_consulting.py 파일.xlsx --owner 7 --apply

## `--owner` 는 반드시 준다

예전에는 안 줘도 돌았고, 그때 줄은 `user_id = NULL` 로 들어갔다. 그 상태는
**두 가지가 한꺼번에 나쁘다.**

  · 넣은 줄을 아무도 못 고친다. 주인 없는 줄은 관리자만 손댈 수 있고
    (`routers/consulting.py` 의 `may_edit_row`), 컨설턴트 화면에는 아예 안 뜬다.
  · 무엇을 지울지가 정해지지 않는다. 지우는 범위가 담당자로 좁혀진 지금,
    담당 없는 실행은 "주인 없는 줄만 지운다" 로 읽어야 하는데 그것을 노리고
    부르는 사람은 없다. 대개는 `--owner` 를 빠뜨린 것이다.

그래서 **안 주면 아무것도 하지 않고 멈춘다.** 지우는 것이 섞여 있는 도구는
기본값이 조용히 도는 쪽이면 안 된다.

## 지우는 것도 그 담당자 것만

시트가 원본이라 통째로 갈아 끼우는 것이 맞다(맞춰 넣으면 시트에서 지운 줄이
앱에 남는다). 다만 **탭 이름만 보고 지우면** `--owner 7` 로 한 사람 것을 넣는
순간 같은 탭에 있던 다른 담당자의 줄이 통째로 사라진다. 지우는 조건에
담당자를 같이 건다.

**월 칸은 지우지 않는다.** 칸은 이제 탭마다 한 벌이라
(`models.ConsultingColumn`) 지우면 그 달 기록이 팀 전체의 줄에서 사라진다.
이름이 같으면 이미 서 있는 칸을 그대로 쓰고, 없는 이름만 새로 만든다.

## 시트 탭 이름 ≠ 앱 탭 이름

사람이 들고 있는 xlsx 의 탭 이름은 앱과 조금씩 다르다(`IR 스타트업` /
`경영본부 전달기업`). 파일을 고치라고 하는 것보다 여기서 받아 주는 편이
안전하다 — 안 받아 주면 **옛 이름의 유령 탭이 생기고** 그때부터 같은 명단이
두 탭으로 갈린다(0039 가 고쳐야 했던 사고다). 띄어쓰기 차이도 같은 사고를
내므로 견줄 때 공백을 다 떼고 본다.

컬럼 순서는 시트마다 다르다(`경영본부 전달 기업` 은 기업명이 뒤에 있다).
자리가 아니라 **이름으로** 찾는다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ConsultingColumn, ConsultingCompany  # noqa: E402
from app.routers.consulting import split_contract_line  # noqa: E402
from app.services import consulting_sheets as cs  # noqa: E402

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


def squash(name: str) -> str:
    """견줄 때 쓰는 모양 — **공백을 다 뗀다.**

    `경영본부 전달기업` 과 `경영본부 전달 기업` 은 사람 눈에 같은 탭인데
    글자로는 다르다. 앞뒤만 떼서는 가운데 띄어쓰기 차이를 못 잡고, 못 잡으면
    유령 탭이 하나 생긴다. 탭 이름은 사람이 손으로 적는 값이라 이 차이가
    실제로 난다.
    """
    return re.sub(r"\s+", "", name or "")


# 원본 파일의 시트 이름 → 앱의 **탭 열쇠**(`ConsultingSheet.kind`).
#
# 이름이 아니라 열쇠로 짝짓는다. 앱의 탭 이름은 화면에서 고치는 값이라
# (`ConsultingSheet.label`) 여기에 이름을 적어 두면 누가 탭 이름을 고친 날
# 짝이 조용히 끊어지고, 그날부터 들어온 줄이 유령 탭으로 간다. 열쇠는 안 바뀐다.
#
# 열쇠는 공백을 뗀 모양으로 찾는다(`squash`).
SHEET_ALIAS = {
    # 첫 탭은 이름이 여러 번 바뀌었다(`중요 스타트업` → `스타트업` →
    # `관리 스타트업`). 사람이 들고 있는 xlsx 는 여전히 옛 이름이고, 시트 쪽
    # 이름은 또 `IR 스타트업` 이다. 전부 같은 탭이다.
    "중요스타트업": cs.STARTUP,
    "스타트업": cs.STARTUP,
    "관리스타트업": cs.STARTUP,
    "IR스타트업": cs.STARTUP,
    "경영본부전달기업": cs.HANDOVER,
    "월간계약업무현황표": cs.CONTRACT,
}


def resolve_sheet(db, raw: str) -> str:
    """시트 탭 이름 → **지금 앱이 쓰는 탭 이름.**

    1. 아는 이름이면 열쇠로 바꿔 지금 이름을 읽어 온다(위 `SHEET_ALIAS`).
    2. 모르는 이름이라도 앱에 같은 모양의 탭이 이미 있으면 그 이름을 쓴다 —
       띄어쓰기만 다른 탭을 새로 만들지 않기 위해서다.
    3. 둘 다 아니면 앞뒤 공백만 떼고 그대로 쓴다. 사람이 시트를 올려 만든
       탭도 그대로 서므로(`sheet_tabs`) 새 탭이 되는 것이 맞다.
    """
    key = squash(raw)
    kind = SHEET_ALIAS.get(key)
    if kind:
        sheet = cs.by_kind(db).get(kind)
        if sheet is not None:
            return sheet.label
    for label in cs.labels(db):
        if squash(label) == key:
            return label
    return (raw or "").strip()


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


# `월간 계약 업무현황표` 는 다른 두 시트와 모양이 다르다. 머리글이 있는 표가
# 아니라 **월 묶음 + 슬래시 한 줄**이다:
#
#     6월  (무료계약 2개사 / 유료계약 3개사)
#     기업명 / 계약금액 / 성공보수율 / 계약일
#     ○○○/ 무료/ 3.5%/ 미정
#
# 이 모양 때문에 처음엔 건너뛰었는데, 그러면 화면에서 이 표를 아예 볼 수 없다.
#
# 처음에는 슬래시 줄을 `company_name` 에 통째로 넣었다. 한 칸에 뭉쳐 있으면
# 계약금으로 거를 수도, 보수율만 고칠 수도 없어서 **시트가 적어 둔 머리글
# 순서대로 칸에 나눠 담는다**(`기업명 / 계약금액 / 성공보수율 / 계약일`).
# 나누는 규칙은 앱과 같은 것을 쓴다 — 여기 따로 적으면 다시 올릴 때마다 화면과
# 다른 모양이 들어간다. 나누기 전 줄은 `source_line` 에 그대로 남는다.
_MONTH_LINE = re.compile(r"^\s*(\d{1,2})\s*월")
_HEADER_LINE = re.compile(r"기업명\s*/")


def parse_contract_sheet(ws) -> list:
    """월 묶음 자유 서식 → 줄 목록."""
    out, month = [], ""
    for r in range(1, ws.max_row + 1):
        label = text(ws.cell(r, 1).value)
        body = text(ws.cell(r, 2).value)

        m = _MONTH_LINE.match(label) or _MONTH_LINE.match(body)
        if m and "/" not in (label + body).replace(m.group(0), "", 1)[:3]:
            month = f"{int(m.group(1))}월"
            continue
        if not body or _HEADER_LINE.search(body):
            continue          # 머리글 줄은 값이 아니다
        if "/" not in body:
            continue          # 계약 줄이 아니다

        # 무료·유료는 줄 안에 적혀 있다. 왼쪽 라벨은 병합 때문에 줄과
        # 어긋나 있어(3행이 '무료 계약', 4행이 '유료 계약') 믿을 수 없다.
        kind = "유료" if "유료" in body else ("무료" if "무료" in body else "")
        out.append({"month": month, "kind": kind, "line": body})
    return out


def header_row(ws) -> int:
    """머리글 행. 시트마다 4~5행이다(위에 제목·요약이 붙어 있다)."""
    for r in range(1, 8):
        labels = [text(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
        if sum(1 for x in labels if x) >= 4 and any("기업" in x for x in labels):
            return r
    return 1


def wipe(db, sheet: str, owner: int) -> int:
    """이 (탭, 담당자) 의 줄을 지우고 **몇 줄을 지웠는지** 돌려준다.

    담당자를 조건에 같이 거는 것이 이 함수의 전부다 — 탭 이름만 보고 지우면
    같은 탭에 있던 다른 담당자의 줄이 통째로 사라진다.

    수를 먼저 세는 것은 미리보기 때문이다. `--apply` 없이도 **무엇이 지워질지**
    말할 수 있어야 사람이 사고를 막는다.
    """
    where = (ConsultingCompany.sheet == sheet,
             ConsultingCompany.user_id == owner)
    n = db.execute(select(func.count()).select_from(ConsultingCompany)
                   .where(*where)).scalar_one()
    db.execute(delete(ConsultingCompany).where(*where))
    return n


def month_columns(db, sheet: str, labels) -> tuple:
    """이 탭의 월 칸. **이름이 같으면 이미 있는 것을 그대로 쓴다.**

    지우지 않는다 — 칸은 탭마다 한 벌이라(`models.ConsultingColumn`) 지우면
    그 달 기록이 팀 전체의 줄에서 사라진다. 두 번째 담당자의 시트를 넣을 때
    그 사람 달이 이미 서 있으면 새로 만들 것이 없고, 그것이 맞는 결과다.
    """
    have = {c.label: c for c in db.execute(
        select(ConsultingColumn).where(ConsultingColumn.sheet == sheet)
        .order_by(ConsultingColumn.position, ConsultingColumn.id)
    ).scalars().all()}
    out, made = [], 0
    for label in labels:
        col = have.get(label)
        if col is None:
            col = ConsultingColumn(sheet=sheet, label=label,
                                   position=len(have) + made)
            db.add(col)
            have[label] = col
            made += 1
        out.append(col)
    db.flush()
    return out, made


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="투자컨설턴트 현황 가져오기")
    ap.add_argument("path")
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    # **기본값을 두지 않는다.** 예전에는 0(= 담당 없음)이 기본이라, 빠뜨리고
    # 부르면 주인 없는 줄이 조용히 들어갔다. 위 모듈 설명 참고.
    ap.add_argument("--owner", type=int,
                    help="이 표의 주인(users.id). 반드시 준다 — 지우고 넣는 "
                         "범위가 이 사람 몫이다")
    args = ap.parse_args(argv)

    if not args.owner:
        print("--owner 를 주세요. 이 표는 줄마다 담당이 붙습니다.\n"
              "  · 담당 없이 넣은 줄은 컨설턴트 화면에 안 뜨고 관리자만 고칠 수 "
              "있습니다.\n"
              "  · 지우는 범위도 담당자로 좁혀져 있어, 담당이 없으면 무엇을 "
              "지울지가 정해지지 않습니다.\n"
              "  예: --owner 7", file=sys.stderr)
        return 2

    wb = openpyxl.load_workbook(args.path)
    db = SessionLocal()
    # **탭을 먼저 세워 둔다.** `cs.ensure` 는 없을 때 바로 커밋하는데
    # (`services/consulting_sheets.py` 참고), 그 자리가 아래 반복문 한가운데면
    # 미리보기 도중에 앞 탭에서 지운 줄이 함께 커밋된다 — `--apply` 를 안 붙인
    # 사람이 자료를 잃는다. 아무것도 안 건드린 지금 한 번 부르면 아래에서는
    # 다시 커밋할 일이 없다.
    cs.ensure(db)
    total = removed = 0

    print(f"담당(users.id) {args.owner} 의 표로 넣습니다.\n")
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet = resolve_sheet(db, sheet_name)
        moved = "" if squash(sheet) == squash(sheet_name) else f"  ← 시트 `{sheet_name}`"
        # 계약 현황표는 머리글 있는 표가 아니라 월 묶음 자유 서식이다.
        if cs.kind_of(db, sheet) == cs.CONTRACT:
            lines = parse_contract_sheet(ws)
            gone = wipe(db, sheet, args.owner)
            removed += gone
            for pos, item in enumerate(lines, start=1):
                parts = split_contract_line(item["line"])
                db.add(ConsultingCompany(
                    sheet=sheet, position=pos, user_id=args.owner,
                    region=item["month"],            # 어느 달의 계약인가
                    management=item["kind"],         # 계약여부 — 무료 / 유료
                    # 나누기 전 한 줄. 나눈 결과가 틀렸을 때 여기서 다시 나눈다.
                    source_line=item["line"],
                    company_name=parts.get("company_name") or item["line"],
                    contract_fee=parts.get("contract_fee"),
                    success_fee=parts.get("success_fee"),
                    meeting_at=parts.get("meeting_at")))   # 계약일
            total += len(lines)
            print(f"  {sheet:22} 지움 {gone:3}줄 → 넣음 {len(lines):3}줄 "
                  f"(월 묶음){moved}")
            continue

        hr = header_row(ws)
        head = [(c, text(ws.cell(hr, c).value)) for c in range(1, ws.max_column + 1)]
        if not any("기업" in h for _c, h in head):
            print(f"  건너뜀 (표가 아님): {sheet_name}")
            continue

        where = {}
        for label, field in FIELDS:
            col = next((c for c, h in head if label in h), None)
            if col is not None:
                where[field] = col
        month_cols = [(c, h) for c, h in head if MONTH_MARK in h]

        # **이 담당자 몫만** 갈아 끼운다. 탭 이름만 보고 지우면 같은 탭에 있던
        # 다른 담당자의 줄이 통째로 사라진다.
        gone = wipe(db, sheet, args.owner)
        removed += gone

        cols, made = month_columns(db, sheet, [h for _c, h in month_cols])
        cols = list(zip([c for c, _h in month_cols], cols))

        n = 0
        for r in range(hr + 1, ws.max_row + 1):
            name = text(ws.cell(r, where["company_name"]).value) if "company_name" in where else ""
            if not name:
                continue
            row = ConsultingCompany(sheet=sheet, position=n + 1, company_name=name,
                                    user_id=args.owner)
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
        print(f"  {sheet:22} 지움 {gone:3}줄 → 넣음 {n:3}개사 "
              f"· 월 칸 {len(cols)}개 중 {made}개 새로{moved}")

    print(f"\n합계  지울 줄 {removed}개(담당 {args.owner} 몫) → 넣을 줄 {total}개")
    print("다른 담당자의 줄은 건드리지 않습니다.")
    if args.apply:
        db.commit()
        print("→ 저장했습니다.")
    else:
        db.rollback()
        print("→ 미리보기입니다. 실제로 넣으려면 --apply 를 붙이세요.")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
