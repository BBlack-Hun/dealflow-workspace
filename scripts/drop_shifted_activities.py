"""**줄이 한 칸 밀려 들어간 활동 이력의 잔재를 지운다** — 미리보기가 기본이다.

2026-09-10 시트 임포트가 활동 이력을 **담당자에게 한 칸씩 앞으로 밀려** 넣었다.
09-22 임포트가 옳은 자리에 다시 넣었지만 **잔재를 안 지웠다** — 임포트에는
삭제 경로가 없다(`services/sheet_import.apply_sheet_a` 는 중복이면 건너뛸 뿐
지우지 않는다). 그래서 **한 기록이 두 사람에게 동시에** 붙어 있고, 그만큼
딜소개 횟수·IR 요청 횟수가 부풀어 있다.

    # ① 무엇이 어떻게 갈리는지 본다 (**기본이 미리보기다** — DB 에 안 쓴다)
    python scripts/drop_shifted_activities.py

    # ② 되돌릴 파일을 떠 두고 실제로 지운다
    python scripts/drop_shifted_activities.py --apply --save-baseline /tmp/a.json

    # ③ 지운 것이 계획대로인지 맞춘다
    python scripts/drop_shifted_activities.py --baseline /tmp/a.json

    # ④ 되돌린다 (지운 줄을 **id 까지 그대로** 다시 넣는다)
    python scripts/drop_shifted_activities.py --restore /tmp/a.json --apply

`--apply` 없이는 **DB 를 읽기 전용(`mode=ro`)으로 연다.** 쓸 길 자체를 막는다 —
`scripts/set_group_from_pref.py` · `scripts/clean_group_name.py` 가 같은 방식이고,
이 스크립트도 그 뼈대를 따른다.

## 두 가지 일을 한 판에 한다 — 그런데 **근거가 다르다**

같은 임포트 사고에서 나온 두 모양이라 따로 돌리면 수가 안 맞는다(한쪽이 다른
쪽의 짝을 지워 버릴 수 있다). 그래서 한 계획으로 세우되 **갈래를 갈라 센다.**

  ① **밀려 들어간 잔재** — 기록이 `contact_id` 에 붙어 있는데 실제 주인은
     `contact_id + 1` 이다. 지우면 그 기록은 **옆 사람에게만** 남는다.
  ② **같은 사람 안 중복** — 기록이 **같은 사람에게 두 줄**로 있다. 09-10 때
     달 인식이 실패해 `month=NULL` 로 들어간 줄과, 09-22 에 `month` 가 붙어
     들어온 같은 글이 중복 열쇠(`contact_id, kind, content, month`)에서 **다른
     줄로 취급**되어 새로 만들어졌다. 지우면 그 기록은 **같은 사람에게** 남는다.

두 갈래 모두 **09-10 임포트가 만든 줄만** 지운다. 09-22 줄은 한 줄도 안 건드린다.

## 판정 — 사용자가 손으로 9줄을 지울 때 쓴 자와 같은 자

한 줄씩 셋을 본다. **셋이 다 참일 때만** 잔재로 본다.

  1. `contact_id + 1` 에 **같은 `(kind, content)`** 줄이 있고, 그 줄이
     **09-22 임포트가 넣은 줄**이다.
  2. **그 사람의 월별 칸(`vc_contacts.notes`)에는 그 글이 없다.**
  3. **다음 사람 칸에는 있다.**

**월별 칸이 기준이 되는 이유**는 그 칸이 **전화번호로 맞춰 들어오기** 때문이다
(`scripts/import_new_list.py` 의 `by_phone`). 활동 이력은 이름·회사로 맞춰
들어오는데(`sheet_import.apply_sheet_a`) 줄이 밀리면 그 쪽이 통째로 어긋난다.
번호로 맞춘 칸은 안 흔들리므로, **어느 쪽이 옳은 자리인지 가르는 자**가 된다.

이 자가 맞는지는 **사용자가 이미 지운 9줄로 맞춰 봤다**(act 1288·1376·1393·
1862·1904·1951·2043·2046·2610). 그 아홉이 전부 `잔재확정` 으로, 사용자가 일부러
남긴 act 1948 은 `아님` 으로 갈린다. `--self-check` 가 그것을 매번 다시 센다.

## **글자는 앞 몇 글자로 맞추지 않는다**

앞자리만 보면 딜 소개 글은 거의 다 걸린다 — 같은 회차 글이 날짜로 시작하고
(`7/1 …`) 기업 목록이 이어지는 한 가지 모양이기 때문이다.

**회차 원문 조각 전체**(`ContactActivity.raw_text`, 없으면 `content`)가 월별 칸
값 안에 **통째로 들어 있는가**를 본다. 월별 칸 하나에는 그 달 회차가 여럿
쌓여 있으므로(`7/1 … \\n\\n7/8 … \\n\\n7/15 …`) 부분 문자열로 찾는 것이 맞다.

맞추기 전에 양쪽을 **두 가지로 다듬어** 둘 다 본다. 활동 줄과 월별 칸은 **서로
다른 임포트**가 서로 다른 시트 내보내기에서 읽어 온 글이라 눈에 안 보이는
자리가 어긋나 있다:

  · `NFKC` 정규화 — 전각 괄호·전각 쉼표가 반각과 갈리지 않게.
  · 이어지는 공백·줄바꿈을 한 칸으로, 앞뒤를 떼고 (`L1`).
  · 그 위에 **공백을 통째로 지운 판**을 하나 더 (`L2`).

**둘 중 하나라도 본인 칸에서 찾으면 잔재가 아니다.** 느슨한 쪽을 함께 보는
것이 안전한 방향이다 — 못 찾아서 지우는 것이 찾아서 안 지우는 것보다 나쁘다.

## **`deal_intro` 오탐을 어떻게 걸렀나** — 여기가 제일 위험하다

딜 소개 글은 **그 회차에 뿌린 기업 목록**이라 여러 투자사에게 같은 글이 간다.
그래서 "옆 사람 칸에도 있다" 는 것만으로는 아무것도 못 가른다 — 원래 둘 다
있는 것이 정상이다. 사용자가 act 1948 을 남긴 이유가 그것이다.

세 겹으로 거른다. **딜소개 708줄 중 592줄이 이 겹들에 걸려 `잔재확정` 에서
빠진다.**

  **가드 1 — 본인 칸에 글이 있으면 아니다.** 판정 2번 그대로다. 시트가 이
  사람에게도 그 회차를 적어 두었다는 뜻이므로 두 사람에게 다 있는 것이 맞다.

  **가드 2 — 같은 사람에게 09-22 줄이 들어왔으면 아니다.** 09-22 임포트가
  **같은 `contact_id`** 에 같은 `(kind, content)` 줄을 새로 넣었다면, 옳은
  자리를 다시 잡은 그 임포트가 "이 기록은 이 사람 것" 이라고 말한 것이다.
  **글자 맞추기를 한 번도 안 지나는 근거**라 이 가드가 제일 세다. 이런 줄은
  ①이 아니라 ②(같은 사람 안 중복)로 간다 — 지우기는 하되 **같은 사람에게**
  남는다.

  **가드 3 — 기업 이름이 본인 칸에 절반 이상 흩어져 있으면 애매다.** 회차
  글자는 안 맞는데(시트 쪽 표기가 달라서) 그 회차의 기업 이름이 본인 칸
  여기저기에 있다면, 표기만 다를 뿐 같은 회차일 수 있다. `company_names` 에
  이미 쪼개져 있는 이름을 쓴다(`services/company_names.split` 이 쪼갠 것이다).

  절반으로 끊는 이유: 한 회차는 보통 기업 서넛이고, 인기 있는 기업은 달마다
  다시 소개되므로 **하나쯤 겹치는 것은 우연**이다. 실제로 걸린 줄의 겹침은
  0 아니면 0.6 이상으로 갈려 있어 가운데가 거의 비어 있다.

## **갈래는 셋이고, 애매한 줄은 안 지운다**

`잔재확정` 만 지운다. `애매` · `아님` 은 **세어서 보여 줄 뿐 건드리지 않는다.**
사용자가 act 1948 에서 한 판단을 그대로 규칙으로 옮긴 것이다 — 자동으로 지우면
그 판단을 할 기회 자체가 없어진다.

## ②에서 **어느 쪽을 남기나 — 달이 있는 쪽**

짝을 칸마다 세어 보면 **09-22 쪽이 모든 칸에서 같거나 더 차 있고, 09-10 쪽에만
있는 값은 하나도 없다**(`month` 10/339 대 339/339 · `happened_at` 10/337 대
337/337 · `weekday` 같음 · `company_names` 334 대 334). 그래서 **달을 채워
합치지 않는다** — 채워 봐야 `happened_at` · `weekday` 가 빈 열등한 줄이 남고,
그 둘은 주간·월간 보고가 읽는 칸이다.

**먼저 생긴 쪽(09-10)을 남기면 안 되는 더 센 이유**가 있다. 임포트의 중복
열쇠가 `(contact_id, kind, content, month)` 라, 달이 빈 줄을 남기면 **다음에
같은 시트를 올릴 때 달이 붙은 줄이 또 새로 생긴다.** 달이 붙은 쪽을 남기면
다음 임포트가 그 줄에 걸려 건너뛴다 — 몇 번을 올려도 한 줄이다.

**달이 다르면 안 지운다.** 같은 사람에게 같은 글이 있어도 `month` 가 서로 다른
줄이 10개 있는데, 들여다보면 `happened_at` 도 다르다(`2026-06-18` 대
`2026-07-01`). 짧은 기업 목록 하나가 두 달에 각각 소개된 **서로 다른 회차**다.
`month=NULL` 이거나 짝과 **달이 같을 때만** 지운다.

## **지우기지 감추기가 아니다** — `undone_at` 을 안 쓰는 이유

이 표에는 되돌림 표시(`ContactActivity.undone_at`)가 있고, 모든 ORM 조회에서
한 자리로 걸러진다(`models._hide_undone_activities`). 그런데 **임포트의 중복
검사도 그 조회를 지난다**(`sheet_import` 의 `db.execute(select(...))`). 감춰만
두면 다음 임포트가 그 줄을 못 보고 **같은 줄을 다시 만든다.** 감춘 자리에
잔재가 다시 쌓이는 것이라 여기서는 지우는 것이 맞다.

사용자가 먼저 지운 9줄도 지우기였다. 되돌릴 길은 `--save-baseline` 이 맡는다 —
**줄 전체를 id 까지 떠 두므로** `--restore` 가 원래 번호 그대로 되살린다.

## 이름을 찍지 않는다

이 표에는 투자사·기업 이야기가 들어 있다. 미리보기는 **id 와 값의 모양**(길이 ·
갈래 · 달)만 찍는다. 값 자체는 `--show-values` 일 때만 본다. 떠 둔 되돌리기
파일에는 값이 그대로 들어 있으니 **저장소 밖(`/tmp`)에 두어라.**
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TABLE = "contact_activities"

#: 줄이 밀려 들어간 임포트의 날. 이 날 만들어진 줄만 지운다.
SHIFT_DAY = "2026-09-10"
#: 옳은 자리에 다시 넣은 임포트의 날. 이 날 줄은 **한 줄도 안 건드린다.**
FIX_DAY = "2026-09-22"
#: 몇 칸 밀렸나. 담당자 줄 번호가 하나씩 앞으로 밀렸다.
SHIFT = 1
#: 기업 이름이 본인 칸에 이만큼 흩어져 있으면 `애매` 로 내린다 (가드 3).
OVERLAP_LIMIT = 0.5

#: 사용자가 손으로 지운 잔재 9줄. `--self-check` 가 이 아홉이 전부 `잔재확정`
#: 으로 갈리는지 다시 센다 — 판정을 고쳤을 때 자가 어긋나면 여기서 걸린다.
KNOWN_RESIDUE = (1288, 1376, 1393, 1862, 1904, 1951, 2043, 2046, 2610)
#: 사용자가 **일부러 남긴** 줄. 내용이 기업 목록이라 두 사람 칸에 다 있다.
KNOWN_KEEP = 1948

RESIDUE = "잔재확정"
AMBIGUOUS = "애매"
NOT_RESIDUE = "아님"

#: 지울 줄의 갈래. ①은 옆 사람에게, ②는 같은 사람에게 기록이 남는다.
BY_SHIFT = "밀린 잔재"
BY_DUP = "같은 사람 안 중복"

COLUMNS = ("id", "contact_id", "month", "kind", "content", "happened_at",
           "source", "created_at", "updated_at", "weekday", "company_names",
           "company_count", "raw_text", "batch_key", "undone_at")

_WS = re.compile(r"\s+")
_ZERO_WIDTH = ("​", "﻿", "‌", "‍")


def norm_loose(text: str) -> str:
    """이어지는 공백을 한 칸으로. 활동 줄과 월별 칸이 **다른 임포트**를 지나
    와서 줄바꿈·공백이 서로 다르다."""
    text = unicodedata.normalize("NFKC", text or "")
    for mark in _ZERO_WIDTH:
        text = text.replace(mark, "")
    return _WS.sub(" ", text).strip()


def norm_tight(text: str) -> str:
    """공백을 아예 뺀 판. 한쪽이 `7/1○○○` 처럼 붙어 있어도 맞는다."""
    return norm_loose(text).replace(" ", "")


def open_db(path: Path, write: bool) -> sqlite3.Connection:
    """`--apply` 가 없으면 **읽기 전용으로** 연다. 미리보기가 쓸 길을 막는다."""
    if write:
        return sqlite3.connect(str(path))
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def pad(text: str, width: int, right: bool = False) -> str:
    """표의 칸을 **눈에 보이는 너비**로 맞춘다 (한글 한 글자가 두 칸을 먹는다)."""
    room = max(0, width - sum(
        2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text))
    return (" " * room + text) if right else (text + " " * room)


class Item:
    """계획 한 줄. **미리보기와 저장이 이 한 벌을 같이 지난다.**"""

    def __init__(self, row, tier, why, keeper=None, family=None, overlap=0.0):
        self.row = row
        self.tier = tier            # 잔재확정 | 애매 | 아님
        self.why = why              # 사람이 읽을 근거 한 줄
        self.keeper = keeper        # 지운 뒤 그 기록을 들고 있을 줄의 id
        self.family = family        # 밀린 잔재 | 같은 사람 안 중복
        self.overlap = overlap      # 기업 이름이 본인 칸에 겹친 비율 (가드 3)

    @property
    def drops(self) -> bool:
        return self.tier == RESIDUE


def read_rows(con: sqlite3.Connection):
    cols = ", ".join(COLUMNS)
    return [dict(zip(COLUMNS, r))
            for r in con.execute(f"SELECT {cols} FROM {TABLE} ORDER BY id")]


def read_notes(con: sqlite3.Connection):
    """담당자마다의 **월별 칸 값들.** 읽기는 앱과 같은 자리를 쓴다."""
    from app.services.contact_columns import load_notes

    out = {}
    for contact_id, raw in con.execute("SELECT id, notes FROM vc_contacts"):
        # `dump_notes` 가 빈 값을 안 담으므로 **키가 없으면 그 칸은 비어 있다** —
        # 곧 그 달 그 갈래에 적힌 것이 없다는 뜻이다.
        out[contact_id] = {k: v for k, v in load_notes(raw).items() if v}
    return out


def _in_cells(cells, needle: str) -> bool:
    """이 글이 그 사람 월별 칸 **어딘가에 통째로** 들어 있는가.

    **두 가지로 다듬어 둘 다 본다.** 하나라도 찾으면 참이다 — 느슨한 쪽이
    안전한 방향이다(못 찾아서 지우는 쪽이 더 나쁘다).
    """
    for shape in (norm_loose, norm_tight):
        target = shape(needle)
        if target and any(target in shape(value) for value in cells.values()):
            return True
    return False


def _companies(row) -> list:
    try:
        names = json.loads(row["company_names"] or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(names, list):
        return []
    return [n for n in (norm_tight(str(x)) for x in names) if len(n) >= 2]


def _overlap(row, cells) -> float:
    """이 회차의 기업 이름이 본인 칸에 얼마나 흩어져 있나 (가드 3)."""
    names = _companies(row)
    if not names:
        return 0.0
    blob = norm_tight(" ".join(cells.values()))
    return sum(1 for n in names if n in blob) / len(names)


def plan(con: sqlite3.Connection):
    """줄마다 `Item`. **DB 를 읽기만 한다.**

    미리보기와 저장이 **같은 계획 하나**를 지나야 미리 본 것이 실제와 같다.
    """
    rows = read_rows(con)
    notes = read_notes(con)
    same = defaultdict(list)
    for row in rows:
        same[(row["contact_id"], row["kind"], row["content"])].append(row)

    items = []
    for row in rows:
        if (row["created_at"] or "")[:10] != SHIFT_DAY:
            continue
        key = (row["contact_id"], row["kind"], row["content"])
        mine = [r for r in same[key] if (r["created_at"] or "")[:10] == FIX_DAY]
        nxt = [r for r in same[(row["contact_id"] + SHIFT, row["kind"],
                                row["content"])]
               if (r["created_at"] or "")[:10] == FIX_DAY]

        # ② 같은 사람 안 중복 — **가드 2 이기도 하다.** 옳은 자리를 다시 잡은
        # 임포트가 같은 사람에게 줄을 넣었다면 그 기록은 이 사람 것이 맞다.
        if mine:
            keeper = mine[0]
            if row["month"] is None or row["month"] == keeper["month"]:
                items.append(Item(row, RESIDUE,
                                  "같은 사람에게 달이 붙은 09-22 줄이 있다",
                                  keeper["id"], BY_DUP))
            else:
                # 달도 날짜도 다르다 — 같은 글이 두 달에 각각 소개된 **다른 회차**다.
                items.append(Item(row, NOT_RESIDUE,
                                  "같은 사람의 09-22 줄과 **달이 다르다** "
                                  "— 서로 다른 회차",
                                  None, BY_DUP))
            continue

        if not nxt:
            continue                      # 조건 1 이 아니다 — 후보가 아니다

        cells = notes.get(row["contact_id"], {})
        needle = row["raw_text"] or row["content"]
        if not _in_cells(notes.get(row["contact_id"] + SHIFT, {}), needle):
            # 조건 3 이 아니다. 옆 사람 칸이 그 글을 모르면 밀렸다고 말할 수 없다.
            items.append(Item(row, NOT_RESIDUE,
                              "다음 사람 월별 칸에 그 글이 없다", None, BY_SHIFT))
            continue
        if _in_cells(cells, needle):
            # 가드 1 — 시트가 이 사람에게도 그 회차를 적어 두었다.
            items.append(Item(row, NOT_RESIDUE,
                              "본인 월별 칸에도 그 글이 그대로 있다",
                              None, BY_SHIFT))
            continue
        ratio = _overlap(row, cells)
        if ratio >= OVERLAP_LIMIT:
            # 가드 3 — 글자는 안 맞는데 기업 이름이 본인 칸에 흩어져 있다.
            items.append(Item(row, AMBIGUOUS,
                              f"기업 이름이 본인 칸에 {ratio:.0%} 겹친다",
                              None, BY_SHIFT, ratio))
            continue
        items.append(Item(row, RESIDUE,
                          "본인 칸에 없고 다음 사람 칸에 있다",
                          nxt[0]["id"], BY_SHIFT, ratio))
    return items, rows


# ─────────────────────────────────────────────────────────────────────────────
# 미리보기
# ─────────────────────────────────────────────────────────────────────────────

def print_tiers(items) -> None:
    kinds = ("deal_intro", "ir_request", "meeting")
    print(f"① 후보 {len(items)}줄 — 갈래별·판정별")
    print("   " + pad("판정", 12) + pad("갈래", 20)
          + "".join(pad(k, 12, right=True) for k in kinds)
          + pad("합", 8, right=True) + pad("사람", 8, right=True))
    for tier in (RESIDUE, AMBIGUOUS, NOT_RESIDUE):
        for family in (BY_SHIFT, BY_DUP):
            mine = [it for it in items
                    if it.tier == tier and it.family == family]
            if not mine:
                continue
            counts = Counter(it.row["kind"] for it in mine)
            print("   " + pad(tier, 12) + pad(family, 20)
                  + "".join(pad(str(counts.get(k, 0)), 12, right=True)
                            for k in kinds)
                  + pad(str(len(mine)), 8, right=True)
                  + pad(str(len({it.row["contact_id"] for it in mine})),
                        8, right=True))
    drop = [it for it in items if it.drops]
    print("   " + pad("─ 지운다", 32)
          + "".join(pad(str(sum(1 for it in drop if it.row["kind"] == k)),
                        12, right=True) for k in kinds)
          + pad(str(len(drop)), 8, right=True)
          + pad(str(len({it.row["contact_id"] for it in drop})), 8, right=True))
    print()
    print("   근거별")
    for why, count in Counter(it.why for it in items).most_common():
        print("     " + pad(why, 56) + pad(str(count), 6, right=True))
    print()


def print_counts(items, rows) -> None:
    """**지우기 전/후로 몇 명의 횟수가 어떻게 바뀌나.**

    이 표가 이 일의 목적이다 — 잔재를 지우는 까닭이 부풀어 있는 횟수이기 때문에.
    """
    dropped = {it.row["id"] for it in items if it.drops}
    print("② 횟수가 어떻게 바뀌나")
    print("   " + pad("갈래", 14) + pad("전", 8, right=True)
          + pad("→", 4, right=True) + pad("후", 8, right=True)
          + pad("줄어듦", 9, right=True) + pad("사람", 8, right=True)
          + pad("0 이 되는 사람", 16, right=True))
    for kind in ("deal_intro", "ir_request", "meeting"):
        before = Counter(r["contact_id"] for r in rows if r["kind"] == kind)
        after = Counter(r["contact_id"] for r in rows
                        if r["kind"] == kind and r["id"] not in dropped)
        moved = {c for c in before if before[c] != after.get(c, 0)}
        zeroed = {c for c in moved if after.get(c, 0) == 0}
        print("   " + pad(kind, 14)
              + pad(str(sum(before.values())), 8, right=True)
              + pad("→", 4, right=True)
              + pad(str(sum(after.values())), 8, right=True)
              + pad(f"-{sum(before.values()) - sum(after.values())}", 9, right=True)
              + pad(str(len(moved)), 8, right=True)
              + pad(str(len(zeroed)), 16, right=True))
    people_before = len({r["contact_id"] for r in rows})
    people_after = len({r["contact_id"] for r in rows if r["id"] not in dropped})
    print(f"   활동이 한 줄이라도 있는 사람: {people_before}명 → {people_after}명")
    if people_before != people_after:
        print("   ⚠ 활동이 **통째로 사라지는 사람**이 있다. 그럴 리 없는 일이다"
              " — 아래 ③을 보라.")
    print()


def print_safety(items, rows) -> None:
    """**확인해야 하는 것들.** 하나라도 어긋나면 돌리면 안 된다."""
    dropped = {it.row["id"] for it in items if it.drops}
    print("③ 안전 확인")

    # (1) 한 쌍에서 한쪽만 — 지운 뒤에도 그 기록이 누군가에게 남는가
    left = Counter((r["kind"], r["content"]) for r in rows
                   if r["id"] not in dropped)
    byid = {r["id"]: r for r in rows}
    gone = [i for i in dropped if not left[(byid[i]["kind"], byid[i]["content"])]]
    mark = "OK" if not gone else "⚠"
    print(f"   [{mark}] 지운 뒤 **세상에서 사라지는** 기록: {len(gone)}건")
    if gone:
        print("        " + ", ".join(str(i) for i in gone[:20]))
    print("        (한 쌍에서 한쪽만 지운다 — 남는 쪽의 id 를 줄마다 들고 있다)")

    # (2) 짝을 지우지는 않는가
    keepers = {it.keeper for it in items if it.drops and it.keeper}
    bad = keepers & dropped
    print(f"   [{'OK' if not bad else '⚠'}] 남기기로 한 줄을 지우지는 않는가: "
          f"겹침 {len(bad)}건")

    # (3) 어제 작업·손으로 적은 줄을 건드리지 않는가
    days = Counter((byid[i]["created_at"] or "")[:10] for i in dropped)
    srcs = Counter(byid[i]["source"] for i in dropped)
    batch = sum(1 for i in dropped if byid[i]["batch_key"])
    ok = set(days) <= {SHIFT_DAY} and set(srcs) <= {"import"} and not batch
    print(f"   [{'OK' if ok else '⚠'}] 지우는 줄이 **{SHIFT_DAY} 임포트 것뿐인가**: "
          f"날짜 {dict(days)} · source {dict(srcs)} · batch_key 있는 줄 {batch}")
    print(f"        ({FIX_DAY} 줄·손으로 적은 줄(`manual`)·묶음 줄은 한 줄도 "
          "안 건드린다)")

    # (4) 지운 뒤에도 남는 중복
    after = Counter((r["contact_id"], r["kind"], r["content"], r["month"])
                    for r in rows if r["id"] not in dropped)
    rest = [k for k, v in after.items() if v > 1]
    print(f"   [--] 지운 뒤에도 남는 `(사람, 갈래, 글, 달)` 중복: {len(rest)}묶음")
    print("        이 일의 몫이 아니다 — 09-10 임포트가 **한 판 안에서** 같은 칸을"
          " 두 번 읽은 것이라")
    print("        두 줄 다 같은 사람 것이다. 따로 볼 일이다.")
    print()


def print_self_check(items) -> int:
    """**사용자가 손으로 지운 9줄과 남긴 1줄로 자를 맞춘다.**

    그 열 줄은 사람이 한 줄씩 보고 판단한 것이라 이 스크립트의 **정답지**다.
    판정을 고쳤을 때 자가 어긋나면 여기서 걸린다.
    """
    tiers = {it.row["id"]: it.tier for it in items}
    print("④ 자 맞추기 — 사용자가 손으로 판단한 10줄")
    missing = [i for i in KNOWN_RESIDUE if i not in tiers]
    wrong = [i for i in KNOWN_RESIDUE if tiers.get(i) not in (None, RESIDUE)]
    if missing:
        print(f"   [--] 지운 9줄은 이미 DB 에 없다 ({len(missing)}줄) — "
              "맞출 것이 없다. 정상이다.")
    if wrong:
        print(f"   [⚠] 지운 9줄 중 `{RESIDUE}` 가 아닌 줄: {wrong}")
    keep = tiers.get(KNOWN_KEEP)
    if keep is None:
        print(f"   [⚠] 사용자가 남긴 act {KNOWN_KEEP} 이 후보에 없다 — "
              "자를 맞출 수가 없다.")
    elif keep == RESIDUE:
        print(f"   [⚠] 사용자가 **일부러 남긴** act {KNOWN_KEEP} 을 "
              f"`{RESIDUE}` 로 본다. 판정이 너무 세다.")
    else:
        print(f"   [OK] 사용자가 남긴 act {KNOWN_KEEP} → `{keep}` "
              "(두 사람 칸에 다 있는 글이라 안 지운다)")
    print()
    return len(wrong) + (1 if keep == RESIDUE else 0)


def print_rows(items, limit: int, show_values: bool) -> None:
    """지우는 줄을 편다. **값은 안 찍는다** — `--show-values` 일 때만.

    **갈래마다 따로 센 만큼 편다.** 한 덩어리로 자르면 큰 갈래가 자리를 다 먹어
    정작 눈으로 봐야 할 작은 갈래가 한 줄도 안 보인다.
    """
    drop = [it for it in items if it.drops]
    print(f"⑤ 지우는 줄 {len(drop)}개"
          + ("" if show_values else " — 글은 모양(길이)으로만 찍는다"
                                   " (`--show-values` 로 값을 본다)"))
    print("   " + pad("act", 7, right=True) + pad("사람", 8, right=True)
          + "  " + pad("갈래", 12) + pad("달", 10)
          + pad("→ 남는 줄", 11, right=True)
          + "  " + pad("근거", 44) + ("글" if show_values else "글 길이"))
    for kind in ("deal_intro", "ir_request", "meeting"):
        mine = [it for it in drop if it.row["kind"] == kind]
        for it in mine[:limit or None]:
            text = it.row["raw_text"] or it.row["content"]
            print("   " + pad(str(it.row["id"]), 7, right=True)
                  + pad(str(it.row["contact_id"]), 8, right=True)
                  + "  " + pad(kind, 12)
                  + pad(it.row["month"] or "(빈값)", 10)
                  + pad(str(it.keeper), 11, right=True)
                  + "  " + pad(it.why, 44)
                  + (text if show_values else f"{len(text)}자"))
        if limit and len(mine) > limit:
            print(f"   … `{kind}` {len(mine) - limit}줄 더 "
                  "(`--limit 0` 으로 전부 편다)")
    print()


def print_watch(items, limit: int, show_values: bool) -> None:
    """**눈으로 봐야 하는 줄** — `애매` 로 갈려 안 지우는 줄.

    사용자가 act 1948 에서 한 판단이 이것이다. 기업 목록이라 두 칸에 다 있는
    것이 정상일 수 있어서 남겼다. 그래서 이 칸은 **매기지 않고 세어서 보여
    준다** — 사람이 보고 정한다.
    """
    watch = [it for it in items if it.tier == AMBIGUOUS]
    print(f"⑥ 눈으로 볼 줄 {len(watch)}개 — 글자는 본인 칸에 없는데 "
          "**기업 이름이 겹쳐** 안 지우는 줄")
    if not watch:
        print("   없다.")
        print()
        return
    print("   " + pad("act", 7, right=True) + pad("사람", 8, right=True)
          + "  " + pad("갈래", 12) + pad("겹침", 8, right=True) + "  "
          + ("글" if show_values else "글 길이"))
    for it in sorted(watch, key=lambda x: -x.overlap)[:limit or None]:
        text = it.row["raw_text"] or it.row["content"]
        print("   " + pad(str(it.row["id"]), 7, right=True)
              + pad(str(it.row["contact_id"]), 8, right=True)
              + "  " + pad(it.row["kind"], 12)
              + pad(f"{it.overlap:.0%}", 8, right=True) + "  "
              + (text if show_values else f"{len(text)}자"))
    if limit and len(watch) > limit:
        print(f"   … {len(watch) - limit}줄 더 (`--limit 0` 으로 전부 편다)")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 쓰기 · 되돌리기
# ─────────────────────────────────────────────────────────────────────────────

def apply_plan(con: sqlite3.Connection, items) -> int:
    """계획대로 지운다. **`잔재확정` 만** 지운다."""
    ids = [it.row["id"] for it in items if it.drops]
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        con.execute(f"DELETE FROM {TABLE} WHERE id IN ({marks})", chunk)
    con.commit()
    return len(ids)


def save_baseline(path: Path, items) -> int:
    """되돌리기 파일. **지우는 줄을 칸 하나까지 통째로** 떠 둔다.

    값을 고치는 스크립트와 달리 여기서는 줄이 사라지므로, `before` 에 줄 전체가
    없으면 되살릴 수가 없다. `id` 도 그대로 떠서 **원래 번호로** 돌아간다.
    """
    data = [{"id": it.row["id"], "family": it.family, "why": it.why,
             "keeper": it.keeper, "before": it.row, "after": None}
            for it in items if it.drops]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return len(data)


def restore(con: sqlite3.Connection, path: Path) -> int:
    """떠 둔 줄을 **id 까지 그대로** 다시 넣는다 — 원상 복구.

    이미 있는 번호면 건너뛴다(두 번 돌려도 같은 자리에 선다).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    cols = ", ".join(COLUMNS)
    marks = ", ".join("?" * len(COLUMNS))
    count = 0
    for item in data:
        row = item["before"]
        con.execute(f"INSERT OR IGNORE INTO {TABLE} ({cols}) VALUES ({marks})",
                    [row[c] for c in COLUMNS])
        count += 1
    con.commit()
    return count


def check_baseline(con: sqlite3.Connection, path: Path) -> int:
    """**계획대로 지워졌는가.** 떠 둔 번호가 지금 DB 에 없어야 한다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [item["id"] for item in data]
    still = set()
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        still |= {r[0] for r in con.execute(
            f"SELECT id FROM {TABLE} WHERE id IN ({marks})", chunk)}
    print(f"⑦ 기준과 맞추기 — 떠 둔 {len(data)}줄")
    print(f"   계획대로 지워짐 {len(data) - len(still)}줄 · 아직 남음 {len(still)}줄")
    if still:
        print("   남아 있는 id: "
              + ", ".join(str(i) for i in sorted(still)[:20])
              + (" …" if len(still) > 20 else ""))
    print()
    return len(still)


def default_db() -> Path:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///"):])
    return Path(__file__).resolve().parent.parent / "data" / "dealflow.db"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="줄이 밀려 들어간 활동 이력의 잔재를 지운다 "
                    "(기본은 미리보기 — DB 에 안 쓴다)")
    ap.add_argument("--db", default="", help="SQLite 파일 (기본: DATABASE_URL)")
    # `--dry-run` 은 **기본값**이라 안 적어도 미리보기다. 그래도 받는다 —
    # 적어 두고 돌린 명령이 "안 적었으니 저장됐나" 로 읽히면 안 된다.
    ap.add_argument("--dry-run", action="store_true",
                    help="미리보기 (기본값 — `--apply` 없이는 늘 이쪽이다)")
    ap.add_argument("--apply", action="store_true",
                    help="실제로 DB 에서 지운다. `--save-baseline` 을 함께 줘야 한다")
    ap.add_argument("--save-baseline", default="",
                    help="지우는 줄을 **통째로** 이 파일로 떠 둔다")
    ap.add_argument("--baseline", default="",
                    help="떠 둔 파일과 지금 DB 를 맞춘다 (지운 뒤에 돌린다)")
    ap.add_argument("--restore", default="",
                    help="떠 둔 파일로 **원상 복구**한다 (`--apply` 와 함께)")
    ap.add_argument("--show-values", action="store_true",
                    help="글을 찍는다. 기본은 끔 — 투자사·기업 이야기가 들어 있다")
    ap.add_argument("--limit", type=int, default=15,
                    help="⑤·⑥에 갈래마다 몇 줄까지 펼까 (0 = 전부)")
    ap.add_argument("--self-check", action="store_true",
                    help="자 맞추기가 어긋나면 **종료코드 1** 로 물러난다")
    args = ap.parse_args()

    path = Path(args.db) if args.db else default_db()
    if not path.exists():
        print(f"그런 파일이 없다: {path}", file=sys.stderr)
        return 2

    if args.restore:
        if not args.apply:
            print("되돌리기도 DB 에 쓰는 일이다. `--apply` 를 함께 줘라.",
                  file=sys.stderr)
            return 2
        con = open_db(path, write=True)
        try:
            count = restore(con, Path(args.restore))
        finally:
            con.close()
        print(f"되돌렸다: {count}줄 ← {args.restore}")
        return 0

    if args.apply and not args.save_baseline:
        # 지우는 일이다. 되돌릴 파일 없이 지우게 두지 않는다.
        print("`--apply` 에는 `--save-baseline` 이 있어야 한다 "
              "(되돌릴 파일 없이 지우지 않는다).", file=sys.stderr)
        return 2

    con = open_db(path, write=args.apply)
    try:
        items, rows = plan(con)

        print(f"자료      : {path}" + ("" if args.apply else "  (읽기 전용)"))
        print("무엇을 하나: 줄이 한 칸 밀려 들어간 활동 이력의 잔재를 지운다")
        print(f"어디를     : **{SHIFT_DAY} 임포트가 만든 줄만** · "
              f"{FIX_DAY} 줄은 안 건드린다")
        print(f"덮는가     : 덮지 않는다 — **지운다.** `{RESIDUE}` 만, "
              f"`{AMBIGUOUS}`·`{NOT_RESIDUE}` 은 그대로 둔다")
        print("쓰는가     : " + ("**쓴다 (--apply)**" if args.apply
                                 else "아니다 — 미리보기"))
        print()

        if not items:
            print("후보가 없다. 이미 정리됐거나 날짜가 안 맞는다.")
            return 2

        print_tiers(items)
        print_counts(items, rows)
        print_safety(items, rows)
        bad = print_self_check(items)
        print_rows(items, args.limit, args.show_values)
        print_watch(items, args.limit, args.show_values)

        if args.save_baseline:
            saved = save_baseline(Path(args.save_baseline), items)
            print(f"되돌리기 파일을 떠 두었다: {args.save_baseline} ({saved}줄)")
            print("   ※ 줄이 통째로 들어 있다. 저장소 밖에 두어라.")
            print()

        if args.apply:
            count = apply_plan(con, items)
            print(f"DB 에서 지웠다: {count}줄")
            print(f"   되돌리려면: python {Path(__file__).name} "
                  f"--restore {args.save_baseline} --apply")
            print()

        if args.baseline:
            return 1 if check_baseline(con, Path(args.baseline)) else 0
        return 1 if (args.self_check and bad) else 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
