"""`Series A 이상 딜 소싱` 탭의 [딜소개 문구 올리기] — 파일로 `딜소개 문구` 칸만 채운다.

사용자 결정(2026-10-16): **관리자가** 시트 파일(.xlsx · .csv)을 올려
`SeriesACompany.deal_pitch` 를 채운다. 다른 사람에게는 단추도 없고 길도 막힌다
(`routers/series_a.can_upload_pitch`).

## 줄은 가져오기와 **같은 함수**로 맞춘다

`series_a_import.match` 하나를 지난다 — 가져오기 열쇠 `(기업명, 수신 일자, 공유
심사역, 회사)` → 열쇠 없는 줄의 지금 값 열쇠 → `(기업명, 수신 일자)`(양쪽 다
하나일 때만, 아니면 `애매해서 건너뜀`). 여기서 따로 맞추면 같은 파일이 스크립트
가져오기와 이 화면에서 다른 줄에 닿는다. 칸을 채울지 · 덮을지 · 둘지도 가져오기의
`cell_plan` 그대로다.

## 바꾸는 것은 `딜소개 문구` **한 칸뿐이다**

  · **줄을 만들지 않는다.** 표에 없는 딜(`못 맞춘 줄`)은 수와 목록만 알린다 —
    줄을 더하는 길은 시트 가져오기(`scripts/import_series_a.py`)와 [기업 추가]다.
  · **`import_key` 도 적지 않는다.** 가져오기는 열쇠 없는 줄을 맞추면 그 줄에 열쇠를
    적지만(`linked`), 이 길은 딜소개 문구 말고는 아무 칸도 안 바꾸기로 했다. 열쇠는
    다음 가져오기가 적는다 — 같은 `match` 로 맞추므로 같은 줄에 적힌다.
  · 기본은 **빈 칸만 채운다.** [이미 적힌 문구도 덮어쓰기]를 켰을 때만 다른 글을
    덮는다(`overwrite`). 파일의 빈 칸은 아무것도 안 지우고, 같은 글은 그대로 둔다.

## 미리보기 → 반영

같은 파일을 두 번 보낸다 — `dry_run` 으로 무엇이 바뀌는지 보고, 그 다음 반영한다
(`routers/data_io.import_contacts` 와 같은 짜임). 반영도 **파일에서 처음부터 다시
센다**(`plan`) — 서버에 미리보기를 쌓아 두지 않는다. 그 사이 누가 표를 고쳤으면
반영의 답이 미리보기와 다를 수 있고, 답은 **실제로 바꾼 것**을 말한다.

쓰기는 요청 안에서 ORM 으로 한다(`apply`) — 수정 로그(`services/edit_log.py`)가 줄마다
누가 바꿨는지 남긴다(`series_a_companies` 는 공용 표로 지켜본다).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

from sqlalchemy.orm import Session

from ..models import SeriesACompany
from . import series_a_import as sai

#: 이 길이 바꾸는 칸. 이 밖의 칸은 읽기만 한다(줄을 알아보는 데).
FIELD = "deal_pitch"

#: 줄을 알아보는 칸 — 미리보기 목록에 싣는 차례(기업명 · 수신 일자 · 공유 심사역 · 회사).
IDENT = ("name", "received_at", "shared_by", "source_firm")


@dataclass
class Change:
    """바꿀 줄 하나 — 지금 문구 → 새 문구."""

    row: SeriesACompany
    before: str
    after: str
    #: `sai.FILL`(빈 칸 채움) 또는 `sai.OVERWRITE`(덮어씀).
    how: str


@dataclass
class Plan:
    overwrite: bool = False
    #: 파일에서 읽은 줄(기업명이 있는 줄).
    records: int = 0
    #: 표의 줄에 맞은 파일 줄.
    matched: int = 0
    #: 표에 없는 딜 — 넣을 값 그대로(줄을 만들지 않는다).
    unmatched: List[dict] = field(default_factory=list)
    #: 열쇠 없는 줄 중 어느 것인지 몰라 건너뛴 파일 줄(`sai.match` 의 3).
    ambiguous: List[dict] = field(default_factory=list)
    #: 파일 안에서 열쇠가 겹쳐 건너뛴 줄(앞 줄만 쓴다).
    duplicates: int = 0
    changes: List[Change] = field(default_factory=list)
    #: 맞았지만 그대로인 줄 — 같은 글 · 이미 다른 글이 있어 안 덮음 · 파일 칸이 빔.
    same: int = 0
    kept: int = 0
    blank: int = 0

    @property
    def filled(self) -> int:
        return sum(1 for c in self.changes if c.how == sai.FILL)

    @property
    def overwritten(self) -> int:
        return sum(1 for c in self.changes if c.how == sai.OVERWRITE)


def plan(db: Session, records: Iterable[dict], overwrite: bool = False) -> Plan:
    """파일 줄들(`sai.parse` 의 `records`) → 무엇을 바꿀지. **아무것도 고치지 않는다.**"""
    records = list(records)
    found = sai.match(sai.table(db), records)
    out = Plan(overwrite=overwrite, records=len(records),
               duplicates=len(found.duplicates), ambiguous=list(found.ambiguous))
    # 넷째 값(`linked` — 가져오기라면 열쇠를 적을 줄)은 쓰지 않는다. 이 길은
    # `import_key` 를 적지 않는다(머리말).
    for values, _key, row, _linked in found.pairs:
        if row is None:
            out.unmatched.append(values)
            continue
        out.matched += 1
        value = values.get(FIELD, "")
        how = sai.cell_plan(row.deal_pitch, value, overwrite)
        if how in (sai.FILL, sai.OVERWRITE):
            out.changes.append(Change(row=row, before=(row.deal_pitch or "").strip(),
                                      after=value, how=how))
        elif how == sai.SAME:
            out.same += 1
        elif how == sai.KEEP:
            out.kept += 1
        else:
            out.blank += 1
    return out


def apply(p: Plan) -> int:
    """`plan` 대로 `딜소개 문구` 만 적는다. **커밋하지 않는다** — 부르는 쪽이 정한다."""
    for change in p.changes:
        change.row.deal_pitch = change.after
    return len(p.changes)


def ident(src) -> dict:
    """줄을 알아보는 네 칸 — 넣을 값(dict)이든 표의 줄이든."""
    get = src.get if isinstance(src, dict) else (lambda attr: getattr(src, attr, None))
    return {attr: get(attr) or "" for attr in IDENT}
