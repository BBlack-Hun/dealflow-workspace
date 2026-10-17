"""투자사 `선호 투자분야` 를 **분야 기준 목록의 말**로 다시 매긴다(개선 과제 #30).

## 왜

이 칸에 들어 있는 것이 분야만이 아니다. 운영 값을 보면 그룹 표시(`B` · `b그룹`),
카톡방 기록(`방 나가셨음`), 날짜(`딥테크 6/16`), 단계 말(`Seed Pre A` · `Pre IPO`),
긴 통화 메모가 함께 산다. 그래서 딜 맞추기(`matcher`)는 `B` 를 분야로 읽고, 화면의
분야 필터는 줄 수만큼 갈래가 생긴다.

사용자가 정했다(2026-10-17) —

  · 분야는 기준 목록의 말로 바꾼다(`로봇, AI, 소부장` → `로봇, AI·SaaS·데이터,
    딥테크·제조`).
  · 메모 · 그룹 표시 · 날짜 · 단계 말은 **메모로 옮긴다**(기존 메모 뒤에
    `[선호분야 칸에서 옮김] …`). 원래 글은 백업 칸(`sectors_raw`)에 남는다.
  · 빈 칸은 건드리지 않는다. 라운드 사이즈도 건드리지 않는다(③ 대기).

## 어떻게 읽나 — 줄(행) 단위

글을 줄바꿈으로 나눠 **줄마다** 본다. 한 줄 안은 쉼표 · 빗금 · 괄호 · 가운뎃점으로
조각을 내되, 날짜(`6/17`)는 쪼개지 않는다.

    조각에 목록의 말만 있다(`로봇` · `화장품 뷰티 기업`)      → 분야로
    목록의 말 + 다른 말(`6/17 반도체`, `M&A 건은 소비재`)    → 분야로 + 그 줄을 메모로
    목록의 말이 없고 메모로 보인다(날짜·단계·그룹·문장)     → 그 줄을 메모로
    목록의 말도 아니고 메모로도 안 보인다(`스포츠`)         → **못 맞춘 조각**

**메모로는 조각이 아니라 그 줄을 통째로 옮긴다.** `로봇, AI, 소부장 7/7` 에서
`7/7` 만 떼어 옮기면 무슨 날짜인지 알 수 없다 — 줄째로 옮겨야 "7/7 에 들은 선호"
라는 맥락이 남는다. 분야 말은 따로 뽑아 칸에 다시 적는다.

**뒤집는 말이 있는 줄은 분야를 뽑지 않는다**(`바이오 제외` · `AI 솔루션은 투자하지
않음`). 그대로 뽑으면 안 보겠다고 적어 둔 분야를 선호로 적게 된다 — 비어 있는
것보다 나쁘다(`invest_stage` 머리말의 같은 판단). 그 줄은 통째로 메모로 간다.

**못 맞춘 조각은 칸에 남긴다.** 지우면 글이 사라지고, 메모로 보내면 `메모로
옮길 글` 과 섞여 보이지 않는다. 남겨 두면 미리보기에 따로 뜨고, 관리자가 목록에
소분류를 더하거나 손으로 고친 뒤 다시 돌리면 그때 맞는다.

## 다시 돌려도 같다

반영한 줄은 기준 목록의 말뿐이라 다음 미리보기에 안 뜬다. 백업은 처음 한 번만
적는다(`taxonomy.backup_once`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, VcContact
from . import group_name, invest_stage, sector_words
from . import taxonomy as tx

#: 메모에 붙일 때 앞에 세우는 표시. `group_name.MOVED_MARK`(`[그룹 칸에서 옮김]`)와
#: 같은 결로 짓되 **어느 칸에서 왔는지**를 적는다 — 둘이 섞이면 되돌아볼 때 어느
#: 칸 글인지 가를 수 없다. `pref_group.moved_text` 가 이 표시도 함께 읽는다.
MOVED_MARK = "[선호분야 칸에서 옮김]"

#: 조각을 가르는 글자. **날짜는 미리 감춘 뒤에** 가른다(`_DATE`).
_SPLIT = re.compile(r"[,/|;()\[\]{}·ㆍ∙•、]|\.\s+|\.$")

#: 날짜 꼴 — `6/17` · `7.1` · `2026-06-17` · `6월 17일` · `6/5일` · `0902`.
_DATE = re.compile(
    r"(?:\d{4}\s*[-./]\s*)?(?<!\d)\d{1,2}\s*[/.]\s*\d{1,2}(?!\d)\s*일?"
    r"|\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?(?:\s*\d\s*주차)?"
    r"|(?<!\d)0\d{3}(?!\d)")

#: 단계 말. `invest_stage.stages_of` 가 `Series C 이상` · `Pre IPO` 를 읽고, 여기서는
#: 방향만 분명한 말(`초기` · `후기`)까지 더 본다 — 칸을 고르는 것이 아니라 **메모로
#: 보낼지만** 가르므로 넓게 잡아도 된다.
_STAGE = re.compile(
    r"초기|후기|중기|극초기|창업\s*초기|성장\s*단계|그로스|growth|레이터|late|early|"
    r"얼리|시드|엔젤|시리즈|series|seed|pre\s*-?\s*a|pre\s*-?\s*ipo|ipo|상장|프리",
    re.IGNORECASE)

#: 금액 · 규모 — 라운드 사이즈 칸의 말이다(그 칸은 건드리지 않고, 섞여 든 것은 메모로).
_AMOUNT = re.compile(r"\d[\d,.]*\s*(?:억|만|천|원|%|배)|value|밸류|티켓|규모",
                     re.IGNORECASE)

#: 메모로 보이는 말 — 카톡방 · 연락 기록, 사람 · 직함, 딜 종류, 조건 문장.
_NOTE = re.compile(
    r"방|나가|나감|보류|전화|부재|문자|카톡|연락|요청|검토|진행|거절|거부|완료|예정|"
    r"확인|회신|답변|소개|하심|하셨|셨|드림|님|대표|부장|팀장|이사|심사역|담당|관리|"
    r"개설|펀드|딜|deal|m&a|pef?|메자닌|바이아웃|buy\s*-?\s*out|세컨더리|구주|크레딧|"
    r"매출|이익|흑자|지분|투자|선호|위주|가능|필요|개인|사정|회사|하우스|비상장|"
    r"지역|소재지|이전|입주|졸업|팁스|tips|기금|등급|선정|대상|"
    # '분야를 가리지 않는다' — 선호가 없다는 말이라 분야로 읽을 것이 없다.
    r"가리지|가림|무관|상관\s*없|구분\s*없",
    re.IGNORECASE)

#: 뒤집는 말 — 이 말이 든 줄은 분야를 뽑지 않는다(머리말).
_NEGATION = re.compile(r"제외|빼고|않|안\s*함|안\s*봄|안\s*받|어려|불가|적음|아님|"
                       r"지양|싫|꺼림|별로|관심\s*없|투자\s*안")

#: 분야 말 옆에 붙어도 **뜻을 더하지 않는 말**. 이것만 남으면 그 조각은 분야뿐이다.
FILLER = frozenset({
    "분야", "분야쪽", "관련", "관련된", "기업", "기업들", "회사", "위주", "위주로",
    "중심", "중심으로", "등", "등등", "쪽", "산업", "스타트업", "벤처", "벤처기업",
    "전문", "기술", "선호", "및", "전반", "솔루션", "플랫폼", "서비스", "업종",
    "섹터", "그리고", "또는", "or", "and", "&", "기반", "포함", "메인", "주력",
    "미래", "차세대", "b2b", "b2c", "분야는", "분야를", "업", "테크", "tech",
})

#: 이만큼 넘게 긴 조각은 목록의 말이 없으면 문장으로 본다(메모로).
SENTENCE_LEN = 8

# 조각의 갈래
PART_SECTOR = "sector"     # 목록의 말뿐
PART_MIXED = "mixed"       # 목록의 말 + 다른 말
PART_NOTE = "note"         # 목록의 말 없이 메모로 보임
PART_UNKNOWN = "unknown"   # 목록의 말도 메모도 아님 — 못 맞춘 조각


@dataclass
class Part:
    text: str
    kind: str
    tokens: List[str] = field(default_factory=list)


@dataclass
class LineResult:
    text: str
    tokens: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    to_memo: bool = False
    negated: bool = False


@dataclass
class Result:
    """한 사람의 선호분야를 어떻게 바꿀지."""

    before: str
    after: str
    moved: List[str] = field(default_factory=list)
    unmatched: List[str] = field(default_factory=list)
    tokens: List[str] = field(default_factory=list)

    @property
    def changes(self) -> bool:
        return self.after != self.before.strip() or bool(self.moved)


def _protect_dates(text: str) -> Tuple[str, bool]:
    """날짜를 한 글자 자리표시로 바꾼다 — 가르는 글자(`/` `.`)가 날짜를 쪼개지 않게."""
    found = bool(_DATE.search(text))
    return _DATE.sub(" \u2063 ", text), found


def _leftover(text: str, hits: Sequence[sector_words.Hit]) -> List[str]:
    """찾은 말을 지우고 남은 낱말들 — 뜻을 더하지 않는 말(`FILLER`)은 뺀다."""
    chars = list(text)
    for hit in hits:
        for i in range(hit.start, hit.end):
            chars[i] = " "
    rest = "".join(chars).replace("\u2063", " ")
    words = [w for w in re.split(r"[\s~\-+:]+", rest) if w]
    return [w for w in words if w.lower() not in FILLER and tx.norm(w)]


def _is_note(text: str, had_date: bool) -> bool:
    plain = text.replace("\u2063", " ").strip()
    if had_date or "\u2063" in text:
        return True
    if group_name.canonical(plain) is not None:
        return True          # 그룹 표시 · 그룹 이름(`B` · `b그룹` · `Pre IPO`)
    if invest_stage.stages_of(plain) or _STAGE.search(plain):
        return True
    if _AMOUNT.search(plain) or _NOTE.search(plain):
        return True
    return len(tx.norm(plain)) >= SENTENCE_LEN


def read_part(text: str, resolver: Optional[tx.Resolver]) -> Part:
    """조각 하나를 읽는다."""
    hits = sector_words.find(text, resolver)
    tokens = tx.dedupe(h.token for h in hits)
    if hits:
        rest = _leftover(text, hits)
        # 한 글자 찌꺼기(`만` · `들`)는 뜻을 더하지 않는다.
        if "\u2063" not in text and not any(len(tx.norm(w)) > 1 for w in rest):
            return Part(text.strip(), PART_SECTOR, tokens)
        return Part(text.strip(), PART_MIXED, tokens)
    plain = text.replace("\u2063", " ").strip()
    words = [w for w in re.split(r"\s+", plain) if w]
    if words and all(w.lower() in FILLER for w in words):
        # `등` · `기타 분야` 처럼 뜻을 더하지 않는 말만 남은 조각 — 그냥 둔다.
        return Part(plain, PART_SECTOR, [])
    if _is_note(text, False):
        return Part(plain, PART_NOTE, [])
    return Part(plain, PART_UNKNOWN, [])


#: 목록 이름을 감추는 자리표시의 앞뒤. 개인용 영역 글자라 실제 글에는 안 나온다.
_NAME_OPEN, _NAME_CLOSE = "\ue000", "\ue001"


def _protect_names(text: str, resolver: Optional[tx.Resolver]):
    """**가르는 글자가 든 목록 이름**을 자리표시로 감춘다 — `(감춘 글, 되돌릴 표)`.

    조각을 가르는 글자 중 `·` `(` `)` 는 목록 이름 안에도 있다(`핀테크·블록체인` ·
    `DID·인증` · `공급망금융(SCF)`). 그대로 가르면 이름이 반쪽으로 쪼개져, 대분류를
    골라 적은 줄(`핀테크·블록체인, 로봇`)에서 `블록체인` 이 소분류로 따로 걸리고
    `DID·인증` 은 `DID` · `인증` 두 조각이 된다 — 목록대로 적힌 값을 재분류가 망친다.
    그래서 가르기 **전에** 글 전체에서 이름을 먼저 찾고(`sector_words.find` — 긴 말이
    이긴다), 가르는 글자가 든 것만 감춰 둔다. 날짜를 감추는 `_protect_dates` 와 같은 수다.
    """
    saved = {}
    out, last = [], 0
    for i, hit in enumerate(sector_words.find(text, resolver)):
        piece = text[hit.start:hit.end]
        if not _SPLIT.search(piece):
            continue
        key = f"{_NAME_OPEN}{i}{_NAME_CLOSE}"
        saved[key] = piece
        out.append(text[last:hit.start])
        out.append(key)
        last = hit.end
    out.append(text[last:])
    return "".join(out), saved


def _restore_names(text: str, saved) -> str:
    for key, piece in saved.items():
        text = text.replace(key, piece)
    return text


def read_line(line: str, resolver: Optional[tx.Resolver]) -> LineResult:
    """줄 하나를 읽는다. 무엇을 칸에 남기고 무엇을 메모로 보낼지."""
    text = line.strip()
    out = LineResult(text=text)
    if not text:
        return out
    # 줄 전체가 목록의 이름 하나다(`ESG,푸드,애그테크` 처럼 가운뎃점 대신 쉼표로
    # 적어도) — 조각을 내면 반쪽 이름들이 따로 걸린다.
    whole = resolver.by_norm(re.sub(r"[,/|;]", "", text)) if resolver else None
    if whole is not None and not whole.is_hidden:
        parent = resolver.parent_of(whole) if whole.parent_id else None
        if whole.parent_id is None or parent is not None:
            out.tokens = [whole.name]
            return out
    if _NEGATION.search(text):
        out.negated = True
        out.to_memo = True
        return out
    protected, _had_date = _protect_dates(text)
    protected, names = _protect_names(protected, resolver)
    for raw in _SPLIT.split(protected):
        if not raw or not raw.replace("\u2063", "").strip():
            if raw and "\u2063" in raw:
                out.to_memo = True       # 날짜만 있는 조각
            continue
        part = read_part(_restore_names(raw, names), resolver)
        if part.kind in (PART_SECTOR, PART_MIXED):
            out.tokens += part.tokens
        if part.kind in (PART_MIXED, PART_NOTE):
            out.to_memo = True
        if part.kind == PART_UNKNOWN:
            out.unknown.append(part.text)
    out.tokens = tx.dedupe(out.tokens)
    return out


def classify(value: Optional[str], resolver: Optional[tx.Resolver]) -> Result:
    """선호분야 글 하나 → 바꿀 계획. **DB 를 안 본다**(목록은 `resolver` 로 받는다)."""
    before = value or ""
    lines = [r for r in (read_line(l, resolver) for l in before.splitlines()) if r.text]
    # 목록의 말도 메모 말도 없는 줄(`ex. ○○`)은 **다른 줄이 분야나 메모로 읽힐
    # 때** 그 글의 일부다 — 같이 메모로 보낸다. 그 줄 하나뿐인 글(`스포츠`)은
    # 칸에 남겨 `못 맞춘 조각` 으로 띄운다(분야 말을 사전이 모르는 것일 수 있다).
    for i, line in enumerate(lines):
        if line.to_memo or line.tokens or not line.unknown:
            continue
        others = [o for j, o in enumerate(lines) if j != i]
        if any(o.to_memo or o.tokens for o in others):
            line.to_memo = True
    tokens: List[str] = []
    keep_unknown: List[str] = []
    moved: List[str] = []
    for line in lines:
        tokens += line.tokens
        if line.to_memo:
            moved.append(line.text)
        else:
            keep_unknown += line.unknown
    tokens = tx.dedupe(tokens)
    after = tx.join_sectors(tx.dedupe(tokens + keep_unknown))
    # 못 맞춘 조각 = **칸에 남는** 조각. 메모로 가는 줄 안의 말은 그 줄째로
    # `메모로 옮길 글` 에 보인다.
    return Result(before=before, after=after, moved=moved,
                  unmatched=list(dict.fromkeys(keep_unknown)), tokens=tokens)


def append_memo(memo: Optional[str], lines: Sequence[str]) -> str:
    """메모 뒤에 옮긴 줄을 붙인다. 이미 같은 줄이 있으면 또 붙이지 않는다."""
    current = (memo or "").rstrip()
    have = {l.strip() for l in current.splitlines()}
    add = [f"{MOVED_MARK} {line}" for line in lines
           if f"{MOVED_MARK} {line}" not in have]
    if not add:
        return memo or ""
    return "\n".join(([current] if current else []) + add)


# ── 미리보기 · 반영 ─────────────────────────────────────────────────────────

def _rows(db: Session) -> List[VcContact]:
    """선호분야가 **적힌** 줄만. 빈 칸은 건드리지 않는다(사용자 결정)."""
    return [c for c in db.execute(
        select(VcContact).where(VcContact.sectors.is_not(None))
        .order_by(VcContact.id)).scalars() if (c.sectors or "").strip()]


def plan(db: Session) -> List[Tuple[VcContact, Result]]:
    tx.ensure_seed(db)
    resolver = tx.Resolver.load(db)
    return [(c, classify(c.sectors, resolver)) for c in _rows(db)]


def preview(db: Session) -> dict:
    """미리보기 — 사람마다 `전 → 후 · 메모로 옮길 글 · 못 맞춘 조각`."""
    owners = {u.id: u.name for u in db.execute(select(User)).scalars()}
    changes, only_unmatched = [], []
    untouched = 0
    for contact, result in plan(db):
        row = {"id": contact.id, "name": contact.name or "",
               "firm": contact.firm or "", "owner": owners.get(contact.user_id, ""),
               "hidden": bool(contact.is_hidden),
               "before": result.before, "after": result.after,
               "moved": result.moved, "unmatched": result.unmatched}
        if result.changes:
            changes.append(row)
        elif result.unmatched:
            only_unmatched.append(row)
        else:
            untouched += 1
    return {"rows": changes, "unmatched_only": only_unmatched,
            "counts": {"changes": len(changes),
                       "matched": sum(1 for r in changes if r["after"]),
                       "moved": sum(1 for r in changes if r["moved"]),
                       "unmatched": sum(1 for r in changes + only_unmatched
                                        if r["unmatched"]),
                       "untouched": untouched,
                       "total": len(changes) + len(only_unmatched) + untouched}}


def apply(db: Session, contact_ids: Optional[Sequence[int]] = None) -> dict:
    """반영 — `contact_ids` 가 없으면 **미리보기에 뜬 전부**. 한 트랜잭션.

    계획은 여기서 다시 세운다(화면이 보낸 값은 안 쓴다 — 그 사이 칸이 고쳐졌을
    수 있다). 원래 글은 처음 한 번만 백업 칸에 남는다.
    """
    wanted = None if contact_ids is None else {int(i) for i in contact_ids}
    if wanted is not None and not wanted:
        raise tx.TaxonomyError("반영할 투자사를 고르세요")
    applied = 0
    moved = 0
    for contact, result in plan(db):
        if not result.changes or (wanted is not None and contact.id not in wanted):
            continue
        tx.backup_once(contact, "sectors")
        contact.sectors = result.after or None
        if result.moved:
            contact.memo = append_memo(contact.memo, result.moved)
            moved += 1
        applied += 1
    if wanted is not None and not applied:
        raise tx.TaxonomyError("그 사이 값이 바뀌었습니다. 미리보기를 다시 열어 주세요")
    db.commit()
    return {"applied": applied, "moved": moved,
            "skipped": (len(wanted) - applied) if wanted is not None else 0}
