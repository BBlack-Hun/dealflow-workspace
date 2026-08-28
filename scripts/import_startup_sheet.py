"""스타트업 리마인드 명단 가져오기 — **이미 있는 줄을 채운다.**

이 명단만 성격이 다르다. 다른 탭은 **딜을 받을 투자사**인데 여기는 **우리가
챙기는 스타트업**이고, 기업명·성함이 따로 적히며 사업분야·계약여부·성공보수율
같은 칸이 붙는다. 그래서 이 명단은 `투자사 명함` 이 아니라 `스타트업 리마인드`
배치로 세운다(`app/services/contact_columns.py`).

## 새로 만들지 않고 채운다

앱에 이미 서른두 줄이 들어와 있는데 이름·연락처만 채워져 있었다. 다시 만들면
**같은 사람이 두 줄**이 된다. 기업명으로 맞춰 이미 있는 줄을 채우고, 못 맞춘
줄은 만들지 않고 **적어서 알린다** — 조용히 새로 만들면 그게 두 줄이 된다.

## 명단 이름은 인자로 받는다

코드에 이름을 박아 두면 다음 명단에서 또 박아야 하고, 박는 것을 잊은 곳만
조용히 옛 동작을 한다. 무엇을 어느 명단으로 넣을지는 부르는 사람이 정한다.

## 달마다 늘어나는 칸

`7월 리마인드 문자 (7/28)` · `7월 리마인드 TEL` · `7월 카톡 연결` 은 한 달에
세 칸씩 늘어난다. 고정 칸으로 알아본 것 말고 **남는 머리글 전부**를 월별 칸
(`ContactColumn`)으로 세운다 — 8월 시트를 그대로 올리면 8월 칸이 저절로 생긴다.

    python scripts/import_startup_sheet.py 파일.csv --sheet "명단 이름"
    python scripts/import_startup_sheet.py 파일.csv --sheet "명단 이름" --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ContactColumn, RefSheet, VcContact  # noqa: E402
from app.services import contact_columns as cc  # noqa: E402
from app.services import sheet_owner  # noqa: E402
from app.services import spreadsheet as sp  # noqa: E402

# 시트 머리글(**포함**으로 찾는다) → 담당자 모델의 칸.
#
# 포함으로 찾는 이유는 머리글에 줄바꿈과 설명이 섞여 있어서다
# (`한줄 소개\n예시) 사업분야 | …`). 완전 일치로 찾으면 그런 칸이 통째로 빠진다.
FIELDS = [
    ("기업명", "firm"),
    ("성함", "name"),
    ("연락처", "phone"),
    ("이메일", "email"),
    ("메모", "memo"),
]

# 시트 머리글 → 그 명단에만 있는 칸(`VcContact.notes` 의 고정 키).
# 배치가 정한 키를 그대로 쓴다 — 여기서 새 이름을 지으면 화면이 못 찾는다.
NOTES = [
    ("IR 자료 회신", "ir_reply"),
    ("사업분야 대분류", "sector_major"),
    ("소분류", "sector_minor"),
    ("기업구분", "company_kind"),
    ("한줄 소개", "one_liner"),
    ("IR dack", "ir_deck"),
    ("계약여부", "contract"),
    ("성공보수율", "success_fee"),
]


def norm(value) -> str:
    """칸 하나를 글자로. 줄바꿈은 남긴다 — 메모의 줄바꿈이 곧 대화 단위다."""
    if value is None:
        return ""
    return str(value).replace("\r", "").strip()


def flat(value) -> str:
    """머리글용. 줄바꿈을 공백으로 편다(머리글 한 칸에 두 줄로 들어 있다)."""
    return " ".join(norm(value).split())


def has_row_no(value) -> bool:
    """시트의 `NO` 칸에 번호가 있는가.

    표 아래에 운영 가이드가 줄글로 붙어 있어서, 기업명 칸에 그 문장이 들어오면
    담당자가 되어 버린다(예전에 서른여덟 줄이 그렇게 들어갔다).

    글자 길이나 문장부호로 가르려 했더니 양쪽으로 틀렸다 — 멀쩡한 담당자를
    길다고 지우고, 정작 `안녕하세요 대표님` 은 짧아서 통과시켰다.

    **번호가 붙은 줄만 표의 줄이다.** 짐작이 아니라 시트가 직접 말해 주는
    사실이라 양쪽 다 틀리지 않는다.
    """
    try:
        return float(norm(value)) > 0
    except (TypeError, ValueError):
        return False


def find_header(rows) -> int:
    """머리행은 위치가 아니라 **내용**으로 찾는다.

    시트 위쪽에 제목·빈 줄이 있고 사람이 행을 넣다 빼다 하므로 '첫 줄'이라고
    못 박으면 곧 깨진다.
    """
    for i, row in enumerate(rows[:30]):
        cells = [flat(c) for c in row]
        if "NO" in cells and any("기업명" in c for c in cells):
            return i
    return -1


def parse(rows) -> dict:
    """시트 → {월별 칸 이름들, 줄들}."""
    at = find_header(rows)
    if at < 0:
        return {"columns": [], "items": [], "skipped": []}
    header = [flat(c) for c in rows[at]]

    def find(token):
        return next((i for i, h in enumerate(header) if token in h), None)

    where = {f: find(t) for t, f in FIELDS}
    notes_at = {k: find(t) for t, k in NOTES}
    used = {i for i in list(where.values()) + list(notes_at.values()) if i is not None}
    used.add(find("NO"))
    # 남는 머리글이 곧 **달마다 늘어나는 칸**이다. 목록을 손으로 적어 두면
    # 8월 시트를 올렸을 때 그 세 칸이 조용히 버려진다.
    months = [(i, header[i]) for i in range(len(header))
              if i not in used and header[i]]

    items, skipped = [], []
    for row in rows[at + 1:]:
        cells = list(row) + [""] * (len(header) - len(row))
        firm = norm(cells[where["firm"]]) if where.get("firm") is not None else ""
        if not firm:
            continue
        if not has_row_no(cells[0] if cells else None):
            skipped.append(firm)      # 표 아래에 붙은 운영 가이드 줄
            continue
        item = {"fields": {}, "notes": {}}
        for field, i in where.items():
            if i is not None and norm(cells[i]):
                item["fields"][field] = norm(cells[i])
        for key, i in notes_at.items():
            if i is not None and norm(cells[i]):
                item["notes"][key] = norm(cells[i])
        item["months"] = {label: norm(cells[i]) for i, label in months
                          if norm(cells[i])}
        items.append(item)
    return {"columns": [label for _i, label in months],
            "items": items, "skipped": skipped}


def guide_text(rows) -> str:
    """표 **아래에 붙은 줄글**(운영 프로세스·스크립트)을 그대로 모은다.

    시트 한 장에 두 가지가 들어 있다 — 위는 표, 아래는 업무 안내다. 표만
    가져오면 안내는 매번 구글 시트를 따로 열어 봐야 하고, 안내까지 표로 읽으면
    문장이 칸에 잘려 사라진다. 그래서 **번호 없는 줄만** 줄글로 따로 담는다.

    참고 자료로 넣는 이유는 하나 더 있다. 이 안내를 표 밑에 그대로 펼치면 화면이
    복잡해진다 — 참고 자료는 탭 단추로 열고 닫는 자리라 필요할 때만 편다.
    """
    at = find_header(rows)
    out = []
    for row in rows[at + 1:]:
        if has_row_no(row[0] if row else None):
            continue                 # 표의 줄은 명단으로 들어간다
        cells = [norm(c) for c in row]
        cells = [c for c in cells if c]
        if cells:
            # 한 행의 칸들은 줄바꿈으로 잇는다(`구분 | 진행 순서` 두 칸짜리 행).
            out.append("\n".join(cells))
    return "\n\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="스타트업 리마인드 명단 가져오기")
    ap.add_argument("path")
    ap.add_argument("--sheet", required=True,
                    help="앱의 명단(탭) 이름. 이 명단의 줄을 채운다")
    ap.add_argument("--tab", default=None,
                    help="엑셀 파일 안의 탭 이름(여러 탭이 있을 때)")
    ap.add_argument("--guide", default="업무 프로세스",
                    help="표 아래 줄글을 담을 참고 자료 이름")
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args()

    data = Path(args.path).read_bytes()
    rows = sp.read_rows(args.path, data, args.tab)
    parsed = parse(rows)
    guide = guide_text(rows)
    if not parsed["items"]:
        print("읽을 내용을 찾지 못했습니다. `NO` 와 `기업명` 이 있는 시트인지 확인하세요.")
        return 1

    db = SessionLocal()
    existing = [c for c in db.execute(select(VcContact)).scalars().all()
                if args.sheet in sheet_owner.labels_of(c.source_sheet)]
    by_firm = {(c.firm or "").strip(): c for c in existing}

    matched = [i for i in parsed["items"] if i["fields"].get("firm", "") in by_firm]
    missing = [i["fields"].get("firm", "") for i in parsed["items"]
               if i["fields"].get("firm", "") not in by_firm]

    print(f"명단 `{args.sheet}`")
    print(f"  시트 {len(parsed['items'])}줄 · 앱에 있는 줄 {len(existing)}개 "
          f"· 맞은 줄 {len(matched)}개")
    print(f"  달마다 늘어나는 칸 {len(parsed['columns'])}개: "
          f"{', '.join(parsed['columns']) or '없음'}")
    if parsed["skipped"]:
        # 조용히 버리면 몇 줄이 왜 빠졌는지 알 수 없다.
        print(f"  건너뜀 {len(parsed['skipped'])}줄 (번호가 없는 줄 = 표 아래 줄글)")
    print(f"  참고 자료 `{args.guide}`: 줄글 {len(guide)}자")
    if missing:
        # **새로 만들지 않는다.** 만들면 같은 사람이 두 줄이 된다.
        print(f"  ⚠ 앱에서 못 찾은 기업 {len(missing)}개 — 새로 만들지 않습니다:")
        for name in missing[:5]:
            print(f"      {name}")

    if not args.apply:
        print("\n미리보기입니다. 넣으려면 --apply 를 붙이세요.")
        db.close()
        return 0

    # 명단 설정 — 이 명단은 스타트업 배치로 세우고, 투자사로 세지 않는다.
    # 화면에서 되돌릴 수 있다(탭 옆 [숨김 해제]).
    owner = sheet_owner.ensure(db, args.sheet)
    owner.layout = cc.STARTUP
    owner.is_hidden = 1

    # 월별 칸 먼저 — 줄의 값이 칸 id 를 키로 쓴다.
    columns = {c.label: c for c in cc.month_columns(db, args.sheet)}
    for pos, label in enumerate(parsed["columns"]):
        if label not in columns:
            col = ContactColumn(sheet=args.sheet, label=label, position=pos)
            db.add(col)
            columns[label] = col
    db.flush()

    for item in matched:
        contact = by_firm[item["fields"]["firm"]]
        for field, value in item["fields"].items():
            setattr(contact, field, value)
        values = cc.load_notes(contact.notes)
        values.update(item["notes"])
        for label, text in item["months"].items():
            values[cc.note_key(columns[label].id)] = text
        contact.notes = cc.dump_notes(values)

    # 표 아래 줄글 → 참고 자료.
    #
    # 예전에는 **시트 한 장을 통째로** 참고 자료에 넣어 두었다(표 32줄 + 안내
    # 42줄). 그러면 같은 서른두 사람이 명단에도, 참고 자료에도 있어 어느 쪽이
    # 최신인지 알 수 없다 — 이 저장소가 투자사 명단 탭을 참고 자료로 안 가져오는
    # 이유와 같다. 그래서 그 줄이 있으면 **줄글로 갈아 끼운다.**
    if guide:
        row = db.execute(
            select(RefSheet).where(RefSheet.title.in_([args.guide, args.sheet]))
        ).scalars().first()
        if row is None:
            row = RefSheet(page="contacts", position=99)
            db.add(row)
        row.title = args.guide
        row.page = "contacts"
        row.kind = "text"
        row.content_json = json.dumps({"body": guide}, ensure_ascii=False)
        # 넣어 놓고 꺼 두면 아무도 못 본다 — 참고 자료는 켜 둔 것이 기본이다.
        row.is_active = 1

    db.commit()
    print(f"\n{len(matched)}줄 채웠습니다 (칸 {len(parsed['columns'])}개).")
    if guide:
        print(f"참고 자료 `{args.guide}` 를 넣고 켰습니다.")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
