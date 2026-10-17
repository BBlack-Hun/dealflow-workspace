"""분야 기준 목록 — **대분류 → 소분류 두 단계의 고정 목록이 사는 한 곳**(개선 과제 #2).

## 왜 필요한가

IR 기업 현황의 `대분류`·`소분류` 와 투자사의 `선호 투자분야` 가 같은 것을 서로
다른 말로 적어 왔다. 기업은 `딥테크·제조 / 반도체` 인데 투자사는 `제조분야(방산,
반도체 분야) 6/25` 처럼 적으니, 둘을 맞춰 보는 자리(`matcher.evaluate_company` ·
`llm_brief` 의 분야 이름)가 글자 우연에 기대고 있었다.

사용자가 정했다(2026-10-17) — **기준은 IR 기업 현황의 대분류·소분류다.** 그 목록을
여기서 들고, 관리자가 `분야 기준 목록` 화면에서 고친다(`routers/taxonomy.py`).

## 지우지 않는다 — 숨기고, 합친 곳을 남긴다

목록의 줄을 지우면 그 이름을 쓰던 값이 어디로 가야 할지가 사라진다. 그래서 줄은
숨기기만 하고(`is_hidden`), 합칠 때는 **어디로 합쳤는지**(`merged_into_id`)를
남긴다. 옛 이름(`신약개` · `뷰티` · `물류`)은 처음부터 이 화살표로 들어 있다
(`SEED_ALIASES`) — 정리 화면이 그 이름을 만나면 화살표를 따라 기준 이름으로
바꾼다(`Resolver`).

## 같은 말인지 — 가운뎃점·공백·대소문자는 안 본다

목록의 철자와 실제 값이 조금씩 다르다(`AI·SaaS·데이터` / `AI SaaS 데이터` ·
`ai saas`). 견줄 때는 그 셋을 지운 꼴로 본다(`norm`). 저장은 **목록에 적힌
글자 그대로** 한다.

## 이름을 바꾸거나 합치면 값도 같이 바뀐다

목록만 바뀌고 값이 그대로면 그날부터 목록 밖의 말이 된다. 그래서 이름 바꾸기 ·
합치기 · 옮기기는 **그 이름을 쓰는 IR 기업 현황 값과 투자사 선호분야 값**을 함께
고친다(`plan_rename` · `plan_merge` · `plan_move`). 바꾸기 전에 몇 줄이 바뀌는지
먼저 세어 보여 주고(`impact`), 반영은 한 트랜잭션이다(`apply_edits` 뒤 한 번의
`commit`). 바뀌는 값의 원래 글은 처음 한 번만 백업 칸에 남는다(`backup_once`).

ORM 으로만 고친다 — 수정 로그(`edit_log`)와 딜 소싱 동기화(`sourcing_sync`)가 둘 다
flush 자리에 서 있어서, `UPDATE` 한 방으로 고치면 둘 다 건너뛴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import IrCompany, SectorTerm, VcContact

# ── 처음 값 ─────────────────────────────────────────────────────────────────
#
# 사용자가 정한 표 그대로다(2026-10-17). 글자를 고치지 않는다 — 이 목록이 곧
# 기준이다. 차례도 표의 차례다.
SEED: Sequence[Tuple[str, Sequence[str]]] = (
    ("AI·SaaS·데이터", ("업무자동화", "AI SaaS", "생성형AI", "데이터분석",
                        "AI Agent", "데이터 인프라", "머신러닝", "MLOps", "ERP")),
    ("헬스케어·바이오", ("디지털헬스케어", "의료기기", "신약개발", "웨어러블 헬스케어",
                         "의료AI", "바이오테크", "병원 SaaS", "진단기기",
                         "디지털치료제", "바이오소재")),
    ("ESG·푸드·애그테크", ("푸드테크", "순환경제", "클린테크", "에너지", "스마트팜",
                           "정밀농업", "환경모니터링", "대체식품", "탄소저감",
                           "애그테크")),
    ("커머스·라이프스타일", ("라이프스타일 플랫폼", "뷰티테크", "여행", "레저",
                             "펫테크", "D2C", "리테일테크", "브랜드 애그리게이터",
                             "이커머스")),
    ("딥테크·제조", ("광학", "센서", "첨단소재", "로봇", "산업장비", "반도체",
                     "제조DX", "스마트팩토리", "국방기술", "배터리")),
    ("콘텐츠·엔터테인먼트", ("콘텐츠 제작솔루션", "공연", "이벤트",
                             "크리에이터 플랫폼", "게임", "음악", "IP",
                             "버추얼휴먼", "숏폼")),
    ("에듀테크·HR테크", ("XR교육", "HR SaaS", "시니어 커리어", "AI학습",
                         "온라인교육", "인재매칭", "채용플랫폼")),
    ("모빌리티·물류", ("스마트물류", "모빌리티 플랫폼", "EV충전", "배송테크",
                       "물류자동화", "자율주행", "라스트마일")),
    ("프롭테크·스마트시티", ("건설DX", "스마트시티", "건물관리 SaaS",
                             "부동산 플랫폼")),
    ("핀테크·블록체인", ("블록체인", "RegTech", "간편결제", "공급망금융(SCF)",
                         "자산관리", "DID·인증")),
)

#: 표의 `정리 규칙` 중 **옛 이름 → 기준 이름**. 숨긴 채 합쳐진 줄로 들어간다.
#: `(옛 이름, 그 이름이 있던 대분류 — 대분류면 None, 기준 이름)`.
#:
#: 대분류를 옮기는 규칙(`첨단소재` 는 딥테크·제조로 · `배터리` 는 여기로 모음 …)은
#: 여기 없다 — 소분류가 **목록에서 어느 대분류 아래 있는가**가 그 규칙이다
#: (`services/ir_sector_cleanup.py`). 별칭으로 적으면 같은 규칙이 두 벌이 된다.
SEED_ALIASES: Sequence[Tuple[str, Optional[str], str]] = (
    ("신약개", "헬스케어·바이오", "신약개발"),            # 오탈자
    ("비추얼휴먼", "콘텐츠·엔터테인먼트", "버추얼휴먼"),    # 오탈자
    ("건물 빌딩 관리", "프롭테크·스마트시티", "건물관리 SaaS"),
    ("뷰티", None, "커머스·라이프스타일"),
    ("물류", None, "모빌리티·물류"),
)

#: 시험용으로 보이는 대분류. **지우지 않고** 정리 화면에 `정리 대상` 으로만
#: 띄운다(사용자 결정 — 누가 왜 넣었는지 확인하기 전에는 손대지 않는다).
CLEANUP_ONLY_MAJORS = ("테스트",)

# ── 같은 말인지 ─────────────────────────────────────────────────────────────

#: 견줄 때 지우는 것 — 공백과 가운뎃점 꼴들(`·` `ㆍ` `•` `‧` `・` `∙`).
_SKIP = re.compile(r"[\s·ㆍ•‧・∙]+")


def norm(text: Optional[str]) -> str:
    """견주는 꼴. 가운뎃점·공백·대소문자를 지운다. `AI · SaaS·데이터` → `aisaas데이터`."""
    return _SKIP.sub("", text or "").lower()


#: IR 소분류 칸 하나에 여럿이 적힌다(`AI Agent, 업무자동화` · `생성형AI / AI SaaS`).
_MINOR_SPLIT = re.compile(r"[,/]")


def split_minor(cell: Optional[str]) -> List[str]:
    """IR 소분류 칸 → 낱말들. 쉼표와 `/` 로 가른다(가운뎃점은 이름 안에 있다 —
    `DID·인증`)."""
    return [t.strip() for t in _MINOR_SPLIT.split(cell or "") if t.strip()]


def join_minor(tokens: Iterable[str]) -> str:
    return ", ".join(tokens)


def split_sectors(value: Optional[str]) -> List[str]:
    """투자사 `선호 투자분야` → 낱말들. 화면·엑셀이 읽는 그대로 **쉼표**로만
    가른다(`routers/contacts._split_csv`)."""
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def join_sectors(tokens: Iterable[str]) -> str:
    return ", ".join(tokens)


def dedupe(tokens: Iterable[str]) -> List[str]:
    """같은 말(`norm`)이 두 번이면 먼저 나온 것만. 차례는 그대로."""
    seen, out = set(), []
    for token in tokens:
        key = norm(token)
        if key and key not in seen:
            seen.add(key)
            out.append(token)
    return out


# ── 처음 값 넣기 ────────────────────────────────────────────────────────────

def ensure_seed(db: Session) -> bool:
    """목록이 **비어 있으면** 처음 값을 넣는다. 넣었으면 True.

    줄을 지우는 길이 없으므로(숨김·합침만) 비어 있다는 것은 한 번도 안 넣었다는
    뜻이다 — 사람이 정리해 둔 목록을 되살리는 일은 없다.
    """
    if db.execute(select(func.count(SectorTerm.id))).scalar():
        return False
    majors: Dict[str, SectorTerm] = {}
    for i, (major, minors) in enumerate(SEED):
        row = SectorTerm(name=major, position=i)
        db.add(row)
        db.flush()
        majors[major] = row
        for j, minor in enumerate(minors):
            db.add(SectorTerm(name=minor, parent_id=row.id, position=j))
    db.flush()
    by_name = {norm(t.name): t for t in db.execute(select(SectorTerm)).scalars()}
    for k, (alias, parent, target) in enumerate(SEED_ALIASES):
        goal = by_name[norm(target)]
        db.add(SectorTerm(
            name=alias, is_hidden=1, merged_into_id=goal.id,
            parent_id=(majors[parent].id if parent else None),
            position=1000 + k))
    db.commit()
    return True


# ── 읽기 ────────────────────────────────────────────────────────────────────

def all_terms(db: Session) -> List[SectorTerm]:
    return list(db.execute(
        select(SectorTerm).order_by(SectorTerm.position, SectorTerm.id)).scalars())


@dataclass
class Resolver:
    """옛 이름·철자 차이를 **기준 이름**으로 돌려주는 자.

    줄 전부(숨김·합침 포함)를 한 번 읽어 두고 파이썬에서 찾는다 — 정리 미리보기가
    기업 수백 곳을 한 번에 돌린다.
    """

    terms: Dict[int, SectorTerm] = field(default_factory=dict)
    majors: Dict[str, int] = field(default_factory=dict)
    minors: Dict[str, List[int]] = field(default_factory=dict)

    @classmethod
    def load(cls, db: Session) -> "Resolver":
        return cls.of(all_terms(db))

    @classmethod
    def of(cls, rows: Iterable[SectorTerm]) -> "Resolver":
        out = cls()
        for row in rows:
            out.terms[row.id] = row
        for row in out.terms.values():
            key = norm(row.name)
            if row.parent_id is None:
                out.majors.setdefault(key, row.id)
            else:
                out.minors.setdefault(key, []).append(row.id)
        return out

    def canonical(self, term_id: Optional[int]) -> Optional[SectorTerm]:
        """합쳐진 줄이면 화살표 끝까지 따라간다(돌고 도는 화살표는 끊는다)."""
        seen = set()
        row = self.terms.get(term_id) if term_id else None
        while row is not None and row.merged_into_id and row.id not in seen:
            seen.add(row.id)
            following = self.terms.get(row.merged_into_id)
            if following is None:
                break
            row = following
        return row

    def major(self, text: Optional[str]) -> Optional[SectorTerm]:
        """대분류 이름 → 기준 대분류 줄. 모르면 None."""
        hit = self.majors.get(norm(text))
        return self.canonical(hit) if hit else None

    def minor(self, text: Optional[str]) -> Optional[SectorTerm]:
        """소분류 이름 → 기준 소분류 줄. 모르면 None.

        같은 이름이 여럿이면(합쳐진 옛 이름이 다른 대분류에 남은 경우) 화살표를
        따라간 끝이 같으므로 첫 것을 쓴다.
        """
        ids = self.minors.get(norm(text)) or []
        return self.canonical(ids[0]) if ids else None

    def parent_of(self, minor: SectorTerm) -> Optional[SectorTerm]:
        return self.canonical(minor.parent_id)

    def by_norm(self, text: Optional[str]) -> Optional[SectorTerm]:
        """대분류든 소분류든 — 같은 꼴의 기준 줄."""
        return self.major(text) or self.minor(text)

    def visible_majors(self) -> List[SectorTerm]:
        return sorted((t for t in self.terms.values()
                       if t.parent_id is None and not t.is_hidden
                       and not t.merged_into_id),
                      key=lambda t: (t.position, t.id))

    def visible_minors(self, major_id: int) -> List[SectorTerm]:
        return sorted((t for t in self.terms.values()
                       if t.parent_id == major_id and not t.is_hidden
                       and not t.merged_into_id),
                      key=lambda t: (t.position, t.id))


def tree(db: Session, *, include_hidden: bool = False) -> List[dict]:
    """화면이 그리는 목록. 대분류마다 소분류를 붙여 차례대로.

    `include_hidden` 은 관리자 화면 하나만 쓴다 — 고르는 자리(투자사 선호분야)에
    숨긴 줄이 서면 숨긴 뜻이 없다.
    """
    ensure_seed(db)
    resolver = Resolver.load(db)
    names = {t.id: t.name for t in resolver.terms.values()}
    out = []
    majors = sorted((t for t in resolver.terms.values() if t.parent_id is None),
                    key=lambda t: (t.position, t.id))
    for major in majors:
        if not include_hidden and (major.is_hidden or major.merged_into_id):
            continue
        minors = sorted((t for t in resolver.terms.values()
                         if t.parent_id == major.id),
                        key=lambda t: (t.position, t.id))
        out.append({
            "id": major.id, "name": major.name,
            "hidden": bool(major.is_hidden),
            "merged_into": names.get(major.merged_into_id, ""),
            "minors": [{"id": m.id, "name": m.name, "hidden": bool(m.is_hidden),
                        "merged_into": names.get(m.merged_into_id, "")}
                       for m in minors
                       if include_hidden or not (m.is_hidden or m.merged_into_id)],
        })
    return out


def picker_tree(db: Session) -> List[dict]:
    """고르는 자리(투자사 선호분야)가 쓰는 꼴 — `[{name, minors: [이름…]}]`."""
    return [{"name": m["name"], "minors": [x["name"] for x in m["minors"]]}
            for m in tree(db)]


# ── 값을 고칠 계획 ──────────────────────────────────────────────────────────

class TaxonomyError(Exception):
    """할 수 없는 고침. 화면에 그대로 띄운다(400)."""


@dataclass
class Edit:
    """값 하나를 어떻게 바꿀지. 미리보기는 세기만 하고, 반영은 그대로 적는다."""

    obj: object
    field: str
    old: str
    new: str


#: 값 칸 → 원래 값을 남기는 칸.
RAW_FIELD = {"sector_major": "sector_major_raw",
             "sector_minor": "sector_minor_raw",
             "sectors": "sectors_raw"}


def backup_once(obj, field_name: str) -> None:
    """바꾸기 **전에** 원래 값을 백업 칸에 남긴다 — 이미 남아 있으면 그대로 둔다.

    NULL 이 '아직 손댄 적 없음' 이다. 빈 값을 바꾸는 경우(빈 대분류에 제안을
    넣을 때)에는 `""` 을 남긴다 — 그래야 다음 판이 이 칸을 다시 백업하지 않는다.
    """
    raw = RAW_FIELD.get(field_name)
    if raw and getattr(obj, raw, None) is None:
        setattr(obj, raw, getattr(obj, field_name, None) or "")


def apply_edits(edits: Iterable[Edit]) -> int:
    """계획대로 적는다. 커밋은 부르는 쪽이 한 번에 한다. 바꾼 칸 수를 돌려준다."""
    count = 0
    for edit in edits:
        if (getattr(edit.obj, edit.field, None) or "") == edit.new:
            continue
        backup_once(edit.obj, edit.field)
        setattr(edit.obj, edit.field, edit.new or None)
        count += 1
    return count


def impact(edits: Sequence[Edit]) -> dict:
    """미리보기 수 — **몇 줄이** 바뀌는가(칸 수가 아니다)."""
    ir = {id(e.obj) for e in edits if isinstance(e.obj, IrCompany)}
    vc = {id(e.obj) for e in edits if isinstance(e.obj, VcContact)}
    return {"ir": len(ir), "vc": len(vc)}


def pick_major(current: Optional[str], majors: Sequence[str]) -> str:
    """소분류들이 가리키는 대분류들 중 이 기업의 대분류를 고른다.

    지금 대분류가 그중에 있으면 **그대로 둔다** — 소분류가 둘 이상의 대분류에
    걸친 기업(`EV충전, 배터리`)을 괜히 옮기지 않는다. 없으면 **첫 소분류**의
    대분류다(사람이 먼저 적은 것이 그 기업의 주 분야다).
    """
    if not majors:
        return current or ""
    if current and norm(current) in {norm(m) for m in majors}:
        return next(m for m in majors if norm(m) == norm(current))
    return majors[0]


def _ir_rows(db: Session) -> List[IrCompany]:
    return list(db.execute(select(IrCompany).order_by(IrCompany.id)).scalars())


def _vc_rows(db: Session) -> List[VcContact]:
    return list(db.execute(
        select(VcContact).where(VcContact.sectors.is_not(None))
        .order_by(VcContact.id)).scalars())


def _replace_tokens(tokens: List[str], old: str, new: str) -> List[str]:
    key = norm(old)
    return dedupe(new if norm(t) == key else t for t in tokens)


def _vc_edits(db: Session, old: str, new: str) -> List[Edit]:
    """투자사 선호분야에서 `old` 낱말을 `new` 로. **낱말이 통째로 같을 때만**
    바꾼다 — 아직 자유 글로 남은 줄(`6/17 반도체 소부장 위주`)은 안 건드린다."""
    out = []
    for row in _vc_rows(db):
        tokens = split_sectors(row.sectors)
        if not any(norm(t) == norm(old) for t in tokens):
            continue
        after = join_sectors(_replace_tokens(tokens, old, new))
        if after != (row.sectors or ""):
            out.append(Edit(row, "sectors", row.sectors or "", after))
    return out


def _check_name(db: Session, name: str, *, exclude: Optional[int] = None) -> str:
    text = re.sub(r"\s+", " ", (name or "")).strip()
    if not text:
        raise TaxonomyError("이름을 적어 주세요")
    if "," in text or "/" in text:
        # 소분류 칸·선호분야 칸이 이 글자로 여럿을 가른다 — 이름에 들어가면
        # 한 이름이 두 낱말로 쪼개진다.
        raise TaxonomyError("이름에 쉼표(,)나 빗금(/)은 쓸 수 없습니다")
    for row in all_terms(db):
        if row.id != exclude and norm(row.name) == norm(text):
            where = ("숨긴 줄" if row.is_hidden or row.merged_into_id else "목록")
            raise TaxonomyError(f"이미 {where}에 같은 이름이 있습니다: {row.name}")
    return text


def _live(db: Session, term_id: int) -> SectorTerm:
    row = db.get(SectorTerm, term_id)
    if row is None:
        raise TaxonomyError("없는 줄입니다")
    if row.merged_into_id:
        raise TaxonomyError("이미 다른 줄로 합쳐진 이름입니다")
    return row


def plan_rename(db: Session, term_id: int, new_name: str) -> Tuple[SectorTerm, str, List[Edit]]:
    """이름을 바꾸면 무엇이 바뀌는가 — (줄, 새 이름, 값 고침)."""
    row = _live(db, term_id)
    name = _check_name(db, new_name, exclude=row.id)
    edits: List[Edit] = []
    if row.parent_id is None:
        for company in _ir_rows(db):
            if company.sector_major and norm(company.sector_major) == norm(row.name):
                edits.append(Edit(company, "sector_major", company.sector_major, name))
    else:
        for company in _ir_rows(db):
            tokens = split_minor(company.sector_minor)
            if any(norm(t) == norm(row.name) for t in tokens):
                after = join_minor(_replace_tokens(tokens, row.name, name))
                edits.append(Edit(company, "sector_minor",
                                  company.sector_minor or "", after))
    edits += _vc_edits(db, row.name, name)
    return row, name, edits


def plan_merge(db: Session, source_id: int, target_id: int) -> Tuple[SectorTerm, SectorTerm, List[Edit]]:
    """`source` 를 `target` 으로 합치면 무엇이 바뀌는가.

    같은 단계끼리만 합친다(대분류↔대분류 · 소분류↔소분류). 소분류를 다른
    대분류의 소분류로 합치면, 그 소분류 때문에 옛 대분류에 서 있던 기업은 새
    대분류로 따라간다(`pick_major` — 다른 소분류가 옛 대분류를 붙들고 있으면 둔다).
    """
    source, target = _live(db, source_id), _live(db, target_id)
    if source.id == target.id:
        raise TaxonomyError("같은 줄로는 합칠 수 없습니다")
    if (source.parent_id is None) != (target.parent_id is None):
        raise TaxonomyError("대분류는 대분류끼리, 소분류는 소분류끼리 합칩니다")
    if target.is_hidden:
        # 숨긴 줄로 합치면 그 값이 고르는 목록 밖의 말이 된다.
        raise TaxonomyError("숨긴 줄로는 합칠 수 없습니다 — 먼저 다시 보이게 하세요")
    edits: List[Edit] = []
    resolver = Resolver.load(db)
    if source.parent_id is None:
        for company in _ir_rows(db):
            if company.sector_major and norm(company.sector_major) == norm(source.name):
                edits.append(Edit(company, "sector_major", company.sector_major,
                                  target.name))
    else:
        old_parent = resolver.canonical(source.parent_id)
        new_parent = resolver.canonical(target.parent_id)
        for company in _ir_rows(db):
            tokens = split_minor(company.sector_minor)
            if not any(norm(t) == norm(source.name) for t in tokens):
                continue
            after = _replace_tokens(tokens, source.name, target.name)
            edits.append(Edit(company, "sector_minor", company.sector_minor or "",
                              join_minor(after)))
            if (old_parent and new_parent and old_parent.id != new_parent.id
                    and norm(company.sector_major) == norm(old_parent.name)):
                majors = []
                for token in after:
                    term = (target if norm(token) == norm(target.name)
                            else resolver.minor(token))
                    parent = (new_parent if term is target
                              else resolver.parent_of(term) if term else None)
                    if parent:
                        majors.append(parent.name)
                new_major = pick_major(company.sector_major, majors)
                if new_major and new_major != company.sector_major:
                    edits.append(Edit(company, "sector_major",
                                      company.sector_major or "", new_major))
    edits += _vc_edits(db, source.name, target.name)
    return source, target, edits


def plan_move(db: Session, term_id: int, parent_id: int) -> Tuple[SectorTerm, SectorTerm, List[Edit]]:
    """소분류를 다른 대분류로 옮기면 무엇이 바뀌는가.

    소분류 이름은 그대로라 투자사 선호분야는 안 바뀐다. IR 기업 중 **옛 대분류에
    그 소분류로 서 있던 곳**이 새 대분류로 따라간다(`pick_major`).
    """
    row = _live(db, term_id)
    if row.parent_id is None:
        raise TaxonomyError("대분류는 옮길 수 없습니다 — 합치기를 쓰세요")
    parent = _live(db, parent_id)
    if parent.parent_id is not None:
        raise TaxonomyError("소분류 아래로는 옮길 수 없습니다")
    if parent.id == row.parent_id:
        raise TaxonomyError("이미 그 대분류 아래 있습니다")
    if parent.is_hidden:
        raise TaxonomyError("숨긴 대분류 아래로는 옮길 수 없습니다 — 먼저 다시 보이게 하세요")
    resolver = Resolver.load(db)
    old_parent = resolver.canonical(row.parent_id)
    edits: List[Edit] = []
    for company in _ir_rows(db):
        tokens = split_minor(company.sector_minor)
        if not any(norm(t) == norm(row.name) for t in tokens):
            continue
        if old_parent and norm(company.sector_major) != norm(old_parent.name):
            continue
        majors = []
        for token in tokens:
            term = resolver.minor(token)
            if term is not None and term.id == row.id:
                majors.append(parent.name)
            elif term is not None and resolver.parent_of(term):
                majors.append(resolver.parent_of(term).name)
        new_major = pick_major(company.sector_major, majors)
        if new_major and new_major != company.sector_major:
            edits.append(Edit(company, "sector_major", company.sector_major or "",
                              new_major))
    return row, parent, edits


# ── 목록 자체를 고친다 ──────────────────────────────────────────────────────

def _siblings(db: Session, parent_id: Optional[int]) -> List[SectorTerm]:
    query = select(SectorTerm).where(SectorTerm.merged_into_id.is_(None))
    query = query.where(SectorTerm.parent_id.is_(None) if parent_id is None
                        else SectorTerm.parent_id == parent_id)
    return list(db.execute(query.order_by(SectorTerm.position, SectorTerm.id)).scalars())


def add(db: Session, name: str, parent_id: Optional[int] = None) -> SectorTerm:
    """줄 하나를 더한다(맨 아래). 커밋은 부르는 쪽."""
    text = _check_name(db, name)
    if parent_id is not None:
        parent = _live(db, parent_id)
        if parent.parent_id is not None:
            raise TaxonomyError("소분류 아래에는 더할 수 없습니다")
        if parent.is_hidden:
            raise TaxonomyError("숨긴 대분류 아래에는 더할 수 없습니다 — 먼저 다시 보이게 하세요")
    siblings = _siblings(db, parent_id)
    row = SectorTerm(name=text, parent_id=parent_id,
                     position=(max((s.position for s in siblings), default=-1) + 1))
    db.add(row)
    db.flush()
    return row


def rename(db: Session, term_id: int, new_name: str) -> dict:
    row, name, edits = plan_rename(db, term_id, new_name)
    changed = apply_edits(edits)
    row.name = name
    return {"changed": changed, **impact(edits)}


def merge(db: Session, source_id: int, target_id: int) -> dict:
    source, target, edits = plan_merge(db, source_id, target_id)
    changed = apply_edits(edits)
    if source.parent_id is None:
        # 대분류를 합치면 그 소분류들이 새 대분류 맨 아래로 옮겨 간다. 이름은 목록
        # 전체에서 하나뿐이라(`_check_name`) 겹칠 소분류가 없다.
        base = max((m.position for m in _siblings(db, target.id)), default=-1) + 1
        for i, child in enumerate(_siblings(db, source.id)):
            child.parent_id = target.id
            child.position = base + i
    source.merged_into_id = target.id
    source.is_hidden = 1
    return {"changed": changed, **impact(edits)}


def move(db: Session, term_id: int, parent_id: int) -> dict:
    row, parent, edits = plan_move(db, term_id, parent_id)
    changed = apply_edits(edits)
    siblings = _siblings(db, parent.id)
    row.parent_id = parent.id
    row.position = max((s.position for s in siblings), default=-1) + 1
    return {"changed": changed, **impact(edits)}


def set_hidden(db: Session, term_id: int, hidden: bool) -> SectorTerm:
    row = db.get(SectorTerm, term_id)
    if row is None:
        raise TaxonomyError("없는 줄입니다")
    if row.merged_into_id and not hidden:
        raise TaxonomyError("합쳐진 이름은 다시 보이게 할 수 없습니다")
    row.is_hidden = 1 if hidden else 0
    return row


def reorder(db: Session, term_id: int, step: int) -> SectorTerm:
    """같은 부모 안에서 한 칸 위(-1)·아래(+1)로."""
    row = _live(db, term_id)
    siblings = _siblings(db, row.parent_id)
    at = next(i for i, s in enumerate(siblings) if s.id == row.id)
    to = at + (1 if step > 0 else -1)
    if 0 <= to < len(siblings):
        siblings[at], siblings[to] = siblings[to], siblings[at]
    for i, sibling in enumerate(siblings):
        sibling.position = i
    return row
