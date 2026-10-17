"""IR 기업 현황의 대분류·소분류를 **분야 기준 목록**에 맞춘다 — 미리보기 → 고른 것만 반영.

## 무엇을 바꾸나 (사용자가 정한 표의 `정리 규칙` 그대로)

    오탈자 · 옛 이름       `신약개` → `신약개발` · 대분류 `뷰티` → `커머스·라이프스타일`
                           목록에 **합쳐진 옛 이름**으로 들어 있다(`taxonomy.SEED_ALIASES`).
    철자 통일             `AI SaaS 데이터` → `AI·SaaS·데이터` · `생성형AI / AI SaaS` →
                           `생성형AI, AI SaaS` (가운뎃점·공백·대소문자만 다른 것)
    목록에 맞춰 나눔       `광학·센서` → `광학, 센서` — 목록에 둘이 따로 있을 때만
    대분류 옮김           소분류가 목록에서 **다른 대분류 아래** 있으면 그리로
                           (`첨단소재` 는 딥테크·제조로 · `배터리` 는 여기로 모음 …)
    빈 대분류 제안         소분류 → 대분류 대응, 없으면 한 줄 소개의 낱말
                           (`sector_words`). **제안은 미리 골라 두지 않는다** —
                           사용자 결정 ②(제안 목록을 만들어 확인받는다).

옮기는 규칙을 기업마다 따로 적지 않는다. 소분류가 목록에서 어느 대분류 아래에
있는가가 곧 그 규칙이라, 관리자가 목록에서 소분류를 옮기면 다음 미리보기가 그대로
따라간다.

## 손대지 않는 것

  · **시험용으로 보이는 대분류**(`테스트`)는 바꾸지 않고 `정리 대상` 으로만 띄운다.
  · 목록에 없는 말은 그대로 두고 `목록에 없는 값` 으로 띄운다 — 짐작으로 옮기지
    않는다. 목록에 더하거나(별칭으로 합치거나) 손으로 고친 뒤 다시 돌린다.
  · 라운드(`series`)는 보지도 않는다(사용자 결정 ③ — 투자단계 재분류는 대기).

## 원래 값

바꾸기 전에 `sector_major_raw` · `sector_minor_raw` 에 **처음 한 번만** 남긴다
(`taxonomy.backup_once`). 다시 돌려도 백업은 그대로다.

## 반영은 서버가 다시 짠 계획대로

화면이 보낸 값을 그대로 적지 않는다. 고른 기업 번호만 받고 계획을 **다시 세워**
그 안에 있는 것만 바꾼다 — 미리보기를 띄운 사이 누가 그 기업을 고쳤으면 화면의
값은 이미 낡았다(`routers/companies.bulk_one_liner_apply` 와 같은 판단). 제안 줄만은
관리자가 대분류를 바꿔 고를 수 있어, 그 값이 **목록에 있는 대분류일 때만** 받는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IrCompany
from . import sector_hint, sector_words
from . import taxonomy as tx

#: 줄 하나의 갈래. 화면이 이 값으로 묶어 보여 준다.
KIND_FIX = "fix"          # 규칙대로 바꾼다(미리 골라 둔다)
KIND_SUGGEST = "suggest"  # 빈 대분류 제안(미리 고르지 않는다)


@dataclass
class Row:
    """기업 하나를 어떻게 할지."""

    id: int
    name: str
    major: str
    minor: str
    new_major: str
    new_minor: str
    kind: str
    reasons: List[str] = field(default_factory=list)
    #: 제안 줄의 근거가 한 줄 소개였나(`소분류` 근거면 False).
    from_text: bool = False

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "major": self.major, "minor": self.minor,
                "new_major": self.new_major, "new_minor": self.new_minor,
                "kind": self.kind, "reasons": self.reasons,
                "checked": self.kind == KIND_FIX}


@dataclass
class Plan:
    rows: List[Row] = field(default_factory=list)
    #: 시험용으로 보이는 대분류(정리 대상) — 바꾸지 않는다.
    flagged: List[dict] = field(default_factory=list)
    #: 목록에 없는 말 → 그 말을 쓰는 기업 수.
    unknown_majors: Dict[str, int] = field(default_factory=dict)
    unknown_minors: Dict[str, int] = field(default_factory=dict)
    #: 대분류가 비었는데 제안도 못 만든 기업.
    no_suggestion: List[dict] = field(default_factory=list)
    total: int = 0

    def as_dict(self, majors: Sequence[str]) -> dict:
        fixes = [r for r in self.rows if r.kind == KIND_FIX]
        suggests = [r for r in self.rows if r.kind == KIND_SUGGEST]
        return {
            "rows": [r.as_dict() for r in self.rows],
            "flagged": self.flagged,
            "unknown_majors": sorted(self.unknown_majors.items()),
            "unknown_minors": sorted(self.unknown_minors.items()),
            "no_suggestion": self.no_suggestion,
            "majors": list(majors),
            "counts": {"fix": len(fixes), "suggest": len(suggests),
                       "flagged": len(self.flagged),
                       "no_suggestion": len(self.no_suggestion),
                       "total": self.total},
        }


def _minor_terms(resolver: tx.Resolver, cell: str):
    """소분류 칸 → [(적힌 낱말, 기준 줄 또는 None, 까닭)]. 목록에 맞춰 나눌 것은 나눈다."""
    out = []
    for token in tx.split_minor(cell):
        term = resolver.minor(token)
        if term is not None:
            out.append((token, term, ""))
            continue
        # `광학·센서` — 목록에 `광학` 과 `센서` 가 따로 있으면 둘로 나눈다.
        # **조각이 전부 목록에 있을 때만.** 하나라도 모르면 나누지 않는다 —
        # 반쪽만 맞춘 이름이 생긴다.
        parts = [p.strip() for p in token.replace("ㆍ", "·").split("·") if p.strip()]
        found = [resolver.minor(p) for p in parts]
        if len(parts) > 1 and all(found):
            for part, hit in zip(parts, found):
                out.append((part, hit, f"소분류 `{token}` → 목록대로 나눔"))
            continue
        out.append((token, None, ""))
    return out


def _parent_name(resolver: tx.Resolver, token: str) -> str:
    term = resolver.minor(token)
    parent = resolver.parent_of(term) if term is not None else None
    return parent.name if parent is not None else ""


def _suggest(resolver: tx.Resolver, company: IrCompany) -> Optional[tuple]:
    """빈 대분류에 넣을 제안 — (대분류, 까닭). 못 만들면 None.

    소분류 칸에 적힌 글(목록 밖 낱말이라도 `수산업` 처럼 업종이 읽히는 것)을 먼저,
    그다음 한 줄 소개를 본다. 자리채움 글(`회사정보 검색안됨`)에는 만들지 않는다
    (`sector_hint.readable` — 없는 근거로 만든 값이 칸에 들어간다).
    """
    # 한 줄 소개는 앞 토막만 본다 — 뒤는 `매출 13억 | 누적투자 …` 같은 금액이라
    # 업종과 상관이 없다(`sector_hint.source_text` 가 그 자르기를 한 곳에서 한다).
    for label, text in (("소분류", company.sector_minor),
                        ("한 줄 소개", sector_hint.source_text(company))):
        if not text or not sector_hint.readable(text):
            continue
        hits = sector_words.find(text, resolver)
        if not hits:
            continue
        counts: Dict[str, int] = {}
        for hit in hits:
            counts[hit.major] = counts.get(hit.major, 0) + 1
        # 가장 많이 걸린 대분류, 같으면 먼저 나온 것.
        order = [h.major for h in hits]
        best = max(counts, key=lambda m: (counts[m], -order.index(m)))
        words = ", ".join(dict.fromkeys(h.word for h in hits if h.major == best))
        return best, f"{label}의 `{words}`"
    return None


def plan(db: Session) -> Plan:
    """지금 값으로 세운 정리 계획. **아무것도 쓰지 않는다.**"""
    tx.ensure_seed(db)
    resolver = tx.Resolver.load(db)
    flagged_keys = {tx.norm(m) for m in tx.CLEANUP_ONLY_MAJORS}
    out = Plan()
    companies = list(db.execute(select(IrCompany).order_by(IrCompany.name,
                                                           IrCompany.id)).scalars())
    out.total = len(companies)
    for company in companies:
        major = (company.sector_major or "").strip()
        minor = (company.sector_minor or "").strip()
        if major and tx.norm(major) in flagged_keys:
            out.flagged.append({"id": company.id, "name": company.name,
                                "major": major, "minor": minor})
            continue
        reasons: List[str] = []

        # ── 소분류 ──────────────────────────────────────────────────────
        tokens, minor_majors = [], []
        read = _minor_terms(resolver, minor)
        if read and all(term is None for _w, term, _y in read):
            # 목록의 말이 하나도 없는 칸(`어촌 기업 (수산업 …)` 같은 설명 글)은
            # **통째로 그대로** 둔다 — 쉼표를 다시 찍는 것도 고치는 것이다.
            read = [(minor, None, "")]
        for written, term, why in read:
            if term is None:
                tokens.append(written)
                out.unknown_minors[written] = out.unknown_minors.get(written, 0) + 1
                continue
            tokens.append(term.name)
            parent = resolver.parent_of(term)
            if parent is not None:
                minor_majors.append(parent.name)
            if why:
                if why not in reasons:
                    reasons.append(why)
            elif tx.norm(written) != tx.norm(term.name):
                reasons.append(f"소분류 옛 이름 `{written}` → `{term.name}`")
            elif written != term.name:
                reasons.append(f"소분류 철자 통일 `{written}` → `{term.name}`")
        tokens = tx.dedupe(tokens)
        new_minor = tx.join_minor(tokens)
        if new_minor != minor and tx.split_minor(minor) == tokens:
            # 낱말은 그대로인데 가르는 글자만 달랐다(`A / B` → `A, B`).
            reasons.append("소분류 구분 기호 통일")

        # ── 대분류 ──────────────────────────────────────────────────────
        major_term = resolver.major(major) if major else None
        current = major_term.name if major_term else major
        if major and major_term is None:
            out.unknown_majors[major] = out.unknown_majors.get(major, 0) + 1
        elif major_term is not None and current != major:
            if tx.norm(major) == tx.norm(current):
                reasons.append(f"대분류 철자 통일 `{major}` → `{current}`")
            else:
                reasons.append(f"대분류 옛 이름 `{major}` → `{current}`")

        kind = KIND_FIX
        from_text = False
        if minor_majors:
            new_major = tx.pick_major(current, tx.dedupe(minor_majors))
            if not major:
                reasons.append(f"빈 대분류 채움 — 소분류 `{tokens[0]}`: 목록에서 "
                               f"`{new_major}` 아래")
            elif tx.norm(new_major) != tx.norm(current):
                movers = [t for t in tokens if _parent_name(resolver, t) == new_major]
                reasons.append(f"대분류 옮김 — 소분류 `{', '.join(movers)}`: 목록에서 "
                               f"`{new_major}` 아래")
        else:
            new_major = current
            if not major:
                found = _suggest(resolver, company)
                if found is None:
                    out.no_suggestion.append({"id": company.id, "name": company.name,
                                              "minor": minor})
                else:
                    new_major, why = found
                    kind, from_text = KIND_SUGGEST, True
                    reasons.append(f"빈 대분류 제안 — {why}")

        if new_major == major and new_minor == minor:
            continue
        out.rows.append(Row(id=company.id, name=company.name, major=major,
                            minor=minor, new_major=new_major, new_minor=new_minor,
                            kind=kind, reasons=reasons, from_text=from_text))
    return out


def preview(db: Session) -> dict:
    result = plan(db)
    resolver = tx.Resolver.load(db)
    return result.as_dict([m.name for m in resolver.visible_majors()])


def apply(db: Session, items: Sequence[dict]) -> dict:
    """고른 기업만 반영한다. `items` = `[{id, major?}]` — `major` 는 제안 줄에서만 읽는다.

    커밋은 여기서 한 번 한다(한 트랜잭션).
    """
    wanted = {int(i["id"]): (i.get("major") or "").strip()
              for i in items if str(i.get("id", "")).isdigit()}
    if not wanted:
        raise tx.TaxonomyError("반영할 기업을 고르세요")
    result = plan(db)
    resolver = tx.Resolver.load(db)
    majors = {tx.norm(m.name): m.name for m in resolver.visible_majors()}
    edits: List[tx.Edit] = []
    picked = 0
    for row in result.rows:
        if row.id not in wanted:
            continue
        company = db.get(IrCompany, row.id)
        if company is None:
            continue
        new_major = row.new_major
        if row.kind == KIND_SUGGEST and wanted[row.id]:
            chosen = majors.get(tx.norm(wanted[row.id]))
            if chosen is None:
                raise tx.TaxonomyError(f"목록에 없는 대분류입니다: {wanted[row.id]}")
            new_major = chosen
        picked += 1
        if new_major != (company.sector_major or ""):
            edits.append(tx.Edit(company, "sector_major",
                                 company.sector_major or "", new_major))
        if row.new_minor != (company.sector_minor or ""):
            edits.append(tx.Edit(company, "sector_minor",
                                 company.sector_minor or "", row.new_minor))
    if not picked:
        raise tx.TaxonomyError("그 사이 값이 바뀌었습니다. 미리보기를 다시 열어 주세요")
    changed = tx.apply_edits(edits)
    db.commit()
    return {"applied": picked, "changed": changed,
            "skipped": len(wanted) - picked}
