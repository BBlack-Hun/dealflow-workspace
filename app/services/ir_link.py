"""IR 기업 연결 — 같은 기업이 사는 세 자리를 **사람이** 잇는 곳.

## 왜 필요한가

같은 기업이 세 표에 따로 산다.

  · `IrCompany`          IR 기업 현황. **기업 하나에 줄 하나**인 유일한 표다.
  · `VcContact`          좌측 [스타트업] 명단의 줄. 그 배치는 `firm` 이 기업명이다
                         (`contact_columns.STARTUP_LAYOUT`).
  · `ConsultingCompany`  투자컨설턴트 줄. 기업명은 `company_name` 한 칸에
                         계약일·보수율과 섞여 있어 `startup_handoff.company_name_of`
                         로 꺼낸다.
  · `SeriesACompany`     Series A 이상 딜 소싱 줄(받은 딜 한 건 — 10/26 3단계). `name`.

세 표를 이어 주는 칸이 없었다(`models.IrCompany.contract_received` 주석). 그래서
미팅일 · 담당자 · 연매출처럼 **같은 기업의 같은 사실**을 세 화면이 따로 적고,
어느 쪽이 맞는지 물을 길이 없었다. 잇는 칸을 `IrCompany` 쪽으로 둔다 — 공통
축이 될 수 있는 것은 기업 하나에 줄 하나인 그 표뿐이다(`VcContact.ir_company_id`
· `ConsultingCompany.ir_company_id`).

## 이름이 정확히 하나 맞으면 잇는다 — `자동 연결` 로 적고 풀 수 있게  ★

처음에는 "잇는 것은 사람" 이었다. 10/22 사용자가 바꿨다(결정 2): **새로 생기는 줄**은
이름이 정확히 하나 맞으면 저절로 잇고(`services/company_sync._auto_link`),
[후보가 하나인 줄 일괄 연결] 로 이은 줄과 함께 `ir_link_auto` 로 적어 화면에
`자동 연결` 을 보인다 — 잘못 붙었으면 [연결 풀기]. 사람이 한 줄씩 고른 것은 0 이다.

후보가 둘 이상이거나 없으면 여전히 **사람이 고른다**. 이름이 같다고 같은 기업이라는
보장이 없고, 같은 이름의 IR 기업이 둘인 곳이 운영에 실제로 있다. 잇는 순간에는
양쪽 빈칸만 채운다(다른 값은 덮지 않는다 — `company_sync` 머리말).

## 이름을 맞추는 규칙은 새로 짓지 않는다

`deal_history._key` — `(주)`·띄어쓰기·대소문자를 지우고 **통째로 같을 때만**
같은 이름으로 본다. `startup_handoff.existing_firms`(투자컨설턴트 → 스타트업
`있음` 표시)와 `llm_brief.sent_before` 가 이미 그 규칙을 부른다. 여기서 따로
맞추면 한 화면에서는 `이미 있음` 인 기업이 이 화면에서는 `후보 없음` 이 된다.

**부분일치로 후보를 세우지 않는다** — `가나` 는 `가나다라전자` 한가운데에 우연히
박힌다. 부분일치는 사람이 직접 찾는 검색창에서만 쓴다(`search`).

## 같은 이름의 IR 기업이 둘이면 **하나로 세우지 않는다**

비교용 이름이 같은 IR 기업이 둘 이상이면 그 이름은 `후보 여럿` 이다. 둘 중
하나를 골라 `후보 하나` 로 세우면 일괄 연결이 그쪽에 붙이고, 사람은 다른
하나가 있었다는 것을 볼 기회가 없다.

## 한 IR 기업에 여러 줄이 이어져도 된다

두 팀원의 명단에 같은 기업이 서고, 투자컨설턴트 표는 탭마다 같은 기업이 한
줄씩 실린다. 막지 않되 **몇 줄이 붙어 있는지를 화면에 적는다**(`link_counts`).

## 값이 오간다 — `services/company_sync.py`(10/22, 1단계)

대표자명 · 연락처 · 이메일 · 지역 · 견적서 첨부 여부 · 카톡 연결 여부는 이어진
줄끼리 고칠 때 따라 고친다. 계약 · 미팅 칸은 2단계, Series A 줄은 3단계다.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Union

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from ..models import ConsultingCompany, IrCompany, SeriesACompany, VcContact
from . import startup_handoff
from .deal_history import _key as compare_key
from .room_name import normalize_space

Row = Union[VcContact, ConsultingCompany, SeriesACompany]

#: 화면의 탭. 주소(`/ir-link?tab=…`)와 저장 길이 같은 값을 쓴다.
STARTUP = "startup"
CONSULTING = "consulting"
SERIES_A = "series-a"     # IR 기업 현황의 그 탭 주소(`/companies?tab=series-a`)와 같은 글자
KINDS = (STARTUP, CONSULTING, SERIES_A)
MODELS = (VcContact, ConsultingCompany, SeriesACompany)

#: 줄 하나의 상태. 화면의 거르기 칩과 머리의 숫자가 이 넷을 센다.
LINKED = "linked"     # 사람이 이어 두었다
SINGLE = "single"     # 이름이 같은 IR 기업이 정확히 하나 — 일괄 연결이 받는 줄
MULTI = "multi"       # 이름이 같은 IR 기업이 둘 이상 — 사람이 골라야 한다
NONE = "none"         # 이름이 같은 IR 기업이 없다 — 직접 찾아 잇는다

STATE_LABELS = {
    LINKED: "연결됨",
    SINGLE: "후보 하나",
    MULTI: "후보 여럿",
    NONE: "후보 없음",
}

#: 직접 찾기가 한 번에 보여 주는 수. 그보다 많이 걸리면 더 쳐서 좁힌다.
SEARCH_LIMIT = 30


class NotLinkable(ValueError):
    """이을 수 없는 요청 — 까닭을 글로 담는다(화면이 그대로 적는다)."""


def kind_of(row: Row) -> str:
    if isinstance(row, SeriesACompany):
        return SERIES_A
    return CONSULTING if isinstance(row, ConsultingCompany) else STARTUP


def row_name(row: Row) -> str:
    """이 줄이 말하는 **기업명** — 후보를 세울 때 견주는 글자.

    스타트업 명단 줄은 `firm` 이다. `name` 은 대표 성함이라(`STARTUP_LAYOUT`)
    그것으로 견주면 사람 이름이 기업 후보를 부른다(`room_match.company_name`
    이 같은 까닭을 적어 두었다).

    투자컨설턴트 줄은 `company_name` 에서 **기업명만** 꺼낸다 — 그 칸에는
    계약일·보수율이 함께 적혀 있을 수 있다. 꺼내는 규칙은
    `startup_handoff.company_name_of` 한 곳이다(스타트업 명단으로 보낼 때 서는
    이름과 같아야 한다).
    """
    if isinstance(row, ConsultingCompany):
        return startup_handoff.company_name_of(row.company_name)
    if isinstance(row, SeriesACompany):
        return normalize_space(row.name or "")
    return normalize_space(row.firm or "")


# ── 후보 ────────────────────────────────────────────────────────────────────

class Index:
    """IR 기업 목록을 **비교용 이름으로 한 번** 떠 둔 것.

    줄마다 IR 기업 표를 훑으면 150줄짜리 화면에서 150번 훑는다. 부르는 쪽이
    한 번 만들어 줄마다 넘긴다(`consulting.grant_owner_ids` 와 같은 방식).
    """

    def __init__(self, companies: Iterable[IrCompany]) -> None:
        self.by_id: Dict[int, IrCompany] = {}
        self.by_key: Dict[str, List[IrCompany]] = defaultdict(list)
        for company in companies:
            self.by_id[company.id] = company
            key = compare_key(company.name)
            if key:
                self.by_key[key].append(company)

    def candidates(self, name: Optional[str]) -> List[IrCompany]:
        """이름이 **통째로 같은** IR 기업들. 비교용 이름이 비면 없다."""
        key = compare_key(name)
        if not key:
            return []
        return sorted(self.by_key.get(key, []), key=lambda c: c.id)

    def duplicate_keys(self) -> Dict[str, List[IrCompany]]:
        """비교용 이름이 같은 IR 기업 묶음 — 둘 이상인 것만."""
        return {k: v for k, v in self.by_key.items() if len(v) > 1}


def index(db: Session) -> Index:
    return Index(db.execute(select(IrCompany)).scalars().all())


def linked_company(idx: Index, row: Row) -> Optional[IrCompany]:
    """이 줄에 **이어 둔** IR 기업(목록 안에서 찾는다). 없으면 None."""
    if not row.ir_company_id:
        return None
    return idx.by_id.get(row.ir_company_id)


def state(idx: Index, row: Row) -> str:
    """연결됨 · 후보 하나 · 후보 여럿 · 후보 없음."""
    if linked_company(idx, row) is not None:
        return LINKED
    found = idx.candidates(row_name(row))
    if not found:
        return NONE
    return SINGLE if len(found) == 1 else MULTI


def single_candidate(idx: Index, row: Row) -> Optional[IrCompany]:
    """일괄 연결이 받는 **단 하나의 후보.** 아니면 None.

    이미 이어진 줄 · 후보가 없는 줄 · 후보가 둘 이상인 줄은 전부 None 이다.
    마지막 것이 요점이다 — 같은 이름의 IR 기업이 둘이면 어느 쪽인지는 사람이
    고른다(머리말).
    """
    if state(idx, row) != SINGLE:
        return None
    return idx.candidates(row_name(row))[0]


def search(idx: Index, query: Optional[str],
           limit: int = SEARCH_LIMIT) -> List[IrCompany]:
    """사람이 **직접 찾을 때** — 비교용 이름의 부분일치.

    후보(`candidates`)는 통째로 같을 때만 세우지만, 여기는 사람이 쳐서 고르는
    자리라 부분일치가 맞다(`가나다` 로 `(주)가나다랩스` 를 찾는다). 맞추는
    규칙은 같은 `deal_history._key` 다 — 띄어쓰기·`(주)` 를 지운 채로 견준다.

    통째로 같은 것을 먼저, 그다음 이름 차례로 둔다.
    """
    want = compare_key(query)
    if not want:
        return []
    hits = [c for c in idx.by_id.values() if want in compare_key(c.name)]
    hits.sort(key=lambda c: (compare_key(c.name) != want, c.name or "", c.id))
    return hits[:limit]


def link_counts(db: Session) -> Dict[int, int]:
    """IR 기업마다 **이어 둔 줄 수**(스타트업 명단 + 투자컨설턴트 + Series A).

    한 IR 기업에 여러 줄이 붙는 것은 막지 않는다(머리말). 대신 화면이 그 수를
    적어, 같은 기업이 어디에 몇 번 서 있는지를 사람이 볼 수 있게 한다.
    """
    out: Dict[int, int] = defaultdict(int)
    for model in MODELS:
        rows = db.execute(
            select(model.ir_company_id, func.count())
            .where(model.ir_company_id.isnot(None))
            .group_by(model.ir_company_id)).all()
        for company_id, n in rows:
            out[int(company_id)] += int(n)
    return dict(out)


# ── 잇기 · 풀기 ─────────────────────────────────────────────────────────────

def link(db: Session, row: Row, company: IrCompany, auto: bool = False) -> bool:
    """이 줄을 그 IR 기업에 잇는다. 바뀌었으면 True.

    `auto` — 이름으로 이은 것(일괄 연결)이면 True(`자동 연결` 표시), 사람이 한 줄씩
    고른 것이면 False.

    **줄마다 ORM 으로 고친다** — 한꺼번에 `update()` 로 치우면 flush 를 지나지
    않아 수정 로그가 빈다(`services/edit_log.py` 머리글). 잇고 푼 것은 자기
    줄이라도 남는다(`edit_log.ALWAYS_FIELDS`).

    권한은 여기서 안 본다 — 부르는 쪽(`routers/ir_link.py`)이 화면과 같은
    판정을 태워 줄을 가져온다.
    """
    if company is None or company.id is None:
        raise NotLinkable("이을 IR 기업이 없습니다")
    if row.ir_company_id == company.id:
        if not auto and row.ir_link_auto:
            row.ir_link_auto = 0       # 사람이 같은 기업을 다시 골랐다 — 확인한 것으로 본다
            return True
        return False
    row.ir_company_id = company.id
    row.ir_link_auto = 1 if auto else 0
    return True


def unlink(db: Session, row: Row) -> bool:
    """이 줄의 연결을 푼다. 이어진 것이 없었으면 False."""
    if row.ir_company_id is None:
        return False
    row.ir_company_id = None
    row.ir_link_auto = 0
    return True


# ── 나중 기능이 읽는 자리 ───────────────────────────────────────────────────

def company_for(row: Row, db: Optional[Session] = None) -> Optional[IrCompany]:
    """**이 줄에 이어 둔 IR 기업.** 안 이었으면 None.

    값을 맞추는 일(`company_sync`)은 flush 자리에서 `ir_company_id` 를 바로 본다.

    **후보로 대신하지 않는다** — 후보가 하나뿐이어도 사람이 잇기 전까지는
    None 이다. 이름으로 짐작해 돌려주면 이 함수를 읽는 쪽이 사람이 한 번도
    확인하지 않은 기업에 값을 옮긴다.

    세션을 안 넘기면 그 줄이 붙어 있는 세션으로 읽는다.
    """
    if row is None or not row.ir_company_id:
        return None
    session = db or object_session(row)
    if session is None:
        return None
    return session.get(IrCompany, row.ir_company_id)


# ── 화면 조각 ───────────────────────────────────────────────────────────────

def link_href(kind: str, row_id: int) -> str:
    """그 줄 하나를 펴 놓고 잇는 자리."""
    return f"/ir-link?tab={kind}&row={int(row_id)}"


def company_href(company: IrCompany) -> str:
    """IR 기업 현황에서 그 기업을 찾아 둔 주소(`companies_page` 의 `q`)."""
    from urllib.parse import quote

    return "/companies?q=" + quote(company.name or "")


def badge(row: Row, company: Optional[IrCompany],
          candidates: int = 0) -> dict:
    """수정창·표에 다는 작은 표시 — `IR 기업: ○○ (연결됨)` / `연결 안 됨`.

    판정은 하지 않는다. 이어 둔 기업과 후보 수를 부르는 쪽이 넘긴다 —
    한 줄짜리 수정창은 `badge_for`, 쉰 줄짜리 표는 한 번 뜬 `Index` 로 센다.
    """
    kind = kind_of(row)
    out = {"linked": company is not None,
           "auto": bool(company is not None and getattr(row, "ir_link_auto", 0)),
           "link_href": link_href(kind, row.id),
           "candidates": int(candidates)}
    if company is not None:
        out.update({"name": company.name or "",
                    "company_id": company.id,
                    "company_href": company_href(company)})
    return out


def badges(db: Session, rows: Iterable[Row]) -> Dict[int, dict]:
    """여러 줄의 표시를 한 번에 — `{줄 번호: 표시}`. IR 기업 표는 한 번만 훑는다."""
    idx = index(db)
    out = {}
    for row in rows:
        company = linked_company(idx, row)
        out[row.id] = (badge(row, company) if company is not None
                       else badge(row, None, len(idx.candidates(row_name(row)))))
    return out


def badge_for(db: Session, row: Row) -> dict:
    """줄 하나의 표시(수정창). 이어 두었으면 후보는 세지 않는다."""
    company = company_for(row, db)
    if company is not None:
        return badge(row, company)
    return badge(row, None, len(index(db).candidates(row_name(row))))
