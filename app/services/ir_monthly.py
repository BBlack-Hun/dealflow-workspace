"""이번 달 어느 투자사가 어느 기업 IR 을 요청했는가 — **한 곳에서 답한다.**

## 왜 한 함수인가

요청 기록이 **두 곳에 갈려 있다.**

- `ir_requests` — 이 앱에서 누른 것. `company_id` 가 외래키다.
- `contact_activities` 중 `kind='ir_request'` — 시트에서 옮겨 온 것.
  `company_id` 가 없고 `company_names` 텍스트(JSON)뿐이라 **이름 문자열로**
  맞춰야 한다.

둘이 덮는 달이 서로 다르다. 한쪽만 읽으면 어떤 달은 통째로 빈다.

화면이 세는 곳과 발송이 세는 곳이 따로 있으면, 문서에 `3곳` 이라고 적어 보내 놓고
화면은 `2곳` 을 보여 주는 날이 온다 — 이 저장소가 여러 번 겪은 부류다(투자사
117명·123명, 화면마다 다른 참고자료 질의). 그래서 세는 자리는 이 파일 하나다.

## 못 맞춘 것은 **지어내지 않는다**

기업명이 잘 안 붙는다. 완전 일치는 일부뿐이고, 부분 일치까지 넓혀도 나머지는
못 맞춘다. `핵심 딜 8개사` 처럼 **개수만 적힌 요청**도 있어서 어느 기업 몫인지
알 길이 없다.

맞출 수 없는 요청은 **세지 않는다.** 대신 몇 건이 그렇게 빠졌는지를 같이
돌려준다(`skipped`) — 조용히 빠지면 아무도 모르고, 문서의 `2곳` 이 진짜 2곳인지
못 맞춰서 2곳인지 구분할 수 없다.

## 가리기는 여기서 하지 않는다

`services/ir_mask.py` 한 곳에 있다. 이 파일은 그것을 부르기만 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import ContactActivity, IrCompany, IrRequest, VcContact
from . import ir_mask
from .sheet_import import normalize_company_name

# 이 문서를 받는 기업. **계약을 마친 곳만**이다 — 계약검토중·미계약 기업에
# 우리가 받은 투자사 반응을 보내면 그것 자체가 영업 자료가 된다.
# 값은 `routers/companies.CONTRACT_LABELS` 의 키다(`무료계약완료`·`유료계약완료`).
CONTRACTED = ("free", "paid")

# 못 맞춘 까닭. 화면에 그대로 뜬다 — 숫자만 보여 주면 무엇을 고쳐야 할지 모른다.
SKIP_NO_MATCH = "기업 이름을 우리 목록에서 못 찾음"
SKIP_AMBIGUOUS = "기업 이름이 여러 기업에 걸림"
SKIP_COUNT_ONLY = "기업 목록 없이 개수만 적힌 요청"


@dataclass(frozen=True)
class Requester:
    """요청한 투자사 한 곳 — **이미 가려진 값**이다.

    원래 이름은 이 자료구조에 담지 않는다. 담아 두면 화면이 실수로 그것을 그릴
    수 있고, 그 실수는 이름이 새고 나서야 발견된다.
    """

    firm: str        # 가려진 회사명
    person: str      # 가려진 담당자 이름
    date: str        # YYYY-MM-DD (모르면 "")
    source: str      # app(이 앱에서 누름) | sheet(시트에서 옮겨 옴)


@dataclass(frozen=True)
class Skip:
    label: str
    count: int


@dataclass
class MonthlyRequests:
    """한 달치 답 전부."""

    month: str
    # {기업 id: 요청한 투자사들}. 요청이 없는 기업은 **키 자체가 없다.**
    by_company: Dict[int, List[Requester]] = field(default_factory=dict)
    # 어느 기업 몫인지 몰라 어디에도 못 붙인 요청들.
    skipped: List[Skip] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return sum(s.count for s in self.skipped)

    def of(self, company_id: int) -> List[Requester]:
        return self.by_company.get(company_id, [])


# ── 기업명 맞추기 ────────────────────────────────────────────────────────────

def _key(name: Optional[str]) -> str:
    """비교용 이름. `(주)`·띄어쓰기·대소문자 차이로 다른 기업이 되지 않게.

    `services/deal_history.py` 가 쓰는 것과 같은 규칙이다 — 두 곳이 다르게 맞추면
    같은 기록이 화면마다 다른 기업에 붙는다.
    """
    return normalize_company_name(name or "").replace(" ", "").lower()


class _Index:
    """이름 → 기업 id. 못 맞추면 **까닭**을 함께 돌려준다."""

    def __init__(self, companies: List[IrCompany]) -> None:
        self._exact: Dict[str, List[int]] = {}
        for company in companies:
            key = _key(company.name)
            if key:
                self._exact.setdefault(key, []).append(company.id)

    def find(self, raw: Optional[str]) -> Tuple[Optional[int], str]:
        key = _key(raw)
        if not key:
            return None, SKIP_NO_MATCH

        hit = self._exact.get(key)
        if hit is not None:
            # 같은 이름의 기업이 둘이면 **고르지 않는다.** 아무거나 고르면
            # 남의 기업 문서에 남의 투자사가 실린다.
            return (hit[0], "") if len(hit) == 1 else (None, SKIP_AMBIGUOUS)

        # 부분 일치. 시트 원문은 `샘플가 주식회사` · `샘플가(구 샘플나)` 처럼
        # 덧붙은 말이 흔해서, 완전 일치만으로는 대부분이 빠진다.
        #
        # **한 곳에만 걸릴 때만** 받아들인다. 여럿에 걸리면 어느 쪽인지 알 수
        # 없고, 짧은 이름(한 글자)은 아무 데나 걸리므로 아예 보지 않는다.
        if len(key) < 2:
            return None, SKIP_NO_MATCH
        found = {ids[0] for other, ids in self._exact.items()
                 if len(ids) == 1 and len(other) >= 2
                 and (key in other or other in key)}
        if len(found) == 1:
            return found.pop(), ""
        return None, (SKIP_AMBIGUOUS if found else SKIP_NO_MATCH)


# ── 두 출처 ──────────────────────────────────────────────────────────────────

def _act_month(act: ContactActivity) -> str:
    """이 활동은 어느 달 것인가.

    날짜가 있으면 날짜가 정하고, 없으면 시트가 적어 둔 달을 쓴다 —
    `routers/contacts._activity_date` 와 같은 순서다.
    """
    if act.happened_at and len(act.happened_at) >= 7:
        return act.happened_at[:7]
    return act.month or ""


def monthly_requests(db: Session, month: str) -> MonthlyRequests:
    """`2026-09` 한 달치. **두 출처를 합쳐** 기업별로 나눈다.

    ### 같은 요청이 두 번 세어지지 않게

    이 앱에서 누른 것과 시트에서 옮겨 온 것이 같은 건일 수 있다(옮겨 온 뒤에
    앱에서도 눌렀다면). 한 달 안에서 **같은 투자사 × 같은 기업**은 한 줄로
    친다 — 문서가 세는 것은 요청 횟수가 아니라 `몇 곳이 요청했는가` 라서,
    두 줄로 두면 `2곳` 이라고 적히지만 실제로는 한 곳이다.
    """
    out = MonthlyRequests(month=month)
    if not month:
        return out

    companies = db.execute(select(IrCompany)).scalars().all()
    index = _Index(companies)
    known = {c.id for c in companies}

    skips: Dict[str, int] = {}

    def skip(reason: str, count: int = 1) -> None:
        skips[reason] = skips.get(reason, 0) + count

    # {(투자사 id, 기업 id): Requester} — 겹치면 **먼저 온 날**을 남긴다.
    picked: Dict[Tuple[int, int], Requester] = {}

    def add(contact: Optional[VcContact], company_id: int,
            date: str, source: str) -> None:
        if contact is None:
            skip(SKIP_NO_MATCH)
            return
        row = Requester(firm=ir_mask.mask_company(contact.firm),
                        person=ir_mask.mask_person(contact.name),
                        date=(date or "")[:10], source=source)
        key = (contact.id, company_id)
        old = picked.get(key)
        if old is None or (row.date and (not old.date or row.date < old.date)):
            picked[key] = row

    # ── 출처 1: 이 앱에서 누른 요청 ──────────────────────────────────────
    rows = db.execute(
        select(IrRequest, VcContact)
        .outerjoin(VcContact, IrRequest.contact_id == VcContact.id)
        .where(IrRequest.requested_at.startswith(month))
    ).all()
    for req, contact in rows:
        # 외래키가 있으면 그것이 답이다 — 이름으로 다시 맞추지 않는다.
        # 사람이 화면에서 고른 기업을 문자열 규칙이 뒤집으면 안 된다.
        company_id = req.company_id if req.company_id in known else None
        if company_id is None:
            company_id, reason = index.find(req.company_name)
            if company_id is None:
                skip(reason)
                continue
        add(contact, company_id, req.requested_at, "app")

    # ── 출처 2: 시트에서 옮겨 온 요청 ────────────────────────────────────
    acts = db.execute(
        select(ContactActivity, VcContact)
        .outerjoin(VcContact, ContactActivity.contact_id == VcContact.id)
        .where(ContactActivity.kind == "ir_request")
    ).all()
    for act, contact in acts:
        if _act_month(act) != month:
            continue
        names = act.companies
        if not names:
            # `핵심 딜 8개사` — 몇 건인지는 알지만 어느 기업 몫인지 모른다.
            # 적힌 개수만큼 빠졌다고 적는다(개수도 없으면 한 건으로 친다).
            skip(SKIP_COUNT_ONLY, max(act.company_count or 0, 1))
            continue
        for name in names:
            company_id, reason = index.find(name)
            if company_id is None:
                skip(reason)
                continue
            add(contact, company_id, act.happened_at or "", "sheet")

    by_company: Dict[int, List[Requester]] = {}
    for (_contact_id, company_id), row in picked.items():
        by_company.setdefault(company_id, []).append(row)
    for rows_ in by_company.values():
        rows_.sort(key=lambda r: (r.date or "9999", r.firm, r.person))

    out.by_company = by_company
    # 많은 것부터 — 무엇을 먼저 손봐야 하는지가 위에 온다.
    out.skipped = [Skip(label=label, count=count)
                   for label, count in sorted(skips.items(), key=lambda kv: -kv[1])]
    return out


# ── 문서가 읽는 것 ───────────────────────────────────────────────────────────

def contracted(db: Session) -> List[IrCompany]:
    """문서를 받는 기업 — 계약을 마친 곳만, 이름 순."""
    from ..routers.companies import contract_key   # 순환 import 를 피해 늦게 부른다

    rows = db.execute(select(IrCompany).order_by(IrCompany.name)).scalars().all()
    return [c for c in rows if contract_key(c.contract_status) in CONTRACTED]


def contract_label(company: IrCompany) -> str:
    """`무료계약완료` 처럼 **화면에 보이는 말**. 말은 이미 있는 곳에서 가져온다 —
    여기서 다시 적으면 IR 기업 현황과 다른 말이 뜬다."""
    from ..routers.companies import CONTRACT_LABELS, contract_key

    key = contract_key(company.contract_status)
    return CONTRACT_LABELS.get(key, key)


def is_month(value: Optional[str]) -> bool:
    """`2026-09` 꼴인가. 주소로 들어온 값을 그대로 믿지 않는다."""
    return bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value or ""))


def this_month() -> str:
    return clock.today().strftime("%Y-%m")


def month_options(db: Session, limit: int = 24) -> List[str]:
    """고를 수 있는 달. **기록이 있는 달** + 이번 달, 최근 것부터.

    달을 손으로 적어 두지 않는다 — 두 출처가 덮는 달이 서로 다르고 앞으로도
    달라진다. 있는 것을 세어서 만든다.
    """
    months = {this_month()}
    for value in db.execute(select(IrRequest.requested_at)).scalars().all():
        if value and len(value) >= 7:
            months.add(value[:7])
    for act in db.execute(
        select(ContactActivity).where(ContactActivity.kind == "ir_request")
    ).scalars().all():
        got = _act_month(act)
        if got:
            months.add(got)
    return sorted((m for m in months if len(m) == 7), reverse=True)[:limit]


def overview(db: Session, month: str) -> dict:
    """목록 화면이 읽는 것 — 계약 기업마다 이번 달 몇 곳이 요청했는가.

    **요청이 0곳인 기업도 목록에 남긴다.** 빼 버리면 계약 기업인데 안 보이는
    까닭을 화면에서 물을 수가 없다 — 진짜로 0곳인 것과 이름을 못 맞춰 0곳이 된
    것이 똑같이 사라지고, 그 둘은 해야 할 일이 정반대다. 대신 문서는 만들지
    않는다(`sendable=False`).
    """
    data = monthly_requests(db, month)
    rows = []
    for company in contracted(db):
        got = data.of(company.id)
        rows.append({
            "company": company,
            "contract_label": contract_label(company),
            "count": len(got),
            # 보낼 수 있는 문서가 되는가. 0곳이면 적을 것이 없다.
            "sendable": bool(got),
            # 한 곳뿐이면 **가릴 상대가 없다.** 받는 대표가 가려진 이름 하나만 보고
            # 누구인지 짐작할 여지가 가장 큰 자리라, 보내는 사람이 알고 보내야 한다.
            "alone": len(got) == 1,
        })
    return {
        "month": month,
        "rows": rows,
        "skipped": data.skipped,
        "skipped_count": data.skipped_count,
        "sendable_count": sum(1 for r in rows if r["sendable"]),
    }


def report(db: Session, company_id: int, month: str) -> Optional[dict]:
    """문서 한 장에 들어가는 것 전부. 없는/계약 안 한 기업이면 `None`.

    화면도 나중의 발송도 **이 함수 하나**를 부른다.
    """
    company = next((c for c in contracted(db) if c.id == company_id), None)
    if company is None:
        return None
    data = monthly_requests(db, month)
    rows = data.of(company.id)
    return {
        "company": company,
        "month": month,
        "requesters": rows,
        "count": len(rows),
        "alone": len(rows) == 1,
        # 적을 것이 없는 달. 문서는 열리되 **보낼 것이 아니라고** 말한다.
        "empty": not rows,
        "skipped": data.skipped,
        "skipped_count": data.skipped_count,
    }
