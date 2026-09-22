"""`기업 관리` 한 칸에 뭉쳐 있던 **상태 : 상세** 를 두 칸으로 나눈다.

    python scripts/split_consulting_management.py                 # 미리보기
    python scripts/split_consulting_management.py --apply         # 실제로 옮김
    python scripts/split_consulting_management.py --revert         # 되돌림
    python scripts/split_consulting_management.py --revert-from 백업.json

## 이 스크립트가 있는 이유 — **이주가 아니라 사람이 돌린다**

칸을 세우는 것은 이주다(0079). 값을 옮기는 것은 아니다. `alembic upgrade` 는
컨테이너가 뜨면서 저절로 도는 자리라(`RUN_MIGRATIONS=1`), 거기서 운영 자료를
바꾸면 **아무도 보고 있지 않을 때** 바뀌고 결과가 틀려도 알아챌 사람이 없다.
0040 이 계약 줄을 이주 안에서 나눈 것은 그때 값이 다섯 줄이었기 때문이고,
지금은 마흔 줄 넘게 적혀 있는 운영 중인 표다.

그래서 **미리보기가 기본**이다. `--apply` 를 줘야 쓴다.

## 무엇을 어떻게 나누나 — **시트를 적은 사람이 찍어 둔 `:` 하나만 본다**

원본 머리글이 `기업 관리 [ 드랍 이유 상세하게 기입 / 관리중 / 백업팀으로
전환 ]` 이다. 한 칸에 **상태**와 **그 이유를 상세하게 적은 글**을 같이 적으라고
했고, 값이 `드랍 : 몇 차례 …` 처럼 `상태 : 상세` 꼴로 적혀 있다.

    기업 관리 `드랍 : 몇 차례 …`  →  기업 관리 `드랍` · 기업 내용 `몇 차례 …`

**구분자가 없는 줄은 손대지 않는다.** `관리 중` 처럼 상태만 적힌 줄도 있고,
상태 낱말이 아예 없는 줄도 있다. 그런 줄은 어디까지가 상태인지 **아무도 정한
적이 없으므로**, 빈칸에서 갈라 넣으면 앱이 쓴 적 없는 경계를 지어내는 것이
된다. 이 저장소는 적힌 것을 고쳐 쓰지 않는다(`split_contract_line` 참고).

## 왜 원본에서 **비우나** (남겨 두지 않나)

갈라내는 까닭이 바로 그것이다. 칩·KPI·머리글 필터가 `기업 관리` 칸의 낱말로
갈래를 세는데(`services/consulting_status.py` 가 `관리`·`드랍`·`백업팀` 을
찾는다), 상세 글이 그 칸에 남아 있으면 **갈라내기 전과 똑같이** 우연히 든
낱말 하나로 엉뚱한 갈래에 걸린다. 두 벌로 두면 고치는 자리도 둘이 되어 곧
서로 다른 말이 된다.

**그래도 값은 안 잃는다.** 지우는 것이 아니라 옮기는 것이고, 옮기기 전의 한
줄을 백업 파일에 그대로 담는다(아래). 이 스크립트는 **갈래가 바뀌는 줄이
하나라도 있으면 아예 멈춘다** — 나누고 나서 `관리 중` 이던 줄이 `기타 메모`
로 떨어지면 위 KPI 가 조용히 달라진다.

## 되돌리기

  1. `--revert` — DB 에서 되짚는다. `기업 내용` 이 있는 줄을
     `기업 관리 : 기업 내용` 으로 다시 붙이고 `기업 내용` 을 비운다.
     구분자는 옮길 때 쓴 그대로(`" : "`)다.
  2. `--revert-from 백업.json` — **글자 그대로** 되돌린다. 옮기기 전 값을
     통째로 담아 둔 파일이라 구분자 앞뒤 공백까지 원본과 같아진다.
     ①이 못 맞추는 줄(`드랍:몇 차례` 처럼 공백 없이 적힌 줄)이 있으면 이쪽을
     쓴다 — `--apply` 가 그런 줄이 몇 개인지 미리 세어 알려 준다.

**`alembic downgrade` 로는 안 돌아온다.** 그쪽은 칸을 지우는 일이라, 옮겨 둔
상세 글이 칸과 함께 사라진다. 내리기 전에 반드시 여기를 먼저 돌려라 —
0079 의 머리글에 같은 말이 적혀 있다.

## 백업 파일

`--apply` 는 **쓰기 전에** 백업을 먼저 낸다. 기본 자리는
`data/consulting_management_split_<날짜시각>.json` 이고 `--backup` 으로 바꾼다.
파일을 못 쓰면 **아무 것도 안 쓰고 멈춘다** — 되돌릴 근거 없이 운영 자료를
바꾸지 않는다.

    {"revision": "0079_…", "at": "2026-09-21T14:30:00+09:00",
     "rows": [{"id": 12, "management": "드랍 : 몇 차례 …"}, …]}

**값이 들어 있는 파일이다.** 저장소에 커밋하지 마라(`data/` 는 `.gitignore`
안이다).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                   # noqa: E402

from app import clock                                           # noqa: E402
from app.db import SessionLocal                                 # noqa: E402
from app.models import ConsultingCompany                        # noqa: E402
from app.services import consulting_sheets as cs                # noqa: E402
from app.services import consulting_status as status            # noqa: E402

#: 옮길 때 쓰는 구분자 — 되돌릴 때도 이것으로 다시 붙인다.
#: 시트에 실제로 적혀 있는 꼴이 이것이다(개발 자료 22줄 전부 `' : '`).
JOIN = " : "

#: 가르는 자리. **사람이 찍어 둔 `:` 하나만** 본다. 전각(`：`)도 같이 받는다 —
#: 한글 자판에서 그대로 눌러 적히는 글자라, 못 보면 그 줄만 조용히 안 나뉜다.
SPLIT = re.compile(r"\s*[:：]\s*")

#: 값을 옮기지 않는 탭. 저 탭의 `management` 는 `계약여부`(`무료`/`유료`)라는
#: **다른 물음**이라 갈라낼 상세가 없고, 화면에도 `기업 내용` 칸이 안 선다
#: (`routers/consulting.py` 의 `CONTRACT_COLUMNS`). `:` 가 없어 어차피 안
#: 나뉘지만, 나중에 누가 저 칸에 `유료 : 90만` 이라고 적는 날을 막아 둔다.
#:
#: **이름이 아니라 열쇠로 가린다** — 탭 이름은 화면에서 고칠 수 있는 값이라
#: (`ConsultingSheet.label`) 이름으로 적어 두면 이름을 바꾼 날 이 스크립트만
#: 옛 이름을 찾는다(`cs.CONTRACT` 로 찾아 지금 이름을 읽는다).


def _split(text: str) -> tuple:
    """`드랍 : 몇 차례 …` → `("드랍", "몇 차례 …")`. 못 나누면 `(원본, "")`."""
    body = text or ""
    m = SPLIT.search(body)
    if not m:
        return body.strip(), ""
    head, tail = body[:m.start()].strip(), body[m.end():].strip()
    if not head or not tail:
        # 한쪽이 비면 나눈 것이 아니다 — `: 메모` 처럼 앞이 비었거나
        # `드랍 :` 처럼 뒤가 빈 줄이다. 그대로 둔다.
        return body.strip(), ""
    return head, tail


def _plan(db, contract_labels: set) -> dict:
    """무엇을 어떻게 바꿀지. **아무 것도 안 쓴다.**"""
    rows = db.execute(select(ConsultingCompany)).scalars().all()
    move, keep, skipped, tag_change, lossy = [], 0, 0, [], 0
    for row in rows:
        body = (row.management or "").strip()
        if not body:
            continue
        if row.sheet in contract_labels:
            skipped += 1
            continue
        if (row.management_detail or "").strip():
            # 이미 상세가 들어 있는 줄. 덮으면 사람이 적어 둔 글이 사라진다.
            skipped += 1
            continue
        head, tail = _split(body)
        if not tail:
            keep += 1
            continue
        # **갈래가 바뀌면 안 된다.** 나누고 나서 `관리 중` 이던 줄이
        # `기타 메모` 로 떨어지면 위 KPI 와 칩 수가 조용히 달라진다.
        if status.tags(head) != status.tags(body):
            tag_change.append((row.id, status.tags(body), status.tags(head)))
        if head + JOIN + tail != body:
            # `--revert` 로 되붙일 때 원본과 글자가 달라지는 줄. 잃는 것은
            # 구분자 앞뒤 공백뿐이지만 몇 줄인지는 알려 준다
            # (글자 그대로 되돌리려면 `--revert-from` 을 쓴다).
            lossy += 1
        move.append({"id": row.id, "management": row.management,
                     "head": head, "tail": tail})
    return {"move": move, "keep": keep, "skipped": skipped,
            "tag_change": tag_change, "lossy": lossy, "total": len(rows)}


def _report(plan: dict) -> None:
    print(f"  줄 전체            {plan['total']}")
    print(f"  나눌 줄            {len(plan['move'])}")
    print(f"  그대로 둘 줄       {plan['keep']}  (구분자가 없다 — 손대지 않는다)")
    print(f"  건너뛴 줄          {plan['skipped']}  (계약 탭 · 이미 상세가 있는 줄)")
    print(f"  되붙일 때 공백이 달라지는 줄  {plan['lossy']}"
          "  (글자 그대로 되돌리려면 --revert-from)")
    if plan["tag_change"]:
        print(f"  ⚠ 갈래가 바뀌는 줄 {len(plan['tag_change'])}")
        for row_id, before, after in plan["tag_change"]:
            print(f"      #{row_id}: {before} → {after}")


def _backup_path(given: str) -> pathlib.Path:
    if given:
        return pathlib.Path(given)
    stamp = clock.now_iso()[:19].replace(":", "").replace("-", "").replace("T", "_")
    root = pathlib.Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"consulting_management_split_{stamp}.json"


def _apply(db, plan: dict, backup: pathlib.Path) -> None:
    """**백업을 먼저 쓴다.** 못 쓰면 아무 것도 안 바꾸고 멈춘다."""
    payload = {
        "revision": "0080_consulting_management_detail",
        "at": clock.now_iso(),
        "rows": [{"id": m["id"], "management": m["management"]}
                 for m in plan["move"]],
    }
    backup.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"  백업: {backup}")
    for m in plan["move"]:
        row = db.get(ConsultingCompany, m["id"])
        row.management = m["head"]
        row.management_detail = m["tail"]
    db.commit()
    print(f"  {len(plan['move'])}줄을 옮겼습니다.")


def _revert(db, contract_labels: set) -> None:
    """DB 에서 되짚는다 — `기업 관리` 와 `기업 내용` 을 다시 한 줄로."""
    rows = db.execute(select(ConsultingCompany)).scalars().all()
    n = 0
    for row in rows:
        tail = (row.management_detail or "").strip()
        if not tail or row.sheet in contract_labels:
            continue
        head = (row.management or "").strip()
        row.management = (head + JOIN + tail) if head else tail
        row.management_detail = None
        n += 1
    db.commit()
    print(f"  {n}줄을 되돌렸습니다(구분자 `{JOIN}`).")


def _revert_from(db, path: pathlib.Path) -> None:
    """백업 파일에서 **글자 그대로** 되돌린다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    n = missing = 0
    for item in data.get("rows", []):
        row = db.get(ConsultingCompany, item["id"])
        if row is None:
            missing += 1
            continue
        row.management = item["management"]
        row.management_detail = None
        n += 1
    db.commit()
    print(f"  {n}줄을 원본 글자 그대로 되돌렸습니다.")
    if missing:
        print(f"  ⚠ 줄 {missing}개는 지금 표에 없습니다(그 뒤에 지워진 줄).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="실제로 옮긴다. 안 주면 미리보기만 한다.")
    ap.add_argument("--revert", action="store_true",
                    help="DB 에서 되짚어 한 줄로 되붙인다.")
    ap.add_argument("--revert-from", default="",
                    help="백업 파일에서 원본 글자 그대로 되돌린다.")
    ap.add_argument("--backup", default="",
                    help="백업 파일 자리. 안 주면 data/ 밑에 날짜로 만든다.")
    ap.add_argument("--force", action="store_true",
                    help="갈래가 바뀌는 줄이 있어도 밀어붙인다. 웬만하면 쓰지 마라.")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # **이름이 아니라 열쇠로** 찾아 지금 이름을 읽는다. `ensure` 를 쓰는
        # 것은 이 앱의 다른 자리와 같다(`cs.kind_of` · `cs.labels` 전부 그렇다)
        # — 탭 줄이 아직 없는 DB(막 올린 빈 DB)에서 `all_sheets` 는 빈 목록을
        # 돌려주고, 그러면 계약 탭 줄이 **안 걸러진다.**
        contract_labels = {s.label for s in cs.ensure(db) if s.kind == cs.CONTRACT}
        if args.revert_from:
            _revert_from(db, pathlib.Path(args.revert_from))
            return 0
        if args.revert:
            _revert(db, contract_labels)
            return 0

        plan = _plan(db, contract_labels)
        print("기업 관리 → 기업 내용")
        _report(plan)
        if plan["tag_change"] and not args.force:
            print("\n갈래가 바뀌는 줄이 있어 멈춥니다 — 위 목록을 사람이 먼저 보세요.")
            print("(정말 밀어붙이려면 --force)")
            return 2
        if not args.apply:
            print("\n미리보기입니다. 실제로 옮기려면 --apply 를 주세요.")
            return 0
        if not plan["move"]:
            print("\n옮길 줄이 없습니다.")
            return 0
        _apply(db, plan, _backup_path(args.backup))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
