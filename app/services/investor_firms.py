"""투자사 **회사 단위** 값 — `소유 펀드`(개선 과제 #1).

투자사 관리 현황은 사람 줄이라 같은 회사가 여러 줄에 선다. 회사가 가진 펀드는
사람마다 다를 수 없으므로 값은 회사 하나에 한 번만 적고(`InvestorFirm`), 사람 줄은
자기 `firm` 글자에서 열쇠를 지어 그 값을 **보여 준다.** 한 줄에서 고치면 같은
회사의 모든 줄에 같은 값이 선다.

## 회사를 무엇으로 가르나 — `firm_key`

`(주)` · `주식회사` · 띄어쓰기 · 대소문자를 지운 꼴이다. 딜 기업을 맞추는 규칙
(`deal_history._key` · `room_match.key`)과 **같은 규칙**을 쓴다 — 저장소 안에서
"같은 회사인가" 를 두 가지 자로 재면 한쪽만 고쳐지는 날이 온다.

## 엑셀로 한꺼번에 넣기

외부 조사 결과(회사별 소유 펀드)를 `투자사명` · `소유 펀드` 두 칸짜리 표로 받아
넣는다(`parse_upload` → `match` → `apply_upload`). 이름은 위 열쇠로 투자사 관리
현황의 회사에 맞추고, **못 맞춘 이름은 넣지 않고 보여만 준다** — 명단에 없는
회사의 값은 아무 줄에도 안 보여서, 넣어도 확인할 길이 없다. 빈 칸은 건너뛴다
(지우는 것은 화면에서 한다 — 빈 칸이 '지워라' 인지 '모른다' 인지 표만 보고는
알 수 없다).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InvestorFirm, VcContact
from .sheet_import import normalize_company_name

#: 업로드 양식의 머리글. 이 글자로 칸을 찾는다.
HEAD_FIRM = "투자사명"
HEAD_FUNDS = "소유 펀드"
HEADERS = (HEAD_FIRM, HEAD_FUNDS)


def firm_key(name: Optional[str]) -> str:
    """비교용 회사명 — `(주)`·띄어쓰기·대소문자를 지운 꼴."""
    return normalize_company_name(name or "").replace(" ", "").lower()


def funds_map(db: Session) -> Dict[str, str]:
    """열쇠 → 소유 펀드. 표 한 장에 질의 하나(줄마다 묻지 않는다)."""
    return {row.firm_key: row.owned_funds or ""
            for row in db.execute(select(InvestorFirm)).scalars()
            if row.owned_funds}


def funds_of(db: Session, firm: Optional[str]) -> str:
    key = firm_key(firm)
    if not key:
        return ""
    row = db.execute(select(InvestorFirm).where(InvestorFirm.firm_key == key)
                     ).scalar_one_or_none()
    return (row.owned_funds or "") if row else ""


def set_funds(db: Session, firm: Optional[str], value: Optional[str],
              user_id: Optional[int]) -> Optional[InvestorFirm]:
    """이 회사의 소유 펀드를 적는다. 회사명이 비면 적을 자리가 없어 None.

    값이 같으면 아무것도 안 바꾼다(수정 로그에 빈 고침이 쌓이지 않게).
    커밋은 부르는 쪽.
    """
    key = firm_key(firm)
    if not key:
        return None
    text = (value or "").strip()
    row = db.execute(select(InvestorFirm).where(InvestorFirm.firm_key == key)
                     ).scalar_one_or_none()
    if row is None:
        if not text:
            return None
        row = InvestorFirm(firm_key=key, display_name=(firm or "").strip())
        db.add(row)
    if (row.owned_funds or "") == text:
        return row
    row.owned_funds = text or None
    row.updated_by = user_id
    return row


# ── 엑셀 올리기 ─────────────────────────────────────────────────────────────

class UploadError(Exception):
    """올린 표를 읽을 수 없다. 화면에 그대로 띄운다(400)."""


@dataclass
class UploadRow:
    line: int
    name: str
    funds: str


def parse_upload(rows: Sequence[Sequence]) -> List[UploadRow]:
    """표 → (줄 번호, 투자사명, 소유 펀드). 머리글 줄은 이름으로 찾는다(차례 무관)."""
    def cell(row, i):
        return str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else ""

    head_at, cols = None, {}
    for i, row in enumerate(rows[:20]):
        labels = [str(c or "").replace(" ", "").strip() for c in row]
        if HEAD_FIRM.replace(" ", "") in labels and HEAD_FUNDS.replace(" ", "") in labels:
            head_at = i
            cols = {"firm": labels.index(HEAD_FIRM.replace(" ", "")),
                    "funds": labels.index(HEAD_FUNDS.replace(" ", ""))}
            break
    if head_at is None:
        raise UploadError(f"머리글 `{HEAD_FIRM}` · `{HEAD_FUNDS}` 이 있는 줄을 못 찾았습니다 "
                          "— 양식을 내려받아 그 머리글 그대로 채워 주세요")
    out = []
    for i, row in enumerate(rows[head_at + 1:], start=head_at + 2):
        name = cell(row, cols["firm"])
        if not name:
            continue
        out.append(UploadRow(line=i, name=name, funds=cell(row, cols["funds"])))
    return out


@dataclass
class Match:
    matched: List[dict] = field(default_factory=list)
    unmatched: List[dict] = field(default_factory=list)
    blank: List[dict] = field(default_factory=list)
    duplicates: List[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        changes = [m for m in self.matched if m["changes"]]
        return {"matched": self.matched, "unmatched": self.unmatched,
                "blank": self.blank, "duplicates": self.duplicates,
                "counts": {"matched": len(self.matched), "changes": len(changes),
                           "unchanged": len(self.matched) - len(changes),
                           "unmatched": len(self.unmatched),
                           "blank": len(self.blank),
                           "duplicates": len(self.duplicates)}}


def _firms(db: Session) -> Dict[str, dict]:
    """투자사 관리 현황의 회사들 — 열쇠 → {이름, 줄 수}. 회사 단위 표만 있는 회사도 넣는다.

    **스타트업 화면에만 사는 줄은 뺀다** — 그 명단의 `firm` 은 투자사가 아니라
    기업 이름이다(`contact_columns.STARTUP_LAYOUT`). 어느 명단이 어느 화면에
    사는지는 화면이 탭을 가르는 그 판정을 그대로 읽는다(`sheet_owner.page_labels`).
    """
    from . import contact_columns, sheet_owner   # noqa: PLC0415

    startup = sheet_owner.page_labels(db, contact_columns.PAGE_STARTUP)
    out: Dict[str, dict] = {}
    for contact in db.execute(select(VcContact).where(VcContact.firm.is_not(None))).scalars():
        labels = sheet_owner.labels_of(contact.source_sheet)
        if labels and all(label in startup for label in labels):
            continue
        key = firm_key(contact.firm)
        if not key:
            continue
        entry = out.setdefault(key, {"name": contact.firm.strip(), "rows": 0})
        entry["rows"] += 1
    for row in db.execute(select(InvestorFirm)).scalars():
        out.setdefault(row.firm_key, {"name": row.display_name or row.firm_key, "rows": 0})
    return out


def match(db: Session, rows: Iterable[UploadRow]) -> Match:
    """올린 줄을 회사에 맞춘다. **아무것도 쓰지 않는다.**

    같은 회사가 두 번 나오면 **아래 줄**을 쓴다(위에서 아래로 덮는 표의 습관 그대로)
    — 그 사실은 `duplicates` 로 따로 보여 준다.
    """
    firms = _firms(db)
    current = funds_map(db)
    out = Match()
    seen: Dict[str, dict] = {}
    for row in rows:
        key = firm_key(row.name)
        if key not in firms:
            out.unmatched.append({"line": row.line, "name": row.name})
            continue
        if not row.funds:
            out.blank.append({"line": row.line, "name": row.name})
            continue
        entry = {"line": row.line, "name": row.name, "key": key,
                 "firm": firms[key]["name"], "rows": firms[key]["rows"],
                 "before": current.get(key, ""), "after": row.funds,
                 "changes": current.get(key, "") != row.funds}
        if key in seen:
            out.duplicates.append({"line": seen[key]["line"], "name": seen[key]["name"],
                                   "kept_line": row.line})
            out.matched.remove(seen[key])
        seen[key] = entry
        out.matched.append(entry)
    return out


def apply_upload(db: Session, rows: Iterable[UploadRow], user_id: Optional[int]) -> dict:
    """맞춘 회사의 값을 **바꾼다**(회사마다 통째로). 커밋은 여기서 한 번."""
    plan = match(db, rows)
    names = _firms(db)
    changed = 0
    for entry in plan.matched:
        if not entry["changes"]:
            continue
        set_funds(db, names[entry["key"]]["name"], entry["after"], user_id)
        changed += 1
    db.commit()
    return {"changed": changed, **plan.as_dict()["counts"]}
