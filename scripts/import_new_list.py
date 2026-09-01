"""새 담당자의 스타트업 명단을 **새 명단(탭)으로 만든다.**

`import_startup_sheet.py` 는 **이미 있는 줄을 채우기만** 한다. 앱에 서른두 줄이
먼저 들어와 있었고, 다시 만들면 같은 사람이 두 줄이 되기 때문이다. 그 이유는
지금도 유효하다 — 그래서 그 스크립트는 그대로 두고 이걸 따로 둔다.

이번에는 사정이 반대다. 담당자가 새로 들어와 **명단 자체가 없다.** 없는 줄을
못 만들면 아무것도 못 넣는다. 그래서 만드는 길을 연다.

## 만들기와 채우기는 **부르는 사람이 고른다** (`--mode`)

기본값을 두지 않는다. 이 작업의 가장 큰 위험은 채울 자리에 실수로 새로 만들어
**같은 사람이 두 줄이 되는 것**이다. 두 줄이 되면 딜 소개가 두 번 나가고,
받는 쪽에서는 그게 우리 실수인지 알 길이 없다. 위험한 쪽이 기본값이 되어서는
안 되고, 안전한 쪽이 기본값이면 "왜 아무것도 안 들어갔지" 를 매번 겪는다.
**둘 다 적게 한다.**

    create  없는 번호는 만든다. 이미 있는 번호는 만들지 않고 **주인만 바꾼다.**
    fill    이 명단에 이미 있는 줄만 채운다. 없는 번호는 만들지 않고 알린다.

## 맞추는 열쇠는 **휴대폰 번호가 먼저**다

이름으로 이으면 동명이인 때문에 남의 방으로 발송이 나간다(한 이름이 셋인 적이
있었다 — `app/services/sourcing_link.py`). 번호는 사람마다 하나뿐이라 틀릴 여지가
없고, **앱 전체와 대조해도** 안전하다. 판정 자체도 베끼지 않고 `sourcing_link`
의 것을 그대로 부른다 — 두 벌이 되면 한쪽만 고쳐진다.

번호가 있는 줄은 여기서 끝난다. 번호가 **없는** 줄만 아래 한 가지를 더 본다.

## 번호가 없는 줄은 **기업명으로 잇는다**

막는 것은 "번호가 없는 줄" 자체가 아니라 **겹침을 못 알아보는 것**이다. 조용히
넣으면 나중에도 중복인지 알아낼 방법이 없고, 그때는 이미 딜 소개가 두 번 나간
뒤다. 그러니 겹침을 알아볼 다른 근거가 있으면 넣는다.

근거는 이 시트가 이미 들고 있다. **이 배치의 시트는 기업이 주인공이다** —
머리글이 `기업명`·`성함` 이고, `import_startup_sheet.py` 도 같은 시트를 기업명으로
맞춘다. 시트가 번호를 안 적어 둔 줄이 실제로 있고(`전화` 칸에 `x`·`o` 만 적힌
줄), 안 넣으면 그 기업이 통째로 사라진다.

  · **기업이 주인공인 배치에서만** 그렇게 한다(`contact_columns.firm_leads`).
    사람이 주인공인 명단에서 기업명으로 맞추면 같은 투자사의 다른 심사역이 한
    사람으로 뭉개진다. 명단 **이름**이 아니라 **배치**로 가르는 이유는
    `SheetOwner.layout` 주석 그대로다 — 이름을 코드에 적으면 다음 명단에서 또
    적어야 하고, 안 적은 곳만 조용히 옛 동작을 한다. 인자로 받지 않는 이유도
    같다(`import_startup_sheet.NOTES` 의 `원본NO` 주석과 같은 자리다). 팀원들의
    스타트업 워크북은 **한 틀**에서 나와 배치가 같은데, 부르는 쪽에 맡기면 다음
    시트에서 인자 하나를 빠뜨린 판만 여섯 줄을 조용히 버린다.
  · 대조는 **이 명단 안까지만** 한다. 앱 전체를 기업명으로 뒤지면 투자사 명단의
    `투자사명` 과 부딪힌다 — 한 투자사에 심사역이 여럿이라 이름 하나에 여러 줄이
    걸린다. 범위가 이 명단 하나면 틀려도 남의 명단에는 닿지 않는다
    (`import_investor_list.py` 가 번호 없는 줄을 이 명단 안에서 이름+투자사명으로
    찾는 것과 **같은 범위**다).
  · 기업명이 **하나뿐일 때만** 열쇠가 된다. 시트 안에서든 이 명단 안에서든 같은
    이름이 둘이면 어느 줄인지 알 수 없다 — `by_phone` 이 겹친 번호를 아예 빼는
    것과 같은 이유다.
  · 기업명이 **빈 줄**은 여전히 안 넣는다. 대조할 것이 아무것도 없다.
  · **조용히 넣지 않는다.** 몇 줄이 번호 없이 들어가는지, 무엇을 근거로 이었는지,
    무엇이 남는 위험인지를 미리보기와 적용 출력에 적는다.

남는 위험은 셋이고 셋 다 화면에 적는다 — ① 같은 기업이 앱의 **다른 명단**에도
있으면 두 줄이 된다(대조가 거기까지 안 간다), ② 다음 판에서 시트의 기업명이
바뀌어 있으면 그 줄을 못 찾아 또 만든다, ③ **시트에** 번호를 채워 다시 넣으면
번호로는 그 줄을 못 찾아 또 만든다.

③을 코드로 막지 않는 이유: 막으려면 번호가 **있는** 줄도 기업명으로 한 번 더
찾아야 하는데, 그러면 지금 잘 도는 길의 동작이 바뀐다. 이 변경이 건드릴 자리는
번호가 없는 줄까지다. 대신 화면에 **길을 적는다** — 번호는 앱에서 그 줄을 열어
넣으면 되고, 그러면 다음 판부터 번호로 이어진다.

## 겹치는 사람의 배정은 **파일로 받는다** (`--rulings`)

같은 사람이 두 명단에 들어가면 딜 소개가 두 번 나간다. 누가 맡을지는 사람이
정하는 일이지 코드가 정할 일이 아니다. 게다가 이 저장소는 공개라 실명·연락처를
소스에 적을 수 없다. 그래서 결정을 **데이터**로 받는다.

배정된 사람이 앱에 이미 있으면 **새로 만들지 않고 주인만 바꾼다.** 그 줄에
카톡방·발송 이력·담당 투자사가 붙어 있어서, 새로 만들면 그 이력이 통째로
끊긴다.

## 명단 이름과 담당자도 인자다

코드에 박아 두면 다음 명단에서 또 박아야 하고, 박는 것을 잊은 곳만 조용히 옛
동작을 한다. 담당자는 **계정의 휴대폰번호**로 가리키고, 계정이 없으면 만들지
않고 멈춘다 — 임포터가 계정을 만들면 번호를 한 자 잘못 적었을 때 유령 계정이
생기고 그 계정에 사람들이 붙는다. 계정 만들기는 `scripts/add_user.py` 의 일이다.

    python scripts/import_new_list.py 파일.csv \
        --sheet "명단 이름" --owner 01000000000 --mode create
    python scripts/import_new_list.py 파일.csv \
        --sheet "명단 이름" --owner 01000000000 --mode create --apply
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ContactColumn, SheetOwner, User, VcContact  # noqa: E402
from app.services import contact_columns as cc  # noqa: E402
from app.services import sheet_import  # noqa: E402
from app.services import sheet_owner  # noqa: E402
from app.services import spreadsheet as sp  # noqa: E402
from app.services.auth import normalize_phone  # noqa: E402
# 번호로 맞추는 판정은 **한 곳에서만** 한다. 베껴 두면 두 벌이 되고, 한쪽만
# 고쳐지면 그때 맞던 사람이 이제 안 맞는다.
from app.services.sourcing_link import MIN_DIGITS, digits  # noqa: E402
# 시트를 읽는 규칙도 명단 임포터의 것을 그대로 쓴다(머리행 찾기 · 칸 짝짓기 ·
# 달마다 늘어나는 칸). 여기서 다시 쓰면 8월 칸이 한쪽에서만 생긴다.
from scripts.import_startup_sheet import FIELDS, NOTES, norm, parse  # noqa: E402

# 부르는 쪽이 `--map` 으로 걸 수 있는 칸 이름들. 배치가 정한 키만 받는다 —
# 여기서 새 이름을 지으면 값은 들어가는데 화면이 그 칸을 못 찾는다.
MAPPABLE = {f for _t, f in FIELDS} | {k for _t, k in NOTES}

# 이 임포터가 명단에 세우는 배치. **두 자리가 같은 값을 봐야 한다** — 명단을
# 세울 때(아래 `settings.layout`)와, 번호 없는 줄을 기업명으로 이어도 되는지
# 물을 때(`cc.firm_leads`)다. 값을 두 번 적으면 배치를 바꾼 날 한쪽만 바뀌어,
# 사람이 주인공인 명단을 기업명으로 잇게 된다.
LAYOUT = cc.STARTUP


def is_table_row(value) -> bool:
    """이 줄이 표의 줄인가 — **번호 칸이 숫자인 줄.**

    `import_startup_sheet.has_row_no` 는 `> 0` 만 표의 줄로 본다. 표 아래에
    운영 가이드가 줄글로 붙은 시트를 읽으려고 그렇게 두었다.

    여기서는 `0` 도 줄로 센다. 어떤 시트는 **다른 담당자에게 넘긴 줄**의 번호를
    0 으로 바꿔 맨 위에 모아 둔다 — 사람이 지운 것이 아니라 옮긴 표시다.
    그 줄을 통째로 버리면 "누구에게 넘겼는가" 가 사라지고, 배정표가 그 줄을
    가리켜도 임포터가 못 본다.

    줄글은 이 검사에서 걸린다(숫자가 아니다). 여기서 새어 나가도 **기업명 칸이
    빈 줄은 `parse` 가 이미 뺀다** — 두 겹으로 막힌다. (예전에는 "번호 없는 줄은
    어차피 안 들어간다" 가 두 번째 겹이었는데, 이제 번호 없는 줄도 기업명으로
    들어간다. 줄글에는 기업명이 없으니 막는 자리는 그대로다.)
    """
    try:
        float(norm(value))
    except (TypeError, ValueError):
        return False
    return True


def load_rulings(path: str) -> dict:
    """겹치는 사람의 배정표 → `{번호: 넣을 명단 이름}`.

    한 줄에 `번호, 명단 이름` 이고 뒤에 뭘 더 적어도 무시한다(누구인지 사람이
    알아보려고 이름을 적어 두는 자리다). `#` 로 시작하는 줄과 머리글 줄은
    건너뛴다 — 번호로 보이지 않는 첫 칸은 줄이 아니다.

    **명단 이름으로 적는다.** 사람 이름으로 적으면 동명이인에서 갈리고, 그
    이름의 계정이 아직 없을 때 가리킬 것이 없다.
    """
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as fp:
        for row in csv.reader(fp):
            cells = [(c or "").strip() for c in row]
            if not cells or not cells[0] or cells[0].startswith("#"):
                continue
            key = digits(cells[0])
            if len(key) < MIN_DIGITS or len(cells) < 2 or not cells[1]:
                continue
            out[key] = cells[1]
    return out


def by_phone(contacts) -> tuple:
    """`({번호: 앱의 줄}, 겹친 번호들)`. 같은 번호가 둘이면 **아예 뺀다.**

    어느 쪽 줄에 붙일지 알 수 없는데 하나를 골라 두면 반은 틀린다. 틀리면
    남의 이력에 남의 값이 덮인다 — 되돌릴 수 없는 쪽이다.
    """
    seen, clashed = {}, set()
    for c in contacts:
        key = digits(c.phone)
        if len(key) < MIN_DIGITS:
            continue
        if key in seen:
            clashed.add(key)
        seen[key] = c
    for key in clashed:
        seen.pop(key, None)
    return seen, sorted(clashed)


def firm_key(name) -> str:
    """기업명을 **잇기용 열쇠**로. `(주)`·`㈜`·공백을 지운다.

    시트마다 법인 표기를 붙였다 뗐다 하고(`(주)샘플가` · `㈜샘플가` · `샘플가`),
    한 시트 안에서도 다음 달 판에서 달라진다. 글자 그대로 맞추면 같은 기업이
    다음 판에서 안 걸려 **두 줄이 된다.**

    법인 표기 규칙은 앱의 것을 그대로 부른다 — 여기서 다시 적으면 두 벌이 되고
    한쪽만 고쳐진다(`import_investor_list.merge_key` 도 같은 둘을 쓴다).
    **저장은 원문 그대로** 한다. 시트 원문을 바꿔 두면 사람이 화면에서 자기
    기록을 알아보지 못한다.
    """
    return re.sub(r"\s+", "", sheet_import.normalize_company_name(name or ""))


def by_firm(contacts) -> tuple:
    """`({기업명 열쇠: 앱의 줄}, 겹친 이름들)`. 같은 이름이 둘이면 **아예 뺀다.**

    `by_phone` 과 같은 이유다 — 어느 쪽 줄에 붙일지 알 수 없는데 하나를 골라
    두면 반은 틀리고, 틀리면 남의 이력에 남의 값이 덮인다.

    **범위는 부르는 쪽이 좁혀서 준다.** 앱 전체를 이렇게 세우면 투자사 명단의
    `투자사명` 과 부딪힌다 — 한 투자사에 심사역이 여럿이라 이름 하나에 여러
    줄이 걸리고, 그 줄들이 통째로 겹친 것으로 빠진다.
    """
    seen, clashed = {}, set()
    for c in contacts:
        key = firm_key(c.firm)
        if not key:
            continue
        if key in seen:
            clashed.add(key)
        seen[key] = c
    for key in clashed:
        seen.pop(key, None)
    return seen, sorted(clashed)


def apply_values(contact, item, columns) -> None:
    """시트의 값을 줄에 얹는다.

    **빈 칸은 덮지 않는다.** `parse` 가 값이 있는 칸만 담아 주므로, 시트에서
    비어 있는 칸이 앱에서 고쳐 둔 값을 지우는 일이 없다 — 그래서 몇 번을 다시
    돌려도 결과가 같다.
    """
    for field, value in item["fields"].items():
        setattr(contact, field, value)
    values = cc.load_notes(contact.notes)
    values.update(item["notes"])
    for label, text in item["months"].items():
        values[cc.note_key(columns[label].id)] = text
    contact.notes = cc.dump_notes(values)


def move_to(db, contact, label: str, user_id: int) -> str:
    """이미 있는 줄을 이 명단으로 **옮긴다.** 새로 만들지 않는다.

    카톡방·발송 이력·담당 투자사가 이 줄에 붙어 있다. 새로 만들면 그 이력이
    끊기고, 이력이 없는 새 줄로 다시 처음부터 연락하게 된다.

    출처(`source_sheet`)에서 **담당이 정해진 남의 명단은 뺀다.** 남겨 두면 그
    팀원의 대시보드와 발송 대상에 계속 잡혀 같은 사람에게 딜 소개가 두 번
    나간다 — 애초에 배정을 정한 이유가 그것이다.

    담당이 없는 명단(투자사 풀)은 **그대로 둔다.** 풀은 확보해 둔 전체 명단이지
    누구의 담당도 아니라, 거기서 빼면 그 분류 자체가 사라진다
    (`sheet_owner.add_to_sheet` 이 풀에서 빼지 않는 것과 같은 이유다).
    """
    owners = sheet_owner.owner_map(db)
    before = sheet_owner.labels_of(contact.source_sheet)
    keep = [x for x in before
            if x != sheet_owner.MANUAL_SHEET
            and x != label
            and (not owners.get(x) or owners.get(x) == user_id)]
    contact.source_sheet = ",".join(keep + [label])
    contact.user_id = user_id
    return f"{', '.join(before)} → {contact.source_sheet}"


def main() -> int:
    ap = argparse.ArgumentParser(description="새 담당자 명단 만들기 / 채우기")
    ap.add_argument("path")
    ap.add_argument("--sheet", required=True, help="앱의 명단(탭) 이름")
    ap.add_argument("--owner", required=True,
                    help="담당 팀원 계정의 휴대폰번호(없으면 멈춘다)")
    ap.add_argument("--mode", required=True, choices=["create", "fill"],
                    help="create=없는 줄을 만든다 · fill=있는 줄만 채운다")
    ap.add_argument("--tab", default=None, help="엑셀 파일 안의 탭 이름")
    ap.add_argument("--map", action="append", default=[], metavar="머리글=칸",
                    help="시트 머리글을 앱의 칸에 건다 (예: 내용=memo)")
    ap.add_argument("--rulings", default=None,
                    help="겹치는 사람의 배정표 (번호,명단 이름)")
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args()

    aliases = {}
    for pair in args.map:
        label, _, key = pair.partition("=")
        if key not in MAPPABLE:
            ap.error(f"--map 의 칸 이름이 배치에 없습니다: {key!r} "
                     f"(쓸 수 있는 것: {', '.join(sorted(MAPPABLE))})")
        aliases[label] = key

    rulings = load_rulings(args.rulings) if args.rulings else {}

    data = Path(args.path).read_bytes()
    parsed = parse(sp.read_rows(args.path, data, args.tab),
                   is_row=is_table_row, aliases=aliases)
    if not parsed["items"]:
        print("읽을 내용을 찾지 못했습니다. 번호 칸과 `기업명` 이 있는 시트인지 확인하세요.")
        return 1

    db = SessionLocal()
    owner = db.execute(
        select(User).where(User.phone == normalize_phone(args.owner))
    ).scalars().first()
    if owner is None:
        # 계정을 여기서 만들지 않는다 — 번호를 한 자 잘못 적으면 유령 계정이
        # 생기고, 그 계정에 사람들이 붙어 버린다.
        print(f"`{args.owner}` 계정이 없습니다. 먼저 만드세요:\n"
              f"  python scripts/add_user.py --name 이름 --phone {args.owner}")
        db.close()
        return 1

    people = db.execute(select(VcContact)).scalars().all()
    known, clashed = by_phone(people)
    here = [c for c in people
            if args.sheet in sheet_owner.labels_of(c.source_sheet)]
    mine = {c.id for c in here}
    # 번호 없는 줄이 기댈 곳. **이 명단 안까지만** 본다 — 앱 전체를 기업명으로
    # 뒤지면 투자사 명단의 `투자사명` 과 부딪혀 한 투자사의 심사역 여럿이 한 줄로
    # 뭉개진다(`import_investor_list.py` 가 이름+투자사명을 이 명단 안에서만 찾는
    # 것과 같은 범위다). 범위가 이 명단 하나면 틀려도 남의 명단에는 닿지 않는다.
    here_by_firm, firm_clashed = by_firm(here)
    # 기업이 주인공인 배치에서만 기업명으로 잇는다. 명단 이름이 아니라 배치로
    # 가른다 — 이유는 맨 위 설명과 `SheetOwner.layout` 주석에 있다.
    match_by_firm = cc.firm_leads(LAYOUT)

    # 무엇을 할지 먼저 다 정하고, 저장은 맨 끝에 한 번에 한다 — 미리보기와
    # 실제 저장이 **같은 판단**을 지나야 미리보기가 미리보기 구실을 한다.
    fills, moves, creates = [], [], []
    skips = {}            # 이유 → [적어 둘 말]
    seen = set()
    no_phone = []         # 번호 없이 들어갈 줄 — 무엇을 근거로 이었는지까지
    no_phone_new = 0      # 그중 **새로 만드는** 줄

    def skip(reason, note):
        skips.setdefault(reason, []).append(note)

    # 시트 안에서 같은 기업명이 몇 줄인가. **번호 없는 줄은 열쇠가 기업명뿐**이라
    # 그 이름이 둘이면 열쇠 구실을 못 한다. 넣어 두면 다음 판에서 어느 줄이
    # 어느 줄인지 가릴 수 없고, 그때는 이미 두 줄이다 — 그래서 넣기 전에 센다.
    firm_rows = {}
    for item in parsed["items"]:
        fkey = firm_key(item["fields"].get("firm", ""))
        if fkey:
            firm_rows[fkey] = firm_rows.get(fkey, 0) + 1

    # 시트의 **번호 있는 줄**이 집어 갈 앱의 줄. 번호 없는 줄이 그 줄을 기업명으로
    # 다시 집으면 시트의 두 줄이 앱의 한 줄에 겹쳐 얹힌다 — 나중 것이 앞 것을
    # 덮은 것인지조차 알 수 없다(`import_investor_list.py` 의 `taken_rows` 와 같은
    # 자리다). 시트에서 기업명을 새로 적은 줄과 옛 이름 줄이 같이 있을 때 생긴다.
    taken = {found.id for found in
             (known.get(digits(i["fields"].get("phone", "")))
              for i in parsed["items"]) if found is not None}

    for item in parsed["items"]:
        firm = item["fields"].get("firm", "")
        where = f"no={item['no']} {firm}"
        key = digits(item["fields"].get("phone", ""))

        if len(key) < MIN_DIGITS:
            # 번호가 없다. **앱 전체와는 대조할 수 없다** — 대신 이 배치의 시트는
            # 기업이 주인공이라 기업명이 열쇠 노릇을 한다(맨 위 설명 참고).
            if not match_by_firm:
                skip("번호가 없어 겹침을 판단할 수 없다", where)
                continue
            fkey = firm_key(firm)
            if not fkey:
                # 대조할 것이 아무것도 없다. 넣으면 다음 판에서 또 만든다.
                skip("번호도 기업명도 없어 겹침을 판단할 수 없다", where)
                continue
            if firm_rows.get(fkey, 0) > 1:
                # 시트 안에 같은 기업명이 여럿이다. 번호가 없으면 그중 어느 줄인지
                # 가릴 길이 없어, 넣는 순간 다음 판이 못 알아본다.
                skip("시트 안에 같은 기업명이 여럿 — 번호 없이는 못 가른다", where)
                continue
            if fkey in firm_clashed:
                skip("이 명단에 같은 기업명이 두 줄 — 어느 쪽인지 알 수 없다", where)
                continue
            found = here_by_firm.get(fkey)
            if found is not None and found.id in taken:
                skip("그 줄은 시트의 다른 줄이 번호로 집었다", where)
                continue
            if found is not None:
                fills.append((found, item, where))
                no_phone.append(f"{where}  ←→ 이 명단의 `{found.firm or ''}`")
            elif args.mode == "fill":
                skip("앱에 없는 사람 — 채우기 모드에서는 만들지 않는다", where)
            else:
                creates.append((item, where))
                no_phone.append(f"{where}  → 새로 만든다")
                no_phone_new += 1
            continue
        if key in seen:
            # 시트 안에서 같은 줄이 두 번 적힌 것이다. 둘 다 넣으면 앱에서
            # 두 줄이 되고, 그 순간 딜 소개가 두 번 나간다.
            skip("시트 안에서 같은 번호가 두 번", where)
            continue
        seen.add(key)
        if key in clashed:
            skip("앱에 같은 번호가 두 줄 — 어느 쪽인지 알 수 없다", where)
            continue

        ruled = rulings.get(key)
        if ruled and ruled != args.sheet:
            # 사람이 다른 명단으로 배정한 사람이다. 여기 넣으면 두 계정에
            # 들어가 딜 소개가 두 번 나간다.
            skip("다른 명단으로 배정됨", f"{where} → `{ruled}`")
            continue

        found = known.get(key)
        if found is not None and found.id in mine:
            fills.append((found, item, where))       # 이미 이 명단에 있다
        elif found is not None:
            if args.mode == "fill":
                skip("앱의 다른 명단에 있다 (옮기려면 --mode create)", where)
            else:
                moves.append((found, item, where))   # 주인만 바꾼다
        elif args.mode == "fill":
            skip("앱에 없는 사람 — 채우기 모드에서는 만들지 않는다", where)
        else:
            creates.append((item, where))

    # 배정표가 이 명단으로 정했는데 **시트에는 없는** 사람. 시트는 자료일 뿐이고
    # 배정을 정한 것은 사람이라, 시트에 안 적혔다고 배정이 없던 일이 되면 안 된다.
    # (넘겨받는 사람의 시트에는 아직 그 줄이 없는 것이 오히려 보통이다.)
    orphans = []
    for key, label in sorted(rulings.items()):
        if label != args.sheet or key in seen:
            continue
        found = known.get(key)
        if found is None:
            skip("배정표에 있는데 시트에도 앱에도 없다", key[:3] + "…" + key[-4:])
        elif found.id in mine:
            pass                                      # 이미 이 명단이다
        elif args.mode == "fill":
            skip("배정표가 이 명단으로 정했다 (옮기려면 --mode create)",
                 f"{found.firm or ''} {found.name}")
        else:
            orphans.append(found)

    total = len(fills) + len(moves) + len(creates) + len(orphans)
    print(f"명단 `{args.sheet}` · 담당 {owner.name} · 모드 {args.mode}")
    print(f"  시트에서 읽은 표의 줄 {len(parsed['items'])}개")
    print(f"  이 명단에 들어갈 줄 {total}개")
    print(f"    새로 만들 줄             {len(creates)}")
    print(f"    주인만 바꿀 줄           {len(moves)}"
          f"  (앱에 이미 있는 번호 — 이력이 그 줄에 붙어 있다)")
    print(f"    주인만 바꿀 줄(배정표)    {len(orphans)}"
          f"  (시트에는 없지만 이 명단으로 배정된 사람)")
    print(f"    이미 이 명단이라 채울 줄  {len(fills)}")
    print(f"  달마다 늘어나는 칸 {len(parsed['columns'])}개: "
          f"{', '.join(parsed['columns']) or '없음'}")
    if parsed["skipped"]:
        print(f"  표 밖의 줄 {len(parsed['skipped'])}개 (번호 칸이 숫자가 아닌 줄)")
    for who, _item, where in moves:
        print(f"    옮김: {where}  ←→ 앱 `{who.firm or ''} {who.name}`")
    for who in orphans:
        print(f"    옮김(시트에 없음, 배정표): 앱 `{who.firm or ''} {who.name}`")
    if no_phone:
        # **조용히 넣지 않는다.** 번호 없이 들어가는 줄은 무엇을 근거로 이었는지가
        # 곧 그 줄의 안전성이라, 근거를 안 적으면 나중에 두 줄이 됐을 때 왜
        # 그렇게 됐는지 알아낼 데가 없다.
        print(f"\n  번호 없이 들어갈 줄 {len(no_phone)}개 — 번호가 없어 **앱 전체와는 "
              f"대조하지 못했습니다.**\n     이 명단 `{args.sheet}` 안에서 "
              f"**기업명으로만** 이었습니다:")
        for note in no_phone:
            print(f"       {note}")
    if no_phone_new:
        # 새로 만들 때만 적는다 — 채우기는 줄을 만들지 않으므로 ①이 생길 자리가
        # 없다(`import_investor_list.py` 가 같은 경고를 만들기에서만 내는 이유다).
        print(f"  ⚠ 그중 {no_phone_new}개는 **새로 만듭니다.** 남는 위험 셋:\n"
              f"     ① 같은 기업이 **앱의 다른 명단**에 이미 있으면 두 줄이 됩니다 "
              f"— 이 대조는 거기까지 보지 않습니다.\n"
              f"     ② 다음 판에서 시트의 기업명이 바뀌어 있으면 그 줄을 못 찾아 "
              f"또 만듭니다.\n"
              f"     ③ **시트에** 번호를 채워 다시 넣으면 또 만듭니다 — 번호로는 "
              f"이 줄을 못 찾습니다.\n"
              f"        번호는 **앱에서 그 줄을 열어** 넣으세요. 그러면 다음 "
              f"판부터 번호로 이어집니다.")
    if skips:
        # **조용히 버리지 않는다.** 몇 줄이 왜 빠졌는지 모르면 나중에 그 줄이
        # 없다는 것조차 알 수 없다.
        print(f"\n  건너뛸 줄 {sum(len(v) for v in skips.values())}개")
        for reason, rows in skips.items():
            print(f"    ── {reason} ({len(rows)}줄)")
            for note in rows:
                print(f"       {note}")

    if not args.apply:
        print("\n미리보기입니다. 넣으려면 --apply 를 붙이세요.")
        db.close()
        return 0

    # 명단 설정. 이 시트는 기업명·성함이 따로 있고 달마다 칸이 늘어나는
    # 스타트업 명단이라 그 배치로 세운다.
    settings = db.execute(
        select(SheetOwner).where(SheetOwner.label == args.sheet)
    ).scalars().first()
    is_new_sheet = settings is None
    settings = sheet_owner.ensure(db, args.sheet, user_id=owner.id)
    settings.layout = LAYOUT
    if settings.user_id is None:
        # `ensure` 는 이미 있는 명단의 담당을 덮지 않는다(시트를 다시 올린 것만으로
        # 남의 담당이 넘어가면 안 된다). 비어 있는 자리는 채워도 뺏는 것이 아니다.
        settings.user_id = owner.id
    if is_new_sheet:
        # 스타트업은 투자사가 아니다. 투자사로 세면 투자사 수가 부풀고, 딜소개
        # 발송 대상과 소싱 방 잇기(`sourcing_link`)에도 함께 뜬다 — 스타트업
        # 대표의 방으로 "이 딜 어떠세요" 가 나간다.
        #
        # **다시 돌릴 때는 건드리지 않는다.** 화면에서 사람이 [숨김 해제] 를
        # 눌러 둔 것을 임포트 한 번이 되돌리면 안 된다.
        settings.is_hidden = 1

    # 월별 칸이 먼저다 — 줄의 값이 칸 id 를 키로 쓴다.
    columns = {c.label: c for c in cc.month_columns(db, args.sheet, create=False)}
    for pos, label in enumerate(parsed["columns"]):
        if label not in columns:
            columns[label] = ContactColumn(sheet=args.sheet, label=label,
                                           position=pos)
            db.add(columns[label])
    db.flush()

    for contact, item, _where in fills:
        apply_values(contact, item, columns)
    for contact, item, _where in moves:
        move_to(db, contact, args.sheet, owner.id)
        apply_values(contact, item, columns)
    for contact in orphans:
        move_to(db, contact, args.sheet, owner.id)
    for item, _where in creates:
        contact = VcContact(user_id=owner.id, source_sheet=args.sheet,
                            name=item["fields"].get("name", ""))
        db.add(contact)
        apply_values(contact, item, columns)

    db.commit()
    print(f"\n새로 만든 줄 {len(creates)} · 옮긴 줄 {len(moves) + len(orphans)} "
          f"· 채운 줄 {len(fills)} · 칸 {len(parsed['columns'])}개")
    if no_phone:
        # 미리보기에서 한 번 적었어도 여기 또 적는다. 넣고 난 뒤에 남는 기록은
        # 이 줄이라, 여기 없으면 "번호 없이 몇 줄 들어갔더라" 를 알 길이 없다.
        print(f"  그중 번호 없이 들어간 줄 {len(no_phone)}개 "
              f"(새로 만든 것 {no_phone_new}개) — 이 명단 안에서 기업명으로 "
              f"이었습니다.\n  번호는 **앱에서 그 줄을 열어** 넣으세요 "
              f"(시트에 채워 다시 넣으면 두 줄이 됩니다).")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
