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
  3. 표를 여는 것이 `NO` 가 아니다. 사람이 주인공인 명단이라 `이름` + `투자사명`
     이 표를 연다 — `NO` 칸이 아예 없는 시트가 있고, 있는 시트에서도 그 칸은
     줄을 세는 자리라 기록이 아니다(`STRUCTURAL`).

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
  · 시트가 번호를 안 적어 둔다. 딜공유 탭에는 번호 칸이 아예 없고, 번호 칸이 있는
    워크북에서도 그 칸이 빈 줄이 있다(105명 중 12명). 안 넣으면 그 사람들이
    통째로 사라지고, 명단도 이력도 화면에 안 뜬다.
  · **번호는 발송의 열쇠가 아니다.** 딜 소개는 이미 만들어진 카톡방으로 나간다
    (`dashboard._room_state` 는 채널·방 이름만 본다). 번호의 쓸모는 사람을
    대조하는 것이라, 번호가 없어도 명단과 이력은 온전하다.

남는 위험은 하나다 — 나중에 번호를 채웠을 때 그 사람이 앱의 다른 명단에도
있으면 두 줄이 된다. 채우기 모드가 그 자리를 막는다(아래).

## 만들기와 채우기는 **부르는 사람이 고른다** (`--mode`)

`import_new_list.py` 와 같은 어휘·같은 이유다. 이 작업의 가장 큰 위험은 채울
자리에 실수로 새로 만들어 **같은 사람이 두 줄이 되는 것**이고, 두 줄이 되면
딜 소개가 두 번 나간다. 위험한 쪽이 기본값이 되어서는 안 되고, 안전한 쪽이
기본값이면 "왜 아무것도 안 들어갔지" 를 매번 겪는다. **둘 다 적게 한다.**

    create  없는 사람은 만든다. 이미 있는 번호는 만들지 않고 주인만 바꾼다.
    fill    이 명단에 **이미 있는 줄만** 채운다. 없는 사람은 만들지 않고 알린다.

채우기는 만들기의 조용한 판이 아니다. 세 가지를 더 막는다.

  · **빈 칸에만 얹는다.** 만들기는 시트 값으로 덮어쓴다 — 그것이 맞다, 명단이
    그 시트에서 나온 것이니까. 채우기는 이미 서 있는 명단에 **나중에** 명함을
    얹는 일이라, 덮으면 사람이 앱에서 고쳐 둔 값이 시트 한 장에 지워진다.
    그리고 빈 칸만 채우면 **몇 번을 돌려도 두 번째부터는 0칸**이라, 두 번
    돌았는지 아닌지를 결과로 알 수 있다.
  · **칸도 만들지 않는다.** 명함을 찾으러 곁다리 탭을 붙이면 그 탭의 살림 칸
    (`사유`·`전화 여부`)이 남는 머리글로 읽혀 **달 칸으로 선다.** 줄을 안
    만드는 모드가 칸은 만드는 것이 앞뒤가 안 맞기도 하다. 못 세운 칸은 적어서
    알린다.
  · **명단 설정을 건드리지 않는다.** 배치·숨김은 화면과 `set_sheet_layout.py`
    가 정하는 값이다. 명함을 채우려고 부른 명령이 표 모양을 되돌리면 안 된다.

## 채우기가 사람을 찾는 순서

    ① 번호가 있고 **앱이 아는 번호**면 그 줄. 이 명단이면 채우고, 다른 명단이면
       건드리지 않고 알린다(옮기는 것은 만들기 모드의 일이다).
    ② 그 밖에는 **이 명단 안에서** 이름+투자사명.

②가 번호 있는 줄에도 필요하다. 채우려는 값이 바로 그 **번호**이기 때문이다 —
번호가 없어 명단에 들어온 줄을 번호로 찾을 수는 없다. 범위가 이 명단 하나라
틀려도 남의 명단에는 닿지 않고, 투자사명이 다르면 아예 안 걸린다.

그리고 이 순서가 위에 적은 "남는 위험" 을 막는다. 채우려는 번호가 앱의 다른
줄에 이미 있으면 ①에서 걸려 그 줄은 건너뛴다 — **같은 번호가 두 줄이 되는
자리가 없다.**

    python scripts/import_investor_list.py 파일.xlsx \
        --tab "탭1" --tab "탭2" --sheet "명단 이름" --owner 01000000000 --mode create
    python scripts/import_investor_list.py 파일.xlsx … --mode create --apply
    python scripts/import_investor_list.py 파일.xlsx … --mode fill --apply
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

# 표를 여는 **일련번호 칸**. 담을 값은 없지만 **자리는 잡아 둔다.**
#
# 안 잡으면 남는 머리글로 읽혀 `NO` 라는 달 칸이 서고, 그 칸이 고정 칸이 아니라
# 달 묶음 이어받기가 거기서 끊기지도 않는다 — 머리글 윗줄에 걸어 둔 표 제목이
# 칸 이름에 통째로 딸려 들어온다(`① 핵심 10명 … 딜소개 NO`). 사람이 달마다
# 적어 넣는 기록이 아니라 시트가 줄을 세는 데 쓰는 칸이다.
#
# 이름 앞에 `drop:` 을 붙여 담는다. 자리를 잡는 것과 값을 담는 것은 다른 일이라
# 구분이 필요하다 — 앱의 칸처럼 담으면 `VcContact` 에 없는 칸에 값을 얹으려 든다.
DROP = "drop:"
STRUCTURAL = [("NO", "no")]


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
    # 일련번호도 **완전히 일치**할 때만 건다. 두 글자뿐이라 포함으로 찾으면
    # 영문이 섞인 머리글에 걸린다(`NO 응답` · `SNO`).
    for label, key in STRUCTURAL:
        found = next((i for i, h in enumerate(header)
                      if h.strip().upper() == label and i not in taken), None)
        if found is not None:
            at[f"{DROP}{key}"] = found
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
                "shifted": [], "collapsed": {}, "labels": {}}
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

    # **같은 이름의 칸이 두 번 이상 나오면 뭉개진다.** 아래에서 줄의 값을 칸
    # 이름으로 담으므로(`item["months"]` 가 dict 다) 오른쪽 것이 왼쪽 것을
    # 덮는다 — 넉 달치 `IR 요청` 이 한 달치만 남는다.
    #
    # 달 묶음이 걸려 있으면 이름이 갈려 여기 걸릴 일이 없다. 걸리는 것은 원본
    # 시트가 달 묶음을 **첫 칸 머리글에만** 적어 둔 경우다(`8월 1차 딜 소개` 뒤에
    # 달 없는 `IR 요청` 이 따라온다). 그때 어느 달인지는 짐작할 수밖에 없어서
    # **짓지 않고 알린다** — 이름을 지어 붙이면 원본과 글자가 달라져 나란히
    # 놓고 대조할 수가 없고, 짐작이 틀리면 남의 달에 기록이 들어간다.
    collapsed = {}
    for _i, label in months:
        collapsed[label] = collapsed.get(label, 0) + 1
    collapsed = {label: n for label, n in collapsed.items() if n > 1}

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
            # 자리만 잡아 둔 칸(일련번호)은 담지 않는다 — 담을 자리가 없다.
            if not value or key.startswith(DROP):
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
            "shifted": shifted,
            # 뭉개진 달 칸 `{칸 이름: 몇 번}`. 위 설명 참고.
            "collapsed": collapsed,
            # 앱의 칸 → **시트가 그 칸을 부르는 이름.** 채우기 미리보기가 어느 칸을
            # 몇 개 채우는지 적을 때 쓴다. 이름을 스크립트에 따로 적어 두면 시트와
            # 글자가 갈려, 결과를 시트와 나란히 놓고 대조할 수가 없다.
            "labels": {key: header[i] for key, i in where.items()
                       if not key.startswith(DROP)}}


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
    labels = {}
    for parsed in parsed_tabs:
        for key, label in parsed.get("labels", {}).items():
            labels.setdefault(key, label)      # 먼저 적은 탭의 말이 이긴다
    return {"columns": columns, "items": [by_key[k] for k in order],
            "clashed": clashed, "labels": labels}


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


def existing_columns(db, sheet: str) -> dict:
    """이 명단에 **이미 서 있는** 달 칸. `{이름: 줄}`.

    `cc.month_columns` 를 부르지 않는다. 저쪽은 읽는 김에 **이번 달 칸을
    만들어 넣는다**(달이 바뀐 것을 알아채는 자리가 요청뿐이라 그렇게 두었다).
    미리보기가 그것을 부르면 `--apply` 없이 부른 명령이 칸을 만들고 저장까지
    한다 — 미리보기가 미리보기가 아니게 된다.
    """
    return {c.label: c for c in db.execute(
        select(ContactColumn).where(ContactColumn.sheet == sheet)
        .order_by(ContactColumn.position, ContactColumn.id)).scalars()}


def fill_plan(contact, item, columns) -> tuple:
    """채우기가 이 줄에 **무엇을 얹을지** 미리 정한다.

    `(얹을 것, 못 세운 달 칸 이름들)`. 얹을 것은 `[(칸, 값)]` 이고 칸 이름은
    앱의 칸 이름(`phone`) 또는 `note:키` 다.

    ## 빈 칸에만 얹는다

    만들기(`apply_values`)는 시트 값으로 덮는다 — 명단이 그 시트에서 나온 것이니
    그것이 맞다. 채우기는 **이미 서 있는 명단에 나중에 명함을 얹는** 일이라,
    덮으면 사람이 앱에서 고쳐 둔 값이 시트 한 장에 지워진다. 그리고 빈 칸만
    채우면 두 번째부터는 채울 것이 0칸이라, **두 번 돌았는지가 결과로 보인다.**

    ## 없는 달 칸은 만들지 않고 적어서 돌려준다

    명함을 찾으러 곁다리 탭을 붙이면 그 탭의 살림 칸(`사유`·`전화 여부`)이 남는
    머리글로 읽혀 달 칸이 되려 한다. 줄을 안 만드는 모드가 칸은 만드는 것도
    앞뒤가 안 맞는다. 버리지는 않는다 — 무엇을 못 세웠는지 보여야 사람이
    시트를 고치거나 화면에서 칸을 세운다.
    """
    todo, unknown = [], []
    for field, value in item["fields"].items():
        if not getattr(contact, field, ""):
            todo.append((field, value))
    values = cc.load_notes(contact.notes)
    for key, value in item["notes"].items():
        if not values.get(key):
            todo.append((f"note:{key}", value))
    for label, text in item["months"].items():
        column = columns.get(label)
        if column is None:
            unknown.append(label)
            continue
        if not values.get(cc.note_key(column.id)):
            todo.append((f"note:{cc.note_key(column.id)}", text))
    return todo, unknown


def fill_values(contact, todo) -> None:
    """`fill_plan` 이 정한 것을 그대로 얹는다.

    정하는 것과 얹는 것을 나눈 이유는 하나다 — **미리보기와 실제 저장이 같은
    판단을 지나야** 미리보기가 미리보기 구실을 한다. 세어 본 칸 수와 실제로
    들어간 칸 수가 다르면 어느 쪽도 믿을 수 없다.
    """
    values = cc.load_notes(contact.notes)
    for key, value in todo:
        if key.startswith("note:"):
            values[key[5:]] = value
        else:
            setattr(contact, key, value)
    contact.notes = cc.dump_notes(values)


def main() -> int:
    ap = argparse.ArgumentParser(description="투자사 딜공유 명단 만들기 / 채우기")
    ap.add_argument("path")
    ap.add_argument("--sheet", required=True, help="앱의 명단(탭) 이름")
    # 채우기에서는 담당을 바꾸지 않지만 **그래도 받는다.** 이 값이 맞아야
    # 계정이 있는 DB 를 보고 있다는 것이 확인되고(없으면 멈춘다), 만들기와
    # 채우기의 부르는 법이 갈리지 않는다 — 갈리면 급할 때 둘을 헷갈린다.
    ap.add_argument("--owner", required=True,
                    help="담당 팀원 계정의 휴대폰번호(없으면 멈춘다). "
                         "채우기에서는 담당을 바꾸지 않고 확인만 한다")
    # 기본값을 두지 않는다 — 위 설명 참고. `import_new_list.py` 와 같은 말이다.
    ap.add_argument("--mode", required=True, choices=["create", "fill"],
                    help="create=없는 줄을 만든다 · fill=있는 줄의 빈 칸만 채운다")
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

    # 채우기는 **있는 칸에만** 얹는다. 미리보기 단계에서 읽으므로 여기서도
    # 이번 달 칸을 만들어 넣는 `cc.month_columns` 는 부르지 않는다.
    # (만들기는 아래 저장 단계에서 없는 칸을 세우므로 여기서 읽을 것이 없다.)
    columns = existing_columns(db, args.sheet) if args.mode == "fill" else {}

    fills, moves, creates = [], [], []
    skips, seen = {}, set()
    no_phone = 0
    # 채우기: 줄마다 얹을 것 · 칸마다 몇 번 얹는지 · 못 세운 달 칸.
    plans, per_column, unseen_columns = {}, {}, {}
    taken_rows = {}

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
            if found is None and args.mode == "fill":
                # **채우려는 값이 바로 그 번호다.** 번호가 없어 명단에 들어온 줄을
                # 번호로 찾을 수는 없으니, 이 명단 안에서 이름+투자사명으로 한 번
                # 더 찾는다. 앱이 모르는 번호라 여기서 이어도 같은 번호가 두 줄이
                # 되는 자리가 없다(아는 번호였으면 위에서 이미 걸렸다).
                found = mine_by_name.get(merge_key(item))
        else:
            # 번호가 없다. 앱 전체와는 대조할 수 없고, **이 명단 안에서만** 찾는다.
            no_phone += 1
            found = mine_by_name.get(merge_key(item))

        if found is not None and found.id in mine_ids:
            if found.id in taken_rows:
                # 시트의 두 줄이 앱의 한 줄을 가리킨다. 조용히 둘 다 얹으면 나중
                # 것이 앞 것을 덮은 것인지 아닌지조차 알 수 없다.
                skip("시트의 두 줄이 앱의 같은 줄을 가리킨다",
                     f"{where}  ←→ {taken_rows[found.id]}")
                continue
            taken_rows[found.id] = where
            if args.mode == "fill":
                todo, unknown = fill_plan(found, item, columns)
                plans[found.id] = (found, todo, where)
                for field, _value in todo:
                    per_column[field] = per_column.get(field, 0) + 1
                for label in unknown:
                    unseen_columns[label] = unseen_columns.get(label, 0) + 1
            fills.append((found, item, where))
        elif found is not None:
            if args.mode == "fill":
                # 그 사람은 앱에 있지만 **다른 명단**이다. 여기서 옮기면 남의
                # 명단에서 사람이 빠진다 — 옮기는 것은 만들기 모드의 일이다.
                skip("앱의 다른 명단에 있다 (옮기려면 --mode create)", where)
                continue
            moves.append((found, item, where))
        elif args.mode == "fill":
            skip("이 명단에 그 줄이 없다 — 채우기 모드에서는 만들지 않는다", where)
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
            if args.mode == "fill":
                skip("배정표가 이 명단으로 정했다 (옮기려면 --mode create)",
                     f"{found.firm or ''} {found.name}")
            else:
                orphans.append(found)

    total = len(fills) + len(moves) + len(creates) + len(orphans)
    print(f"명단 `{args.sheet}` · 담당 {owner.name} · 모드 {args.mode} · 탭 "
          f"{', '.join(str(t) for t in tabs)}")
    for tab, one in zip(tabs, parsed_tabs):
        print(f"    탭 `{tab}` 에서 읽은 줄 {len(one['items'])}개 "
              f"· 달마다 늘어나는 칸 {len(one['columns'])}개")
    print(f"  합쳐서 {len(parsed['items'])}명 "
          f"(번호가 없는 사람 {no_phone}명 — 이 명단 안에서 이름+투자사명으로 찾는다)")
    print(f"  이 명단에 들어갈 줄 {total}개")
    if args.mode == "create":
        # 채우기에서는 셋 다 늘 0이라 적지 않는다 — 0만 늘어놓으면 정작 봐야 할
        # 칸 수가 묻힌다. 달 칸 목록도 같은 이유로 만들기에서만 편다(채우기는
        # 아래에서 **채운 칸**과 **못 세운 칸**만 적는다).
        print(f"    새로 만들 줄             {len(creates)}")
        print(f"    주인만 바꿀 줄           {len(moves)}"
              f"  (앱에 이미 있는 번호 — 이력이 그 줄에 붙어 있다)")
        print(f"    주인만 바꿀 줄(배정표)    {len(orphans)}")
        print(f"    이미 이 명단이라 채울 줄  {len(fills)}")
        print(f"  달마다 늘어나는 칸 {len(parsed['columns'])}개:")
        for label in parsed["columns"]:
            print(f"      {label}")
    else:
        # **몇 칸을 채우고 몇 줄이 빈칸으로 남는지.** 채우기의 결과는 줄 수가
        # 아니라 칸 수다 — 줄은 이미 다 서 있고, 달라지는 것은 그 안이다.
        cells = sum(len(todo) for _c, todo, _w in plans.values())
        touched = sum(1 for _c, todo, _w in plans.values() if todo)
        # 칸 이름은 **시트가 부르는 말** 그대로다. 스크립트에 따로 적어 두면
        # 시트와 글자가 갈려 결과를 나란히 놓고 대조할 수가 없다.
        # 달 칸은 시트 머리글이 곧 그 칸의 이름이라 명단 쪽에서 되찾는다.
        names = dict(parsed["labels"])
        names.update({f"note:{cc.note_key(col.id)}": label
                      for label, col in columns.items()})
        print(f"\n  채울 칸 {cells}개 · 그중 줄 {touched}개"
              f"  (빈 칸에만 얹습니다 — 두 번 돌리면 0칸입니다)")
        for field, count in sorted(per_column.items(), key=lambda kv: -kv[1]):
            print(f"      {names.get(field, field):<30} {count}")
        # 이 명단에 서 있는데 시트가 닿지 않은 줄. **빈칸으로 남는다.**
        blank = len(mine) - len(plans)
        print(f"  시트에서 못 찾아 그대로 두는 줄 {blank}개 "
              f"(이 명단 {len(mine)}줄 중) — **빈칸으로 둡니다. 지어내지 않습니다.**")
        if unseen_columns:
            print(f"  시트에는 있는데 이 명단에 없는 칸 {len(unseen_columns)}개 "
                  f"— **세우지 않습니다**(채우기는 칸을 만들지 않습니다):")
            for label, count in sorted(unseen_columns.items(), key=lambda kv: -kv[1]):
                print(f"      {label}  ({count}줄)")
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
        if one.get("collapsed"):
            # **넣기 전에 시트를 고쳐야 하는 자리다.** 이대로 넣으면 그 이름의
            # 칸 하나에 마지막 달 값만 남는다 — 화면에는 칸이 멀쩡히 서 있어서
            # 다른 달 기록이 없어진 것을 아무도 눈치채지 못한다.
            print(f"\n  ⚠ 탭 `{tab}` 에 **이름이 같은 달 칸** "
                  f"{len(one['collapsed'])}종 — 한 칸으로 뭉개져 **맨 오른쪽 것만 "
                  f"남습니다.** 시트 머리글에 달을 적어 두면 갈립니다:")
            for label, times in sorted(one["collapsed"].items(),
                                       key=lambda kv: -kv[1]):
                print(f"       {label}  ({times}번)")
        if one["shifted"]:
            # 넣기 전에 **시트를 고쳐야 하는** 줄이다. 그냥 넣으면 같은 사람이
            # 두 줄로 갈린다 — 미리보기가 있는 이유가 이것이다.
            print(f"\n  ⚠ 탭 `{tab}` 에 칸이 한 칸씩 밀린 것으로 보이는 줄 "
                  f"{len(one['shifted'])}개 — **시트를 고친 뒤 넣으세요.** "
                  f"이대로 넣으면 다른 탭의 같은 사람과 안 합쳐져 두 줄이 됩니다:")
            for note in one["shifted"]:
                print(f"       {note}")
        if one["nameless"]:
            # 만들기는 넣는다(빼면 그 사람이 사라진다). 채우기는 잇는 열쇠가
            # 이름+투자사명인데 그 절반이 비어 있는 줄이라, **이름만 같은 남의
            # 줄에 얹힐 수 있다** — 그래서 말이 달라야 한다.
            what = ("**넣습니다.** 이름만으로 찾게 되니" if args.mode == "create"
                    else "이름만 남아 **엉뚱한 줄에 얹힐 수 있습니다.**")
            print(f"\n  탭 `{tab}` 에 투자사명이 빈 줄 {len(one['nameless'])}개 "
                  f"— {what} 시트에서 채워 두면 좋습니다:")
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
    if no_phone and args.mode == "create":
        # 채우기에서는 알릴 것이 아니다 — 줄을 만들지 않으므로 "번호 없이
        # 들어가는" 사람이 없고, 남는 위험(같은 번호가 두 줄)은 채우기가
        # 순서로 막는다(맨 위 설명 참고).
        print(f"\n  ⚠ 번호 없이 들어가는 사람 {no_phone}명. 명단과 이력은 보이고, "
              f"딜 소개도 **카톡방 이름을 채우면** 나갑니다(번호가 아니라 방으로 "
              f"나갑니다).\n     남는 위험: 나중에 번호를 채웠을 때 그 사람이 앱의 "
              f"다른 명단에도 있으면 두 줄이 됩니다 — 채우기 전에 확인하세요.")

    if not args.apply:
        print("\n미리보기입니다. 넣으려면 --apply 를 붙이세요.")
        db.close()
        return 0

    if args.mode == "fill":
        # **명단 설정도 칸도 건드리지 않는다.** 배치·숨김은 화면과
        # `set_sheet_layout.py` 가 정하는 값이라, 명함을 채우려고 부른 명령이
        # 표 모양을 되돌리면 안 된다(투자사 명함 표로 맞춰 둔 명단이 이 한 줄에
        # 딜공유 표로 돌아가던 자리다).
        cells = 0
        for contact, todo, _where in plans.values():
            if not todo:
                # 얹을 것이 없으면 줄을 건드리지 않는다. `dump_notes` 가 빈 값을
                # 털어 내므로, 그냥 지나가도 줄이 바뀐 것으로 기록된다.
                continue
            fill_values(contact, todo)
            cells += len(todo)
        db.commit()
        print(f"\n채운 줄 {sum(1 for _c, t, _w in plans.values() if t)} "
              f"· 채운 칸 {cells}개 · 새로 만든 줄 0 · 새로 세운 칸 0")
        db.close()
        return 0

    settings = db.execute(
        select(SheetOwner).where(SheetOwner.label == args.sheet)
    ).scalars().first()
    is_new_sheet = settings is None
    settings = sheet_owner.ensure(db, args.sheet, user_id=owner.id)
    if settings.user_id is None:
        # `ensure` 는 이미 있는 명단의 담당을 덮지 않는다(시트를 다시 올린 것만으로
        # 남의 담당이 넘어가면 안 된다). 비어 있는 자리는 채워도 뺏는 것이 아니다.
        settings.user_id = owner.id
    if is_new_sheet:
        # **이 사람들은 진짜 투자사다.** 딜 소개를 받을 사람들이라 투자사 수와
        # 발송 대상에 들어가야 맞다(스타트업 명단이 빠지는 것과 반대다).
        settings.is_hidden = 0
        # 배치도 여기서만 정한다. **다시 돌릴 때는 건드리지 않는다** — 숨김과
        # 같은 이유다. 화면에서(또는 `set_sheet_layout.py` 로) 사람이 다른 표로
        # 맞춰 둔 명단이, 같은 워크북을 한 번 더 올렸다는 이유로 옛 표로
        # 되돌아가면 안 된다.
        settings.layout = cc.INVESTOR_MONTHLY

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
