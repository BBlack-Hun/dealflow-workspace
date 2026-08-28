"""담당자별 **투자사 딜공유 명단**을 새 명단(탭)으로 만든다.

`import_new_list.py` 로는 이 시트를 못 읽는다. 저쪽이 읽는 스타트업 시트는
`NO` + `기업명` 이 있는 **머리글 한 줄**짜리인데, 담당자마다 쓰는 딜공유 시트는
모양이 셋 다 다르다.

  1. **머리글이 두 줄**이다. 윗줄은 `8월`·`7월` 같은 **달 묶음**(세 칸을 병합해
     걸어 둔다)이고 아랫줄이 진짜 머리글이다. 윗줄을 안 읽으면 `딜소개` 라는
     같은 이름의 칸이 달 수만큼 생겨 **한 칸으로 뭉개진다** — 여섯 달치 기록이
     한 달치만 남는다.
  2. 머리글이 **엑셀 수식**이다. `="딜소개 8/5 ("&COUNTIF(…)&")"` 처럼 세어 본
     수가 이름에 섞여 있다. 그대로 칸 이름으로 쓰면 수식이 화면에 나오고,
     세어 본 수는 시트를 열 때마다 달라져서 **같은 칸이 달마다 새 칸으로 선다.**
  3. `NO` 칸이 없다. 사람이 주인공인 명단이라 `이름` + `투자사명` 이 표를 연다.

## 왜 따로 두나

`import_new_list.py` 는 그대로 둔다. 저쪽은 스타트업 시트를 읽는 규약(`NO`
칸으로 표의 줄을 가른다 · 스타트업 배치로 세운다 · 투자사로 세지 않는다)이
문서와 검사에 박혀 있다. 여기서 그 규약을 열어 인자로 바꾸면 저쪽 시트를 넣는
사람이 매번 네 개의 인자를 더 적어야 하고, 안 적은 한 번이 조용히 다른 뜻이
된다. **판정은 베끼지 않고 부른다** — 겹치는 사람 배정표·번호로 맞추기·이미
있는 줄 옮기기는 `import_new_list` 의 것을 그대로 쓴다.

## 여러 탭을 **한 명단으로** 합친다 (`--tab` 을 여러 번)

한 사람의 자료가 탭 두 장에 나뉘어 있다 — 한쪽에 연락처(명함), 다른 쪽에 달마다의
딜공유 기록. 둘을 따로 넣으면 같은 사람이 두 줄이 되고, 한쪽만 넣으면 연락처나
이력이 통째로 빠진다. **먼저 적은 탭의 값이 이긴다**(빈 칸은 덮지 않는다).

## 사람을 잇는 열쇠가 **두 가지**다 — 쓰는 자리가 다르다

    번호      **앱 전체**와 대조할 때. 동명이인이 있어 이름으로 이으면 남의 방으로
              딜 소개가 나간다(한 이름이 셋인 적이 있다 — `sourcing_link`).
    이름+회사  **이 명단 안**에서만. ① 탭 두 장을 합칠 때 ② 다시 넣을 때 같은 줄을
              찾을 때. 이 두 자리에서는 번호를 쓸 수가 없다 — 딜공유 탭에는 번호
              칸이 아예 없다. 대신 범위가 이 명단 하나라 틀려도 남의 명단에는
              닿지 않고, 시트 자체가 사람마다 한 줄이라 겹칠 것이 없다
              (넣기 전에 세어서 알린다).

## 번호가 없는 줄도 **넣는다** — 여기서는 넣는 것이 맞다

`import_new_list.py` 는 번호가 없으면 넣지 않는다. 앱에 이미 있는 사람인지
가릴 수가 없어서다. 여기 사정은 다르다.

  · **명단 자체가 새로 생긴다.** 이 명단 안에는 겹칠 상대가 아직 없다.
  · 시트에 번호가 **아예 없다.** 워크북 전 탭을 뒤져도 없다. 안 넣으면 그 사람들이
    통째로 사라지고, 명단도 이력도 화면에 안 뜬다.
  · **번호는 발송의 열쇠가 아니다.** 딜 소개는 이미 만들어진 카톡방으로 나간다
    (`dashboard._room_state` 는 채널·방 이름만 본다). 번호의 쓸모는 사람을
    대조하는 것이라, 번호가 없어도 명단과 이력은 온전하다.

남는 위험은 하나다 — 나중에 번호를 채웠을 때 그 사람이 앱의 다른 명단에도
있으면 두 줄이 된다. 지금은 막을 방법이 없으므로 넣을 때 **몇 명이 그런
상태인지 세어서 알린다.**

    python scripts/import_investor_list.py 파일.xlsx \
        --tab "탭1" --tab "탭2" --sheet "명단 이름" --owner 01000000000
    python scripts/import_investor_list.py 파일.xlsx … --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ContactColumn, SheetOwner, User, VcContact  # noqa: E402
from app.services import contact_columns as cc  # noqa: E402
from app.services import firm_type, sheet_import, sheet_owner  # noqa: E402
from app.services import spreadsheet as sp  # noqa: E402
from app.services.auth import normalize_phone  # noqa: E402
from app.services.sourcing_link import MIN_DIGITS, digits  # noqa: E402
# 겹치는 사람 배정표 · 번호로 맞추기 · 이미 있는 줄 옮기기는 **한 곳에만** 둔다.
# 베껴 두면 두 벌이 되고, 한쪽만 고쳐지면 그때 맞던 사람이 이제 안 맞는다.
from scripts.import_new_list import by_phone, load_rulings, move_to  # noqa: E402
from scripts.import_startup_sheet import flat, norm  # noqa: E402


def clean_label(text: str) -> str:
    """시트 머리글 → **사람이 읽을 칸 이름.** 뜻은 그대로 두고 두 가지만 뗀다.

    ① **수식 껍데기.** `="딜소개 8/5 ("&COUNTIF(…)&") 8/12 ("&…` 에서 따옴표
       안의 글자만 남긴다. 어디가 사람이 쓴 말이고 어디가 계산한 값인지는
       **수식 자신이 말해 준다** — 짐작할 자리가 없다.
       (엑셀은 대개 계산해 둔 값을 함께 저장해서 `sp.read_rows` 가 그쪽을 읽지만,
       계산값이 없는 파일·CSV 로 내보낸 파일에서는 수식이 그대로 올라온다.)

    ② **세어 본 수가 든 괄호.** `(101)` · `(투자사 4 / IR 14)` · `(8)`.
       수식이 세어서 채우는 자리라 시트를 열 때마다 값이 달라진다. 이름에 섞이면
       같은 8월 칸이 다음 임포트에서 **다른 칸**으로 서서, 한 달 기록이 두 칸에
       갈린다.

    사람이 손으로 쓴 괄호는 남긴다 — `관심도 (월말기준)` · `딜소개 (8/26 딜소개
    없음)` · `공통 (9월~)`. 안에 세는 말과 수 말고 다른 낱말이 있으면 사람이 쓴
    것이다.
    """
    text = flat(text)
    if text.startswith("="):
        text = "".join(_top_level_literals(text))
    return _drop_counts(text)


def _top_level_literals(formula: str) -> list:
    """수식에서 **사람이 쓴 말**만 뽑는다 = 괄호 **밖**의 따옴표 안쪽.

    괄호 안에도 따옴표가 있다 — `COUNTIF(E3:E133,"*8/5*")` 의 `*8/5*` 는 무엇을
    셀지 고르는 조건이지 칸 이름이 아니다. 따옴표를 다 긁어모으면 그 조건이
    이름에 들어와 `딜소개 8/5 ( *8/5* ) 8/12 …` 가 된다.

    괄호 깊이만 세면 갈린다 — 이름 조각은 `="…"&함수(…)&"…"` 처럼 **맨 바깥**에서
    이어 붙고, 계산에 쓰는 글자는 반드시 함수 괄호 안에 있다.
    """
    out, depth, i = [], 0, 1        # 1 = 맨 앞 `=` 다음부터
    while i < len(formula):
        ch = formula[i]
        if ch == '"':
            end = formula.find('"', i + 1)
            if end < 0:
                end = len(formula)
            if depth == 0:
                out.append(formula[i + 1:end])
            i = end + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        i += 1
    return out


# 수식이 **세는 대상**. 시트의 수식에 적힌 말 그대로다
# (`COUNTIF(…,"*전달*")` 의 결과를 `투자사 N / IR N` 으로 적는다).
# 이 말과 숫자만 든 괄호가 곧 '세어 본 수'다.
_COUNTED_WORDS = ("투자사", "IR", "미팅확정", "미팅완료")
# 숫자·구분기호만으로 된 조각. `101` · `8/5` · `00` · `4,`
_NUMERIC = re.compile(r"^[0-9\s/.,~·\-()]*$")


def _is_count(inside: str) -> bool:
    """괄호 안이 **세어 본 수**뿐인가."""
    for word in inside.replace("/", " ").split():
        if _NUMERIC.match(word) or word in _COUNTED_WORDS:
            continue
        return False
    return True


def _drop_counts(text: str) -> str:
    """세어 본 수가 든 괄호를 뗀다. 뗀 자리에 공백이 겹치지 않게 다듬는다."""
    out = re.sub(r"\(([^()]*)\)",
                 lambda m: "" if _is_count(m.group(1)) else m.group(0), text)
    # 괄호를 떼면 `딜소개  8/5  8/12` 처럼 공백이 겹치고, 앞뒤에 구분기호만
    # 남기도 한다(`IR 요청 / 미팅 안내` 의 `/` 는 남겨야 뜻이 안 바뀐다).
    return " ".join(out.split()).strip(" -·")


# 그 명단에만 있는 칸(`VcContact.notes` 의 고정 키). 배치가 정한 키를 그대로
# 쓴다 — 여기서 새 이름을 지으면 값은 들어가는데 화면이 그 칸을 못 찾는다.
NOTES = [("기타", "etc")]


def _firm_column(header):
    """투자사명이 어느 열인가.

    시트마다 부르는 법이 다르다 — `투자사명` · `회사`. 그리고 `딜소싱 참여 투자사`
    도 `투자사` 를 품고 있어서 넓게 찾으면 그 칸을 투자사명으로 읽는다.

    **`or` 로 잇지 않는다.** 0번 열이 falsy 라 맨 앞 칸이 투자사명인 시트에서
    조용히 다음 후보로 넘어간다.
    """
    for tokens, exclude in ((["투자사명"], ()), (["회사"], ()),
                            (["투자사"], ("딜소싱", "참여"))):
        found = sheet_import.find_column(header, tokens, exclude=exclude)
        if found is not None:
            return found
    return None


# 머리글 → 앱의 칸. **적은 순서대로 자리를 잡고, 잡힌 자리는 다시 안 준다.**
#
# 시트 머리글은 서로의 조각을 품고 있다 — `그룹/투자분야/라운드사이즈` 안에
# `투자분야` 와 `라운드사이즈` 가 다 들어 있고, `전자 메일 주소` 안에 `주소` 가
# 있다. 먼저 잡은 칸을 빼 두지 않으면 한 열이 두 칸 노릇을 해서, 그룹 칸의 값이
# 선호 투자분야로도 들어간다.
#
# 찾는 규칙은 `sheet_import` 의 것을 그대로 부른다. 같은 시트를 읽으며 이미
# 다듬어 둔 판정이라(`딜소싱 참여 투자사` 를 투자사명으로 보지 않는 것 등),
# 여기서 다시 쓰면 한쪽만 고쳐진다.
def _columns_of(header):
    """머리글 → `{앱의 칸: 열 번호}`. 없는 칸은 담지 않는다."""
    si = sheet_import
    finders = [
        ("name", lambda h: si.find_column(h, ["이름"])),
        ("firm", _firm_column),
        ("phone", lambda h: si.first_column(h, ["휴대"], ["연락처"])),
        # `전자 메일 주소` 를 먼저 잡아야 `주소` 가 이메일을 가져가지 않는다.
        ("email", lambda h: si.first_column(h, ["전자", "메일"], ["이메일"])),
        # `그룹/투자분야/라운드사이즈` 를 먼저 잡는다. 한 칸에 셋이 적혀 있어
        # 쪼개면 근거 없는 값이 되고, 안 잡으면 아래 둘이 나눠 가져간다.
        ("group_name", lambda h: si.find_column(h, ["그룹"])),
        ("round_size", lambda h: si.find_column(h, ["라운드"])),
        ("sectors", lambda h: si.find_column(h, ["선호", "투자분야"])),
        ("interest_level", lambda h: si.find_column(h, ["관심도"])),
        ("kakao_joined", lambda h: si.find_column(h, ["카톡방", "참여"])),
        ("sourcing_note", lambda h: si.find_column(h, ["딜소싱"])),
        ("tips_note", lambda h: si.find_column(h, ["TIPS"])),
        ("department", lambda h: si.find_column(h, ["부서"])),
        ("title", lambda h: si.first_column(h, ["직함"], ["직책"])),
        ("office_phone", lambda h: si.first_column(h, ["유선"], ["근무처", "전화"])),
        ("office_fax", lambda h: si.find_column(h, ["팩스"])),
        ("address", lambda h: si.find_column(h, ["주소"],
                                             exclude=["메일", "이메일", "전자"])),
        ("card_registered_at", lambda h: si.find_column(h, ["명함"])),
        ("memo", lambda h: si.find_column(h, ["메모"])),
    ]
    at, taken = {}, set()
    for field, find in finders:
        found = find(header)
        if found is None or found in taken:
            continue
        at[field] = found
        taken.add(found)
    # 이 명단에만 있는 칸. **완전히 일치**할 때만 건다 — `기타` 는 짧아서
    # 포함으로 찾으면 다른 머리글에 걸린다.
    for label, key in NOTES:
        found = next((i for i, h in enumerate(header)
                      if h == label and i not in taken), None)
        if found is not None:
            at[f"note:{key}"] = found
            taken.add(found)
    return at


# 앱의 칸 중 **글자를 담는 모델 칸**. 나머지(`note:`)는 notes 로 간다.
FIELD_KEYS = {"name", "firm", "phone", "email", "group_name", "round_size",
              "sectors", "interest_level", "kakao_joined", "sourcing_note",
              "tips_note", "department", "title", "office_phone", "office_fax",
              "address", "card_registered_at", "memo"}


def looks_shifted(firm: str) -> bool:
    """투자사명 자리에 **투자사명이 아닌 것**이 들어와 있는가 (번호 · 주소).

    그 줄은 한 칸씩 밀려 있다 — 실제로 휴대폰 칸이 비고 회사·부서·직함·메일이
    통째로 오른쪽으로 밀린 줄이 있었다.

    **버리지 않고 알린다.** 여기서 버리면 그 사람이 명단에서 사라지고, 조용히
    넣으면 더 나쁘다 — 합치는 열쇠가 (이름, 투자사명)이라 밀린 값이 열쇠가 되어
    **같은 사람이 두 줄로 갈린다**(탭 하나에서는 번호가, 다른 탭에서는 진짜
    투자사명이 열쇠가 된다). 미리보기에서 보고 시트를 고친 뒤 넣는 자리다.

    주소 판정은 `sheet_import` 의 것을 그대로 부른다 — 같은 시트를 읽으며 이미
    다듬어 둔 판정이다.
    """
    text = flat(firm)
    if not text:
        return False
    if sheet_import.looks_like_address(text):
        return True
    # 번호만 든 칸. 짧은 사번·층수가 아니라 전화번호 길이일 때만 본다.
    return (len(re.sub(r"\D", "", text)) >= MIN_DIGITS
            and not re.sub(r"[\d\s\-().+]", "", text))


def find_header(rows) -> int:
    """머리행은 위치가 아니라 **내용**으로 찾는다.

    사람이 위쪽에 제목·메모 행을 넣다 뺐다 하므로 '두 번째 줄'이라고 못 박으면
    곧 깨진다. 이 명단은 사람이 주인공이라 `이름` 과 `투자사명`(또는 `회사`)이
    함께 있는 줄이 표를 연다.
    """
    for i, row in enumerate(rows[:30]):
        cells = [clean_label(c) for c in row]
        if any("이름" in c for c in cells) and \
                any(("투자사" in c or "회사" in c) for c in cells):
            return i
    return -1


def group_labels(rows, at: int, header, fixed: set) -> list:
    """머리글 **윗줄**의 달 묶음(`8월`)을 열마다 펴 놓는다.

    묶음은 세 칸을 병합해 걸려 있어서, 읽으면 맨 왼쪽 칸에만 값이 있고 나머지는
    빈칸으로 온다. 그래서 오른쪽으로 **이어받는다.**

    이어받기는 **고정 칸에서 끊는다.** 고정 칸(이름·투자사명·기타…)은 달 묶음에
    속하지 않는 표의 앞뒤라, 거기서 안 끊으면 ① 윗줄 첫 칸에 적힌 메모가 뒤따르는
    칸 이름에 붙고 ② 표 맨 끝의 `대화내역 메모` 가 마지막 달 것으로 읽힌다.
    """
    if at <= 0:
        return [""] * len(header)          # 머리글이 한 줄인 시트
    above = [clean_label(c) for c in rows[at - 1]]
    out, carried = [], ""
    for i in range(len(header)):
        if i in fixed:
            carried = ""
        elif i < len(above) and above[i]:
            carried = above[i]
        out.append(carried)
    return out


def parse_tab(rows) -> dict:
    """시트 한 장 → `{달마다 늘어나는 칸 이름들, 줄들, 못 읽은 줄들}`."""
    at = find_header(rows)
    if at < 0:
        return {"columns": [], "items": [], "skipped": [], "nameless": [],
                "shifted": []}
    header = [clean_label(c) for c in rows[at]]
    where = _columns_of(header)
    fixed = set(where.values())

    groups = group_labels(rows, at, header, fixed)
    # 남는 머리글이 곧 **달마다 늘어나는 칸**이다. 목록을 손으로 적어 두면
    # 9월 시트를 올렸을 때 그 세 칸이 조용히 버려진다.
    #
    # 이름 앞에 달 묶음을 붙인다. 안 붙이면 `딜소개` 가 달 수만큼 생겨 **한
    # 칸으로 뭉개지고**, 여섯 달치가 한 달치만 남는다. 붙이는 것은 원본에 없는
    # 말을 지어내는 것이 아니라 **윗줄에 적힌 것을 제자리에 돌려놓는 것**이다.
    months = [(i, " ".join(x for x in (groups[i], header[i]) if x))
              for i in range(len(header))
              if i not in fixed and header[i]]

    items, skipped, nameless, shifted = [], [], [], []
    for row in rows[at + 1:]:
        cells = list(row) + [""] * (len(header) - len(row))
        name = flat(cells[where["name"]]) if "name" in where else ""
        firm = flat(cells[where["firm"]]) if "firm" in where else ""
        if not name and not firm:
            continue                       # 빈 줄은 알릴 것이 없다
        if not name:
            # 이름이 없으면 누구인지 가리킬 수가 없다.
            skipped.append(f"(이름 없음) · {firm}")
            continue
        if not firm:
            # **버리지 않는다.** 투자사명 칸이 비었을 뿐 그 줄에는 달마다의 기록도
            # 메모도 들어 있다 — 빼면 그 사람이 명단에서 통째로 사라진다
            # (실제로 스물한 줄이 그렇다). 다만 이름만으로는 같은 줄인지 가릴 수
            # 없으니 **몇 명이 그런지 적어서 알린다.**
            nameless.append(name)
        elif looks_shifted(firm):
            shifted.append(f"{name} · 투자사명 자리에 `{firm}`")
        if sheet_import.is_placeholder_name(name):
            # 다른 표가 아래로 이어 붙은 줄이다. 그 줄은 나머지 칸도 통째로 어긋나
            # 있어, 넣으면 회사 칸에 주소가 든 **가짜 담당자**가 생긴다.
            skipped.append(f"{name} · {firm} (머리글이 값 자리에 있다)")
            continue
        item = {"fields": {}, "notes": {}, "months": {}}
        for key, i in where.items():
            value = norm(cells[i])
            if not value:
                continue
            if key.startswith("note:"):
                item["notes"][key[5:]] = value
            else:
                item["fields"][key] = value
        item["months"] = {label: norm(cells[i]) for i, label in months
                          if norm(cells[i])}
        items.append(item)
    return {"columns": [label for _i, label in months],
            "items": items, "skipped": skipped, "nameless": nameless,
            "shifted": shifted}


def merge_key(item) -> tuple:
    """탭 두 장을 합칠 때 **같은 사람인가**. 이름 + 투자사명.

    번호를 못 쓴다 — 딜공유 탭에는 번호 칸이 아예 없다. 대신 범위가 **이 임포트
    안**이라 틀려도 남의 명단에는 닿지 않는다. 시트마다 `㈜`·`(주)`·공백을 넣고
    빼는 법이 달라서 그것만 지우고 본다.
    """
    name = re.sub(r"\s+", "", item["fields"].get("name", ""))
    firm = sheet_import.normalize_company_name(item["fields"].get("firm", ""))
    return (name, re.sub(r"\s+", "", firm))


def merge(parsed_tabs) -> dict:
    """여러 탭 → 한 명단. **먼저 온 탭의 값이 이긴다**(빈 칸은 덮지 않는다).

    한쪽 탭에 연락처가, 다른 쪽에 달마다의 기록이 있어 둘을 합쳐야 한 사람이
    온전해진다. 나중 탭이 앞 탭의 값을 밀어내면 어느 탭을 먼저 적었느냐에 따라
    결과가 달라진다(`sheet_import._fill_if_empty` 와 같은 규칙이다).
    """
    columns, order, by_key, from_tab = [], [], {}, {}
    clashed = []
    for at, parsed in enumerate(parsed_tabs):
        for label in parsed["columns"]:
            if label not in columns:
                columns.append(label)
        for item in parsed["items"]:
            key = merge_key(item)
            found = by_key.get(key)
            if found is None:
                by_key[key], from_tab[key] = item, at
                order.append(key)
                continue
            if from_tab[key] == at:
                # **한 탭 안에서** 같은 사람이 두 줄이다. 시트는 사람마다 한 줄인데
                # 그 전제가 깨진 것이라 조용히 합치지 않고 알린다(탭이 다른 것은
                # 합치라고 부른 것이므로 알릴 일이 아니다).
                clashed.append(f"{item['fields'].get('name', '')} · "
                               f"{item['fields'].get('firm', '')}")
            for group in ("fields", "notes", "months"):
                for k, v in item[group].items():
                    found[group].setdefault(k, v)
    return {"columns": columns, "items": [by_key[k] for k in order],
            "clashed": clashed}


def apply_values(contact, item, columns) -> None:
    """시트의 값을 줄에 얹는다.

    **빈 칸은 덮지 않는다.** `parse_tab` 이 값이 있는 칸만 담아 주므로, 시트에서
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

    joined = item["fields"].get("kakao_joined", "")
    if sheet_import.is_invited(joined) or item["months"]:
        # 카톡으로 보내는 사람이다. 근거가 둘인데 **둘 다 시트가 말해 준 사실**이다.
        #   · `카톡방 참여여부` 에 표시가 있다 (시트가 직접 적었다)
        #   · 달마다의 딜공유 기록이 있다 — 그 기록이 곧 **카톡방으로 보낸 자취**다
        #     (대화내역 메모에 방 제목이 그대로 남아 있다)
        # 이 갈래가 필요한 이유: 딜공유 탭에는 `카톡방 참여여부` 칸이 아예 없다.
        # 그 칸만 보면 스물세 달치 발송 기록이 있는 사람이 `채널 불가 투자사`
        # (= 보낼 길이 없는 줄)로 뜬다. 맞는 상태는 `방 미등록`(= 방 제목만 채우면
        # 보낼 수 있다)이다.
        #
        # **방 이름은 짓지 않는다.** 지어 준 이름이 실제 방 제목과 다르면 발송이
        # 통째로 skip 되고, 이 시트들의 실제 방 제목은 앱이 짓는 모양과 아예
        # 다르다(대화 기록에 남은 방 이름이 그렇게 말한다). 방 이름이 없으면
        # 화면에 `방 미등록` 으로 뜬다 — 고쳐야 할 것이 그대로 보이는 것이 맞다.
        contact.channel_kakao = 1
    if item["fields"].get("email"):
        contact.channel_email = 1
    # 연결이 어디까지 갔는지는 시트에 한 칸으로 있지 않다. **뒤로 내리지는
    # 않는다** — 이미 방이 붙어 발송까지 한 사람을 명단 한 장 때문에 미착수로
    # 되돌리면 발송 대상에서 빠진다.
    if contact.kakao_room_name:
        contact.connect_stage = sheet_import.STAGE_CONNECTED
    elif contact.connect_stage != sheet_import.STAGE_CONNECTED:
        contact.connect_stage = sheet_import.connect_stage(
            joined, item["fields"].get("memo", ""),
            has_room=bool(contact.kakao_room_name))
    if not contact.firm_type:
        code, _why = firm_type.infer(item["fields"].get("firm", ""),
                                     contact.department, contact.title)
        if code != "unknown":
            contact.firm_type = code


def main() -> int:
    ap = argparse.ArgumentParser(description="투자사 딜공유 명단 만들기")
    ap.add_argument("path")
    ap.add_argument("--sheet", required=True, help="앱의 명단(탭) 이름")
    ap.add_argument("--owner", required=True,
                    help="담당 팀원 계정의 휴대폰번호(없으면 멈춘다)")
    ap.add_argument("--tab", action="append", default=[],
                    help="엑셀 파일 안의 탭 이름. 여러 번 적으면 **한 명단으로 합친다** "
                         "(먼저 적은 탭의 값이 이긴다)")
    ap.add_argument("--rulings", default=None,
                    help="겹치는 사람의 배정표 (번호,명단 이름)")
    ap.add_argument("--apply", action="store_true", help="실제로 저장")
    args = ap.parse_args()

    rulings = load_rulings(args.rulings) if args.rulings else {}
    data = Path(args.path).read_bytes()
    tabs = args.tab or [None]
    parsed_tabs = [parse_tab(sp.read_rows(args.path, data, tab)) for tab in tabs]
    parsed = merge(parsed_tabs)
    if not parsed["items"]:
        print("읽을 내용을 찾지 못했습니다. `이름` 과 `투자사명`(또는 `회사`) 이 "
              "있는 시트인지 확인하세요.")
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
    mine = [c for c in people
            if args.sheet in sheet_owner.labels_of(c.source_sheet)]
    mine_ids = {c.id for c in mine}
    # **이 명단 안에서만** 이름+회사로 찾는다. 번호가 없는 줄을 다시 넣을 때
    # 같은 줄을 찾는 유일한 길이다. 앱 전체를 이렇게 뒤지면 동명이인에서 갈린다.
    mine_by_name = {}
    for c in mine:
        mine_by_name.setdefault(
            merge_key({"fields": {"name": c.name or "", "firm": c.firm or ""}}), c)

    fills, moves, creates = [], [], []
    skips, seen = {}, set()
    no_phone = 0

    def skip(reason, note):
        skips.setdefault(reason, []).append(note)

    for item in parsed["items"]:
        where = f"{item['fields'].get('name', '')} · {item['fields'].get('firm', '')}"
        key = digits(item["fields"].get("phone", ""))

        if len(key) >= MIN_DIGITS:
            if key in seen:
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
        else:
            # 번호가 없다. 앱 전체와는 대조할 수 없고, **이 명단 안에서만** 찾는다.
            no_phone += 1
            found = mine_by_name.get(merge_key(item))

        if found is not None and found.id in mine_ids:
            fills.append((found, item, where))
        elif found is not None:
            moves.append((found, item, where))
        else:
            creates.append((item, where))

    # 배정표가 이 명단으로 정했는데 **시트에는 없는** 사람. 시트는 자료일 뿐이고
    # 배정을 정한 것은 사람이라, 시트에 안 적혔다고 배정이 없던 일이 되면 안 된다.
    orphans = []
    for key, label in sorted(rulings.items()):
        if label != args.sheet or key in seen:
            continue
        found = known.get(key)
        if found is None:
            skip("배정표에 있는데 시트에도 앱에도 없다", key[:3] + "…" + key[-4:])
        elif found.id not in mine_ids:
            orphans.append(found)

    total = len(fills) + len(moves) + len(creates) + len(orphans)
    print(f"명단 `{args.sheet}` · 담당 {owner.name} · 탭 "
          f"{', '.join(str(t) for t in tabs)}")
    for tab, one in zip(tabs, parsed_tabs):
        print(f"    탭 `{tab}` 에서 읽은 줄 {len(one['items'])}개 "
              f"· 달마다 늘어나는 칸 {len(one['columns'])}개")
    print(f"  합쳐서 {len(parsed['items'])}명 "
          f"(번호가 없는 사람 {no_phone}명 — 이 명단 안에서 이름+투자사명으로 찾는다)")
    print(f"  이 명단에 들어갈 줄 {total}개")
    print(f"    새로 만들 줄             {len(creates)}")
    print(f"    주인만 바꿀 줄           {len(moves)}"
          f"  (앱에 이미 있는 번호 — 이력이 그 줄에 붙어 있다)")
    print(f"    주인만 바꿀 줄(배정표)    {len(orphans)}")
    print(f"    이미 이 명단이라 채울 줄  {len(fills)}")
    print(f"  달마다 늘어나는 칸 {len(parsed['columns'])}개:")
    for label in parsed["columns"]:
        print(f"      {label}")
    for who, _item, where in moves:
        print(f"    옮김: {where}  ←→ 앱 `{who.firm or ''} {who.name}`")
    for who in orphans:
        print(f"    옮김(시트에 없음, 배정표): 앱 `{who.firm or ''} {who.name}`")
    if parsed["clashed"]:
        print(f"\n  ⚠ 한 탭 안에서 이름+투자사명이 같은 줄 {len(parsed['clashed'])}개 "
              f"— 합쳐졌습니다. 시트에서 확인하세요:")
        for note in parsed["clashed"]:
            print(f"       {note}")
    for tab, one in zip(tabs, parsed_tabs):
        if one["shifted"]:
            # 넣기 전에 **시트를 고쳐야 하는** 줄이다. 그냥 넣으면 같은 사람이
            # 두 줄로 갈린다 — 미리보기가 있는 이유가 이것이다.
            print(f"\n  ⚠ 탭 `{tab}` 에 칸이 한 칸씩 밀린 것으로 보이는 줄 "
                  f"{len(one['shifted'])}개 — **시트를 고친 뒤 넣으세요.** "
                  f"이대로 넣으면 다른 탭의 같은 사람과 안 합쳐져 두 줄이 됩니다:")
            for note in one["shifted"]:
                print(f"       {note}")
        if one["nameless"]:
            # 넣기는 넣는다. 다만 같은 줄인지 가리는 열쇠가 이름 하나뿐이라,
            # 다시 넣을 때 동명이인이 있으면 한 줄로 뭉칠 수 있다.
            print(f"\n  탭 `{tab}` 에 투자사명이 빈 줄 {len(one['nameless'])}개 "
                  f"— **넣습니다.** 이름만으로 찾게 되니 시트에서 채워 두면 좋습니다:")
            print(f"       {', '.join(one['nameless'])}")
        if one["skipped"]:
            print(f"\n  탭 `{tab}` 에서 못 읽은 줄 {len(one['skipped'])}개")
            for note in one["skipped"]:
                print(f"       {note}")
    if skips:
        # **조용히 버리지 않는다.** 몇 줄이 왜 빠졌는지 모르면 나중에 그 줄이
        # 없다는 것조차 알 수 없다.
        print(f"\n  건너뛸 줄 {sum(len(v) for v in skips.values())}개")
        for reason, rows in skips.items():
            print(f"    ── {reason} ({len(rows)}줄)")
            for note in rows:
                print(f"       {note}")
    if no_phone:
        print(f"\n  ⚠ 번호 없이 들어가는 사람 {no_phone}명. 명단과 이력은 보이고, "
              f"딜 소개도 **카톡방 이름을 채우면** 나갑니다(번호가 아니라 방으로 "
              f"나갑니다).\n     남는 위험: 나중에 번호를 채웠을 때 그 사람이 앱의 "
              f"다른 명단에도 있으면 두 줄이 됩니다 — 채우기 전에 확인하세요.")

    if not args.apply:
        print("\n미리보기입니다. 넣으려면 --apply 를 붙이세요.")
        db.close()
        return 0

    settings = db.execute(
        select(SheetOwner).where(SheetOwner.label == args.sheet)
    ).scalars().first()
    is_new_sheet = settings is None
    settings = sheet_owner.ensure(db, args.sheet, user_id=owner.id)
    settings.layout = cc.INVESTOR_MONTHLY
    if settings.user_id is None:
        # `ensure` 는 이미 있는 명단의 담당을 덮지 않는다(시트를 다시 올린 것만으로
        # 남의 담당이 넘어가면 안 된다). 비어 있는 자리는 채워도 뺏는 것이 아니다.
        settings.user_id = owner.id
    if is_new_sheet:
        # **이 사람들은 진짜 투자사다.** 딜 소개를 받을 사람들이라 투자사 수와
        # 발송 대상에 들어가야 맞다(스타트업 명단이 빠지는 것과 반대다).
        # 다시 돌릴 때는 건드리지 않는다 — 화면에서 사람이 정한 값을 임포트
        # 한 번이 되돌리면 안 된다.
        settings.is_hidden = 0

    # 월별 칸이 먼저다 — 줄의 값이 칸 id 를 키로 쓴다.
    columns = {c.label: c for c in cc.month_columns(db, args.sheet)}
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
                            name=item["fields"].get("name", ""), status="active")
        db.add(contact)
        apply_values(contact, item, columns)

    db.commit()
    print(f"\n새로 만든 줄 {len(creates)} · 옮긴 줄 {len(moves) + len(orphans)} "
          f"· 채운 줄 {len(fills)} · 칸 {len(parsed['columns'])}개")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
