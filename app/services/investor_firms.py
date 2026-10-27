"""투자사 **회사 단위** 값 — `챗GPT 조사 소유펀드`(개선 과제 #1) · `펀드 종류` · `소분류`.

화면 이름은 `FIELDS` 한 곳에 있다. `소유 펀드` 는 옛 화면 이름이다 — 저장 칸
(`owned_funds`)은 그대로이고, 옛 머리글로 만든 표도 그대로 받는다(`OLD_HEADS`).

투자사 관리 현황은 사람 줄이라 같은 회사가 여러 줄에 선다. 회사가 가진 펀드는
사람마다 다를 수 없으므로 값은 회사 하나에 한 번만 적고(`InvestorFirm`), 사람 줄은
자기 `firm` 글자에서 열쇠를 지어 그 값을 **보여 준다.** 한 줄에서 고치면 같은
회사의 모든 줄에 같은 값이 선다.

## 회사를 무엇으로 가르나 — `firm_key`

`(주)` · `주식회사` · 띄어쓰기 · 대소문자를 지운 꼴이다. 딜 기업을 맞추는 규칙
(`deal_history._key` · `room_match.key`)과 **같은 규칙**을 쓴다 — 저장소 안에서
"같은 회사인가" 를 두 가지 자로 재면 한쪽만 고쳐지는 날이 온다.

## 엑셀로 한꺼번에 넣기

외부 조사 결과를 `투자사명` + 값 칸(`FIELDS` 의 머리글 — 있는 것만) 표로 받아
넣는다(`parse_upload` → `match` → `apply_upload`). 이름은 위 열쇠로 투자사 관리
현황의 회사에 맞추고, **못 맞춘 이름은 넣지 않고 보여만 준다** — 명단에 없는
회사의 값은 아무 줄에도 안 보여서, 넣어도 확인할 길이 없다. 빈 칸은 **그 칸만**
건너뛴다(지우는 것은 화면에서 한다 — 빈 칸이 '지워라' 인지 '모른다' 인지 표만
보고는 알 수 없다). `소분류` 가 목록 밖이거나 5개를 넘는 줄, `펀드 종류` 가 정해 둔
말(`FUND_TYPES`) 밖인 줄은 통째로 안 넣고 까닭을 보여 준다(`errors`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InvestorFirm, VcContact
from . import taxonomy
from .sheet_import import normalize_company_name

#: 회사 단위 칸 → 화면 · 엑셀 머리글. 업로드도 이 글자로 칸을 찾는다.
FIELDS = {"owned_funds": "챗GPT 조사 소유펀드", "fund_types": "펀드 종류",
          "sub_sectors": "소분류"}
#: 이름을 바꾼 머리글(옛 이름 → 칸) — 옛 양식으로 채운 표도 받는다.
OLD_HEADS = {"소유 펀드": "owned_funds"}
HEAD_FIRM = "투자사명"
HEADERS = (HEAD_FIRM, *FIELDS.values())
#: `소분류` 는 몇 개까지 적나.
MAX_SUB_SECTORS = 5
#: `펀드 종류` 로 적을 수 있는 말 — 정해 둔 13가지(사용자 결정 2026-10-27). 화면의
#: 고르는 칸도 이 차례로 선다. 관리 화면 없이 여기서만 고친다.
FUND_TYPES = (
    "모태 창업초기·청년", "모태 문화·콘텐츠", "모태 소부장·딥테크",
    "모태 미래환경·에너지", "모태 스케일업·세컨더리·M&A", "지역 펀드",
    "농식품·해양수산", "산업은행·성장금융 정책펀드", "대기업·CVC 협업",
    "민간 LP 블라인드", "신기사조합", "PEF", "개인투자조합",
)


def firm_key(name: Optional[str]) -> str:
    """비교용 회사명 — `(주)`·띄어쓰기·대소문자를 지운 꼴."""
    return normalize_company_name(name or "").replace(" ", "").lower()


def split_funds(text: Optional[str]) -> List[str]:
    """쉼표 글 → 이름들. 투자사 관리 현황의 회사 단위 칸 필터(`챗GPT 조사 소유펀드` 등)가 세는 값이다.

    쉼표·줄바꿈으로 나누고 앞뒤 공백을 걷고 겹친 공백을 하나로 줄인다. 이름을
    고치거나 묶지 않는다 — 적힌 글자 그대로가 갈래다. 같은 이름이 두 번이면 한 번.
    """
    parts = (" ".join(p.split()) for p in re.split(r"[,\n]", text or ""))
    return list(dict.fromkeys(p for p in parts if p))


def funds_map(db: Session, field: str = "owned_funds") -> Dict[str, str]:
    """열쇠 → 그 칸(`FIELDS`)의 값. 표 한 장에 질의 하나(줄마다 묻지 않는다)."""
    return {row.firm_key: getattr(row, field)
            for row in db.execute(select(InvestorFirm)).scalars()
            if getattr(row, field)}


def funds_of(db: Session, firm: Optional[str], field: str = "owned_funds") -> str:
    key = firm_key(firm)
    if not key:
        return ""
    row = db.execute(select(InvestorFirm).where(InvestorFirm.firm_key == key)
                     ).scalar_one_or_none()
    return (getattr(row, field) or "") if row else ""


def sub_sector_names(db: Session) -> Dict[str, str]:
    """분야 기준 목록의 **보이는 소분류** — 견주는 꼴(`taxonomy.norm`) → 목록의 글자.

    선호 투자분야를 고르는 목록(`taxonomy.tree`)과 같은 줄들이다 — 숨긴 · 합친 줄은 없다.
    """
    r = taxonomy.Resolver.load(db)
    return {taxonomy.norm(m.name): m.name
            for major in r.visible_majors() for m in r.visible_minors(major.id)}


def _canonical(text: Optional[str], known: Dict[str, str]) -> tuple:
    """쉼표 글 → (목록 글자로 맞춘 이름들 — 겹침 뺌, 목록에 없는 말들).

    띄어쓰기 · 가운뎃점 · 대소문자는 안 본다(`taxonomy.norm`) — `모태 창업초기 청년` 도
    `모태 창업초기·청년` 으로 적힌다.
    """
    tokens = split_funds(text)
    bad = [t for t in tokens if taxonomy.norm(t) not in known]
    names = [known[taxonomy.norm(t)] for t in tokens if t not in bad]
    return list(dict.fromkeys(names)), bad


def clean_fund_types(text: Optional[str]) -> str:
    """`펀드 종류` 글 → `FUND_TYPES` 글자로 맞춘 값. 목록 밖 말은 ValueError(화면에 그대로)."""
    names, bad = _canonical(text, {taxonomy.norm(n): n for n in FUND_TYPES})
    if bad:
        raise ValueError(f"펀드 종류는 정해 둔 {len(FUND_TYPES)}가지 중에서만 적을 수 있습니다 "
                         "— 목록에 없는 말: " + ", ".join(bad)
                         + " (적을 수 있는 말: " + ", ".join(FUND_TYPES) + ")")
    return ", ".join(names)


def clean_sub_sectors(text: Optional[str], known: Dict[str, str]) -> str:
    """`소분류` 글 → 목록의 글자로 맞춘 값. 목록 밖 말 · 5개 넘음은 ValueError(화면에 그대로)."""
    names, bad = _canonical(text, known)
    if bad:
        raise ValueError("소분류는 분야 기준 목록(IR 기업 현황 소분류)에 있는 말만 적을 수 "
                         "있습니다 — 목록에 없는 말: " + ", ".join(bad))
    if len(names) > MAX_SUB_SECTORS:
        raise ValueError(f"소분류는 {MAX_SUB_SECTORS}개까지 적을 수 있습니다 "
                         f"— {len(names)}개를 적었습니다")
    return ", ".join(names)


def set_funds(db: Session, firm: Optional[str], value: Optional[str],
              user_id: Optional[int], field: str = "owned_funds") -> Optional[InvestorFirm]:
    """이 회사의 그 칸(`FIELDS`) 값을 적는다. 회사명이 비면 적을 자리가 없어 None.

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
    if (getattr(row, field) or "") == text:
        return row
    setattr(row, field, text or None)
    row.updated_by = user_id
    # autoflush 가 꺼져 있다 — 같은 판에서 이 회사의 다른 칸을 적을 때 새 줄을 다시
    # 찾아야 한다(못 찾으면 줄을 또 만들어 `firm_key` 겹침으로 터진다).
    db.flush()
    return row


# ── 엑셀 올리기 ─────────────────────────────────────────────────────────────

class UploadError(Exception):
    """올린 표를 읽을 수 없다. 화면에 그대로 띄운다(400)."""


@dataclass
class UploadRow:
    line: int
    name: str
    #: 칸(`FIELDS` 의 열쇠) → 적힌 글. 표에 있는 머리글의 칸만 — 빈 글은 '안 바꿈'.
    values: Dict[str, str]


def parse_upload(rows: Sequence[Sequence]) -> List[UploadRow]:
    """표 → (줄 번호, 투자사명, 칸별 값). 머리글 줄은 이름으로 찾는다(차례 무관)."""
    def cell(row, i):
        return str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else ""

    def flat(text) -> str:
        return str(text or "").replace(" ", "").strip()

    heads = {flat(label): field for field, label in FIELDS.items()}
    heads.update({flat(old): field for old, field in OLD_HEADS.items()})
    head_at, firm_at, cols = None, None, {}
    for i, row in enumerate(rows[:20]):
        labels = [flat(c) for c in row]
        if flat(HEAD_FIRM) in labels and any(label in heads for label in labels):
            head_at, firm_at = i, labels.index(flat(HEAD_FIRM))
            for j, label in enumerate(labels):
                if label in heads:
                    cols.setdefault(heads[label], j)
            break
    if head_at is None:
        raise UploadError(f"머리글 `{HEAD_FIRM}` 과 `" + "` · `".join(FIELDS.values())
                          + "` 중 하나 이상이 있는 줄을 못 찾았습니다 "
                          "— 양식을 내려받아 그 머리글 그대로 채워 주세요")
    out = []
    for i, row in enumerate(rows[head_at + 1:], start=head_at + 2):
        name = cell(row, firm_at)
        if not name:
            continue
        out.append(UploadRow(line=i, name=name,
                             values={field: cell(row, j) for field, j in cols.items()}))
    return out


@dataclass
class Match:
    matched: List[dict] = field(default_factory=list)
    unmatched: List[dict] = field(default_factory=list)
    blank: List[dict] = field(default_factory=list)
    duplicates: List[dict] = field(default_factory=list)
    #: 맞췄지만 값을 못 쓰는 줄(`소분류` · `펀드 종류` 목록 밖 · 소분류 5개 넘음) — 그 줄은 통째로 안 넣는다.
    errors: List[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        changes = [m for m in self.matched if m["changes"]]
        return {"matched": self.matched, "unmatched": self.unmatched,
                "blank": self.blank, "duplicates": self.duplicates,
                "errors": self.errors, "labels": FIELDS,
                "counts": {"matched": len(self.matched), "changes": len(changes),
                           "unchanged": len(self.matched) - len(changes),
                           "unmatched": len(self.unmatched),
                           "blank": len(self.blank),
                           "duplicates": len(self.duplicates),
                           "errors": len(self.errors)}}


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
    current = {f: funds_map(db, f) for f in FIELDS}
    known = sub_sector_names(db)
    out = Match()
    seen: Dict[str, dict] = {}
    for row in rows:
        key = firm_key(row.name)
        if key not in firms:
            out.unmatched.append({"line": row.line, "name": row.name})
            continue
        after = {f: v for f, v in row.values.items() if v}
        if not after:
            out.blank.append({"line": row.line, "name": row.name})
            continue
        try:
            if "sub_sectors" in after:
                after["sub_sectors"] = clean_sub_sectors(after["sub_sectors"], known)
            if "fund_types" in after:
                after["fund_types"] = clean_fund_types(after["fund_types"])
        except ValueError as exc:
            out.errors.append({"line": row.line, "name": row.name, "reason": str(exc)})
            continue
        before = {f: current[f].get(key, "") for f in after}
        entry = {"line": row.line, "name": row.name, "key": key,
                 "firm": firms[key]["name"], "rows": firms[key]["rows"],
                 "before": before, "after": after, "changes": before != after}
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
        for f, value in entry["after"].items():
            set_funds(db, names[entry["key"]]["name"], value, user_id, f)
        changed += 1
    db.commit()
    return {"changed": changed, **plan.as_dict()["counts"]}
